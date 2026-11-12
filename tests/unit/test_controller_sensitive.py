"""The sensitive-read and secret branches of the controller (Plan 0079 Task 7, ADR 0029)."""

from __future__ import annotations

from datetime import UTC, date, datetime
import logging
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from server.cognition.controller import CognitiveController
from server.cognition.identity import ActivePersonContext, ActivePersonStatus, HouseholdRole
from server.cognition.intent_resolution import IntentMatch, IntentResolution
from server.cognition.models import CognitiveEvent, Confidence, ConfidenceBasis, KnowledgeStatus
from server.cognition.response_plan import (
    NO_BIRTH_DATE,
    NOT_ALONE,
    NOT_REGISTERED,
    SECRET_RECORDED_TEXT,
    SECRET_REFUSAL,
    SECURITY_VOICE_RETRY,
    SENSITIVE_RECORDED_TEXT,
    InformationNeed,
    ResponsePlan,
    ResponseSource,
    SensitiveOutcome,
    SensitiveReply,
    TextTurnPayload,
    recorded_exchange,
    spoken_log_text,
)
from server.cognition.sensitive_questions import SensitiveTopic
from server.text_turn import TextTurnResult

pytestmark = pytest.mark.unit

_QUESTION = "¿Qué remedios tomo?"
_STATED = "Mi clave es 1234"
_ASKED = "¿Cuál es mi clave del banco?"
_OFFERED = "Guarda mi contraseña"
_ANSWER = "Tu medicamento es Remedio A."
_DENIAL = "Todavía no puedo confirmar quién eres para contarte lo que sé de ti."
_UNAVAILABLE = "Ahora no puedo revisar lo que sé de ti. Inténtalo de nuevo en un rato."


def _event(message: str, event_id: int = 1) -> CognitiveEvent[TextTurnPayload]:
    at = datetime(2026, 11, 5, 15, tzinfo=UTC)
    return CognitiveEvent(
        event_id=UUID(int=event_id),
        schema_version=1,
        event_type="text.turn",
        occurred_at=at,
        recorded_at=at,
        source="audio.transcribe",
        correlation_id=UUID(int=79),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message=message, conversation_id="voice"),
    )


def _actor(person_id: int | None = 7) -> ActivePersonContext:
    identified = person_id is not None
    return ActivePersonContext(
        person_id=person_id,
        display_name="Canary" if identified else None,
        status=ActivePersonStatus.IDENTIFIED if identified else ActivePersonStatus.UNKNOWN,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.ASSERTED, calibrated=False),
        role=HouseholdRole.OWNER if identified else HouseholdRole.UNKNOWN,
        evidence=(),
        resolved_at=datetime(2026, 11, 5, 15, tzinfo=UTC),
    )


def _legacy() -> AsyncMock:
    return AsyncMock(return_value=TextTurnResult("Respuesta normal.", "neutral", 42, False))


def _reply(outcome: SensitiveOutcome, text: str | None = None) -> AsyncMock:
    return AsyncMock(return_value=SensitiveReply(outcome=outcome, text=text))


def _controller(
    reader: AsyncMock | None,
    *,
    guard: bool = False,
    legacy: AsyncMock | None = None,
    spending: AsyncMock | None = None,
    observed: AsyncMock | None = None,
) -> CognitiveController:
    return CognitiveController(
        today=lambda: date(2026, 11, 5),
        legacy_turn=legacy or _legacy(),
        observed_person_resolver=observed or AsyncMock(return_value=_actor()),
        active_person_resolver=spending or AsyncMock(return_value=_actor()),
        sensitive_reader=reader,
        secret_guard=guard,
    )


async def test_an_answered_read_is_a_known_deterministic_plan() -> None:
    reader = _reply(SensitiveOutcome.ANSWERED, _ANSWER)
    legacy = _legacy()
    event = _event(_QUESTION)

    plan = await _controller(reader, legacy=legacy).handle(event)

    assert plan.need is InformationNeed.SENSITIVE_READ
    assert plan.status is KnowledgeStatus.KNOWN
    assert plan.source is ResponseSource.DETERMINISTIC
    assert plan.response == _ANSWER
    assert plan.claims == ()
    legacy.assert_not_awaited()
    assert reader.await_args is not None
    actor, query, passed = reader.await_args.args
    assert actor.person_id == 7
    assert query.topic is SensitiveTopic.MEDICATION
    assert passed is event


