#!/usr/bin/env bash
# One-shot WSL2 Ubuntu bootstrap for the insurance-agent-rag-poc PoC.
# Run from the repo root:  bash scripts/setup_wsl.sh
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3.11}"
VENV_DIR="${VENV_DIR:-.venv}"

echo "[1/5] Installing system packages..."
sudo apt-get update
sudo apt-get install -y \
  python3.11 python3.11-venv python3.11-dev \
  build-essential curl git

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
echo "  source $VENV_DIR/bin/activate"
