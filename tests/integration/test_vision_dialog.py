"""Integration tests for the V0.5 vision dialogue flow (two rounds).

Round 1: /transcribe detects a visual question → speaks the cue phrase and
answers ``vision_requested=true`` (LLM untouched).
Round 2: /vision/respond takes frame + question → VLM description enters
the character prompt → spoken in-character answer.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

import cv2
import numpy as np
import pytest
from server.exceptions import VisionError
from server.routers import vision as vision_module
from server.settings import settings
from server.text_turn import TextTurnResult
from server.vision import PERCEPTION_FAILED

from server import llm, stt, tts, vision

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    import httpx

# A tiny but genuinely decodable JPEG — validation now decodes the frame
# (PROMPT B3), so magic bytes alone are no longer enough for these tests.
_FAKE_JPEG = cv2.imencode(".jpg", np.zeros((10, 10, 3), dtype=np.uint8))[1].tobytes()


@pytest.fixture(autouse=True)
def _vision_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vision on, external pieces mocked with canned answers."""
    monkeypatch.setattr(settings, "vision_enabled", True)
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value="¿qué ves?"))
    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("AAAA", 42)))
    monkeypatch.setattr(
        vision,
        "perceive",
        AsyncMock(return_value="Una bola roja sobre la mesa."),
    )
    monkeypatch.setattr(
        vision_module,
        "perceive_scene",
        AsyncMock(return_value="Una bola roja sobre la mesa."),
        raising=False,
    )
    monkeypatch.setattr(
        vision,
        "enroll_from_frame",
        AsyncMock(return_value="Acabás de aprender la cara de Felipe."),
    )
    monkeypatch.setattr(
        llm, "generate_response", AsyncMock(return_value=("¡Veo una bola roja!", "joy"))
    )


def _post_respond(client: TestClient, image: bytes, text: str) -> httpx.Response:
    """POST a frame plus the question to /vision/respond."""
    return client.post(
        "/vision/respond",
        files={"image": ("frame.jpg", image, "image/jpeg")},
        data={"text": text},
    )


@pytest.mark.integration
def test_vision_event_from_question_is_fresh_and_opaque() -> None:
    """Visual questions must receive request-local IDs and an opaque scope."""
    first = vision_module._vision_event_from_question("¿qué ves?")
    second = vision_module._vision_event_from_question("¿qué ves?")

    assert first.event_type == "text.turn"
    assert first.source == "vision.respond"
    assert first.subject_id is None
    assert first.occurred_at.tzinfo is not None
    assert first.recorded_at.tzinfo is not None
    assert first.event_id != second.event_id
    assert first.correlation_id != second.correlation_id
    assert first.payload.conversation_id.startswith("interaction:")
    assert first.payload.conversation_id != second.payload.conversation_id


