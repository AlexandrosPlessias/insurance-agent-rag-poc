# Plan: Phase 14 — Container Orchestration & Microservices

## Context

The current stack runs as a single Python process (`run_all.sh` starts FastAPI + Ollama + Aspire
in one terminal). Phase 14 breaks this monolith into independently deployable service pods,
adds a shared infrastructure tier (Postgres, ChromaDB server, Ollama), and introduces a
management UI for operating the running stack. No new product features — this is a pure
infrastructure and packaging phase.

Delivered in two sub-phases:
- **14a** — Docker Compose + Portainer CE (local dev, immediate value)
- **14b** — Kubernetes + Helm + Headlamp (production-ready, follows 14a)

---

## Step 0 — Create and checkout branch

```bash
git checkout -b poc/phase-14-container-orchestration
```

---

## Step 1 — Service decomposition (6 app pods + infra)

```
frontend        nginx:alpine       :80      React SPA (built artifact)
api-gateway     python:3.12-slim   :8000    /chat /health /feedback /plans /admin /reports
voice-service   python:3.12-slim   :8001    /audio/transcribe /audio/synthesize /audio/correction
agentic-service python:3.12-slim   :8002    internal HTTP (called by api-gateway via httpx)
rag-service     python:3.12-slim   :8003    /rag/search (internal)
ingestion-svc   python:3.12-slim   :8004    /ingest

# Infrastructure
chromadb        chromadb/chroma    :8005
postgres        postgres:16-alpine :5432
ollama          ollama/ollama      :11434
aspire          mcr.microsoft.com/dotnet/aspire-dashboard:9.0  :18888/:4317
portainer       portainer/portainer-ce  :9000   (14a only)
headlamp        headlamp-k8s/headlamp   :4466   (14b only)
```

---

## macOS compatibility notes

| Issue | Impact | Fix in plan |
|---|---|---|
| **Ollama already runs natively** on macOS (Homebrew install from `setup_macos.sh`) | Running a second Ollama inside Docker would conflict on `:11434` | Add `docker-compose.override.macos.yml` that removes the `ollama` container and sets `OLLAMA_HOST=http://host.docker.internal:11434` for all services |
| **Apple Silicon (M1/M2/M3)** — some images lack ARM64 variants | Container fails to start or runs under Rosetta emulation (slow) | Add `platform: linux/arm64` to all services in `docker-compose.yml`; verify ARM64 availability for each image (all proposed images — postgres, chromadb, portainer, aspire — have ARM64 builds) |
| **Docker Desktop memory limit** defaults to 2 GB — too low for all pods simultaneously | OOM kills inside containers, especially the agentic service | Document in `docker/README.md`: bump Docker Desktop memory to ≥ 8 GB in Settings → Resources before running `docker compose up` |

Usage on macOS:
```bash
# native Ollama must already be running (setup_macos.sh handles this)
docker compose -f docker-compose.yml -f docker-compose.override.macos.yml up --build
```

---

## Phase 14a — Docker Compose

### New files

**`docker/` directory** — one Dockerfile per service + shared nginx config:
- `docker/frontend/Dockerfile` — multi-stage: `node:20-alpine` build → `nginx:alpine` serve
- `docker/api-gateway/Dockerfile`
- `docker/voice-service/Dockerfile`
- `docker/agentic-service/Dockerfile`
- `docker/rag-service/Dockerfile`
- `docker/ingestion-service/Dockerfile`
- `docker/nginx.conf` — frontend reverse proxy config

