"""Plan persistence and approval-token CRUD for Phase 12.

Shares audit.sqlite with AuditStore — schema extended via schema.sql.
One connection per method, same pattern as MemoryStore and AuditStore.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.observability.logging import get_logger

log = get_logger(__name__)

_TOKEN_TTL_MINUTES = 15


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _expires_in(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat(
        timespec="seconds"
    )


def _hmac_secret() -> bytes:
    return os.environ.get("APPROVAL_HMAC_SECRET", "dev-insecure-secret-change-me").encode()


def _hash_token(raw_token: str) -> str:
    return hmac.new(_hmac_secret(), raw_token.encode(), hashlib.sha256).hexdigest()


class ApprovalStore:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------ plans

    def create_plan(
        self,
        *,
        plan_id: str,
        user_id: str,
        conversation_id: int | None,
        pending_step_id: str,
        trigger_case: str,
        resume_payload: dict[str, Any],
    ) -> None:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO plans "
                "(id, user_id, conversation_id, state, pending_step_id, "
                " trigger_case, resume_payload, created_at, updated_at, expires_at) "
                "VALUES (?, ?, ?, 'suspended', ?, ?, ?, ?, ?, ?)",
                (
                    plan_id,
                    user_id,
                    conversation_id,
                    pending_step_id,
                    trigger_case,
                    json.dumps(resume_payload, default=str),
                    now,
                    now,
                    _expires_in(_TOKEN_TTL_MINUTES),
                ),
            )

    def get_plan(self, plan_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM plans WHERE id = ?", (plan_id,)
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        raw = d.pop("resume_payload", None)
        try:
            d["resume_payload"] = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            d["resume_payload"] = {}
        return d

    def update_plan_state(self, plan_id: str, state: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE plans SET state = ?, updated_at = ? WHERE id = ?",
                (state, _now(), plan_id),
            )

    def get_suspended_plan_for_conversation(
        self, conversation_id: int
    ) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM plans "
                "WHERE conversation_id = ? AND state = 'suspended' "
                "ORDER BY created_at DESC LIMIT 1",
                (conversation_id,),
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        raw = d.pop("resume_payload", None)
        try:
            d["resume_payload"] = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            d["resume_payload"] = {}
        return d

    # --------------------------------------------------------- tokens

    def issue_token(self, *, plan_id: str, step_id: str) -> str:
        """Mint a new raw token. Only the HMAC hash is stored — raw token is returned."""
        raw_token = secrets.token_urlsafe(24)
        token_hash = _hash_token(raw_token)
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO plan_approval_tokens "
                "(token_hash, plan_id, step_id, issued_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (token_hash, plan_id, step_id, now, _expires_in(_TOKEN_TTL_MINUTES)),
            )
        return raw_token

    def verify_and_consume_token(
        self,
        raw_token: str,
        *,
        verdict: str,
        approver_id: str,
        channel: str,
    ) -> dict | None:
        """Verify HMAC + expiry + one-shot in a single atomic transaction.

        Returns the token row on success, None on any failure (expired/used/unknown).
        """
        token_hash = _hash_token(raw_token)
        now = _now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM plan_approval_tokens WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            if row is None:
                log.warning("verify_and_consume_token: unknown token_hash")
                return None
            token = dict(row)
            if token.get("used_at") is not None:
                log.warning(
                    "verify_and_consume_token: already used plan_id=%s", token["plan_id"]
                )
                return None
            if token["expires_at"] < now:
                log.warning(
                    "verify_and_consume_token: expired plan_id=%s", token["plan_id"]
                )
                return None
            conn.execute(
                "UPDATE plan_approval_tokens "
                "SET used_at = ?, verdict = ?, approver_id = ?, channel = ? "
                "WHERE token_hash = ?",
                (now, verdict, approver_id, channel, token_hash),
            )
        return token
