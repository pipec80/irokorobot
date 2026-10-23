"""The canonical memory writer: one place that stores a household fact, whatever the channel.

The spoken confirmation (CM-3a, through ``memory_writer.promote``) and the initial import of
Step 0 are two callers of the same functions (ADR 0022 decision 2; Plan 0050 rule 1): they
produce the same stored fact with the same classification, and the row records who asserted it
and through which channel. **The speaker never assigns the classification**: it is looked up
here, from the predicate and the subject, in one table (ADR 0022 decision 2, Plan 0065 D-2):

* the **owner's** own facts are ``personal`` with the registry's sensitivity, except the owner's
  ``birth_date``, which is ``personal``/``private``;
* a fact about an **active child or pet of the owner** is ``household`` with the registry's
  sensitivity (the stored label equals the registry default, which is what the household
  reader requires to serve it); a predicate whose registry default is ``personal`` is never
  widened to ``household``, so it is only about the owner;
* a fact about the **partner**, an **adult child**, a **relative**, or anyone outside that
  closed set, is refused with the closed reason ``not_household_member`` (other adults: name and
  relationship only, ADR 0022 decision 4, ADR 0024 decisions 9 and 10).

"Child" means a child the owner is guardian of; the ``guardianship`` marker in the child's
attributes says whether they are still a minor, and a child marked ``adult`` gets the partner's
rule on every channel (one with no marker is a minor: fail-open for the local setup). It guards
the obvious misuse: nobody who is already the partner, a relative or an adult can be declared
a child to unlock their facts (``role_conflict`` for a relative), while an exact repeat of a
relation that is already active is accepted so a load run twice changes nothing.

The asserter and the confirmer are the owner (ADR 0022 decision 0). A value that is never stored
(the access code) or a mislabeled security reference is refused first, before anything is
classified, read or logged, with the repository's closed error; no value ever reaches a log or
an exception message. An exact repeat of an active value is
idempotent only for the **same text and the same classification**: a stored row labelled
otherwise (the local setup and the legacy migration store the registry defaults) is refused as
``classification_conflict`` instead of being reported as written. Equal text is compared exactly;
folding case and articles, as ``promote`` does, is a Step 0 decision.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, nullcontext
import logging
from typing import TYPE_CHECKING

from server import db
from server.cognition.identity import HouseholdRole
from server.memory.care_contacts import has_active_contact
from server.memory.declarative import is_adult_dependent
from server.memory.household_authorization import get_active_role
from server.memory.predicate_registry import (
    PredicateCardinality,
    PredicateDefinition,
    PredicateKind,
    normalize_literal,
    resolve_predicate,
)
from server.memory.relational_v4 import (
    EntityRelationV4,
    LiteralFactV4,
    assert_entity_relation,
    assert_literal_fact,
    get_active_entity_relations,
    get_active_literal_facts,
    refuse_unstorable_value,
)
from server.memory.write_types import ConflictPolicy, WriteChannel, WriteRefusal, refusal_error

if TYPE_CHECKING:
    from server.exceptions import WriteRefusedError

__all__ = ["WriteChannel", "WriteRefusal", "write_literal", "write_relation"]

logger = logging.getLogger(__name__)

_WRITE_EVENT = "memory.canonical_write"
_PERSONAL = "personal"
_HOUSEHOLD = "household"
_PRIVATE = "private"
# The owner's own facts that are private rather than merely personal (ADR 0022, Plan 0065 D-2).
_OWNER_PRIVATE_LITERALS = frozenset({"birth_date"})
# Who already holds an adult role cannot be declared somebody's child or pet.
_ADULT_ROLES = frozenset({HouseholdRole.OWNER, HouseholdRole.ADULT})


def _required_predicate(alias: str) -> PredicateDefinition:
    """Resolve a registry predicate this closed module depends on."""
    definition = resolve_predicate(alias)
    if definition is None:
        raise RuntimeError(f"required predicate {alias!r} is not registered")
    return definition


_CHILD_OF = _required_predicate("child_of")
_PET_OF = _required_predicate("pet_of")
_PARTNER_OF = _required_predicate("partner_of")
_MEMBERSHIP_PREDICATES = frozenset({"child_of", "partner_of", "pet_of"})
# The owner's relatives (ADR 0024 decision 10): the partner's rule, name and relationship only.
_RELATIVE_PREDICATES = frozenset({"has_parent", "has_grandparent", "has_grandchild", "has_sibling"})
_RELATIVE_DEFINITIONS = tuple(
    _required_predicate(predicate) for predicate in sorted(_RELATIVE_PREDICATES)
)


def _refusal(
    reason: WriteRefusal, definition: PredicateDefinition, channel: WriteChannel
) -> WriteRefusedError:
    """Log a refusal (reason, predicate id and channel only) and build the error to raise."""
    return refusal_error(reason, what=definition.canonical_id, channel=channel)


async def _has_membership_row(owner_entity_id: int, subject_entity_id: int) -> bool:
    """Return whether the subject has an active ``child_of`` or ``pet_of`` row to the owner.

    ``child_of`` and ``pet_of`` point from the child or the pet to the owner, and only an
    active row counts: a membership that ended is history, not a membership. The partner is
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


