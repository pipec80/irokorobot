"""Tests for create_app()'s composed lifecycle and resource ownership (Plan 0039).

`server.main`'s module-level `app = create_app()` runs once, at import — like
every other test file in this suite, these tests share that one instance.
Where a test needs to observe *entering* the lifespan (not just the already-
running module singleton), it drives `lifespan(app)` directly, matching the
existing convention in `test_main_lifespan.py`.
"""

import logging
from unittest.mock import AsyncMock

import pytest
from server.exceptions import VisionError
from server.main import app, create_app, lifespan
from server.settings import Settings, settings
from server.voice.speaker_embedding import SpeakerBackendError

from server import main


@pytest.mark.unit
def test_create_app_does_not_construct_resources() -> None:
    """Building the FastAPI app object alone must not open any resource.

    Resource construction (the HTTP client, in particular) belongs to the
    lifespan, not to app assembly — constructing a second `FastAPI` instance
    (as this test does) must never open a second HTTP client.
    """
    fresh_app = create_app()

    assert not hasattr(fresh_app.state, "resources")


@pytest.mark.unit
def test_app_state_ready_is_false_before_lifespan() -> None:
    """A freshly assembled app has not started serving traffic yet."""
    fresh_app = create_app()

    assert fresh_app.state.ready is False


@pytest.mark.unit
async def test_lifespan_creates_and_closes_the_http_client_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One client is created on entry and closed on exit — never rebuilt."""
    monkeypatch.setattr(settings, "memory_enabled", False)
    monkeypatch.setattr(main.stt, "preload", lambda: None)
    monkeypatch.setattr(main.tts, "preload", lambda: None)

    async with lifespan(app):
        resources = app.state.resources
        assert app.state.ready is True
        assert resources.http_client.is_closed is False

    assert resources.http_client.is_closed is True
    assert app.state.ready is False


@pytest.mark.unit
async def test_create_app_accepts_an_injected_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`create_app(Settings(...))` drives lifespan behaviour without a global.

    The audit's named isolation case: build an app with memory disabled and
    confirm its lifespan never opens a database, while the module global
    `settings` (which has memory enabled by default) is untouched.
    """

    def _fail_open_db() -> None:
        pytest.fail("open_db must not run when the injected Settings disables memory")

    monkeypatch.setattr(main, "open_db", _fail_open_db)
    monkeypatch.setattr(main.stt, "preload", lambda: None)
    monkeypatch.setattr(main.tts, "preload", lambda: None)

    fresh_app = create_app(Settings(memory_enabled=False))
    assert fresh_app.state.settings.memory_enabled is False

    async with lifespan(fresh_app):
        assert fresh_app.state.ready is True


@pytest.mark.unit
async def test_a_startup_failure_after_client_creation_still_closes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A partial startup failure must not leak the already-open HTTP client."""
    monkeypatch.setattr(settings, "memory_enabled", False)
    monkeypatch.setattr(main.stt, "preload", lambda: None)

    def _fail_tts_preload() -> None:
        raise RuntimeError("simulated startup failure after the client opened")

    monkeypatch.setattr(main.tts, "preload", _fail_tts_preload)

    with pytest.raises(RuntimeError, match="simulated startup failure"):
        async with lifespan(app):
            pytest.fail("must not reach the yield after a startup failure")

    assert app.state.resources.http_client.is_closed is True
    assert app.state.ready is False


def _quiet_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "memory_enabled", False)
    monkeypatch.setattr(main.stt, "preload", lambda: None)
    monkeypatch.setattr(main.tts, "preload", lambda: None)


def _stub_warm_ups(monkeypatch: pytest.MonkeyPatch) -> tuple[AsyncMock, AsyncMock]:
    face_warm = AsyncMock()
    speaker_warm = AsyncMock()
    monkeypatch.setattr(main.faces, "warm_up", face_warm)
    monkeypatch.setattr(main.speaker_embedding, "warm_up", speaker_warm)
    return face_warm, speaker_warm


@pytest.mark.unit
@pytest.mark.parametrize("face_on", [True, False])
@pytest.mark.parametrize("speaker_on", [True, False])
async def test_lifespan_warms_only_the_models_whose_flags_are_on(
    face_on: bool, speaker_on: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review Focus 3: a flag-off model is never touched at startup."""
    _quiet_startup(monkeypatch)
    monkeypatch.setattr(settings, "face_authentication_enabled", face_on)
    monkeypatch.setattr(settings, "speaker_authentication_enabled", speaker_on)
    face_warm, speaker_warm = _stub_warm_ups(monkeypatch)

    async with lifespan(app):
        assert app.state.ready is True

    assert face_warm.await_count == int(face_on)
    assert speaker_warm.await_count == int(speaker_on)


@pytest.mark.unit
async def test_the_injected_settings_not_the_global_decide_what_is_warmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`create_app(Settings(...))` drives startup loading, as it drives the database."""
    _quiet_startup(monkeypatch)
    monkeypatch.setattr(settings, "face_authentication_enabled", False)
    monkeypatch.setattr(settings, "speaker_authentication_enabled", True)
    face_warm, speaker_warm = _stub_warm_ups(monkeypatch)
    fresh_app = create_app(
        Settings(
            memory_enabled=False,
            face_authentication_enabled=True,
            speaker_authentication_enabled=False,
        )
    )

    async with lifespan(fresh_app):
        pass

    face_warm.assert_awaited_once()
    speaker_warm.assert_not_awaited()


@pytest.mark.unit
async def test_a_failed_warm_up_does_not_stop_the_server_or_skip_the_other_model(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Review Focus 2: the model then loads lazily, and the log carries no raw message."""
    _quiet_startup(monkeypatch)
    monkeypatch.setattr(settings, "face_authentication_enabled", True)
    monkeypatch.setattr(settings, "speaker_authentication_enabled", True)
    face_warm, speaker_warm = _stub_warm_ups(monkeypatch)
    face_warm.side_effect = VisionError("secret-canary path")
    speaker_warm.side_effect = SpeakerBackendError("secret-canary path")

    with caplog.at_level(logging.WARNING):
        async with lifespan(app):
            assert app.state.ready is True

    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("Face model warm-up failed" in m and "VisionError" in m for m in messages)
    assert any("Speaker model warm-up failed" in m and "SpeakerBackendError" in m for m in messages)
    assert all("secret-canary" not in m for m in messages)
    assert all(r.exc_info is None for r in caplog.records if r.levelno == logging.WARNING)
    speaker_warm.assert_awaited_once()
