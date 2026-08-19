"""Ollama-only streaming variant of llm.generate_response (R3).

llm.generate_response() returns a finished (text, emotion) tuple — there is
no seam to emit per-sentence audio while the model is still generating. The
JSON schema it forces via Ollama structured outputs ({"response", "emotion"})
is not streameable either: Ollama withholds structured output until the full
object is ready, defeating the point of streaming.

This module trades the JSON contract for a streaming-friendly one: the model
is asked to prefix its plain-text answer with "EMOTION:<emotion>\\n" on its
own first line, then answer normally. generate_response_stream() yields raw
text deltas as they arrive; parse_streaming_emotion() extracts the emotion
tag once the caller has buffered up to the first newline. Kept as a separate
module (not added to llm.py) so llm.py stays under the file size limit and
the non-streaming contract used by POST /transcribe is untouched.

Streaming is local-only: it uses the configured Ollama model and yields its
token deltas to the sentence-streaming pipeline.
"""

from collections.abc import AsyncIterator
import json

import httpx

from server.characters import build_system_prompt, get_character
from server.cognition.identity import ActivePersonContext
from server.exceptions import LLMError
from server.llm import VALID_EMOTIONS
from server.llm_transport import ollama_chat_stream
from server.onboarding import OnboardingSlot
from server.schemas import ConversationTurn, MemoryContext
from server.settings import settings

# Re-exported temporarily so existing call sites/tests can keep resolving
# the streaming protocol from this module. Task 3 moves the orchestration
# call-sites in streaming.py to import from streaming_protocol directly.
from server.streaming_protocol import (  # noqa: F401
    parse_streaming_emotion,
    validate_streaming_body_start,
)

# Sole owner of the streaming /transcribe/stream output contract.
# build_system_prompt is format-neutral (identity/behavior only) — this is
# the ONLY place the streaming EMOTION-tag contract is appended, so the
# model never sees it mixed with the classic JSON contract from llm.py.
_STREAMING_OUTPUT_CONTRACT = (
    "\n\nResponde en texto plano (sin JSON). La primera línea debe ser "
    "exactamente 'EMOTION:<emocion>' donde <emocion> es una de: "
    f"{', '.join(sorted(VALID_EMOTIONS))}. Después de esa línea, escribí tu "
    "respuesta normal."
)


def _streaming_system_prompt(base_prompt: str) -> str:
    """Append the streaming emotion-tag output contract to a format-neutral prompt.

    Args:
        base_prompt: Format-neutral prompt built by ``build_system_prompt``.

    Returns:
        The prompt with exactly one streaming protocol instruction appended.
    """
    return base_prompt + _STREAMING_OUTPUT_CONTRACT


def _build_messages(text: str, history: list[ConversationTurn] | None) -> list[dict[str, str]]:
    """Build the messages array from conversation history and current turn.

    Duplicated (not imported) from llm.py's private helper of the same
    shape — trivial 4-line logic, not worth widening llm.py's public API
    for a single extra call site.
    """
    messages: list[dict[str, str]] = []
    if history:
        messages.extend({"role": turn.role, "content": turn.content} for turn in history)
    messages.append({"role": "user", "content": text})
    return messages


def _build_streaming_base_prompt(
    context: MemoryContext | None,
    *,
    onboarding: bool,
    onboarding_slot: OnboardingSlot | None,
    user_emotion: str | None,
    active_person: ActivePersonContext | None,
) -> str:
    """Build the format-neutral base prompt for the streaming path.

    Only calls ``build_system_prompt`` — output-format ownership stays in
    ``_streaming_system_prompt``.

    Args:
        context: Optional memory context, same as ``llm.generate_response``.
        onboarding: Whether onboarding is in progress.
        onboarding_slot: Next onboarding checklist slot, if any.
        user_emotion: Dominant recent user emotion, if any.
        active_person: Internally resolved person context for this turn, if any.

    Returns:
        Format-neutral system prompt string.
    """
    character = get_character(settings.robot_character)
    return build_system_prompt(
        character,
        context,
        onboarding=onboarding,
        onboarding_slot=onboarding_slot,
        user_emotion=user_emotion,
        active_person=active_person,
    )


async def _stream_local_response(messages: list[dict[str, str]]) -> AsyncIterator[str]:
    """Stream raw text deltas from the local Ollama model.

    Owns only the Ollama streaming transport — prompt/contract assembly is
    the caller's responsibility.

    Args:
        messages: Full messages array (system + history + current turn).

    Yields:
        Raw text deltas as Ollama generates them.

    Raises:
        LLMError: If local Ollama streaming fails or emits invalid NDJSON.
    """
    try:
        async for delta in ollama_chat_stream(messages, model=settings.ollama_model):
            yield delta
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise LLMError("Local Ollama streaming failed") from exc


async def generate_response_stream(
    text: str,
    *,
    context: MemoryContext | None = None,
    history: list[ConversationTurn] | None = None,
    onboarding: bool = False,
    onboarding_slot: OnboardingSlot | None = None,
    user_emotion: str | None = None,
    active_person: ActivePersonContext | None = None,
) -> AsyncIterator[str]:
    """Stream a robot response token-by-token via Ollama.

    Args:
        text: Transcribed user speech.
        context: Optional memory context, same as ``llm.generate_response``.
        history: Optional recent conversation turns.
        onboarding: Whether onboarding is in progress.
        onboarding_slot: Next onboarding checklist slot, if any.
        user_emotion: Dominant recent user emotion, if any.
        active_person: Internally resolved person context for this turn, if any.

    Yields:
        Raw text deltas as Ollama generates them. The first delta(s) carry
        the ``EMOTION:xxx\\n`` tag inline — use ``parse_streaming_emotion``
        once enough has been buffered to see the first newline.

    Raises:
        ValueError: If text is empty.
        LLMError: If local Ollama streaming fails or emits invalid NDJSON.
    """
    if not text:
        raise ValueError("Input text is empty")

    base_prompt = _build_streaming_base_prompt(
        context,
        onboarding=onboarding,
        onboarding_slot=onboarding_slot,
        user_emotion=user_emotion,
        active_person=active_person,
    )
    system_prompt = _streaming_system_prompt(base_prompt)
    messages = _build_messages(text, history)
    async for delta in _stream_local_response(
        [{"role": "system", "content": system_prompt}, *messages]
    ):
        yield delta
