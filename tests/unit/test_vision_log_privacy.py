"""Plan 0089 D-11: no new log line carries a prompt, a description, a read text or an image.

A canary goes through every new log path — an Ollama error, a good and a failed scene, a good
and a failed reading — and is searched for in every captured record, message and ``extra``.
"""

import base64

import httpx
import pytest
from server.exceptions import VisionError
from server.vision.describe import describe_image
from server.vision.read_text import read_text

from server import llm_transport

pytestmark = pytest.mark.unit

_CANARY = "qqprivadoqq"
_IMAGE = b"\xff\xd8" + _CANARY.encode()


def _client(status: int, body: dict[str, object]) -> httpx.AsyncClient:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _assert_no_canary(caplog: pytest.LogCaptureFixture) -> None:
    encoded = base64.b64encode(_IMAGE).decode("ascii")
    assert caplog.records, "the path under test logged nothing"
    for record in caplog.records:
        dump = record.getMessage() + repr(vars(record))
        assert _CANARY not in dump
        assert encoded not in dump


async def test_an_ollama_error_logs_no_message_text(caplog: pytest.LogCaptureFixture) -> None:
    async with _client(500, {"error": "model failed to load"}) as client:
        with caplog.at_level("DEBUG"), pytest.raises(httpx.HTTPStatusError):
            await llm_transport.ollama_chat(
                client, [{"role": "user", "content": _CANARY}], model="qwen2.5:3b"
            )
    _assert_no_canary(caplog)


@pytest.mark.parametrize("call", [describe_image, read_text])
async def test_a_good_vision_answer_logs_no_text(
    call: object, caplog: pytest.LogCaptureFixture
) -> None:
    body: dict[str, object] = {"message": {"content": f"Una taza {_CANARY}."}, "eval_count": 3}
    async with _client(200, body) as client:
        with caplog.at_level("DEBUG"):
            await call(client, _IMAGE)  # type: ignore[operator]  # one of the two vision calls
    _assert_no_canary(caplog)


@pytest.mark.parametrize("call", [describe_image, read_text])
async def test_a_failed_vision_call_logs_no_text(
    call: object, caplog: pytest.LogCaptureFixture
) -> None:
    async with _client(500, {"error": "out of memory"}) as client:
        with caplog.at_level("DEBUG"), pytest.raises(VisionError):
            await call(client, _IMAGE)  # type: ignore[operator]  # one of the two vision calls
    _assert_no_canary(caplog)