async def _is_member_of_owner(owner_entity_id: int, subject_entity_id: int) -> bool:
    """Return whether facts may be stored about the subject: a member who is not an adult child.

    An adult child is still the owner's child (the row exists) but gets the partner's rule, name
    and relationship only (ADR 0024 decision 9).
    """
    return await _has_membership_row(owner_entity_id, subject_entity_id) and not (
        await is_adult_dependent(subject_entity_id)
    )


async def _is_partner_of_owner(owner_entity_id: int, entity_id: int) -> bool:
    """Return whether the entity is the owner's active partner, on either end of the row."""
    for source, target in ((entity_id, owner_entity_id), (owner_entity_id, entity_id)):
        relations = await get_active_entity_relations(
            definition=_PARTNER_OF, source_entity_id=source, target_entity_id=target
        )
        if relations:
            return True
    return False


async def _classify_subject(
    owner_entity_id: int,
    subject_entity_id: int,
    definition: PredicateDefinition,
    channel: WriteChannel,
) -> tuple[str, str]:
    """Return the ``(visibility, sensitivity)`` a fact about this subject is stored with.

    Raises:
        WriteRefusedError: With ``not_household_member`` for the partner or anyone else outside
            the owner, the owner's children and the owner's pets; with ``owner_only_predicate``
            for a predicate whose registry default is ``personal`` about anyone but the owner.
    """
    if subject_entity_id == owner_entity_id:
        private = definition.canonical_id in _OWNER_PRIVATE_LITERALS
        return _PERSONAL, _PRIVATE if private else definition.default_sensitivity
    if not await _is_member_of_owner(owner_entity_id, subject_entity_id):
        raise _refusal(WriteRefusal.NOT_HOUSEHOLD_MEMBER, definition, channel)
    if definition.default_visibility == _PERSONAL:
        # Storing it as `household` would widen what the registry says is personal, and storing
        # it as `personal` would put the owner's word into somebody else's personal memory.
        raise _refusal(WriteRefusal.OWNER_ONLY_PREDICATE, definition, channel)
    return _HOUSEHOLD, definition.default_sensitivity


async def _holds_relative_role(owner_entity_id: int, entity_id: int) -> bool:
    """Return whether the entity is a relative or a contact (not merely a person to keep out).

    Either role would be unlocked by relabeling the person a child, a pet or the partner.
    """
    if await has_active_contact(entity_id):
        return True
    for definition in _RELATIVE_DEFINITIONS:
        ends = [(owner_entity_id, entity_id)]
        if definition.symmetric:
            ends.append((entity_id, owner_entity_id))
        for source, target in ends:
            if await get_active_entity_relations(
                definition=definition, source_entity_id=source, target_entity_id=target
            ):
                return True
    return False


async def _is_active_repeat(
    definition: PredicateDefinition, source_entity_id: int, target_entity_id: int
) -> bool:
    """Return whether this exact relation is already active (on either end if it is symmetric)."""
    ends = [(source_entity_id, target_entity_id)]
    if definition.symmetric:
        ends.append((target_entity_id, source_entity_id))
    for source, target in ends:
        if await get_active_entity_relations(
            definition=definition, source_entity_id=source, target_entity_id=target
        ):
            return True
    return False


