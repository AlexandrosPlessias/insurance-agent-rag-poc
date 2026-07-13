#!/usr/bin/env bash
# One-shot launcher: [1/3] Aspire -> [2/3] FastAPI -> [3/3] React.
# Ctrl+C in this terminal cleanly stops everything.
#
# Env knobs:
#   SKIP_OBSERVABILITY=true   -> don't start Aspire (use this if you've
#                                set OTEL_ENABLED=false in your .env)
#   API_PORT=8000             -> override FastAPI port
#   API_HOST=0.0.0.0          -> override FastAPI bind address
#   SKIP_REACT=true           -> skip the React dev server
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

# Load nvm-managed Node so `npm run dev` uses the Linux install, not the Windows
# Node leaked into PATH by WSL interop (which can't run the Linux-native binaries
# in frontend/node_modules). See scripts/nvm_env.sh for the why.
# shellcheck source=scripts/nvm_env.sh
source "$SCRIPT_DIR/nvm_env.sh"
load_nvm || true

API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8000}"
ASPIRE_NAME="aspire-dashboard"

API_PID=""
REACT_PID=""
STARTED_ASPIRE=false

color()  { printf '\033[1;36m%s\033[0m\n' "$*"; }
# prefix LABEL COLOR — colorise each log line with a per-service colour.
# Usage:  some_cmd 2>&1 | prefix "[api]" "\033[36m"
prefix() {
  local label=$1 clr=${2:-"\033[0m"} reset="\033[0m"
  while IFS= read -r line; do
    printf "${clr}${label}${reset} %s\n" "$line"
  done
}

# Per-service colour aliases (cyan · green)
PREFIX_API()   { prefix "[api]"   "\033[36m"; }
PREFIX_REACT() { prefix "[react]" "\033[32m"; }

# Kill any process currently holding a TCP port (avoids "Address already in use"
# when restarting after a crash or incomplete Ctrl+C).
free_port() {
  local port=$1
  local pids
  # || true: lsof exits 1 when no process holds the port — don't let that
  # trip set -euo pipefail and silently kill the whole script.
  pids=$(lsof -ti:"$port" 2>/dev/null || true)
  [ -z "$pids" ] && return 0
  color "  Port ${port} in use — freeing stale process(es): ${pids}"
  # shellcheck disable=SC2086
  kill -9 $pids 2>/dev/null || true
  sleep 0.3
}

cleanup() {
  printf '\n'
  color "Shutting down stack ..."
  # Kill child processes first (vite worker, uvicorn reloader) then the parent,
  # so orphaned children don't keep holding ports between restarts.
  for _pid in "$REACT_PID" "$API_PID"; do
    [ -z "$_pid" ] && continue
    pkill -9 -P "$_pid" 2>/dev/null || true
    kill  -9  "$_pid"   2>/dev/null || true
  done
  # lsof can't see WSL2 socket processes — kill vite/esbuild by name as a
  # safety net so ports 5173+ are released for the next run.
  pkill -9 -f "vite"   2>/dev/null || true
  pkill -9 -f "esbuild" 2>/dev/null || true
  # fuser -k kills by socket owner regardless of process name — catches orphaned
  # node worker processes that pkill misses because their argv no longer contains
  # "vite" (e.g. grandchildren spawned via npm that inherited the listener).
  if command -v fuser >/dev/null 2>&1; then
    for _p in $(seq 5173 5182); do fuser -k "${_p}/tcp" 2>/dev/null || true; done
  fi
  if [ "$STARTED_ASPIRE" = "true" ]; then
    color "Stopping Aspire Dashboard ..."
    docker stop -t 2 "$ASPIRE_NAME" >/dev/null 2>&1 || true
  fi
  color "Done."
  exit 0
}
trap cleanup INT TERM

# ---------- [1/3] Aspire Dashboard ----------
# Always rebuild the container so each run starts with empty in-memory
# telemetry. Set KEEP_OBSERVABILITY_DATA=true to reuse an existing
# container instead.
if [ "${SKIP_OBSERVABILITY:-false}" = "true" ]; then
  color "[1/3] Skipping observability (SKIP_OBSERVABILITY=true)"
