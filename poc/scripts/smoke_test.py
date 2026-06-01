"""End-to-end smoke test against a real seed PDF.

Pipeline exercised:
  Phase 6 ingestion  - PDF -> Markdown -> sidecar -> ChromaDB
  Phase 2 graph      - supervisor -> RAG -> validator (+ 1-retry loop)
  Phase 3 graph      - supervisor -> report (Markdown + chart)
  Phase 4 memory     - SQLite-persisted conversation, cross-turn history
  Phase 5 telemetry  - traces / logs / metrics flow to Aspire if enabled

The previous version synthesised a 3-page mock policy with PyMuPDF; now
that we ship real seed PDFs under data/knowledge_base/raw/, the smoke
test uses one of them directly. Questions are scoped to content present
in Enhanced_Customer_Guidelines_2024.pdf so they're answerable end-to-end.

Run from poc/:  python scripts/smoke_test.py
"""
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.rag_agent import answer_question  # noqa: E402
from app.config import settings  # noqa: E402
from app.ingestion.pipeline import ingest_document  # noqa: E402
from app.memory.store import MemoryStore  # noqa: E402
from app.observability.logging import (  # noqa: E402
    configure_logging,
    get_logger,
)
from app.rag.vectorstore import reset_collection  # noqa: E402

configure_logging("INFO")
log = get_logger("smoke_test")

# The most recent customer-guidelines doc - widest year coverage in the
# repo's seed PDFs, includes refund policy with multiple payment methods
# (better RAG signal than the older 2020 cash-only edition).
SAMPLE_PDF = settings.raw_pdf_dir / "Enhanced_Customer_Guidelines_2024.pdf"

USER_ID = "smoke_user"

# Questions scoped to known 2024 content. The supervisor classifies each
# into one of the routes; we assert the route loosely via the printed
# banner so a human reader can spot routing regressions. Phase 7 cases
# at the end exercise the new clarifier / out_of_year branches.
SAMPLE_QUESTIONS = [
    (
        "rag",
        "What is the refund window in the 2024 customer guidelines?",
    ),
    (
        "rag",
        "Based on the 2020 policy, how should a refund without a "
        "receipt but with a bank transaction be handled?",
    ),
    (
        "rag",
        "How should employees handle a suspected theft incident in 2024?",
    ),
    (
        "report",
        "Give me a summary report of the 2024 customer guidelines",
    ),
    (
        "out_of_scope",
        "What is 2 + 2?",
    ),
    # Phase 7 - clarifier branch (year missing).
    (
        "needs_clarification",
        "What is the refund window?",
    ),
    # Phase 7 - out-of-year fallback (2023 is the KB gap).
    (
        "out_of_year",
        "What does the 2023 policy say about refunds?",
    ),
    # Phase 7 - clarifier follow-up: the bare "2024" reply should be
    # stitched onto the previous "What is the refund window?" so the
    # supervisor routes to rag, not out_of_scope.
    (
        "rag",
        "2024",
    ),
    # Phase 8 - data route: single scalar metric query.
    (
        "data",
        "What was the total gross written premium in 2024?",
    ),
    # Phase 8 - data route: weighted_mean of a rate metric across
    # channels. Tests both group_by and the weighted_mean aggregation.
    (
        "data",
        "Renewal rate by channel in 2024",
    ),
    # Phase 8 - data route DRILL-DOWN: this follow-up should INHERIT
    # the previous metric (renewal_rate_pct) and year (2024), and
    # change only the group_by dimension. The Operation expander
    # should show 'Inherited' = {metric, filters, aggregation},
    # 'Changed' = {group_by}.
    (
        "data",
        "Now break that by product line instead",
    ),
    # Phase 8 - GUARD: sum on NPS is a rate/snapshot-like aggregation
    # error. The executor refuses with reason=invalid_aggregation;
    # the agent surfaces a templated refusal message naming the
    # allowed aggregations for the metric.
    (
        "data",
        "What is the total NPS summed across all channels in 2024?",
    ),
    # Phase 8 - GUARD: 2023 year_gap. Symmetric with Phase 7's RAG
    # out_of_year fallback - executor refuses with reason=year_gap.
    (
        "data",
        "What was the gross written premium in 2023?",
    ),
]


