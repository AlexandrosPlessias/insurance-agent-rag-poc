"""Phase 11 feedback endpoint.

POST /feedback — record a thumbs-up (+1) or thumbs-down (-1) verdict on
any assistant turn identified by its OTel trace_id.

Storage: a `feedback.received` row in the existing audit_events table
(no new table — same storage surface as Phase 7 audit pattern).

Latest-wins semantics: reviewers can change their score; each submission
appends a new row with an updated_at timestamp so the full audit trail is
preserved and the CSV export can show the most-recent score per trace_id.
"""
from datetime import datetime, timezone

from fastapi import APIRouter

from app.api.schemas import FeedbackRequest, FeedbackResponse
from app.audit import events as audit_events
from app.audit.middleware import get_audit_store
from app.observability.logging import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse)
def submit_feedback(request: FeedbackRequest) -> FeedbackResponse:
    """Record a feedback score for an assistant turn.

    Args:
        request: FeedbackRequest with trace_id, plan_id, user_id, score,
            and an optional comment.

    Returns:
        FeedbackResponse with ok flag and the new audit row id.
    """
    log.info(
        "POST /feedback: user=%r trace=%r score=%s",
        request.user_id,
        request.trace_id,
        request.score,
    )
    payload = {
        "plan_id": request.plan_id,
        "score": request.score,
        "comment": request.comment,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    row_id = get_audit_store().log(
        event_type=audit_events.FEEDBACK_RECEIVED,
        user_id=request.user_id,
        trace_id=request.trace_id,
        conversation_id=request.conversation_id,
        payload=payload,
    )
    log.info("Feedback persisted: row_id=%d", row_id)
    return FeedbackResponse(ok=row_id > 0, row_id=row_id)
