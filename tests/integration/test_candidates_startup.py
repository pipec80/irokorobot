"""Start-up reconciles the candidate store before any request is served (ADR 0021 decision 6)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from server.main import create_app, lifespan
from server.memory import candidates
from server.memory.candidate_types import CandidateChannel, CandidateStatus, ProposedCandidate
from server.memory.declarative import upsert_entity
from server.settings import Settings, settings

from server import db, main

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration


async def _seed_an_offered_candidate(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    """Leave one `offered` candidate in a database file, as a previous process would have."""
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    owner = await upsert_entity(name="Canary Owner", type="person")
    stored = await candidates.insert_candidate(
        ProposedCandidate(predicate="likes", value_text="el mate", value_key="mate"),
        subject_person_id=owner,
        asserted_by_person_id=owner,
        channel=CandidateChannel.VOICE_CLASSIC,
        correlation_id=uuid4(),
        now=datetime.now(UTC),
    )
    assert stored.candidate_id is not None
    assert await candidates.mark_offered(
        stored.candidate_id, owner, correlation_id=uuid4(), now=datetime.now(UTC)
    )
    await db.close_db()
    db._conn = None
    return stored.candidate_id


async def _candidate_after_a_start(
    candidate_id: int, db_path: Path, monkeypatch: pytest.MonkeyPatch, *, switch_on: bool
) -> candidates.Candidate | None:
    """Run the real lifespan against the file and read the candidate back afterwards."""
    monkeypatch.setattr(main.stt, "preload", lambda: None)
    monkeypatch.setattr(main.tts, "preload", lambda: None)
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "memory_candidates_enabled", switch_on)
    app = create_app(
        Settings(
            memory_enabled=True,
            memory_candidates_enabled=switch_on,
            brain_db_path=db_path,
        )
    )
    async with lifespan(app):
        assert app.state.ready is True
    db._conn = None
    await db.open_db()
    try:
        return await candidates.get_candidate(candidate_id)
    finally:
        await db.close_db()
        db._conn = None


async def test_a_start_with_the_switch_on_returns_the_offer_to_proposed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "startup.db"
    candidate_id = await _seed_an_offered_candidate(db_path, monkeypatch)

    candidate = await _candidate_after_a_start(candidate_id, db_path, monkeypatch, switch_on=True)

    assert candidate is not None
    assert candidate.status is CandidateStatus.PROPOSED
    assert candidate.value_text == "el mate"
    assert candidate.offered_at is None


async def test_a_start_with_the_switch_off_voids_every_live_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "startup.db"
    candidate_id = await _seed_an_offered_candidate(db_path, monkeypatch)

    candidate = await _candidate_after_a_start(candidate_id, db_path, monkeypatch, switch_on=False)

    assert candidate is not None
    assert candidate.status is CandidateStatus.EXPIRED
    assert (candidate.value_text, candidate.value_key) == (None, None)
