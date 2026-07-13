#!/usr/bin/env python3
"""Phase 13 voice smoke-test — faster-whisper STT and piper-tts TTS.

Run from the repo root with the venv active (cd src && source .venv/bin/activate).

LANGUAGE SELECTION
    An interactive EN / EL menu is shown at startup unless --lang is passed.

    python src/scripts/smoke_test_voice.py                     # interactive menu, then TTS
    python src/scripts/smoke_test_voice.py --lang el           # Greek, skip menu

MODES
    # TTS only — synthesize a sample phrase and play it back:
    python src/scripts/smoke_test_voice.py [--lang en|el]

    # Full loop — TTS → play WAV → STT (verifies round-trip quality):
    python src/scripts/smoke_test_voice.py --self-test [--lang en|el]

    # Mic recording — record N seconds, transcribe, speak transcript back:
    python src/scripts/smoke_test_voice.py --record [SECONDS] [--lang en|el]
    python src/scripts/smoke_test_voice.py --record 5 --lang el

    # Specific DirectShow device (device list is printed at startup):
    python src/scripts/smoke_test_voice.py --record 5 --device 1

    # Transcribe an existing audio file:
    python src/scripts/smoke_test_voice.py path/to/audio.wav [--lang en|el]

PASS CRITERIA
    STT: non-empty transcript, latency < 10 s on CPU
    TTS: WAV > 10 KB with valid RIFF header, latency < 5 s

PLATFORM NOTES
    Audio playback : Windows PowerShell SoundPlayer (WSL2-compatible, no extra packages)
    Mic recording  : ffmpeg.exe (DirectShow) — install with: winget install Gyan.FFmpeg

ENV OVERRIDES (src/.env or process environment)
    WHISPER_MODEL=medium     # tiny | small | medium | large-v3
    VOICE_LANGUAGE=en        # ISO-639-1 hint; --lang takes precedence when both set
"""
from __future__ import annotations

import glob
import io
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import wave

_PIPER_DIR = pathlib.Path("src/voice/piper_voices")

# Reads from environment so src/.env overrides work without code changes
_WHISPER_MODEL: str = os.environ.get("WHISPER_MODEL", "medium")

# ── Language configuration ────────────────────────────────────────────────────

_LANG_CONFIG: dict[str, dict[str, str]] = {
    "en": {
        "label":      "English",
        "voice_id":   "en_US-lessac-medium",
        "tts_text":   "Insurance claim filed. Awaiting adjuster review.",
        "tts_bytes_text": "Claim approved. Payment within five business days.",
    },
    "el": {
        "label":      "Ελληνικά (Greek)",
        "voice_id":   "el_GR-rapunzelina-low",
        "tts_text":   "Η ασφαλιστική αξίωση κατατέθηκε. Αναμένεται αξιολόγηση.",
        "tts_bytes_text": "Η αξίωση εγκρίθηκε. Η πληρωμή θα γίνει εντός πέντε εργάσιμων ημερών.",
    },
}


def _select_language(cli_lang: str | None) -> str:
    """Return the ISO-639-1 language code to use for this run.

    If cli_lang is provided (via --lang), validate and return it directly.
    Otherwise show an interactive menu so the user picks at startup.
    """
    if cli_lang is not None:
        if cli_lang not in _LANG_CONFIG:
            print(f"ERROR: unsupported --lang {cli_lang!r}. Choose from: {list(_LANG_CONFIG)}")
            sys.exit(1)
        return cli_lang

    # Interactive prompt
    print("╔══════════════════════════════════════╗")
    print("║  Voice Smoke-Test — Language Select  ║")
    print("╠══════════════════════════════════════╣")
    for i, (code, cfg) in enumerate(_LANG_CONFIG.items(), 1):
        print(f"║  [{i}] {cfg['label']:<32} ║")
    print("╚══════════════════════════════════════╝")

    keys = list(_LANG_CONFIG)
    while True:
        raw = input(f"Select [1-{len(keys)}] (default 1): ").strip()
        if raw == "":
            return keys[0]
        if raw.isdigit() and 1 <= int(raw) <= len(keys):
            return keys[int(raw) - 1]
        if raw in keys:
            return raw
        print(f"  Invalid choice — enter a number between 1 and {len(keys)}.")

