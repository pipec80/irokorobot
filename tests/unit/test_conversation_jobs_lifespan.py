"""The lifespan starts the conversation job only with the record switch on (Plan 0076 Task 10)."""

from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from server.main import create_app, lifespan
from server.settings import Settings

from server import main

pytestmark = pytest.mark.unit


@pytest.fixture
def stubbed(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Stub every start-up side effect; return the conversation job's start seam."""
    monkeypatch.setattr(main.stt, "preload", lambda: None)
    monkeypatch.setattr(main.tts, "preload", lambda: None)
    monkeypatch.setattr(main, "open_db", AsyncMock())
    monkeypatch.setattr(main, "close_db", AsyncMock())
    monkeypatch.setattr(main, "run_migrations", AsyncMock())
    monkeypatch.setattr(main.candidates, "reset_for_startup", AsyncMock())
    monkeypatch.setattr(main.retention, "start_background_job", Mock())
    monkeypatch.setattr(main.retention, "stop_background_job", AsyncMock())
    start = Mock()
    monkeypatch.setattr(main.conversation_jobs, "start_background_job", start)
    monkeypatch.setattr(main.conversation_jobs, "stop_background_job", AsyncMock())
    return start


@pytest.mark.parametrize("record_on", [True, False])
async def test_the_lifespan_starts_the_job_only_with_the_record_switch_on(
    stubbed: Mock, tmp_path: Path, record_on: bool
) -> None:
    app = create_app(
        Settings(
            memory_enabled=True,
            conversation_record_enabled=record_on,
            brain_db_path=tmp_path / "lifespan.db",
        )
    )

    async with lifespan(app):
        pass

    assert stubbed.called is record_on
