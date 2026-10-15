"""Integration tests for the canonical writer (ADR 0021 decision 8) over a temporary SQLite."""

from __future__ import annotations

import asyncio
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
from server.cognition.models import Confidence, ConfidenceBasis
from server.exceptions import BrainMemoryError
from server.memory import candidates, memory_writer
from server.memory.biometric_consent import grant_face_consent
from server.memory.candidate_policy import CandidateStep
from server.memory.candidate_types import (
    CandidateChannel,
    CandidateReason,
    CandidateStatus,
    ProposedCandidate,
)
from server.memory.candidates import iso_utc
from server.memory.declarative import upsert_entity
from server.memory.memory_writer import PromotionOutcome, promote
from server.memory.predicate_registry import PredicateDefinition, resolve_predicate
from server.memory.relational_v4 import (
    AssertionLifecycle,
    assert_literal_fact,
    get_active_literal_facts,
    get_literal_fact,
)
from server.settings import settings

from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable
    from pathlib import Path

    from server.memory.relational_v4 import LiteralFactV4

pytestmark = pytest.mark.integration

_T0 = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
_ANSWER = _T0 + timedelta(seconds=20)
# `db.transaction()` is not reentrant and the suite has no pytest timeout: a nested transaction
# or a checkpoint inside one would hang the run instead of failing it. Every write is bounded.
_TIMEOUT_S = 5
_CANARY = "quokka cuantico"


async def _bounded[T](awaitable: Awaitable[T]) -> T:
    """Fail with ``TimeoutError`` instead of hanging when a write waits on itself."""
    return await asyncio.wait_for(awaitable, timeout=_TIMEOUT_S)


def _events(caplog: pytest.LogCaptureFixture, event: str) -> list[logging.LogRecord]:
    """Return the captured records that carry the structured *event*."""
    return [record for record in caplog.records if getattr(record, "event", None) == event]


def _extra(record: logging.LogRecord, name: str) -> object:
    """Read one structured ``extra`` field of a captured log record."""
    return getattr(record, name)


def _file_bytes(db_path: Path) -> bytes:
    """Concatenate the database file and its write-ahead log, as an attacker would read them."""
    pieces = [db_path.read_bytes()]
    wal = db_path.with_name(db_path.name + "-wal")
    if wal.exists():
        pieces.append(wal.read_bytes())
    return b"".join(pieces)


def _evidence(source: IdentityEvidenceSource, person_id: int) -> IdentityEvidence:
    return IdentityEvidence(
        evidence_id=uuid4(),
        source=source,
        candidate_person_id=person_id,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
        observed_at=_T0,
        reference="canary",
    )


def _actor(person_id: int, *sources: IdentityEvidenceSource) -> ActivePersonContext:
    sources = sources or (IdentityEvidenceSource.FACE, IdentityEvidenceSource.VOICE)
    person = PersonRecord(person_id=person_id, display_name="Canary", entity_type="person")
    return resolve_active_person(
        evidence=tuple(_evidence(s, person_id) for s in sources),
        lookup_person=lambda pid: person if pid == person_id else None,
        lookup_role=lambda _pid: HouseholdRole.OWNER,
        clock=lambda: _T0,
    )


@pytest.fixture
async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "writer.db")
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    owner_id = await upsert_entity(name="Canary Owner", type="person")
    await grant_face_consent(owner_id)
    yield owner_id
    await db.close_db()
    db._conn = None


def _definition(name: str) -> PredicateDefinition:
    definition = resolve_predicate(name)
    assert definition is not None
    return definition


