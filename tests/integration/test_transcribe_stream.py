"""Integration tests for POST /transcribe/stream."""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
import json
import logging
import time
from unittest.mock import AsyncMock, Mock
from uuid import UUID

from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
import httpx
import pytest
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityEvidence,
    IdentityEvidenceSource,
)
from server.cognition.models import Confidence, ConfidenceBasis
from server.exceptions import LLMError, TTSError
from server.routers import transcribe as transcribe_module
from server.schemas import ConversationTurn
from server.settings import settings
from server.text_turn import PreparedTextTurn

from server import llm, llm_streaming, pipeline, streaming, stt, tts


def _manual_active_person() -> ActivePersonContext:
    """Create explicit manual identity evidence for shared-stream tests."""
    resolved_at = datetime(2026, 8, 10, tzinfo=UTC)
    confidence = Confidence(
        score=1.0,
        basis=ConfidenceBasis.ASSERTED,
        calibrated=True,
        reason="Explicit local selection",
    )
    return ActivePersonContext(
        person_id=7,
        display_name="Sofía",
        status=ActivePersonStatus.IDENTIFIED,
        confidence=confidence,
        role=HouseholdRole.UNKNOWN,
        evidence=(
            IdentityEvidence(
                evidence_id=UUID("11111111-1111-1111-1111-111111111111"),
                source=IdentityEvidenceSource.MANUAL,
                candidate_person_id=7,
                confidence=confidence,
                observed_at=resolved_at,
                reference="trusted-local-adapter",
            ),
        ),
        resolved_at=resolved_at,
    )


@pytest.fixture(autouse=True)
def _mock_stt_and_tts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default: successful STT/TTS with canned answers; LLM set per test."""
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value="hola robot"))
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("QQ==", 10)))

    async def local_stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        yield "EMOTION:joy\nHola. ¿Cómo estás?"

    monkeypatch.setattr(llm_streaming, "generate_response_stream", local_stream)


def _post_stream(client: TestClient, audio: bytes) -> httpx.Response:
    """Post one WAV 16kHz, mono, int16 stream request."""
    return client.post(
        "/transcribe/stream",
        files={"audio": ("a.wav", audio, "audio/wav")},
    )


def _parse_ndjson(text: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in text.strip().split("\n") if line.strip()]


def _post_stream_with_deltas(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    audio: bytes,
    deltas: list[str],
) -> list[dict[str, object]]:
    """Feed fixed LLM stream deltas through one live POST /transcribe/stream call."""

    async def fake_generate(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        for delta in deltas:
            yield delta

    monkeypatch.setattr(llm_streaming, "generate_response_stream", fake_generate)
    response = _post_stream(client, audio)
    assert response.status_code == 200
    return _parse_ndjson(response.text)


def _is_nonnegative_int(value: object) -> bool:
    """Return whether one untyped NDJSON value is a valid timing value."""
    return isinstance(value, int) and value >= 0


@pytest.mark.integration
def test_stream_happy_path_emits_sentence_audio(
    client: TestClient, silence_wav_bytes: bytes
) -> None:
    """The local stream emits one audio event for each completed sentence."""
    response = _post_stream(client, silence_wav_bytes)
    assert response.status_code == 200
    events = _parse_ndjson(response.text)

    assert events[0] == {"type": "text_heard", "value": "hola robot"}
    assert events[1] == {"type": "emotion", "value": "joy"}
    audio_events = [e for e in events if e["type"] == "audio"]
    assert [e["text"] for e in audio_events] == ["Hola.", "¿Cómo estás?"]
    assert all(e["audio_base64"] == "QQ==" for e in audio_events)
    assert events[-1]["type"] == "done"
    for field in ("stt_ms", "llm_ms", "tts_ms", "total_ms"):
        duration = events[-1][field]
        assert isinstance(duration, (int, float))
        assert duration >= 0


@pytest.mark.integration
def test_stream_prepares_shared_voice_turn(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Streaming keeps one fresh internal scope for preparation and recording."""
    scope = "interaction:stream-request"
    prepared = PreparedTextTurn(
        "hola robot",
        scope,
        None,
        None,
        False,
        None,
        None,
        None,
    )
    prepare = AsyncMock(return_value=prepared)
    record = Mock()
    new_scope = Mock(return_value=scope)
    monkeypatch.setattr(transcribe_module, "new_interaction_scope", new_scope, raising=False)
    monkeypatch.setattr(transcribe_module, "prepare_text_turn", prepare)
    monkeypatch.setattr(streaming, "record_text_turn", record)

    response = _post_stream(client, silence_wav_bytes)

    assert response.status_code == 200
    new_scope.assert_called_once_with()
    prepare.assert_awaited_once_with("hola robot", scope)
    assert record.call_args.args == (
        "hola robot",
        scope,
        "Hola. ¿Cómo estás?",
        "joy",
    )
    assert callable(record.call_args.kwargs["schedule_consolidation"])


