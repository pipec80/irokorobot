"""Channel-agnostic text turn orchestration."""

from collections.abc import Callable
from dataclasses import dataclass
import logging
import time

from server import llm
from server.exceptions import BrainMemoryError, LLMError
from server.memory import meta, working
from server.memory.context import build_context
from server.onboarding import OnboardingSlot, next_missing_slot
from server.schemas import ConversationTurn, MemoryContext
from server.settings import settings

logger = logging.getLogger(__name__)

ConsolidationScheduler = Callable[[str, str], None]

_onboarding_done = False


@dataclass(frozen=True)
class PreparedTextTurn:
    """Inputs resolved for one text generation."""

    message: str
    conversation_id: str
    context: MemoryContext | None
    history: list[ConversationTurn] | None
    onboarding: bool
    onboarding_slot: OnboardingSlot | None
    user_emotion: str | None
    owner_name: str | None
    perception: str | None


@dataclass(frozen=True)
class TextTurnResult:
    """Structured output from one completed text turn."""

    response: str
    emotion: str
    duration_ms: int
    llm_failed: bool


async def _needs_onboarding() -> bool:
    """Return whether persistent onboarding remains incomplete."""
    global _onboarding_done  # noqa: PLW0603
    if _onboarding_done:
        return False
    _onboarding_done = await meta.get_flag("onboarding_complete") == "true"
    return not _onboarding_done


async def _memory_prompt_state(
    message: str,
) -> tuple[MemoryContext | None, bool, OnboardingSlot | None, str | None]:
    """Resolve persistent prompt inputs, degrading on memory failure."""
    try:
        context = await build_context(message)
        onboarding = await _needs_onboarding()
        slot = await next_missing_slot() if onboarding else None
        if onboarding and slot is None:
            await meta.set_flag("onboarding_complete", "true")
            onboarding = False
            logger.info("Onboarding checklist complete — interview finished")
        owner_name = await meta.get_flag("owner_name")
        return context, onboarding, slot, owner_name
    except BrainMemoryError as exc:
        logger.warning("Memory unavailable — degrading to stateless turn: %s", exc)
        return None, False, None, None


async def prepare_text_turn(
    message: str,
    conversation_id: str,
    *,
    perception: str | None = None,
) -> PreparedTextTurn:
    """Resolve shared prompt inputs for one conversation.

    Args:
        message: Current user message.
        conversation_id: Ephemeral working-memory identifier.
        perception: Optional textual visual perception for this turn.

    Returns:
        Immutable inputs for one LLM generation.

    Raises:
        ValueError: If ``conversation_id`` is empty.
    """
    if not conversation_id:
        raise ValueError("conversation_id must not be empty")
    if not settings.memory_enabled:
        return PreparedTextTurn(
            message, conversation_id, None, None, False, None, None, None, perception
        )
    history = working.get_history(conversation_id)
    user_emotion = working.get_recent_emotion(conversation_id)
    context, onboarding, slot, owner_name = await _memory_prompt_state(message)
    return PreparedTextTurn(
        message,
        conversation_id,
        context,
        history,
        onboarding,
        slot,
        user_emotion,
        owner_name,
        perception,
    )


async def _generate(prepared: PreparedTextTurn) -> tuple[str, str, bool]:
    """Generate a response, degrading to the configured local phrase."""
    try:
        response, emotion = await llm.generate_response(
            prepared.message,
            context=prepared.context,
            history=prepared.history,
            onboarding=prepared.onboarding,
            onboarding_slot=prepared.onboarding_slot,
            user_emotion=prepared.user_emotion,
            owner_name=prepared.owner_name,
            perception=prepared.perception,
        )
        logger.info("LLM response: %r (emotion=%s)", response, emotion)
        return response, emotion, False
    except (LLMError, ValueError) as exc:
        logger.error("LLM failed — using fallback phrase: %s", exc, exc_info=True)
        return settings.llm_fallback_phrase, "neutral", True


def record_text_turn(
    message: str,
    conversation_id: str,
    response: str,
    emotion: str,
    *,
    schedule_consolidation: ConsolidationScheduler | None = None,
) -> None:
    """Record a successful turn and optionally schedule consolidation.

    Args:
        message: Current user message.
        conversation_id: Ephemeral working-memory identifier.
        response: Generated assistant response.
        emotion: Emotion detected during generation.
        schedule_consolidation: Optional channel-owned scheduling callback.
    """
    if not settings.memory_enabled:
        return
    working.add_emotion(conversation_id, emotion)
    working.add_turn(conversation_id, "user", message)
    working.add_turn(conversation_id, "assistant", response)
    if schedule_consolidation is not None:
        schedule_consolidation(message, response)


async def process_text_turn(
    message: str,
    conversation_id: str,
    *,
    perception: str | None = None,
    schedule_consolidation: ConsolidationScheduler | None = None,
) -> TextTurnResult:
    """Generate and record one channel-agnostic text turn.

    Args:
        message: Current user message.
        conversation_id: Ephemeral working-memory identifier.
        perception: Optional textual visual perception for this turn.
        schedule_consolidation: Optional channel-owned scheduling callback.

    Returns:
        Text, emotion, elapsed time, and fallback status for the turn.
    """
    started = time.perf_counter()
    prepared = await prepare_text_turn(message, conversation_id, perception=perception)
    response, emotion, llm_failed = await _generate(prepared)
    if not llm_failed:
        record_text_turn(
            message,
            conversation_id,
            response,
            emotion,
            schedule_consolidation=schedule_consolidation,
        )
    duration_ms = round((time.perf_counter() - started) * 1000)
    return TextTurnResult(response, emotion, duration_ms, llm_failed)
