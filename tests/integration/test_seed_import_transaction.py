"""One transaction, the commissioning record and the owner's review (Plan 0071 Task 4b).

ADR 0024 decisions 6, 7 and 8: a dry run writes nothing; an apply needs the interviewer's answer
to the review question, opens (or reuses) the record and stores the hash, the counts and the
statuses in the same transaction as the rows; any problem or failure leaves nothing at all.
Every name and value is an invented canary.
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any

import pytest
from server.exceptions import CommissioningClosedError, CommissioningMissingError
from server.memory import seed_import
from server.memory.commissioning import (
    CommissioningInput,
    ConfirmationMode,
    DiskEncryption,
    InterviewerRole,
    close_commissioning,
    get_open_commissioning,
    list_section_statuses,
    open_commissioning,
)
from server.memory.declarative import create_third_party
from server.memory.seed_file import LoadedSeed, parse_seed_text
from server.memory.seed_import import OperationStatus, SeedReport, run_seed
from server.memory.seed_plan import build_plan
from server.settings import settings

from tests.integration.seed_household import NOW, owner, scalar, seed_db
from tests.unit.seed_data import Toml, full_seed, to_toml

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["owner", "seed_db"]

pytestmark = pytest.mark.integration

_LABEL = "Canary Interviewer"


def _loaded(data: Toml) -> LoadedSeed:
    text = to_toml(data)
    return LoadedSeed(
        seed=parse_seed_text(text), sha256=hashlib.sha256(text.encode("utf-8")).hexdigest()
    )


def _details(mode: ConfirmationMode = ConfirmationMode.OWNER_IN_PERSON) -> CommissioningInput:
    return CommissioningInput(
        interviewer_label=_LABEL,
        interviewer_role=InterviewerRole.BUILDER,
        confirmation_mode=mode,
        disk_encryption=DiskEncryption.DECLARED_YES,
    )


async def _run(
    owner_id: int,
    data: Toml | None = None,
    *,
    commit: bool = True,
    approved: bool = True,
    commissioning: CommissioningInput | None = None,
) -> SeedReport:
    loaded = _loaded(full_seed() if data is None else data)
    return await run_seed(
        loaded,
        build_plan(loaded.seed),
        owner_entity_id=owner_id,
        commit=commit,
        approved=approved,
        commissioning=commissioning,
        replace=False,
        now=NOW,
    )


async def _rows() -> tuple[object, ...]:
    return (
        await scalar("SELECT COUNT(*) FROM entities"),
        await scalar("SELECT COUNT(*) FROM literal_facts_v4"),
        await scalar("SELECT COUNT(*) FROM entity_relations_v4"),
        await scalar("SELECT COUNT(*) FROM care_contacts"),
        await scalar("SELECT COUNT(*) FROM commissioning_records"),
        await scalar("SELECT COUNT(*) FROM commissioning_sections"),
    )


# --- the dry run ------------------------------------------------------------------------------


async def test_a_dry_run_reports_and_persists_nothing(owner: int) -> None:
    before = await _rows()

    report = await _run(owner, commit=False, approved=False)

    assert report.applied is False
    assert report.record_id is None
    assert {outcome.status for outcome in report.outcomes} == {OperationStatus.WRITTEN}
    assert report.rows_after.entities > report.rows_before.entities
    assert report.rows_after.contacts == 2
    assert report.statuses == build_plan(_loaded(full_seed()).seed).section_statuses
    assert report.problems == ()
    assert await _rows() == before
    assert await get_open_commissioning() is None


async def test_a_dry_run_after_an_apply_is_all_unchanged(owner: int) -> None:
    await _run(owner, commissioning=_details())

    report = await _run(owner, commit=False, approved=False)

    assert {outcome.status for outcome in report.outcomes} == {OperationStatus.UNCHANGED}
    assert report.rows_after == report.rows_before


# --- the apply --------------------------------------------------------------------------------


async def test_an_approved_apply_writes_and_opens_the_record(owner: int) -> None:
    loaded = _loaded(full_seed())

    report = await _run(owner, commissioning=_details())

    assert report.applied is True
    record = await get_open_commissioning()
    assert record is not None
    assert report.record_id == record.id
    assert record.interviewer_label == _LABEL
    assert record.interviewer_role is InterviewerRole.BUILDER
    assert record.confirmation_mode is ConfirmationMode.OWNER_IN_PERSON
    assert record.disk_encryption is DiskEncryption.DECLARED_YES
    assert record.seed_file_sha256 == loaded.sha256
    assert record.counts["contacts"] == 2
    assert record.counts["written"] == len(report.outcomes)
    assert dict(await list_section_statuses(record.id)) == dict(report.statuses)
    assert await scalar("SELECT COUNT(*) FROM care_contacts") == 2


async def test_a_second_apply_reuses_the_open_record(owner: int) -> None:
    first = await _run(owner, commissioning=_details())
    data = full_seed()
    data["owner"]["likes"] = ["té verde", "el mar"]

    second = await _run(owner, data)

    assert second.applied is True
    assert second.record_id == first.record_id
    assert await scalar("SELECT COUNT(*) FROM commissioning_records") == 1
    record = await get_open_commissioning()
    assert record is not None
    assert record.seed_file_sha256 == _loaded(data).sha256
    assert record.counts["written"] == 1


async def test_a_representative_leaves_no_confirmer_on_every_apply(owner: int) -> None:
    await _run(owner, commissioning=_details(ConfirmationMode.REPRESENTATIVE))
    data = full_seed()
    data["owner"]["likes"] = ["té verde", "el mar"]

    await _run(owner, data, commissioning=None)

    assert await scalar("SELECT COUNT(*) FROM literal_facts_v4") > 0
    for table in ("literal_facts_v4", "entity_relations_v4", "care_contacts"):
        assert (
            await scalar(
                f"SELECT COUNT(*) FROM {table} WHERE confirmed_by_entity_id IS NOT NULL"  # noqa: S608
            )
            == 0
        )


async def test_the_owners_own_review_confirms_every_row(owner: int) -> None:
    await _run(owner, commissioning=_details(ConfirmationMode.BUILDER_IS_OWNER))

    assert (
        await scalar(
            "SELECT COUNT(*) FROM literal_facts_v4 WHERE confirmed_by_entity_id IS NOT ?", owner
        )
        == 0
    )


async def test_an_unapproved_apply_raises_and_writes_nothing(owner: int) -> None:
    before = await _rows()

    with pytest.raises(ValueError, match="review"):
        await _run(owner, approved=False, commissioning=_details())

    assert await _rows() == before


async def test_a_first_apply_without_the_commissioning_raises_and_writes_nothing(
    owner: int,
) -> None:
    before = await _rows()

    with pytest.raises(CommissioningMissingError):
        await _run(owner, commissioning=None)

    assert await _rows() == before


# --- all or nothing ---------------------------------------------------------------------------


async def test_a_problem_rolls_everything_back_the_record_included(owner: int) -> None:
    await create_third_party(name="Canary Child", type="person")
    before = await _rows()

    report = await _run(owner, commissioning=_details())

    assert report.applied is False
    assert report.problems
    assert report.record_id is None
    assert await _rows() == before
    assert await get_open_commissioning() is None


async def test_a_conflict_on_a_later_apply_changes_nothing(owner: int) -> None:
    await _run(owner, commissioning=_details())
    before = await _rows()
    record = await get_open_commissioning()
    data = full_seed()
    data["owner"]["birth_date"] = "1951-05-17"

    report = await _run(owner, data)

    assert report.applied is False
    assert [o.reason for o in report.problems] == ["value_conflict"]
    assert await _rows() == before
    assert await get_open_commissioning() == record


async def test_a_failure_half_way_leaves_nothing_and_propagates(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = await _rows()
    real = seed_import.write_contact
    calls = 0

    async def failing(**kwargs: Any) -> object:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected")
        return await real(**kwargs)

    monkeypatch.setattr(seed_import, "write_contact", failing)

    with pytest.raises(RuntimeError, match="injected"):
        await _run(owner, commissioning=_details())

    assert await _rows() == before


async def test_a_commissioning_error_is_never_swallowed(owner: int) -> None:
    before = await _rows()
    bad = CommissioningInput(
        interviewer_label="x" * 81,
        interviewer_role=InterviewerRole.BUILDER,
        confirmation_mode=ConfirmationMode.OWNER_IN_PERSON,
        disk_encryption=DiskEncryption.UNKNOWN,
    )

    with pytest.raises(ValueError, match="interviewer label"):
        await _run(owner, commissioning=bad)

    assert await _rows() == before


async def test_a_closed_commissioning_stops_the_run_before_anything_else(owner: int) -> None:
    record = await open_commissioning(_details(), started_at=NOW)
    await close_commissioning(record.id, NOW)

    with pytest.raises(CommissioningClosedError):
        await _run(owner, commit=False, approved=False)


async def test_the_switch_of_the_memory_does_not_stop_an_import(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "memory_enabled", False)

    report = await _run(owner, commissioning=_details())

    assert report.applied is True


async def test_the_last_log_line_holds_only_the_record_the_hash_the_counts_and_the_path(
    owner: int, seed_db: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="server.memory.seed_import")
    loaded = _loaded(full_seed())

    report = await _run(owner, commissioning=_details())

    (line,) = [r for r in caplog.records if r.name == "server.memory.seed_import"]
    message = line.getMessage()
    assert str(report.record_id) in message
    assert loaded.sha256[:12] in message
    assert loaded.sha256 not in message
    assert str(seed_db.resolve()) in message
    assert "Canary" not in message
    assert "Canary" not in repr(line.__dict__)
