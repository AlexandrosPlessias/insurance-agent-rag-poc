"""Skill: answer-policy-question — year-scoped RAG with citations."""
from app.llm import load_prompt
from app.skills import Skill

skill = Skill(
    name="answer-policy-question",
    description=(
        "Answer a question about insurance policy terms, exclusions, or "
        "procedures using semantic retrieval from the knowledge base. "
        "Returns a grounded answer with inline citations."
    ),
    owner_worker="rag",
    model="qwen2.5:7b",
    system_prompt=load_prompt("skills/answer_policy_question"),
    input_fields={
        "query": "the user's policy question (str)",
        "year": "optional int – policy year to scope the search to",
    },
    tools_used=["vector_search", "clarifier_check"],
)
