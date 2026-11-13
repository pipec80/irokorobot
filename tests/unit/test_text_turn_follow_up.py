"""The pending-topic follow-up in the text turn: after the reply, after any offer (Plan 0084 Task 5).

D-8, D-11 and D-12: prepared while the model answers, committed only for a built reply, spoken
after it, never when a memory offer is spoken instead, appended to the session (never the
record). The preparation and the commit are doubles; canaries only.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from server.cognition.authorization import ConsentStatus
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityAssurance,
    IdentityEvidence,
    IdentityEvidenceSource,
)
from server.cognition.models import Confidence, ConfidenceBasis
from server.exceptions import LLMError
from server.memory import continuity
from server.memory.candidate_dialogue import PendingOffer
from server.memory.continuity import ContinuityTurn
from server.memory.pending_follow_up import PendingFollowUp
from server.settings import settings

from server import text_turn

if TYPE_CHECKING:
    import httpx

pytestmark = pytest.mark.unit

_OWNER = 7
_SENTENCE = "¿Cómo te fue ayer con el banco?"
_OFFER = "Antes me dijiste que te gusta el mate."


def _face_owner() -> ActivePersonContext:
    at = datetime(2026, 11, 12, tzinfo=UTC)
    confidence = Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=True)
    return ActivePersonContext(
        person_id=_OWNER,
        display_name="Canary",
        status=ActivePersonStatus.IDENTIFIED,
        confidence=confidence,
        role=HouseholdRole.OWNER,
        evidence=(
            IdentityEvidence(
                evidence_id=UUID(int=3),
                source=IdentityEvidenceSource.FACE,
                candidate_person_id=_OWNER,
                confidence=confidence,
                observed_at=at,
                reference="in-turn-face-evidence",
            ),
        ),
        resolved_at=at,
        assurance=IdentityAssurance.BASIC,
    )


def _follow_up() -> PendingFollowUp:
    return PendingFollowUp(
        topic_id=3,
        sentence=_SENTENCE,
        actor=_face_owner(),
        correlation_id=UUID(int=84),
        sensitivity="normal",
        consent=ConsentStatus.NOT_REQUIRED,
    )


@pytest.fixture
def commit(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Memory, the record and the pending topics on; the commit is a spy."""
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "conversation_record_enabled", True)
    monkeypatch.setattr(settings, "pending_topics_enabled", True)
    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
    spy = AsyncMock(return_value=_SENTENCE)
    monkeypatch.setattr(text_turn, "commit_follow_up", spy)
    return spy


def _generate(monkeypatch: pytest.MonkeyPatch, reply: str | Exception = "Hola.") -> None:
    mock = (
        AsyncMock(side_effect=reply)
        if isinstance(reply, Exception)
        else AsyncMock(return_value=(reply, "neutral"))
    )
    monkeypatch.setattr(text_turn.llm, "generate_response", mock)


async def _turn(
    client: httpx.AsyncClient,
    prepare: AsyncMock | None,
    *,
    record: Mock | None = None,
    prepare_offer: AsyncMock | None = None,
) -> text_turn.TextTurnResult:
    return await text_turn.process_text_turn(
        client,
        "hola",
        "voice",
        active_person=_face_owner(),
        prepare_offer=prepare_offer,
        prepare_follow_up=prepare,
        record_turn=record,
    )


def _session() -> list[str]:
    return [turn.content for turn in continuity.open_turn(_OWNER).history]


async def test_the_follow_up_is_said_after_the_reply_and_joins_the_session(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, commit: AsyncMock
) -> None:
    _generate(monkeypatch)
    prepare = AsyncMock(return_value=_follow_up())
    record = Mock()

    result = await _turn(http_client, prepare, record=record)

    assert result.response == "Hola."
    assert result.follow_up == _SENTENCE
    assert result.offer is None
    assert result.spoken_after == _SENTENCE
    assert prepare.await_args is not None
    actor, session = prepare.await_args.args
    assert actor.person_id == _OWNER
    assert session == ContinuityTurn((), _OWNER, session.generation)
    commit.assert_awaited_once()
    # The record keeps the reply only (D-12); the session the reply and the question.
    record.assert_called_once_with("hola", "Hola.", actor)
    assert _session() == ["hola", f"Hola. {_SENTENCE}"]


