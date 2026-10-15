"""The composite "enrolled for strong" reader (ADR 0021 decision 3) over a temporary SQLite."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from server.memory.biometric_consent import (
    grant_face_consent,
    revoke_face_consent,
)
from server.memory.declarative import upsert_entity
from server.memory.enrollment import is_enrolled_for_strong
from server.memory.voice_consent import grant_voice_consent, revoke_voice_consent
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration


@pytest.fixture
async def person(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "enrollment.db")
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield await upsert_entity(name="Canary Owner", type="person")
    await db.close_db()
    db._conn = None


async def test_nothing_enrolled_is_not_enrolled(person: int) -> None:
    assert not await is_enrolled_for_strong(person)


async def test_face_alone_or_voice_alone_is_not_enough(person: int) -> None:
    await grant_face_consent(person)
    assert not await is_enrolled_for_strong(person)

    await revoke_face_consent(person)
    await grant_voice_consent(person)
    assert not await is_enrolled_for_strong(person)


async def test_both_consents_enrol_and_revoking_either_unenrols(person: int) -> None:
    await grant_face_consent(person)
    await grant_voice_consent(person)
    assert await is_enrolled_for_strong(person)

    await revoke_voice_consent(person)
    assert not await is_enrolled_for_strong(person)

    await grant_voice_consent(person)
    await revoke_face_consent(person)
    assert not await is_enrolled_for_strong(person)
