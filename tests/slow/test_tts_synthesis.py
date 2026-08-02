"""Slow tests for server.tts — real Piper model required.

These tests load the full Piper voice (~30-60 MB) and run actual synthesis.
Run with: uv run pytest -m slow
Skip with: uv run pytest -m "not slow"
"""

import base64
import io
import wave

import pytest
from server.exceptions import TTSError

from server import tts


@pytest.mark.slow
async def test_synthesize_returns_valid_wav_base64(piper_voice_path: object) -> None:
    """synthesize must return (base64_wav, duration_ms) at 16 kHz mono int16.

    Piper voices emit at their native sample rate (22 050 Hz for medium
    voices); tts resamples the output to honor the audio contract, so the
    API response is ALWAYS 16 kHz regardless of the configured voice.
    """
    audio_b64, duration_ms = await tts.synthesize("Hola, soy Omnibot.")

    assert isinstance(audio_b64, str)
    assert duration_ms > 0

    wav_bytes = base64.b64decode(audio_b64)
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getframerate() == 16_000  # contract — never the Piper-native rate
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2  # int16
        assert wf.getnframes() > 0


@pytest.mark.slow
async def test_synthesize_empty_text_raises_value_error(piper_voice_path: object) -> None:
    with pytest.raises(ValueError, match="empty"):
        await tts.synthesize("")


@pytest.mark.slow
def test_preload_is_idempotent(piper_voice_path: object) -> None:
    """Calling preload twice must not fail or reload the model."""
    tts.preload()
    tts.preload()


@pytest.mark.slow
async def test_synthesis_is_longer_for_longer_text(piper_voice_path: object) -> None:
    """Longer input text must produce a longer audio buffer."""
    short_b64, _ = await tts.synthesize("Hola.")
    long_b64, _ = await tts.synthesize(
        "Hola, soy Omnibot dos mil y estoy probando mi sistema de voz en este momento."
    )
    short_frames = _nframes(short_b64)
    long_frames = _nframes(long_b64)
    assert long_frames > short_frames


def _nframes(audio_b64: str) -> int:
    wav_bytes = base64.b64decode(audio_b64)
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        return wf.getnframes()


@pytest.mark.slow
async def test_ttserror_wraps_underlying_failures(
    piper_voice_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If Piper itself raises, synthesize must surface a TTSError."""

    def _broken_sync(_text: str) -> tuple[bytes, int]:
        raise tts.TTSError("boom")

    monkeypatch.setattr(tts, "_synthesize_sync", _broken_sync)
    with pytest.raises(TTSError):
        await tts.synthesize("hola")
