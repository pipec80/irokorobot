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
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from server import db
from server.db import get_conn
from server.exceptions import CommissioningClosedError, CommissioningOpenError

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "ENROLLABLE_MODALITIES",
    "POOL_VERSION",
    "Backup",
    "BackupKind",
    "CommissioningInput",
    "CommissioningRecord",
    "ConfirmationMode",
    "Consents",
    "DiskEncryption",
    "InterviewerRole",
    "Modality",
    "Section",
    "SectionStatus",
    "SessionDetails",
    "clear_section_statuses",
    "close_commissioning",
    "get_open_commissioning",
    "importer_window_open",
    "list_section_statuses",
    "open_commissioning",
    "read_session_details",
    "record_backup",
    "record_biometric_notice",
    "record_consents",
    "record_import",
    "record_modalities",
    "record_readiness",
    "set_section_status",
]

logger = logging.getLogger(__name__)

# The version of the data pool a record was opened with (docs/architecture/seed-data-pool.md).
POOL_VERSION = 1
_EVENT = "memory.commissioning"
_MAX_LABEL = 80
_MAX_DESTINATION = 80
_MAX_BACKUP_REFERENCE = 200
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_SHA256 = re.compile(r"[0-9a-f]{64}")
# A count is named by a plain word, never by a household value (a name would be one).
_COUNT_NAME = re.compile(r"[a-z][a-z0-9_]{0,39}")
# The biometric notice is versioned "v" then digits (ADR 0024 decision 15; Plan 0072).
_NOTICE_VERSION = re.compile(r"v[0-9]+")
# A backup's destruction date is recorded as an ISO day (shape only, like the file hash).
_ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
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


class BackupKind(StrEnum):
    """Which backup of the alta a reference and a destruction date belong to (ADR 0024 dec 13)."""

    PRE_RESET = "pre_reset"
    BASELINE = "baseline"


@dataclass(frozen=True)
class Consents:
    """The owner's consents for the operations plane (ADR 0025 decision 10).

    Recording a consent builds and enables nothing; the destination label is the only free text and
    carries no household value.
    """

    telemetry: bool
    remote_support: bool
    backup: bool
    backup_destination: str | None = None


@dataclass(frozen=True)
class Backup:
    """A backup's path and the date it must be destroyed (ADR 0024 decision 4)."""

    reference: str
    destroy_by: str


@dataclass(frozen=True)
class SessionDetails:
    """The acta columns the session fills (Plan 0072); every field is absent until recorded."""

    biometric_notice_version: str | None
    consents: Consents | None
    modalities: frozenset[Modality]
    pre_reset_backup: Backup | None
    baseline_backup: Backup | None
    readiness_json: str | None


# The session-detail columns, read back by ``read_session_details`` (kept apart from ``_COLUMNS`` so
# ``CommissioningRecord`` and its every caller are untouched).
_DETAIL_COLUMNS = (
    "biometric_notice_version, consents_json, modalities_json, backup_reference, backup_destroy_by, "
    "baseline_backup_reference, baseline_destroy_by, readiness_json"
)


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


_BACKUP_COLUMNS: dict[BackupKind, tuple[str, str]] = {
    BackupKind.PRE_RESET: ("backup_reference", "backup_destroy_by"),
    BackupKind.BASELINE: ("baseline_backup_reference", "baseline_destroy_by"),
}


async def _set_columns(
    record_id: int, columns: Mapping[str, object], manage_transaction: bool
) -> None:
    """Update one or more acta columns of an open record; refuse a closed or missing one.

    The column names come from this module's closed maps, never from a caller, so the assignment
    list is safe to build by hand.
    """
    assignments = ", ".join(f"{name} = ?" for name in columns)
    async with _transaction(manage_transaction):
        await _read_open(record_id)
        await get_conn().execute(
            f"UPDATE commissioning_records SET {assignments} WHERE id = ?",  # noqa: S608
            (*columns.values(), record_id),
        )


