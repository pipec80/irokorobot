"""The spoken memory offer on the streaming route (ADR 0021 decision 9, Plan 0063).

The offer is one more ``audio`` event after the reply's sentences and before ``done``, with
empty text: the robot plays it and prints nothing, and it never reaches ``log_spoken``, the
session history or the ``llm_ms`` accounting.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
import time
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityAssurance,
    IdentityEvidence,
    IdentityEvidenceSource,
)
from server.cognition.models import Confidence, ConfidenceBasis
from server.exceptions import LLMError, TTSError
from server.memory.candidate_dialogue import OfferPreparer, PendingOffer
from server.memory.continuity import ContinuityTurn
from server.settings import settings
from server.text_turn import PreparedTextTurn

from server import llm_streaming, streaming, streaming_render, text_turn, tts

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator

    import httpx

pytestmark = pytest.mark.integration

_OFFER = "Antes me dijiste que te gusta el mate."
_REPLY = "Hola, qué gusto."


def _face_owner() -> ActivePersonContext:
    resolved_at = datetime(2026, 10, 15, tzinfo=UTC)
    confidence = Confidence(
        score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=True, reason="In-turn face match"
    )
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
                observed_at=resolved_at,
                reference="in-turn-face-evidence",
            ),
        ),
        resolved_at=resolved_at,
        assurance=IdentityAssurance.BASIC,
    )


def _prepared() -> PreparedTextTurn:
    return PreparedTextTurn(
        "hola", "interaction:canary", [], None, None, _face_owner(), ContinuityTurn((), 7, 0)
    )


def _pending() -> PendingOffer:
    return PendingOffer(
        candidate_id=1,
        subject_person_id=7,
        phrase=_OFFER,
        actor=_face_owner(),
        correlation_id=UUID(int=1),
    )


@pytest.fixture
def stream_on(monkeypatch: pytest.MonkeyPatch) -> dict[str, Mock | AsyncMock]:
    """Memory and candidates on, a scripted model, a spy TTS and a spy commit."""
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)

    async def generate_stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        yield _REPLY

    monkeypatch.setattr(llm_streaming, "generate_response_stream", generate_stream)
    synthesize = AsyncMock(side_effect=[("UkVQTFk=", 30), ("T0ZGRVI=", 70)])
    monkeypatch.setattr(tts, "synthesize", synthesize)
    commit = AsyncMock(return_value=_OFFER)
    monkeypatch.setattr(text_turn, "commit_offer", commit)
    spoken = Mock()
    monkeypatch.setattr(streaming_render, "log_spoken", spoken)
    monkeypatch.setattr(streaming, "log_spoken", spoken)
    record = Mock()
    monkeypatch.setattr(streaming, "record_text_turn", record)
    return {"synthesize": synthesize, "commit": commit, "spoken": spoken, "record": record}


async def _events(
    client: httpx.AsyncClient, prepare_offer: OfferPreparer | None
) -> list[dict[str, object]]:
    return [
        json.loads(line)
        async for line in streaming.stream_pipeline(
            client=client,
            prepared=_prepared(),
            stt_ms=0,
            request_start=time.perf_counter(),
            schedule_proposal=lambda _message, _actor: None,
            prepare_offer=prepare_offer,
        )
    ]


async def test_the_offer_is_one_more_audio_event_after_the_reply_with_no_text(
    http_client: httpx.AsyncClient, stream_on: dict[str, Mock | AsyncMock]
) -> None:
    events = await _events(http_client, AsyncMock(return_value=_pending()))

    assert [event["type"] for event in events] == [
        "text_heard",
        "emotion",
        "audio",
        "audio",
        "done",
    ]
    assert events[2]["text"] == _REPLY
    assert events[3] == {"type": "audio", "text": "", "audio_base64": "T0ZGRVI=", "duration_ms": 70}
    assert stream_on["synthesize"].await_args_list[-1].args == (_OFFER,)


async def test_done_expects_a_short_reply_after_a_spoken_offer(
    http_client: httpx.AsyncClient, stream_on: dict[str, Mock | AsyncMock]
) -> None:
    events = await _events(http_client, AsyncMock(return_value=_pending()))

    assert events[-1]["type"] == "done"
    assert events[-1]["expects_short_reply"] is True


async def test_done_expects_nothing_without_an_offer(
    http_client: httpx.AsyncClient, stream_on: dict[str, Mock | AsyncMock]
) -> None:
    events = await _events(http_client, None)

    assert events[-1]["type"] == "done"
    assert events[-1]["expects_short_reply"] is False


async def test_done_expects_nothing_when_the_offer_audio_failed(
    http_client: httpx.AsyncClient, stream_on: dict[str, Mock | AsyncMock]
) -> None:
    """The offer is committed but its synthesis raises: no offer event, so no reply is expected."""
    stream_on["synthesize"].side_effect = [("UkVQTFk=", 30), TTSError("piper down")]

    events = await _events(http_client, AsyncMock(return_value=_pending()))

    stream_on["commit"].assert_awaited_once()
    assert [event["type"] for event in events] == ["text_heard", "emotion", "audio", "done"]
    assert events[-1]["expects_short_reply"] is False


async def test_the_offer_never_reaches_the_spoken_log_nor_the_session(
    http_client: httpx.AsyncClient, stream_on: dict[str, Mock | AsyncMock]
) -> None:
    await _events(http_client, AsyncMock(return_value=_pending()))

    assert [call.args[0] for call in stream_on["spoken"].call_args_list] == [_REPLY]
    record_call = stream_on["record"].call_args
    assert record_call is not None
    assert record_call.args[1] == _REPLY


async def test_the_offer_synthesis_is_tts_time_not_model_time(
    http_client: httpx.AsyncClient, stream_on: dict[str, Mock | AsyncMock]
) -> None:
    async def synthesize(text: str) -> tuple[str, int]:
        if text != _OFFER:
            return "UkVQTFk=", 30
        await asyncio.sleep(0.3)  # the offer's synthesis really takes this long
        return "T0ZGRVI=", 300

    stream_on["synthesize"].side_effect = synthesize

    events = await _events(http_client, AsyncMock(return_value=_pending()))

    done = events[-1]
    assert done["tts_ms"] == 330
    llm_ms = done["llm_ms"]
    assert isinstance(llm_ms, int)
    assert llm_ms < 100  # the 300 ms of the offer's synthesis is TTS time, not the model's


async def test_a_fallback_reply_carries_no_offer(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    stream_on: dict[str, Mock | AsyncMock],
) -> None:
    async def broken(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        raise LLMError("down")
        yield ""  # pragma: no cover — makes this an async generator

    monkeypatch.setattr(llm_streaming, "generate_response_stream", broken)
    stream_on["synthesize"].side_effect = None
    stream_on["synthesize"].return_value = ("RkFMTA==", 20)

    events = await _events(http_client, AsyncMock(return_value=_pending()))

    assert [event["type"] for event in events].count("audio") == 1
    stream_on["commit"].assert_not_awaited()


async def test_a_reply_that_fails_after_its_first_sentence_carries_no_offer(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    stream_on: dict[str, Mock | AsyncMock],
) -> None:
    """PARTIAL_FALLBACK: a sentence was already spoken, then the model failed."""

    async def broken_midway(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        yield f"{_REPLY} Y luego"
        raise LLMError("down")

    monkeypatch.setattr(llm_streaming, "generate_response_stream", broken_midway)
    stream_on["synthesize"].side_effect = [("UkVQTFk=", 30), ("RkFMTA==", 20)]

    events = await _events(http_client, AsyncMock(return_value=_pending()))

    audio = [event for event in events if event["type"] == "audio"]
    assert [event["text"] for event in audio] == [_REPLY, settings.llm_fallback_phrase]
    assert [event["type"] for event in events][-1] == "done"
    assert [call.args for call in stream_on["synthesize"].await_args_list] == [
        (_REPLY,),
        (settings.llm_fallback_phrase,),
    ]
    stream_on["commit"].assert_not_awaited()
    assert [call.args[0] for call in stream_on["spoken"].call_args_list] == [
        _REPLY,
        settings.llm_fallback_phrase,
    ]
    stream_on["record"].assert_not_called()


@pytest.mark.parametrize(
    "deltas",
    [["{ no es texto"], [f"{_REPLY} ", "Luego EMOTION: joy."]],
    ids=["invalid-start", "tag-after-a-spoken-sentence"],
)
async def test_a_reply_that_breaks_the_protocol_carries_no_offer(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    stream_on: dict[str, Mock | AsyncMock],
    deltas: list[str],
) -> None:
    """PROTOCOL_FALLBACK, before and after a sentence was spoken: no offer, no commit."""

    async def generate_stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        for delta in deltas:
            yield delta

    monkeypatch.setattr(llm_streaming, "generate_response_stream", generate_stream)
    stream_on["synthesize"].side_effect = None
    stream_on["synthesize"].return_value = ("RkFMTA==", 20)

    events = await _events(http_client, AsyncMock(return_value=_pending()))

    texts = [event["text"] for event in events if event["type"] == "audio"]
    assert texts[-1] == settings.llm_fallback_phrase
    assert "" not in texts  # no silent offer event
    assert _OFFER not in [call.args[0] for call in stream_on["synthesize"].await_args_list]
    assert events[-1]["type"] == "done"
    stream_on["commit"].assert_not_awaited()
    stream_on["record"].assert_not_called()


async def test_an_offer_that_fails_to_synthesize_is_skipped_and_the_turn_still_ends_done(
    http_client: httpx.AsyncClient, stream_on: dict[str, Mock | AsyncMock]
) -> None:
    stream_on["synthesize"].side_effect = [("UkVQTFk=", 30), TTSError("piper down")]

    events = await _events(http_client, AsyncMock(return_value=_pending()))

    assert [event["type"] for event in events] == ["text_heard", "emotion", "audio", "done"]


async def test_no_preparation_means_the_stream_is_unchanged(
    http_client: httpx.AsyncClient, stream_on: dict[str, Mock | AsyncMock]
) -> None:
    events = await _events(http_client, None)

    assert [event["type"] for event in events] == ["text_heard", "emotion", "audio", "done"]
    stream_on["commit"].assert_not_awaited()


async def test_the_offer_is_prepared_while_the_model_streams(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    stream_on: dict[str, Mock | AsyncMock],
) -> None:
    """The model waits for the preparation to start: a sequential seam would deadlock."""
    prepared = asyncio.Event()

    async def generate_stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        await asyncio.wait_for(prepared.wait(), timeout=2)
        yield _REPLY

    async def prepare(_actor: ActivePersonContext) -> PendingOffer:
        prepared.set()
        return _pending()

    monkeypatch.setattr(llm_streaming, "generate_response_stream", generate_stream)

    events = await _events(http_client, prepare)

    assert [event["type"] for event in events][-2:] == ["audio", "done"]
    stream_on["commit"].assert_awaited_once()


async def test_a_reply_that_fails_to_synthesize_commits_no_offer(
    http_client: httpx.AsyncClient, stream_on: dict[str, Mock | AsyncMock]
) -> None:
    stream_on["synthesize"].side_effect = TTSError("piper down")

    with pytest.raises(TTSError):
        await _events(http_client, AsyncMock(return_value=_pending()))

    stream_on["commit"].assert_not_awaited()


async def test_committing_the_offer_never_counts_as_model_time(
    http_client: httpx.AsyncClient, stream_on: dict[str, Mock | AsyncMock]
) -> None:
    """The commit is audit and a compare-and-set: 0.5 s of it must not show up as model time."""

    async def slow_commit(_pending: PendingOffer) -> str:
        await asyncio.sleep(0.5)
        return _OFFER

    stream_on["commit"].side_effect = slow_commit
    # Both syntheses report 0 ms, so the whole half second can only be the commit's.
    stream_on["synthesize"].side_effect = [("UkVQTFk=", 0), ("T0ZGRVI=", 0)]

    events = await _events(http_client, AsyncMock(return_value=_pending()))

    done = events[-1]
    assert done["type"] == "done"
    assert done["tts_ms"] == 0
    total_ms = done["total_ms"]
    llm_ms = done["llm_ms"]
    assert isinstance(total_ms, int)
    assert isinstance(llm_ms, int)
    assert total_ms >= 500  # the commit really ran inside the measured turn
    assert llm_ms < 100


async def test_a_client_that_hangs_up_cancels_the_preparation(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    stream_on: dict[str, Mock | AsyncMock],
) -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def prepare(_actor: ActivePersonContext) -> PendingOffer:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return _pending()

    stream = cast(
        "AsyncGenerator[str, None]",
        streaming.stream_pipeline(
            client=http_client,
            prepared=_prepared(),
            stt_ms=0,
            request_start=time.perf_counter(),
            schedule_proposal=lambda _message, _actor: None,
            prepare_offer=prepare,
        ),
    )
    await anext(stream)  # text_heard, before the preparation starts
    await anext(stream)  # the model is streaming and the preparation is running
    await asyncio.wait_for(started.wait(), timeout=2)

    await stream.aclose()

    await asyncio.wait_for(cancelled.wait(), timeout=2)


async def test_any_failure_of_the_offer_synthesis_is_skipped_not_fatal(
    http_client: httpx.AsyncClient, stream_on: dict[str, Mock | AsyncMock]
) -> None:
    """The reply was already spoken: a closed executor or a disk error must not end it in error."""
    stream_on["synthesize"].side_effect = [("UkVQTFk=", 30), RuntimeError("executor shut down")]

    events = await _events(http_client, AsyncMock(return_value=_pending()))

    assert [event["type"] for event in events] == ["text_heard", "emotion", "audio", "done"]
