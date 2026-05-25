"""Streamlit frontend - entrypoint for `streamlit run`.

Features:
  - Token-streamed answers via st.write_stream.
  - Shows the reformulated query (transparency).
  - Each citation gets a "View chunk" popover and a "Download PDF" link.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st  # noqa: E402

from app.ui.api_client import (  # noqa: E402
    get_health,
    source_url,
    stream_chat,
)

st.set_page_config(page_title="Insurance Assistant", layout="wide")
st.title("Insurance Assistant - Local RAG PoC")

with st.sidebar:
    st.subheader("Backend status")
    try:
        h = get_health()
        st.success(f"API reachable - Ollama: {h['ollama_reachable']}")
    except Exception as e:
        st.error(f"API unreachable: {e}")
    st.caption(
        "Phase 1: reformulation + streaming RAG. "
        "Phase 2 will add the LangGraph supervisor."
    )

if "history" not in st.session_state:
    st.session_state.history = []


def render_citations(citations: list[dict]) -> None:
    if not citations:
        return
    st.markdown("**Sources**")
    for i, c in enumerate(citations, start=1):
        cols = st.columns([4, 2, 2])
        cols[0].caption(f"[{i}] {c['source']} - page {c['page']}")
        cols[1].link_button(
            "Download PDF",
            source_url(c["source"]),
            use_container_width=True,
        )
        with cols[2].popover(
            f"View chunk {i}", use_container_width=True
        ):
            st.markdown(f"**{c['source']} (p. {c['page']})**")
            st.text(c.get("content", "") or "(no content captured)")


def render_reformulation(reformulated: str, original: str) -> None:
    if not reformulated or reformulated.strip() == original.strip():
        return
    with st.expander("Reformulated query (used for retrieval)"):
        st.code(reformulated, language="text")


# Replay prior turns
for entry in st.session_state.history:
    with st.chat_message(entry["role"]):
        if entry["role"] == "assistant":
            render_reformulation(
                entry.get("reformulated_query", ""),
                entry.get("original_question", ""),
            )
        st.write(entry["content"])
        if entry["role"] == "assistant":
            render_citations(entry.get("citations", []))

question = st.chat_input("Ask about a policy...")
if question:
    st.session_state.history.append(
        {"role": "user", "content": question}
    )
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        meta_slot = st.empty()
        citations: list[dict] = []
        reformulated_holder = {"value": ""}
        error_holder = {"value": ""}

        def token_stream():
            for event in stream_chat(question):
                etype = event.get("type")
                if etype == "meta":
                    reformulated_holder["value"] = event.get(
                        "reformulated_query", ""
                    )
                    if reformulated_holder["value"]:
                        meta_slot.info(
                            "Reformulated query used for retrieval: "
                            f"_{reformulated_holder['value']}_"
                        )
                elif etype == "token":
                    yield event["value"]
                elif etype == "done":
                    citations.extend(event.get("citations", []))
                elif etype == "error":
                    error_holder["value"] = event.get("value", "")

        try:
            answer = st.write_stream(token_stream())
        except Exception as e:
            answer = ""
            error_holder["value"] = str(e)

        if error_holder["value"]:
            st.error(f"Backend error: {error_holder['value']}")

        render_citations(citations)

        st.session_state.history.append(
            {
                "role": "assistant",
                "content": answer,
                "citations": citations,
                "reformulated_query": reformulated_holder["value"],
                "original_question": question,
            }
        )
