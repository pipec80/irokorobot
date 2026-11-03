"""The recall branch of the controller (Plan 0078 Task 9, ADR 0028 decisions 4, 5 and 8)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from server.cognition.controller import CognitiveController
from server.cognition.identity import ActivePersonContext, ActivePersonStatus, HouseholdRole
from server.cognition.models import CognitiveEvent, Confidence, ConfidenceBasis, KnowledgeStatus
from server.cognition.recall_cues import CueStrength
from server.cognition.response_plan import (
    NO_MEMORY,
    RECALL_LOGGED_TEXT,
    InformationNeed,
    RecallReply,
    ResponseSource,
    TextTurnPayload,
    spoken_log_text,
)
from server.text_turn import TextTurnResult

pytestmark = pytest.mark.unit

_STRONG = "¿Qué te conté del cerro?"
_WEAK = "¿Te acuerdas de Mozart?"
_REFUSAL = "Todavía no puedo confirmar quién eres para contarte lo que sé de ti."
_ANSWER = "Sí, ayer me contaste que fuiste al cerro con Zeta."


def _event(message: str, event_id: int = 1) -> CognitiveEvent[TextTurnPayload]:
    at = datetime(2026, 11, 4, 15, tzinfo=UTC)
    return CognitiveEvent(
        event_id=UUID(int=event_id),
        schema_version=1,
        event_type="text.turn",
        occurred_at=at,
        recorded_at=at,
        source="audio.transcribe",
        correlation_id=UUID(int=78),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message=message, conversation_id="voice"),
    )


def _actor(person_id: int | None, role: HouseholdRole = HouseholdRole.OWNER) -> ActivePersonContext:
    return ActivePersonContext(
        person_id=person_id,
        display_name="Canary" if person_id is not None else None,
        status=ActivePersonStatus.IDENTIFIED
        if person_id is not None
        else ActivePersonStatus.UNKNOWN,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.ASSERTED, calibrated=False),
        role=role,
        evidence=(),
        resolved_at=datetime(2026, 11, 4, 15, tzinfo=UTC),
    )


def _legacy() -> AsyncMock:
    return AsyncMock(return_value=TextTurnResult("Respuesta normal.", "neutral", 42, False))


def _controller(
    answerer: AsyncMock | None,
    actor: ActivePersonContext,
    *,
    legacy: AsyncMock | None = None,
    spending: AsyncMock | None = None,
) -> CognitiveController:
    async def observe(_event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        return actor

    return CognitiveController(
        today=lambda: date(2026, 11, 4),
        legacy_turn=legacy or _legacy(),
        observed_person_resolver=observe,
        active_person_resolver=spending or AsyncMock(return_value=actor),
        recall_answerer=answerer,
    )


async def test_a_strong_cue_with_hits_answers_from_them() -> None:
    answerer = AsyncMock(return_value=RecallReply(text=_ANSWER, found=True))
    legacy = _legacy()
    event = _event(_STRONG)

    plan = await _controller(answerer, _actor(7), legacy=legacy).handle(event)

    assert plan.need is InformationNeed.RECALL
    assert plan.status is KnowledgeStatus.KNOWN
    assert plan.source is ResponseSource.DETERMINISTIC
    assert plan.response == _ANSWER
    legacy.assert_not_awaited()
    assert answerer.await_args is not None
    actor, cue, passed = answerer.await_args.args
    assert actor.person_id == 7
    assert cue.strength is CueStrength.STRONG
    assert passed is event


async def test_a_strong_cue_without_hits_says_it_does_not_remember() -> None:
    plan = await _controller(AsyncMock(return_value=RecallReply(text=None)), _actor(7)).handle(
        _event(_STRONG)
    )

    assert plan.need is InformationNeed.RECALL
    assert plan.response == NO_MEMORY


async def test_a_strong_cue_whose_search_failed_says_it_does_not_remember() -> None:
    plan = await _controller(AsyncMock(return_value=RecallReply(text=NO_MEMORY)), _actor(7)).handle(
        _event(_STRONG)
    )

    assert plan.response == NO_MEMORY


@pytest.mark.parametrize("reply", [RecallReply(text=None), RecallReply(text=NO_MEMORY)])
async def test_a_weak_cue_without_hits_falls_through_to_conversation(reply: RecallReply) -> None:
    legacy = _legacy()
    controller = _controller(AsyncMock(return_value=reply), _actor(7), legacy=legacy)

    assert await controller.decide(_event(_WEAK)) is None
    plan = await controller.handle(_event(_WEAK))
    assert plan.response == "Respuesta normal."


async def test_a_weak_cue_with_hits_answers_from_them() -> None:
    answerer = AsyncMock(return_value=RecallReply(text=_ANSWER, found=True))

    plan = await _controller(answerer, _actor(7)).handle(_event(_WEAK))

    assert plan.response == _ANSWER


async def test_a_stranger_strong_cue_hears_the_refusal_and_a_weak_cue_converses() -> None:
    """Review focus 4: the answerer (search and embedding) is never reached for a stranger."""
    answerer = AsyncMock()
    stranger = _controller(answerer, _actor(None, HouseholdRole.UNKNOWN))

    strong = await stranger.handle(_event(_STRONG))
    weak = await stranger.handle(_event(_WEAK, event_id=2))

    assert strong.response == _REFUSAL
    assert weak.response == "Respuesta normal."
    answerer.assert_not_awaited()


async def test_a_denied_owner_sounds_like_a_stranger() -> None:
    denied = AsyncMock(return_value=RecallReply(text=None, denied=True))

    from_denied = await _controller(denied, _actor(8, HouseholdRole.ADULT)).handle(_event(_STRONG))
    from_stranger = await _controller(AsyncMock(), _actor(None, HouseholdRole.UNKNOWN)).handle(
        _event(_STRONG)
    )

    assert from_denied == from_stranger
    weak = await _controller(denied, _actor(8, HouseholdRole.ADULT)).decide(_event(_WEAK))
    assert weak is None


async def test_recall_never_spends_a_grant() -> None:
    spending = AsyncMock()
    answerer = AsyncMock(return_value=RecallReply(text=_ANSWER, found=True))

    await _controller(answerer, _actor(7), spending=spending).handle(_event(_STRONG))

    spending.assert_not_awaited()


async def test_the_classic_double_decide_searches_once_per_event() -> None:
    answerer = AsyncMock(return_value=RecallReply(text=None))
    controller = _controller(answerer, _actor(7))

    assert await controller.decide(_event(_WEAK)) is None
    await controller.handle(_event(_WEAK))

    answerer.assert_awaited_once()


async def test_without_the_answerer_a_recall_phrase_resolves_as_before() -> None:
    legacy = _legacy()
    controller = CognitiveController(today=lambda: date(2026, 11, 4), legacy_turn=legacy)

    plan = await controller.handle(_event("¿Qué te conté ayer?"))

    assert plan.need is InformationNeed.GENERIC_CONVERSATION
    legacy.assert_awaited_once()


def test_the_opt_in_log_shows_the_marker() -> None:
    from server.cognition.response_plan import ResponsePlan  # noqa: PLC0415 - local to this test

    found = ResponsePlan(
        need=InformationNeed.RECALL,
        status=KnowledgeStatus.KNOWN,
        source=ResponseSource.DETERMINISTIC,
        response=_ANSWER,
    )
    not_found = ResponsePlan(
        need=InformationNeed.RECALL,
        status=KnowledgeStatus.UNKNOWN,
        source=ResponseSource.DETERMINISTIC,
        response=NO_MEMORY,
    )

    assert spoken_log_text(found) == RECALL_LOGGED_TEXT == "[recuerdo leído]"
    assert spoken_log_text(not_found) is None


def test_a_recall_reply_never_shows_its_text_in_the_repr() -> None:
    assert "Zeta" not in repr(RecallReply(text=_ANSWER, found=True))
