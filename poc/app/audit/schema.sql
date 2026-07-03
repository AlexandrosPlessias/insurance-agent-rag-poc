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

-- Phase 12: suspendable plans and HMAC approval tokens
CREATE TABLE IF NOT EXISTS plans (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    conversation_id INTEGER,
    state           TEXT NOT NULL DEFAULT 'suspended',  -- suspended|approved|rejected|done
    pending_step_id TEXT,
    trigger_case    TEXT,           -- report|unverified|kpi|ingest
    resume_payload  TEXT,           -- JSON: {question, history, plan, step_results, ...}
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plan_approval_tokens (
    token_hash  TEXT PRIMARY KEY,
    plan_id     TEXT NOT NULL,
    step_id     TEXT NOT NULL,
    issued_at   TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    used_at     TEXT,
    verdict     TEXT,           -- approved|rejected
    approver_id TEXT,
    channel     TEXT,           -- ui|telegram
    FOREIGN KEY (plan_id) REFERENCES plans(id)
);

CREATE INDEX IF NOT EXISTS idx_plans_user_ts    ON plans(user_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_plans_conv_state ON plans(conversation_id, state);
