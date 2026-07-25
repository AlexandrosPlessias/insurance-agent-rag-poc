# Setup Guide

First-time setup for the PoC. After this, see [USAGE.md](USAGE.md) for day-to-day operation.

The entire stack runs in Docker — no Python venv, no native Ollama, no native npm required.

---

## 1. Prerequisites

### Windows / WSL2

| Requirement | Notes |
|---|---|
| **Docker Desktop** | Enable WSL2 integration: Settings → Resources → WSL Integration → turn on your Ubuntu distro |
| **WSL2 + Ubuntu** | 22.04 or 24.04 (`wsl --install -d Ubuntu` from PowerShell) |
| **RAM** | 16 GB minimum (`qwen2.5:7b` ≈ 4.7 GB resident) |
| **Disk** | ~15 GB free (model weights + images + ChromaDB volume) |
| **git** | To clone the repo |

### macOS

| Requirement | Notes |
|---|---|
| **Docker Desktop for Mac** | Apple Silicon or Intel; enable "Use Rosetta for x86/amd64 emulation" if prompted |
| **RAM** | 16 GB minimum |
| **Disk** | ~15 GB free |
| **git** | To clone the repo |

---

## 2. WSL2 filesystem: work on ext4, not OneDrive

> **Skip this section if you cloned directly into your WSL home (`~/…`).** Run
> `df -T . | awk 'NR==2{print $2}'` from the repo root — if the output is `ext4` you
> are already on the fast path.

### Why it matters

When the repo lives under `/mnt/c/` (OneDrive or any Windows path), every file read and
write crosses the 9p bridge between the Linux kernel and the Windows host. For
file-intensive workloads — Docker build contexts, `npm install`, Python imports — this is
10–50× slower than a native ext4 syscall. It can also cause Docker bind-mount issues
where container file watchers miss changes.

### Verify you are on ext4

```bash
df -T . | awk 'NR==2{print $2}'
# Expected: ext4
# Bad:      9p  (Windows mount) or drvfs
```

### If you cloned under OneDrive — re-clone into WSL home

```bash
# From a WSL terminal:
cd ~
git clone <your-remote-url> insurance-agent-rag-poc
cd insurance-agent-rag-poc
```

Copy your existing `src/.env` if you had one:

```bash
cp /mnt/c/path/to/old/src/.env src/.env
```

---

## 3. Clone the repo

```bash
git clone <your-remote-url> insurance-agent-rag-poc
cd insurance-agent-rag-poc
```

---

## 4. Configuration

All infrastructure URLs (Ollama, ChromaDB, service-to-service addresses) are baked into
the container defaults — you do not need to configure them. The only file you need to
create is `src/.env`, which holds secrets and optional overrides.

```bash
cp src/.env.example src/.env
```

Then open `src/.env` and fill in the values:

| Variable | Required | Purpose |
|---|---|---|
| `APPROVAL_HMAC_SECRET` | **Yes** | Signs approval-gate tokens. Generate with `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `TELEGRAM_BOT_TOKEN` | No | Telegram bot token for approval notifications. Leave blank to use UI-only flow |
| `TELEGRAM_CHAT_ID` | No | Telegram chat ID to receive approval messages |
| `LLM_MODEL` | No | Override worker model (default: `qwen2.5:7b`) |
| `PLANNER_MODEL` | No | Override planner model (default: `qwen2.5:3b`) |
| `EMBED_MODEL` | No | Override embedding model (default: `nomic-embed-text`) |
| `LOG_LEVEL` | No | `DEBUG` for verbose output (default: `INFO`) |
| `APPROVALS_KPI_THRESHOLD` | No | KPI value above which a human-approval gate fires (default: `1000000.0`) |
| `AUDIT_RETAIN_AUDIO` | No | Persist raw audio blobs alongside audit records (default: `false`) |
| `VOICE_ENABLED` | No | Show the mic button and AudioPlayer in the UI (default: `true`). Set to `false` to disable voice completely |
| `VOICE_STT_MODEL` | No | Whisper model size for speech-to-text: `tiny` / `small` / `medium` / `large-v3` (default: `small`). Larger = more accurate, slower |

### APPROVAL_HMAC_SECRET

Generate a proper secret so approval tokens can't be forged:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Paste the output into `src/.env`:

```
APPROVAL_HMAC_SECRET=<paste here>
```

> Never commit this value — `src/.env` is gitignored. `.dockerignore` also prevents it
> from being baked into images; Compose passes it at runtime via `env_file:`.

### Optional: Telegram approval notifications

Skip this if you want UI-only approvals.

1. Open Telegram → search **@BotFather** → `/newbot` → follow prompts → copy the token.
2. Set `TELEGRAM_BOT_TOKEN=<token>` in `src/.env`.
3. Send any message to your bot, then open:

   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```

   Copy the `chat.id` from the response.
