"""A temporary database with the owner set up as `personal-setup` does, for the Plan 0071 tests.

The owner has a PIN and no children. Every name is an invented canary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import SecretStr
import pytest
from server.memory.seed_file import parse_seed_text
from server.memory.seed_plan import SeedPlan, build_plan
from server.personal_setup import PersonalSetupInput, apply_personal_setup
from server.settings import settings

from server import db
from tests.unit.seed_data import Toml, to_toml

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

OWNER_NAME = "Canary Owner"
NOW = "2026-10-26T12:00:00.000000+00:00"


@pytest.fixture
async def seed_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Path]:
    """Open a fresh temporary database at the latest schema, with nothing in it."""
    path = tmp_path / "seed.db"
    monkeypatch.setattr(settings, "brain_db_path", path)
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        yield path
    finally:
        await db.close_db()
        db._conn = None


@pytest.fixture
async def owner(seed_db: Path) -> int:
    """Set up the owner and a PIN exactly as `just setup-personal` does, with no children."""
    del seed_db
    result = await apply_personal_setup(
        PersonalSetupInput(owner_name=OWNER_NAME, child_names=(), pin=SecretStr("482173"))
    )
    assert result.personal_security_ready
    return result.owner_entity_id


def plan_of(data: Toml) -> SeedPlan:
    """Build the plan of an invented seed dictionary."""
    return build_plan(parse_seed_text(to_toml(data)))


async def scalar(sql: str, *params: object) -> object:
    """Return the first column of the first row of a test query."""
    cursor = await db.get_conn().execute(sql, params)
    row = await cursor.fetchone()
    await cursor.close()
    assert row is not None
    return row[0]
