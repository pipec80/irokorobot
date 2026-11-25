"""Shared Ollama transport: the one place that talks HTTP to Ollama.

Chat (``/api/chat``, plain and streaming), embeddings (``/api/embed``) and the
start-up reachability check (``/api/tags``) live here; llm.py, llm_streaming.py, memory/consolidation.py,
memory/candidate_extraction.py, the recall index and search (``memory/recall_index.py``,
``memory/recall_search.py``) and vision/describe.py all reach Ollama through these helpers, and
``tests/unit/test_ollama_seam.py`` keeps it that way. Every caller
passes the lifespan-owned ``httpx.AsyncClient`` (Plan 0039); nothing here
constructs one. Building prompts and parsing the model's own output stay with
each caller: chat wants ``{"response", "emotion"}``, consolidation a
``TurnExtraction`` schema.
"""

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
import json
import logging
import time
from typing import Any, Final

import httpx

from server.exceptions import LLMError
from server.settings import settings

logger = logging.getLogger(__name__)

#: One Ollama chat message: ``role`` and ``content`` strings, plus an ``images``
#: list of base64 strings on a multimodal (VLM) turn.
type ChatMessage = Mapping[str, str | list[str]]

#: The longest piece of Ollama's own ``error`` text a log line keeps (Plan 0089 D-11).
_ERROR_TEXT_MAX: Final = 300
_NS_PER_MS: Final = 1_000_000


@dataclass(frozen=True)
class OllamaMetrics:
    """What one Ollama answer cost, from the fields Ollama returns with it (Plan 0089 D-11).

    Durations are in milliseconds and counts in tokens; a field Ollama did not send is ``None``.
    ``load_ms`` separates loading the model from thinking (``prompt_eval_ms`` and ``eval_ms``).
    """

    load_ms: int | None
    prompt_eval_count: int | None
    prompt_eval_ms: int | None
    eval_count: int | None
    eval_ms: int | None
    total_ms: int | None


def ollama_metrics(body: object) -> OllamaMetrics:
    """Read the duration and count fields of one decoded Ollama answer.

    Args:
        body: One decoded ``/api/chat`` body, or the final line of a stream.

    Returns:
        The metrics; each missing or non-integer field is ``None``.
    """
    fields = body if isinstance(body, dict) else {}

    def number(key: str) -> int | None:
        value = fields.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    def millis(key: str) -> int | None:
        value = number(key)
        return None if value is None else value // _NS_PER_MS

    return OllamaMetrics(
        load_ms=millis("load_duration"),
        prompt_eval_count=number("prompt_eval_count"),
        prompt_eval_ms=millis("prompt_eval_duration"),
        eval_count=number("eval_count"),
        eval_ms=millis("eval_duration"),
        total_ms=millis("total_duration"),
    )


def _error_text(body: object) -> str | None:
    """Ollama's own ``error`` field, cut to its log length; ``None`` when there is none."""
    error = body.get("error") if isinstance(body, dict) else None
    return error[:_ERROR_TEXT_MAX] if isinstance(error, str) else None


def _response_error_text(response: httpx.Response) -> str | None:
    """The ``error`` field of a read error response; ``None`` for a body that is not JSON."""
    try:
        return _error_text(response.json())
    except ValueError:
        return None


def _phase(exc: httpx.HTTPError) -> str:
    """Name the phase a transport failure happened in: ``connect``, ``first_byte`` or ``read``."""
    match exc:
        case httpx.ConnectError() | httpx.ConnectTimeout():
            return "connect"
        case httpx.ReadTimeout():
            return "first_byte"
        case _:
            return "read"


def _log_failure(
    *,
    model: str,
    started: float,
    phase: str,
    error_type: str,
    status: int | None = None,
    ollama_error: str | None = None,
) -> None:
    """Log why one Ollama call failed: never a prompt, a message or an image (Plan 0089 D-11).

    Ollama's ``error`` text is its own diagnosis (a model that needs more memory, a runner that
    stopped); it never echoes the request's content.
    """
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.warning(
        "Ollama call failed: model=%s phase=%s status=%s error=%s elapsed_ms=%d (%s)",
        model,
        phase,
        status,
        error_type,
        elapsed_ms,
        ollama_error,
        extra={
            "event": "ollama.failed",
            "model": model,
            "phase": phase,
            "status": status,
            "error_type": error_type,
            "elapsed_ms": elapsed_ms,
            "ollama_error": ollama_error,
        },
    )


