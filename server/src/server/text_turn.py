"""Channel-agnostic text turn orchestration."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import inspect
import logging
import time
from typing import cast
from uuid import uuid4

from server import llm
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    IdentityEvidence,
    IdentityEvidenceSource,
    resolve_active_person,
)
from server.exceptions import BrainMemoryError, LLMError
from server.memory import working
from server.memory.context import build_context
from server.onboarding import OnboardingSlot
from server.schemas import ConversationTurn, MemoryContext
from server.settings import settings

logger = logging.getLogger(__name__)

type LegacyConsolidationScheduler = Callable[[str, str], None]
type ContextualConsolidationScheduler = Callable[[str, str, ActivePersonContext], None]
type ConsolidationScheduler = LegacyConsolidationScheduler | ContextualConsolidationScheduler


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
    active_person: ActivePersonContext | None = None
    history_scope: str | None = None


@dataclass(frozen=True)
class TextTurnResult:
    """Structured output from one completed text turn."""

    response: str
    emotion: str
    duration_ms: int
    llm_failed: bool


def _missing_person(_: int) -> None:
    """Provide the no-evidence lookup used by public text adapters."""


def _resolve_turn_person(active_person: ActivePersonContext | None) -> ActivePersonContext:
    """Return supplied internal evidence or the safe default unknown context."""
    if active_person is not None:
        return active_person
    return resolve_active_person(
        evidence=(),
        lookup_person=_missing_person,
        clock=lambda: datetime.now(UTC),
    )


def _manual_evidence(active_person: ActivePersonContext) -> IdentityEvidence | None:
    """Return the verified manual evidence eligible for legacy compatibility."""
    if active_person.status is not ActivePersonStatus.IDENTIFIED or active_person.person_id is None:
        return None
    return next(
        (
            evidence
            for evidence in active_person.evidence
            if evidence.source is IdentityEvidenceSource.MANUAL
            and evidence.candidate_person_id == active_person.person_id
        ),
        None,
    )


def _history_scope(active_person: ActivePersonContext) -> str:
    """Return an internal history key without trusting a public conversation ID."""
    evidence = _manual_evidence(active_person)
    if evidence is not None:
        return f"session:{evidence.evidence_id.hex}:person:{active_person.person_id}"
    return f"turn:{uuid4().hex}"


def _clear_evidence_scopes(active_person: ActivePersonContext) -> None:
    """Clear histories associated with expired, cleared, or ambiguous evidence."""
    for evidence in active_person.evidence:
        if evidence.candidate_person_id is not None:
            working.clear(
                f"session:{evidence.evidence_id.hex}:person:{evidence.candidate_person_id}"
            )


def _schedule_consolidation(
    scheduler: ConsolidationScheduler,
    message: str,
    response: str,
    active_person: ActivePersonContext,
) -> None:
    """Call a contextual scheduler while retaining the legacy adapter seam."""
    try:
        inspect.signature(scheduler).bind(message, response, active_person)
    except (TypeError, ValueError):
        cast("LegacyConsolidationScheduler", scheduler)(message, response)
    else:
        cast("ContextualConsolidationScheduler", scheduler)(message, response, active_person)


async def _memory_prompt_state(
    message: str,
) -> tuple[MemoryContext | None, bool, OnboardingSlot | None, str | None]:
    """Resolve legacy-compatible persistent context without global onboarding."""
    try:
        context = await build_context(message)
        return context, False, None, None
    except BrainMemoryError as exc:
        logger.warning("Memory unavailable — degrading to stateless turn: %s", exc)
        return None, False, None, None


async def prepare_text_turn(
    message: str,
    conversation_id: str,
    *,
    perception: str | None = None,
    active_person: ActivePersonContext | None = None,
) -> PreparedTextTurn:
    """Resolve shared prompt inputs for one conversation.

    Args:
        message: Current user message.
        conversation_id: Ephemeral working-memory identifier.
        perception: Optional textual visual perception for this turn.
        active_person: Internally resolved evidence for this turn only.

    Returns:
        Immutable inputs for one LLM generation.

    Raises:
        ValueError: If ``conversation_id`` is empty.
    """
    if not conversation_id:
        raise ValueError("conversation_id must not be empty")
    resolved_person = _resolve_turn_person(active_person)
    history_scope = _history_scope(resolved_person)
    if not settings.memory_enabled:
        return PreparedTextTurn(
            message,
            conversation_id,
            None,
            None,
            False,
            None,
            None,
            None,
            perception,
            resolved_person,
            history_scope,
        )
    if _manual_evidence(resolved_person) is None:
        _clear_evidence_scopes(resolved_person)
        return PreparedTextTurn(
            message,
            conversation_id,
            None,
            None,
            False,
            None,
            None,
            None,
            perception,
            resolved_person,
            history_scope,
        )
    history = working.get_history(history_scope)
    user_emotion = working.get_recent_emotion(history_scope)
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
        resolved_person,
        history_scope,
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
    _conversation_id: str,
    response: str,
    emotion: str,
    *,
    active_person: ActivePersonContext | None = None,
    history_scope: str | None = None,
    schedule_consolidation: ConsolidationScheduler | None = None,
) -> None:
    """Record a successful turn and optionally schedule consolidation.

    Args:
        message: Current user message.
        conversation_id: Ephemeral working-memory identifier.
        response: Generated assistant response.
        emotion: Emotion detected during generation.
        active_person: Internally resolved evidence for this turn only.
        history_scope: Internal working-memory key calculated during preparation.
        schedule_consolidation: Optional channel-owned scheduling callback.
    """
    if not settings.memory_enabled:
        return
    resolved_person = _resolve_turn_person(active_person)
    scope = history_scope or _history_scope(resolved_person)
    working.add_emotion(scope, emotion)
    working.add_turn(scope, "user", message)
    working.add_turn(scope, "assistant", response)
    if _manual_evidence(resolved_person) is None:
        working.clear(scope)
        return
    if schedule_consolidation is not None:
        _schedule_consolidation(schedule_consolidation, message, response, resolved_person)


async def process_text_turn(
    message: str,
    conversation_id: str,
    *,
    perception: str | None = None,
    active_person: ActivePersonContext | None = None,
    schedule_consolidation: ConsolidationScheduler | None = None,
) -> TextTurnResult:
    """Generate and record one channel-agnostic text turn.

    Args:
        message: Current user message.
        conversation_id: Ephemeral working-memory identifier.
        perception: Optional textual visual perception for this turn.
        active_person: Internally resolved evidence for this turn only.
        schedule_consolidation: Optional channel-owned scheduling callback.

    Returns:
        Text, emotion, elapsed time, and fallback status for the turn.
    """
    started = time.perf_counter()
    prepared = await prepare_text_turn(
        message,
        conversation_id,
        perception=perception,
        active_person=active_person,
    )
    response, emotion, llm_failed = await _generate(prepared)
    if not llm_failed:
        record_text_turn(
            message,
            conversation_id,
            response,
            emotion,
            active_person=prepared.active_person,
            history_scope=prepared.history_scope,
            schedule_consolidation=schedule_consolidation,
        )
    duration_ms = round((time.perf_counter() - started) * 1000)
    return TextTurnResult(response, emotion, duration_ms, llm_failed)
