"""Care contacts: people with a phone the owner wants called or told (Plan 0070, ADR 0024 decision 5).

A caregiver's phone is a fact about a third party, which ADR 0022 closes, so contacts are
operational data in the ``care_contacts`` table, written only here. Being a contact opens **no**
fact about the person and never makes them a household member. The writer assigns the
classification (``personal``/``private``, or ``personal``/``location`` when the contact holds a
key); the caller states the channel and whether the owner confirmed. Nothing reads the table by
voice and no alert is built: capturing a phone calls nobody.

This module is the only place with SQL on ``care_contacts`` (an architecture guard says so). No
phone and no relationship label reaches a log, an error message or a ``repr``.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, nullcontext
from dataclasses import dataclass, field
from enum import StrEnum
import logging
import re

from server import db
from server.db import get_conn
from server.memory.write_types import ConflictPolicy, WriteChannel, WriteRefusal, refusal_error

__all__ = [
    "CareContact",
    "ContactRole",
    "entity_has_contact_rows",
    "has_active_contact",
    "list_active_contacts",
    "normalize_phone",
    "write_contact",
]

logger = logging.getLogger(__name__)

_WRITE_EVENT = "memory.care_contact_write"
_WHAT = "care_contact"
_PERSONAL = "personal"
_PRIVATE = "private"
_LOCATION = "location"
# `+`, then 8 to 15 digits, the first not 0 (E.164). ASCII digits only, never `\d`.
_PHONE_PATTERN = re.compile(r"\+[1-9][0-9]{7,14}")
_PHONE_SEPARATORS = re.compile(r"[\s().-]")
_MAX_RELATIONSHIP = 40
_COLUMNS = (
    "id, owner_entity_id, contact_entity_id, role, relationship, phone, phone_alt, call_order, "
    "has_key, may_receive_health_info, may_view_activity, visibility, sensitivity, "
    "asserted_by_entity_id, channel, confirmed_by_entity_id, confirmed_at, created_at, revoked_at"
)


class ContactRole(StrEnum):
    """Closed list of the roles a contact can have (ADR 0024 decision 5)."""

    EMERGENCY = "emergency"
    CAREGIVER = "caregiver"
    DOCTOR = "doctor"
    KEY_HOLDER = "key_holder"
    NEIGHBOR = "neighbor"
    TRUSTED = "trusted"
    OTHER = "other"


@dataclass(frozen=True)
class CareContact:
    """One row of ``care_contacts``; its ``repr`` omits the phones and the relationship."""

    id: int
    owner_entity_id: int
    contact_entity_id: int
    role: ContactRole
    relationship: str | None = field(repr=False)
    phone: str = field(repr=False)
    phone_alt: str | None = field(repr=False)
    call_order: int | None
    has_key: bool
    may_receive_health_info: bool
    may_view_activity: bool
    visibility: str
    sensitivity: str
    asserted_by_entity_id: int | None
    channel: str
    confirmed_by_entity_id: int | None
    confirmed_at: str
    created_at: str
    revoked_at: str | None


@dataclass(frozen=True)
class _Terms:
    """What a caller states about a contact: a repeat is an identical set of terms."""

    phone: str = field(repr=False)
    phone_alt: str | None = field(repr=False)
    relationship: str | None = field(repr=False)
    call_order: int | None
    has_key: bool
    may_receive_health_info: bool
    may_view_activity: bool

    @classmethod
    def of(cls, row: CareContact) -> _Terms:
        """Read the terms back from a stored row."""
        return cls(
            row.phone,
            row.phone_alt,
            row.relationship,
            row.call_order,
            row.has_key,
            row.may_receive_health_info,
            row.may_view_activity,
        )


def normalize_phone(raw: str) -> str | None:
    """Return a phone in international format, or ``None`` when it cannot be one.

    Spaces, hyphens, dots and parentheses are stripped. What is left must be ``+`` and 8 to 15
    ASCII digits, the first not ``0``: a later alert never has to guess a country code.

    Args:
        raw: The phone as written, for example ``"+56 9 0000 0001"``.

    Returns:
        The canonical phone, for example ``"+56900000001"``, or ``None``.
    """
    stripped = _PHONE_SEPARATORS.sub("", raw)
    return stripped if _PHONE_PATTERN.fullmatch(stripped) else None


def _row(values: tuple[object, ...]) -> CareContact:
    """Build a ``CareContact`` from a row selected with ``_COLUMNS``."""
    (
        row_id,
        owner,
        contact,
        role,
        relationship,
        phone,
        phone_alt,
        call_order,
        has_key,
        may_receive_health_info,
        may_view_activity,
        visibility,
        sensitivity,
        asserted_by,
        channel,
        confirmed_by,
        confirmed_at,
        created_at,
        revoked_at,
    ) = values
    return CareContact(
        id=int(str(row_id)),
        owner_entity_id=int(str(owner)),
        contact_entity_id=int(str(contact)),
        role=ContactRole(str(role)),
        relationship=None if relationship is None else str(relationship),
        phone=str(phone),
        phone_alt=None if phone_alt is None else str(phone_alt),
        call_order=None if call_order is None else int(str(call_order)),
        has_key=bool(has_key),
        may_receive_health_info=bool(may_receive_health_info),
        may_view_activity=bool(may_view_activity),
        visibility=str(visibility),
        sensitivity=str(sensitivity),
        asserted_by_entity_id=None if asserted_by is None else int(str(asserted_by)),
        channel=str(channel),
        confirmed_by_entity_id=None if confirmed_by is None else int(str(confirmed_by)),
        confirmed_at=str(confirmed_at),
        created_at=str(created_at),
        revoked_at=None if revoked_at is None else str(revoked_at),
    )


async def _fetch_all(sql: str, *params: object) -> tuple[CareContact, ...]:
    cursor = await get_conn().execute(sql, params)
    rows = await cursor.fetchall()
    await cursor.close()
    return tuple(_row(tuple(row)) for row in rows)


async def _scalar(sql: str, *params: object) -> object | None:
    cursor = await get_conn().execute(sql, params)
    row = await cursor.fetchone()
    await cursor.close()
    return None if row is None else row[0]


async def list_active_contacts(owner_entity_id: int) -> tuple[CareContact, ...]:
    """Return the owner's active contacts by call order (those with none last), then by id.

    Args:
        owner_entity_id: The owner whose contacts are listed.

    Returns:
        The active rows; revoked ones are hidden.
    """
    return await _fetch_all(
        f"SELECT {_COLUMNS} FROM care_contacts "  # noqa: S608
        "WHERE owner_entity_id = ? AND revoked_at IS NULL "
        "ORDER BY call_order IS NULL, call_order, id",
        owner_entity_id,
    )


async def has_active_contact(entity_id: int) -> bool:
    """Return whether the entity is an active contact of anybody."""
    found = await _scalar(
        "SELECT 1 FROM care_contacts WHERE contact_entity_id = ? AND revoked_at IS NULL LIMIT 1",
        entity_id,
    )
    return found is not None


async def entity_has_contact_rows(entity_id: int) -> bool:
    """Return whether the entity is the contact of any row at all, revoked ones included."""
    found = await _scalar(
        "SELECT 1 FROM care_contacts WHERE contact_entity_id = ? LIMIT 1", entity_id
    )
    return found is not None


def _validated(
    phone: str, phone_alt: str | None, call_order: int | None, label: str | None
) -> tuple[str, str | None, str | None]:
    """Normalize the phones and the label, or raise a ``ValueError`` that holds none of them."""
    canonical = normalize_phone(phone)
    if canonical is None:
        raise ValueError("phone is not in international format")
    canonical_alt = None
    if phone_alt is not None:
        canonical_alt = normalize_phone(phone_alt)
        if canonical_alt is None:
            raise ValueError("second phone is not in international format")
    if call_order is not None and call_order < 1:
        raise ValueError("call order is below the minimum")
    relationship = None if label is None else label.strip()
    if relationship is not None and not 1 <= len(relationship) <= _MAX_RELATIONSHIP:
        raise ValueError("relationship length is out of range")
    return canonical, canonical_alt, relationship


async def _require_a_person(
    owner_entity_id: int, contact_entity_id: int, channel: WriteChannel
) -> None:
    """Refuse the owner as their own contact, and anything that is not a person."""
    if contact_entity_id == owner_entity_id:
        raise refusal_error(WriteRefusal.CONTACT_IS_OWNER, what=_WHAT, channel=channel)
    entity_type = await _scalar("SELECT type FROM entities WHERE id = ?", contact_entity_id)
    if entity_type is None:
        raise ValueError(f"entity {contact_entity_id} does not exist")
    if entity_type != "person":
        raise refusal_error(WriteRefusal.NOT_A_PERSON, what=_WHAT, channel=channel)


async def _active_row(
    owner_entity_id: int, contact_entity_id: int, role: ContactRole
) -> CareContact | None:
    rows = await _fetch_all(
        f"SELECT {_COLUMNS} FROM care_contacts "  # noqa: S608
        "WHERE owner_entity_id = ? AND contact_entity_id = ? AND role = ? AND revoked_at IS NULL",
        owner_entity_id,
        contact_entity_id,
        role.value,
    )
    return rows[0] if rows else None


async def _require_a_free_order(
    owner_entity_id: int, call_order: int | None, superseded_id: int | None, channel: WriteChannel
) -> None:
    """Refuse an order another active contact already holds (the row being replaced does not count)."""
    if call_order is None:
        return
    taken = await _scalar(
        "SELECT 1 FROM care_contacts WHERE owner_entity_id = ? AND call_order = ? "
        "AND revoked_at IS NULL AND id != ? LIMIT 1",
        owner_entity_id,
        call_order,
        -1 if superseded_id is None else superseded_id,
    )
    if taken is not None:
        raise refusal_error(WriteRefusal.ORDER_TAKEN, what=_WHAT, channel=channel)


def _transaction(manage_transaction: bool) -> AbstractAsyncContextManager[object]:
    """Own a transaction, or join the one the caller owns (``db.transaction`` is not reentrant)."""
    return db.transaction() if manage_transaction else nullcontext()


async def write_contact(
    *,
    owner_entity_id: int,
    contact_entity_id: int,
    role: ContactRole,
    phone: str,
    channel: WriteChannel,
    confirmed_at: str,
    phone_alt: str | None = None,
    relationship: str | None = None,
    call_order: int | None = None,
    has_key: bool = False,
    may_receive_health_info: bool = False,
    may_view_activity: bool = False,
    on_conflict: ConflictPolicy = ConflictPolicy.SUPERSEDE,
    confirmed_by_owner: bool = True,
    manage_transaction: bool = True,
) -> CareContact:
    """Store one care contact: the owner asserts it and the writer classifies it.

    An identical contact (same owner, contact, role and values) returns the row already there.
    The same owner, contact and role with another value supersedes the old row (it is revoked,
    the new one inserted) under ``SUPERSEDE`` and is a ``value_conflict`` under ``REFUSE``.
    One person with two roles has two rows. A person who is a contact is never a household
    member: this writes no fact about them.

    Args:
        owner_entity_id: The owner, who asserts (and confirms unless ``confirmed_by_owner`` is off).
        contact_entity_id: An existing person: an adult child, the partner, a relative or a third
            party made apart.
        role: The contact's role.
        phone: International format; spaces, hyphens, dots and parentheses are stripped.
        channel: The channel the contact arrived through.
        confirmed_at: When it was confirmed, as UTC ISO 8601.
        phone_alt: An optional second phone (a mobile and a landline).
        relationship: An optional short label such as ``"vecina"`` (1 to 40 characters).
        call_order: The position among the owner's active contacts, unique and belonging to the
            person; ``None`` means an alert never calls them.
        has_key: Whether the contact holds a key (stored ``location`` instead of ``private``).
        may_receive_health_info: The allow-list counterpart of ``withhold_from`` (CM-5 reads it).
        may_view_activity: Whether the contact may later see the owner's activity events.
        on_conflict: ``SUPERSEDE`` or ``REFUSE`` when the same role has other values.
        confirmed_by_owner: ``False`` stores no confirmer (the owner did not confirm it).
        manage_transaction: ``False`` joins the caller's open transaction.

    Returns:
        The stored row, or the identical active one.

    Raises:
        ValueError: For a phone not in international format (the message holds no digit), an
            order below 1, a label outside 1 to 40 characters, an unlisted channel or a contact
            that does not exist.
        WriteRefusedError: With ``contact_is_owner``, ``not_a_person``, ``order_taken`` or
            ``value_conflict``.
    """
    canonical, canonical_alt, label = _validated(phone, phone_alt, call_order, relationship)
    write_channel = WriteChannel(channel)
    async with _transaction(manage_transaction):
        await _require_a_person(owner_entity_id, contact_entity_id, write_channel)
        current = await _active_row(owner_entity_id, contact_entity_id, role)
        wanted = _Terms(
            canonical,
            canonical_alt,
            label,
            call_order,
            has_key,
            may_receive_health_info,
            may_view_activity,
        )
        if current is not None and _Terms.of(current) == wanted:
            return current
        if current is not None and on_conflict is ConflictPolicy.REFUSE:
            raise refusal_error(WriteRefusal.VALUE_CONFLICT, what=_WHAT, channel=write_channel)
        await _require_a_free_order(
            owner_entity_id, call_order, None if current is None else current.id, write_channel
        )
        if current is not None:
            await get_conn().execute(
                "UPDATE care_contacts SET revoked_at = ? WHERE id = ?", (confirmed_at, current.id)
            )
        stored = await _insert(
            owner_entity_id,
            contact_entity_id,
            role,
            wanted,
            channel=write_channel,
            confirmed_at=confirmed_at,
            confirmed_by_owner=confirmed_by_owner,
        )
    _announce(stored, committed=manage_transaction)
    return stored


async def _insert(
    owner_entity_id: int,
    contact_entity_id: int,
    role: ContactRole,
    terms: _Terms,
    *,
    channel: WriteChannel,
    confirmed_at: str,
    confirmed_by_owner: bool,
) -> CareContact:
    """Insert the row, classified by the writer, and read it back."""
    cursor = await get_conn().execute(
        "INSERT INTO care_contacts (owner_entity_id, contact_entity_id, role, phone, phone_alt, "
        "relationship, call_order, has_key, may_receive_health_info, may_view_activity, "
        "visibility, sensitivity, asserted_by_entity_id, channel, confirmed_by_entity_id, "
        "confirmed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            owner_entity_id,
            contact_entity_id,
            role.value,
            terms.phone,
            terms.phone_alt,
            terms.relationship,
            terms.call_order,
            int(terms.has_key),
            int(terms.may_receive_health_info),
            int(terms.may_view_activity),
            _PERSONAL,
            _LOCATION if terms.has_key else _PRIVATE,
            owner_entity_id,
            channel.value,
            owner_entity_id if confirmed_by_owner else None,
            confirmed_at,
        ),
    )
    row_id = cursor.lastrowid
    await cursor.close()
    if row_id is None:
        raise RuntimeError("INSERT into care_contacts returned no row id")
    (stored,) = await _fetch_all(f"SELECT {_COLUMNS} FROM care_contacts WHERE id = ?", row_id)  # noqa: S608
    return stored


def _announce(row: CareContact, *, committed: bool) -> None:
    """Log one stored row by id and closed fields, only once it is certain to persist."""
    logger.log(
        logging.INFO if committed else logging.DEBUG,
        "Care contact %s",
        "written" if committed else "staged",
        extra={
            "event": _WRITE_EVENT,
            "row_id": row.id,
            "role": row.role.value,
            "channel": row.channel,
        },
    )
