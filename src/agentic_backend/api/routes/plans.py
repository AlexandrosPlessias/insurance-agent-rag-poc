"""— Plan approval API endpoints.

POST /plans/{plan_id}/approve          UI path — no token required (session trusted)
POST /plans/{plan_id}/reject           UI path
GET  /plans/{plan_id}/resume/stream    Resume after approval; NDJSON SSE
POST /plans/by-token/approve           Telegram path — HMAC token required
POST /plans/by-token/reject            Telegram path — HMAC token required
GET  /plans/{plan_id}                  Status check (used by UI on page refresh)
"""
import json
from typing import Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from opentelemetry import trace
from pydantic import BaseModel

from agentic_backend.approvals.store import ApprovalStore
from agentic_backend.audit import events as audit_events
from agentic_backend.audit.store import AuditStore
from agentic_backend.config import settings
from agentic_backend.graph.streaming import stream_plan_resume
from agentic_backend.observability.logging import get_logger
from agentic_backend.observability.tracing import annotate_request_span

log = get_logger(__name__)
router = APIRouter(prefix="/plans", tags=["plans"])

_approval_store = ApprovalStore(settings.database_url)
_audit_store = AuditStore(settings.database_url)


class ApproveRequest(BaseModel):
    approver_id: str = "ui_user"
    channel: str = "ui"


class RejectRequest(BaseModel):
    approver_id: str = "ui_user"
    channel: str = "ui"
    reason: str = ""


class TokenApproveRequest(BaseModel):
    token: str
    approver_id: str
    channel: str


class TokenRejectRequest(BaseModel):
    token: str
    approver_id: str
    channel: str
    reason: str = ""


# ---------------------------------------------------------- Telegram (token) paths
# MUST be defined before the /{plan_id}/… routes — FastAPI matches in definition
# order, so "by-token" would otherwise be swallowed by the {plan_id} wildcard.

@router.post("/by-token/approve", status_code=200)
def approve_by_token(body: TokenApproveRequest) -> dict:
    token_row = _approval_store.verify_and_consume_token(
        body.token,
        verdict="approved",
        approver_id=body.approver_id,
        channel=body.channel,
    )
    if token_row is None:
        raise HTTPException(status_code=410, detail="Token expired, already used, or invalid")

    plan_id: str = token_row["plan_id"]
    plan = _approval_store.get_plan(plan_id)
    if plan is None or plan["state"] != "suspended":
        raise HTTPException(status_code=409, detail="Plan is no longer awaiting approval")

    _approval_store.update_plan_state(plan_id, "approved")
    _audit_store.log(
        event_type=audit_events.APPROVAL_GRANTED,
        user_id=plan["user_id"],
        conversation_id=plan.get("conversation_id"),
        payload={"plan_id": plan_id, "approver_id": body.approver_id, "channel": body.channel},
    )
    log.info("Plan approved via token plan_id=%s channel=%s", plan_id, body.channel)
    return {"status": "approved", "plan_id": plan_id}


@router.post("/by-token/reject", status_code=200)
def reject_by_token(body: TokenRejectRequest) -> dict:
    token_row = _approval_store.verify_and_consume_token(
        body.token,
        verdict="rejected",
        approver_id=body.approver_id,
        channel=body.channel,
    )
    if token_row is None:
        raise HTTPException(status_code=410, detail="Token expired, already used, or invalid")

    plan_id: str = token_row["plan_id"]
    plan = _approval_store.get_plan(plan_id)
    if plan is None or plan["state"] != "suspended":
        raise HTTPException(status_code=409, detail="Plan is no longer awaiting approval")

    _approval_store.update_plan_state(plan_id, "rejected")
    _audit_store.log(
        event_type=audit_events.APPROVAL_REJECTED,
        user_id=plan["user_id"],
        conversation_id=plan.get("conversation_id"),
        payload={
            "plan_id": plan_id,
            "approver_id": body.approver_id,
            "channel": body.channel,
            "reason": body.reason,
        },
    )
    log.info("Plan rejected via token plan_id=%s channel=%s", plan_id, body.channel)
    return {"status": "rejected", "plan_id": plan_id}


