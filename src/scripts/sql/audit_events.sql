-- Recent 50 audit events
SELECT id, ts, event_type, user_id, trace_id,
       LEFT(payload_json, 200) AS payload_preview
FROM audit_events
ORDER BY id DESC
LIMIT 50;
