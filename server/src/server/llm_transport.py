"""Shared Ollama transport: the one place that talks HTTP to Ollama.

Chat (``/api/chat``, plain and streaming) and embeddings (``/api/embed``) live
here; llm.py, llm_streaming.py, memory/consolidation.py, memory/embeddings.py
and vision/describe.py all reach Ollama through these helpers, and
``tests/unit/test_ollama_seam.py`` keeps it that way. Every caller
passes the lifespan-owned ``httpx.AsyncClient`` (Plan 0039); nothing here
constructs one. Building prompts and parsing the model's own output stay with
each caller: chat wants ``{"response", "emotion"}``, consolidation a
``TurnExtraction`` schema.
"""

from collections.abc import AsyncIterator, Mapping, Sequence
import json
import logging
from typing import Any

import httpx

from server.exceptions import LLMError
from server.settings import settings

logger = logging.getLogger(__name__)

#: One Ollama chat message: ``role`` and ``content`` strings, plus an ``images``
#: list of base64 strings on a multimodal (VLM) turn.
type ChatMessage = Mapping[str, str | list[str]]


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
    resp = await client.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    try:
        body: object = resp.json()
    except ValueError as exc:
        raise LLMError("Ollama returned a non-JSON response") from exc
    return message_content(body)


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
    async with client.stream("POST", url, json=payload, timeout=timeout) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line.strip():
                continue
            event = json.loads(line)
            if isinstance(event, dict) and "error" in event:
                raise LLMError("Ollama reported an error mid-stream")
            if isinstance(event, dict) and "message" not in event:
                continue
            delta = message_content(event)
            if delta:
                yield delta


async def ollama_embed(
    client: httpx.AsyncClient,
    text: str,
    *,
    model: str,
    timeout: float | None = None,
) -> list[float]:
    """Call Ollama's ``/api/embed`` for one text and return its embedding vector.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039) — never
            constructed here.
        text: Non-empty text to embed.
        model: Ollama embedding model name.
        timeout: Optional per-request timeout override, in seconds.

    Returns:
        The first embedding of the response, as floats. Its length is the
        caller's contract to check.

    Raises:
        httpx.HTTPError: If the Ollama server is unreachable or returns an error.
        LLMError: If the body is not JSON or carries no numeric vector.
    """
    url = f"{settings.ollama_url}/api/embed"
    resp = await client.post(url, json={"model": model, "input": text}, timeout=timeout)
    resp.raise_for_status()
    try:
        body: object = resp.json()
    except ValueError as exc:
        raise LLMError("Ollama returned a non-JSON response") from exc
    embeddings = body.get("embeddings") if isinstance(body, dict) else None
    vector = embeddings[0] if isinstance(embeddings, list) and embeddings else None
    if not isinstance(vector, list) or not all(
        isinstance(value, int | float) and not isinstance(value, bool) for value in vector
    ):
        raise LLMError("Ollama embedding response carries no numeric vector")
    return [float(value) for value in vector]
