"""The diary outlives its raw record; a plan that did not happen is never told as done (Plan 0086).

Task 2: D-11 (ADR 0032 decision 5, ADR 0039 decision 2) and the pins of case 1 (D-2). Canary rows
only.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from server.cognition.occurred_time import occurred_window
from server.cognition.recall_cues import WhenKind
from server.memory import conversation_record as record, recall_store
from server.memory.conversation_consent import revoke_conversation_consent
from server.memory.conversation_record import EpisodeStatus
from server.memory.conversation_types import RecordedTurn, TurnVerdict, make_turn
from server.memory.declarative import upsert_entity
from server.memory.recall_answer import word_when
from server.memory.recall_search import RecallHit
from server.settings import settings
from server.timestamps import instant_text

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_T0 = datetime(2026, 10, 29, 10, 0, tzinfo=UTC)
_TZ = ZoneInfo("America/Santiago")
_PLAN = "mañana voy a jugar a la pelota con mis amigos del barrio"
_CANCELLED = "al final se suspendió el partido de mañana porque va a llover"


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "diary.db")
    monkeypatch.setattr(settings, "working_memory_idle_seconds", 180)
    monkeypatch.setattr(settings, "conversation_segment_max_turns", 60)
    monkeypatch.setattr(settings, "conversation_segment_max_bytes", 65536)
    monkeypatch.setattr(settings, "conversation_record_eligible_days", 365)
    monkeypatch.setattr(settings, "conversation_record_ineligible_days", 30)
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        yield await upsert_entity(name="Canary Owner", type="person")
    finally:
        await db.close_db()
        db._conn = None


def _turn(seconds: float, heard: str = "fuimos al cerro con la canaria") -> RecordedTurn:
    return make_turn(
        heard,
        "qué bueno",
        voice=TurnVerdict.VERIFIED,
        correlation_id=UUID(int=int(seconds * 1000) + 1),
        at=_T0 + timedelta(seconds=seconds),
    )


async def _count(sql: str, *params: object) -> int:
    cursor = await db.get_conn().execute(sql, params)
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return int(row[0])


async def _closed_record(owner: int, seconds: float, *, episode: bool) -> int:
    """A closed, eligible record with one turn unit, and optionally its written episode."""
    turn = _turn(seconds)
    record_id = await record.append_turn(turn, owner_entity_id=owner, now=turn.at)
    async with db.transaction() as conn:
        await recall_store.insert_turn_unit(
            conn,
            record_id=record_id,
            owner_entity_id=owner,
            turn=turn,
            turn_id=await record.find_turn_id(conn, turn.correlation_id),
        )
    assert await record.close_idle_records(turn.at + timedelta(hours=1)) == 1
    if episode:
        async with db.transaction() as conn:
            cursor = await conn.execute(
                "INSERT INTO conversation_episodes (source_record_id, owner_entity_id, "
                "visibility, sensitivity, summary, model, created_at, expires_at) "
                "VALUES (?, ?, 'personal', 'normal', ?, 'canary', ?, ?)",
                (
                    record_id,
                    owner,
                    "La persona contó que fue al cerro.",
                    instant_text(_T0),
                    instant_text(_T0 + timedelta(days=365)),
                ),
            )
            episode_id = int(cursor.lastrowid or 0)
            await cursor.close()
            await recall_store.insert_episode_unit(
                conn,
                record_id=record_id,
                episode_id=episode_id,
                owner_entity_id=owner,
                summary="La persona contó que fue al cerro.",
                sensitivity="normal",
                said_at=instant_text(turn.at),
            )
        await record.set_episode_status(record_id, EpisodeStatus.DONE)
    return record_id


async def test_an_expired_record_keeps_its_written_episode_and_loses_its_turns(
    owner: int,
) -> None:
    record_id = await _closed_record(owner, 0, episode=True)

    assert await record.purge_records(_T0 + timedelta(days=400)) == 1

    assert await _count("SELECT COUNT(*) FROM conversation_records WHERE id = ?", record_id) == 1
    assert await _count("SELECT COUNT(*) FROM conversation_turns") == 0
    assert await _count("SELECT COUNT(*) FROM recall_units WHERE kind = 'turn'") == 0
    assert await _count("SELECT COUNT(*) FROM conversation_episodes") == 1
    assert await _count("SELECT COUNT(*) FROM recall_units WHERE kind = 'episode'") == 1
    # A kept record is not purged again on the next run.
    assert await record.purge_records(_T0 + timedelta(days=401)) == 0


async def test_an_expired_record_without_an_episode_goes_whole(owner: int) -> None:
    await _closed_record(owner, 0, episode=False)

    assert await record.purge_records(_T0 + timedelta(days=400)) == 1

    assert await _count("SELECT COUNT(*) FROM conversation_records") == 0
    assert await _count("SELECT COUNT(*) FROM recall_units") == 0


async def test_the_episode_unit_is_recalled_after_its_record_expired(owner: int) -> None:
    await _closed_record(owner, 0, episode=True)
    later = instant_text(_T0 + timedelta(days=400))
    await record.purge_records(_T0 + timedelta(days=400))

    hits = await recall_store.lexical_hits(
        owner_entity_id=owner, terms=("cerro",), since=None, until=None, now=later, limit=5
    )

    units = await recall_store.units_by_id(hits, owner_entity_id=owner, now=later)
    assert [unit.kind for unit in units] == ["episode"]


async def test_the_cap_deletes_turns_oldest_first_and_stops_at_the_kept_records(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    oldest = await _closed_record(owner, 0, episode=True)
    newest = await _closed_record(owner, 3600, episode=True)
    monkeypatch.setattr(record, "_BYTES_PER_MB", 1)
    weight = await _count("SELECT bytes FROM conversation_turns LIMIT 1")
    monkeypatch.setattr(settings, "conversation_record_max_total_mb", weight)

    assert await record.purge_records(_T0 + timedelta(days=1)) == 1

    assert await _count("SELECT COUNT(*) FROM conversation_turns WHERE record_id = ?", oldest) == 0
    assert await _count("SELECT COUNT(*) FROM conversation_turns WHERE record_id = ?", newest) == 1
    monkeypatch.setattr(settings, "conversation_record_max_total_mb", 0)
    assert await record.purge_records(_T0 + timedelta(days=1)) == 1
    assert await record.purge_records(_T0 + timedelta(days=1)) == 0
    assert await _count("SELECT COUNT(*) FROM conversation_episodes") == 2


async def test_withdrawing_the_consent_deletes_the_kept_diary(owner: int) -> None:
    await _closed_record(owner, 0, episode=True)
    await record.purge_records(_T0 + timedelta(days=400))

    await revoke_conversation_consent(owner, now=_T0 + timedelta(days=401))

    assert await _count("SELECT COUNT(*) FROM conversation_episodes") == 0
    assert await _count("SELECT COUNT(*) FROM recall_units") == 0


# --- case 1: a plan that did not happen (D-2) ------------------------------------------------------


def test_a_plan_for_tomorrow_has_no_occurred_day() -> None:
    assert occurred_window(_PLAN, said_day=date(2026, 11, 17)) is None
    assert occurred_window(_CANCELLED, said_day=date(2026, 11, 17)) is None


def test_when_did_i_play_says_the_date_is_not_recorded_and_quotes_the_plan() -> None:
    unit = recall_store.RecallUnit(
        id=1, record_id=1, kind="turn", body=_PLAN, said_at=datetime(2026, 11, 17, 15, tzinfo=UTC)
    )

    answer = word_when(
        (RecallHit(unit=unit, distance=None),),
        WhenKind.HAPPENED,
        today=date(2026, 11, 17),
        tz=_TZ,
    )

    assert answer.startswith("No tengo registrado cuándo fue. Sí recuerdo que hoy me contaste")
    assert "jugar a la pelota" in answer
    assert "jugaste" not in answer


async def test_the_plan_and_its_cancellation_are_both_found(owner: int) -> None:
    plan = _turn(0, heard=_PLAN)
    cancelled = _turn(60, heard=_CANCELLED)
    for turn in (plan, cancelled):
        record_id = await record.append_turn(turn, owner_entity_id=owner, now=turn.at)
        async with db.transaction() as conn:
            await recall_store.insert_turn_unit(
                conn, record_id=record_id, owner_entity_id=owner, turn=turn
            )
    now = instant_text(_T0 + timedelta(hours=1))

    hits = await recall_store.lexical_hits(
        owner_entity_id=owner, terms=("partido",), since=None, until=None, now=now, limit=5
    )
    found = await recall_store.lexical_hits(
        owner_entity_id=owner, terms=("pelota",), since=None, until=None, now=now, limit=5
    )

    bodies = [
        u.body for u in await recall_store.units_by_id(hits + found, owner_entity_id=owner, now=now)
    ]
    assert _PLAN in bodies
    assert _CANCELLED in bodies
