# Architecture

Technical deep-dive into how the assistant is wired together. For the high-level picture see [Home](Home.md).

---

## Repo layout

```
insurance-agent-rag-poc/
├── src/
│   ├── agentic_backend/      # FastAPI + LangGraph backend (Python)
│   │   ├── agents/           # Planner, Assembler, legacy worker agents
│   │   ├── api/              # FastAPI routes (chat, ingest, reports, sources, plans, audio)
│   │   ├── approvals/        # HMAC-signed approval tokens + Telegram bot
│   │   ├── audit/            # Audit event writer + middleware
│   │   ├── graph/            # LangGraph builder, orchestrator, state, streaming
│   │   ├── ingestion/        # PDF → Markdown → ChromaDB pipeline
│   │   ├── llm/              # Ollama client, prompt loader, Skills/Tools prompts
│   │   ├── memory/           # PostgreSQL conversations
│   │   ├── observability/    # OTel logging + tracing helpers
│   │   ├── skills/           # Skill registry + auto-discovery
│   │   ├── tools/            # Tool registry + atomic tool implementations
│   │   └── voice/            # STT (faster-whisper) + TTS (piper-tts) engines
│   ├── data/                 # Knowledge-base PDFs, processed MD, metadata, ChromaDB
│   │   └── audit_audio/      # Raw audio blobs when AUDIT_RETAIN_AUDIO=true (gitignored)
│   ├── frontend/             # React + Vite + TypeScript SPA
│   ├── scripts/              # CLI tools (ingest, smoke test, audit export, screenshots…)
│   └── tests/                # pytest unit + integration tests
├── docs/
│   ├── architecture/         # Deep-dive reference docs
│   ├── presentation/         # Stakeholder deck (deck.md + PPTX)
│   └── wiki/                 # This wiki (source of truth — sync'd to GitHub wiki)
├── SETUP.md                  # First-time install guide
└── USAGE.md                  # Day-to-day operation guide
```

---

## Phase 11 agentic pipeline

Every chat turn travels through this pipeline:

```
User message
     │
     ▼
  Planner (3B model + self-critique)
     │  emits Plan{steps: list[Step]}
     ▼
  Orchestrator (pure routing, no LLM)
     │  fans out independent Steps in parallel via LangGraph Send()
     ├──► Worker → Skill → Tools → StepResult
     ├──► Worker → Skill → Tools → StepResult
     └──► Worker → Skill → Tools → StepResult
     │
     ▼
  Assembler (merge H3 sections + unified citations)
     │
     ▼
  Streamed answer (NDJSON) → React SPA
```

**Single-intent questions** are degenerate DAGs (one Step). The Assembler is a no-op
pass-through — no code path splits.

**Multi-intent questions** (*"Refund window AND the 2024 loss ratio?"*) produce a Plan
with two parallel Steps. Both workers run concurrently; the Assembler merges their
answers under separate H3 headings with unified citations.

Full reference: [`architecture/GRAPH.md`](../architecture/GRAPH.md) ·
[`architecture/agentic-pipeline.md`](../architecture/agentic-pipeline.md)

---

## Skills and Tools

Skills are loaded from `src/agentic_backend/skills/` at startup via auto-discovery.
Each Skill is a Pydantic-validated record:

```python
class Skill(BaseModel):
    name: str          # identifier the Planner uses in the Plan
    description: str   # the only thing the Planner ever sees
    system_prompt: str # never shown to the Planner — prompt injection guard
    tools_used: list[str]
    input_schema: dict
    output_schema: dict
```

**Current Skills:**
`answer-policy-question` · `clarify-year` · `compute-kpi` ·
`executive-section-summary` · `out-of-year-fallback` · `decline`

Tools are atomic typed functions in `src/agentic_backend/tools/`, each emitting one
OTel span + one audit row per call:

| Tool | What it does |
|---|---|
| `vector_search` | Semantic search over ChromaDB `policies` collection |
| `kpi_query` | Filter + aggregate the KPI CSV via pandas |
| `knowledge_base_lookup` | Fetch a specific processed Markdown doc by source key |
| `clarifier_check` | Emit a clarifying question as a StepResult |
| `audit_write` | Persist an arbitrary event to the PostgreSQL audit trail |

---

## LangGraph state machine

The compiled graph is built in `src/agentic_backend/graph/builder.py`. The
streaming endpoint (`POST /chat/stream`) uses a manual walker in
`src/agentic_backend/graph/streaming.py` that calls the same node functions but
yields NDJSON stage events between nodes so the React `PipelineStepper` updates live.

Diagram + edge reference: [`architecture/GRAPH.md`](../architecture/GRAPH.md)

---

## Approval gates (Phase 12)

Long-running Plans (e.g. the executive annual report) can be paused between Steps
pending a human sign-off. The approval flow:

1. Orchestrator suspends the Plan and writes a row to the `plans` PostgreSQL table.
2. A Telegram message (or stub webhook) is sent with a signed approval URL.
3. The reviewer clicks **Approve** / **Reject** — the URL carries an HMAC-signed token.
4. The backend verifies the token, updates `plan_status`, and resumes the Plan.

Full guide: [Approval-Gates.md](Approval-Gates.md)

---

## Voice I/O (Phase 13)

Voice is wired at the **transport boundary** — the LangGraph graph receives and returns
plain text strings unchanged. Audio is transcribed before the graph sees input;
synthesized after it produces output.

```
Browser mic  →  POST /audio/transcribe  →  transcript text
                                                 │
                                         POST /chat/stream  (graph unchanged)
                                                 │
                                          final answer text
                                                 │
             ←  POST /audio/synthesize  ←  WAV response
```

**STT:** `faster-whisper` (CTranslate2-backed, int8 CPU, pip-installable). Singleton
`WhisperModel` lazy-loaded on first call. OTel span: `tool.speech_to_text`.

**TTS:** `piper-tts` (pip-installable, `.onnx` models). Multi-voice cache keyed by language —
`en_US-lessac-medium` (English) and `el_GR-rapunzelina-low` (Greek). OTel span: `tool.text_to_speech`.

**WER metric:** `POST /audio/correction` fires when the user edits a voice-filled transcript
before sending. WER + CER computed via Levenshtein; logged as `voice.correction` audit event.

**Audit retention:** `AUDIT_RETAIN_AUDIO=true` writes raw blobs to `data/audit_audio/<sha256>.wav`.
Default off — only sha256 + transcript recorded.

Full reference: [architecture/voice-integration.md](../architecture/voice-integration.md)

---

## Data flow diagram

```
Browser (React SPA)
  │  POST /audio/transcribe  (voice in — Phase 13)
  │  POST /api/chat/stream   (NDJSON)
  │  POST /audio/synthesize  (voice out — Phase 13)
  ▼
FastAPI (uvicorn, port 8000)
  │  voice: faster-whisper STT / piper-tts TTS
  │  LangGraph graph.stream()
  ▼
LangGraph runtime
  ├─ Planner → Ollama qwen2.5:3b
  ├─ Workers → Ollama qwen2.5:7b (bind_tools)
  │   ├─ vector_search → ChromaDB (local)
  │   └─ kpi_query → pandas (in-process)
  └─ Assembler → merge
  │
  ├─ audit_write → PostgreSQL (audit_events)
  ├─ OTel spans → OTLP → .NET Aspire Dashboard (:18888)
  └─ memory → PostgreSQL (conversations, messages)
```
