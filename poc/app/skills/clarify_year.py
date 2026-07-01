"""Skill: clarify-year — ask the user which policy year they mean."""
from app.llm import load_prompt
from app.skills import Skill

skill = Skill(
    name="clarify-year",
    description=(
        "Ask the user one targeted clarifying question when no policy year "
        "can be resolved from the question or conversation history."
    ),
    owner_worker="any",
    model="qwen2.5:7b",
    system_prompt=load_prompt("skills/clarify_year"),
    input_fields={
        "question": "the user's original question (str)",
        "reason": (
            "why clarification is needed: "
            "'year_missing' | 'year_gap' | 'ambiguous_clause'"
        ),
    },
    tools_used=[],
)
