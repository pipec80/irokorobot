"""The canonical writer's refuse-on-conflict policy and the honest confirmer (Plan 0070 Task 4b).

ADR 0024 decisions 6 and 8: a load made while commissioning refuses to overwrite a value that
differs from the stored one, and an interview whose owner did not confirm stores no confirmer.
Every name is an invented canary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from server.cognition.authorization import ConsentStatus
from server.cognition.identity import ActivePersonContext, ActivePersonStatus, HouseholdRole
from server.cognition.models import Confidence, ConfidenceBasis, KnowledgeStatus
from server.exceptions import WriteRefusedError
from server.memory.canonical_writer import write_literal, write_relation
from server.memory.declarative import create_third_party, upsert_entity
from server.memory.household_authorization import bootstrap_initial_owner
from server.memory.policy_gated_v4_reader import PolicyGatedV4Reader
from server.memory.predicate_registry import resolve_predicate
from server.memory.relational_v4 import (
    AssertionLifecycle,
    get_active_entity_relations,
    get_active_literal_facts,
    get_literal_fact,
)
from server.memory.write_types import ConflictPolicy, WriteChannel
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from server.memory.predicate_registry import PredicateDefinition
    from server.memory.relational_v4 import EntityRelationV4, LiteralFactV4

pytestmark = pytest.mark.integration

_CONFIRMED_AT = "2026-10-22T12:00:00.000000+00:00"
_NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
_CHANNEL = WriteChannel.IMPORT_ASSISTED


@dataclass(frozen=True)
class _Home:
    owner: int
    partner: int
    suitor: int
    town: int
    city: int


@pytest.fixture
async def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Home]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "canonical-conflicts.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        owner = await upsert_entity(name="Canary Owner", type="person")
        await bootstrap_initial_owner(person_entity_id=owner, confirmed_person_entity_id=owner)
        partner = await create_third_party(name="Canary Partner", type="person")
        suitor = await create_third_party(name="Canary Suitor", type="person")
        town = await upsert_entity(name="Canary Town", type="place")
        city = await upsert_entity(name="Canary City", type="place")
        yield _Home(owner, partner, suitor, town, city)
    finally:
        await db.close_db()
        db._conn = None


def _definition(alias: str) -> PredicateDefinition:
    definition = resolve_predicate(alias)
    assert definition is not None
    return definition


async def _literal(
    home: _Home,
    predicate: str,
    value: str,
    *,
    on_conflict: ConflictPolicy = ConflictPolicy.REFUSE,
    confirmed_by_owner: bool = True,
) -> LiteralFactV4:
    return await write_literal(
        owner_entity_id=home.owner,
        subject_entity_id=home.owner,
        predicate=predicate,
        value=value,
        channel=_CHANNEL,
        confirmed_at=_CONFIRMED_AT,
        on_conflict=on_conflict,
        confirmed_by_owner=confirmed_by_owner,
    )


async def _relate(
    home: _Home,
    source: int,
    predicate: str,
    target: int,
    *,
    on_conflict: ConflictPolicy = ConflictPolicy.REFUSE,
    confirmed_by_owner: bool = True,
) -> EntityRelationV4:
    return await write_relation(
        owner_entity_id=home.owner,
        source_entity_id=source,
        predicate=predicate,
        target_entity_id=target,
        channel=_CHANNEL,
        confirmed_at=_CONFIRMED_AT,
        on_conflict=on_conflict,
        confirmed_by_owner=confirmed_by_owner,
    )


# --- refuse on conflict -------------------------------------------------------------------------


async def test_a_second_single_value_that_differs_is_refused_and_the_first_stays_active(
    home: _Home,
) -> None:
    first = await _literal(home, "birth_date", "1950-01-02")

    with pytest.raises(WriteRefusedError) as refusal:
        await _literal(home, "birth_date", "1951-01-02")

    assert refusal.value.reason == "value_conflict"
    active = await get_active_literal_facts(
        subject_entity_id=home.owner, definition=_definition("birth_date")
    )
    assert [fact.id for fact in active] == [first.id]


async def test_the_same_single_value_is_idempotent_under_the_refusing_policy(home: _Home) -> None:
    first = await _literal(home, "birth_date", "1950-01-02")

    again = await _literal(home, "birth_date", "1950-01-02")

    assert again.id == first.id


async def test_a_multi_value_predicate_never_conflicts(home: _Home) -> None:
    await _literal(home, "likes", "el mate")
    await _literal(home, "likes", "el cafe")

    active = await get_active_literal_facts(
        subject_entity_id=home.owner, definition=_definition("likes")
    )
    assert sorted(fact.value_text for fact in active) == ["el cafe", "el mate"]


async def test_the_default_policy_still_supersedes(home: _Home) -> None:
    first = await _literal(home, "birth_date", "1950-01-02", on_conflict=ConflictPolicy.SUPERSEDE)

    second = await _literal(home, "birth_date", "1951-01-02", on_conflict=ConflictPolicy.SUPERSEDE)

    assert second.id != first.id
    superseded = await get_literal_fact(first.id)
    assert superseded is not None
    assert superseded.lifecycle is AssertionLifecycle.SUPERSEDED


@pytest.mark.parametrize("reversed_ends", [False, True])
async def test_a_second_partner_is_refused_from_either_end(
    home: _Home, reversed_ends: bool
) -> None:
    first = await _relate(home, home.owner, "partner_of", home.partner)
    source, target = (home.suitor, home.owner) if reversed_ends else (home.owner, home.suitor)

    with pytest.raises(WriteRefusedError) as refusal:
        await _relate(home, source, "partner_of", target)

    assert refusal.value.reason == "value_conflict"
    assert [
        row.id for row in await get_active_entity_relations(definition=_definition("partner_of"))
    ] == [first.id]


async def test_the_same_partner_again_is_idempotent(home: _Home) -> None:
    first = await _relate(home, home.owner, "partner_of", home.partner)

    again = await _relate(home, home.partner, "partner_of", home.owner)

    assert again.id == first.id


async def test_a_second_home_is_refused_and_the_same_one_is_idempotent(home: _Home) -> None:
    first = await _relate(home, home.owner, "lives_in", home.town)

    again = await _relate(home, home.owner, "lives_in", home.town)
    with pytest.raises(WriteRefusedError) as refusal:
        await _relate(home, home.owner, "lives_in", home.city)

    assert again.id == first.id
    assert refusal.value.reason == "value_conflict"


async def test_the_refusal_logs_only_the_reason_the_predicate_and_the_channel(
    home: _Home, caplog: pytest.LogCaptureFixture
) -> None:
    await _literal(home, "birth_date", "1950-01-02")

    with caplog.at_level(logging.DEBUG), pytest.raises(WriteRefusedError) as refusal:
        await _literal(home, "birth_date", "1951-01-02")

    events = [
        r for r in caplog.records if getattr(r, "event", "") == "memory.canonical_write_refused"
    ]
    assert len(events) == 1
    record = events[0]
    assert (
        getattr(record, "reason", None),
        getattr(record, "predicate", None),
        getattr(record, "channel", None),
    ) == ("value_conflict", "birth_date", "import_assisted")
    assert "1951" not in refusal.value.reason + str(refusal.value)
    assert all("1951" not in r.getMessage() and "1951" not in repr(vars(r)) for r in caplog.records)


# --- an honest confirmer ------------------------------------------------------------------------


async def test_a_literal_the_owner_did_not_confirm_stores_no_confirmer_but_keeps_the_date(
    home: _Home,
) -> None:
    fact = await _literal(home, "likes", "el mate", confirmed_by_owner=False)

    assert fact.confirmed_by_entity_id is None
    assert fact.confirmed_at == _CONFIRMED_AT
    assert fact.asserted_by_entity_id == home.owner


async def test_a_relation_the_owner_did_not_confirm_stores_no_confirmer_but_keeps_the_date(
    home: _Home,
) -> None:
    relation = await _relate(home, home.owner, "lives_in", home.town, confirmed_by_owner=False)

    assert relation.confirmed_by_entity_id is None
    assert relation.confirmed_at == _CONFIRMED_AT
    assert relation.asserted_by_entity_id == home.owner


async def test_the_default_confirmer_is_the_owner(home: _Home) -> None:
    fact = await _literal(home, "likes", "el mate")

    assert fact.confirmed_by_entity_id == home.owner


async def test_the_policy_gated_reader_still_serves_what_nobody_confirmed(home: _Home) -> None:
    child = await create_third_party(name="Canary Child", type="person")
    membership = await _relate(home, child, "child_of", home.owner, confirmed_by_owner=False)
    taste = await write_literal(
        owner_entity_id=home.owner,
        subject_entity_id=child,
        predicate="likes",
        value="el tren",
        channel=_CHANNEL,
        confirmed_at=_CONFIRMED_AT,
        confirmed_by_owner=False,
    )
    actor = ActivePersonContext(
        person_id=home.owner,
        display_name="Owner",
        status=ActivePersonStatus.IDENTIFIED,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.ASSERTED, calibrated=False),
        role=HouseholdRole.OWNER,
        evidence=(),
        resolved_at=_NOW,
    )
    reader = PolicyGatedV4Reader()

    literals = await reader.read_active_literals(
        actor=actor,
        subject_entity_id=child,
        predicate_alias="le_gusta",
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=UUID(int=1),
        requested_at=_NOW,
    )
    relations = await reader.read_active_relations(
        actor=actor,
        predicate_alias="hijo_de",
        target_entity_id=home.owner,
        consent=ConsentStatus.GRANTED,
        correlation_id=UUID(int=2),
        requested_at=_NOW,
    )

    assert (membership.confirmed_by_entity_id, taste.confirmed_by_entity_id) == (None, None)
    assert literals.status is KnowledgeStatus.KNOWN
    assert [fact.value_text for fact in literals.facts] == ["el tren"]
    assert relations.status is KnowledgeStatus.KNOWN