4. Set `TELEGRAM_CHAT_ID=<chat_id>` in `src/.env`.

---

## 5. First run

### Step 1 — start shared infrastructure (all platforms)

Ollama (LLM runtime) and Portainer run in a separate shared stack that is reused across
projects. Start it once — it is idempotent and safe to re-run if already running:

```bash
./start-infra.sh
```

The script auto-detects an NVIDIA GPU and applies the GPU profile automatically. Pass
`--cpu` to force CPU-only mode, or `--gpu` to force GPU mode.

### Step 2 — start project services

#### Windows / WSL2

```bash
docker compose up --build
```

#### macOS

Before running Compose, make sure Docker Desktop is open and the Docker daemon is
reachable. If Docker is not running, Compose will fail with:
`Cannot connect to the Docker daemon at unix:///Users/<you>/.docker/run/docker.sock`.

```bash
docker info
```

If that command fails, start Docker Desktop and wait until it finishes starting:

```bash
open -a Docker
```

```bash
docker compose -f docker-compose.yml -f docker-compose.override.macos.yml up --build
```

The override file adds `platform: linux/arm64` to each service so images build natively
on Apple Silicon.

### What happens on first run

| Phase | What | Approximate time |
|---|---|---|
| Image build | Docker builds all service images from source | 3–8 min (depends on cache) |
| Model download (`ollama-pull`) | Downloads `qwen2.5:7b`, `qwen2.5:3b`, `nomic-embed-text` (~7 GB total) into a named volume | 10–20 min (depends on connection) |
| PDF ingestion (`ingestion-service`) | Clears ChromaDB and indexes all PDFs in `src/data/knowledge_base/raw/` | 2–5 min |

**Total first-run time: 15–30 minutes.** Subsequent runs skip the model download (weights
persist in the shared `ollama_models` volume) and rebuild only changed layers, so they start in
under a minute.

The `ingestion-service` re-indexes PDFs on every container start. Watch for the
`=== Ingestion complete ===` banner in the logs before sending queries.

---

## 6. Verify

Once all containers are up and the ingestion banner has appeared:

```bash
curl http://localhost:8000/health
```

Expected response: `{"status":"ok",...}`

The stack runs **14 implemented phases** — all services below should be healthy.

| URL | What |
|---|---|
| <http://localhost:5173> | React SPA — main entry point |
| <http://localhost:8000/docs> | FastAPI OpenAPI docs |
| <http://localhost:18888> | Aspire observability dashboard |
| <http://localhost:9000> | Portainer container management |

Portainer first-time login:

1. Open <http://localhost:9000/#!/init/admin> to create the initial local admin account.
2. If you see a timeout page (`/timeout.html#!/auth`), restart Portainer and reload:

```bash
docker compose -f docker-compose.infra.yml restart portainer
```

Internal services (debugging only):

| Port | Service |
|---|---|
| :8001 | voice-service (STT + TTS) |
| :8002 | agentic-service (LangGraph) |
| :8003 | rag-service (retrieval) |
| :8004 | ingestion-service (PDF pipeline) |
| :8005 | ChromaDB (vector store) |
| :5432 | PostgreSQL — connect via DBeaver / TablePlus: host `localhost`, db `poc`, user `poc` |

---

## 7. Tests

The test suite has two layers that run in different environments.

### Unit tests (import smoke test)

`test_imports.py` is the only test that can run **natively without Docker** — useful
for a quick sanity check during development without rebuilding images:

```bash
# One-time native install (Python 3.11+ required):
pip install -e "src/[test]"

# Run natively:
cd src && pytest tests/unit/test_imports.py -v
```

Or inside Docker:

```bash
docker compose exec agentic-service python -m pytest tests/unit/test_imports.py -v
```

| File | What it covers |
|---|---|
| `test_imports.py` | Imports all agentic-backend modules — catches syntax errors and missing deps at import time |

Expected: **71 passed** in ~4 seconds.

---

### Integration tests — full Docker stack required

Integration tests call the live `agentic-service` API (`POST /chat`, `POST /feedback`) and assert on routing decisions, planner intent, answer quality, and citation grounding.

**Prerequisites:**