elif ! command -v docker >/dev/null 2>&1; then
  color "[1/3] Docker not found — skipping Aspire."
  color "      macOS:  brew install --cask docker"
  color "      WSL2:   sudo apt-get install -y docker.io"
  color "      Set OTEL_ENABLED=false in .env to silence API startup warnings."
elif ! docker info >/dev/null 2>&1; then
  # Daemon installed but not running — on macOS we can start it automatically.
  if [[ "$(uname)" == "Darwin" ]]; then
    color "[1/3] Docker daemon not running — opening Docker Desktop..."
    open /Applications/Docker.app
    color "      Waiting for daemon (up to 60 s)..."
    for _ in $(seq 1 30); do
      sleep 2
      docker info >/dev/null 2>&1 && break || true
    done
  fi
  if ! docker info >/dev/null 2>&1; then
    color "[1/3] Docker daemon still not reachable — skipping Aspire."
    color "      WSL2/Linux: sudo systemctl start docker"
    color "      Set OTEL_ENABLED=false in .env to silence API startup warnings."
  fi
elif [ "${KEEP_OBSERVABILITY_DATA:-false}" = "true" ] \
     && docker ps --format '{{.Names}}' | grep -q "^${ASPIRE_NAME}$"; then
  color "[1/3] Reusing existing Aspire Dashboard (KEEP_OBSERVABILITY_DATA=true)"
  STARTED_ASPIRE=true
else
  color "[1/3] Restarting Aspire Dashboard with empty telemetry ..."
  # Tolerate Aspire-start failure (daemon stopped, network error,
  # port busy). Without this guard, set -e + a non-zero exit from
  # run_observability.sh would kill the API + UI launch too.
  if RUN_ALL_ACTIVE=1 bash scripts/run_observability.sh; then
    STARTED_ASPIRE=true
    # Give the OTLP listener a moment so the API's startup probe
    # succeeds.
    sleep 3
  else
    color "  WARN: Aspire failed to start - continuing without observability."
    color "  Tip: re-run with SKIP_OBSERVABILITY=true + OTEL_ENABLED=false"
    color "       to silence the API's startup warning."
  fi
fi

# ---------- [2/3] FastAPI ----------
# Resolve the Python venv. Default is the in-tree .venv, but when it's been
# relocated to WSL-native ext4 to escape OneDrive (dramatically faster imports,
# and OneDrive can't dehydrate it), fall back to $HOME/irp-venv. Override
# explicitly with VENV_DIR=/path/to/venv.
VENV_DIR="${VENV_DIR:-.venv}"
if [ ! -f "$VENV_DIR/bin/activate" ] && [ -f "$HOME/irp-venv/bin/activate" ]; then
  VENV_DIR="$HOME/irp-venv"
fi
if [ ! -f "$VENV_DIR/bin/activate" ]; then
  echo "ERROR: no usable venv (looked in '$VENV_DIR'). Run: bash scripts/setup_wsl.sh" >&2
  exit 1
fi
color "  Using venv: $VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# Auto-ingest seed PDFs the first time, or when explicitly reset.
#   SKIP_AUTO_INGEST=true    -> never run ingestion here (also skips the slow
#                               knowledge-base probe below)
#   RESET_KNOWLEDGE=true     -> wipe ChromaDB then re-ingest before starting
if [ "${RESET_KNOWLEDGE:-false}" = "true" ]; then
  color "  RESET_KNOWLEDGE=true - wiping stores and re-ingesting ..."
  python scripts/reset_stores.py || true
  python scripts/ingest_pdfs.py || color "  WARN: ingestion failed - continuing"
