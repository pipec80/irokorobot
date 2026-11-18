"""Every store writes its times in the one 32-character format (Plan 0085, decision D-3).

One write path per store, over a temporary SQLite opened like production. Every time column the
path touches must hold exactly ``YYYY-MM-DDTHH:MM:SS.ffffff+00:00``, including the columns whose SQL
default used to fire because the INSERT left them out. The validity of a temporal relation is a
household day, never an instant. Canary rows only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import re
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
from server.cognition.identity import HouseholdRole
from server.cognition.pin_credentials import EncodedPinCredential
from server.memory import candidates, conversation_record as record, recall_store, relational_v4
from server.memory.biometric_consent import grant_face_consent, revoke_face_consent
from server.memory.candidate_types import CandidateChannel, ProposedCandidate
from server.memory.care_contacts import ContactRole, revoke_contact, write_contact
from server.memory.conversation_consent import (
    grant_conversation_consent,
)
from server.memory.conversation_episodes import EpisodeOutcome, write_episode
from server.memory.conversation_summary import EpisodeDraft
from server.memory.conversation_types import TurnVerdict, make_turn
from server.memory.declarative import create_third_party, upsert_entity
from server.memory.deletion_register import withdraw_conversation_consent
from server.memory.household_authorization import (
    assign_household_role,
    bootstrap_initial_owner,
    revoke_active_role,
)
from server.memory.meta import set_flag
from server.memory.owner_credentials import revoke_owner_pin_credential, save_owner_pin_credential
from server.memory.predicate_registry import PredicateDefinition, resolve_predicate
from server.memory.relational_v4 import (
    assert_entity_relation,
    assert_literal_fact,
    get_entity_relation,
    get_literal_fact,
    revoke_entity_relation,
    revoke_literal_fact,
)
from server.memory.voice_consent import grant_voice_consent, revoke_voice_consent
from server.memory.write_types import WriteChannel
from server.settings import settings
from server.timestamps import instant_text

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_INSTANT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00")
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_T0 = datetime(2026, 10, 29, 10, 0, tzinfo=UTC)


@pytest.fixture
async def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """A fresh temporary database with the full schema, opened like production."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "time-format.db")
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    monkeypatch.setattr(settings, "conversation_record_enabled", True)
    monkeypatch.setattr(settings, "conversation_episodes_enabled", True)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield
    await db.close_db()
    db._conn = None


async def _assert_instants(table: str, *columns: str) -> None:
    """Each column holds at least one value and every value is a 32-character instant."""
    for column in columns:
        values = await _days(table, column)
        assert values, f"{table}.{column} was never written"
        assert all(_INSTANT.fullmatch(value) for value in values), (table, column, values)


async def _person(name: str) -> int:
    return await upsert_entity(name=name, type="person")


def _credential() -> EncodedPinCredential:
    return EncodedPinCredential(
        algorithm="scrypt",
        parameters_json='{"n": 32768, "r": 8, "p": 3, "dklen": 32}',
        salt=b"0" * 16,
        verifier=b"1" * 32,
    )


def _definition(alias: str) -> PredicateDefinition:
    definition = resolve_predicate(alias)
    assert definition is not None
    return definition


@pytest.mark.usefixtures("store")
async def test_meta_flag_writes_its_time() -> None:
    await set_flag("canary", "one")
    await set_flag("canary", "two")

    await _assert_instants("meta", "updated_at")


@pytest.mark.usefixtures("store")
async def test_entities_write_their_times() -> None:
    await _person("Canary Owner")
    await upsert_entity(name="Canary Owner", type="person", attributes={"k": "v"})
    await create_third_party(name="Canary Third", type="person")

    await _assert_instants("entities", "created_at", "updated_at")


@pytest.mark.usefixtures("store")
async def test_care_contacts_write_their_times() -> None:
    owner = await _person("Canary Owner")
    contact = await create_third_party(name="Canary Neighbour", type="person")
    stamp = instant_text(_T0)
    row = await write_contact(
        owner_entity_id=owner,
        contact_entity_id=contact,
        role=ContactRole.NEIGHBOR,
        phone="+56900000001",
        channel=WriteChannel.ADMIN_LOCAL,
        confirmed_at=stamp,
    )
    await write_contact(
        owner_entity_id=owner,
        contact_entity_id=contact,
        role=ContactRole.NEIGHBOR,
        phone="+56900000002",
        channel=WriteChannel.ADMIN_LOCAL,
        confirmed_at=stamp,
    )
    assert await revoke_contact(row.id, revoked_at=stamp) is False

    await _assert_instants("care_contacts", "created_at", "confirmed_at", "revoked_at")


