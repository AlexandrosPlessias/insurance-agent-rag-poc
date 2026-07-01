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
    submit_feedback,
    upload_document,
)

# Initialise OTel for the UI process - no-op if OTEL_ENABLED=false.
# Skip LangChain instrumentation: the UI never calls LangChain directly,
# and importing it here would add several seconds to the first page load.
setup_otel(service_suffix="ui", instrument_langchain=False)

st.set_page_config(
    page_title="ACME Insurances · Assistant",
    page_icon="🛡️",
    layout="wide",
)

# Branded header - kept native (st.title + st.caption) so it plays
# nicely with Streamlit's sticky-bottom chat_input. An earlier
# attempt at a column+HTML header was eating vertical space and
# hiding the chat input below the fold on smaller screens.
st.title("🛡️ ACME Insurances")
st.caption("Policy & claims assistant · local RAG · PoC")

# Full graph topology rendered every turn. Each tuple is
# (stage_key, label, route_that_owns_it, tools_used).
# route=None means the stage is shared across all routes (Supervisor);
# validator is only on the RAG path (route="rag"). Tools are shown as a
# small badge row under the status pill so the user can see at a glance
# what each agent calls into. Order matters for the left-to-right layout.
PIPELINE_TOPOLOGY: list[tuple[str, str, str | None, list[str]]] = [
    # Phase 11 — Planner → Orchestrator → Worker(s) → Assembler
    ("planner",      "Planner",      None, ["LLM(3B)"]),
    ("orchestrator", "Orchestrator", None, ["DAG"]),
    ("worker",       "Worker",       None, ["skills"]),
    ("assembler",    "Assembler",    None, ["merge"]),
]

# --- Session-state defaults ---
if "user_id" not in st.session_state:
    st.session_state.user_id = "default_user"
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None
if "history" not in st.session_state:
    st.session_state.history = []
if "rated_turns" not in st.session_state:
    st.session_state.rated_turns = set()


# --- Cached API calls ---
# Streamlit reruns the whole script on every interaction. Without
# caching, every keystroke / button click re-hits /health and
# /conversations on the API (which in turn pings Ollama on /health,
# making the round-trip slow). Short TTLs keep the sidebar feeling
# fresh; we clear the conversations cache explicitly when one is
# created or after a chat turn finishes so new rows show up at once.


@st.cache_data(ttl=10, show_spinner=False)
def cached_get_health() -> dict:
    return get_health()


@st.cache_data(ttl=5, show_spinner=False)
def cached_list_conversations(user_id: str) -> list[dict]:
    return list_conversations(user_id)


def _invalidate_conversation_cache() -> None:
    cached_list_conversations.clear()


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
    st.session_state.rated_turns = set()


def _start_new_conversation() -> None:
    st.session_state.conversation_id = None
    st.session_state.history = []
    st.session_state.rated_turns = set()


