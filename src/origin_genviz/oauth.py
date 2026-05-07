"""Self-contained OAuth for the upstream MCP server.

origin-genviz used to read tokens out of `~/.claude/.credentials.json`.
That tied us to whatever Claude Code happened to do with the upstream's
auth state, which in practice meant we'd silently break whenever Claude
Code rewrote, namespaced, or skipped the per-server OAuth entry.

This module makes us standalone:
  - FileTokenStorage persists OAuth state to ~/.config/origin-genviz/credentials.json
  - login() runs the full RFC 8414 + dynamic-registration + PKCE flow,
    pops a browser, captures the redirect on a local one-shot HTTP server
  - The MCP SDK's OAuthClientProvider plugs into streamablehttp_client
    as an httpx Auth, transparently refreshing tokens at runtime

When tokens go truly stale (refresh_token rotation lost), the proxy
fails with `LoginRequiredError` and the operator runs `origin-genviz login`.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import anyio
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)

from .config import Config

log = logging.getLogger(__name__)


class LoginRequiredError(RuntimeError):
    """Raised when the proxy needs the operator to (re-)run `origin-genviz login`."""


# -----------------------------------------------------------------------------
# Storage
# -----------------------------------------------------------------------------


class FileTokenStorage(TokenStorage):
    """JSON file persistence for OAuth tokens + dynamic-client info.

    Layout:
        {
          "tokens": { ...OAuthToken... },
          "client": { ...OAuthClientInformationFull... }
        }

    File is mode 0600. Parent dir is created on first write.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text())
        except json.JSONDecodeError:
            log.warning("Could not parse %s; treating as empty.", self._path)
            return {}

    def _save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str))
        os.chmod(tmp, 0o600)
        tmp.replace(self._path)

    async def get_tokens(self) -> OAuthToken | None:
        d = self._load().get("tokens")
        return OAuthToken.model_validate(d) if d else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        data = self._load()
        data["tokens"] = json.loads(tokens.model_dump_json(exclude_none=True))
        self._save(data)
        log.debug("persisted upstream tokens to %s", self._path)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        d = self._load().get("client")
        return OAuthClientInformationFull.model_validate(d) if d else None

    async def set_client_info(self, info: OAuthClientInformationFull) -> None:
        data = self._load()
        data["client"] = json.loads(info.model_dump_json(exclude_none=True))
        self._save(data)
        log.debug("persisted dynamic client registration to %s", self._path)


# -----------------------------------------------------------------------------
# Local callback server + browser launcher (login flow only)
# -----------------------------------------------------------------------------