@pytest.mark.integration
def test_stream_answers_current_date_without_legacy_generation(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deterministic stream response must bypass prompt preparation and LLM output."""
    prepared = PreparedTextTurn(
        "¿Qué fecha es hoy?", "interaction:date", None, None, False, None, None, None
    )
    prepare = AsyncMock(return_value=prepared)
    record = Mock()

    async def legacy_stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        yield "EMOTION:joy\nRespuesta legacy."

    llm_stream = Mock(side_effect=legacy_stream)
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value="¿Qué fecha es hoy?"))
    synthesize = AsyncMock(return_value=("AAAA", 42))
    monkeypatch.setattr(transcribe_module, "_today", lambda: date(2026, 8, 12))
    monkeypatch.setattr(transcribe_module, "prepare_text_turn", prepare)
    monkeypatch.setattr(llm_streaming, "generate_response_stream", llm_stream)
    monkeypatch.setattr(streaming, "record_text_turn", record)
    monkeypatch.setattr(tts, "synthesize", synthesize)

    response = _post_stream(client, silence_wav_bytes)

    assert response.status_code == 200
    events = _parse_ndjson(response.text)
    assert events[0] == {"type": "text_heard", "value": "¿Qué fecha es hoy?"}
    assert events[1] == {"type": "emotion", "value": "neutral"}
    assert events[2]["type"] == "audio"
    assert events[2]["text"] == "Hoy es 2026-08-12."
    assert [event["type"] for event in events] == ["text_heard", "emotion", "audio", "done"]
    timings = events[-1]
    assert all(
        _is_nonnegative_int(timings[field]) for field in ("stt_ms", "llm_ms", "tts_ms", "total_ms")
    )
    assert events[-1]["type"] == "done"
    synthesize.assert_awaited_once_with("Hoy es 2026-08-12.")
    prepare.assert_not_awaited()
    llm_stream.assert_not_called()
    record.assert_not_called()


@pytest.mark.integration
def test_stream_denies_private_household_request_before_legacy_generation(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A public stream must audit and deny protected data before generation."""
    prepared = PreparedTextTurn(
        "¿Cómo se llaman mis hijos?", "interaction:private", None, None, False, None, None, None
    )
    prepare = AsyncMock(return_value=prepared)
    record = Mock()

    async def legacy_stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        yield "EMOTION:joy\nRespuesta legacy."

    llm_stream = Mock(side_effect=legacy_stream)
    audit = AsyncMock()
    synthesize = AsyncMock(return_value=("AAAA", 42))
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value="¿Cómo se llaman mis hijos?"))
    monkeypatch.setattr(transcribe_module, "prepare_text_turn", prepare)
    monkeypatch.setattr(transcribe_module, "record_authorization_decision", audit)
    monkeypatch.setattr(llm_streaming, "generate_response_stream", llm_stream)
    monkeypatch.setattr(streaming, "record_text_turn", record)
    monkeypatch.setattr(tts, "synthesize", synthesize)

    response = _post_stream(client, silence_wav_bytes)

    assert response.status_code == 200
    events = _parse_ndjson(response.text)
    assert events[0] == {"type": "text_heard", "value": "¿Cómo se llaman mis hijos?"}
    assert events[1] == {"type": "emotion", "value": "neutral"}
    assert events[2]["type"] == "audio"
    assert "información familiar privada" in str(events[2]["text"])
    assert [event["type"] for event in events] == ["text_heard", "emotion", "audio", "done"]
    timings = events[-1]
    assert all(
        _is_nonnegative_int(timings[field]) for field in ("stt_ms", "llm_ms", "tts_ms", "total_ms")
    )
    assert events[-1]["type"] == "done"
    synthesize.assert_awaited_once_with(str(events[2]["text"]))
    audit.assert_awaited_once()
    audit_call = audit.await_args
    assert audit_call is not None
    request, decision = audit_call.args
    assert request.actor.person_id is None
    assert request.target_person_id is None
    assert "Máximo" not in repr((request, decision))
    assert "Sofía" not in repr((request, decision))
    prepare.assert_not_awaited()
    llm_stream.assert_not_called()
    record.assert_not_called()


