"""Unit tests for the owner's sensitive read: audience, level, consent, policy, audit, answer (Plan 0079 Task 6).

Order under test: the household decision of a child's birthday, two faces, the owner pre-check, the
security level, the consent, the policy and its audit row, and only then the read. Everything is an
invented canary; no stored value may reach a log line.
"""

from datetime import UTC, datetime, timedelta
import logging
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from server.cognition.authorization import (
    AuthorizationRequest,
    ConsentStatus,
    evaluate_authorization,
)
from server.cognition.household_tools import ChildBirthdays, HouseholdKnowledgeTools
from server.cognition.identity import (
    ActivePersonContext,
    HouseholdRole,
    IdentityEvidence,
    IdentityEvidenceSource,
    PersonRecord,
    resolve_active_person,
)
from server.cognition.identity_fusion import FusionReason
from server.cognition.models import (
    AuthorizationAction,
    AuthorizationDecision,
    AuthorizationStatus,
    Confidence,
    ConfidenceBasis,
    KnowledgeStatus,
)
from server.cognition.response_plan import NO_BIRTH_DATE, SensitiveOutcome, SensitiveReply
from server.cognition.sensitive_questions import SensitiveQuery, SensitiveTopic
from server.memory.candidate_policy import PolicyEvaluator
from server.memory.sensitive_access import sensitive_reply

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
_OWNER = 7
_CORRELATION = UUID(int=79)
_DOSE_CANARY = "Remedio A 50 mg"
_ADDRESS_CANARY = "Calle Falsa 123 #4"
_NAMES = frozenset({"Zeta", "Omega", "Canary Visitor"})
_CHILDREN = (("Omega", "2018-03-03"), ("Zeta", "2020-07-09"))


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
        lookup_role=lambda _pid: HouseholdRole.OWNER,
        clock=lambda: _NOW,
    )


def _face() -> ActivePersonContext:
    return _actor(IdentityEvidenceSource.FACE)


def _strong() -> ActivePersonContext:
    return _actor(IdentityEvidenceSource.FACE, IdentityEvidenceSource.VOICE)


def _stranger() -> ActivePersonContext:
    return _actor()


def _tools(
    result: ChildBirthdays | None = None,
) -> Mock:
    tools = Mock(spec=HouseholdKnowledgeTools)
    tools.get_children_birthdays = AsyncMock(
        return_value=result or ChildBirthdays(KnowledgeStatus.KNOWN, _CHILDREN)
    )
    return tools


def _query(topic: SensitiveTopic, *keywords: str) -> SensitiveQuery:
    return SensitiveQuery(topic=topic, keywords=keywords)


class _Seams:
    """The doubles of one call, so a test can assert what each one saw."""

    def __init__(self, *, values: tuple[str, ...] = (_DOSE_CANARY,), alta: bool = True) -> None:
        self.audit = AsyncMock()
        self.alta_closed = AsyncMock(return_value=alta)
        self.names = AsyncMock(return_value=_NAMES)
        self.reader = AsyncMock(return_value=values)
        self.tools = _tools()


async def _reply(
    query: SensitiveQuery,
    seams: _Seams,
    *,
    actor: ActivePersonContext | None = None,
    faces: FusionReason | None = FusionReason.FACE_ONLY,
    face_consent: ConsentStatus = ConsentStatus.GRANTED,
    voice_check: bool = False,
    policy: PolicyEvaluator = evaluate_authorization,
) -> SensitiveReply:
    return await sensitive_reply(
        actor or _face(),
        query,
        faces=faces,
        face_consent=face_consent,
        voice_check=voice_check,
        correlation_id=_CORRELATION,
        now=_NOW,
        household_tools=seams.tools,
        policy=policy,
        audit=seams.audit,
        alta_closed=seams.alta_closed,
        names=seams.names,
        reader=seams.reader,
    )


def _nothing_touched(seams: _Seams) -> None:
    seams.audit.assert_not_awaited()
    seams.reader.assert_not_awaited()
    seams.alta_closed.assert_not_awaited()
    seams.tools.get_children_birthdays.assert_not_awaited()


async def test_two_faces_hear_not_alone_and_nothing_is_read_or_audited() -> None:
    seams = _Seams()

    reply = await _reply(
        _query(SensitiveTopic.MEDICATION), seams, faces=FusionReason.VETO_MULTIPLE_FACES
    )

    assert reply.outcome is SensitiveOutcome.NOT_ALONE
    assert reply.text is None
    _nothing_touched(seams)


