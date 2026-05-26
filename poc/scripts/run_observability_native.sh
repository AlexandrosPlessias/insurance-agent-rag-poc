#!/usr/bin/env bash
# OpenObserve as a native WSL service - no Docker required.
#
# Usage:
#   bash scripts/run_observability_native.sh                # download + run
#   bash scripts/run_observability_native.sh --download-only  # fetch binary then exit
#
# - Downloads the OpenObserve binary (once) into poc/.openobserve/
# - Stores data under poc/.openobserve/data/
# - Runs in the foreground (Ctrl+C to stop), or wrap with systemd-run/nohup
#
# After it starts, paste the printed OTEL_* block into poc/.env and
# restart the API + UI.
set -euo pipefail

DOWNLOAD_ONLY=false
for arg in "$@"; do
  case "$arg" in
    --download-only) DOWNLOAD_ONLY=true ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $arg" >&2
      echo "Use --help for usage." >&2
      exit 2
      ;;
  esac
done

cd "$(dirname "$0")/.."

INSTALL_DIR="${INSTALL_DIR:-.openobserve}"
DATA_DIR="${DATA_DIR:-${INSTALL_DIR}/data}"
ZO_VERSION="${ZO_VERSION:-v0.13.2}"
ADMIN_EMAIL="${ZO_ROOT_USER_EMAIL:-admin@example.com}"
ADMIN_PASSWORD="${ZO_ROOT_USER_PASSWORD:-Complexpass#123}"
HTTP_PORT="${ZO_HTTP_PORT:-5080}"

ARCH=$(uname -m)
case "$ARCH" in
  x86_64)  ARCH=amd64 ;;
  aarch64) ARCH=arm64 ;;
  *) echo "Unsupported arch: $ARCH" >&2; exit 1 ;;
esac

mkdir -p "$INSTALL_DIR" "$DATA_DIR"

if [ ! -x "$INSTALL_DIR/openobserve" ]; then
  URL="https://github.com/openobserve/openobserve/releases/download/${ZO_VERSION}/openobserve-${ZO_VERSION}-linux-${ARCH}-musl.tar.gz"
  echo "Downloading OpenObserve ${ZO_VERSION} ..."
  curl -fsSL "$URL" | tar -xz -C "$INSTALL_DIR"
  if [ ! -x "$INSTALL_DIR/openobserve" ]; then
    echo "ERROR: openobserve binary missing after extraction." >&2
    echo "Inspect $INSTALL_DIR for the right filename." >&2
    exit 1
  fi
else
  echo "OpenObserve binary already present at $INSTALL_DIR/openobserve"
fi

if [ "$DOWNLOAD_ONLY" = "true" ]; then
  echo "Download-only mode: binary ready. Run without --download-only to start it."
  exit 0
fi

B64=$(printf '%s' "${ADMIN_EMAIL}:${ADMIN_PASSWORD}" | base64 -w0)

cat <<EOF

OpenObserve is starting on http://localhost:${HTTP_PORT}
  Login: ${ADMIN_EMAIL} / ${ADMIN_PASSWORD}

----------------------------------------------------------------------
Add (or update) these lines in poc/.env:

OTEL_ENABLED=true
OTEL_PROTOCOL=http
OTEL_ENDPOINT=http://localhost:${HTTP_PORT}/api/default
OTEL_HEADERS=Authorization=Basic ${B64}
OTEL_UI_URL=http://localhost:${HTTP_PORT}
----------------------------------------------------------------------

Then restart the API and UI; new traces and logs appear in the
"Streams" tab of the dashboard (filter by service.name).

Stop with Ctrl+C.
EOF

cd "$INSTALL_DIR"
export ZO_ROOT_USER_EMAIL="$ADMIN_EMAIL"
export ZO_ROOT_USER_PASSWORD="$ADMIN_PASSWORD"
export ZO_DATA_DIR="$DATA_DIR"
export ZO_HTTP_PORT="$HTTP_PORT"
exec ./openobserve
