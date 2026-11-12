"""Who may hear the owner's sensitive data, and the one place that reads it (Plan 0079, ADR 0029).

``sensitive_reply`` answers one recognized question. The order is fixed and every step fails
closed:

1. For a child's birthday only, the household decision (D-5), before any audience or policy
   check: a family word, or, for the face-identified owner alone, a stored name, makes it a
   household question; anything else is ordinary conversation (``NOT_HOUSEHOLD``).
2. Two faces in view: ``NOT_ALONE``. Nothing is read, nothing is audited.
3. Not a face-identified speaker at ``basic`` or more: ``DENIED``, the answer a stranger hears.
4. A security question below ``strong``: ``RETRY_VOICE`` only when the voice exists to be retried
   (D-11), else ``DENIED``.
5. The consent (D-9), the policy request (D-10) and its audit row **before** the read. A
   failing audit means no read at all.
6. The read, then the fixed wording of ``sensitive_answers``.

The level of a topic comes only from ``TOPIC_LEVEL`` and its labels only from ``TOPIC_LABEL``,
never from what is stored. The children's birth dates go through ``HouseholdKnowledgeTools``,
which composes the paths that already authorize and audit them. The function never raises: any
failure is ``UNAVAILABLE`` with one warning that names the exception class and nothing else, and
exactly one ``sensitive.read`` line is logged per call, with the topic, the level, the outcome and
a count, never a value or a keyword.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
import logging
from typing import TYPE_CHECKING, Final

from server.cognition.authorization import (
    ASSURANCE_RANK,
    AuthorizationRequest,
    ConsentStatus,
    DataSensitivity,
    DataVisibility,
    evaluate_authorization,
)
from server.cognition.household_request import CHILD_WORDS
from server.cognition.identity import HouseholdRole, IdentityAssurance
from server.cognition.identity_fusion import FusionReason
from server.cognition.models import AuthorizationAction, AuthorizationStatus, KnowledgeStatus
from server.cognition.recall_cues import RELATIVE_WORDS
from server.cognition.response_plan import NO_BIRTH_DATE, SensitiveOutcome, SensitiveReply
from server.cognition.sensitive_answers import word_children_birthdays, word_own_answer
from server.cognition.sensitive_questions import (
    CONTACT_TOPICS,
    TOPIC_LABEL,
    TOPIC_LEVEL,
    TOPIC_PREDICATE,
    SensitiveLevel,
    SensitiveTopic,
)
from server.memory.care_contacts import list_active_contacts
from server.memory.commissioning import has_closed_commissioning
from server.memory.contact_access import contact_reply, is_own_contact_question, stored_name
from server.memory.entity_labels import read_household_names
from server.memory.household_authorization import record_authorization_decision
from server.memory.profile_card_access import may_read_own_memory
from server.memory.sensitive_store import read_own_values
from server.text_keys import normalize_spanish

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import datetime
    from uuid import UUID

    from server.cognition.household_tools import ChildBirthdays, HouseholdKnowledgeTools
    from server.cognition.identity import ActivePersonContext
    from server.cognition.sensitive_questions import SensitiveQuery
    from server.memory.candidate_policy import AuditWriter, PolicyEvaluator
    from server.memory.contact_access import ContactsReader, NameReader

logger = logging.getLogger(__name__)

__all__ = ["sensitive_reply"]

type OwnValuesReader = Callable[[int, str, str], Awaitable[tuple[str, ...]]]
type NamesReader = Callable[[], Awaitable[frozenset[str]]]
type AltaChecker = Callable[[], Awaitable[bool]]


class _ChildScope(StrEnum):
    """What a child's birthday question is about, once it is a household question."""

    ALL = "all"  # a word such as «hijos»
    NAMED = "named"  # a stored name, said by the face-identified owner alone
    RELATIVE = "relative"  # «mamá», «hermano»: the alta stores no birth date for them
    NONE = "none"  # ordinary conversation


@dataclass(frozen=True)
class _Call:
    """One call's inputs and seams, so the steps share them without long parameter lists."""

    actor: ActivePersonContext
    query: SensitiveQuery
    faces: FusionReason | None
    face_consent: ConsentStatus
    voice_check: bool
    correlation_id: UUID
    now: datetime
    household_tools: HouseholdKnowledgeTools
    policy: PolicyEvaluator
    audit: AuditWriter
    alta_closed: AltaChecker
    names: NamesReader
    reader: OwnValuesReader
    contacts: ContactsReader
    contact_names: NameReader


@dataclass(frozen=True)
class _Done:
    """A step's result: the reply and how many entries it concerned (a count for the log)."""

    reply: SensitiveReply
    entries: int = 0


_REFERENCE_TOPICS: Final = frozenset(
    {SensitiveTopic.SECRET_HOLDER, SensitiveTopic.DOCUMENT_LOCATION}
)
# Sensitivities whose read needs the person's consent and a closed alta (D-9).
_CONSENT_SENSITIVITIES: Final = frozenset({"medical", "location", "security"})
_NOT_REGISTERED_BIRTH_DATE: Final = SensitiveReply(SensitiveOutcome.NOT_REGISTERED, NO_BIRTH_DATE)


