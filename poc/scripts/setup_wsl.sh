#!/usr/bin/env bash
# One-shot WSL2 Ubuntu bootstrap for the insurance-agent-rag-poc PoC.
# Run from anywhere:  bash poc/scripts/setup_wsl.sh
set -euo pipefail

# Always operate from the poc/ root regardless of where the script is invoked.
cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"

echo "[1/5] Installing system packages..."
sudo apt-get update
sudo apt-get install -y \
  python3 python3-venv python3-dev \
  build-essential curl git

# Require Python 3.10+ (Ubuntu 22.04 ships 3.10, Ubuntu 24.04 ships 3.12).
"$PYTHON_BIN" -c "import sys; assert sys.version_info >= (3, 10), \
  f'Python 3.10+ required, found {sys.version.split()[0]}'"
echo "Using $($PYTHON_BIN --version)"

echo "[2/5] Creating Python venv at $VENV_DIR..."
$PYTHON_BIN -m venv "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "[3/5] Installing Python deps..."
pip install --upgrade pip wheel
pip install -r requirements.txt

echo "[4/5] Installing Ollama..."
if ! command -v ollama >/dev/null 2>&1; then
  curl -fsSL https://ollama.com/install.sh | sh
fi

echo "[5/5] Pulling local models (this can take a while)..."
ollama pull qwen2.5:7b
ollama pull nomic-embed-text

echo
echo "Setup complete. Activate the venv with:"
echo "  cd poc && source $VENV_DIR/bin/activate"
