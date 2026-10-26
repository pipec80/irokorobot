"""The seed applier: write a plan of operations through the canonical writers (Plan 0071).

The importer is an administration act, not a conversation (ADR 0024 decision 7): it bypasses the
policy and the ``memory_enabled`` switch, and what replaces them is the commissioning record and a
log line with counts only. Every write goes through the canonical writer, the contacts writer or
``create_third_party`` with the channel ``import_assisted``, the owner as asserter and the
refuse-on-conflict policy (decision 8), joined to one transaction the caller owns. One operation's
refusal is reported, never raised, so the interviewer sees every problem at once; anything else
propagates. No outcome, error or log line holds a name, a value or a phone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import logging
from typing import TYPE_CHECKING

from server import db
from server.exceptions import (
    AmbiguousEntityError,
    CommissioningClosedError,
    CommissioningMissingError,
    SeedOwnerError,
    UnstorableValueError,
    WriteRefusedError,
)
from server.memory.canonical_writer import write_literal, write_relation
from server.memory.care_contacts import ContactRole, count_active_contacts, write_contact
from server.memory.commissioning import (
    ConfirmationMode,
    get_open_commissioning,
    importer_window_open,
    open_commissioning,
    record_import,
    set_section_status,
)
from server.memory.declarative import (
    Guardianship,
    count_entities,
    create_third_party,
    is_adult_dependent,
)
from server.memory.entity_labels import get_person_label
from server.memory.owner_credentials import get_active_owner_pin_credential
from server.memory.relational_v4 import count_v4_rows
from server.memory.seed_plan import OWNER_REF, OperationKind
from server.memory.seed_replace import assert_no_voice_memory, retract_earlier_import
from server.memory.write_types import ConflictPolicy, WriteChannel
from server.personal_setup import read_personal_setup_status
from server.settings import settings
from server.text_keys import fold_name

if TYPE_CHECKING:
    from collections.abc import Mapping

    from server.memory.commissioning import (
        CommissioningInput,
        CommissioningRecord,
        Section,
        SectionStatus,
    )
    from server.memory.seed_file import LoadedSeed
    from server.memory.seed_plan import SeedOperation, SeedPlan, SeedRef
    from server.schemas import EntityType

__all__ = [
    "OperationOutcome",
    "OperationStatus",
    "RowCounts",
    "SeedReport",
    "count_rows",
    "resolve_ready_owner",
    "run_operations",
    "run_seed",
]

logger = logging.getLogger(__name__)

#: The importer's one channel: an interview with an interviewer (ADR 0024 decision 6).
_CHANNEL = WriteChannel.IMPORT_ASSISTED
_EVENT = "memory.seed_load"
_POLICY = ConflictPolicy.REFUSE


class OperationStatus(StrEnum):
    """What one operation did."""

    WRITTEN = "written"
    UNCHANGED = "unchanged"
    REFUSED = "refused"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class OperationOutcome:
    """One operation and what became of it; ``reason`` is a closed word or ``None``."""

    operation: SeedOperation
    status: OperationStatus
    reason: str | None = None


@dataclass(frozen=True)
class RowCounts:
    """How many entities, V4 rows and active contacts the database holds."""

    entities: int
    literals: int
    relations: int
    contacts: int


@dataclass(frozen=True)
class SeedReport:
    """The result of one run, dry or applied; it holds no value."""

    outcomes: tuple[OperationOutcome, ...]
    statuses: Mapping[Section, SectionStatus] = field(repr=False)
    rows_before: RowCounts
    rows_after: RowCounts
    applied: bool
    record_id: int | None

    @property
    def problems(self) -> tuple[OperationOutcome, ...]:
        """The outcomes that were refused or skipped, in plan order."""
        return tuple(
            outcome
            for outcome in self.outcomes
            if outcome.status in {OperationStatus.REFUSED, OperationStatus.SKIPPED}
        )


class _RefusedError(Exception):
    """A refusal the applier itself finds (a changed guardianship); carries a closed reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


async def count_rows() -> RowCounts:
    """Return the counts the applier compares before and after each operation."""
    v4 = await count_v4_rows()
    return RowCounts(
        entities=await count_entities(),
        literals=v4.literals,
        relations=v4.relations,
        contacts=await count_active_contacts(),
    )


