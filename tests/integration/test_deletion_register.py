"""The deletion register and protocol (Plan 0086 Task 3, D-12; ADR 0032 decision 6, ADR 0039).

A deletion for good survives a cut, a restart and a restore, and a reissued id is never deleted
by a second start. Canary rows only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import shutil
from types import MappingProxyType
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from server.exceptions import BrainMemoryError
from server.memory import conversation_record, deletion_register, recall_store, relational_v4
from server.memory.care_contacts import ContactRole, write_contact
from server.memory.conversation_consent import grant_conversation_consent
from server.memory.conversation_types import TurnVerdict, make_turn
from server.memory.declarative import upsert_entity
from server.memory.deletion_register import Deletion, DeletionKind, forget, replay_register
from server.memory.predicate_registry import PredicateDefinition, resolve_predicate
from server.memory.write_types import WriteChannel
from server.settings import settings
from server.timestamps import instant_text

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    import aiosqlite

pytestmark = pytest.mark.integration

_T0 = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)
_CANARY = "canario-registro-9K4Z"


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "register.db")
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    try:
        yield await upsert_entity(name="Canary Owner", type="person")
    finally:
        await db.close_db()
        db._conn = None


def _definition(name: str) -> PredicateDefinition:
    definition = resolve_predicate(name)
    assert definition is not None
    return definition


async def _count(sql: str, *params: object) -> int:
    cursor = await db.get_conn().execute(sql, params)
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return int(row[0])


async def _taste(owner: int, value: str = _CANARY) -> int:
    fact = await relational_v4.assert_literal_fact(
        subject_entity_id=owner, definition=_definition("likes"), value=value
    )
    return fact.id


async def _turn(owner: int, seconds: float = 0) -> tuple[int, int]:
    """A stored, verified turn with its recall unit; returns (record id, turn id)."""
    turn = make_turn(
        f"fuimos al cerro {_CANARY}",
        "qué bueno",
        voice=TurnVerdict.VERIFIED,
        correlation_id=UUID(int=int(seconds) + 1),
        at=_T0 + timedelta(seconds=seconds),
    )

    async def index(
        conn: aiosqlite.Connection, record_id: int, turn_id: int, appended: object
    ) -> None:
        del appended
        await recall_store.insert_turn_unit(
            conn, record_id=record_id, owner_entity_id=owner, turn=turn, turn_id=turn_id
        )

    record_id = await conversation_record.append_turn(
        turn, owner_entity_id=owner, now=turn.at, index=index
    )
    async with db.transaction() as conn:
        turn_id = await conversation_record.find_turn_id(conn, turn.correlation_id)
    assert turn_id is not None
    return record_id, turn_id


async def _episode(owner: int, record_id: int) -> None:
    async with db.transaction() as conn:
        await conn.execute(
            "INSERT INTO conversation_episodes (source_record_id, owner_entity_id, visibility, "
            "sensitivity, summary, model, created_at, expires_at) "
            "VALUES (?, ?, 'personal', 'normal', ?, 'canary', ?, ?)",
            (
                record_id,
                owner,
                f"La persona contó {_CANARY}.",
                instant_text(_T0),
                instant_text(_T0 + timedelta(days=365)),
            ),
        )


def _lines() -> list[dict[str, object]]:
    path = deletion_register.register_path()
    return [json.loads(raw) for raw in path.read_text(encoding="utf-8").splitlines()]


async def _restart() -> None:
    await db.close_db()
    db._conn = None
    await db.open_db()
    await db.run_migrations()


async def _backup(target: Path) -> None:
    """Copy the database as a backup, as an operator would with the server stopped."""
    await db.close_db()
    db._conn = None
    shutil.copyfile(settings.brain_db_path, target)
    await db.open_db()


async def _restore(source: Path) -> None:
    """Put a backup back in place of the database (the register file stays)."""
    await db.close_db()
    db._conn = None
    for suffix in ("-wal", "-shm"):
        settings.brain_db_path.with_name(settings.brain_db_path.name + suffix).unlink(
            missing_ok=True
        )
    shutil.copyfile(source, settings.brain_db_path)
    await db.open_db()
    await db.run_migrations()


async def test_each_kind_leaves_no_row_and_one_line_without_a_value(owner: int) -> None:
    friend = await upsert_entity(name="Canaria", type="person")
    contact = await write_contact(
        owner_entity_id=owner,
        contact_entity_id=friend,
        role=ContactRole.EMERGENCY,
        phone="+56911111111",
        channel=WriteChannel.ADMIN_LOCAL,
        confirmed_at=instant_text(_T0),
    )
    relation = await relational_v4.assert_entity_relation(
        source_entity_id=owner, definition=_definition("has_sibling"), target_entity_id=friend
    )
    fact = await _taste(owner)
    record_id, turn_id = await _turn(owner)
    second_record, _ = await _turn(owner, 3600)
    await _episode(owner, second_record)
    deletions = [
        Deletion(DeletionKind.LITERAL_FACT, fact),
        Deletion(DeletionKind.ENTITY_RELATION, relation.id),
        Deletion(DeletionKind.CARE_CONTACT, contact.id),
        Deletion(DeletionKind.ENTITY, friend),
        Deletion(DeletionKind.TURN, turn_id),
        Deletion(DeletionKind.EPISODE, second_record),
        Deletion(DeletionKind.RECORD, record_id),
    ]

    result = await forget(deletions, now=_T0)

    assert result.checkpointed is True
    assert await _count("SELECT COUNT(*) FROM literal_facts_v4") == 0
    assert await _count("SELECT COUNT(*) FROM entity_relations_v4") == 0
    assert await _count("SELECT COUNT(*) FROM care_contacts") == 0
    assert await _count("SELECT COUNT(*) FROM entities WHERE id = ?", friend) == 0
    assert await _count("SELECT COUNT(*) FROM conversation_turns WHERE id = ?", turn_id) == 0
    assert await _count("SELECT COUNT(*) FROM conversation_episodes") == 0
    assert await _count("SELECT COUNT(*) FROM conversation_records WHERE id = ?", record_id) == 0
    lines = _lines()
    assert [line["kind"] for line in lines] == [d.kind.value for d in deletions]
    assert [line["seq"] for line in lines] == list(range(1, len(deletions) + 1))
    text = deletion_register.register_path().read_text(encoding="utf-8")
    assert _CANARY not in text
    assert "Canaria" not in text


async def test_a_restore_never_resurrects(owner: int, tmp_path: Path) -> None:
    fact = await _taste(owner)
    await _backup(tmp_path / "before.db")
    await forget([Deletion(DeletionKind.LITERAL_FACT, fact)], now=_T0)

    await _restore(tmp_path / "before.db")
    assert await _count("SELECT COUNT(*) FROM literal_facts_v4") == 1  # the backup has it

    assert await replay_register() == 1
    assert await _count("SELECT COUNT(*) FROM literal_facts_v4") == 0
    assert await replay_register() == 0  # the marker moved


async def test_a_reissued_id_survives_a_second_start(owner: int, tmp_path: Path) -> None:
    await _backup(tmp_path / "empty.db")  # no fact yet: the next fact id is 1 here
    deleted = await _taste(owner)
    await forget([Deletion(DeletionKind.LITERAL_FACT, deleted)], now=_T0)
    await _restore(tmp_path / "empty.db")
    await replay_register()

    reissued = await _taste(owner, "el mate")  # the restored database hands out the same id
    assert reissued == deleted
    await _restart()
    assert await replay_register() == 0

    assert await _count("SELECT COUNT(*) FROM literal_facts_v4 WHERE id = ?", reissued) == 1


async def test_a_cut_after_the_append_deletes_at_the_next_start(owner: int) -> None:
    fact = await _taste(owner)
    deletion_register._append([Deletion(DeletionKind.LITERAL_FACT, fact)], instant_text(_T0))
    assert await _count("SELECT COUNT(*) FROM literal_facts_v4") == 1  # the cut: nothing deleted

    await _restart()
    assert await replay_register() == 1

    assert await _count("SELECT COUNT(*) FROM literal_facts_v4") == 0


async def test_a_half_written_last_line_is_ignored_and_replaced(owner: int) -> None:
    first = await _taste(owner)
    second = await _taste(owner, "el mate")
    await forget([Deletion(DeletionKind.LITERAL_FACT, first)], now=_T0)
    with deletion_register.register_path().open("ab") as handle:
        handle.write(b'{"seq":2,"kind":"literal_fa')

    assert await replay_register() == 0
    await forget([Deletion(DeletionKind.LITERAL_FACT, second)], now=_T0)

    assert [line["seq"] for line in _lines()] == [1, 2]
    assert await _count("SELECT COUNT(*) FROM literal_facts_v4") == 0


async def test_an_unreadable_middle_line_refuses_the_start(owner: int) -> None:
    fact = await _taste(owner)
    await forget([Deletion(DeletionKind.LITERAL_FACT, fact)], now=_T0)
    path = deletion_register.register_path()
    path.write_text("no es una línea\n" + path.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(BrainMemoryError, match="1 unreadable line") as caught:
        await replay_register()
    assert "no es" not in str(caught.value)


async def test_the_deletion_commits_under_full_and_puts_normal_back(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    fact = await _taste(owner)
    seen: list[int] = []
    original = relational_v4.delete_literal_fact_row

    async def watching(conn: aiosqlite.Connection, row_id: int) -> int:
        cursor = await conn.execute("PRAGMA synchronous")
        row = await cursor.fetchone()
        await cursor.close()
        assert row is not None
        seen.append(int(row[0]))
        return await original(conn, row_id)

    monkeypatch.setattr(
        deletion_register,
        "_DELETERS",
        MappingProxyType({**deletion_register._DELETERS, DeletionKind.LITERAL_FACT: watching}),
    )

    await forget([Deletion(DeletionKind.LITERAL_FACT, fact)], now=_T0)

    assert seen == [2]  # FULL
    assert await _count("PRAGMA synchronous") == 1  # NORMAL


async def test_withdrawing_the_consent_and_deleting_a_record_write_their_lines(
    owner: int,
) -> None:
    await grant_conversation_consent(owner, notice_version="v1", now=_T0)
    first, _ = await _turn(owner)
    await _turn(owner, 3600)

    assert await deletion_register.forget_record(first, now=_T0) is True
    assert await deletion_register.withdraw_conversation_consent(owner, now=_T0) == 1

    assert [line["kind"] for line in _lines()] == ["record", "owner_records"]
    assert await _count("SELECT COUNT(*) FROM conversation_records") == 0
    assert (
        await _count("SELECT COUNT(*) FROM conversation_consent_grants WHERE revoked_at IS NULL")
        == 0
    )
