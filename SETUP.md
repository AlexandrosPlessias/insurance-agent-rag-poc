# Setup Guide

First-time installation of the PoC for either Windows/WSL2 or macOS. After this, see [USAGE.md](USAGE.md) for day-to-day operation.

---

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| **Windows 11** with WSL2 + Ubuntu | `wsl --install -d Ubuntu` from PowerShell |
| **Ubuntu** (inside WSL2) | 22.04 or 24.04 |
| **Disk** | ~10 GB free (models + dependencies + indexes) |
| **RAM** | 16 GB minimum recommended (`qwen2.5:7b` ≈ 4.7 GB resident) |
| **Python** | 3.11+ — installed by the bootstrap script |
| **Ollama** | Installed by the bootstrap script |
| **Docker** on WSL (Docker Desktop with WSL integration is fine) | Required only for the Aspire observability backend; the app itself runs natively |

---

## 2. WSL filesystem: work on ext4, not OneDrive

> **Skip this section if you cloned directly into your WSL home (`~/…`).** Run
> `df -T . | awk 'NR==2{print $2}'` from the repo root — if the output is `ext4` you
> are already on the fast path.

### Why it matters

Two separate problems arise when the repo lives under `/mnt/c/` (OneDrive or any Windows
path):

- **9p VirtioFS overhead.** Every file read and write crosses the 9p bridge between the
  Linux kernel and the Windows host. For file-intensive workloads — `npm install`,
  `vite` hot-reload, Python cold imports — this is 10–50× slower than a native ext4
  syscall. A `pip install -r requirements.txt` that takes 30 s on ext4 can take 10+ min
  on OneDrive.

- **Windows Node leaking into PATH.** WSL interop puts Windows `.exe` binaries on the
  Linux PATH. When a script runs `npm` or `npx` without loading nvm first, it picks up
  the Windows `node.exe`, which cannot execute the Linux ELF binaries inside
  `frontend/node_modules`. This causes `npm run dev` to fail silently and
  `npx playwright install chromium` to refuse to install.

### Verify you are on ext4

```bash
df -T . | awk 'NR==2{print $2}'
# Expected: ext4
# Bad:      9p  (Windows mount)  or  drvfs
```

### If you cloned under OneDrive — re-clone into WSL home

```bash
# From a WSL terminal (not Windows Explorer / Windows terminal):
cd ~
git clone <your-remote-url> insurance-agent-rag-poc
cd insurance-agent-rag-poc
```

Then copy your `.env` and data files if you had them:

```bash
cp /mnt/c/path/to/old/src/.env src/.env
# ChromaDB and SQLite are gitignored — copy them too if you want to keep history:
cp -r /mnt/c/path/to/old/src/data/chroma_db src/data/chroma_db
cp    /mnt/c/path/to/old/src/data/audit.sqlite src/data/audit.sqlite
```

### Python venv

The bootstrap script creates the venv at `~/irp-venv` (ext4) and `run_all.sh` finds it
automatically — no manual action is needed. Do not create the venv inside `src/.venv`
while the repo is on a Windows mount; it will be unbearably slow and may fail mid-install.

### Node (npm / npx)

`scripts/nvm_env.sh` loads the Linux Node installed by nvm before any script runs,
bypassing the Windows `node.exe` on the PATH. This is automatic — you do not need to
source nvm manually. If you run `npm` or `npx` directly in a shell where nvm is not
loaded, prefix the command with `source ~/.nvm/nvm.sh` first.

---

## 2a. macOS (Apple Silicon / Intel)

If you are running the PoC on macOS instead of WSL2, use the one-shot bootstrap script — it mirrors the WSL2 setup but uses Homebrew instead of apt.

### Prerequisites

