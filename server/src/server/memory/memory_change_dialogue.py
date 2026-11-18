"""Correct a taste or set a memory aside by voice (Plan 0086 D-5 to D-7, ADR 0032 decisions 3, 4).

As a person's memory does, the robot replaces or sets aside what it knew; it never destroys it
on a spoken word (a deletion for good is ``iroko-admin``'s, with the PIN). Two steps:

1. ``propose_change``: the owner's face (``basic``, no token) says a change of the closed grammar
   (``cognition.memory_change``); the robot reads it back and asks «Dime: sí, autorizo.». The
   pending change lives **in this process**, one per person, for the answer window; a restart
   loses it and changes nothing.
2. ``answer_change``: the same face says a closed verb alone; the policy is asked and audited
   (``correct_personal_memory`` or ``archive_personal_memory``) before anything is written, then
   the correction (the old taste becomes history, the new one current) or the archive (the
   scope's rows get one ``archived_at``) commits in one transaction.

Anything above ``normal``, a care contact and an enrolled person are refused with the fixed
phrase that points to ``iroko-admin``. Nothing here logs a value or a name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING, Literal

from server import db
from server.cognition.authorization import (
    AuthorizationRequest,
    ConsentStatus,
    DataSensitivity,
    DataVisibility,
    evaluate_authorization,
)
from server.cognition.models import AuthorizationAction, AuthorizationStatus
from server.cognition.response_plan import MemoryAnswerReply
from server.memory import continuity
from server.memory.canonical_writer import WriteChannel, write_literal
from server.memory.forget_scope import archive_rows, person_scope
from server.memory.household_authorization import record_authorization_decision
from server.memory.lexicon import (
    CHANGE_ADMIN_ONLY,
    CHANGE_ARCHIVE_ONE_QUESTION,
    CHANGE_ARCHIVE_QUESTION,
    CHANGE_ARCHIVED,
    CHANGE_CORRECT_QUESTION,
    CHANGE_CORRECTED,
    CHANGE_DECLINED,
    CHANGE_FAILED,
    CHANGE_NOTHING_TO_ARCHIVE,
    CHANGE_NOTHING_TO_CORRECT,
    CHANGE_REPLACE_QUESTION,
    CHANGE_TASTES,
    OFFER_VERB_PLURAL,
    OFFER_VERB_SINGULAR,
    PLURAL_ARTICLES,
)
from server.memory.predicate_registry import resolve_predicate
from server.memory.preference_gate import match_preference
from server.memory.profile_card_access import may_read_own_memory
from server.memory.relational_v4 import (
    get_active_literal_facts,
    revoke_literal_fact,
    supersede_literal_fact,
    unarchive_literal_fact,
)
from server.settings import settings
from server.text_keys import comparison_key
from server.timestamps import instant_text

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from uuid import UUID

    from server.cognition.identity import ActivePersonContext
    from server.cognition.intent_resolution import MemoryAnswer
    from server.cognition.memory_change import MemoryChange
    from server.cognition.models import AuthorizationDecision

__all__ = [
    "answer_change",
    "compose_taste",
    "has_any_pending_change",
    "has_pending_change",
    "propose_change",
    "reset_pending_changes",
]

logger = logging.getLogger(__name__)

type PolicyEvaluator = Callable[[AuthorizationRequest], AuthorizationDecision]
type AuditWriter = Callable[[AuthorizationRequest, AuthorizationDecision], Awaitable[object]]

_NORMAL = "normal"
_PERSONAL = "personal"
# The first-person trigger that declares each taste, to check a correction's new value.
_GATE_TRIGGERS = {"likes": "me gusta", "dislikes": "no me gusta", "prefers": "prefiero"}
_EVENT = "memory.change"


@dataclass(frozen=True)
class _Pending:
    """One change read back and waiting for its closed verb; ``repr`` shows no value."""

    kind: Literal["correct", "archive"]
    expires_at: datetime
    channel: WriteChannel
    fact_id: int | None = None
    replacement: str | None = field(default=None, repr=False)
    replacement_predicate: str | None = None
    facts: tuple[int, ...] = ()
    relations: tuple[int, ...] = ()
    units: tuple[int, ...] = ()
    topics: tuple[int, ...] = ()


_PENDING: dict[int, _Pending] = {}


def reset_pending_changes() -> None:
    """Forget every pending change (a test's isolation; a restart does the same)."""
    _PENDING.clear()


def has_pending_change(person_id: int, now: datetime) -> bool:
    """Whether *person_id* has a change read back and still waiting: no offer is spoken then."""
    pending = _PENDING.get(person_id)
    return pending is not None and pending.expires_at > now


def has_any_pending_change(now: datetime) -> bool:
    """Whether any change waits for its verb in this process (a route binds the answer then)."""
    return any(pending.expires_at > now for pending in _PENDING.values())


def compose_taste(predicate: str, value: str) -> str:
    """«te gusta el té», «te gustan los porotos», «no te gusta …», «prefieres …».

    Args:
        predicate: ``likes``, ``dislikes`` or ``prefers``.
        value: The value as stored or said, article included.

    Returns:
        The clause of the read-back.
    """
    first = value.split(maxsplit=1)[0].casefold() if value.strip() else ""
    verb = OFFER_VERB_PLURAL if first in PLURAL_ARTICLES else OFFER_VERB_SINGULAR
    return CHANGE_TASTES[predicate].format(verb=verb, value=value)


def _log(outcome: str, correlation_id: UUID) -> None:
    logger.info(
        "Memory change: %s",
        outcome,
        extra={"event": _EVENT, "outcome": outcome, "correlation_id": str(correlation_id)},
    )


def _ask(phrase: str) -> MemoryAnswerReply:
    return MemoryAnswerReply(phrase, expects_short_reply=True)


async def _propose_correction(
    change: MemoryChange, person_id: int, *, channel: WriteChannel, now: datetime
) -> tuple[MemoryAnswerReply, _Pending | None]:
    predicate = change.predicate or ""
    definition = resolve_predicate(predicate)
    if definition is None:
        return MemoryAnswerReply(CHANGE_FAILED), None
    key = comparison_key(change.target)
    facts = await get_active_literal_facts(subject_entity_id=person_id, definition=definition)
    fact = next((row for row in facts if comparison_key(row.value_text) == key), None)
    if fact is None:
        old = compose_taste(predicate, change.target)
        return MemoryAnswerReply(CHANGE_NOTHING_TO_CORRECT.format(old=old)), None
    if fact.sensitivity != _NORMAL or fact.visibility != _PERSONAL:
        return MemoryAnswerReply(CHANGE_ADMIN_ONLY), None
    old = compose_taste(predicate, fact.value_text)
    pending = _Pending(
        kind="correct",
        expires_at=now + timedelta(seconds=settings.memory_candidate_answer_seconds),
        channel=channel,
        fact_id=fact.id,
        replacement=change.replacement,
        replacement_predicate=change.replacement_predicate,
    )
    if change.replacement is None or change.replacement_predicate is None:
        return _ask(CHANGE_CORRECT_QUESTION.format(old=old)), pending
    if not _passes_the_taste_gate(change.replacement_predicate, change.replacement):
        return MemoryAnswerReply(CHANGE_ADMIN_ONLY), None
    new = compose_taste(change.replacement_predicate, change.replacement)
    return _ask(CHANGE_REPLACE_QUESTION.format(old=old, new=new)), pending


def _passes_the_taste_gate(predicate: str, value: str) -> bool:
    """Whether a new value is a taste the preference gate would accept as said.

    A correction's new value enters the store without a candidate, so it meets the same filters
    first (ADR 0021 decision 4): no person, place, health, money, credential or disclosure word,
    no clause, one taste of that polarity.
    """
    trigger = _GATE_TRIGGERS.get(predicate)
    if trigger is None:
        return False
    matches = match_preference(f"{trigger} {value}").matches
    return len(matches) == 1 and matches[0].predicate == predicate


async def _own_tastes_named(person_id: int, target: str) -> tuple[int, ...]:
    """The owner's own ordinary tastes whose value is *target* («olvídate del té»)."""
    key = comparison_key(target)
    found: list[int] = []
    for predicate in CHANGE_TASTES:
        definition = resolve_predicate(predicate)
        if definition is None:
            continue
        found += [
            fact.id
            for fact in await get_active_literal_facts(
                subject_entity_id=person_id, definition=definition
            )
            if comparison_key(fact.value_text) == key and fact.sensitivity == _NORMAL
        ]
    return tuple(found)


async def _propose_archive(
    change: MemoryChange, person_id: int, *, channel: WriteChannel, now: datetime
) -> tuple[MemoryAnswerReply, _Pending | None]:
    scope = await person_scope(person_id, now=instant_text(now), words=change.target)
    if scope.enrolled or scope.above_normal or scope.contacts or not scope.all_personal:
        return MemoryAnswerReply(CHANGE_ADMIN_ONLY), None
    tastes = await _own_tastes_named(person_id, change.target)
    count = scope.archivable + len(tastes)
    if count == 0:
        return MemoryAnswerReply(CHANGE_NOTHING_TO_ARCHIVE.format(target=change.target)), None
    pending = _Pending(
        kind="archive",
        expires_at=now + timedelta(seconds=settings.memory_candidate_answer_seconds),
        channel=channel,
        facts=(*scope.facts, *tastes),
        relations=scope.relations,
        units=scope.units,
        topics=scope.topics,
    )
    question = (
        CHANGE_ARCHIVE_ONE_QUESTION.format(target=change.target)
        if count == 1
        else CHANGE_ARCHIVE_QUESTION.format(count=count, target=change.target)
    )
    return _ask(question), pending


async def propose_change(
    change: MemoryChange,
    *,
    actor: ActivePersonContext,
    channel: WriteChannel,
    correlation_id: UUID,
    now: datetime,
) -> MemoryAnswerReply | None:
    """Read a spoken change back and keep it pending, or fall through (``None``).

    The caller resolved the actor before calling, for every message of this shape.

    Args:
        change: The parsed change.
        actor: The turn's observed actor; only the owner's own face (``basic``, no token) goes on.
        channel: The route's write channel, for a correction's new fact.
        correlation_id: The turn's id.
        now: The caller's clock reading.

    Returns:
        The fixed read-back (or a fixed refusal or «nothing stored»); ``None`` for anyone else,
        so a stranger hears ordinary conversation and nothing is pending. Never raises.
    """
    person_id = actor.person_id
    if person_id is None or not may_read_own_memory(actor):
        return None
    try:
        if change.kind == "correct":
            reply, pending = await _propose_correction(change, person_id, channel=channel, now=now)
        else:
            reply, pending = await _propose_archive(change, person_id, channel=channel, now=now)
    except Exception as exc:  # fail closed: the owner asked, so a fixed phrase, never the model
        logger.warning("Memory change read-back failed (%s)", type(exc).__name__, exc_info=True)
        _log("failed", correlation_id)
        _PENDING.pop(person_id, None)
        return MemoryAnswerReply(CHANGE_FAILED)
    # The latest request is the open question: an older read-back is dropped even when this one
    # proposes nothing, so a verb never applies a change the owner moved on from.
    _PENDING.pop(person_id, None)
    if pending is not None:
        _PENDING[person_id] = pending
    _log("proposed" if pending is not None else "not_proposed", correlation_id)
    return reply


async def _allowed(
    pending: _Pending,
    actor: ActivePersonContext,
    person_id: int,
    *,
    correlation_id: UUID,
    now: datetime,
    policy: PolicyEvaluator,
    audit: AuditWriter,
) -> bool:
    action = (
        AuthorizationAction.CORRECT_PERSONAL_MEMORY
        if pending.kind == "correct"
        else AuthorizationAction.ARCHIVE_PERSONAL_MEMORY
    )
    request = AuthorizationRequest(
        actor=actor,
        action=action,
        target_person_id=person_id,
        visibility=frozenset({DataVisibility.PERSONAL}),
        sensitivity=frozenset({DataSensitivity.NORMAL}),
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=correlation_id,
        requested_at=now,
    )
    decision = policy(request)
    await audit(request, decision)  # the audit precedes the effect; a failure means no effect
    return decision.decision is AuthorizationStatus.ALLOWED


async def _apply_correction(pending: _Pending, person_id: int, now: datetime) -> None:
    at = instant_text(now)
    old = pending.fact_id
    if old is None:
        raise ValueError("a correction names its fact")
    async with db.transaction() as conn:
        if pending.replacement is None or pending.replacement_predicate is None:
            await revoke_literal_fact(old, revoked_at=at, manage_transaction=False)
            return
        new = await write_literal(
            owner_entity_id=person_id,
            subject_entity_id=person_id,
            predicate=pending.replacement_predicate,
            value=pending.replacement,
            channel=pending.channel,
            confirmed_at=at,
            confidence=1.0,
            manage_transaction=False,
        )
        if new.archived_at is not None:
            await unarchive_literal_fact(conn, new.id)
        if new.id != old:
            await supersede_literal_fact(conn, old, by=new.id, at=at)


async def _apply_archive(pending: _Pending, now: datetime) -> None:
    async with db.transaction() as conn:
        await archive_rows(
            conn,
            facts=pending.facts,
            relations=pending.relations,
            units=pending.units,
            topics=pending.topics,
            at=instant_text(now),
        )
    # The short-term session may still carry what was just set aside: the next turn starts clean.
    continuity.reset()


async def answer_change(
    answer: MemoryAnswer,
    *,
    actor: ActivePersonContext,
    correlation_id: UUID,
    now: datetime,
    policy: PolicyEvaluator = evaluate_authorization,
    audit: AuditWriter = record_authorization_decision,
) -> MemoryAnswerReply | None:
    """Apply or decline the speaker's pending change, or fall through (``None``).

    Args:
        answer: The parsed answer; only a closed verb alone (no value) answers a change.
        actor: The turn's observed actor; the owner's own face (``basic``) is enough.
        correlation_id: The answering turn's id.
        now: The caller's clock reading.
        policy: The pure evaluator; tests inject doubles.
        audit: The audit writer; tests inject doubles.

    Returns:
        A fixed result phrase; ``None`` when this speaker has no pending change in the window
        (the answer then goes on to the memory offer, or to ordinary conversation). Never
        raises.
    """
    person_id = actor.person_id
    if person_id is None or answer.phrase or not may_read_own_memory(actor):
        return None
    if not has_pending_change(person_id, now):
        _PENDING.pop(person_id, None)
        return None
    pending = _PENDING.pop(person_id)
    if not answer.accept:
        _log("declined", correlation_id)
        return MemoryAnswerReply(CHANGE_DECLINED)
    try:
        if not await _allowed(
            pending,
            actor,
            person_id,
            correlation_id=correlation_id,
            now=now,
            policy=policy,
            audit=audit,
        ):
            _log("denied", correlation_id)
            return MemoryAnswerReply(CHANGE_FAILED)
        if pending.kind == "correct":
            await _apply_correction(pending, person_id, now)
        else:
            await _apply_archive(pending, now)
    except Exception as exc:  # fail closed and tell the owner: the change was theirs
        logger.warning("Memory change failed (%s)", type(exc).__name__, exc_info=True)
        _log("failed", correlation_id)
        return MemoryAnswerReply(CHANGE_FAILED)
    _log(pending.kind, correlation_id)
    return MemoryAnswerReply(CHANGE_CORRECTED if pending.kind == "correct" else CHANGE_ARCHIVED)
