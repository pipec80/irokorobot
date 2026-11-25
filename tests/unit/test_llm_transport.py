"""Unit tests for server.llm_transport: strip_json_fences, ollama_chat(_stream).

Plan 0039: ``ollama_chat``/``ollama_chat_stream`` now take an injected
``httpx.AsyncClient`` instead of constructing their own — tests build a real
client over ``httpx.MockTransport`` rather than monkeypatching the
``httpx.AsyncClient`` constructor.
"""

from collections.abc import AsyncIterator, Callable
import json
import logging

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


@pytest.mark.unit
async def test_ollama_embed_can_refuse_to_truncate() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"embeddings": [[0.5]]})

    async with _mock_client(handler) as client:
        await llm_transport.ollama_embed(client, "hola", model="nomic", truncate=False)

    assert captured["payload"] == {"model": "nomic", "input": "hola", "truncate": False}


@pytest.mark.unit
async def test_ollama_token_count_reads_the_prompt_eval_count() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"embeddings": [[0.5]], "prompt_eval_count": 7})

    async with _mock_client(handler) as client:
        count = await llm_transport.ollama_token_count(client, "hola", model="nomic")

    assert count == 7
    assert str(captured["payload"]).count("hola") == 1


@pytest.mark.unit
@pytest.mark.parametrize("body", [{"embeddings": [[0.5]]}, {"prompt_eval_count": "7"}, []])
async def test_ollama_token_count_rejects_a_body_without_a_count(body: object) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    async with _mock_client(handler) as client:
        with pytest.raises(LLMError):
            await llm_transport.ollama_token_count(client, "hola", model="nomic")


# --- Plan 0089 D-11: an Ollama failure says why, and a good answer says what it cost ---

_OOM = "model requires more system memory (5.1 GiB) than is available (3.2 GiB)"


def _failures(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "event", None) == "ollama.failed"]


@pytest.mark.unit
async def test_an_ollama_error_status_logs_its_cause_and_still_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": _OOM})

    async with _mock_client(handler) as client:
        with (
            caplog.at_level("WARNING", logger="server.llm_transport"),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await llm_transport.ollama_chat(client, [], model="qwen3-vl:2b-instruct")

    (record,) = _failures(caplog)
    assert record.status == 500  # type: ignore[attr-defined]  # set through ``extra``
    assert record.ollama_error == _OOM  # type: ignore[attr-defined]
    assert record.phase == "read"  # type: ignore[attr-defined]
    assert record.model == "qwen3-vl:2b-instruct"  # type: ignore[attr-defined]
    assert isinstance(record.elapsed_ms, int)  # type: ignore[attr-defined]
    assert _OOM in record.getMessage()


@pytest.mark.unit
@pytest.mark.parametrize(
    "error, phase",
    [
        (httpx.ConnectError("refused"), "connect"),
        (httpx.ConnectTimeout("no route"), "connect"),
        (httpx.ReadTimeout("slow"), "first_byte"),
    ],
)
async def test_a_transport_failure_logs_its_phase(
    error: httpx.HTTPError, phase: str, caplog: pytest.LogCaptureFixture
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise error

    async with _mock_client(handler) as client:
        with (
            caplog.at_level("WARNING", logger="server.llm_transport"),
            pytest.raises(type(error)),
        ):
            await llm_transport.ollama_chat(client, [], model="qwen2.5:3b")

    (record,) = _failures(caplog)
    assert record.phase == phase  # type: ignore[attr-defined]
    assert record.status is None  # type: ignore[attr-defined]
    assert record.error_type == type(error).__name__  # type: ignore[attr-defined]


@pytest.mark.unit
async def test_a_midstream_error_line_logs_ollama_s_text(caplog: pytest.LogCaptureFixture) -> None:
    handler = _stream_handler(
        ['{"message": {"content": "Hola"}}', '{"error": "model runner has unexpectedly stopped"}']
    )
    async with _mock_client(handler) as client:
        with (
            caplog.at_level("WARNING", logger="server.llm_transport"),
            pytest.raises(LLMError, match="mid-stream"),
        ):
            await _drain([], llm_transport.ollama_chat_stream(client, [], model="qwen2.5:3b"))

    (record,) = _failures(caplog)
    assert record.ollama_error == "model runner has unexpectedly stopped"  # type: ignore[attr-defined]
    assert record.phase == "read"  # type: ignore[attr-defined]


@pytest.mark.unit
async def test_an_error_status_on_a_stream_logs_its_cause(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": 'model "nope" not found, try pulling it first'})

    async with _mock_client(handler) as client:
        with (
            caplog.at_level("WARNING", logger="server.llm_transport"),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await _drain([], llm_transport.ollama_chat_stream(client, [], model="nope"))

    (record,) = _failures(caplog)
    assert record.status == 404  # type: ignore[attr-defined]
    assert "not found" in record.ollama_error  # type: ignore[attr-defined]


@pytest.mark.unit
async def test_ollama_s_error_text_is_cut_to_300_characters(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "x" * 900})

    async with _mock_client(handler) as client:
        with (
            caplog.at_level("WARNING", logger="server.llm_transport"),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await llm_transport.ollama_chat(client, [], model="qwen2.5:3b")

    (record,) = _failures(caplog)
    assert len(record.ollama_error) == 300  # type: ignore[attr-defined]


@pytest.mark.unit
async def test_a_non_json_error_body_logs_no_ollama_text(caplog: pytest.LogCaptureFixture) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>bad gateway</html>")

    async with _mock_client(handler) as client:
        with (
            caplog.at_level("WARNING", logger="server.llm_transport"),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await llm_transport.ollama_chat(client, [], model="qwen2.5:3b")

    (record,) = _failures(caplog)
    assert record.ollama_error is None  # type: ignore[attr-defined]


@pytest.mark.unit
def test_ollama_metrics_reads_durations_in_milliseconds() -> None:
    body = {
        "message": {"content": "x"},
        "total_duration": 2_500_000_000,
        "load_duration": 1_200_000_000,
        "prompt_eval_count": 812,
        "prompt_eval_duration": 900_000_000,
        "eval_count": 41,
        "eval_duration": 350_000_000,
    }
    assert llm_transport.ollama_metrics(body) == llm_transport.OllamaMetrics(
        load_ms=1200,
        prompt_eval_count=812,
        prompt_eval_ms=900,
        eval_count=41,
        eval_ms=350,
        total_ms=2500,
    )


@pytest.mark.unit
@pytest.mark.parametrize("body", [{"message": {"content": "x"}}, [], {"eval_count": "41"}])
def test_missing_or_bad_metrics_are_none(body: object) -> None:
    metrics = llm_transport.ollama_metrics(body)
    assert metrics == llm_transport.OllamaMetrics(None, None, None, None, None, None)


@pytest.mark.unit
async def test_ollama_chat_measured_returns_the_text_and_its_metrics() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"message": {"content": "hola"}, "eval_count": 3, "eval_duration": 4_000_000}
        )

    async with _mock_client(handler) as client:
        text, metrics = await llm_transport.ollama_chat_measured(client, [], model="qwen2.5:3b")

    assert text == "hola"
    assert metrics.eval_count == 3
    assert metrics.eval_ms == 4
