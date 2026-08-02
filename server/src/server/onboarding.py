"""Slot-driven onboarding checklist — structure lives in code, not prompts.

A 3B model drifts off a prompted interview script after a few turns
(observed live 2026-07-13: the owner talked about his children before
introducing himself and the robot anchored a child as its owner). The
checklist derives WHAT is missing from the DB on every turn; the
character's prompt only decides HOW to ask for it. It survives restarts
and failed consolidations because state lives in facts, not conversation.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

from server.memory.declarative import load_entity_with_facts
from server.memory.meta import get_flag
from server.memory.relations import find_facts_by_predicate

logger = logging.getLogger(__name__)

# Relations point AT the owner (child hijo_de owner), so coverage is
# checked on the fact's object side — unless declined ("hijo_de: ninguno"
# lives on the owner entity and is caught by the direct-predicate check).
_RELATION_SLOTS = frozenset({"pareja_de", "hijo_de", "mascota_de"})


@dataclass(frozen=True)
class OnboardingSlot:
    """One datum the robot must learn during the first interview.

    Attributes:
        key: Canonical fact predicate that covers the slot.
        question_hint: What to ask, in Spanish, injected into the prompt.
        optional: Declinable slot — "no tengo hijos" covers it with the
            fact object "ninguno".
    """

    key: str
    question_hint: str
    optional: bool = False


_CHECKLIST: tuple[OnboardingSlot, ...] = (
    OnboardingSlot(key="nombre", question_hint="su nombre"),
    OnboardingSlot(key="fecha_nacimiento", question_hint="cuándo nació"),
    OnboardingSlot(key="vive_en", question_hint="dónde vive"),
    OnboardingSlot(key="pareja_de", question_hint="si tiene pareja", optional=True),
    OnboardingSlot(key="hijo_de", question_hint="si tiene hijos y sus nombres", optional=True),
    OnboardingSlot(
        key="mascota_de", question_hint="si tiene mascotas y sus nombres", optional=True
    ),
    OnboardingSlot(key="trabaja_en", question_hint="en qué trabaja"),
    OnboardingSlot(key="le_gusta", question_hint="qué le gusta hacer"),
)


async def _slot_covered(slot: OnboardingSlot, owner_name: str, owner_predicates: set[str]) -> bool:
    """Return ``True`` when an active fact already answers *slot*.

    Args:
        slot: The checklist slot to test.
        owner_name: The anchored owner name.
        owner_predicates: Predicates of the owner entity's active facts.

    Returns:
        ``True`` if a direct fact on the owner covers the slot (including
        declined optionals) or, for relation slots, if any entity points
        at the owner with that predicate.
    """
    if slot.key in owner_predicates:
        return True
    if slot.key in _RELATION_SLOTS:
        return bool(await find_facts_by_predicate(slot.key, object_value=owner_name))
    return False


async def next_missing_slot() -> OnboardingSlot | None:
    """Return the next unanswered checklist slot, or ``None`` when complete.

    Mandatory slots first (in checklist order), then optional ones. The
    answer to every slot is derived from the DB — never from conversation
    state — so the interview survives restarts and failed consolidations.

    Returns:
        The first missing mandatory slot; if all mandatory are covered,
        the first unanswered optional slot; ``None`` when everything is
        covered.

    Raises:
        BrainMemoryError: If the DB is unavailable.
    """
    owner_name = await get_flag("owner_name")
    if owner_name is None:
        return _CHECKLIST[0]  # every other slot anchors on the owner's name

    owner = await load_entity_with_facts(owner_name)
    owner_predicates = {f.predicate for f in owner.facts} if owner else set()

    first_optional: OnboardingSlot | None = None
    for slot in _CHECKLIST[1:]:
        if await _slot_covered(slot, owner_name, owner_predicates):
            continue
        if not slot.optional:
            return slot
        if first_optional is None:
            first_optional = slot
    return first_optional
