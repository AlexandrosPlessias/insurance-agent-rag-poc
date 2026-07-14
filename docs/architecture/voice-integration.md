# Voice Integration (Phase 13)

> Multi-modal voice layer — local STT (faster-whisper) + TTS (piper-tts), EN/ΕΛ support,
> WER/CER quality signal, and audit retention.
> Config reference: [src/agentic_backend/config.py](../../src/agentic_backend/config.py).
> Roadmap context: [README.md § Phase 13](../../README.md#phase-13--multi-modal-voice).

---

## 1 · Architecture philosophy

Voice is wired at the **transport boundary**, not inside the LangGraph graph. The graph
receives and returns plain text strings — it has no awareness that audio was involved.

```
                ┌──────────────────────────────────────────┐
                │              Browser / UI                │
                └──────┬───────────────────────────────────┘
                       │ multipart WAV / JSON body
                       ▼
              ┌─────────────────────┐
              │  POST /audio/transcribe  │  STT boundary
              │  faster-whisper      │  (transport layer)
              └──────────┬──────────┘
                         │ plain text string
                         ▼
              ┌─────────────────────────────────────────┐
              │           LangGraph graph                │
              │  (Planner · Orchestrator · Workers)      │
              │  unchanged — receives/returns str        │
              └──────────┬──────────────────────────────┘
                         │ plain text string
                         ▼
              ┌─────────────────────┐
              │  POST /audio/synthesize  │  TTS boundary
              │  piper-tts           │  (transport layer)
              └──────────┬──────────┘
                         │ raw WAV bytes
                         ▼
                ┌──────────────────────────────────────────┐
                │           AudioPlayer (React)             │
                └──────────────────────────────────────────┘
```

**Key constraint.** Neither STT nor TTS may call into the graph, modify graph state, or be
invoked from inside a Skill or Tool. They are HTTP endpoints consumed exclusively by the
frontend. This keeps the graph text-only, stateless with respect to audio, and independently
testable.

---

## 2 · STT — `src/agentic_backend/voice/stt.py`

### 2.1 Library

| Aspect | Value |
|---|---|
| Library | `faster-whisper` (CTranslate2-backed quantised Whisper) |
| Compute | int8 CPU — no GPU required, no native compilation |
| Distribution | pip-installable; model weights downloaded on first call |
| Model singleton | `_model: WhisperModel` — lazy-loaded, cached for the process lifetime |

### 2.2 API

```python
def transcribe(audio_bytes: bytes, language: str | None = None) -> dict:
    ...
```

**Returns:**

```python
{
    "transcript":   str,   # concatenated segment text
    "language":     str,   # detected or forced language code
    "duration_ms":  int,   # audio length in milliseconds
}
```

**Internals.**

1. `audio_bytes` written to a temporary `.wav` file.
2. `WhisperModel.transcribe(path, vad_filter=True, language=language)` called; VAD filter
   suppresses silence segments before beam search.
3. Temp file deleted unconditionally (try/finally).
4. Segments concatenated; timing metadata aggregated.

### 2.3 Config

| Env var | Default | Options |
|---|---|---|
| `VOICE_STT_MODEL` | `medium` | `tiny` / `small` / `medium` / `large-v3` |

Larger models improve accuracy at the cost of first-call load time and per-call latency.
The `medium` default balances accuracy against a ~600 MB model footprint.

### 2.4 OTel span

Span name: **`tool.speech_to_text`**

| Attribute | Value |
|---|---|
| `model_id` | active Whisper model tag |
| `audio_bytes` | raw size in bytes |
| `language_hint` | caller-supplied language (may be `None`) |
| `latency_ms` | wall-clock transcription time |
| `language` | detected or forced language code |
| `audio_duration_ms` | audio length |
| `transcript_chars` | character count of the returned transcript |

---

## 3 · TTS — `src/agentic_backend/voice/tts.py`

### 3.1 Library

| Aspect | Value |
|---|---|
| Library | `piper-tts` |
| Model format | `.onnx` + `.onnx.json` sidecar per voice |
| Distribution | pip-installable; voice files downloaded separately (see [§ 9](#9--setup)) |
| Voice cache | `_voices: dict[str, PiperVoice]` — keyed by `voice_id`, one entry per language |

### 3.2 API

```python
def synthesize(text: str, language: str = "en") -> bytes:
    ...
```

Returns raw WAV bytes in RIFF/PCM format, ready for direct HTTP streaming.

**Voice selection.**

```python
def _voice_id_for_language(language: str) -> str:
    return VOICE_TTS_VOICE_EL if language == "el" else VOICE_TTS_VOICE
```

A `PiperVoice` for the resolved `voice_id` is loaded on first use and kept in `_voices`
for subsequent calls.

### 3.3 Supported languages

| Language code | Voice ID | Model size |
|---|---|---|
| `en` | `en_US-lessac-medium` | ~65 MB |
| `el` | `el_GR-rapunzelina-low` | ~61 MB |

### 3.4 Config

| Env var | Default |
|---|---|
| `VOICE_TTS_VOICE` | `en_US-lessac-medium` |
| `VOICE_TTS_VOICE_EL` | `el_GR-rapunzelina-low` |
| `VOICE_MODELS_DIR` | `src/voice/piper_voices` |

`VOICE_MODELS_DIR` is the directory where `.onnx` and `.onnx.json` files are expected.
It is gitignored; voices are downloaded once via the bootstrap script.

### 3.5 OTel span

Span name: **`tool.text_to_speech`**

| Attribute | Value |
|---|---|
| `voice_id` | active piper voice identifier |
| `char_count` | input text length |
| `language` | requested language code |
| `latency_ms` | wall-clock synthesis time |
| `wav_bytes` | size of the returned WAV payload |

---

## 4 · API routes — `src/agentic_backend/api/routes/audio.py`

All three endpoints return **HTTP 404** when `VOICE_ENABLED=false`. No audio processing
code runs when voice is disabled.

### 4.1 `POST /audio/transcribe`

**Request:** `multipart/form-data`

| Field | Type | Description |
|---|---|---|
| `file` | binary | WAV audio blob |
| `language` | string (optional) | force language code (`en`, `el`) |
| `user_id` | string | caller identity for audit |

**Response:** `application/json`

```json
{
  "transcript":  "...",
  "language":    "en",
  "duration_ms": 3200
}
```

**Audit retention.** When `AUDIT_RETAIN_AUDIO=true`, the raw WAV is written to
`data/audit_audio/<sha256>.wav` before transcription. The `sha256` is the hex digest
of the raw bytes and serves as the deduplication key in the audit log.

**Audit event:** `voice.transcribe`

---

### 4.2 `POST /audio/synthesize`

**Request:** `application/json`

```json
{ "text": "...", "language": "en" }
```

**Response:** `audio/wav` — raw binary WAV stream.

**Audit event:** `voice.synthesize`

---

### 4.3 `POST /audio/correction`

Accepts a user's corrected transcript and the original STT output. Computes WER and CER
via Levenshtein distance and logs the result as a quality signal. No model call is made.

**Request:** `application/json`

```json
{ "original": "...", "corrected": "...", "language": "en" }
```

**Response:** `application/json`

```json
{ "wer": 0.12, "cer": 0.04 }
```

**Metric definitions:**

```
WER = word-level Levenshtein(original, corrected) / len(reference_words)
CER = char-level Levenshtein(original, corrected) / len(reference_chars)
```

**Audit event:** `voice.correction`

---

## 5 · Frontend components

### 5.1 Component inventory

| Component | Path | Responsibility |
|---|---|---|
| `VoiceInput` | `src/frontend/src/components/VoiceInput.tsx` | Mic button, EN/ΕΛ language toggle, recording state machine |
| `AudioPlayer` | `src/frontend/src/components/AudioPlayer.tsx` | Plays synthesized TTS for each assistant message |
| `ChatInput` | `src/frontend/src/components/ChatInput.tsx` | Tracks `voiceOriginal`; fires correction report on edit |

### 5.2 `VoiceInput`

- Hidden when `voiceEnabled=false` (feature flag from server config).
- States: `idle` → `recording` → `processing` → `idle`.
- Captures audio via `navigator.mediaDevices.getUserMedia` + `MediaRecorder`.
- On stop: calls `transcribeAudio(blob, language)` (see [§ 5.4](#54-api-client)); pastes
  the returned transcript into the chat input.

### 5.3 Correction flow (`ChatInput`)

1. `VoiceInput` sets the input value and stores the raw transcript as `voiceOriginal`.
2. If the user edits the pre-filled transcript before submitting, `voiceOriginal ≠ submitted`.
3. On submit, `ChatInput` calls `reportVoiceCorrection(voiceOriginal, submitted, language)`.
4. The `/audio/correction` endpoint computes WER/CER and writes a `voice.correction` audit
   event — no extra user action required.

This provides a continuous, friction-free quality signal for STT accuracy in production.

### 5.4 API client

`src/frontend/src/api/client.ts` exports three voice helpers:

| Function | Endpoint | Payload |
|---|---|---|
| `transcribeAudio(blob, language)` | `POST /audio/transcribe` | multipart |
| `synthesizeSpeech(text, language)` | `POST /audio/synthesize` | JSON |
| `reportVoiceCorrection(original, corrected, language)` | `POST /audio/correction` | JSON |

---

## 6 · Audit events

All events are written to the existing `audit_events` table keyed by `trace_id`.
The canonical source is [`src/agentic_backend/audit/events.py`](../../src/agentic_backend/audit/events.py).

| `event_type` | `payload_json` shape |
|---|---|
| `voice.transcribe` | `{sha256, audio_bytes, audio_retained, language, duration_ms, transcript}` |
| `voice.synthesize` | `{text_sha256, char_count, voice_id, wav_bytes, latency_ms}` |
| `voice.correction` | `{original, corrected, language, wer, cer}` |

**`audio_retained`** is `true` only when `AUDIT_RETAIN_AUDIO=true` and the WAV was
successfully written to `data/audit_audio/`. It is `false` otherwise, even if the
`sha256` is present (the hash is always computed from the bytes in memory).

---

## 7 · Config reference

All variables are loaded by `src/agentic_backend/config.py`.

| Env var | Default | Description |
|---|---|---|
| `VOICE_ENABLED` | `false` | Master gate — `false` makes all `/audio/*` return 404 |
| `VOICE_STT_MODEL` | `medium` | Whisper model size: `tiny` / `small` / `medium` / `large-v3` |
| `VOICE_TTS_VOICE` | `en_US-lessac-medium` | Piper voice ID for English |
| `VOICE_TTS_VOICE_EL` | `el_GR-rapunzelina-low` | Piper voice ID for Greek |
| `VOICE_MODELS_DIR` | `src/voice/piper_voices` | Directory containing `.onnx` + `.onnx.json` files |
| `AUDIT_RETAIN_AUDIO` | `false` | When `true`, raw WAV blobs are saved to `data/audit_audio/` |

The `data/audit_audio/` directory and the contents of `VOICE_MODELS_DIR` are both
gitignored. Neither should be committed.

---

## 8 · OTel span hierarchy

Voice calls appear as top-level spans within the enclosing `chat.turn` trace. They are
siblings of graph spans, not children — reflecting the transport-boundary placement.

```
chat.turn (trace root)
├── tool.speech_to_text          ← /audio/transcribe
│     (attributes: see § 2.4)
├── planner.plan
│   └── …
├── orchestrator.execute
│   └── …
└── tool.text_to_speech          ← /audio/synthesize
      (attributes: see § 3.5)
```

The `voice.correction` call is fire-and-forget from the frontend after the turn
completes; it does not appear within a `chat.turn` span. Its audit row is written
synchronously inside the endpoint before the HTTP response is returned.

---

## 9 · Setup

### 9.1 Voice model download (one-off)

```bash
# English TTS voice (~65 MB)
bash src/scripts/download_voice_models.sh

# Greek TTS voice (~61 MB)
bash src/scripts/download_voice_models.sh el_GR-rapunzelina-low
```

Models are placed in `src/voice/piper_voices/`. The STT model (faster-whisper) is
downloaded automatically on the first transcription call — no additional step required.

### 9.2 Enable voice

```bash
# .env (or environment)
VOICE_ENABLED=true
```

All `/audio/*` endpoints become active. The mic button appears in the frontend.

### 9.3 Enable audio audit retention

```bash
AUDIT_RETAIN_AUDIO=true
```

Ensure `data/audit_audio/` exists and is writable. The directory is created by the
bootstrap script if absent; it is listed in `.gitignore`.

---

## 10 · Smoke test

`src/scripts/smoke_test_voice.py` provides three test modes:

| Mode | Description |
|---|---|
| TTS self-test | Synthesizes a fixed sentence in EN and ΕΛ; plays the result locally |
| STT from file | Transcribes a supplied WAV file; prints transcript + detected language |
| Live mic (`--record`) | Captures audio from a selected input device; round-trips through STT |

The script includes an interactive language picker (EN / ΕΛ) and, in `--record` mode,
an interactive device picker listing available microphones.

```bash
python src/scripts/smoke_test_voice.py
python src/scripts/smoke_test_voice.py --record
```

---

## 11 · References

- STT implementation: [`src/agentic_backend/voice/stt.py`](../../src/agentic_backend/voice/stt.py)
- TTS implementation: [`src/agentic_backend/voice/tts.py`](../../src/agentic_backend/voice/tts.py)
- API routes: [`src/agentic_backend/api/routes/audio.py`](../../src/agentic_backend/api/routes/audio.py)
- Audit events: [`src/agentic_backend/audit/events.py`](../../src/agentic_backend/audit/events.py)
- Config: [`src/agentic_backend/config.py`](../../src/agentic_backend/config.py)
- Frontend API client: [`src/frontend/src/api/client.ts`](../../src/frontend/src/api/client.ts)
- Voice model download script: [`src/scripts/download_voice_models.sh`](../../src/scripts/download_voice_models.sh)
- Smoke test: [`src/scripts/smoke_test_voice.py`](../../src/scripts/smoke_test_voice.py)
- Agentic pipeline (graph internals): [agentic-pipeline.md](agentic-pipeline.md)
