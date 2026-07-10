"""Skill: decline — politely refuse out-of-scope questions."""
from agentic_backend.skills import Skill

skill = Skill(
    name="decline",
    description=(
        "Politely refuse to answer a question that has NOTHING to do with "
        "insurance, company policies, KPI metrics, or the ACME knowledge base. "
        "Use this for arithmetic, general knowledge, geography, coding, jokes, "
        "or any topic entirely outside ACME's insurance domain. "
        "Do NOT use this for insurance questions that are merely hard to answer."
    ),
    owner_worker="any",
    model="",
    system_prompt="",
    input_fields={},
    tools_used=[],
)
