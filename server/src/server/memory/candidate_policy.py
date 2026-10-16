"""The policy check of a candidate step (ADR 0021 decision 7): evaluate, audit, then act.

Three steps ask ADR 0019's policy a question about the owner's own personal memory:

* ``PROPOSE`` asks ``propose_personal_memory`` before a candidate is stored;
* ``READ`` asks ``read_personal_conversation_memory`` before an offer is spoken
  (``candidate_dialogue.commit_offer``);
* ``CONFIRM`` asks ``confirm_personal_memory`` inside ``memory_writer.promote``, which the spoken
  answer reaches through ``candidate_dialogue.answer_offer``.

The policy minimums are ``basic`` for propose and read and ``strong`` for confirm, but every
caller of CM-3a demands more (the firewall rule): the actor must be the composite of face and
voice of that turn and carry no token. A weaker actor is refused here before the policy is
even asked, so a bug upstream cannot weaken the rule.

The audit row is written **before** the effect and a failing audit denies (ADR 0019 §6.3).
Nothing here reads or returns a protected value.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
import logging
from typing import TYPE_CHECKING

from server.cognition.authorization import (
    AuthorizationRequest,
    ConsentStatus,
    evaluate_authorization,
)
from server.cognition.models import AuthorizationAction, AuthorizationDecision, AuthorizationStatus
from server.cognition.strong_actor import is_face_and_voice_actor
from server.memory.candidate_classifier import CANDIDATE_SENSITIVITY, CANDIDATE_VISIBILITY
from server.memory.candidate_types import CandidateReason
from server.memory.household_authorization import record_authorization_decision
from server.settings import settings

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from server.cognition.identity import ActivePersonContext

logger = logging.getLogger(__name__)

__all__ = ["CandidateStep", "PolicyOutcome", "authorize_step"]

type PolicyEvaluator = Callable[[AuthorizationRequest], AuthorizationDecision]
type AuditWriter = Callable[[AuthorizationRequest, AuthorizationDecision], Awaitable[None]]


class CandidateStep(StrEnum):
    """The step of a candidate's life that asks the policy."""

    PROPOSE = "propose"
    READ = "read"
    CONFIRM = "confirm"


_ACTIONS = {
    CandidateStep.PROPOSE: AuthorizationAction.PROPOSE_PERSONAL_MEMORY,
    CandidateStep.READ: AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY,
    CandidateStep.CONFIRM: AuthorizationAction.CONFIRM_PERSONAL_MEMORY,
}


@dataclass(frozen=True)
class PolicyOutcome:
    """The result of one step's policy check.

    Attributes:
        allowed: Whether the step may take effect.
        reason: ``None`` when allowed, else the closed reason it was refused for.
        policy_id: The policy's outcome id when the policy was asked, else ``None``.
    """

    allowed: bool
    reason: CandidateReason | None = None
    policy_id: str | None = None


def _refused(
    reason: CandidateReason, step: CandidateStep, policy_id: str | None = None
) -> PolicyOutcome:
    logger.info(
        "Candidate policy: %s refused (%s)",
        step.value,
        reason.value,
        extra={"event": "candidate.policy", "step": step, "reason": reason, "policy_id": policy_id},
    )
    return PolicyOutcome(allowed=False, reason=reason, policy_id=policy_id)


async def authorize_step(
    step: CandidateStep,
    *,
    actor: ActivePersonContext,
    subject_person_id: int,
    correlation_id: UUID,
    now: datetime,
    policy: PolicyEvaluator = evaluate_authorization,
    audit: AuditWriter = record_authorization_decision,
) -> PolicyOutcome:
    """Ask the policy whether *actor* may take *step* on the subject's own ordinary memory.

    Args:
        step: Which step asks.
        actor: The face-and-voice actor of this turn, never a token actor.
        subject_person_id: Whose memory the candidate would become. Targeting the subject
            (not the actor) lets the policy's own-data rule fire.
        correlation_id: The turn's id, so the audit row joins to the candidate and the fact.
        now: The caller's clock reading.
        policy: The pure evaluator; tests inject doubles.
        audit: The audit writer; tests inject doubles.

    Returns:
        ``allowed`` only when the kill-switch is on, the actor is the composite, the policy
        allows and the audit row was written. Any other case is a refusal with a closed
        reason, and the caller must neither store, speak nor promote.
    """
    if not settings.memory_candidates_enabled:
        return _refused(CandidateReason.DENIED, step)
    if not is_face_and_voice_actor(actor):
        return _refused(CandidateReason.STRONG_UNREACHABLE, step)
    request = AuthorizationRequest(
        actor=actor,
        action=_ACTIONS[step],
        target_person_id=subject_person_id,
        visibility=frozenset({CANDIDATE_VISIBILITY}),
        sensitivity=frozenset({CANDIDATE_SENSITIVITY}),
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=correlation_id,
        requested_at=now,
    )
    decision = policy(request)
    try:
        await audit(request, decision)
    except Exception as exc:
        # The audit must precede the effect and a failing audit denies it (ADR 0019 §6.3).
        # Only the class is logged: the exception could carry a row value.
        logger.warning("Candidate audit failed (%s): the step is denied", type(exc).__name__)
        return _refused(CandidateReason.DENIED, step, decision.policy_id)
    if decision.decision is not AuthorizationStatus.ALLOWED:
        return _refused(CandidateReason.DENIED, step, decision.policy_id)
    return PolicyOutcome(allowed=True, policy_id=decision.policy_id)
