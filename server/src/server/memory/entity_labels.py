"""Exact entity labels for authorized P0.5-B2 relationship results."""

from pydantic import BaseModel, ConfigDict

from server.db import get_conn

__all__ = ["EntityLabel", "get_person_label"]


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
