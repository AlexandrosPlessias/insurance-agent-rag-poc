#!/usr/bin/env bash
# One-shot macOS bootstrap for the insurance-agent-rag-poc PoC.
# Run from anywhere:  bash src/scripts/setup_macos.sh
#
# Requires: macOS 12+, Homebrew, Xcode Command Line Tools
# Skip the Aspire Docker image pre-pull with:
#   SKIP_OBSERVABILITY=true bash src/scripts/setup_macos.sh
# Skip voice model downloads (Piper TTS + faster-whisper STT) with:
#   SKIP_VOICE=true bash src/scripts/setup_macos.sh
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

echo "[1/8] Checking Xcode Command Line Tools..."
if ! xcode-select -p >/dev/null 2>&1; then
  echo "  Installing Xcode CLT — a GUI dialog will appear, complete it then rerun."
  xcode-select --install
  echo "  Waiting for installation..." >&2
  until xcode-select -p >/dev/null 2>&1; do sleep 5; done
fi
echo "  CLT path: $(xcode-select -p)"

echo "[2/8] Installing Homebrew packages..."
if ! command -v brew >/dev/null 2>&1; then
  echo "ERROR: Homebrew not found. Install from https://brew.sh then rerun." >&2
  exit 1
fi
brew update --quiet
# sqlite3 ships with macOS; we only install the others
brew install python git curl zstd 2>/dev/null || true

"$PYTHON_BIN" -c "import sys; assert sys.version_info >= (3, 11), \
  f'Python 3.11+ required, found {sys.version.split()[0]}'"
echo "  Using $($PYTHON_BIN --version)"

echo "[3/8] Creating Python venv at $VENV_DIR..."
$PYTHON_BIN -m venv "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "[4/8] Installing Python deps..."
pip install --upgrade pip wheel
pip install -r requirements.txt

echo "[5/8] Installing Node.js via nvm..."
install_and_load_nvm
nvm install --lts
nvm alias default 'lts/*'
load_nvm
echo "  Node $(node -v) at $(command -v node)"

echo "[6/8] Installing frontend deps..."
if [ "$SKIP_FRONTEND" = "true" ]; then
  echo "  Skipped (SKIP_FRONTEND=true)."
else
  (
    cd frontend
    npm install
    if [ "$SKIP_PLAYWRIGHT" = "true" ]; then
      echo "  Skipping Playwright browser (SKIP_PLAYWRIGHT=true)."
    else
      npx playwright install chromium
      # playwright install-deps is Linux-only; not needed on macOS
    fi
  )
fi

echo "[7/8] Installing Ollama..."
if ! command -v ollama >/dev/null 2>&1; then
  brew install ollama
fi

# Start the Ollama daemon if it isn't already running
if ! pgrep -x ollama >/dev/null 2>&1; then
  echo "  Starting Ollama daemon in background..."
  ollama serve >/dev/null 2>&1 &
  OLLAMA_PID=$!
  sleep 3
  echo "  Ollama PID $OLLAMA_PID"
fi

ollama pull qwen2.5:7b
ollama pull qwen2.5:3b
ollama pull nomic-embed-text

echo "[8/9] Installing Docker Desktop for Aspire observability (Phase 5)..."
if [ "$SKIP_OBSERVABILITY" = "true" ]; then
  echo "  Skipped (SKIP_OBSERVABILITY=true). Pull later:"
  echo "    docker pull $ASPIRE_IMAGE"
else
  if ! command -v docker >/dev/null 2>&1; then
    echo "  Installing Docker Desktop via Homebrew..."
    brew install --cask docker
  fi
  # Docker Desktop needs to be running before we can pull
  if ! docker info >/dev/null 2>&1; then
    echo "  Starting Docker Desktop..."
    open /Applications/Docker.app
    echo "  Waiting for daemon (up to 60 s)..."
    for _ in $(seq 1 30); do
      sleep 2
      docker info >/dev/null 2>&1 && break || true
    done
  fi
  if docker info >/dev/null 2>&1; then
    docker pull "$ASPIRE_IMAGE" && echo "  OK — image cached" \
      || echo "  WARN: docker pull failed; run_observability.sh will retry" >&2
  else
    echo "  WARN: Docker daemon did not start in time."
    echo "  Open Docker Desktop manually, then: docker pull $ASPIRE_IMAGE"
  fi
fi

echo "[9/9] Downloading voice models — Piper TTS + faster-whisper STT (Phase 13, optional)..."
if [ "$SKIP_VOICE" = "true" ]; then
  echo "  Skipped (SKIP_VOICE=true). Download later with:"
  echo "    bash scripts/download_voice_models.sh                          # EN voice"
  echo "    bash scripts/download_voice_models.sh el_GR-rapunzelina-low   # EL voice"
  echo "    python -c \"from faster_whisper.utils import download_model; download_model('medium')\""
else
  # Piper TTS — EN and EL voices
  if [ -f "voice/piper_voices/en_US-lessac-medium.onnx" ]; then
    echo "  Piper EN model already present — skipping."
  else
    bash "$SCRIPT_DIR/download_voice_models.sh"
  fi
  if [ -f "voice/piper_voices/el_GR-rapunzelina-low.onnx" ]; then
    echo "  Piper EL model already present — skipping."
  else
    bash "$SCRIPT_DIR/download_voice_models.sh" el_GR-rapunzelina-low
  fi

  # faster-whisper STT — pre-cache the model so the first API call is instant
  # and avoids HuggingFace unauthenticated rate limits (especially on macOS).
  WHISPER_MODEL="${VOICE_STT_MODEL:-medium}"
  echo "  Pre-downloading faster-whisper model '${WHISPER_MODEL}' to HF cache..."
  if python -c "
from faster_whisper.utils import download_model
download_model('${WHISPER_MODEL}')
print('  faster-whisper model ready.')
" 2>&1; then
    :
  else
    echo "  WARN: faster-whisper download failed (network / HF rate limit)." >&2
    echo "        The model will be downloaded automatically on first /audio/transcribe call." >&2
    echo "        To retry: python -c \"from faster_whisper.utils import download_model; download_model('${WHISPER_MODEL}')\"" >&2
  fi
fi

echo
echo "============================================================"
echo "Setup complete."
echo "============================================================"
echo
echo "1) Activate the venv:"
echo "     cd src && source $VENV_DIR/bin/activate"
echo
echo "2) Copy the example env:"
echo "     cp .env.example .env"
echo
echo "3) Start everything in ONE terminal (Aspire + API + UI):"
echo "     bash scripts/run_all.sh"
echo "   Ctrl+C stops the whole stack."
echo
echo "   Or run individual pieces:"
echo "     ollama serve                        # Ollama (if not already running)"
echo "     bash scripts/run_observability.sh   # Aspire (Docker)"
echo "     bash scripts/run_api.sh             # FastAPI"
echo "     cd frontend && npm run dev           # React dev server"
echo