@pytest.mark.parametrize(
    "outcome, text, expected",
    [
        (SensitiveOutcome.NOT_ALONE, None, NOT_ALONE),
        (SensitiveOutcome.RETRY_VOICE, None, SECURITY_VOICE_RETRY),
        (SensitiveOutcome.DENIED, None, _DENIAL),
        (SensitiveOutcome.NOT_REGISTERED, None, NOT_REGISTERED),
        (SensitiveOutcome.NOT_REGISTERED, NO_BIRTH_DATE, NO_BIRTH_DATE),
        (SensitiveOutcome.UNAVAILABLE, None, _UNAVAILABLE),
    ],
)
async def test_every_other_outcome_is_an_unknown_fixed_phrase(
    outcome: SensitiveOutcome, text: str | None, expected: str
) -> None:
    legacy = _legacy()

    plan = await _controller(_reply(outcome, text), legacy=legacy).handle(_event(_QUESTION))

    assert plan.need is InformationNeed.SENSITIVE_READ
    assert plan.status is KnowledgeStatus.UNKNOWN
    assert plan.source is ResponseSource.DETERMINISTIC
    assert plan.response == expected
    legacy.assert_not_awaited()


def test_the_fixed_phrases_are_the_decided_ones() -> None:
    assert NOT_ALONE == "Te lo digo cuando estemos solos."
    assert SECURITY_VOICE_RETRY == (
        "No reconocí bien tu voz. Pregúntamelo de nuevo con una frase completa."
    )
    assert SECRET_REFUSAL == "Las claves y los códigos no los guardo ni los repito."  # noqa: S105  # pragma: allowlist secret - a phrase
    assert SENSITIVE_RECORDED_TEXT == "[dato sensible leído]"
    assert SECRET_RECORDED_TEXT == "[dato de seguridad omitido]"  # noqa: S105  # pragma: allowlist secret - a marker


async def test_a_not_household_reply_is_ordinary_conversation() -> None:
    legacy = _legacy()
    controller = _controller(_reply(SensitiveOutcome.NOT_HOUSEHOLD), legacy=legacy)

    assert await controller.decide(_event("¿Cuándo nació Mozart?")) is None
    plan = await controller.handle(_event("¿Cuándo nació Mozart?"))

    assert plan.need is InformationNeed.GENERIC_CONVERSATION
    assert plan.response == "Respuesta normal."


async def test_a_not_household_reply_keeps_todays_protected_household_path() -> None:
    """Ruling 10: «el cumpleaños de mi tía» is PROTECTED_HOUSEHOLD today, reader or not."""
    message = "¿Cuándo es el cumpleaños de mi tía?"
    reader = _reply(SensitiveOutcome.NOT_HOUSEHOLD)
    with_reader = _controller(reader)
    today = _controller(None)

    plan = await with_reader.handle(_event(message))
    expected = await today.handle(_event(message))

    reader.assert_awaited_once()  # the reader really ran and fell through; no vacuous equality
    assert plan == expected
    assert plan.need is InformationNeed.PROTECTED_HOUSEHOLD


async def test_a_sensitive_answer_never_spends_a_grant() -> None:
    spending = AsyncMock()
    observed = AsyncMock(return_value=_actor())

    await _controller(
        _reply(SensitiveOutcome.ANSWERED, _ANSWER), spending=spending, observed=observed
    ).handle(_event(_QUESTION))

    spending.assert_not_awaited()
    observed.assert_awaited_once()


async def test_a_sensitive_answer_is_not_written_to_continuity() -> None:
    """Continuity is written only by the legacy text turn; a controller answer never reaches it."""
    legacy = _legacy()
    controller = _controller(_reply(SensitiveOutcome.ANSWERED, _ANSWER), legacy=legacy)

    plan = await controller.handle(_event(_QUESTION))

    assert plan.source is ResponseSource.DETERMINISTIC
    legacy.assert_not_awaited()


async def test_the_classic_double_decide_reads_once_per_event() -> None:
    reader = _reply(SensitiveOutcome.NOT_HOUSEHOLD)
    controller = _controller(reader)

    assert await controller.decide(_event(_QUESTION)) is None
    await controller.handle(_event(_QUESTION))

    reader.assert_awaited_once()


