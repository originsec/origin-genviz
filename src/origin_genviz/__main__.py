"""Stdio entry point: `origin-genviz` (or `python -m origin_genviz`)."""
from __future__ import annotations

import anyio

from .config import Config
from .server import run


def main() -> None:
    config = Config.from_env()
    anyio.run(run, config)


if __name__ == "__main__":
    main()
