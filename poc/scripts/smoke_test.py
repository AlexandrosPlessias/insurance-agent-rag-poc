"""End-to-end smoke test (no external PDFs needed).

Synthesises a small ACME insurance policy PDF, ingests it, runs 3 sample
queries through the RAG agent, and prints answers + citations.

Run from poc/:  python scripts/smoke_test.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fitz  # PyMuPDF  # noqa: E402

from app.agents.rag_agent import answer_question  # noqa: E402
from app.observability.logging import configure_logging, get_logger  # noqa: E402
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
    "What is the deductible for collision claims?",
    "How many days do I have to report a claim?",
    "What is the annual premium and can I pay in installments?",
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


def main() -> int:
    print("\n" + "=" * 70)
    print("Phase 1 smoke test — local RAG over a synthetic insurance policy")
    print("=" * 70 + "\n")

    build_sample_pdf(SAMPLE_PDF)

    log.info("Resetting Chroma collection for a clean run ...")
    try:
        reset_collection()
    except Exception as e:
        log.warning("reset_collection failed (probably first run): %s", e)

    documents = load_pdf(SAMPLE_PDF)
    chunks = chunk_documents(documents)
    add_documents(chunks)

    for q in SAMPLE_QUESTIONS:
        print("\n" + "-" * 70)
        print(f"Q: {q}")
        print("-" * 70)
        t0 = time.perf_counter()
        result = answer_question(q)
        dt = time.perf_counter() - t0
        print(f"A: {result.answer}\n")
        print("Citations:")
        for c in result.citations:
            print(f"  - {c.as_citation()}")
        print(f"\n[elapsed: {dt:.1f}s]")

    print("\n" + "=" * 70)
    print("Smoke test complete.")
    print("=" * 70 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
