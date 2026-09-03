"""Integration tests for GET /ready (Plan 0040 Task 4).

`/ready` is distinct from `/health`: liveness (`/health`) only proves the
process is up, while readiness proves the lifespan finished successfully
AND every mandatory local resource (STT model, TTS voice, and — only when
`MEMORY_ENABLED` — the SQLite connection) is currently loaded/open. Every
probe here is a side-effect-free state check (`is_loaded()`/`is_open()`) —
never a real model load or an Ollama/VLM call, and never anything gated on
optional vision.
"""

from collections.abc import Generator

from fastapi.testclient import TestClient
import pytest
from server.main import app
from server.settings import settings

from server import db, stt, tts


@pytest.fixture(autouse=True)
def _reset_ready_state() -> Generator[None, None, None]:
    """Leave `app.state.ready` exactly as found — no lifespan runs here."""
    original = getattr(app.state, "ready", False)
    yield
    app.state.ready = original  # type: ignore[misc]  # test-only state reset


@pytest.mark.api
def test_ready_returns_503_before_lifespan_completes(client: TestClient) -> None:
    """Never entering the lifespan (this fixture's normal case) must read as not ready."""
    app.state.ready = False  # type: ignore[misc]  # simulate pre-lifespan state
    response = client.get("/ready")
    assert response.status_code == 503


@pytest.mark.api
def test_ready_returns_503_when_stt_model_is_not_loaded(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.state.ready = True  # type: ignore[misc]
    monkeypatch.setattr(stt, "is_loaded", lambda: False)
    monkeypatch.setattr(tts, "is_loaded", lambda: True)
    monkeypatch.setattr(settings, "memory_enabled", False)

    response = client.get("/ready")

    assert response.status_code == 503


@pytest.mark.api
def test_ready_returns_503_when_tts_voice_is_not_loaded(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.state.ready = True  # type: ignore[misc]
    monkeypatch.setattr(stt, "is_loaded", lambda: True)
    monkeypatch.setattr(tts, "is_loaded", lambda: False)
    monkeypatch.setattr(settings, "memory_enabled", False)

    response = client.get("/ready")

    assert response.status_code == 503


@pytest.mark.api
def test_ready_returns_503_when_memory_enabled_but_db_is_not_open(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.state.ready = True  # type: ignore[misc]
    monkeypatch.setattr(stt, "is_loaded", lambda: True)
    monkeypatch.setattr(tts, "is_loaded", lambda: True)
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(db, "is_open", lambda: False)

    response = client.get("/ready")

    assert response.status_code == 503


@pytest.mark.api
def test_ready_returns_200_when_lifespan_succeeded_and_every_probe_passes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.state.ready = True  # type: ignore[misc]
    monkeypatch.setattr(stt, "is_loaded", lambda: True)
    monkeypatch.setattr(tts, "is_loaded", lambda: True)
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(db, "is_open", lambda: True)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


@pytest.mark.api
def test_ready_does_not_check_the_db_when_memory_is_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MEMORY_ENABLED=false never opens a DB connection — /ready must not demand one."""
    app.state.ready = True  # type: ignore[misc]
    monkeypatch.setattr(stt, "is_loaded", lambda: True)
    monkeypatch.setattr(tts, "is_loaded", lambda: True)
    monkeypatch.setattr(settings, "memory_enabled", False)
    monkeypatch.setattr(db, "is_open", lambda: False)

    response = client.get("/ready")

    assert response.status_code == 200


@pytest.mark.api
@pytest.mark.parametrize("vision_enabled", [True, False])
def test_ready_is_unaffected_by_vision_enabled_state(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, vision_enabled: bool
) -> None:
    """Disabled (or enabled) optional vision must never make the server unready."""
    app.state.ready = True  # type: ignore[misc]
    monkeypatch.setattr(stt, "is_loaded", lambda: True)
    monkeypatch.setattr(tts, "is_loaded", lambda: True)
    monkeypatch.setattr(settings, "memory_enabled", False)
    monkeypatch.setattr(settings, "vision_enabled", vision_enabled)

    response = client.get("/ready")

    assert response.status_code == 200
