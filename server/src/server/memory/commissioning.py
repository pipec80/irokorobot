"""The commissioning record: the acta of the alta of the robot (Plan 0070, ADR 0024 decisions 2, 6, 13, 15).

A commissioning is one conversation, before the robot goes into service, in which an interviewer
and the owner fill in the data pool. This module opens the record, stores the hash and the counts
of each import, one status per section ("absence is data") and the closing that ends the
replacement window. It holds **no household value**: the interviewer's label (a person's name)
is its only free text, and it never reaches a log or a ``repr``. Only this module has SQL on
``commissioning_records`` and ``commissioning_sections`` (an architecture guard says so).

The columns for the consents, the modalities enrolled, the backups and the readiness report are
written by a function of Plan 0072.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, nullcontext
from dataclasses import dataclass, field
from enum import StrEnum
import json
import logging
import re
from types import MappingProxyType
from typing import TYPE_CHECKING
from uuid import uuid4

from server import db
from server.db import get_conn
from server.exceptions import CommissioningClosedError, CommissioningOpenError

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "ENROLLABLE_MODALITIES",
    "POOL_VERSION",
    "CommissioningInput",
    "CommissioningRecord",
    "ConfirmationMode",
    "DiskEncryption",
    "InterviewerRole",
    "Modality",
    "Section",
    "SectionStatus",
    "close_commissioning",
    "get_open_commissioning",
    "importer_window_open",
    "list_section_statuses",
    "open_commissioning",
    "record_import",
    "set_section_status",
]

logger = logging.getLogger(__name__)

# The version of the data pool a record was opened with (docs/architecture/seed-data-pool.md).
POOL_VERSION = 1
_EVENT = "memory.commissioning"
_MAX_LABEL = 80
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_SHA256 = re.compile(r"[0-9a-f]{64}")
# A count is named by a plain word, never by a household value (a name would be one).
_COUNT_NAME = re.compile(r"[a-z][a-z0-9_]{0,39}")
_COLUMNS = (
    "id, installation_id, started_at, interviewer_label, interviewer_role, confirmation_mode, "
    "disk_encryption, pool_version, seed_file_sha256, counts_json, closed_at"
)


class InterviewerRole(StrEnum):
    """Who held the interview."""

    BUILDER = "builder"
    FAMILY = "family"
    TECHNICIAN = "technician"
    OTHER = "other"


class ConfirmationMode(StrEnum):
    """How the owner confirmed what was loaded (ADR 0024 decision 6)."""

    OWNER_IN_PERSON = "owner_in_person"
    REPRESENTATIVE = "representative"
    BUILDER_IS_OWNER = "builder_is_owner"


class DiskEncryption(StrEnum):
    """The interviewer's declaration about the disk; the system verifies nothing."""

    DECLARED_YES = "declared_yes"
    DECLARED_NO = "declared_no"
    UNKNOWN = "unknown"


class SectionStatus(StrEnum):
    """What silence means in a section of the pool (ADR 0024 decision 2)."""

    PROVIDED = "provided"
    NONE = "none"
    UNKNOWN = "unknown"
    DECLINED = "declined"
    NOT_ASKED = "not_asked"


class Section(StrEnum):
    """The sections of the data pool that carry a status."""

    CONDITIONS = "conditions"
    ALLERGIES = "allergies"
    MEDICATIONS = "medications"
    DEVICES = "devices"
    CONTACTS = "contacts"
    WITHHOLD = "withhold"
    SECRETS = "secrets"  # pragma: allowlist secret (a section name)
    DOCUMENTS = "documents"
    HOUSEHOLD = "household"
    HOME = "home"
    FUNCTION = "function"


class Modality(StrEnum):
    """Closed inventory of the ways of recognizing the owner (ADR 0024 decision 15).

    The last three are reserved: a new modality is an adapter, its own enrolment and consent and
    an ADR that sets its assurance, never a change of the pool.
    """

    PIN = "pin"
    FACE = "face"
    VOICE = "voice"
    FINGERPRINT = "fingerprint"
    IRIS = "iris"
    TOKEN = "token"  # noqa: S105  # pragma: allowlist secret (a modality name)


ENROLLABLE_MODALITIES = frozenset({Modality.PIN, Modality.FACE, Modality.VOICE})


@dataclass(frozen=True)
class CommissioningInput:
    """What the interviewer declares when the commissioning opens."""

    interviewer_label: str = field(repr=False)
    interviewer_role: InterviewerRole
    confirmation_mode: ConfirmationMode
    disk_encryption: DiskEncryption


@dataclass(frozen=True)
class CommissioningRecord:
    """One commissioning as stored; its ``repr`` omits the interviewer's label."""

    id: int
    installation_id: str
    started_at: str
    interviewer_label: str = field(repr=False)
    interviewer_role: InterviewerRole
    confirmation_mode: ConfirmationMode
    disk_encryption: DiskEncryption
    pool_version: int
    seed_file_sha256: str | None
    counts: Mapping[str, int]
    closed_at: str | None


