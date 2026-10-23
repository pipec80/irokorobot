"""The canonical writer, literals (Plan 0065 Task 6a, ADR 0022 decisions 2, 4, 5 and 9).

One writer serves every channel: the same fact written through the spoken confirmation or the
import is stored with the same classification, assigned by the writer from the predicate and the
subject, and records who asserted it and through which channel.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import inspect
from itertools import count
import logging
from typing import TYPE_CHECKING, cast
from uuid import UUID

import pytest
from server.cognition.authorization import ConsentStatus
from server.cognition.identity import ActivePersonContext, ActivePersonStatus, HouseholdRole
from server.cognition.models import Confidence, ConfidenceBasis, KnowledgeStatus
from server.exceptions import UnstorableValueError, WriteRefusedError
from server.memory.candidate_types import CandidateChannel
from server.memory.canonical_writer import WriteChannel, write_literal
from server.memory.declarative import upsert_entity
from server.memory.household_authorization import bootstrap_initial_owner
from server.memory.policy_gated_v4_reader import PolicyGatedV4Reader
from server.memory.predicate_registry import PredicateDefinition, resolve_predicate
from server.memory.relational_v4 import (
    AssertionLifecycle,
    LiteralFactV4,
    assert_entity_relation,
    get_active_literal_facts,
    get_literal_fact,
)
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

_CONFIRMED_AT = "2026-10-22T12:00:00.000000+00:00"
_ASSERTED_AT = "2026-10-22T11:59:00.000000+00:00"
_NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
_CODE_CANARY = "canary-gate-code-5150"


@dataclass(frozen=True)
class _Household:
    """The people and pets of one invented household."""

    owner: int
    child: int
    pet: int
    partner: int
    visitor: int


@pytest.fixture
async def household(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Household]:
    """A migrated database with an owner, a child, a pet, a partner and an unrelated person."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "canonical-writer.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        owner = await upsert_entity(name="Canary Owner", type="person")
        await bootstrap_initial_owner(person_entity_id=owner, confirmed_person_entity_id=owner)
        child = await upsert_entity(name="Canary Child", type="person")
        pet = await upsert_entity(name="Canary Pet", type="other")
        partner = await upsert_entity(name="Canary Partner", type="person")
        visitor = await upsert_entity(name="Canary Visitor", type="person")
        for source, alias, target in (
            (child, "child_of", owner),
            (pet, "pet_of", owner),
            (partner, "partner_of", owner),
        ):
            definition = resolve_predicate(alias)
            assert definition is not None
            await assert_entity_relation(
                source_entity_id=source, target_entity_id=target, definition=definition
            )
        yield _Household(owner, child, pet, partner, visitor)
    finally:
        await db.close_db()
        db._conn = None


async def _count_literals() -> int:
    cursor = await db.get_conn().execute("SELECT COUNT(*) FROM literal_facts_v4")
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return int(row[0])


async def _write(
    home: _Household,
    subject: int,
    predicate: str,
    value: str,
    channel: WriteChannel = WriteChannel.IMPORT_FILE,
    *,
    confidence: float = 0.9,
    asserted_at: str | None = None,
) -> LiteralFactV4:
    return await write_literal(
        owner_entity_id=home.owner,
        subject_entity_id=subject,
        predicate=predicate,
        value=value,
        channel=channel,
        confirmed_at=_CONFIRMED_AT,
        confidence=confidence,
        asserted_at=asserted_at,
    )


@pytest.mark.integration
async def test_the_same_fact_from_two_channels_has_one_classification(
    household: _Household,
) -> None:
    """A conversation fact and an import fact of one subject are stored alike."""
    spoken = await _write(household, household.child, "likes", "el tren", WriteChannel.VOICE_STREAM)
    imported = await _write(household, household.child, "likes", "los autos")

    assert (spoken.visibility, spoken.sensitivity) == ("household", "normal")
    assert (imported.visibility, imported.sensitivity) == ("household", "normal")
    assert (spoken.channel, imported.channel) == ("voice_stream", "import_file")
    owner_spoken = await _write(
        household, household.owner, "likes", "el mate", WriteChannel.VOICE_CLASSIC
    )
    owner_imported = await _write(household, household.owner, "likes", "el cafe")
    assert (owner_spoken.visibility, owner_spoken.sensitivity) == ("personal", "normal")
    assert (owner_imported.visibility, owner_imported.sensitivity) == ("personal", "normal")


