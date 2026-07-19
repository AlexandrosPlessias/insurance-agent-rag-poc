# Container Orchestration (Phase 14)

Technical reference for the Phase 14 Docker Compose + Kubernetes deployment.
For the user-facing overview see [`docs/wiki/Container-Orchestration.md`](../wiki/Container-Orchestration.md).

---

## Architecture philosophy

Phase 14 breaks the monolithic FastAPI process into independently deployable service pods.
No new product features are introduced — this is purely an infrastructure and packaging phase.
The LangGraph graph, voice pipeline, RAG retrieval, and ingestion pipeline are all unchanged;
they now run in separate containers instead of a single process.

---

## Service map

```
                    ┌──────────────────┐
                    │   frontend       │  nginx:alpine · :5173→80
                    │   React SPA      │  Built artifact; /api/* proxied to api-gateway
                    └────────┬─────────┘
                             │ HTTP (nginx proxy)
                             ▼
                    ┌──────────────────┐
                    │   api-gateway    │  python:3.12-slim · :8000
                    │   FastAPI        │  /chat /health /feedback /plans /admin /reports
                    └──┬───────┬───────┘
                       │       │ httpx fan-out
          ┌────────────┘       └──────────────┐
          ▼                                   ▼
┌──────────────────┐              ┌───────────────────┐
│  agentic-service │              │   voice-service   │
│  LangGraph       │  :8002       │   STT + TTS       │  :8001
│  Planner+Workers │              │   /audio/*        │
└──────┬───────────┘              └───────────────────┘
       │
       ▼
┌──────────────────┐    ┌──────────────────┐
│   rag-service    │    │ ingestion-service │
│   ChromaDB       │    │  PDF pipeline    │
│   retrieval :8003│    │  :8004           │
└──────┬───────────┘    └────────┬─────────┘
       │                         │
       ▼                         ▼
┌─────────────────────────────────────────┐
│              Infrastructure             │
│  chromadb  :8005  (vector store)        │
│  ollama    :11434 (LLM inference)       │
│  aspire    :18888 (OTel dashboard)      │
│  portainer :9000  (container mgmt UI)   │
└─────────────────────────────────────────┘

Init / one-shot containers (restart: "no"):
  ollama-pull   — downloads models into ollama_data volume on first run
  aspire-clear  — restarts Aspire on every `docker compose up` to wipe telemetry
```

---

## Phase 14a — Docker Compose

### Files

| Path | Purpose |
|---|---|
| `docker-compose.yml` | Full stack definition: all services, volumes, healthchecks, network |
| `docker-compose.override.macos.yml` | macOS overlay: adds `platform: linux/arm64` for Apple Silicon |
| `.dockerignore` | Excludes `src/.env` from image builds — secrets injected at runtime only |
| `docker/frontend/Dockerfile` | Multi-stage: `node:20-alpine` build → `nginx:alpine` serve |
| `docker/api-gateway/Dockerfile` | `python:3.12-slim` + `requirements/gateway.txt` |
| `docker/voice-service/Dockerfile` | `python:3.12-slim` + `requirements/voice.txt` |
| `docker/agentic-service/Dockerfile` | `python:3.12-slim` + `requirements/agentic.txt` |
| `docker/rag-service/Dockerfile` | `python:3.12-slim` + `requirements/rag.txt` |
| `docker/ingestion-service/Dockerfile` | `python:3.12-slim` + `requirements/ingestion.txt` + libgl (PyMuPDF) |
| `docker/nginx.conf` | Frontend reverse proxy; `proxy_buffering off` for SSE streaming |
| `src/requirements/base.txt` | Core FastAPI + OTel — shared by all Python services |
| `src/requirements/gateway.txt` | base + python-telegram-bot |
| `src/requirements/agentic.txt` | base + LangGraph + langchain stack + reporting |
| `src/requirements/rag.txt` | base + chromadb + langchain-chroma/ollama |
| `src/requirements/voice.txt` | base + faster-whisper + piper-tts |
| `src/requirements/ingestion.txt` | base + pymupdf + chromadb + langchain stack |

### Key design decisions

**Docker-only runtime**

There is no native dev mode. Docker Compose is the only supported runtime. All infrastructure
URLs (Ollama, ChromaDB, inter-service) are baked into `config.py` defaults pointing at Docker
service names (`http://ollama:11434`, `chromadb:8000`, etc.). `src/.env` carries secrets only.

