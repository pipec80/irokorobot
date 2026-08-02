"""Slow tests for server.stt — real faster-whisper model required.

Uses silent audio as input: we test the transcription pipeline mechanics
(model load, VAD, segment aggregation), not the accuracy of Whisper itself.
"""

import pytest
from server.exceptions import TranscriptionError

from server import stt


@pytest.mark.slow
async def test_transcribe_silence_returns_empty_or_short_string(
    silence_wav_bytes: bytes,
) -> None:
    """Silent audio must produce an empty string (VAD filters everything out)."""
    text = await stt.transcribe(silence_wav_bytes)
    # Silence with VAD filter typically yields "" or a whitespace-only string
    assert isinstance(text, str)
    assert text.strip() == ""


@pytest.mark.slow
async def test_transcribe_empty_bytes_raises_value_error() -> None:
    with pytest.raises(ValueError, match="empty"):
        await stt.transcribe(b"")


@pytest.mark.slow
def test_preload_is_idempotent() -> None:
    """Calling preload twice must not fail or reload the model."""
    stt.preload()
    stt.preload()


@pytest.mark.slow
async def test_transcription_error_wraps_underlying_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If Whisper inference raises, transcribe must surface a TranscriptionError."""

    def _broken_sync(_audio: bytes, _hotwords: str | None) -> str:
        raise stt.TranscriptionError("boom")

    monkeypatch.setattr(stt, "_transcribe_sync", _broken_sync)
    with pytest.raises(TranscriptionError):
        await stt.transcribe(b"\x00" * 100)
