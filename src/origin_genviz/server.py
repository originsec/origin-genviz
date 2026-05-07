"""Stdio MCP proxy: re-exposes every origin-staging tool, augments
results with an Origin-branded visualization when the agent decides
one is warranted.

Uses the MCP Python SDK's lowlevel Server so we can register the
upstream's exact tool schemas verbatim and preserve isError /
structuredContent on responses.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

import mcp.types as types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from .config import Config
from .oauth import LoginRequiredError
from .upstream import Upstream
from .viz_agent import VizAgent, VizDecision

log = logging.getLogger(__name__)


SERVER_NAME = "origin-genviz"
SERVER_VERSION = "0.1.0"
# Canonical MCP Apps / mcp-ui mime type. Clients that don't recognize the
# `;profile=mcp-app` parameter still render the resource as plain HTML.
UI_MIME = "text/html;profile=mcp-app"


def _extract_text(content_blocks: list[types.ContentBlock]) -> str:
    """Flatten upstream content into a single string for the agent."""
    parts: list[str] = []
    for block in content_blocks:
        # Prefer structured access; fall back to dict-style for safety.
        btype = getattr(block, "type", None) or (
            block.get("type") if isinstance(block, dict) else None
        )
        if btype == "text":
            text = getattr(block, "text", None) or (
                block.get("text") if isinstance(block, dict) else None
            )
            if text:
                parts.append(text)
        elif btype == "resource":
            res = getattr(block, "resource", None) or (
                block.get("resource") if isinstance(block, dict) else None
            )
            if res is None:
                continue
            text = getattr(res, "text", None) or (
                res.get("text") if isinstance(res, dict) else None
            )
            if text:
                parts.append(text)
    return "\n\n".join(parts)


def _make_ui_resource(tool_name: str, html: str, title: str | None) -> types.EmbeddedResource:
    """Return an MCP embedded resource using the ui:// scheme (MCP App UI / mcp-ui)."""
    safe_tool = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in tool_name)
    uri = f"ui://origin-genviz/{safe_tool}/{uuid.uuid4().hex[:12]}"
    annotations = None
    if title:
        annotations = types.Annotations(audience=["user"], priority=0.9)
    return types.EmbeddedResource(
        type="resource",
        resource=types.TextResourceContents(
            uri=uri,
            mimeType=UI_MIME,
            text=html,
        ),
        annotations=annotations,
    )


def _unwrap(exc: BaseException) -> BaseException:
    """Walk ExceptionGroups / chains for a meaningful inner exception.

    streamable-http opens its own anyio TaskGroup and re-raises errors as
    `BaseExceptionGroup`s, which makes JSON-RPC error messages opaque
    ("unhandled errors in a TaskGroup"). Surface the original where we can.
    """
    seen: set[int] = set()

    def walk(e: BaseException) -> BaseException | None:
        if id(e) in seen:
            return None
        seen.add(id(e))
        if isinstance(e, LoginRequiredError):
            return e
        if isinstance(e, BaseExceptionGroup):
            for sub in e.exceptions:
                hit = walk(sub)
                if hit is not None:
                    return hit
        for chained in (e.__cause__, e.__context__):
            if chained is not None and chained is not e:
                hit = walk(chained)
                if hit is not None:
                    return hit
        return None

    return walk(exc) or exc


def build_server(config: Config, upstream: Upstream, agent: VizAgent) -> Server:
    server: Server = Server(SERVER_NAME, version=SERVER_VERSION)

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        try:
            tools = await upstream.list_tools()
        except BaseException as e:
            inner = _unwrap(e)
            if isinstance(inner, LoginRequiredError):
                # Re-raise as a regular RuntimeError so the framework
                # converts it to a clean JSON-RPC error.
                raise RuntimeError(str(inner)) from inner
            raise
        # Pass through verbatim. The proxy advertises the upstream's exact
        # name/description/schema so callers see no behavioural difference.
        return list(tools)

    async def _handle_call_tool_request(
        req: types.CallToolRequest,
    ) -> types.ServerResult:
        name = req.params.name
        arguments = req.params.arguments or {}
        log.info("proxying tool=%s args=%s", name, list(arguments.keys()))

        try:
            upstream_result = await upstream.call_tool(name, arguments)
        except BaseException as e:  # noqa: BLE001
            log.exception("upstream tool call failed")
            inner = _unwrap(e)
            err = types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=f"origin-genviz: upstream call failed: {inner}",
                    )
                ],
                isError=True,
            )
            return types.ServerResult(err)

        content: list[types.ContentBlock] = list(upstream_result.content or [])
        is_error = bool(upstream_result.isError)
        structured = getattr(upstream_result, "structuredContent", None)

        decision: VizDecision | None = None
        if not is_error and agent.enabled:
            text_for_agent = _extract_text(content)
            if structured is not None and not text_for_agent:
                import json as _json

                try:
                    text_for_agent = _json.dumps(structured, ensure_ascii=False)
                except (TypeError, ValueError):
                    text_for_agent = repr(structured)
            decision = await agent.decide(name, arguments, text_for_agent, is_error)

        if decision and decision.visualize and decision.html:
            content.append(_make_ui_resource(name, decision.html, decision.title))
            log.info(
                "appended viz for tool=%s (rationale=%s)", name, decision.rationale
            )
        elif decision and decision.rationale:
            log.debug("no viz for %s: %s", name, decision.rationale)

        result = types.CallToolResult(
            content=content,
            isError=is_error,
            structuredContent=structured,
        )
        return types.ServerResult(result)

    # Register directly on request_handlers so we have full control over
    # the response shape (preserve isError + structuredContent verbatim).
    server.request_handlers[types.CallToolRequest] = _handle_call_tool_request

    return server


async def run(config: Config) -> None:
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    upstream = Upstream(config)
    agent = VizAgent(config)
    if not agent.enabled:
        log.warning(
            "Cerebras API key not configured (CEREBRAS_API_KEY unset). "
            "Proxy will pass tool results through unchanged."
        )

    # Best-effort warm fetch. If it fails (e.g. expired token), log loudly
    # and continue — list_tools will retry on the first real client request,
    # giving the operator a chance to fix auth without restarting.
    try:
        await upstream.list_tools()
    except Exception as e:  # noqa: BLE001
        log.warning(
            "Could not discover upstream tools at startup: %s. "
            "The proxy will retry on first list_tools request.",
            e,
        )

    server = build_server(config, upstream, agent)

    init_options = InitializationOptions(
        server_name=SERVER_NAME,
        server_version=SERVER_VERSION,
        capabilities=server.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities={},
        ),
    )

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, init_options)
