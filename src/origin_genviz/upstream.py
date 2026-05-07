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
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult, Tool

from .config import Config
from .oauth import build_oauth_provider

log = logging.getLogger(__name__)


class Upstream:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._tools_cache: list[Tool] | None = None
        self._provider = (
            None
            if config.upstream_token_override
            else build_oauth_provider(config, interactive=False)
        )

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
            ctx = streamablehttp_client(
                self._config.upstream_url,
                auth=self._provider,
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
        self._tools_cache = list(result.tools)
        log.info("Discovered %d upstream tools", len(self._tools_cache))
        return self._tools_cache

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None
    ) -> CallToolResult:
        async with self._session() as session:
            return await session.call_tool(name, arguments or {})

    def invalidate_tools_cache(self) -> None:
        self._tools_cache = None
