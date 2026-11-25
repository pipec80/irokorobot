"""Unit tests for the grounded, code-owned VLM describe prompt (P0-C7 Task 2).

Verifies the exact wire payload sent to the local Ollama VLM: one fixed,
code-owned prompt — never the caller's raw question — carrying every
grounding rule, one image, the configured model, and the current
non-streaming/temperature contract.
"""

import base64
import inspect
from io import BytesIO
from typing import Any
from unittest.mock import AsyncMock

import httpx
from PIL import Image
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

    assert list(parameters) == ["client", "image"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_describe_image_sends_the_fixed_prompt_one_image_and_current_options(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wire payload carries the fixed prompt, one image, and preserved options."""
    mock = _mock_post(monkeypatch, _FakeResponse({"message": {"content": "Una escena."}}))

    await describe_image(http_client, b"fake-image-bytes")

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
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty VLM response must never be treated as a valid description."""
    _mock_post(monkeypatch, _FakeResponse({"message": {"content": "   "}}))

    with pytest.raises(VisionError):
        await describe_image(http_client, b"fake-image-bytes")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_describe_image_rejects_an_unexpected_backend_shape(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A backend response missing the expected keys must raise, not crash raw."""
    _mock_post(monkeypatch, _FakeResponse({"unexpected": "shape"}))

    with pytest.raises(VisionError):
        await describe_image(http_client, b"fake-image-bytes")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_describe_image_wraps_a_transport_failure(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreachable Ollama backend must surface as a VisionError, not raw httpx."""
    mock = AsyncMock(side_effect=httpx.ConnectError("refused"))
    monkeypatch.setattr(httpx.AsyncClient, "post", mock)

    with pytest.raises(VisionError):
        await describe_image(http_client, b"fake-image-bytes")


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"message": {"content": None}}, {"message": None}])
async def test_describe_image_rejects_a_null_description(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
) -> None:
    """A null VLM message must be a VisionError, never "None" or a raw TypeError."""
    _mock_post(monkeypatch, _FakeResponse(payload))

    with pytest.raises(VisionError):
        await describe_image(http_client, b"fake-image-bytes")


# --- Plan 0089 D-11: a good scene says what it cost, a failed one says why ---


def _jpeg(width: int, height: int) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


def _client(reply: Exception | dict[str, Any]) -> httpx.AsyncClient:
    def handler(_request: httpx.Request) -> httpx.Response:
        if isinstance(reply, Exception):
            raise reply
        return httpx.Response(200, json=reply)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.unit
async def test_a_good_scene_logs_vision_metrics_in_milliseconds(
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = {
        "message": {"content": "Una taza amarilla qqtazaqq."},
        "total_duration": 9_000_000_000,
        "load_duration": 6_000_000_000,
        "prompt_eval_count": 700,
        "prompt_eval_duration": 2_000_000_000,
        "eval_count": 30,
        "eval_duration": 1_000_000_000,
    }
    async with _client(body) as client:
        with caplog.at_level("INFO", logger="server.vision.describe"):
            await describe_image(client, _jpeg(640, 360))

    (record,) = [r for r in caplog.records if getattr(r, "event", None) == "vision.metrics"]
    assert record.capability == "scene"  # type: ignore[attr-defined]  # set through ``extra``
    assert (record.width, record.height) == (640, 360)  # type: ignore[attr-defined]
    assert record.load_ms == 6000  # type: ignore[attr-defined]
    assert record.prompt_eval_count == 700  # type: ignore[attr-defined]
    assert record.prompt_eval_ms == 2000  # type: ignore[attr-defined]
    assert record.eval_count == 30  # type: ignore[attr-defined]
    assert record.eval_ms == 1000  # type: ignore[attr-defined]
    assert record.total_ms == 9000  # type: ignore[attr-defined]


@pytest.mark.unit
@pytest.mark.parametrize(
    "reply, cause",
    [
        (httpx.ReadTimeout("slow"), "ReadTimeout"),
        ({"message": {"content": "  "}}, "nothing_described"),
        ({"unexpected": "shape"}, "LLMError"),
    ],
)
async def test_a_failed_scene_logs_its_cause(
    reply: Exception | dict[str, Any], cause: str, caplog: pytest.LogCaptureFixture
) -> None:
    async with _client(reply) as client:
        with (
            caplog.at_level("WARNING", logger="server.vision.describe"),
            pytest.raises(VisionError),
        ):
            await describe_image(client, b"fake-image-bytes")

    (record,) = [r for r in caplog.records if getattr(r, "event", None) == "vision.describe_failed"]
    assert record.cause == cause  # type: ignore[attr-defined]
    assert (record.width, record.height) == (None, None)  # type: ignore[attr-defined]
