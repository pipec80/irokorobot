"""Physical deletion proven at the byte level (Plan 0085, decision D-4).

A canary is written to a plain row (a memory candidate) and to a recall unit, so FTS5 and the
``vec0`` table hold it too. Each is erased through its store; after a checkpoint that reports
success, neither the database file nor its write-ahead log holds the canary text or its vector
bytes. This proves the SQLite files, not the storage medium (that is encryption, ADR 0033).
Invented canaries only.
"""

from __future__ import annotations

from datetime import UTC, datetime
import struct
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from server.memory import candidates, conversation_record, recall_store
from server.memory.candidate_types import CandidateChannel, CandidateStatus, ProposedCandidate
from server.memory.conversation_types import RecordedTurn, TurnVerdict
from server.memory.declarative import upsert_entity
from server.memory.embeddings import EMBEDDING_DIM
from server.settings import settings

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


async def _index_turn(conn: aiosqlite.Connection, record_id: int, turn: RecordedTurn) -> None:
    """Index the appended turn as a recall unit, inside the append's transaction."""
    owner_cursor = await conn.execute(
        "SELECT owner_entity_id FROM conversation_records WHERE id = ?", (record_id,)
    )
    row = await owner_cursor.fetchone()
    await owner_cursor.close()
    assert row is not None
    await recall_store.insert_turn_unit(
        conn, record_id=record_id, owner_entity_id=int(row[0]), turn=turn
    )


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

    assert await conversation_record.delete_record(record_id) is True

    assert await db.checkpoint_wal() is True
    after = _file_bytes(store)
    assert _TURN_CANARY.encode() not in after
    assert _TURN_TOKEN_LOWER not in after
    assert _VECTOR_BYTES not in after
    assert _VECTOR_SLICE not in after
