"""The database health check (Plan 0085 D-11): counts only, a planted fault per measure.

A clean database passes; each measure sees the fault planted for it; the printed report carries
no value of the database (canaries only).
"""

# ruff: noqa: S608 - planted rows are built from fixture ints and fixed canaries; no input reaches the SQL.
from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
import sqlite3
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from server.admin_cli import AdminRequest, run_admin_command
from server.exceptions import BrainMemoryError
from server.memory import db_health, document_store, recall_store
from server.memory.conversation_types import RecordedTurn, TurnVerdict
from server.memory.db_health import HealthReport, check_health, health_failed, render_health
from server.memory.declarative import upsert_entity
from server.memory.document_store import NewSection, NewSource
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from pathlib import Path

    import aiosqlite

pytestmark = pytest.mark.integration

_SAID = datetime(2026, 11, 3, 15, tzinfo=UTC)
_FUTURE = "2027-11-03T10:00:00.000000+00:00"
_VECTOR = [1.0] + [0.0] * 767
_CANARY = "Zeta canary"


@pytest.fixture
async def health_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    """A migrated database with one owner, one record and one unit with a vector of the model."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "health.db")
    monkeypatch.setattr(settings, "embedding_model", "canary-model-a")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        owner = await upsert_entity(name="Canary Owner", type="person")
        record_id = await _record(owner)
        unit_id = await _unit(owner, record_id, "el cerro")
        assert await recall_store.store_vector(unit_id, _VECTOR, model="canary-model-a")
        yield owner
    finally:
        await db.close_db()
        db._conn = None


async def _record(owner: int) -> int:
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "INSERT INTO conversation_records (owner_entity_id, started_at, last_turn_at, "
            "closed_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (owner, _FUTURE, _FUTURE, _FUTURE, _FUTURE),
        )
        record_id = int(cursor.lastrowid or 0)
        await cursor.close()
    return record_id


async def _unit(owner: int, record_id: int, heard: str) -> int:
    turn = RecordedTurn(
        at=_SAID, heard=heard, said="ok", voice=TurnVerdict.VERIFIED, correlation_id=uuid4()
    )
    async with db.transaction() as conn:
        return await recall_store.insert_turn_unit(
            conn, record_id=record_id, owner_entity_id=owner, turn=turn
        )


async def _plant(
    *statements: str, check_constraints: bool = True, foreign_keys: bool = True
) -> None:
    """Write the faulty rows the schema itself would refuse, then restore the safeguards."""
    conn = db.get_conn()
    await conn.execute(f"PRAGMA foreign_keys = {'ON' if foreign_keys else 'OFF'}")
    await conn.execute(f"PRAGMA ignore_check_constraints = {'OFF' if check_constraints else 'ON'}")
    try:
        async with db.transaction() as tx:
            for statement in statements:
                await tx.execute(statement)
    finally:
        await conn.execute("PRAGMA ignore_check_constraints = OFF")
        await conn.execute("PRAGMA foreign_keys = ON")


def _faults(report: HealthReport) -> dict[str, int]:
    """The measures that count a fault (not the pending work)."""
    return {
        "integrity_errors": report.integrity_errors,
        "foreign_key_violations": report.foreign_key_violations,
        "fts_errors": report.fts_errors,
        "vectors_without_unit": report.vectors_without_unit,
        "units_without_fts_row": report.units_without_fts_row,
        "face_vectors_without_profile": report.face_vectors_without_profile,
        "times_outside_format": report.times_outside_format,
        "rows_unlinked_from_their_turn": report.rows_unlinked_from_their_turn,
        "document_vectors_without_section": report.document_vectors_without_section,
        "sections_without_fts_row": report.sections_without_fts_row,
    }


async def test_a_clean_database_passes(health_db: int) -> None:
    report = await check_health(db.get_conn())

    assert _faults(report) == dict.fromkeys(_faults(report), 0)
    assert report.units_without_vector == 0
    assert report.units_of_another_model == 0
    assert not health_failed(report)
    assert report.sqlite_version >= db.SQLITE_FLOOR
    assert report.vec_version == (0, 1, 9)


async def test_the_report_is_made_of_ints_only(health_db: int) -> None:
    report = await check_health(db.get_conn())

    for value in vars(report).values():
        parts = value if isinstance(value, tuple) else (value,)
        assert all(isinstance(part, int) for part in parts)


async def test_integrity_check_sees_a_row_the_schema_refuses(health_db: int) -> None:
    await _plant("UPDATE recall_units SET visibility = 'other'", check_constraints=False)

    report = await check_health(db.get_conn())

    assert report.integrity_errors >= 1
    assert {k: v for k, v in _faults(report).items() if k != "integrity_errors"} == dict.fromkeys(
        (
            "foreign_key_violations",
            "fts_errors",
            "vectors_without_unit",
            "units_without_fts_row",
            "face_vectors_without_profile",
            "times_outside_format",
            "rows_unlinked_from_their_turn",
            "document_vectors_without_section",
            "sections_without_fts_row",
        ),
        0,
    )
    assert health_failed(report)


async def test_foreign_key_check_sees_a_row_without_its_parent(health_db: int) -> None:
    await _plant(
        "INSERT INTO face_profiles (entity_id, label, created_at) "
        "VALUES (9999, 'canary', '2026-11-03T15:00:00.000000+00:00')",
        foreign_keys=False,
    )

    report = await check_health(db.get_conn())

    assert report.foreign_key_violations == 1
    assert health_failed(report)


async def test_fts_integrity_check_sees_a_missing_index_row(health_db: int) -> None:
    await _plant(
        "INSERT INTO recall_units_fts (recall_units_fts, rowid, body) "
        "SELECT 'delete', id, body FROM recall_units"
    )

    report = await check_health(db.get_conn())

    assert report.fts_errors == 1
    assert report.units_without_fts_row == 1
    assert health_failed(report)


async def test_a_locked_database_is_not_reported_as_a_damaged_index(
    health_db: int,
) -> None:
    """The ``integrity-check`` command writes: a lock held by another process stops the check."""
    conn = db.get_conn()
    await conn.execute("PRAGMA busy_timeout = 0")
    other = sqlite3.connect(settings.brain_db_path, isolation_level=None)
    try:
        other.execute("BEGIN IMMEDIATE")

        with pytest.raises(BrainMemoryError, match="could not run"):
            await check_health(conn)
    finally:
        other.close()
        await conn.execute("PRAGMA busy_timeout = 5000")


async def test_a_vector_without_its_unit_is_an_orphan(health_db: int) -> None:
    await _plant(
        "INSERT INTO recall_units_vec (rowid, owner_entity_id, sensitivity, embedding) "
        f"VALUES (9999, {health_db}, 'normal', vec_f32('[{', '.join(['0.5'] * 768)}]'))"
    )

    report = await check_health(db.get_conn())

    assert report.vectors_without_unit == 1
    assert health_failed(report)


async def test_a_face_vector_without_a_profile_is_an_orphan(health_db: int) -> None:
    await _plant(
        f"INSERT INTO vec_faces (rowid, embedding) VALUES (9999, vec_f32('[{', '.join(['0.5'] * 512)}]'))"
    )

    report = await check_health(db.get_conn())

    assert report.face_vectors_without_profile == 1
    assert health_failed(report)


async def test_a_time_outside_the_format_is_counted(health_db: int) -> None:
    await _plant(
        f"UPDATE entities SET created_at = '2026-11-03 15:00:00' WHERE id = {health_db}",
        "INSERT INTO meta (key, value, updated_at) VALUES ('canary', 'x', '2026-11-03T15:00:00+00:00')",
    )

    report = await check_health(db.get_conn())

    assert report.times_outside_format == 2
    assert health_failed(report)


async def test_an_impossible_calendar_instant_is_counted(health_db: int) -> None:
    await _plant("UPDATE entities SET created_at = '2026-02-31T15:00:00.000000+00:00'")

    assert (await check_health(db.get_conn())).times_outside_format == 1


async def test_a_validity_bound_that_is_not_a_day_or_a_month_is_counted(health_db: int) -> None:
    await _plant(
        "INSERT INTO literal_facts_v4 (subject_entity_id, predicate, value_text, confidence, "
        "asserted_at, valid_from, lifecycle, visibility, sensitivity) "
        f"VALUES ({health_db}, 'canary_predicate', 'canary value', 1.0, "
        "'2026-11-03T15:00:00.000000+00:00', '2026-11-03T15:00:00.000000+00:00', "
        "'active', 'personal', 'normal')"
    )

    assert (await check_health(db.get_conn())).times_outside_format == 1


async def test_a_day_and_a_month_are_valid_bounds(health_db: int) -> None:
    await _plant(
        "INSERT INTO literal_facts_v4 (subject_entity_id, predicate, value_text, confidence, "
        "asserted_at, valid_from, valid_to, lifecycle, visibility, sensitivity) "
        f"VALUES ({health_db}, 'canary_predicate', 'canary value', 1.0, "
        "'2026-11-03T15:00:00.000000+00:00', '2026-11-03', '2026-12', "
        "'active', 'personal', 'normal')"
    )

    assert (await check_health(db.get_conn())).times_outside_format == 0


# A row derived from a turn, written with no link to the turn (what the C2 deletion would miss).
_UNLINKED_ROWS = {
    "recall_units": (
        "INSERT INTO recall_units (owner_entity_id, source_record_id, kind, body, said_at, "
        "visibility, sensitivity, correlation_id{link_column}) VALUES ({owner}, {record}, 'turn', "
        "'palabra canario', '{at}', 'personal', 'normal', '{cid}'{link_value})"
    ),
    "memory_candidates": (
        "INSERT INTO memory_candidates (subject_person_id, asserted_by_person_id, predicate, "
        "value_text, value_key, status, channel, source_correlation_id, proposed_at, expires_at"
        "{link_column}) VALUES ({owner}, {owner}, 'likes', 'canario', '{cid}', 'proposed', "
        "'voice_classic', '{cid}', '{at}', '{at}'{link_value})"
    ),
    "pending_topics": (
        "INSERT INTO pending_topics (owner_entity_id, source_record_id, correlation_id, said_day, "
        "due_day, heard, state, sensitivity, created_at{link_column}) VALUES ({owner}, {record}, "
        "'{cid}', '2026-11-16', '2026-11-17', 'voy al banco', 'unnamed', 'normal', '{at}'"
        "{link_value})"
    ),
}
_LINK_COLUMN = {
    "recall_units": "turn_id",
    "memory_candidates": "source_turn_id",
    "pending_topics": "source_turn_id",
}


async def _stored_turn(record_id: int, cid: str) -> int:
    """Store a turn row with *cid* and return its id."""
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "INSERT INTO conversation_turns (record_id, correlation_id, said_at, verdict, heard, "
            "said) VALUES (?, ?, ?, 'verified', 'hola', 'ok')",
            (record_id, cid, _FUTURE),
        )
        turn_id = int(cursor.lastrowid or 0)
        await cursor.close()
    return turn_id


def _unlinked_row(table: str, *, owner: int, record: int, cid: str, turn_id: int | None) -> str:
    return _UNLINKED_ROWS[table].format(
        owner=owner,
        record=record,
        cid=cid,
        at=_FUTURE,
        link_column="" if turn_id is None else f", {_LINK_COLUMN[table]}",
        link_value="" if turn_id is None else f", {turn_id}",
    )


@pytest.mark.parametrize("table", list(_UNLINKED_ROWS))
async def test_a_derived_row_unlinked_from_a_stored_turn_is_a_fault(
    health_db: int, table: str
) -> None:
    record_id = await _record(health_db)
    cid = str(uuid4())
    await _stored_turn(record_id, cid)
    await _plant(_unlinked_row(table, owner=health_db, record=record_id, cid=cid, turn_id=None))

    report = await check_health(db.get_conn())

    assert report.rows_unlinked_from_their_turn == 1
    assert health_failed(report)


@pytest.mark.parametrize("table", list(_UNLINKED_ROWS))
async def test_a_derived_row_with_no_stored_turn_or_with_its_link_is_not_a_fault(
    health_db: int, table: str
) -> None:
    record_id = await _record(health_db)
    linked_cid = str(uuid4())
    turn_id = await _stored_turn(record_id, linked_cid)
    await _plant(
        # The turn was never stored (the record was off, or the turn purged): nothing to link.
        _unlinked_row(table, owner=health_db, record=record_id, cid=str(uuid4()), turn_id=None),
        _unlinked_row(table, owner=health_db, record=record_id, cid=linked_cid, turn_id=turn_id),
    )

    report = await check_health(db.get_conn())

    assert report.rows_unlinked_from_their_turn == 0
    assert not health_failed(report)


async def test_pending_embedding_work_is_counted_and_is_not_a_fault(health_db: int) -> None:
    await _unit(health_db, await _record(health_db), "la playa")
    unit_id = await _unit(health_db, await _record(health_db), "el río")
    assert await recall_store.store_vector(unit_id, _VECTOR, model="canary-model-old")

    report = await check_health(db.get_conn())

    assert report.units_without_vector == 1
    assert report.units_of_another_model == 1
    assert not health_failed(report)


async def _document(owner: int, bodies: list[str]) -> list[int]:
    """One canary document of *owner*; returns its section ids in order."""
    sections = [NewSection(position=i, heading="", body=body) for i, body in enumerate(bodies)]
    source = NewSource(
        owner_entity_id=owner,
        title="Manual canario",
        file_sha256="d" * 64,
        format="md",
        level="normal",
        channel="admin_local",
        loaded_at=_FUTURE.replace("2027", "2026"),
        loaded_by_entity_id=owner,
    )
    async with db.transaction() as conn:
        source_id = await document_store.insert_source(conn, source=source, sections=sections)
    cursor = await db.get_conn().execute(
        "SELECT id FROM document_sections WHERE source_id = ? ORDER BY position", (source_id,)
    )
    ids = [int(row[0]) for row in await cursor.fetchall()]
    await cursor.close()
    return ids


async def test_a_document_vector_without_its_section_is_an_orphan(health_db: int) -> None:
    await _plant(
        "INSERT INTO document_sections_vec (rowid, owner_entity_id, level, source_id, embedding) "
        f"VALUES (9999, {health_db}, 'normal', 1, vec_f32('[{', '.join(['0.5'] * 768)}]'))"
    )

    report = await check_health(db.get_conn())

    assert report.document_vectors_without_section == 1
    assert health_failed(report)


async def test_a_section_missing_from_its_word_index_is_a_fault(health_db: int) -> None:
    (section,) = await _document(health_db, ["zzfiltro canario"])
    await _plant(
        "INSERT INTO document_sections_fts (document_sections_fts, rowid, heading, body) "
        f"VALUES ('delete', {section}, '', 'zzfiltro canario')"
    )

    report = await check_health(db.get_conn())

    assert report.sections_without_fts_row == 1
    assert health_failed(report)


async def test_pending_document_work_is_counted_and_is_not_a_fault(health_db: int) -> None:
    old, refused, _pending = await _document(health_db, ["zzuno", "zzdos", "zztres"])
    assert await document_store.store_section_vector(old, _VECTOR, model="canary-model-old")
    assert await document_store.mark_section_refused(refused, model="canary-model-a")

    report = await check_health(db.get_conn())

    assert (report.sections_without_vector, report.sections_of_another_model) == (1, 1)
    assert report.sections_refused == 1
    assert not health_failed(report)


async def _digest(conn: aiosqlite.Connection) -> list[tuple[str, list[tuple[object, ...]]]]:
    """Every row of every ordinary table, in a fixed order: a change to any row changes it."""
    cursor = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND substr(name, 1, 7) <> 'sqlite_' ORDER BY name"
    )
    names = [str(row[0]) for row in await cursor.fetchall()]
    await cursor.close()
    digest = []
    for name in names:
        cursor = await conn.execute(f'SELECT * FROM "{name}" ORDER BY 1')
        digest.append((name, [tuple(row) for row in await cursor.fetchall()]))
        await cursor.close()
    return digest


async def test_check_health_changes_no_row_and_leaves_no_transaction(health_db: int) -> None:
    await _plant("UPDATE entities SET created_at = '2026-11-03 15:00:00'")
    conn = db.get_conn()
    before = await _digest(conn)

    await check_health(conn)

    assert await _digest(conn) == before
    assert not conn.in_transaction


# --- the printed report and the command -----------------------------------------------------------


def _sink() -> tuple[list[str], Callable[[str], None]]:
    lines: list[str] = []
    return lines, lines.append


async def _run_health(write: Callable[[str], None]) -> int:
    def refuse(_prompt: str) -> str:
        raise AssertionError("the health command asks nothing")

    await db.close_db()
    db._conn = None
    return await run_admin_command(
        AdminRequest(command="health"),
        read_text=refuse,
        read_secret=refuse,
        write_text=write,
        now="2026-11-03T15:00:00.000000+00:00",
    )


async def test_the_health_command_on_a_clean_database_exits_zero(health_db: int) -> None:
    lines, write = _sink()

    assert await _run_health(write) == 0

    text = "\n".join(lines)
    assert "errores de integridad: 0" in text
    assert "SQLite 3." in text
    assert "sqlite-vec v0.1.9" in text


async def test_the_health_command_needs_no_owner_and_no_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "empty.db")
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    lines, write = _sink()

    assert await _run_health(write) == 0
    assert any("errores de integridad: 0" in line for line in lines)


async def test_the_health_command_exits_one_on_a_fault_and_prints_no_value(
    health_db: int,
) -> None:
    await _plant(
        f"UPDATE entities SET name = '{_CANARY}', created_at = '{_CANARY} 2026' WHERE id = {health_db}"
    )
    lines, write = _sink()

    assert await _run_health(write) == 1

    text = "\n".join(lines)
    assert "filas fuera del formato de hora: 1" in text
    assert _CANARY not in text
    assert "Canary" not in text
    assert "el cerro" not in text


def test_every_count_of_the_report_is_listed_once_in_the_measures() -> None:
    counted = [field.name for field in dataclasses.fields(HealthReport) if field.type == "int"]
    listed = [name for name, _label, _is_fault in db_health._MEASURES]

    assert counted
    assert sorted(listed) == sorted(counted)


def test_render_health_names_every_measure_in_spanish() -> None:
    report = HealthReport(
        sqlite_version=(3, 50, 4),
        vec_version=(0, 1, 9),
        integrity_errors=1,
        foreign_key_violations=2,
        fts_errors=1,
        vectors_without_unit=3,
        units_without_fts_row=4,
        face_vectors_without_profile=5,
        times_outside_format=6,
        rows_unlinked_from_their_turn=9,
        document_vectors_without_section=10,
        sections_without_fts_row=11,
        units_without_vector=7,
        units_of_another_model=8,
        sections_without_vector=12,
        sections_of_another_model=13,
        sections_refused=14,
    )

    text = "\n".join(render_health(report))

    for line in (
        "errores de integridad: 1",
        "violaciones de claves foráneas: 2",
        "errores del índice de texto: 1",
        "vectores sin unidad: 3",
        "unidades sin fila en el índice de texto: 4",
        "vectores de caras sin perfil: 5",
        "filas fuera del formato de hora: 6",
        "filas sin vínculo con su turno: 9",
        "unidades sin vector (pendientes): 7",
        "unidades de otro modelo (pendientes): 8",
        "SQLite 3.50.4",
        "sqlite-vec v0.1.9",
    ):
        assert line in text
