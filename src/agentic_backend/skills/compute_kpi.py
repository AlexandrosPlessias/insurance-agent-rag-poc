"""Skill: compute-kpi — translate a question into a typed KPI query."""
from agentic_backend.llm import load_prompt
from agentic_backend.skills import Skill

skill = Skill(
    name="compute-kpi",
    description=(
        "Compute an insurance KPI or financial metric from the analytics "
        "dataset (NOT from policy PDFs). Use this skill for any question "
        "about numbers, volumes, or rates: gross written premium (GWP), "
        "loss ratio, renewal rate, NPS, churn, claim count, premium income, "
        "or any other business metric. Translates the question into a typed "
        "Operation (metric, filters, aggregation, group_by) and renders a "
        "Markdown table."
    ),
    owner_worker="data",
    model="qwen2.5:7b",
    system_prompt=load_prompt("skills/compute_kpi"),
    input_fields={
        "question": "the user's analytics question (str)",
        "year": "optional int – primary year filter",
    },
    tools_used=["kpi_query", "clarifier_check"],
)
