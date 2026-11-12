"""The owner's contacts read through the real table and writer (Plan 0082 Task 5).

A migrated database, the contacts writer and the canonical entities; only the alta check and the
audit are doubles. Canaries only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from server.cognition.authorization import ConsentStatus, evaluate_authorization
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
from server.cognition.models import Confidence, ConfidenceBasis
from server.cognition.response_plan import SensitiveOutcome
from server.cognition.sensitive_questions import SensitiveQuery, SensitiveTopic
from server.memory.care_contacts import ContactRole, revoke_contact, write_contact
from server.memory.declarative import create_third_party, upsert_entity
from server.memory.household_authorization import bootstrap_initial_owner
from server.memory.sensitive_access import sensitive_reply
from server.memory.write_types import WriteChannel
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)
_CONFIRMED_AT = "2026-11-11T09:00:00.000000+00:00"
_CORRELATION = UUID(int=820)


class _Home:
    """The people of one invented household and a second, unrelated owner."""

    def __init__(self, owner: int, other_owner: int, daughter: int, doctor: int) -> None:
        self.owner = owner
        self.other_owner = other_owner
        self.daughter = daughter
        self.doctor = doctor


@pytest.fixture
async def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Home]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "contact-access.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        owner = await upsert_entity(name="Canary Owner", type="person")
        await bootstrap_initial_owner(person_entity_id=owner, confirmed_person_entity_id=owner)
        other_owner = await upsert_entity(name="Canary Other Owner", type="person")
        daughter = await create_third_party(name="Canary Daughter", type="person")
        doctor = await create_third_party(name="Canary Doctor", type="person")
        yield _Home(owner, other_owner, daughter, doctor)
    finally:
        await db.close_db()
        db._conn = None


async def _contact(owner: int, contact: int, role: ContactRole, phone: str, **extra: object) -> int:
    row = await write_contact(
        owner_entity_id=owner,
        contact_entity_id=contact,
        role=role,
        phone=phone,
        channel=WriteChannel.IMPORT_FILE,
        confirmed_at=_CONFIRMED_AT,
        **extra,  # type: ignore[arg-type]  # a test helper passing optional keywords through
    )
    return row.id


def _face_owner(owner: int) -> ActivePersonContext:
    person = PersonRecord(person_id=owner, display_name="Canary", entity_type="person")
    evidence = IdentityEvidence(
        evidence_id=uuid4(),
        source=IdentityEvidenceSource.FACE,
        candidate_person_id=owner,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
        observed_at=_NOW - timedelta(seconds=1),
        reference="canary",
        expires_at=None,
        grant_scope=None,
        grant_spent=False,
    )
    return resolve_active_person(
        evidence=(evidence,),
        lookup_person=lambda pid: person if pid == owner else None,
        lookup_role=lambda _: HouseholdRole.OWNER,
        clock=lambda: _NOW,
    )


async def _ask(
    owner: int, *words: str, topic: SensitiveTopic = SensitiveTopic.CONTACT_PHONE
) -> str | None:
    reply = await sensitive_reply(
        _face_owner(owner),
        SensitiveQuery(topic=topic, keywords=words),
        faces=FusionReason.FACE_ONLY,
        face_consent=ConsentStatus.GRANTED,
        voice_check=False,
        correlation_id=_CORRELATION,
        now=_NOW,
        household_tools=Mock(spec=HouseholdKnowledgeTools),
        policy=evaluate_authorization,
        audit=AsyncMock(),
        alta_closed=AsyncMock(return_value=True),
        names=AsyncMock(return_value=frozenset()),
    )
    assert reply.outcome in {SensitiveOutcome.ANSWERED, SensitiveOutcome.NOT_REGISTERED}
    return reply.text


async def test_the_order_and_the_names_come_from_the_table(home: _Home) -> None:
    await _contact(home.owner, home.doctor, ContactRole.DOCTOR, "+56900000003", call_order=2)
    await _contact(
        home.owner,
        home.daughter,
        ContactRole.CAREGIVER,
        "+56900000001",
        call_order=1,
        relationship="hija",
        has_key=True,
    )
    first = await _ask(home.owner, "mi", "contacto", "1")
    assert first is not None
    assert first.startswith("El teléfono de Canary Daughter, tu hija, es ")
    everyone = await _ask(home.owner, "mis", "contactos")
    assert everyone is not None
    assert everyone.index("Canary Daughter") < everyone.index("Canary Doctor")
    keys = await _ask(home.owner, topic=SensitiveTopic.KEY_HOLDERS)
    assert keys == "Canary Daughter tiene llave de tu casa."


async def test_a_revoked_contact_is_not_read(home: _Home) -> None:
    row = await _contact(
        home.owner, home.daughter, ContactRole.CAREGIVER, "+56900000001", relationship="hija"
    )
    assert await revoke_contact(row, revoked_at=_CONFIRMED_AT)
    assert await _ask(home.owner, "mi", "hija") == "No tengo ese teléfono guardado."


async def test_another_owners_contact_is_not_read(home: _Home) -> None:
    await _contact(
        home.other_owner, home.daughter, ContactRole.CAREGIVER, "+56900000001", relationship="hija"
    )
    assert await _ask(home.owner, "mi", "hija") == "No tengo ese teléfono guardado."
