"""Exact entity labels for authorized P0.5-B2 relationship results.

It also lists the household's known names and aliases for the candidate classifier (ADR 0021),
so a person's or a pet's name is never kept as a taste.
"""

import json
import logging

from pydantic import BaseModel, ConfigDict

from server.db import get_conn
from server.exceptions import BrainMemoryError

logger = logging.getLogger(__name__)

__all__ = ["EntityLabel", "get_person_label", "list_known_names"]


class EntityLabel(BaseModel):
    """Immutable display-safe label for one persisted person entity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_id: int
    display_name: str


async def get_person_label(*, entity_id: int) -> EntityLabel | None:
    """Return one exact person label without reading legacy facts.

    Args:
        entity_id: Integer ID of the entity selected by an authorized v4 relation.

    Returns:
        The exact person label, or ``None`` when the ID is absent or non-person.
    """
    cursor = await get_conn().execute(
        "SELECT id, name FROM entities WHERE id = ? AND type = ?",
        (entity_id, "person"),
    )
    row = await cursor.fetchone()
    await cursor.close()
    if row is None:
        return None
    return EntityLabel(entity_id=int(row[0]), display_name=str(row[1]))


async def list_known_names() -> frozenset[str]:
    """Return every name and alias of the people and pets the household knows.

    Used by the candidate classifier to refuse an object that is somebody's name (ADR 0021
    decision 5); the folding is the classifier's, so the names are returned as stored.

    Returns:
        The names and aliases of every ``person`` entity and of every ``other`` entity (pets).

    Raises:
        BrainMemoryError: If the database is not open, or if an entity's stored aliases are not
            a JSON list of strings. The list fails closed: a name silently left out would let
            a pet's alias be accepted as a taste.
    """
    cursor = await get_conn().execute(
        "SELECT id, name, aliases FROM entities WHERE type IN ('person', 'other')"
    )
    rows = list(await cursor.fetchall())
    await cursor.close()
    names: set[str] = set()
    for entity_id, name, aliases in rows:
        names.add(str(name))
        names.update(_decode_aliases(int(entity_id), aliases))
    return frozenset(names)


def _decode_aliases(entity_id: int, stored: object) -> list[str]:
    """Decode one entity's aliases column, or raise ``BrainMemoryError`` (never log the value)."""
    try:
        decoded = json.loads(str(stored))
    except ValueError:
        decoded = None
    if isinstance(decoded, list) and all(isinstance(alias, str) for alias in decoded):
        return [str(alias) for alias in decoded]
    logger.warning(
        "Entity aliases are malformed: entity=%d",
        entity_id,
        extra={"event": "entity_labels.aliases_malformed", "entity_id": entity_id},
    )
    raise BrainMemoryError("Stored entity aliases are not a list of strings")
