"""The relatives question in the controller (Plan 0078 Task 10, ADR 0028 decision 9)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from server.cognition.controller import CognitiveController
from server.cognition.household_tools import HouseholdToolName, HouseholdToolResult, SidedNames
from server.cognition.identity import ActivePersonContext, ActivePersonStatus, HouseholdRole
from server.cognition.models import CognitiveEvent, Confidence, ConfidenceBasis, KnowledgeStatus
from server.cognition.response_plan import (
    NOT_REGISTERED,
    RELATIVES_LOGGED_TEXT,
    InformationNeed,
    RecallReply,
    ResponseSource,
    TextTurnPayload,
    spoken_log_text,
)
from server.text_turn import TextTurnResult

pytestmark = pytest.mark.unit

_REFUSAL = "Todavía no puedo confirmar quién eres para contarte lo que sé de ti."


def _event(message: str) -> CognitiveEvent[TextTurnPayload]:
    at = datetime(2026, 11, 4, 15, tzinfo=UTC)
    return CognitiveEvent(
        event_id=UUID(int=1),
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


def _actor(person_id: int | None) -> ActivePersonContext:
    return ActivePersonContext(
        person_id=person_id,
        display_name="Canary" if person_id is not None else None,
        status=ActivePersonStatus.IDENTIFIED
        if person_id is not None
        else ActivePersonStatus.UNKNOWN,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.ASSERTED, calibrated=False),
        role=HouseholdRole.OWNER if person_id is not None else HouseholdRole.UNKNOWN,
        evidence=(),
        resolved_at=datetime(2026, 11, 4, 15, tzinfo=UTC),
    )


def _tools(
    status: KnowledgeStatus,
    value: tuple[str, ...] | None = None,
    parents: SidedNames | None = None,
) -> Mock:
    tools = Mock()
    tools.get_relatives = AsyncMock(
        return_value=HouseholdToolResult(
            tool_name=HouseholdToolName.GET_RELATIVES, status=status, value=value
        )
    )
    tools.get_parents = AsyncMock(return_value=parents or SidedNames(status=status))
    return tools


def _parents(
    *,
    female: tuple[str, ...] = (),
    male: tuple[str, ...] = (),
    unlabelled: tuple[str, ...] = (),
    status: KnowledgeStatus = KnowledgeStatus.KNOWN,
) -> SidedNames:
    return SidedNames(status=status, female=female, male=male, unlabelled=unlabelled)


def _controller(
    tools: Mock | None,
    actor: ActivePersonContext,
    *,
    recall: bool = True,
    spending: AsyncMock | None = None,
    legacy: AsyncMock | None = None,
) -> CognitiveController:
    async def observe(_event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        return actor

    return CognitiveController(
        today=lambda: date(2026, 11, 4),
        legacy_turn=legacy
        or AsyncMock(return_value=TextTurnResult("Respuesta normal.", "neutral", 1, False)),
        observed_person_resolver=observe,
        active_person_resolver=spending or AsyncMock(return_value=actor),
        household_tools=tools,  # type: ignore[arg-type]  # a double of the tools
        recall_answerer=AsyncMock(return_value=RecallReply(text=None)) if recall else None,
    )


async def test_parents_are_read_together() -> None:
    tools = _tools(KnowledgeStatus.KNOWN, parents=_parents(female=("Zeta",), male=("Omega",)))

    plan = await _controller(tools, _actor(7)).handle(_event("¿Cómo se llaman mis papás?"))

    assert plan.need is InformationNeed.RELATIVES_NAMES
    assert plan.status is KnowledgeStatus.KNOWN
    assert plan.source is ResponseSource.DETERMINISTIC
    assert plan.response == "Tus papás se llaman Omega y Zeta."
    assert tools.get_parents.await_args is not None
    assert tools.get_parents.await_args.kwargs["owner_entity_id"] == 7
    tools.get_relatives.assert_not_awaited()


async def test_the_mother_question_speaks_the_mother() -> None:
    tools = _tools(KnowledgeStatus.KNOWN, parents=_parents(female=("Zeta",), male=("Omega",)))

    plan = await _controller(tools, _actor(7)).handle(_event("¿Cómo se llama mi mamá?"))

    assert plan.need is InformationNeed.RELATIVES_NAMES
    assert plan.status is KnowledgeStatus.KNOWN
    assert plan.response == "Tu mamá se llama Zeta."
    tools.get_relatives.assert_not_awaited()


async def test_the_father_question_speaks_the_father() -> None:
    tools = _tools(KnowledgeStatus.KNOWN, parents=_parents(female=("Zeta",), male=("Omega",)))

    plan = await _controller(tools, _actor(7)).handle(_event("¿Cuál es el nombre de mi padre?"))

    assert plan.response == "Tu papá se llama Omega."


async def test_a_parent_without_a_side_is_not_labelled() -> None:
    tools = _tools(KnowledgeStatus.KNOWN, parents=_parents(unlabelled=("Omega", "Zeta")))

    plan = await _controller(tools, _actor(7)).handle(_event("¿Cómo se llama mi mamá?"))

    assert (
        plan.response
        == "No tengo claro cuál de ellos es tu mamá. Tus papás se llaman Omega y Zeta."
    )


async def test_one_unlabelled_parent_asked_for_both_uses_the_singular() -> None:
    tools = _tools(KnowledgeStatus.KNOWN, parents=_parents(unlabelled=("Zeta",)))

    plan = await _controller(tools, _actor(7)).handle(_event("¿Cómo se llaman mis papás?"))

    assert plan.response == "Tu papá o tu mamá se llama Zeta."


async def test_one_recorded_mother_asked_for_both_keeps_her_side() -> None:
    tools = _tools(KnowledgeStatus.KNOWN, parents=_parents(female=("Zeta",)))

    plan = await _controller(tools, _actor(7)).handle(_event("¿Cómo se llaman mis papás?"))

    assert plan.response == "Tu mamá se llama Zeta."


async def test_the_absent_side_is_not_registered() -> None:
    tools = _tools(KnowledgeStatus.KNOWN, parents=_parents(female=("Zeta",)))

    plan = await _controller(tools, _actor(7)).handle(_event("¿Cómo se llama mi papá?"))

    assert plan.need is InformationNeed.RELATIVES_NAMES
    assert plan.response == NOT_REGISTERED


async def test_no_parent_stored_is_not_registered() -> None:
    tools = _tools(KnowledgeStatus.UNKNOWN)

    plan = await _controller(tools, _actor(7)).handle(_event("¿Cómo se llaman mis papás?"))

    assert plan.response == NOT_REGISTERED


async def test_an_unauthorized_parent_read_sounds_like_a_stranger() -> None:
    tools = _tools(KnowledgeStatus.UNAUTHORIZED)

    plan = await _controller(tools, _actor(8)).handle(_event("¿Cómo se llama mi mamá?"))

    assert plan.response == _REFUSAL


@pytest.mark.parametrize("message", ["¿Cómo se llama mi mamá?", "¿Cómo se llaman mis papás?"])
@pytest.mark.parametrize("status", [None, ActivePersonStatus.AMBIGUOUS])
async def test_a_stranger_and_two_faces_never_reach_the_parents(
    message: str, status: ActivePersonStatus | None
) -> None:
    tools = _tools(KnowledgeStatus.KNOWN, parents=_parents(female=("Zeta",), male=("Omega",)))
    # Two faces: a person id is present, but the status is not IDENTIFIED.
    actor = _actor(None)
    if status is not None:
        actor = _actor(7).model_copy(update={"status": status})

    plan = await _controller(tools, actor).handle(_event(message))

    assert plan.response == _REFUSAL
    tools.get_parents.assert_not_awaited()
    tools.get_relatives.assert_not_awaited()


async def test_a_sibling_still_goes_through_get_relatives() -> None:
    tools = _tools(KnowledgeStatus.KNOWN, ("Zeta",))

    await _controller(tools, _actor(7)).handle(_event("¿Quién es mi hermana?"))

    tools.get_parents.assert_not_awaited()
    assert tools.get_relatives.await_args is not None
    assert tools.get_relatives.await_args.kwargs["predicate"] == "has_sibling"


@pytest.mark.parametrize(
    "message, names, said",
    [
        ("¿Cómo se llama mi perrita?", ("Zeta",), "Tu mascota se llama Zeta."),
        (
            "¿Cómo se llaman mis mascotas?",
            ("Omega", "Zeta"),
            "Tus mascotas se llaman Omega y Zeta.",
        ),
        ("¿Cómo se llama mi esposa?", ("Zeta",), "Tu pareja se llama Zeta."),
        ("¿Quiénes son mis hermanos?", ("Omega", "Zeta"), "Tus hermanos se llaman Omega y Zeta."),
        ("¿Quién es mi hermana?", ("Zeta",), "Tu hermano o hermana se llama Zeta."),
        ("¿Cómo se llaman mis abuelos?", ("Omega", "Zeta"), "Tus abuelos se llaman Omega y Zeta."),
        ("¿Cómo se llama mi nieta?", ("Zeta",), "Tu nieto o nieta se llama Zeta."),
        (
            "¿Cómo se llaman mis nietos?",
            ("Canary", "Omega", "Zeta"),
            "Tus nietos se llaman Canary, Omega y Zeta.",
        ),
    ],
)
async def test_a_pet_and_a_partner_are_read(
    message: str, names: tuple[str, ...], said: str
) -> None:
    plan = await _controller(_tools(KnowledgeStatus.KNOWN, names), _actor(7)).handle(
        _event(message)
    )

    assert plan.response == said


async def test_nothing_stored_is_not_registered() -> None:
    plan = await _controller(_tools(KnowledgeStatus.UNKNOWN), _actor(7)).handle(
        _event("¿Cómo se llama mi abuela?")
    )

    assert plan.need is InformationNeed.RELATIVES_NAMES
    assert plan.response == NOT_REGISTERED


async def test_a_stranger_hears_the_refusal() -> None:
    tools = _tools(KnowledgeStatus.KNOWN, ("Zeta",))

    plan = await _controller(tools, _actor(None)).handle(_event("¿Cómo se llaman mis papás?"))

    assert plan.response == _REFUSAL
    tools.get_relatives.assert_not_awaited()


async def test_an_unauthorized_read_sounds_like_a_stranger() -> None:
    plan = await _controller(_tools(KnowledgeStatus.UNAUTHORIZED), _actor(8)).handle(
        _event("¿Cómo se llaman mis papás?")
    )

    assert plan.response == _REFUSAL


async def test_the_relatives_never_spend_a_grant() -> None:
    spending = AsyncMock()

    await _controller(
        _tools(KnowledgeStatus.KNOWN, ("Zeta",)), _actor(7), spending=spending
    ).handle(_event("¿Cómo se llama mi mamá?"))

    spending.assert_not_awaited()


async def test_with_recall_disabled_the_question_is_protected_as_today() -> None:
    tools = _tools(KnowledgeStatus.KNOWN, ("Zeta",))

    plan = await _controller(tools, _actor(7), recall=False).handle(
        _event("¿Cómo se llaman mis papás?")
    )

    assert plan.need is InformationNeed.PROTECTED_HOUSEHOLD
    tools.get_relatives.assert_not_awaited()


async def test_without_the_tools_the_question_keeps_the_protected_route() -> None:
    plan = await _controller(None, _actor(7)).handle(_event("¿Cómo se llaman mis papás?"))

    assert plan.need is InformationNeed.PROTECTED_HOUSEHOLD


def test_the_opt_in_log_shows_the_marker() -> None:
    from server.cognition.response_plan import ResponsePlan  # noqa: PLC0415 - local to this test

    plan = ResponsePlan(
        need=InformationNeed.RELATIVES_NAMES,
        status=KnowledgeStatus.KNOWN,
        source=ResponseSource.DETERMINISTIC,
        response="Tus papás se llaman Omega y Zeta.",
    )

    assert spoken_log_text(plan) == RELATIVES_LOGGED_TEXT == "[parientes leídos]"
