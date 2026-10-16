"""The spoken offer and the explicit answer (ADR 0021 decision 9, Plan 0063).

Every offer, answer and promotion needs the face and the voice of the same person on the
turn's own clip and never a token; anything else falls through to ordinary generation, so the
callers here return ``None`` and change nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from server.cognition.identity import (
    ActivePersonContext,
    HouseholdRole,
    IdentityEvidence,
    IdentityEvidenceSource,
    PersonRecord,
    resolve_active_person,
)
from server.cognition.intent_resolution import MemoryAnswer, parse_memory_answer
from server.cognition.models import (
    AuthorizationAction,
    AuthorizationDecision,
    CognitiveEvent,
    Confidence,
    ConfidenceBasis,
)
from server.cognition.response_plan import TextTurnPayload
from server.memory import candidate_dialogue, candidates
from server.memory.candidate_classifier import comparison_key
from server.memory.candidate_dialogue import (
    ANSWER_CONTRADICTION_PHRASE,
    ANSWER_FAILED_PHRASE,
    ANSWER_REJECTED_PHRASE,
    ANSWER_SAVED_PHRASE,
    PendingOffer,
    answer_offer,
    commit_offer,
    compose_offer,
    prepare_offer,
)
from server.memory.candidate_types import CandidateChannel, CandidateStatus, ProposedCandidate
from server.memory.declarative import upsert_entity
from server.memory.predicate_registry import resolve_predicate
from server.memory.relational_v4 import assert_literal_fact, get_active_literal_facts
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from server.cognition.authorization import AuthorizationRequest

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)
_WAV = b"RIFF-canary-clip"
_TURN = UUID(int=6363)


def _evidence(source: IdentityEvidenceSource, person_id: int) -> IdentityEvidence:
    token = source is IdentityEvidenceSource.LOCAL_UNLOCK
    return IdentityEvidence(
        evidence_id=uuid4(),
        source=source,
        candidate_person_id=person_id,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
        observed_at=_NOW - timedelta(seconds=1),
        reference="canary",
        expires_at=_NOW + timedelta(minutes=5) if token else None,
        grant_scope="personal_protected_read" if token else None,
        grant_spent=token,
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


def _strong(person_id: int) -> ActivePersonContext:
    return _actor(person_id, IdentityEvidenceSource.FACE, IdentityEvidenceSource.VOICE)


def _event() -> CognitiveEvent[TextTurnPayload]:
    return CognitiveEvent(
        event_id=uuid4(),
        schema_version=1,
        event_type="text.turn",
        occurred_at=_NOW,
        recorded_at=_NOW,
        source="audio.transcribe",
        correlation_id=_TURN,
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message="canary", conversation_id="canary"),
    )


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "dialogue.db")
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield await upsert_entity(name="Canary Owner", type="person")
    await db.close_db()
    db._conn = None


async def _candidate(
    person_id: int,
    value: str = "el mate",
    key: str = "mate",
    predicate: str = "likes",
    *,
    offered: bool = False,
) -> int:
    result = await candidates.insert_candidate(
        ProposedCandidate(predicate=predicate, value_text=value, value_key=key),
        subject_person_id=person_id,
        asserted_by_person_id=person_id,
        channel=CandidateChannel.VOICE_STREAM,
        correlation_id=uuid4(),
        now=_NOW - timedelta(minutes=5),
    )
    assert result.candidate_id is not None
    if offered:
        assert await candidates.mark_offered(
            result.candidate_id, person_id, correlation_id=uuid4(), now=_NOW
        )
    return result.candidate_id


async def _status(candidate_id: int) -> CandidateStatus:
    stored = await candidates.get_candidate(candidate_id)
    assert stored is not None
    return stored.status


async def _likes(person_id: int) -> list[object]:
    definition = resolve_predicate("likes")
    assert definition is not None
    return list(await get_active_literal_facts(subject_entity_id=person_id, definition=definition))


def _leaked(caplog: pytest.LogCaptureFixture, canary: str) -> bool:
    """Whether *canary* shows in any record's message or in any of its ``extra`` fields."""
    return any(
        canary in record.getMessage() or canary in str(record.__dict__) for record in caplog.records
    )


