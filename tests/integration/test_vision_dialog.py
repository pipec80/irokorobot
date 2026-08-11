"""Integration tests for the V0.5 vision dialogue flow (two rounds).

Round 1: /transcribe detects a visual question → speaks the cue phrase and
answers ``vision_requested=true`` (LLM untouched).
Round 2: /vision/respond takes frame + question → VLM description enters
the character prompt → spoken in-character answer.
"""

from __future__ import annotations

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
def test_vision_respond_vlm_down_still_speaks(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dead VLM must not mute the robot: it answers blind with an excuse."""
    monkeypatch.setattr(vision, "perceive", AsyncMock(side_effect=VisionError("vlm down")))

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
def test_vision_respond_routes_enrollment(client: TestClient) -> None:
    """Round 2 (V1): the enroll phrase routes to enroll_from_frame with the
    captured name — not to the scene-description path."""
    resp = _post_respond(client, _FAKE_JPEG, "aprende mi cara, soy Felipe")

    assert resp.status_code == 200
    vision.enroll_from_frame.assert_awaited_once()  # type: ignore[attr-defined]  # AsyncMock
    name, _image = vision.enroll_from_frame.await_args.args  # type: ignore[attr-defined]
    assert name == "Felipe"
    vision.perceive.assert_not_awaited()  # type: ignore[attr-defined]  # AsyncMock
    kwargs = llm.generate_response.await_args.kwargs  # type: ignore[attr-defined]  # AsyncMock
    assert "Felipe" in kwargs["perception"]


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
