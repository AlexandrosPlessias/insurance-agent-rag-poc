#!/usr/bin/env bash
# WSL2 Ubuntu bootstrap for the insurance-agent-rag-poc PoC.
# Run from anywhere:  bash src/scripts/setup_wsl.sh
#
# All services run in Docker Compose — no Python venv or native Ollama required.
# Prerequisites: Docker Desktop for Windows with WSL2 integration enabled.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "============================================================"
echo "  Insurance Agent PoC — WSL2 bootstrap"
echo "============================================================"
echo

# ── 0. NVIDIA Container Toolkit (optional — only needed for GPU inference) ────
# If you have an NVIDIA GPU and want Ollama to use it (highly recommended),
# run these commands once before starting the stack:
#
#   curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
#     | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
#   curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
#     | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
#     | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
#   sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
#   sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
#   # Then restart Docker Desktop from the Windows system tray.
#   # Verify with: docker run --rm --gpus all ubuntu nvidia-smi
#
# The docker-compose.yml already has `deploy.resources.reservations.devices`
# on the ollama service — no further changes needed once the toolkit is installed.

# ── 1. Verify Docker is reachable ────────────────────────────────
echo "[1/3] Checking Docker..."
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: 'docker' not found." >&2
  echo "  Install Docker Desktop for Windows and enable WSL2 integration:" >&2
  echo "  Settings → Resources → WSL Integration → turn on for this distro" >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon is not reachable." >&2
  echo "  Open Docker Desktop on Windows and wait for the whale icon to settle." >&2
  exit 1
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
docker compose up --build

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