_CALLBACK_HTML = b"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><title>Origin \xc2\xb7 Auth Complete</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@500;700&family=Inter:wght@400;500&display=swap" rel="stylesheet">
<style>
  body { font-family: Inter, system-ui, sans-serif; background: #FFF1E5; color: #33302E;
         margin: 0; min-height: 100vh; display: grid; place-items: center; }
  .card { background: #FFFCF8; border: 1px solid #E6D9CE; border-radius: 10px;
          padding: 32px 40px; box-shadow: 0 1px 2px rgba(26,22,20,.06); max-width: 480px; }
  .eyebrow { font-family: "Fira Code", ui-monospace, monospace; font-weight: 500;
             font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase;
             color: #903C2E; margin: 0 0 16px; }
  h1 { font-family: "Fira Code", ui-monospace, monospace; font-weight: 700;
       letter-spacing: -0.03em; margin: 0 0 8px; font-size: 28px; }
  p { margin: 0; color: #66605C; line-height: 1.5; }
</style></head>
<body><div class="card">
  <p class="eyebrow">Origin \xc2\xb7 Auth</p>
  <h1>Authentication complete.</h1>
  <p>You can close this tab. origin-genviz now has tokens it can refresh.</p>
</div></body></html>
"""


async def open_browser_redirect(url: str) -> None:
    """Open the auth URL in the user's browser; print as a fallback."""
    print(f"\nOpening browser to authenticate origin-staging:\n  {url}\n")
    try:
        webbrowser.open(url, new=2)
    except Exception as e:  # noqa: BLE001
        log.warning("Could not auto-open browser (%s). Open the URL above manually.", e)


def _run_oneshot_server(port: int, result: dict, done: threading.Event) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            qs = parse_qs(urlparse(self.path).query)
            result["code"] = (qs.get("code") or [None])[0]
            result["state"] = (qs.get("state") or [None])[0]
            error = (qs.get("error") or [None])[0]
            if error:
                result["error"] = error
                result["error_description"] = (qs.get("error_description") or [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(_CALLBACK_HTML)))
            self.end_headers()
            self.wfile.write(_CALLBACK_HTML)
            done.set()

        def log_message(self, format, *args):  # silence stderr access log
            return

    server = HTTPServer(("127.0.0.1", port), Handler)
    server.timeout = 1
    while not done.is_set():
        server.handle_request()


async def wait_for_callback(port: int, timeout: float) -> tuple[str, str | None]:
    """Run a one-shot HTTP listener on `port`. Return (code, state)."""
    result: dict[str, str | None] = {}
    done = threading.Event()

    thread = threading.Thread(
        target=_run_oneshot_server, args=(port, result, done), daemon=True
    )
    thread.start()

    try:
        with anyio.fail_after(timeout):
            await anyio.to_thread.run_sync(done.wait)
    except TimeoutError as e:
        raise LoginRequiredError(
            f"Timed out after {timeout}s waiting for OAuth callback on port {port}."
        ) from e

    if "error" in result:
        raise LoginRequiredError(
            f"OAuth callback returned error: {result['error']} "
            f"({result.get('error_description', '')})"
        )
    code = result.get("code")
    if not code:
        raise LoginRequiredError("OAuth callback did not include an authorization code.")
    return code, result.get("state")


async def _refuse_redirect(url: str) -> None:
    raise LoginRequiredError(
        "origin-genviz needs to (re-)authenticate the upstream MCP server.\n"
        "Run `origin-genviz login` interactively to refresh the OAuth tokens.\n"
        f"(Auth URL would have been: {url})"
    )


async def _refuse_callback() -> tuple[str, str | None]:
    raise LoginRequiredError(
        "origin-genviz refused to launch a callback listener in non-interactive "
        "mode. Run `origin-genviz login` to refresh OAuth tokens."
    )


# -----------------------------------------------------------------------------
# Provider construction
# -----------------------------------------------------------------------------


def _client_metadata(config: Config) -> OAuthClientMetadata:
    return OAuthClientMetadata(
        client_name="origin-genviz",
        redirect_uris=[f"http://localhost:{config.oauth_redirect_port}/callback"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",  # public client + PKCE
        scope=None,
    )


def build_oauth_provider(
    config: Config,
    *,
    interactive: bool,
) -> OAuthClientProvider:
    """Build the SDK's OAuthClientProvider wired to our storage + handlers.

    interactive=True: real browser + local callback server (login command).
    interactive=False: any flow attempt raises LoginRequiredError instead
        of opening a browser. Used by the proxy at runtime.
    """
    storage = FileTokenStorage(config.local_token_path)
    metadata = _client_metadata(config)
    if interactive:
        async def cb() -> tuple[str, str | None]:
            return await wait_for_callback(
                config.oauth_redirect_port, config.oauth_login_timeout_s
            )

        return OAuthClientProvider(
            server_url=config.upstream_url,
            client_metadata=metadata,
            storage=storage,
            redirect_handler=open_browser_redirect,
            callback_handler=cb,
            timeout=config.oauth_login_timeout_s,
        )
    return OAuthClientProvider(
        server_url=config.upstream_url,
        client_metadata=metadata,
        storage=storage,
        redirect_handler=_refuse_redirect,
        callback_handler=_refuse_callback,
        timeout=15,
    )


# -----------------------------------------------------------------------------
# Top-level commands
# -----------------------------------------------------------------------------


async def cmd_login(config: Config) -> int:
    """Run the OAuth flow end-to-end and persist tokens."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    print(f"Authenticating against {config.upstream_url}")
    print(f"Tokens will be stored at {config.local_token_path}")
    provider = build_oauth_provider(config, interactive=True)

    # An MCP initialize handshake forces the auth flow to run end-to-end.
    async with streamablehttp_client(
        config.upstream_url,
        auth=provider,
        timeout=config.oauth_login_timeout_s,
    ) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
    print("Login successful.")
    return 0


def cmd_logout(config: Config) -> int:
    if config.local_token_path.exists():
        config.local_token_path.unlink()
        print(f"Removed {config.local_token_path}")
    else:
        print("No tokens to remove.")
    return 0


async def cmd_status(config: Config) -> int:
    storage = FileTokenStorage(config.local_token_path)
    tokens = await storage.get_tokens()
    client = await storage.get_client_info()
    print(f"upstream:    {config.upstream_url}")
    print(f"token file:  {config.local_token_path}  exists={config.local_token_path.exists()}")
    if client:
        print(f"client_id:   {client.client_id}")
    if tokens:
        print(f"access_token: present (len={len(tokens.access_token)})")
        if tokens.expires_in is not None:
            print(f"expires_in:   {tokens.expires_in}s (relative; advisory)")
        if tokens.refresh_token:
            print(f"refresh_token: present (len={len(tokens.refresh_token)})")
        if tokens.scope:
            print(f"scope:        {tokens.scope}")
    else:
        print("access_token: MISSING — run `origin-genviz login`")
    return 0