async def _offered(
    owner_id: int,
    value: str = "el mate",
    key: str = "mate",
    predicate: str = "likes",
    *,
    subject: int | None = None,
) -> int:
    """Store a candidate and move it to `offered`."""
    subject_id = subject or owner_id
    stored = await _bounded(
        candidates.insert_candidate(
            ProposedCandidate(predicate=predicate, value_text=value, value_key=key),
            subject_person_id=subject_id,
            asserted_by_person_id=subject_id,
            channel=CandidateChannel.VOICE_CLASSIC,
            correlation_id=uuid4(),
            now=_T0,
        )
    )
    assert stored.candidate_id is not None
    assert await _bounded(
        candidates.mark_offered(stored.candidate_id, subject_id, correlation_id=uuid4(), now=_T0)
    )
    return stored.candidate_id


async def _promote(
    candidate_id: int,
    actor: ActivePersonContext,
    *,
    audit: AsyncMock | None = None,
    now: datetime = _ANSWER,
    correlation: UUID | None = None,
) -> memory_writer.PromotionResult:
    return await _bounded(
        promote(
            candidate_id,
            actor=actor,
            correlation_id=correlation or uuid4(),
            now=now,
            audit=audit or AsyncMock(),
        )
    )


async def _facts(owner_id: int, predicate: str = "likes") -> list[str]:
    return [
        fact.value_text
        for fact in await get_active_literal_facts(
            subject_entity_id=owner_id, definition=_definition(predicate)
        )
    ]


async def _fact(owner_id: int, predicate: str, value: str) -> LiteralFactV4:
    """Store an already-confirmed fact the way the legacy path would."""
    return await _bounded(
        assert_literal_fact(
            subject_entity_id=owner_id, definition=_definition(predicate), value=value
        )
    )


async def test_an_offered_candidate_becomes_one_personal_confirmed_fact(owner: int) -> None:
    candidate_id = await _offered(owner, "el mate", "mate")
    answer = uuid4()

    result = await _promote(candidate_id, _actor(owner), correlation=answer)

    assert result.outcome is PromotionOutcome.PROMOTED
    assert result.fact_id is not None
    fact = await get_literal_fact(result.fact_id)
    assert fact is not None
    assert (fact.subject_entity_id, fact.predicate, fact.value_text) == (owner, "likes", "el mate")
    assert (fact.visibility, fact.sensitivity) == ("personal", "normal")
    assert fact.confidence == 1.0
    assert fact.lifecycle is AssertionLifecycle.ACTIVE
    assert fact.source_memory_id is None
    assert fact.confirmed_by_entity_id == owner
    assert fact.confirmed_at == iso_utc(_ANSWER)
    assert fact.asserted_at == iso_utc(_T0)
    candidate = await candidates.get_candidate(candidate_id)
    assert candidate is not None
    assert candidate.status is CandidateStatus.CONFIRMED
    assert candidate.promoted_fact_id == fact.id
    assert candidate.resolution_correlation_id == str(answer)
    assert (candidate.value_text, candidate.value_key) == (None, None)


async def test_the_registry_default_that_the_household_reader_relies_on_does_not_move(
    owner: int,
) -> None:
    likes = _definition("likes")
    before = (likes.default_visibility, likes.default_sensitivity)

    await _promote(await _offered(owner), _actor(owner))

    after = _definition("likes")
    assert (
        (after.default_visibility, after.default_sensitivity) == before == ("household", "normal")
    )


async def test_the_confirmation_is_audited_before_the_write(owner: int) -> None:
    candidate_id = await _offered(owner)
    seen_facts: list[int] = []

    async def audit(*_args: object) -> None:
        seen_facts.append(len(await _facts(owner)))

    result = await _bounded(
        promote(candidate_id, actor=_actor(owner), correlation_id=uuid4(), now=_ANSWER, audit=audit)
    )

    assert result.outcome is PromotionOutcome.PROMOTED
    assert seen_facts == [0]
    assert await _facts(owner) == ["el mate"]


