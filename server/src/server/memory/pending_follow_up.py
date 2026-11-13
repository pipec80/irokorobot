"""The greeting that picks a pending topic up, beside the memory offer (Plan 0084 D-8 to D-11).

* ``prepare_follow_up`` runs concurrently with generation and only reads: the face-identified owner
  on a **new** short-term session, no topic asked yet on this household day, and the oldest open
  topic due one or two days ago. It writes nothing.
* ``commit_follow_up`` runs once the reply was built (never on a fallback, and not when a memory
  offer is spoken instead): the policy is asked ``read_personal_conversation_memory`` for the
  owner's own data, its audit row is written **before** the topic is used, and the topic moves to
  ``asked`` (compare-and-set).

Face only (``basic``): with two faces in view the generic identity is suspended and nothing is
prepared. A ``medical`` topic needs the consent the sensitive read needs (Plan 0079 D-9): the
face's grant — which every face-identified owner carries, since the face only identifies the owner
with an active consent — and a closed alta. Logs carry a closed outcome and ids, never a topic,
a day or a sentence; neither function raises.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
import logging
from typing import TYPE_CHECKING

from server.cognition.authorization import (
    AuthorizationRequest,
    ConsentStatus,
    DataSensitivity,
    DataVisibility,
    evaluate_authorization,
)
from server.cognition.identity import HouseholdRole
from server.cognition.models import AuthorizationAction, AuthorizationStatus
from server.cognition.pending_topics import follow_up_sentence
from server.memory.commissioning import has_closed_commissioning
from server.memory.failure_log import failure_level, failure_site
from server.memory.household_authorization import record_authorization_decision
from server.memory.pending_store import asked_today, due_topic, mark_asked
from server.memory.profile_card_access import may_read_own_memory
from server.memory.sensitive_access import own_read_consent

if TYPE_CHECKING:
    from datetime import date, datetime
    from uuid import UUID

    from server.cognition.identity import ActivePersonContext
    from server.memory.candidate_policy import AuditWriter, PolicyEvaluator
    from server.memory.continuity import ContinuityTurn
    from server.memory.pending_store import PendingSensitivity
    from server.memory.sensitive_access import AltaChecker

logger = logging.getLogger(__name__)

__all__ = [
    "FollowUpOutcome",
    "FollowUpPreparer",
    "PendingFollowUp",
    "commit_follow_up",
    "log_follow_up",
    "prepare_follow_up",
    "yield_to_offer",
]


class FollowUpOutcome(StrEnum):
    """What one follow-up step did, in closed terms (D-15)."""

    ASKED = "asked"
    NONE_DUE = "none_due"
    ALREADY_TODAY = "already_today"
    OFFER_WON = "offer_won"
    DENIED = "denied"
    AUDIT_FAILED = "audit_failed"


@dataclass(frozen=True)
class PendingFollowUp:
    """A follow-up ready to be committed once the turn's reply is built.

    Attributes:
        topic_id: The topic it picks up.
        sentence: The fixed sentence; it names the topic, so it never reaches a log.
        actor: The face-identified owner of this turn, for the policy request.
        correlation_id: The turn's id; it stamps the audit row.
        sensitivity: The topic's sensitivity, for the policy request.
        consent: The consent of the request (D-9).
    """

    topic_id: int
    sentence: str = field(repr=False)
    actor: ActivePersonContext = field(repr=False)
    correlation_id: UUID
    sensitivity: PendingSensitivity
    consent: ConsentStatus


#: What a voice route binds and hands to the text turn: the speaker and the turn's session view in,
#: a follow-up or ``None`` out. The route binds the household day and the turn's correlation id.
type FollowUpPreparer = Callable[
    [ActivePersonContext, ContinuityTurn], Awaitable[PendingFollowUp | None]
]


def _owner_on_a_new_session(actor: ActivePersonContext, session: ContinuityTurn) -> int | None:
    """The owner's id when their face named them at ``basic`` or more on a new session (D-8)."""
    person_id = actor.person_id
    if not may_read_own_memory(actor) or actor.role is not HouseholdRole.OWNER:
        return None
    if person_id is None or session.person_id != person_id or session.history:
        return None
    return person_id


