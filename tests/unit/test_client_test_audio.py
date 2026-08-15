"""Unit tests for the no-microphone client QA audio path."""

import io
from pathlib import Path
import wave

import numpy as np
import pytest
from server.exceptions import AudioContractError

from scripts import client_test


class _FakeVoice:
    """Piper stand-in that writes a controlled mono int16 WAV."""

    def __init__(self, sample_rate: int) -> None:
        """Create one fake voice with the requested output rate."""
        self._sample_rate = sample_rate

    def synthesize_wav(
        self,
        _text: str,
        output: wave.Wave_write,
        *,
        syn_config: object,
    ) -> None:
        """Write a short valid PCM WAV without loading a real model."""
        del syn_config
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(self._sample_rate)
        output.writeframes(np.zeros(self._sample_rate // 10, dtype=np.int16).tobytes())


def _read_header(wav_bytes: bytes) -> tuple[int, int, int]:
    """Return rate, channel count, and sample width from one WAV payload."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        return wav.getframerate(), wav.getnchannels(), wav.getsampwidth()


def _voice_path(tmp_path: Path) -> str:
    """Create an existing stand-in model path for script validation."""
    path = tmp_path / "voice.onnx"
    path.touch()
    return str(path)


@pytest.mark.unit
def test_synthesize_locally_normalizes_native_piper_rate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The text QA path must convert Piper-native 22 050 Hz before HTTP."""
    monkeypatch.setattr(client_test.PiperVoice, "load", lambda _path: _FakeVoice(22_050))

    wav_bytes = client_test.synthesize_locally("Hola Iroko", _voice_path(tmp_path))

    assert _read_header(wav_bytes) == (16_000, 1, 2)


@pytest.mark.unit
def test_synthesize_locally_keeps_contract_compliant_voice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Piper voice already at 16 kHz must remain contract-compliant."""
    monkeypatch.setattr(client_test.PiperVoice, "load", lambda _path: _FakeVoice(16_000))

    wav_bytes = client_test.synthesize_locally("Hola Iroko", _voice_path(tmp_path))

    assert _read_header(wav_bytes) == (16_000, 1, 2)


@pytest.mark.unit
def test_synthesize_locally_raises_before_http_when_final_validation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The script must report a local contract failure before any server call."""
    monkeypatch.setattr(client_test.PiperVoice, "load", lambda _path: _FakeVoice(16_000))

    def reject(_wav_bytes: bytes) -> None:
        """Simulate a final local contract rejection."""
        raise AudioContractError("test rejection")

    monkeypatch.setattr(client_test, "validate_wav_contract", reject, raising=False)

    with pytest.raises(AudioContractError, match="test rejection"):
        client_test.synthesize_locally("Hola Iroko", _voice_path(tmp_path))
