"""The one query behind the owner's sensitive read (Plan 0079 Task 6, Ruling 14).

It writes no SQL: the v4 repository reads the active facts of one subject and one predicate, and
this module keeps the rows stored with exactly the visibility and sensitivity the caller asks for.
The caller is ``sensitive_access``, which has already checked the audience, the consent and the
policy and written the audit row; this module authorizes nothing and logs nothing.
"""

from __future__ import annotations

from typing import Final

from server.memory.predicate_registry import resolve_predicate
from server.memory.relational_v4 import get_active_literal_facts

__all__ = ["read_own_values"]

# The owner's own data is stored ``personal`` by the canonical writer (Plan 0065, D-4).
_OWN_VISIBILITY: Final = "personal"


async def read_own_values(
    owner_entity_id: int, predicate: str, sensitivity: str
) -> tuple[str, ...]:
    """Return the owner's active values of one predicate stored ``personal`` with *sensitivity*.

    A row of the same predicate stored with another visibility or sensitivity is not the owner's
    data of this kind and is left out; a revoked, superseded or expired row never qualifies (the
    repository returns active rows only). Values come back exactly as stored.

    Args:
        owner_entity_id: The owner, the speaker the audience check already established.
        predicate: A registered literal predicate, such as ``medication``.
        sensitivity: The sensitivity the canonical writer stores for the topic, such as ``medical``.

    Returns:
        The values ordered by row id; empty when nothing qualifies.

    Raises:
        ValueError: If *predicate* is not a registered literal predicate. The message never
            carries the predicate or a stored value.
    """
    definition = resolve_predicate(predicate)
    if definition is None:
        raise ValueError("predicate is not registered")
    facts = await get_active_literal_facts(subject_entity_id=owner_entity_id, definition=definition)
    return tuple(
        fact.value_text
        for fact in facts
        if fact.visibility == _OWN_VISIBILITY and fact.sensitivity == sensitivity
    )
