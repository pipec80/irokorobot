"""Shared pytest fixtures for the omnibotpipec test suite."""

from collections.abc import AsyncGenerator, Generator
import io
from pathlib import Path
import wave

from fastapi.testclient import TestClient
import httpx
import numpy as np
import pytest
from server.cognition.owner_authentication import owner_unlock_service
from server.main import app
from server.resources import AppResources
from server.settings import settings


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Return a synchronous FastAPI test client.

    Does NOT enter the lifespan context — Whisper/Piper stay unloaded.
    Memory is disabled to avoid DB dependency in pipeline-only tests.

    Plan 0039: routers now depend on `request.app.state.resources`
    (`ResourcesDep`), which the real lifespan sets — since that lifespan
    never runs here, this fixture assigns a lightweight `AppResources`
    itself (a real, unconnected `httpx.AsyncClient`) so endpoint tests keep
    working without paying for full startup.

    Function-scoped on purpose (Plan 0032): it mutates the `settings`
    singleton, so a session-scoped fixture would leave `memory_enabled`
    flipped for every later test and let one test's captured logs bleed into
    another's assertions. Constructing `TestClient` is cheap because the
    lifespan never runs.
    """
    original = settings.memory_enabled
    settings.memory_enabled = False  # type: ignore[misc]  # runtime override
    app.state.resources = AppResources(
        http_client=httpx.AsyncClient(), owner_unlock_service=owner_unlock_service
    )
    yield TestClient(app)  # type: ignore[misc]
    settings.memory_enabled = original  # type: ignore[misc]  # restore


@pytest.fixture
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Return a real, unconnected httpx.AsyncClient for injected-client tests.

    Plan 0039: production code no longer constructs its own
    `httpx.AsyncClient` — call sites take one as a parameter. Tests that
    exercise a mocked backend (`monkeypatch` on the function actually making
    the network call) need a real client instance to pass through, never one
    that itself talks to the network.
    """
    async with httpx.AsyncClient() as client:
        yield client


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
