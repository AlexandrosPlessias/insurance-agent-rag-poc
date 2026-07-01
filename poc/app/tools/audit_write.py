"""Tool: audit_write — persist a structured event to the audit trail."""
from __future__ import annotations

from typing import Any

from app.audit.middleware import get_audit_store
from app.tools import AgentTool


def _run(
    event_type: str,
    payload: dict[str, Any],
    user_id: str = "anonymous",
    trace_id: str | None = None,
    conversation_id: int | None = None,
) -> None:
    """Write one audit row.

    Args:
        event_type: one of the constants in app.audit.events.
        payload: structured payload dict (serialised to JSON in store).
        user_id: owning user identifier.
        trace_id: OTel trace_id for cross-system correlation.
        conversation_id: owning conversation, if available.
    """
    get_audit_store().log(
        event_type=event_type,
        user_id=user_id,
        payload=payload,
        trace_id=trace_id,
        conversation_id=conversation_id,
    )


tool = AgentTool(
    name="audit_write",
    description=(
        "Persist a structured audit event to the compliance audit trail. "
        "Returns None — side-effect only."
    ),
    input_fields={
        "event_type": "event type constant (e.g. 'planner.plan')",
        "payload": "structured dict written as JSON to audit_events",
        "user_id": "owning user identifier",
        "trace_id": "optional OTel trace_id for Aspire correlation",
        "conversation_id": "optional owning conversation id",
    },
    run=_run,
)
