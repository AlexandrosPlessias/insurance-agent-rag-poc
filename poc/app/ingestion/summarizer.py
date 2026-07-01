"""LLM-based document summariser for description + keywords.

Produces the two fields that power semantic search filtering:
  - description: 1-2 sentence summary (max 250 chars).
  - keywords: 5-10 lowercase tags.

A single LLM call yields both. Failures degrade gracefully to empty
results - the metadata builder falls back to filename/first-paragraph
defaults so ingestion never blocks on a slow or unavailable model.
"""
import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from app.llm import load_prompt
from app.llm.ollama_client import get_llm
from app.observability.logging import get_logger
from app.observability.tracing import get_tracer

log = get_logger(__name__)
tracer = get_tracer(__name__)

_PROMPT = load_prompt("document_summary")
# Truncate huge docs so we don't blow the LLM context window. We keep
# the top + bottom which usually capture the doc's intent and footers.
_MAX_INPUT_CHARS = 8000


def _truncate(text: str, limit: int = _MAX_INPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + "\n\n[... truncated ...]\n\n" + text[-half:]


def _parse_json(raw: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    log.warning("Summariser output not parseable as JSON: %r", raw[:120])
    return {}


def summarize_document(markdown: str) -> dict:
    """Return {"description": str, "keywords": list[str]}.

    Never raises - logs and returns empty values on any failure.
    """
    if not markdown or not markdown.strip():
        return {"description": "", "keywords": []}

    with tracer.start_as_current_span("ingestion.summarize") as span:
        span.set_attribute("input_chars", len(markdown))
        snippet = _truncate(markdown)
        log.info(
            "Summarising document (%d chars -> %d submitted)",
            len(markdown),
            len(snippet),
        )
        try:
            result = get_llm().invoke(
                [
                    SystemMessage(content=_PROMPT),
                    HumanMessage(content=snippet),
                ]
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Summariser LLM call failed: %s", exc)
            span.set_attribute("error", str(exc))
            return {"description": "", "keywords": []}

        parsed = _parse_json(str(result.content))
        description = str(parsed.get("description", "")).strip()
        raw_keywords = parsed.get("keywords") or []
        if not isinstance(raw_keywords, list):
            raw_keywords = []
        keywords = [
            str(k).strip().lower()
            for k in raw_keywords
            if isinstance(k, (str, int, float)) and str(k).strip()
        ]
        span.set_attribute("description.chars", len(description))
        span.set_attribute("keywords.count", len(keywords))
        log.info(
            "  -> %d-char description, %d keywords",
            len(description),
            len(keywords),
        )
        return {"description": description, "keywords": keywords}
