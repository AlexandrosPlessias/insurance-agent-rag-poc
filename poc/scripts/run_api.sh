#!/usr/bin/env bash
set -euo pipefail
source .venv/bin/activate
uvicorn app.api.main:app --reload \
  --host "${API_HOST:-0.0.0.0}" \
  --port "${API_PORT:-8000}"
