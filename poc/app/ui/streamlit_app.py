"""Streamlit frontend - Phase 5.

Adds:
  - setup_otel() so httpx calls to the backend are traced.
  - "Aspire Dashboard" link in the sidebar when OTEL_ENABLED=true.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st  # noqa: E402

from app.config import settings  # noqa: E402
from app.observability.tracing import setup_otel  # noqa: E402
from app.ui.api_client import (  # noqa: E402
    get_health,
    get_messages,
    list_conversations,
    source_url,
    stream_chat,
)

# Initialise OTel for the UI process - no-op if OTEL_ENABLED=false.
setup_otel(service_suffix="ui")

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

# --- Session-state defaults ---
if "user_id" not in st.session_state:
    st.session_state.user_id = "default_user"
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None
if "history" not in st.session_state:
    st.session_state.history = []


def _load_history(conv_id: int) -> list[dict]:
    """Convert backend messages into the local history format."""
    try:
        raw = get_messages(conv_id)
    except Exception as e:
        st.error(f"Failed to load messages: {e}")
        return []
    history: list[dict] = []
    for m in raw:
        entry: dict = {
            "role": m["role"],
            "content": m["content"],
        }
        if m["role"] == "assistant":
            entry.update(
                {
                    "route": m.get("route") or "",
                    "citations": m.get("citations") or [],
                    "validated": True,
                    "critique": "",
                    "reformulated_query": "",
                    "original_question": "",
                }
            )
        history.append(entry)
    return history


def _switch_conversation(conv_id: int) -> None:
    st.session_state.conversation_id = conv_id
    st.session_state.history = _load_history(conv_id)


def _start_new_conversation() -> None:
    st.session_state.conversation_id = None
    st.session_state.history = []


# --- Sidebar ---
with st.sidebar:
    st.subheader("User")
    new_user = st.text_input(
        "User ID",
        value=st.session_state.user_id,
        help="Identifies the owner of conversations and long-term memory.",
    )
    if new_user != st.session_state.user_id:
        st.session_state.user_id = new_user
        _start_new_conversation()

    st.divider()
    st.subheader("Conversations")
    if st.button("+ New conversation", use_container_width=True):
        _start_new_conversation()
        st.rerun()

    try:
        convos = list_conversations(st.session_state.user_id)
    except Exception as e:
        convos = []
        st.error(f"Failed to list conversations: {e}")

    if not convos:
        st.caption("No saved conversations yet.")
    for c in convos:
        is_current = c["id"] == st.session_state.conversation_id
        label = c.get("title") or f"Conversation {c['id']}"
        if is_current:
            label = f"* {label}"
        if st.button(
            label,
            key=f"conv_{c['id']}",
            use_container_width=True,
        ):
            _switch_conversation(c["id"])
            st.rerun()

    st.divider()
    st.subheader("Backend status")
    try:
        h = get_health()
        st.success(f"API reachable - Ollama: {h['ollama_reachable']}")
    except Exception as e:
        st.error(f"API unreachable: {e}")

    if settings.otel_enabled:
        st.divider()
        st.subheader("Observability")
        st.link_button(
            "Open Aspire Dashboard",
            settings.otel_ui_url,
            use_container_width=True,
        )
        st.caption(
            "OTel is on - traces and logs stream to "
            f"`{settings.otel_endpoint}`."
        )

    st.markdown(
        "**Implemented phases**\n"
        "- 1 · streaming RAG with citations\n"
        "- 2 · supervisor + validator + retry\n"
        "- 3 · report agent (Markdown + charts)\n"
        "- 4 · SQLite long-term memory\n"
        "- 5 · OpenTelemetry (traces + logs + metrics)\n"
        "- 6 · per-document ingestion (PDF -> Markdown -> Chroma)"
    )


# --- Render helpers ---


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
        # Prefer the cleaned section_title (e.g. "Refund Policy"); fall
        # back to the verbatim section (e.g. "1. Refund Policy") so we
        # still show something for chunks that lack section_title.
        section = (c.get("section") or "").strip()
        section_title = (c.get("section_title") or "").strip()
        section_display = section_title or section
        page = c.get("page", 0)

        # Build the caption text. Page is shown only when present and
        # > 0 (older indexed chunks may still have it).
        bits = [f"[{i}] {c['source']}"]
        if page:
            bits.append(f"p.{page}")
        if section_display:
            bits.append(section_display)
        caption_text = "  ·  ".join(bits)

        cols = st.columns([4, 2, 2])
        cols[0].caption(caption_text)
        cols[1].link_button(
            "Download PDF",
            source_url(c["source"]),
            use_container_width=True,
        )
        with cols[2].popover(
            f"View chunk {i}", use_container_width=True
        ):
            header = f"**{c['source']}**"
            if page:
                header += f" (p. {page})"
            if section_display:
                header += f"  \n_Section: {section_display}_"
            st.markdown(header)
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
            if route == "report":
                st.markdown(entry["content"], unsafe_allow_html=False)
            else:
                st.write(entry["content"])
            if route == "rag":
                render_validation(
                    entry.get("validated", True),
                    entry.get("critique", ""),
                )
            render_citations(entry.get("citations", []))
        else:
            st.write(entry["content"])

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
            for event in stream_chat(
                question,
                user_id=st.session_state.user_id,
                conversation_id=st.session_state.conversation_id,
            ):
                etype = event.get("type")
                if etype == "conversation":
                    cid = event.get("conversation_id")
                    if cid is not None:
                        st.session_state.conversation_id = int(cid)
                elif etype == "stage":
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
                        route_holder["value"] = event.get(
                            "route", ""
                        )
                elif etype == "error":
                    error_holder["value"] = event.get("value", "")

        try:
            answer = st.write_stream(token_stream())
        except Exception as e:
            answer = ""
            error_holder["value"] = str(e)

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
