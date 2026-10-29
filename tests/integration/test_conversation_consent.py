"""The conversation storage consent: grant, revoke-and-delete, the notice (Plan 0076 Task 5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from server.memory import conversation_record as record
from server.memory.conversation_consent import (
    CONVERSATION_NOTICE_VERSION,
    grant_conversation_consent,
    has_active_conversation_consent,
    load_conversation_notice,
    revoke_conversation_consent,
)
from server.memory.conversation_types import TurnVerdict, make_turn
from server.memory.declarative import upsert_entity
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_T0 = datetime(2026, 10, 29, 10, 0, tzinfo=UTC)


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "consent.db")
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield await upsert_entity(name="Canary Owner", type="person")
    await db.close_db()
    db._conn = None


async def _store_conversation(owner: int, seconds: float) -> int:
    turn = make_turn(
        "me gusta el mate",
        "Qué rico.",
        voice=TurnVerdict.VERIFIED,
        correlation_id=UUID(int=int(seconds) + 1),
        at=_T0 + timedelta(seconds=seconds),
    )
    return await record.append_turn(turn, owner_entity_id=owner, now=turn.at)


async def test_grant_is_idempotent_and_records_the_notice_version(owner: int) -> None:
    first = await grant_conversation_consent(owner, notice_version="v1", now=_T0)
    second = await grant_conversation_consent(owner, notice_version="v1", now=_T0)

    assert first == second
    assert await has_active_conversation_consent(owner)
    cursor = await db.get_conn().execute(
        "SELECT notice_version FROM conversation_consent_grants WHERE id = ?", (first,)
    )
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    assert row[0] == "v1"


async def test_revoke_deletes_every_record_and_episode_and_reports_the_count(owner: int) -> None:
    await grant_conversation_consent(owner, notice_version="v1", now=_T0)
    first = await _store_conversation(owner, 0)
    await _store_conversation(owner, 600)
    await record.set_episode_status(first, record.EpisodeStatus.DONE)

    deleted = await revoke_conversation_consent(owner, now=_T0 + timedelta(hours=1))

    assert deleted == 2
    assert not await has_active_conversation_consent(owner)
    assert await record.list_records() == ()


async def test_revoke_without_a_grant_deletes_nothing_and_succeeds(owner: int) -> None:
    assert await revoke_conversation_consent(owner, now=_T0) == 0


async def test_a_new_grant_after_a_revoke_is_a_new_row(owner: int) -> None:
    first = await grant_conversation_consent(owner, notice_version="v1", now=_T0)
    await revoke_conversation_consent(owner, now=_T0)

    second = await grant_conversation_consent(owner, notice_version="v1", now=_T0)

    assert second != first
    assert await has_active_conversation_consent(owner)


def test_the_notice_file_exists_and_names_its_version() -> None:
    notice = load_conversation_notice()

    assert f"versión {CONVERSATION_NOTICE_VERSION}" in notice
    assert "Incluye lo que digan otras personas" in notice
    assert "Ni audio ni imágenes" in notice
