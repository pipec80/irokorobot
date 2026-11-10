"""Pure types that tell the sides of a family apart (Plan 0080 D-4).

This module imports no storage, HTTP or adapter module, so the cognitive core can name these
types without pulling the memory layer: the tools that fill them live in ``household_tools``.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from server.cognition.models import KnowledgeStatus

__all__ = ["Side", "SideGroup", "SidedNames"]


class Side(StrEnum):
    """Which side of the family a relative is on: a mother or a daughter, a father or a son."""

    FEMALE = "female"
    MALE = "male"


class SideGroup(StrEnum):
    """The relatives a side is told apart in (Plan 0080 D-4)."""

    PARENTS = "parents"
    CHILDREN = "children"


@dataclass(frozen=True)
class SidedNames:
    """The names of one group of relatives, grouped by the side that is recorded for each.

    Attributes:
        status: ``KNOWN`` when at least one was read, ``UNAUTHORIZED`` when any policy step
            refused, ``UNKNOWN`` when there is no authorized record of any side.
        female: The mothers or daughters, sorted. Hidden from ``repr``: it carries names.
        male: The fathers or sons, sorted. Hidden from ``repr``.
        unlabelled: Members whose side is not recorded, sorted. Hidden from ``repr``.
    """

    status: KnowledgeStatus
    female: tuple[str, ...] = field(default=(), repr=False)
    male: tuple[str, ...] = field(default=(), repr=False)
    unlabelled: tuple[str, ...] = field(default=(), repr=False)