async def resolve_ready_owner(expected_name: str) -> int:
    """Return the ready owner's entity id, refusing an absent owner or another name.

    The importer never creates the owner (ADR 0024 decision 11): the owner and the PIN must exist
    (``just setup-personal``) and the name in the file must fold to the stored one. Nothing is
    written.

    Args:
        expected_name: The owner's name as the file states it.

    Returns:
        The owner's entity id.

    Raises:
        SeedOwnerError: ``owner_not_ready`` when there is no ready owner holding the active PIN,
            ``owner_name_mismatch`` when the stored owner's folded name differs.
    """
    status = await read_personal_setup_status()
    credential = await get_active_owner_pin_credential()
    if not status.personal_security_ready or credential is None:
        raise SeedOwnerError("owner_not_ready")
    label = await get_person_label(entity_id=credential.person_entity_id)
    if label is None or _folded(label.display_name) != _folded(expected_name):
        raise SeedOwnerError("owner_name_mismatch")
    return credential.person_entity_id


def _folded(name: str) -> str:
    return " ".join(fold_name(name).split())


def _text(attributes: Mapping[str, object], key: str) -> str | None:
    value = attributes.get(key)
    return None if value is None else str(value)


async def _create(operation: SeedOperation) -> int:
    """Create (or find again by its import key) one entity and check its guardianship."""
    entity_type: EntityType = "other" if operation.entity_type == "other" else "person"
    guardianship = _text(operation.attributes, "guardianship")
    entity_id = await create_third_party(
        name=operation.entity_name or "",
        type=entity_type,
        import_key=operation.import_key,
        attributes=None if guardianship is None else {"guardianship": guardianship},
        manage_transaction=False,
    )
    if guardianship is not None and await is_adult_dependent(entity_id) != (
        guardianship == Guardianship.ADULT
    ):
        raise _RefusedError("guardianship_conflict")
    return entity_id


@dataclass(frozen=True)
class _Run:
    """What every write of one run shares: the owner, the instant and who confirmed."""

    owner: int
    now: str
    confirmed: bool


async def _relation(operation: SeedOperation, ids: Mapping[SeedRef, int], run: _Run) -> None:
    await write_relation(
        owner_entity_id=run.owner,
        source_entity_id=ids[operation.subject or OWNER_REF],
        predicate=operation.predicate or "",
        target_entity_id=ids[operation.target or OWNER_REF],
        channel=_CHANNEL,
        confirmed_at=run.now,
        asserted_at=run.now,
        on_conflict=_POLICY,
        confirmed_by_owner=run.confirmed,
        manage_transaction=False,
    )


async def _literal(operation: SeedOperation, ids: Mapping[SeedRef, int], run: _Run) -> None:
    await write_literal(
        owner_entity_id=run.owner,
        subject_entity_id=ids[operation.subject or OWNER_REF],
        predicate=operation.predicate or "",
        value=operation.value or "",
        channel=_CHANNEL,
        confirmed_at=run.now,
        asserted_at=run.now,
        on_conflict=_POLICY,
        confirmed_by_owner=run.confirmed,
        manage_transaction=False,
    )


async def _contact(operation: SeedOperation, ids: Mapping[SeedRef, int], run: _Run) -> None:
    terms = operation.attributes
    order = terms.get("call_order")
    await write_contact(
        owner_entity_id=run.owner,
        contact_entity_id=ids[operation.subject or OWNER_REF],
        role=ContactRole(str(terms["role"])),
        phone=str(terms["phone"]),
        phone_alt=_text(terms, "phone_alt"),
        relationship=_text(terms, "relationship"),
        call_order=order if isinstance(order, int) else None,
        has_key=terms.get("has_key") is True,
        may_receive_health_info=terms.get("may_receive_health_info") is True,
        may_view_activity=terms.get("may_view_activity") is True,
        channel=_CHANNEL,
        confirmed_at=run.now,
        on_conflict=_POLICY,
        confirmed_by_owner=run.confirmed,
        manage_transaction=False,
    )


async def _apply(operation: SeedOperation, ids: dict[SeedRef, int], run: _Run) -> None:
    """Run one operation; an entity it creates becomes reachable by its reference."""
    match operation.kind:
        case OperationKind.CREATE_ENTITY:
            entity_id = await _create(operation)
            if operation.subject is not None:
                ids[operation.subject] = entity_id
        case OperationKind.WRITE_RELATION:
            await _relation(operation, ids, run)
        case OperationKind.WRITE_LITERAL:
            await _literal(operation, ids, run)
        case OperationKind.WRITE_CONTACT:
            await _contact(operation, ids, run)