# --- Sidebar (ACME-branded) ---
# Order is now task-priority: brand → conversations (daily task) →
# identity (compact) → knowledge base (upload) → service health
# (always visible badge) → diagnostics + build history (collapsed).
with st.sidebar:
    # Brand block at the top of the sidebar.
    st.markdown(
        "<div style='padding: .2rem 0 .6rem 0;'>"
        "<div style='font-size: 1.25rem; font-weight: 600; "
        "letter-spacing: .02em;'>🛡️ ACME Insurances</div>"
        "<div style='font-size: .78rem; color: rgba(170,180,200,.65); "
        "margin-top: .1rem;'>local assistant · qwen2.5:7b</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    # 💬 Conversations — primary task surface.
    st.subheader("💬 Conversations")
    if st.button(
        "➕ New conversation", use_container_width=True, type="primary"
    ):
        _start_new_conversation()
        _invalidate_conversation_cache()
        st.rerun()

    try:
        convos = cached_list_conversations(st.session_state.user_id)
    except Exception as e:
        convos = []
        st.error(f"Failed to list conversations: {e}")

    if not convos:
        st.caption("No saved conversations yet.")
    for c in convos:
        is_current = c["id"] == st.session_state.conversation_id
        label = c.get("title") or f"Conversation {c['id']}"
        if is_current:
            label = f"● {label}"
        if st.button(
            label,
            key=f"conv_{c['id']}",
            use_container_width=True,
        ):
            _switch_conversation(c["id"])
            st.rerun()

    st.divider()

    # 👤 Identity — compact, sits below conversations because the
    # default user_id is fine for most demo flows.
    st.subheader("👤 Identity")
    new_user = st.text_input(
        "User ID",
        value=st.session_state.user_id,
        help="Identifies the owner of conversations and long-term memory.",
        label_visibility="collapsed",
    )
    if new_user != st.session_state.user_id:
        st.session_state.user_id = new_user
        _start_new_conversation()
        _invalidate_conversation_cache()

    st.divider()

    # 📚 Knowledge base — document upload form.
    with st.expander("📚 Knowledge base", expanded=False):
        st.caption("Index a new policy PDF.")
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
            "📥 Ingest",
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

    # Service health — always visible (small badge, no header).
    # Result is cached for 10s so quick keystrokes don't re-probe
    # Ollama through /health on every script rerun.
    try:
        h = cached_get_health()
        ollama_ok = h["ollama_reachable"]
        st.caption(
            ("🟢 Service ready" if ollama_ok else "🟡 Ollama unreachable")
            + (" · Ollama OK" if ollama_ok else "")
        )
    except Exception as e:
        st.caption(f"🔴 API unreachable: {e}")

    # ⚙️ Diagnostics — Aspire link + build history. Collapsed by
    # default because daily users don't need it.
    with st.expander("⚙️ Diagnostics", expanded=False):
        if settings.otel_enabled:
            st.link_button(
                "📊 Open Aspire Dashboard",
                settings.otel_ui_url,
                use_container_width=True,
            )
            st.caption(
                "Traces &amp; logs stream to "
                f"`{settings.otel_endpoint}`."
            )
            st.divider()

        st.markdown("**Implemented phases**")
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
            "OTel log dedup  \n"
            "✅ **Phase 8** · Talk-to-Data agent · typed Operation JSON · "
            "pandas executor with 5 schema-aware guards · drill-down "
            "with inherited/changed chips · `data.plan`/`data.execute` "
            "stage events + audit  \n"
            "✅ **Phase 9** · executive annual report · "
            "section-by-section pipeline · deterministic risk bands · "
            "Markdown / DOCX / PDF writers · "
            "`GET /reports/{year}.{ext}` download API  \n"
            "✅ **Phase 10** · PoC stakeholder deck — python-pptx "
            "builder from `deck.md` + screenshot embedding  \n"
            "✅ **Phase 11** · Agentic multi-intent stack — Planner "
            "(qwen2.5:3b) · Orchestrator (LangGraph Send() DAG) · "
            "Worker thin-shells · Skills registry · Tools registry · "
            "Assembler (H3 merge + citation dedup) · "
            "Feedback (👍👎 → audit_events)"
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


# Sub-stages that fire inside the RAG node. The backend emits these
# as `stage` events from app.graph.streaming so the UI can flip each
# one independently. Each carries the single dominant tool used by
# that step (LLM for reformulate / answer, Chroma for retrieve).
RAG_SUBSTAGES: list[tuple[str, str, str]] = [
    ("rag.reformulate", "reformulate", "LLM"),
    ("rag.retrieve",    "retrieve",    "Chroma"),
    ("rag.answer",      "answer",      "LLM"),
]

# Phase 8 - sub-stages inside the data node. plan = LLM-typed
# Operation JSON, execute = pandas filter + group + aggregate.
DATA_SUBSTAGES: list[tuple[str, str, str]] = [
    ("data.plan",    "plan",    "LLM"),
    ("data.execute", "execute", "pandas"),
]

# Phase 11 - sub-stages emitted inside the RAG worker step.
# Keys are suffixes; full stage key = "worker.{step_id}.{suffix}".
WORKER_SUBSTAGES: list[tuple[str, str, str]] = [
    ("reformulate", "reformulate", "LLM"),
    ("retrieve",    "retrieve",    "Chroma"),
    ("answer",      "answer",      "LLM"),
]

_SKILL_LABELS: dict[str, str] = {
    "answer-policy-question":    "Policy Q&A",
    "compute-kpi":               "KPI Query",
    "executive-section-summary": "Exec Report",
    "clarify-year":              "Clarify Year",
    "out-of-year-fallback":      "Year Guard",
    "decline":                   "Out of Scope",
}


def _prettify_skill(skill: str) -> str:
    return _SKILL_LABELS.get(skill, skill.replace("-", " ").title())


def _render_substage(col, label: str, tool: str, status: str) -> None:
    """One compact sub-pill rendered under the RAG cell."""
    if status == "done":
        bg, fg, icon = "rgba(46,160,67,.18)", "rgba(140,230,160,.95)", "✓"
    elif status == "running":
        bg, fg, icon = "rgba(70,140,220,.20)", "rgba(170,210,255,.95)", "⟳"
    else:
        bg, fg, icon = "rgba(120,120,120,.05)", "rgba(150,150,150,.55)", "○"
    col.markdown(
        f"<div style='display: flex; align-items: center; "
        f"justify-content: space-between; "
        f"padding: .15rem .4rem; margin-top: .15rem; "
        f"border-radius: .25rem; background: {bg}; "
        f"color: {fg}; font-size: .75rem;'>"
        f"<span>{icon} {label}</span>"
        f"<span style='font-family: monospace; "
        f"font-size: .65rem; opacity: .85;'>{tool}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )


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


def _build_dynamic_topology(
    stages: dict,
) -> list[tuple[str, str, str | None, list[str]]]:
    """Expand PIPELINE_TOPOLOGY's single 'worker' entry into N per-step columns.

    Detects active step IDs from keys like 'worker.step-1' in stages.
    Falls back to the original placeholder column when no steps exist yet.
    """
    step_ids = sorted(
        {
            k.split(".")[1]
            for k in stages
            if k.startswith("worker.")
            and k.count(".") == 1
            and k.split(".")[1].startswith("step-")
        },
        key=lambda s: int(s.split("-")[1]),
    )
    topology: list[tuple[str, str, str | None, list[str]]] = []
    for entry in PIPELINE_TOPOLOGY:
        if entry[0] != "worker":
            topology.append(entry)
        elif step_ids:
            for sid in step_ids:
                skill = stages.get(f"worker.{sid}.skill", "Worker")
                topology.append((f"worker.{sid}", skill, None, ["LLM", "Chroma"]))
        else:
            topology.append(entry)
    return topology


def render_stepper(slot, stages: dict, route: str = "") -> None:
    """Render the full graph topology every turn.

    Uses _build_dynamic_topology to expand the single 'worker' entry into
    one column per active step, so parallel / sequential workers each get
    their own pill. Orchestrator shows a live (X/N) progress count derived
    from completed worker steps vs the total declared by the planner.
    """
    effective_topology = _build_dynamic_topology(stages)

    # Orchestrator progress: count steps done vs total declared by planner.
    completed_workers = sum(
        1 for k, v in stages.items()
        if k.startswith("worker.")
        and k.count(".") == 1
        and k.split(".")[1].startswith("step-")
        and v == "done"
    )
    total_str = stages.get("orchestrator.total", "")

    with slot.container():
        cols = st.columns(len(effective_topology))
        for col, (key, label, owner, tools) in zip(cols, effective_topology):
            on_path = _on_active_path(route, owner)
            status = stages.get(key, "pending") if on_path else "off_path"

            # Dynamic labels.
            display_label = label
            if key == "orchestrator" and total_str and status == "running":
                display_label = f"{label} ({completed_workers}/{total_str})"

            if status == "done":
                col.success(f"✓ {display_label}")
            elif status == "running":
                col.info(f"⟳ {display_label} …")
            elif status == "off_path":
                col.markdown(
                    f"<div style='padding: .5rem .5rem; "
                    f"border-radius: .375rem; "
                    f"background-color: rgba(120,120,120,.04); "
                    f"color: rgba(150,150,150,.45); "
                    f"text-align: center; "
                    f"font-size: .82rem; "
                    f"text-decoration: line-through "
                    f"rgba(150,150,150,.35);'>"
                    f"{display_label}</div>",
                    unsafe_allow_html=True,
                )
            else:
                col.markdown(
                    f"<div style='padding: .5rem .75rem; "
                    f"border-radius: .375rem; "
                    f"background-color: rgba(120,140,200,.10); "
                    f"border: 1px dashed rgba(120,140,200,.35); "
                    f"color: rgba(180,200,255,.85); "
                    f"text-align: center; "
                    f"font-size: .92rem;'>"
                    f"○ {display_label}</div>",
                    unsafe_allow_html=True,
                )

            _render_tools_row(col, tools, dim=(status == "off_path"))

            if key == "rag" and on_path:
                for sub_key, sub_label, sub_tool in RAG_SUBSTAGES:
                    sub_status = stages.get(sub_key, "pending")
                    _render_substage(col, sub_label, sub_tool, sub_status)

            if key == "data" and on_path:
                for sub_key, sub_label, sub_tool in DATA_SUBSTAGES:
                    sub_status = stages.get(sub_key, "pending")
                    _render_substage(col, sub_label, sub_tool, sub_status)

            # Phase 11: per-step worker sub-stages. key = "worker.step-N".
            if key.startswith("worker.step-") and on_path:
                has_substages = any(
                    f"{key}.{suf}" in stages for suf, _, _ in WORKER_SUBSTAGES
                )
                if has_substages:
                    for suf, sub_label, sub_tool in WORKER_SUBSTAGES:
                        sub_status = stages.get(f"{key}.{suf}", "pending")
                        _render_substage(col, sub_label, sub_tool, sub_status)


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


def render_report_downloads(year: int | None, run_id: str = "") -> None:
    """Phase 9 - DOCX + PDF download buttons under an executive report.

    Renders link_buttons to the API's GET /reports/{year}.docx and
    .pdf endpoints. Year+run_id are surfaced together so the
    download filename matches what the user sees in the chat.
    """
    if not year:
        return
    api = settings.ui_api_url.rstrip("/")
    cols = st.columns([2, 2, 2, 4])
    cols[0].link_button(
        "📄 Download DOCX",
        f"{api}/reports/{year}.docx",
        use_container_width=True,
    )
    cols[1].link_button(
        "📑 Download PDF",
        f"{api}/reports/{year}.pdf",
        use_container_width=True,
    )
    cols[2].link_button(
        "📝 Download MD",
        f"{api}/reports/{year}.md",
        use_container_width=True,
    )
    if run_id:
        cols[3].caption(
            f"_Report id `{run_id}` · same id = same numbers_"
        )


def render_operation_expander(op: dict | None) -> None:
    """Phase 8: 'How this was computed' expander for data turns.

    Renders the Operation JSON the planner emitted with inherited /
    changed chips when it's a drill-down. The expander stays closed
    by default - it's a verification surface, not a primary read.
    """
    if not op:
        return
    import json as _json

    drilldown = bool(op.get("_drilldown"))
    inherited = op.get("_inherited") or []
    changed = op.get("_changed") or []
    title = "How this was computed"
    if drilldown:
        title += "  ·  drill-down"

    with st.expander(title, expanded=False):
        if drilldown:
            row = st.columns(2)
            row[0].markdown(
                "**Inherited from previous turn:**  \n"
                + (
                    "  ".join(f"`{c}`" for c in inherited)
                    or "_(none)_"
                )
            )
            row[1].markdown(
                "**Changed this turn:**  \n"
                + (
                    "  ".join(f"`{c}`" for c in changed)
                    or "_(none)_"
                )
            )

        # Hide the internal `_drilldown` / `_inherited` / `_changed`
        # annotations from the displayed JSON - they're for UI use
        # only, not part of the typed Operation.
        public = {k: v for k, v in op.items() if not k.startswith("_")}
        st.code(_json.dumps(public, indent=2), language="json")


# Branded chat avatars: shield for the ACME assistant, person silhouette
# for the user. Streamlit defaults to a generic robot and person glyph.
ASSISTANT_AVATAR = "🛡️"
USER_AVATAR = "👤"


# --- Replay prior turns ---
for _turn_idx, entry in enumerate(st.session_state.history):
    avatar = (
        ASSISTANT_AVATAR if entry["role"] == "assistant" else USER_AVATAR
    )
    with st.chat_message(entry["role"], avatar=avatar):
        route = entry.get("route", "")
        if entry["role"] == "assistant":
            if route == "rag":
                render_reformulation(
                    entry.get("reformulated_query", ""),
                    entry.get("original_question", ""),
                )
            # Markdown-bearing routes (report + Phase 8 data) need
            # st.markdown so tables / formatting render; the plain
            # branches use st.write.
            if route in ("report", "data"):
                st.markdown(entry["content"], unsafe_allow_html=False)
            else:
                st.write(entry["content"])
            if route == "rag":
                render_validation(
                    entry.get("validated", True),
                    entry.get("critique", ""),
                )
            # Phase 9: replay download buttons for executive reports.
            if (
                route == "report"
                and entry.get("report_kind") == "executive"
            ):
                render_report_downloads(
                    entry.get("report_year"),
                    entry.get("report_run_id", ""),
                )
            if route == "data":
                render_operation_expander(entry.get("data_operation"))
            else:
                render_citations(entry.get("citations", []))
            # Phase 11: feedback thumbs for any turn that has a plan_id.
            _entry_plan_id = entry.get("plan_id", "")
            if _entry_plan_id:
                _fb_key = (
                    f"{st.session_state.conversation_id}_{_turn_idx}"
                )
                if _fb_key not in st.session_state.rated_turns:
                    st.markdown(
                        "<hr style='margin: .5rem 0; opacity: .15;'>",
                        unsafe_allow_html=True,
                    )
                    fb_cols = st.columns([1, 1, 10])
                    with fb_cols[0]:
                        if st.button(
                            "👍",
                            key=f"fb_up_{_fb_key}",
                            help="This answer was helpful",
                        ):
                            try:
                                submit_feedback(
                                    trace_id=_entry_plan_id,
                                    score=1,
                                    user_id=st.session_state.user_id,
                                    plan_id=_entry_plan_id,
                                    conversation_id=st.session_state.conversation_id,
                                )
                                st.session_state.rated_turns.add(_fb_key)
                                st.toast(
                                    "Feedback recorded — thanks!",
                                    icon="👍",
                                )
                            except Exception:
                                st.toast(
                                    "Could not record feedback.",
                                    icon="⚠️",
                                )
                            st.rerun()
                    with fb_cols[1]:
                        if st.button(
                            "👎",
                            key=f"fb_dn_{_fb_key}",
                            help="This answer needs improvement",
                        ):
                            try:
                                submit_feedback(
                                    trace_id=_entry_plan_id,
                                    score=-1,
                                    user_id=st.session_state.user_id,
                                    plan_id=_entry_plan_id,
                                    conversation_id=st.session_state.conversation_id,
                                )
                                st.session_state.rated_turns.add(_fb_key)
                                st.toast(
                                    "Feedback recorded — thanks!",
                                    icon="👎",
                                )
                            except Exception:
                                st.toast(
                                    "Could not record feedback.",
                                    icon="⚠️",
                                )
                            st.rerun()
                else:
                    st.caption("✓ Feedback sent")
        else:
            st.write(entry["content"])

question = st.chat_input(
    "Ask ACME's assistant about a policy, claim, or refund..."
)
if question:
    st.session_state.history.append(
        {"role": "user", "content": question}
    )
    with st.chat_message("user", avatar=USER_AVATAR):
        st.write(question)

    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
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
        # Phase 9: an executive report turn carries a year + a
        # report_run_id on the `done` event, so the UI can render
        # DOCX / PDF / MD download buttons that hit the API's
        # /reports/{year}.{ext} endpoints.
        report_kind_holder = {"value": ""}
        report_year_holder: dict = {"value": None}
        report_run_id_holder = {"value": ""}
        # Phase 8 data turn: tokens come as a single Markdown blob,
        # so we capture them like a report and render with st.markdown
        # AFTER the stream. The Operation JSON travels on the `done`
        # event and feeds the 'How this was computed' expander.
        data_holder = {"value": ""}
        data_operation_holder: dict = {"value": None}
        # Phase 11 — plan_id for feedback + trace_id from OTel.
        plan_id_holder = {"value": ""}
        trace_id_holder = {"value": ""}

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
                    info = event.get("info", "")
                    status = (
                        "running"
                        if event["status"] == "started"
                        else "done"
                    )
                    # Phase 11 worker routing:
                    #   worker.step-N          → per-step pill
                    #   worker.step-N.substage → per-step sub-stage pills
                    # Orchestrator stays non-green until assembler finishes.
                    if node.startswith("worker."):
                        parts = node.split(".")
                        if len(parts) == 2:
                            # worker.step-N started/done
                            step_id = parts[1]
                            if status == "running":
                                for token in info.split():
                                    if token.startswith("skill="):
                                        stages[f"worker.{step_id}.skill"] = (
                                            _prettify_skill(token[6:])
                                        )
                                        break
                                # clear sub-stages from any prior run of
                                # this step (retry scenario)
                                for suf, _, _ in WORKER_SUBSTAGES:
                                    stages.pop(f"worker.{step_id}.{suf}", None)
                            stages[f"worker.{step_id}"] = status
                        elif len(parts) >= 3:
                            # worker.step-N.substage
                            stages[f"worker.{parts[1]}.{parts[2]}"] = status
                    elif node == "orchestrator":
                        if status == "running":
                            # capture total step count for progress display
                            for token in info.split():
                                if token.startswith("steps="):
                                    stages["orchestrator.total"] = token[6:]
                                    break
                        # orchestrator backend-done: stay non-green until
                        # assembler finishes so the pill turns green together
                        # with the final answer being ready.
                        stages["orchestrator"] = "running"
                    elif node == "assembler" and status == "done":
                        stages["orchestrator"] = "done"
                        stages["assembler"] = "done"
                    else:
                        stages[node] = status
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
                    elif route_holder["value"] == "data":
                        data_holder["value"] += event["value"]
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
                    route_holder["value"] = (
                        event.get("route") or route_holder["value"] or "agentic"
                    )
                    op = event.get("data_operation")
                    if op:
                        data_operation_holder["value"] = op
                    # Phase 9 - executive report metadata.
                    rk = event.get("report_kind")
                    if rk:
                        report_kind_holder["value"] = rk
                        report_year_holder["value"] = event.get(
                            "report_year"
                        )
                        report_run_id_holder["value"] = (
                            event.get("report_run_id") or ""
                        )
                    # Phase 11 - feedback identifiers.
                    plan_id_holder["value"] = event.get("plan_id") or ""
                    trace_id_holder["value"] = (
                        event.get("trace_id") or ""
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
            # Phase 9: executive-pipeline report turns offer
            # downloadable DOCX / PDF / MD via the API endpoints.
            if report_kind_holder["value"] == "executive":
                render_report_downloads(
                    report_year_holder["value"],
                    report_run_id_holder["value"],
                )

        if route_holder["value"] == "data" and data_holder["value"]:
            answer = data_holder["value"]
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
        if route_holder["value"] == "data":
            render_operation_expander(data_operation_holder["value"])
        else:
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
                # Phase 8: keep the Operation payload alongside the
                # answer so the replay loop can re-render the
                # 'How this was computed' expander when scrolling back.
                "data_operation": data_operation_holder["value"],
                # Phase 9: executive-report metadata so the replay
                # loop can re-render the DOCX/PDF download buttons.
                "report_kind": report_kind_holder["value"],
                "report_year": report_year_holder["value"],
                "report_run_id": report_run_id_holder["value"],
                # Phase 11: plan_id for feedback buttons in history replay.
                "plan_id": plan_id_holder["value"],
            }
        )

        # A new conversation may have been created on the backend
        # during this turn (auto-titled by the first assistant reply).
        # Drop the cached conversation list so the sidebar reflects
        # the new row on the next rerun instead of waiting for TTL.
        _invalidate_conversation_cache()
        # Render feedback buttons in the live block immediately after the
        # response using keys that mirror what the history-replay loop will
        # use.  When the user clicks, Streamlit reruns; the live block is
        # skipped (question=None) and the history-replay handler processes
        # the click — no bare st.rerun() needed here, which avoids the
        # chat_input re-delivery loop present in some Streamlit builds.
        _live_plan_id = plan_id_holder["value"]
        if _live_plan_id:
            _live_turn_idx = len(st.session_state.history) - 1
            _live_fb_key = (
                f"{st.session_state.conversation_id}_{_live_turn_idx}"
            )
            if _live_fb_key not in st.session_state.rated_turns:
                st.markdown(
                    "<hr style='margin: .5rem 0; opacity: .15;'>",
                    unsafe_allow_html=True,
                )
                fb_live_cols = st.columns([1, 1, 10])
                with fb_live_cols[0]:
                    st.button(
                        "👍",
                        key=f"fb_up_{_live_fb_key}",
                        help="This answer was helpful",
                    )
                with fb_live_cols[1]:
                    st.button(
                        "👎",
                        key=f"fb_dn_{_live_fb_key}",
                        help="This answer needs improvement",
                    )
            else:
                st.caption("✓ Feedback sent")
