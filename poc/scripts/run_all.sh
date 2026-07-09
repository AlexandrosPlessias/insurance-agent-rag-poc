#!/usr/bin/env bash
# One-shot launcher: [1/4] Aspire -> [2/4] FastAPI -> [3/4] Streamlit (parity) + [3b/4] React -> [4/4] Telegram bot.
# Ctrl+C in this terminal cleanly stops everything.
#
# Env knobs:
#   SKIP_OBSERVABILITY=true   -> don't start Aspire (use this if you've
#                                set OTEL_ENABLED=false in your .env)
#   API_PORT=8000             -> override FastAPI port
#   API_HOST=0.0.0.0          -> override FastAPI bind address
#   SKIP_REACT=true           -> skip the React dev server (parity sprint only)
set -euo pipefail
cd "$(dirname "$0")/.."

API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8000}"
ASPIRE_NAME="aspire-dashboard"

API_PID=""
UI_PID=""
REACT_PID=""
BOT_PID=""
STARTED_ASPIRE=false

color()  { printf '\033[1;36m%s\033[0m\n' "$*"; }
prefix() { sed -u "s/^/$1 /"; }

cleanup() {
  printf '\n'
  color "Shutting down stack ..."
  [ -n "$BOT_PID"   ] && kill  "$BOT_PID"   2>/dev/null || true
  [ -n "$REACT_PID" ] && kill  "$REACT_PID" 2>/dev/null || true
  [ -n "$UI_PID"    ] && kill  "$UI_PID"    2>/dev/null || true
  [ -n "$API_PID"   ] && kill  "$API_PID"   2>/dev/null || true
  [ -n "$BOT_PID"   ] && wait  "$BOT_PID"   2>/dev/null || true
  [ -n "$REACT_PID" ] && wait  "$REACT_PID" 2>/dev/null || true
  [ -n "$UI_PID"    ] && wait  "$UI_PID"    2>/dev/null || true
  [ -n "$API_PID"   ] && wait  "$API_PID"   2>/dev/null || true
  if [ "$STARTED_ASPIRE" = "true" ]; then
    color "Stopping Aspire Dashboard ..."
    docker stop "$ASPIRE_NAME" >/dev/null 2>&1 || true
  fi
  color "Done."
  exit 0
}
trap cleanup INT TERM

# ---------- [1/4] Aspire Dashboard ----------
# Always rebuild the container so each run starts with empty in-memory
# telemetry. Set KEEP_OBSERVABILITY_DATA=true to reuse an existing
# container instead.
if [ "${SKIP_OBSERVABILITY:-false}" = "true" ]; then
  color "[1/4] Skipping observability (SKIP_OBSERVABILITY=true)"
elif ! command -v docker >/dev/null 2>&1; then
  color "[1/4] Docker not found - skipping Aspire (set OTEL_ENABLED=false in .env to silence warnings)"
elif [ "${KEEP_OBSERVABILITY_DATA:-false}" = "true" ] \
     && docker ps --format '{{.Names}}' | grep -q "^${ASPIRE_NAME}$"; then
  color "[1/4] Reusing existing Aspire Dashboard (KEEP_OBSERVABILITY_DATA=true)"
  STARTED_ASPIRE=true
else
  color "[1/4] Restarting Aspire Dashboard with empty telemetry ..."
  # Tolerate Aspire-start failure (daemon stopped, network error,
  # port busy). Without this guard, set -e + a non-zero exit from
  # run_observability.sh would kill the API + UI launch too.
  if bash scripts/run_observability.sh; then
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

# ---------- [2/4] FastAPI ----------
if [ ! -d ".venv" ]; then
  echo "ERROR: .venv missing. Run: bash scripts/setup_wsl.sh" >&2
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# Auto-ingest seed PDFs the first time, or when explicitly reset.
#   SKIP_AUTO_INGEST=true    -> never run ingestion here
#   RESET_KNOWLEDGE=true     -> wipe ChromaDB then re-ingest before starting
if [ "${RESET_KNOWLEDGE:-false}" = "true" ]; then
  color "  RESET_KNOWLEDGE=true - wiping stores and re-ingesting ..."
  python scripts/reset_stores.py || true
  python scripts/ingest_pdfs.py || color "  WARN: ingestion failed - continuing"
elif [ "${SKIP_AUTO_INGEST:-false}" != "true" ]; then
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

color "[2/4] Starting FastAPI on http://${API_HOST}:${API_PORT} ..."
uvicorn app.api.main:app --reload \
  --host "$API_HOST" \
  --port "$API_PORT" \
  2>&1 | prefix "[api]" &
API_PID=$!

# Wait for /health to respond
for _ in $(seq 1 30); do
  if curl -fs "http://localhost:${API_PORT}/health" >/dev/null 2>&1; then
    color "      API ready"
    break
  fi
  sleep 1
done

# ---------- [3/4] Streamlit (parity sprint — remove at cutover) ----------
color "[3/4] Starting Streamlit on http://localhost:8501 ..."
streamlit run app/ui/streamlit_app.py \
  --server.headless true \
  --server.runOnSave false \
  2>&1 | prefix "[ui] " &
UI_PID=$!

# ---------- [3b/4] React dev server ----------
if [ "${SKIP_REACT:-false}" = "true" ]; then
  color "[3b/4] Skipping React dev server (SKIP_REACT=true)"
elif [ ! -d "frontend/node_modules" ]; then
  color "[3b/4] React deps not installed — run: cd poc/frontend && npm install"
else
  color "[3b/4] Starting React dev server on http://localhost:5173 ..."
  cd frontend
  npm run dev 2>&1 | prefix "[react]" &
  REACT_PID=$!
  cd ..
fi

# ---------- [4/4] Telegram bot (only when token is configured) ----------
# Load TELEGRAM_BOT_TOKEN from .env if not already in the environment.
if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] && [ -f ".env" ]; then
  TELEGRAM_BOT_TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' .env | cut -d= -f2- | tr -d '[:space:]')"
fi

if [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
  color "[4/4] Starting Telegram approval bot ..."
  python scripts/run_telegram_bot.py \
    2>&1 | prefix "[bot]" &
  BOT_PID=$!
  color "      Bot ready (listening for /approve and /reject)"
else
  color "[4/4] Skipping Telegram bot (TELEGRAM_BOT_TOKEN not set)"
fi

printf '\n'
color "============================================================"
color "Stack running:"
[ -n "${REACT_PID:-}" ] && \
  color "  UI (React):      http://localhost:5173"
color "  UI (Streamlit):  http://localhost:8501  (parity sprint)"
color "  API:             http://localhost:${API_PORT}"
[ "$STARTED_ASPIRE" = "true" ] && \
  color "  Aspire:          http://localhost:18888"
[ -n "${BOT_PID:-}" ] && \
  color "  Bot:             Telegram approval bot active"
color "Press Ctrl+C to stop everything."
color "============================================================"
printf '\n'

# Block until a child dies (typically only on Ctrl+C, which triggers
# `cleanup` via trap before reaching here).
wait