def _actions(audit: AsyncMock) -> list[tuple[AuthorizationAction, str]]:
    calls: list[tuple[AuthorizationAction, str]] = []
    for call in audit.await_args_list:
        request: AuthorizationRequest = call.args[0]
        decision: AuthorizationDecision = call.args[1]
        calls.append((request.action, decision.decision.value))
    return calls


# --- the phrase ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "predicate, value, expected",
    [
        (
            "likes",
            "el mate",
            "Antes me dijiste que te gusta el mate. ¿Quieres que lo guarde? "
            "Dime: sí, autorizo guardar el mate.",
        ),
        (
            "likes",
            "las empanadas",
            "Antes me dijiste que te gustan las empanadas. ¿Quieres que lo guarde? "
            "Dime: sí, autorizo guardar las empanadas.",
        ),
        (
            "dislikes",
            "el cilantro",
            "Antes me dijiste que no te gusta el cilantro. ¿Quieres que lo guarde? "
            "Dime: sí, autorizo guardar el cilantro.",
        ),
        (
            "prefers",
            "el té",
            "Antes me dijiste que prefieres el té. ¿Quieres que lo guarde? "
            "Dime: sí, autorizo guardar el té.",
        ),
    ],
)
def test_the_offer_is_neutral_spanish_and_tells_the_exact_answer(
    predicate: str, value: str, expected: str
) -> None:
    assert compose_offer(predicate, value) == expected


@pytest.mark.parametrize(
    "value", ["el mate", "lo picante", "las empanadas", "bailar", "el café con leche"]
)
def test_the_answer_the_offer_asks_for_resolves_that_offer(value: str) -> None:
    """Round trip: the words the robot tells the owner to say parse back to the same key."""
    offer = compose_offer("likes", value)
    instructed = offer.split("Dime: ", 1)[1]

    answer = parse_memory_answer(instructed)

    assert answer is not None
    assert answer.accept
    assert comparison_key(answer.phrase) == comparison_key(value)


def test_an_unknown_predicate_has_no_offer() -> None:
    with pytest.raises(ValueError, match="no offer"):
        compose_offer("lives_in", "la costa")


# --- preparing an offer (concurrently with generation) --------------------------------------


async def test_the_oldest_candidate_is_prepared_with_the_voice_of_the_same_person(
    owner: int,
) -> None:
    first = await _candidate(owner)
    await _candidate(owner, "el jazz", "jazz")
    verify = AsyncMock(return_value=_strong(owner))

    offer = await prepare_offer(
        _actor(owner), wav_bytes=_WAV, event=_event(), verify=verify, clock=lambda: _NOW
    )

    assert offer is not None
    assert (offer.candidate_id, offer.subject_person_id) == (first, owner)
    assert offer.correlation_id == _TURN
    assert "el mate" in offer.phrase
    verify.assert_awaited_once()
    assert verify.await_args is not None
    assert verify.await_args.kwargs["wav_bytes"] == _WAV
    assert await _status(first) is CandidateStatus.PROPOSED


async def test_no_candidate_means_no_voice_check_at_all(owner: int) -> None:
    verify = AsyncMock(return_value=_strong(owner))

    offer = await prepare_offer(
        _actor(owner), wav_bytes=_WAV, event=_event(), verify=verify, clock=lambda: _NOW
    )

    assert offer is None
    verify.assert_not_awaited()


@pytest.mark.parametrize(
    "sources",
    [
        (IdentityEvidenceSource.LOCAL_UNLOCK,),
        (IdentityEvidenceSource.FACE, IdentityEvidenceSource.LOCAL_UNLOCK),
        (IdentityEvidenceSource.MANUAL,),
    ],
)
async def test_a_token_or_a_manual_actor_is_never_offered_anything(
    owner: int, sources: tuple[IdentityEvidenceSource, ...]
) -> None:
    await _candidate(owner)
    verify = AsyncMock(return_value=_strong(owner))

    offer = await prepare_offer(
        _actor(owner, *sources), wav_bytes=_WAV, event=_event(), verify=verify
    )

    assert offer is None
    verify.assert_not_awaited()