def _strip_data_uri_images(markdown: str) -> str:
    """Replace base64 chart payloads with a placeholder for readable stdout."""
    return re.sub(
        r"!\[([^\]]*)\]\(data:image/[^)]+\)",
        r"![\1](embedded chart, base64 omitted)",
        markdown,
    )


def main() -> int:
    if not SAMPLE_PDF.is_file():
        log.error(
            "Sample PDF not found at %s. Make sure the seed PDFs in "
            "data/knowledge_base/raw/ are present.",
            SAMPLE_PDF,
        )
        return 1

    print("\n" + "=" * 72)
    print(
        "Smoke test - real seed PDF + supervisor / RAG / report / memory"
    )
    print(f"  source: {SAMPLE_PDF.name}")
    print("=" * 72 + "\n")

    # Reset Chroma so the test runs in isolation: only the 2024 PDF's
    # chunks are present, so retrieval answers are pinned to its content.
    log.info("Resetting Chroma collection for an isolated run ...")
    try:
        reset_collection()
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "reset_collection failed (probably first run): %s", exc
        )

    # Reset SQLite memory so cross-session history starts empty.
    if settings.sqlite_path.exists():
        log.info("Removing SQLite memory at %s", settings.sqlite_path)
        settings.sqlite_path.unlink()

    # Phase 7 - reset audit DB so the smoke run gets a clean trail.
    if settings.audit_sqlite_path.exists():
        log.info(
            "Removing audit DB at %s", settings.audit_sqlite_path
        )
        settings.audit_sqlite_path.unlink()

    # Ingest the seed PDF through the Phase 6 pipeline. The LLM
    # summariser writes a fresh sidecar; subsequent queries pick up the
    # newly-built section_title metadata.
    ingest_result = ingest_document(SAMPLE_PDF)
    log.info(
        "Ingest: %d pages -> %d chunks (%s)",
        ingest_result.page_count,
        ingest_result.chunks_indexed,
        ingest_result.markdown_path.name,
    )

    store = MemoryStore(settings.sqlite_path)
    conv_id = store.create_conversation(USER_ID, title=None)
    log.info("Created conversation %d for user %r", conv_id, USER_ID)

    for expected_route, q in SAMPLE_QUESTIONS:
        print("\n" + "-" * 72)
        print(f"Q: {q}")
        print(f"   (expected route: {expected_route})")
        print("-" * 72)

        # Mimic the API route: load memory, persist user msg, invoke graph.
        history = store.get_messages(conv_id, limit=6)
        activity = store.get_user_activity(USER_ID, limit=10)
        store.add_message(conv_id, "user", q)

        t0 = time.perf_counter()
        result = answer_question(
            q,
            user_id=USER_ID,
            history=history,
            user_activity=activity,
        )
        dt = time.perf_counter() - t0

        store.add_message(
            conv_id,
            "assistant",
            result.answer,
            route=result.route,
            citations=[
                {
                    "source": c.source,
                    "content": c.content,
                    "download_url": f"/sources/{c.source}",
                    "section": c.section,
                    "section_title": c.section_title,
                }
                for c in result.citations
            ],
        )

        printable = (
            _strip_data_uri_images(result.answer)
            if result.route == "report"
            else result.answer
        )
        print(f"A:\n{printable}\n")
        print(f"Route       : {result.route}")
        print(
            f"Memory      : {len(history)} history msgs, "
            f"{len(activity)} activity msgs"
        )
        if result.route == "rag":
            print(f"Validated   : {result.validated}")
            print(f"Retries     : {result.retry_count}")
        if result.route in ("rag", "report"):
            print("Citations   :")
            for c in result.citations:
                print(f"  - {c.as_citation()}")
        print(f"\n[elapsed: {dt:.1f}s]")

    print("\n" + "=" * 72)
    print(
        f"Smoke test complete. Conversation id={conv_id} for "
        f"user {USER_ID!r} persisted in SQLite."
    )
    print("=" * 72 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
