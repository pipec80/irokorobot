"""One seed load in one transaction, with the commissioning record and the owner's review (Plan 0071).

``run_seed`` runs the applier (``seed_import.run_operations``) and the commissioning calls in a
single ``db.transaction()``: a dry run counts inside it and rolls back; an apply needs the
interviewer's ``SI`` to the owner's review, opens (or reuses) the record and stores the file's hash,
the counts and every section's status; any problem, refusal or failure leaves nothing, the record
included. With ``replace`` it first retracts what earlier imports wrote (``seed_replace``). It does
not read ``memory_enabled``: the import is an administration act (ADR 0024 decision 7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING

from server import db
from server.exceptions import CommissioningClosedError, CommissioningMissingError
from server.memory.commissioning import (
    ConfirmationMode,
    get_open_commissioning,
    importer_window_open,
    open_commissioning,
    record_import,
    set_section_status,
)
from server.memory.seed_import import (
    OperationOutcome,
    OperationStatus,
    SeedReport,
    count_rows,
    run_operations,
)
from server.memory.seed_plan import OperationKind
from server.memory.seed_replace import assert_no_voice_memory, retract_earlier_import
from server.settings import settings

if TYPE_CHECKING:
    from server.memory.commissioning import CommissioningInput, CommissioningRecord
    from server.memory.seed_file import LoadedSeed
    from server.memory.seed_plan import SeedPlan

__all__ = ["run_seed"]

logger = logging.getLogger(__name__)

_EVENT = "memory.seed_load"

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
        await assert_no_voice_memory(request.now)
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
