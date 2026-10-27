"""Migration 011: care contacts and the commissioning record (Plan 0070 Task 5, ADR 0024).

The checks and the partial unique indexes are the last line of defence of two writers that
validate first: every one of them is exercised with raw SQL so a writer bug cannot hide it.
Phones are invented (`+56900000001`); labels are canaries.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest
from server.memory.declarative import upsert_entity
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_PHONE = "+56900000001"
_TABLES = {"care_contacts", "commissioning_records", "commissioning_sections"}


@pytest.fixture
async def v11_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "migration-011.db")
    db._conn = None
    try:
        await db.open_db()
        # Scope this migration-011 suite to migrations up to 11, so a later migration does not
        # change the version this file pins (Plan 0073 added 012).
        monkeypatch.setattr(db, "_MIGRATIONS", tuple(m for m in db._MIGRATIONS if m[0] <= 11))
        await db.run_migrations()
        yield
    finally:
        await db.close_db()
        db._conn = None


@pytest.fixture
async def v10_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[tuple[int, str], ...]]:
    """A database migrated only to version 10; yields the full migration list for the upgrade."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "upgrade-v10.db")
    db._conn = None
    try:
        await db.open_db()
        # Scope this migration-011 suite to migrations up to 11: start at 10, upgrade to 11.
        up_to_eleven = tuple(m for m in db._MIGRATIONS if m[0] <= 11)
        monkeypatch.setattr(db, "_MIGRATIONS", tuple(m for m in up_to_eleven if m[0] <= 10))
        await db.run_migrations()
        yield up_to_eleven
    finally:
        await db.close_db()
        db._conn = None


async def _scalar(sql: str, *params: object) -> object:
    cursor = await db.get_conn().execute(sql, params)
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return row[0]


async def _tables() -> set[str]:
    cursor = await db.get_conn().execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    names = {str(row[0]) for row in await cursor.fetchall()}
    await cursor.close()
    return names


async def _people(count: int) -> list[int]:
    return [await upsert_entity(name=f"Canary Person {n}", type="person") for n in range(count)]


async def _contact(owner: int, contact: int, **overrides: object) -> None:
    columns = {
        "owner_entity_id": owner,
        "contact_entity_id": contact,
        "role": "caregiver",
        "phone": _PHONE,
        "channel": "import_assisted",
        "confirmed_at": "2026-10-23T10:00:00+00:00",
        **overrides,
    }
    names = ", ".join(columns)
    marks = ", ".join("?" for _ in columns)
    await db.get_conn().execute(
        f"INSERT INTO care_contacts ({names}) VALUES ({marks})",  # noqa: S608
        tuple(columns.values()),
    )
    await db.get_conn().commit()


async def _record(**overrides: object) -> None:
    columns = {
        "installation_id": "0" * 36,
        "started_at": "2026-10-23T10:00:00+00:00",
        "interviewer_label": "Canary Interviewer",
        "interviewer_role": "family",
        "confirmation_mode": "owner_in_person",
        "disk_encryption": "unknown",
        "pool_version": 1,
        **overrides,
    }
    names = ", ".join(columns)
    marks = ", ".join("?" for _ in columns)
    await db.get_conn().execute(
        f"INSERT INTO commissioning_records ({names}) VALUES ({marks})",  # noqa: S608
        tuple(columns.values()),
    )
    await db.get_conn().commit()


# --- the migration itself -----------------------------------------------------------------------


async def test_a_fresh_database_is_at_version_eleven_with_the_three_tables(v11_db: None) -> None:
    assert await _scalar("PRAGMA user_version") == 11
    assert await _tables() >= _TABLES


