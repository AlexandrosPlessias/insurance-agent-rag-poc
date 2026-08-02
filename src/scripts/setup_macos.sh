#!/usr/bin/env bash
# macOS bootstrap for the insurance-agent-rag-poc PoC.
# Run from anywhere:  bash src/scripts/setup_macos.sh
#
# Prerequisites: Docker Desktop for Mac (Apple Silicon or Intel), Ollama, 16 GB RAM, 15 GB free disk.
# On Apple Silicon, native Ollama runs inference via Apple Metal GPU.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "============================================================"
echo "  Insurance Agent PoC — macOS bootstrap"
echo "============================================================"
echo

# ── 1. Verify Docker is reachable ────────────────────────────────
echo "[1/4] Checking Docker..."
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: 'docker' not found." >&2
  echo "  Install Docker Desktop for Mac from https://www.docker.com/products/docker-desktop" >&2
  echo "  Or via Homebrew:  brew install --cask docker" >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "  Docker daemon not running — attempting to start Docker Desktop..."
  open /Applications/Docker.app 2>/dev/null || true
  echo "  Waiting up to 60 s for daemon..."
  for _ in $(seq 1 30); do
    sleep 2
    docker info >/dev/null 2>&1 && break || true
  done
  if ! docker info >/dev/null 2>&1; then
    echo "ERROR: Docker daemon did not start. Open Docker Desktop manually and rerun." >&2
    exit 1
  fi
fi
echo "  Docker $(docker --version | awk '{print $3}' | tr -d ',') — daemon reachable."

# ── 2. Verify native Ollama is installed (required for Metal GPU on macOS) ────
echo "[2/4] Checking Ollama..."
if ! command -v ollama >/dev/null 2>&1; then
  echo "  Ollama not found — installing via Homebrew..."
  if ! command -v brew >/dev/null 2>&1; then
    echo "ERROR: Homebrew not found. Install from https://brew.sh then re-run." >&2
    exit 1
  fi
  brew install ollama
fi
echo "  Ollama $(ollama --version 2>/dev/null | head -1) — found."

# ── 3. Verify src/.env exists ─────────────────────────────────────
echo "[3/4] Checking src/.env..."
ENV_FILE="$REPO_ROOT/src/.env"
EXAMPLE_FILE="$REPO_ROOT/src/.env.example"
if [ ! -f "$ENV_FILE" ]; then
  if [ -f "$EXAMPLE_FILE" ]; then
    cp "$EXAMPLE_FILE" "$ENV_FILE"
    echo "  Created src/.env from src/.env.example."
    echo "  IMPORTANT: Edit src/.env and set APPROVAL_HMAC_SECRET before starting."
    echo "    Generate one with:  python3 -c \"import secrets; print(secrets.token_hex(32))\""
  else
    echo "ERROR: src/.env not found and no .env.example to copy from." >&2
    exit 1
  fi
else
  echo "  src/.env already exists."
fi

# ── 4. Build + start the stack ───────────────────────────────────
echo "[4/4] Starting shared infra then project services..."
echo "  On Apple Silicon, native Ollama handles LLM inference via Metal GPU."
echo "  Models are stored in ~/.ollama — no Docker volume download needed."
echo
cd "$REPO_ROOT"

# start-infra.sh auto-detects macOS, starts native ollama serve, and proxies Docker
# containers to it via docker-compose.infra.mac.yml (nginx → host.docker.internal:11434).
./start-infra.sh

# Detect Apple Silicon — use the macOS override for platform: linux/arm64
ARCH="$(uname -m)"
if [ "$ARCH" = "arm64" ]; then
  echo "  Apple Silicon detected — using docker-compose.override.macos.yml"
  docker compose -f docker-compose.yml -f docker-compose.override.macos.yml up --build
else
  echo "  Intel Mac detected"
  docker compose up --build
fi

echo
echo "============================================================"
echo "  Stack running."
echo "============================================================"
echo "  React SPA   → http://localhost:5173"
echo "  API gateway → http://localhost:8000"
echo "  Aspire OTel → http://localhost:18888"
echo "  Portainer   → http://localhost:9000"
echo
echo "  Stop with: docker compose down"
echo "  Logs:      docker compose logs -f <service>"
echo
