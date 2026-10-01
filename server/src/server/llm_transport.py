"""Shared Ollama ``/api/chat`` transport helpers.

Used by llm.py, llm_streaming.py and memory/consolidation.py. Every caller
passes the lifespan-owned ``httpx.AsyncClient`` (Plan 0039); nothing here
constructs one. Building prompts and parsing the model's own output stay with
each caller: chat wants ``{"response", "emotion"}``, consolidation a
``TurnExtraction`` schema.
"""

from collections.abc import AsyncIterator
import json
import logging
from typing import Any

import httpx

from server.exceptions import LLMError
from server.settings import settings

logger = logging.getLogger(__name__)


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
    messages: list[dict[str, str]],
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
    messages: list[dict[str, str]],
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
