#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
uvicorn app.api.main:app --reload \
  --host "${API_HOST:-0.0.0.0}" \
  --port "${API_PORT:-8000}"
