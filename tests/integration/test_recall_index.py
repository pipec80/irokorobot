"""Writing and embedding the recall units (Plan 0078 Task 5, ADR 0028 decisions 1 to 3).

Canary rows only; the embedding model is a double.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from server.cognition.identity import (
    ActivePersonContext,
    HouseholdRole,
    IdentityEvidence,
    IdentityEvidenceSource,
    PersonRecord,
    resolve_active_person,
)
from server.cognition.models import CognitiveEvent, Confidence, ConfidenceBasis
from server.cognition.response_plan import TextTurnPayload
from server.memory import (
    conversation_jobs,
    conversation_record as record,
    recall_index,
    recall_store,
)
from server.memory.conversation_capture import capture_turn
from server.memory.conversation_episodes import write_episode
from server.memory.conversation_summary import EpisodeDraft, EpisodeSensitivity
from server.memory.conversation_types import TurnVerdict, make_turn
from server.memory.declarative import upsert_entity
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    import aiosqlite
    from server.memory.conversation_types import RecordedTurn

pytestmark = pytest.mark.integration

_T0 = datetime(2026, 11, 3, 15, 0, tzinfo=UTC)
_NOW_ISO = "2026-11-04T12:00:00.000000+00:00"
_HEARD = "fuimos al cerro con Zeta"
_SAID = "zzrobotzz qué lindo paseo"
_DIMENSIONS = 768


def _vector() -> list[float]:
    values = [0.0] * _DIMENSIONS
    values[0] = 1.0
    return values


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "recall-index.db")
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "conversation_record_enabled", True)
    monkeypatch.setattr(settings, "conversation_episodes_enabled", True)
    monkeypatch.setattr(settings, "recall_enabled", True)
    monkeypatch.setattr(settings, "working_memory_idle_seconds", 180)
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        yield await upsert_entity(name="Canary Owner", type="person")
    finally:
        await db.close_db()
        db._conn = None


@pytest.fixture
def embedded(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    embed = AsyncMock(return_value=_vector())
    monkeypatch.setattr(recall_index, "ollama_embed", embed)
    return embed


def _event() -> CognitiveEvent[TextTurnPayload]:
    return CognitiveEvent(
        event_id=uuid4(),
        schema_version=1,
        event_type="text.turn",
        occurred_at=_T0,
        recorded_at=_T0,
        source="audio.transcribe",
        correlation_id=uuid4(),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message="canary", conversation_id="canary-scope"),
    )


def _face(person_id: int) -> ActivePersonContext:
    person = PersonRecord(person_id=person_id, display_name="Canary", entity_type="person")
    evidence = IdentityEvidence(
        evidence_id=uuid4(),
        source=IdentityEvidenceSource.FACE,
        candidate_person_id=person_id,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
        observed_at=_T0 - timedelta(seconds=1),
        reference="canary",
    )
    return resolve_active_person(
        evidence=(evidence,),
        lookup_person=lambda pid: person if pid == person_id else None,
        lookup_role=lambda _pid: HouseholdRole.OWNER,
        clock=lambda: _T0,
    )


async def _capture(
    owner: int,
    verdict: TurnVerdict,
    *,
    heard: str = _HEARD,
    client: httpx.AsyncClient | None = None,
    at: datetime = _T0,
) -> None:
    """Capture one exchange whose verdict is *verdict*, the way the voice routes do."""
    match verdict:
        case TurnVerdict.NOT_CHECKED:
            actor, fused = None, None
        case TurnVerdict.NOT_OWNER:
            actor, fused = _face(owner + 100), None
        case TurnVerdict.NOT_VERIFIED:
            actor, fused = _face(owner), None
        case TurnVerdict.VERIFIED:
            actor, fused = _face(owner), _face(owner)
    await capture_turn(
        heard,
        _SAID,
        actor,
        wav_bytes=b"RIFF-canary",
        event=_event(),
        at=at,
        verify=AsyncMock(return_value=fused),
        owner=AsyncMock(return_value=owner),
        consented=AsyncMock(return_value=True),
        clock=lambda: at,
        client=client or httpx.AsyncClient(),
    )


async def _rows(sql: str, *params: object) -> list[tuple[object, ...]]:
    cursor = await db.get_conn().execute(sql, params)
    rows = [tuple(row) for row in await cursor.fetchall()]
    await cursor.close()
    return rows


async def _units() -> list[tuple[object, ...]]:
    return await _rows(
        "SELECT kind, body, sensitivity, embedding_model FROM recall_units ORDER BY id"
    )


async def test_a_verified_turn_gets_a_unit_in_the_same_transaction(owner: int) -> None:
    turn = make_turn(_HEARD, _SAID, voice=TurnVerdict.VERIFIED, correlation_id=uuid4(), at=_T0)

    async def failing(conn: aiosqlite.Connection, record_id: int, recorded: RecordedTurn) -> int:
        await recall_store.insert_turn_unit(
            conn, record_id=record_id, owner_entity_id=owner, turn=recorded
        )
        raise RuntimeError("index failed")

    with pytest.raises(RuntimeError, match="index failed"):
        await record.append_turn(turn, owner_entity_id=owner, now=_T0, index=failing)

    assert await _rows("SELECT id FROM conversation_records") == []
    assert await _units() == []

    async def indexer(conn: aiosqlite.Connection, record_id: int, recorded: RecordedTurn) -> int:
        return await recall_store.insert_turn_unit(
            conn, record_id=record_id, owner_entity_id=owner, turn=recorded
        )

    record_id = await record.append_turn(turn, owner_entity_id=owner, now=_T0, index=indexer)

    assert await _rows("SELECT source_record_id FROM recall_units") == [(record_id,)]


async def test_no_unit_without_recall_enabled(
    owner: int, embedded: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "recall_enabled", False)

    await _capture(owner, TurnVerdict.VERIFIED)

    assert await _rows("SELECT COUNT(*) FROM conversation_records") == [(1,)]
    assert await _units() == []
    embedded.assert_not_awaited()


@pytest.mark.parametrize("verdict", list(TurnVerdict))
async def test_no_unit_for_not_verified_not_owner_or_not_checked(
    owner: int, embedded: AsyncMock, verdict: TurnVerdict
) -> None:
    await _capture(owner, verdict)

    units = await _units()
    assert await _rows("SELECT COUNT(*) FROM conversation_records") == [(1,)]
    assert len(units) == int(verdict is TurnVerdict.VERIFIED)
    assert embedded.await_count == int(verdict is TurnVerdict.VERIFIED)


async def test_a_blank_verified_turn_is_recorded_without_a_unit(
    owner: int, embedded: AsyncMock
) -> None:
    await _capture(owner, TurnVerdict.VERIFIED, heard="   ")

    assert await _rows("SELECT COUNT(*) FROM conversation_records") == [(1,)]
    assert await _units() == []


async def test_the_robot_reply_is_never_a_unit(owner: int, embedded: AsyncMock) -> None:
    await _capture(owner, TurnVerdict.VERIFIED)

    units = await _units()
    assert [unit[1] for unit in units] == [_HEARD]
    assert all("zzrobotzz" not in str(unit[1]) for unit in units)
    embedded.assert_awaited_once()
    assert embedded.await_args is not None
    assert embedded.await_args.args[1] == _HEARD


async def test_the_unit_is_embedded_with_the_setting_model(owner: int, embedded: AsyncMock) -> None:
    await _capture(owner, TurnVerdict.VERIFIED)

    assert embedded.await_args is not None
    assert embedded.await_args.kwargs["model"] == settings.embedding_model
    assert await _units() == [("turn", _HEARD, "normal", settings.embedding_model)]


async def test_an_unreachable_embedding_model_leaves_a_lexical_unit(
    owner: int, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        recall_index, "ollama_embed", AsyncMock(side_effect=httpx.ConnectError("Zeta canary"))
    )

    with caplog.at_level(logging.INFO):
        await _capture(owner, TurnVerdict.VERIFIED)

    assert await _units() == [("turn", _HEARD, "normal", None)]
    hits = await recall_store.lexical_hits(
        owner_entity_id=owner, terms=["cerro"], since=None, until=None, now=_NOW_ISO, limit=3
    )
    assert len(hits) == 1
    assert all(
        "Zeta" not in r.getMessage() and "cerro" not in r.getMessage() for r in caplog.records
    )


async def _closed(owner: int) -> record.RecordView:
    await record.close_idle_records(_T0 + timedelta(minutes=10))
    pending = await record.next_pending_record()
    assert pending is not None
    return pending


def _summarizer(sensitivity: EpisodeSensitivity) -> AsyncMock:
    async def summarize(_client: httpx.AsyncClient, _turns: object) -> EpisodeDraft:
        await asyncio.sleep(0)
        return EpisodeDraft(summary="La persona contó un paseo al cerro.", sensitivity=sensitivity)

    return AsyncMock(side_effect=summarize)


async def test_the_episode_raises_the_sensitivity_of_its_turns(
    owner: int, embedded: AsyncMock
) -> None:
    await _capture(owner, TurnVerdict.VERIFIED)
    await _capture(
        owner,
        TurnVerdict.VERIFIED,
        heard="me duele la rodilla, fui al doctor",
        at=_T0 + timedelta(seconds=5),
    )
    view = await _closed(owner)

    await write_episode(
        view,
        client=httpx.AsyncClient(),
        now=_T0 + timedelta(minutes=11),
        summarize=_summarizer("location"),
    )

    rows = await _rows("SELECT kind, sensitivity FROM recall_units ORDER BY id")
    assert rows == [("turn", "location"), ("turn", "medical"), ("episode", "location")]
    vectors = await _rows("SELECT sensitivity FROM recall_units_vec ORDER BY rowid")
    assert vectors == [("location",), ("medical",)]


async def test_no_episode_unit_without_recall_enabled(
    owner: int, embedded: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _capture(owner, TurnVerdict.VERIFIED)
    view = await _closed(owner)
    monkeypatch.setattr(settings, "recall_enabled", False)

    await write_episode(
        view,
        client=httpx.AsyncClient(),
        now=_T0 + timedelta(minutes=11),
        summarize=_summarizer("medical"),
    )

    assert await _rows("SELECT kind, sensitivity FROM recall_units") == [("turn", "normal")]


@pytest.mark.parametrize("episode_first", [True, False])
async def test_two_turns_verified_while_the_episode_is_written_end_protective(
    owner: int, monkeypatch: pytest.MonkeyPatch, episode_first: bool
) -> None:
    """Review focus 5: vectors stored while the episode is written still end protective."""
    monkeypatch.setattr(
        recall_index, "ollama_embed", AsyncMock(side_effect=httpx.ConnectError("offline"))
    )
    await _capture(owner, TurnVerdict.VERIFIED)
    await _capture(owner, TurnVerdict.VERIFIED, heard="tomamos mate", at=_T0 + timedelta(seconds=3))
    view = await _closed(owner)
    unit_ids = [int(str(row[0])) for row in await _rows("SELECT id FROM recall_units ORDER BY id")]

    episode = write_episode(
        view,
        client=httpx.AsyncClient(),
        now=_T0 + timedelta(minutes=11),
        summarize=_summarizer("medical"),
    )
    vectors = [
        recall_store.store_vector(unit_id, _vector(), model="canary") for unit_id in unit_ids
    ]
    jobs = [episode, *vectors] if episode_first else [*vectors, episode]
    await asyncio.gather(*jobs)

    assert await _rows("SELECT kind, sensitivity FROM recall_units ORDER BY id") == [
        ("turn", "medical"),
        ("turn", "medical"),
        ("episode", "medical"),
    ]
    assert await _rows("SELECT sensitivity FROM recall_units_vec ORDER BY rowid") == [
        ("medical",),
        ("medical",),
    ]


async def test_backfill_waits_for_an_open_conversation(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    offline = AsyncMock(side_effect=httpx.ConnectError("offline"))
    monkeypatch.setattr(recall_index, "ollama_embed", offline)
    await _capture(owner, TurnVerdict.VERIFIED)
    online = AsyncMock(return_value=_vector())
    monkeypatch.setattr(recall_index, "ollama_embed", online)
    monkeypatch.setattr(settings, "conversation_episodes_enabled", False)

    await conversation_jobs.run_once(httpx.AsyncClient(), _T0 + timedelta(seconds=30))

    online.assert_not_awaited()
    assert await recall_store.units_without_vector(5) != []

    await conversation_jobs.run_once(httpx.AsyncClient(), _T0 + timedelta(minutes=10))

    online.assert_awaited_once()
    assert await recall_store.units_without_vector(5) == []


async def test_backfill_needs_recall_enabled(owner: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        recall_index, "ollama_embed", AsyncMock(side_effect=httpx.ConnectError("x"))
    )
    await _capture(owner, TurnVerdict.VERIFIED)
    online = AsyncMock(return_value=_vector())
    monkeypatch.setattr(recall_index, "ollama_embed", online)
    monkeypatch.setattr(settings, "recall_enabled", False)
    monkeypatch.setattr(settings, "conversation_episodes_enabled", False)

    await conversation_jobs.run_once(httpx.AsyncClient(), _T0 + timedelta(minutes=10))

    online.assert_not_awaited()


async def test_backfill_embeds_the_episode_unit(owner: int, embedded: AsyncMock) -> None:
    await _capture(owner, TurnVerdict.VERIFIED)
    view = await _closed(owner)
    await write_episode(
        view,
        client=httpx.AsyncClient(),
        now=_T0 + timedelta(minutes=11),
        summarize=_summarizer("normal"),
    )
    assert len(await recall_store.units_without_vector(5)) == 1

    assert await recall_index.backfill_vectors(httpx.AsyncClient()) == 1

    assert await recall_store.units_without_vector(5) == []


async def test_backfill_stops_at_the_first_failure(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    offline = AsyncMock(side_effect=httpx.ConnectError("offline"))
    monkeypatch.setattr(recall_index, "ollama_embed", offline)
    await _capture(owner, TurnVerdict.VERIFIED)
    await _capture(owner, TurnVerdict.VERIFIED, heard="tomamos mate", at=_T0 + timedelta(seconds=3))
    offline.reset_mock()

    assert await recall_index.backfill_vectors(httpx.AsyncClient()) == 0

    offline.assert_awaited_once()


async def test_warm_up_failure_only_logs(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        recall_index, "ollama_embed", AsyncMock(side_effect=httpx.ConnectError("Zeta canary"))
    )

    with caplog.at_level(logging.WARNING):
        await recall_index.warm_up(httpx.AsyncClient())

    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("ConnectError" in message for message in messages)
    assert all("Zeta" not in message for message in messages)


async def test_warm_up_embeds_one_fixed_word(monkeypatch: pytest.MonkeyPatch) -> None:
    embed = AsyncMock(return_value=_vector())
    monkeypatch.setattr(recall_index, "ollama_embed", embed)

    await recall_index.warm_up(httpx.AsyncClient())

    embed.assert_awaited_once()
    assert embed.await_args is not None
    assert embed.await_args.kwargs["model"] == settings.embedding_model


async def test_embed_unit_on_a_vector_of_the_wrong_size_is_false(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        recall_index, "ollama_embed", AsyncMock(side_effect=httpx.ConnectError("x"))
    )
    await _capture(owner, TurnVerdict.VERIFIED)
    monkeypatch.setattr(recall_index, "ollama_embed", AsyncMock(return_value=[1.0, 0.0]))
    ((unit_id, body),) = await recall_store.units_without_vector(1)

    assert not await recall_index.embed_unit(httpx.AsyncClient(), unit_id, body)