async def record_biometric_notice(
    record_id: int, version: str, *, manage_transaction: bool = True
) -> None:
    """Record the version of the biometric notice read to the owner (ADR 0024 decision 15).

    Args:
        record_id: The open commissioning.
        version: The notice's version, ``"v"`` followed by digits.
        manage_transaction: ``False`` joins the caller's open transaction.

    Raises:
        ValueError: For a version that is not ``"v"`` then digits, or an unknown record.
        CommissioningClosedError: If the commissioning is closed.
    """
    if _NOTICE_VERSION.fullmatch(version) is None:
        raise ValueError("the biometric notice version must be 'v' then digits")
    await _set_columns(record_id, {"biometric_notice_version": version}, manage_transaction)
    _announce("notice_recorded", record_id, committed=manage_transaction)


async def record_consents(
    record_id: int, consents: Consents, *, manage_transaction: bool = True
) -> None:
    """Record the operations-plane consents (ADR 0025 decision 10); a consent enables nothing.

    Args:
        record_id: The open commissioning.
        consents: The three yes/no consents and an optional backup destination label.
        manage_transaction: ``False`` joins the caller's open transaction.

    Raises:
        ValueError: For a destination over 80 characters or with a control character, or an
            unknown record.
        CommissioningClosedError: If the commissioning is closed.
    """
    destination = consents.backup_destination
    if destination is not None and (
        len(destination) > _MAX_DESTINATION or _CONTROL_CHARACTERS.search(destination)
    ):
        raise ValueError("the backup destination must be at most 80 printable characters")
    payload = json.dumps(
        {
            "telemetry": consents.telemetry,
            "remote_support": consents.remote_support,
            "backup": consents.backup,
            "backup_destination": destination,
        }
    )
    await _set_columns(record_id, {"consents_json": payload}, manage_transaction)
    _announce("consents_recorded", record_id, committed=manage_transaction)


async def record_modalities(
    record_id: int, modalities: frozenset[Modality], *, manage_transaction: bool = True
) -> None:
    """Record the modalities enrolled in the session (ADR 0024 decision 15).

    Args:
        record_id: The open commissioning.
        modalities: A subset of ``ENROLLABLE_MODALITIES`` (``pin``, ``face``, ``voice``).
        manage_transaction: ``False`` joins the caller's open transaction.

    Raises:
        ValueError: For a modality outside the enrollable set, or an unknown record.
        CommissioningClosedError: If the commissioning is closed.
    """
    if not modalities <= ENROLLABLE_MODALITIES:
        raise ValueError("only enrollable modalities (pin, face, voice) may be recorded")
    payload = json.dumps(sorted(modality.value for modality in modalities))
    await _set_columns(record_id, {"modalities_json": payload}, manage_transaction)
    _announce("modalities_recorded", record_id, committed=manage_transaction)


async def record_backup(
    record_id: int,
    *,
    which: BackupKind,
    reference: str,
    destroy_by: str,
    manage_transaction: bool = True,
) -> None:
    """Record a backup's path and the date it must be destroyed (ADR 0024 decisions 4, 13).

    Args:
        record_id: The open commissioning.
        which: The pre-reset backup or the baseline backup.
        reference: The backup's path, 1 to 200 printable characters.
        destroy_by: The destruction date as an ISO day (``YYYY-MM-DD``).
        manage_transaction: ``False`` joins the caller's open transaction.

    Raises:
        ValueError: For a bad reference or destruction date, or an unknown record.
        CommissioningClosedError: If the commissioning is closed.
    """
    if not 1 <= len(reference) <= _MAX_BACKUP_REFERENCE or _CONTROL_CHARACTERS.search(reference):
        raise ValueError("the backup reference must be 1 to 200 printable characters")
    if _ISO_DAY.fullmatch(destroy_by) is None:
        raise ValueError("the destruction date must be an ISO day (YYYY-MM-DD)")
    reference_column, date_column = _BACKUP_COLUMNS[which]
    await _set_columns(
        record_id, {reference_column: reference, date_column: destroy_by}, manage_transaction
    )
    _announce("backup_recorded", record_id, committed=manage_transaction)