@pytest.mark.integration
def test_transcribe_visual_question_requests_frame(
    client: TestClient, silence_wav_bytes: bytes
) -> None:
    """Round 1: visual question → cue phrase + vision_requested, no LLM call."""
    resp = client.post("/transcribe", files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")})

    assert resp.status_code == 200
    body = resp.json()
    assert body["vision_requested"] is True
    assert body["llm_response"] == settings.vision_look_phrase
    llm.generate_response.assert_not_awaited()  # type: ignore[attr-defined]  # AsyncMock


@pytest.mark.integration
def test_transcribe_normal_question_has_no_vision_flag(
    client: TestClient, silence_wav_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-visual turn keeps the normal pipeline and vision_requested=False."""
    monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value="hola robot"))

    resp = client.post("/transcribe", files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")})

    assert resp.status_code == 200
    body = resp.json()
    assert body["vision_requested"] is False
    assert body["llm_response"] == "¡Veo una bola roja!"


@pytest.mark.integration
def test_vision_respond_answers_in_character(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round 2 should use a fresh internal scope for each visual dialogue."""
    scopes = ("interaction:vision-one", "interaction:vision-two")
    process = AsyncMock(return_value=TextTurnResult("¡Veo una bola roja!", "joy", 7, False))
    new_scope = Mock(side_effect=scopes)
    monkeypatch.setattr(vision_module, "process_text_turn", process)
    monkeypatch.setattr(vision_module, "new_interaction_scope", new_scope, raising=False)

    responses = [_post_respond(client, _FAKE_JPEG, "¿qué ves?") for _ in scopes]

    assert [response.status_code for response in responses] == [200, 200]
    assert all(response.json()["llm_response"] == "¡Veo una bola roja!" for response in responses)
    assert all(response.json()["vision_requested"] is False for response in responses)
    assert [call.args[1] for call in process.await_args_list] == list(scopes)
    assert all(
        call.kwargs == {"perception": "Una bola roja sobre la mesa."}
        for call in process.await_args_list
    )
    assert all(scope not in response.text for scope in scopes for response in responses)


@pytest.mark.integration
def test_vision_respond_routes_current_date_without_legacy_generation(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deterministic visual question must not enter the generic text path."""
    process = AsyncMock(return_value=TextTurnResult("legacy", "joy", 7, False))
    monkeypatch.setattr(vision_module, "process_text_turn", process)
    monkeypatch.setattr(vision_module, "_today", lambda: date(2026, 8, 14), raising=False)

    response = _post_respond(client, _FAKE_JPEG, "¿Qué fecha es hoy?")

    assert response.status_code == 200
    body = response.json()
    assert body["llm_response"] == "Hoy es 2026-08-14."
    assert body["emotion"] == "neutral"
    process.assert_not_awaited()


@pytest.mark.integration
def test_vision_respond_denies_protected_data_before_legacy_generation(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unknown visual requester must not send family data to legacy generation."""
    process = AsyncMock(return_value=TextTurnResult("legacy", "joy", 7, False))
    audit = AsyncMock()
    reader = Mock()
    tools = Mock()
    monkeypatch.setattr(vision_module, "process_text_turn", process)
    monkeypatch.setattr(vision_module, "record_authorization_decision", audit, raising=False)
    monkeypatch.setattr(vision_module, "PolicyGatedV4Reader", Mock(return_value=reader))
    monkeypatch.setattr(vision_module, "HouseholdKnowledgeTools", Mock(return_value=tools))

    response = _post_respond(client, _FAKE_JPEG, "¿Cómo se llaman mis hijos?")

    assert response.status_code == 200
    body = response.json()
    assert body["llm_response"] == (
        "No puedo acceder a información familiar privada sin una autorización comprobada."
    )
    assert body["emotion"] == "neutral"
    process.assert_not_awaited()
    audit.assert_awaited_once()
    audit_call = audit.await_args
    assert audit_call is not None
    request, decision = audit_call.args
    assert request.actor.person_id is None
    assert request.target_person_id is None
    assert decision.decision.value == "denied"
    assert "Máximo" not in repr(request)
    assert "Sofía" not in repr(request)
    reader.read_active_literals.assert_not_called()
    reader.read_active_relations.assert_not_called()
    tools.get_children.assert_not_called()
    tools.count_children.assert_not_called()


@pytest.mark.integration
def test_vision_respond_uses_nonidentity_scene_perception(
    client: TestClient,
) -> None:
    """An unresolved visual turn must not recognize or inject persisted names."""
    resp = _post_respond(client, _FAKE_JPEG, "¿qué ves?")

    assert resp.status_code == 200
    vision_module.perceive_scene.assert_awaited_once()  # type: ignore[attr-defined]  # AsyncMock
    vision.perceive.assert_not_awaited()  # type: ignore[attr-defined]  # AsyncMock
    kwargs = llm.generate_response.await_args.kwargs  # type: ignore[attr-defined]  # AsyncMock
    assert kwargs["perception"] == "Una bola roja sobre la mesa."


@pytest.mark.integration
def test_vision_respond_vlm_down_still_speaks(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dead VLM must not mute the robot: it answers blind with an excuse."""
    monkeypatch.setattr(
        vision_module,
        "perceive_scene",
        AsyncMock(side_effect=VisionError("vlm down")),
        raising=False,
    )

    resp = _post_respond(client, _FAKE_JPEG, "¿qué ves?")

    assert resp.status_code == 200
    kwargs = llm.generate_response.await_args.kwargs  # type: ignore[attr-defined]  # AsyncMock
    assert kwargs["perception"] == PERCEPTION_FAILED


@pytest.mark.integration
def test_transcribe_enroll_phrase_requests_frame(
    client: TestClient, silence_wav_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Round 1 (V1): an explicit enroll phrase also asks for a camera frame."""
    monkeypatch.setattr(
        stt, "transcribe", AsyncMock(return_value="Iroko, aprende mi cara, soy Felipe")
    )

    resp = client.post("/transcribe", files={"audio": ("a.wav", silence_wav_bytes, "audio/wav")})

    assert resp.status_code == 200
    assert resp.json()["vision_requested"] is True


@pytest.mark.integration
def test_vision_respond_quarantines_enrollment_phrase(client: TestClient) -> None:
    """Enrollment phrases must not reach a public biometric write path."""
    resp = _post_respond(client, _FAKE_JPEG, "aprende mi cara, soy Felipe")

    assert resp.status_code == 200
    vision.enroll_from_frame.assert_not_awaited()  # type: ignore[attr-defined]  # AsyncMock
    vision_module.perceive_scene.assert_not_awaited()  # type: ignore[attr-defined]  # AsyncMock
    kwargs = llm.generate_response.await_args.kwargs  # type: ignore[attr-defined]  # AsyncMock
    assert kwargs["perception"] == vision_module._BIOMETRIC_ENROLLMENT_UNAVAILABLE


@pytest.mark.integration
def test_vision_respond_disabled_returns_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "vision_enabled", False)

    resp = _post_respond(client, _FAKE_JPEG, "¿qué ves?")

    assert resp.status_code == 503


@pytest.mark.integration
def test_vision_respond_empty_text_returns_422(client: TestClient) -> None:
    resp = _post_respond(client, _FAKE_JPEG, "   ")

    assert resp.status_code == 422