async def test_the_real_audit_row_names_the_action_and_carries_no_value(owner: int) -> None:
    candidate_id = await _offered(owner, "el zumo de pomelo", "zumo de pomelo")
    answer = uuid4()

    result = await _bounded(
        promote(candidate_id, actor=_actor(owner), correlation_id=answer, now=_ANSWER)
    )

    assert result.outcome is PromotionOutcome.PROMOTED
    cursor = await db.get_conn().execute(
        "SELECT action, decision, policy_id, data_categories, actor_entity_id, target_entity_id, "
        "reason FROM authorization_audit_events WHERE correlation_id = ?",
        (str(answer),),
    )
    rows = list(await cursor.fetchall())
    await cursor.close()
    assert len(rows) == 1
    action, decision, policy_id, categories, actor_id, target_id, reason = rows[0]
    assert (action, decision, policy_id) == (
        "confirm_personal_memory",
        "allowed",
        "cm1.personal-memory.allowed",
    )
    assert categories == "normal,personal"
    assert (actor_id, target_id) == (owner, owner)
    assert "pomelo" not in reason


async def test_a_duplicate_is_the_result_not_an_error(owner: int) -> None:
    existing = await _fact(owner, "likes", "El Mate")
    candidate_id = await _offered(owner, "el mate", "mate")

    result = await _promote(candidate_id, _actor(owner))

    assert result.outcome is PromotionOutcome.ALREADY_PRESENT
    assert result.fact_id == existing.id
    assert await _facts(owner) == ["El Mate"]
    candidate = await candidates.get_candidate(candidate_id)
    assert candidate is not None
    assert candidate.status is CandidateStatus.CONFIRMED
    assert candidate.promoted_fact_id == existing.id


async def test_an_exact_duplicate_does_not_reach_the_unique_index(owner: int) -> None:
    await _fact(owner, "likes", "el mate")

    result = await _promote(await _offered(owner, "el mate", "mate"), _actor(owner))

    assert result.outcome is PromotionOutcome.ALREADY_PRESENT


@pytest.mark.parametrize(
    "fact_predicate, candidate_predicate, fact_text",
    [("likes", "dislikes", "El Máte"), ("dislikes", "likes", "EL MATE")],
)
async def test_the_opposite_polarity_is_a_contradiction_in_both_directions_and_folded(
    owner: int, fact_predicate: str, candidate_predicate: str, fact_text: str
) -> None:
    fact = await _fact(owner, fact_predicate, fact_text)
    candidate_id = await _offered(owner, "el mate", "mate", candidate_predicate)

    result = await _promote(candidate_id, _actor(owner))

    assert result.outcome is PromotionOutcome.CONTRADICTION
    assert result.fact_id is None
    assert await _facts(owner, candidate_predicate) == []
    assert await _facts(owner, fact_predicate) == [fact_text]
    stored = await get_literal_fact(fact.id)
    assert stored is not None
    assert stored.lifecycle is AssertionLifecycle.ACTIVE
    candidate = await candidates.get_candidate(candidate_id)
    assert candidate is not None
    assert candidate.status is CandidateStatus.REJECTED
    assert (candidate.value_text, candidate.value_key) == (None, None)


async def test_a_contradiction_scrubs_the_value_from_the_file_and_its_log(owner: int) -> None:
    await _fact(owner, "dislikes", "Quokka Cuántico")  # folds to the candidate's key
    candidate_id = await _offered(owner, f"el {_CANARY}", _CANARY, "likes")
    db_path = settings.brain_db_path
    assert f"el {_CANARY}".encode() in _file_bytes(db_path)  # the check is not vacuous

    result = await _promote(candidate_id, _actor(owner))

    assert result.outcome is PromotionOutcome.CONTRADICTION
    assert f"el {_CANARY}".encode() not in _file_bytes(db_path)
    assert _CANARY.encode() not in _file_bytes(db_path.with_name(db_path.name + "-wal"))


async def test_a_prefers_candidate_has_no_opposite(owner: int) -> None:
    await _fact(owner, "dislikes", "el mate")

    result = await _promote(await _offered(owner, "el mate", "mate", "prefers"), _actor(owner))

    assert result.outcome is PromotionOutcome.PROMOTED
    assert await _facts(owner, "prefers") == ["el mate"]


