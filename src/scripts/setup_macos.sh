#!/usr/bin/env bash
# macOS bootstrap for the insurance-agent-rag-poc PoC.
# Run from anywhere:  bash src/scripts/setup_macos.sh
#
# All services run in Docker Compose — no Python venv or native Ollama required.
# Prerequisites: Docker Desktop for Mac (Apple Silicon or Intel), 16 GB RAM, 15 GB free disk.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "============================================================"
echo "  Insurance Agent PoC — macOS bootstrap"
echo "============================================================"
echo

# ── 1. Verify Docker is reachable ────────────────────────────────
echo "[1/3] Checking Docker..."
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

# ── 2. Verify src/.env exists ─────────────────────────────────────
echo "[2/3] Checking src/.env..."
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

# ── 3. Build + start the stack ───────────────────────────────────
echo "[3/3] Building Docker images and starting the stack..."
echo "  This pulls ~7 GB of Ollama models on the first run — may take 15–30 min."
echo "  Subsequent runs reuse the 'ollama_data' named volume."
echo
cd "$REPO_ROOT"

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
