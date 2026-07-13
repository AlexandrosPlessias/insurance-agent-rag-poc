#!/usr/bin/env bash
# Spin up the .NET Aspire Dashboard as a local OTel backend.
#   - OTLP gRPC: localhost:4317  (where the API + UI send data)
#   - Web UI:    http://localhost:18888
#
# Requires Docker (or Docker Desktop) on WSL2. Auth is disabled - PoC only.
# After this starts, set OTEL_ENABLED=true in poc/.env and restart the API/UI.
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-aspire-dashboard}"
IMAGE="${IMAGE:-mcr.microsoft.com/dotnet/aspire-dashboard:9.0}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not found." >&2
  echo "       macOS:  brew install --cask docker" >&2
  echo "       WSL2:   sudo apt-get install -y docker.io" >&2
  exit 1
fi

# Daemon liveness check. `command -v docker` only proves the CLI is on PATH;
# the daemon may still be stopped. On macOS we can open Docker Desktop
# automatically; on other platforms we fail fast with a useful message.
if ! docker info >/dev/null 2>&1; then
  if [[ "$(uname)" == "Darwin" ]]; then
    echo "Docker daemon not running — starting Docker Desktop..."
    open /Applications/Docker.app
    echo "Waiting for daemon (up to 60 s)..."
    for _ in $(seq 1 30); do
      sleep 2
      docker info >/dev/null 2>&1 && break || true
    done
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "ERROR: Docker daemon isn't reachable." >&2
    echo "       Windows/WSL2: open Docker Desktop and wait for the whale icon." >&2
    echo "       Linux:        sudo systemctl start docker" >&2
    echo "       Or skip Aspire: SKIP_OBSERVABILITY=true bash scripts/run_all.sh" >&2
    exit 1
  fi
fi

# Stop any existing instance
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "Stopping existing ${CONTAINER_NAME} ..."
  docker rm -f "${CONTAINER_NAME}" >/dev/null
fi

echo "Pulling ${IMAGE} (first run can take ~1 min) ..."
# stdout is NOT redirected so the user sees pull progress. Exit
# code is checked explicitly to surface a useful message instead
# of the silent set-e kill.
if ! docker pull "${IMAGE}"; then
  echo "ERROR: docker pull failed. Check your network / Docker login" >&2
  echo "       and retry. To run without Aspire instead, set" >&2
  echo "       SKIP_OBSERVABILITY=true and rerun scripts/run_all.sh." >&2
  exit 1
fi

echo "Starting ${CONTAINER_NAME} ..."
docker run -d --rm \
  --name "${CONTAINER_NAME}" \
  -p 18888:18888 \
  -p 4317:18889 \
  -e DASHBOARD__FRONTEND__AUTHMODE=Unsecured \
  -e DASHBOARD__OTLP__AUTHMODE=Unsecured \
  "${IMAGE}" >/dev/null

cat <<EOF

Aspire Dashboard running.
  Web UI:    http://localhost:18888
  OTLP gRPC: localhost:4317

Stop with:  docker stop ${CONTAINER_NAME}
EOF

# Only print the manual-start instructions when invoked standalone
# (not via run_all.sh, which manages the full stack itself).
if [ -z "${RUN_ALL_ACTIVE:-}" ]; then
  cat <<EOF

Next (standalone mode):
  1. Set OTEL_ENABLED=true in src/.env
  2. Restart the API:  bash scripts/run_api.sh
  3. Restart the UI:   cd poc/frontend && npm run dev
  4. Make a query and refresh the dashboard.
EOF
fi
