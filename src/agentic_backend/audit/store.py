"""PostgreSQL-backed audit log.

Sibling to memory.MemoryStore — same connection-per-method style.
One physical table `audit_events` keyed only on user_id + trace_id;
conversation_id is recorded but not foreign-keyed back to conversations
(the audit log is intentionally decoupled so the compliance team can
archive/export audit rows independently).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import psycopg2
import psycopg2.extras

from agentic_backend.observability.logging import get_logger

log = get_logger(__name__)


class AuditStore:
    def __init__(self, database_url: str):
        self._url = database_url
        log.info("AuditStore ready (postgres)")

    # --- connection helpers ---

    def _connect(self):
        conn = psycopg2.connect(self._url)
        conn.cursor_factory = psycopg2.extras.RealDictCursor
        conn.autocommit = True
        return conn

    # --- write ---

    def log(
        self,
        *,
        event_type: str,
        user_id: str,
        payload: dict[str, Any],
        conversation_id: int | None = None,
        trace_id: str | None = None,
    ) -> int:
        """Insert one audit row. Returns the new row id.

        Writes are best-effort: if PostgreSQL errors out we log and return 0
        rather than crash the request. Audit must never break user-facing
        flows.
        """
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            with self._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO audit_events "
                    "(ts, conversation_id, user_id, trace_id, "
                    " event_type, payload_json) "
                    "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                    (
                        ts,
                        conversation_id,
                        user_id,
                        trace_id,
                        event_type,
                        json.dumps(payload, default=str, ensure_ascii=False),
                    ),
                )
                row_id = int(cur.fetchone()["id"])
        except psycopg2.Error as exc:
            log.warning(
                "AuditStore.log failed (event=%s user=%s): %s",
                event_type,
                user_id,
                exc,
            )
            return 0
        return row_id

    # --- read (export + tests) ---

    def recent(self, limit: int = 100) -> list[dict]:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, ts, conversation_id, user_id, trace_id, "
                "       event_type, payload_json "
                "FROM audit_events "
                "ORDER BY id DESC LIMIT %s",
                (int(limit),),
            )
            rows = cur.fetchall()
        return [_row_to_dict(r) for r in rows]

    def by_trace_id(self, trace_id: str) -> list[dict]:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, ts, conversation_id, user_id, trace_id, "
                "       event_type, payload_json "
                "FROM audit_events "
                "WHERE trace_id = %s "
                "ORDER BY id ASC",
                (trace_id,),
            )
            rows = cur.fetchall()
        return [_row_to_dict(r) for r in rows]

    def iter_all(self):
        """Cursor-style iteration for export and inspection."""
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, ts, conversation_id, user_id, trace_id, "
                "       event_type, payload_json "
                "FROM audit_events ORDER BY id ASC"
            )
            for row in cur.fetchall():
                yield _row_to_dict(row)


def _row_to_dict(row: dict) -> dict:
    d = dict(row)
    raw = d.pop("payload_json", None)
    try:
        d["payload"] = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        d["payload"] = {"_raw": raw}
    return d