@pytest.mark.parametrize("state", ["proposed", "expired", "resolved"])
async def test_only_an_unexpired_offered_candidate_is_promoted(owner: int, state: str) -> None:
    stored = await _bounded(
        candidates.insert_candidate(
            ProposedCandidate(predicate="likes", value_text="el mate", value_key="mate"),
            subject_person_id=owner,
            asserted_by_person_id=owner,
            channel=CandidateChannel.VOICE_STREAM,
            correlation_id=uuid4(),
            now=_T0,
        )
    )
    assert stored.candidate_id is not None
    now = _ANSWER
    if state in {"expired", "resolved"}:
        await _bounded(
            candidates.mark_offered(stored.candidate_id, owner, correlation_id=uuid4(), now=_T0)
        )
    if state == "resolved":
        await _bounded(
            candidates.resolve_candidate(
                stored.candidate_id,
                owner,
                to=CandidateStatus.REJECTED,
                correlation_id=uuid4(),
                now=_T0,
            )
        )
    if state == "expired":
        now = _T0 + timedelta(seconds=settings.memory_candidate_ttl_seconds)

    result = await _promote(stored.candidate_id, _actor(owner), now=now)

    assert result.outcome is PromotionOutcome.NOT_OFFERED
    assert await _facts(owner) == []


async def test_a_second_promotion_of_the_same_candidate_writes_nothing(owner: int) -> None:
    candidate_id = await _offered(owner)
    first = await _promote(candidate_id, _actor(owner))

    second = await _promote(candidate_id, _actor(owner))

    assert first.outcome is PromotionOutcome.PROMOTED
    assert second.outcome is PromotionOutcome.NOT_OFFERED
    assert await _facts(owner) == ["el mate"]


async def test_two_confirmations_at_once_promote_exactly_one_fact(owner: int) -> None:
    candidate_id = await _offered(owner)

    results = await asyncio.gather(
        _promote(candidate_id, _actor(owner)), _promote(candidate_id, _actor(owner))
    )

    assert sorted(r.outcome.value for r in results) == ["not_offered", "promoted"]
    assert await _facts(owner) == ["el mate"]


async def test_the_candidate_is_found_by_the_actors_id_never_by_one_the_request_carries(
    owner: int,
) -> None:
    other = await upsert_entity(name="Canary Visitor", type="person")
    theirs = await _offered(owner, subject=other, value="el jazz", key="jazz")

    result = await _promote(theirs, _actor(owner))

    assert result.outcome is PromotionOutcome.NOT_OFFERED
    assert await _facts(owner) == []
    assert await _facts(other) == []
    candidate = await candidates.get_candidate(theirs)
    assert candidate is not None
    assert candidate.status is CandidateStatus.OFFERED


@pytest.mark.parametrize(
    "sources",
    [
        (IdentityEvidenceSource.FACE,),
        (IdentityEvidenceSource.LOCAL_UNLOCK,),
        (IdentityEvidenceSource.MANUAL,),
        (),
    ],
)
async def test_a_weaker_actor_promotes_nothing_and_leaves_the_candidate_offered(
    owner: int,
    sources: tuple[IdentityEvidenceSource, ...],
    caplog: pytest.LogCaptureFixture,
) -> None:
    candidate_id = await _offered(owner, f"el {_CANARY}", _CANARY)
    audit = AsyncMock()
    actor = _actor(owner, *sources) if sources else _actor(owner, IdentityEvidenceSource.VOICE)

    with caplog.at_level(logging.DEBUG):
        result = await _promote(candidate_id, actor, audit=audit)

    assert result.outcome is PromotionOutcome.DENIED
    assert await _facts(owner) == []
    audit.assert_not_awaited()
    candidate = await candidates.get_candidate(candidate_id)
    assert candidate is not None
    assert candidate.status is CandidateStatus.OFFERED
    assert candidate.value_text == f"el {_CANARY}"
    # The refusal is not silent: one closed-reason line, and no value in it.
    (refusal,) = _events(caplog, "candidate.policy")
    assert (_extra(refusal, "step"), _extra(refusal, "reason")) == (
        CandidateStep.CONFIRM,
        CandidateReason.STRONG_UNREACHABLE,
    )
    assert _CANARY not in caplog.text


