"""Privacy tests: household content must never reach the logs (Plan 0032).

Each test feeds a unique sentinel through a real code path and asserts the
sentinel never appears in captured log output. A sentinel stands for something
only the household could have produced: a transcript, a model reply, a spoken
sentence, a visual description, or a person's name.

Plan 0043's real acceptance run logged two of these at INFO, which is what put
this file in scope.
"""

from collections.abc import AsyncIterator
import logging
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
import numpy as np
import pytest
from server.memory import context as memory_context, declarative, relations
from server.memory.normalize import normalize_extraction
from server.schemas import ExtractedEntity, TurnExtraction
from server.vision import describe, faces

from server import llm, llm_streaming, stt, tts

# Distinctive enough that a substring match cannot be a coincidence.
_TRANSCRIPT = "SENTINELTRANSCRIPTZQX"
_REPLY = "SENTINELREPLYZQX"
_VISUAL = "SENTINELVISUALZQX"
_PERSON = "Sentinelpersonzqx"


@pytest.fixture
def _sentinel_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every model boundary return a traceable sentinel."""
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value=_TRANSCRIPT))
    monkeypatch.setattr(llm, "generate_response", AsyncMock(return_value=(_REPLY, "joy")))
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("QQ==", 42)))


@pytest.mark.integration
@pytest.mark.usefixtures("_sentinel_pipeline")
def test_classic_turn_never_logs_the_transcript_or_the_reply(
    client: TestClient,
    silence_wav_bytes: bytes,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`pipeline.py` and `text_turn.py` log both at INFO today; they must not."""
    with caplog.at_level(logging.DEBUG):
        response = client.post(
            "/transcribe", files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")}
        )

    assert response.status_code == 200
    assert _TRANSCRIPT not in caplog.text
    assert _REPLY not in caplog.text


