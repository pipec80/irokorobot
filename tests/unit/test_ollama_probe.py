"""The start-up probe that only warns when Ollama is unreachable (Plan 0064, D-6).

It does one ``GET /api/tags`` and never raises: a server that starts before Ollama must still
start, and say so. It does not detect a model that answers ``/api/tags`` while it is still
loading (the cold-start 500 seen in the 0063 acceptance).
"""

from collections.abc import Callable
import logging

import httpx
import pytest
from server.ollama_probe import probe_ollama

pytestmark = pytest.mark.unit

_BASE_URL = "http://ollama.test:11434"


def _client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


async def test_an_ollama_that_answers_is_reachable_and_nothing_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"models": []})

    with caplog.at_level(logging.WARNING):
        async with _client(httpx.MockTransport(handler)) as client:
            assert await probe_ollama(client, _BASE_URL) is True

    assert [(r.method, str(r.url)) for r in seen] == [("GET", f"{_BASE_URL}/api/tags")]
    assert _warnings(caplog) == []


async def test_a_trailing_slash_in_the_base_url_does_not_double_the_path() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200)

    async with _client(httpx.MockTransport(handler)) as client:
        await probe_ollama(client, f"{_BASE_URL}/")

    assert seen == ["/api/tags"]


def _connection_refused(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused", request=request)


def _server_error(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(500)


@pytest.mark.parametrize(
    "handler, error_class",
    [(_connection_refused, "ConnectError"), (_server_error, "HTTPStatusError")],
)
async def test_an_ollama_that_does_not_answer_warns_once_with_the_class_only(
    handler: Callable[[httpx.Request], httpx.Response],
    error_class: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        async with _client(httpx.MockTransport(handler)) as client:
            assert await probe_ollama(client, _BASE_URL) is False

    messages = _warnings(caplog)
    assert len(messages) == 1
    assert error_class in messages[0]
    assert "refused" not in messages[0]
    assert all(r.exc_info is None for r in caplog.records)
