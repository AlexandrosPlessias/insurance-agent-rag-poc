#!/usr/bin/env python3
"""Phase 12 Telegram approval bot entry point.

Usage (from poc/ with venv active):
    python scripts/run_telegram_bot.py

Requires TELEGRAM_BOT_TOKEN in poc/.env.
The FastAPI backend must be running on API_HOST:API_PORT.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agentic_backend.approvals.telegram_bot as telegram_bot
from agentic_backend.config import settings
from agentic_backend.observability.logging import get_logger

log = get_logger(__name__)


async def main() -> None:
    token = getattr(settings, "telegram_bot_token", "") or ""
    if not token:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is not set. Add it to poc/.env and restart."
        )
    log.info("Starting Telegram approval bot (api=%s:%s) …", settings.api_host, settings.api_port)
    await telegram_bot.run(token)


if __name__ == "__main__":
    asyncio.run(main())
