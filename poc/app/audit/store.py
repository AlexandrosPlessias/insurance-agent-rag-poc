"""SQLite-backed audit log (Phase 7).

Sibling to memory.MemoryStore - same connection-per-method style, same
schema.sql convention. One physical file `audit.sqlite` keyed only on
the user_id + trace_id; conversation_id is recorded but not foreign-keyed
back to memory.sqlite (the two DBs are intentionally decoupled so the
compliance team can rotate/archive audit.sqlite independently).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.observability.logging import get_logger

log = get_logger(__name__)

_SCHEMA_FILE = Path(__file__).parent / "schema.sql"


class AuditStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        log.info("AuditStore ready at %s", self.db_path)

    # --- connection helpers ---

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        schema = _SCHEMA_FILE.read_text(encoding="utf-8")
        with self._connect() as conn:
            conn.executescript(schema)

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

        Writes are best-effort: if SQLite errors out we log and return 0
        rather than crash the request. Audit must never break user-facing
        flows.
        """
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "INSERT INTO audit_events "
                    "(ts, conversation_id, user_id, trace_id, "
                    " event_type, payload_json) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        ts,
                        conversation_id,
                        user_id,
                        trace_id,
                        event_type,
                        json.dumps(payload, default=str, ensure_ascii=False),
                    ),
                )
                row_id = int(cur.lastrowid or 0)
        except sqlite3.Error as exc:
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
            rows = conn.execute(
                "SELECT id, ts, conversation_id, user_id, trace_id, "
                "       event_type, payload_json "
                "FROM audit_events "
                "ORDER BY id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def by_trace_id(self, trace_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, ts, conversation_id, user_id, trace_id, "
                "       event_type, payload_json "
                "FROM audit_events "
                "WHERE trace_id = ? "
                "ORDER BY id ASC",
                (trace_id,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def iter_all(self):
        """Cursor-style iteration for the CSV export script."""
        with self._connect() as conn:
            for row in conn.execute(
                "SELECT id, ts, conversation_id, user_id, trace_id, "
                "       event_type, payload_json "
                "FROM audit_events ORDER BY id ASC"
            ):
                yield _row_to_dict(row)


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    raw = d.pop("payload_json", None)
    try:
        d["payload"] = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        d["payload"] = {"_raw": raw}
    return d
