"""Authorize and audit a recall before any search (Plan 0078 Task 8, ADR 0028 decision 5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import httpx
import pytest
from server.cognition.authorization import evaluate_authorization
from server.cognition.identity import (
    ActivePersonContext,
    HouseholdRole,
    IdentityEvidence,
    IdentityEvidenceSource,
    PersonRecord,
    resolve_active_person,
)
from server.cognition.models import AuthorizationAction, Confidence, ConfidenceBasis
from server.cognition.recall_cues import CueStrength, RecallCue, WhenKind
from server.memory.recall_access import recall_reply
from server.memory.recall_answer import NO_MEMORY
from server.memory.recall_search import RecallHit, RecallSearch
from server.memory.recall_store import RecallUnit

if TYPE_CHECKING:
    from server.cognition.response_plan import RecallReply

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 11, 4, 15, tzinfo=UTC)
_OWNER = 7
_CANARY = "zzcanaryzz fuimos al cerro con Zeta"
_CUE = RecallCue(strength=CueStrength.STRONG, query="que del cerro", window=None)


def _actor(
    source: IdentityEvidenceSource = IdentityEvidenceSource.FACE,
    role: HouseholdRole = HouseholdRole.OWNER,
) -> ActivePersonContext:
    token = source is IdentityEvidenceSource.LOCAL_UNLOCK
    person = PersonRecord(person_id=_OWNER, display_name="Canary", entity_type="person")
    evidence = IdentityEvidence(
        evidence_id=uuid4(),
        source=source,
        candidate_person_id=_OWNER,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
        observed_at=_NOW - timedelta(seconds=1),
        reference="canary",
        expires_at=_NOW + timedelta(minutes=5) if token else None,
        grant_scope="personal_protected_read" if token else None,
        grant_spent=token,
    )
    return resolve_active_person(
        evidence=(evidence,),
        lookup_person=lambda pid: person if pid == _OWNER else None,
        lookup_role=lambda _pid: role,
        clock=lambda: _NOW,
    )


def _hit(distance: float | None = 0.1) -> RecallHit:
    unit = RecallUnit(
        id=1, record_id=1, kind="turn", body=_CANARY, said_at=_NOW - timedelta(days=1)
    )
    return RecallHit(unit=unit, distance=distance)


def _found(*hits: RecallHit, best: float | None = 0.1) -> AsyncMock:
    return AsyncMock(return_value=RecallSearch(hits=hits, best_distance=best, lexical_only=False))


async def _reply(
    actor: ActivePersonContext | None = None,
    *,
    cue: RecallCue = _CUE,
    search: AsyncMock | None = None,
    answer: AsyncMock | None = None,
    policy: Mock | None = None,
    audit: AsyncMock | None = None,
) -> RecallReply:
    return await recall_reply(
        actor or _actor(),
        cue,
        question="¿Qué te conté del cerro?",
        correlation_id=UUID(int=78),
        now=_NOW,
        client=httpx.AsyncClient(),
        search=search or _found(_hit()),
        answer=answer or AsyncMock(return_value="Ayer me contaste del cerro."),
        policy=policy or Mock(side_effect=evaluate_authorization),
        audit=audit or AsyncMock(),
    )


async def test_the_audit_row_is_written_before_any_search() -> None:
    order: list[str] = []
    audit = AsyncMock(side_effect=lambda *_: order.append("audit"))
    search = AsyncMock(
        side_effect=lambda *_a, **_k: (
            order.append("search")
            or RecallSearch(hits=(_hit(),), best_distance=0.1, lexical_only=False)
        )
    )

    reply = await _reply(search=search, audit=audit)

    assert order == ["audit", "search"]
    assert audit.await_args is not None
    request = audit.await_args.args[0]
    assert request.action is AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY
    assert {str(v) for v in request.visibility} == {"personal"}
    assert {str(s) for s in request.sensitivity} == {"normal"}
    assert reply.found
    assert reply.text == "Ayer me contaste del cerro."


async def test_a_denied_actor_triggers_no_search_and_no_embedding() -> None:
    """Review focus 4: nothing reads the diary before the policy allowed it."""
    search = _found(_hit())

    reply = await _reply(_actor(role=HouseholdRole.ADULT), search=search)

    search.assert_not_awaited()
    assert reply.denied


async def test_a_token_speaker_is_not_asked() -> None:
    policy, audit, search = Mock(), AsyncMock(), _found(_hit())

    reply = await _reply(
        _actor(IdentityEvidenceSource.LOCAL_UNLOCK), search=search, policy=policy, audit=audit
    )

    assert reply.denied
    policy.assert_not_called()
    audit.assert_not_awaited()
    search.assert_not_awaited()


async def test_a_failing_audit_means_no_search_and_no_memory() -> None:
    search = _found(_hit())

    reply = await _reply(search=search, audit=AsyncMock(side_effect=RuntimeError("db")))

    search.assert_not_awaited()
    assert reply.text == NO_MEMORY
    assert not reply.found


async def test_a_failing_search_is_no_memory() -> None:
    reply = await _reply(search=AsyncMock(side_effect=RuntimeError("db")))

    assert reply.text == NO_MEMORY


async def test_no_hits_is_nothing_found() -> None:
    answer = AsyncMock()

    reply = await _reply(search=_found(best=0.7), answer=answer)

    assert reply.text is None
    assert not reply.found
    answer.assert_not_awaited()


async def test_no_log_line_carries_a_body(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        await _reply(search=_found(_hit(0.1234567), best=0.1234567))

    messages = [record.getMessage() for record in caplog.records]
    assert all("zzcanaryzz" not in message and "Zeta" not in message for message in messages)
    assert all("cerro" not in message for message in messages)
    logged = [record for record in caplog.records if getattr(record, "event", "") == "recall.read"]
    assert len(logged) == 1
    assert logged[0].best_distance == 0.123  # type: ignore[attr-defined]  # a log extra
    assert logged[0].hits == 1  # type: ignore[attr-defined]  # a log extra
    assert logged[0].route == "strong"  # type: ignore[attr-defined]  # a log extra


def _when_cue(kind: WhenKind, strength: CueStrength = CueStrength.STRONG) -> RecallCue:
    return RecallCue(strength=strength, query="cuando fui a la playa", window=None, when=kind)


@pytest.mark.parametrize(
    "kind, expected",
    [
        (WhenKind.TOLD, "Ayer me contaste esto: zzcanaryzz fuimos al cerro con Zeta"),
        (
            WhenKind.HAPPENED,
            "No tengo registrado cuándo fue. Sí recuerdo que ayer me contaste esto: "
            "zzcanaryzz fuimos al cerro con Zeta",
        ),
    ],
)
async def test_a_when_cue_is_worded_without_the_model(kind: WhenKind, expected: str) -> None:
    answer = AsyncMock(return_value="the model must not be asked")

    reply = await _reply(cue=_when_cue(kind), answer=answer)

    answer.assert_not_awaited()
    assert reply.text == expected
    assert reply.found


@pytest.mark.parametrize("strength", list(CueStrength))
async def test_a_when_cue_that_finds_nothing_keeps_the_nothing_found_rule(
    strength: CueStrength,
) -> None:
    answer = AsyncMock()

    reply = await _reply(
        cue=_when_cue(WhenKind.HAPPENED, strength), search=_found(best=0.7), answer=answer
    )

    assert reply.text is None
    assert not reply.found
    answer.assert_not_awaited()


@pytest.mark.parametrize(
    "kind, logged", [(None, None), (WhenKind.TOLD, "told"), (WhenKind.HAPPENED, "happened")]
)
async def test_the_log_line_carries_the_closed_when_value(
    caplog: pytest.LogCaptureFixture, kind: WhenKind | None, logged: str | None
) -> None:
    cue = RecallCue(strength=CueStrength.STRONG, query="que del cerro", window=None, when=kind)

    with caplog.at_level(logging.DEBUG):
        await _reply(cue=cue)

    lines = [r for r in caplog.records if getattr(r, "event", "") == "recall.read"]
    assert len(lines) == 1
    assert lines[0].when == logged  # type: ignore[attr-defined]  # a log extra
    assert all("zzcanaryzz" not in record.getMessage() for record in caplog.records)
