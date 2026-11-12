"""The owner's contacts and the rest of the profile read after the checks (Plan 0082 Task 5).

Order under test: a contact question that names no own contact is ordinary conversation first;
then two faces, the owner pre-check, the level, the consent, the policy and its audit row, and only
then the read. Canaries only: no stored value, name or phone may reach a log line.
"""

from datetime import UTC, datetime, timedelta
import logging
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from server.cognition.authorization import ConsentStatus, evaluate_authorization
from server.cognition.contact_answers import CANNOT_CALL, NO_KEY_HOLDER, NO_PHONE
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
from server.cognition.response_plan import SensitiveOutcome, SensitiveReply
from server.cognition.sensitive_questions import SensitiveQuery, SensitiveTopic
from server.memory.care_contacts import CareContact, ContactRole
from server.memory.contact_access import is_own_contact_question
from server.memory.sensitive_access import sensitive_reply

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)
_OWNER = 7
_CORRELATION = UUID(int=82)
_DAUGHTER, _DOCTOR, _NEIGHBOR, _FRIEND = 11, 12, 13, 14
_NAMES = {
    _DAUGHTER: "Canary Daughter",
    _DOCTOR: "Canary Doctor",
    _NEIGHBOR: "Canary Neighbor",
    _FRIEND: "Canary Friend",
}
_DAUGHTER_PHONE = "+56900000001"
_SPOKEN_DAUGHTER = "más cinco seis nueve, cero cero cero cero, cero cero cero uno"


def _row(
    row_id: int,
    contact: int,
    role: ContactRole,
    phone: str,
    *,
    relationship: str | None = None,
    call_order: int | None = None,
    has_key: bool = False,
) -> CareContact:
    return CareContact(
        id=row_id,
        owner_entity_id=_OWNER,
        contact_entity_id=contact,
        role=role,
        relationship=relationship,
        phone=phone,
        phone_alt=None,
        call_order=call_order,
        has_key=has_key,
        may_receive_health_info=False,
        may_view_activity=False,
        visibility="personal",
        sensitivity="location" if has_key else "private",
        asserted_by_entity_id=_OWNER,
        channel="import_file",
        confirmed_by_entity_id=_OWNER,
        confirmed_at="2026-11-11T09:00:00+00:00",
        created_at="2026-11-11T09:00:00",
        revoked_at=None,
    )


_ROWS = (
    _row(
        1,
        _DAUGHTER,
        ContactRole.CAREGIVER,
        _DAUGHTER_PHONE,
        relationship="hija",
        call_order=1,
        has_key=True,
    ),
    _row(2, _DOCTOR, ContactRole.DOCTOR, "+56900000003", call_order=2),
    _row(3, _NEIGHBOR, ContactRole.NEIGHBOR, "+56900000004", relationship="vecina", has_key=True),
    _row(4, _FRIEND, ContactRole.TRUSTED, "+56900000005", relationship="amiga"),
)


def _evidence(source: IdentityEvidenceSource) -> IdentityEvidence:
    return IdentityEvidence(
        evidence_id=uuid4(),
        source=source,
        candidate_person_id=_OWNER,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
        observed_at=_NOW - timedelta(seconds=1),
        reference="canary",
        expires_at=None,
        grant_scope=None,
        grant_spent=False,
    )


def _actor(*sources: IdentityEvidenceSource) -> ActivePersonContext:
    person = PersonRecord(person_id=_OWNER, display_name="Canary", entity_type="person")
    return resolve_active_person(
        evidence=tuple(_evidence(source) for source in sources),
        lookup_person=lambda pid: person if pid == _OWNER else None,
        lookup_role=lambda _: HouseholdRole.OWNER,
        clock=lambda: _NOW,
    )


class _Seams:
    """The doubles of one call, so a test can assert what each one saw."""

    def __init__(self, rows: tuple[CareContact, ...] = _ROWS, *, alta: bool = True) -> None:
        self.calls: list[str] = []
        self.audit = AsyncMock(side_effect=lambda *_: self.calls.append("audit"))
        self.alta_closed = AsyncMock(return_value=alta)
        self.reader = AsyncMock(return_value=("si",))
        self.contacts = AsyncMock(side_effect=lambda _owner: self._read(rows))
        self.contact_names = AsyncMock(side_effect=_NAMES.get)

    def _read(self, rows: tuple[CareContact, ...]) -> tuple[CareContact, ...]:
        self.calls.append("read")
        return rows


async def _reply(
    query: SensitiveQuery,
    seams: _Seams,
    *,
    actor: ActivePersonContext | None = None,
    faces: FusionReason | None = FusionReason.FACE_ONLY,
    voice_check: bool = False,
) -> SensitiveReply:
    return await sensitive_reply(
        actor or _actor(IdentityEvidenceSource.FACE),
        query,
        faces=faces,
        face_consent=ConsentStatus.GRANTED,
        voice_check=voice_check,
        correlation_id=_CORRELATION,
        now=_NOW,
        household_tools=Mock(spec=HouseholdKnowledgeTools),
        policy=evaluate_authorization,
        audit=seams.audit,
        alta_closed=seams.alta_closed,
        names=AsyncMock(return_value=frozenset()),
        reader=seams.reader,
        contacts=seams.contacts,
        contact_names=seams.contact_names,
    )