async def test_a_version_ten_database_upgrades_in_place_without_losing_a_row(
    v10_db: tuple[tuple[int, str], ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, child = await _people(2)
    conn = db.get_conn()
    await conn.execute(
        "INSERT INTO literal_facts_v4 (subject_entity_id, predicate, value_text) "
        "VALUES (?, 'likes', 'el tren')",
        (child,),
    )
    await conn.execute(
        "INSERT INTO entity_relations_v4 (source_entity_id, predicate, target_entity_id) "
        "VALUES (?, 'child_of', ?)",
        (child, owner),
    )
    await conn.commit()
    assert not _TABLES & await _tables()

    monkeypatch.setattr(db, "_MIGRATIONS", v10_db)
    await db.run_migrations()

    assert await _scalar("PRAGMA user_version") == 11
    assert await _tables() >= _TABLES
    assert await _scalar("SELECT COUNT(*) FROM entities") == 2
    assert await _scalar("SELECT COUNT(*) FROM literal_facts_v4") == 1
    assert await _scalar("SELECT COUNT(*) FROM entity_relations_v4") == 1


async def test_running_the_migrations_twice_changes_nothing(v11_db: None) -> None:
    owner, contact = await _people(2)
    await _contact(owner, contact)

    await db.run_migrations()

    assert await _scalar("PRAGMA user_version") == 11
    assert await _scalar("SELECT COUNT(*) FROM care_contacts") == 1


# --- every CHECK rejects a value outside its list -----------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"phone": "0900000001"},
        {"phone": "56900000001"},
        {"phone": "+0900000001"},
        {"phone": "+5690"},
        {"phone": "+5690000000000000"},
        {"phone_alt": "0900000001"},
        {"role": "boss"},
        {"call_order": 0},
        {"has_key": 2},
        {"may_receive_health_info": 2},
        {"may_view_activity": -1},
        {"visibility": "household"},
        {"sensitivity": "normal"},
        {"sensitivity": "security"},
        {"relationship": ""},
        {"relationship": "x" * 41},
    ],
)
async def test_a_care_contact_check_rejects_a_value_outside_its_list(
    v11_db: None, overrides: dict[str, object]
) -> None:
    owner, contact = await _people(2)

    with pytest.raises(sqlite3.IntegrityError):
        await _contact(owner, contact, **overrides)