async def test_a_voice_that_is_not_verified_is_offered_nothing(owner: int) -> None:
    await _candidate(owner)

    offer = await prepare_offer(
        _actor(owner), wav_bytes=_WAV, event=_event(), verify=AsyncMock(return_value=None)
    )

    assert offer is None


async def test_the_switch_off_prepares_nothing(owner: int, monkeypatch: pytest.MonkeyPatch) -> None:
    await _candidate(owner)
    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
    verify = AsyncMock(return_value=_strong(owner))

    assert await prepare_offer(_actor(owner), wav_bytes=_WAV, event=_event(), verify=verify) is None
    verify.assert_not_awaited()


async def test_a_failing_preparation_never_raises_and_never_logs_its_message(
    owner: int, caplog: pytest.LogCaptureFixture
) -> None:
    await _candidate(owner)
    verify = AsyncMock(side_effect=RuntimeError("zumo de pomelo"))

    with caplog.at_level(logging.DEBUG):
        offer = await prepare_offer(_actor(owner), wav_bytes=_WAV, event=_event(), verify=verify)

    assert offer is None
    assert not _leaked(caplog, "pomelo")
    assert "RuntimeError" in caplog.text


# --- committing an offer (after the reply was built) ----------------------------------------


def _pending(candidate_id: int, owner: int) -> PendingOffer:
    return PendingOffer(
        candidate_id=candidate_id,
        subject_person_id=owner,
        phrase=compose_offer("likes", "el mate"),
        actor=_strong(owner),
        correlation_id=_TURN,
    )


async def test_the_read_is_audited_before_the_candidate_becomes_offered(owner: int) -> None:
    candidate_id = await _candidate(owner)
    seen: list[CandidateStatus] = []

    async def audit(_request: AuthorizationRequest, _decision: AuthorizationDecision) -> None:
        seen.append(await _status(candidate_id))

    phrase = await commit_offer(_pending(candidate_id, owner), now=_NOW, audit=audit)

    assert phrase == compose_offer("likes", "el mate")
    assert seen == [CandidateStatus.PROPOSED]
    stored = await candidates.get_candidate(candidate_id)
    assert stored is not None
    assert stored.status is CandidateStatus.OFFERED
    assert stored.offer_correlation_id == str(_TURN)
    assert stored.offer_count == 1


async def test_a_failing_audit_speaks_nothing_and_offers_nothing(owner: int) -> None:
    candidate_id = await _candidate(owner)

    phrase = await commit_offer(
        _pending(candidate_id, owner),
        now=_NOW,
        audit=AsyncMock(side_effect=RuntimeError("audit down")),
    )

    assert phrase is None
    assert await _status(candidate_id) is CandidateStatus.PROPOSED


async def test_an_offer_already_made_elsewhere_is_neither_audited_nor_spoken(owner: int) -> None:
    """Another turn offered it first: no "allowed" row is written for an offer never spoken."""
    candidate_id = await _candidate(owner, offered=True)
    audit = AsyncMock()

    assert await commit_offer(_pending(candidate_id, owner), now=_NOW, audit=audit) is None
    audit.assert_not_awaited()


async def test_a_voice_verified_for_another_person_is_offered_nothing(owner: int) -> None:
    visitor = await upsert_entity(name="Canary Visitor", type="person")
    await _candidate(owner)

    offer = await prepare_offer(
        _actor(owner),
        wav_bytes=_WAV,
        event=_event(),
        verify=AsyncMock(return_value=_strong(visitor)),
    )

    assert offer is None


async def test_the_read_audit_row_names_the_read_action(owner: int) -> None:
    candidate_id = await _candidate(owner)
    audit = AsyncMock()

    await commit_offer(_pending(candidate_id, owner), now=_NOW, audit=audit)

    assert _actions(audit) == [(AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY, "allowed")]


# --- the answer --------------------------------------------------------------------------------


