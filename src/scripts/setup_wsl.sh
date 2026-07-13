#!/usr/bin/env bash
# One-shot WSL2 Ubuntu bootstrap for the insurance-agent-rag-poc PoC.
# Run from anywhere:  bash poc/scripts/setup_wsl.sh
#
# Skip the Aspire Docker image pre-pull with:
#   SKIP_OBSERVABILITY=true bash poc/scripts/setup_wsl.sh
# Skip the Piper TTS voice model download with:
#   SKIP_VOICE=true bash poc/scripts/setup_wsl.sh
set -euo pipefail

# Resolve the script's directory as an absolute path BEFORE cd-ing away.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Always operate from src/ regardless of where the script is invoked.
cd "$SCRIPT_DIR/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"
SKIP_OBSERVABILITY="${SKIP_OBSERVABILITY:-false}"
SKIP_FRONTEND="${SKIP_FRONTEND:-false}"
SKIP_PLAYWRIGHT="${SKIP_PLAYWRIGHT:-false}"
SKIP_VOICE="${SKIP_VOICE:-false}"
ASPIRE_IMAGE="${ASPIRE_IMAGE:-mcr.microsoft.com/dotnet/aspire-dashboard:9.0}"

# shellcheck source=scripts/nvm_env.sh
source "$SCRIPT_DIR/nvm_env.sh"

echo "[1/9] Installing system packages..."
sudo apt-get update
sudo apt-get install -y \
  python3 python3-venv python3-dev \
  build-essential curl git zstd \
  sqlite3
# sqlite3 CLI is a debug convenience for the Phase 7 audit DB
# (poc/data/audit.sqlite). The app itself only uses Python's
# stdlib sqlite3 module - this is just so `sqlite3 audit.sqlite`
# in USAGE.md doesn't error out for first-time users.

# Require Python 3.11+ (Ubuntu 22.04 ships 3.10 -- install 3.11 via deadsnakes
# PPA if needed; Ubuntu 24.04 ships 3.12).
"$PYTHON_BIN" -c "import sys; assert sys.version_info >= (3, 11), \
  f'Python 3.11+ required, found {sys.version.split()[0]}'"
echo "Using $($PYTHON_BIN --version)"

echo "[2/9] Creating Python venv at $VENV_DIR..."
$PYTHON_BIN -m venv "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "[3/9] Installing Python deps (incl. OpenTelemetry SDK + instrumentations)..."
pip install --upgrade pip wheel
pip install -r requirements.txt

echo "[4/9] Installing Node.js via nvm..."
# install_and_load_nvm installs nvm (pinned) if missing, then loads it into this
# shell. We pin the LTS so every dev gets the same Node regardless of the Windows
# Node that WSL leaks into PATH.
install_and_load_nvm
nvm install --lts
nvm alias default 'lts/*'
load_nvm
echo "  Using Node $(node -v) at $(command -v node)"

echo "[5/9] Installing frontend deps + Playwright browser..."
if [ "$SKIP_FRONTEND" = "true" ]; then
  echo "  Skipped (SKIP_FRONTEND=true)."
else
  (
    cd frontend
    npm install
    if [ "$SKIP_PLAYWRIGHT" = "true" ]; then
      echo "  Skipping Playwright browser (SKIP_PLAYWRIGHT=true)."
    else
      # Chromium download lands in the user cache (~/.cache/ms-playwright); the
      # system libs it links against need root, so we preserve PATH into sudo.
      npx playwright install chromium
      sudo env "PATH=$PATH" npx playwright install-deps chromium \
        || echo "  WARN: playwright install-deps failed — screenshots may not run." >&2
    fi
  )
fi

echo "[6/9] Installing Ollama..."
if ! command -v ollama >/dev/null 2>&1; then
  curl -fsSL https://ollama.com/install.sh | sh
fi

echo "[7/9] Pulling local models (this can take a while)..."
ollama pull qwen2.5:7b
ollama pull qwen2.5:3b
ollama pull nomic-embed-text

