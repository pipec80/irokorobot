"""Hardening of the canonical writer found by the independent reviews of Plan 0065.

Each test pins a case the first tests of the plan did not vary: the order in which a SECURITY value
is refused, a stored row that disagrees with what the writer would assign, empty or backdated
validity, a membership that is not the owner's or no longer active, a personal-default predicate
about someone else, the logs that must not claim a write before the commit, and concurrent or
interrupted batches. No real clock, no real names, no value in any assertion message.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime
import logging
from typing import TYPE_CHECKING, cast
from uuid import UUID

import pytest
from server.cognition.authorization import ConsentStatus
from server.cognition.identity import ActivePersonContext, ActivePersonStatus, HouseholdRole
from server.cognition.models import Confidence, ConfidenceBasis, KnowledgeStatus
from server.exceptions import AmbiguousEntityError, UnstorableValueError, WriteRefusedError
from server.memory.canonical_writer import WriteChannel, write_literal, write_relation
from server.memory.declarative import create_third_party, upsert_entity
from server.memory.household_authorization import (
    assign_household_role,
    bootstrap_initial_owner,
)
from server.memory.policy_gated_v4_reader import PolicyGatedV4Reader
from server.memory.predicate_registry import (
    PredicateCardinality,
    PredicateDefinition,
    PredicateKind,
    resolve_predicate,
)
from server.memory.relational_v4 import (
    AssertionLifecycle,
    EntityRelationV4,
    LiteralFactV4,
    assert_entity_relation,
    assert_literal_fact,
    get_active_entity_relations,
    get_active_literal_facts,
    get_entity_relation,
    get_literal_fact,
)
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_CONFIRMED_AT = "2026-10-22T12:00:00.000000+00:00"
_ASSERTED_AT = "2026-10-22T11:59:00+00:00"
_NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
_CODE_CANARY = "canary-gate-code-5150"
_BOUND_S = 10


@dataclass(frozen=True)
class _Home:
    """An invented household plus a second, unrelated one."""

    early_partner: int
    owner: int
    child: int
    pet: int
    partner: int
    visitor: int
    town: int
    city: int
    other_owner: int
    other_child: int


def _definition(alias: str) -> PredicateDefinition:
    definition = resolve_predicate(alias)
    assert definition is not None
    return definition


@pytest.fixture
async def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Home]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "hardening.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        # Created first so its id is lower than the owner's: the sorted() path of partner_of.
        early_partner = await upsert_entity(name="Canary Early Partner", type="person")
        owner = await upsert_entity(name="Canary Owner", type="person")
        await bootstrap_initial_owner(person_entity_id=owner, confirmed_person_entity_id=owner)
        child = await upsert_entity(name="Canary Child", type="person")
        pet = await upsert_entity(name="Canary Pet", type="other")
        partner = await upsert_entity(name="Canary Partner", type="person")
        visitor = await upsert_entity(name="Canary Visitor", type="person")
        town = await upsert_entity(name="Canary Town", type="place")
        city = await upsert_entity(name="Canary City", type="place")
        other_owner = await upsert_entity(name="Canary Other Owner", type="person")
        other_child = await upsert_entity(name="Canary Other Child", type="person")
        for source, alias, target in (
            (child, "child_of", owner),
            (pet, "pet_of", owner),
            (partner, "partner_of", owner),
            (other_child, "child_of", other_owner),
        ):
            await assert_entity_relation(
                source_entity_id=source, target_entity_id=target, definition=_definition(alias)
            )
        yield _Home(
            early_partner,
            owner,
            child,
            pet,
            partner,
            visitor,
            town,
            city,
            other_owner,
            other_child,
        )
    finally:
        await db.close_db()
        db._conn = None


async def _counts() -> tuple[int, int, int]:
    conn = db.get_conn()
    counts: list[int] = []
    for table in ("literal_facts_v4", "entity_relations_v4", "entities"):
        cursor = await conn.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
        row = await cursor.fetchone()
        await cursor.close()
        assert row is not None
        counts.append(int(row[0]))
    return counts[0], counts[1], counts[2]


async def _literal(
    home: _Home,
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


async def _relation(
    home: _Home,
    source: int,
    predicate: str,
    target: int,
    channel: WriteChannel = WriteChannel.IMPORT_FILE,
    *,
    asserted_at: str | None = _ASSERTED_AT,
    valid_from: str | None = None,
    valid_to: str | None = None,
) -> EntityRelationV4:
    return await write_relation(
        owner_entity_id=home.owner,
        source_entity_id=source,
        predicate=predicate,
        target_entity_id=target,
        channel=channel,
        confirmed_at=_CONFIRMED_AT,
        asserted_at=asserted_at,
        valid_from=valid_from,
        valid_to=valid_to,
    )


def _events(caplog: pytest.LogCaptureFixture, event: str) -> list[logging.LogRecord]:
    return [record for record in caplog.records if getattr(record, "event", None) == event]


def _no_value_in_logs(caplog: pytest.LogCaptureFixture, value: str) -> bool:
    return all(
        value not in record.getMessage() and value not in repr(vars(record))
        for record in caplog.records
    )


# --- a SECURITY value is refused first, whoever it is about -----------------------------------


@pytest.mark.parametrize("who", ["owner", "child", "partner", "visitor"])
async def test_a_security_value_raises_the_security_error_before_anything_else_is_decided(
    home: _Home, caplog: pytest.LogCaptureFixture, who: str
) -> None:
    """Even about an outsider: no classification, no refusal log, no read of the stored rows."""
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("server.memory.canonical_writer").debug("control record")
        with pytest.raises(UnstorableValueError):
            await _literal(home, getattr(home, who), "access_code", _CODE_CANARY)

    assert any(record.getMessage() == "control record" for record in caplog.records)
    assert not _events(caplog, "memory.canonical_write_refused")
    assert _no_value_in_logs(caplog, _CODE_CANARY)
    assert (await _counts())[0] == 0


async def test_the_repository_refuses_a_security_predicate_whatever_sensitivity_is_asked(
    home: _Home,
) -> None:
    """A caller cannot downgrade the label: the predicate is what decides."""
    for sensitivity in ("normal", "private", None):
        with pytest.raises(UnstorableValueError):
            await assert_literal_fact(
                subject_entity_id=home.owner,
                definition=_definition("access_code"),
                value=_CODE_CANARY,
                sensitivity=sensitivity,
            )
    security_relation = PredicateDefinition(
        canonical_id="shares_code_with",
        aliases=frozenset({"shares_code_with"}),
        kind=PredicateKind.RELATION,
        cardinality=PredicateCardinality.RELATION,
        subject_types=frozenset({"person"}),
        target_types=frozenset({"person"}),
        default_sensitivity="security",
    )
    with pytest.raises(UnstorableValueError):
        await assert_entity_relation(
            source_entity_id=home.owner,
            target_entity_id=home.visitor,
            definition=security_relation,
            sensitivity="normal",
        )

    assert (await _counts())[0] == 0


# --- an existing row that disagrees with what the writer would assign -------------------------


async def test_a_stored_row_with_another_classification_is_a_conflict_not_a_success(
    home: _Home,
) -> None:
    """The local setup and the legacy migration store the registry defaults, as `household`."""
    older = await assert_literal_fact(
        subject_entity_id=home.owner, definition=_definition("birth_date"), value="1980-02-03"
    )

    with pytest.raises(WriteRefusedError) as refusal:
        await _literal(home, home.owner, "birth_date", "1980-02-03")

    assert refusal.value.reason == "classification_conflict"
    assert await get_literal_fact(older.id) == older
    assert (await _counts())[0] == 1


async def test_an_active_relation_with_another_classification_is_a_conflict_too(
    home: _Home,
) -> None:
    older = await assert_entity_relation(
        source_entity_id=home.owner,
        target_entity_id=home.town,
        definition=_definition("lives_in"),
    )

    with pytest.raises(WriteRefusedError) as refusal:
        await _relation(home, home.owner, "lives_in", home.town)

    assert refusal.value.reason == "classification_conflict"
    assert await get_entity_relation(older.id) == older


async def test_a_repeat_with_a_wild_confidence_is_still_refused(home: _Home) -> None:
    await _literal(home, home.child, "likes", "el tren")

    with pytest.raises(ValueError, match="confidence"):
        await _literal(home, home.child, "likes", "el tren", confidence=7.0)


# --- validity -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "valid_from, valid_to", [("", None), (None, ""), ("   ", None), (None, "  ")]
)
async def test_an_empty_date_is_refused_and_never_stored_as_history(
    home: _Home, valid_from: str | None, valid_to: str | None
) -> None:
    before = await _counts()

    with pytest.raises(ValueError, match="valid_"):
        await _relation(
            home, home.owner, "lives_in", home.town, valid_from=valid_from, valid_to=valid_to
        )

    assert await _counts() == before


def _day(value: str) -> date:
    """The calendar day of a stored validity value (a date, a month or a timestamp)."""
    return date.fromisoformat(value[:10] if len(value) >= 10 else f"{value[:7]}-01")


async def test_a_back_dated_move_never_leaves_an_inverted_range(home: _Home) -> None:
    """Zero-length rather than negative: the older row ends where it began."""
    current = await _relation(home, home.owner, "lives_in", home.city, valid_from="2024-06-15")

    backdated = await _relation(home, home.owner, "lives_in", home.town, valid_from="2018-03-01")

    assert backdated.lifecycle is AssertionLifecycle.ACTIVE
    cursor = await db.get_conn().execute(
        "SELECT valid_from, valid_to FROM entity_relations_v4 "
        "WHERE predicate = 'lives_in' AND valid_to IS NOT NULL"
    )
    ranges = list(await cursor.fetchall())
    await cursor.close()
    assert ranges
    assert all(_day(str(end)) >= _day(str(start)) for start, end in ranges)
    closed = await get_entity_relation(current.id)
    assert closed is not None
    assert closed.lifecycle is AssertionLifecycle.SUPERSEDED
    assert closed.valid_to == "2024-06-15"


async def test_a_spoken_date_before_an_undated_assertion_does_not_invert_either(
    home: _Home,
) -> None:
    undated = await _relation(
        home, home.owner, "lives_in", home.town, asserted_at="2026-10-22T09:00:00+00:00"
    )

    await _relation(home, home.owner, "lives_in", home.city, valid_from="2024-06")

    closed = await get_entity_relation(undated.id)
    assert closed is not None
    assert closed.valid_to is not None
    assert closed.valid_from is not None
    assert _day(closed.valid_to) >= _day(closed.valid_from)


async def test_a_repeat_with_another_date_keeps_the_first_one(home: _Home) -> None:
    """Documented: an exact repeat of an active triple returns the stored row untouched."""
    first = await _relation(home, home.owner, "lives_in", home.town, valid_from="2018-03-01")

    again = await _relation(home, home.owner, "lives_in", home.town, valid_from="2019-01-01")

    assert again == first
    assert again.valid_from == "2018-03-01"


# --- membership -------------------------------------------------------------------------------


async def test_a_child_of_someone_else_is_not_a_household_member(home: _Home) -> None:
    with pytest.raises(WriteRefusedError) as refusal:
        await _literal(home, home.other_child, "likes", "el tren")

    assert refusal.value.reason == "not_household_member"


async def test_a_former_child_is_refused(home: _Home) -> None:
    """A membership that ended is history, not a membership."""
    await _relation(home, home.visitor, "child_of", home.owner, valid_to="2010-01-01")

    with pytest.raises(WriteRefusedError):
        await _literal(home, home.visitor, "likes", "el tren")


async def test_the_partner_cannot_be_turned_into_a_child_to_unlock_their_literals(
    home: _Home,
) -> None:
    with pytest.raises(WriteRefusedError) as refusal:
        await _relation(home, home.partner, "child_of", home.owner)

    assert refusal.value.reason == "not_household_member"
    with pytest.raises(WriteRefusedError):
        await _literal(home, home.partner, "birth_date", "1985-04-05")


async def test_a_child_cannot_be_turned_into_the_partner(home: _Home) -> None:
    with pytest.raises(WriteRefusedError) as refusal:
        await _relation(home, home.owner, "partner_of", home.child)

    assert refusal.value.reason == "not_household_member"


async def test_a_second_partner_accumulates_as_the_adr_says(home: _Home) -> None:
    """`partner_of` is not temporal: a break-up is a CM-6 matter (ADR 0022 *Negative*)."""
    await _relation(home, home.owner, "partner_of", home.partner)
    await _relation(home, home.owner, "partner_of", home.early_partner)

    active = await get_active_entity_relations(definition=_definition("partner_of"))
    assert len(active) == 2


async def test_a_partner_with_a_lower_id_is_stored_once_in_either_order(home: _Home) -> None:
    assert home.early_partner < home.owner
    forward = await _relation(home, home.owner, "partner_of", home.early_partner)
    backward = await _relation(
        home, home.early_partner, "partner_of", home.owner, WriteChannel.VOICE_STREAM
    )

    assert backward.id == forward.id
    assert (backward.source_entity_id, backward.target_entity_id) == (
        home.early_partner,
        home.owner,
    )
    assert backward.channel == "import_file"


async def test_a_partner_cannot_be_their_own_partner(home: _Home) -> None:
    with pytest.raises(WriteRefusedError) as refusal:
        await _relation(home, home.owner, "partner_of", home.owner)

    assert refusal.value.reason == "not_household_member"


async def test_an_adult_child_is_classified_like_a_minor(home: _Home) -> None:
    """The subject has a birth date that makes them 40; the writer does not look at it (D-2)."""
    await _relation(home, home.visitor, "child_of", home.owner)
    adult_birth = await _literal(home, home.visitor, "birth_date", "1986-01-02")
    minor_birth = await _literal(home, home.child, "birth_date", "2018-05-06")

    assert (adult_birth.visibility, adult_birth.sensitivity) == (
        minor_birth.visibility,
        minor_birth.sensitivity,
    )
    assert (adult_birth.visibility, adult_birth.sensitivity) == ("household", "child_data")


# --- a personal-default predicate is only about the owner -------------------------------------


async def test_a_personal_default_predicate_is_only_about_the_owner(home: _Home) -> None:
    own = await _literal(home, home.owner, "private_topic", "salud")
    assert (own.visibility, own.sensitivity) == ("personal", "normal")

    with pytest.raises(WriteRefusedError) as refusal:
        await _literal(home, home.child, "private_topic", "salud")

    assert refusal.value.reason == "owner_only_predicate"
    assert (
        await get_active_literal_facts(
            subject_entity_id=home.child, definition=_definition("private_topic")
        )
        == []
    )


# --- the reader serves what the writer stores for a child or a pet ---------------------------


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


async def test_the_household_reader_serves_a_childs_and_a_pets_stated_age(home: _Home) -> None:
    await _literal(home, home.child, "stated_age", "7")
    await _literal(home, home.pet, "stated_age", "3")
    await _literal(home, home.owner, "stated_age", "41")
    reader = PolicyGatedV4Reader()

    async def read(subject: int, turn: int) -> tuple[KnowledgeStatus, list[str]]:
        result = await reader.read_active_literals(
            actor=_owner_actor(home.owner),
            subject_entity_id=subject,
            predicate_alias="edad_dicha",
            consent=ConsentStatus.GRANTED,
            correlation_id=UUID(int=turn),
            requested_at=_NOW,
        )
        return result.status, [fact.value_text for fact in result.facts]

    assert await read(home.child, 1) == (KnowledgeStatus.KNOWN, ["7"])
    assert await read(home.pet, 2) == (KnowledgeStatus.KNOWN, ["3"])
    # The owner's own facts are `personal`: the household reader does not serve them (CM-5).
    assert (await read(home.owner, 3))[0] is not KnowledgeStatus.KNOWN


# --- idempotence compares a text by its key (ADR 0024 decision 12, Plan 0071) ------------------


async def test_idempotence_folds_a_text_by_its_key(home: _Home) -> None:
    """A spoken and an imported spelling differing by case are one row: the writer folds text."""
    spoken = await _literal(home, home.child, "likes", "el tren", WriteChannel.VOICE_STREAM)
    imported = await _literal(home, home.child, "likes", "El tren")

    assert spoken.id == imported.id


# --- logs: ids and closed fields only, and "written" waits for the commit ---------------------


async def test_the_refusal_log_exists_and_carries_only_closed_fields(
    home: _Home, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO), pytest.raises(WriteRefusedError):
        await _literal(home, home.visitor, "likes", _CODE_CANARY, WriteChannel.VOICE_CLASSIC)

    records = _events(caplog, "memory.canonical_write_refused")
    assert len(records) == 1
    record = records[0]
    assert (record.reason, record.predicate, record.channel) == (  # type: ignore[attr-defined]  # structured extra
        "not_household_member",
        "likes",
        "voice_classic",
    )
    assert _no_value_in_logs(caplog, _CODE_CANARY)


async def test_a_write_is_logged_once_and_only_after_it_commits(
    home: _Home, caplog: pytest.LogCaptureFixture
) -> None:
    async def rolled_back() -> None:
        async with db.transaction():
            await write_literal(
                owner_entity_id=home.owner,
                subject_entity_id=home.child,
                predicate="likes",
                value="el tren",
                channel=WriteChannel.IMPORT_FILE,
                confirmed_at=_CONFIRMED_AT,
                manage_transaction=False,
            )
            raise RuntimeError("rolled back")

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(RuntimeError, match="rolled back"):
            await rolled_back()
        staged = _events(caplog, "memory.canonical_write")
        assert [record.levelno for record in staged] == [logging.DEBUG]
        caplog.clear()

        await _literal(home, home.child, "likes", "el tren")

    assert len(_events(caplog, "memory.canonical_write")) == 1
    assert _events(caplog, "memory.canonical_write")[0].levelno == logging.INFO


async def test_a_third_party_is_announced_only_after_its_transaction_commits(
    home: _Home, caplog: pytest.LogCaptureFixture
) -> None:
    async def rolled_back() -> None:
        async with db.transaction():
            await create_third_party(
                name="Canary Grandchild", type="person", manage_transaction=False
            )
            raise RuntimeError("rolled back")

    with caplog.at_level(logging.DEBUG), pytest.raises(RuntimeError, match="rolled back"):
        await rolled_back()

    staged = _events(caplog, "entity.third_party_created")
    assert [record.levelno for record in staged] == [logging.DEBUG]


async def test_a_third_party_with_odd_stored_attributes_is_ambiguous_not_a_crash(
    home: _Home,
) -> None:
    conn = db.get_conn()
    await conn.execute(
        "INSERT INTO entities (name, type, attributes, aliases) VALUES (?, 'person', '[]', '[]')",
        ("Canary Odd",),
    )
    await conn.commit()

    with pytest.raises(AmbiguousEntityError):
        await create_third_party(name="Canary Odd", type="person", import_key="k1")


# --- batches: concurrent, interrupted, partly refused ----------------------------------------


async def test_two_identical_literal_writes_make_one_row(home: _Home) -> None:
    first, second = await asyncio.wait_for(
        asyncio.gather(
            _literal(home, home.child, "likes", "el tren"),
            _literal(home, home.child, "likes", "el tren", WriteChannel.VOICE_STREAM),
        ),
        _BOUND_S,
    )

    assert first.id == second.id
    assert (await _counts())[0] == 1


async def test_two_identical_relation_writes_make_one_row(home: _Home) -> None:
    before = (await _counts())[1]

    first, second = await asyncio.wait_for(
        asyncio.gather(
            _relation(home, home.owner, "lives_in", home.town),
            _relation(home, home.owner, "lives_in", home.town, WriteChannel.VOICE_STREAM),
        ),
        _BOUND_S,
    )

    assert first.id == second.id
    assert (await _counts())[1] == before + 1


async def test_two_stated_ages_at_once_leave_exactly_one_active(home: _Home) -> None:
    await asyncio.wait_for(
        asyncio.gather(
            _literal(home, home.child, "stated_age", "7"),
            _literal(home, home.child, "stated_age", "8"),
        ),
        _BOUND_S,
    )

    active = await get_active_literal_facts(
        subject_entity_id=home.child, definition=_definition("stated_age")
    )
    assert len(active) == 1


async def test_a_caught_refusal_leaves_the_rest_of_a_batch_committable(home: _Home) -> None:
    """The «preview and skip» importer: refuse one line, keep the others, commit once."""

    async def batch() -> tuple[int, int]:
        async with db.transaction():
            kept = await write_literal(
                owner_entity_id=home.owner,
                subject_entity_id=home.child,
                predicate="likes",
                value="el tren",
                channel=WriteChannel.IMPORT_FILE,
                confirmed_at=_CONFIRMED_AT,
                manage_transaction=False,
            )
            with pytest.raises(WriteRefusedError):
                await write_literal(
                    owner_entity_id=home.owner,
                    subject_entity_id=home.visitor,
                    predicate="likes",
                    value="el jazz",
                    channel=WriteChannel.IMPORT_FILE,
                    confirmed_at=_CONFIRMED_AT,
                    manage_transaction=False,
                )
            relation = await write_relation(
                owner_entity_id=home.owner,
                source_entity_id=home.child,
                predicate="lives_in",
                target_entity_id=home.town,
                channel=WriteChannel.IMPORT_FILE,
                confirmed_at=_CONFIRMED_AT,
                manage_transaction=False,
            )
        return kept.id, relation.id

    fact_id, relation_id = await asyncio.wait_for(batch(), _BOUND_S)

    assert await get_literal_fact(fact_id) is not None
    assert await get_entity_relation(relation_id) is not None


async def test_a_failure_in_the_middle_of_a_batch_rolls_everything_back(home: _Home) -> None:
    before = await _counts()

    async def batch() -> None:
        async with db.transaction():
            await write_literal(
                owner_entity_id=home.owner,
                subject_entity_id=home.child,
                predicate="likes",
                value="el tren",
                channel=WriteChannel.IMPORT_FILE,
                confirmed_at=_CONFIRMED_AT,
                manage_transaction=False,
            )
            await write_literal(
                owner_entity_id=home.owner,
                subject_entity_id=home.child,
                predicate="stated_age",
                value="ocho",
                channel=WriteChannel.IMPORT_FILE,
                confirmed_at=_CONFIRMED_AT,
                manage_transaction=False,
            )

    with pytest.raises(ValueError, match="canonical literal"):
        await asyncio.wait_for(batch(), _BOUND_S)

    assert await _counts() == before


async def test_a_plain_channel_string_is_accepted(home: _Home) -> None:
    fact = await write_literal(
        owner_entity_id=home.owner,
        subject_entity_id=home.child,
        predicate="likes",
        value="el tren",
        channel=cast("WriteChannel", "voice_stream"),
        confirmed_at=_CONFIRMED_AT,
    )

    assert fact.channel == "voice_stream"


# --- who already holds a household role is not somebody's child -------------------------------


async def test_someone_who_holds_an_adult_role_cannot_be_declared_a_child(home: _Home) -> None:
    await assign_household_role(
        person_entity_id=home.visitor, role=HouseholdRole.ADULT, grantor_entity_id=home.owner
    )

    with pytest.raises(WriteRefusedError) as refusal:
        await _relation(home, home.visitor, "child_of", home.owner)

    assert refusal.value.reason == "not_household_member"
    with pytest.raises(WriteRefusedError):
        await _literal(home, home.visitor, "birth_date", "1980-01-02")


async def test_someone_with_the_child_role_can_be_declared_a_child(home: _Home) -> None:
    await assign_household_role(
        person_entity_id=home.visitor, role=HouseholdRole.CHILD, grantor_entity_id=home.owner
    )

    relation = await _relation(home, home.visitor, "child_of", home.owner)

    assert (relation.visibility, relation.sensitivity) == ("household", "child_data")