async def _membership_refusal(
    owner_entity_id: int,
    source_entity_id: int,
    target_entity_id: int,
    definition: PredicateDefinition,
) -> WriteRefusal | None:
    """Return why a membership relation is refused, or ``None`` when it may be stored.

    The owner must be at the owning end. An exact repeat of an active row is accepted whatever
    the source has become since (a load run twice changes nothing). Otherwise a relative cannot
    be relabeled a member (``role_conflict``), a partner cannot be declared a child or a pet, a
    child or a pet cannot be declared the partner, and an entity that already holds an adult
    household role cannot be declared a child or a pet: any of these would unlock facts about an
    adult that decision 4 keeps out (``not_household_member``).
    """
    owner_ends = {target_entity_id}
    if definition.symmetric:
        owner_ends.add(source_entity_id)
    if owner_entity_id not in owner_ends or source_entity_id == target_entity_id:
        return WriteRefusal.NOT_HOUSEHOLD_MEMBER
    if await _is_active_repeat(definition, source_entity_id, target_entity_id):
        return None
    if definition.symmetric:
        other = target_entity_id if source_entity_id == owner_entity_id else source_entity_id
    else:
        other = source_entity_id
    if await _holds_relative_role(owner_entity_id, other):
        return WriteRefusal.ROLE_CONFLICT
    if definition.symmetric:
        has_two_roles = await _has_membership_row(owner_entity_id, other)
    else:
        has_two_roles = await _is_partner_of_owner(owner_entity_id, other) or (
            await get_active_role(other) in _ADULT_ROLES
        )
    return WriteRefusal.NOT_HOUSEHOLD_MEMBER if has_two_roles else None


async def _classify_relative(
    owner_entity_id: int,
    source_entity_id: int,
    target_entity_id: int,
    definition: PredicateDefinition,
    channel: WriteChannel,
) -> tuple[str, str]:
    """Return the ``(visibility, sensitivity)`` of a relation to a relative or a person to keep out.

    The owner must be the source (a symmetric ``has_sibling`` read from the relative's end is
    ``not_household_member``). A relative cannot be a member or the partner already
    (``role_conflict``); ``withhold_from`` may point at anyone.
    """
    classification = await _classify_subject(owner_entity_id, source_entity_id, definition, channel)
    if definition.canonical_id in _RELATIVE_PREDICATES and (
        await _has_membership_row(owner_entity_id, target_entity_id)
        or await _is_partner_of_owner(owner_entity_id, target_entity_id)
    ):
        raise _refusal(WriteRefusal.ROLE_CONFLICT, definition, channel)
    return classification


async def _classify_relation(
    owner_entity_id: int,
    source_entity_id: int,
    target_entity_id: int,
    definition: PredicateDefinition,
    channel: WriteChannel,
) -> tuple[str, str]:
    """Return the ``(visibility, sensitivity)`` a relation is stored with.

    A membership relation (``child_of``, ``partner_of``, ``pet_of``) is the act that says who
    belongs to the owner's household, so it only needs the owner at its owning end: the child
    or the pet points to the owner, and the partner may be on either end (the relation is
    symmetric). It is ``household`` with the registry's sensitivity. A relation to a relative or
    to a person to keep out is ``personal``, from the owner. Any other relation (``lives_in``,
    ``works_at``) is classified by its source like a literal about that subject.

    Raises:
        WriteRefusedError: With ``not_household_member`` when the owner is not at the owning end
            of a membership relation, when it would give one entity two roles, or when the
            source of another relation is the partner or an outsider; with ``role_conflict``
            when a relative would become a member or a member a relative.
    """
    if definition.canonical_id in _MEMBERSHIP_PREDICATES:
        refusal = await _membership_refusal(
            owner_entity_id, source_entity_id, target_entity_id, definition
        )
        if refusal is not None:
            raise _refusal(refusal, definition, channel)
        return _HOUSEHOLD, definition.default_sensitivity
    if definition.canonical_id in _RELATIVE_PREDICATES | {"withhold_from"}:
        return await _classify_relative(
            owner_entity_id, source_entity_id, target_entity_id, definition, channel
        )
    return await _classify_subject(owner_entity_id, source_entity_id, definition, channel)


def _refuse_a_different_single_value(
    definition: PredicateDefinition, channel: WriteChannel
) -> None:
    """Refuse a value that differs from the active one of a single-value predicate.

    Raises:
        WriteRefusedError: With ``value_conflict`` for a single-value predicate; multi-value
            predicates never conflict and are not asked.
    """
    if definition.cardinality is PredicateCardinality.SINGLE_CURRENT:
        raise _refusal(WriteRefusal.VALUE_CONFLICT, definition, channel)


