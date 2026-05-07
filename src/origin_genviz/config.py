from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_UPSTREAM_URL = "https://mcp.staging.originhq.com/mcp"
DEFAULT_LOCAL_TOKEN_PATH = (
    Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    / "origin-genviz"
    / "credentials.json"
)

DEFAULT_CEREBRAS_BASE_URL = "https://api.cerebras.ai/v1"
DEFAULT_CEREBRAS_MODEL = "zai-glm-4.7"
DEFAULT_CEREBRAS_TEMPERATURE = 0.2

DEFAULT_OAUTH_REDIRECT_PORT = 53217
DEFAULT_OAUTH_LOGIN_TIMEOUT_S = 300.0

DEFAULT_VIZ_DENYLIST = frozenset({"analytics_describe_schema"})


def _parse_name_set(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


@dataclass(frozen=True)
class Config:
    # Upstream MCP server
    upstream_url: str
    upstream_token_override: str | None  # short-circuits OAuth entirely

    # Local OAuth state (this proxy's own credentials, NOT Claude Code's)
    local_token_path: Path
    oauth_redirect_port: int
    oauth_login_timeout_s: float

    # Cerebras
    cerebras_api_key: str | None
    cerebras_base_url: str
    cerebras_model: str
    cerebras_temperature: float

    # Visualization scope. Empty allowlist → all tools eligible (default).
    # Names match the upstream tool name verbatim (no prefix). When both
    # are set, allowlist wins; explicit deny then prunes.
    viz_allowlist: frozenset[str]
    viz_denylist: frozenset[str]

    # Tuning
    request_timeout_s: float
    agent_timeout_s: float
    agent_max_input_chars: int
    log_level: str

    def viz_eligible(self, tool_name: str) -> bool:
        if tool_name in self.viz_denylist:
            return False
        if self.viz_allowlist and tool_name not in self.viz_allowlist:
            return False
        return True

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            upstream_url=os.environ.get("ORIGIN_STAGING_URL", DEFAULT_UPSTREAM_URL),
            upstream_token_override=os.environ.get("ORIGIN_STAGING_TOKEN"),
            local_token_path=Path(
                os.environ.get(
                    "ORIGIN_GENVIZ_TOKEN_PATH", str(DEFAULT_LOCAL_TOKEN_PATH)
                )
            ).expanduser(),
            oauth_redirect_port=int(
                os.environ.get("ORIGIN_GENVIZ_OAUTH_PORT", DEFAULT_OAUTH_REDIRECT_PORT)
            ),
            oauth_login_timeout_s=float(
                os.environ.get(
                    "ORIGIN_GENVIZ_OAUTH_TIMEOUT_S", DEFAULT_OAUTH_LOGIN_TIMEOUT_S
                )
            ),
            cerebras_api_key=os.environ.get("CEREBRAS_API_KEY"),
            cerebras_base_url=os.environ.get(
                "CEREBRAS_BASE_URL", DEFAULT_CEREBRAS_BASE_URL
            ),
            cerebras_model=os.environ.get("CEREBRAS_MODEL", DEFAULT_CEREBRAS_MODEL),
            cerebras_temperature=float(
                os.environ.get("CEREBRAS_TEMPERATURE", DEFAULT_CEREBRAS_TEMPERATURE)
            ),
            viz_allowlist=_parse_name_set(os.environ.get("ORIGIN_GENVIZ_VIZ_ALLOW")),
            viz_denylist=DEFAULT_VIZ_DENYLIST
            | _parse_name_set(os.environ.get("ORIGIN_GENVIZ_VIZ_DENY")),
            request_timeout_s=float(os.environ.get("UPSTREAM_TIMEOUT_S", "60")),
            agent_timeout_s=float(os.environ.get("AGENT_TIMEOUT_S", "30")),
            agent_max_input_chars=int(
                os.environ.get("AGENT_MAX_INPUT_CHARS", "60000")
            ),
            log_level=os.environ.get("ORIGIN_GENVIZ_LOG", "INFO").upper(),
        )
