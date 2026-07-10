"""Tool: knowledge_base_lookup — direct fetch of a processed KB section."""
from __future__ import annotations

from pathlib import Path

from agentic_backend.config import settings
from agentic_backend.tools import AgentTool


def _run(doc_id: str, section: str = "") -> str:
    """Read a processed Markdown document (optionally a named section).

    Args:
        doc_id: filename stem of a document in the processed dir
            (e.g. "acme_policy_2024").
        section: optional heading to extract (case-insensitive prefix match).

    Returns:
        Markdown text of the document or section, or an empty string if
        not found.
    """
    processed_dir: Path = settings.processed_dir
    candidate = processed_dir / f"{doc_id}.md"
    if not candidate.exists():
        return ""

    text = candidate.read_text(encoding="utf-8")

    if not section:
        return text

    # Extract the named section: return lines from the matching heading
    # up to the next same-or-higher-level heading.
    lines = text.splitlines()
    section_lower = section.lower()
    in_section = False
    section_level = 0
    collected: list[str] = []
    for line in lines:
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            heading_text = line.lstrip("#").strip().lower()
            if not in_section:
                if heading_text.startswith(section_lower):
                    in_section = True
                    section_level = level
                    collected.append(line)
            else:
                if level <= section_level:
                    break
                collected.append(line)
        elif in_section:
            collected.append(line)

    return "\n".join(collected)


tool = AgentTool(
    name="knowledge_base_lookup",
    description=(
        "Fetch a processed Markdown document or a named section from the "
        "knowledge base by document ID (stem of the .md filename)."
    ),
    input_fields={
        "doc_id": "filename stem of the processed document (without .md)",
        "section": "optional heading to extract (case-insensitive prefix)",
    },
    run=_run,
)