async def _refuse_a_conflicting_relation(
    owner_entity_id: int,
    source_entity_id: int,
    target_entity_id: int,
    definition: PredicateDefinition,
    channel: WriteChannel,
) -> None:
    """Refuse a second partner (from either end) or a second place of a temporal relation.

    The same partner or place again is not a conflict (the repository returns the row there).

    Raises:
        WriteRefusedError: With ``value_conflict`` when an active row points somewhere else.
    """
    if definition.canonical_id == "partner_of":
        other = target_entity_id if source_entity_id == owner_entity_id else source_entity_id
        rows = [
            *await get_active_entity_relations(
                definition=definition, source_entity_id=owner_entity_id
            ),
            *await get_active_entity_relations(
                definition=definition, target_entity_id=owner_entity_id
            ),
        ]
        known = {
            row.target_entity_id
            if row.source_entity_id == owner_entity_id
            else row.source_entity_id
            for row in rows
        }
    elif definition.cardinality is PredicateCardinality.TEMPORAL:
        rows = await get_active_entity_relations(
            definition=definition, source_entity_id=source_entity_id
        )
        other = target_entity_id
        known = {row.target_entity_id for row in rows}
    else:
        return
    if known - {other}:
        raise _refusal(WriteRefusal.VALUE_CONFLICT, definition, channel)


def _require_same_classification(
    stored_visibility: str,
    stored_sensitivity: str,
    assigned: tuple[str, str],
    definition: PredicateDefinition,
    channel: WriteChannel,
) -> None:
    """Refuse to report a stored row as written when it is labelled otherwise.

    Raises:
        WriteRefusedError: With ``classification_conflict`` when the row found was stored with
            another visibility or sensitivity than the writer would assign.
    """
    if (stored_visibility, stored_sensitivity) != assigned:
        raise _refusal(WriteRefusal.CLASSIFICATION_CONFLICT, definition, channel)


def _validate_confidence(confidence: float) -> None:
    """Reject a confidence outside 0 to 1 before anything is looked up or returned."""
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")


def _transaction(manage_transaction: bool) -> AbstractAsyncContextManager[object]:
    """Own a transaction, or join the one the caller already owns (``db.transaction`` is not reentrant)."""
    return db.transaction() if manage_transaction else nullcontext()