def _record(values: tuple[object, ...]) -> CommissioningRecord:
    """Build a record from a row selected with ``_COLUMNS``."""
    (
        row_id,
        installation_id,
        started_at,
        label,
        role,
        mode,
        disk,
        pool_version,
        digest,
        counts_json,
        closed_at,
    ) = values
    counts = json.loads(str(counts_json)) if counts_json is not None else {}
    return CommissioningRecord(
        id=int(str(row_id)),
        installation_id=str(installation_id),
        started_at=str(started_at),
        interviewer_label=str(label),
        interviewer_role=InterviewerRole(str(role)),
        confirmation_mode=ConfirmationMode(str(mode)),
        disk_encryption=DiskEncryption(str(disk)),
        pool_version=int(str(pool_version)),
        seed_file_sha256=None if digest is None else str(digest),
        counts=MappingProxyType(counts),
        closed_at=None if closed_at is None else str(closed_at),
    )


def _transaction(manage_transaction: bool) -> AbstractAsyncContextManager[object]:
    """Own a transaction, or join the one the caller owns (``db.transaction`` is not reentrant)."""
    return db.transaction() if manage_transaction else nullcontext()


async def _scalar(sql: str, *params: object) -> object | None:
    cursor = await get_conn().execute(sql, params)
    row = await cursor.fetchone()
    await cursor.close()
    return None if row is None else row[0]


async def importer_window_open() -> bool:
    """Return whether the importer may still run: true while **no** commissioning is closed.

    Before the first record exists the window is open too (the importer opens the record).
    """
    closed = await _scalar("SELECT COUNT(*) FROM commissioning_records WHERE closed_at IS NOT NULL")
    return closed == 0


async def get_open_commissioning() -> CommissioningRecord | None:
    """Return the open commissioning, or ``None`` when none is open."""
    cursor = await get_conn().execute(
        f"SELECT {_COLUMNS} FROM commissioning_records WHERE closed_at IS NULL"  # noqa: S608
    )
    row = await cursor.fetchone()
    await cursor.close()
    return None if row is None else _record(tuple(row))


def _check_details(details: CommissioningInput) -> None:
    """Refuse a label outside 1 to 80 characters or with a control character, and a bad mode."""
    label = details.interviewer_label
    if not 1 <= len(label) <= _MAX_LABEL or _CONTROL_CHARACTERS.search(label):
        raise ValueError("interviewer label must be 1 to 80 printable characters")
    if (
        details.confirmation_mode is ConfirmationMode.BUILDER_IS_OWNER
        and details.interviewer_role is not InterviewerRole.BUILDER
    ):
        raise ValueError("builder_is_owner needs the builder interviewer role")


async def open_commissioning(
    details: CommissioningInput, *, started_at: str, manage_transaction: bool = True
) -> CommissioningRecord:
    """Open the commissioning, with a random installation id derived from nothing about the house.

    Args:
        details: The interviewer's label, role, the confirmation mode and the disk declaration.
        started_at: When it opened, as UTC ISO 8601.
        manage_transaction: ``False`` joins the caller's open transaction.

    Returns:
        The new open record.

    Raises:
        ValueError: For a label outside 1 to 80 printable characters, or ``builder_is_owner``
            with an interviewer who is not the builder.
        CommissioningClosedError: If any commissioning was closed (there is one per robot).
        CommissioningOpenError: If a commissioning is already open.
    """
    _check_details(details)
    async with _transaction(manage_transaction):
        if not await importer_window_open():
            raise CommissioningClosedError
        if await get_open_commissioning() is not None:
            raise CommissioningOpenError
        cursor = await get_conn().execute(
            "INSERT INTO commissioning_records (installation_id, started_at, interviewer_label, "
            "interviewer_role, confirmation_mode, disk_encryption, pool_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid4()),
                started_at,
                details.interviewer_label,
                details.interviewer_role.value,
                details.confirmation_mode.value,
                details.disk_encryption.value,
                POOL_VERSION,
            ),
        )
        record_id = cursor.lastrowid
        await cursor.close()
        if record_id is None:
            raise RuntimeError("INSERT into commissioning_records returned no row id")
        record = await _read(record_id)
    _announce("opened", record.id, committed=manage_transaction)
    return record


