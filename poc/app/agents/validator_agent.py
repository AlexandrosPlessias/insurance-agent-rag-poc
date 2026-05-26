"""Validator node - LLM-as-judge for groundedness and citation correctness.

Returns a state update with:
  - validation: {grounded, citations_ok, critique}
  - retry_count: incremented on failure (when retry is allowed)
  - last_critique: critique text passed back to RAG on retry
  - final_answer / final_citations / validated: set on terminal acceptance
"""
import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from app.graph.state import GraphState
from app.llm import load_prompt
from app.llm.ollama_client import get_llm
from app.observability.logging import get_logger
from app.rag.retriever import RetrievedChunk

log = get_logger(__name__)

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
    # Fail-open for PoC: assume valid so we don't loop forever on parse errors.
    return {"grounded": True, "citations_ok": True, "critique": ""}


def validator_node(state: GraphState) -> dict:
    answer = state.get("draft_answer", "")
    chunks = state.get("chunks", [])
    question = state.get("question", "")
    retry_count = state.get("retry_count", 0)

    log.info(
        "Validator checking %d-char answer against %d chunk(s) [retry=%d]",
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

    log.info(
        "Validation: grounded=%s citations_ok=%s critique=%r",
        grounded,
        citations_ok,
        critique[:80],
    )

    passed = grounded and citations_ok
    update: dict = {
        "validation": {
            "grounded": grounded,
            "citations_ok": citations_ok,
            "critique": critique,
        },
    }

    if passed or retry_count >= 1:
        # Terminal: persist as the final answer.
        update["final_answer"] = answer
        update["final_citations"] = chunks
        update["validated"] = passed
    else:
        # Loop back to RAG with the critique.
        update["retry_count"] = retry_count + 1
        update["last_critique"] = critique

    return update
