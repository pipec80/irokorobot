"""Integration tests for the background proposal (ADR 0021 decisions 3, 4, 7, 10)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
from server.cognition.identity import (
    ActivePersonContext,
    HouseholdRole,
    IdentityEvidence,
    IdentityEvidenceSource,
    PersonRecord,
    resolve_active_person,
)
from server.cognition.models import CognitiveEvent, Confidence, ConfidenceBasis
from server.cognition.response_plan import TextTurnPayload
from server.exceptions import LLMError
from server.memory import candidates
from server.memory.biometric_consent import grant_face_consent
from server.memory.candidate_limits import limiter
from server.memory.candidate_proposal import ProposalOutcome, propose_candidates
from server.memory.candidate_types import CandidateChannel, CandidateReason, RawCandidate
from server.memory.declarative import upsert_entity
from server.memory.entity_labels import list_known_names
from server.memory.household_authorization import record_authorization_decision
from server.memory.voice_consent import grant_voice_consent
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
_WAV = b"RIFF-canary-clip"
_CORRELATION = UUID(int=4242)


def _evidence(source: IdentityEvidenceSource, person_id: int) -> IdentityEvidence:
    return IdentityEvidence(
        evidence_id=uuid4(),
        source=source,
        candidate_person_id=person_id,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
        observed_at=_NOW - timedelta(seconds=1),
        reference="canary",
        expires_at=_NOW + timedelta(minutes=5)
        if source is IdentityEvidenceSource.LOCAL_UNLOCK
        else None,
        grant_scope="personal_protected_read"
        if source is IdentityEvidenceSource.LOCAL_UNLOCK
        else None,
        grant_spent=source is IdentityEvidenceSource.LOCAL_UNLOCK,
    )


def _actor(person_id: int, *sources: IdentityEvidenceSource) -> ActivePersonContext:
    sources = sources or (IdentityEvidenceSource.FACE,)
    person = PersonRecord(person_id=person_id, display_name="Canary", entity_type="person")
    return resolve_active_person(
        evidence=tuple(_evidence(s, person_id) for s in sources),
        lookup_person=lambda pid: person if pid == person_id else None,
        lookup_role=lambda _pid: HouseholdRole.OWNER,
        clock=lambda: _NOW,
    )


def _event() -> CognitiveEvent[TextTurnPayload]:
    return CognitiveEvent(
        event_id=uuid4(),
        schema_version=1,
        event_type="text.turn",
        occurred_at=_NOW,
        recorded_at=_NOW,
        source="audio.transcribe",
        correlation_id=_CORRELATION,
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message="canary", conversation_id="canary"),
    )


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "proposal.db")
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    limiter.reset()
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    owner_id = await upsert_entity(name="Canary Owner", type="person")
    await grant_face_consent(owner_id)
    await grant_voice_consent(owner_id)
    yield owner_id
    await db.close_db()
    db._conn = None
    limiter.reset()


class _Seams:
    """The doubles of one proposal: what the voice check and the model say."""

    def __init__(
        self,
        owner_id: int,
        *triples: RawCandidate,
        strong: bool = True,
        extract_error: Exception | None = None,
    ) -> None:
        self.owner_id = owner_id
        self.extract = AsyncMock(side_effect=extract_error, return_value=triples)
        self.strong_actor = _actor(
            owner_id, IdentityEvidenceSource.FACE, IdentityEvidenceSource.VOICE
        )
        self.verify = AsyncMock(return_value=self.strong_actor if strong else None)
        self.audit = AsyncMock()
        self.client = httpx.AsyncClient()

    async def run(
        self,
        message: str = "me gusta el mate",
        actor: ActivePersonContext | None = None,
        **overrides: object,
    ) -> ProposalOutcome:
        kwargs: dict[str, object] = {
            "event": _event(),
            "wav_bytes": _WAV,
            "channel": CandidateChannel.VOICE_CLASSIC,
            "extract": self.extract,
            "verify": self.verify,
            "audit": self.audit,
            "clock": lambda: _NOW,
        }
        kwargs.update(overrides)
        return await propose_candidates(
            self.client,
            message,
            actor or _actor(self.owner_id),
            **kwargs,  # type: ignore[arg-type]
        )


def _taste(obj: str = "el mate", predicate: str = "likes", topic: str = "drink") -> RawCandidate:
    return RawCandidate(predicate=predicate, object=obj, topic=topic)


async def _live() -> list[tuple[str, str]]:
    cursor = await db.get_conn().execute(
        "SELECT predicate, value_text FROM memory_candidates WHERE status IN ('proposed','offered')"
    )
    rows = [(str(r[0]), str(r[1])) for r in await cursor.fetchall()]
    await cursor.close()
    return rows


async def test_a_taste_said_with_face_and_voice_becomes_one_proposed_candidate(owner: int) -> None:
    seams = _Seams(owner, _taste())

    outcome = await seams.run()

    assert outcome == ProposalOutcome(stored=1, reasons=())
    assert await _live() == [("likes", "el mate")]
    seams.extract.assert_awaited_once()
    assert seams.extract.call_args.args[1] == "me gusta el mate"
    seams.verify.assert_awaited_once()
    assert seams.verify.call_args.kwargs["wav_bytes"] == _WAV
    seams.audit.assert_awaited_once()
    assert seams.audit.call_args.args[0].action.value == "propose_personal_memory"
    stored = await candidates.get_candidate(1)
    assert stored is not None
    assert stored.source_correlation_id == str(_CORRELATION)
    assert stored.subject_person_id == stored.asserted_by_person_id == owner


async def test_the_real_audit_row_is_written_for_the_proposal(owner: int) -> None:
    seams = _Seams(owner, _taste())

    await seams.run(audit=record_authorization_decision)

    cursor = await db.get_conn().execute(
        "SELECT action, decision, correlation_id, data_categories FROM authorization_audit_events"
    )
    rows = list(await cursor.fetchall())
    await cursor.close()
    assert rows == [("propose_personal_memory", "allowed", str(_CORRELATION), "normal,personal")]


@pytest.mark.parametrize(
    "message, reason",
    [
        ("hola robot", CandidateReason.GATE_NO_MATCH),
        ("¿te gusta el mate?", CandidateReason.NOT_A_TASTE),
        (
            "Prefiero que no menciones mi mudanza reciente delante de visitas",
            CandidateReason.NOT_A_TASTE,
        ),
        ("prefiero no hablar de mi divorcio", CandidateReason.NEGATION_UNSUPPORTED),
    ],
)
async def test_a_text_the_gate_refuses_costs_no_voice_check_and_no_model_call(
    owner: int, message: str, reason: CandidateReason
) -> None:
    seams = _Seams(owner, _taste())

    outcome = await seams.run(message)

    assert outcome == ProposalOutcome(reasons=(reason,))
    seams.verify.assert_not_awaited()
    seams.extract.assert_not_awaited()
    assert await _live() == []


@pytest.mark.parametrize(
    "sources",
    [
        (IdentityEvidenceSource.LOCAL_UNLOCK,),
        (IdentityEvidenceSource.FACE, IdentityEvidenceSource.LOCAL_UNLOCK),
        (IdentityEvidenceSource.MANUAL,),
        (IdentityEvidenceSource.VOICE,),
    ],
)
async def test_an_actor_that_is_not_a_token_free_face_never_reaches_the_voice_or_the_model(
    owner: int, sources: tuple[IdentityEvidenceSource, ...]
) -> None:
    seams = _Seams(owner, _taste())

    outcome = await seams.run(actor=_actor(owner, *sources))

    assert outcome.reasons == (CandidateReason.STRONG_UNREACHABLE,)
    seams.verify.assert_not_awaited()
    seams.extract.assert_not_awaited()


async def test_a_voice_that_is_not_verified_costs_no_model_call(owner: int) -> None:
    seams = _Seams(owner, _taste(), strong=False)

    outcome = await seams.run()

    assert outcome.reasons == (CandidateReason.STRONG_UNREACHABLE,)
    seams.extract.assert_not_awaited()
    assert await _live() == []


async def test_a_failing_voice_check_fails_closed(owner: int) -> None:
    seams = _Seams(owner, _taste())
    seams.verify.side_effect = RuntimeError("model exploded")

    outcome = await seams.run()

    assert outcome.reasons == (CandidateReason.DENIED,)
    seams.extract.assert_not_awaited()


async def test_the_kill_switch_does_nothing_at_all(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
    seams = _Seams(owner, _taste())

    await seams.run()

    seams.verify.assert_not_awaited()
    seams.extract.assert_not_awaited()


async def test_a_second_matching_turn_while_one_extracts_is_dropped_as_busy(owner: int) -> None:
    release = asyncio.Event()
    started = asyncio.Event()
    first = _Seams(owner, _taste())

    async def slow(*_args: object) -> tuple[RawCandidate, ...]:
        started.set()
        await release.wait()
        return (_taste(),)

    first.extract = AsyncMock(side_effect=slow)
    second = _Seams(owner, _taste("el jazz", topic="music"))
    running = asyncio.create_task(first.run())
    await started.wait()

    dropped = await second.run("me gusta el jazz")
    release.set()
    done = await running

    assert dropped.reasons == (CandidateReason.BUSY,)
    second.verify.assert_not_awaited()
    second.extract.assert_not_awaited()
    assert done.stored == 1
    assert not limiter.busy


async def test_the_hourly_budget_is_spent_then_returns_with_the_clock(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "memory_candidate_extractions_per_hour", 1)
    fake = {"now": 1000.0}
    monkeypatch.setattr(limiter, "_clock", lambda: fake["now"])
    seams = _Seams(owner, _taste())

    first = await seams.run()
    second = await seams.run("me gusta el mate verde")
    fake["now"] += 3600.0
    third = await seams.run("me gusta el mate cocido")

    assert first.stored == 1
    assert second.reasons == (CandidateReason.BUDGET,)
    assert third.reasons != (CandidateReason.BUDGET,)
    assert seams.extract.await_count == 2


@pytest.mark.parametrize(
    "error", [LLMError("bad json"), httpx.ConnectError("zumo de pomelo is down")]
)
async def test_a_failed_extraction_stores_nothing_and_frees_the_slot_without_logging_the_message(
    owner: int, error: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    seams = _Seams(owner, extract_error=error)

    with caplog.at_level(logging.DEBUG, logger="server"):
        outcome = await seams.run()

    assert outcome.reasons == (CandidateReason.DENIED,)
    assert await _live() == []
    assert not limiter.busy
    assert "pomelo" not in caplog.text
    assert "bad json" not in caplog.text


async def test_cancelling_the_extraction_frees_the_slot(owner: int) -> None:
    started = asyncio.Event()
    seams = _Seams(owner, _taste())

    async def forever(*_args: object) -> tuple[RawCandidate, ...]:
        started.set()
        await asyncio.Event().wait()
        return ()

    seams.extract = AsyncMock(side_effect=forever)
    task = asyncio.create_task(seams.run())
    await started.wait()
    assert limiter.busy

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert not limiter.busy


@pytest.mark.parametrize(
    "triple, message, reason",
    [
        (_taste("mi hijo", topic="food"), "me gusta mi hijo", CandidateReason.SENSITIVE_TOPIC),
        (_taste("el té", topic="drink"), "me gusta el mate", CandidateReason.NOT_GROUNDED),
        (
            _taste(predicate="lives_in", topic="food"),
            "me gusta el mate",
            CandidateReason.GATE_MISMATCH,
        ),
        (_taste(topic="health"), "me gusta el mate", CandidateReason.SENSITIVE_TOPIC),
        (_taste("Tomasito", topic="animal"), "me gusta Tomasito", CandidateReason.SENSITIVE_TOPIC),
    ],
)
async def test_what_the_classifier_drops_is_never_stored(
    owner: int, triple: RawCandidate, message: str, reason: CandidateReason
) -> None:
    await upsert_entity(name="Tomasito", type="other")
    seams = _Seams(owner, triple)

    outcome = await seams.run(message)

    assert outcome == ProposalOutcome(stored=0, reasons=(reason,))
    assert await _live() == []
    seams.audit.assert_not_awaited()


async def test_only_the_triples_the_policy_allows_are_stored(owner: int) -> None:
    seams = _Seams(owner, _taste("el mate"), _taste("el jazz", topic="music"))
    seams.audit.side_effect = [None, RuntimeError("down")]

    outcome = await seams.run("me gusta el mate y me gusta el jazz")

    assert outcome.stored == 1
    assert outcome.reasons == (CandidateReason.DENIED,)
    assert await _live() == [("likes", "el mate")]


async def test_enrolment_is_checked_again_right_before_the_store(owner: int) -> None:
    seams = _Seams(owner, _taste())

    outcome = await seams.run(enrolled=AsyncMock(return_value=False))

    assert outcome.reasons == (CandidateReason.STRONG_UNREACHABLE,)
    assert await _live() == []
    seams.audit.assert_not_awaited()  # no "allowed" row for something that was not stored


async def test_a_repeated_statement_and_the_cap_are_reported_not_raised(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "memory_candidate_max_live", 1)
    seams = _Seams(owner, _taste())
    await seams.run()
    seams.extract.return_value = (_taste(),)

    again = await seams.run()
    seams.extract.return_value = (_taste("el jazz", topic="music"),)
    other = await seams.run("me gusta el jazz")

    assert again.reasons == (CandidateReason.DUPLICATE,)
    assert other.reasons == (CandidateReason.CAPACITY,)
    assert await _live() == [("likes", "el mate")]


async def test_the_extractor_sees_only_the_users_words(owner: int) -> None:
    seams = _Seams(owner, _taste())

    await seams.run("me gusta el mate")

    assert seams.extract.call_args.args[1] == "me gusta el mate"
    assert len(seams.extract.call_args.args) == 2  # a client and the user's text, nothing else


async def test_no_value_reaches_a_log_line(owner: int, caplog: pytest.LogCaptureFixture) -> None:
    seams = _Seams(owner, _taste("el zumo de pomelo", topic="drink"))

    with caplog.at_level(logging.DEBUG, logger="server"):
        outcome = await seams.run("me gusta el zumo de pomelo")

    assert outcome.stored == 1
    assert "pomelo" not in caplog.text


async def test_the_known_names_are_people_and_pets_with_their_aliases(owner: int) -> None:
    await upsert_entity(name="Tomasito", type="other", aliases=["Tomi"])
    await upsert_entity(name="Cafetera", type="object")

    names = await list_known_names()

    assert {"Canary Owner", "Tomasito", "Tomi"} <= names
    assert "Cafetera" not in names
