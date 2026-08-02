"""Unit tests for server.llm_transport: strip_json_fences, ollama_chat(_stream)."""

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


class _FakeResponse:
    """Minimal stand-in for httpx.Response, non-streaming path."""

    def __init__(self, content: str) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, object]:
        return {"message": {"content": self._content}}


class _FakeAsyncClient:
    """Minimal stand-in for httpx.AsyncClient — captures the last POST payload."""

    last_payload: dict[str, object] | None = None

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def post(self, _url: str, json: dict[str, object]) -> _FakeResponse:
        _FakeAsyncClient.last_payload = json
        return _FakeResponse("hola humano")


@pytest.mark.unit
async def test_ollama_chat_returns_message_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_transport.httpx, "AsyncClient", _FakeAsyncClient)
    result = await llm_transport.ollama_chat(
        [{"role": "user", "content": "hola"}], model="qwen2.5:3b"
    )
    assert result == "hola humano"
    assert _FakeAsyncClient.last_payload is not None
    assert _FakeAsyncClient.last_payload["stream"] is False
    assert _FakeAsyncClient.last_payload["model"] == "qwen2.5:3b"


@pytest.mark.unit
async def test_ollama_chat_includes_format_and_options_when_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm_transport.httpx, "AsyncClient", _FakeAsyncClient)
    schema = {"type": "object"}
    await llm_transport.ollama_chat(
        [{"role": "user", "content": "hola"}],
        model="qwen2.5:3b",
        format_schema=schema,
        options={"temperature": 0.1},
    )
    payload = _FakeAsyncClient.last_payload
    assert payload is not None
    assert payload["format"] == schema
    assert payload["options"] == {"temperature": 0.1}


@pytest.mark.unit
async def test_ollama_chat_omits_format_when_not_given(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_transport.httpx, "AsyncClient", _FakeAsyncClient)
    await llm_transport.ollama_chat([{"role": "user", "content": "hola"}], model="qwen2.5:3b")
    payload = _FakeAsyncClient.last_payload
    assert payload is not None
    assert "format" not in payload
    assert "options" not in payload


class _FakeStreamResponse:
    """Minimal stand-in for the object yielded by httpx.AsyncClient.stream()."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    async def __aenter__(self) -> "_FakeStreamResponse":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    def raise_for_status(self) -> None:
        pass

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStreamingAsyncClient(_FakeAsyncClient):
    """Adds a fake .stream() context manager on top of _FakeAsyncClient."""

    lines: list[str] = []

    def stream(self, _method: str, _url: str, json: dict[str, object]) -> _FakeStreamResponse:
        _FakeAsyncClient.last_payload = json
        return _FakeStreamResponse(_FakeStreamingAsyncClient.lines)


@pytest.mark.unit
async def test_ollama_chat_stream_yields_content_deltas(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeStreamingAsyncClient.lines = [
        '{"message": {"content": "Hola"}}',
        '{"message": {"content": " mundo"}}',
        '{"done": true}',
    ]
    monkeypatch.setattr(llm_transport.httpx, "AsyncClient", _FakeStreamingAsyncClient)
    deltas = [d async for d in llm_transport.ollama_chat_stream([], model="qwen2.5:3b")]
    assert deltas == ["Hola", " mundo"]


@pytest.mark.unit
async def test_ollama_chat_stream_skips_blank_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeStreamingAsyncClient.lines = [
        "",
        '{"message": {"content": "Hola"}}',
        "   ",
    ]
    monkeypatch.setattr(llm_transport.httpx, "AsyncClient", _FakeStreamingAsyncClient)
    deltas = [d async for d in llm_transport.ollama_chat_stream([], model="qwen2.5:3b")]
    assert deltas == ["Hola"]


@pytest.mark.unit
async def test_ollama_chat_stream_sets_stream_true(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeStreamingAsyncClient.lines = []
    monkeypatch.setattr(llm_transport.httpx, "AsyncClient", _FakeStreamingAsyncClient)
    async for _ in llm_transport.ollama_chat_stream([], model="qwen2.5:3b"):
        pass
    payload = _FakeAsyncClient.last_payload
    assert payload is not None
    assert payload["stream"] is True