# ── Telegram poll signal ───────────────────────────────────────────────────────
# React calls start when an ApprovalCard mounts and stop when it unmounts.
# Routes must be async so event.set/clear runs in the event loop (not a thread).

class TelegramPollBody(BaseModel):
    plan_id: str


@router.post("/telegram-poll/start", status_code=204)
async def telegram_poll_start(body: TelegramPollBody) -> None:
    # Lazy import: telegram_bot starts an asyncio event loop on module load
    # when python-telegram-bot is installed; deferring keeps startup fast when
    # Telegram is not configured.
    from agentic_backend.approvals.telegram_bot import signal_start

    signal_start(body.plan_id)


@router.post("/telegram-poll/stop", status_code=204)
async def telegram_poll_stop(body: TelegramPollBody) -> None:
    from agentic_backend.approvals.telegram_bot import signal_stop  # see above

    signal_stop(body.plan_id)


# ------------------------------------------------------------------ UI paths

@router.post("/{plan_id}/approve", status_code=200)
def approve_plan(plan_id: str, body: ApproveRequest) -> dict:
    plan = _approval_store.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    if plan["state"] != "suspended":
        raise HTTPException(
            status_code=409,
            detail=f"Plan state is {plan['state']!r}, not suspended",
        )

    _approval_store.update_plan_state(plan_id, "approved")
    _audit_store.log(
        event_type=audit_events.APPROVAL_GRANTED,
        user_id=plan["user_id"],
        conversation_id=plan.get("conversation_id"),
        payload={"plan_id": plan_id, "approver_id": body.approver_id, "channel": body.channel},
    )
    log.info("Plan approved plan_id=%s by=%s channel=%s", plan_id, body.approver_id, body.channel)
    return {"status": "approved", "plan_id": plan_id}


@router.post("/{plan_id}/reject", status_code=200)
def reject_plan(plan_id: str, body: RejectRequest) -> dict:
    plan = _approval_store.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    if plan["state"] != "suspended":
        raise HTTPException(
            status_code=409,
            detail=f"Plan state is {plan['state']!r}, not suspended",
        )

    _approval_store.update_plan_state(plan_id, "rejected")
    _audit_store.log(
        event_type=audit_events.APPROVAL_REJECTED,
        user_id=plan["user_id"],
        conversation_id=plan.get("conversation_id"),
        payload={
            "plan_id": plan_id,
            "approver_id": body.approver_id,
            "channel": body.channel,
            "reason": body.reason,
        },
    )
    log.info("Plan rejected plan_id=%s by=%s reason=%r", plan_id, body.approver_id, body.reason)
    return {"status": "rejected", "plan_id": plan_id}


@router.get("/{plan_id}/resume/stream")
def resume_plan_stream(plan_id: str) -> StreamingResponse:
    plan = _approval_store.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    if plan["state"] != "approved":
        raise HTTPException(
            status_code=409,
            detail=f"Plan state is {plan['state']!r} — must be 'approved' to resume",
        )

    annotate_request_span(
        trace.get_current_span(),
        user_id=plan.get("user_id"),
        conversation_id=plan.get("conversation_id"),
        plan_id=plan_id,
    )

    def _ndjson() -> Iterator[bytes]:
        for event in stream_plan_resume(plan_id):
            yield (json.dumps(event) + "\n").encode("utf-8")

    return StreamingResponse(_ndjson(), media_type="application/x-ndjson")


@router.get("/{plan_id}")
def get_plan_status(plan_id: str) -> dict:
    plan = _approval_store.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {
        "plan_id": plan["id"],
        "state": plan["state"],
        "pending_step_id": plan.get("pending_step_id"),
        "trigger_case": plan.get("trigger_case"),
        "expires_at": plan.get("expires_at"),
        "conversation_id": plan.get("conversation_id"),
    }