async def test_a_failing_audit_promotes_nothing(
    owner: int, caplog: pytest.LogCaptureFixture
) -> None:
    candidate_id = await _offered(owner, f"el {_CANARY}", _CANARY)

    with caplog.at_level(logging.DEBUG):
        result = await _promote(
            candidate_id, _actor(owner), audit=AsyncMock(side_effect=RuntimeError(_CANARY))
        )

    assert result.outcome is PromotionOutcome.DENIED
    assert await _facts(owner) == []
    candidate = await candidates.get_candidate(candidate_id)
    assert candidate is not None
    assert candidate.status is CandidateStatus.OFFERED
    (refusal,) = _events(caplog, "candidate.policy")
    assert _extra(refusal, "reason") is CandidateReason.DENIED
    assert _CANARY not in caplog.text  # the exception class is logged, never its message


async def test_the_kill_switch_stops_promotion_and_says_so(
    owner: int, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    candidate_id = await _offered(owner, f"el {_CANARY}", _CANARY)
    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
    audit = AsyncMock()

    with caplog.at_level(logging.DEBUG):
        result = await _promote(candidate_id, _actor(owner), audit=audit)

    assert result.outcome is PromotionOutcome.DENIED
    assert await _facts(owner) == []
    audit.assert_not_awaited()
    (refusal,) = _events(caplog, "candidate.policy")
    assert (_extra(refusal, "step"), _extra(refusal, "reason")) == (
        CandidateStep.CONFIRM,
        CandidateReason.DENIED,
    )
    assert _CANARY not in caplog.text


async def test_an_actor_without_a_person_is_denied_with_one_closed_reason_line(
    owner: int, caplog: pytest.LogCaptureFixture
) -> None:
    candidate_id = await _offered(owner, f"el {_CANARY}", _CANARY)
    nobody = resolve_active_person(
        evidence=(),
        lookup_person=lambda _pid: None,
        lookup_role=lambda _pid: HouseholdRole.OWNER,
        clock=lambda: _T0,
    )
    assert nobody.person_id is None
    audit = AsyncMock()
    answer = uuid4()

    with caplog.at_level(logging.DEBUG):
        result = await _promote(candidate_id, nobody, audit=audit, correlation=answer)

    assert result.outcome is PromotionOutcome.DENIED
    audit.assert_not_awaited()
    (line,) = _events(caplog, "candidate.promotion")
    assert _extra(line, "outcome") is PromotionOutcome.DENIED
    assert _extra(line, "reason") is CandidateReason.STRONG_UNREACHABLE
    assert _extra(line, "correlation_id") == str(answer)
    assert _CANARY not in caplog.text
    candidate = await candidates.get_candidate(candidate_id)
    assert candidate is not None
    assert candidate.status is CandidateStatus.OFFERED


async def test_the_promotion_line_carries_the_confirming_turns_correlation_id(
    owner: int, caplog: pytest.LogCaptureFixture
) -> None:
    candidate_id = await _offered(owner, f"el {_CANARY}", _CANARY)
    answer = uuid4()

    with caplog.at_level(logging.DEBUG):
        result = await _promote(candidate_id, _actor(owner), correlation=answer)

    assert result.outcome is PromotionOutcome.PROMOTED
    (line,) = _events(caplog, "candidate.promotion")
    assert _extra(line, "outcome") is PromotionOutcome.PROMOTED
    assert _extra(line, "correlation_id") == str(answer)
    assert (_extra(line, "candidate_id"), _extra(line, "fact_id")) == (candidate_id, result.fact_id)
    assert _CANARY not in caplog.text


async def test_a_normal_promotion_completes_inside_the_time_bound(owner: int) -> None:
    """A nested transaction or a checkpoint inside one would wait on itself forever."""
    candidate_id = await _offered(owner)

    result = await asyncio.wait_for(
        promote(
            candidate_id,
            actor=_actor(owner),
            correlation_id=uuid4(),
            now=_ANSWER,
            audit=AsyncMock(),
        ),
        _TIMEOUT_S,
    )

    assert result.outcome is PromotionOutcome.PROMOTED


@pytest.mark.parametrize(
    "seam, raised",
    [
        ("assert_literal_fact", ValueError("not a literal")),
        ("get_active_literal_facts", BrainMemoryError("db unavailable")),
        ("resolve_candidate_in_transaction", None),
    ],
)
async def test_the_failures_that_escape_roll_the_transaction_back(
    owner: int, monkeypatch: pytest.MonkeyPatch, seam: str, raised: Exception | None
) -> None:
    """The documented ``Raises``: ValueError, BrainMemoryError, and RuntimeError for a lost CAS."""
    candidate_id = await _offered(owner)

    async def failing(*_args: object, **_kwargs: object) -> bool:
        if raised is not None:
            raise raised
        return False  # the compare-and-set lost inside the transaction

    monkeypatch.setattr(memory_writer, seam, failing)

    expected = type(raised) if raised is not None else RuntimeError
    with pytest.raises(expected):
        await _promote(candidate_id, _actor(owner))

    assert await _facts(owner) == []
    candidate = await candidates.get_candidate(candidate_id)
    assert candidate is not None
    assert candidate.status is CandidateStatus.OFFERED
    assert candidate.value_text == "el mate"


async def test_a_failure_inside_the_transaction_rolls_back_fact_and_resolution(
    owner: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate_id = await _offered(owner)
    real = memory_writer.assert_literal_fact
    calls: list[bool] = []

    async def failing(**kwargs: object) -> object:
        calls.append(bool(kwargs["manage_transaction"]))
        await real(**kwargs)  # type: ignore[arg-type]  # the wrapper forwards typed keywords as `object`
        raise RuntimeError("boom after the insert")

    monkeypatch.setattr(memory_writer, "assert_literal_fact", failing)

    with pytest.raises(RuntimeError, match="boom"):
        await _promote(candidate_id, _actor(owner))

    assert calls == [False]  # it joined the writer's transaction, it did not open its own
    assert await _facts(owner) == []
    candidate = await candidates.get_candidate(candidate_id)
    assert candidate is not None
    assert candidate.status is CandidateStatus.OFFERED
    assert candidate.value_text == "el mate"


async def test_a_postponed_checkpoint_does_not_turn_a_committed_promotion_into_a_failure(
    owner: int,
) -> None:
    candidate_id = await _offered(owner)
    # Many rows and one fetch: the statement stays active, as a coroutine between an execute
    # and its fetchall would leave it.
    cursor = await db.get_conn().execute("SELECT * FROM sqlite_master")
    await cursor.fetchone()

    result = await _promote(candidate_id, _actor(owner))
    await cursor.close()

    assert result.outcome is PromotionOutcome.PROMOTED
    assert await _facts(owner) == ["el mate"]


async def test_promoting_a_missing_candidate_is_not_offered_and_writes_nothing(
    owner: int,
) -> None:
    """The caller is Plan 0063's answer branch, after an answer matched an offer: the audit row
    is written first by design, so a speculative call would leave a trace and must not happen."""
    result = await _promote(987654, _actor(owner))

    assert result.outcome is PromotionOutcome.NOT_OFFERED
    assert await _facts(owner) == []