- macOS 12+ (Monterey or newer)
- [Homebrew](https://brew.sh) installed
- `bash` available (pre-installed on all macOS versions; run the script with `bash`, not `zsh`)

### One-shot bootstrap

```bash
# Normalise line endings if you cloned on Windows
sed -i '' 's/\r$//' src/scripts/*.sh
chmod +x src/scripts/*.sh

bash src/scripts/setup_macos.sh
```

The script does the following in order:

| Step | What |
|---|---|
| [1/8] | Checks / installs Xcode Command Line Tools |
| [2/8] | `brew install python git curl zstd` |
| [3/8] | Creates `src/.venv` and installs Python deps |
| [4/8] | `pip install -r requirements.txt` |
| [5/8] | Installs Node LTS via nvm |
| [6/8] | `npm install` + Playwright Chromium in `src/frontend/` |
| [7/8] | `brew install ollama` (if missing) + pulls all three models |
| [8/8] | Pre-pulls the Aspire Dashboard Docker image (skipped if Docker not running) |

**Skip flags** (same as the WSL2 script):

```bash
SKIP_OBSERVABILITY=true bash src/scripts/setup_macos.sh   # no Docker/Aspire
SKIP_FRONTEND=true      bash src/scripts/setup_macos.sh   # no Node/npm
SKIP_PLAYWRIGHT=true    bash src/scripts/setup_macos.sh   # no Chromium download
```

### Configuration

```bash
cd src
cp .env.example .env
```

Then follow the configuration variables described in [section 4](#4-configuration).

### Verify the install

```bash
cd src && source .venv/bin/activate
python scripts/smoke_test.py
```

> Docker Desktop is optional on macOS. If not installed, set `OTEL_ENABLED=false` in `.env` to silence the Aspire startup warning, or install Docker Desktop and run `bash src/scripts/run_observability.sh` separately.

---

## 3. One-shot bootstrap

From the **repo root** inside WSL2 Ubuntu:

```bash
# If you cloned on Windows, normalise line endings first. Otherwise
# scripts may fail with "set: pipefail: invalid option name" or
# "bad interpreter: /bin/bash^M".
sed -i 's/\r$//' src/scripts/*.sh

chmod +x src/scripts/*.sh
bash src/scripts/setup_wsl.sh
```

> Always invoke with **`bash`**, not `sh` — Ubuntu's `/bin/sh` is `dash` and doesn't support `pipefail`.

The script does six things:

| Step | What |
|---|---|
| [1/6] | `apt install python3 python3-venv python3-dev build-essential curl git zstd sqlite3` (`sqlite3` is a debug convenience for the Phase 7 audit DB — the app itself only uses Python's stdlib `sqlite3` module) |
| [2/6] | Creates `src/.venv` |
| [3/6] | `pip install -r src/requirements.txt` (incl. OpenTelemetry SDK + instrumentations) |
| [4/6] | Installs Ollama if missing |
| [5/6] | Pulls `qwen2.5:7b`, `qwen2.5:3b` (Planner fast lane, Phase 11), and `nomic-embed-text` (~6.5 GB total, **takes 10–20 min on first run**) |
| [6/6] | Pre-pulls the Aspire Dashboard Docker image (~150 MB). Skipped if Docker isn't installed or `SKIP_OBSERVABILITY=true`. |

---

## 4. Configuration

Copy the example env into your local `.env`:

```bash
cd src
cp .env.example .env
```

Defaults work out of the box. Adjust only what you need:

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | Local Ollama daemon |
| `LLM_MODEL` | `qwen2.5:7b` | Worker reasoning model |
| `PLANNER_MODEL` | `qwen2.5:3b` | Planner fast-lane model (Phase 11) |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model |
| `CHROMA_PERSIST_DIR` | `src/data/chroma_db` | Vector store on disk |
| `SQLITE_PATH` | `src/data/memory.sqlite` | Episodic memory (Phase 4) |
| `AUDIT_SQLITE_PATH` | `src/data/audit.sqlite` | Phase 7 audit trail (separate file from memory) |
| `API_PORT` | `8000` | FastAPI port |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` / `RETRIEVAL_K` | `1000` / `150` / `5` | RAG tuning |
| `LOG_LEVEL` | `INFO` | `DEBUG` for verbose stderr |
| `OTEL_ENABLED` | `true` | Self-disables if Aspire isn't running, so safe to leave on |
| `OTEL_ENDPOINT` | `http://localhost:4317` | Aspire OTLP gRPC receiver |
| `OTEL_UI_URL` | `http://localhost:18888` | Aspire web UI |
| `APPROVAL_HMAC_SECRET` | *(required for Phase 12)* | Signs approval-gate tokens — set to any long random string in dev; use `python -c "import secrets; print(secrets.token_hex(32))"` to generate one |
| `APPROVALS_KPI_THRESHOLD` | `1000000.0` | KPI value above which a human-in-the-loop approval gate is triggered |
| `TELEGRAM_BOT_TOKEN` | *(optional)* | Telegram bot token for approval notifications — leave blank to use UI-only flow |
| `TELEGRAM_CHAT_ID` | *(optional)* | Telegram chat ID to receive approval messages |
| `VOICE_ENABLED` | `false` | Set `true` to activate `/audio/transcribe`, `/audio/synthesize`, `/audio/correction` (Phase 13) |
| `VOICE_STT_MODEL` | `medium` | faster-whisper model size: `tiny` / `small` / `medium` / `large-v3` |
| `VOICE_TTS_VOICE` | `en_US-lessac-medium` | Piper voice ID for English — must match a model in `src/voice/piper_voices/` |
| `VOICE_TTS_VOICE_EL` | `el_GR-rapunzelina-low` | Piper voice ID for Greek (UI language toggle ΕΛ) |
| `AUDIT_RETAIN_AUDIO` | `false` | Persist raw audio blobs to `data/audit_audio/<sha256>.wav` alongside the audit record |

### APPROVAL_HMAC_SECRET (Phase 12)

This secret signs the approval-gate tokens that flow between the backend and Telegram/UI.
Any value works in dev, but generate a proper one so tokens can't be forged:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Paste the output into `src/.env`:

```
APPROVAL_HMAC_SECRET=<paste here>
```

> ⚠ Never commit this value — `src/.env` is gitignored.

### Optional: Telegram approval notifications (Phase 12)

Skip this if you want UI-only approvals — the app works without it.

1. Open Telegram → search **@BotFather** → send `/newbot` → follow prompts → copy the token.
2. Set `TELEGRAM_BOT_TOKEN=<token>` in `src/.env`.
3. Send any message to your new bot, then open:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
   Copy the `chat.id` value from the response.
4. Set `TELEGRAM_CHAT_ID=<chat_id>` in `src/.env`.
5. Trigger an approval gate in the UI — you should receive a Telegram message with an approve/reject button.

> ⚠ Gitignored (local-only state): `src/data/chroma_db/`, `src/data/memory.sqlite`, `src/data/audit.sqlite`, `src/data/knowledge_base/processed/`, `src/data/knowledge_base/metadata/*.json`, `src/.venv/`. **Tracked**: `src/data/knowledge_base/raw/` (seed PDFs ship with the repo) and `src/data/knowledge_base/metadata/schema.json`.

---

## 5. Verify the install

End-to-end smoke test (synthesises a sample insurance PDF, ingests it, runs four sample questions including a report + an out-of-scope decline):

```bash
cd src && source .venv/bin/activate
python scripts/smoke_test.py
```

You should see Aspire-style log lines tagged by module name and a final answer for each question, e.g.:

```
Q: What is the refund window in the 2024 customer guidelines?
A: Refunds are processed within 14 calendar days of an approved request.
Route       : rag
Validated   : True
Citations   :
  - Enhanced_Customer_Guidelines_2024.pdf  ·  Refund Policy
```

If that passes, you're done with setup. Head to [USAGE.md](USAGE.md).

---

## 6. Troubleshooting setup

| Symptom | Fix |
|---|---|
| `set: pipefail: invalid option name` or `bad interpreter: /bin/bash^M` | CRLF line endings — `sed -i 's/\r$//' src/scripts/*.sh` |
| `sh: invalid option name` running a script | You used `sh script.sh`. Use `bash script.sh` — Ubuntu's `/bin/sh` is `dash` |
| `E: Unable to locate package python3.11` | The script now uses `python3` (whatever the distro ships); rerun `bash src/scripts/setup_wsl.sh` |
| `zstd` missing during Ollama install | Already added to apt install in step [1/6]; rerun if you bootstrapped before this fix |
| `ollama: command not found` | Re-run `bash src/scripts/setup_wsl.sh` or install manually: `curl -fsSL https://ollama.com/install.sh \| sh` |
| Out of memory pulling `qwen2.5:7b` | Use the lighter fallback: `ollama pull llama3.1:8b` and set `LLM_MODEL=llama3.1:8b` in `.env` |
| `ModuleNotFoundError: No module named 'app'` | You're not in src/` — `cd src` first, or use the provided `bash src/scripts/run_*.sh` wrappers |
