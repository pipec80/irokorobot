"""Unit test for the process-local one-worker invariant at server startup."""

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
