"""Shared pytest fixtures for the omnibotpipec test suite."""

from collections.abc import Generator
import io
from pathlib import Path
import wave

from fastapi.testclient import TestClient
import numpy as np
import pytest
from server.main import app
from server.settings import settings


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    """Return a synchronous FastAPI test client.

    Does NOT enter the lifespan context — Whisper/Piper stay unloaded.
    Memory is disabled to avoid DB dependency in pipeline-only tests.
    """
    original = settings.memory_enabled
    settings.memory_enabled = False  # type: ignore[misc]  # runtime override
    yield TestClient(app)  # type: ignore[misc]
    settings.memory_enabled = original  # type: ignore[misc]  # restore


@pytest.fixture(scope="session")
def silence_wav_bytes() -> bytes:
    """Return a 1-second silent WAV at 16kHz mono int16.

    Useful for tests that exercise the audio-ingest path without needing
    real speech content.
    """
    samples = np.zeros(16_000, dtype=np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16_000)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()


@pytest.fixture(scope="session")
def piper_voice_path() -> Path:
    """Return the path to the default Piper voice model (es_MX-ald-medium).

    Skips the test if the model is not downloaded on this machine.
    """
    path = Path("models") / "piper" / "es_MX-ald-medium.onnx"
    if not path.exists():
        pytest.skip(f"Piper voice model not found at {path}")
    return path