# ffmpeg.exe search order (Windows paths, accessible from WSL2 /mnt/c/...)
_FFMPEG_GLOBS = [
    "/mnt/c/Users/*/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg*/**/ffmpeg.exe",
    "/mnt/c/Program Files/ffmpeg/bin/ffmpeg.exe",
    "/mnt/c/ffmpeg/bin/ffmpeg.exe",
]


# ── Audio helpers (WSL2 → Windows) ───────────────────────────────────────────

def _wsl_to_win(path: pathlib.Path) -> str:
    """Convert a WSL path to a Windows path string for PowerShell."""
    result = subprocess.run(
        ["wslpath", "-w", str(path)], capture_output=True, text=True
    )
    return result.stdout.strip()


def _win_temp_wav() -> tuple[str, pathlib.Path]:
    """Return (win_path_str, wsl_path) for a fresh WAV in Windows TEMP."""
    win_temp = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", "$env:TEMP"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    win_wav = win_temp + r"\irp_voice_rec.wav"
    wsl_wav = pathlib.Path(
        subprocess.run(["wslpath", "-u", win_wav], capture_output=True, text=True).stdout.strip()
    )
    wsl_wav.unlink(missing_ok=True)
    return win_wav, wsl_wav


def _find_ffmpeg() -> pathlib.Path | None:
    """Locate ffmpeg.exe on the Windows side (visible via /mnt/c/...)."""
    for pattern in _FFMPEG_GLOBS:
        matches = glob.glob(pattern, recursive=True)
        if matches:
            return pathlib.Path(matches[0])
    return None


def _list_dshow_audio_devices(ffmpeg: pathlib.Path) -> list[str]:
    """Return DirectShow audio input device names."""
    result = subprocess.run(
        [str(ffmpeg), "-f", "dshow", "-list_devices", "true", "-i", "dummy"],
        capture_output=True, text=True, check=False,
    )
    combined = result.stdout + result.stderr
    return [
        m.group(1)
        for line in combined.splitlines()
        if "(audio)" in line
        for m in [re.search(r'"([^"]+)"', line)]
        if m
    ]


def _select_device(cli_device: int | None) -> int:
    """List available DirectShow audio devices and let the user pick one.

    If cli_device is already set (via --device N), validate it and return
    immediately without prompting.
    """
    ffmpeg = _find_ffmpeg()
    if ffmpeg is None:
        raise RuntimeError(
            "ffmpeg.exe not found. Install with: winget install Gyan.FFmpeg"
        )
    devices = _list_dshow_audio_devices(ffmpeg)
    if not devices:
        raise RuntimeError(
            "No DirectShow audio input devices found. "
            "Check that a microphone is connected and enabled in Windows."
        )

    if cli_device is not None:
        if cli_device >= len(devices):
            raise RuntimeError(
                f"--device {cli_device} out of range (only {len(devices)} device(s) found)."
            )
        return cli_device

    print("╔══════════════════════════════════════════════════╗")
    print("║  Select Audio Input Device                       ║")
    print("╠══════════════════════════════════════════════════╣")
    for idx, name in enumerate(devices):
        truncated = name[:44] if len(name) > 44 else name
        print(f"║  [{idx}] {truncated:<44} ║")
    print("╚══════════════════════════════════════════════════╝")

    while True:
        raw = input(f"Select [0-{len(devices) - 1}] (default 0): ").strip()
        if raw == "":
            return 0
        if raw.isdigit() and 0 <= int(raw) < len(devices):
            return int(raw)
        print(f"  Invalid choice — enter a number between 0 and {len(devices) - 1}.")


