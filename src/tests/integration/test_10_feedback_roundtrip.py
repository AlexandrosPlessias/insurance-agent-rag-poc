"""Integration test: feedback submission via POST /feedback + audit store read-back.

Write path: POST /feedback → HTTP 200, ok=True, row_id > 0.
Read-back path: direct audit store query (no HTTP read endpoint exists).

Acceptance criteria:
  - POST /feedback returns HTTP 200
  - response ok == True
  - response row_id > 0
  - audit store contains the written row with matching score and plan_id
"""

from datetime import datetime, timezone

import pytest

from agentic_backend.audit import events as audit_events
from agentic_backend.audit.middleware import get_audit_store

_SMOKE_USER = "smoke_test_user"
_TEST_PLAN_ID = "integration-test-plan-0000"


@pytest.mark.integration
def test_feedback_roundtrip(client) -> None:
    """Feedback submitted via the API is persisted and readable from the audit store."""
    payload = {
        "trace_id": _TEST_PLAN_ID,
        "plan_id": _TEST_PLAN_ID,
        "user_id": _SMOKE_USER,
        "score": 1,
        "comment": "integration test thumbs-up",
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    http_resp = client.post("/feedback", json=payload)
    assert http_resp.status_code == 200, (
        f"POST /feedback returned HTTP {http_resp.status_code}: {http_resp.text}"
    )

    body = http_resp.json()
    assert body["ok"] is True, f"expected ok=True, got {body['ok']!r}"
    assert body["row_id"] > 0, (
        f"expected a positive row_id, got {body['row_id']!r}"
    )

    # Read-back via the audit store (no HTTP read endpoint exists)
    audit_store = get_audit_store()
    matching_rows = [
        row
        for row in audit_store.iter_all()
        if row["event_type"] == audit_events.FEEDBACK_RECEIVED
        and row.get("user_id") == _SMOKE_USER
        and row.get("payload", {}).get("plan_id") == _TEST_PLAN_ID
    ]
    assert matching_rows, (
        "No feedback.received row found for the written plan_id — persistence failed"
    )

    last = matching_rows[-1]
    assert last["payload"]["score"] == 1, (
        f"read-back score must be 1, got {last['payload']['score']!r}"
    )
    assert last["payload"]["plan_id"] == _TEST_PLAN_ID, (
        f"read-back plan_id must match, got {last['payload']['plan_id']!r}"
    )
