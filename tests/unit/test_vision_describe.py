"""Unit tests for the grounded, code-owned VLM describe prompt (P0-C7 Task 2).

Verifies the exact wire payload sent to the local Ollama VLM: one fixed,
code-owned prompt — never the caller's raw question — carrying every
grounding rule, one image, the configured model, and the current
non-streaming/temperature contract.
"""

import base64
import inspect
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from server.exceptions import VisionError
from server.settings import settings
from server.vision.describe import _DESCRIBE_PROMPT, describe_image


class _FakeResponse:
    """Minimal stand-in for an `httpx.Response` used by `describe_image`."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


def _mock_post(monkeypatch: pytest.MonkeyPatch, response: _FakeResponse) -> AsyncMock:
    """Patch `httpx.AsyncClient.post` and return the mock for call inspection."""
    mock = AsyncMock(return_value=response)
    monkeypatch.setattr(httpx.AsyncClient, "post", mock)
    return mock


@pytest.mark.unit
def test_describe_image_signature_has_no_question_parameter() -> None:
    """The caller's raw question must never be able to reach the VLM prompt."""
    parameters = inspect.signature(describe_image).parameters

    assert list(parameters) == ["image"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_describe_image_sends_the_fixed_prompt_one_image_and_current_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wire payload carries the fixed prompt, one image, and preserved options."""
    mock = _mock_post(monkeypatch, _FakeResponse({"message": {"content": "Una escena."}}))

    await describe_image(b"fake-image-bytes")

    call = mock.await_args
    assert call is not None
    payload = call.kwargs["json"]
    assert payload["model"] == settings.vlm_model
    assert payload["stream"] is False
    assert payload["options"] == {"temperature": 0.3}
    assert len(payload["messages"]) == 1
    message = payload["messages"][0]
    assert message["role"] == "user"
    assert message["content"] == _DESCRIBE_PROMPT
    assert message["images"] == [base64.b64encode(b"fake-image-bytes").decode("ascii")]


@pytest.mark.unit
@pytest.mark.parametrize(
    "required_rule",
    [
        "evidencia visible",
        "no se distingue",
        "identidad",
        "género",
        "relación",
        "intención",
        "emoción",
        "estado mental",
        "contenedor",
    ],
)
def test_fixed_prompt_contains_every_grounding_rule(required_rule: str) -> None:
    """Each grounding constraint from the plan must be present in the fixed prompt."""
    assert required_rule in _DESCRIBE_PROMPT.lower()


@pytest.mark.unit
def test_fixed_prompt_requires_spanish_and_forbids_lists_and_english() -> None:
    """Preserve the original V0 formatting contract alongside the new grounding rules."""
    assert "español" in _DESCRIBE_PROMPT.lower()
    assert "sin listas" in _DESCRIBE_PROMPT.lower()
    assert "sin inglés" in _DESCRIBE_PROMPT.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_describe_image_rejects_an_empty_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty VLM response must never be treated as a valid description."""
    _mock_post(monkeypatch, _FakeResponse({"message": {"content": "   "}}))

    with pytest.raises(VisionError):
        await describe_image(b"fake-image-bytes")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_describe_image_rejects_an_unexpected_backend_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A backend response missing the expected keys must raise, not crash raw."""
    _mock_post(monkeypatch, _FakeResponse({"unexpected": "shape"}))

    with pytest.raises(VisionError):
        await describe_image(b"fake-image-bytes")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_describe_image_wraps_a_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreachable Ollama backend must surface as a VisionError, not raw httpx."""
    mock = AsyncMock(side_effect=httpx.ConnectError("refused"))
    monkeypatch.setattr(httpx.AsyncClient, "post", mock)

    with pytest.raises(VisionError):
        await describe_image(b"fake-image-bytes")
