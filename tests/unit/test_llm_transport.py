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
from server.exceptions import LLMError

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


async def _drain(sink: list[str], stream: AsyncIterator[str]) -> None:
    """Consume a delta stream into *sink* so a `pytest.raises` block stays one statement."""
    async for delta in stream:
        sink.append(delta)


@pytest.mark.unit
@pytest.mark.parametrize(
    "body",
    [
        {"message": {"content": None}},
        {"message": None},
        {"message": {"role": "assistant"}},
        ["not", "an", "object"],
    ],
)
async def test_ollama_chat_rejects_a_body_without_text_content(body: object) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    async with _mock_client(handler) as client:
        with pytest.raises(LLMError):
            await llm_transport.ollama_chat(client, [], model="qwen2.5:3b")


@pytest.mark.unit
async def test_ollama_chat_wraps_a_non_json_body() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>proxy error</html>")

    async with _mock_client(handler) as client:
        with pytest.raises(LLMError):
            await llm_transport.ollama_chat(client, [], model="qwen2.5:3b")


@pytest.mark.unit
async def test_ollama_chat_stream_rejects_a_null_message() -> None:
    handler = _stream_handler(['{"message": {"content": "Hola"}}', '{"message": null}'])
    async with _mock_client(handler) as client:
        with pytest.raises(LLMError):
            await _drain([], llm_transport.ollama_chat_stream(client, [], model="qwen2.5:3b"))


@pytest.mark.unit
async def test_ollama_chat_stream_rejects_a_midstream_error_line() -> None:
    handler = _stream_handler(['{"message": {"content": "Hola"}}', '{"error": "runner stopped"}'])
    deltas: list[str] = []
    async with _mock_client(handler) as client:
        with pytest.raises(LLMError):
            await _drain(deltas, llm_transport.ollama_chat_stream(client, [], model="qwen2.5:3b"))
    assert deltas == ["Hola"]


@pytest.mark.unit
async def test_ollama_chat_stream_accepts_an_empty_thinking_delta() -> None:
    handler = _stream_handler(
        [
            '{"message": {"role": "assistant", "content": "", "thinking": "hmm"}}',
            '{"message": {"content": "Hola"}}',
            '{"done": true}',
        ]
    )
    async with _mock_client(handler) as client:
        deltas = [d async for d in llm_transport.ollama_chat_stream(client, [], model="qwen2.5:3b")]
    assert deltas == ["Hola"]


@pytest.mark.unit
async def test_ollama_chat_sends_message_images_verbatim() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": "una mesa"}})

    message = {"role": "user", "content": "Describe", "images": ["QUJD"]}
    async with _mock_client(handler) as client:
        text = await llm_transport.ollama_chat(
            client, [message], model="vlm", options={"temperature": 0.3}, timeout=5.0
        )

    assert text == "una mesa"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["messages"] == [message]
    assert payload["options"] == {"temperature": 0.3}
    assert payload["stream"] is False
    assert "format" not in payload


@pytest.mark.unit
async def test_ollama_embed_posts_to_api_embed_and_returns_the_vector() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"embeddings": [[0.5, 1, 2.25]]})

    async with _mock_client(handler) as client:
        vector = await llm_transport.ollama_embed(client, "hola", model="nomic", timeout=5.0)

    assert vector == [0.5, 1.0, 2.25]
    assert str(captured["url"]).endswith("/api/embed")
    assert captured["payload"] == {"model": "nomic", "input": "hola"}


@pytest.mark.unit
@pytest.mark.parametrize(
    "body",
    [
        {},
        {"embeddings": []},
        {"embeddings": [None]},
        {"embeddings": [["x"]]},
        {"embeddings": [[True]]},
        ["not", "an", "object"],
    ],
)
async def test_ollama_embed_rejects_a_body_without_a_numeric_vector(body: object) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    async with _mock_client(handler) as client:
        with pytest.raises(LLMError):
            await llm_transport.ollama_embed(client, "hola", model="nomic")


@pytest.mark.unit
async def test_ollama_embed_wraps_a_non_json_body() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"nope")

    async with _mock_client(handler) as client:
        with pytest.raises(LLMError):
            await llm_transport.ollama_embed(client, "hola", model="nomic")