def _announce(
    kind: str,
    definition: PredicateDefinition,
    channel: WriteChannel,
    row_id: int,
    *,
    committed: bool,
) -> None:
    """Log one stored row by id and closed fields, only once it is certain to persist.

    A write joined to the caller's transaction may still be rolled back by the caller, so it is
    only *staged* (debug); a write that owned its transaction is *written* (info) after the commit.
    """
    logger.log(
        logging.INFO if committed else logging.DEBUG,
        "Canonical %s %s",
        kind,
        "written" if committed else "staged",
        extra={
            "event": _WRITE_EVENT,
            "kind": kind,
            "predicate": definition.canonical_id,
            "channel": channel.value,
            "row_id": row_id,
        },
    )


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
    on_conflict: ConflictPolicy = ConflictPolicy.SUPERSEDE,
    confirmed_by_owner: bool = True,
    manage_transaction: bool = True,
) -> LiteralFactV4:
    """Store one literal fact about the owner, a child or a pet, whatever the channel.

    The caller names the subject, the predicate and the value; the writer assigns the
    classification (there is no visibility or sensitivity parameter, and nobody but the subject
    can write into the subject's ``personal`` memory), records the owner as asserter and
    confirmer, and records the channel. An exact repeat of an active value with the same
    classification returns the row already there (it never relies on the unique index's
    ``IntegrityError``); a row stored with another classification is a conflict, not a success.

    Args:
        owner_entity_id: The household owner, who asserts and confirms. The caller is trusted to
            have established that: the writer does not authenticate (the policy does).
        subject_entity_id: The entity the fact is about: the owner, a child or a pet of theirs.
        predicate: A registered literal predicate or its alias.
        value: The raw value; normalized by the registry rule.
        channel: The channel the fact arrived through.
        confirmed_at: When the owner confirmed it, as UTC ISO 8601.
        confidence: Confidence in the fact, between 0 and 1.
        asserted_at: Assertion timestamp (the as-of date of a stated age); now when ``None``.
        on_conflict: ``SUPERSEDE`` (the default) replaces a different single value; ``REFUSE``
            raises ``value_conflict`` instead and changes nothing (a load made while the robot
            is being commissioned, ADR 0024 decision 8).
        confirmed_by_owner: ``False`` stores no confirmer (``confirmed_by_entity_id`` is ``NULL``,
            ``confirmed_at`` is kept) because the owner did not confirm it themselves
            (ADR 0024 decision 6); the asserter is still the owner.
        manage_transaction: ``False`` joins a transaction the caller already owns, so several
            writes commit or roll back together; ``db.transaction()`` is not reentrant, so a
            caller already inside one **must** pass ``False``.

    Returns:
        The stored fact, or the active one already stored for the same value.

    Raises:
        UnstorableValueError: For an unstorable predicate; raised first, nothing is read,
            stored or logged.
        WriteRefusedError: With ``not_household_member`` for the partner or an outsider,
            ``owner_only_predicate`` for a personal-default predicate about someone else,
            ``classification_conflict`` for a stored row labelled otherwise, or
            ``value_conflict`` under ``REFUSE`` for a different single value.
        ValueError: For an unregistered or non-literal predicate, an unlisted channel, an
            invalid value or a confidence out of range.
    """
    definition = _literal_definition(predicate)
    refuse_unstorable_value(definition)
    write_channel = WriteChannel(channel)
    _validate_confidence(confidence)
    async with _transaction(manage_transaction):
        fact, created = await _write_literal(
            owner_entity_id=owner_entity_id,
            subject_entity_id=subject_entity_id,
            definition=definition,
            value=value,
            channel=write_channel,
            confirmed_at=confirmed_at,
            confidence=confidence,
            asserted_at=asserted_at,
            on_conflict=on_conflict,
            confirmed_by_owner=confirmed_by_owner,
        )
    if created:
        _announce("literal", definition, write_channel, fact.id, committed=manage_transaction)
    return fact


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
    on_conflict: ConflictPolicy,
    confirmed_by_owner: bool,
) -> tuple[LiteralFactV4, bool]:
    """Classify, de-duplicate and store one literal inside the caller's transaction."""
    visibility, sensitivity = await _classify_subject(
        owner_entity_id, subject_entity_id, definition, channel
    )
    normalized = normalize_literal(definition, value)
    if normalized is not None:
        active = await get_active_literal_facts(
            subject_entity_id=subject_entity_id, definition=definition
        )
        present = next((fact for fact in active if fact.value_text == normalized), None)
        if present is not None:
            _require_same_classification(
                present.visibility,
                present.sensitivity,
                (visibility, sensitivity),
                definition,
                channel,
            )
            return present, False
        if on_conflict is ConflictPolicy.REFUSE and active:
            _refuse_a_different_single_value(definition, channel)
    fact = await assert_literal_fact(
        subject_entity_id=subject_entity_id,
        definition=definition,
        value=value,
        confidence=confidence,
        asserted_at=asserted_at,
        visibility=visibility,
        sensitivity=sensitivity,
        confirmed_by_entity_id=owner_entity_id if confirmed_by_owner else None,
        confirmed_at=confirmed_at,
        asserted_by_entity_id=owner_entity_id,
        channel=channel.value,
        manage_transaction=False,
    )
    return fact, True


def _relation_definition(predicate: str) -> PredicateDefinition:
    """Resolve a closed relation predicate or reject the alias."""
    definition = resolve_predicate(predicate)
    if definition is None or definition.kind is not PredicateKind.RELATION:
        raise ValueError("write_relation needs a registered relation predicate")
    return definition