def _depends_on_a_failure(operation: SeedOperation, ids: Mapping[SeedRef, int]) -> bool:
    """A write whose subject or target entity was not created cannot run."""
    if operation.kind is OperationKind.CREATE_ENTITY:
        return False
    return any(ref is not None and ref not in ids for ref in (operation.subject, operation.target))


async def _outcome(
    operation: SeedOperation, ids: dict[SeedRef, int], run: _Run
) -> OperationOutcome:
    """Run one operation and say what it did; only the closed refusals are caught."""
    if _depends_on_a_failure(operation, ids):
        return OperationOutcome(operation, OperationStatus.SKIPPED, "dependency_failed")
    before = await count_rows()
    try:
        await _apply(operation, ids, run)
    except (WriteRefusedError, _RefusedError) as exc:
        reason = exc.reason
    except AmbiguousEntityError:
        reason = "entity_exists"
    except UnstorableValueError:
        reason = "unstorable_value"
    except ValueError:
        # The registry's or a writer's validation of this one value: never echoed.
        reason = "invalid_value"
    else:
        changed = await count_rows() != before
        status = OperationStatus.WRITTEN if changed else OperationStatus.UNCHANGED
        return OperationOutcome(operation, status)
    return OperationOutcome(operation, OperationStatus.REFUSED, reason)


async def run_operations(
    plan: SeedPlan, *, owner_entity_id: int, now: str, confirmed_by_owner: bool
) -> tuple[OperationOutcome, ...]:
    """Run every operation of a plan inside the transaction the caller owns.

    Each write uses the channel ``import_assisted``, the owner as asserter and the refuse policy;
    ``written`` or ``unchanged`` comes from the row counts before and after the operation. The
    dependents of an entity that was not created are ``skipped``.

    Args:
        plan: The plan of operations.
        owner_entity_id: The ready owner (``resolve_ready_owner``).
        now: UTC ISO 8601: the confirmation and the assertion instant of every row.
        confirmed_by_owner: ``False`` stores no confirmer (the ``representative`` mode).

    Returns:
        One outcome per operation, in plan order.

    Raises:
        Exception: Anything but a closed refusal of one operation propagates unchanged, so the
            caller's transaction rolls back.
    """
    run = _Run(owner=owner_entity_id, now=now, confirmed=confirmed_by_owner)
    ids: dict[SeedRef, int] = {OWNER_REF: owner_entity_id}
    return tuple([await _outcome(operation, ids, run) for operation in plan.operations])


# --- one transaction, the record and the owner's review (Task 4b) -----------------------------

# How the acta names the rows of each kind the file holds (plain lowercase words, never a value).
_COUNT_NAMES = {
    OperationKind.CREATE_ENTITY: "entities",
    OperationKind.WRITE_RELATION: "relations",
    OperationKind.WRITE_LITERAL: "literals",
    OperationKind.WRITE_CONTACT: "contacts",
}
_HELD = frozenset({OperationStatus.WRITTEN, OperationStatus.UNCHANGED})


class _RollbackError(Exception):
    """Raised inside the transaction to undo a dry run or a run with problems; carries the report."""

    def __init__(self, report: SeedReport) -> None:
        super().__init__("seed load rolled back")
        self.report = report


def _acta_counts(outcomes: tuple[OperationOutcome, ...]) -> dict[str, int]:
    """The rows of each kind the file holds after the load, and how many this load wrote."""
    counts = dict.fromkeys(_COUNT_NAMES.values(), 0)
    for outcome in outcomes:
        if outcome.status in _HELD:
            counts[_COUNT_NAMES[outcome.operation.kind]] += 1
    counts["written"] = sum(o.status is OperationStatus.WRITTEN for o in outcomes)
    return counts


async def _record(
    loaded: LoadedSeed,
    plan: SeedPlan,
    outcomes: tuple[OperationOutcome, ...],
    opened: CommissioningRecord | None,
    details: CommissioningInput | None,
    now: str,
) -> int:
    """Open the record (or reuse the open one) and store the hash, the counts and the statuses.

    It runs outside the per-operation catch, so a commissioning error is never taken for an
    operation's ``invalid_value``.
    """
    if opened is None:
        if details is None:
            raise CommissioningMissingError
        opened = await open_commissioning(details, started_at=now, manage_transaction=False)
    await record_import(
        opened.id,
        seed_file_sha256=loaded.sha256,
        counts=_acta_counts(outcomes),
        manage_transaction=False,
    )
    for section, status in plan.section_statuses.items():
        await set_section_status(opened.id, section, status, now, manage_transaction=False)
    return opened.id


