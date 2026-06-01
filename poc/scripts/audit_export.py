"""Phase 7 audit export.

Dump every row of audit.sqlite to CSV for compliance review. Usage:

    python scripts/audit_export.py               # -> data/audit_export.csv
    python scripts/audit_export.py --out FILE    # -> FILE
    python scripts/audit_export.py --trace-id ID # filter to one trace

The CSV is flat: payload_json is kept as a single column so the file
opens cleanly in Excel / PowerBI without needing per-event schemas.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.audit.store import AuditStore  # noqa: E402
from app.config import settings  # noqa: E402

_COLUMNS = [
    "id",
    "ts",
    "user_id",
    "conversation_id",
    "trace_id",
    "event_type",
    "payload_json",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=settings.audit_sqlite_path.parent / "audit_export.csv",
    )
    parser.add_argument(
        "--trace-id",
        help="Export only events belonging to this OTel trace id.",
    )
    args = parser.parse_args()

    if not settings.audit_sqlite_path.is_file():
        print(
            f"Audit DB not found at {settings.audit_sqlite_path}. "
            "Nothing to export.",
            file=sys.stderr,
        )
        return 1

    store = AuditStore(settings.audit_sqlite_path)
    rows = (
        store.by_trace_id(args.trace_id)
        if args.trace_id
        else list(store.iter_all())
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_COLUMNS)
        writer.writeheader()
        for r in rows:
            writer.writerow(
                {
                    "id": r["id"],
                    "ts": r["ts"],
                    "user_id": r["user_id"],
                    "conversation_id": r.get("conversation_id"),
                    "trace_id": r.get("trace_id"),
                    "event_type": r["event_type"],
                    "payload_json": json.dumps(
                        r.get("payload", {}),
                        ensure_ascii=False,
                        default=str,
                    ),
                }
            )

    print(f"Exported {len(rows)} audit row(s) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
