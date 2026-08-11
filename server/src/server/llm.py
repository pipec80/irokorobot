"""Local Ollama client for conversational response generation."""

import json
import logging
import re
from typing import Any

from server.characters import build_system_prompt, get_character
from server.cognition.identity import ActivePersonContext
from server.exceptions import LLMError
from server.llm_transport import ollama_chat, strip_json_fences
from server.onboarding import OnboardingSlot
from server.schemas import ConversationTurn, MemoryContext
from server.settings import settings

logger = logging.getLogger(__name__)

# Public: shared with llm_streaming.py, which needs the same emotion
# vocabulary for its "EMOTION:xxx\n" streaming tag protocol.
VALID_EMOTIONS = frozenset({"neutral", "joy", "anger", "sadness", "surprise"})
FALLBACK_EMOTION = "neutral"

# Salvage pattern for malformed JSON: extracts the "response" string value so
# the TTS never reads braces and quotes aloud.
_RESPONSE_RE = re.compile(r'"response"\s*:\s*"((?:[^"\\]|\\.)*)"')

# JSON schema forced via Ollama structured outputs — small models drift into
# free text otherwise (observed with qwen2.5:3b during QA). Mirrors the
# approach already used by the consolidation extractor. Only used by the
# non-streaming path: Ollama disables token streaming while this is set.
# dict[str, Any]: JSON-schema literal, heterogeneous by nature.
_OLLAMA_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "response": {"type": "string"},
        "emotion": {"type": "string", "enum": sorted(VALID_EMOTIONS)},
    },
    "required": ["response", "emotion"],
}


def _parse_llm_output(raw: str) -> tuple[str, str]:
    """Extract response text and emotion from model JSON output.

    Falls back to raw text + neutral emotion if JSON is malformed.

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
    system_prompt: str,
    messages: list[dict[str, str]],
) -> tuple[str, str]:
    """Call local Ollama API.

    Args:
        system_prompt: Full system prompt including any memory context.
        messages: Conversation messages (history + current turn).

    Returns:
        Tuple of (response_text, emotion).

    Raises:
        LLMError: If the Ollama server is unreachable or returns an error.
    """
    raw = await ollama_chat(
        [{"role": "system", "content": system_prompt}, *messages],
        model=settings.ollama_model,
        format_schema=_OLLAMA_RESPONSE_SCHEMA,
    )
    return _parse_llm_output(raw)


def _build_messages(
    text: str,
    history: list[ConversationTurn] | None,
) -> list[dict[str, str]]:
    """Build the messages array from conversation history and current turn."""
    messages: list[dict[str, str]] = []
    if history:
        messages.extend({"role": turn.role, "content": turn.content} for turn in history)
    messages.append({"role": "user", "content": text})
    return messages


async def generate_response(
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
    """Generate a robot response and detect the user's emotion.

    Uses local Ollama in one model call for response and emotion detection.

    Args:
        text: Transcribed user speech.
        context: Optional declarative entities and semantic memories to inject
            as system context. When ``None``, behaves as before (no memory).
        history: Optional recent conversation turns (oldest first) appended
            to the messages array. Working-memory deque already trims to N.
        onboarding: If ``True``, Iroko is meeting the owner for the first time
            and will ask introductory questions.
        onboarding_slot: Next missing checklist slot during onboarding. The
            prompt names the ONE datum to ask for this turn.
        user_emotion: Dominant non-neutral emotion from recent turns. When
            provided, the system prompt includes a behavioral adaptation
            directive so the robot adjusts its tone accordingly.
        active_person: Internally resolved person context for this turn. Its
            display name can guide neutral presentation when identified.
        perception: What the camera sees this turn (VLM description) —
            injected as a visual-perception block (V0.5).

    Returns:
        Tuple of (response_text, emotion). Emotion is one of:
        neutral, joy, anger, sadness, surprise.

    Raises:
        LLMError: If the local Ollama API call fails.
        ValueError: If text is empty.
    """
    if not text:
        raise ValueError("Input text is empty")

    character = get_character(settings.robot_character)
    system_prompt = build_system_prompt(
        character,
        context,
        onboarding=onboarding,
        onboarding_slot=onboarding_slot,
        user_emotion=user_emotion,
        active_person=active_person,
        perception=perception,
    )

    messages = _build_messages(text, history)

    try:
        logger.info("LLM provider: ollama (%s)", settings.ollama_model)
        response_text, emotion = await _generate_ollama(
            system_prompt,
            messages,
        )
        logger.info(
            "LLM response (%d chars) emotion=%s",
            len(response_text),
            emotion,
        )
        return response_text, emotion
    except (LLMError, ValueError):
        raise
    except Exception as exc:
        raise LLMError("LLM API call failed") from exc
