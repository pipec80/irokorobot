"""The canonical memory writer: one place that stores a household fact, whatever the channel.

The spoken confirmation (CM-3a, through ``memory_writer.promote``) and the initial import of
Step 0 are two callers of the same functions (ADR 0022 decision 2; Plan 0050 rule 1): they
produce the same stored fact with the same classification, and the row records who asserted it
and through which channel. **The speaker never assigns the classification**: it is looked up
here, from the predicate and the subject, in one table (ADR 0022 decision 2, Plan 0065 D-2):

* the **owner's** own facts are ``personal`` with the registry's sensitivity, except the owner's
  ``birth_date``, which is ``personal``/``private``;
* a fact about a **child or a pet of the owner** is ``household`` with the registry's
  sensitivity (the stored label equals the registry default, which is what the household
  reader requires to serve it);
* a fact about the **partner**, or about anyone outside that closed set, is refused with the
  closed reason ``not_household_member`` (other adults: name and relationship only, decision 4).

"Child" means a child the owner is guardian of. The writer cannot tell a minor from an adult
child (no age is needed to say ``child_of``), so it classifies both alike; how an adult child is
treated is the Step 0 ADR's decision (ADR 0022 *Negative consequences*).

The asserter and the confirmer are the owner (ADR 0022 decision 0). A SECURITY value is refused
by the repository (``SecurityStorageUndecidedError``) and the error passes through untouched; no
value ever reaches a log or an exception message.
"""

from __future__ import annotations

from enum import StrEnum
import logging

from server import db
from server.exceptions import WriteRefusedError
from server.memory.predicate_registry import (
    PredicateDefinition,
    PredicateKind,
    normalize_literal,
    resolve_predicate,
)
from server.memory.relational_v4 import (
    LiteralFactV4,
    assert_literal_fact,
    get_active_entity_relations,
    get_active_literal_facts,
)

__all__ = ["WriteChannel", "WriteRefusal", "write_literal"]

logger = logging.getLogger(__name__)

_WRITE_EVENT = "memory.canonical_write"
_REFUSED_EVENT = "memory.canonical_write_refused"
_PERSONAL = "personal"
_HOUSEHOLD = "household"
_PRIVATE = "private"
# The owner's own facts that are private rather than merely personal (ADR 0022, Plan 0065 D-2).
_OWNER_PRIVATE_LITERALS = frozenset({"birth_date"})


class WriteChannel(StrEnum):
    """Closed list of the channels a fact can arrive through (Plan 0065 D-6).

    The first two are the values a memory candidate already carries; ``import_file`` is the
    initial load of Step 0. A perceptual channel is added when that source exists.
    """

    VOICE_CLASSIC = "voice_classic"
    VOICE_STREAM = "voice_stream"
    IMPORT_FILE = "import_file"


class WriteRefusal(StrEnum):
    """Closed reasons the writer refuses a write for."""

    NOT_HOUSEHOLD_MEMBER = "not_household_member"


def _required_predicate(alias: str) -> PredicateDefinition:
    """Resolve a registry predicate this closed module depends on."""
    definition = resolve_predicate(alias)
    if definition is None:
        raise RuntimeError(f"required predicate {alias!r} is not registered")
    return definition


_CHILD_OF = _required_predicate("child_of")
_PET_OF = _required_predicate("pet_of")


async def _is_member_of_owner(owner_entity_id: int, subject_entity_id: int) -> bool:
    """Return whether the subject is an active child or pet of the owner.

    ``child_of`` and ``pet_of`` point from the child or the pet to the owner. The partner is
    deliberately not a member here: a fact about the partner is refused (decision 4).
    """
    for definition in (_CHILD_OF, _PET_OF):
        relations = await get_active_entity_relations(
            definition=definition,
            source_entity_id=subject_entity_id,
            target_entity_id=owner_entity_id,
        )
        if relations:
            return True
    return False


def _refusal(
    reason: WriteRefusal, definition: PredicateDefinition, channel: WriteChannel
) -> WriteRefusedError:
    """Log a refusal (reason, predicate id and channel only) and build the error to raise."""
    logger.info(
        "Canonical write refused: %s",
        reason.value,
        extra={
            "event": _REFUSED_EVENT,
            "reason": reason.value,
            "predicate": definition.canonical_id,
            "channel": channel.value,
        },
    )
    return WriteRefusedError(reason.value)


