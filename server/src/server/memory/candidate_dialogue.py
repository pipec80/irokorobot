"""The spoken offer and the explicit answer (ADR 0021 decision 9, Plan 0063).

A candidate the owner stated earlier is offered back on a later generic voice turn, and only an
explicit answer that repeats the value resolves it. Both need the face **and** the voice of the
same person on that turn's own clip and never a token (decision 3); anything else returns
``None`` and the turn is the ordinary one, byte for byte, so whether an offer exists is never
revealed to anybody else.

* ``prepare_offer`` runs concurrently with generation: it reads the person's oldest offerable
  candidate and, only when one waits, checks the voice of the turn's clip. It writes nothing.
* ``commit_offer`` runs once the reply was built (never on a fallback): it asks the policy for
  ``read_personal_conversation_memory`` (audited before the effect) and moves the candidate to
  ``offered``. No claim is made that the offer was heard.
* ``answer_offer`` is the controller's answer branch: a «sí» promotes through the one writer, a
  «no» is audited as ``confirm_personal_memory`` and rejects the candidate.

Audio contract for the clip: WAV, 16 000 Hz, mono, signed int16, held in memory only. Logs carry
ids, a status and a closed outcome, never a value and never an exception's message.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
import logging
from pathlib import Path
import sqlite3
import traceback
from typing import TYPE_CHECKING

from server.cognition.authorization import evaluate_authorization
from server.cognition.clock import utc_now
from server.cognition.strong_actor import (
    VoiceVerifier,
    is_face_actor,
    is_face_and_voice_actor,
    verify_face_and_voice,
)
from server.exceptions import BrainMemoryError
from server.memory.candidate_classifier import comparison_key
from server.memory.candidate_policy import CandidateStep, authorize_step
from server.memory.candidate_types import CandidateStatus
from server.memory.candidates import (
    find_offered,
    mark_offered,
    next_offerable,
    resolve_candidate,
    still_offerable,
)
from server.memory.household_authorization import record_authorization_decision
from server.memory.lexicon import (
    ANSWER_CONTRADICTION_PHRASE,
    ANSWER_FAILED_PHRASE,
    ANSWER_REJECTED_PHRASE,
    ANSWER_SAVED_PHRASE,
    OFFER_QUESTION,
    OFFER_STATEMENTS,
    OFFER_VERB_PLURAL,
    OFFER_VERB_SINGULAR,
    PLURAL_ARTICLES,
)
from server.memory.memory_writer import PromotionOutcome, promote
from server.settings import settings

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from server.cognition.authorization import AuthorizationRequest
    from server.cognition.identity import ActivePersonContext
    from server.cognition.intent_resolution import MemoryAnswer
    from server.cognition.models import AuthorizationDecision, CognitiveEvent
    from server.cognition.response_plan import TextTurnPayload

logger = logging.getLogger(__name__)

__all__ = [
    "ANSWER_CONTRADICTION_PHRASE",
    "ANSWER_FAILED_PHRASE",
    "ANSWER_REJECTED_PHRASE",
    "ANSWER_SAVED_PHRASE",
    "OfferPreparer",
    "PendingOffer",
    "answer_offer",
    "commit_offer",
    "compose_offer",
    "prepare_offer",
]

type PolicyEvaluator = Callable[[AuthorizationRequest], AuthorizationDecision]
type AuditWriter = Callable[[AuthorizationRequest, AuthorizationDecision], Awaitable[None]]
type Clock = Callable[[], datetime]


@dataclass(frozen=True)
class PendingOffer:
    """An offer ready to be spoken once the turn's reply is built.

    Attributes:
        candidate_id: The candidate it offers.
        subject_person_id: Whose candidate it is (the speaker).
        phrase: The spoken offer; it carries the value, so it never reaches a log.
        actor: The face-and-voice actor of this turn, for the policy's read step.
        correlation_id: The turn's id; it stamps the audit row and the candidate.
    """

    candidate_id: int
    subject_person_id: int
    phrase: str = field(repr=False)
    actor: ActivePersonContext = field(repr=False)
    correlation_id: UUID


#: What a voice route binds and hands to the text turn: the actor in, an offer or ``None`` out.
type OfferPreparer = Callable[[ActivePersonContext], Awaitable[PendingOffer | None]]


def compose_offer(predicate: str, value_text: str) -> str:
    """Return the spoken offer for one candidate.

    Args:
        predicate: ``likes``, ``dislikes`` or ``prefers``.
        value_text: The stored phrase, article included ("las empanadas").

    Returns:
        The statement and the question, which tells the exact answer with the value.

    Raises:
        ValueError: If *predicate* has no offer.
    """
    statement = OFFER_STATEMENTS.get(predicate)
    if statement is None:
        raise ValueError(f"{predicate} has no offer")
    first_word = value_text.split(maxsplit=1)[0].casefold() if value_text.strip() else ""
    verb = OFFER_VERB_PLURAL if first_word in PLURAL_ARTICLES else OFFER_VERB_SINGULAR
    return " ".join(
        (
            statement.format(verb=verb, value=value_text),
            OFFER_QUESTION.format(value=value_text),
        )
    )


async def prepare_offer(
    actor: ActivePersonContext,
    *,
    wav_bytes: bytes | None,
    event: CognitiveEvent[TextTurnPayload],
    verify: VoiceVerifier = verify_face_and_voice,
    clock: Clock = utc_now,
) -> PendingOffer | None:
    """Find the speaker's oldest offerable candidate and check the voice, writing nothing.

    Cheapest first: the kill-switch and a token-free face actor, then a read of the store, and
    only when a candidate waits the voice of the turn's own clip for the person the face named.

    Args:
        actor: The turn's face-identified actor.
        wav_bytes: The turn's own clip — WAV, 16 000 Hz, mono, int16 — or ``None``.
        event: The turn's event; its correlation id stamps what follows.
        verify: The voice-check seam; tests inject doubles.
        clock: Source of "now" for the store's deadlines.

    Returns:
        The offer to speak once the reply is built, or ``None``. Never raises: any failure is
        logged by its class and offers nothing.
    """
    try:
        if not settings.memory_candidates_enabled or not is_face_actor(actor):
            return None
        person_id = actor.person_id
        if person_id is None:
            return None
        candidate = await next_offerable(person_id, now=clock())
        if candidate is None or candidate.value_text is None:
            return None
        strong = await verify(actor, wav_bytes=wav_bytes, event=event)
        if strong is None or strong.person_id != person_id:
            _log("candidate.offer", "voice_unverified", candidate.id, event.correlation_id)
            return None
        return PendingOffer(
            candidate_id=candidate.id,
            subject_person_id=person_id,
            phrase=compose_offer(candidate.predicate, candidate.value_text),
            actor=strong,
            correlation_id=event.correlation_id,
        )
    except Exception as exc:  # background seam of a turn: never reaches the user's reply
        _log_failure("candidate.offer", exc, event.correlation_id)
        return None


async def commit_offer(
    offer: PendingOffer,
    *,
    now: datetime | None = None,
    policy: PolicyEvaluator = evaluate_authorization,
    audit: AuditWriter = record_authorization_decision,
) -> str | None:
    """Ask the policy, audit, and mark the candidate ``offered``; return the phrase to speak.

    Args:
        offer: What ``prepare_offer`` returned for this turn.
        now: The caller's clock reading; the current UTC time when omitted.
        policy: The pure evaluator; tests inject doubles.
        audit: The audit writer; tests inject doubles.

    Returns:
        The offer's phrase, or ``None`` when the candidate is no longer offerable (asked before
        the audit, so no "allowed" row is written for it), the policy refused, the audit failed
        or the compare-and-set lost anyway. Never raises.
    """
    try:
        moment = now or utc_now()
        if not await still_offerable(offer.candidate_id, offer.subject_person_id, now=moment):
            _log("candidate.offer", "not_offerable", offer.candidate_id, offer.correlation_id)
            return None
        allowed = await authorize_step(
            CandidateStep.READ,
            actor=offer.actor,
            subject_person_id=offer.subject_person_id,
            correlation_id=offer.correlation_id,
            now=moment,
            policy=policy,
            audit=audit,
        )
        if not allowed.allowed:
            return None
        if not await mark_offered(
            offer.candidate_id,
            offer.subject_person_id,
            correlation_id=offer.correlation_id,
            now=moment,
        ):
            _log("candidate.offer", "not_offerable", offer.candidate_id, offer.correlation_id)
            return None
        _log("candidate.offer", "offered", offer.candidate_id, offer.correlation_id)
        return offer.phrase
    except Exception as exc:  # the reply was built; a failing offer must not break it
        _log_failure("candidate.offer", exc, offer.correlation_id, offer.candidate_id)
        return None


async def answer_offer(
    answer: MemoryAnswer,
    *,
    actor: ActivePersonContext,
    correlation_id: UUID,
    now: datetime,
    policy: PolicyEvaluator = evaluate_authorization,
    audit: AuditWriter = record_authorization_decision,
) -> str | None:
    """Resolve the speaker's open offer that the answer names, or fall through.

    The caller resolved the actor (face and voice) before calling, for every message of this
    shape, so the cost of the check never depends on whether an offer exists.

    Args:
        answer: The parsed answer: accept or reject, and the value it repeats.
        actor: The turn's actor; only the face-and-voice composite may answer.
        correlation_id: The answering turn's id.
        now: The caller's clock reading.
        policy: The pure evaluator; tests inject doubles.
        audit: The audit writer; tests inject doubles.

    Returns:
        The fixed result phrase. ``None`` falls through to ordinary generation: switch off, a
        weaker actor, no open offer with that value or a failing lookup, none of which may be
        told apart. Once the verified owner's own open offer is found, a refusal or a failure
        says ``ANSWER_FAILED_PHRASE`` instead, so the model never improvises «listo». Never
        raises (a cancellation excepted).
    """
    candidate_id = await _find_open_offer(answer, actor, correlation_id, now)
    person_id = actor.person_id
    if candidate_id is None or person_id is None:
        return None
    try:
        if answer.accept:
            spoken = await _accept(candidate_id, actor, correlation_id, now, policy, audit)
        else:
            spoken = await _reject(
                candidate_id, actor, person_id, correlation_id, now, policy, audit
            )
    except Exception as exc:  # fail closed, and tell the owner: the offer was theirs
        _log_failure("candidate.answer", exc, correlation_id, candidate_id)
        return ANSWER_FAILED_PHRASE
    return ANSWER_FAILED_PHRASE if spoken is None else spoken


async def _find_open_offer(
    answer: MemoryAnswer, actor: ActivePersonContext, correlation_id: UUID, now: datetime
) -> int | None:
    """Return the id of the actor's open offer that *answer* names, or ``None``.

    Everything before the offer is found falls through silently: nothing is observable about it.
    """
    try:
        person_id = actor.person_id
        if (
            not settings.memory_candidates_enabled
            or person_id is None
            or not is_face_and_voice_actor(actor)
        ):
            return None
        key = comparison_key(answer.phrase)
        candidate = await find_offered(person_id, key, now=now) if key else None
    except Exception as exc:  # fail closed: the turn falls through to ordinary generation
        _log_failure("candidate.answer", exc, correlation_id)
        return None
    return None if candidate is None else candidate.id


async def _accept(
    candidate_id: int,
    actor: ActivePersonContext,
    correlation_id: UUID,
    now: datetime,
    policy: PolicyEvaluator,
    audit: AuditWriter,
) -> str | None:
    """Promote through the one writer (it asks and audits the confirm step itself)."""
    result = await promote(
        candidate_id,
        actor=actor,
        correlation_id=correlation_id,
        now=now,
        policy=policy,
        audit=audit,
    )
    _log("candidate.answer", result.outcome.value, candidate_id, correlation_id)
    match result.outcome:
        case PromotionOutcome.PROMOTED | PromotionOutcome.ALREADY_PRESENT:
            return ANSWER_SAVED_PHRASE
        case PromotionOutcome.CONTRADICTION:
            return ANSWER_CONTRADICTION_PHRASE
        case _:
            return None


async def _reject(
    candidate_id: int,
    actor: ActivePersonContext,
    person_id: int,
    correlation_id: UUID,
    now: datetime,
    policy: PolicyEvaluator,
    audit: AuditWriter,
) -> str | None:
    """Audit the confirm step, then reject the candidate and erase its value."""
    allowed = await authorize_step(
        CandidateStep.CONFIRM,
        actor=actor,
        subject_person_id=person_id,
        correlation_id=correlation_id,
        now=now,
        policy=policy,
        audit=audit,
    )
    if not allowed.allowed:
        return None
    if not await resolve_candidate(
        candidate_id,
        person_id,
        to=CandidateStatus.REJECTED,
        correlation_id=correlation_id,
        now=now,
    ):
        return None
    _log("candidate.answer", "rejected", candidate_id, correlation_id)
    return ANSWER_REJECTED_PHRASE


def _log(event: str, outcome: str, candidate_id: int, correlation_id: UUID) -> None:
    """Log one dialogue step: ids and a closed outcome, never a value."""
    logger.info(
        "Candidate %s: %s",
        event.removeprefix("candidate."),
        outcome,
        extra={
            "event": event,
            "outcome": outcome,
            "candidate_id": candidate_id,
            "correlation_id": str(correlation_id),
        },
    )


#: Failures a bad moment explains (database, disk, a lost race); any other class is a bug.
_OPERATIONAL_FAILURES = (
    BrainMemoryError,
    sqlite3.Error,
    OSError,
    TimeoutError,
    RuntimeError,
    ValueError,
)


def _failure_site(exc: Exception) -> str:
    """Return ``file:line:function`` of the innermost frame; it never carries a message."""
    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return "unknown"
    frame = frames[-1]
    return f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"


def _log_failure(
    event: str, exc: Exception, correlation_id: UUID, candidate_id: int | None = None
) -> None:
    """Log a failure by class, site and ids only: a database error's message can carry a value.

    A class a bad moment explains is a warning; any other (a ``TypeError`` from signature drift)
    is a bug and an error, with the site to find it.
    """
    operational = isinstance(exc, _OPERATIONAL_FAILURES)
    name = type(exc).__name__
    site = _failure_site(exc)
    logger.log(
        logging.WARNING if operational else logging.ERROR,
        "Candidate %s failed (%s at %s)",
        event.removeprefix("candidate."),
        name,
        site,
        extra={
            "event": f"{event}_error",
            "error_type": name,
            "site": site,
            "candidate_id": candidate_id,
            "correlation_id": str(correlation_id),
        },
    )