async def record_readiness(
    record_id: int, readiness_json: str, *, manage_transaction: bool = True
) -> None:
    """Record the readiness report built by the session (ADR 0024 decision 14).

    Args:
        record_id: The open commissioning.
        readiness_json: The readiness report as a JSON string.
        manage_transaction: ``False`` joins the caller's open transaction.

    Raises:
        ValueError: For a string that is not valid JSON, or an unknown record.
        CommissioningClosedError: If the commissioning is closed.
    """
    try:
        json.loads(readiness_json)
    except ValueError as exc:
        raise ValueError("the readiness report must be valid JSON") from exc
    await _set_columns(record_id, {"readiness_json": readiness_json}, manage_transaction)
    _announce("readiness_recorded", record_id, committed=manage_transaction)


def _decode_backup(reference: object, destroy_by: object) -> Backup | None:
    """Build a backup from its two columns, or ``None`` when the reference is absent."""
    if reference is None:
        return None
    return Backup(reference=str(reference), destroy_by=str(destroy_by))


def _decode_consents(consents_json: object) -> Consents | None:
    """Decode the consents this module itself wrote, or ``None`` when none were recorded."""
    if consents_json is None:
        return None
    data: Any = json.loads(str(consents_json))  # Any: a JSON object this module itself wrote
    destination = data["backup_destination"]
    return Consents(
        telemetry=bool(data["telemetry"]),
        remote_support=bool(data["remote_support"]),
        backup=bool(data["backup"]),
        backup_destination=None if destination is None else str(destination),
    )


def _decode_modalities(modalities_json: object) -> frozenset[Modality]:
    """Decode the modalities this module itself wrote, or an empty set when none were recorded."""
    if modalities_json is None:
        return frozenset()
    values: Any = json.loads(str(modalities_json))  # Any: a JSON list this module itself wrote
    return frozenset(Modality(str(value)) for value in values)


async def read_session_details(record_id: int) -> SessionDetails:
    """Return the acta columns the session fills; each is absent until it is recorded.

    Args:
        record_id: The commissioning, open or closed.

    Returns:
        The notice version, the consents, the modalities, the two backups and the readiness report.

    Raises:
        ValueError: If the record does not exist.
    """
    cursor = await get_conn().execute(
        f"SELECT {_DETAIL_COLUMNS} FROM commissioning_records WHERE id = ?",  # noqa: S608
        (record_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    if row is None:
        raise ValueError(f"commissioning {record_id} does not exist")
    (
        notice,
        consents_json,
        modalities_json,
        backup_reference,
        backup_destroy_by,
        baseline_reference,
        baseline_destroy_by,
        readiness_json,
    ) = row
    return SessionDetails(
        biometric_notice_version=None if notice is None else str(notice),
        consents=_decode_consents(consents_json),
        modalities=_decode_modalities(modalities_json),
        pre_reset_backup=_decode_backup(backup_reference, backup_destroy_by),
        baseline_backup=_decode_backup(baseline_reference, baseline_destroy_by),
        readiness_json=None if readiness_json is None else str(readiness_json),
    )


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


async def clear_section_statuses(record_id: int, *, manage_transaction: bool = True) -> None:
    """Forget every section status of an open record (a replacement records them again).

    Args:
        record_id: The open commissioning.
        manage_transaction: ``False`` joins the caller's open transaction.

    Raises:
        ValueError: If the record does not exist.
        CommissioningClosedError: If the commissioning is closed.
    """
    async with _transaction(manage_transaction):
        await _read_open(record_id)
        await get_conn().execute(
            "DELETE FROM commissioning_sections WHERE commissioning_id = ?", (record_id,)
        )
    _announce("sections_cleared", record_id, committed=manage_transaction)


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