async def _classify_literal(
    owner_entity_id: int,
    subject_entity_id: int,
    definition: PredicateDefinition,
    channel: WriteChannel,
) -> tuple[str, str]:
    """Return the ``(visibility, sensitivity)`` a literal about this subject is stored with.

    Raises:
        WriteRefusedError: With ``not_household_member`` for the partner or anyone else outside
            the owner, the owner's children and the owner's pets.
    """
    if subject_entity_id == owner_entity_id:
        private = definition.canonical_id in _OWNER_PRIVATE_LITERALS
        return _PERSONAL, _PRIVATE if private else definition.default_sensitivity
    if await _is_member_of_owner(owner_entity_id, subject_entity_id):
        return _HOUSEHOLD, definition.default_sensitivity
    raise _refusal(WriteRefusal.NOT_HOUSEHOLD_MEMBER, definition, channel)


def _literal_definition(predicate: str) -> PredicateDefinition:
    """Resolve a closed literal predicate or reject the alias."""
    definition = resolve_predicate(predicate)
    if definition is None or definition.kind is not PredicateKind.LITERAL:
        raise ValueError("write_literal needs a registered literal predicate")
    return definition


async def write_literal(
    *,
    owner_entity_id: int,
    subject_entity_id: int,
    predicate: str,
    value: str,
    channel: WriteChannel,
    confirmed_at: str,
    confidence: float = 0.9,
    asserted_at: str | None = None,
    manage_transaction: bool = True,
) -> LiteralFactV4:
    """Store one literal fact about the owner, a child or a pet, whatever the channel.

    The caller names the subject, the predicate and the value; the writer assigns the
    classification (there is no visibility or sensitivity parameter, and nobody but the subject
    can write into the subject's ``personal`` memory), records the owner as asserter and
    confirmer, and records the channel. An exact repeat of an active value returns the row
    already there (it never relies on the unique index's ``IntegrityError``).

    Args:
        owner_entity_id: The household owner, who asserts and confirms.
        subject_entity_id: The entity the fact is about: the owner, a child or a pet of theirs.
        predicate: A registered literal predicate or its alias.
        value: The raw value; normalized by the registry rule.
        channel: The channel the fact arrived through.
        confirmed_at: When the owner confirmed it, as UTC ISO 8601.
        confidence: Confidence in the fact, between 0 and 1.
        asserted_at: Assertion timestamp (the as-of date of a stated age); now when ``None``.
        manage_transaction: ``False`` joins a transaction the caller already owns, so several
            writes commit or roll back together; ``db.transaction()`` is not reentrant.

    Returns:
        The stored fact, or the active one already stored for the same value.

    Raises:
        WriteRefusedError: With ``not_household_member`` for the partner or an outsider.
        SecurityStorageUndecidedError: For a SECURITY value; nothing is stored or logged.
        ValueError: For an unregistered or non-literal predicate, an unlisted channel, an
            invalid value or a confidence out of range.
    """
    definition = _literal_definition(predicate)
    write_channel = WriteChannel(channel)
    if not manage_transaction:
        return await _write_literal(
            owner_entity_id=owner_entity_id,
            subject_entity_id=subject_entity_id,
            definition=definition,
            value=value,
            channel=write_channel,
            confirmed_at=confirmed_at,
            confidence=confidence,
            asserted_at=asserted_at,
        )
    # The duplicate check shares a transaction with the insert that follows it.
    async with db.transaction():
        return await _write_literal(
            owner_entity_id=owner_entity_id,
            subject_entity_id=subject_entity_id,
            definition=definition,
            value=value,
            channel=write_channel,
            confirmed_at=confirmed_at,
            confidence=confidence,
            asserted_at=asserted_at,
        )


async def _write_literal(
    *,
    owner_entity_id: int,
    subject_entity_id: int,
    definition: PredicateDefinition,
    value: str,
    channel: WriteChannel,
    confirmed_at: str,
    confidence: float,
    asserted_at: str | None,
) -> LiteralFactV4:
    """Classify, de-duplicate and store one literal inside the caller's transaction."""
    visibility, sensitivity = await _classify_literal(
        owner_entity_id, subject_entity_id, definition, channel
    )
    normalized = normalize_literal(definition, value)
    if normalized is not None:
        active = await get_active_literal_facts(
            subject_entity_id=subject_entity_id, definition=definition
        )
        present = next((fact for fact in active if fact.value_text == normalized), None)
        if present is not None:
            return present
    fact = await assert_literal_fact(
        subject_entity_id=subject_entity_id,
        definition=definition,
        value=value,
        confidence=confidence,
        asserted_at=asserted_at,
        visibility=visibility,
        sensitivity=sensitivity,
        confirmed_by_entity_id=owner_entity_id,
        confirmed_at=confirmed_at,
        asserted_by_entity_id=owner_entity_id,
        channel=channel.value,
        manage_transaction=False,
    )
    logger.info(
        "Canonical literal written",
        extra={
            "event": _WRITE_EVENT,
            "kind": "literal",
            "predicate": definition.canonical_id,
            "channel": channel.value,
            "fact_id": fact.id,
        },
    )
    return fact