async def test_a_secret_turn_calls_no_model_and_no_resolver() -> None:
    reader = _reply(SensitiveOutcome.ANSWERED, _ANSWER)
    legacy = _legacy()
    spending = AsyncMock()
    observed = AsyncMock()
    controller = _controller(
        reader, guard=True, legacy=legacy, spending=spending, observed=observed
    )

    plan = await controller.handle(_event(_STATED))

    assert plan.need is InformationNeed.SECRET_VALUE
    assert plan.status is KnowledgeStatus.UNKNOWN
    assert plan.source is ResponseSource.DETERMINISTIC
    assert plan.response == SECRET_REFUSAL
    legacy.assert_not_awaited()
    reader.assert_not_awaited()
    spending.assert_not_awaited()
    observed.assert_not_awaited()


async def test_a_secret_question_is_refused_too() -> None:
    plan = await _controller(None, guard=True).handle(_event(_ASKED))

    assert plan.need is InformationNeed.SECRET_VALUE
    assert plan.response == SECRET_REFUSAL


async def test_a_message_that_states_and_asks_takes_the_secret_branch() -> None:
    reader = _reply(SensitiveOutcome.ANSWERED, _ANSWER)

    plan = await _controller(reader, guard=True).handle(
        _event("Mi clave es 1234, ¿qué remedios tomo?")
    )

    assert plan.need is InformationNeed.SECRET_VALUE
    reader.assert_not_awaited()


async def test_an_offered_secret_is_refused_without_a_model() -> None:
    """«Guarda mi contraseña» gives no value; the model must not invite it in the next turn."""
    legacy = _legacy()

    plan = await _controller(None, guard=True, legacy=legacy).handle(_event(_OFFERED))

    assert plan.need is InformationNeed.SECRET_VALUE
    assert plan.response == SECRET_REFUSAL
    legacy.assert_not_awaited()


@pytest.mark.parametrize(
    "message, kind", [(_STATED, "stated"), (_ASKED, "asked"), (_OFFERED, "offered")]
)
async def test_a_secret_turn_logs_its_kind_and_never_a_text(
    message: str, kind: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="server.cognition.controller"):
        await _controller(None, guard=True).handle(_event(message))

    records = [r for r in caplog.records if getattr(r, "event", None) == "secret.turn"]
    assert len(records) == 1
    assert records[0].kind == kind  # type: ignore[attr-defined]  # LogRecord extra field
    assert "1234" not in caplog.text
    assert "banco" not in caplog.text


async def test_without_the_guard_a_secret_is_ordinary_conversation() -> None:
    legacy = _legacy()

    plan = await _controller(None, legacy=legacy).handle(_event(_STATED))

    assert plan.need is InformationNeed.GENERIC_CONVERSATION
    legacy.assert_awaited_once()


async def test_without_the_reader_a_sensitive_question_resolves_as_today() -> None:
    legacy = _legacy()

    plan = await _controller(None, legacy=legacy).handle(_event(_QUESTION))

    assert plan.need is InformationNeed.GENERIC_CONVERSATION
    legacy.assert_awaited_once()


def _resolver() -> Mock:
    return Mock(
        return_value=IntentResolution(
            need=InformationNeed.GENERIC_CONVERSATION, match=IntentMatch.NONE, rule_id=None
        )
    )


async def test_the_resolver_gets_a_flag_only_when_it_is_set() -> None:
    bare = _resolver()
    await CognitiveController(
        today=lambda: date(2026, 11, 5), legacy_turn=_legacy(), intent_resolver=bare
    ).handle(_event("hola"))
    both = _resolver()
    await CognitiveController(
        today=lambda: date(2026, 11, 5),
        legacy_turn=_legacy(),
        intent_resolver=both,
        sensitive_reader=_reply(SensitiveOutcome.ANSWERED),
        secret_guard=True,
    ).handle(_event("hola"))
    guard_only = _resolver()
    await CognitiveController(
        today=lambda: date(2026, 11, 5),
        legacy_turn=_legacy(),
        intent_resolver=guard_only,
        secret_guard=True,
    ).handle(_event("hola"))

    bare.assert_called_once_with("hola")
    both.assert_called_once_with("hola", sensitive=True, secrets=True)
    guard_only.assert_called_once_with("hola", secrets=True)


