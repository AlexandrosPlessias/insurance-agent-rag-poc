-- Messages for a specific conversation
-- Usage: docker compose exec postgres psql -U poc -d poc -v conv_id=1 -f /tmp/messages.sql
SELECT id, role, LEFT(content, 120) AS preview, route, created_at
FROM messages
WHERE conversation_id = :'conv_id'
ORDER BY created_at;
