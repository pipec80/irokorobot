"""The offline owner-PIN check for the admin (Plan 0073 Task 3, ADR 0025 decision 4).

A sensitive admin edit needs the owner's PIN with the server stopped. `verify_owner_pin` reuses
the single cryptographic verifier (`verify_pin`) over the active credential; it raises
`AdminPinError` and never carries the PIN. The PIN here is invented.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest
from server.cognition.pin_credentials import hash_pin
from server.exceptions import AdminPinError
from server.memory.admin_pin import verify_owner_pin
from server.memory.declarative import upsert_entity
from server.memory.household_authorization import bootstrap_initial_owner
from server.memory.owner_credentials import save_owner_pin_credential
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_PIN = "482173"
_WRONG = "999999"


@pytest.fixture
async def owner_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[bool]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "admin-pin.db")
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        yield True
    finally:
        await db.close_db()
        db._conn = None


async def _make_owner_with_pin(pin: str) -> int:
    owner = await upsert_entity(name="Canary Owner", type="person")
    await bootstrap_initial_owner(person_entity_id=owner, confirmed_person_entity_id=owner)
    await save_owner_pin_credential(person_entity_id=owner, credential=hash_pin(pin))
    return owner


async def test_the_right_pin_verifies(owner_db: bool) -> None:
    await _make_owner_with_pin(_PIN)
    assert await verify_owner_pin(_PIN) is None


async def test_a_wrong_pin_is_refused(owner_db: bool) -> None:
    await _make_owner_with_pin(_PIN)
    with pytest.raises(AdminPinError):
        await verify_owner_pin(_WRONG)


async def test_no_active_credential_is_refused(owner_db: bool) -> None:
    with pytest.raises(AdminPinError):
        await verify_owner_pin(_PIN)


async def test_the_pin_never_reaches_the_message_or_a_log(
    owner_db: bool, caplog: pytest.LogCaptureFixture
) -> None:
    await _make_owner_with_pin(_PIN)
    with caplog.at_level(logging.DEBUG), pytest.raises(AdminPinError) as caught:
        await verify_owner_pin(_WRONG)
    assert _WRONG not in str(caught.value)
    assert _WRONG not in caplog.text