@pytest.mark.usefixtures("store")
async def test_household_roles_and_their_audit_write_their_times() -> None:
    owner = await _person("Canary Owner")
    adult = await _person("Canary Adult")
    await bootstrap_initial_owner(person_entity_id=owner, confirmed_person_entity_id=owner)
    await assign_household_role(
        person_entity_id=adult, role=HouseholdRole.ADULT, grantor_entity_id=owner
    )
    await save_owner_pin_credential(person_entity_id=owner, credential=_credential())
    await revoke_active_role(person_entity_id=adult)
    await revoke_active_role(person_entity_id=owner)

    await _assert_instants("household_role_assignments", "granted_at", "revoked_at")
    await _assert_instants("authorization_audit_events", "evaluated_at")
    await _assert_instants("owner_pin_credentials", "created_at", "updated_at", "revoked_at")


@pytest.mark.usefixtures("store")
async def test_owner_pin_rotation_and_revocation_write_their_times() -> None:
    owner = await _person("Canary Owner")
    await bootstrap_initial_owner(person_entity_id=owner, confirmed_person_entity_id=owner)
    await save_owner_pin_credential(person_entity_id=owner, credential=_credential())
    await save_owner_pin_credential(person_entity_id=owner, credential=_credential())
    await revoke_owner_pin_credential(person_entity_id=owner)

    await _assert_instants("owner_pin_credentials", "created_at", "updated_at", "revoked_at")


@pytest.mark.usefixtures("store")
async def test_face_and_voice_consent_write_their_times() -> None:
    person = await _person("Canary Owner")
    await grant_face_consent(person)
    await revoke_face_consent(person)
    await grant_voice_consent(person)
    await revoke_voice_consent(person)

    await _assert_instants("face_consent_grants", "granted_at", "revoked_at")
    await _assert_instants("voice_consent_grants", "granted_at", "revoked_at")


@pytest.mark.usefixtures("store")
async def test_literal_facts_write_instants_and_close_on_a_day() -> None:
    owner = await _person("Canary Owner")
    await assert_literal_fact(
        subject_entity_id=owner, definition=_definition("preferred_name"), value="Canary"
    )
    second = await assert_literal_fact(
        subject_entity_id=owner, definition=_definition("preferred_name"), value="Canario"
    )
    await revoke_literal_fact(second.id, revoked_at="2026-10-29T10:00:00+00:00")

    await _assert_instants("literal_facts_v4", "asserted_at", "superseded_at")
    assert all(_DAY.fullmatch(day) for day in await _days("literal_facts_v4", "valid_to"))


async def _days(table: str, column: str) -> list[str]:
    """Every non-NULL value of one column, as text."""
    cursor = await db.get_conn().execute(
        f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL"  # noqa: S608
    )
    rows = list(await cursor.fetchall())
    await cursor.close()
    return [str(row[0]) for row in rows]


@pytest.mark.usefixtures("store")
async def test_a_temporal_relation_opens_and_closes_on_household_days() -> None:
    owner = await _person("Canary Owner")
    town = await upsert_entity(name="Canary Town", type="place")
    city = await upsert_entity(name="Canary City", type="place")
    lives_in = _definition("lives_in")

    previous = await assert_entity_relation(
        source_entity_id=owner, target_entity_id=town, definition=lives_in
    )
    current = await assert_entity_relation(
        source_entity_id=owner, target_entity_id=city, definition=lives_in
    )
    closed = await get_entity_relation(previous.id)

    assert previous.valid_from is not None
    assert _DAY.fullmatch(previous.valid_from)
    assert current.valid_from is not None
    assert _DAY.fullmatch(current.valid_from)
    assert closed is not None
    assert closed.valid_to == current.valid_from
    assert await revoke_entity_relation(current.id, revoked_at="2026-10-29T02:30:00+00:00")
    revoked = await get_entity_relation(current.id)
    assert revoked is not None
    # 02:30 UTC is still the 28th in the household's America/Santiago.
    assert revoked.valid_to == "2026-10-28"
    await _assert_instants("entity_relations_v4", "asserted_at", "superseded_at")


@pytest.mark.usefixtures("store")
async def test_a_superseded_temporal_fact_closes_on_today_not_on_the_new_assertion_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(relational_v4, "utc_now", lambda: _T0)
    # No literal predicate is temporal in the registry: borrow a single-current one.
    temporal = _definition("preferred_name").model_copy(update={"temporal": True})
    owner = await _person("Canary Owner")
    old = await assert_literal_fact(subject_entity_id=owner, definition=temporal, value="Canary")
    await assert_literal_fact(
        subject_entity_id=owner,
        definition=temporal,
        value="Canario",
        asserted_at=instant_text(_T0 - timedelta(days=5)),
    )

    closed = await get_literal_fact(old.id)

    assert closed is not None
    assert closed.valid_from == "2026-10-29"
    # Closed on the day it was superseded (today), never before its own opening day.
    assert closed.valid_to == "2026-10-29"