@pytest.mark.integration
async def test_the_classification_table_by_subject_and_predicate(household: _Household) -> None:
    owner_birth = await _write(household, household.owner, "birth_date", "1980-02-03")
    child_birth = await _write(household, household.child, "birth_date", "2018-05-06")
    child_age = await _write(household, household.child, "stated_age", "7")
    pet_species = await _write(household, household.pet, "species", "gato")
    pet_age = await _write(household, household.pet, "stated_age", "3")
    owner_topic = await _write(household, household.owner, "private_topic", "salud")

    assert (owner_birth.visibility, owner_birth.sensitivity) == ("personal", "private")
    assert (child_birth.visibility, child_birth.sensitivity) == ("household", "child_data")
    assert (child_age.visibility, child_age.sensitivity) == ("household", "child_data")
    assert (pet_species.visibility, pet_species.sensitivity) == ("household", "normal")
    assert (pet_age.visibility, pet_age.sensitivity) == ("household", "child_data")
    assert (owner_topic.visibility, owner_topic.sensitivity) == ("personal", "normal")


@pytest.mark.integration
@pytest.mark.parametrize("who", ["partner", "visitor", "missing"])
async def test_a_literal_about_the_partner_or_an_outsider_is_refused(
    household: _Household, who: str
) -> None:
    """Other adults: name and relationship only (ADR 0022 decision 4)."""
    subject = {
        "partner": household.partner,
        "visitor": household.visitor,
        "missing": 987654,
    }[who]

    with pytest.raises(WriteRefusedError) as refusal:
        await _write(household, subject, "likes", "el jazz")

    assert refusal.value.reason == "not_household_member"
    assert "el jazz" not in str(refusal.value)
    assert await _count_literals() == 0


@pytest.mark.integration
async def test_nobody_but_the_subject_writes_into_the_subjects_personal_memory(
    household: _Household,
) -> None:
    """The invariant of ADR 0022 decision 5: a caller cannot even ask for another's `personal`."""
    signature = inspect.signature(write_literal)
    assert not set(signature.parameters) & {"visibility", "sensitivity", "asserted_by_entity_id"}
    with pytest.raises(TypeError):
        signature.bind(
            owner_entity_id=household.owner,
            subject_entity_id=household.child,
            predicate="likes",
            value="el tren",
            channel=WriteChannel.IMPORT_FILE,
            confirmed_at=_CONFIRMED_AT,
            visibility="personal",
        )

    for subject in (household.child, household.pet):
        fact = await _write(household, subject, "likes", "el sol")
        assert fact.visibility == "household"
    stored = await get_active_literal_facts(
        subject_entity_id=household.owner, definition=_definition("likes")
    )
    assert stored == []


