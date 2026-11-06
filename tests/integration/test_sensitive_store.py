"""The owner's sensitive read against a real migrated database and the canonical writer (Plan 0079 Task 6).

Only the active rows stored with exactly the topic's visibility and sensitivity are read, in id
order; the children's birth dates come through the household tools, a child without a date as
``None``. Everything is an invented canary.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from server.cognition.authorization import ConsentStatus
from server.cognition.household_tools import HouseholdKnowledgeTools
from server.cognition.identity import (
    ActivePersonContext,
    HouseholdRole,
    IdentityEvidence,
    IdentityEvidenceSource,
    PersonRecord,
    resolve_active_person,
)
from server.cognition.identity_fusion import FusionReason
from server.cognition.models import Confidence, ConfidenceBasis, KnowledgeStatus
from server.cognition.response_plan import NO_BIRTH_DATE, SensitiveOutcome
from server.cognition.sensitive_questions import SensitiveQuery, SensitiveTopic
from server.memory.canonical_writer import WriteChannel, write_literal
from server.memory.declarative import upsert_entity
from server.memory.household_authorization import bootstrap_initial_owner
from server.memory.policy_gated_v4_reader import PolicyGatedV4Reader
from server.memory.predicate_registry import resolve_predicate
from server.memory.relational_v4 import assert_entity_relation, assert_literal_fact
from server.memory.sensitive_access import sensitive_reply
from server.memory.sensitive_store import read_own_values
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

_NOW = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
_CONFIRMED_AT = "2026-11-05T09:00:00.000000+00:00"
_CORRELATION = UUID(int=790)


class _Home:
    """The people of one invented household."""

    def __init__(self, owner: int, zeta: int, omega: int) -> None:
        self.owner = owner
        self.zeta = zeta
        self.omega = omega


@pytest.fixture
async def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Home]:
    """A migrated database with an owner and two children, Zeta (dated) and Omega (undated)."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "sensitive-store.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        owner = await upsert_entity(name="Canary Owner", type="person")
        await bootstrap_initial_owner(person_entity_id=owner, confirmed_person_entity_id=owner)
        zeta = await upsert_entity(name="Zeta", type="person")
        omega = await upsert_entity(name="Omega", type="person")
        child_of = resolve_predicate("child_of")
        assert child_of is not None
        for child in (zeta, omega):
            await assert_entity_relation(
                source_entity_id=child, target_entity_id=owner, definition=child_of
            )
        yield _Home(owner, zeta, omega)
    finally:
        await db.close_db()
        db._conn = None


async def _write(home: _Home, subject: int, predicate: str, value: str) -> int:
    fact = await write_literal(
        owner_entity_id=home.owner,
        subject_entity_id=subject,
        predicate=predicate,
        value=value,
        channel=WriteChannel.IMPORT_FILE,
        confirmed_at=_CONFIRMED_AT,
    )
    return fact.id


def _face_owner(home: _Home) -> ActivePersonContext:
    person = PersonRecord(person_id=home.owner, display_name="Canary", entity_type="person")
    evidence = IdentityEvidence(
        evidence_id=uuid4(),
        source=IdentityEvidenceSource.FACE,
        candidate_person_id=home.owner,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
        observed_at=_NOW - timedelta(seconds=1),
        reference="canary",
        expires_at=None,
        grant_scope=None,
        grant_spent=False,
    )
    return resolve_active_person(
        evidence=(evidence,),
        lookup_person=lambda pid: person if pid == home.owner else None,
        lookup_role=lambda _pid: HouseholdRole.OWNER,
        clock=lambda: _NOW,
    )


async def _audit_count() -> int:
    cursor = await db.get_conn().execute("SELECT COUNT(*) FROM authorization_audit_events")
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return int(row[0])


async def _alta_closed() -> bool:
    return True


@pytest.mark.integration
async def test_only_rows_of_the_exact_labels_are_read_in_id_order(home: _Home) -> None:
    medication = resolve_predicate("medication")
    assert medication is not None
    await _write(home, home.owner, "medication", "Remedio A 50 mg")
    await _write(home, home.owner, "medication", "Remedio B")
    # Same predicate and subject, stored with other labels: never read as the owner's medical data.
    await assert_literal_fact(
        subject_entity_id=home.owner,
        definition=medication,
        value="Remedio normal",
        visibility="personal",
        sensitivity="normal",
    )
    await assert_literal_fact(
        subject_entity_id=home.owner,
        definition=medication,
        value="Remedio del hogar",
        visibility="household",
        sensitivity="medical",
    )
    await _write(home, home.owner, "blood_type", "O+")

    values = await read_own_values(home.owner, "medication", "medical")

    assert values == ("Remedio A 50 mg", "Remedio B")


