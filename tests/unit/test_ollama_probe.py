"""The start-up probe that only warns when Ollama is unreachable (Plan 0064, D-6).

It does one ``GET /api/tags`` through the shared transport and never raises: a server that
starts before Ollama must still start, and say so. It does not detect a model that answers
``/api/tags`` while it is still loading (the cold-start 500 seen in the 0063 acceptance).
"""

import asyncio
from collections.abc import Callable, Coroutine
import logging

import httpx
import pytest
from server.ollama_probe import probe_ollama
from server.settings import settings

from server import ollama_probe

pytestmark = pytest.mark.unit

type Handler = (
    Callable[[httpx.Request], httpx.Response]
    | Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]
)


def _client(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


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
        async with _client(handler) as client:
            assert await probe_ollama(client) is True

    assert [(r.method, str(r.url)) for r in seen] == [("GET", f"{settings.ollama_url}/api/tags")]
    assert _warnings(caplog) == []


def _connection_refused(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused", request=request)


def _server_error(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(500)


async def _stalls(_request: httpx.Request) -> httpx.Response:
    await asyncio.sleep(5)
    return httpx.Response(200)


@pytest.mark.parametrize(
    "handler, error_class",
    [
        (_connection_refused, "ConnectError"),
        (_server_error, "HTTPStatusError"),
        (_stalls, "TimeoutError"),
    ],
    ids=["connection-refused", "server-error", "stalled-host"],
)
async def test_an_ollama_that_does_not_answer_warns_once_with_the_class_only(
    handler: Handler,
    error_class: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(ollama_probe, "_PROBE_TIMEOUT_SECONDS", 0.05)

    with caplog.at_level(logging.WARNING):
        async with _client(handler) as client:
            assert await probe_ollama(client) is False

    messages = _warnings(caplog)
    assert len(messages) == 1
    assert error_class in messages[0]
    assert "refused" not in messages[0]
    assert all(r.exc_info is None for r in caplog.records)


@pytest.mark.parametrize("url", ["http://[::1", "", "localhost:11434"])
async def test_a_malformed_url_is_a_warning_not_a_failed_start(
    url: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """``InvalidURL`` and ``ValueError`` are not an ``HTTPError``: the probe must never raise."""
    monkeypatch.setattr(settings, "ollama_url", url)

    with caplog.at_level(logging.WARNING):
        async with _client(lambda _request: httpx.Response(200)) as client:
            assert await probe_ollama(client) is False

    assert len(_warnings(caplog)) == 1