**SQLite shared volume (Phase 14a/14b)**

SQLite is kept as-is. Both `memory.sqlite` and `audit.sqlite` live on the `sqlite_data`
named Docker volume so they persist across restarts. WAL mode is enabled at every connection
(`PRAGMA journal_mode=WAL`) to allow concurrent reads from non-writer pods. All writes are
routed exclusively through `api-gateway`. This is a pragmatic workaround — see Phase 14c for
the full Postgres migration.

**ChromaDB server mode**

`src/agentic_backend/rag/vectorstore.py` always uses `chromadb.HttpClient(host, port)`.
The dual embedded/server-mode branch has been removed. ChromaDB is always accessed over HTTP
at `chromadb:8000` (internal) / `localhost:8005` (host-side).

**SSE streaming preserved**

`docker/nginx.conf` sets `proxy_buffering off` so `/api/chat/stream` SSE chunks flow
through nginx to the browser token-by-token. `gateway_client.stream_post()` uses
`httpx.AsyncClient.stream()` for the same reason on the backend fan-out path.

**Model persistence (named volumes)**

Ollama models are stored in a named volume `ollama_data` so they survive restarts without
re-downloading (~7 GB). The `ollama-pull` one-shot init container pulls `qwen2.5:7b`,
`qwen2.5:3b`, and `nomic-embed-text` on first run and exits (code 0). Subsequent
`docker compose up` calls skip the download.

| Model | Storage |
|---|---|
| Ollama models | `ollama_data` named volume (pulled once by `ollama-pull`) |
| faster-whisper | `~/.cache/huggingface:/root/.cache/huggingface` (bind mount) |
| Piper TTS | `./src/voice/piper_voices:/app/voice/piper_voices:ro` |

**Startup ingestion — skip if data exists**

`ingestion-service` checks `get_chunk_count()` at startup. If ChromaDB already has chunks,
ingestion is skipped entirely — no wipe, no re-index. This prevents the ~15-minute re-index
from being triggered on every `docker compose up` during development.

To force a full re-index: set `FORCE_REINGEST=true` in `src/.env`, restart the service,
then remove the flag.

**Aspire trace clearing**

The `aspire-clear` one-shot container (`restart: "no"`) runs on every `docker compose up`.
It waits 15 s for Aspire to initialise, then restarts the Aspire container via the Docker
socket — wiping all in-memory telemetry for a clean slate each session. Uses the same Docker
socket trust level as Portainer.

### Running

**WSL2 / Linux:**
```bash
docker compose up --build        # first run (downloads ~7 GB models — 15-30 min)
docker compose up                # subsequent runs (~30 s to healthy)
docker compose ps                # verify all healthy
```

**macOS (Apple Silicon):**
```bash
docker compose -f docker-compose.yml -f docker-compose.override.macos.yml up --build
```

### Setup scripts

`src/scripts/setup_wsl.sh` and `src/scripts/setup_macos.sh` verify Docker is running,
scaffold `src/.env` from the example, and launch `docker compose up --build`. No Python
venv, Ollama install, or Node.js required on the host.

---

## Container Monitoring — Portainer CE

### Overview

Portainer CE runs as the `portainer` service at http://localhost:9000. It mounts the Docker
socket (`/var/run/docker.sock`) read-write and provides a full container management UI
without requiring the Docker CLI.

### First-time setup

1. Open http://localhost:9000 within 5 minutes of first `docker compose up` (Portainer
   locks itself after 5 minutes for security).
2. Set an admin password (min 12 chars). Generate a strong one:
   ```bash
   python3 -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters + string.digits + '!@#') for _ in range(16)))"
   ```
3. Select **Docker Standalone** → **Connect**. You land on the Environment Details page.
4. Click **Live Connect** if shown, then navigate to **local** → **Containers**.

### Key monitoring views