@pytest.mark.integration
def test_unresolved_stream_does_not_load_entity_hotwords(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unresolved stream must not query persistent names before STT."""
    list_names = AsyncMock(return_value=["Sofía"])
    stt_mock = AsyncMock(return_value="hola robot")
    monkeypatch.setattr(pipeline, "list_entity_names", list_names)
    monkeypatch.setattr(stt, "transcribe", stt_mock)
    monkeypatch.setattr(settings, "memory_enabled", True)

    response = _post_stream(client, silence_wav_bytes)

    assert response.status_code == 200
    list_names.assert_not_awaited()
    assert stt_mock.await_args_list[-1].kwargs["extra_hotwords"] == []


@pytest.mark.integration
def test_stream_happy_path_ollama_streams_multiple_deltas(
    client: TestClient, silence_wav_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        for delta in ("EMOTION:joy\n", "Hola. ", "¿Cómo estás?"):
            yield delta

    monkeypatch.setattr(llm_streaming, "generate_response_stream", fake_stream)
    response = _post_stream(client, silence_wav_bytes)
    assert response.status_code == 200
    events = _parse_ndjson(response.text)

    assert events[0] == {"type": "text_heard", "value": "hola robot"}
    assert events[1] == {"type": "emotion", "value": "joy"}
    audio_events = [e for e in events if e["type"] == "audio"]
    assert [e["text"] for e in audio_events] == ["Hola.", "¿Cómo estás?"]
    assert events[-1]["type"] == "done"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stream_uses_local_deltas_after_invalid_runtime_provider_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Streaming must stay local even when a caller corrupts the provider field."""
    prepared = PreparedTextTurn("hola", "public-turn", None, None, False, None, None, None)

    async def local_stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        yield "EMOTION:joy\nHola."

    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(llm_streaming, "generate_response_stream", local_stream)
    monkeypatch.delattr(llm, "generate_response")

    deltas = [delta async for delta in streaming._text_deltas(prepared)]

    assert deltas == ["EMOTION:joy\nHola."]


def _assert_audible_protocol_fallback(events: list[dict[str, object]]) -> None:
    """Assert the mandatory P0-C6 fallback shape shared by every invalid-output test."""
    assert [event["type"] for event in events] == ["text_heard", "emotion", "audio", "done"]
    assert events[1]["value"] == "neutral"
    assert events[2]["text"] == settings.llm_fallback_phrase
    duration = events[2]["duration_ms"]
    assert isinstance(duration, int)
    assert duration > 0
    done = events[-1]
    tts_ms = done["tts_ms"]
    assert isinstance(tts_ms, int)
    assert tts_ms > 0


@pytest.mark.integration
def test_stream_hybrid_json_uses_audible_protocol_fallback(
    client: TestClient, silence_wav_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The observed 2026-08-17 hybrid output must speak fallback, never silence."""
    deltas = ['EMOTION: joy {"response": "¡Qué emocionante!", "emotion": "joy"}']
    record = Mock()
    monkeypatch.setattr(streaming, "record_text_turn", record)
    events = _post_stream_with_deltas(client, monkeypatch, silence_wav_bytes, deltas)
    _assert_audible_protocol_fallback(events)
    tts.synthesize.assert_awaited_once_with(settings.llm_fallback_phrase)
    record.assert_not_called()


@pytest.mark.integration
def test_stream_structured_body_uses_audible_protocol_fallback(
    client: TestClient, silence_wav_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A valid emotion line followed by a JSON body is still invalid output."""
    deltas = ['EMOTION:joy\n{"response": "hola"}']
    record = Mock()
    monkeypatch.setattr(streaming, "record_text_turn", record)
    events = _post_stream_with_deltas(client, monkeypatch, silence_wav_bytes, deltas)
    _assert_audible_protocol_fallback(events)
    tts.synthesize.assert_awaited_once_with(settings.llm_fallback_phrase)
    record.assert_not_called()


@pytest.mark.integration
def test_stream_truncated_emotion_uses_audible_protocol_fallback(
    client: TestClient, silence_wav_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stream ends mid tag ("EMOTION:ale", no \\n) — spoken as fallback, never silence."""
    record = Mock()
    monkeypatch.setattr(streaming, "record_text_turn", record)
    events = _post_stream_with_deltas(client, monkeypatch, silence_wav_bytes, ["EMOTION:ale"])
    _assert_audible_protocol_fallback(events)
    tts.synthesize.assert_awaited_once_with(settings.llm_fallback_phrase)
    record.assert_not_called()


@pytest.mark.integration
def test_stream_empty_model_output_uses_audible_protocol_fallback(
    client: TestClient, silence_wav_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The model producing nothing at all must still end audibly, not silently."""
    record = Mock()
    monkeypatch.setattr(streaming, "record_text_turn", record)
    events = _post_stream_with_deltas(client, monkeypatch, silence_wav_bytes, [])
    _assert_audible_protocol_fallback(events)
    tts.synthesize.assert_awaited_once_with(settings.llm_fallback_phrase)
    record.assert_not_called()


@pytest.mark.integration
def test_stream_emotion_only_uses_audible_protocol_fallback(
    client: TestClient, silence_wav_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A valid tag followed by an empty/whitespace-only body is invalid output."""
    record = Mock()
    monkeypatch.setattr(streaming, "record_text_turn", record)
    events = _post_stream_with_deltas(client, monkeypatch, silence_wav_bytes, ["EMOTION:joy\n   "])
    _assert_audible_protocol_fallback(events)
    tts.synthesize.assert_awaited_once_with(settings.llm_fallback_phrase)
    record.assert_not_called()


@pytest.mark.integration
def test_every_done_has_prior_contract_valid_audio(
    client: TestClient, silence_wav_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No matter how the model misbehaves, `done` always follows at least one audio event."""
    invalid_delta_cases = [
        ['EMOTION: joy {"response": "hola", "emotion": "joy"}'],
        ['EMOTION:joy\n{"response": "hola"}'],
        ["EMOTION:ale"],
        [],
        ["EMOTION:joy\n   "],
        ["Hola sin protocolo."],
    ]
    for deltas in invalid_delta_cases:
        events = _post_stream_with_deltas(client, monkeypatch, silence_wav_bytes, deltas)
        done_index = next(i for i, event in enumerate(events) if event["type"] == "done")
        audio_before_done = [event for event in events[:done_index] if event["type"] == "audio"]
        assert len(audio_before_done) >= 1, f"no audio before done for deltas={deltas!r}"


@pytest.mark.integration
def test_stream_invalid_output_is_not_logged_raw(
    client: TestClient,
    silence_wav_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The raw invalid candidate text must never reach an INFO/WARN log line."""
    raw_marker = "¡Qué emocionante!"
    deltas = [f'EMOTION: joy {{"response": "{raw_marker}", "emotion": "joy"}}']
    caplog.set_level(logging.INFO)
    _post_stream_with_deltas(client, monkeypatch, silence_wav_bytes, deltas)
    for record in caplog.records:
        assert raw_marker not in record.getMessage()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stream_partial_llm_failure_preserves_audio_then_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider failure after one spoken sentence must preserve it, not re-announce emotion."""
    prepared = PreparedTextTurn(
        "hola robot", "interaction:partial", None, None, False, None, None, None
    )
    record = Mock()
    monkeypatch.setattr(streaming, "record_text_turn", record)

    async def partial_then_fail(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        yield "EMOTION:joy\n"
        yield "Hola. "
        raise LLMError("provider died mid-stream")

    monkeypatch.setattr(llm_streaming, "generate_response_stream", partial_then_fail)

    events = [
        json.loads(line)
        async for line in streaming.stream_pipeline(
            prepared=prepared,
            stt_ms=0,
            request_start=time.perf_counter(),
            schedule_consolidation=lambda *_a, **_k: None,
        )
    ]

    assert [event["type"] for event in events] == [
        "text_heard",
        "emotion",
        "audio",
        "audio",
        "done",
    ]
    assert events[1]["value"] == "joy"
    audio_events = [event for event in events if event["type"] == "audio"]
    assert audio_events[0]["text"] == "Hola."
    assert audio_events[1]["text"] == settings.llm_fallback_phrase
    record.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stream_protocol_fallback_tts_failure_has_no_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A TTS failure while speaking the fallback must never yield a `done` line."""
    prepared = PreparedTextTurn(
        "hola robot", "interaction:tts-fail", None, None, False, None, None, None
    )

    async def plain_text(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        yield "Hola sin protocolo."

    monkeypatch.setattr(llm_streaming, "generate_response_stream", plain_text)
    monkeypatch.setattr(tts, "synthesize", AsyncMock(side_effect=TTSError("piper down")))

    collected: list[str] = []
    with pytest.raises(TTSError):  # noqa: PT012 — must collect partial NDJSON lines before it raises
        async for line in streaming.stream_pipeline(
            prepared=prepared,
            stt_ms=0,
            request_start=time.perf_counter(),
            schedule_consolidation=lambda *_a, **_k: None,
        ):
            collected.append(line)

    assert not any(json.loads(line)["type"] == "done" for line in collected)


@pytest.mark.integration
def test_stream_unknown_emotion_prefix_falls_back_to_neutral(
    client: TestClient, silence_wav_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tag line completes but names an emotion outside VALID_EMOTIONS."""

    async def fake_stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        for delta in ("EMOTION:sarcasmo\n", "Hola."):
            yield delta

    monkeypatch.setattr(llm_streaming, "generate_response_stream", fake_stream)
    response = _post_stream(client, silence_wav_bytes)
    assert response.status_code == 200
    events = _parse_ndjson(response.text)

    assert events[0] == {"type": "text_heard", "value": "hola robot"}
    emotion_events = [e for e in events if e["type"] == "emotion"]
    assert emotion_events == [{"type": "emotion", "value": "neutral"}]
    audio_events = [e for e in events if e["type"] == "audio"]
    assert [e["text"] for e in audio_events] == ["Hola."]
    assert events[-1]["type"] == "done"


@pytest.mark.integration
def test_stream_llm_failure_speaks_fallback_phrase(
    client: TestClient, silence_wav_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = Mock()

    async def failing_stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        raise LLMError("ollama down")
        yield ""

    monkeypatch.setattr(llm_streaming, "generate_response_stream", failing_stream)
    monkeypatch.setattr(streaming, "record_text_turn", record)
    response = _post_stream(client, silence_wav_bytes)
    assert response.status_code == 200
    events = _parse_ndjson(response.text)

    assert events[0] == {"type": "text_heard", "value": "hola robot"}
    assert events[1] == {"type": "emotion", "value": "neutral"}
    audio_events = [e for e in events if e["type"] == "audio"]
    assert audio_events[-1]["text"] == settings.llm_fallback_phrase
    assert events[-1]["type"] == "done"
    record.assert_not_called()


@pytest.mark.integration
async def test_streaming_propagates_prepared_identity_history_and_recording_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The local stream receives prepared identity and history before recording."""
    active_person = _manual_active_person()
    history = [ConversationTurn(role="user", content="previous question")]
    prepared = PreparedTextTurn(
        "hola robot",
        "public-id",
        None,
        history,
        False,
        None,
        None,
        None,
        active_person,
        "session:11111111111111111111111111111111:person:7",
    )
    streamed_kwargs: dict[str, object] = {}

    async def generate_stream(*_args: object, **kwargs: object) -> AsyncIterator[str]:
        streamed_kwargs.update(kwargs)
        yield "EMOTION:joy\nHola."

    monkeypatch.setattr(llm_streaming, "generate_response_stream", generate_stream)

    local_deltas = [delta async for delta in streaming._text_deltas(prepared)]

    assert local_deltas == ["EMOTION:joy\nHola."]
    assert streamed_kwargs["history"] == history
    assert streamed_kwargs["active_person"] is active_person

    record = Mock()
    monkeypatch.setattr(streaming, "record_text_turn", record)

    _ = [
        line
        async for line in streaming.stream_pipeline(
            prepared=prepared,
            stt_ms=0,
            request_start=time.perf_counter(),
            schedule_consolidation=lambda _message, _response, _active_person: None,
        )
    ]

    record_call = record.call_args
    assert record_call is not None
    assert record_call.kwargs["active_person"] is active_person
    assert record_call.kwargs["history_scope"] == prepared.history_scope


@pytest.mark.integration
@pytest.mark.asyncio
async def test_streaming_schedules_manual_identity_for_consolidation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Streaming must preserve manual identity through its scheduler callback."""
    active_person = _manual_active_person()
    prepared = PreparedTextTurn(
        "hola robot",
        "public-id",
        None,
        [],
        False,
        None,
        None,
        None,
        active_person,
        "session:11111111111111111111111111111111:person:7",
    )
    scheduler = Mock()
    monkeypatch.setattr(settings, "memory_enabled", True)

    _ = [
        line
        async for line in streaming.stream_pipeline(
            prepared=prepared,
            stt_ms=0,
            request_start=time.perf_counter(),
            schedule_consolidation=scheduler,
        )
    ]

    scheduler.assert_called_once_with("hola robot", "Hola. ¿Cómo estás?", active_person)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_background_scheduler_forwards_manual_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The FastAPI background bridge must pass identity as data, not permission."""
    active_person = _manual_active_person()
    consolidate = AsyncMock()
    background_tasks = BackgroundTasks()
    monkeypatch.setattr(transcribe_module, "consolidate_turn", consolidate)

    scheduler = transcribe_module._consolidation_scheduler(background_tasks)
    scheduler("hola robot", "Hola.", active_person)
    await background_tasks()

    consolidate.assert_awaited_once_with(
        "hola robot",
        "Hola.",
        active_person=active_person,
    )
    assert active_person.role is HouseholdRole.UNKNOWN
