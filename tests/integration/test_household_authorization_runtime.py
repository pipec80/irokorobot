"""Integration tests for the P0.5-A public authorization boundary."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient
import pytest
from server.main import app
from server.routers import chat
from server.settings import settings
from server.text_turn import TextTurnResult

from server import db


@asynccontextmanager
async def _client() -> AsyncIterator[AsyncClient]:
    """Yield an application client without starting model lifespans."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def authorization_runtime_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[misc]
    """Open a temporary database for audit persistence without real models."""
    db_path = tmp_path / "authorization-runtime.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield
    await db.close_db()
    db._conn = None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_public_protected_chat_is_audited_without_legacy_generation(
    authorization_runtime_db: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown public chat is denied and audited before legacy memory can run."""
    legacy_turn = AsyncMock(return_value=TextTurnResult("legacy", "joy", 42, False))
    monkeypatch.setattr(chat, "process_text_turn", legacy_turn)

    async with _client() as client:
        response = await client.post(
            "/chat",
            json={"message": "¿Cómo se llaman mis hijos?", "conversation_id": "web-primary"},
        )

    assert response.status_code == 200
    assert response.json()["response"] == (
        "No puedo acceder a información familiar privada sin una autorización comprobada."
    )
    legacy_turn.assert_not_awaited()

    cursor = await db.get_conn().execute(
        "SELECT actor_entity_id, action, decision, policy_id, data_categories "
        "FROM authorization_audit_events"
    )
    rows = await cursor.fetchall()
    await cursor.close()
    assert rows == [
        (
            None,
            "read_household_data",
            "denied",
            "p0.5.identity-unresolved",
            "household,private",
        )
    ]
