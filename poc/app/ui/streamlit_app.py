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
    upload_document,
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
        ("decline", "Decline"),
    ],
    # Phase 7 - terminal branches that end the turn with one assistant
    # message and no validator step.
    "needs_clarification": [
        ("supervisor", "Supervisor"),
        ("clarifier", "Clarifier"),
    ],
    "out_of_year": [
        ("supervisor", "Supervisor"),
        ("fallback", "Year Fallback"),
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
    with st.expander("📤 Upload document", expanded=False):
        uploaded_file = st.file_uploader(
            "PDF",
            type=["pdf"],
            label_visibility="collapsed",
            key="ingest_uploader",
        )
        up_title = st.text_input(
            "Title", placeholder="e.g. ACME Auto Policy 2025"
        )
        up_year_str = st.text_input(
            "Year", placeholder="e.g. 2025"
        )
        up_keywords = st.text_input(
            "Keywords", placeholder="comma-separated"
        )
        up_category = st.text_input(
            "Document category", placeholder="e.g. policy, guidelines"
        )
        if st.button(
            "Ingest",
            disabled=uploaded_file is None,
            use_container_width=True,
        ) and uploaded_file is not None:
            up_year: int | None = None
            if up_year_str.strip():
                try:
                    up_year = int(up_year_str.strip())
                except ValueError:
                    st.warning("Year must be an integer; ignoring.")
            with st.spinner(f"Ingesting {uploaded_file.name} ..."):
                try:
                    result = upload_document(
                        uploaded_file.name,
                        uploaded_file.getvalue(),
                        title=up_title or None,
                        year=up_year,
                        keywords=up_keywords or None,
                        document_category=up_category or None,
                    )
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Upload failed: {exc}")
                else:
                    # `st.toast` survives the rerun (st.success would
                    # be wiped). Toast pops at the bottom-right; the
                    # rerun then refreshes the conversation list and
                    # any downstream queries pick up the new chunks.
                    st.toast(
                        f"Indexed {result.get('chunks_indexed', '?')} "
                        f"chunks from {uploaded_file.name} "
                        f"({result.get('page_count', '?')} pages)",
                        icon="✅",
                    )
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
        "- 6 · per-document ingestion (PDF -> Markdown -> Chroma)\n"
        "- 7 · year-aware retrieval + clarifier + audit trail"
    )


# --- Render helpers ---


def render_stepper(slot, stages: dict, route: str = "_default") -> None:
    """Horizontal stage timeline for the active route.

    Renders every stage of the active route from turn start, so the
    user sees the full pipeline they're about to traverse and watches
    it light up as the backend reports `stage` events. Completed steps
    flip to green, the running step shows an indeterminate-progress
    blue badge, pending steps stay greyed.
    """
    labels = STAGE_SETS.get(route, STAGE_SETS["_default"])
    with slot.container():
        cols = st.columns(len(labels))
        for idx, (col, (key, label)) in enumerate(zip(cols, labels)):
            status = stages.get(key, "pending")
            arrow = "" if idx == 0 else " → "
            if status == "done":
                col.success(f"{arrow}✓ {label}")
            elif status == "running":
                col.info(f"{arrow}⟳ {label} …")
            else:
                # Pending step: greyed so the user can see what's next.
                col.markdown(
                    f"<div style='padding: .5rem .75rem; "
                    f"border-radius: .375rem; "
                    f"background-color: rgba(120,120,120,.08); "
                    f"color: rgba(180,180,180,.6); "
                    f"font-size: .92rem;'>"
                    f"{arrow}○ {label}</div>",
                    unsafe_allow_html=True,
                )


def render_citations(citations: list[dict]) -> None:
    """Group citations by source PDF.

    Each PDF appears once with the retrieval-rank indexes it contributed
    ("chunks 1, 3, 5"), a single Download PDF button, then the section
    titles + per-chunk View popovers stacked underneath. Avoids the
    visual noise of `[1] foo.pdf / [2] foo.pdf / [3] foo.pdf` when
    multiple top-k hits come from the same document.
    """
    if not citations:
        return
    st.markdown("**Sources**")

    # Preserve retrieval rank as the citation "number" - the chunks
    # are ordered by similarity, so the lowest index is the closest
    # hit and that's what we want to show.
    by_source: dict[str, list[tuple[int, dict]]] = {}
    for i, c in enumerate(citations, start=1):
        by_source.setdefault(c["source"], []).append((i, c))

    for source, items in by_source.items():
        chunk_nums = ", ".join(str(i) for i, _ in items)
        n = len(items)
        chunk_label = (
            f"chunk {chunk_nums}" if n == 1 else f"chunks {chunk_nums}"
        )

        header_cols = st.columns([6, 2])
        header_cols[0].markdown(
            f"📄 **{source}**  ·  _{chunk_label}_"
        )
        header_cols[1].link_button(
            "Download PDF",
            source_url(source),
            use_container_width=True,
        )

        for i, c in items:
            section = (c.get("section") or "").strip()
            section_title = (c.get("section_title") or "").strip()
            section_display = section_title or section or "(unsectioned)"

            row = st.columns([1, 5, 2])
            row[0].caption(f"  [{i}]")
            row[1].caption(section_display)
            with row[2].popover(
                f"View chunk {i}", use_container_width=True
            ):
                header = f"**{source}**  ·  _chunk {i}_"
                if section_display and section_display != "(unsectioned)":
                    header += f"  \n_Section: {section_display}_"
                st.markdown(header)
                st.text(
                    c.get("content", "") or "(no content captured)"
                )


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

# Streamlit re-runs top-to-bottom on every event; the `processing`
# flag stays True from submission until the streaming finishes, so
# the chat_input is greyed out and the user can't fire a second
# question while the agent is mid-flight.
is_processing = st.session_state.get("processing", False)
question = st.chat_input(
    (
        "Working on your last question..."
        if is_processing
        else "Ask about a policy, or request a report..."
    ),
    disabled=is_processing,
)
if question:
    st.session_state.processing = True
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
                        # Order matters: check the more-specific Phase 7
                        # routes before the generic "rag" substring.
                        if "needs_clarification" in info:
                            route_holder["value"] = "needs_clarification"
                        elif "out_of_year" in info:
                            route_holder["value"] = "out_of_year"
                        elif "out_of_scope" in info:
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
        elif route_holder["value"] == "needs_clarification":
            st.caption(
                "I asked a clarifying question - your next reply "
                "will restart the routing."
            )
        elif route_holder["value"] == "out_of_year":
            st.caption(
                "Out-of-year fallback - the requested year isn't "
                "in the knowledge base."
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

        # Stream is finished - re-enable the chat input on the next
        # rerun. We trigger that rerun explicitly so the disabled
        # input flips back to active immediately instead of waiting
        # for the user to interact again.
        st.session_state.processing = False
        st.rerun()
