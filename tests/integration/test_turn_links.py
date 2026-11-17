"""A turn is linked to everything derived from it (Plan 0085 B4, ADR 0038 decision 6).

Deleting one turn removes its recall unit (and the unit's FTS row and vector), its memory candidate
and its pending topic, and nothing else. Canary rows only; the embedding model is not used.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from server.cognition.models import CognitiveEvent
from server.cognition.response_plan import TextTurnPayload
from server.memory import candidates, conversation_record as record, pending_store, recall_store
from server.memory.candidate_types import CandidateChannel, ProposedCandidate
from server.memory.conversation_capture import capture_turn
from server.memory.conversation_types import RecordedTurn, TurnVerdict, make_turn
from server.memory.declarative import upsert_entity
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    import aiosqlite

pytestmark = pytest.mark.integration

_T0 = datetime(2026, 11, 16, 10, 0, tzinfo=UTC)
_DIMENSIONS = 768
_MODEL = "canary-embedder"


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "turn-links.db")
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    monkeypatch.setattr(settings, "conversation_record_enabled", True)
    monkeypatch.setattr(settings, "recall_enabled", True)
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        yield await upsert_entity(name="Canary Owner", type="person")
    finally:
        await db.close_db()
        db._conn = None


async def _rows(sql: str, *params: object) -> list[tuple[object, ...]]:
    cursor = await db.get_conn().execute(sql, params)
    rows = [tuple(row) for row in await cursor.fetchall()]
    await cursor.close()
    return rows


async def _count(table: str) -> int:
    return int(str((await _rows(f"SELECT count(*) FROM {table}"))[0][0]))  # noqa: S608


def _turn(number: int, heard: str) -> RecordedTurn:
    return make_turn(
        heard,
        "respuesta canario",
        voice=TurnVerdict.VERIFIED,
        correlation_id=UUID(int=number),
        at=_T0 + timedelta(seconds=number),
    )


async def _candidate(owner: int, cid: UUID, key: str) -> int:
    stored = await candidates.insert_candidate(
        ProposedCandidate(predicate="likes", value_text=key, value_key=key),
        subject_person_id=owner,
        asserted_by_person_id=owner,
        channel=CandidateChannel.VOICE_CLASSIC,
        correlation_id=cid,
        now=_T0,
    )
    assert stored.candidate_id is not None
    return stored.candidate_id


def _derive_everything(owner: int) -> record.TurnIndexer:
    """The hook the capture runs: a unit, a pending topic and the candidates' link."""

    async def index(
        conn: aiosqlite.Connection, record_id: int, turn_id: int, recorded: RecordedTurn
    ) -> None:
        await recall_store.insert_turn_unit(
            conn, record_id=record_id, turn_id=turn_id, owner_entity_id=owner, turn=recorded
        )
        await pending_store.insert_unnamed(
            conn,
            owner_entity_id=owner,
            record_id=record_id,
            turn_id=turn_id,
            correlation_id=recorded.correlation_id,
            said_day=date(2026, 11, 16),
            due_day=date(2026, 11, 17),
            heard=recorded.heard,
            sensitivity="normal",
            now=_T0,
        )
        await candidates.link_source_turn(
            conn, correlation_id=recorded.correlation_id, turn_id=turn_id
        )

    return index


async def _append(owner: int, turn: RecordedTurn) -> int:
    await record.append_turn(turn, owner_entity_id=owner, now=_T0, index=_derive_everything(owner))
    rows = await _rows(
        "SELECT id FROM conversation_turns WHERE correlation_id = ?", str(turn.correlation_id)
    )
    return int(str(rows[0][0]))


def _vector() -> list[float]:
    values = [0.0] * _DIMENSIONS
    values[0] = 1.0
    return values


async def test_deleting_one_turn_removes_what_is_derived_from_it_and_nothing_else(
    owner: int,
) -> None:
    """Review focus 4: unit, FTS row, vector, candidate and pending topic go; the rest stays."""
    first, second = _turn(1, "zzprimero gato canario"), _turn(2, "zzsegundo perro canario")
    first_candidate = await _candidate(owner, first.correlation_id, "primero")  # before its turn
    first_id = await _append(owner, first)
    second_id = await _append(owner, second)
    second_candidate = await _candidate(owner, second.correlation_id, "segundo")  # after its turn
    for unit_id, _body in await recall_store.units_without_vector(10):
        assert await recall_store.store_vector(unit_id, _vector(), model=_MODEL) is True
    assert [await _count(t) for t in ("recall_units", "recall_units_vec")] == [2, 2]
    assert await _rows("SELECT id FROM memory_candidates ORDER BY id") == [
        (first_candidate,),
        (second_candidate,),
    ]

    await db.get_conn().execute("DELETE FROM conversation_turns WHERE id = ?", (first_id,))
    await db.get_conn().commit()

    assert await _rows("SELECT turn_id FROM recall_units") == [(second_id,)]
    assert await _rows("SELECT source_turn_id FROM memory_candidates") == [(second_id,)]
    assert await _rows("SELECT source_turn_id FROM pending_topics") == [(second_id,)]
    assert await _count("recall_units_vec") == 1
    assert await _rows(
        "SELECT count(*) FROM recall_units_fts WHERE recall_units_fts MATCH 'zzprimero'"
    ) == [(0,)]
    assert await _rows(
        "SELECT count(*) FROM recall_units_fts WHERE recall_units_fts MATCH 'zzsegundo'"
    ) == [(1,)]
    assert await _count("conversation_records") == 1  # the record stays
    assert await _rows("SELECT id FROM conversation_turns") == [(second_id,)]