echo "[8/9] Installing Docker (for the Phase 5 Aspire observability backend)..."
if [ "$SKIP_OBSERVABILITY" = "true" ]; then
  echo "  Skipped (SKIP_OBSERVABILITY=true). Install later with:"
  echo "    sudo apt-get install -y docker.io"
elif command -v docker >/dev/null 2>&1; then
  echo "  Docker CLI already present ($(docker --version 2>/dev/null \
    | head -1))."
  if docker info >/dev/null 2>&1; then
    echo "  Daemon is reachable - nothing to do."
  else
    echo "  Daemon NOT reachable. If you're on Windows with Docker"
    echo "  Desktop, open it and wait for the whale icon to settle."
    echo "  On native Linux/WSL:  sudo systemctl start docker"
  fi
else
  # Detect WSL vs native Linux. On WSL we still install docker.io
  # (works fine; some users prefer it over Docker Desktop), but flag
  # the alternative.
  IS_WSL=false
  if grep -qiE '(microsoft|wsl)' /proc/version 2>/dev/null; then
    IS_WSL=true
  fi
  if [ "$IS_WSL" = "true" ]; then
    echo "  WSL detected. Installing docker.io (apt). If you'd rather"
    echo "  use Docker Desktop on Windows with WSL integration, abort"
    echo "  now (Ctrl+C), install Docker Desktop, then rerun this script."
  else
    echo "  Native Linux detected. Installing docker.io (apt)."
  fi
  sudo apt-get install -y docker.io
  # Add the current user to the 'docker' group so future invocations
  # don't need sudo. Takes effect after a fresh login / `newgrp docker`.
  if ! id -nG "$USER" | grep -qw docker; then
    sudo usermod -aG docker "$USER"
    echo "  Added $USER to the 'docker' group. Run 'newgrp docker' (or"
    echo "  log out and back in) so 'docker' works without sudo."
  fi
  # Start the daemon if it isn't already up.
  if ! sudo service docker status >/dev/null 2>&1; then
    sudo service docker start || true
  fi
  if docker info >/dev/null 2>&1 \
     || sudo docker info >/dev/null 2>&1; then
    echo "  Docker daemon reachable."
  else
    echo "  WARN: docker installed but daemon not reachable yet."
    echo "        Try:  sudo service docker start"
    echo "        Then: bash scripts/run_observability.sh"
  fi
fi

echo "[9/10] Pre-pulling Aspire Dashboard image (Phase 5 observability)..."
if [ "$SKIP_OBSERVABILITY" = "true" ]; then
  echo "  Skipped (SKIP_OBSERVABILITY=true). Pull later with:"
  echo "    docker pull $ASPIRE_IMAGE"
elif ! command -v docker >/dev/null 2>&1; then
  echo "  Docker still not found - skipping image pre-pull."
  echo "  Set OTEL_ENABLED=false in .env to silence the API startup"
  echo "  warning about Aspire being unreachable."
elif ! docker info >/dev/null 2>&1 \
     && ! sudo docker info >/dev/null 2>&1; then
  echo "  Docker daemon not reachable - skipping image pre-pull."
  echo "  Start the daemon and run: docker pull $ASPIRE_IMAGE"
else
  if docker pull "$ASPIRE_IMAGE" \
     || sudo docker pull "$ASPIRE_IMAGE"; then
    echo "  OK - image cached"
  else
    echo "  WARN: docker pull failed; run_observability.sh will retry" >&2
  fi
fi

echo "[10/10] Downloading Piper TTS voice models (Phase 13, optional)..."
if [ "$SKIP_VOICE" = "true" ]; then
  echo "  Skipped (SKIP_VOICE=true). Download later with:"
  echo "    bash scripts/download_voice_models.sh"
elif [ -f "voice/piper_voices/en_US-lessac-medium.onnx" ]; then
  echo "  Voice model already present — skipping download."
else
  bash "$SCRIPT_DIR/download_voice_models.sh"
  bash "$SCRIPT_DIR/download_voice_models.sh" el_GR-rapunzelina-low
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
echo "     cd poc/frontend && npm run dev       # React dev server"
echo
