"""The reading branch of the controller (Plan 0088 Task B9, D-17, Review focus 5)."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from server.cognition.controller import CognitiveController
from server.cognition.response_plan import (
    COULD_NOT_READ,
    NOTHING_TO_READ,
    READ_OFFER,
    READ_SECRET,
    READING_KEPT,
    InformationNeed,
    KeepOutcome,
    MemoryAnswerReply,
    ReadingOutcome,
    ReadingReply,
)

from tests.unit.test_controller_recall import _actor, _event, _legacy

if TYPE_CHECKING:
    from server.cognition.identity import ActivePersonContext

pytestmark = pytest.mark.unit

_TEXT = "Leche descremada zzcanaryzz"


def _controller(
    reader: AsyncMock | None,
    keeper: AsyncMock | None,
    *,
    answerer: AsyncMock | None = None,
    actor: ActivePersonContext | None = None,
) -> CognitiveController:
    person = actor or _actor(7)

    async def observe(_event: object) -> ActivePersonContext:
        return person

    return CognitiveController(
        today=lambda: date(2026, 11, 4),
        legacy_turn=_legacy(),
        observed_person_resolver=observe,
        active_person_resolver=AsyncMock(return_value=person),
        memory_answerer=answerer,
        text_reader=reader,
        reading_keeper=keeper,
    )


def _reader(outcome: ReadingOutcome, text: str | None = None) -> AsyncMock:
    return AsyncMock(return_value=ReadingReply(outcome=outcome, text=text))


def _keeper(outcome: KeepOutcome = KeepOutcome.NO_SLOT) -> AsyncMock:
    return AsyncMock(return_value=outcome)


@pytest.mark.parametrize(
    "outcome, spoken",
    [(ReadingOutcome.NO_FRAME, NOTHING_TO_READ), (ReadingOutcome.FAILED, COULD_NOT_READ)],
)
async def test_no_frame_and_a_vlm_failure_say_their_phrases(
    outcome: ReadingOutcome, spoken: str
) -> None:
    plan = await _controller(_reader(outcome), _keeper()).handle(_event("Iroko, lee esto"))

    assert (plan.need, plan.response) == (InformationNeed.READ_TEXT, spoken)


async def test_the_read_text_is_spoken_then_offered() -> None:
    plan = await _controller(_reader(ReadingOutcome.READ, _TEXT), _keeper()).handle(
        _event("lee esto")
    )

    assert plan.response == f"{_TEXT} {READ_OFFER}"
    assert READ_OFFER == "¿Lo guardo? Dime: sí, guárdalo."


async def test_a_text_with_a_code_is_not_spoken_and_nothing_is_offered() -> None:
    plan = await _controller(_reader(ReadingOutcome.SECRET), _keeper()).handle(_event("lee esto"))

    assert plan.response == READ_SECRET
    assert READ_OFFER not in plan.response


async def test_keep_with_an_open_slot_stores_the_reading_and_leaves_the_candidate() -> None:
    answerer = AsyncMock(return_value=MemoryAnswerReply(phrase="Guardado."))
    keeper = _keeper(KeepOutcome.KEPT)

    plan = await _controller(None, keeper, answerer=answerer).handle(_event("Sí, guárdalo"))

    assert plan.response == READING_KEPT
    assert keeper.await_args is not None
    assert keeper.await_args.args[1] is True
    answerer.assert_not_awaited()


async def test_keep_with_no_slot_keeps_adr_0021_s_meaning() -> None:
    keeper = _keeper(KeepOutcome.NO_SLOT)
    legacy = _legacy()
    controller = _controller(None, keeper)
    controller._legacy_turn = legacy  # the same double, observed

    await controller.handle(_event("Sí, guárdalo"))

    assert keeper.await_count == 1


async def test_any_other_turn_is_handed_to_the_keeper_as_no_keep() -> None:
    keeper = _keeper(KeepOutcome.NOT_KEPT)

    await _controller(None, keeper).handle(_event("Hola, ¿cómo estás?"))

    assert keeper.await_args is not None
    assert keeper.await_args.args[1] is False


async def test_the_classic_route_s_second_decision_does_not_read_or_keep_twice() -> None:
    reader = _reader(ReadingOutcome.READ, _TEXT)
    keeper = _keeper()
    controller = _controller(reader, keeper)
    event = _event("lee esto")

    await controller.decide(event)
    await controller.decide(event)

    assert (reader.await_count, keeper.await_count) == (1, 1)


async def test_without_the_reader_a_reading_phrase_is_conversation() -> None:
    plan = await _controller(None, None).handle(_event("lee esto"))

    assert plan.response == "Respuesta normal."