async def test_a_candidate_with_the_record_off_keeps_a_null_turn(owner: int) -> None:
    await _candidate(owner, uuid4(), "sin registro")

    assert await _rows("SELECT source_turn_id FROM memory_candidates") == [(None,)]


async def test_a_candidate_ends_linked_in_both_orders(owner: int) -> None:
    before, after = _turn(1, "palabra uno"), _turn(2, "palabra dos")
    await _candidate(owner, before.correlation_id, "antes")  # proposed first, linked by the append
    before_id = await _append(owner, before)
    after_id = await _append(owner, after)

    await _candidate(owner, after.correlation_id, "despues")  # proposed after its turn

    assert await _rows("SELECT value_key, source_turn_id FROM memory_candidates ORDER BY id") == [
        ("antes", before_id),
        ("despues", after_id),
    ]


async def test_linking_leaves_a_candidate_that_already_has_its_turn_alone(owner: int) -> None:
    turn = _turn(1, "palabra uno")
    turn_id = await _append(owner, turn)
    await _candidate(owner, turn.correlation_id, "uno")

    async with db.transaction() as conn:
        changed = await candidates.link_source_turn(
            conn, correlation_id=turn.correlation_id, turn_id=turn_id + 50
        )

    assert changed == 0
    assert await _rows("SELECT source_turn_id FROM memory_candidates") == [(turn_id,)]


async def test_indexing_a_turn_twice_leaves_one_unit(owner: int) -> None:
    turn = _turn(1, "palabra canario")
    turn_id = await _append(owner, turn)

    async with db.transaction() as conn:
        again = await recall_store.insert_turn_unit(
            conn, record_id=1, turn_id=turn_id, owner_entity_id=owner, turn=turn
        )

    assert await _rows("SELECT id FROM recall_units") == [(again,)]
    assert await _count("recall_units_fts") == 1


async def test_an_episode_has_one_unit_however_often_it_is_indexed(owner: int) -> None:
    turn = _turn(1, "palabra canario")
    await _append(owner, turn)
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "INSERT INTO conversation_episodes (source_record_id, owner_entity_id, visibility, "
            "sensitivity, summary, model, created_at, expires_at) "
            "VALUES (1, ?, 'personal', 'normal', 'resumen canario', 'canary', ?, ?)",
            (owner, "2026-11-16T10:00:00.000000+00:00", "2027-11-16T10:00:00.000000+00:00"),
        )
        episode_id = int(cursor.lastrowid or 0)
        await cursor.close()
        ids = {
            await recall_store.insert_episode_unit(
                conn,
                record_id=1,
                episode_id=episode_id,
                owner_entity_id=owner,
                summary="resumen canario",
                sensitivity="normal",
                said_at="2026-11-16T10:00:00.000000+00:00",
            )
            for _ in range(2)
        }

    assert len(ids) == 1
    assert await _rows("SELECT count(*) FROM recall_units WHERE kind = 'episode'") == [(1,)]


def _event(cid: UUID) -> CognitiveEvent[TextTurnPayload]:
    return CognitiveEvent(
        event_id=uuid4(),
        schema_version=1,
        event_type="text.turn",
        occurred_at=_T0,
        recorded_at=_T0,
        source="audio.transcribe",
        correlation_id=cid,
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message="canary", conversation_id="canary-scope"),
    )


async def test_the_capture_links_a_candidate_proposed_before_it(owner: int) -> None:
    cid = uuid4()
    await _candidate(owner, cid, "antes de la captura")

    await capture_turn(
        "palabra canario",
        "respuesta canario",
        None,
        wav_bytes=None,
        event=_event(cid),
        at=_T0,
        owner=AsyncMock(return_value=owner),
        consented=AsyncMock(return_value=True),
        clock=lambda: _T0,
    )

    turn_ids = await _rows("SELECT id FROM conversation_turns")
    assert len(turn_ids) == 1
    assert await _rows("SELECT source_turn_id FROM memory_candidates") == turn_ids
