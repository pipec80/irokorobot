"""``promote`` stores its fact through the canonical writer (Plan 0065 Task 6c, ADR 0022 dec. 2).

The spoken confirmation of CM-3a is the writer's first caller: it keeps its transaction shape,
its audit order, ``confidence 1.0`` and the ``asserted_at`` of the turn, and the row it stores is
the one the writer's own table would give. The existing ``promote`` tests pin the outcomes; these
pin the seam and the equivalence of the two classification rules.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from server.cognition.identity import (
    ActivePersonContext,
    HouseholdRole,
    IdentityEvidence,
    IdentityEvidenceSource,
    PersonRecord,
    resolve_active_person,
)
from server.cognition.models import Confidence, ConfidenceBasis
from server.memory import candidates, memory_writer
from server.memory.biometric_consent import grant_face_consent
from server.memory.candidate_classifier import CANDIDATE_SENSITIVITY, CANDIDATE_VISIBILITY
from server.memory.candidate_types import CandidateChannel, ProposedCandidate
from server.memory.candidates import iso_utc
from server.memory.canonical_writer import WriteChannel, write_literal
from server.memory.declarative import upsert_entity
from server.memory.memory_writer import PromotionOutcome, promote
from server.memory.relational_v4 import get_literal_fact
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_T0 = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
_ANSWER = _T0 + timedelta(seconds=20)
_TIMEOUT_S = 5


def _actor(person_id: int) -> ActivePersonContext:
    person = PersonRecord(person_id=person_id, display_name="Canary", entity_type="person")
    evidence = tuple(
        IdentityEvidence(
            evidence_id=uuid4(),
            source=source,
            candidate_person_id=person_id,
            confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
            observed_at=_T0,
            reference="canary",
        )
        for source in (IdentityEvidenceSource.FACE, IdentityEvidenceSource.VOICE)
    )
    return resolve_active_person(
        evidence=evidence,
        lookup_person=lambda pid: person if pid == person_id else None,
        lookup_role=lambda _pid: HouseholdRole.OWNER,
        clock=lambda: _T0,
    )


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "promote-writer.db")
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    try:
        owner_id = await upsert_entity(name="Canary Owner", type="person")
        await grant_face_consent(owner_id)
        yield owner_id
    finally:
        await db.close_db()
        db._conn = None


async def _offered(
    owner_id: int,
    channel: CandidateChannel,
    value: str = "el mate",
    key: str = "mate",
    predicate: str = "likes",
) -> int:
    stored = await asyncio.wait_for(
        candidates.insert_candidate(
            ProposedCandidate(predicate=predicate, value_text=value, value_key=key),
            subject_person_id=owner_id,
            asserted_by_person_id=owner_id,
            channel=channel,
            correlation_id=uuid4(),
            now=_T0,
        ),
        _TIMEOUT_S,
    )
    assert stored.candidate_id is not None
    assert await candidates.mark_offered(
        stored.candidate_id, owner_id, correlation_id=uuid4(), now=_T0
    )
    return stored.candidate_id


async def _promote(candidate_id: int, owner_id: int) -> memory_writer.PromotionResult:
    return await asyncio.wait_for(
        promote(
            candidate_id,
            actor=_actor(owner_id),
            correlation_id=uuid4(),
            now=_ANSWER,
            audit=AsyncMock(),
        ),
        _TIMEOUT_S,
    )


@pytest.mark.parametrize("channel", list(CandidateChannel))
async def test_promote_stores_the_fact_through_the_canonical_writer(
    owner: int, monkeypatch: pytest.MonkeyPatch, channel: CandidateChannel
) -> None:
    seen: list[dict[str, object]] = []

    async def spy(**kwargs: object) -> object:
        seen.append(kwargs)
        return await write_literal(**kwargs)  # type: ignore[arg-type]  # forwards typed keywords

    monkeypatch.setattr(memory_writer, "write_literal", spy)
    candidate_id = await _offered(owner, channel)

    result = await _promote(candidate_id, owner)

    assert result.outcome is PromotionOutcome.PROMOTED
    assert len(seen) == 1
    call = seen[0]
    assert call["channel"] == WriteChannel(channel.value)
    assert call["manage_transaction"] is False
    assert (call["owner_entity_id"], call["subject_entity_id"]) == (owner, owner)
    assert call["confidence"] == 1.0
    assert call["asserted_at"] == iso_utc(_T0)
    assert call["confirmed_at"] == iso_utc(_ANSWER)


async def test_the_promoted_row_records_the_asserter_and_the_channel(owner: int) -> None:
    candidate_id = await _offered(owner, CandidateChannel.VOICE_STREAM)

    result = await _promote(candidate_id, owner)

    assert result.fact_id is not None
    fact = await get_literal_fact(result.fact_id)
    assert fact is not None
    assert (fact.visibility, fact.sensitivity) == ("personal", "normal")
    assert fact.confidence == 1.0
    assert fact.asserted_at == iso_utc(_T0)
    assert fact.confirmed_by_entity_id == owner
    assert fact.confirmed_at == iso_utc(_ANSWER)
    assert fact.asserted_by_entity_id == owner
    assert fact.channel == "voice_stream"


@pytest.mark.parametrize("predicate", ["likes", "dislikes", "prefers"])
async def test_the_writer_table_gives_a_taste_the_classification_the_candidate_policy_asks(
    owner: int, predicate: str
) -> None:
    """Two rules, one answer: what the policy authorizes is what the writer stores."""
    fact = await write_literal(
        owner_entity_id=owner,
        subject_entity_id=owner,
        predicate=predicate,
        value="el mate",
        channel=WriteChannel.VOICE_CLASSIC,
        confirmed_at=iso_utc(_ANSWER),
    )

    assert (fact.visibility, fact.sensitivity) == (
        CANDIDATE_VISIBILITY.value,
        CANDIDATE_SENSITIVITY.value,
    )
