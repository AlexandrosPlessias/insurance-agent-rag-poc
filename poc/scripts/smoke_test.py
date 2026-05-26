"""End-to-end smoke test (no external PDFs needed).

Phase 3 demo:
  - Synthesises an ACME insurance policy PDF and ingests it.
  - 3 in-scope RAG questions (supervisor -> rag -> validator).
  - 1 report request (supervisor -> report).
  - 1 out-of-scope question (supervisor -> decline).

Run from poc/:  python scripts/smoke_test.py
"""
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fitz  # PyMuPDF  # noqa: E402

from app.agents.rag_agent import answer_question  # noqa: E402
from app.observability.logging import (  # noqa: E402
    configure_logging,
    get_logger,
)
from app.rag.chunker import chunk_documents  # noqa: E402
from app.rag.loader import load_pdf  # noqa: E402
from app.rag.vectorstore import add_documents, reset_collection  # noqa: E402

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
    ("report", "Give me a summary report of the policy"),
    ("out_of_scope", "What is 2 + 2?"),
]


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
    """Replace embedded base64 PNGs so terminal output stays readable."""
    return re.sub(
        r"!\[([^\]]*)\]\(data:image/[^)]+\)",
        r"![\1](embedded chart, base64 omitted)",
        markdown,
    )


def main() -> int:
    print("\n" + "=" * 72)
    print("Phase 3 smoke test - supervisor + RAG/validator + report agent")
    print("=" * 72 + "\n")

    build_sample_pdf(SAMPLE_PDF)

    log.info("Resetting Chroma collection for a clean run ...")
    try:
        reset_collection()
    except Exception as e:
        log.warning("reset_collection failed (probably first run): %s", e)

    documents = load_pdf(SAMPLE_PDF)
    chunks = chunk_documents(documents)
    add_documents(chunks)

    for expected_route, q in SAMPLE_QUESTIONS:
        print("\n" + "-" * 72)
        print(f"Q: {q}")
        print(f"   (expected route: {expected_route})")
        print("-" * 72)
        t0 = time.perf_counter()
        result = answer_question(q)
        dt = time.perf_counter() - t0
        printable = (
            _strip_data_uri_images(result.answer)
            if result.route == "report"
            else result.answer
        )
        print(f"A:\n{printable}\n")
        print(f"Route       : {result.route}")
        if result.route == "rag":
            print(f"Validated   : {result.validated}")
            print(f"Retries     : {result.retry_count}")
        if result.route in ("rag", "report"):
            print("Citations   :")
            for c in result.citations:
                print(f"  - {c.as_citation()}")
        print(f"\n[elapsed: {dt:.1f}s]")

    print("\n" + "=" * 72)
    print("Smoke test complete.")
    print("=" * 72 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
