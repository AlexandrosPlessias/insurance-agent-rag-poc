"""RAG worker agent — retrieval-augmented answering over policy documents."""
from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage

from app.llm.ollama_client import get_llm
from app.rag.retriever import RetrievedChunk, retrieve

SYSTEM_PROMPT = """You are an enterprise insurance assistant. Answer the user's \
question strictly using the provided context. If the context does not contain the \
answer, say so explicitly — do not invent information. Cite the source documents \
and page numbers you used.

Context:
{context}
"""


@dataclass
class RagResponse:
    answer: str
    citations: list[RetrievedChunk]


def answer_question(question: str) -> RagResponse:
    chunks = retrieve(question)
    context = "\n\n".join(
        f"[{i + 1}] {c.as_citation()}\n{c.content}" for i, c in enumerate(chunks)
    )
    messages = [
        SystemMessage(content=SYSTEM_PROMPT.format(context=context or "(no documents indexed)")),
        HumanMessage(content=question),
    ]
    result = get_llm().invoke(messages)
    return RagResponse(answer=str(result.content), citations=chunks)
