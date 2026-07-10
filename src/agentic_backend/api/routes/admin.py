"""Admin read-only endpoints — no auth guard (PoC only).

GET /admin/conversations   All conversations across all users (+ message count)
GET /admin/plans           All plan approval records
GET /admin/audit           Recent audit events (last ?limit=200)
"""
from fastapi import APIRouter, Depends

from agentic_backend.api.dependencies import get_memory_store
from agentic_backend.approvals.store import ApprovalStore
from agentic_backend.audit.store import AuditStore
from agentic_backend.config import settings
from agentic_backend.memory.store import MemoryStore

router = APIRouter(prefix="/admin", tags=["admin"])

_approval_store = ApprovalStore(settings.audit_sqlite_path)
_audit_store = AuditStore(settings.audit_sqlite_path)


@router.get("/conversations")
def admin_conversations(
    store: MemoryStore = Depends(get_memory_store),
) -> list[dict]:
    """Return all conversations across all users with message counts."""
    return store.list_all_conversations()


@router.get("/plans")
def admin_plans() -> list[dict]:
    """Return all plan approval records, newest first."""
    return _approval_store.list_all_plans()


@router.get("/audit")
def admin_audit(limit: int = 200) -> list[dict]:
    """Return recent audit events.

    Args:
        limit: Maximum number of rows to return. Defaults to 200.
    """
    return _audit_store.recent(limit=limit)
