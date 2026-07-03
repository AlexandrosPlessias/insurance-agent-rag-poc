#!/usr/bin/env python3
"""Phase 12 Telegram approval bot entry point.

Usage (from poc/ with venv active):
    python scripts/run_telegram_bot.py

Requires TELEGRAM_BOT_TOKEN in poc/.env.
The FastAPI backend must be running on UI_API_URL.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.approvals.telegram_bot import build_app
from app.config import settings
from app.observability.logging import get_logger

log = get_logger(__name__)


def main() -> None:
    token = getattr(settings, "telegram_bot_token", "") or ""
    if not token:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is not set. Add it to poc/.env and restart."
        )
    log.info("Starting Telegram approval bot (api=%s) …", settings.ui_api_url)
    app = build_app(token)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
