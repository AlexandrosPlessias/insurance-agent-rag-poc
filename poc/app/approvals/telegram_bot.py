"""Phase 12 Telegram bot — /approve and /reject command handlers.

Runs as a standalone process via poc/scripts/run_telegram_bot.py.
Never touches the DB directly — delegates all decisions to the FastAPI backend.

Commands accepted:
  /approve <token>           — approve the pending plan
  /approval <token>          — alias for /approve
  /reject <token> [reason]   — reject with optional reason
"""
from __future__ import annotations

import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from app.config import settings
from app.observability.logging import get_logger

log = get_logger(__name__)

_API_BASE = settings.ui_api_url


async def approve_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    log.info(
        "approve_handler received chat_id=%s args=%r",
        update.effective_chat.id,
        context.args,
    )
    if not context.args:
        await update.message.reply_text("Usage: /approve <token>")
        return

    raw_token = context.args[0]
    approver_id = str(update.effective_chat.id)
    url = f"{_API_BASE}/plans/by-token/approve"
    log.info("approve_handler calling url=%s token_prefix=%s", url, raw_token[:8])

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                url,
                json={"token": raw_token, "approver_id": approver_id, "channel": "telegram"},
                timeout=15.0,
            )
    except Exception as exc:
        log.warning("approve_handler: httpx error url=%s exc=%s", url, exc)
        await update.message.reply_text("Could not reach the approval API. Please try again.")
        return

    log.info("approve_handler response status=%s body=%r", r.status_code, r.text[:200])
    if r.status_code == 200:
        await update.message.reply_text("Plan approved. It will resume on the next UI refresh.")
    elif r.status_code == 410:
        await update.message.reply_text("Token expired or already used.")
    elif r.status_code == 409:
        await update.message.reply_text("Plan is no longer awaiting approval.")
    else:
        await update.message.reply_text(f"Approval failed (HTTP {r.status_code}).")


async def reject_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    log.info(
        "reject_handler received chat_id=%s args=%r",
        update.effective_chat.id,
        context.args,
    )
    if not context.args:
        await update.message.reply_text("Usage: /reject <token> [reason]")
        return

    raw_token = context.args[0]
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else ""
    approver_id = str(update.effective_chat.id)
    url = f"{_API_BASE}/plans/by-token/reject"
    log.info("reject_handler calling url=%s token_prefix=%s reason=%r", url, raw_token[:8], reason)

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                url,
                json={
                    "token": raw_token,
                    "approver_id": approver_id,
                    "channel": "telegram",
                    "reason": reason,
                },
                timeout=15.0,
            )
    except Exception as exc:
        log.warning("reject_handler: httpx error url=%s exc=%s", url, exc)
        await update.message.reply_text("Could not reach the approval API. Please try again.")
        return

    log.info("reject_handler response status=%s body=%r", r.status_code, r.text[:200])
    if r.status_code == 200:
        await update.message.reply_text("Plan rejected.")
    elif r.status_code == 410:
        await update.message.reply_text("Token expired or already used.")
    else:
        await update.message.reply_text(f"Rejection failed (HTTP {r.status_code}).")


def build_app(token: str) -> Application:
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("approve", approve_handler))
    app.add_handler(CommandHandler("approval", approve_handler))  # alias
    app.add_handler(CommandHandler("reject", reject_handler))
    return app
