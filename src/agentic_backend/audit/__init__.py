"""audit trail.

Captures every routing/retrieval/validation/fallback/clarifier decision
into a separate SQLite file (`audit.sqlite`). Each row carries the OTel
trace_id so a span in Aspire is one click away from its audit record.

Public surface:
    from agentic_backend.audit import AuditStore, events
    store = AuditStore(settings.audit_sqlite_path)
    store.log(event_type=events.SUPERVISOR_ROUTE, user_id=..., payload={...})
"""
from agentic_backend.audit import events
from agentic_backend.audit.store import AuditStore

__all__ = ["AuditStore", "events"]