@pytest.mark.integration
async def test_a_security_value_is_refused_without_a_trace(
    household: _Household, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("server.memory.canonical_writer").debug("control record")
        with pytest.raises(UnstorableValueError) as refusal:
            await _write(household, household.owner, "access_code", _CODE_CANARY)
    assert any(record.getMessage() == "control record" for record in caplog.records)

    assert await _count_literals() == 0
    assert _CODE_CANARY not in str(refusal.value) + repr(refusal.value)
    assert all(
        _CODE_CANARY not in record.getMessage() and _CODE_CANARY not in repr(vars(record))
        for record in caplog.records
    )


@pytest.mark.integration
async def test_the_stored_row_records_who_asserted_it_and_through_which_channel(
    household: _Household,
) -> None:
    fact = await _write(
        household,
        household.child,
        "likes",
        "el tren",
        WriteChannel.VOICE_CLASSIC,
        confidence=1.0,
        asserted_at=_ASSERTED_AT,
    )

    stored = await get_literal_fact(fact.id)
    assert stored == fact
    assert fact.asserted_by_entity_id == household.owner
    assert fact.confirmed_by_entity_id == household.owner
    assert fact.confirmed_at == _CONFIRMED_AT
    assert fact.channel == "voice_classic"
    assert fact.confidence == 1.0
    assert fact.asserted_at == _ASSERTED_AT
    assert fact.lifecycle is AssertionLifecycle.ACTIVE


@pytest.mark.integration
async def test_an_exact_repeat_is_idempotent(household: _Household) -> None:
    first = await _write(household, household.child, "likes", "el tren", WriteChannel.VOICE_STREAM)

    again = await _write(household, household.child, "likes", "el tren", WriteChannel.IMPORT_FILE)

    assert again.id == first.id
    assert again.channel == "voice_stream"
    assert await _count_literals() == 1


@pytest.mark.integration
async def test_a_single_current_literal_supersedes_the_previous_value(
    household: _Household,
) -> None:
    first = await _write(
        household, household.child, "stated_age", "7", asserted_at="2026-01-10T09:00:00+00:00"
    )
    second = await _write(
        household, household.child, "stated_age", "8", asserted_at="2027-02-11T09:00:00+00:00"
    )

    active = await get_active_literal_facts(
        subject_entity_id=household.child, definition=_definition("stated_age")
    )
    assert [fact.value_text for fact in active] == ["8"]
    assert active[0].asserted_at == second.asserted_at == "2027-02-11T09:00:00+00:00"
    superseded = await get_literal_fact(first.id)
    assert superseded is not None
    assert superseded.lifecycle is AssertionLifecycle.SUPERSEDED


def _owner_actor(owner_id: int) -> ActivePersonContext:
    return ActivePersonContext(
        person_id=owner_id,
        display_name="Owner",
        status=ActivePersonStatus.IDENTIFIED,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.ASSERTED, calibrated=False),
        role=HouseholdRole.OWNER,
        evidence=(),
        resolved_at=_NOW,
    )


@pytest.mark.integration
async def test_the_household_reader_still_returns_what_the_writer_stores(
    household: _Household,
) -> None:
    """The stored classification equals the registry default, so the reader's equality holds."""
    await _write(household, household.child, "likes", "el tren")
    await _write(household, household.child, "birth_date", "2018-05-06")
    await _write(household, household.pet, "species", "gato")
    reader = PolicyGatedV4Reader()
    turns = count(1)

    async def read(subject: int, alias: str, consent: ConsentStatus) -> list[str]:
        result = await reader.read_active_literals(
            actor=_owner_actor(household.owner),
            subject_entity_id=subject,
            predicate_alias=alias,
            consent=consent,
            correlation_id=UUID(int=next(turns)),
            requested_at=_NOW,
        )
        assert result.status is KnowledgeStatus.KNOWN, (subject, alias)
        return [fact.value_text for fact in result.facts]

    assert await read(household.child, "le_gusta", ConsentStatus.NOT_REQUIRED) == ["el tren"]
    assert await read(household.pet, "especie", ConsentStatus.NOT_REQUIRED) == ["gato"]
    assert await read(household.child, "fecha_nacimiento", ConsentStatus.GRANTED) == ["2018-05-06"]


@pytest.mark.integration
@pytest.mark.parametrize(
    "predicate, value, channel",
    [
        ("inventado", "x", WriteChannel.IMPORT_FILE),
        ("child_of", "x", WriteChannel.IMPORT_FILE),
        ("stated_age", "ocho", WriteChannel.IMPORT_FILE),
        ("likes", "el tren", "telepathy"),
    ],
)
async def test_an_unknown_predicate_a_relation_a_bad_value_or_a_bad_channel_is_refused(
    household: _Household, predicate: str, value: str, channel: str
) -> None:
    with pytest.raises(ValueError, match=r"."):
        await write_literal(
            owner_entity_id=household.owner,
            subject_entity_id=household.child,
            predicate=predicate,
            value=value,
            channel=cast("WriteChannel", channel),  # the point: a channel outside the list
            confirmed_at=_CONFIRMED_AT,
        )

    assert await _count_literals() == 0


@pytest.mark.unit
def test_the_channels_are_a_closed_list_that_covers_the_candidates() -> None:
    assert {channel.value for channel in WriteChannel} == {
        "voice_classic",
        "voice_stream",
        "import_file",
    }
    assert {channel.value for channel in CandidateChannel} <= {c.value for c in WriteChannel}


def _definition(alias: str) -> PredicateDefinition:
    definition = resolve_predicate(alias)
    assert definition is not None
    return definition
