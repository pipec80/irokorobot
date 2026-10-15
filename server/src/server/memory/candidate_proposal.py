"""Propose memory candidates from one successful generic voice turn (ADR 0021 decisions 3, 4, 7, 10).

It runs as a background task after the reply was sent and never touches the user's request:
every failure is swallowed and logged as a closed reason.

The order is deliberate, cheapest and most protective first:

1. the **gate** (pure) — does the text declare a first-person taste at all?
2. a **face actor** with no token, and no extraction already in flight;
3. the **voice** of this turn's own clip, for the person the face named — no clip, a clip below
   the floor, another voice or a backend failure means no candidate (the firewall rule);
4. the **limiter** — one extraction at a time, so many per hour;
5. the **extractor** — one model call that sees only the user's words, no retry;
6. the **classifier** — each triple is accepted or dropped by a pure function;
7. per accepted triple, in this order: a re-check that both consents are still active (the
   model call took a while); a read-only **pre-check** of what the store would refuse (a
   repeated taste, the per-person cap), so the audit log has no "allowed" row for it; the
   **policy** (``propose_personal_memory``) with its audit row; a second consent re-check
   immediately before the write (the audit waits on the write lock); and the **store**, which
   stays the authority and decides again inside its own transaction.

Audio contract for the clip: WAV, 16 000 Hz, mono, signed int16. It is held in memory only.
Logs carry ids, the predicate, a status and closed reasons — never a value, a transcript or an
exception message.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import aiosqlite
import httpx

from server.cognition.authorization import evaluate_authorization
from server.cognition.clock import utc_now
from server.cognition.strong_actor import is_face_actor, verify_face_and_voice
from server.exceptions import BrainMemoryError, LLMError
from server.memory.candidate_classifier import classify
from server.memory.candidate_extraction import extract_candidates
from server.memory.candidate_limits import limiter
from server.memory.candidate_policy import CandidateStep, authorize_step
from server.memory.candidate_types import (
    CandidateChannel,
    CandidateReason,
    GateMatch,
    ProposedCandidate,
    RawCandidate,
)
from server.memory.candidates import InsertStatus, insert_candidate, precheck_insert
from server.memory.enrollment import is_enrolled_for_strong
from server.memory.entity_labels import list_known_names
from server.memory.household_authorization import record_authorization_decision
from server.memory.preference_gate import match_preference
from server.settings import settings

if TYPE_CHECKING:
    from datetime import datetime

    from server.cognition.identity import ActivePersonContext
    from server.cognition.models import CognitiveEvent
    from server.cognition.response_plan import TextTurnPayload
    from server.memory.candidate_policy import AuditWriter, PolicyEvaluator

logger = logging.getLogger(__name__)

__all__ = ["ProposalOutcome", "propose_candidates"]

type Extractor = Callable[[httpx.AsyncClient, str], Awaitable[tuple[RawCandidate, ...]]]
type NameReader = Callable[[], Awaitable[frozenset[str]]]
type EnrollmentReader = Callable[[int], Awaitable[bool]]
type Clock = Callable[[], datetime]


class VoiceVerifier(Protocol):
    """The voice-check seam: ``verify_face_and_voice`` or a test double (same keyword names)."""

    def __call__(
        self,
        actor: ActivePersonContext,
        *,
        wav_bytes: bytes | None,
        event: CognitiveEvent[TextTurnPayload],
    ) -> Awaitable[ActivePersonContext | None]:
        """Return the actor fused at ``strong``, or ``None`` when the voice was not verified."""
        ...


# What an insert that did not store a candidate is reported as (`INSERTED` is absent).
_INSERT_REASONS = {
    InsertStatus.DUPLICATE: CandidateReason.DUPLICATE,
    InsertStatus.CAPACITY: CandidateReason.CAPACITY,
    InsertStatus.DISABLED: CandidateReason.DENIED,
}


@dataclass(frozen=True)
class ProposalOutcome:
    """What one proposal attempt did, in closed terms.

    Attributes:
        stored: Candidates inserted.
        reasons: The closed reason of every triple or step that did not become a candidate.
    """

    stored: int = 0
    reasons: tuple[CandidateReason, ...] = field(default=())


@dataclass
class _Tally:
    """What one run has done so far, so the failure boundary can report it truthfully."""

    stored: int = 0
    reasons: list[CandidateReason] = field(default_factory=list)


def _dropped(reason: CandidateReason, event: CognitiveEvent[TextTurnPayload]) -> ProposalOutcome:
    logger.info(
        "Candidate proposal: dropped (%s)",
        reason.value,
        extra={
            "event": "candidate.proposal",
            "stored": 0,
            "reason": reason,
            "correlation_id": str(event.correlation_id),
        },
    )
    return ProposalOutcome(reasons=(reason,))


def _innermost_frame(exc: Exception) -> tuple[str, int, str]:
    """Locate where *exc* was raised: file basename, line and function. Never the message."""
    traceback = exc.__traceback__
    if traceback is None:
        return "unknown", 0, "unknown"
    while traceback.tb_next is not None:
        traceback = traceback.tb_next
    code = traceback.tb_frame.f_code
    return Path(code.co_filename).name, traceback.tb_lineno, code.co_name


async def propose_candidates(
    client: httpx.AsyncClient,
    message: str,
    actor: ActivePersonContext,
    *,
    event: CognitiveEvent[TextTurnPayload],
    wav_bytes: bytes | None,
    channel: CandidateChannel,
    extract: Extractor = extract_candidates,
    verify: VoiceVerifier = verify_face_and_voice,
    read_names: NameReader = list_known_names,
    enrolled: EnrollmentReader = is_enrolled_for_strong,
    clock: Clock = utc_now,
    policy: PolicyEvaluator = evaluate_authorization,
    audit: AuditWriter = record_authorization_decision,
) -> ProposalOutcome:
    """Turn one generic voice turn into at most three stored candidates.

    Args:
        client: Shared, lifecycle-owned HTTP client (Plan 0039), for the extractor.
        message: The user's own transcript of this turn — never the assistant's reply.
        actor: The face-identified actor of the turn.
        event: The turn's event (its correlation id joins audit rows to candidates).
        wav_bytes: The turn's own clip — WAV, 16 000 Hz, mono, int16 — or ``None``.
        channel: The voice route this came from.
        extract: The extractor seam; tests inject doubles.
        verify: The voice-check seam; tests inject doubles.
        read_names: Reader of the names the household knows; tests inject doubles.
        enrolled: Reader of the composite enrolment; tests inject doubles.
        clock: Source of every timestamp the store keeps.
        policy: The pure policy evaluator; tests inject doubles.
        audit: The audit writer; tests inject doubles.

    Returns:
        The closed outcome. Never raises: any failure is logged by class and reported as a
        dropped step, because this runs after the user already got their reply.
    """
    tally = _Tally()
    try:
        return await _propose(
            client,
            message,
            actor,
            event=event,
            wav_bytes=wav_bytes,
            channel=channel,
            extract=extract,
            verify=verify,
            read_names=read_names,
            enrolled=enrolled,
            clock=clock,
            policy=policy,
            audit=audit,
            tally=tally,
        )
    except Exception as exc:  # background boundary: nothing may reach the user's request
        # Only the class and the place are logged: the message could carry a value.
        file_name, line, function = _innermost_frame(exc)
        logger.warning(
            "Candidate proposal failed (%s) at %s:%d in %s",
            type(exc).__name__,
            file_name,
            line,
            function,
            extra={
                "event": "candidate.proposal_error",
                "error_type": type(exc).__name__,
                # Not `filename`/`lineno`/`funcName`: those are reserved LogRecord attributes.
                "error_file": file_name,
                "error_line": line,
                "error_function": function,
                "stored": tally.stored,
                "correlation_id": str(event.correlation_id),
            },
        )
        return ProposalOutcome(
            stored=tally.stored, reasons=(*tally.reasons, CandidateReason.DENIED)
        )


def _refusal_before_voice(
    message: str, actor: ActivePersonContext
) -> tuple[tuple[GateMatch, ...], CandidateReason | None]:
    """Apply the free checks: kill-switch, gate, a token-free face actor, nothing in flight."""
    if not settings.memory_candidates_enabled:
        return (), CandidateReason.DENIED
    gate = match_preference(message)
    if gate.reason is not None:
        return (), gate.reason
    if not is_face_actor(actor):
        return (), CandidateReason.STRONG_UNREACHABLE
    if limiter.busy:
        return (), CandidateReason.BUSY
    return gate.matches, None


async def _extract_once(
    client: httpx.AsyncClient, message: str, extract: Extractor
) -> tuple[RawCandidate, ...] | CandidateReason:
    """Take the extraction slot, call the model once (no retry) and always release the slot."""
    refused = limiter.try_acquire()
    if refused is not None:
        return refused
    try:
        return await extract(client, message)
    except (LLMError, httpx.HTTPError) as exc:
        # The reason set is closed (ADR 0021): model-down and bad JSON both end as DENIED, and
        # only this event and the class tell them apart.
        logger.warning(
            "Candidate extraction failed (%s)",
            type(exc).__name__,
            extra={"event": "candidate.extraction_failed", "error_type": type(exc).__name__},
        )
        return CandidateReason.DENIED
    finally:
        limiter.release()


async def _propose(
    client: httpx.AsyncClient,
    message: str,
    actor: ActivePersonContext,
    *,
    event: CognitiveEvent[TextTurnPayload],
    wav_bytes: bytes | None,
    channel: CandidateChannel,
    extract: Extractor,
    verify: VoiceVerifier,
    read_names: NameReader,
    enrolled: EnrollmentReader,
    clock: Clock,
    policy: PolicyEvaluator,
    audit: AuditWriter,
    tally: _Tally,
) -> ProposalOutcome:
    """Run the steps in order; each early return is a closed reason.

    ``tally`` is filled as triples are stored, so a failure halfway still reports the truth.
    """
    matches, refusal = _refusal_before_voice(message, actor)
    if refusal is not None:
        return _dropped(refusal, event)
    strong = await verify(actor, wav_bytes=wav_bytes, event=event)
    if strong is None or strong.person_id is None:
        return _dropped(CandidateReason.STRONG_UNREACHABLE, event)
    raw = await _extract_once(client, message, extract)
    if isinstance(raw, CandidateReason):
        return _dropped(raw, event)
    known = await read_names()
    for triple in raw:
        verdict = classify(
            strong,
            triple,
            message,
            matches=matches,
            known_person_names=known,
        )
        if isinstance(verdict, CandidateReason):
            tally.reasons.append(verdict)
            continue
        outcome = await _store(
            verdict,
            strong,
            channel=channel,
            event=event,
            enrolled=enrolled,
            clock=clock,
            policy=policy,
            audit=audit,
        )
        if outcome is None:
            tally.stored += 1
        else:
            tally.reasons.append(outcome)
    logger.info(
        "Candidate proposal: stored=%d dropped=%d",
        tally.stored,
        len(tally.reasons),
        extra={
            "event": "candidate.proposal",
            "stored": tally.stored,
            "reasons": [reason.value for reason in tally.reasons],
            "channel": channel,
            "correlation_id": str(event.correlation_id),
        },
    )
    return ProposalOutcome(stored=tally.stored, reasons=tuple(tally.reasons))


async def _still_enrolled(enrolled: EnrollmentReader, person_id: int) -> bool:
    """Read the composite enrolment; a read that fails means "not enrolled" (fail closed)."""
    try:
        return await enrolled(person_id)
    except (BrainMemoryError, aiosqlite.Error) as exc:
        # Only the class is logged: the message of a database error can carry a row value.
        logger.warning(
            "Candidate enrolment check failed (%s): the step is denied",
            type(exc).__name__,
            extra={"event": "candidate.enrolment_check_failed", "error_type": type(exc).__name__},
        )
        return False


async def _store(
    proposal: ProposedCandidate,
    strong: ActivePersonContext,
    *,
    channel: CandidateChannel,
    event: CognitiveEvent[TextTurnPayload],
    enrolled: EnrollmentReader,
    clock: Clock,
    policy: PolicyEvaluator,
    audit: AuditWriter,
) -> CandidateReason | None:
    """Run one accepted triple through the checks and the store. ``None`` means it was stored.

    The order is: enrolment re-check, read-only pre-check, policy and audit row, a second
    enrolment re-check immediately before the write, insert. The pre-check keeps a repeated
    taste or a capped person from leaving an "allowed" audit row for nothing; it is advisory,
    so a race between it and the insert can still end in a refusal after an audit row, and
    ``insert_candidate`` is the authority. The second re-check closes the window in which a
    consent is revoked while the audit write waits for the write lock.
    """
    person_id = strong.person_id
    if person_id is None:
        return CandidateReason.DENIED
    # The model call took a while: a consent revoked meanwhile stops the write, and it is read
    # before the audit row so the log never says "allowed" for something that was not stored.
    if not await _still_enrolled(enrolled, person_id):
        return CandidateReason.STRONG_UNREACHABLE
    refused = await precheck_insert(proposal, subject_person_id=person_id)
    if refused is not None:
        return _INSERT_REASONS.get(refused, CandidateReason.DENIED)
    allowed = await authorize_step(
        CandidateStep.PROPOSE,
        actor=strong,
        subject_person_id=person_id,
        correlation_id=event.correlation_id,
        now=clock(),
        policy=policy,
        audit=audit,
    )
    if not allowed.allowed:
        return allowed.reason or CandidateReason.DENIED
    if not await _still_enrolled(enrolled, person_id):
        return CandidateReason.STRONG_UNREACHABLE
    result = await insert_candidate(
        proposal,
        subject_person_id=person_id,
        asserted_by_person_id=person_id,
        channel=channel,
        correlation_id=event.correlation_id,
        now=clock(),
    )
    return _INSERT_REASONS.get(result.status)