async def test_yes_with_the_value_promotes_the_offer(owner: int) -> None:
    candidate_id = await _candidate(owner, offered=True)
    audit = AsyncMock()

    phrase = await answer_offer(
        MemoryAnswer(accept=True, phrase="el mate"),
        actor=_strong(owner),
        correlation_id=_TURN,
        now=_NOW + timedelta(seconds=10),
        audit=audit,
    )

    assert phrase == ANSWER_SAVED_PHRASE
    stored = await candidates.get_candidate(candidate_id)
    assert stored is not None
    assert stored.status is CandidateStatus.CONFIRMED
    assert stored.promoted_fact_id is not None
    assert _actions(audit) == [(AuthorizationAction.CONFIRM_PERSONAL_MEMORY, "allowed")]


async def test_no_with_the_value_rejects_it_after_auditing_the_confirm_step(owner: int) -> None:
    candidate_id = await _candidate(owner, offered=True)
    audit = AsyncMock()

    phrase = await answer_offer(
        MemoryAnswer(accept=False, phrase="el mate"),
        actor=_strong(owner),
        correlation_id=_TURN,
        now=_NOW + timedelta(seconds=10),
        audit=audit,
    )

    assert phrase == ANSWER_REJECTED_PHRASE
    stored = await candidates.get_candidate(candidate_id)
    assert stored is not None
    assert stored.status is CandidateStatus.REJECTED
    assert (stored.value_text, stored.value_key) == (None, None)
    assert _actions(audit) == [(AuthorizationAction.CONFIRM_PERSONAL_MEMORY, "allowed")]
    assert await _likes(owner) == []


async def test_the_reject_is_audited_before_the_candidate_changes(owner: int) -> None:
    candidate_id = await _candidate(owner, offered=True)
    seen: list[CandidateStatus] = []

    async def audit(_request: AuthorizationRequest, _decision: AuthorizationDecision) -> None:
        seen.append(await _status(candidate_id))

    phrase = await answer_offer(
        MemoryAnswer(accept=False, phrase="el mate"),
        actor=_strong(owner),
        correlation_id=_TURN,
        now=_NOW + timedelta(seconds=10),
        audit=audit,
    )

    assert phrase == ANSWER_REJECTED_PHRASE
    assert seen == [CandidateStatus.OFFERED]


async def test_a_failing_audit_never_rejects(owner: int) -> None:
    candidate_id = await _candidate(owner, offered=True)

    phrase = await answer_offer(
        MemoryAnswer(accept=False, phrase="el mate"),
        actor=_strong(owner),
        correlation_id=_TURN,
        now=_NOW + timedelta(seconds=10),
        audit=AsyncMock(side_effect=RuntimeError("audit down")),
    )

    assert phrase == ANSWER_FAILED_PHRASE
    stored = await candidates.get_candidate(candidate_id)
    assert stored is not None
    assert stored.status is CandidateStatus.OFFERED
    assert stored.value_text == "el mate"


async def test_a_contradiction_is_said_plainly_and_writes_nothing(owner: int) -> None:
    definition = resolve_predicate("dislikes")
    assert definition is not None
    await assert_literal_fact(subject_entity_id=owner, definition=definition, value="el mate")
    await _candidate(owner, offered=True)

    phrase = await answer_offer(
        MemoryAnswer(accept=True, phrase="el mate"),
        actor=_strong(owner),
        correlation_id=_TURN,
        now=_NOW + timedelta(seconds=10),
        audit=AsyncMock(),
    )

    assert phrase == ANSWER_CONTRADICTION_PHRASE
    assert await _likes(owner) == []


@pytest.mark.parametrize(
    "answer",
    [
        MemoryAnswer(accept=True, phrase="el cafe"),
        MemoryAnswer(accept=False, phrase="el cafe"),
        MemoryAnswer(accept=True, phrase="el"),
    ],
)
async def test_an_answer_with_another_value_falls_through_and_changes_nothing(
    owner: int, answer: MemoryAnswer
) -> None:
    candidate_id = await _candidate(owner, offered=True)
    audit = AsyncMock()

    phrase = await answer_offer(
        answer, actor=_strong(owner), correlation_id=_TURN, now=_NOW, audit=audit
    )

    assert phrase is None
    assert await _status(candidate_id) is CandidateStatus.OFFERED
    audit.assert_not_awaited()


