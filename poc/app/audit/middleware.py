"""Helpers for capturing audit events from inside graph nodes.

The graph nodes call `record(state, event_type, payload)` after their
LLM/retrieval step. `current_trace_id()` pulls the active OTel trace_id
so the audit row links back to the Aspire span without each node having
to know about OTel internals.
"""
from __future__ import annotations

from typing import Any

from app.audit.store import AuditStore
from app.config import settings
from app.observability.logging import get_logger

log = get_logger(__name__)

# One process-wide AuditStore. The schema is created lazily on first
# instantiation and inserts open per-call connections (mirrors MemoryStore),
# so concurrent worker threads are safe.
_store: AuditStore | None = None


def get_audit_store() -> AuditStore:
    global _store
    if _store is None:
        _store = AuditStore(settings.audit_sqlite_path)
    return _store


def current_trace_id() -> str | None:
    """Active OTel trace_id formatted as hex, or None if OTel is off."""
    try:
        from opentelemetry import trace as _trace

        span = _trace.get_current_span()
        if span is None:
            return None
        ctx = span.get_span_context()
        if not getattr(ctx, "trace_id", 0):
            return None
        # OTel formats trace_id as a 128-bit int; Aspire shows it hex-padded.
        return f"{ctx.trace_id:032x}"
    except Exception:  # noqa: BLE001 - audit must never crash a request
        return None


def record(
    state: dict[str, Any],
    *,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Convenience: write one audit row from inside a graph node.

    Pulls user_id / conversation_id from the LangGraph state and trace_id
    from the active OTel span. Failures are swallowed (logged at WARN) so
    a broken audit log can never break a user-facing chat turn.
    """
    user_id = str(state.get("user_id") or "anonymous")
    conv_id = state.get("conversation_id")
    try:
        conv_id_int = int(conv_id) if conv_id is not None else None
    except (TypeError, ValueError):
        conv_id_int = None

    trace_id = state.get("audit_trace_id") or current_trace_id()

    get_audit_store().log(
        event_type=event_type,
        user_id=user_id,
        conversation_id=conv_id_int,
        trace_id=trace_id,
        payload=payload,
    )
