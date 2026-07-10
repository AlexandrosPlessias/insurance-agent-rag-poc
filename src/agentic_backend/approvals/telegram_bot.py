"""Telegram bot — event-driven polling.

Runs as a background asyncio task inside FastAPI (started in the lifespan).
Polls Telegram ONLY while an ApprovalCard is visible in the React UI.

Signal flow
-----------
  ApprovalCard mounts  → POST /plans/telegram-poll/start → signal_start(plan_id)
                          → _poll_event.set()  → bot wakes, polls Telegram
  ApprovalCard unmounts → POST /plans/telegram-poll/stop  → signal_stop(plan_id)
                          → (last plan removed) → _poll_event.clear() → bot sleeps
"""
from __future__ import annotations

import asyncio
import logging

import httpx
from telegram import Bot, Update
from telegram.error import NetworkError, TimedOut

from agentic_backend.config import settings
from agentic_backend.observability.logging import get_logger

log = get_logger(__name__)

_API_BASE = f"http://{settings.api_host}:{settings.api_port}"
_POLL_TIMEOUT = 10  # Telegram long-poll timeout (seconds)

# Silence chatty library loggers — only our logger emits INFO.
for _noisy in ("httpx", "httpx._client", "telegram", "telegram.ext", "apscheduler"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# ── shared signal (set by plans router, awaited by run()) ─────────────────────

_poll_event: asyncio.Event = asyncio.Event()
_active_plan_ids: set[str] = set()


def signal_start(plan_id: str) -> None:
    """Called (from async route) when an ApprovalCard mounts."""
    _active_plan_ids.add(plan_id)
    _poll_event.set()
    log.info("telegram-poll start plan_id=%s active=%d", plan_id, len(_active_plan_ids))


def signal_stop(plan_id: str) -> None:
    """Called (from async route) when an ApprovalCard unmounts."""
    _active_plan_ids.discard(plan_id)
    if not _active_plan_ids:
        _poll_event.clear()
        log.info("telegram-poll stop — all gates resolved, bot idle")
    else:
        log.info("telegram-poll stop plan_id=%s active=%d", plan_id, len(_active_plan_ids))


# ── startup helper ────────────────────────────────────────────────────────────

async def _drain_stale_updates(bot: Bot) -> int:
    """Skip any updates already queued in Telegram before this session started.

    Prevents old /approve commands from previous sessions being replayed
    on startup and causing 409 errors on the approval API.
    Returns the offset to use for the first real get_updates call.
    """
    try:
        updates = await bot.get_updates(timeout=0, allowed_updates=["message"])
        if updates:
            offset = updates[-1].update_id + 1
            log.info("Drained %d stale Telegram update(s), starting at offset=%d", len(updates), offset)
            return offset
    except Exception as exc:
        log.debug("_drain_stale_updates: %s", exc)
    return 0


# ── command handlers ───────────────────────────────────────────────────────────

async def _approve(bot: Bot, update: Update, args: list[str]) -> None:
    if not args:
        await update.message.reply_text("Usage: /approve <token>")
        return
    raw_token = args[0]
    approver_id = str(update.effective_chat.id)
    url = f"{_API_BASE}/plans/by-token/approve"
    log.info("approve token_prefix=%s", raw_token[:8])
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                url,
                json={"token": raw_token, "approver_id": approver_id, "channel": "telegram"},
                timeout=15.0,
            )
    except Exception as exc:
        log.warning("approve: httpx error — %s", exc)
        await update.message.reply_text("Could not reach the approval API. Please try again.")
        return
    if r.status_code == 200:
        await update.message.reply_text("Plan approved. It will resume on the next UI refresh.")
    elif r.status_code == 410:
        await update.message.reply_text("Token expired or already used.")
    elif r.status_code == 409:
        await update.message.reply_text("Plan is no longer awaiting approval.")
    else:
        await update.message.reply_text(f"Approval failed (HTTP {r.status_code}).")


async def _reject(bot: Bot, update: Update, args: list[str]) -> None:
    if not args:
        await update.message.reply_text("Usage: /reject <token> [reason]")
        return
    raw_token = args[0]
    reason = " ".join(args[1:]) if len(args) > 1 else ""
    approver_id = str(update.effective_chat.id)
    url = f"{_API_BASE}/plans/by-token/reject"
    log.info("reject token_prefix=%s reason=%r", raw_token[:8], reason)
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
        log.warning("reject: httpx error — %s", exc)
        await update.message.reply_text("Could not reach the approval API. Please try again.")
        return
    if r.status_code == 200:
        await update.message.reply_text("Plan rejected.")
    elif r.status_code == 410:
        await update.message.reply_text("Token expired or already used.")
    else:
        await update.message.reply_text(f"Rejection failed (HTTP {r.status_code}).")


async def _dispatch(bot: Bot, update: Update) -> None:
    if not update.message or not update.message.text:
        return
    parts = update.message.text.strip().split()
    cmd = parts[0].lower().lstrip("/").split("@")[0]  # handle /cmd@BotName
    args = parts[1:]
    if cmd in ("approve", "approval"):
        await _approve(bot, update, args)
    elif cmd == "reject":
        await _reject(bot, update, args)


# ── main loop ──────────────────────────────────────────────────────────────────

async def run(token: str) -> None:
    """Background task: sleeps until UI signals, then polls Telegram."""
    bot = Bot(token=token)
    offset = await _drain_stale_updates(bot)

    log.info("Telegram bot ready — waiting for approval gate signal")

    while True:
        # Block here with zero CPU/network until ApprovalCard mounts.
        await _poll_event.wait()

        # ── active: at least one ApprovalCard is visible ──────────────────────
        log.info("Approval gate active — polling Telegram for /approve or /reject")

        while _poll_event.is_set():
            try:
                updates = await bot.get_updates(
                    offset=offset,
                    timeout=_POLL_TIMEOUT,
                    allowed_updates=["message"],
                )
                for update in updates:
                    offset = update.update_id + 1
                    await _dispatch(bot, update)
            except (TimedOut, NetworkError) as exc:
                log.debug("get_updates: %s", exc)
            except asyncio.CancelledError:
                raise  # propagate so FastAPI lifespan can shut down cleanly
            except Exception as exc:
                log.warning("get_updates unexpected error — %s", exc)
                await asyncio.sleep(2)

        log.info("Approval resolved — Telegram polling stopped, bot idle")
