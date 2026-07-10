"""Skill: executive-section-summary — annual report section pipeline."""
from agentic_backend.skills import Skill

skill = Skill(
    name="executive-section-summary",
    description=(
        "Generate an executive annual report for a given policy year. "
        "Pulls KPI data and policy context, writes narrative sections, "
        "and returns a full Markdown report with risk indicators."
    ),
    owner_worker="report",
    model="qwen2.5:7b",
    # Executive section prompts live in prompts/executive/ — loaded by
    # the report agent internally, so no top-level system_prompt here.
    system_prompt="",
    input_fields={
        "year": "int – the policy year for the annual report",
    },
    tools_used=["kpi_query", "vector_search", "knowledge_base_lookup"],
    requires_approval=True,
)
