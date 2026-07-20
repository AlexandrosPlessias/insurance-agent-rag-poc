-- Feedback received (thumbs up/down)
SELECT id, ts, user_id, trace_id,
       payload_json::json->>'score'   AS score,
       payload_json::json->>'comment' AS comment
FROM audit_events
WHERE event_type = 'feedback.received'
ORDER BY id DESC;