def test_recorded_exchange_markers() -> None:
    def plan(need: InformationNeed, status: KnowledgeStatus, response: str) -> ResponsePlan:
        return ResponsePlan(
            need=need, status=status, source=ResponseSource.DETERMINISTIC, response=response
        )

    secret = plan(InformationNeed.SECRET_VALUE, KnowledgeStatus.UNKNOWN, SECRET_REFUSAL)
    read = plan(InformationNeed.SENSITIVE_READ, KnowledgeStatus.KNOWN, _ANSWER)
    refused = plan(InformationNeed.SENSITIVE_READ, KnowledgeStatus.UNKNOWN, NOT_ALONE)
    other = plan(InformationNeed.CURRENT_DATE, KnowledgeStatus.KNOWN, "Hoy es jueves.")

    assert recorded_exchange(secret, _STATED) == (SECRET_RECORDED_TEXT, SECRET_REFUSAL)
    assert recorded_exchange(read, _QUESTION) == (_QUESTION, SENSITIVE_RECORDED_TEXT)
    assert recorded_exchange(refused, _QUESTION) == (_QUESTION, NOT_ALONE)
    assert recorded_exchange(other, "¿Qué día es hoy?") == ("¿Qué día es hoy?", "Hoy es jueves.")


def test_the_spoken_log_shows_the_marker() -> None:
    read = ResponsePlan(
        need=InformationNeed.SENSITIVE_READ,
        status=KnowledgeStatus.KNOWN,
        source=ResponseSource.DETERMINISTIC,
        response=_ANSWER,
    )
    refused = ResponsePlan(
        need=InformationNeed.SENSITIVE_READ,
        status=KnowledgeStatus.UNKNOWN,
        source=ResponseSource.DETERMINISTIC,
        response=NOT_ALONE,
    )

    assert spoken_log_text(read) == SENSITIVE_RECORDED_TEXT
    assert spoken_log_text(refused) is None


# --- Plan 0082 Task 6: the alta flag reaches the resolver and the grammar ---


async def test_the_controller_passes_the_alta_flag_only_when_set() -> None:
    off = _resolver()
    await CognitiveController(
        today=lambda: date(2026, 11, 5),
        legacy_turn=_legacy(),
        intent_resolver=off,
        sensitive_reader=_reply(SensitiveOutcome.ANSWERED),
    ).handle(_event("hola"))
    on = _resolver()
    await CognitiveController(
        today=lambda: date(2026, 11, 5),
        legacy_turn=_legacy(),
        intent_resolver=on,
        sensitive_reader=_reply(SensitiveOutcome.ANSWERED),
        alta_read=True,
    ).handle(_event("hola"))
    without_reader = _resolver()
    await CognitiveController(
        today=lambda: date(2026, 11, 5),
        legacy_turn=_legacy(),
        intent_resolver=without_reader,
        alta_read=True,
    ).handle(_event("hola"))

    off.assert_called_once_with("hola", sensitive=True)
    on.assert_called_once_with("hola", sensitive=True, alta=True)
    without_reader.assert_called_once_with("hola")


async def test_an_alta_question_reaches_the_reader_only_with_the_flag() -> None:
    contact = "¿Tienes el teléfono de mi hija?"
    reader = _reply(SensitiveOutcome.ANSWERED, "El teléfono de Canary, tu hija, es más uno.")
    legacy = _legacy()
    plan = await CognitiveController(
        today=lambda: date(2026, 11, 5),
        legacy_turn=legacy,
        observed_person_resolver=AsyncMock(return_value=_actor()),
        active_person_resolver=AsyncMock(return_value=_actor()),
        sensitive_reader=reader,
        alta_read=True,
    ).handle(_event(contact))
    assert plan.need is InformationNeed.SENSITIVE_READ
    query = reader.await_args.args[1] if reader.await_args else None
    assert query is not None
    assert query.keywords == ("mi", "hija")
    legacy.assert_not_awaited()

    off_reader = _reply(SensitiveOutcome.ANSWERED)
    off_plan = await _controller(off_reader).handle(_event(contact))
    off_reader.assert_not_awaited()
    assert off_plan.need is not InformationNeed.SENSITIVE_READ


async def test_a_contact_answer_is_not_written_to_continuity() -> None:
    legacy = _legacy()
    plan = await CognitiveController(
        today=lambda: date(2026, 11, 5),
        legacy_turn=legacy,
        observed_person_resolver=AsyncMock(return_value=_actor()),
        active_person_resolver=AsyncMock(return_value=_actor()),
        sensitive_reader=_reply(SensitiveOutcome.ANSWERED, "El teléfono de tu hija es más uno."),
        alta_read=True,
    ).handle(_event("Llama a mi contacto 1"))
    assert plan.response == "El teléfono de tu hija es más uno."
    legacy.assert_not_awaited()  # only the legacy text turn writes continuity