Each Python service Dockerfile follows this pattern:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY src/requirements/<service>.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ .
CMD ["uvicorn", "agentic_backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**`src/requirements/` directory** — per-service dependency slices (split from `requirements.txt`):
- `base.txt` — fastapi, pydantic, opentelemetry, httpx, python-dotenv, pydantic-settings
- `agentic.txt` — base + langchain stack, langgraph, pandas, reportlab, python-pptx, python-docx, python-telegram-bot
- `rag.txt` — base + chromadb, langchain-chroma, langchain-text-splitters, langchain-ollama
- `voice.txt` — base + faster-whisper, piper-tts
- `ingestion.txt` — base + pymupdf, pymupdf4llm, jsonschema
- `gateway.txt` — base only (routes + httpx fan-out)
- Keep root `src/requirements.txt` as full union for local dev / CI

**`docker-compose.yml`** at repo root — all services, volumes, env_file, depends_on, healthchecks, network.

**`.env.docker`** at repo root — Docker-specific env overrides:
```
CHROMA_HOST=chromadb
CHROMA_PORT=8005
OLLAMA_HOST=http://ollama:11434
AGENTIC_SERVICE_URL=http://agentic-service:8002
RAG_SERVICE_URL=http://rag-service:8003
VOICE_SERVICE_URL=http://voice-service:8001
INGESTION_SERVICE_URL=http://ingestion-service:8004
# DATABASE_URL deferred to Phase 14c (SQLite shared volume used in 14a/14b)
```

**`src/agentic_backend/api/gateway_client.py`** — thin `httpx.AsyncClient` wrapper; reads service base URLs from `settings`; used by api-gateway route handlers to fan out requests.

> **Streaming preserved:** `/chat/stream` (SSE) must NOT be buffered at the gateway. The gateway route handler uses `httpx.AsyncClient.stream("POST", ...)` and wraps the result in FastAPI's `StreamingResponse`, forwarding each chunk as it arrives. This keeps the token-by-token UX identical to the current monolith. All other routes use normal `await client.post(...)`.

**Voice capabilities preserved:** `/audio/transcribe`, `/audio/synthesize`, `/audio/correction` move to `voice-service` unchanged. Piper `.onnx` files and Whisper model cache are Docker volumes mounted at the same paths the code already reads — zero code changes in `voice/stt.py` or `voice/tts.py`.

**`src/frontend/src/components/ServicesStatus.tsx`** — polls `GET /health/services` every 10 s; renders a status grid (service name + latency + ✅/⚠/❌). Mounted in the sidebar.

### Key code migrations

**SQLite — shared volume + single writer (Phase 14a/14b strategy)**

SQLite is kept as-is. Both `memory.sqlite` and `audit.sqlite` are mounted from a named Docker volume (`sqlite_data`) so the files persist across container restarts. All DB writes are routed exclusively through `api-gateway` — no other pod imports or writes to SQLite directly. WAL mode is enabled at startup (`PRAGMA journal_mode=WAL`) to allow concurrent reads from other pods.

Zero Python code changes required. Only `docker-compose.yml` volume config.

Full SQLite → Postgres migration is deferred to **Phase 14c** (see below).

**ChromaDB embedded → server mode** (`src/agentic_backend/rag/retriever.py`, one-line change):
```python
client = (
    chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    if settings.chroma_host
    else chromadb.PersistentClient(path=str(settings.chroma_persist_dir))
)
```
Add `chroma_host: str | None = None` and `chroma_port: int = 8005` to `config.py`.

**Model files as Docker volumes** (no code change — mount paths stay identical inside container):
- `./src/voice/piper_voices:/app/voice/piper_voices:ro` — Piper `.onnx` files
- `~/.ollama:/root/.ollama` — **bind mount** host's existing Ollama model cache; no re-download on first run (WSL2/Linux only; macOS uses native Ollama via `host.docker.internal`)
- `~/.cache/huggingface:/root/.cache/huggingface` — **bind mount** host's existing faster-whisper model cache; no re-download

**New gateway endpoint** `GET /health/services` in `src/agentic_backend/api/routes/health.py` — fans out `httpx` health checks to all downstream services, returns JSON summary.

`run_all.sh` is **not removed** — local non-Docker dev continues to work unchanged.

---

## Phase 14b — Kubernetes + Helm

### New files

```
helm/
  Chart.yaml
  values.yaml              # default / dev values
  values.prod.yaml         # production overrides
  templates/
    _helpers.tpl
    configmap.yaml
    <service>/             # one sub-folder per pod
      deployment.yaml
      service.yaml
    voice-service/hpa.yaml
    api-gateway/hpa.yaml
    postgres/pvc.yaml + secret.yaml
    chromadb/pvc.yaml
    ollama/pvc.yaml
```

Each Deployment includes `livenessProbe` + `readinessProbe` on `GET /health`, resource requests/limits, and `envFrom` referencing the shared ConfigMap + per-service Secret. HPA on `voice-service` and `api-gateway` (CPU threshold, min 1 / max 3 replicas).

---

## Phase 14c — SQLite → PostgreSQL migration (separate phase, added to BACKLOG.md)

**Goal:** Replace the shared-volume SQLite workaround with a proper multi-writer Postgres instance.

| Item | Detail |
|---|---|
| Add `alembic` + `asyncpg` to `src/requirements.txt` | Migration tooling + async Postgres driver |
| Add `database_url: str` to `src/agentic_backend/config.py` | Defaults to SQLite for local dev; overridden to `postgresql+asyncpg://...` in Docker |
| Update `src/agentic_backend/memory/store.py` | Use `settings.database_url` instead of hardcoded path |
| Update `src/agentic_backend/audit/store.py` | Same swap |
| Create `alembic/` at repo root | Initial migration mirrors existing SQLite schema |
| `docker-compose.yml` | Replace `sqlite_data` volume with `postgres` service + `pg_data` volume |
| Remove single-writer constraint from api-gateway | All pods can now write directly |

**When to do it:** After Phase 14a is stable in Docker Compose and smoke tests pass. Can run in parallel with Phase 14b (Kubernetes).

**Deliverables:**
- `alembic/` directory at repo root with initial migration
- Updated `docker-compose.yml` — replace `sqlite_data` named volume with `postgres` service + `pg_data` volume
- Updated `src/agentic_backend/config.py` — `database_url` field
- Updated `src/agentic_backend/memory/store.py` + `src/agentic_backend/audit/store.py` — use `settings.database_url`
- Remove single-writer constraint from api-gateway (all pods write directly)
- `src/requirements.txt` — add `alembic`, `asyncpg`
- `docs/BACKLOG.md` — Phase 14c section added
- `README.md` + `docs/wiki/Home.md` — Phase 14c roadmap row

**Verification:**
- `docker compose exec postgres psql -U poc -c '\dt'` — audit + memory tables present
- `alembic upgrade head` runs cleanly from scratch
- `python src/scripts/smoke_test.py` — full chat flow, audit events written to Postgres

> During implementation, add this as **Phase 14c** in `docs/BACKLOG.md` immediately after the Phase 14b section, and add a row to the roadmap tables in `README.md` and `docs/wiki/Home.md`.

---

## Setup script changes (setup_wsl.sh + setup_macos.sh)

Both scripts get a new **optional** final step — opt-in via `DOCKER_SETUP=true`, off by default so the existing native dev flow is untouched.

**`setup_wsl.sh` — new step [11/11]:**
```bash
echo "[11/11] Docker Compose stack (Phase 14, optional)..."
if [ "${DOCKER_SETUP:-false}" = "true" ]; then
  docker compose build --pull
  docker compose pull postgres chromadb portainer aspire
  echo "  Images ready. Run: docker compose up"
else
  echo "  Skipped (DOCKER_SETUP=true to enable). Or directly: docker compose up --build"
fi
```

**`setup_macos.sh` — new step [10/10] (same logic, different Compose command):**
```bash
echo "[10/10] Docker Compose stack (Phase 14, optional)..."
if [ "${DOCKER_SETUP:-false}" = "true" ]; then
  docker compose -f docker-compose.yml -f docker-compose.override.macos.yml build --pull
  docker compose pull postgres chromadb portainer aspire
  echo "  Images ready. Run: docker compose -f docker-compose.yml -f docker-compose.override.macos.yml up"
else
  echo "  Skipped (DOCKER_SETUP=true to enable)."
fi
```

`run_all.sh` stays unchanged — native (non-Docker) dev continues to work as before.

---

## Files to create (full list)

| Path | Purpose |
|---|---|
| `docker/` | Per-service Dockerfiles + nginx.conf |
| `docker-compose.yml` | Full local Compose stack |
| `.env.docker` | Docker env overrides |
| `src/requirements/*.txt` | Per-service dependency slices |
| `src/agentic_backend/api/gateway_client.py` | httpx inter-service client |
| `src/frontend/src/components/ServicesStatus.tsx` | Health status grid in SPA |
| `alembic/` | Deferred to Phase 14c |
| `helm/` | Kubernetes + Helm chart (14b) |
| `docs/architecture/container-orchestration.md` | Technical deep-dive |
| `docs/wiki/Container-Orchestration.md` | User-facing wiki page |

## Files to modify

| Path | Change |
|---|---|
| `src/agentic_backend/config.py` | `database_url`, `chroma_host`, `chroma_port`, `*_service_url` fields |
| `src/agentic_backend/rag/retriever.py` | ChromaDB client swap (2 lines) |
| `src/agentic_backend/memory/store.py` | Enable WAL mode at startup (`PRAGMA journal_mode=WAL`) |
| `src/agentic_backend/audit/store.py` | Same WAL pragma |
| `src/agentic_backend/api/routes/health.py` | Add `GET /health/services` fan-out |
| `src/frontend/src/App.tsx` | Mount ServicesStatus in sidebar |
| `src/.env.example` | Document new Docker env vars |
| `src/requirements.txt` | No changes (alembic/asyncpg deferred to Phase 14c) |
| `README.md` | Phase 14 ✅, roadmap update |
| `docs/wiki/Home.md` | Roadmap row + deep-dive index |
| `.github/scripts/transform_wiki_links.py` | Add container-orchestration.md substitution |

---

## Verification

1. `docker compose up --build` — all containers reach `healthy`
2. `docker compose ps` — no service in `Exit` or `Restarting`
3. `python src/scripts/smoke_test.py` — full chat flow via api-gateway at `:8000`
4. SQLite persistence: `docker compose exec api-gateway ls data/` — `memory.sqlite` and `audit.sqlite` present on the shared volume
5. Portainer CE at `http://localhost:9000` — all containers visible, logs accessible
6. React SPA Services tab — all pods show ✅
7. (14b) `helm install insurance-rag ./helm --dry-run` — no template errors
8. (14b) `kubectl get pods` — all deployments `Ready`
9. Run `/wiki-check` before any PR merge to `dev`