async def test_two_faces_hear_not_alone_for_a_family_word_too() -> None:
    seams = _Seams()

    reply = await _reply(
        _query(SensitiveTopic.CHILD_BIRTHDAY, "hijos"),
        seams,
        faces=FusionReason.VETO_MULTIPLE_FACES,
    )

    assert reply.outcome is SensitiveOutcome.NOT_ALONE
    _nothing_touched(seams)


async def test_a_stranger_is_denied() -> None:
    seams = _Seams()

    reply = await _reply(
        _query(SensitiveTopic.MEDICATION), seams, actor=_stranger(), faces=FusionReason.NO_EVIDENCE
    )

    assert reply.outcome is SensitiveOutcome.DENIED
    assert reply.text is None
    _nothing_touched(seams)


@pytest.mark.parametrize("faces", [None, FusionReason.NO_EVIDENCE, FusionReason.ERROR])
async def test_no_frame_is_denied_never_not_alone(faces: FusionReason | None) -> None:
    """Review focus 3: a voice turn with no frame has no face evidence; it hears the denial."""
    seams = _Seams()

    reply = await _reply(_query(SensitiveTopic.ADDRESS), seams, actor=_stranger(), faces=faces)

    assert reply.outcome is SensitiveOutcome.DENIED
    _nothing_touched(seams)


async def test_security_with_the_face_alone_asks_to_retry() -> None:
    seams = _Seams()

    reply = await _reply(
        _query(SensitiveTopic.SECRET_HOLDER),
        seams,
        faces=FusionReason.FACE_ONLY,
        voice_check=True,
    )

    assert reply.outcome is SensitiveOutcome.RETRY_VOICE
    assert reply.text is None
    _nothing_touched(seams)


@pytest.mark.parametrize(
    "faces, voice_check",
    [
        (FusionReason.FACE_ONLY, False),
        (FusionReason.BACKEND_UNAVAILABLE, True),
        (FusionReason.ERROR, True),
        (None, True),
    ],
)
async def test_security_without_a_voice_backend_is_denied(
    faces: FusionReason | None, voice_check: bool
) -> None:
    """Review focus 4 (D-11): no voice to retry with means the denial, never an endless retry."""
    seams = _Seams()

    reply = await _reply(
        _query(SensitiveTopic.DOCUMENT_LOCATION),
        seams,
        faces=faces,
        voice_check=voice_check,
    )

    assert reply.outcome is SensitiveOutcome.DENIED
    _nothing_touched(seams)


async def test_security_with_face_and_voice_answers() -> None:
    seams = _Seams(values=("La clave del banco la sabe Omega",))

    reply = await _reply(
        _query(SensitiveTopic.SECRET_HOLDER),
        seams,
        actor=_strong(),
        faces=FusionReason.FACE_AND_VOICE,
        voice_check=True,
    )

    assert reply.outcome is SensitiveOutcome.ANSWERED
    assert reply.text == "Sobre las claves tengo anotado: La clave del banco la sabe Omega."
    seams.reader.assert_awaited_once_with(_OWNER, "secret_holder", "security")


async def test_no_closed_alta_is_denied_and_the_denial_is_audited() -> None:
    seams = _Seams(alta=False)

    reply = await _reply(_query(SensitiveTopic.MEDICATION), seams)

    assert reply.outcome is SensitiveOutcome.DENIED
    seams.alta_closed.assert_awaited_once()
    seams.audit.assert_awaited_once()
    seams.reader.assert_not_awaited()


async def test_a_face_that_gave_no_consent_is_denied_without_asking_the_alta() -> None:
    seams = _Seams()

    reply = await _reply(
        _query(SensitiveTopic.BLOOD_TYPE), seams, face_consent=ConsentStatus.MISSING
    )

    assert reply.outcome is SensitiveOutcome.DENIED
    seams.alta_closed.assert_not_awaited()
    seams.reader.assert_not_awaited()


async def test_the_request_carries_the_stored_labels_and_the_granted_consent() -> None:
    seams = _Seams()

    await _reply(_query(SensitiveTopic.ADDRESS), seams)

    request = seams.audit.await_args_list[0].args[0]
    assert request.action is AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY
    assert request.target_person_id == _OWNER
    assert {item.value for item in request.visibility} == {"personal"}
    assert {item.value for item in request.sensitivity} == {"location"}
    assert request.consent is ConsentStatus.GRANTED
    assert request.correlation_id == _CORRELATION
    seams.reader.assert_awaited_once_with(_OWNER, "home_address", "location")


