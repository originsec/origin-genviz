from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_UPSTREAM_URL = "https://mcp.staging.originhq.com/mcp"
DEFAULT_UPSTREAM_NAME = "origin-staging"
DEFAULT_CRED_PATH = Path.home() / ".claude" / ".credentials.json"

DEFAULT_CEREBRAS_BASE_URL = "https://api.cerebras.ai/v1"
DEFAULT_CEREBRAS_MODEL = "zai-glm-4.7"
DEFAULT_CEREBRAS_TEMPERATURE = 0.2


@dataclass(frozen=True)
class Config:
    upstream_url: str
    upstream_server_name: str
    credentials_path: Path
    upstream_token_override: str | None

    cerebras_api_key: str | None
    cerebras_base_url: str
    cerebras_model: str
    cerebras_temperature: float

    request_timeout_s: float
    agent_timeout_s: float
    agent_max_input_chars: int
    log_level: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            upstream_url=os.environ.get("ORIGIN_STAGING_URL", DEFAULT_UPSTREAM_URL),
            upstream_server_name=os.environ.get(
                "ORIGIN_STAGING_SERVER_NAME", DEFAULT_UPSTREAM_NAME
            ),
            credentials_path=Path(
                os.environ.get("CLAUDE_CREDENTIALS_PATH", str(DEFAULT_CRED_PATH))
            ).expanduser(),
            upstream_token_override=os.environ.get("ORIGIN_STAGING_TOKEN"),
            cerebras_api_key=os.environ.get("CEREBRAS_API_KEY"),
            cerebras_base_url=os.environ.get(
                "CEREBRAS_BASE_URL", DEFAULT_CEREBRAS_BASE_URL
            ),
            cerebras_model=os.environ.get("CEREBRAS_MODEL", DEFAULT_CEREBRAS_MODEL),
            cerebras_temperature=float(
                os.environ.get("CEREBRAS_TEMPERATURE", DEFAULT_CEREBRAS_TEMPERATURE)
            ),
            request_timeout_s=float(os.environ.get("UPSTREAM_TIMEOUT_S", "60")),
            agent_timeout_s=float(os.environ.get("AGENT_TIMEOUT_S", "30")),
            agent_max_input_chars=int(
                os.environ.get("AGENT_MAX_INPUT_CHARS", "60000")
            ),
            log_level=os.environ.get("ORIGIN_GENVIZ_LOG", "INFO").upper(),
        )
