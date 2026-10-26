"""The readiness report of the alta: data present and hardware ready, per capability (Plan 0072).

ADR 0024 decision 14: a capability is ready only when its pool data **and** its hardware are. This
module is pure. For each capability that exists today it derives whether its data is present from the
section statuses (never typed by hand) and combines it with a typed hardware status (``supported``,
``configured``, ``verified``), checked by a person one capability at a time. A capability that is
``planned`` or an ``idea`` in the catalogue is not reported here: it is "not supported" by absence.

The catalogue mirrors the *Capabilities and what they need* table of
``docs/architecture/seed-data-pool.md``; the six entries are its ``exists`` rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
from typing import TYPE_CHECKING, Any

from server.memory.commissioning import Section, SectionStatus

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "CATALOGUE",
    "Capability",
    "CapabilityReadiness",
    "CatalogueEntry",
    "HardwareStatus",
    "Verdict",
    "evaluate_readiness",
    "readiness_from_json",
    "readiness_to_json",
]


class Capability(StrEnum):
    """A capability that exists today (the ``exists`` rows of the catalogue)."""

    SPEAK_REPLY = "speak_reply"
    UNDERSTAND_SPEECH = "understand_speech"
    RECOGNIZE_FACE = "recognize_face"
    RECOGNIZE_VOICE = "recognize_voice"
    REMEMBER_TASTE = "remember_taste"
    DESCRIBE_SCENE = "describe_scene"


class Verdict(StrEnum):
    """Whether a capability is ready, and if not, what blocks it."""

    READY = "ready"
    BLOCKED_BY_DATA = "blocked_by_data"
    BLOCKED_BY_HARDWARE = "blocked_by_hardware"
    BLOCKED_BY_BOTH = "blocked_by_both"


@dataclass(frozen=True)
class CatalogueEntry:
    """One capability and the pool sections its data needs (empty when it needs none)."""

    capability: Capability
    data_sections: frozenset[Section]


@dataclass(frozen=True)
class HardwareStatus:
    """The typed hardware and software status of a capability, checked by a person (decision 14)."""

    supported: bool
    configured: bool
    verified: bool


@dataclass(frozen=True)
class CapabilityReadiness:
    """One capability's derived data-readiness, its typed hardware status and the verdict."""

    capability: Capability
    data_present: bool
    hardware: HardwareStatus
    verdict: Verdict


# The six capabilities that exist today, with the pool sections each needs (decision 14).
CATALOGUE: tuple[CatalogueEntry, ...] = (
    CatalogueEntry(Capability.SPEAK_REPLY, frozenset()),
    CatalogueEntry(Capability.UNDERSTAND_SPEECH, frozenset()),
    CatalogueEntry(Capability.RECOGNIZE_FACE, frozenset()),
    CatalogueEntry(Capability.RECOGNIZE_VOICE, frozenset()),
    CatalogueEntry(Capability.REMEMBER_TASTE, frozenset()),
    CatalogueEntry(Capability.DESCRIBE_SCENE, frozenset({Section.FUNCTION})),
)

_NO_HARDWARE = HardwareStatus(supported=False, configured=False, verified=False)


def _verdict(*, data_present: bool, hardware_ready: bool) -> Verdict:
    """Combine the two readiness dimensions into one verdict."""
    match (data_present, hardware_ready):
        case (True, True):
            return Verdict.READY
        case (False, True):
            return Verdict.BLOCKED_BY_DATA
        case (True, False):
            return Verdict.BLOCKED_BY_HARDWARE
        case _:
            return Verdict.BLOCKED_BY_BOTH


def evaluate_readiness(
    statuses: Mapping[Section, SectionStatus],
    hardware: Mapping[Capability, HardwareStatus],
) -> tuple[CapabilityReadiness, ...]:
    """Derive the readiness of every catalogued capability.

    A capability's data is present when it needs no section, or when every section it needs is
    ``provided``; its hardware is ready only when it is ``supported``, ``configured`` **and**
    ``verified``. Neither a permission nor the form turns anything on.

    Args:
        statuses: The status of each pool section (from the commissioning record).
        hardware: The typed hardware status per capability; a missing one counts as nothing ready.

    Returns:
        One readiness per catalogued capability, in the catalogue's order.
    """
    report: list[CapabilityReadiness] = []
    for entry in CATALOGUE:
        data_present = all(
            statuses.get(section) is SectionStatus.PROVIDED for section in entry.data_sections
        )
        status = hardware.get(entry.capability, _NO_HARDWARE)
        hardware_ready = status.supported and status.configured and status.verified
        report.append(
            CapabilityReadiness(
                capability=entry.capability,
                data_present=data_present,
                hardware=status,
                verdict=_verdict(data_present=data_present, hardware_ready=hardware_ready),
            )
        )
    return tuple(report)


def readiness_to_json(report: tuple[CapabilityReadiness, ...]) -> str:
    """Serialize a readiness report for the acta column; it carries no household value."""
    return json.dumps(
        {
            item.capability.value: {
                "data_present": item.data_present,
                "supported": item.hardware.supported,
                "configured": item.hardware.configured,
                "verified": item.hardware.verified,
                "verdict": item.verdict.value,
            }
            for item in report
        }
    )


def readiness_from_json(readiness_json: str) -> tuple[CapabilityReadiness, ...]:
    """Rebuild a readiness report from the JSON this module itself wrote."""
    data: Any = json.loads(readiness_json)  # Any: a JSON object this module itself wrote
    return tuple(
        CapabilityReadiness(
            capability=Capability(name),
            data_present=bool(value["data_present"]),
            hardware=HardwareStatus(
                supported=bool(value["supported"]),
                configured=bool(value["configured"]),
                verified=bool(value["verified"]),
            ),
            verdict=Verdict(value["verdict"]),
        )
        for name, value in data.items()
    )
