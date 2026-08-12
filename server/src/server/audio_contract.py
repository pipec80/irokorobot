"""Audio contract enforcement for HTTP endpoints.

Validates that uploaded audio matches the mandatory contract — WAV, 16 000 Hz,
mono, int16 (see .Codex/rules/audio-contract.md) — before it reaches STT.
"""

import io
import wave

from server.exceptions import AudioContractError

_EXPECTED_FRAMERATE = 16_000
_EXPECTED_CHANNELS = 1
_EXPECTED_SAMPWIDTH = 2


def validate_wav_contract(audio_bytes: bytes) -> None:
    """Validate that audio bytes are a WAV file matching the mandatory contract.

    Args:
        audio_bytes: Raw uploaded bytes, expected to be WAV 16kHz mono int16.

    Raises:
        AudioContractError: If the bytes are not a valid WAV container, or the
            container is not 16kHz/mono/int16, or it has no frames.
    """
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            nframes = wf.getnframes()
    except (wave.Error, EOFError) as exc:
        raise AudioContractError("Audio is not a valid WAV file") from exc

    if channels != _EXPECTED_CHANNELS:
        raise AudioContractError(f"Audio must be mono (1 channel) — got {channels} channel(s)")
    if sampwidth != _EXPECTED_SAMPWIDTH:
        raise AudioContractError(f"Audio must be 16-bit int16 — got {sampwidth * 8}-bit samples")
    if framerate != _EXPECTED_FRAMERATE:
        raise AudioContractError(f"Audio must be {_EXPECTED_FRAMERATE} Hz — got {framerate} Hz")
    if nframes <= 0:
        raise AudioContractError("Audio contains no frames")
