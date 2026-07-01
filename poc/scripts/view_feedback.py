"""View all thumbs-up / thumbs-down feedback stored in the audit DB.

Queries audit.sqlite for every feedback.received event and prints a
formatted table to stdout. Creates the DB lazily if it doesn't exist yet.

Usage (from poc/):
    python scripts/view_feedback.py              # all feedback
    python scripts/view_feedback.py --user alice # filter by user_id
    python scripts/view_feedback.py --limit 20  # last N rows
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.audit.store import AuditStore  # noqa: E402
from app.config import settings  # noqa: E402

W_TS = 20
W_USER = 18
W_SCORE = 6
W_PLAN = 36
W_CONV = 6


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", help="Filter by user_id")
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Maximum rows to show (default: 200)",
    )
    args = parser.parse_args()

    store = AuditStore(settings.audit_sqlite_path)
    all_feedback = [
        r for r in store.iter_all()
        if r["event_type"] == "feedback.received"
    ]

    rows = all_feedback
    if args.user:
        rows = [r for r in rows if r.get("user_id") == args.user]

    rows = rows[-args.limit:]

    if not rows:
        if args.user and all_feedback:
            users = sorted({r.get("user_id", "") for r in all_feedback})
            n = len(all_feedback)
            label = "entry" if n == 1 else "entries"
            print(
                f"No feedback found for user {args.user!r}. "
                f"{n} total {label} exist under: "
                f"{', '.join(repr(u) for u in users)}"
            )
        else:
            print("No feedback entries found.")
        return 0

    header = (
        f"{'Timestamp':<{W_TS}}  "
        f"{'User':<{W_USER}}  "
        f"{'Score':<{W_SCORE}}  "
        f"{'Plan ID':<{W_PLAN}}  "
        f"{'Conv':>{W_CONV}}  "
        f"Comment"
    )
    sep = "-" * len(header)
    print(f"\n{sep}")
    print(header)
    print(sep)

    for r in rows:
        p = r.get("payload", {})
        score_raw = p.get("score", 0)
        try:
            score_int = int(score_raw)
        except (TypeError, ValueError):
            score_int = 0
        score_label = "👍 +1" if score_int > 0 else "👎 -1"
        plan_id = str(p.get("plan_id") or r.get("trace_id") or "")[:W_PLAN]
        comment = str(p.get("comment") or "")
        ts = str(r.get("ts") or "")[:W_TS]
        user = str(r.get("user_id") or "")[:W_USER]
        conv = str(r.get("conversation_id") or "")[:W_CONV]

        print(
            f"{ts:<{W_TS}}  "
            f"{user:<{W_USER}}  "
            f"{score_label:<{W_SCORE}}  "
            f"{plan_id:<{W_PLAN}}  "
            f"{conv:>{W_CONV}}  "
            f"{comment}"
        )

    print(sep)
    thumbs_up = sum(
        1 for r in rows
        if int(r.get("payload", {}).get("score", 0)) > 0
    )
    thumbs_down = len(rows) - thumbs_up
    print(
        f"\nTotal: {len(rows)} feedback entries — "
        f"👍 {thumbs_up}  👎 {thumbs_down}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
