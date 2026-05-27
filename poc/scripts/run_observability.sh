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
  echo "ERROR: docker not found. Install Docker (Desktop on Windows, "
  echo "       docker-ce in WSL2) and retry." >&2
  exit 1
fi

# Stop any existing instance
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "Stopping existing ${CONTAINER_NAME} ..."
  docker rm -f "${CONTAINER_NAME}" >/dev/null
fi

echo "Pulling ${IMAGE} (first run can take ~1 min) ..."
docker pull "${IMAGE}" >/dev/null

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

Next:
  1. Set OTEL_ENABLED=true in poc/.env
  2. Restart the API:  bash scripts/run_api.sh
  3. Restart the UI:   bash scripts/run_ui.sh
  4. Make a query and refresh the dashboard.

Stop with:  docker stop ${CONTAINER_NAME}
EOF