def _log_http_error(exc: httpx.HTTPError, *, model: str, started: float) -> None:
    """Log one failed request with its phase, and the status and Ollama's text when it answered."""
    if isinstance(exc, httpx.HTTPStatusError):
        _log_failure(
            model=model,
            started=started,
            phase="read",
            error_type=type(exc).__name__,
            status=exc.response.status_code,
            ollama_error=_response_error_text(exc.response),
        )
        return
    _log_failure(model=model, started=started, phase=_phase(exc), error_type=type(exc).__name__)


def strip_json_fences(raw: str) -> str:
    """Strip a ```json ... ``` (or plain ``` ... ```) markdown fence, if present.

    Small local models often wrap structured output in a markdown code fence
    even when instructed not to; downstream JSON parsing needs the bare text.

    Args:
        raw: Raw model output, possibly fenced.

    Returns:
        The text with any leading/trailing fence markers removed and stripped.
    """
    return raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()


def message_content(payload: object) -> str:
    """Return ``message.content`` from one decoded Ollama ``/api/chat`` object.

    Args:
        payload: One decoded JSON response body or NDJSON stream line.

    Returns:
        The message text, possibly empty.

    Raises:
        LLMError: If the object carries no string ``message.content``.
    """
    message = payload.get("message") if isinstance(payload, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise LLMError("Ollama response carries no text message content")
    return content


async def ollama_chat(
    client: httpx.AsyncClient,
    messages: Sequence[ChatMessage],
    *,
    model: str,
    format_schema: dict[str, Any] | None = None,  # Any: JSON-schema literal, heterogeneous
    options: dict[str, float] | None = None,
    timeout: float | None = None,
) -> str:
    """Call Ollama's ``/api/chat`` non-streaming and return the raw message content.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039) — never
            constructed here.
        messages: Full messages array (system + history + current turn).
        model: Ollama model name to call.
        format_schema: Optional JSON schema forcing structured output.
        options: Optional Ollama generation options (e.g. ``{"temperature": 0.1}``).
        timeout: Optional per-request timeout override, in seconds, applied
            to every phase of this one call — inference regularly runs
            longer than the client's own general-purpose default.

    Returns:
        Raw ``message.content`` string from the response — not yet fence-stripped
        or parsed, callers decide how to interpret it.

    Raises:
        httpx.HTTPError: If the Ollama server is unreachable or returns an error.
        LLMError: If the response body is not JSON or carries no text content.
    """
    content, _metrics = await ollama_chat_measured(
        client, messages, model=model, format_schema=format_schema, options=options, timeout=timeout
    )
    return content


async def ollama_chat_measured(
    client: httpx.AsyncClient,
    messages: Sequence[ChatMessage],
    *,
    model: str,
    format_schema: dict[str, Any] | None = None,  # Any: JSON-schema literal, heterogeneous
    options: dict[str, float] | None = None,
    timeout: float | None = None,
) -> tuple[str, OllamaMetrics]:
    """Call ``/api/chat`` non-streaming; return the content and what the answer cost.

    The same call as ``ollama_chat`` (whose arguments these are); a failed request is logged
    once with its phase, status and Ollama's own error text, then re-raised unchanged
    (Plan 0089 D-11).

    Returns:
        ``(content, metrics)``: the raw ``message.content`` and the answer's ``OllamaMetrics``.

    Raises:
        httpx.HTTPError: If the Ollama server is unreachable or returns an error.
        LLMError: If the response body is not JSON or carries no text content.
    """
    url = f"{settings.ollama_url}/api/chat"
    payload: dict[str, Any] = {  # Any: heterogeneous Ollama request payload
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if format_schema is not None:
        payload["format"] = format_schema
    if options is not None:
        payload["options"] = options
    started = time.perf_counter()
    try:
        resp = await client.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        _log_http_error(exc, model=model, started=started)
        raise
    try:
        body: object = resp.json()
    except ValueError as exc:
        raise LLMError("Ollama returned a non-JSON response") from exc
    return message_content(body), ollama_metrics(body)


async def ollama_chat_stream(
    client: httpx.AsyncClient,
    messages: Sequence[ChatMessage],
    *,
    model: str,
    options: dict[str, float] | None = None,
    timeout: float | None = None,
) -> AsyncIterator[str]:
    """Call Ollama's ``/api/chat`` with ``stream=true`` and yield content deltas.

    Ollama streams one NDJSON object per line, each carrying a partial
    ``message.content`` token/chunk; the final line has ``"done": true``.
    No ``format`` (structured-output) schema here — that mode disables
    Ollama's token streaming, and R3's whole point is to synthesize speech
    before the full response is generated.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039) — never
            constructed here.
        messages: Full messages array (system + history + current turn).
        model: Ollama model name to call.
        options: Optional Ollama generation options.
        timeout: Optional per-request timeout override, in seconds — see
            ``ollama_chat``.

    Yields:
        Successive ``message.content`` deltas as they arrive.

    Raises:
        httpx.HTTPError: If the Ollama server is unreachable or returns an error.
        LLMError: If a line reports an error or carries no text message content.
    """
    url = f"{settings.ollama_url}/api/chat"
    payload: dict[str, Any] = {  # Any: heterogeneous Ollama request payload
        "model": model,
        "messages": messages,
        "stream": True,
    }
    if options is not None:
        payload["options"] = options
    started = time.perf_counter()
    try:
        async with client.stream("POST", url, json=payload, timeout=timeout) as resp:
            if resp.is_error:
                await resp.aread()  # the error body holds Ollama's own cause
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                event = json.loads(line)
                if isinstance(event, dict) and "error" in event:
                    _log_failure(
                        model=model,
                        started=started,
                        phase="read",
                        error_type="LLMError",
                        ollama_error=_error_text(event),
                    )
                    raise LLMError("Ollama reported an error mid-stream")
                if isinstance(event, dict) and "message" not in event:
                    continue
                delta = message_content(event)
                if delta:
                    yield delta
    except httpx.HTTPError as exc:
        _log_http_error(exc, model=model, started=started)
        raise


async def ollama_embed(
    client: httpx.AsyncClient,
    text: str,
    *,
    model: str,
    timeout: float | None = None,
    truncate: bool = True,
) -> list[float]:
    """Call Ollama's ``/api/embed`` for one text and return its embedding vector.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039) — never
            constructed here.
        text: Non-empty text to embed.
        model: Ollama embedding model name.
        timeout: Optional per-request timeout override, in seconds.
        truncate: ``False`` asks Ollama to refuse a text longer than the model's window
            (HTTP 400) instead of cutting it silently (Plan 0088 D-10); the default sends no
            field, as before.

    Returns:
        The first embedding of the response, as floats. Its length is the
        caller's contract to check.

    Raises:
        httpx.HTTPError: If the Ollama server is unreachable or returns an error.
        LLMError: If the body is not JSON or carries no numeric vector.
    """
    payload: dict[str, object] = {"model": model, "input": text}
    if not truncate:
        payload["truncate"] = False
    body = await _embed_body(client, payload, timeout=timeout)
    embeddings = body.get("embeddings") if isinstance(body, dict) else None
    vector = embeddings[0] if isinstance(embeddings, list) and embeddings else None
    if not isinstance(vector, list) or not all(
        isinstance(value, int | float) and not isinstance(value, bool) for value in vector
    ):
        raise LLMError("Ollama embedding response carries no numeric vector")
    return [float(value) for value in vector]


async def ollama_token_count(
    client: httpx.AsyncClient, text: str, *, model: str, timeout: float | None = None
) -> int:
    """Count the tokens the embedding model reads of *text* (Plan 0088 D-10).

    Ollama's ``/api/embed`` reports ``prompt_eval_count``, special tokens included, capped at the
    model's window: a count at the window means the text reaches or passes it.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039).
        text: Non-empty text.
        model: Ollama embedding model name.
        timeout: Optional per-request timeout override, in seconds.

    Returns:
        The token count.

    Raises:
        httpx.HTTPError: If the Ollama server is unreachable or returns an error.
        LLMError: If the body is not JSON or carries no integer count.
    """
    body = await _embed_body(client, {"model": model, "input": text}, timeout=timeout)
    count = body.get("prompt_eval_count") if isinstance(body, dict) else None
    if not isinstance(count, int) or isinstance(count, bool):
        raise LLMError("Ollama embedding response carries no token count")
    return count


async def _embed_body(
    client: httpx.AsyncClient, payload: dict[str, object], *, timeout: float | None
) -> object:
    """POST one ``/api/embed`` request and return its decoded JSON body; log a failed request."""
    started = time.perf_counter()
    try:
        resp = await client.post(f"{settings.ollama_url}/api/embed", json=payload, timeout=timeout)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        _log_http_error(exc, model=str(payload.get("model")), started=started)
        raise
    try:
        return resp.json()
    except ValueError as exc:
        raise LLMError("Ollama returned a non-JSON response") from exc


async def check_reachable(client: httpx.AsyncClient) -> None:
    """Call Ollama's ``/api/tags`` once to see whether it answers.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039) — never
            constructed here.

    Raises:
        httpx.HTTPError: If the Ollama server is unreachable or returns an error.
        httpx.InvalidURL: If ``settings.ollama_url`` is not a valid URL.
    """
    resp = await client.get(f"{settings.ollama_url}/api/tags")
    resp.raise_for_status()
