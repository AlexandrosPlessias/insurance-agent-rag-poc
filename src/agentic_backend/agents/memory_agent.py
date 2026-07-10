"""Memory helpers used by RAG and report agents.

Not a graph node - just utility functions for formatting persistent
memory into prompt-friendly strings.
"""
from agentic_backend.observability.logging import get_logger

log = get_logger(__name__)

MAX_HISTORY_CHARS = 1600  # per turn truncation guardrail


def _truncate(text: str, limit: int = MAX_HISTORY_CHARS) -> str:
    if not text:
        return ""
    return text if len(text) <= limit else text[: limit - 3] + "..."


def format_history_for_prompt(
    history: list[dict],
    max_turns: int = 3,
) -> str:
    """Render the last N turns as a 'RECENT CONVERSATION' block.

    `history` is a list of {role, content, ...} dicts in chronological
    order. Returns "" if there is no usable history.
    """
    if not history:
        return ""
    # Take the last 2*max_turns messages (user+assistant pairs).
    recent = history[-(2 * max_turns):]
    lines = ["RECENT CONVERSATION:"]
    for msg in recent:
        role = msg.get("role", "?").upper()
        content = _truncate(str(msg.get("content", "")))
        lines.append(f"  {role}: {content}")
    return "\n".join(lines) + "\n"


def format_user_activity(activity: list[dict]) -> list[str]:
    """Render cross-conversation activity as a list of bullet strings.

    `activity` is a list of {content, created_at, title, ...} dicts from
    MemoryStore.get_user_activity (newest first). Returns a list of
    Markdown bullet lines or [] when empty.
    """
    if not activity:
        return []
    bullets: list[str] = []
    for msg in activity:
        ts = str(msg.get("created_at", "")).split(".")[0]
        title = msg.get("title") or "(untitled)"
        content = _truncate(str(msg.get("content", "")), limit=140)
        bullets.append(f"- *{ts}* [{title}] {content}")
    return bullets
