"""Validator node - LLM-as-judge for groundedness and citation correctness.

Phase 5: span attributes capture grounded/citations_ok/retry decision.
"""
import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from app.graph.state import GraphState
from app.llm import load_prompt
from app.llm.ollama_client import get_llm
from app.observability.logging import get_logger
from app.observability.metrics import record_validator_outcome, track_node
from app.observability.tracing import annotate_request_span, get_tracer
from app.rag.retriever import RetrievedChunk

log = get_logger(__name__)
tracer = get_tracer(__name__)

VALIDATOR_PROMPT = load_prompt("validator")


def _format_context(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "(no chunks were retrieved)"
    return "\n\n".join(
        f"[{i + 1}] {c.source} (p. {c.page})\n{c.content}"
        for i, c in enumerate(chunks)
    )


def _parse_validation(raw: str) -> dict:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    log.warning("Validator output not parseable as JSON: %r", raw[:120])
    return {"grounded": True, "citations_ok": True, "critique": ""}


def validator_node(state: GraphState) -> dict:
    answer = state.get("draft_answer", "")
    chunks = state.get("chunks", [])
    question = state.get("question", "")
    retry_count = state.get("retry_count", 0)

    with tracer.start_as_current_span("validator.judge") as span, \
            track_node("validator", route="rag"):
        annotate_request_span(
            span,
            user_id=state.get("user_id"),
            conversation_id=state.get("conversation_id"),
        )
        span.set_attribute("validator.answer_chars", len(answer))
        span.set_attribute("validator.chunk_count", len(chunks))
        span.set_attribute("validator.retry_count", retry_count)

        log.info(
            "Validator checking %d-char answer against %d chunk(s) "
            "[retry=%d]",
            len(answer),
            len(chunks),
            retry_count,
        )

        user_msg = (
            f"QUESTION:\n{question}\n\n"
            f"ANSWER:\n{answer}\n\n"
            f"CONTEXT:\n{_format_context(chunks)}"
        )

        result = get_llm().invoke(
            [
                SystemMessage(content=VALIDATOR_PROMPT),
                HumanMessage(content=user_msg),
            ]
        )
        parsed = _parse_validation(str(result.content))

        grounded = bool(parsed.get("grounded", True))
        citations_ok = bool(parsed.get("citations_ok", True))
        critique = str(parsed.get("critique", "")).strip()

        span.set_attribute("validator.grounded", grounded)
        span.set_attribute("validator.citations_ok", citations_ok)
        if critique:
            span.set_attribute("validator.critique", critique[:200])

        log.info(
            "Validation: grounded=%s citations_ok=%s critique=%r",
            grounded,
            citations_ok,
            critique[:80],
        )

        passed = grounded and citations_ok
        record_validator_outcome(passed=passed, retry_count=retry_count)
        update: dict = {
            "validation": {
                "grounded": grounded,
                "citations_ok": citations_ok,
                "critique": critique,
            },
        }

        if passed or retry_count >= 1:
            update["final_answer"] = answer
            update["final_citations"] = chunks
            update["validated"] = passed
            span.set_attribute("validator.terminal", True)
        else:
            update["retry_count"] = retry_count + 1
            update["last_critique"] = critique
            span.set_attribute("validator.terminal", False)

        return update
