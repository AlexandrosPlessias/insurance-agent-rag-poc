-- All plans (newest first)
SELECT id, user_id, conversation_id, state, trigger_case, created_at, expires_at
FROM plans
ORDER BY created_at DESC
LIMIT 50;
