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

# Full graph topology rendered every turn. Each tuple is
# (stage_key, label, route_that_owns_it, tools_used).
# route=None means the stage is shared across all routes (Supervisor);
# validator is only on the RAG path (route="rag"). Tools are shown as a
# small badge row under the status pill so the user can see at a glance
# what each agent calls into. Order matters for the left-to-right layout.
PIPELINE_TOPOLOGY: list[tuple[str, str, str | None, list[str]]] = [
    # tier 1 - always runs
    ("supervisor", "Supervisor", None,
        ["LLM", "regex(year)"]),
    # tier 2 - exactly one of these fires
    ("rag",        "RAG",        "rag",
        ["LLM", "Chroma", "embed"]),
    ("report",     "Report",     "report",
        ["LLM", "Chroma", "matplotlib"]),
    ("clarifier",  "Clarifier",  "needs_clarification",
        ["LLM"]),
    ("fallback",   "Fallback",   "out_of_year",
        ["template"]),
    ("decline",    "Decline",    "out_of_scope",
        ["template"]),
    # tier 3 - only on the rag path
    ("validator",  "Validator",  "rag",
        ["LLM"]),
]

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

    # Build-history reference, hidden behind an expander so the
    # sidebar stays compact. Order is chronological (1 -> 7) so the
    # reader sees the PoC's progression rather than a flat checklist.
    with st.expander("📋 Implemented phases", expanded=False):
        st.markdown(
            "✅ **Phase 1** · streaming RAG with citations  \n"
            "✅ **Phase 2** · supervisor + validator with 1-retry loop  \n"
            "✅ **Phase 3** · report agent (Markdown + embedded charts)  \n"
            "✅ **Phase 4** · SQLite long-term memory + per-user "
            "conversations  \n"
            "✅ **Phase 5** · OpenTelemetry traces · logs · metrics "
            "(Aspire)  \n"
            "✅ **Phase 6** · per-document ingestion "
            "(PDF → Markdown → ChromaDB)  \n"
            "✅ **Phase 7** · year-aware retrieval · clarifier · "
            "out-of-year fallback · audit trail · UI enrichment "
            "(full-topology stepper, grouped citations, chunk_index) · "
            "OTel log dedup"
        )


# --- Render helpers ---


def _on_active_path(route: str, owner: str | None) -> bool:
    """True iff a topology node belongs to the route the supervisor picked.

    Supervisor (owner=None) is always on the path. Tier-2 branch nodes
    are on the path only when their owning route matches. Validator
    (owner='rag') is on the path only when route='rag'.
    """
    if owner is None:
        return True
    return route == owner


def _render_tools_row(col, tools: list[str], dim: bool = False) -> None:
    """Tiny badge row under a node's status pill.

    Renders one chip per tool the agent calls into. `dim=True` is used
    for off-path branches so the badges fade with the rest of the cell.
    """
    if not tools:
        return
    base_bg = "rgba(120,140,200,.10)"
    base_color = "rgba(200,210,240,.85)"
    if dim:
        base_bg = "rgba(120,120,120,.03)"
        base_color = "rgba(150,150,150,.4)"
    chips = "".join(
        f"<span style='display: inline-block; "
        f"padding: .08rem .35rem; margin: .1rem .1rem 0 0; "
        f"border-radius: .25rem; background: {base_bg}; "
        f"color: {base_color}; font-size: .68rem; "
        f"font-family: monospace;'>"
        f"{t}</span>"
        for t in tools
    )
    col.markdown(
        f"<div style='text-align: center; margin-top: -.4rem;'>"
        f"{chips}</div>",
        unsafe_allow_html=True,
    )