async def _read(record_id: int) -> CommissioningRecord:
    """Read one record by id or reject a missing one."""
    cursor = await get_conn().execute(
        f"SELECT {_COLUMNS} FROM commissioning_records WHERE id = ?",  # noqa: S608
        (record_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    if row is None:
        raise ValueError(f"commissioning {record_id} does not exist")
    return _record(tuple(row))


async def _read_open(record_id: int) -> CommissioningRecord:
    """Read a record that must still be open."""
    record = await _read(record_id)
    if record.closed_at is not None:
        raise CommissioningClosedError
    return record


def _check_import(seed_file_sha256: str, counts: Mapping[str, int]) -> None:
    """Refuse a hash that is not 64 lowercase hex digits and counts that are not plain."""
    if _SHA256.fullmatch(seed_file_sha256) is None:
        raise ValueError("the file hash must be 64 lowercase hex digits")
    for name, value in counts.items():
        if _COUNT_NAME.fullmatch(name) is None:
            raise ValueError("counts are named by a plain lowercase word")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("counts must be non-negative integers")


async def record_import(
    record_id: int,
    *,
    seed_file_sha256: str,
    counts: Mapping[str, int],
    manage_transaction: bool = True,
) -> None:
    """Record the hash of the file just imported and how many rows of each kind it wrote.

    A later import of the same commissioning replaces both: the acta keeps the last one.

    Args:
        record_id: The open commissioning.
        seed_file_sha256: SHA-256 of the file, as 64 lowercase hex digits.
        counts: Counts by plain lowercase name; never a household value.
        manage_transaction: ``False`` joins the caller's open transaction.

    Raises:
        ValueError: For a bad hash, a count name or value, or an unknown record.
        CommissioningClosedError: If the commissioning is closed.
    """
    _check_import(seed_file_sha256, counts)
    async with _transaction(manage_transaction):
        await _read_open(record_id)
        await get_conn().execute(
            "UPDATE commissioning_records SET seed_file_sha256 = ?, counts_json = ? WHERE id = ?",
            (seed_file_sha256, json.dumps(dict(sorted(counts.items()))), record_id),
        )
    _announce("import_recorded", record_id, committed=manage_transaction)


async def set_section_status(
    record_id: int,
    section: Section,
    status: SectionStatus,
    recorded_at: str,
    *,
    manage_transaction: bool = True,
) -> None:
    """Set (or overwrite) the status of one section; a status is not a fact.

    Args:
        record_id: The open commissioning.
        section: One of the eleven sections.
        status: One of the five statuses.
        recorded_at: When it was recorded, as UTC ISO 8601.
        manage_transaction: ``False`` joins the caller's open transaction.

    Raises:
        ValueError: For a section or status outside the lists, or an unknown record.
        CommissioningClosedError: If the commissioning is closed.
    """
    valid_section, valid_status = Section(section), SectionStatus(status)
    async with _transaction(manage_transaction):
        await _read_open(record_id)
        await get_conn().execute(
            "INSERT INTO commissioning_sections (commissioning_id, section, status, recorded_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT (commissioning_id, section) "
            "DO UPDATE SET status = excluded.status, recorded_at = excluded.recorded_at",
            (record_id, valid_section.value, valid_status.value, recorded_at),
        )
    _announce("section_set", record_id, committed=manage_transaction)


async def list_section_statuses(record_id: int) -> Mapping[Section, SectionStatus]:
    """Return the status of every section; one nobody recorded is ``not_asked``.

    Args:
        record_id: The commissioning, open or closed.

    Raises:
        ValueError: If the record does not exist.
    """
    await _read(record_id)
    cursor = await get_conn().execute(
        "SELECT section, status FROM commissioning_sections WHERE commissioning_id = ?",
        (record_id,),
    )
    recorded = {Section(str(row[0])): SectionStatus(str(row[1])) for row in await cursor.fetchall()}
    await cursor.close()
    return MappingProxyType({s: recorded.get(s, SectionStatus.NOT_ASKED) for s in Section})


async def close_commissioning(
    record_id: int, closed_at: str, *, manage_transaction: bool = True
) -> None:
    """Close the commissioning: the importer no longer replaces anything (ADR 0024 decision 8).

    Args:
        record_id: The open commissioning.
        closed_at: When it closed, as UTC ISO 8601.
        manage_transaction: ``False`` joins the caller's open transaction.

    Raises:
        ValueError: If the record does not exist.
        CommissioningClosedError: If it was already closed.
    """
    async with _transaction(manage_transaction):
        await _read_open(record_id)
        await get_conn().execute(
            "UPDATE commissioning_records SET closed_at = ? WHERE id = ?", (closed_at, record_id)
        )
    _announce("closed", record_id, committed=manage_transaction)


def _announce(what: str, record_id: int, *, committed: bool) -> None:
    """Log one step by record id and a closed word, only once it is certain to persist."""
    logger.log(
        logging.INFO if committed else logging.DEBUG,
        "Commissioning %s",
        what if committed else f"{what} (staged)",
        extra={"event": _EVENT, "step": what, "record_id": record_id},
    )