@pytest.mark.integration
async def test_revoked_rows_are_not_read(home: _Home) -> None:
    fact_id = await _write(home, home.owner, "home_address", "Calle Falsa 123 #4")
    await db.get_conn().execute(
        "UPDATE literal_facts_v4 SET lifecycle = 'revoked' WHERE id = ?", (fact_id,)
    )
    await db.get_conn().commit()

    assert await read_own_values(home.owner, "home_address", "location") == ()


@pytest.mark.integration
async def test_another_subjects_rows_are_not_read(home: _Home) -> None:
    await _write(home, home.zeta, "birth_date", "2020-07-09")

    assert await read_own_values(home.owner, "birth_date", "private") == ()


@pytest.mark.integration
async def test_the_owners_birthday_is_stored_private(home: _Home) -> None:
    await _write(home, home.owner, "birth_date", "1990-03-03")

    assert await read_own_values(home.owner, "birth_date", "private") == ("1990-03-03",)
    assert await read_own_values(home.owner, "birth_date", "child_data") == ()


@pytest.mark.integration
async def test_an_unknown_predicate_is_refused_without_the_text(home: _Home) -> None:
    with pytest.raises(ValueError, match="predicate") as raised:
        await read_own_values(home.owner, "no_such_predicate", "medical")

    assert "no_such_predicate" not in str(raised.value)


@pytest.mark.integration
async def test_get_children_birthdays_returns_a_child_without_a_date_as_none(
    home: _Home,
) -> None:
    await _write(home, home.zeta, "birth_date", "2020-07-09")
    tools = HouseholdKnowledgeTools(reader=PolicyGatedV4Reader())

    result = await tools.get_children_birthdays(
        parent_entity_id=home.owner,
        actor=_face_owner(home),
        consent=ConsentStatus.GRANTED,
        correlation_id=_CORRELATION,
        requested_at=_NOW,
    )

    assert result.status is KnowledgeStatus.KNOWN
    assert result.children == (("Omega", None), ("Zeta", "2020-07-09"))


@pytest.mark.integration
async def test_the_owner_hears_the_stored_medication_after_one_audit_row(home: _Home) -> None:
    await _write(home, home.owner, "medication", "Remedio A 50 mg")
    before = await _audit_count()

    reply = await sensitive_reply(
        _face_owner(home),
        SensitiveQuery(SensitiveTopic.MEDICATION, ()),
        faces=FusionReason.FACE_ONLY,
        face_consent=ConsentStatus.GRANTED,
        voice_check=False,
        correlation_id=_CORRELATION,
        now=_NOW,
        household_tools=HouseholdKnowledgeTools(reader=PolicyGatedV4Reader()),
        alta_closed=_alta_closed,
    )

    assert reply.outcome is SensitiveOutcome.ANSWERED
    assert reply.text == "Tu medicamento es Remedio A 50 mg."
    assert await _audit_count() == before + 1


@pytest.mark.integration
async def test_a_named_child_and_an_unnamed_one_are_worded_from_the_real_store(
    home: _Home,
) -> None:
    await _write(home, home.zeta, "birth_date", "2020-07-09")
    tools = HouseholdKnowledgeTools(reader=PolicyGatedV4Reader())

    async def ask(*keywords: str) -> tuple[SensitiveOutcome, str | None]:
        reply = await sensitive_reply(
            _face_owner(home),
            SensitiveQuery(SensitiveTopic.CHILD_BIRTHDAY, keywords),
            faces=FusionReason.FACE_ONLY,
            face_consent=ConsentStatus.GRANTED,
            voice_check=False,
            correlation_id=_CORRELATION,
            now=_NOW,
            household_tools=tools,
            alta_closed=_alta_closed,
        )
        return reply.outcome, reply.text

    assert await ask("zeta") == (
        SensitiveOutcome.ANSWERED,
        "El cumpleaños de Zeta es el 9 de julio.",
    )
    assert await ask("omega") == (SensitiveOutcome.NOT_REGISTERED, NO_BIRTH_DATE)
    assert await ask("mozart") == (SensitiveOutcome.NOT_HOUSEHOLD, None)
