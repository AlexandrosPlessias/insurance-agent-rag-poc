"""LLM client factories and prompt loading."""
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    """Read a prompt template from app/llm/prompts/{name}.txt.

    Subdirectories are supported — pass ``"skills/my_skill"`` to load
    ``app/llm/prompts/skills/my_skill.txt``.  Skill prompts live under
    ``prompts/skills/``; the planner prompt lives at ``prompts/planner.txt``.
    """
    path = _PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8").rstrip("\n")