def _phone(*words: str) -> SensitiveQuery:
    return SensitiveQuery(topic=SensitiveTopic.CONTACT_PHONE, keywords=words)


def _nothing_touched(seams: _Seams) -> None:
    seams.audit.assert_not_awaited()
    seams.contacts.assert_not_awaited()
    seams.contact_names.assert_not_awaited()


async def test_two_faces_hear_not_alone_and_nothing_is_read() -> None:
    seams = _Seams()
    reply = await _reply(_phone("mi", "hija"), seams, faces=FusionReason.VETO_MULTIPLE_FACES)
    assert reply == SensitiveReply(SensitiveOutcome.NOT_ALONE)
    _nothing_touched(seams)


async def test_a_stranger_is_denied() -> None:
    seams = _Seams()
    reply = await _reply(_phone("mi", "hija"), seams, actor=_actor(), faces=None)
    assert reply == SensitiveReply(SensitiveOutcome.DENIED)
    _nothing_touched(seams)


@pytest.mark.parametrize("faces", [FusionReason.FACE_ONLY, FusionReason.VETO_MULTIPLE_FACES, None])
@pytest.mark.parametrize(
    "query",
    [
        _phone("los", "bomberos"),
        SensitiveQuery(topic=SensitiveTopic.CONTACT_CALL, keywords=("canary",)),
    ],
)
async def test_a_question_with_no_own_contact_is_ordinary(
    query: SensitiveQuery, faces: FusionReason | None
) -> None:
    seams = _Seams()
    reply = await _reply(query, seams, faces=faces)
    assert reply == SensitiveReply(SensitiveOutcome.NOT_HOUSEHOLD)
    _nothing_touched(seams)


def test_is_own_contact_question() -> None:
    assert is_own_contact_question(_phone("mi", "hija"))
    assert is_own_contact_question(_phone("contacto", "1"))
    assert is_own_contact_question(SensitiveQuery(topic=SensitiveTopic.KEY_HOLDERS, keywords=()))
    assert not is_own_contact_question(_phone("los", "bomberos"))


async def test_the_audit_row_precedes_the_read() -> None:
    seams = _Seams()
    await _reply(_phone("mi", "hija"), seams)
    assert seams.calls == ["audit", "read"]
    awaited = seams.audit.await_args
    assert awaited is not None
    request, decision = awaited.args
    assert {item.value for item in request.sensitivity} == {"private", "location"}
    assert {item.value for item in request.visibility} == {"personal"}
    assert request.target_person_id == _OWNER
    assert decision.decision.value == "allowed"


async def test_a_failing_audit_reads_nothing() -> None:
    seams = _Seams()
    seams.audit.side_effect = RuntimeError("audit down")
    reply = await _reply(_phone("mi", "hija"), seams)
    assert reply == SensitiveReply(SensitiveOutcome.UNAVAILABLE)
    seams.contacts.assert_not_awaited()


async def test_no_closed_alta_is_denied() -> None:
    seams = _Seams(alta=False)
    reply = await _reply(_phone("mi", "hija"), seams)
    assert reply == SensitiveReply(SensitiveOutcome.DENIED)
    seams.contacts.assert_not_awaited()


@pytest.mark.parametrize(
    "words, name",
    [
        (("mi", "hija"), "Canary Daughter"),
        (("mis", "hijas"), "Canary Daughter"),
        (("mi", "contacto", "1"), "Canary Daughter"),
        (("mi", "primer", "contacto"), "Canary Daughter"),
        (("mi", "doctor"), "Canary Doctor"),
        (("mi", "contacto", "numero", "dos"), "Canary Doctor"),
        (("mi", "vecina"), "Canary Neighbor"),
        (("mi", "amiga", "canary"), "Canary Friend"),
    ],
)
async def test_by_relationship_role_order_and_name(words: tuple[str, ...], name: str) -> None:
    reply = await _reply(_phone(*words), _Seams())
    assert reply.outcome is SensitiveOutcome.ANSWERED
    assert reply.text is not None
    assert reply.text.startswith(f"El teléfono de {name}, tu ")


async def test_the_daughter_is_said_with_her_label_and_phone() -> None:
    reply = await _reply(_phone("mi", "hija"), _Seams())
    assert reply.text == f"El teléfono de Canary Daughter, tu hija, es {_SPOKEN_DAUGHTER}."


async def test_none_selected_says_no_phone() -> None:
    reply = await _reply(_phone("mi", "tio"), _Seams())
    assert reply == SensitiveReply(SensitiveOutcome.NOT_REGISTERED, NO_PHONE)


