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

### Windows / WSL2

```bash
docker compose up --build
```

### macOS

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
persist in the `ollama_data` volume) and rebuild only changed layers, so they start in
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

| URL | What |
|---|---|
| http://localhost:5173 | React SPA — main entry point |
| http://localhost:8000/docs | FastAPI OpenAPI docs |
| http://localhost:18888 | Aspire observability dashboard |
| http://localhost:9000 | Portainer container management |

---

## 7. Troubleshooting setup

| Symptom | Fix |
|---|---|
| Container exits immediately on startup | Check logs: `docker compose logs <service>`. Usually a missing `src/.env` or wrong `APPROVAL_HMAC_SECRET` |
| `ollama-pull` stalls or exits with error | Model download interrupted — `docker compose restart ollama-pull`. Weights that were already downloaded are preserved in the volume |
| `ingestion-service` keeps restarting | ChromaDB container not healthy yet — Compose depends_on ordering handles this, but check `docker compose logs chromadb` for OOM or disk-full errors |
| `ChromaDB connection refused` from a service | The `chromadb` container is still starting. Wait for its health check to pass (`docker compose ps`) |
| Port already in use (5173 / 8000 / 9000 / 18888) | Another process owns the port. Find it: `ss -tlnp | grep :<port>` on Linux, or `lsof -i :<port>` on macOS. Kill it or stop the conflicting service |
| Docker Desktop OOM — container killed | Increase Docker Desktop memory limit: Settings → Resources → Memory. Minimum 8 GB recommended; 12 GB for comfortable operation |
| macOS: image build fails with wrong arch | Ensure you're using the macOS override file: `docker compose -f docker-compose.yml -f docker-compose.override.macos.yml up --build` |
| `permission denied` on `src/data/` | Docker bind-mount permission issue on WSL2. Run `chmod -R 777 src/data` or move the repo to ext4 (see section 2) |
| Model download works but inference is very slow | Docker Desktop may not have enough memory assigned. Raise to at least 10 GB in Settings → Resources |