async def prepare_follow_up(
    actor: ActivePersonContext,
    session: ContinuityTurn,
    *,
    today: date,
    correlation_id: UUID,
    alta_closed: AltaChecker = has_closed_commissioning,
) -> PendingFollowUp | None:
    """Find the topic a greeting of this turn may pick up, writing nothing.

    Args:
        actor: The turn's resolved speaker.
        session: The turn's view of the short-term session.
        today: The household's local day.
        correlation_id: The turn's id.
        alta_closed: Whether a commissioning is closed; tests inject doubles.

    Returns:
        The follow-up to commit once the reply is built, or ``None``. Never raises (a
        cancellation excepted): a failure is logged by its class and prepares nothing.
    """
    try:
        owner_id = _owner_on_a_new_session(actor, session)
        if owner_id is None:
            return None
        # Most days nothing is due: one query then, the second only when a topic waits.
        topic = await due_topic(owner_id, today=today)
        if topic is not None and topic.sensitivity == "medical" and not await alta_closed():
            # The policy would deny it: it must not block a normal topic (Task 8 review).
            topic = await due_topic(owner_id, today=today, normal_only=True)
        if topic is None:
            log_follow_up(FollowUpOutcome.NONE_DUE, correlation_id)
            return None
        if await asked_today(owner_id, today=today):
            log_follow_up(FollowUpOutcome.ALREADY_TODAY, correlation_id)
            return None
        return PendingFollowUp(
            topic_id=topic.id,
            sentence=follow_up_sentence(topic.topic, due_day=topic.due_day, today=today),
            actor=actor,
            correlation_id=correlation_id,
            sensitivity=topic.sensitivity,
            # The face only identifies an owner with an active consent: its grant is given.
            consent=await own_read_consent(
                frozenset({topic.sensitivity}),
                face_consent=ConsentStatus.GRANTED,
                alta_closed=alta_closed,
            ),
        )
    except Exception as exc:  # background seam of a turn: never reaches the user's reply
        _log_failure(exc, correlation_id)
        return None


async def commit_follow_up(
    follow_up: PendingFollowUp,
    *,
    now: datetime,
    policy: PolicyEvaluator = evaluate_authorization,
    audit: AuditWriter = record_authorization_decision,
) -> str | None:
    """Ask the policy, write its audit row, then mark the topic ``asked``; return the sentence.

    Args:
        follow_up: What ``prepare_follow_up`` returned for this turn.
        now: The caller's clock reading.
        policy: The pure evaluator; tests inject doubles.
        audit: The audit writer; tests inject doubles.

    Returns:
        The sentence to speak after the reply, or ``None`` when the policy refused, the audit
        failed or the topic was no longer open. Never raises (a cancellation excepted).
    """
    try:
        request = AuthorizationRequest(
            actor=follow_up.actor,
            action=AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY,
            target_person_id=follow_up.actor.person_id,
            visibility=frozenset({DataVisibility.PERSONAL}),
            sensitivity=frozenset({DataSensitivity(follow_up.sensitivity)}),
            consent=follow_up.consent,
            correlation_id=follow_up.correlation_id,
            requested_at=now,
        )
        decision = policy(request)
        try:
            await audit(request, decision)
        except Exception as exc:  # no audit row, no use of the topic
            log_follow_up(
                FollowUpOutcome.AUDIT_FAILED,
                follow_up.correlation_id,
                follow_up.topic_id,
                error=exc,
            )
            return None
        if decision.decision is not AuthorizationStatus.ALLOWED:
            log_follow_up(FollowUpOutcome.DENIED, follow_up.correlation_id, follow_up.topic_id)
            return None
        if not await mark_asked(follow_up.topic_id, now=now):
            log_follow_up(
                FollowUpOutcome.ALREADY_TODAY, follow_up.correlation_id, follow_up.topic_id
            )
            return None
        log_follow_up(FollowUpOutcome.ASKED, follow_up.correlation_id, follow_up.topic_id)
        return follow_up.sentence
    except Exception as exc:  # the reply was built; a failing follow-up must not break it
        _log_failure(exc, follow_up.correlation_id)
        return None


def yield_to_offer(follow_up: PendingFollowUp) -> None:
    """Note that a memory offer is spoken instead: the topic stays ``open`` (D-11).

    Args:
        follow_up: The prepared follow-up that is not committed.
    """
    log_follow_up(FollowUpOutcome.OFFER_WON, follow_up.correlation_id, follow_up.topic_id)


def log_follow_up(
    outcome: FollowUpOutcome,
    correlation_id: UUID,
    topic_id: int | None = None,
    *,
    error: Exception | None = None,
) -> None:
    """Log one follow-up step: a closed outcome, ids and an error's class, never a topic or day."""
    logger.log(
        logging.INFO if error is None else failure_level(error),
        "Pending topic follow-up: %s",
        outcome.value,
        extra={
            "event": "pending.follow_up",
            "outcome": outcome.value,
            "topic_id": topic_id,
            "correlation_id": str(correlation_id),
            "error_type": None if error is None else type(error).__name__,
        },
    )


def _log_failure(exc: Exception, correlation_id: UUID) -> None:
    """Log a failure by class and site: a database error's message can carry a value."""
    name, site = type(exc).__name__, failure_site(exc)
    logger.log(
        failure_level(exc),
        "Pending topic follow-up failed (%s at %s)",
        name,
        site,
        extra={
            "event": "pending.follow_up_error",
            "error_type": name,
            "site": site,
            "correlation_id": str(correlation_id),
        },
    )