async def test_the_audit_row_precedes_the_read() -> None:
    order: list[str] = []
    seams = _Seams()

    def policy(request: AuthorizationRequest) -> AuthorizationDecision:
        order.append("policy")
        return evaluate_authorization(request)

    seams.audit.side_effect = lambda *_: order.append("audit")
    seams.reader.side_effect = lambda *_: order.append("reader") or (_DOSE_CANARY,)

    reply = await _reply(_query(SensitiveTopic.MEDICATION), seams, policy=policy)

    assert reply.outcome is SensitiveOutcome.ANSWERED
    assert order == ["policy", "audit", "reader"]


async def test_a_refusing_policy_is_audited_and_denied() -> None:
    seams = _Seams()

    def refuse(request: AuthorizationRequest) -> AuthorizationDecision:
        return evaluate_authorization(request).model_copy(
            update={"decision": AuthorizationStatus.DENIED}
        )

    reply = await _reply(_query(SensitiveTopic.MEDICATION), seams, policy=refuse)

    assert reply.outcome is SensitiveOutcome.DENIED
    seams.audit.assert_awaited_once()
    seams.reader.assert_not_awaited()


async def test_a_failing_audit_reads_nothing(caplog: pytest.LogCaptureFixture) -> None:
    seams = _Seams()
    seams.audit.side_effect = RuntimeError(_DOSE_CANARY)

    with caplog.at_level(logging.DEBUG):
        reply = await _reply(_query(SensitiveTopic.MEDICATION), seams)

    assert reply.outcome is SensitiveOutcome.UNAVAILABLE
    seams.reader.assert_not_awaited()
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "RuntimeError" in warnings[0].getMessage()
    assert _DOSE_CANARY not in caplog.text


async def test_a_failing_read_is_unavailable_and_class_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    seams = _Seams()
    seams.reader.side_effect = ValueError(_ADDRESS_CANARY)

    with caplog.at_level(logging.DEBUG):
        reply = await _reply(_query(SensitiveTopic.ADDRESS), seams)

    assert reply.outcome is SensitiveOutcome.UNAVAILABLE
    assert "ValueError" in caplog.text
    assert _ADDRESS_CANARY not in caplog.text


async def test_a_value_that_cannot_be_worded_is_unavailable() -> None:
    seams = _Seams(values=("tal vez",))

    reply = await _reply(_query(SensitiveTopic.ANTICOAGULANT), seams)

    assert reply.outcome is SensitiveOutcome.UNAVAILABLE
    assert reply.text is None


async def test_nothing_stored_is_not_registered() -> None:
    seams = _Seams(values=())

    reply = await _reply(_query(SensitiveTopic.ALLERGY), seams)

    assert reply.outcome is SensitiveOutcome.NOT_REGISTERED
    assert reply.text is None


async def test_a_stored_value_is_read_as_written() -> None:
    seams = _Seams(values=(_DOSE_CANARY,))

    reply = await _reply(_query(SensitiveTopic.MEDICATION), seams)

    assert reply.outcome is SensitiveOutcome.ANSWERED
    assert reply.text == f"Tu medicamento es {_DOSE_CANARY}."


async def test_the_matching_reference_entries_are_read() -> None:
    seams = _Seams(values=("Banco: la sabe Omega", "Alarma: la sabe Zeta", "Portón: nadie"))

    reply = await _reply(
        _query(SensitiveTopic.SECRET_HOLDER, "banco"),
        seams,
        actor=_strong(),
        faces=FusionReason.FACE_AND_VOICE,
    )

    assert reply.text == "Sobre las claves tengo anotado: Banco: la sabe Omega."


async def test_no_matching_entry_reads_them_all() -> None:
    seams = _Seams(values=("Banco: la sabe Omega", "Alarma: la sabe Zeta"))

    reply = await _reply(
        _query(SensitiveTopic.SECRET_HOLDER, "cajero"),
        seams,
        actor=_strong(),
        faces=FusionReason.FACE_AND_VOICE,
    )

    assert (
        reply.text == "Sobre las claves tengo anotado: Banco: la sabe Omega; Alarma: la sabe Zeta."
    )


async def test_a_named_child_is_read() -> None:
    seams = _Seams()

    reply = await _reply(_query(SensitiveTopic.CHILD_BIRTHDAY, "zeta"), seams)

    assert reply.outcome is SensitiveOutcome.ANSWERED
    assert reply.text == "El cumpleaños de Zeta es el 9 de julio."
    seams.tools.get_children_birthdays.assert_awaited_once()
    call = seams.tools.get_children_birthdays.await_args.kwargs
    assert call["parent_entity_id"] == _OWNER
    assert call["consent"] is ConsentStatus.GRANTED
    seams.audit.assert_not_awaited()  # the household tools own their audit rows


