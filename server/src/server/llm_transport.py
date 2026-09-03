"""Shared Ollama chat transport, used by llm.py and memory/consolidation.py.

Design note (R3): the conversation path (llm.py) and the consolidation path
(memory/consolidation.py) send Ollama completely different prompts/schemas —
chat wants ``{"response", "emotion"}``, consolidation wants a
``TurnExtraction`` JSON schema — so their payloads and parsing are NOT merged
here. What genuinely repeats byte-for-byte across both call sites (and a
third, non-chat one in vision/describe.py) is the transport itself: building
the ``httpx.AsyncClient``, the ``POST {ollama_url}/api/chat`` call,
``raise_for_status()``, reading ``resp.json()["message"]["content"]``, and
stripping ```json fences from the result. That transport layer — plus its
``stream=true`` NDJSON counterpart needed for R3's sentence-streaming TTS —
lives here as the single shared helper.
"""

from collections.abc import AsyncIterator
import json
import logging
from typing import Any

import httpx

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
    content: str = resp.json()["message"]["content"]
    return content


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
            delta = event.get("message", {}).get("content", "")
            if delta:
                yield delta