@pytest.mark.integration
def test_streaming_turn_never_logs_the_spoken_sentence(
    client: TestClient,
    silence_wav_bytes: bytes,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`streaming_render.py` logs every synthesized sentence at INFO today."""
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value=_TRANSCRIPT))
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("QQ==", 42)))

    async def sentinel_stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        yield f"EMOTION:joy\n{_REPLY}."

    monkeypatch.setattr(llm_streaming, "generate_response_stream", sentinel_stream)

    with caplog.at_level(logging.DEBUG):
        response = client.post(
            "/transcribe/stream",
            files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")},
        )
        body = response.text

    assert response.status_code == 200
    assert _REPLY in body, "the sentinel must still reach the client over the wire"
    assert _TRANSCRIPT not in caplog.text
    assert _REPLY not in caplog.text


@pytest.mark.integration
def test_dropping_an_ungrounded_person_never_logs_their_name(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`normalize.py` logs the rejected person's name — a household member's name."""
    extraction = TurnExtraction(
        entities=[ExtractedEntity(name=_PERSON, type="person")],
        facts=[],
    )

    with caplog.at_level(logging.DEBUG):
        result = normalize_extraction(extraction, user_text="algo sin ese nombre")

    assert result.entities == [], "the ungrounded entity must still be dropped"
    assert _PERSON not in caplog.text


@pytest.mark.integration
async def test_scene_description_is_never_logged(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`vision/describe.py` logs the first 160 characters of what the camera saw."""

    class _FakeResponse:
        """Stand in for the Ollama chat response without a live VLM."""

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict[str, dict[str, str]]:
            return {"message": {"content": _VISUAL}}

    class _FakeClient:
        """Minimal async client honouring the context-manager protocol."""

        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        async def post(self, *_args: object, **_kwargs: object) -> _FakeResponse:
            return _FakeResponse()

    monkeypatch.setattr(describe.httpx, "AsyncClient", lambda **_kw: _FakeClient())

    with caplog.at_level(logging.DEBUG):
        description, _ = await describe.describe_image(b"fake-jpeg-bytes")

    assert description == _VISUAL, "the description must still be returned to the caller"
    assert _VISUAL not in caplog.text


@pytest.mark.integration
@pytest.mark.usefixtures("_sentinel_pipeline")
def test_every_response_carries_a_request_id(
    client: TestClient,
    silence_wav_bytes: bytes,
) -> None:
    """Correlation is what replaces the content being removed from the logs."""
    response = client.post(
        "/transcribe", files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")}
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]


@pytest.mark.integration
@pytest.mark.usefixtures("_sentinel_pipeline")
def test_redaction_does_not_remove_content_from_the_response(
    client: TestClient,
    silence_wav_bytes: bytes,
) -> None:
    """Redacting logs must never redact the reply — that would break the product."""
    response = client.post(
        "/transcribe", files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")}
    )

    body = response.json()
    assert body["text_heard"] == _TRANSCRIPT
    assert body["llm_response"] == _REPLY


@pytest.mark.integration
async def test_storing_an_entity_never_logs_its_name(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`declarative.py` logs the name of every entity it stores — a person's name."""

    class _FakeCursor:
        lastrowid = 7

        @staticmethod
        async def close() -> None:
            return None

    class _FakeConn:
        @staticmethod
        async def execute(*_args: object, **_kwargs: object) -> _FakeCursor:
            return _FakeCursor()

        @staticmethod
        async def commit() -> None:
            return None

    monkeypatch.setattr(declarative, "get_conn", _FakeConn)
    monkeypatch.setattr(declarative, "_find_entity_folded", AsyncMock(return_value=None))
    monkeypatch.setattr(declarative, "write_outbox", AsyncMock(return_value=None))

    with caplog.at_level(logging.DEBUG):
        entity_id = await declarative.upsert_entity(name=_PERSON, type="person")

    assert entity_id == 7, "the entity must still be stored and its id returned"
    assert _PERSON not in caplog.text


@pytest.mark.integration
async def test_building_context_never_logs_the_users_words(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`context.py` logs the first 40 characters of what the user actually said."""
    monkeypatch.setattr(memory_context, "entities_for_relations", AsyncMock(return_value=[]))
    monkeypatch.setattr(memory_context, "load_entity_with_facts", AsyncMock(return_value=None))
    monkeypatch.setattr(memory_context, "search_memories", AsyncMock(return_value=[]))

    with caplog.at_level(logging.DEBUG):
        await memory_context.build_context(_TRANSCRIPT)

    assert _TRANSCRIPT not in caplog.text


@pytest.mark.integration
async def test_relational_lookup_never_logs_the_users_words(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`relations.py` logs the same 40 characters on the relational path."""
    monkeypatch.setattr(relations, "find_facts_by_predicate", AsyncMock(return_value=[]))
    # "mis hijos" triggers a predicate, so the logging branch is actually reached.
    spoken = f"mis hijos {_TRANSCRIPT}"

    with caplog.at_level(logging.DEBUG):
        await relations.entities_for_relations(spoken)

    assert _TRANSCRIPT not in caplog.text


@pytest.mark.integration
async def test_enrolling_a_face_never_logs_the_persons_name(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`faces.py` logs the enrolled label — a person's name beside biometric data.

    This is the most sensitive pairing in the repository: a household member's
    name written next to the row that stores their face embedding.
    """

    class _FakeCursor:
        lastrowid = 3

        @staticmethod
        async def close() -> None:
            return None

    class _FakeConn:
        @staticmethod
        async def execute(*_args: object, **_kwargs: object) -> _FakeCursor:
            return _FakeCursor()

        @staticmethod
        async def commit() -> None:
            return None

    monkeypatch.setattr(faces.db, "get_conn", _FakeConn)
    embedding = np.zeros(512, dtype=np.float32)

    with caplog.at_level(logging.DEBUG):
        profile_id = await faces.enroll_face(entity_id=1, embedding=embedding, label=_PERSON)

    assert profile_id == 3, "the profile must still be stored and its id returned"
    assert _PERSON not in caplog.text
