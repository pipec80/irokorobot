"""Local Ollama client for conversational response generation."""

import json
import logging
import re
from typing import Any

import httpx

from server.characters import build_system_prompt, get_character
from server.cognition.identity import ActivePersonContext
from server.exceptions import LLMError
from server.llm_transport import ollama_chat, strip_json_fences
from server.onboarding import OnboardingSlot
from server.schemas import ConversationTurn, MemoryContext
from server.settings import settings

logger = logging.getLogger(__name__)

# Public: shared with llm_streaming.py for its "EMOTION:xxx\n" tag protocol.
VALID_EMOTIONS = frozenset({"neutral", "joy", "anger", "sadness", "surprise"})
FALLBACK_EMOTION = "neutral"

# Salvage regex for malformed JSON — extracts response text so TTS never reads raw braces.
_RESPONSE_RE = re.compile(r'"response"\s*:\s*"((?:[^"\\]|\\.)*)"')

# JSON schema forced via Ollama structured outputs (mirrors the consolidation
# extractor); non-streaming path only. dict[str, Any]: heterogeneous JSON-schema literal.
_OLLAMA_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "response": {"type": "string"},
        "emotion": {"type": "string", "enum": sorted(VALID_EMOTIONS)},
    },
    "required": ["response", "emotion"],
}

# Sole owner of the classic contract — kept separate from llm_streaming.py's tag contract.
_CLASSIC_OUTPUT_CONTRACT = f"""

FORMATO — respondé SIEMPRE con JSON válido, sin texto adicional:
{{"response": "<tu respuesta en español>", "emotion": "<emoción del usuario>"}}
Emociones válidas: {", ".join(sorted(VALID_EMOTIONS))}.
La emoción describe el estado del USUARIO, no el tuyo."""


def _classic_system_prompt(base_prompt: str) -> str:
    """Append the classic JSON output contract to a format-neutral prompt.

    Args:
        base_prompt: Format-neutral prompt built by ``build_system_prompt``.

    Returns:
        The prompt with exactly one classic JSON contract appended.
    """
    return base_prompt + _CLASSIC_OUTPUT_CONTRACT


def _parse_llm_output(raw: str) -> tuple[str, str]:
    """Extract response text and emotion from model JSON output; falls back
    to raw text + neutral emotion when the JSON is malformed.

    Args:
        raw: Raw string from the model, expected to be valid JSON.

    Returns:
        Tuple of (response_text, emotion).
    """
    text = strip_json_fences(raw)
    try:
        data = json.loads(text)
        response_text = data["response"]
        emotion = data.get("emotion", FALLBACK_EMOTION).lower()
        if emotion not in VALID_EMOTIONS:
            logger.warning("Unknown emotion '%s' from LLM — defaulting to neutral", emotion)
            emotion = FALLBACK_EMOTION
        return response_text, emotion
    except (json.JSONDecodeError, KeyError) as exc:
        match = _RESPONSE_RE.search(text)
        if match:
            logger.warning("LLM returned malformed JSON (%s) — salvaged response field", exc)
            try:
                salvaged: str = json.loads(f'"{match.group(1)}"')
            except json.JSONDecodeError:
                salvaged = match.group(1)
            return salvaged, FALLBACK_EMOTION
        logger.warning("LLM returned non-JSON output (%s) — using raw text", exc)
        return raw, FALLBACK_EMOTION


async def _generate_ollama(
    client: httpx.AsyncClient, system_prompt: str, messages: list[dict[str, str]]
) -> tuple[str, str]:
    """Call local Ollama API.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039).
        system_prompt: Full system prompt including any memory context.
        messages: Conversation messages (history + current turn).

    Returns:
        Tuple of (response_text, emotion).

    Raises:
        LLMError: If the Ollama server is unreachable or returns an error.
    """
    raw = await ollama_chat(
        client,
        [{"role": "system", "content": system_prompt}, *messages],
        model=settings.ollama_model,
        format_schema=_OLLAMA_RESPONSE_SCHEMA,
        timeout=settings.ollama_timeout_s,
    )
    return _parse_llm_output(raw)


def _build_messages(text: str, history: list[ConversationTurn] | None) -> list[dict[str, str]]:
    """Build the messages array from conversation history and current turn."""
    messages: list[dict[str, str]] = []
    if history:
        messages.extend({"role": turn.role, "content": turn.content} for turn in history)
    messages.append({"role": "user", "content": text})
    return messages


def _build_classic_base_prompt(
    context: MemoryContext | None,
    *,
    onboarding: bool,
    onboarding_slot: OnboardingSlot | None,
    user_emotion: str | None,
    active_person: ActivePersonContext | None,
    perception: str | None,
) -> str:
    """Build the format-neutral base prompt for the classic /transcribe path.

    Resolves the character, then only calls ``build_system_prompt`` — output
    format stays owned by ``_classic_system_prompt``. Args match ``generate_response``.

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
        perception=perception,
    )


async def generate_response(
    client: httpx.AsyncClient,
    text: str,
    *,
    context: MemoryContext | None = None,
    history: list[ConversationTurn] | None = None,
    onboarding: bool = False,
    onboarding_slot: OnboardingSlot | None = None,
    user_emotion: str | None = None,
    active_person: ActivePersonContext | None = None,
    perception: str | None = None,
) -> tuple[str, str]:
    """Generate a robot response and detect the user's emotion in one local Ollama call.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039).
        text: Transcribed user speech.
        context: Optional memory context for the system prompt (``None`` = no memory).
        history: Optional recent conversation turns (oldest first, already trimmed).
        onboarding: If ``True``, asks first-run introductory questions.
        onboarding_slot: Next onboarding checklist slot; names the ONE datum to ask.
        user_emotion: Dominant recent user emotion; adds a tone-adaptation directive.
        active_person: Resolved person context; guides neutral presentation.
        perception: Camera VLM description this turn, injected as a perception block (V0.5).

    Returns:
        Tuple of (response_text, emotion) — see ``VALID_EMOTIONS`` for valid values.

    Raises:
        LLMError: If the local Ollama API call fails.
        ValueError: If text is empty.
    """
    if not text:
        raise ValueError("Input text is empty")

    base_prompt = _build_classic_base_prompt(
        context,
        onboarding=onboarding,
        onboarding_slot=onboarding_slot,
        user_emotion=user_emotion,
        active_person=active_person,
        perception=perception,
    )
    system_prompt = _classic_system_prompt(base_prompt)
    messages = _build_messages(text, history)

    try:
        logger.info("LLM provider: ollama (%s)", settings.ollama_model)
        response_text, emotion = await _generate_ollama(client, system_prompt, messages)
        logger.info("LLM response (%d chars) emotion=%s", len(response_text), emotion)
        return response_text, emotion
    except (LLMError, ValueError):
        raise
    except Exception as exc:
        raise LLMError("LLM API call failed") from exc
