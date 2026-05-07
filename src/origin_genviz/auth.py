"""Resolves the upstream OAuth bearer token, with in-memory refresh.

Source of truth (in order):
1. ORIGIN_STAGING_TOKEN env var (explicit override; no refresh)
2. ~/.claude/.credentials.json -> mcpOAuth["<serverName>|*"]
   The proxy reads this entry and, when the access_token is expired or
   rejected with 401, exchanges the refresh_token at the auth server's
   token endpoint to obtain a fresh access_token. The new token is held
   in memory only — we do NOT write back to the Claude credentials store
   to avoid races with Claude Code's own refresh logic.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

# Refresh slightly before expiry so we don't race expiry mid-call.
_EXPIRY_SKEW_S = 30


class AuthError(RuntimeError):
    pass


@dataclass
class _CredEntry:
    access_token: str
    refresh_token: str | None
    token_endpoint: str | None
    client_id: str | None
    expires_at_ms: float | None  # epoch ms; None if unknown


def _read_cred_entry(credentials_path: Path, server_name: str) -> _CredEntry:
    if not credentials_path.exists():
        raise AuthError(
            f"Credentials file not found at {credentials_path}. "
            "Either run `claude mcp` to authenticate the upstream, "
            "or set ORIGIN_STAGING_TOKEN explicitly."
        )

    try:
        data = json.loads(credentials_path.read_text())
    except json.JSONDecodeError as e:
        raise AuthError(f"Could not parse {credentials_path}: {e}") from e

    mcp_oauth = data.get("mcpOAuth") or {}
    matched: dict | None = None
    for key, entry in mcp_oauth.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("serverName") == server_name:
            matched = entry
            break
        if matched is None and isinstance(key, str) and key.startswith(f"{server_name}|"):
            matched = entry
    if not matched:
        raise AuthError(
            f"No mcpOAuth entry for serverName={server_name!r} in {credentials_path}. "
            "Authenticate the upstream MCP via Claude Code first."
        )

    access_token = matched.get("accessToken")
    if not access_token:
        raise AuthError(f"mcpOAuth entry for {server_name!r} has no accessToken.")

    discovery = matched.get("discoveryState") or {}
    auth_server_url = discovery.get("authorizationServerUrl")
    token_endpoint = _derive_token_endpoint(auth_server_url) if auth_server_url else None

    return _CredEntry(
        access_token=access_token,
        refresh_token=matched.get("refreshToken"),
        token_endpoint=token_endpoint,
        client_id=matched.get("clientId"),
        expires_at_ms=matched.get("expiresAt") if isinstance(matched.get("expiresAt"), (int, float)) else None,
    )


def _derive_token_endpoint(auth_server_url: str) -> str:
    """Best-effort: try the canonical AuthKit path; fallback to discovery."""
    base = auth_server_url.rstrip("/")
    # AuthKit-style endpoint we already verified for staging.
    return f"{base}/oauth2/token"


def _discover_token_endpoint(auth_server_url: str) -> str | None:
    """Fetch RFC 8414 / OIDC discovery to confirm token_endpoint."""
    base = auth_server_url.rstrip("/")
    for path in (
        "/.well-known/oauth-authorization-server",
        "/.well-known/openid-configuration",
    ):
        try:
            r = httpx.get(f"{base}{path}", timeout=10)
            if r.status_code == 200:
                te = r.json().get("token_endpoint")
                if te:
                    return te
        except Exception as e:  # noqa: BLE001
            log.debug("discovery at %s failed: %s", path, e)
    return None


class TokenManager:
    """Provides bearer tokens with on-demand refresh.

    Thread-safe (lock around refresh); per-process in-memory cache. Reads
    the credentials file on every miss so that out-of-band refreshes by
    Claude Code are picked up automatically.
    """

    def __init__(
        self,
        credentials_path: Path,
        server_name: str,
        override: str | None = None,
    ) -> None:
        self._credentials_path = credentials_path
        self._server_name = server_name
        self._override = override

        self._lock = threading.Lock()
        self._cached_access_token: str | None = None
        self._cached_expires_at_ms: float | None = None
        self._cached_refresh_token: str | None = None
        self._cached_token_endpoint: str | None = None
        self._cached_client_id: str | None = None

    def _now_ms(self) -> float:
        return time.time() * 1000

    def _is_cache_fresh(self) -> bool:
        if self._cached_access_token is None:
            return False
        if self._cached_expires_at_ms is None:
            return True  # unknown expiry; trust until rejected
        return self._cached_expires_at_ms - _EXPIRY_SKEW_S * 1000 > self._now_ms()

    def _refresh_via_grant(self) -> bool:
        """Exchange the refresh_token for a new access_token. Returns True on success."""
        if not (self._cached_refresh_token and self._cached_token_endpoint):
            return False
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self._cached_refresh_token,
        }
        if self._cached_client_id:
            data["client_id"] = self._cached_client_id
        log.info("refreshing upstream token via %s", self._cached_token_endpoint)
        try:
            r = httpx.post(
                self._cached_token_endpoint,
                data=data,
                headers={"Accept": "application/json"},
                timeout=15,
            )
        except httpx.HTTPError as e:
            log.warning("token refresh request failed: %s", e)
            return False
        if r.status_code != 200:
            log.warning(
                "token refresh returned %s: %s", r.status_code, r.text[:300]
            )
            return False
        try:
            body = r.json()
        except json.JSONDecodeError:
            log.warning("token refresh body not JSON: %s", r.text[:300])
            return False
        access = body.get("access_token")
        if not access:
            log.warning("token refresh response missing access_token")
            return False
        self._cached_access_token = access
        if "expires_in" in body and isinstance(body["expires_in"], (int, float)):
            self._cached_expires_at_ms = self._now_ms() + body["expires_in"] * 1000
        else:
            self._cached_expires_at_ms = None
        new_refresh = body.get("refresh_token")
        if isinstance(new_refresh, str):
            self._cached_refresh_token = new_refresh
        log.info("upstream token refreshed (expires_in=%s)", body.get("expires_in"))
        return True

    def _reload_from_disk(self) -> None:
        entry = _read_cred_entry(self._credentials_path, self._server_name)
        self._cached_access_token = entry.access_token
        self._cached_expires_at_ms = entry.expires_at_ms
        self._cached_refresh_token = entry.refresh_token
        self._cached_token_endpoint = entry.token_endpoint
        self._cached_client_id = entry.client_id

    def get_token(self, *, force_refresh: bool = False) -> str:
        if self._override:
            return self._override

        with self._lock:
            if force_refresh or not self._is_cache_fresh():
                # Re-read from disk first so that an out-of-band refresh
                # by Claude Code is picked up before we attempt our own.
                if not force_refresh:
                    self._reload_from_disk()
                    if self._is_cache_fresh():
                        assert self._cached_access_token is not None
                        return self._cached_access_token
                else:
                    # On forced refresh (after a 401), try grant exchange first;
                    # fall back to disk if that fails.
                    if self._refresh_via_grant():
                        assert self._cached_access_token is not None
                        return self._cached_access_token
                    self._reload_from_disk()
                    if self._is_cache_fresh():
                        assert self._cached_access_token is not None
                        return self._cached_access_token

                # Either disk token is stale or this is first-load with stale token.
                if self._refresh_via_grant():
                    assert self._cached_access_token is not None
                    return self._cached_access_token

                # Last resort: refresh failed AND disk token is stale.
                expired = (
                    self._cached_expires_at_ms is not None
                    and self._cached_expires_at_ms < self._now_ms()
                )
                if self._cached_access_token and not expired:
                    log.warning(
                        "Refresh failed; using disk access token (expiry unknown)."
                    )
                    return self._cached_access_token
                raise AuthError(
                    "Upstream access token is expired and refresh failed "
                    "(refresh_token likely rotated/invalidated). "
                    "Re-authenticate the upstream MCP server in Claude Code "
                    "(e.g. `claude mcp` and reconnect origin-staging), "
                    "or set ORIGIN_STAGING_TOKEN to a fresh bearer."
                )

            assert self._cached_access_token is not None
            return self._cached_access_token


# Backwards-compatible helper for any callers that just want a token.
def load_bearer_token(
    credentials_path: Path,
    server_name: str,
    override: str | None = None,
) -> str:
    return TokenManager(credentials_path, server_name, override).get_token()
