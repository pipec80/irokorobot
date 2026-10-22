"""The canonical memory writer: the only place a V4 fact is created from a candidate.

One function, ``promote`` (ADR 0021 decision 8), in **one** ``db.transaction()``:

1. housekeeping, then the candidate must be ``offered``, unexpired and the actor's own;
2. a **contradiction** (the same key under the opposite polarity among the active facts)
   closes the candidate ``rejected`` and writes nothing;
3. a **duplicate** (the same folded key among the active facts of that predicate) is the
   result, idempotently: the candidate is confirmed against the fact already there;
4. otherwise the fact is stored through the canonical writer's ``write_literal``
   (``manage_transaction=False``, Plan 0065): the writer assigns the classification (an owner's
   taste is ``personal``/``normal``) and records the owner as asserter and confirmer, the
   candidate's channel and the confirmation time;
5. the candidate is marked ``confirmed`` with its ``promoted_fact_id`` and its value is erased.

The duplicate and the contradiction are decided by comparing folded keys, never by relying on
the ``IntegrityError`` a duplicate raises (a test pins that error, and it would roll back the
whole transaction). The spoken confirmation is wired to it: ``candidate_dialogue.answer_offer``
promotes a confirmed candidate through this one writer.

The policy is asked and audited **before** the transaction (ADR 0019 §6.3), through
``authorize_step``; a refusal writes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import logging
from typing import TYPE_CHECKING

from server import db
from server.cognition.authorization import evaluate_authorization
from server.memory.candidate_classifier import comparison_key
from server.memory.candidate_policy import CandidateStep, authorize_step
from server.memory.candidate_types import CandidateReason, CandidateStatus
from server.memory.candidates import (
    checkpoint_after_scrub,
    get_candidate_in_transaction,
    iso_utc,
    resolve_candidate_in_transaction,
    run_housekeeping,
)
from server.memory.canonical_writer import WriteChannel, write_literal
from server.memory.household_authorization import record_authorization_decision
from server.memory.predicate_registry import resolve_predicate
from server.memory.relational_v4 import get_active_literal_facts

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    import aiosqlite

    from server.cognition.identity import ActivePersonContext
    from server.memory.candidate_policy import AuditWriter, PolicyEvaluator

logger = logging.getLogger(__name__)

__all__ = ["PromotionOutcome", "PromotionResult", "promote"]

# Opposite polarity, by canonical predicate. `prefers` has no opposite.
_OPPOSITE = {"likes": "dislikes", "dislikes": "likes"}
_PROMOTION_EVENT = "candidate.promotion"


class PromotionOutcome(StrEnum):
    """Closed outcome of one promotion attempt."""

    PROMOTED = "promoted"
    ALREADY_PRESENT = "already_present"
    CONTRADICTION = "contradiction"
    NOT_OFFERED = "not_offered"
    DENIED = "denied"


@dataclass(frozen=True)
class PromotionResult:
    """What ``promote`` did.

    Attributes:
        outcome: The closed outcome.
        fact_id: The canonical fact the candidate became (``PROMOTED``) or matched
            (``ALREADY_PRESENT``); ``None`` otherwise.
    """

    outcome: PromotionOutcome
    fact_id: int | None = None


async def promote(
    candidate_id: int,
    *,
    actor: ActivePersonContext,
    correlation_id: UUID,
    now: datetime,
    policy: PolicyEvaluator = evaluate_authorization,
    audit: AuditWriter = record_authorization_decision,
) -> PromotionResult:
    """Promote one offered candidate of *actor* to a canonical V4 literal fact.

    Args:
        candidate_id: The candidate row, looked up by this caller-supplied id and accepted
            only when its subject is the actor's own person id. The subject is never taken
            from the request: another person's candidate is ``NOT_OFFERED``.
        actor: The face-and-voice actor of the confirming turn.
        correlation_id: The confirming turn's id, for the audit row and the candidate.
        now: The caller's clock reading.
        policy: The pure policy evaluator; tests inject doubles.
        audit: The audit writer; tests inject doubles.

    Returns:
        ``DENIED`` for the kill-switch, a weaker actor, a policy refusal or an audit failure
        (nothing is written; ``authorize_step`` logged the closed reason); ``NOT_OFFERED``
        for a candidate that is not the actor's, not ``offered`` or lapsed;
        ``CONTRADICTION`` after closing the candidate; otherwise ``PROMOTED`` or
        ``ALREADY_PRESENT`` with the fact id.

    Raises:
        RuntimeError: If the candidate's compare-and-set lost inside the transaction (another
            writer resolved it between the read and the write). The transaction is rolled back.
        ValueError: If the canonical writer rejects the value or confidence. Rolled back.
        BrainMemoryError: If the database is not open. Rolled back.
    """
    person_id = actor.person_id
    if person_id is None:
        # No person to name: authorize_step needs a subject, so the refusal is logged here.
        _log_denied(CandidateReason.STRONG_UNREACHABLE, candidate_id, correlation_id)
        return PromotionResult(PromotionOutcome.DENIED)
    # The kill-switch and the face-and-voice rule are refused (and logged) by authorize_step.
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
        return PromotionResult(PromotionOutcome.DENIED)
    async with db.transaction() as conn:
        scrubbed = await run_housekeeping(conn, now)
        result = await _promote_in_transaction(
            conn, candidate_id, person_id, correlation_id=correlation_id, now=now
        )
    # A resolution erased the candidate's value; a refusal changed nothing.
    resolved = result.outcome is not PromotionOutcome.NOT_OFFERED
    await checkpoint_after_scrub(scrubbed + int(resolved))
    logger.info(
        "Candidate promotion: %s",
        result.outcome.value,
        extra={
            "event": _PROMOTION_EVENT,
            "outcome": result.outcome,
            "candidate_id": candidate_id,
            "fact_id": result.fact_id,
            "correlation_id": str(correlation_id),
        },
    )
    return result


def _log_denied(reason: CandidateReason, candidate_id: int, correlation_id: UUID) -> None:
    """Log one early denial: ids and a closed reason, never a value."""
    logger.info(
        "Candidate promotion: %s (%s)",
        PromotionOutcome.DENIED.value,
        reason.value,
        extra={
            "event": _PROMOTION_EVENT,
            "outcome": PromotionOutcome.DENIED,
            "reason": reason,
            "candidate_id": candidate_id,
            "correlation_id": str(correlation_id),
        },
    )


async def _promote_in_transaction(
    conn: aiosqlite.Connection,
    candidate_id: int,
    person_id: int,
    *,
    correlation_id: UUID,
    now: datetime,
) -> PromotionResult:
    """Run steps 1 (after housekeeping) to 5 inside the transaction the caller opened."""
    candidate = await get_candidate_in_transaction(conn, candidate_id)
    if (
        candidate is None
        or candidate.subject_person_id != person_id
        or candidate.status is not CandidateStatus.OFFERED
        or candidate.value_key is None
        or candidate.value_text is None
        or candidate.expires_at <= iso_utc(now)
    ):
        return PromotionResult(PromotionOutcome.NOT_OFFERED)
    definition = resolve_predicate(candidate.predicate)
    if definition is None:
        return PromotionResult(PromotionOutcome.NOT_OFFERED)

    opposite = _OPPOSITE.get(definition.canonical_id)
    opposite_definition = resolve_predicate(opposite) if opposite else None
    if opposite_definition is not None:
        clashing = await get_active_literal_facts(
            subject_entity_id=person_id, definition=opposite_definition
        )
        if any(comparison_key(fact.value_text) == candidate.value_key for fact in clashing):
            await _resolve(
                conn, candidate_id, person_id, CandidateStatus.REJECTED, correlation_id, now, None
            )
            return PromotionResult(PromotionOutcome.CONTRADICTION)

    active = await get_active_literal_facts(subject_entity_id=person_id, definition=definition)
    present = next(
        (fact for fact in active if comparison_key(fact.value_text) == candidate.value_key), None
    )
    if present is not None:
        await _resolve(
            conn,
            candidate_id,
            person_id,
            CandidateStatus.CONFIRMED,
            correlation_id,
            now,
            present.id,
        )
        return PromotionResult(PromotionOutcome.ALREADY_PRESENT, present.id)

    fact = await write_literal(
        owner_entity_id=person_id,
        subject_entity_id=person_id,
        predicate=definition.canonical_id,
        value=candidate.value_text,
        channel=WriteChannel(candidate.channel.value),
        confirmed_at=iso_utc(now),
        confidence=1.0,
        asserted_at=candidate.proposed_at,
        manage_transaction=False,
    )
    await _resolve(
        conn, candidate_id, person_id, CandidateStatus.CONFIRMED, correlation_id, now, fact.id
    )
    return PromotionResult(PromotionOutcome.PROMOTED, fact.id)


async def _resolve(
    conn: aiosqlite.Connection,
    candidate_id: int,
    person_id: int,
    to: CandidateStatus,
    correlation_id: UUID,
    now: datetime,
    fact_id: int | None,
) -> None:
    """Resolve the candidate in the open transaction; a lost compare-and-set rolls it back."""
    resolved = await resolve_candidate_in_transaction(
        conn,
        candidate_id,
        person_id,
        to=to,
        correlation_id=correlation_id,
        now=now,
        promoted_fact_id=fact_id,
    )
    if not resolved:
        raise RuntimeError("candidate resolution lost its compare-and-set inside the transaction")
