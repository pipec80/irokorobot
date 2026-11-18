"""Physical deletion proven at the byte level (Plan 0085, decision D-4).

A canary is written to a plain row (a memory candidate) and to a recall unit, so FTS5 and the
``vec0`` table hold it too. Each is erased through its store; after a checkpoint that reports
success, neither the database file nor its write-ahead log holds the canary text or its vector
bytes. This proves the SQLite files, not the storage medium (that is encryption, ADR 0033).
Invented canaries only.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
import struct
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from server.memory import candidates, conversation_record, pending_store, recall_store
from server.memory.candidate_types import CandidateChannel, CandidateStatus, ProposedCandidate
from server.memory.conversation_types import RecordedTurn, TurnVerdict
from server.memory.declarative import upsert_entity
from server.memory.deletion_register import Deletion, DeletionKind, forget, forget_record
from server.memory.embeddings import EMBEDDING_DIM
from server.memory.predicate_registry import resolve_predicate
from server.memory.relational_v4 import assert_literal_fact
from server.settings import settings
from server.timestamps import instant_text

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    import aiosqlite

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 11, 16, 10, 0, tzinfo=UTC)
_CANDIDATE_CANARY = "canario-candidato-7Q2X"
_TURN_CANARY = "canario-borrado-7Q2X"
# FTS5 (unicode61) stores lowercased tokens, so the verbatim canary never appears in its shadow
# tables: a leak there is only visible through the lowercased distinctive token.
_TURN_TOKEN_LOWER = b"7q2x"
# What hangs from the canary turn: a memory candidate's value and a pending topic's words. Deleting
# the record deletes the turn and, through its link, both (Plan 0085 D-8).
_LINKED_CANDIDATE_CANARY = "canario-ligado-candidato-7Q2X"
_LINKED_TOPIC_CANARY = "canario-ligado-pendiente-7Q2X"
_MODEL = "canary-model"
_CID = UUID("00000000-0000-0000-0000-0000000000bb")
_VECTOR = [0.123456789 + index / 10_000 for index in range(EMBEDDING_DIM)]
_VECTOR_BYTES = struct.pack(f"{EMBEDDING_DIM}f", *_VECTOR)
_VECTOR_SLICE = _VECTOR_BYTES[:16]


@pytest.fixture
async def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Path]:
    """A fresh temporary database with the full schema and the candidate subsystem on."""
    db_path = tmp_path / "physical-deletion.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield db_path
    await db.close_db()
    db._conn = None


def _file_bytes(db_path: Path) -> bytes:
    """Concatenate the database file and its write-ahead log, as an attacker would read them."""
    pieces = [db_path.read_bytes()]
    wal = db_path.with_name(db_path.name + "-wal")
    if wal.exists():
        pieces.append(wal.read_bytes())
    return b"".join(pieces)


async def _index_turn(
    conn: aiosqlite.Connection, record_id: int, turn_id: int, turn: RecordedTurn
) -> None:
    """Index the appended turn as a recall unit, inside the append's transaction."""
    owner_cursor = await conn.execute(
        "SELECT owner_entity_id FROM conversation_records WHERE id = ?", (record_id,)
    )
    row = await owner_cursor.fetchone()
    await owner_cursor.close()
    assert row is not None
    await recall_store.insert_turn_unit(
        conn, record_id=record_id, turn_id=turn_id, owner_entity_id=int(row[0]), turn=turn
    )


async def _link_candidate_and_topic_to_the_turn(owner: int) -> None:
    """Hang a memory candidate and a pending topic from the canary turn, as the capture does."""
    stored = await candidates.insert_candidate(
        ProposedCandidate(
            predicate="likes", value_text=_LINKED_CANDIDATE_CANARY, value_key="canario-ligado"
        ),
        subject_person_id=owner,
        asserted_by_person_id=owner,
        channel=CandidateChannel.VOICE_CLASSIC,
        correlation_id=_CID,
        now=_NOW,
    )
    assert stored.candidate_id is not None
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "SELECT t.id, t.record_id FROM conversation_turns t WHERE t.correlation_id = ?",
            (str(_CID),),
        )
        row = await cursor.fetchone()
        await cursor.close()
        assert row is not None
        await pending_store.insert_unnamed(
            conn,
            owner_entity_id=owner,
            record_id=int(row[1]),
            correlation_id=_CID,
            said_day=date(2026, 11, 16),
            due_day=date(2026, 11, 17),
            heard=_LINKED_TOPIC_CANARY,
            sensitivity="normal",
            now=_NOW,
            turn_id=int(row[0]),
        )
    cursor = await db.get_conn().execute(
        "SELECT (SELECT count(*) FROM memory_candidates WHERE source_turn_id IS NOT NULL), "
        "(SELECT count(*) FROM pending_topics WHERE source_turn_id IS NOT NULL)"
    )
    assert tuple(await cursor.fetchone() or ()) == (1, 1)  # both hang from the turn
    await cursor.close()