async def test_call_opens_with_cannot_call() -> None:
    call = SensitiveQuery(topic=SensitiveTopic.CONTACT_CALL, keywords=("mi", "contacto", "1"))
    answered = await _reply(call, _Seams())
    assert answered == SensitiveReply(
        SensitiveOutcome.ANSWERED,
        f"{CANNOT_CALL} El teléfono de Canary Daughter, tu hija, es {_SPOKEN_DAUGHTER}.",
    )
    nobody = SensitiveQuery(topic=SensitiveTopic.CONTACT_CALL, keywords=("mi", "tio"))
    assert await _reply(nobody, _Seams()) == SensitiveReply(
        SensitiveOutcome.NOT_REGISTERED, f"{CANNOT_CALL} {NO_PHONE}"
    )


async def test_a_refused_call_hears_the_refusal_not_cannot_call() -> None:
    call = SensitiveQuery(topic=SensitiveTopic.CONTACT_CALL, keywords=("mi", "hija"))
    assert await _reply(call, _Seams(), actor=_actor(), faces=None) == SensitiveReply(
        SensitiveOutcome.DENIED
    )
    assert await _reply(call, _Seams(), faces=FusionReason.VETO_MULTIPLE_FACES) == (
        SensitiveReply(SensitiveOutcome.NOT_ALONE)
    )


async def test_one_person_with_two_roles_is_said_once() -> None:
    rows = (
        _row(
            1,
            _DAUGHTER,
            ContactRole.CAREGIVER,
            _DAUGHTER_PHONE,
            relationship="hija",
            call_order=1,
            has_key=True,
        ),
        _row(
            5, _DAUGHTER, ContactRole.KEY_HOLDER, _DAUGHTER_PHONE, relationship="hija", has_key=True
        ),
    )
    phone = await _reply(_phone("mis", "contactos"), _Seams(rows))
    assert phone.text == f"El teléfono de Canary Daughter, tu hija, es {_SPOKEN_DAUGHTER}."
    keys = await _reply(SensitiveQuery(topic=SensitiveTopic.KEY_HOLDERS, keywords=()), _Seams(rows))
    assert keys.text == "Canary Daughter tiene llave de tu casa."


async def test_at_most_three_people() -> None:
    reply = await _reply(_phone("mis", "contactos"), _Seams())
    assert reply.text is not None
    assert reply.text.count("El teléfono de") == 3
    assert "Canary Friend" not in reply.text


async def test_key_holders() -> None:
    keys = SensitiveQuery(topic=SensitiveTopic.KEY_HOLDERS, keywords=())
    assert await _reply(keys, _Seams()) == SensitiveReply(
        SensitiveOutcome.ANSWERED,
        "Tienen llave de tu casa: Canary Daughter y Canary Neighbor.",
    )
    assert await _reply(keys, _Seams(_ROWS[1:2])) == SensitiveReply(
        SensitiveOutcome.NOT_REGISTERED, NO_KEY_HOLDER
    )


async def test_lives_alone_needs_strong() -> None:
    alone = SensitiveQuery(topic=SensitiveTopic.LIVES_ALONE, keywords=())
    retry = await _reply(alone, _Seams(), voice_check=True)
    assert retry == SensitiveReply(SensitiveOutcome.RETRY_VOICE)
    denied = await _reply(alone, _Seams(), voice_check=False)
    assert denied == SensitiveReply(SensitiveOutcome.DENIED)
    strong = _actor(IdentityEvidenceSource.FACE, IdentityEvidenceSource.VOICE)
    answered = await _reply(alone, _Seams(), actor=strong, faces=FusionReason.FACE_AND_VOICE)
    assert answered == SensitiveReply(
        SensitiveOutcome.ANSWERED, "Tengo registrado que vives sin nadie más en casa."
    )


@pytest.mark.parametrize(
    "topic, value, predicate, sensitivity",
    [
        (SensitiveTopic.MOBILITY, "baston", "mobility", "medical"),
        (SensitiveTopic.HEALTH_COVERAGE, "Previsión Canary", "health_coverage", "private"),
        (SensitiveTopic.FLOOR, "4", "floor", "location"),
        (SensitiveTopic.HOME_ACCESS, "Portón azul", "home_access_note", "location"),
    ],
)
async def test_the_new_profile_topics_read_their_predicate(
    topic: SensitiveTopic, value: str, predicate: str, sensitivity: str
) -> None:
    seams = _Seams()
    seams.reader.return_value = (value,)
    reply = await _reply(SensitiveQuery(topic=topic, keywords=()), seams)
    assert reply.outcome is SensitiveOutcome.ANSWERED
    seams.reader.assert_awaited_once_with(_OWNER, predicate, sensitivity)
    seams.contacts.assert_not_awaited()


async def test_no_value_reaches_a_log_line(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    for words in (("mi", "hija"), ("mi", "tio"), ("los", "bomberos"), ("mis", "contactos")):
        await _reply(_phone(*words), _Seams())
    await _reply(SensitiveQuery(topic=SensitiveTopic.KEY_HOLDERS, keywords=()), _Seams())
    logged = " ".join(record.getMessage() + str(record.__dict__) for record in caplog.records)
    assert "Canary" not in logged
    assert "569" not in logged
    assert "hija" not in logged
    assert "cero" not in logged
