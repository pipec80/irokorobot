"""Every table that refers to `entities` is classified for the replacement (Plan 0071 Task 5a).

The cleanup of a replacement deletes an entity an earlier import created only when nothing refers
to it. It looks at the V4 rows and the contacts itself; it never relies on ``ON DELETE CASCADE``
to decide what is safe. A new table that refers to ``entities`` fails here until someone says
which of the three cases it is.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from server import db
from tests.integration.seed_household import seed_db

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["seed_db"]

pytestmark = pytest.mark.integration

# (a) Checked by the cleanup: an entity with a row here is never deleted.
_CHECKED = {
    "literal_facts_v4": "the cleanup asks entity_has_rows",
    "entity_relations_v4": "the cleanup asks entity_has_rows, on either end",
    "care_contacts": "the cleanup asks entity_has_contact_rows (RESTRICT besides)",
}
# (b) ON DELETE CASCADE, harmless because a replacement is refused once the robot learned by voice.
_CASCADE_COVERED_BY_THE_VOICE_REFUSAL = {
    "memory_candidates": "a live candidate refuses the replacement; resolved ones hold no value",
    "facts": "the legacy table: the importer never writes it and the voice path is retired",
}
# (c) RESTRICT, NO ACTION or SET NULL: deleting a referred entity fails loudly or is harmless.
_FAIL_LOUDLY_OR_HARMLESS = {
    "face_profiles": "NO ACTION: a face of an imported person would stop the cleanup",
    "voice_profiles": "NO ACTION: a voice would stop the cleanup",
    "face_consent_grants": "RESTRICT",
    "voice_consent_grants": "RESTRICT",
    "household_role_assignments": "RESTRICT (grantor SET NULL)",
    "owner_pin_credentials": "RESTRICT",
    "authorization_audit_events": "SET NULL: the audit keeps its row without the person",
}
_SAFE_ACTIONS = frozenset({"RESTRICT", "NO ACTION", "SET NULL"})


async def _references_to_entities() -> dict[str, set[str]]:
    cursor = await db.get_conn().execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    )
    tables = [str(row[0]) for row in await cursor.fetchall()]
    await cursor.close()
    found: dict[str, set[str]] = {}
    for table in tables:
        cursor = await db.get_conn().execute(f"PRAGMA foreign_key_list({table})")
        for row in await cursor.fetchall():
            # (id, seq, table, from, to, on_update, on_delete, match)
            if str(row[2]) == "entities":
                found.setdefault(table, set()).add(str(row[6]))
        await cursor.close()
    return found


async def test_every_table_that_refers_to_entities_is_classified(seed_db: Path) -> None:
    del seed_db
    found = await _references_to_entities()

    classified = (
        set(_CHECKED) | set(_CASCADE_COVERED_BY_THE_VOICE_REFUSAL) | set(_FAIL_LOUDLY_OR_HARMLESS)
    )
    assert set(found) == classified


async def test_only_the_covered_tables_cascade(seed_db: Path) -> None:
    del seed_db
    found = await _references_to_entities()

    for table in _FAIL_LOUDLY_OR_HARMLESS:
        assert found[table] <= _SAFE_ACTIONS, table
    for table in _CASCADE_COVERED_BY_THE_VOICE_REFUSAL:
        assert "CASCADE" in found[table], table