async def test_a_rejected_candidate_value_leaves_no_byte_in_the_file_or_the_log(
    store: Path,
) -> None:
    """The value scrub is physical: the canary is found while live and never after."""
    owner = await upsert_entity(name="Canary Owner", type="person")
    stored = await candidates.insert_candidate(
        ProposedCandidate(predicate="likes", value_text=_CANDIDATE_CANARY, value_key="canario"),
        subject_person_id=owner,
        asserted_by_person_id=owner,
        channel=CandidateChannel.VOICE_CLASSIC,
        correlation_id=uuid4(),
        now=_NOW,
    )
    assert stored.candidate_id is not None
    await db.get_conn().commit()
    assert _CANDIDATE_CANARY.encode() in _file_bytes(store)

    await candidates.mark_offered(stored.candidate_id, owner, correlation_id=uuid4(), now=_NOW)
    await candidates.resolve_candidate(
        stored.candidate_id, owner, to=CandidateStatus.REJECTED, correlation_id=uuid4(), now=_NOW
    )

    assert await db.checkpoint_wal() is True
    assert _CANDIDATE_CANARY.encode() not in _file_bytes(store)


async def test_a_deleted_record_leaves_no_text_or_vector_byte_in_the_file_or_the_log(
    store: Path,
) -> None:
    """Deleting a record erases its turn, recall unit, FTS5 tokens and vector from the bytes."""
    owner = await upsert_entity(name="Canary Owner", type="person")
    turn = RecordedTurn(
        at=_NOW,
        heard=_TURN_CANARY,
        said="respuesta",
        voice=TurnVerdict.VERIFIED,
        correlation_id=_CID,
    )
    record_id = await conversation_record.append_turn(
        turn, owner_entity_id=owner, now=_NOW, index=_index_turn
    )
    await _link_candidate_and_topic_to_the_turn(owner)
    unit_ids = [unit_id for unit_id, _ in await recall_store.units_without_vector(10)]
    assert len(unit_ids) == 1
    assert await recall_store.store_vector(unit_ids[0], _VECTOR, model=_MODEL) is True
    await db.get_conn().commit()

    # Sanity: the canary text and the vector bytes ARE in the files before the deletion.
    live = _file_bytes(store)
    assert _TURN_CANARY.encode() in live
    assert _TURN_TOKEN_LOWER in live
    assert _VECTOR_BYTES in live
    assert _VECTOR_SLICE in live
    assert _LINKED_CANDIDATE_CANARY.encode() in live
    assert _LINKED_TOPIC_CANARY.encode() in live

    assert await forget_record(record_id, now=_NOW) is True

    assert await db.checkpoint_wal() is True
    after = _file_bytes(store)
    assert _TURN_CANARY.encode() not in after
    assert _TURN_TOKEN_LOWER not in after
    assert _VECTOR_BYTES not in after
    assert _VECTOR_SLICE not in after
    assert _LINKED_CANDIDATE_CANARY.encode() not in after
    assert _LINKED_TOPIC_CANARY.encode() not in after


_FACT_CANARY = "canario-hecho-7Q2X"
_EPISODE_CANARY = "canario-episodio-7Q2X"


async def test_a_fact_a_turn_and_an_episode_forgotten_leave_no_byte(store: Path) -> None:
    """Plan 0086 D-12: the deletion protocol leaves nothing of the three in the file or the log."""
    owner = await upsert_entity(name="Canary Owner", type="person")
    likes = resolve_predicate("likes")
    assert likes is not None
    fact = await assert_literal_fact(subject_entity_id=owner, definition=likes, value=_FACT_CANARY)
    turn = RecordedTurn(
        at=_NOW,
        heard=_TURN_CANARY,
        said="respuesta",
        voice=TurnVerdict.VERIFIED,
        correlation_id=_CID,
    )
    record_id = await conversation_record.append_turn(
        turn, owner_entity_id=owner, now=_NOW, index=_index_turn
    )
    unit_ids = [unit_id for unit_id, _ in await recall_store.units_without_vector(10)]
    assert await recall_store.store_vector(unit_ids[0], _VECTOR, model=_MODEL) is True
    async with db.transaction() as conn:
        turn_id = await conversation_record.find_turn_id(conn, _CID)
        await conn.execute(
            "INSERT INTO conversation_episodes (source_record_id, owner_entity_id, visibility, "
            "sensitivity, summary, model, created_at, expires_at) "
            "VALUES (?, ?, 'personal', 'normal', ?, 'canary', ?, ?)",
            (record_id, owner, _EPISODE_CANARY, instant_text(_NOW), instant_text(_NOW)),
        )
    assert turn_id is not None
    live = _file_bytes(store)
    for canary in (_FACT_CANARY, _TURN_CANARY, _EPISODE_CANARY):
        assert canary.encode() in live
    assert _VECTOR_BYTES in live

    result = await forget(
        [
            Deletion(DeletionKind.LITERAL_FACT, fact.id),
            Deletion(DeletionKind.TURN, turn_id),
            Deletion(DeletionKind.EPISODE, record_id),
        ],
        now=_NOW,
    )

    assert result.checkpointed is True
    after = _file_bytes(store)
    for canary in (_FACT_CANARY, _TURN_CANARY, _EPISODE_CANARY):
        assert canary.encode() not in after
    assert _TURN_TOKEN_LOWER not in after
    assert _VECTOR_BYTES not in after
    assert _VECTOR_SLICE not in after
