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
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentic_backend.agents.rag_agent import answer_question  # noqa: E402
from agentic_backend.audit import events as audit_events  # noqa: E402
from agentic_backend.audit.middleware import get_audit_store  # noqa: E402
from agentic_backend.config import settings  # noqa: E402
from agentic_backend.memory.store import MemoryStore  # noqa: E402
from agentic_backend.observability.logging import (  # noqa: E402
    configure_logging,
    get_logger,
)
from agentic_backend.rag.vectorstore import get_chunk_count, reset_collection  # noqa: E402

configure_logging("INFO")
log = get_logger("smoke_test")

# The most recent customer-guidelines doc - widest year coverage in the
# repo's seed PDFs, includes refund policy with multiple payment methods
# (better RAG signal than the older 2020 cash-only edition).
SAMPLE_PDF = settings.raw_pdf_dir / "Enhanced_Customer_Guidelines_2024.pdf"

USER_ID = "smoke_user"

# Smoke-test scenarios. Each scenario runs in its OWN conversation so
# year context from one scenario doesn't pollute the next. Without this
# isolation the clarifier scenario silently inherits a year from a
# previous turn's history (via _resolve_year_from_history) and never
# fires, and the bare "2024" follow-up gets re-classified as a fresh
# question instead of being stitched onto the clarifier's original.
SCENARIOS: list[dict] = [
    {
        "title": "Phase 1-3 - Basic RAG (with 2024 year context)",
        "questions": [
            ("rag",
             "What is the refund window in the 2024 customer "
             "guidelines?"),
            ("rag",
             "How should employees handle a suspected theft incident "
             "in 2024?"),
        ],
    },
    {
        "title": "Phase 7 - relative date worked example (2020 policy)",
        "questions": [
            ("rag",
             "Based on the 2020 policy, how should a refund without "
             "a receipt but with a bank transaction be handled?"),
        ],
    },
    {
        "title": "Phase 3 - Report agent (Markdown + chart)",
        "questions": [
            ("report",
             "Give me a summary report of the 2024 customer guidelines"),
        ],
    },
    {
        "title": "Phase 7 - Clarifier + follow-up (in a CLEAN conversation)",
        "questions": [
            # Fresh conversation: no prior turns, so the supervisor
            # can't inherit a year from history. The clarifier
            # override fires because route='rag' AND no year resolvable.
            ("needs_clarification", "What is the refund window?"),
            # Bare "2024" follow-up. supervisor_node's clarifier-
            # followup logic stitches it onto the original question:
            # 'What is the refund window? 2024' -> routed to rag.
            ("rag", "2024"),
        ],
    },
    {
        "title": "Phase 7 - Out-of-year fallback (2023 is the KB gap)",
        "questions": [
            ("out_of_year",
             "What does the 2023 policy say about refunds?"),
        ],
    },
    {
        "title": "Out-of-scope decline",
        "questions": [
            ("out_of_scope", "What is 2 + 2?"),
        ],
    },
    {
        "title": (
            "Phase 8 - Talk-to-Data "
            "(scalar + grouped + drill-down + guards)"
        ),
        "questions": [
            # Single scalar metric query.
            ("data", "What was the total gross written premium in 2024?"),
            # weighted_mean of a rate metric, grouped by channel.
            ("data", "Renewal rate by channel in 2024"),
            # DRILL-DOWN: inherits metric / year / aggregation, changes
            # only group_by. Operation expander chips:
            #   Inherited = {metric, filters, aggregation}
            #   Changed   = {group_by}
            ("data", "Now break that by product line instead"),
            # GUARD: sum on a stock-like metric -> invalid_aggregation.
            ("data",
             "What is the total NPS summed across all channels in 2024?"),
            # GUARD: 2023 year_gap, symmetric with Phase 7's
            # out_of_year fallback.
            ("data", "What was the gross written premium in 2023?"),
        ],
    },
    {
        "title": "Phase 9 - Executive annual report (2024)",
        "questions": [
            # Routes to report. With target_year=2024 the report_node
            # dispatches to the executive pipeline (collector ->
            # narrator -> assemble -> markdown_writer). The on-screen
            # answer is the rendered Markdown report; the API exposes
            # GET /reports/2024.{md,docx,pdf} for downloads.
            ("report",
             "Give me the 2024 executive annual report"),
        ],
    },
    {
        "title": "Phase 11 - Multi-intent (policy RAG + KPI data, single turn)",
        "questions": [
            # Two intents in one sentence: the Planner should produce a
            # 2-step plan (answer-policy-question + compute-kpi) so the
            # orchestrator dispatches two workers and the assembler merges
            # both answers into a single response.
            ("agentic",
             "What is the refund policy in the 2024 guidelines, "
             "and what was the gross written premium in 2024?"),
        ],
    },
]

_W = 72  # report column width