async def test_an_open_offer_wins_and_the_topic_waits(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    commit: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    monkeypatch.setattr(text_turn, "commit_offer", AsyncMock(return_value=_OFFER))
    offer = PendingOffer(
        candidate_id=1,
        subject_person_id=_OWNER,
        phrase=_OFFER,
        actor=_face_owner(),
        correlation_id=UUID(int=1),
    )
    _generate(monkeypatch)

    result = await _turn(
        http_client,
        AsyncMock(return_value=_follow_up()),
        prepare_offer=AsyncMock(return_value=offer),
    )

    assert result.offer == _OFFER
    assert result.follow_up is None
    assert result.spoken_after == _OFFER
    commit.assert_not_awaited()
    assert _session() == ["hola", "Hola."]
    assert [
        r.__dict__.get("outcome")
        for r in caplog.records
        if r.__dict__.get("event") == "pending.follow_up"
    ] == ["offer_won"]
    assert "banco" not in caplog.text


async def test_a_fallback_reply_carries_no_follow_up(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, commit: AsyncMock
) -> None:
    _generate(monkeypatch, LLMError("down"))

    result = await _turn(http_client, AsyncMock(return_value=_follow_up()))

    assert result.llm_failed
    assert result.follow_up is None
    commit.assert_not_awaited()


async def test_a_refused_commit_says_nothing_and_the_session_keeps_the_reply(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, commit: AsyncMock
) -> None:
    commit.return_value = None
    _generate(monkeypatch)

    result = await _turn(http_client, AsyncMock(return_value=_follow_up()))

    assert result.follow_up is None
    assert result.spoken_after is None
    assert _session() == ["hola", "Hola."]


async def test_nothing_prepared_commits_nothing(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, commit: AsyncMock
) -> None:
    _generate(monkeypatch)
    result = await _turn(http_client, AsyncMock(return_value=None))
    assert result.follow_up is None
    commit.assert_not_awaited()


@pytest.mark.parametrize(
    "switch", ["pending_topics_enabled", "conversation_record_enabled", "memory_enabled"]
)
async def test_switch_off_prepares_nothing_and_the_result_is_todays(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    commit: AsyncMock,
    switch: str,
) -> None:
    monkeypatch.setattr(settings, switch, False)
    _generate(monkeypatch)
    prepare = AsyncMock(return_value=_follow_up())

    result = await _turn(http_client, prepare)

    prepare.assert_not_awaited()
    commit.assert_not_awaited()
    assert result == text_turn.TextTurnResult(
        result.response, result.emotion, result.duration_ms, result.llm_failed
    )


async def test_a_cancelled_turn_cancels_the_follow_up_it_was_preparing(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, commit: AsyncMock
) -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def prepare(_actor: object, _session: object) -> PendingFollowUp:
        started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return _follow_up()

    async def generate(*_args: object, **_kwargs: object) -> tuple[str, str]:
        await started.wait()
        raise asyncio.CancelledError

    monkeypatch.setattr(text_turn.llm, "generate_response", generate)

    with pytest.raises(asyncio.CancelledError):
        await _turn(http_client, prepare)  # type: ignore[arg-type]  # a plain coroutine double
    await asyncio.wait_for(cancelled.wait(), timeout=1)
    commit.assert_not_awaited()


def test_the_follow_up_never_shows_in_the_repr_of_a_turn_result() -> None:
    result = text_turn.TextTurnResult("Hola.", "neutral", 1, False, None, _SENTENCE)
    assert "banco" not in repr(result)
