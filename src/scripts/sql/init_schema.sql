-- Memory store
CREATE TABLE IF NOT EXISTS conversations (
    id          SERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    title       TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_conversations_user_id ON conversations(user_id);

CREATE TABLE IF NOT EXISTS messages (
    id              SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content         TEXT NOT NULL,
    route           TEXT,
    citations_json  TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS ix_messages_created_at ON messages(created_at);

-- Audit store
CREATE TABLE IF NOT EXISTS audit_events (
    id              SERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    conversation_id INTEGER,
    user_id         TEXT NOT NULL,
    trace_id        TEXT,
    event_type      TEXT NOT NULL,
    payload_json    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_user_ts  ON audit_events(user_id, ts);
CREATE INDEX IF NOT EXISTS idx_audit_trace    ON audit_events(trace_id);
CREATE INDEX IF NOT EXISTS idx_audit_type_ts  ON audit_events(event_type, ts);

-- Approval store
CREATE TABLE IF NOT EXISTS plans (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    conversation_id INTEGER,
    state           TEXT NOT NULL DEFAULT 'suspended',
    pending_step_id TEXT,
    trigger_case    TEXT,
    resume_payload  TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plans_user_ts    ON plans(user_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_plans_conv_state ON plans(conversation_id, state);

CREATE TABLE IF NOT EXISTS plan_approval_tokens (
    token_hash  TEXT PRIMARY KEY,
    plan_id     TEXT NOT NULL REFERENCES plans(id),
    step_id     TEXT NOT NULL,
    issued_at   TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    used_at     TEXT,
    verdict     TEXT,
    approver_id TEXT,
    channel     TEXT
);
