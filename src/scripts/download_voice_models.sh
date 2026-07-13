#!/usr/bin/env bash
# Download Piper TTS voice models for Phase 13 — Multi-modal Voice.
# faster-whisper downloads its own model on first transcription call (no action needed here).
#
# Usage: bash src/scripts/download_voice_models.sh [voice]
#   voice  Piper voice ID (default: en_US-lessac-medium)
#
# Model files land in src/voice/piper_voices/ (gitignored, ~65 MB).
set -euo pipefail

VOICE="${1:-en_US-lessac-medium}"
REPO="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
DEST="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/src/voice/piper_voices"

mkdir -p "$DEST"

# Derive the HuggingFace path from the voice ID: en_US-lessac-medium → en/en_US/lessac/medium
lang="${VOICE%%_*}"                   # en
locale="${VOICE%%-*}"                  # en_US
quality="${VOICE##*-}"                 # medium
speaker="${VOICE#*-}"; speaker="${speaker%-*}"  # lessac

HF_PATH="${lang}/${locale}/${speaker}/${quality}/${VOICE}"

for ext in ".onnx" ".onnx.json"; do
    url="${REPO}/${HF_PATH}${ext}"
    target="${DEST}/${VOICE}${ext}"
    if [[ -f "$target" ]]; then
        echo "  already present: $target"
    else
        echo "  downloading ${VOICE}${ext}…"
        curl -L --progress-bar -o "$target" "$url"
    fi
done

echo ""
echo "Piper models ready in: $DEST"
echo "  $(ls -lh "$DEST"/*.onnx 2>/dev/null | awk '{print $5, $9}' || echo '(none found)')"
echo ""
echo "faster-whisper will download the STT model on first use (no action needed)."
