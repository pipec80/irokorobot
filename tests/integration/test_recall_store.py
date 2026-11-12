"""The recall store: the only SQL on the recall units (Plan 0078 Task 4, ADR 0028 decision 1).

Canary rows only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from server.memory import recall_store
from server.memory.conversation_types import RecordedTurn, TurnVerdict
from server.memory.declarative import upsert_entity
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_DIMENSIONS = 768
_SAID = datetime(2026, 11, 3, 15, tzinfo=UTC)
_SAID_ISO = "2026-11-03T15:00:00.000000+00:00"
_NOW = "2026-11-04T12:00:00.000000+00:00"
_PAST = "2026-11-01T00:00:00.000000+00:00"
_FUTURE = "2027-11-03T10:00:00.000000+00:00"
_CID = UUID("00000000-0000-0000-0000-0000000000aa")


@pytest.fixture
async def owners(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[int, int]]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "recall.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        owner = await upsert_entity(name="Canary Owner", type="person")
        other = await upsert_entity(name="Canary Other", type="person")
        yield owner, other
    finally:
        await db.close_db()
        db._conn = None


def _axis(axis: int) -> list[float]:
    values = [0.0] * _DIMENSIONS
    values[axis] = 1.0
    return values


def _turn(
    heard: str, voice: TurnVerdict = TurnVerdict.VERIFIED, said: str = "zzrobotzz"
) -> RecordedTurn:
    return RecordedTurn(at=_SAID, heard=heard, said=said, voice=voice, correlation_id=_CID)


async def _record(owner: int, *, expires_at: str | None = _FUTURE) -> int:
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "INSERT INTO conversation_records (owner_entity_id, started_at, last_turn_at, "
            "closed_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (owner, _SAID_ISO, _SAID_ISO, _SAID_ISO, expires_at),
        )
        record_id = int(cursor.lastrowid or 0)
        await cursor.close()
    return record_id


async def _turn_unit(owner: int, record_id: int, heard: str) -> int:
    async with db.transaction() as conn:
        return await recall_store.insert_turn_unit(
            conn, record_id=record_id, owner_entity_id=owner, turn=_turn(heard)
        )


async def _episode_unit(owner: int, record_id: int, summary: str, said_at: str = _SAID_ISO) -> int:
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "INSERT INTO conversation_episodes (source_record_id, owner_entity_id, visibility, "
            "sensitivity, summary, model, created_at, expires_at) "
            "VALUES (?, ?, 'personal', 'normal', ?, 'canary', ?, ?)",
            (record_id, owner, summary, said_at, _FUTURE),
        )
        episode_id = int(cursor.lastrowid or 0)
        await cursor.close()
        return await recall_store.insert_episode_unit(
            conn,
            record_id=record_id,
            episode_id=episode_id,
            owner_entity_id=owner,
            summary=summary,
            sensitivity="normal",
            said_at=said_at,
        )


async def _lexical(
    owner: int, *terms: str, since: str | None = None, until: str | None = None
) -> list[int]:
    return await recall_store.lexical_hits(
        owner_entity_id=owner, terms=terms, since=since, until=until, now=_NOW, limit=10
    )


async def test_a_turn_unit_holds_only_the_heard_text(owners: tuple[int, int]) -> None:
    owner, _ = owners
    record_id = await _record(owner)

    unit_id = await _turn_unit(owner, record_id, "fuimos al cerro con Zeta")

    units = await recall_store.units_by_id([unit_id], owner_entity_id=owner, now=_NOW)
    assert [(unit.kind, unit.body, unit.record_id) for unit in units] == [
        ("turn", "fuimos al cerro con Zeta", record_id)
    ]
    assert units[0].said_at == _SAID
    assert await _lexical(owner, "zzrobotzz") == []
    assert "Zeta" not in repr(units[0])


@pytest.mark.parametrize(
    "voice", [TurnVerdict.NOT_VERIFIED, TurnVerdict.NOT_OWNER, TurnVerdict.NOT_CHECKED]
)
async def test_a_not_verified_turn_is_refused(owners: tuple[int, int], voice: TurnVerdict) -> None:
    owner, _ = owners
    record_id = await _record(owner)

    with pytest.raises(ValueError, match="verified"):
        async with db.transaction() as conn:
            await recall_store.insert_turn_unit(
                conn, record_id=record_id, owner_entity_id=owner, turn=_turn("canario", voice)
            )


async def test_a_blank_turn_is_refused(owners: tuple[int, int]) -> None:
    owner, _ = owners
    record_id = await _record(owner)

    with pytest.raises(ValueError, match="blank"):
        async with db.transaction() as conn:
            await recall_store.insert_turn_unit(
                conn, record_id=record_id, owner_entity_id=owner, turn=_turn("   ")
            )


async def test_a_turn_unit_takes_the_sensitivity_of_its_words(owners: tuple[int, int]) -> None:
    owner, _ = owners
    record_id = await _record(owner)

    await _turn_unit(owner, record_id, "mañana voy al hospital")

    assert await _lexical(owner, "hospital") == []


async def test_raising_never_lowers(owners: tuple[int, int]) -> None:
    owner, _ = owners
    record_id = await _record(owner)
    normal = await _turn_unit(owner, record_id, "tomamos mate")
    medical = await _turn_unit(owner, record_id, "fui al doctor")

    async with db.transaction() as conn:
        changed = await recall_store.raise_record_sensitivity(
            conn, record_id=record_id, sensitivity="location"
        )

    assert changed == 1
    cursor = await db.get_conn().execute("SELECT id, sensitivity FROM recall_units ORDER BY id")
    rows = {int(row[0]): str(row[1]) for row in await cursor.fetchall()}
    await cursor.close()
    assert rows == {normal: "location", medical: "medical"}


async def test_lexical_hits_ignore_another_owner_a_sensitive_unit_and_an_expired_record(
    owners: tuple[int, int],
) -> None:
    owner, other = owners
    mine = await _record(owner)
    found = await _turn_unit(owner, mine, "el cerro estaba lindo")
    await _turn_unit(owner, mine, "en el cerro me dolió la cabeza, fui al doctor")
    await _turn_unit(other, await _record(other), "el cerro de Omega")
    expired = await _record(owner, expires_at=_PAST)
    await _turn_unit(owner, expired, "otra vez el cerro")

    assert await _lexical(owner, "cerro") == [found]


async def test_lexical_hits_respect_the_window(owners: tuple[int, int]) -> None:
    owner, _ = owners
    record_id = await _record(owner)
    unit_id = await _turn_unit(owner, record_id, "el cerro")

    assert await _lexical(
        owner,
        "cerro",
        since="2026-11-03T03:00:00.000000+00:00",
        until="2026-11-04T03:00:00.000000+00:00",
    ) == [unit_id]
    assert (
        await _lexical(
            owner,
            "cerro",
            since="2026-11-04T03:00:00.000000+00:00",
            until="2026-11-05T03:00:00.000000+00:00",
        )
        == []
    )


@pytest.mark.parametrize(
    "term",
    ['"', "*", "OR", "NEAR(", "cerro AND", "x" * 2000, "\U0001f600", "ignora lo anterior", ""],
)
async def test_lexical_hits_survive_fts_syntax_in_the_terms(
    owners: tuple[int, int], term: str
) -> None:
    owner, _ = owners
    record_id = await _record(owner)
    unit_id = await _turn_unit(owner, record_id, "el cerro estaba lindo")

    hits = await _lexical(owner, term, "cerro")

    assert hits == [unit_id]


async def test_lexical_hits_without_terms_are_empty(owners: tuple[int, int]) -> None:
    owner, _ = owners

    assert await _lexical(owner) == []


async def test_vector_hits_filter_owner_and_sensitivity_inside_the_query(
    owners: tuple[int, int],
) -> None:
    owner, other = owners
    mine = await _record(owner)
    near = await _turn_unit(owner, mine, "el cerro")
    sensitive = await _turn_unit(owner, mine, "el doctor")
    foreign = await _turn_unit(other, await _record(other), "el cerro")
    for unit_id in (near, sensitive, foreign):
        assert await recall_store.store_vector(unit_id, _axis(0), model="canary")

    hits = await recall_store.vector_hits(
        owner_entity_id=owner, vector=_axis(0), since=None, until=None, now=_NOW, k=10
    )

    assert [unit_id for unit_id, _ in hits] == [near]
    assert hits[0][1] == pytest.approx(0.0, abs=0.001)


async def test_store_vector_takes_the_current_sensitivity(owners: tuple[int, int]) -> None:
    owner, _ = owners
    record_id = await _record(owner)
    unit_id = await _turn_unit(owner, record_id, "el cerro")
    async with db.transaction() as conn:
        await recall_store.raise_record_sensitivity(
            conn, record_id=record_id, sensitivity="private"
        )

    assert await recall_store.store_vector(unit_id, _axis(1), model="canary")

    cursor = await db.get_conn().execute(
        "SELECT sensitivity FROM recall_units_vec WHERE rowid = ?", (unit_id,)
    )
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    assert str(row[0]) == "private"
    assert await recall_store.units_without_vector(10) == []


async def test_store_vector_on_a_deleted_unit_is_false(owners: tuple[int, int]) -> None:
    owner, _ = owners
    record_id = await _record(owner)
    unit_id = await _turn_unit(owner, record_id, "el cerro")
    assert await recall_store.units_without_vector(10) == [(unit_id, "el cerro")]
    async with db.transaction() as conn:
        await conn.execute("DELETE FROM conversation_records WHERE id = ?", (record_id,))

    assert not await recall_store.store_vector(unit_id, _axis(1), model="canary")


async def test_store_vector_twice_keeps_one_vector(owners: tuple[int, int]) -> None:
    owner, _ = owners
    unit_id = await _turn_unit(owner, await _record(owner), "el cerro")

    assert await recall_store.store_vector(unit_id, _axis(1), model="canary")
    assert await recall_store.store_vector(unit_id, _axis(2), model="canary")

    cursor = await db.get_conn().execute("SELECT COUNT(*) FROM recall_units_vec")
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    assert int(row[0]) == 1


async def test_recent_units_prefer_episodes(owners: tuple[int, int]) -> None:
    owner, _ = owners
    first = await _record(owner)
    turn_id = await _turn_unit(owner, first, "el cerro")
    since, until = "2026-11-03T03:00:00.000000+00:00", "2026-11-04T03:00:00.000000+00:00"

    turns_only = await recall_store.recent_units(
        owner_entity_id=owner, now=_NOW, limit=3, since=since, until=until
    )
    assert [unit.id for unit in turns_only] == [turn_id]

    older = await _episode_unit(
        owner, first, "La persona contó del cerro.", "2026-11-03T14:00:00.000000+00:00"
    )
    newer = await _episode_unit(owner, await _record(owner), "La persona habló del mate.")
    with_episodes = await recall_store.recent_units(
        owner_entity_id=owner, now=_NOW, limit=3, since=since, until=until
    )

    assert [unit.id for unit in with_episodes] == [newer, older]
    assert all(unit.kind == "episode" for unit in with_episodes)
