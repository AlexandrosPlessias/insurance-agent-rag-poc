# Approval Gates (Phase 12)

Human-in-the-loop checkpoints that pause a running Plan until a reviewer approves or rejects it.
The flow is designed to be channel-agnostic: Telegram is the default; Slack or Teams can be
wired in by swapping the notifier in `src/agentic_backend/approvals/telegram_bot.py`.

---

## When does approval trigger?

The Orchestrator calls `approvals/store.py:request_approval()` when a Step is tagged
`requires_approval = true` in the Skill spec. Currently only the `executive-section-summary`
Skill marks itself this way (the annual report generation involves substantial compute and
sends a document externally — the reviewer confirms intent before it runs).

---

## The approval token

Tokens are HMAC-SHA256 signed with `settings.approval_hmac_secret` (set via
`APPROVAL_HMAC_SECRET` in `src/.env`). The signed payload is:

```json
{
  "plan_id": "<uuid>",
  "step_id": "<step-id>",
  "exp": <unix-timestamp>
}
```

The default TTL is **24 hours**. Tokens are single-use: after verification the row in `plans`
is updated and subsequent calls with the same token return 410 Gone.

> **Security note:** Never use the default `dev-insecure-secret-change-me` value in production.
> The backend logs a `SECURITY` warning at startup if the default is detected.

---

## Approve or reject

The Telegram message contains two buttons:

- **✅ Approve** → `GET /api/plans/approve?token=<signed-token>`
- **❌ Reject** → `GET /api/plans/reject?token=<signed-token>`

Both endpoints verify the HMAC token, update `plans.status`, and resume or cancel the
waiting Plan. The frontend `PipelineStepper` polls `GET /api/plans/{plan_id}` and
transitions from the `waiting_approval` stage once the status changes.

---

## Running the Telegram bot

```bash
cd src && source .venv/bin/activate
python scripts/run_telegram_bot.py
```

Environment variables required in `src/.env`:

```env
TELEGRAM_BOT_TOKEN=<your-bot-token>
TELEGRAM_CHAT_ID=<your-chat-id>
APPROVAL_HMAC_SECRET=<strong-random-secret>
APPROVAL_BASE_URL=http://localhost:8000
```

If `TELEGRAM_BOT_TOKEN` is empty, the bot module is skipped silently — the approval request
is logged to the console instead, and the signed URL is printed so you can paste it manually.

---

## Database schema

```sql
CREATE TABLE plans (
    plan_id     TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'running',
    payload     TEXT,               -- JSON blob of the serialized Plan
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

`status` values: `running` · `waiting_approval` · `approved` · `rejected` · `completed` · `failed`

---

## Extending to Slack / Teams

Replace `src/agentic_backend/approvals/telegram_bot.py` with a module that exposes the same
`signal_start()` / `signal_stop()` / `send_approval_request(plan_id, step_id, approve_url, reject_url)` interface. The Orchestrator and FastAPI routes import only those three functions, so the
channel implementation is fully swappable.
