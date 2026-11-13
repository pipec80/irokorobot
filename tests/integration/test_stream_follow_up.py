"""The pending-topic follow-up on the streaming route (Plan 0084 Task 5, D-11 and D-12).

Like the memory offer, it is one more ``audio`` event with empty text after the reply's
sentences and before ``done``; it never reaches ``log_spoken`` and ``done`` gains no field. The
session keeps it beside the reply; an offer on the same turn wins.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import time
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
from server.memory.candidate_dialogue import PendingOffer
from server.memory.continuity import ContinuityTurn
from server.memory.pending_follow_up import PendingFollowUp
from server.settings import settings
from server.text_turn import PreparedTextTurn

from server import llm_streaming, streaming, streaming_render, text_turn, tts

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx

pytestmark = pytest.mark.integration

_REPLY = "Hola, qué gusto."
_SENTENCE = "¿Cómo te fue ayer con el banco?"
_OFFER = "Antes me dijiste que te gusta el mate."


def _face_owner() -> ActivePersonContext:
    at = datetime(2026, 11, 12, tzinfo=UTC)
    confidence = Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=True)
    return ActivePersonContext(
        person_id=7,
        display_name="Canary",
        status=ActivePersonStatus.IDENTIFIED,
        confidence=confidence,
        role=HouseholdRole.OWNER,
        evidence=(
            IdentityEvidence(
                evidence_id=UUID(int=3),
                source=IdentityEvidenceSource.FACE,
                candidate_person_id=7,
                confidence=confidence,
                observed_at=at,
                reference="in-turn-face-evidence",
            ),
        ),
        resolved_at=at,
        assurance=IdentityAssurance.BASIC,
    )


def _prepared() -> PreparedTextTurn:
    return PreparedTextTurn(
        "hola", "interaction:canary", [], None, None, _face_owner(), ContinuityTurn((), 7, 0)
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
def stream_on(monkeypatch: pytest.MonkeyPatch) -> dict[str, Mock | AsyncMock]:
    """Memory, the record and the topics on, a scripted model, spy TTS, commits and session."""
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "conversation_record_enabled", True)
    monkeypatch.setattr(settings, "pending_topics_enabled", True)
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)

    async def generate_stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        yield _REPLY

    monkeypatch.setattr(llm_streaming, "generate_response_stream", generate_stream)
    synthesize = AsyncMock(side_effect=[("UkVQTFk=", 30), ("Rk9MTE9X", 60)])
    monkeypatch.setattr(tts, "synthesize", synthesize)
    commit = AsyncMock(return_value=_SENTENCE)
    monkeypatch.setattr(text_turn, "commit_follow_up", commit)
    monkeypatch.setattr(text_turn, "commit_offer", AsyncMock(return_value=_OFFER))
    spoken = Mock()
    monkeypatch.setattr(streaming_render, "log_spoken", spoken)
    monkeypatch.setattr(streaming, "log_spoken", spoken)
    record = Mock()
    monkeypatch.setattr(streaming, "record_text_turn", record)
    return {"synthesize": synthesize, "commit": commit, "spoken": spoken, "record": record}


async def _events(
    client: httpx.AsyncClient,
    *,
    follow_up: PendingFollowUp | None,
    offer: PendingOffer | None = None,
    recorder: Mock | None = None,
) -> list[dict[str, object]]:
    return [
        json.loads(line)
        async for line in streaming.stream_pipeline(
            client=client,
            prepared=_prepared(),
            stt_ms=0,
            request_start=time.perf_counter(),
            schedule_proposal=lambda _message, _actor: None,
            prepare_offer=AsyncMock(return_value=offer),
            record_turn=recorder,
            prepare_follow_up=AsyncMock(return_value=follow_up),
        )
    ]


async def test_the_follow_up_is_one_more_audio_event_and_joins_the_session(
    http_client: httpx.AsyncClient, stream_on: dict[str, Mock | AsyncMock]
) -> None:
    recorder = Mock()
    events = await _events(http_client, follow_up=_follow_up(), recorder=recorder)

    assert [event["type"] for event in events] == [
        "text_heard",
        "emotion",
        "audio",
        "audio",
        "done",
    ]
    assert events[3] == {"type": "audio", "text": "", "audio_base64": "Rk9MTE9X", "duration_ms": 60}
    assert stream_on["synthesize"].await_args_list[1].args == (_SENTENCE,)
    assert set(events[4]) == set(
        json.loads(
            streaming_render.StreamDoneEvent(
                stt_ms=0, llm_ms=0, tts_ms=0, total_ms=0
            ).model_dump_json()
        )
    )
    stream_on["record"].assert_called_once()
    assert stream_on["record"].call_args.args[1] == f"{_REPLY} {_SENTENCE}"
    recorder.assert_called_once_with("hola", _REPLY, _prepared().active_person)
    assert all(_SENTENCE not in str(call) for call in stream_on["spoken"].call_args_list)


async def test_an_offer_wins_on_the_stream(
    http_client: httpx.AsyncClient, stream_on: dict[str, Mock | AsyncMock]
) -> None:
    offer = PendingOffer(
        candidate_id=1,
        subject_person_id=7,
        phrase=_OFFER,
        actor=_face_owner(),
        correlation_id=UUID(int=1),
    )
    events = await _events(http_client, follow_up=_follow_up(), offer=offer)

    assert stream_on["synthesize"].await_args_list[1].args == (_OFFER,)
    assert [event["type"] for event in events].count("audio") == 2
    stream_on["commit"].assert_not_awaited()
    assert stream_on["record"].call_args.args[1] == _REPLY


async def test_nothing_prepared_is_todays_stream(
    http_client: httpx.AsyncClient, stream_on: dict[str, Mock | AsyncMock]
) -> None:
    events = await _events(http_client, follow_up=None)

    assert [event["type"] for event in events] == ["text_heard", "emotion", "audio", "done"]
    assert stream_on["record"].call_args.args[1] == _REPLY


async def test_a_failed_stream_carries_no_follow_up(
    http_client: httpx.AsyncClient,
    stream_on: dict[str, Mock | AsyncMock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        raise LLMError("down")
        yield ""  # pragma: no cover  # makes this an async generator

    monkeypatch.setattr(llm_streaming, "generate_response_stream", failing)
    stream_on["synthesize"].side_effect = [("RkFMTA==", 30)]

    events = await _events(http_client, follow_up=_follow_up())

    assert [event["type"] for event in events].count("audio") == 1
    stream_on["commit"].assert_not_awaited()
    stream_on["record"].assert_not_called()
