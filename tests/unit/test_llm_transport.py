"""Unit tests for server.llm_transport: strip_json_fences, ollama_chat(_stream).

Plan 0039: ``ollama_chat``/``ollama_chat_stream`` now take an injected
``httpx.AsyncClient`` instead of constructing their own — tests build a real
client over ``httpx.MockTransport`` rather than monkeypatching the
``httpx.AsyncClient`` constructor.
"""

from collections.abc import AsyncIterator, Callable
import json

import httpx
import pytest

from server import llm_transport


@pytest.mark.unit
def test_strip_json_fences_removes_json_tagged_fence() -> None:
    raw = '```json\n{"a": 1}\n```'
    assert llm_transport.strip_json_fences(raw) == '{"a": 1}'


@pytest.mark.unit
def test_strip_json_fences_removes_bare_fence() -> None:
    raw = '```\n{"a": 1}\n```'
    assert llm_transport.strip_json_fences(raw) == '{"a": 1}'


@pytest.mark.unit
def test_strip_json_fences_passes_through_unfenced_text() -> None:
    raw = '{"a": 1}'
    assert llm_transport.strip_json_fences(raw) == '{"a": 1}'


def _mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    """Build a real AsyncClient over a MockTransport for one test."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.unit
async def test_ollama_chat_returns_message_content() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": "hola humano"}})

    async with _mock_client(handler) as client:
        result = await llm_transport.ollama_chat(
            client, [{"role": "user", "content": "hola"}], model="qwen2.5:3b"
        )
    assert result == "hola humano"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["stream"] is False
    assert payload["model"] == "qwen2.5:3b"


@pytest.mark.unit
async def test_ollama_chat_includes_format_and_options_when_given() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": "hola"}})

    schema = {"type": "object"}
    async with _mock_client(handler) as client:
        await llm_transport.ollama_chat(
            client,
            [{"role": "user", "content": "hola"}],
            model="qwen2.5:3b",
            format_schema=schema,
            options={"temperature": 0.1},
        )
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["format"] == schema
    assert payload["options"] == {"temperature": 0.1}


@pytest.mark.unit
async def test_ollama_chat_omits_format_when_not_given() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": "hola"}})

    async with _mock_client(handler) as client:
        await llm_transport.ollama_chat(
            client, [{"role": "user", "content": "hola"}], model="qwen2.5:3b"
        )
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert "format" not in payload
    assert "options" not in payload


def _stream_handler(lines: list[str]) -> Callable[[httpx.Request], httpx.Response]:
    """Build a MockTransport handler returning NDJSON lines as a streamed body."""
    body = "\n".join(lines).encode()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    return handler


@pytest.mark.unit
async def test_ollama_chat_stream_yields_content_deltas() -> None:
    handler = _stream_handler(
        [
            '{"message": {"content": "Hola"}}',
            '{"message": {"content": " mundo"}}',
            '{"done": true}',
        ]
    )
    async with _mock_client(handler) as client:
        deltas = [d async for d in llm_transport.ollama_chat_stream(client, [], model="qwen2.5:3b")]
    assert deltas == ["Hola", " mundo"]


@pytest.mark.unit
async def test_ollama_chat_stream_skips_blank_lines() -> None:
    handler = _stream_handler(
        [
            "",
            '{"message": {"content": "Hola"}}',
            "   ",
        ]
    )
    async with _mock_client(handler) as client:
        deltas = [d async for d in llm_transport.ollama_chat_stream(client, [], model="qwen2.5:3b")]
    assert deltas == ["Hola"]


@pytest.mark.unit
async def test_ollama_chat_stream_sets_stream_true() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, content=b"")

    async with _mock_client(handler) as client:
        deltas: AsyncIterator[str] = llm_transport.ollama_chat_stream(
            client, [], model="qwen2.5:3b"
        )
        async for _ in deltas:
            pass
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["stream"] is True
