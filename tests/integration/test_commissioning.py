"""The commissioning record: the acta of the alta, with no household value (Plan 0070 Task 7).

ADR 0024 decisions 2, 6, 8, 13 and 15: who interviewed and how the owner confirmed, the hash and
the counts of each import, the status of each section, and the closing that ends the replacement
window. The only free text in it is the interviewer's label (a canary here).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from server.exceptions import CommissioningClosedError, CommissioningError, CommissioningOpenError
from server.memory.commissioning import (
    ENROLLABLE_MODALITIES,
    POOL_VERSION,
    CommissioningInput,
    ConfirmationMode,
    DiskEncryption,
    InterviewerRole,
    Modality,
    Section,
    SectionStatus,
    close_commissioning,
    get_open_commissioning,
    importer_window_open,
    list_section_statuses,
    open_commissioning,
    record_import,
    set_section_status,
)
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_STARTED_AT = "2026-10-23T10:00:00+00:00"
_LATER = "2026-10-23T11:00:00+00:00"
_CLOSED_AT = "2026-10-23T12:00:00+00:00"
_LABEL = "Canary Interviewer"
_HASH = "ab" * 32


@pytest.fixture
async def commissioning_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "commissioning.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        yield
    finally:
        await db.close_db()
        db._conn = None


def _details(
    *,
    label: str = _LABEL,
    role: InterviewerRole = InterviewerRole.FAMILY,
    mode: ConfirmationMode = ConfirmationMode.OWNER_IN_PERSON,
) -> CommissioningInput:
    return CommissioningInput(
        interviewer_label=label,
        interviewer_role=role,
        confirmation_mode=mode,
        disk_encryption=DiskEncryption.UNKNOWN,
    )


async def _open() -> int:
    record = await open_commissioning(_details(), started_at=_STARTED_AT)
    return record.id


async def _count(table: str) -> int:
    cursor = await db.get_conn().execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return int(row[0])


# --- the lists ----------------------------------------------------------------------------------


def test_the_modalities_are_a_closed_list_of_six_and_three_can_be_enrolled() -> None:
    assert {modality.value for modality in Modality} == {
        "pin",
        "face",
        "voice",
        "fingerprint",
        "iris",
        "token",
    }
    assert {modality.value for modality in ENROLLABLE_MODALITIES} == {"pin", "face", "voice"}


def test_the_sections_and_statuses_are_the_closed_lists_of_the_data_pool() -> None:
    assert {section.value for section in Section} == {
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
    }
    assert {status.value for status in SectionStatus} == {
        "provided",
        "none",
        "unknown",
        "declined",
        "not_asked",
    }


# --- opening, reading, importing, closing -------------------------------------------------------


async def test_a_commissioning_is_opened_read_imported_and_closed(commissioning_db: None) -> None:
    opened = await open_commissioning(_details(), started_at=_STARTED_AT)

    assert opened.pool_version == POOL_VERSION
    assert (opened.seed_file_sha256, dict(opened.counts), opened.closed_at) == (None, {}, None)
    assert (opened.interviewer_role, opened.confirmation_mode) == (
        InterviewerRole.FAMILY,
        ConfirmationMode.OWNER_IN_PERSON,
    )
    assert opened.disk_encryption is DiskEncryption.UNKNOWN
    assert await get_open_commissioning() == opened

    await record_import(opened.id, seed_file_sha256=_HASH, counts={"children": 2, "contacts": 3})
    imported = await get_open_commissioning()
    assert imported is not None
    assert imported.seed_file_sha256 == _HASH
    assert dict(imported.counts) == {"children": 2, "contacts": 3}

    await close_commissioning(opened.id, _CLOSED_AT)
    assert await get_open_commissioning() is None


async def test_the_installation_id_is_a_random_uuid_kept_across_imports(
    commissioning_db: None,
) -> None:
    opened = await open_commissioning(_details(), started_at=_STARTED_AT)
    await record_import(opened.id, seed_file_sha256=_HASH, counts={"children": 1})
    await record_import(opened.id, seed_file_sha256="cd" * 32, counts={"children": 2})

    reread = await get_open_commissioning()

    assert reread is not None
    assert len(opened.installation_id) == 36
    assert UUID(opened.installation_id).version == 4
    assert reread.installation_id == opened.installation_id
    assert reread.seed_file_sha256 == "cd" * 32


async def test_two_installations_get_two_different_ids(
    commissioning_db: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = (await open_commissioning(_details(), started_at=_STARTED_AT)).installation_id
    await db.close_db()
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "second.db")
    db._conn = None
    await db.open_db()
    await db.run_migrations()

    second = (await open_commissioning(_details(), started_at=_STARTED_AT)).installation_id

    assert first != second


async def test_the_importer_window_is_open_until_a_commissioning_is_closed(
    commissioning_db: None,
) -> None:
    assert await importer_window_open() is True

    record_id = await _open()
    assert await importer_window_open() is True

    await close_commissioning(record_id, _CLOSED_AT)
    assert await importer_window_open() is False


async def test_a_second_commissioning_is_refused_while_one_is_open(commissioning_db: None) -> None:
    await _open()

    with pytest.raises(CommissioningOpenError):
        await open_commissioning(_details(), started_at=_LATER)

    assert await _count("commissioning_records") == 1


async def test_a_new_commissioning_is_refused_after_one_closed(commissioning_db: None) -> None:
    await close_commissioning(await _open(), _CLOSED_AT)

    with pytest.raises(CommissioningClosedError):
        await open_commissioning(_details(), started_at=_LATER)

    assert await _count("commissioning_records") == 1


async def test_the_errors_are_value_errors_with_a_closed_message(commissioning_db: None) -> None:
    record_id = await _open()
    with pytest.raises(CommissioningOpenError) as already_open:
        await open_commissioning(_details(label="Canary Other"), started_at=_LATER)
    await close_commissioning(record_id, _CLOSED_AT)
    with pytest.raises(CommissioningClosedError) as closed:
        await record_import(record_id, seed_file_sha256=_HASH, counts={})

    for error in (already_open.value, closed.value):
        assert isinstance(error, CommissioningError)
        assert isinstance(error, ValueError)
        assert "Canary" not in str(error) + repr(error)


# --- what is refused before anything is written -------------------------------------------------


@pytest.mark.parametrize("label", ["", "x" * 81, "Canary\nInterviewer", "Canary\x00", "\t"])
async def test_a_label_of_zero_or_81_characters_or_with_a_control_character_is_refused(
    commissioning_db: None, label: str
) -> None:
    with pytest.raises(ValueError, match="interviewer label"):
        await open_commissioning(_details(label=label), started_at=_STARTED_AT)

    assert await _count("commissioning_records") == 0


async def test_a_label_of_one_or_80_characters_is_accepted(commissioning_db: None) -> None:
    record = await open_commissioning(_details(label="x" * 80), started_at=_STARTED_AT)

    assert len(record.interviewer_label) == 80


async def test_builder_is_owner_needs_the_builder_role(commissioning_db: None) -> None:
    with pytest.raises(ValueError, match="builder_is_owner"):
        await open_commissioning(
            _details(role=InterviewerRole.FAMILY, mode=ConfirmationMode.BUILDER_IS_OWNER),
            started_at=_STARTED_AT,
        )
    assert await _count("commissioning_records") == 0

    record = await open_commissioning(
        _details(role=InterviewerRole.BUILDER, mode=ConfirmationMode.BUILDER_IS_OWNER),
        started_at=_STARTED_AT,
    )
    assert record.confirmation_mode is ConfirmationMode.BUILDER_IS_OWNER


@pytest.mark.parametrize(
    "counts",
    [
        {"children": "2"},
        {"children": 2.0},
        {"children": True},
        {"children": -1},
        {"Canary Child": 1},
        {"children of canary": 1},
        {"": 1},
    ],
)
async def test_the_counts_are_integers_under_a_plain_name(
    commissioning_db: None, counts: dict[str, object]
) -> None:
    record_id = await _open()

    with pytest.raises(ValueError, match="counts"):
        await record_import(record_id, seed_file_sha256=_HASH, counts=counts)  # type: ignore[arg-type]  # the bad types are the test

    record = await get_open_commissioning()
    assert record is not None
    assert (record.seed_file_sha256, dict(record.counts)) == (None, {})


@pytest.mark.parametrize("digest", ["", "abc", "AB" * 32, "zz" * 32, "ab" * 33, "Canary Child"])
async def test_the_file_hash_is_64_lowercase_hex_digits(
    commissioning_db: None, digest: str
) -> None:
    record_id = await _open()

    with pytest.raises(ValueError, match="hash"):
        await record_import(record_id, seed_file_sha256=digest, counts={})


async def test_nothing_of_a_household_reaches_the_record_but_the_label(
    commissioning_db: None,
) -> None:
    record_id = await _open()
    await record_import(record_id, seed_file_sha256=_HASH, counts={"children": 2})
    await set_section_status(record_id, Section.CONTACTS, SectionStatus.PROVIDED, _LATER)

    cursor = await db.get_conn().execute("SELECT * FROM commissioning_records")
    (row,) = await cursor.fetchall()
    names = [description[0] for description in cursor.description]
    await cursor.close()
    cursor = await db.get_conn().execute("SELECT * FROM commissioning_sections")
    section_rows = await cursor.fetchall()
    await cursor.close()

    holders = [name for name, value in zip(names, row, strict=True) if "Canary" in str(value)]
    assert holders == ["interviewer_label"]
    assert not any("Canary" in str(value) for section_row in section_rows for value in section_row)


# --- sections -----------------------------------------------------------------------------------


async def test_a_section_is_not_asked_until_somebody_says_otherwise(commissioning_db: None) -> None:
    record_id = await _open()

    statuses = await list_section_statuses(record_id)

    assert set(statuses) == set(Section)
    assert set(statuses.values()) == {SectionStatus.NOT_ASKED}


async def test_a_status_is_set_overwritten_and_listed(commissioning_db: None) -> None:
    record_id = await _open()
    await set_section_status(record_id, Section.ALLERGIES, SectionStatus.NONE, _STARTED_AT)
    await set_section_status(record_id, Section.HOME, SectionStatus.DECLINED, _STARTED_AT)

    await set_section_status(record_id, Section.ALLERGIES, SectionStatus.PROVIDED, _LATER)

    statuses = await list_section_statuses(record_id)
    assert statuses[Section.ALLERGIES] is SectionStatus.PROVIDED
    assert statuses[Section.HOME] is SectionStatus.DECLINED
    assert statuses[Section.CONDITIONS] is SectionStatus.NOT_ASKED
    assert await _count("commissioning_sections") == 2


@pytest.mark.parametrize("section,status", [("maybe", "provided"), ("home", "maybe")])
async def test_a_status_or_section_outside_the_lists_never_reaches_the_database(
    commissioning_db: None, section: str, status: str
) -> None:
    record_id = await _open()

    with pytest.raises(ValueError, match="is not a valid"):
        await set_section_status(record_id, section, status, _LATER)  # type: ignore[arg-type]  # the bad values are the test

    assert await _count("commissioning_sections") == 0


async def test_a_closed_record_rejects_an_import_and_a_status(commissioning_db: None) -> None:
    record_id = await _open()
    await close_commissioning(record_id, _CLOSED_AT)

    with pytest.raises(CommissioningClosedError):
        await record_import(record_id, seed_file_sha256=_HASH, counts={"children": 1})
    with pytest.raises(CommissioningClosedError):
        await set_section_status(record_id, Section.HOME, SectionStatus.PROVIDED, _LATER)
    with pytest.raises(CommissioningClosedError):
        await close_commissioning(record_id, _LATER)

    assert await _count("commissioning_sections") == 0


async def test_an_unknown_record_is_a_value_error(commissioning_db: None) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        await record_import(9999, seed_file_sha256=_HASH, counts={})
    with pytest.raises(ValueError, match="does not exist"):
        await set_section_status(9999, Section.HOME, SectionStatus.NONE, _LATER)
    with pytest.raises(ValueError, match="does not exist"):
        await close_commissioning(9999, _CLOSED_AT)
    with pytest.raises(ValueError, match="does not exist"):
        await list_section_statuses(9999)


# --- transactions and traces --------------------------------------------------------------------


async def _open_then_give_up(message: str) -> None:
    """Write twice inside a transaction the caller owns, then fail."""
    async with db.transaction():
        record = await open_commissioning(
            _details(), started_at=_STARTED_AT, manage_transaction=False
        )
        await set_section_status(
            record.id, Section.HOME, SectionStatus.NONE, _LATER, manage_transaction=False
        )
        raise RuntimeError(message)


async def test_a_write_joined_to_the_callers_transaction_rolls_back_with_it(
    commissioning_db: None,
) -> None:
    message = "the caller gives up"
    with pytest.raises(RuntimeError, match=message):
        await _open_then_give_up(message)

    assert await _count("commissioning_records") == 0
    assert await _count("commissioning_sections") == 0


async def test_no_log_record_holds_the_label(
    commissioning_db: None, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        record_id = await _open()
        await record_import(record_id, seed_file_sha256=_HASH, counts={"children": 1})
        await set_section_status(record_id, Section.HOME, SectionStatus.NONE, _LATER)
        await close_commissioning(record_id, _CLOSED_AT)
        record = await get_open_commissioning()

    assert record is None
    assert caplog.records
    assert all(_LABEL not in record.getMessage() + repr(vars(record)) for record in caplog.records)


async def test_the_repr_of_a_record_and_of_its_input_omits_the_label(
    commissioning_db: None,
) -> None:
    record = await open_commissioning(_details(), started_at=_STARTED_AT)

    assert _LABEL not in repr(record) + repr(_details())