def play_wav(wav_path: pathlib.Path) -> None:
    """Play a WAV file via Windows PowerShell SoundPlayer (works in WSL2)."""
    win_path = _wsl_to_win(wav_path)
    print("  Playing via Windows SoundPlayer…")
    ps_cmd = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        f"$p = New-Object System.Media.SoundPlayer '{win_path}'; "
        "$p.PlaySync()"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
        check=False,
        capture_output=True,
    )


def _check_audio_level(wsl_wav: pathlib.Path) -> None:
    """Print peak amplitude so the caller can spot a silent/too-quiet recording."""
    import array as array_mod
    import math

    with wave.open(str(wsl_wav), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
        sample_width = wf.getsampwidth()

    if sample_width == 2:
        samples = array_mod.array("h", raw)
        peak = max(abs(s) for s in samples) if samples else 0
        rms = math.sqrt(sum(s * s for s in samples) / len(samples)) if samples else 0
        db = 20 * math.log10(rms / 32768) if rms > 0 else -96
        print(f"  audio level : peak={peak}  rms={rms:.0f}  ({db:.1f} dBFS)")
        if db < -40:
            print(
                "  WARNING: audio level is very low — mic may not be the right device. "
                "Try --device 1 to switch to the next device in the list."
            )


def record_mic(duration_s: int = 5, device_index: int = 0) -> pathlib.Path:
    """Record from a Windows DirectShow audio device for duration_s seconds.

    Uses ffmpeg.exe — writes to Windows TEMP so WSL2 can read it back via
    /mnt/c/... without MCI's UNC-path limitation.  Captures at 16 kHz mono
    (Whisper's native rate) to avoid resampling artefacts.

    Args:
        duration_s: Recording length in seconds.
        device_index: Index into the DirectShow device list (0 = first device).
    """
    ffmpeg = _find_ffmpeg()
    if ffmpeg is None:
        raise RuntimeError(
            "ffmpeg.exe not found. Install ffmpeg on Windows "
            "(winget install Gyan.FFmpeg) and retry."
        )

    devices = _list_dshow_audio_devices(ffmpeg)
    if not devices:
        raise RuntimeError(
            "No DirectShow audio input devices found. "
            "Check that a microphone is connected and enabled in Windows."
        )
    if device_index >= len(devices):
        raise RuntimeError(
            f"Device {device_index} out of range (only {len(devices)} device(s) found)."
        )
    mic_name = devices[device_index]
    win_wav, wsl_wav = _win_temp_wav()

    print(f"  Recording {duration_s}s via ffmpeg DirectShow: {mic_name!r}")
    result = subprocess.run(
        [
            str(ffmpeg), "-y",
            "-f", "dshow", "-i", f"audio={mic_name}",
            # loudnorm brings quiet mic captures to -16 LUFS broadcast standard,
            # eliminating low-signal hallucinations ("Hello.", Georgian script, etc.)
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            # 16 kHz mono = Whisper's native rate; avoids resampling hallucinations
            "-ar", "16000", "-ac", "1",
            "-t", str(duration_s),
            win_wav,
        ],
        capture_output=True, text=True, check=False,
    )

    if not wsl_wav.exists() or wsl_wav.stat().st_size < 1000:
        tail = "\n".join((result.stdout + result.stderr).splitlines()[-8:])
        raise RuntimeError(
            f"Recording failed (ffmpeg exit={result.returncode}).\n{tail}"
        )
    print(f"  Recorded: {wsl_wav.stat().st_size:,} bytes → {wsl_wav}")
    _check_audio_level(wsl_wav)
    return wsl_wav


# ── Piper TTS ─────────────────────────────────────────────────────────────────

def _load_piper(language: str = "en") -> object | None:
    try:
        from piper.voice import PiperVoice
    except ImportError:
        print("  ERROR: piper-tts not installed — pip install piper-tts")
        return None
    voice_id = _LANG_CONFIG[language]["voice_id"]
    onnx = _PIPER_DIR / f"{voice_id}.onnx"
    if not onnx.exists():
        print(f"  ERROR: model not found at {onnx}")
        print(f"  Run:  bash src/scripts/download_voice_models.sh {voice_id}")
        return None
    print(f"  Loading voice ({voice_id})…")
    t0 = time.perf_counter()
    voice = PiperVoice.load(str(onnx))
    print(
        f"  voice loaded in {time.perf_counter() - t0:.1f}s"
        f"  (sample_rate: {voice.config.sample_rate})"
    )
    return voice


def synthesize_to_file(
    voice: object, text: str, out_path: pathlib.Path
) -> float:
    """Synthesize text to a WAV file; return latency in seconds."""
    t0 = time.perf_counter()
    with wave.open(str(out_path), "wb") as wav_fh:
        voice.synthesize_wav(text, wav_fh)  # type: ignore[attr-defined]
    return time.perf_counter() - t0


def synthesize_to_bytes(voice: object, text: str) -> bytes:
    """Synthesize text and return raw WAV bytes (mirrors /audio/synthesize)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_fh:
        voice.synthesize_wav(text, wav_fh)  # type: ignore[attr-defined]
    return buf.getvalue()


# ── Test functions ────────────────────────────────────────────────────────────

def test_tts(
    text: str | None = None,
    autoplay: bool = True,
    language: str = "en",
) -> tuple[bool, pathlib.Path | None]:
    print("\n=== TTS — piper-tts (file output) ===")
    voice = _load_piper(language)
    if voice is None:
        return False, None

    if text is None:
        text = _LANG_CONFIG[language]["tts_text"]
    out_path = pathlib.Path(tempfile.mktemp(suffix=".wav"))
    print(f"  Synthesizing: {text!r}")
    elapsed = synthesize_to_file(voice, text, out_path)
    size = out_path.stat().st_size

    print(f"  latency  : {elapsed:.2f}s")
    print(f"  output   : {out_path}  ({size:,} bytes)")
    ok = size > 10_000
    print(f"  result: {'PASS ✓' if ok else 'FAIL — WAV too small (< 10 KB)'}")
    if ok and autoplay:
        play_wav(out_path)
    return ok, out_path if ok else None


def test_tts_bytes(
    text: str | None = None,
    language: str = "en",
) -> bool:
    print("\n=== TTS bytes variant (mirrors POST /audio/synthesize) ===")
    voice = _load_piper(language)
    if voice is None:
        return False

    if text is None:
        text = _LANG_CONFIG[language]["tts_bytes_text"]
    wav_bytes = synthesize_to_bytes(voice, text)
    ok = len(wav_bytes) > 10_000 and wav_bytes[:4] == b"RIFF"
    print(f"  bytes length : {len(wav_bytes):,}")
    print(f"  RIFF header  : {wav_bytes[:4]!r}")
    print(f"  result: {'PASS ✓' if ok else 'FAIL'}")
    return ok


def test_stt(audio_path: str, language: str | None = None) -> bool:
    print(f"\n=== STT — faster-whisper  [{audio_path}] ===")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("  ERROR: faster-whisper not installed — pip install faster-whisper")
        return False

    print(f"  Loading model {_WHISPER_MODEL!r} (int8, CPU)…")
    print("  First run may download model weights — subsequent runs are instant.")
    t0 = time.perf_counter()
    model = WhisperModel(_WHISPER_MODEL, device="cpu", compute_type="int8")
    print(f"  model loaded in {time.perf_counter() - t0:.1f}s")

    if language:
        print(f"  language hint: {language!r}")
    print("  Transcribing…")
    t1 = time.perf_counter()
    # vad_filter suppresses hallucinated text on silence (e.g. Georgian script artefacts)
    segments, info = model.transcribe(audio_path, language=language, vad_filter=True)
    transcript = " ".join(s.text.strip() for s in segments)
    elapsed = time.perf_counter() - t1

    print(f"  language  : {info.language}")
    print(f"  duration  : {info.duration:.1f}s")
    print(f"  latency   : {elapsed:.2f}s")
    print(f"  transcript: {transcript!r}")

    if not transcript.strip():
        print("  result: PASS ✓ (silence detected — no speech)")
        return True
    print("  result: PASS ✓")
    return True


# ── main ─────────────────────────────────────────────────────────────────────

def _usage() -> None:
    print(__doc__)


if __name__ == "__main__":
    args = sys.argv[1:]

    # ── Parse --lang and --device before the mode dispatch ───────────────────
    cli_lang: str | None = None
    if "--lang" in args:
        idx = args.index("--lang")
        if idx + 1 < len(args):
            cli_lang = args[idx + 1]
            args = args[:idx] + args[idx + 2:]
        else:
            print("ERROR: --lang requires a value (en or el)")
            sys.exit(1)

    # Language selection: interactive menu if not given on CLI
    lang = _select_language(cli_lang)
    cfg = _LANG_CONFIG[lang]
    print(f"\nLanguage: {cfg['label']}  |  voice: {cfg['voice_id']}  |  STT hint: {lang}\n")

    results: list[bool] = []

    if not args:
        # TTS only with playback
        print("TTS-only mode (add --self-test or --record N for STT)\n")
        ok, _ = test_tts(language=lang)
        results.append(ok)
        results.append(test_tts_bytes(language=lang))

    elif args[0] == "--self-test":
        # TTS → WAV → play → STT
        print("Self-test: TTS → play → STT\n")
        ok_tts, wav_path = test_tts(language=lang)
        results.append(ok_tts)
        results.append(test_tts_bytes(language=lang))
        if wav_path:
            results.append(test_stt(str(wav_path), language=lang))

    elif args[0] == "--record":
        # --record [SECONDS] [--device N]
        remaining = args[1:]
        duration = int(remaining[0]) if remaining and remaining[0].lstrip("-").isdigit() else 5
        cli_device: int | None = None
        if "--device" in remaining:
            di = remaining.index("--device")
            if di + 1 < len(remaining):
                cli_device = int(remaining[di + 1])
        try:
            device_index = _select_device(cli_device)
        except RuntimeError as exc:
            print(f"  ERROR: {exc}")
            sys.exit(1)
        print(f"\nMic-record mode: {duration}s → STT + TTS playback of transcript\n")
        try:
            wav_path = record_mic(duration, device_index=device_index)
        except RuntimeError as exc:
            print(f"  ERROR: {exc}")
            sys.exit(1)
        stt_ok = test_stt(str(wav_path), language=lang)
        results.append(stt_ok)
        results.append(test_tts_bytes(language=lang))
        if stt_ok:
            from faster_whisper import WhisperModel
            model = WhisperModel(_WHISPER_MODEL, device="cpu", compute_type="int8")
            segs, _ = model.transcribe(str(wav_path), language=lang, vad_filter=True)
            transcript = " ".join(s.text.strip() for s in segs)
            if transcript.strip():
                print(f"\n  Speaking back: {transcript!r}")
                ok_reply, _ = test_tts(text=transcript, autoplay=True, language=lang)
                results.append(ok_reply)
            else:
                print("\n  (silence — nothing to speak back)")

    elif args[0] in ("-h", "--help"):
        _usage()
        sys.exit(0)

    else:
        # Explicit audio file
        results.append(test_stt(args[0], language=lang))
        ok, _ = test_tts(language=lang)
        results.append(ok)
        results.append(test_tts_bytes(language=lang))

    verdict = "ALL PASS ✓" if all(results) else "SOME FAILURES — see above"
    print(f"\n{'=' * 50}")
    print(f"Overall: {verdict}")
