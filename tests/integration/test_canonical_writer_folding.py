"""The canonical writer compares text values by their key (Plan 0071 Task 1, ADR 0024 decision 12).

A spoken «El Café» and an imported «café» are one row, in either order; two different tastes
stay two; a date, a number or a reference is compared exactly, and so is a text whose key comes
out empty. Every name is an invented canary.
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
from server.memory import candidates
from server.memory.biometric_consent import grant_face_consent
from server.memory.candidate_types import CandidateChannel, ProposedCandidate
from server.memory.candidates import iso_utc
from server.memory.canonical_writer import write_literal
from server.memory.declarative import upsert_entity
from server.memory.memory_writer import PromotionOutcome, promote
from server.memory.predicate_registry import resolve_predicate
from server.memory.relational_v4 import get_active_literal_facts
from server.memory.write_types import WriteChannel
from server.settings import settings
from server.text_keys import comparison_key

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_T0 = datetime(2026, 10, 26, 10, 0, tzinfo=UTC)
_ANSWER = _T0 + timedelta(seconds=20)
_TIMEOUT_S = 5
_IMPORT = WriteChannel.IMPORT_ASSISTED


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
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "writer-folding.db")
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    db._conn = None
    try:
        await db.open_db()
        await db.run_migrations()
        owner_id = await upsert_entity(name="Canary Owner", type="person")
        await grant_face_consent(owner_id)
        yield owner_id
    finally:
        await db.close_db()
        db._conn = None


async def _promote_by_voice(owner_id: int, phrase: str) -> PromotionOutcome:
    stored = await asyncio.wait_for(
        candidates.insert_candidate(
            ProposedCandidate(
                predicate="likes", value_text=phrase, value_key=comparison_key(phrase)
            ),
            subject_person_id=owner_id,
            asserted_by_person_id=owner_id,
            channel=CandidateChannel.VOICE_STREAM,
            correlation_id=uuid4(),
            now=_T0,
        ),
        _TIMEOUT_S,
    )
    assert stored.candidate_id is not None
    assert await candidates.mark_offered(
        stored.candidate_id, owner_id, correlation_id=uuid4(), now=_T0
    )
    result = await asyncio.wait_for(
        promote(
            stored.candidate_id,
            actor=_actor(owner_id),
            correlation_id=uuid4(),
            now=_ANSWER,
            audit=AsyncMock(),
        ),
        _TIMEOUT_S,
    )
    return result.outcome


async def _import(owner_id: int, predicate: str, value: str) -> None:
    await write_literal(
        owner_entity_id=owner_id,
        subject_entity_id=owner_id,
        predicate=predicate,
        value=value,
        channel=_IMPORT,
        confirmed_at=iso_utc(_ANSWER),
    )


async def _values(owner_id: int, predicate: str) -> list[str]:
    definition = resolve_predicate(predicate)
    assert definition is not None
    facts = await get_active_literal_facts(subject_entity_id=owner_id, definition=definition)
    return [fact.value_text for fact in facts]


async def test_a_spoken_taste_and_the_same_imported_taste_are_one_row(owner: int) -> None:
    assert await _promote_by_voice(owner, "El Café") is PromotionOutcome.PROMOTED

    await _import(owner, "likes", "café")

    assert await _values(owner, "likes") == ["El Café"]


async def test_an_imported_taste_and_the_same_spoken_taste_are_one_row(owner: int) -> None:
    await _import(owner, "likes", "café")

    assert await _promote_by_voice(owner, "El Café") is PromotionOutcome.ALREADY_PRESENT

    assert await _values(owner, "likes") == ["café"]


async def test_two_different_tastes_stay_two_rows(owner: int) -> None:
    await _import(owner, "likes", "el café")
    await _import(owner, "likes", "el té")

    assert await _values(owner, "likes") == ["el café", "el té"]


async def test_a_text_whose_key_is_empty_is_compared_exactly(owner: int) -> None:
    await _import(owner, "likes", "la")
    await _import(owner, "likes", "los")
    await _import(owner, "likes", "la")

    assert await _values(owner, "likes") == ["la", "los"]


async def test_a_reference_is_compared_exactly_not_by_key(owner: int) -> None:
    await _import(owner, "document_location", "El testamento en el cajón")
    await _import(owner, "document_location", "testamento en el cajon")

    assert await _values(owner, "document_location") == [
        "El testamento en el cajón",
        "testamento en el cajon",
    ]


async def test_a_date_and_a_number_are_compared_exactly(owner: int) -> None:
    await _import(owner, "birth_date", "1950-05-17")
    await _import(owner, "birth_date", "1950-05-17")
    await _import(owner, "floor", "20")
    await _import(owner, "floor", "20")

    assert await _values(owner, "birth_date") == ["1950-05-17"]
    assert await _values(owner, "floor") == ["20"]
