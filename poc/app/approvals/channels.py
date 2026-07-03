"""Approval notification channels — pluggable ABC.

UiOnlyChannel  : no-op (Streamlit UI handles approval inline)
TelegramChannel: sends approval request to a Telegram chat via the Bot API
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from app.observability.logging import get_logger

log = get_logger(__name__)


class ApprovalChannel(ABC):
    """Send an approval request notification. Implementations must never raise."""

    @abstractmethod
    def send(
        self,
        *,
        raw_token: str,
        plan_id: str,
        message: str,
        expires_at: str,
        trigger_case: str,
    ) -> None: ...


class UiOnlyChannel(ApprovalChannel):
    """No-op — Streamlit UI is the only approval surface."""

    def send(self, **_kwargs: object) -> None:
        return


class TelegramChannel(ApprovalChannel):
    """Send an HMAC-signed approval token to a Telegram chat.

    The bot runner (`poc/scripts/run_telegram_bot.py`) must be running separately.
    Uses synchronous httpx so it can be called from any sync context (streaming.py).
    Failures are logged but never raised — Telegram is a secondary surface.
    """

    _SENDMSG = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id

    def send(
        self,
        *,
        raw_token: str,
        plan_id: str,
        message: str,
        expires_at: str,
        trigger_case: str,
    ) -> None:
        text = (
            f"*ACME — Approval Required* ({trigger_case})\n\n"
            f"{message}\n\n"
            f"Expires: `{expires_at}`\n\n"
            f"Approve: `/approve {raw_token}`\n"
            f"Reject:  `/reject {raw_token} <reason>`"
        )
        try:
            r = httpx.post(
                self._SENDMSG.format(token=self._bot_token),
                json={"chat_id": self._chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=10.0,
            )
            r.raise_for_status()
            log.info("TelegramChannel.send ok plan_id=%s", plan_id)
        except Exception as exc:
            log.warning("TelegramChannel.send failed plan_id=%s: %s", plan_id, exc)


def get_channel() -> ApprovalChannel:
    """Return the configured channel based on settings."""
    from app.config import settings

    token = getattr(settings, "telegram_bot_token", "") or ""
    chat_id = getattr(settings, "telegram_chat_id", "") or ""
    if token and chat_id:
        return TelegramChannel(bot_token=token, chat_id=chat_id)
    return UiOnlyChannel()