@pytest.mark.usefixtures("store")
@pytest.mark.parametrize(
    "given, stored",
    [
        ("2026-01-02 03:04:05", "2026-01-02T03:04:05.000000+00:00"),
        ("2026-01-02T03:04:05+03:00", "2026-01-02T00:04:05.000000+00:00"),
    ],
)
async def test_an_old_format_asserted_at_is_stored_as_the_utc_instant(
    given: str, stored: str
) -> None:
    owner = await _person("Canary Owner")
    town = await upsert_entity(name="Canary Town", type="place")
    await assert_literal_fact(
        subject_entity_id=owner,
        definition=_definition("preferred_name"),
        value="Canary",
        asserted_at=given,
    )
    await assert_entity_relation(
        source_entity_id=owner,
        target_entity_id=town,
        definition=_definition("lives_in"),
        asserted_at=given,
    )

    assert await _days("literal_facts_v4", "asserted_at") == [stored]
    assert await _days("entity_relations_v4", "asserted_at") == [stored]


@pytest.mark.usefixtures("store")
@pytest.mark.parametrize("given", ["2026-11-16", "2026-11-16T10", "junk-7Q2X", ""])
async def test_a_stored_moment_that_is_not_an_instant_is_refused_without_echoing_it(
    given: str,
) -> None:
    owner = await _person("Canary Owner")
    fact = await assert_literal_fact(
        subject_entity_id=owner, definition=_definition("preferred_name"), value="Canary"
    )

    with pytest.raises(ValueError, match="not a stored instant") as refused:
        await revoke_literal_fact(fact.id, revoked_at=given)
    with pytest.raises(ValueError, match="not a stored instant"):
        await assert_literal_fact(
            subject_entity_id=owner,
            definition=_definition("preferred_name"),
            value="Canario",
            asserted_at=given,
        )

    assert "7Q2X" not in str(refused.value)
    assert await _days("literal_facts_v4", "asserted_at") != []  # the first fact is untouched


@pytest.mark.usefixtures("store")
async def test_conversation_consent_record_and_episode_write_their_times() -> None:
    owner = await _person("Canary Owner")
    await grant_conversation_consent(owner, notice_version="v1", now=_T0)
    turn = make_turn(
        "me gusta el mate",
        "Qué rico.",
        voice=TurnVerdict.VERIFIED,
        correlation_id=UUID(int=1),
        at=_T0,
    )
    record_id = await record.append_turn(turn, owner_entity_id=owner, now=_T0)
    await record.close_idle_records(_T0 + timedelta(minutes=5))
    view = await record.read_record(record_id)
    assert view is not None
    draft = EpisodeDraft(summary="Le gusta el mate.", sensitivity="normal")
    outcome = await write_episode(
        view,
        client=httpx.AsyncClient(),
        now=_T0 + timedelta(minutes=10),
        summarize=AsyncMock(return_value=draft),
    )
    assert outcome is EpisodeOutcome.WRITTEN

    await _assert_instants(
        "conversation_records", "started_at", "last_turn_at", "closed_at", "expires_at"
    )
    await _assert_instants("conversation_episodes", "created_at", "expires_at")
    await withdraw_conversation_consent(owner, now=_T0 + timedelta(hours=1))
    await _assert_instants("conversation_consent_grants", "granted_at", "revoked_at")


@pytest.mark.usefixtures("store")
async def test_a_recall_turn_unit_writes_its_time() -> None:
    owner = await _person("Canary Owner")
    turn = make_turn(
        "fuimos al cerro",
        "Qué bien.",
        voice=TurnVerdict.VERIFIED,
        correlation_id=UUID(int=3),
        at=_T0 + timedelta(hours=3),
    )
    record_id = await record.append_turn(turn, owner_entity_id=owner, now=turn.at)
    async with db.transaction() as conn:
        await recall_store.insert_turn_unit(
            conn, record_id=record_id, owner_entity_id=owner, turn=turn
        )

    await _assert_instants("recall_units", "said_at")


@pytest.mark.usefixtures("store")
async def test_candidates_write_their_times() -> None:
    owner = await _person("Canary Owner")
    await candidates.insert_candidate(
        ProposedCandidate(predicate="likes", value_text="el mate", value_key="mate"),
        subject_person_id=owner,
        asserted_by_person_id=owner,
        channel=CandidateChannel.VOICE_CLASSIC,
        correlation_id=uuid4(),
        now=_T0,
    )

    await _assert_instants("memory_candidates", "proposed_at", "expires_at")