def render_stepper(slot, stages: dict, route: str = "") -> None:
    """Render the full graph topology every turn.

    All seven nodes (Supervisor + 5 branches + Validator) are visible
    from the moment the turn starts so the user can see the whole
    pipeline. As the backend emits `stage` events, nodes on the active
    route's path flip green (done) or blue (running); branches the
    supervisor *didn't* pick stay greyed out, so the visualisation
    showcases every flow and the one that fired. Under each node we
    render the tools the agent calls (LLM, Chroma, embed, ...) so the
    'graphical state' surfaces what's actually being invoked.
    """
    with slot.container():
        cols = st.columns(len(PIPELINE_TOPOLOGY))
        for col, (key, label, owner, tools) in zip(cols, PIPELINE_TOPOLOGY):
            on_path = _on_active_path(route, owner)
            status = stages.get(key, "pending") if on_path else "off_path"

            if status == "done":
                col.success(f"✓ {label}")
            elif status == "running":
                col.info(f"⟳ {label} …")
            elif status == "off_path":
                # Branch we did NOT take - dimmed and visually quiet.
                col.markdown(
                    f"<div style='padding: .5rem .5rem; "
                    f"border-radius: .375rem; "
                    f"background-color: rgba(120,120,120,.04); "
                    f"color: rgba(150,150,150,.45); "
                    f"text-align: center; "
                    f"font-size: .82rem; "
                    f"text-decoration: line-through "
                    f"rgba(150,150,150,.35);'>"
                    f"{label}</div>",
                    unsafe_allow_html=True,
                )
            else:
                # On-path but not yet reached - pending pill.
                col.markdown(
                    f"<div style='padding: .5rem .75rem; "
                    f"border-radius: .375rem; "
                    f"background-color: rgba(120,140,200,.10); "
                    f"border: 1px dashed rgba(120,140,200,.35); "
                    f"color: rgba(180,200,255,.85); "
                    f"text-align: center; "
                    f"font-size: .92rem;'>"
                    f"○ {label}</div>",
                    unsafe_allow_html=True,
                )

            _render_tools_row(col, tools, dim=(status == "off_path"))


def render_citations(citations: list[dict]) -> None:
    """Group citations by source PDF.

    Each PDF appears once with the per-document chunk indexes it
    contributed ("chunks 12, 28"), a single Download PDF button, then
    the section titles + per-chunk View popovers stacked underneath.

    The chunk number shown is `metadata.chunk_index` - the chunk's
    position inside the source document, populated by the chunker.
    That's the same number printed by `scripts/inspect_chroma.py
    --report`, so the user can open a citation, jump to the report,
    and find the exact chunk. If a citation lacks chunk_index (chunks
    indexed before this change), we fall back to the retrieval rank.
    """
    if not citations:
        return
    st.markdown("**Sources**")

    # Resolve chunk number for each citation: real chunk_index from
    # metadata when available, retrieval rank as fallback.
    def _chunk_num(rank: int, citation: dict) -> int:
        ci = int(citation.get("chunk_index") or 0)
        return ci if ci > 0 else rank

    # When EVERY citation lacks chunk_index, the chunks were ingested
    # before that field existed - the numbers shown will be retrieval
    # rank, not the actual position in the document. Tell the user
    # how to populate the real numbers so they can cross-reference
    # against `scripts/inspect_chroma.py --report`.
    legacy_chunks = all(
        int(c.get("chunk_index") or 0) == 0 for c in citations
    )
    if legacy_chunks:
        st.caption(
            "ℹ️ _Chunk numbers shown are retrieval rank. "
            "To see the actual document-position chunk numbers "
            "(matching `inspect_chroma.py --report`), re-ingest:_  \n"
            "`python scripts/reset_stores.py --keep-audit "
            "&& python scripts/ingest_pdfs.py`"
        )

    by_source: dict[str, list[tuple[int, dict]]] = {}
    for rank, c in enumerate(citations, start=1):
        by_source.setdefault(c["source"], []).append(
            (_chunk_num(rank, c), c)
        )

    for source, items in by_source.items():
        chunk_nums = ", ".join(str(n) for n, _ in items)
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

        for num, c in items:
            section = (c.get("section") or "").strip()
            section_title = (c.get("section_title") or "").strip()
            section_display = section_title or section or "(unsectioned)"

            row = st.columns([1, 5, 2])
            row[0].caption(f"  [{num}]")
            row[1].caption(section_display)
            with row[2].popover(
                f"View chunk {num}", use_container_width=True
            ):
                header = f"**{source}**  ·  _chunk {num}_"
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

question = st.chat_input(
    "Ask about a policy, or request a report..."
)
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
        # Initial render: route not yet known. All tier-2 branches
        # render as off-path (dim/strikethrough) and flip when the
        # supervisor's `done` event tells us which one was chosen.
        render_stepper(stepper_slot, stages, route="")

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
                        route=route_holder["value"],
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