async def write_relation(
    *,
    owner_entity_id: int,
    source_entity_id: int,
    predicate: str,
    target_entity_id: int,
    channel: WriteChannel,
    confirmed_at: str,
    confidence: float = 0.9,
    asserted_at: str | None = None,
    valid_from: str | None = None,
    valid_to: str | None = None,
    on_conflict: ConflictPolicy = ConflictPolicy.SUPERSEDE,
    confirmed_by_owner: bool = True,
    manage_transaction: bool = True,
) -> EntityRelationV4:
    """Store one relation of the owner's household, whatever the channel.

    Membership relations (``child_of``, ``partner_of``, ``pet_of``) say who belongs to the
    household and are ``household`` data; ``lives_in`` and ``works_at`` follow their source like
    a literal about that subject. The classification is the writer's, as for ``write_literal``;
    the owner is the asserter and the confirmer. Validity follows ADR 0022 decision 6: a spoken
    ``valid_from`` closes the previous relation of a temporal predicate at that date (never
    before the previous one began), and an explicit ``valid_to`` stores history without touching
    the current row. An exact repeat of an active triple returns the row already stored, **with
    its first dates**, and a stored row labelled otherwise is a conflict. A ``valid_from`` in the
    future supersedes the current relation at once: planned moves wait for CM-5. The targets (a
    third party made by ``create_third_party``, a place) are not classified: only the source's
    membership counts.

    Args:
        owner_entity_id: The household owner, who asserts and confirms (trusted, see
            ``write_literal``).
        source_entity_id: The entity the relation starts from (the child, the pet, the owner).
        predicate: A registered relation predicate or its alias.
        target_entity_id: The entity it points to.
        channel: The channel the relation arrived through.
        confirmed_at: When the owner confirmed it, as UTC ISO 8601.
        confidence: Confidence in the relation, between 0 and 1.
        asserted_at: Assertion timestamp; now when ``None``.
        valid_from: When it began, as ``YYYY-MM-DD`` or ``YYYY-MM``.
        valid_to: When it ended; makes the row history.
        on_conflict: ``SUPERSEDE`` (the default) replaces a different single value; ``REFUSE``
            raises ``value_conflict`` instead and changes nothing (a load made while the robot
            is being commissioned, ADR 0024 decision 8).
        confirmed_by_owner: ``False`` stores no confirmer (``confirmed_by_entity_id`` is ``NULL``,
            ``confirmed_at`` is kept) because the owner did not confirm it themselves
            (ADR 0024 decision 6); the asserter is still the owner.
        manage_transaction: ``False`` joins a transaction the caller already owns, so several
            writes commit or roll back together; ``db.transaction()`` is not reentrant, so a
            caller already inside one **must** pass ``False``.

    Returns:
        The stored relation, or the active one already stored for the same triple.

    Raises:
        UnstorableValueError: For an unstorable relation; raised first.
        WriteRefusedError: With ``not_household_member`` when the relation is outside the
            owner's household (the partner's own facts, an outsider, a second role),
            ``owner_only_predicate`` or ``classification_conflict`` as for ``write_literal``;
            ``value_conflict`` under ``REFUSE`` for a second partner or a second home.
        ValueError: For an unregistered or non-relation predicate, an unlisted channel, an
            invalid endpoint, date or confidence.
    """
    definition = _relation_definition(predicate)
    refuse_unstorable_value(definition)
    write_channel = WriteChannel(channel)
    _validate_confidence(confidence)
    async with _transaction(manage_transaction):
        relation = await _write_relation(
            owner_entity_id=owner_entity_id,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            definition=definition,
            channel=write_channel,
            confirmed_at=confirmed_at,
            confidence=confidence,
            asserted_at=asserted_at,
            valid_from=valid_from,
            valid_to=valid_to,
            on_conflict=on_conflict,
            confirmed_by_owner=confirmed_by_owner,
        )
    _announce("relation", definition, write_channel, relation.id, committed=manage_transaction)
    return relation


async def _write_relation(
    *,
    owner_entity_id: int,
    source_entity_id: int,
    target_entity_id: int,
    definition: PredicateDefinition,
    channel: WriteChannel,
    confirmed_at: str,
    confidence: float,
    asserted_at: str | None,
    valid_from: str | None,
    valid_to: str | None,
    on_conflict: ConflictPolicy,
    confirmed_by_owner: bool,
) -> EntityRelationV4:
    """Classify and store one relation inside the caller's transaction."""
    visibility, sensitivity = await _classify_relation(
        owner_entity_id, source_entity_id, target_entity_id, definition, channel
    )
    if on_conflict is ConflictPolicy.REFUSE and valid_to is None:
        await _refuse_a_conflicting_relation(
            owner_entity_id, source_entity_id, target_entity_id, definition, channel
        )
    relation = await assert_entity_relation(
        source_entity_id=source_entity_id,
        target_entity_id=target_entity_id,
        definition=definition,
        confidence=confidence,
        asserted_at=asserted_at,
        visibility=visibility,
        sensitivity=sensitivity,
        confirmed_by_entity_id=owner_entity_id if confirmed_by_owner else None,
        confirmed_at=confirmed_at,
        valid_from=valid_from,
        valid_to=valid_to,
        asserted_by_entity_id=owner_entity_id,
        channel=channel.value,
        manage_transaction=False,
    )
    # The repository returns an existing active triple untouched: it must carry the label the
    # writer would have given it, or the caller would be told a wrong row was written.
    _require_same_classification(
        relation.visibility, relation.sensitivity, (visibility, sensitivity), definition, channel
    )
    return relation
