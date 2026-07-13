"""Tool: text_to_speech — synthesize text to WAV bytes via Piper TTS."""
from __future__ import annotations

from agentic_backend.tools import AgentTool


def _run(text: str) -> bytes:
    """Synthesize text to a WAV audio clip.

    Args:
        text: Plain text to speak.

    Returns:
        Raw WAV bytes (RIFF/PCM).
    """
    from agentic_backend.voice import tts

    return tts.synthesize(text)


tool = AgentTool(
    name="text_to_speech",
    description=(
        "Synthesize plain text to WAV audio using a local Piper TTS model. "
        "Returns raw WAV bytes ready to stream as audio/wav."
    ),
    input_fields={
        "text": "plain text to synthesize",
    },
    run=_run,
)
