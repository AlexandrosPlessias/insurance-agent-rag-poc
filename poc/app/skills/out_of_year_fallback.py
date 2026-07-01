"""Skill: out-of-year-fallback — graceful refusal for uncovered years."""
from app.llm import load_prompt
from app.skills import Skill

skill = Skill(
    name="out-of-year-fallback",
    description=(
        "Gracefully decline a question about a year not covered by the "
        "knowledge base, and offer the nearest covered years instead."
    ),
    owner_worker="any",
    model="qwen2.5:7b",
    system_prompt=load_prompt("skills/out_of_year_fallback"),
    input_fields={
        "requested_year": "int – the year the user asked about",
    },
    tools_used=[],
)
