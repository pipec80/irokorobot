"""The occurred-time flag through the resolver, the controller and ``tells_something``.

Plan 0083 Task 5 (D-1, D-13): with the flag off every resolution, cue and unit is today's; on, the
usted forms and the years and seasons reach recall. Phrases from the shared fixture; canaries only.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from itertools import product
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from server.cognition import intent_resolution as resolver_module
from server.cognition.controller import CognitiveController
from server.cognition.identity import ActivePersonContext, ActivePersonStatus, HouseholdRole
from server.cognition.intent_resolution import resolve_information_need
from server.cognition.models import CognitiveEvent, Confidence, ConfidenceBasis
from server.cognition.response_plan import InformationNeed, RecallReply, TextTurnPayload
from server.memory.recall_store import tells_something
from server.settings import settings
from server.text_turn import TextTurnResult
import yaml

if TYPE_CHECKING:
    from server.cognition.recall_cues import RecallCue

pytestmark = pytest.mark.unit

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "recall_cues_occurred.yaml"
_CASES = cast("list[dict[str, object]]", yaml.safe_load(_FIXTURE.read_text(encoding="utf-8")))
_MESSAGES = [str(case["message"]) for case in _CASES]
_USTED_WHEN = _MESSAGES[4]  # «¿Se acuerda cuándo fui a la playa?»
_LAST_YEAR = _MESSAGES[0]  # «¿Qué hice el año pasado?»


@pytest.mark.parametrize("recall, sensitive, secrets, alta", list(product([False, True], repeat=4)))
def test_with_the_flag_off_the_rules_are_unchanged(
    *, recall: bool, sensitive: bool, secrets: bool, alta: bool
) -> None:
    today = resolver_module._rules_for(recall, sensitive, secrets, alta)
    assert resolver_module._rules_for(recall, sensitive, secrets, alta, False) == today
    if not recall:
        assert resolver_module._rules_for(recall, sensitive, secrets, alta, True) == today


@pytest.mark.parametrize("message", _MESSAGES)
def test_the_resolver_flag_needs_recall(message: str) -> None:
    assert resolve_information_need(message, occurred=True) == resolve_information_need(message)
    with_cue = next(case for case in _CASES if case["message"] == message)["with_flag"]
    on = resolve_information_need(message, recall=True, occurred=True)
    if with_cue is None:
        assert on.need is not InformationNeed.RECALL
    else:
        assert on.need is InformationNeed.RECALL


def test_an_usted_when_question_is_recall_only_with_the_flag() -> None:
    assert resolve_information_need(_USTED_WHEN, recall=True).need is not InformationNeed.RECALL
    on = resolve_information_need(_USTED_WHEN, recall=True, occurred=True)
    assert on.need is InformationNeed.RECALL
    assert on.rule_id == "recall.strong.v1"


def _event(message: str) -> CognitiveEvent[TextTurnPayload]:
    at = datetime(2026, 11, 12, 15, tzinfo=UTC)
    return CognitiveEvent(
        event_id=UUID(int=83),
        schema_version=1,
        event_type="text.turn",
        occurred_at=at,
        recorded_at=at,
        source="audio.transcribe",
        correlation_id=UUID(int=83),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message=message, conversation_id="voice"),
    )


def _owner() -> ActivePersonContext:
    return ActivePersonContext(
        person_id=1,
        display_name="Canary",
        status=ActivePersonStatus.IDENTIFIED,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.ASSERTED, calibrated=False),
        role=HouseholdRole.OWNER,
        evidence=(),
        resolved_at=datetime(2026, 11, 12, 15, tzinfo=UTC),
    )


def _controller(
    answerer: AsyncMock, *, occurred_time: bool, resolver: object = None
) -> CognitiveController:
    async def observe(_event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        return _owner()

    extra = {} if resolver is None else {"intent_resolver": resolver}
    return CognitiveController(
        today=lambda: date(2026, 11, 12),
        legacy_turn=AsyncMock(
            return_value=TextTurnResult("Respuesta normal.", "neutral", 1, False)
        ),
        observed_person_resolver=observe,
        recall_answerer=answerer,
        occurred_time=occurred_time,
        **extra,  # type: ignore[arg-type]  # the resolver spy stands in for the real one
    )


@pytest.mark.parametrize("occurred_time", [False, True])
async def test_the_controller_passes_the_flag_only_when_set(*, occurred_time: bool) -> None:
    seen: list[dict[str, bool]] = []

    def spy(message: str, **flags: bool) -> object:
        seen.append(flags)
        return resolve_information_need(message, **flags)

    answerer = AsyncMock(return_value=RecallReply(text="zzanswerzz", found=True))
    await _controller(answerer, occurred_time=occurred_time, resolver=spy).decide(
        _event(_LAST_YEAR)
    )
    assert seen
    assert all(("occurred" in flags) is occurred_time for flags in seen)


@pytest.mark.parametrize("occurred_time", [False, True])
async def test_the_cue_reaches_the_answerer_with_its_window(*, occurred_time: bool) -> None:
    answerer = AsyncMock(return_value=RecallReply(text="zzanswerzz", found=True))
    await _controller(answerer, occurred_time=occurred_time).decide(_event(_LAST_YEAR))
    assert answerer.await_args is not None
    cue = cast("RecallCue", answerer.await_args.args[1])
    if occurred_time:
        assert cue.window is not None
        assert (cue.window.start, cue.window.end) == (date(2025, 1, 1), date(2025, 12, 31))
    else:
        assert cue.window is None


def test_tells_something_follows_the_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "recall_enabled", True)
    monkeypatch.setattr(settings, "occurred_time_enabled", False)
    assert tells_something(_USTED_WHEN) is True
    monkeypatch.setattr(settings, "occurred_time_enabled", True)
    assert tells_something(_USTED_WHEN) is False
    monkeypatch.setattr(settings, "recall_enabled", False)
    assert tells_something(_USTED_WHEN) is True
