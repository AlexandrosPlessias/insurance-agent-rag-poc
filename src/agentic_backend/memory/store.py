"""SQLite-backed memory store: conversations + messages.

One MemoryStore instance per app. Connections are opened per-method
so it's safe under FastAPI's worker threading model.
"""
import json
import sqlite3
from pathlib import Path
from typing import Any

from agentic_backend.observability.logging import get_logger

log = get_logger(__name__)

_SCHEMA_FILE = Path(__file__).parent / "schema.sql"


class MemoryStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        log.info("MemoryStore ready at %s", self.db_path)

    # --- connection helpers ---

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")   # safe concurrent reads across pods
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        schema = _SCHEMA_FILE.read_text(encoding="utf-8")
        with self._connect() as conn:
            conn.executescript(schema)

    # --- conversations ---

    def create_conversation(
        self, user_id: str, title: str | None = None
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO conversations (user_id, title) VALUES (?, ?)",
                (user_id, title),
            )
            conv_id = int(cur.lastrowid or 0)
        log.info("Created conversation %d for user=%r", conv_id, user_id)
        return conv_id

    def list_conversations(self, user_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, user_id, title, created_at "
                "FROM conversations "
                "WHERE user_id = ? "
                "ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_all_conversations(self) -> list[dict]:
        """Return all conversations across all users with their message counts.

        Returns:
            List of dicts with keys: id, user_id, title, created_at, message_count.
            Ordered by created_at descending (newest first).
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT c.id, c.user_id, c.title, c.created_at, "
                "       COUNT(m.id) AS message_count "
                "FROM conversations c "
                "LEFT JOIN messages m ON m.conversation_id = c.id "
                "GROUP BY c.id "
                "ORDER BY c.created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_conversation(self, conversation_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, user_id, title, created_at "
                "FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
        return dict(row) if row else None

    def delete_conversation(self, conversation_id: int) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        log.info("Deleted conversation %d", conversation_id)

    def set_title_if_empty(
        self, conversation_id: int, title: str
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE conversations SET title = ? "
                "WHERE id = ? AND (title IS NULL OR title = '')",
                (title, conversation_id),
            )

    # --- messages ---

    def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        route: str | None = None,
        citations: list[dict] | None = None,
    ) -> int:
        citations_json = json.dumps(citations) if citations else None
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO messages "
                "(conversation_id, role, content, route, citations_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (conversation_id, role, content, route, citations_json),
            )
            msg_id = int(cur.lastrowid or 0)
        # Auto-title the conversation on the first user message.
        if role == "user":
            title = content[:50].strip()
            if len(content) > 50:
                title += "..."
            self.set_title_if_empty(conversation_id, title)
        return msg_id

    def get_messages(
        self,
        conversation_id: int,
        limit: int | None = None,
    ) -> list[dict]:
        sql = (
            "SELECT id, conversation_id, role, content, route, "
            "       citations_json, created_at "
            "FROM messages "
            "WHERE conversation_id = ? "
            "ORDER BY created_at ASC, id ASC"
        )
        params: tuple[Any, ...] = (conversation_id,)
        if limit is not None:
            # Fetch the LAST N then return in chronological order.
            sql = (
                "SELECT * FROM ("
                + sql.replace(
                    "ORDER BY created_at ASC, id ASC",
                    "ORDER BY created_at DESC, id DESC LIMIT ?",
                )
                + ") ORDER BY created_at ASC, id ASC"
            )
            params = (conversation_id, limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_message(r) for r in rows]

    def get_messages_with_summary(
        self,
        conversation_id: int,
        recent_n: int = 6,
    ) -> list[dict]:
        """Return the last `recent_n` messages, prepended by an LLM-summary
        of any older messages.

        When the conversation has more than `recent_n` total messages,
        the older slice is condensed by `agentic_backend.memory.summarizer` into a
        single synthetic system message:
            {"role": "system", "content": "[Earlier in this
             conversation: ...]"}
        which is then prepended to the recent slice. Older messages are
        not deleted from the DB - this is a *prompt-time* compression,
        not a storage policy.
        """
        all_msgs = self.get_messages(conversation_id)
        if len(all_msgs) <= recent_n:
            return all_msgs
        older = all_msgs[: -recent_n]
        recent = all_msgs[-recent_n:]
        # Lazy import: keeps agentic_backend.memory.store LLM-agnostic for tests.
        from agentic_backend.memory.summarizer import summarize_messages

        digest = summarize_messages(older)
        if not digest:
            # LLM unavailable or empty - just return the recent slice.
            return recent
        summary_msg = {
            "role": "system",
            "content": f"[Earlier in this conversation: {digest}]",
            "created_at": "",
            "citations": [],
        }
        return [summary_msg] + recent

    def get_user_activity(
        self, user_id: str, limit: int = 10
    ) -> list[dict]:
        """Recent user messages across ALL the user's conversations."""
        sql = (
            "SELECT m.id, m.conversation_id, m.role, m.content, m.route, "
            "       m.citations_json, m.created_at, c.title "
            "FROM messages m "
            "JOIN conversations c ON c.id = m.conversation_id "
            "WHERE c.user_id = ? AND m.role = 'user' "
            "ORDER BY m.created_at DESC, m.id DESC LIMIT ?"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, (user_id, limit)).fetchall()
        return [self._row_to_message(r) for r in rows]

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> dict:
        d = dict(row)
        if d.get("citations_json"):
            try:
                d["citations"] = json.loads(d["citations_json"])
            except json.JSONDecodeError:
                d["citations"] = []
        else:
            d["citations"] = []
        d.pop("citations_json", None)
        return d
