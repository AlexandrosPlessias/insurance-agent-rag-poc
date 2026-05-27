#!/usr/bin/env bash
# One-shot launcher: Aspire (Docker) -> FastAPI -> Streamlit UI.
# Ctrl+C in this terminal cleanly stops all three.
#
# Env knobs:
#   SKIP_OBSERVABILITY=true   -> don't start Aspire (use this if you've
#                                set OTEL_ENABLED=false in your .env)
#   API_PORT=8000             -> override FastAPI port
#   API_HOST=0.0.0.0          -> override FastAPI bind address
set -euo pipefail
cd "$(dirname "$0")/.."

API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8000}"
ASPIRE_NAME="aspire-dashboard"

API_PID=""
UI_PID=""
STARTED_ASPIRE=false

color()  { printf '\033[1;36m%s\033[0m\n' "$*"; }
prefix() { sed -u "s/^/$1 /"; }

cleanup() {
  printf '\n'
  color "Shutting down stack ..."
  [ -n "$UI_PID"  ] && kill  "$UI_PID"  2>/dev/null || true
  [ -n "$API_PID" ] && kill  "$API_PID" 2>/dev/null || true
  [ -n "$UI_PID"  ] && wait  "$UI_PID"  2>/dev/null || true
  [ -n "$API_PID" ] && wait  "$API_PID" 2>/dev/null || true
  if [ "$STARTED_ASPIRE" = "true" ]; then
    color "Stopping Aspire Dashboard ..."
    docker stop "$ASPIRE_NAME" >/dev/null 2>&1 || true
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
  color "[1/3] Docker not found - skipping Aspire (set OTEL_ENABLED=false in .env to silence warnings)"
elif [ "${KEEP_OBSERVABILITY_DATA:-false}" = "true" ] \
     && docker ps --format '{{.Names}}' | grep -q "^${ASPIRE_NAME}$"; then
  color "[1/3] Reusing existing Aspire Dashboard (KEEP_OBSERVABILITY_DATA=true)"
  STARTED_ASPIRE=true
else
  color "[1/3] Restarting Aspire Dashboard with empty telemetry ..."
  bash scripts/run_observability.sh
  STARTED_ASPIRE=true
  # Give the OTLP listener a moment so the API's startup probe succeeds.
  sleep 3
fi

# ---------- [2/3] FastAPI ----------
if [ ! -d ".venv" ]; then
  echo "ERROR: .venv missing. Run: bash scripts/setup_wsl.sh" >&2
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

color "[2/3] Starting FastAPI on http://${API_HOST}:${API_PORT} ..."
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

# ---------- [3/3] Streamlit ----------
color "[3/3] Starting Streamlit on http://localhost:8501 ..."
streamlit run app/ui/streamlit_app.py \
  --server.headless true \
  --server.runOnSave false \
  2>&1 | prefix "[ui] " &
UI_PID=$!

printf '\n'
color "============================================================"
color "Stack running:"
color "  UI:        http://localhost:8501"
color "  API:       http://localhost:${API_PORT}"
[ "$STARTED_ASPIRE" = "true" ] && \
  color "  Aspire:    http://localhost:18888"
color "Press Ctrl+C to stop everything."
color "============================================================"
printf '\n'

# Block until a child dies (typically only on Ctrl+C, which triggers
# `cleanup` via trap before reaching here).
wait
