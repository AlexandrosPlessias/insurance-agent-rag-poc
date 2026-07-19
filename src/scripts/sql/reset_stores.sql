-- DANGER: wipes all conversation, audit, and plan data. ChromaDB reset is separate.
-- docker compose exec postgres psql -U poc -d poc < src/scripts/sql/reset_stores.sql
TRUNCATE conversations, messages, audit_events, plans, plan_approval_tokens
    RESTART IDENTITY CASCADE;
