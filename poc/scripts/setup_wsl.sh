#!/usr/bin/env bash
# One-shot WSL2 Ubuntu bootstrap for the insurance-agent-rag-poc PoC.
# Run from anywhere:  bash poc/scripts/setup_wsl.sh
#
# Skip the Aspire Docker image pre-pull with:
#   SKIP_OBSERVABILITY=true bash poc/scripts/setup_wsl.sh
set -euo pipefail

# Always operate from the poc/ root regardless of where the script is invoked.
cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"
SKIP_OBSERVABILITY="${SKIP_OBSERVABILITY:-false}"
ASPIRE_IMAGE="${ASPIRE_IMAGE:-mcr.microsoft.com/dotnet/aspire-dashboard:9.0}"

echo "[1/6] Installing system packages..."
sudo apt-get update
sudo apt-get install -y \
  python3 python3-venv python3-dev \
  build-essential curl git zstd \
  sqlite3
# sqlite3 CLI is a debug convenience for the Phase 7 audit DB
# (poc/data/audit.sqlite). The app itself only uses Python's
# stdlib sqlite3 module - this is just so `sqlite3 audit.sqlite`
# in USAGE.md doesn't error out for first-time users.

# Require Python 3.10+ (Ubuntu 22.04 ships 3.10, Ubuntu 24.04 ships 3.12).
"$PYTHON_BIN" -c "import sys; assert sys.version_info >= (3, 10), \
  f'Python 3.10+ required, found {sys.version.split()[0]}'"
echo "Using $($PYTHON_BIN --version)"

echo "[2/6] Creating Python venv at $VENV_DIR..."
$PYTHON_BIN -m venv "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "[3/6] Installing Python deps (incl. OpenTelemetry SDK + instrumentations)..."
pip install --upgrade pip wheel
pip install -r requirements.txt

echo "[4/6] Installing Ollama..."
if ! command -v ollama >/dev/null 2>&1; then
  curl -fsSL https://ollama.com/install.sh | sh
fi

echo "[5/6] Pulling local models (this can take a while)..."
ollama pull qwen2.5:7b
ollama pull nomic-embed-text

echo "[6/6] Pre-pulling Aspire Dashboard image (Phase 5 observability)..."
if [ "$SKIP_OBSERVABILITY" = "true" ]; then
  echo "  Skipped (SKIP_OBSERVABILITY=true). Pull later with:"
  echo "    docker pull $ASPIRE_IMAGE"
elif ! command -v docker >/dev/null 2>&1; then
  echo "  Docker not found - skipping. Install Docker Desktop (with WSL"
  echo "  integration) to enable the Aspire observability backend, or"
  echo "  set OTEL_ENABLED=false in .env to silence the startup warning."
else
  if docker pull "$ASPIRE_IMAGE"; then
    echo "  OK - image cached"
  else
    echo "  WARN: docker pull failed; run_observability.sh will retry" >&2
  fi
fi

echo
echo "============================================================"
echo "Setup complete."
echo "============================================================"
echo
echo "1) Activate the venv:"
echo "     cd poc && source $VENV_DIR/bin/activate"
echo
echo "2) Copy the example env:"
echo "     cp .env.example .env"
echo
echo "3) Start everything in ONE terminal (Aspire + API + UI):"
echo "     bash scripts/run_all.sh"
echo "   Ctrl+C stops the whole stack."
echo
echo "   Or run individual pieces:"
echo "     bash scripts/run_observability.sh   # Aspire (Docker)"
echo "     bash scripts/run_api.sh             # FastAPI"
echo "     bash scripts/run_ui.sh              # Streamlit"
echo
