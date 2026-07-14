# Voice Integration (Phase 13)

Local, cloud-free audio I/O for the insurance assistant. Users can dictate questions and
hear answers spoken back. The LangGraph graph is untouched — voice is wired as a
**transport-layer bookend** around the existing chat pipeline.

For the full technical reference see
[`docs/architecture/voice-integration.md`](../architecture/voice-integration.md).

---

## How it works

```
Browser mic  →  POST /audio/transcribe  →  transcript text
                                                 │
                                         POST /chat/stream  (graph unchanged)
                                                 │
                                          final answer text
                                                 │
             ←  POST /audio/synthesize  ←  WAV response
```

**STT:** [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — CTranslate2-backed Whisper,
int8 CPU, pip-installable, no native compilation required. Silence suppressed via `vad_filter=True`.

**TTS:** [piper-tts](https://github.com/rhasspy/piper) — local neural TTS, `.onnx` models
downloaded once. Two voices ship with the PoC:

| Language | Voice ID | Model size |
|---|---|---|
| English | `en_US-lessac-medium` | ~65 MB |
| Greek | `el_GR-rapunzelina-low` | ~61 MB |

---

## API endpoints

All three return **404** when `VOICE_ENABLED=false`.

| Endpoint | Method | Purpose |
|---|---|---|
| `/audio/transcribe` | POST multipart | Upload audio → `{transcript, language, duration_ms}` |
| `/audio/synthesize` | POST JSON | `{text, language}` → `audio/wav` binary |
| `/audio/correction` | POST JSON | `{original, corrected, language}` → `{wer, cer}` |

---

## React UI

- **`VoiceInput`** — mic button + **EN / ΕΛ** language toggle. Hidden when `VOICE_ENABLED=false`.
  States: idle → recording → processing → idle.
- **`AudioPlayer`** — renders below each assistant message; calls `/audio/synthesize` on first
  render, caches the blob.
- **WER tracking** — `ChatInput` stores the original voice transcript; if the user edits it before
  sending, the frontend fires `POST /audio/correction` automatically (no extra user action).

---

## Audit events

| Event type | When logged | Key payload fields |
|---|---|---|
| `voice.transcribe` | Every `/audio/transcribe` call | `audio_sha256`, `language`, `duration_ms`, `transcript`, `audio_retained` |
| `voice.synthesize` | Every `/audio/synthesize` call | `text_sha256`, `voice_id`, `char_count`, `latency_ms` |
| `voice.correction` | User edits a voice transcript | `original`, `corrected`, `language`, `wer`, `cer` |

---

## Observability

Two new OTel spans appear in Aspire for every voice call:

| Span name | Key attributes |
|---|---|
| `tool.speech_to_text` | `model_id`, `audio_bytes`, `latency_ms`, `language`, `audio_duration_ms`, `transcript_chars` |
| `tool.text_to_speech` | `voice_id`, `char_count`, `language`, `latency_ms`, `wav_bytes` |

---

## Configuration

| Env var | Default | Description |
|---|---|---|
| `VOICE_ENABLED` | `false` | Master gate — `false` means all `/audio/*` return 404 |
| `VOICE_STT_MODEL` | `medium` | Whisper model: `tiny` / `small` / `medium` / `large-v3` |
| `VOICE_TTS_VOICE` | `en_US-lessac-medium` | English Piper voice |
| `VOICE_TTS_VOICE_EL` | `el_GR-rapunzelina-low` | Greek Piper voice |
| `AUDIT_RETAIN_AUDIO` | `false` | Persist raw audio to `data/audit_audio/<sha256>.wav` |

---

## Setup

```bash
# Download Piper voice models (one-off, ~130 MB total)
bash src/scripts/download_voice_models.sh                          # English
bash src/scripts/download_voice_models.sh el_GR-rapunzelina-low   # Greek

# Enable voice in src/.env
VOICE_ENABLED=true

# faster-whisper downloads its STT model on first transcription call — no extra step
```

Models land in `src/voice/piper_voices/` which is gitignored.

---

## Smoke test

```bash
cd src && source .venv/bin/activate
python src/scripts/smoke_test_voice.py              # interactive language picker
python src/scripts/smoke_test_voice.py --lang el    # Greek, skip picker
python src/scripts/smoke_test_voice.py --self-test  # TTS-only, no mic needed
python src/scripts/smoke_test_voice.py --record 5   # 5-second mic capture + STT
```

---

## Privacy posture

- Audio never leaves the workstation — 100 % local inference.
- Raw blobs not persisted by default — only sha256 + transcript logged.
- `AUDIT_RETAIN_AUDIO=true` is opt-in and intended for QA/compliance environments only.
