"""Unit test for the process-local one-worker invariant at server startup."""

from unittest.mock import AsyncMock

import pytest
from server.main import lifespan
from server.settings import settings

from server import main


@pytest.mark.unit
async def test_lifespan_refuses_to_start_with_more_than_one_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Owner-unlock grants are process-local — multi-worker must fail loudly.

    Asserted before any model preload so this test never touches Whisper/Piper.
    """
    monkeypatch.setattr(settings, "uvicorn_workers", 2)
    monkeypatch.setattr(main.stt, "preload", lambda: pytest.fail("must not preload"))
    monkeypatch.setattr(main.tts, "preload", lambda: pytest.fail("must not preload"))

    with pytest.raises(RuntimeError, match="UVICORN_WORKERS must be 1"):
        async with lifespan(main.app):
            pass


@pytest.mark.unit
async def test_lifespan_accepts_exactly_one_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    """The documented single-worker configuration must start normally."""
    monkeypatch.setattr(settings, "uvicorn_workers", 1)
    monkeypatch.setattr(settings, "memory_enabled", False)
    monkeypatch.setattr(main.stt, "preload", lambda: None)
    monkeypatch.setattr(main.tts, "preload", lambda: None)

    async with lifespan(main.app):
        pass


@pytest.mark.unit
@pytest.mark.parametrize("reachable", [True, False])
async def test_lifespan_probes_ollama_once_and_an_unreachable_one_never_stops_the_start(
    reachable: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan 0064, D-6: the probe only warns; the server is ready either way."""
    probe = AsyncMock(return_value=reachable)
    monkeypatch.setattr(settings, "uvicorn_workers", 1)
    monkeypatch.setattr(settings, "memory_enabled", False)
    monkeypatch.setattr(main.stt, "preload", lambda: None)
    monkeypatch.setattr(main.tts, "preload", lambda: None)
    monkeypatch.setattr(main, "probe_ollama", probe)

    async with lifespan(main.app):
        assert main.app.state.ready is True
        client = main.app.state.resources.http_client

    probe.assert_awaited_once_with(client)