1. Stack is running and all containers are healthy (`docker compose ps`)
2. PDFs have been ingested — watch for `=== Ingestion complete ===` in `docker compose logs ingestion-service`, or run manually:

```bash
docker compose exec ingestion-service python scripts/ingest_pdfs.py
```

**Run all integration tests:**

```bash
docker compose exec agentic-service \
    python -m pytest tests/integration/ -v --skip-ingest
```

`--skip-ingest` tells the test suite to use the ChromaDB data already indexed by the ingestion-service, rather than trying to re-ingest inside the agentic-service container (which doesn't have the PDF dependencies).

**Run a single file:**

```bash
docker compose exec agentic-service \
    python -m pytest tests/integration/test_00_planner_intent.py -v --skip-ingest
```

**What is tested (18 tests across 12 files):**

| File | Scenario | Key assertions |
|---|---|---|
| `test_00_planner_intent.py` | Intent classifier × fast + accurate mode (6 parametrized cases) | `intent`, `effective_response_mode` — including the fast→accurate override for analytics queries |
| `test_01_rag_basic.py` | Basic RAG for 2024 policy questions | `route=rag`, `intent=policy_qa`, citations ≥ 1 |
| `test_02_clarifier_followup.py` | Year-ambiguous question → clarifier → bare-year follow-up → RAG | 2-turn conversation, `conversation_id` threaded |
| `test_03_rag_relative_date.py` | 2020 year-scoped retrieval | Citation source contains "2020" |
| `test_04_out_of_year.py` | 2023 year gap fallback | `route=out_of_year`, answer mentions "2023" |
| `test_05_out_of_scope.py` | Non-insurance question declined | `route=out_of_scope`, answer ≠ "4" |
| `test_06_multi_intent.py` | Policy + KPI in one question → agentic plan | `route=agentic`, answer covers both intents |
| `test_07_talk_to_data.py` | Scalar → grouped → drill-down chain; invalid-agg + year-gap guards | `route=data` on all 5 turns |
| `test_08_report_summary.py` | Markdown summary report | `route=report`, answer ≥ 200 chars, contains `#` |
| `test_09_executive_report.py` | Full executive annual report pipeline | `route=report`, answer ≥ 500 chars |
| `test_10_feedback_roundtrip.py` | `POST /feedback` write + audit store read-back | `ok=True`, `row_id > 0`, payload matches |

Expected: **18 passed** (runtime varies — executive report and multi-intent can take 60–120 s each).

---

## 8. Troubleshooting setup

| Symptom | Fix |
|---|---|
| Container exits immediately on startup | Check logs: `docker compose logs <service>`. Usually a missing `src/.env` or wrong `APPROVAL_HMAC_SECRET` |
| `ollama-pull` stalls or exits with error | Model download interrupted — `docker compose -f docker-compose.infra.yml restart ollama-pull`. Weights already downloaded are preserved in the volume |
| `ingestion-service` keeps restarting | ChromaDB container not healthy yet — Compose depends_on ordering handles this, but check `docker compose logs chromadb` for OOM or disk-full errors |
| `ChromaDB connection refused` from a service | The `chromadb` container is still starting. Wait for its health check to pass (`docker compose ps`) |
| Portainer shows `timeout.html#!/auth` and no local-account form | Open <http://localhost:9000/#!/init/admin>. If still timed out, restart Portainer: `docker compose -f docker-compose.infra.yml restart portainer` |
| Port already in use (5173 / 8000 / 9000 / 18888) | Another process owns the port. Find it: `ss -tlnp | grep :<port>` on Linux, or `lsof -i :<port>` on macOS. Kill it or stop the conflicting service |
| Docker Desktop OOM — container killed | Increase Docker Desktop memory limit: Settings → Resources → Memory. Minimum 8 GB recommended; 12 GB for comfortable operation |
| macOS: image build fails with wrong arch | Ensure you're using the macOS override file: `docker compose -f docker-compose.yml -f docker-compose.override.macos.yml up --build` |
| macOS: `could not select device driver "nvidia" with capabilities: [[gpu]]` | Your stack is trying to apply Linux CUDA settings on macOS. Use the macOS override file and recreate: `docker compose -f docker-compose.yml -f docker-compose.override.macos.yml down` then `docker compose -f docker-compose.yml -f docker-compose.override.macos.yml up --build` |
| `permission denied` on `src/data/` | Docker bind-mount permission issue on WSL2. Run `chmod -R 777 src/data` or move the repo to ext4 (see section 2) |
| Model download works but inference is very slow | Docker Desktop may not have enough memory assigned. Raise to at least 10 GB in Settings → Resources |