| View | Path | What it shows |
|---|---|---|
| Container list | Containers | All 12 containers with status, CPU %, memory usage, uptime |
| Container logs | Containers → `<name>` → Logs | Real-time log stream with search + filter; auto-scroll |
| Container stats | Containers → `<name>` → Stats | Live CPU, memory, network I/O, disk I/O charts |
| Container exec | Containers → `<name>` → Console | Interactive shell inside a running container |
| Image list | Images | Pulled images with sizes; use to spot bloat |
| Volume list | Volumes | Named volumes (`sqlite_data`, `chroma_data`, `ollama_data`, etc.) |
| Network | Networks | `poc-net` bridge — shows which containers are connected |

### Operational tasks via Portainer

**Restart a single service:**
Containers → find `insurance-agent-rag-poc-api-gateway-1` → ⏹ Stop → ▶ Start
(or use the **Restart** button directly)

**Tail logs in real time:**
Containers → `ingestion-service-1` → Logs → enable *Auto-refresh* → *Lines*: 200

**Force re-ingest:**
1. Containers → `ingestion-service-1` → Console → Connect
2. Run `FORCE_REINGEST=true python scripts/ingest_pdfs.py`

**Inspect ChromaDB:**
Containers → `ingestion-service-1` → Console → Connect → `python scripts/inspect_chroma.py`

**Check Ollama model list:**
Containers → `ollama-1` → Console → Connect → `ollama list`

### Container health at a glance

The React SPA **Services panel** (sidebar) polls `GET /health/services` every 10 s.
`api-gateway` fans this out to all downstream pods and returns `[{name, status, latency_ms}]`
— this gives you service-level health without Portainer. Portainer adds the infrastructure
view: resource utilisation, raw logs, and the ability to restart containers.

### Security posture

- Docker socket is mounted read-write to Portainer only (and `aspire-clear` for the one-shot
  Aspire restart). No other container has socket access.
- Portainer stores its config in the `portainer_data` named volume. If the volume is corrupt
  or the password is lost, remove it with `docker volume rm insurance-agent-rag-poc_portainer_data`
  and recreate Portainer — it will prompt for a new admin password.

---

## Phase 14b — Kubernetes + Helm

### Files

```
helm/
  Chart.yaml
  values.yaml              # default / dev values
  values.prod.yaml         # production overrides
  templates/
    _helpers.tpl
    configmap.yaml
    <service>/deployment.yaml + service.yaml
    voice-service/hpa.yaml
    api-gateway/hpa.yaml
    postgres/pvc.yaml + secret.yaml
    chromadb/pvc.yaml
    ollama/pvc.yaml
```

### Key design decisions

- Each `Deployment` has `livenessProbe` + `readinessProbe` on `GET /health`
- Resource requests/limits on every pod
- HPA on `voice-service` and `api-gateway` (CPU threshold, min 1 / max 3 replicas)
- `envFrom` referencing shared `ConfigMap` + per-service `Secret`
- **Headlamp** — http://localhost:4466 (rolling updates, log streaming, pod restart)
- Complement tools: **k9s** (terminal), **Stern** (multi-pod log aggregation)

---

## Phase 14c — SQLite → PostgreSQL (future)

See [`docs/BACKLOG.md` Phase 14c section](../BACKLOG.md) for the full migration plan.
Short summary: swap `sqlite3` for SQLAlchemy async + `asyncpg`; add Alembic migrations;
replace the `sqlite_data` named volume with a `postgres:16-alpine` service.

---

## Observability

All existing OTel spans continue to work. Each container exports to `http://aspire:18889`
(OTLP gRPC) inside the `poc-net` bridge. Traces from all pods appear in a single Aspire
Dashboard timeline at http://localhost:18888.

Health routes (`/health`, `/health/services`) are excluded from OTel instrumentation to
prevent healthcheck noise from flooding the traces view.

The React SPA **Services panel** polls `GET /health/services` every 10 s. The api-gateway
fans this out to all downstream pods via `gateway_client.all_service_health()` and returns
a `[{name, status, latency_ms}]` JSON array — no Docker socket access required.

---

## Security notes

- No secrets baked into images — `src/.env` excluded via `.dockerignore`; injected at
  runtime via compose `env_file: src/.env`
- Docker socket mounted to Portainer (full management) and `aspire-clear` (one-shot restart
  only) — no other container has socket access
- Piper model volume is read-only (`:ro`)
- `proxy_buffering off` prevents nginx from holding partial SSE responses in memory
- All inter-service traffic stays inside the `poc-net` Docker bridge — nothing exposed
  to host except the mapped ports