async def test_all_children_are_read() -> None:
    seams = _Seams()

    reply = await _reply(_query(SensitiveTopic.CHILD_BIRTHDAY, "hijos"), seams)

    assert reply.outcome is SensitiveOutcome.ANSWERED
    assert reply.text == "Omega cumple el 3 de marzo y Zeta cumple el 9 de julio."


async def test_a_child_without_a_date_is_said_in_a_list() -> None:
    seams = _Seams()
    seams.tools = _tools(
        ChildBirthdays(KnowledgeStatus.KNOWN, (("Omega", None), ("Zeta", "2020-07-09")))
    )

    reply = await _reply(_query(SensitiveTopic.CHILD_BIRTHDAY, "hijos"), seams)

    assert reply.text == "De Omega no tengo la fecha y Zeta cumple el 9 de julio."


async def test_selected_children_without_a_date_have_no_birth_date() -> None:
    seams = _Seams()
    seams.tools = _tools(ChildBirthdays(KnowledgeStatus.KNOWN, (("Omega", None), ("Zeta", None))))

    reply = await _reply(_query(SensitiveTopic.CHILD_BIRTHDAY, "hija"), seams)

    assert reply.outcome is SensitiveOutcome.NOT_REGISTERED
    assert reply.text == NO_BIRTH_DATE


async def test_a_name_that_is_no_child_has_no_birth_date() -> None:
    seams = _Seams()
    seams.names.return_value = frozenset({"Zeta", "Omega", "Canary Visitor"})

    reply = await _reply(_query(SensitiveTopic.CHILD_BIRTHDAY, "visitor"), seams)

    assert reply.outcome is SensitiveOutcome.NOT_REGISTERED
    assert reply.text == NO_BIRTH_DATE


async def test_a_relative_word_has_no_birth_date_and_reads_nothing() -> None:
    seams = _Seams()

    reply = await _reply(_query(SensitiveTopic.CHILD_BIRTHDAY, "mama"), seams)

    assert reply.outcome is SensitiveOutcome.NOT_REGISTERED
    assert reply.text == NO_BIRTH_DATE
    _nothing_touched(seams)


@pytest.mark.parametrize("faces", [FusionReason.FACE_ONLY, FusionReason.VETO_MULTIPLE_FACES])
async def test_a_stranger_name_is_not_a_household_question(faces: FusionReason) -> None:
    seams = _Seams()

    reply = await _reply(_query(SensitiveTopic.CHILD_BIRTHDAY, "mozart"), seams, faces=faces)

    assert reply.outcome is SensitiveOutcome.NOT_HOUSEHOLD
    assert reply.text is None
    _nothing_touched(seams)


async def test_a_bare_birthday_question_is_not_a_household_question() -> None:
    seams = _Seams()

    reply = await _reply(_query(SensitiveTopic.CHILD_BIRTHDAY), seams)

    assert reply.outcome is SensitiveOutcome.NOT_HOUSEHOLD
    _nothing_touched(seams)


@pytest.mark.parametrize("faces", [FusionReason.NO_EVIDENCE, FusionReason.VETO_MULTIPLE_FACES])
async def test_a_stored_name_asked_by_a_visitor_is_not_a_household_question(
    faces: FusionReason,
) -> None:
    """No oracle (Plan 0077): a stored name asked by a visitor or in company is conversation."""
    seams = _Seams()

    reply = await _reply(
        _query(SensitiveTopic.CHILD_BIRTHDAY, "zeta"), seams, actor=_stranger(), faces=faces
    )

    assert reply.outcome is SensitiveOutcome.NOT_HOUSEHOLD
    seams.names.assert_not_awaited()
    _nothing_touched(seams)


async def test_a_family_word_asked_by_a_visitor_is_denied() -> None:
    seams = _Seams()

    reply = await _reply(
        _query(SensitiveTopic.CHILD_BIRTHDAY, "hijo"),
        seams,
        actor=_stranger(),
        faces=FusionReason.NO_EVIDENCE,
    )

    assert reply.outcome is SensitiveOutcome.DENIED
    _nothing_touched(seams)


async def test_unauthorized_children_are_denied() -> None:
    seams = _Seams()
    seams.tools = _tools(ChildBirthdays(KnowledgeStatus.UNAUTHORIZED))

    reply = await _reply(_query(SensitiveTopic.CHILD_BIRTHDAY, "hijos"), seams)

    assert reply.outcome is SensitiveOutcome.DENIED
    assert reply.text is None


