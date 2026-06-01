-- Phase 7 audit trail schema. Loaded by AuditStore._init_schema().
CREATE TABLE IF NOT EXISTS audit_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT NOT NULL,        -- ISO-8601 UTC
    conversation_id INTEGER,
    user_id         TEXT NOT NULL,
    trace_id        TEXT,                 -- OTel trace id (hex) for span correlation
    event_type      TEXT NOT NULL,        -- see app.audit.events
    payload_json    TEXT NOT NULL         -- event-specific structured fields
);

CREATE INDEX IF NOT EXISTS idx_audit_user_ts ON audit_events(user_id, ts);
CREATE INDEX IF NOT EXISTS idx_audit_trace   ON audit_events(trace_id);
CREATE INDEX IF NOT EXISTS idx_audit_type_ts ON audit_events(event_type, ts);