async def test_an_answer_with_no_offer_outstanding_falls_through(owner: int) -> None:
    candidate_id = await _candidate(owner)
    audit = AsyncMock()

    phrase = await answer_offer(
        MemoryAnswer(accept=True, phrase="el mate"),
        actor=_strong(owner),
        correlation_id=_TURN,
        now=_NOW,
        audit=audit,
    )

    assert phrase is None
    assert await _status(candidate_id) is CandidateStatus.PROPOSED
    audit.assert_not_awaited()


@pytest.mark.parametrize(
    "sources",
    [
        (IdentityEvidenceSource.FACE,),
        (IdentityEvidenceSource.VOICE,),
        (IdentityEvidenceSource.FACE, IdentityEvidenceSource.LOCAL_UNLOCK),
        (
            IdentityEvidenceSource.FACE,
            IdentityEvidenceSource.VOICE,
            IdentityEvidenceSource.LOCAL_UNLOCK,
        ),
    ],
)
async def test_a_weaker_or_token_actor_cannot_answer(
    owner: int,
    sources: tuple[IdentityEvidenceSource, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refused before the store is read, so nothing depends on whether an offer exists."""
    candidate_id = await _candidate(owner, offered=True)
    audit = AsyncMock()
    reader = AsyncMock(wraps=candidates.find_offered)
    monkeypatch.setattr(candidate_dialogue, "find_offered", reader)

    phrase = await answer_offer(
        MemoryAnswer(accept=True, phrase="el mate"),
        actor=_actor(owner, *sources),
        correlation_id=_TURN,
        now=_NOW,
        audit=audit,
    )

    assert phrase is None
    assert await _status(candidate_id) is CandidateStatus.OFFERED
    audit.assert_not_awaited()
    reader.assert_not_awaited()


async def test_another_persons_offer_is_never_answered(owner: int) -> None:
    visitor = await upsert_entity(name="Canary Visitor", type="person")
    theirs = await _candidate(visitor, offered=True)

    phrase = await answer_offer(
        MemoryAnswer(accept=True, phrase="el mate"),
        actor=_strong(owner),
        correlation_id=_TURN,
        now=_NOW,
        audit=AsyncMock(),
    )

    assert phrase is None
    assert await _status(theirs) is CandidateStatus.OFFERED


async def test_an_answer_after_the_window_falls_through(owner: int) -> None:
    candidate_id = await _candidate(owner, offered=True)
    late = _NOW + timedelta(seconds=settings.memory_candidate_answer_seconds + 1)

    phrase = await answer_offer(
        MemoryAnswer(accept=True, phrase="el mate"),
        actor=_strong(owner),
        correlation_id=_TURN,
        now=late,
        audit=AsyncMock(),
    )

    assert phrase is None
    assert await _status(candidate_id) is CandidateStatus.OFFERED


async def test_the_switch_off_answers_nothing(owner: int, monkeypatch: pytest.MonkeyPatch) -> None:
    candidate_id = await _candidate(owner, offered=True)
    monkeypatch.setattr(settings, "memory_candidates_enabled", False)

    phrase = await answer_offer(
        MemoryAnswer(accept=True, phrase="el mate"),
        actor=_strong(owner),
        correlation_id=_TURN,
        now=_NOW,
        audit=AsyncMock(),
    )

    assert phrase is None
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    assert await _status(candidate_id) is CandidateStatus.OFFERED


async def test_a_failing_answer_says_it_could_not_save_and_never_logs_its_message(
    owner: int, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    await _candidate(owner, offered=True)
    monkeypatch.setattr(
        candidate_dialogue, "promote", AsyncMock(side_effect=RuntimeError("zumo de pomelo"))
    )

    with caplog.at_level(logging.DEBUG):
        phrase = await answer_offer(
            MemoryAnswer(accept=True, phrase="el mate"),
            actor=_strong(owner),
            correlation_id=_TURN,
            now=_NOW,
            audit=AsyncMock(),
        )

    assert phrase == ANSWER_FAILED_PHRASE
    assert not _leaked(caplog, "pomelo")
    assert "RuntimeError" in caplog.text


async def test_an_accept_the_writer_denies_says_it_could_not_save(owner: int) -> None:
    candidate_id = await _candidate(owner, offered=True)

    phrase = await answer_offer(
        MemoryAnswer(accept=True, phrase="el mate"),
        actor=_strong(owner),
        correlation_id=_TURN,
        now=_NOW + timedelta(seconds=10),
        audit=AsyncMock(side_effect=RuntimeError("audit down")),
    )

    assert phrase == ANSWER_FAILED_PHRASE
    assert await _status(candidate_id) is CandidateStatus.OFFERED
    assert await _likes(owner) == []


async def test_a_lookup_that_fails_before_the_offer_is_found_falls_through(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No oracle: until the verified owner's own offer is found nothing is said about it."""
    await _candidate(owner, offered=True)
    monkeypatch.setattr(candidate_dialogue, "find_offered", AsyncMock(side_effect=OSError("disk")))

    phrase = await answer_offer(
        MemoryAnswer(accept=True, phrase="el mate"),
        actor=_strong(owner),
        correlation_id=_TURN,
        now=_NOW,
        audit=AsyncMock(),
    )

    assert phrase is None


async def test_a_failure_names_the_turn_the_candidate_and_where_without_a_value(
    owner: int, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    candidate_id = await _candidate(owner, "el quokka", "quokka", offered=True)

    async def boom(*_args: object, **_kwargs: object) -> None:
        raise TypeError("el quokka")

    monkeypatch.setattr(candidate_dialogue, "promote", boom)

    with caplog.at_level(logging.DEBUG):
        await answer_offer(
            MemoryAnswer(accept=True, phrase="el quokka"),
            actor=_strong(owner),
            correlation_id=_TURN,
            now=_NOW,
            audit=AsyncMock(),
        )

    failures = [r for r in caplog.records if r.__dict__.get("event") == "candidate.answer_error"]
    assert len(failures) == 1
    record = failures[0]
    # A TypeError is a programming bug, not an operational failure: it is an ERROR with a site.
    assert record.levelno == logging.ERROR
    assert record.__dict__["correlation_id"] == str(_TURN)
    assert record.__dict__["candidate_id"] == candidate_id
    assert record.__dict__["site"].endswith(":boom")  # the innermost frame, never a message
    assert not _leaked(caplog, "quokka")


async def test_an_operational_failure_stays_a_warning(
    owner: int, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    await _candidate(owner, offered=True)
    monkeypatch.setattr(candidate_dialogue, "promote", AsyncMock(side_effect=OSError("disk")))

    with caplog.at_level(logging.DEBUG):
        await answer_offer(
            MemoryAnswer(accept=True, phrase="el mate"),
            actor=_strong(owner),
            correlation_id=_TURN,
            now=_NOW,
            audit=AsyncMock(),
        )

    failures = [r for r in caplog.records if r.__dict__.get("event") == "candidate.answer_error"]
    assert [r.levelno for r in failures] == [logging.WARNING]


async def test_no_log_line_carries_the_value(owner: int, caplog: pytest.LogCaptureFixture) -> None:
    candidate_id = await _candidate(owner, "el quokka", "quokka")

    with caplog.at_level(logging.DEBUG):
        offer = await prepare_offer(
            _actor(owner),
            wav_bytes=_WAV,
            event=_event(),
            verify=AsyncMock(return_value=_strong(owner)),
        )
        assert offer is not None
        await commit_offer(offer, now=_NOW, audit=AsyncMock())
        await answer_offer(
            MemoryAnswer(accept=True, phrase="el quokka"),
            actor=_strong(owner),
            correlation_id=_TURN,
            now=_NOW + timedelta(seconds=5),
            audit=AsyncMock(),
        )

    assert await _status(candidate_id) is CandidateStatus.CONFIRMED
    assert caplog.records
    assert not _leaked(caplog, "quokka")


async def test_the_offer_never_shows_in_the_repr_of_a_pending_offer(owner: int) -> None:
    pending = PendingOffer(
        candidate_id=1,
        subject_person_id=owner,
        phrase=compose_offer("likes", "el quokka"),
        actor=_strong(owner),
        correlation_id=_TURN,
    )

    assert "quokka" not in repr(pending)
    assert "Canary" not in repr(pending)
