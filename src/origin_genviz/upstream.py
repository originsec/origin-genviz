"""Streamable-HTTP MCP client for the upstream origin-staging server.

Auth resolution (in order):
  1. ORIGIN_STAGING_TOKEN env var → static bearer header (no refresh)
  2. OAuthClientProvider against the upstream's discovered auth server
     using ~/.config/origin-genviz/credentials.json for storage

The provider transparently refreshes the access token using the stored
refresh_token. If refresh fails (e.g. user revoked, refresh_token rotated
out of our knowledge), the proxy raises LoginRequiredError, which the
operator resolves by running `origin-genviz login`.
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.auth.utils import (
    build_oauth_authorization_server_metadata_discovery_urls,
    build_protected_resource_metadata_discovery_urls,
    create_oauth_metadata_request,
    handle_auth_metadata_response,
    handle_protected_resource_response,
)
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult, Tool

from .config import Config
from .oauth import build_oauth_provider

log = logging.getLogger(__name__)


async def _prefetch_oauth_metadata(provider, server_url: str) -> None:
    """Discover OAuth metadata so the provider knows the real token endpoint.

    The MCP SDK persists tokens and client_info to disk but not the
    discovered metadata.  When the provider is recreated from storage it
    falls back to ``server_url + /token`` for refresh, which is often
    wrong (e.g. the upstream uses a separate auth server).  We do the
    discovery here with plain httpx and attach the results to the
    provider context before the first request.
    """
    if provider.context.oauth_metadata is not None:
        return

    async with httpx.AsyncClient() as client:
        # 1. Protected resource metadata
        prm_urls = build_protected_resource_metadata_discovery_urls(
            None, server_url
        )
        for url in prm_urls:
            req = create_oauth_metadata_request(url)
            resp = await client.send(req)
            prm = await handle_protected_resource_response(resp)
            if prm:
                provider.context.protected_resource_metadata = prm
                if prm.authorization_servers:
                    provider.context.auth_server_url = str(
                        prm.authorization_servers[0]
                    )
                break

        # 2. Authorization server metadata
        if provider.context.auth_server_url is None:
            return  # nothing to discover
        asm_urls = build_oauth_authorization_server_metadata_discovery_urls(
            provider.context.auth_server_url, server_url
        )
        for url in asm_urls:
            req = create_oauth_metadata_request(url)
            resp = await client.send(req)
            ok, asm = await handle_auth_metadata_response(resp)
            if not ok:
                break
            if asm:
                provider.context.oauth_metadata = asm
                break


def _repair_json_schema(node: object) -> None:
    """In-place repair of common JSON-Schema lapses in upstream tool schemas.

    Strict validators (e.g. VS Code's MCP chat client) reject schemas where
    `{"type": "array"}` has no `items` clause. Goose / Claude Code accept
    them. We patch in a permissive `items: {}` so all clients can validate
    without narrowing what's accepted by the upstream.

    Walks every value reachable from the root since tool schemas nest
    deeply (oneOf / anyOf / properties / items / additionalProperties /
    patternProperties / etc.).
    """
    if isinstance(node, dict):
        t = node.get("type")
        is_array = t == "array" or (isinstance(t, list) and "array" in t)
        if is_array and "items" not in node:
            node["items"] = {}
        for v in node.values():
            _repair_json_schema(v)
    elif isinstance(node, list):
        for v in node:
            _repair_json_schema(v)


class Upstream:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._tools_cache: list[Tool] | None = None

    @asynccontextmanager
    async def _session(self):
        if self._config.upstream_token_override:
            ctx = streamablehttp_client(
                self._config.upstream_url,
                headers={
                    "Authorization": f"Bearer {self._config.upstream_token_override}"
                },
                timeout=self._config.request_timeout_s,
            )
        else:
            # Build a fresh provider every session so tokens saved after startup
            # (e.g. by a later `origin-genviz login`) are picked up immediately.
            provider = build_oauth_provider(self._config, interactive=False)
            # The MCP SDK's _initialize() loads tokens from disk but leaves
            # token_expiry_time as None, so is_token_valid() incorrectly
            # returns True for stale tokens. Force a refresh by treating any
            # stored token as expired.
            await provider._initialize()
            if (
                provider.context.current_tokens
                and provider.context.token_expiry_time is None
            ):
                provider.context.token_expiry_time = time.time() - 1
            # The SDK also does not persist discovered metadata, so refresh
            # would hit the wrong token endpoint. Prefetch it here.
            await _prefetch_oauth_metadata(provider, self._config.upstream_url)
            ctx = streamablehttp_client(
                self._config.upstream_url,
                auth=provider,
                timeout=self._config.request_timeout_s,
            )
        async with ctx as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session

    async def list_tools(self, *, force: bool = False) -> list[Tool]:
        if self._tools_cache is not None and not force:
            return self._tools_cache
        async with self._session() as session:
            result = await session.list_tools()
        tools = list(result.tools)
        for t in tools:
            _repair_json_schema(t.inputSchema)
            if t.outputSchema is not None:
                _repair_json_schema(t.outputSchema)
        self._tools_cache = tools
        log.info("Discovered %d upstream tools", len(self._tools_cache))
        return self._tools_cache

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None
    ) -> CallToolResult:
        async with self._session() as session:
            return await session.call_tool(name, arguments or {})

    def invalidate_tools_cache(self) -> None:
        self._tools_cache = None