def _done(outcome: SensitiveOutcome, text: str | None = None, entries: int = 0) -> _Done:
    return _Done(SensitiveReply(outcome, text), entries)


async def sensitive_reply(
    actor: ActivePersonContext,
    query: SensitiveQuery,
    *,
    faces: FusionReason | None,
    face_consent: ConsentStatus,
    voice_check: bool,
    correlation_id: UUID,
    now: datetime,
    household_tools: HouseholdKnowledgeTools,
    policy: PolicyEvaluator = evaluate_authorization,
    audit: AuditWriter = record_authorization_decision,
    alta_closed: AltaChecker = has_closed_commissioning,
    names: NamesReader = read_household_names,
    reader: OwnValuesReader = read_own_values,
    contacts: ContactsReader = list_active_contacts,
    contact_names: NameReader = stored_name,
) -> SensitiveReply:
    """Answer one sensitive question after the audience, level, consent and policy checks.

    Args:
        actor: The turn's resolved speaker.
        query: The recognized question: its topic and the words that narrow it.
        faces: How the turn's identity ended (the fusion reason), or ``None`` without a frame.
        face_consent: The consent the face path resolved for the speaker.
        voice_check: Whether the voice can still be asked for again (speaker authentication is
            on); a security question retries only then.
        correlation_id: The turn's id, so the audit rows join to the rest of the turn.
        now: The caller's clock reading.
        household_tools: The tools that read the children and their birth dates.
        policy: The pure evaluator; tests inject doubles.
        audit: The audit writer; tests inject doubles.
        alta_closed: Whether a commissioning is closed (one ``SELECT``, no cache).
        names: The household's stored names, for the child's birthday decision.
        reader: The owner's values query; tests inject doubles.
        contacts: The owner's active contacts (Plan 0082); tests inject doubles.
        contact_names: A contact's stored name (Plan 0082); tests inject doubles.

    Returns:
        The reply; ``text`` carries the answer only for ``ANSWERED`` and, for a birth date not
        registered, the fixed ``NO_BIRTH_DATE``. It never raises.
    """
    call = _Call(
        actor,
        query,
        faces,
        face_consent,
        voice_check,
        correlation_id,
        now,
        household_tools,
        policy,
        audit,
        alta_closed,
        names,
        reader,
        contacts,
        contact_names,
    )
    try:
        result = await _decide(call)
    except Exception as exc:  # fail closed: a store, tool or template failure is no answer
        logger.warning("Sensitive read failed (%s)", type(exc).__name__)
        result = _done(SensitiveOutcome.UNAVAILABLE)
    topic = query.topic
    logger.info(
        "Sensitive read: %s %s",
        topic.value,
        result.reply.outcome.value,
        extra={
            "event": "sensitive.read",
            "topic": topic.value,
            "level": TOPIC_LEVEL[topic].value,
            "outcome": result.reply.outcome.value,
            "entries": result.entries,
        },
    )
    return result.reply


async def _decide(call: _Call) -> _Done:
    """Run the fixed order; each early return is a refusal that reads nothing."""
    scope = _ChildScope.NONE
    if call.query.topic in CONTACT_TOPICS and not is_own_contact_question(call.query):
        return _done(SensitiveOutcome.NOT_HOUSEHOLD)  # nobody's own contact: nothing read (D-6)
    if call.query.topic is SensitiveTopic.CHILD_BIRTHDAY:
        scope = await _child_scope(call)
        if scope is _ChildScope.NONE:
            return _done(SensitiveOutcome.NOT_HOUSEHOLD)
    if call.faces is FusionReason.VETO_MULTIPLE_FACES:
        return _done(SensitiveOutcome.NOT_ALONE)
    if not may_read_own_memory(call.actor):
        return _done(SensitiveOutcome.DENIED)
    if TOPIC_LEVEL[call.query.topic] is SensitiveLevel.SECURITY and not _is_strong(call):
        retry = call.voice_check and call.faces is FusionReason.FACE_ONLY
        return _done(SensitiveOutcome.RETRY_VOICE if retry else SensitiveOutcome.DENIED)
    return await _read(call, scope)


async def _read(call: _Call, scope: _ChildScope) -> _Done:
    """Once every check passed, read the store the topic lives in."""
    if call.query.topic is SensitiveTopic.CHILD_BIRTHDAY:
        return await _read_children(call, scope)
    if call.query.topic in CONTACT_TOPICS:
        return await _read_contacts(call)
    return await _read_own(call)


async def _read_contacts(call: _Call) -> _Done:
    """The contacts' one policy request, its audit row, then the read (Plan 0082, D-8)."""
    reply, entries = await contact_reply(
        call.actor,
        call.query,
        consent=await _consent(call, DataSensitivity.LOCATION.value),
        correlation_id=call.correlation_id,
        now=call.now,
        policy=call.policy,
        audit=call.audit,
        contacts=call.contacts,
        names=call.contact_names,
    )
    return _Done(reply, entries)


def _is_strong(call: _Call) -> bool:
    return ASSURANCE_RANK[call.actor.assurance] >= ASSURANCE_RANK[IdentityAssurance.STRONG]


