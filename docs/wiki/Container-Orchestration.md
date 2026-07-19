# Container Orchestration (Phase 14)

Phase 14 breaks the monolithic FastAPI process into independently deployable service pods,
adds a shared infrastructure tier, and introduces a management UI for operating the running
stack. No new product features — this is purely an infrastructure and packaging phase.

For the full technical reference see
[`docs/architecture/container-orchestration.md`](../architecture/container-orchestration.md).

---

## Services

| Pod | Port | Responsibility |
|---|---|---|
| **frontend** | `:5173` → 80 | React SPA (nginx static serve + API proxy) |
| **api-gateway** | `:8000` | `/chat` `/health` `/feedback` `/plans` `/admin` `/reports` |
| **voice-service** | `:8001` | `/audio/transcribe` `/audio/synthesize` `/audio/correction` |
| **agentic-service** | `:8002` | LangGraph planner + workers (internal, called by gateway) |
| **rag-service** | `:8003` | ChromaDB retrieval (internal) |
| **ingestion-service** | `:8004` | PDF ingestion pipeline |
| **chromadb** | `:8005` | Vector store (server mode) |
| **ollama** | `:11434` | LLM inference (containerized; `ollama-pull` init downloads models once) |
| **aspire** | `:18888` | OTel traces + metrics + logs |
| **portainer** | `:9000` | Container management UI (Phase 14a) |

---

## Phase 14a — Docker Compose

### Prerequisites

- Docker Desktop ≥ 4.x (or Docker Engine + Compose plugin on WSL2/Linux)
- **WSL2**: WSL2 integration enabled in Docker Desktop Settings → Resources
- **macOS**: bump Docker Desktop memory to ≥ 8 GB in Settings → Resources → Memory
- 16 GB RAM, 15 GB free disk (Ollama models download automatically on first run)

### Run

**WSL2 / Linux:**
```bash
# from repo root
docker compose up --build       # first run — builds all images
docker compose up               # subsequent runs
docker compose ps               # verify all containers healthy
```

**macOS** (Apple Silicon — override adds `platform: linux/arm64`):
```bash
docker compose -f docker-compose.yml -f docker-compose.override.macos.yml up --build
```

### Access

| Service | URL |
|---|---|
| React SPA | http://localhost:5173 |
| API gateway | http://localhost:8000 |
| Portainer (container mgmt) | http://localhost:9000 |
| Aspire (OTel dashboard) | http://localhost:18888 |

### Management with Portainer CE

Open http://localhost:9000 after first launch. Portainer provides:
- Container list with status, CPU, memory
- Log streaming per container
- One-click restart / stop / start
- Image pull and update

---

## Phase 14b — Kubernetes + Helm

```bash
# Install the chart (dry-run first)
helm install insurance-rag ./helm --dry-run
helm install insurance-rag ./helm

# Check pod status
kubectl get pods

# Open Headlamp dashboard
kubectl port-forward svc/headlamp 4466:80
# → http://localhost:4466
```

**Management tools:**
- **Headlamp** (`:4466`) — web UI: rolling updates, log tail, pod restart
- **k9s** — terminal explorer (`k9s` in any terminal)
- **Stern** — aggregated multi-pod logs (`stern insurance-rag`)

---

## Configuration

All inter-service URLs are baked into `config.py` defaults — no separate env override file needed.
`src/.env` carries **secrets only**:

| Var | Required | Purpose |
|---|---|---|
| `APPROVAL_HMAC_SECRET` | Yes | HMAC key for Telegram approval callbacks |
| `TELEGRAM_BOT_TOKEN` | Optional | Telegram bot integration |
| `TELEGRAM_CHAT_ID` | Optional | Telegram chat for notifications |
| `VOICE_LLM_MODEL` | Optional | Override default voice LLM model |
| `VOICE_STT_MODEL` | Optional | Override faster-whisper model size |

Internal container-to-container URLs (`http://ollama:11434`, `http://chromadb:8000`, etc.) resolve automatically inside the `poc-net` Docker bridge — nothing to configure.

---

## Services tab in the UI

The React SPA Services panel (sidebar) polls `GET /health/services` every 10 s. The api-gateway
fans this out to all downstream pods and returns `[{name, status, latency_ms}]`. Each pod appears
as a row (✅ ok / ⚠ degraded / ❌ down) without requiring Portainer or Docker socket access.

---

## Model files

| Model | Storage |
|---|---|
| Ollama models | `ollama_data` named volume — downloaded once by `ollama-pull` init container, persisted across restarts |
| faster-whisper | `~/.cache/huggingface:/root/.cache/huggingface` (bind mount — reuses host cache) |
| Piper TTS `.onnx` | `./src/voice/piper_voices:/app/voice/piper_voices:ro` (bind mount, read-only) |

On first run `ollama-pull` pulls `qwen2.5:7b`, `qwen2.5:3b`, and `nomic-embed-text` (~7 GB total).
Subsequent `docker compose up` runs skip the download entirely.

---

## Phase 14c — SQLite → PostgreSQL (future)

Phase 14a/14b keep SQLite on a shared Docker volume (`sqlite_data`) with WAL mode enabled.
Phase 14c replaces this with a proper `postgres:16-alpine` container and Alembic migrations
so all pods can write to memory and audit tables concurrently.

See [`docs/BACKLOG.md`](../BACKLOG.md) for the Phase 14c delivery plan.

---

## Privacy & security posture

- No secrets baked into images — all values injected via `env_file` at runtime
- Docker socket mounted only to Portainer — no other container has socket access
- Piper model volume is read-only (`:ro`)
- All inter-service traffic stays inside the `poc-net` Docker bridge network
- OTel data stays inside the local Aspire container
