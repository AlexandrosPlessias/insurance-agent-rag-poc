"""End-to-end smoke test (no external PDFs needed).

Phase 4 + Phase 6 demo:
  - Synthesises an ACME insurance policy PDF.
  - Runs it through `ingest_document()` (PDF -> Markdown -> metadata
    sidecar -> ChromaDB) - same pipeline the UI upload route uses.
  - Creates a user-scoped conversation in SQLite.
  - Runs 3 RAG questions (each persisted as messages).
  - Asks for a personalized report - the report agent reads the user's
    activity from SQLite and includes a "User Activity" section.
  - Runs 1 out-of-scope question (decline path).

Run from poc/:  python scripts/smoke_test.py
"""
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fitz  # PyMuPDF  # noqa: E402

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

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
SAMPLE_PDF = FIXTURE_DIR / "sample_policy.pdf"

SAMPLE_PAGES = [
    """ACME Insurance - Comprehensive Auto Policy
Effective Date: 2026-01-01
Policy Number: AC-12345-XY

This policy provides coverage for the insured vehicle against
collision, theft, fire, and third-party liability up to EUR 1,000,000.

Section 1 - Coverage
Collision coverage applies to damage caused by impact with another
vehicle or object. Deductible: EUR 500 per claim.
Theft coverage applies if the vehicle is stolen and not recovered
within 30 days.""",

    """Section 2 - Exclusions
This policy does not cover:
- Damage caused by intentional acts.
- Wear and tear or mechanical breakdown.
- Use of the vehicle for commercial purposes without endorsement.
- Driving under the influence of alcohol or drugs.

Section 3 - Claims Procedure
Claims must be reported within 14 days of the incident.
Required documents: police report, photos, witness statements.""",

    """Section 4 - Premium and Renewal
Annual premium: EUR 850.
Premium is payable in full at policy inception or in 4 equal
quarterly installments of EUR 220.

Policy auto-renews on the anniversary date unless cancelled
in writing 30 days prior.""",
]

SAMPLE_QUESTIONS = [
    ("rag", "What is the deductible for collision claims?"),
    ("rag", "How many days do I have to report a claim?"),
    ("rag", "What is the annual premium and can I pay in installments?"),
    ("report", "Give me a personalized summary report of the policy"),
    ("out_of_scope", "What is 2 + 2?"),
]

USER_ID = "smoke_user"


def build_sample_pdf(path: Path) -> None:
    log.info("Building synthetic sample PDF at %s", path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    for page_text in SAMPLE_PAGES:
        page = doc.new_page()
        page.insert_text((50, 72), page_text, fontsize=11, fontname="helv")
    doc.save(path)
    doc.close()


def _strip_data_uri_images(markdown: str) -> str:
    return re.sub(
        r"!\[([^\]]*)\]\(data:image/[^)]+\)",
        r"![\1](embedded chart, base64 omitted)",
        markdown,
    )


def main() -> int:
    print("\n" + "=" * 72)
    print("Phase 4+6 smoke test - ingestion pipeline + supervisor + memory")
    print("=" * 72 + "\n")

    build_sample_pdf(SAMPLE_PDF)

    log.info("Resetting Chroma collection for a clean run ...")
    try:
        reset_collection()
    except Exception as e:
        log.warning("reset_collection failed (probably first run): %s", e)

    # Reset SQLite memory for a clean cross-session demo.
    if settings.sqlite_path.exists():
        log.info("Removing SQLite memory at %s", settings.sqlite_path)
        settings.sqlite_path.unlink()

    # Run the same per-document ingestion pipeline used by the API and
    # the upcoming UI upload form (Phase 6: PDF -> Markdown -> metadata
    # sidecar -> ChromaDB).
    ingest_result = ingest_document(
        SAMPLE_PDF,
        extra_metadata={
            "title": "ACME Auto Policy (smoke test fixture)",
            "year": 2026,
            "description": "Synthetic insurance policy for end-to-end testing.",
            "keywords": ["smoke-test", "auto", "policy"],
            "language": "en",
            "document_category": ["policy", "smoke-test"],
        },
    )
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
                    "page": c.page,
                    "content": c.content,
                    "download_url": f"/sources/{c.source}",
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
        print(f"Memory      : {len(history)} history msgs, "
              f"{len(activity)} activity msgs")
        if result.route == "rag":
            print(f"Validated   : {result.validated}")
            print(f"Retries     : {result.retry_count}")
        if result.route in ("rag", "report"):
            print("Citations   :")
            for c in result.citations:
                print(f"  - {c.as_citation()}")
        print(f"\n[elapsed: {dt:.1f}s]")

    print("\n" + "=" * 72)
    print(f"Smoke test complete. Conversation id={conv_id} for user "
          f"{USER_ID!r} persisted in SQLite.")
    print("=" * 72 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
