"""Entry point: `origin-genviz [serve|login|logout|status]`.

Default subcommand is `serve` (stdio MCP). The other subcommands manage
the proxy's own OAuth state for the upstream origin-staging server.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import anyio

from .config import Config
from .oauth import LoginRequiredError, cmd_login, cmd_logout, cmd_status
from .server import run as serve_run


def _load_dotenv_if_present() -> None:
    """Load .env from the project root before reading config.

    Goose / Claude Desktop / etc. typically spawn the proxy with their own
    cwd, not the project's. Look at the package's parent dirs and at cwd
    so a stand-alone `.env` next to pyproject.toml is picked up regardless
    of how the process was launched. Existing env vars always win.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    candidates = [
        Path(__file__).resolve().parent.parent.parent / ".env",  # repo root
        Path.cwd() / ".env",
    ]
    for path in candidates:
        if path.is_file():
            load_dotenv(path, override=False)
            return


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="origin-genviz")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("serve", help="Run the stdio MCP proxy (default).")
    sub.add_parser(
        "login", help="Interactively authenticate the upstream MCP via OAuth."
    )
    sub.add_parser("logout", help="Remove the stored upstream OAuth tokens.")
    sub.add_parser(
        "status", help="Print stored OAuth state (token presence, scope)."
    )

    args = parser.parse_args()
    cmd = args.cmd or "serve"
    _load_dotenv_if_present()
    config = Config.from_env()

    if cmd == "logout":
        # Logout is a sync, no-network operation; do logging anyway.
        _setup_logging(config.log_level)
        sys.exit(cmd_logout(config))

    async def _run() -> int:
        _setup_logging(config.log_level)
        if cmd == "login":
            return await cmd_login(config)
        if cmd == "status":
            return await cmd_status(config)
        # serve
        try:
            await serve_run(config)
            return 0
        except LoginRequiredError as e:
            print(f"\norigin-genviz: {e}\n", file=sys.stderr)
            return 2

    sys.exit(anyio.run(_run))


if __name__ == "__main__":
    main()