@pytest.mark.parametrize(
    "result",
    [
        ChildBirthdays(KnowledgeStatus.UNKNOWN),
        ChildBirthdays(KnowledgeStatus.KNOWN, ()),
    ],
)
async def test_no_registered_children_is_not_registered(result: ChildBirthdays) -> None:
    seams = _Seams()
    seams.tools = _tools(result)

    reply = await _reply(_query(SensitiveTopic.CHILD_BIRTHDAY, "hijos"), seams)

    assert reply.outcome is SensitiveOutcome.NOT_REGISTERED
    assert reply.text is None


async def test_a_malformed_stored_date_is_unavailable() -> None:
    seams = _Seams()
    seams.tools = _tools(ChildBirthdays(KnowledgeStatus.KNOWN, (("Zeta", "no es fecha"),)))

    reply = await _reply(_query(SensitiveTopic.CHILD_BIRTHDAY, "zeta"), seams)

    assert reply.outcome is SensitiveOutcome.UNAVAILABLE


async def test_the_owners_birthday_is_read_as_private_without_consent() -> None:
    seams = _Seams(values=("1990-03-03",))

    reply = await _reply(
        _query(SensitiveTopic.OWN_BIRTHDAY), seams, face_consent=ConsentStatus.MISSING
    )

    assert reply.outcome is SensitiveOutcome.ANSWERED
    assert reply.text == "Tu cumpleaños es el 3 de marzo."
    request = seams.audit.await_args_list[0].args[0]
    assert request.consent is ConsentStatus.NOT_REQUIRED
    assert {item.value for item in request.sensitivity} == {"private"}
    seams.alta_closed.assert_not_awaited()
    seams.reader.assert_awaited_once_with(_OWNER, "birth_date", "private")


def test_a_reply_hides_its_text_from_repr() -> None:
    assert _DOSE_CANARY not in repr(SensitiveReply(SensitiveOutcome.ANSWERED, _DOSE_CANARY))


def test_the_outcomes_are_the_seven_of_the_log_contract() -> None:
    assert {outcome.value for outcome in SensitiveOutcome} == {
        "answered",
        "not_alone",
        "retry_voice",
        "denied",
        "not_registered",
        "unavailable",
        "not_household",
    }


_SCENARIOS = [
    ("answered", SensitiveTopic.MEDICATION, {}),
    ("not_alone", SensitiveTopic.MEDICATION, {"faces": FusionReason.VETO_MULTIPLE_FACES}),
    ("denied", SensitiveTopic.MEDICATION, {"actor": "stranger"}),
    ("retry_voice", SensitiveTopic.SECRET_HOLDER, {"voice_check": True}),
    ("not_registered", SensitiveTopic.MEDICATION, {"values": ()}),
    ("unavailable", SensitiveTopic.MEDICATION, {"audit_fails": True}),
    ("not_household", SensitiveTopic.CHILD_BIRTHDAY, {"keywords": ("mozart",)}),
]


@pytest.mark.parametrize("outcome, topic, options", _SCENARIOS)
async def test_no_value_reaches_a_log_line(
    outcome: str,
    topic: SensitiveTopic,
    options: dict[str, object],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One structured line per call, whatever the outcome, with no value and no keyword."""
    values = options.get("values", (_DOSE_CANARY, _ADDRESS_CANARY))
    assert isinstance(values, tuple)
    seams = _Seams(values=values)
    if options.get("audit_fails"):
        seams.audit.side_effect = RuntimeError(_ADDRESS_CANARY)
    keywords = options.get("keywords", ())
    assert isinstance(keywords, tuple)
    faces = options.get("faces", FusionReason.FACE_ONLY)
    assert faces is None or isinstance(faces, FusionReason)

    with caplog.at_level(logging.DEBUG):
        reply = await _reply(
            _query(topic, *keywords),
            seams,
            actor=_stranger() if options.get("actor") == "stranger" else _face(),
            faces=faces,
            voice_check=bool(options.get("voice_check", False)),
        )

    assert reply.outcome.value == outcome
    lines = [
        record for record in caplog.records if getattr(record, "event", "") == "sensitive.read"
    ]
    assert len(lines) == 1
    assert lines[0].__dict__["topic"] == topic.value
    assert lines[0].__dict__["outcome"] == outcome
    for secret in (_DOSE_CANARY, _ADDRESS_CANARY, "mozart"):
        assert secret not in caplog.text
        assert all(secret not in str(record.__dict__) for record in caplog.records)