@dataclass
class TestResult:
    scenario: str
    question: str
    expected_route: str
    actual_route: str
    passed: bool
    elapsed_s: float
    error: str = field(default="")


def _strip_data_uri_images(markdown: str) -> str:
    """Replace base64 chart payloads with a placeholder for readable stdout."""
    return re.sub(
        r"!\[([^\]]*)\]\(data:image/[^)]+\)",
        r"![\1](embedded chart, base64 omitted)",
        markdown,
    )


def _trunc(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def _print_summary(results: list[TestResult]) -> None:
    passed_count = sum(1 for r in results if r.passed)
    failed_count = len(results) - passed_count
    total_s = sum(r.elapsed_s for r in results)

    print("\n" + "═" * _W)
    print(f" RESULTS SUMMARY{f'  ({len(results)} tests · {total_s:.1f}s total)':>{_W - 17}}")
    print("═" * _W)
    print(f"  {'#':>3}  {'':4}  {'Got / Expected':<24}  {'Scenario · Question'}")
    print("  " + "─" * (_W - 2))

    for i, r in enumerate(results, 1):
        status = "PASS" if r.passed else "FAIL"
        if r.passed:
            route_col = _trunc(r.actual_route, 24)
        else:
            route_col = _trunc(f"{r.actual_route} / {r.expected_route}", 24)
        label = _trunc(f"{r.scenario} · {r.question}", _W - 38)
        print(f"  {i:>3}  {status}  {route_col:<24}  {label}")
        if r.error:
            print(f"       {'':4}  {'':24}  error: {_trunc(r.error, _W - 38)}")

    print("  " + "─" * (_W - 2))
    verdict = "ALL PASSED" if failed_count == 0 else f"{failed_count} FAILED"
    print(f"  PASSED {passed_count}/{len(results)}   {verdict}   {total_s:.1f}s total")
    print("═" * _W + "\n")


def main() -> int:
    # --skip-ingest: skip PDF reset + ingest — use data already in ChromaDB.
    # Required when running inside the agentic-service container (Docker),
    # which does not have pymupdf4llm. Ensure ingestion-service has already
    # indexed the PDFs before running with this flag.
    skip_ingest = "--skip-ingest" in sys.argv

    print("\n" + "=" * _W)
    print("Smoke test - real seed PDF + supervisor / RAG / report / memory")
    if skip_ingest:
        print("  mode: --skip-ingest (using existing ChromaDB data)")
    else:
        print(f"  source: {SAMPLE_PDF.name}")
    print("=" * _W + "\n")

    if skip_ingest:
        chunk_count = get_chunk_count()
        if chunk_count == 0:
            log.error(
                "ChromaDB is empty and --skip-ingest was set. "
                "Run ingestion first: docker compose exec ingestion-service "
                "python scripts/ingest_pdfs.py"
            )
            return 1
        log.info("--skip-ingest: ChromaDB has %d chunks — skipping reset + ingest.", chunk_count)
    else:
        if not SAMPLE_PDF.is_file():
            log.error(
                "Sample PDF not found at %s. Make sure the seed PDFs in "
                "data/knowledge_base/raw/ are present.",
                SAMPLE_PDF,
            )
            return 1

        # Reset Chroma so the test runs in isolation: only the 2024 PDF's
        # chunks are present, so retrieval answers are pinned to its content.
        log.info("Resetting Chroma collection for an isolated run ...")
        try:
            reset_collection()
        except Exception as exc:  # noqa: BLE001
            log.warning("reset_collection failed (probably first run): %s", exc)

        # Ingest the seed PDF through the Phase 6 pipeline. The LLM
        # summariser writes a fresh sidecar; subsequent queries pick up the
        # newly-built section_title metadata.
        from agentic_backend.ingestion.pipeline import ingest_document  # noqa: PLC0415

        ingest_result = ingest_document(SAMPLE_PDF)
        log.info(
            "Ingest: %d pages -> %d chunks (%s)",
            ingest_result.page_count,
            ingest_result.chunks_indexed,
            ingest_result.markdown_path.name,
        )

    store = MemoryStore(settings.database_url)
    results: list[TestResult] = []

    for scenario in SCENARIOS:
        # Each scenario gets its own clean conversation - no year
        # context leaks across, so the clarifier scenario actually
        # fires and the bare-token follow-up gets stitched correctly.
        conv_id = store.create_conversation(USER_ID, title=scenario["title"])
        print("\n" + "=" * _W)
        print(f"SCENARIO  : {scenario['title']}")
        print(f"  (conv id: {conv_id})")
        print("=" * _W)

        for expected_route, q in scenario["questions"]:
            print("\n" + "-" * _W)
            print(f"Q: {q}")
            print(f"   (expected route: {expected_route})")
            print("-" * _W)

            # Mimic the API route: load memory, persist user msg,
            # invoke the compiled graph. History is conversation-
            # scoped, so it stays clean per scenario.
            history = store.get_messages(conv_id, limit=6)
            activity = store.get_user_activity(USER_ID, limit=10)
            store.add_message(conv_id, "user", q)

            t0 = time.perf_counter()
            try:
                answer = answer_question(
                    q,
                    user_id=USER_ID,
                    history=history,
                    user_activity=activity,
                )
                elapsed_s = time.perf_counter() - t0
                actual_route = answer.route
                passed = actual_route == expected_route
                error = ""
            except Exception as exc:  # noqa: BLE001
                elapsed_s = time.perf_counter() - t0
                actual_route = "ERROR"
                passed = False
                error = str(exc)
                log.exception("answer_question raised for q=%r", q)
                results.append(
                    TestResult(
                        scenario=scenario["title"],
                        question=q,
                        expected_route=expected_route,
                        actual_route=actual_route,
                        passed=passed,
                        elapsed_s=elapsed_s,
                        error=error,
                    )
                )
                print(f"\n[ERROR after {elapsed_s:.1f}s]: {exc}")
                continue

            store.add_message(
                conv_id,
                "assistant",
                answer.answer,
                route=answer.route,
                citations=[
                    {
                        "source": c.source,
                        "content": c.content,
                        "download_url": f"/sources/{c.source}",
                        "section": c.section,
                        "section_title": c.section_title,
                    }
                    for c in answer.citations
                ],
            )

            printable = (
                _strip_data_uri_images(answer.answer)
                if answer.route == "report"
                else answer.answer
            )
            print(f"A:\n{printable}\n")
            match_label = "OK" if passed else "MISMATCH"
            print(f"Route       : {answer.route} (expected: {expected_route}) [{match_label}]")
            print(
                f"Memory      : {len(history)} history msgs, "
                f"{len(activity)} activity msgs"
            )
            if answer.route == "rag":
                print(f"Validated   : {answer.validated}")
                print(f"Retries     : {answer.retry_count}")
            if answer.route in ("rag", "report"):
                print("Citations   :")
                for c in answer.citations:
                    print(f"  - {c.as_citation()}")
            print(f"\n[elapsed: {elapsed_s:.1f}s]")

            results.append(
                TestResult(
                    scenario=scenario["title"],
                    question=q,
                    expected_route=expected_route,
                    actual_route=actual_route,
                    passed=passed,
                    elapsed_s=elapsed_s,
                )
            )

    # ── Feedback round-trip ───────────────────────────────────────────────────
    print("\n" + "=" * _W)
    print("FEEDBACK SMOKE TEST")
    print("=" * _W)

    feedback_passed = False
    feedback_error = ""
    t0 = time.perf_counter()
    try:
        from datetime import datetime, timezone

        audit_store = get_audit_store()
        test_plan_id = "smoke-test-plan-0000"
        row_id = audit_store.log(
            event_type=audit_events.FEEDBACK_RECEIVED,
            user_id=USER_ID,
            trace_id=test_plan_id,
            payload={
                "plan_id": test_plan_id,
                "score": 1,
                "comment": "smoke test thumbs-up",
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
        )
        assert row_id > 0, f"FAIL: feedback write returned row_id={row_id}"
        print(f"  Write OK  : row_id={row_id}")

        feedback_rows = [
            r for r in audit_store.iter_all()
            if r["event_type"] == audit_events.FEEDBACK_RECEIVED
            and r.get("user_id") == USER_ID
        ]
        assert feedback_rows, "FAIL: no feedback.received rows found after write"

        last = feedback_rows[-1]
        assert last["payload"]["score"] == 1, (
            f"FAIL: expected score=1, got {last['payload']['score']}"
        )
        assert last["payload"]["plan_id"] == test_plan_id, (
            f"FAIL: plan_id mismatch: {last['payload']['plan_id']!r}"
        )
        print(
            f"  Read-back OK: score={last['payload']['score']}  "
            f"plan_id={last['payload']['plan_id']}"
        )
        print(f"  Total feedback rows for {USER_ID!r}: {len(feedback_rows)}")
        print("  [PASS] feedback.received round-trip verified")
        feedback_passed = True
    except Exception as exc:  # noqa: BLE001
        feedback_error = str(exc)
        log.exception("Feedback smoke test failed")
        print(f"  [FAIL] {exc}")

    results.append(
        TestResult(
            scenario="[feedback]",
            question="feedback.received round-trip",
            expected_route="pass",
            actual_route="pass" if feedback_passed else "fail",
            passed=feedback_passed,
            elapsed_s=time.perf_counter() - t0,
            error=feedback_error,
        )
    )

    _print_summary(results)

    failed_count = sum(1 for r in results if not r.passed)
    return 1 if failed_count else 0


if __name__ == "__main__":
    sys.exit(main())
