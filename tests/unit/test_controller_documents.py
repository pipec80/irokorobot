"""The document branch of the controller (Plan 0088 Task B8, D-11, D-14, D-15)."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest
from server.cognition.controller import CognitiveController
from server.cognition.identity import ActivePersonContext, HouseholdRole
from server.cognition.models import KnowledgeStatus
from server.cognition.recall_cues import CueStrength
from server.cognition.response_plan import DocumentReply, InformationNeed, RecallReply

from tests.unit.test_controller_recall import _actor, _event, _legacy

pytestmark = pytest.mark.unit

_STRONG = "¿Qué dice mi manual de la lavadora sobre el filtro?"
_WEAK = "¿Qué dice el manual de la lavadora sobre el filtro?"
_RECALL = "¿Qué te conté del cerro?"
_ANSWER = "Según Manual de la lavadora: gírelo hacia la izquierda."
_NOT_FOUND = "No lo encuentro en tus documentos."
_REFUSAL = "Todavía no puedo confirmar quién eres para contarte lo que sé de ti."


def _controller(
    documents: AsyncMock | None,
    actor: ActivePersonContext,
    *,
    recall: AsyncMock | None = None,
    legacy: AsyncMock | None = None,
) -> CognitiveController:
    async def observe(_event: object) -> ActivePersonContext:
        return actor

    return CognitiveController(
        today=lambda: date(2026, 11, 4),
        legacy_turn=legacy or _legacy(),
        observed_person_resolver=observe,
        active_person_resolver=AsyncMock(return_value=actor),
        recall_answerer=recall,
        document_answerer=documents,
    )


def _reply(**values: object) -> AsyncMock:
    return AsyncMock(return_value=DocumentReply(**values))  # type: ignore[arg-type]  # test values


async def test_a_found_answer_is_spoken_as_a_document_plan() -> None:
    legacy = _legacy()
    answerer = _reply(text=_ANSWER, found=True)

    plan = await _controller(answerer, _actor(7), legacy=legacy).handle(_event(_WEAK))

    assert (plan.need, plan.status, plan.response) == (
        InformationNeed.DOCUMENT,
        KnowledgeStatus.KNOWN,
        _ANSWER,
    )
    legacy.assert_not_awaited()
    assert answerer.await_args is not None
    _, cue, _ = answerer.await_args.args
    assert cue.strength is CueStrength.WEAK


async def test_a_strong_cue_with_nothing_found_says_the_fixed_phrase() -> None:
    plan = await _controller(_reply(text=None), _actor(7)).handle(_event(_STRONG))

    assert plan.response == _NOT_FOUND


@pytest.mark.parametrize("reply", [{"text": None}, {"text": None, "scope_found": False}])
async def test_a_weak_cue_with_nothing_found_or_no_document_converses(
    reply: dict[str, object],
) -> None:
    legacy = _legacy()

    plan = await _controller(_reply(**reply), _actor(7), legacy=legacy).handle(_event(_WEAK))

    assert plan.response == "Respuesta normal."
    legacy.assert_awaited_once()


async def test_a_failure_text_is_spoken_even_for_a_weak_cue() -> None:
    plan = await _controller(_reply(text=_NOT_FOUND), _actor(7)).handle(_event(_WEAK))

    assert plan.response == _NOT_FOUND


@pytest.mark.parametrize(
    "actor", [_actor(None), _actor(9, role=HouseholdRole.GUEST)], ids=["no face", "visitor"]
)
async def test_a_stranger_hears_the_generic_denial_on_a_strong_cue(
    actor: ActivePersonContext,
) -> None:
    answerer = _reply(text=None, denied=True)

    plan = await _controller(answerer, actor).handle(_event(_STRONG))

    assert plan.response == _REFUSAL


async def test_no_face_is_never_handed_to_the_answerer() -> None:
    answerer = _reply(text=_ANSWER, found=True)

    await _controller(answerer, _actor(None)).handle(_event(_STRONG))

    answerer.assert_not_awaited()


async def test_a_recall_cue_never_reads_documents_and_a_document_cue_never_reads_the_diary() -> (
    None
):
    documents = _reply(text=_ANSWER, found=True)
    recall = AsyncMock(return_value=RecallReply(text="Me contaste algo.", found=True))
    controller = _controller(documents, _actor(7), recall=recall)

    await controller.handle(_event(_RECALL, event_id=1))
    documents.assert_not_awaited()
    await controller.handle(_event(_WEAK, event_id=2))
    assert recall.await_count == 1


async def test_without_the_answerer_a_document_question_is_conversation() -> None:
    legacy = _legacy()

    plan = await _controller(None, _actor(7), legacy=legacy).handle(_event(_WEAK))

    assert plan.response == "Respuesta normal."
