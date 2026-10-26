"""Retract what an earlier import wrote, while commissioning only (Plan 0071 Task 5b).

ADR 0024 decision 8: with the replacement flag the earlier import's rows, contacts, statuses and
orphan entities are retracted and the file is written again with the refuse policy; anything the
robot learned by voice refuses the replacement, and a closed commissioning refuses the importer.
Every name and value is an invented canary.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from uuid import uuid4

import pytest
from server.exceptions import CommissioningClosedError, ReplaceRefusedError
from server.memory import candidates
from server.memory.candidate_types import CandidateChannel, ProposedCandidate
from server.memory.canonical_writer import write_literal
from server.memory.care_contacts import ContactRole, write_contact
from server.memory.commissioning import (
    CommissioningInput,
    ConfirmationMode,
    DiskEncryption,
    InterviewerRole,
    Section,
    SectionStatus,
    close_commissioning,
    get_open_commissioning,
    list_section_statuses,
)
from server.memory.declarative import create_third_party
from server.memory.seed_file import LoadedSeed, parse_seed_text
from server.memory.seed_import import SeedReport, run_seed
from server.memory.seed_plan import build_plan
from server.memory.write_types import WriteChannel
from server.settings import settings

from tests.integration.seed_household import NOW, owner, scalar, seed_db
from tests.unit.seed_data import Toml, full_seed, to_toml

__all__ = ["owner", "seed_db"]

pytestmark = pytest.mark.integration


def _loaded(data: Toml) -> LoadedSeed:
    text = to_toml(data)
    return LoadedSeed(
        seed=parse_seed_text(text), sha256=hashlib.sha256(text.encode("utf-8")).hexdigest()
    )


async def _run(
    owner_id: int, data: Toml, *, replace: bool, first: bool = False, commit: bool = True
) -> SeedReport:
    loaded = _loaded(data)
    return await run_seed(
        loaded,
        build_plan(loaded.seed),
        owner_entity_id=owner_id,
        commit=commit,
        approved=commit,
        commissioning=CommissioningInput(
            interviewer_label="Canary Interviewer",
            interviewer_role=InterviewerRole.BUILDER,
            confirmation_mode=ConfirmationMode.BUILDER_IS_OWNER,
            disk_encryption=DiskEncryption.UNKNOWN,
        )
        if first
        else None,
        replace=replace,
        now=NOW,
    )


async def _rows() -> tuple[object, ...]:
    return (
        await scalar("SELECT COUNT(*) FROM entities"),
        await scalar("SELECT COUNT(*) FROM literal_facts_v4"),
        await scalar("SELECT COUNT(*) FROM entity_relations_v4"),
        await scalar("SELECT COUNT(*) FROM care_contacts"),
        await scalar("SELECT COUNT(*) FROM commissioning_sections"),
    )


def _changed() -> Toml:
    """The same household with a corrected birth date, one contact fewer and no devices status."""
    data = full_seed()
    data["owner"]["birth_date"] = "1951-05-17"
    data["contacts"] = data["contacts"][:1]
    data["status"] = {}
    return data


async def test_a_replacement_retracts_the_earlier_import_and_writes_the_file_again(
    owner: int,
) -> None:
    await _run(owner, full_seed(), replace=False, first=True)

    report = await _run(owner, _changed(), replace=True)

    assert report.applied is True
    assert (
        await scalar(
            "SELECT value_text FROM literal_facts_v4 WHERE predicate = 'birth_date' AND subject_entity_id = ?",
            owner,
        )
        == "1951-05-17"
    )
    assert (
        await scalar(
            "SELECT COUNT(*) FROM literal_facts_v4 WHERE predicate = 'birth_date' AND subject_entity_id = ?",
            owner,
        )
        == 1
    )
    assert await scalar("SELECT COUNT(*) FROM care_contacts") == 1
    assert await scalar("SELECT COUNT(*) FROM entities WHERE name = 'Canary Doctor'") == 0
    record = await get_open_commissioning()
    assert record is not None
    statuses = await list_section_statuses(record.id)
    assert statuses[Section.DEVICES] is SectionStatus.NOT_ASKED


async def test_the_same_file_replaced_ends_where_it_started(owner: int) -> None:
    await _run(owner, full_seed(), replace=False, first=True)
    before = await _rows()

    report = await _run(owner, full_seed(), replace=True)

    assert report.applied is True
    assert await _rows() == before


async def test_a_replacement_keeps_what_the_local_setup_wrote(owner: int) -> None:
    await _run(owner, full_seed(), replace=False, first=True)

    await _run(owner, _changed(), replace=True)

    assert await scalar("SELECT COUNT(*) FROM entities WHERE name = 'Canary Owner'") == 1
    assert await scalar("SELECT COUNT(*) FROM household_role_assignments") == 1


async def test_a_voice_row_refuses_the_replacement_and_nothing_is_retracted(owner: int) -> None:
    await _run(owner, full_seed(), replace=False, first=True)
    await write_literal(
        owner_entity_id=owner,
        subject_entity_id=owner,
        predicate="likes",
        value="el mar",
        channel=WriteChannel.VOICE_STREAM,
        confirmed_at=NOW,
    )
    before = await _rows()

    with pytest.raises(ReplaceRefusedError):
        await _run(owner, _changed(), replace=True)

    assert await _rows() == before


async def test_a_live_candidate_refuses_the_replacement(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _run(owner, full_seed(), replace=False, first=True)
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    await candidates.insert_candidate(
        ProposedCandidate(predicate="likes", value_text="el mate", value_key="mate"),
        subject_person_id=owner,
        asserted_by_person_id=owner,
        channel=CandidateChannel.VOICE_CLASSIC,
        correlation_id=uuid4(),
        now=datetime(2026, 10, 26, 12, 0, tzinfo=UTC),
    )
    before = await _rows()

    with pytest.raises(ReplaceRefusedError):
        await _run(owner, _changed(), replace=True, commit=False)

    assert await _rows() == before


async def test_a_closed_commissioning_refuses_the_replacement(owner: int) -> None:
    report = await _run(owner, full_seed(), replace=False, first=True)
    assert report.record_id is not None
    await close_commissioning(report.record_id, NOW)

    with pytest.raises(CommissioningClosedError):
        await _run(owner, _changed(), replace=True)


async def test_a_replacement_with_no_earlier_import_is_harmless(owner: int) -> None:
    report = await _run(owner, full_seed(), replace=True, first=True)

    assert report.applied is True
    assert await scalar("SELECT COUNT(*) FROM care_contacts") == 2


async def test_a_refusal_after_the_retraction_rolls_the_retraction_back(owner: int) -> None:
    await _run(owner, full_seed(), replace=False, first=True)
    await create_third_party(name="Canary Newborn", type="person")
    before = await _rows()
    data = _changed()
    data["children"].append({"name": "Canary Newborn", "guardianship": "minor"})

    report = await _run(owner, data, replace=True)

    assert report.applied is False
    assert [o.reason for o in report.problems][:1] == ["entity_exists"]
    assert await _rows() == before
    assert (
        await scalar(
            "SELECT value_text FROM literal_facts_v4 WHERE predicate = 'birth_date' AND subject_entity_id = ?",
            owner,
        )
        == "1950-05-17"
    )


async def test_a_surviving_entity_with_another_guardianship_is_a_conflict(owner: int) -> None:
    await _run(owner, full_seed(), replace=False, first=True)
    child = await scalar("SELECT id FROM entities WHERE name = 'Canary Child'")
    await write_contact(
        owner_entity_id=owner,
        contact_entity_id=child,
        role=ContactRole.NEIGHBOR,
        phone="+56900000055",
        channel=WriteChannel.VOICE_CLASSIC,
        confirmed_at=NOW,
    )
    data = full_seed()
    data["children"][0] = {"name": "Canary Child", "guardianship": "adult"}

    report = await _run(owner, data, replace=True)

    assert ("create.child", "guardianship_conflict") in [
        (o.operation.label, o.reason) for o in report.problems
    ]
    assert report.applied is False


async def test_a_lapsed_candidate_does_not_refuse_the_replacement(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A candidate past its expiry is no longer live, even before the housekeeping scrubs it."""
    await _run(owner, full_seed(), replace=False, first=True)
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    await candidates.insert_candidate(
        ProposedCandidate(predicate="likes", value_text="el mate", value_key="mate"),
        subject_person_id=owner,
        asserted_by_person_id=owner,
        channel=CandidateChannel.VOICE_CLASSIC,
        correlation_id=uuid4(),
        now=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
    )

    report = await _run(owner, _changed(), replace=True)

    assert report.applied is True