async def _transaction_body(
    loaded: LoadedSeed,
    plan: SeedPlan,
    opened: CommissioningRecord | None,
    request: _Request,
) -> SeedReport:
    """Everything one run does inside its transaction; raises ``_RollbackError`` to undo it."""
    before = await count_rows()
    if request.replace:
        await assert_no_voice_memory()
        await retract_earlier_import()
    outcomes = await run_operations(
        plan,
        owner_entity_id=request.owner,
        now=request.now,
        confirmed_by_owner=request.confirmed,
    )
    after = await count_rows()
    report = SeedReport(outcomes, plan.section_statuses, before, after, False, None)
    if report.problems or not request.commit:
        raise _RollbackError(report)
    record_id = await _record(loaded, plan, outcomes, opened, request.details, request.now)
    return SeedReport(outcomes, plan.section_statuses, before, after, True, record_id)


@dataclass(frozen=True)
class _Request:
    owner: int
    now: str
    commit: bool
    confirmed: bool
    replace: bool
    details: CommissioningInput | None = field(repr=False)


def _announce(report: SeedReport, loaded: LoadedSeed) -> None:
    """The one log line of a run: the record, a prefix of the hash, the counts and the database."""
    counts = _acta_counts(report.outcomes)
    logger.info(
        "Seed load %s: record=%s sha256=%s counts=%s problems=%d db=%s",
        "applied" if report.applied else "not applied",
        report.record_id,
        loaded.sha256[:12],
        counts,
        len(report.problems),
        settings.brain_db_path.resolve(),
        extra={
            "event": _EVENT,
            "applied": report.applied,
            "record_id": report.record_id,
            "problems": len(report.problems),
        },
    )


async def run_seed(
    loaded: LoadedSeed,
    plan: SeedPlan,
    *,
    owner_entity_id: int,
    commit: bool,
    approved: bool,
    commissioning: CommissioningInput | None,
    replace: bool,
    now: str,
) -> SeedReport:
    """Run one load in one transaction: a dry run, or an approved apply with its record.

    A dry run (``commit=False``) runs every operation, counts the rows inside the transaction and
    rolls everything back. An apply needs the interviewer's ``SI`` to the owner's review
    (``approved``); it opens the commissioning record with ``commissioning`` the first time, or
    reuses the open one (whose confirmation mode then decides the confirmer), and stores the
    file's hash, the counts and every section's status. Any problem, refusal or failure rolls
    back everything, the record included. ``memory_enabled`` is not read: the import is an
    administration act (ADR 0024 decision 7).

    Args:
        loaded: The validated file and its hash.
        plan: Its plan of operations.
        owner_entity_id: The ready owner (``resolve_ready_owner``).
        commit: ``False`` for a dry run.
        approved: The interviewer answered ``SI`` to the owner's review question.
        commissioning: The interviewer's declaration; required only when no record is open.
        replace: First retract what earlier imports wrote (``seed_replace``), inside the same
            transaction; refused once the robot learned anything by voice.
        now: UTC ISO 8601 with microseconds; every row and the record share it.

    Returns:
        The report; ``applied`` is ``True`` only when everything was written.

    Raises:
        CommissioningClosedError: If a commissioning was closed; raised before anything else.
        CommissioningMissingError: For a first apply without ``commissioning``.
        ReplaceRefusedError: For ``replace`` once a voice row or a live candidate exists.
        ValueError: For an apply that was not approved, or a declaration the record refuses.
    """
    if not await importer_window_open():
        raise CommissioningClosedError
    if commit and not approved:
        raise ValueError("a seed load is applied only after the owner's review")
    opened = await get_open_commissioning()
    if commit and opened is None and commissioning is None:
        raise CommissioningMissingError
    declared = opened or commissioning
    mode = declared.confirmation_mode if declared is not None else None
    request = _Request(
        owner=owner_entity_id,
        now=now,
        commit=commit,
        confirmed=mode is not ConfirmationMode.REPRESENTATIVE,
        replace=replace,
        details=commissioning,
    )
    try:
        async with db.transaction():
            report = await _transaction_body(loaded, plan, opened, request)
    except _RollbackError as rollback:
        report = rollback.report
    _announce(report, loaded)
    return report
