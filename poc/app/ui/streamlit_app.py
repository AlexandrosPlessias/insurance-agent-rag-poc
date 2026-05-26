"""Streamlit frontend - Phase 3.

Adds dynamic progress stepper that adapts to the route:
  - rag:          Supervisor -> RAG -> Validator
  - report:       Supervisor -> Report
  - out_of_scope: Supervisor
Reports render as Markdown with embedded charts.
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

STAGE_SETS = {
    "rag": [
        ("supervisor", "Supervisor"),
        ("rag", "RAG"),
        ("validator", "Validator"),
    ],
    "report": [
        ("supervisor", "Supervisor"),
        ("report", "Report"),
    ],
    "out_of_scope": [
        ("supervisor", "Supervisor"),
    ],
    "_default": [
        ("supervisor", "Supervisor"),
        ("rag", "RAG"),
        ("validator", "Validator"),
    ],
}

with st.sidebar:
    st.subheader("Backend status")
    try:
        h = get_health()
        st.success(f"API reachable - Ollama: {h['ollama_reachable']}")
    except Exception as e:
        st.error(f"API unreachable: {e}")
    st.caption(
        "Phase 1: reformulation + streaming RAG.\n"
        "Phase 2: supervisor + validator with 1-retry loop.\n"
        "Phase 3: report agent (Markdown + embedded chart)."
    )

if "history" not in st.session_state:
    st.session_state.history = []


def render_stepper(slot, stages: dict, route: str = "_default") -> None:
    labels = STAGE_SETS.get(route, STAGE_SETS["_default"])
    with slot.container():
        cols = st.columns(len(labels))
        for col, (key, label) in zip(cols, labels):
            status = stages.get(key, "pending")
            if status == "done":
                col.success(f"+ {label}")
            elif status == "running":
                col.info(f"~ {label}")
            else:
                col.caption(f"o {label}")


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


def render_validation(validated: bool, critique: str) -> None:
    if validated:
        st.success("Validated - grounded and citations correct")
    else:
        msg = "Unverified - validator failed after retry"
        if critique:
            msg += f"\n\nCritique: {critique}"
        st.warning(msg)


def render_reformulation(reformulated: str, original: str) -> None:
    if not reformulated or reformulated.strip() == original.strip():
        return
    with st.expander("Reformulated query (used for retrieval)"):
        st.code(reformulated, language="text")


def render_answer(content: str, route: str) -> None:
    if route == "report":
        # Reports are full Markdown with embedded images.
        st.markdown(content, unsafe_allow_html=False)
    else:
        st.write(content)


# --- Replay prior turns ---
for entry in st.session_state.history:
    with st.chat_message(entry["role"]):
        route = entry.get("route", "")
        if entry["role"] == "assistant":
            if route == "rag":
                render_reformulation(
                    entry.get("reformulated_query", ""),
                    entry.get("original_question", ""),
                )
        render_answer(entry["content"], route) if entry[
            "role"
        ] == "assistant" else st.write(entry["content"])
        if entry["role"] == "assistant":
            if route == "rag":
                render_validation(
                    entry.get("validated", True),
                    entry.get("critique", ""),
                )
            render_citations(entry.get("citations", []))

question = st.chat_input("Ask about a policy, or request a report...")
if question:
    st.session_state.history.append(
        {"role": "user", "content": question}
    )
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        stepper_slot = st.empty()
        meta_slot = st.empty()
        stages: dict[str, str] = {}
        render_stepper(stepper_slot, stages, route="_default")

        citations: list[dict] = []
        validated_holder = {"value": True}
        critique_holder = {"value": ""}
        reformulated_holder = {"value": ""}
        route_holder = {"value": ""}
        error_holder = {"value": ""}
        report_holder = {"value": ""}

        def token_stream():
            for event in stream_chat(question):
                etype = event.get("type")
                if etype == "stage":
                    node = event["node"]
                    status = (
                        "running"
                        if event["status"] == "started"
                        else "done"
                    )
                    stages[node] = status
                    if (
                        node == "supervisor"
                        and event.get("status") == "done"
                    ):
                        info = event.get("info", "")
                        if "out_of_scope" in info:
                            route_holder["value"] = "out_of_scope"
                        elif "report" in info:
                            route_holder["value"] = "report"
                        elif "rag" in info:
                            route_holder["value"] = "rag"
                    render_stepper(
                        stepper_slot,
                        stages,
                        route=route_holder["value"] or "_default",
                    )
                elif etype == "meta":
                    reformulated_holder["value"] = event.get(
                        "reformulated_query", ""
                    )
                    if reformulated_holder["value"]:
                        meta_slot.info(
                            "Reformulated query: "
                            f"_{reformulated_holder['value']}_"
                        )
                elif etype == "token":
                    if route_holder["value"] == "report":
                        # Buffer report content - render as Markdown later.
                        report_holder["value"] += event["value"]
                    else:
                        yield event["value"]
                elif etype == "done":
                    citations.extend(event.get("citations", []))
                    validated_holder["value"] = event.get(
                        "validated", True
                    )
                    critique_holder["value"] = event.get(
                        "critique", ""
                    )
                    if not route_holder["value"]:
                        route_holder["value"] = event.get("route", "")
                elif etype == "error":
                    error_holder["value"] = event.get("value", "")

        try:
            answer = st.write_stream(token_stream())
        except Exception as e:
            answer = ""
            error_holder["value"] = str(e)

        # Reports were buffered, not streamed - render now.
        if route_holder["value"] == "report" and report_holder["value"]:
            answer = report_holder["value"]
            st.markdown(answer, unsafe_allow_html=False)

        if error_holder["value"]:
            st.error(f"Backend error: {error_holder['value']}")

        if route_holder["value"] == "rag":
            render_validation(
                validated_holder["value"],
                critique_holder["value"],
            )
        render_citations(citations)

        st.session_state.history.append(
            {
                "role": "assistant",
                "content": answer,
                "citations": citations,
                "reformulated_query": reformulated_holder["value"],
                "original_question": question,
                "validated": validated_holder["value"],
                "critique": critique_holder["value"],
                "route": route_holder["value"],
            }
        )
