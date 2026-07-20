-- All conversations with message count (newest first)
SELECT c.id, c.user_id, c.title, c.created_at, COUNT(m.id) AS messages
FROM conversations c
LEFT JOIN messages m ON m.conversation_id = c.id
GROUP BY c.id
ORDER BY c.created_at DESC;
