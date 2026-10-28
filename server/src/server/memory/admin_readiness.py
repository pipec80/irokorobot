"""Recompute the readiness report read-only for the admin (Plan 0073 Task 7, ADR 0025, C-2).

After the alta closes, the acta is frozen: `set_section_status` and every acta writer refuse a
closed record. So `status` never edits the acta; it **recomputes** which pool sections hold active
rows now, keeps the hardware attestation the acta froze, and reports the readiness of each
capability. It calls no commissioning writer, so it never raises `CommissioningClosedError`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from server.memory.care_contacts import list_active_contacts
from server.memory.commissioning import (
    Section,
    SectionStatus,
    get_latest_commissioning,
    read_session_details,
)
from server.memory.commissioning_readiness import (
    HardwareStatus,
    evaluate_readiness,
    readiness_from_json,
)
from server.memory.relational_v4 import list_active_facts, list_active_relations

if TYPE_CHECKING:
    from collections.abc import Mapping

    from server.memory.commissioning_readiness import Capability, CapabilityReadiness

__all__ = ["derive_section_presence", "recompute_readiness"]

# Which active rows make each pool section present now (the reverse of the importer's D-5 map).
_SECTION_LITERALS: dict[Section, frozenset[str]] = {
    Section.CONDITIONS: frozenset({"health_condition"}),
    Section.ALLERGIES: frozenset({"allergic_to"}),
    Section.MEDICATIONS: frozenset({"medication", "takes_anticoagulant", "rescue_medication"}),
    Section.DEVICES: frozenset({"implanted_device"}),
    Section.SECRETS: frozenset({"secret_holder"}),
    Section.DOCUMENTS: frozenset({"document_location"}),
    Section.HOME: frozenset(
        {
            "home_address",
            "dwelling_type",
            "floor",
            "has_lift",
            "home_access_note",
            "lives_alone",
            "preferred_emergency_facility",
        }
    ),
    Section.FUNCTION: frozenset({"mobility", "hearing", "vision"}),
}
_HOUSEHOLD_RELATIONS = frozenset({"child_of", "partner_of", "pet_of"})


async def derive_section_presence(owner_entity_id: int) -> Mapping[Section, bool]:
    """Return, per pool section, whether the owner holds any active row of it now.

    A coarse present/absent derivation (it cannot tell ``none`` from ``declined``); it is for the
    admin's divergence view and for the data side of the recomputed readiness.

    Args:
        owner_entity_id: The owner whose rows are read.

    Returns:
        One boolean per section.
    """
    literal_predicates = {fact.predicate for fact in await list_active_facts(owner_entity_id)}
    relation_predicates = {rel.predicate for rel in await list_active_relations(owner_entity_id)}
    has_contacts = bool(await list_active_contacts(owner_entity_id))
    presence: dict[Section, bool] = {}
    for section in Section:
        if section in _SECTION_LITERALS:
            presence[section] = bool(_SECTION_LITERALS[section] & literal_predicates)
        elif section is Section.CONTACTS:
            presence[section] = has_contacts
        elif section is Section.WITHHOLD:
            presence[section] = "withhold_from" in relation_predicates
        elif section is Section.HOUSEHOLD:
            presence[section] = bool(_HOUSEHOLD_RELATIONS & relation_predicates)
        else:
            presence[section] = False
    return presence


async def _frozen_hardware() -> Mapping[Capability, HardwareStatus]:
    """Read the hardware attestation the acta froze; empty when there is no readiness yet."""
    record = await get_latest_commissioning()
    if record is None:
        return {}
    details = await read_session_details(record.id)
    if details.readiness_json is None:
        return {}
    return {item.capability: item.hardware for item in readiness_from_json(details.readiness_json)}


async def recompute_readiness(owner_entity_id: int) -> tuple[CapabilityReadiness, ...]:
    """Recompute the readiness read-only: data from the active rows, hardware from the frozen acta.

    Args:
        owner_entity_id: The owner whose data side is recomputed.

    Returns:
        One readiness per catalogued capability; it edits nothing and raises no closed-record error.
    """
    presence = await derive_section_presence(owner_entity_id)
    statuses: Mapping[Section, SectionStatus] = {
        section: SectionStatus.PROVIDED if present else SectionStatus.NOT_ASKED
        for section, present in presence.items()
    }
    return evaluate_readiness(statuses, await _frozen_hardware())
