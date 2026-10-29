"""Channel-agnostic text turn orchestration."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
import logging
import time
from uuid import uuid4

import httpx

from server import llm, turn_log
from server.claim_guard import neutralize_memory_claims
from server.cognition.authorization import ASSURANCE_RANK
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    IdentityAssurance,
    resolve_active_person,
)
from server.cognition.strong_actor import is_face_actor
from server.exceptions import LLMError
from server.memory import continuity
from server.memory.candidate_dialogue import OfferPreparer, PendingOffer, commit_offer
from server.memory.continuity import ContinuityTurn, SuspendCause
from server.schemas import ConversationTurn
from server.settings import settings

logger = logging.getLogger(__name__)

#: Channel-owned callback that schedules a background candidate proposal (ADR 0021 decision 10). It
#: receives the user's own words and the face-identified actor; the route that owns the clip
#: and the turn's correlation id binds them. It never receives the assistant's reply.
ProposalScheduler = Callable[[str, ActivePersonContext], None]

#: Channel-owned seam that renders the speaker's profile card for the prompt (Plan 0074, ADR 0026
#: decision 3), or ``None`` when there is none to show. Only the two voice routes pass one; it owns
#: the policy and the audit row, never raises into the turn and is awaited only for a speaker the
#: continuity session already accepts.
ProfileCardProvider = Callable[[ActivePersonContext], Awaitable[str | None]]


@dataclass(frozen=True)
class PreparedTextTurn:
    """Inputs resolved for one text generation."""

    message: str
    conversation_id: str
    history: list[ConversationTurn] | None
    user_emotion: str | None
    perception: str | None
    active_person: ActivePersonContext | None = None
    continuity: ContinuityTurn | None = None
    # The rendered profile card carries the person's own data: hidden from ``repr``.
    profile_card: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class TextTurnResult:
    """Structured output from one completed text turn.

    Attributes:
        response: The reply text, exactly what is recorded in the session history.
        emotion: The closed emotion label of the reply.
        duration_ms: Generation time of the reply; the memory offer is never counted in it.
        llm_failed: Whether the reply is the fallback phrase instead of a model answer.
        offer: The spoken phrase of a memory offer, said after the reply. It is never part of
            the reply's text, the session history, the wire's ``llm_response`` or
            ``duration_ms`` (ADR 0021 decision 9). Hidden from ``repr``: it carries a value.
    """

    response: str
    emotion: str
    duration_ms: int
    llm_failed: bool
    offer: str | None = field(default=None, repr=False)


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


def new_interaction_scope() -> str:
    """Create an opaque conversation identifier for one unresolved request.

    Returns:
        A process-local identifier not derived from user input or exposed by a response.
        It labels an event only: it is never identity and never selects the session.
    """
    return f"interaction:{uuid4().hex}"


def _continuity_person_id(active_person: ActivePersonContext) -> int | None:
    """Return the person who may use the short-term session, or ``None`` (ADR 0020 §2).

    Only a person identified by a trusted source with an assurance of at least ``basic``
    has continuity. Assurance is compared through its rank, never alphabetically.
    """
    if active_person.status is not ActivePersonStatus.IDENTIFIED or active_person.person_id is None:
        return None
    if ASSURANCE_RANK[active_person.assurance] < ASSURANCE_RANK[IdentityAssurance.BASIC]:
        return None
    return active_person.person_id


async def _load_profile_card(
    provider: ProfileCardProvider, person: ActivePersonContext
) -> str | None:
    """Ask the provider for the card; any failure means no card and never fails the turn."""
    try:
        return await provider(person)
    except Exception as exc:  # the card is an extra: the turn is answered without it
        logger.warning("Profile card unavailable (%s)", type(exc).__name__)
        return None


async def prepare_text_turn(
    message: str,
    conversation_id: str,
    *,
    perception: str | None = None,
    active_person: ActivePersonContext | None = None,
    suspend_cause: SuspendCause | None = None,
    profile_card_provider: ProfileCardProvider | None = None,
) -> PreparedTextTurn:
    """Resolve shared prompt inputs for one conversation.

    The speaker decides what the turn may read (ADR 0020): an identified person gets the
    short-term session's history; an unknown or ambiguous speaker suspends it and the turn
    reads nothing. No persistent memory is read here: the profile card is the only durable
    datum that reaches the prompt (Plan 0074), and the legacy ``MANUAL``-gated retrieval is
    gone (Plan 0076).

    Args:
        message: Current user message.
        conversation_id: Ephemeral conversation label; never identity, never selects history.
        perception: Optional textual visual perception for this turn.
        active_person: Internally resolved evidence for this turn only.
        suspend_cause: Why the speaker could not be identified, for the transition log.
        profile_card_provider: Optional channel-owned seam that renders the speaker's profile
            card (Plan 0074). It is awaited only for a speaker the continuity session accepts
            (identified, at least ``basic``) with ``MEMORY_ENABLED`` on; a failure leaves no card.

    Returns:
        Immutable inputs for one LLM generation.

    Raises:
        ValueError: If ``conversation_id`` is empty.
    """
    if not conversation_id:
        raise ValueError("conversation_id must not be empty")
    resolved_person = _resolve_turn_person(active_person)
    if not settings.memory_enabled:
        turn_log.log_memory("skipped", "MEMORY_ENABLED is off")
        return PreparedTextTurn(
            message=message,
            conversation_id=conversation_id,
            history=None,
            user_emotion=None,
            perception=perception,
            active_person=resolved_person,
        )
    person_id = _continuity_person_id(resolved_person)
    turn = continuity.open_turn(person_id, None if person_id is not None else suspend_cause)
    history = list(turn.history) if turn.writable else None
    profile_card = (
        await _load_profile_card(profile_card_provider, resolved_person)
        if profile_card_provider is not None and person_id is not None and turn.writable
        else None
    )
    turn_log.log_memory(
        "loaded" if turn.writable else "skipped",
        f"history_turns={len(history or [])}, no retrieval, no vector search",
    )
    return PreparedTextTurn(
        message=message,
        conversation_id=conversation_id,
        history=history,
        user_emotion=None,
        perception=perception,
        active_person=resolved_person,
        continuity=turn,
        profile_card=profile_card,
    )


async def _generate(client: httpx.AsyncClient, prepared: PreparedTextTurn) -> tuple[str, str, bool]:
    """Generate a response, degrading to the configured local phrase."""
    try:
        response, emotion = await llm.generate_response(
            client,
            prepared.message,
            history=prepared.history,
            user_emotion=prepared.user_emotion,
            active_person=prepared.active_person,
            perception=prepared.perception,
            profile_card=prepared.profile_card,
        )
        # The model stores nothing (Plan 0064): a claim of saving is false, and the history
        # must never keep it, so the guard runs before the reply is logged or recorded.
        response = neutralize_memory_claims(response)
        logger.info(
            "LLM produced %d chars (emotion=%s)",
            len(response),
            emotion,
            extra={"event": "llm.response", "chars": len(response), "emotion": emotion},
        )
        return response, emotion, False
    except (LLMError, ValueError) as exc:
        if llm.is_connectivity_failure(exc):
            logger.warning("LLM unreachable — using fallback phrase: %s", exc)
        else:
            logger.error("LLM failed — using fallback phrase: %s", exc, exc_info=True)
        return settings.llm_fallback_phrase, "neutral", True


def record_text_turn(
    message: str,
    response: str,
    *,
    active_person: ActivePersonContext | None = None,
    continuity_turn: ContinuityTurn | None = None,
    schedule_proposal: ProposalScheduler | None = None,
) -> None:
    """Record a successful turn and optionally schedule a candidate proposal.

    Args:
        message: Current user message.
        response: Generated assistant response.
        active_person: Internally resolved evidence for this turn only.
        continuity_turn: The session view this turn read; a suspended or stale turn writes
            nothing.
        schedule_proposal: Optional channel-owned scheduling callback; reached only by a
            face-identified speaker with no token, and only with the candidate kill-switch on.
            The callback's own background task checks the voice before anything is extracted.
    """
    if not settings.memory_enabled:
        return
    resolved_person = _resolve_turn_person(active_person)
    if continuity_turn is not None and continuity.record_pair(continuity_turn, message, response):
        turn_log.log_memory("recorded", "identified speaker, exchange kept in the session")
    else:
        turn_log.log_memory("discarded", "no identified speaker, nothing kept")
    if (
        schedule_proposal is not None
        and settings.memory_candidates_enabled
        and is_face_actor(resolved_person)
    ):
        # Identity gates this callback; it is not an authorization decision (the policy is
        # asked, and audited, in the background task, with the voice of the turn's own clip).
        schedule_proposal(message, resolved_person)
        turn_log.log_memory("proposal-scheduled", "face-identified speaker")


def start_offer(
    prepare_offer: OfferPreparer | None, active_person: ActivePersonContext | None
) -> asyncio.Future[PendingOffer | None] | None:
    """Start preparing a memory offer concurrently with generation, when one may exist.

    Only a face-identified speaker with no token, with memory and the candidate kill-switch on,
    starts it (ADR 0021 decisions 3 and 9). The preparation reads the store first and verifies
    the voice only when a candidate waits; it runs concurrently with generation, so that extra
    check is normally hidden behind the model's own latency.

    Args:
        prepare_offer: The route-bound preparation (it owns the clip and the event), or ``None``.
        active_person: The turn's resolved speaker.

    Returns:
        The running preparation, or ``None`` when no offer can be made on this turn.
    """
    if (
        prepare_offer is None
        or active_person is None
        or not settings.memory_enabled
        or not settings.memory_candidates_enabled
        or not is_face_actor(active_person)
    ):
        return None
    return asyncio.ensure_future(prepare_offer(active_person))


async def finish_offer(
    task: asyncio.Future[PendingOffer | None] | None, *, reply_failed: bool
) -> str | None:
    """Commit the prepared offer once the reply was built, or drop it.

    Args:
        task: What ``start_offer`` returned.
        reply_failed: Whether the reply is the fallback phrase; a fallback never carries one.

    Returns:
        The phrase to speak after the reply, or ``None``.
    """
    if task is None:
        return None
    if reply_failed:
        task.cancel()
        # Waits for the cancelled preparation without swallowing a cancellation of the caller.
        await asyncio.gather(task, return_exceptions=True)
        return None
    try:
        pending = await task
    except Exception as exc:  # the reply is built: a broken preparation must not cost it
        logger.warning("Memory offer preparation failed (%s)", type(exc).__name__)
        return None
    return None if pending is None else await commit_offer(pending)


def drop_offer(task: asyncio.Future[PendingOffer | None] | None) -> None:
    """Cancel a preparation the turn will never finish (it was cancelled or it raised).

    Args:
        task: What ``start_offer`` returned; a finished one is left alone.
    """
    if task is not None and not task.done():
        task.cancel()


async def process_text_turn(
    client: httpx.AsyncClient,
    message: str,
    conversation_id: str,
    *,
    perception: str | None = None,
    active_person: ActivePersonContext | None = None,
    suspend_cause: SuspendCause | None = None,
    schedule_proposal: ProposalScheduler | None = None,
    prepare_offer: OfferPreparer | None = None,
    profile_card_provider: ProfileCardProvider | None = None,
) -> TextTurnResult:
    """Generate and record one channel-agnostic text turn.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039).
        message: Current user message.
        conversation_id: Ephemeral conversation label; never identity.
        perception: Optional textual visual perception for this turn.
        active_person: Internally resolved evidence for this turn only.
        suspend_cause: Why the speaker could not be identified, for the transition log.
        schedule_proposal: Optional channel-owned proposal scheduling callback.
        prepare_offer: Optional channel-owned memory-offer preparation (ADR 0021 decision 9); it runs
            concurrently with generation.
        profile_card_provider: Optional channel-owned profile card seam (Plan 0074); see
            ``prepare_text_turn``.

    Returns:
        Text, emotion, elapsed time, fallback status and the optional offer for the turn.
    """
    started = time.perf_counter()
    prepared = await prepare_text_turn(
        message,
        conversation_id,
        perception=perception,
        active_person=active_person,
        suspend_cause=suspend_cause,
        profile_card_provider=profile_card_provider,
    )
    offer_task = start_offer(prepare_offer, prepared.active_person)
    try:
        response, emotion, llm_failed = await _generate(client, prepared)
        if not llm_failed:
            record_text_turn(
                message,
                response,
                active_person=prepared.active_person,
                continuity_turn=prepared.continuity,
                schedule_proposal=schedule_proposal,
            )
        # Measured before the offer is committed: the offer never counts as generation time.
        duration_ms = round((time.perf_counter() - started) * 1000)
        offer = await finish_offer(offer_task, reply_failed=llm_failed)
    finally:
        drop_offer(offer_task)
    return TextTurnResult(response, emotion, duration_ms, llm_failed, offer)
