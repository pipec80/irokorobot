"""Tests for create_app()'s composed lifecycle and resource ownership (Plan 0039).

`server.main`'s module-level `app = create_app()` runs once, at import — like
every other test file in this suite, these tests share that one instance.
Where a test needs to observe *entering* the lifespan (not just the already-
running module singleton), it drives `lifespan(app)` directly, matching the
existing convention in `test_main_lifespan.py`.
"""

import pytest
from server.main import app, create_app, lifespan
from server.settings import settings

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

    assert getattr(fresh_app.state, "ready", False) is False


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
