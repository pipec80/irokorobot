"""Integration tests for POST /transcribe/stream."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
import json
import time
from unittest.mock import AsyncMock, Mock
from uuid import UUID

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
from server.exceptions import LLMError
from server.routers import transcribe as transcribe_module
from server.schemas import ConversationTurn
from server.settings import settings
from server.text_turn import PreparedTextTurn

from server import llm, llm_streaming, streaming, stt, tts


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


def _post_stream(client: TestClient, audio: bytes) -> httpx.Response:
    """Post one WAV 16kHz, mono, int16 stream request."""
    return client.post(
        "/transcribe/stream",
        files={"audio": ("a.wav", audio, "audio/wav")},
    )


def _parse_ndjson(text: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in text.strip().split("\n") if line.strip()]


@pytest.mark.integration
def test_stream_happy_path_anthropic_wraps_as_single_delta(
    client: TestClient, silence_wav_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Anthropic path has no real streaming — one LLM call, N sentences."""
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(
        llm, "generate_response", AsyncMock(return_value=("Hola. ¿Cómo estás?", "joy"))
    )
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
    """Streaming should prepare prompt inputs through the shared service."""
    prepared = PreparedTextTurn(
        "hola robot",
        settings.voice_conversation_id,
        None,
        None,
        False,
        None,
        None,
        None,
        None,
    )
    prepare = AsyncMock(return_value=prepared)
    record = Mock()
    monkeypatch.setattr(transcribe_module, "prepare_text_turn", prepare)
    monkeypatch.setattr(streaming, "record_text_turn", record)
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(llm, "generate_response", AsyncMock(return_value=("Hola.", "joy")))

    response = _post_stream(client, silence_wav_bytes)

    assert response.status_code == 200
    prepare.assert_awaited_once_with("hola robot", settings.voice_conversation_id)
    assert record.call_args.args == (
        "hola robot",
        settings.voice_conversation_id,
        "Hola.",
        "joy",
    )
    assert callable(record.call_args.kwargs["schedule_consolidation"])


@pytest.mark.integration
def test_stream_happy_path_ollama_streams_multiple_deltas(
    client: TestClient, silence_wav_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "llm_provider", "ollama")

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
def test_stream_truncated_emotion_tag_is_discarded_not_spoken(
    client: TestClient, silence_wav_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stream ends mid tag ("EMOTION:ale", no \\n) — discarded, never spoken."""
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    record = Mock()

    async def fake_stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        yield "EMOTION:ale"

    monkeypatch.setattr(llm_streaming, "generate_response_stream", fake_stream)
    monkeypatch.setattr(streaming, "record_text_turn", record)
    response = _post_stream(client, silence_wav_bytes)
    assert response.status_code == 200
    events = _parse_ndjson(response.text)

    assert events[0] == {"type": "text_heard", "value": "hola robot"}
    emotion_events = [e for e in events if e["type"] == "emotion"]
    assert emotion_events == [{"type": "emotion", "value": "neutral"}]
    audio_events = [e for e in events if e["type"] == "audio"]
    for event in audio_events:
        text = event["text"]
        assert isinstance(text, str)
        assert "EMOTION" not in text
    assert events[-1]["type"] == "done"
    record.assert_not_called()


@pytest.mark.integration
def test_stream_unknown_emotion_prefix_falls_back_to_neutral(
    client: TestClient, silence_wav_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tag line completes but names an emotion outside VALID_EMOTIONS."""
    monkeypatch.setattr(settings, "llm_provider", "ollama")

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
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(llm, "generate_response", AsyncMock(side_effect=LLMError("ollama down")))
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
    """Both provider paths must use the same prepared identity and scope."""
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
        None,
        active_person,
        "session:11111111111111111111111111111111:person:7",
    )
    standard_generate = AsyncMock(return_value=("Hola.", "joy"))
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(llm, "generate_response", standard_generate)

    standard_deltas = [delta async for delta in streaming._text_deltas(prepared)]

    assert standard_deltas == ["EMOTION:joy\nHola."]
    assert standard_generate.await_args.kwargs["history"] == history
    assert standard_generate.await_args.kwargs["active_person"] is active_person

    streamed_kwargs: dict[str, object] = {}

    async def generate_stream(*_args: object, **kwargs: object) -> AsyncIterator[str]:
        streamed_kwargs.update(kwargs)
        yield "EMOTION:joy\nHola."

    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(llm_streaming, "generate_response_stream", generate_stream)

    ollama_deltas = [delta async for delta in streaming._text_deltas(prepared)]

    assert ollama_deltas == ["EMOTION:joy\nHola."]
    assert streamed_kwargs["history"] == history
    assert streamed_kwargs["active_person"] is active_person

    record = Mock()
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(streaming, "record_text_turn", record)

    _ = [
        line
        async for line in streaming.stream_pipeline(
            prepared=prepared,
            stt_ms=0,
            request_start=time.perf_counter(),
            schedule_consolidation=lambda _message, _response: None,
        )
    ]

    assert record.call_args.kwargs["active_person"] is active_person
    assert record.call_args.kwargs["history_scope"] == prepared.history_scope