async def test_a_care_contact_accepts_the_valid_edges(v11_db: None) -> None:
    owner, contact = await _people(2)

    await _contact(
        owner,
        contact,
        phone="+12345678",
        phone_alt="+123456789012345",
        relationship="x" * 40,
        call_order=1,
        sensitivity="location",
        has_key=1,
    )

    assert await _scalar("SELECT COUNT(*) FROM care_contacts") == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"interviewer_role": "boss"},
        {"confirmation_mode": "telepathy"},
        {"confirmation_mode": "builder_is_owner", "interviewer_role": "family"},
        {"disk_encryption": "maybe"},
        {"interviewer_label": ""},
        {"interviewer_label": "x" * 81},
        {"installation_id": "short"},
        {"pool_version": None},
    ],
)
async def test_a_commissioning_record_check_rejects_a_value_outside_its_list(
    v11_db: None, overrides: dict[str, object]
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        await _record(**overrides)


async def test_the_builder_may_be_the_owner(v11_db: None) -> None:
    await _record(confirmation_mode="builder_is_owner", interviewer_role="builder")

    assert await _scalar("SELECT COUNT(*) FROM commissioning_records") == 1


@pytest.mark.parametrize(
    "section,status",
    [("maybe", "provided"), ("conditions", "maybe"), ("allergies", "")],
)
async def test_a_section_check_rejects_a_section_or_status_outside_its_list(
    v11_db: None, section: str, status: str
) -> None:
    await _record()
    with pytest.raises(sqlite3.IntegrityError):
        await db.get_conn().execute(
            "INSERT INTO commissioning_sections (commissioning_id, section, status, recorded_at) "
            "VALUES (1, ?, ?, '2026-10-23T10:00:00+00:00')",
            (section, status),
        )


async def test_the_eleven_sections_and_five_statuses_are_accepted(v11_db: None) -> None:
    await _record()
    sections = [
        "conditions",
        "allergies",
        "medications",
        "devices",
        "contacts",
        "withhold",
        "secrets",
        "documents",
        "household",
        "home",
        "function",
    ]
    statuses = ["provided", "none", "unknown", "declined", "not_asked"]
    for index, section in enumerate(sections):
        await db.get_conn().execute(
            "INSERT INTO commissioning_sections (commissioning_id, section, status, recorded_at) "
            "VALUES (1, ?, ?, '2026-10-23T10:00:00+00:00')",
            (section, statuses[index % len(statuses)]),
        )
    await db.get_conn().commit()

    assert await _scalar("SELECT COUNT(*) FROM commissioning_sections") == 11


async def test_a_section_status_is_one_row_per_record_and_section(v11_db: None) -> None:
    await _record()
    insert = (
        "INSERT INTO commissioning_sections (commissioning_id, section, status, recorded_at) "
        "VALUES (1, 'home', 'provided', '2026-10-23T10:00:00+00:00')"
    )
    await db.get_conn().execute(insert)

    with pytest.raises(sqlite3.IntegrityError):
        await db.get_conn().execute(insert)


async def test_deleting_a_record_deletes_its_sections(v11_db: None) -> None:
    await _record()
    await db.get_conn().execute(
        "INSERT INTO commissioning_sections (commissioning_id, section, status, recorded_at) "
        "VALUES (1, 'home', 'provided', '2026-10-23T10:00:00+00:00')"
    )
    await db.get_conn().commit()

    await db.get_conn().execute("DELETE FROM commissioning_records WHERE id = 1")
    await db.get_conn().commit()

    assert await _scalar("SELECT COUNT(*) FROM commissioning_sections") == 0


# --- the partial unique indexes really enforce --------------------------------------------------


async def test_one_active_row_per_owner_contact_and_role(v11_db: None) -> None:
    owner, contact = await _people(2)
    await _contact(owner, contact, role="caregiver")

    with pytest.raises(sqlite3.IntegrityError):
        await _contact(owner, contact, role="caregiver", phone="+56900000002")
    await _contact(owner, contact, role="key_holder")

    assert await _scalar("SELECT COUNT(*) FROM care_contacts") == 2


async def test_a_revoked_row_does_not_block_a_new_one(v11_db: None) -> None:
    owner, contact = await _people(2)
    await _contact(owner, contact, call_order=1, revoked_at="2026-10-23T11:00:00+00:00")

    await _contact(owner, contact, call_order=1)

    assert await _scalar("SELECT COUNT(*) FROM care_contacts") == 2


async def test_two_active_contacts_cannot_share_a_call_order_but_may_share_no_order(
    v11_db: None,
) -> None:
    owner, first, second, third = await _people(4)
    await _contact(owner, first, call_order=1)

    with pytest.raises(sqlite3.IntegrityError):
        await _contact(owner, second, call_order=1)
    await _contact(owner, second)
    await _contact(owner, third)

    assert await _scalar("SELECT COUNT(*) FROM care_contacts") == 3


async def test_a_second_open_record_fails_but_one_after_a_closed_record_is_not_blocked(
    v11_db: None,
) -> None:
    await _record()

    with pytest.raises(sqlite3.IntegrityError):
        await _record(installation_id="1" * 36)
    await db.get_conn().execute(
        "UPDATE commissioning_records SET closed_at = '2026-10-23T12:00:00+00:00'"
    )
    await db.get_conn().commit()
    await _record(installation_id="2" * 36)

    assert await _scalar("SELECT COUNT(*) FROM commissioning_records") == 2


async def test_an_entity_a_contact_refers_to_cannot_be_deleted(v11_db: None) -> None:
    owner, contact = await _people(2)
    await _contact(owner, contact)

    for entity_id in (owner, contact):
        with pytest.raises(sqlite3.IntegrityError):
            await db.get_conn().execute("DELETE FROM entities WHERE id = ?", (entity_id,))