async def _child_scope(call: _Call) -> _ChildScope:
    """Decide whether a child's birthday question is a household question (D-5).

    A stored name counts only for the face-identified owner alone: for anyone else (a visitor, a
    face-identified child or adult, two faces) a refusal would confirm the name exists (Plan
    0077), so it stays ordinary conversation.
    """
    words = frozenset(call.query.keywords)
    if words & CHILD_WORDS:
        return _ChildScope.ALL
    owner_alone = (
        call.faces is not FusionReason.VETO_MULTIPLE_FACES
        and may_read_own_memory(call.actor)
        and call.actor.role is HouseholdRole.OWNER
    )
    if owner_alone and words and _names_hit(words, await call.names()):
        return _ChildScope.NAMED
    if words & RELATIVE_WORDS:
        return _ChildScope.RELATIVE
    return _ChildScope.NONE


def _names_hit(words: frozenset[str], stored: frozenset[str]) -> bool:
    """Whether a word is a stored name or a whole word of one, compared folded."""
    for name in stored:
        folded = normalize_spanish(name)
        if folded in words or words & set(folded.split()):
            return True
    return False


async def _consent(call: _Call, sensitivity: str) -> ConsentStatus:
    """The consent of an own read (D-9): the face's grant and a closed alta, or none."""
    if sensitivity not in _CONSENT_SENSITIVITIES:
        return ConsentStatus.NOT_REQUIRED
    if call.face_consent is ConsentStatus.GRANTED and await call.alta_closed():
        return ConsentStatus.GRANTED
    return ConsentStatus.MISSING


async def _read_own(call: _Call) -> _Done:
    """Policy, the audit row, then the read of the owner's own values (D-10)."""
    topic = call.query.topic
    person_id = call.actor.person_id
    if person_id is None:  # unreachable after the pre-check; the type narrows here
        return _done(SensitiveOutcome.DENIED)
    visibility, sensitivity = TOPIC_LABEL[topic]
    request = AuthorizationRequest(
        actor=call.actor,
        action=AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY,
        target_person_id=person_id,
        visibility=frozenset({DataVisibility(visibility)}),
        sensitivity=frozenset({DataSensitivity(sensitivity)}),
        consent=await _consent(call, sensitivity),
        correlation_id=call.correlation_id,
        requested_at=call.now,
    )
    decision = call.policy(request)
    await call.audit(request, decision)  # a failing audit propagates: no read at all
    if decision.decision is not AuthorizationStatus.ALLOWED:
        return _done(SensitiveOutcome.DENIED)
    values = await call.reader(person_id, TOPIC_PREDICATE[topic], sensitivity)
    if not values:
        return _done(SensitiveOutcome.NOT_REGISTERED)
    chosen = _matching_entries(topic, values, frozenset(call.query.keywords))
    return _done(SensitiveOutcome.ANSWERED, word_own_answer(topic, chosen), len(chosen))


def _matching_entries(
    topic: SensitiveTopic, values: tuple[str, ...], keywords: frozenset[str]
) -> tuple[str, ...]:
    """Select the reference entries a keyword names; none selected means all of them (D-5)."""
    if topic not in _REFERENCE_TOPICS or not keywords:
        return values
    matching = tuple(value for value in values if keywords & set(normalize_spanish(value).split()))
    return matching or values


async def _read_children(call: _Call, scope: _ChildScope) -> _Done:
    """Read the children's birth dates through the household tools and word the selection."""
    person_id = call.actor.person_id
    if scope is _ChildScope.RELATIVE or person_id is None:
        return _Done(_NOT_REGISTERED_BIRTH_DATE)  # the alta stores no birth date for relatives
    result = await call.household_tools.get_children_birthdays(
        parent_entity_id=person_id,
        actor=call.actor,
        consent=call.face_consent,
        correlation_id=call.correlation_id,
        requested_at=call.now,
    )
    if result.status is KnowledgeStatus.UNAUTHORIZED:
        return _done(SensitiveOutcome.DENIED)
    if result.status is not KnowledgeStatus.KNOWN or not result.children:
        return _done(SensitiveOutcome.NOT_REGISTERED)
    chosen = _chosen_children(result, scope, frozenset(call.query.keywords))
    if not any(born is not None for _label, born in chosen):
        return _Done(_NOT_REGISTERED_BIRTH_DATE, len(chosen))
    text = word_children_birthdays(
        tuple((label, None if born is None else date.fromisoformat(born)) for label, born in chosen)
    )
    return _done(SensitiveOutcome.ANSWERED, text, len(chosen))


def _chosen_children(
    result: ChildBirthdays, scope: _ChildScope, keywords: frozenset[str]
) -> tuple[tuple[str, str | None], ...]:
    """The children a keyword names; only when none is named, all of them for a family word.

    A matching child label wins («mi hijo Zeta» is Zeta); a family word alone selects every child.
    """
    named = tuple(
        child for child in result.children if keywords & set(normalize_spanish(child[0]).split())
    )
    if named or scope is not _ChildScope.ALL:
        return named
    return result.children
