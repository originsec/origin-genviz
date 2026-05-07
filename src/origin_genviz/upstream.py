"""Streamable-HTTP MCP client for the upstream origin-staging server.

A short-lived session is opened per call. On a 401 we force a token
refresh via the OAuth refresh_token grant and retry once.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult, Tool

from .auth import TokenManager
from .config import Config

log = logging.getLogger(__name__)


class UpstreamError(RuntimeError):
    pass


def _is_unauthorized(exc: BaseException) -> bool:
    """Walk exception groups / chains looking for an HTTP 401."""
    seen: list[BaseException] = [exc]
    while seen:
        e = seen.pop()
        if isinstance(e, httpx.HTTPStatusError) and e.response is not None:
            if e.response.status_code in (401, 403):
                return True
        if isinstance(e, BaseExceptionGroup):
            seen.extend(e.exceptions)
        if e.__cause__:
            seen.append(e.__cause__)
        if e.__context__ and e.__context__ is not e.__cause__:
            seen.append(e.__context__)
    return False


class Upstream:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._tools_cache: list[Tool] | None = None
        self._token_mgr = TokenManager(
            config.credentials_path,
            config.upstream_server_name,
            config.upstream_token_override,
            server_url=config.upstream_url,
        )

    @asynccontextmanager
    async def _session(self, *, force_refresh_token: bool = False):
        token = self._token_mgr.get_token(force_refresh=force_refresh_token)
        headers = {"Authorization": f"Bearer {token}"}
        async with streamablehttp_client(
            self._config.upstream_url,
            headers=headers,
            timeout=self._config.request_timeout_s,
        ) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session

    async def list_tools(self, *, force: bool = False) -> list[Tool]:
        if self._tools_cache is not None and not force:
            return self._tools_cache

        async def _fetch(force_refresh: bool) -> list[Tool]:
            async with self._session(force_refresh_token=force_refresh) as session:
                result = await session.list_tools()
            return list(result.tools)

        try:
            tools = await _fetch(force_refresh=False)
        except BaseException as e:
            if _is_unauthorized(e):
                log.info("list_tools 401 — refreshing token and retrying once")
                tools = await _fetch(force_refresh=True)
            else:
                raise

        self._tools_cache = tools
        log.info("Discovered %d upstream tools", len(self._tools_cache))
        return self._tools_cache

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None
    ) -> CallToolResult:
        async def _do(force_refresh: bool) -> CallToolResult:
            async with self._session(force_refresh_token=force_refresh) as session:
                return await session.call_tool(name, arguments or {})

        try:
            return await _do(force_refresh=False)
        except BaseException as e:
            if _is_unauthorized(e):
                log.info("call_tool 401 — refreshing token and retrying once")
                return await _do(force_refresh=True)
            raise

    def invalidate_tools_cache(self) -> None:
        self._tools_cache = None