elif [ "${SKIP_AUTO_INGEST:-false}" != "true" ]; then
  # This probe imports chromadb + langchain + the embeddings client cold, which
  # is slow (~10-30s) — worse with .venv on /mnt/c under OneDrive. Announce it so
  # the terminal doesn't look frozen. Skip it entirely with SKIP_AUTO_INGEST=true
  # once the knowledge base is already ingested.
  color "[2/3] Preparing FastAPI — checking knowledge base (cold import, ~10-30s; set SKIP_AUTO_INGEST=true to skip) ..."
  CHUNK_COUNT=$(python - <<'PY' 2>/dev/null || echo 0
try:
    from app.rag.vectorstore import get_vectorstore
    print(get_vectorstore()._collection.count())
except Exception:
    print(0)
PY
)
  PDF_COUNT=$(find data/knowledge_base/raw -maxdepth 1 -name '*.pdf' 2>/dev/null | wc -l)
  if [ "${CHUNK_COUNT:-0}" = "0" ] && [ "${PDF_COUNT:-0}" -gt "0" ]; then
    color "  Chroma is empty and ${PDF_COUNT} PDF(s) present - first-time ingestion ..."
    python scripts/ingest_pdfs.py || color "  WARN: ingestion failed - continuing"
  fi
fi

free_port "$API_PORT"
color "[2/3] Starting FastAPI on http://${API_HOST}:${API_PORT} ..."
uvicorn agentic_backend.api.main:app --reload \
  --host "$API_HOST" \
  --port "$API_PORT" \
  2>&1 | PREFIX_API &
API_PID=$!

# Wait for /health to respond
for _ in $(seq 1 30); do
  if curl -fs "http://localhost:${API_PORT}/health" >/dev/null 2>&1; then
    color "      API ready"
    break
  fi
  sleep 1
done

# ---------- [3/3] React dev server ----------
if [ "${SKIP_REACT:-false}" = "true" ]; then
  color "[3/3] Skipping React dev server (SKIP_REACT=true)"
elif ! command -v npm >/dev/null 2>&1; then
  color "[3/3] npm not found — run: bash scripts/setup_wsl.sh (installs Node via nvm)"
else
  # Auto-install deps on first run (or after a node_modules wipe) so the dev
  # server never silently fails to start. Check for the vite binary rather than
  # just the node_modules dir — when node_modules is a junction to an (empty)
  # relocated cache, `-d` passes but the deps aren't actually installed.
  if [ ! -x "frontend/node_modules/.bin/vite" ]; then
    color "[3/3] Installing React deps (node_modules empty or missing) ..."
    ( cd frontend && npm install )
  fi
  pkill -9 -f "vite"    2>/dev/null || true
  pkill -9 -f "esbuild" 2>/dev/null || true
  if command -v fuser >/dev/null 2>&1; then
    for _p in $(seq 5173 5182); do fuser -k "${_p}/tcp" 2>/dev/null || true; done
  fi
  sleep 1
  color "[3/3] Starting React dev server on http://localhost:5173 ..."
  cd frontend
  npm run dev 2>&1 | PREFIX_REACT &
  REACT_PID=$!
  cd ..
fi

# Wait for the React dev server to accept connections before printing the
# "all services ready" banner, so the banner is always the last thing shown.
if [ "${SKIP_REACT:-false}" != "true" ] && command -v npm >/dev/null 2>&1; then
  for _ in $(seq 1 30); do
    if curl -fs "http://localhost:5173" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

printf '\n'
printf '\033[1;36m╔══════════════════════════════════════════════════╗\033[0m\n'
printf '\033[1;36m║   Insurance RAG PoC  ·  all services ready       ║\033[0m\n'
printf '\033[1;36m╠══════════════════════════════════════════════════╣\033[0m\n'
printf '\033[1;36m║   API    →  http://localhost:8000                ║\033[0m\n'
printf '\033[1;36m║   UI     →  http://localhost:5173                ║\033[0m\n'
printf '\033[1;36m║   Aspire →  http://localhost:18888               ║\033[0m\n'
printf '\033[1;36m╚══════════════════════════════════════════════════╝\033[0m\n'
printf '\n'
color "Press Ctrl+C to stop everything."
printf '\n'

# Block until a child dies (typically only on Ctrl+C, which triggers
# `cleanup` via trap before reaching here).
wait
