"""Prompt-time conversation compression for long-running conversations.

When a conversation grows beyond the recent_n window, this module condenses
the older slice into a single synthetic system message so the LLM context
stays bounded without losing critical earlier context.

Returns an empty string when the LLM is unavailable; the caller falls back
to returning only the recent slice in that case.
"""
from __future__ import annotations

from agentic_backend.observability.logging import get_logger

log = get_logger(__name__)

_SUMMARY_PROMPT = (
    "Summarize the following conversation excerpt in 2-3 sentences. "
    "Preserve key facts, decisions, and user intent. "
    "Write in third person past tense.\n\n"
    "{transcript}"
)

_MAX_TRANSCRIPT_CHARS = 8_000


def summarize_messages(messages: list[dict]) -> str:
    """Return a single-string digest of *messages*, or '' on failure.

    Args:
        messages: List of dicts with at least ``role`` and ``content`` keys.

    Returns:
        Summary string, or empty string when the LLM is unreachable.
    """
    if not messages:
        return ""

    transcript_lines = [
        f"{m['role'].upper()}: {m.get('content', '')}"
        for m in messages
        if m.get("content")
    ]
    transcript = "\n".join(transcript_lines)[:_MAX_TRANSCRIPT_CHARS]

    try:
        from agentic_backend.llm.ollama_client import chat_completion

        result = chat_completion(_SUMMARY_PROMPT.format(transcript=transcript))
        return result or ""
    except Exception as exc:
        log.warning("Memory summarization unavailable, skipping: %s", exc)
        return ""
