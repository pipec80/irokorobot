"""The follow-up of a pending topic: who hears it, when, and the audit first (Plan 0084 Task 5).

D-8, D-9, D-10 and D-15. The store is a double; the policy is the real one. Canaries only.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import logging
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from server.cognition.authorization import AuthorizationRequest, ConsentStatus
from server.cognition.identity import (
    ActivePersonContext,
    HouseholdRole,
    IdentityEvidence,
    IdentityEvidenceSource,
    PersonRecord,
    resolve_active_person,
)
from server.cognition.models import (
    AuthorizationAction,
    AuthorizationDecision,
    AuthorizationStatus,
    Confidence,
    ConfidenceBasis,
)
from server.memory import pending_follow_up
from server.memory.continuity import ContinuityTurn
from server.memory.pending_follow_up import (
    PendingFollowUp,
    commit_follow_up,
    prepare_follow_up,
)
from server.memory.pending_store import PendingTopic
from server.schemas import ConversationTurn

pytestmark = pytest.mark.unit

_OWNER = 7
_TODAY = date(2026, 11, 12)
_NOW = datetime(2026, 11, 12, 15, tzinfo=UTC)
_CORRELATION = UUID(int=84)
_BANK = PendingTopic(
    id=3, topic="el banco", due_day=_TODAY - timedelta(days=1), sensitivity="normal"
)
_DOCTOR = PendingTopic(
    id=4, topic="el médico", due_day=_TODAY - timedelta(days=2), sensitivity="medical"
)
_NEW = ContinuityTurn((), _OWNER, 0)
_CONTINUED = ContinuityTurn(
    (
        ConversationTurn(role="user", content="hola"),
        ConversationTurn(role="assistant", content="Hola."),
    ),
    _OWNER,
    0,
)


def _actor(
    *sources: IdentityEvidenceSource, role: HouseholdRole = HouseholdRole.OWNER
) -> ActivePersonContext:
    person = PersonRecord(person_id=_OWNER, display_name="Canary", entity_type="person")
    evidence = tuple(
        IdentityEvidence(
            evidence_id=uuid4(),
            source=source,
            candidate_person_id=_OWNER,
            confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
            observed_at=_NOW - timedelta(seconds=1),
            reference="canary",
        )
        for source in sources
    )
    return resolve_active_person(
        evidence=evidence,
        lookup_person=lambda pid: person if pid == _OWNER else None,
        lookup_role=lambda _pid: role,
        clock=lambda: _NOW,
    )


class _Store:
    """The store's follow-up functions, patched into the module, sharing one call log."""

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        due: PendingTopic | None = _BANK,
        asked: bool = False,
        marked: bool = True,
    ) -> None:
        self.calls = Mock()
        self.due_topic = AsyncMock(return_value=due)
        self.asked_today = AsyncMock(return_value=asked)
        self.mark_asked = AsyncMock(return_value=marked)
        self.calls.attach_mock(self.mark_asked, "mark_asked")
        for name in ("due_topic", "asked_today", "mark_asked"):
            monkeypatch.setattr(pending_follow_up, name, getattr(self, name))


async def _prepare(
    actor: ActivePersonContext | None = None,
    session: ContinuityTurn = _NEW,
    *,
    alta: bool = True,
) -> PendingFollowUp | None:
    return await prepare_follow_up(
        actor or _actor(IdentityEvidenceSource.FACE),
        session,
        today=_TODAY,
        correlation_id=_CORRELATION,
        alta_closed=AsyncMock(return_value=alta),
    )


def _audited(audit: AsyncMock) -> tuple[AuthorizationRequest, AuthorizationDecision]:
    assert audit.await_args is not None
    request, decision = audit.await_args.args
    return request, decision


def _outcomes(caplog: pytest.LogCaptureFixture) -> list[object]:
    return [
        r.__dict__.get("outcome")
        for r in caplog.records
        if r.__dict__.get("event") == "pending.follow_up"
    ]


async def test_a_new_session_of_the_face_owner_is_asked_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    store = _Store(monkeypatch)
    audit = AsyncMock()
    store.calls.attach_mock(audit, "audit")

    prepared = await _prepare()
    assert prepared is not None
    assert prepared.sentence == "¿Cómo te fue ayer con el banco?"
    assert "banco" not in repr(prepared)
    spoken = await commit_follow_up(prepared, now=_NOW, audit=audit)

    assert spoken == "¿Cómo te fue ayer con el banco?"
    assert [name for name, _args, _kwargs in store.calls.mock_calls] == ["audit", "mark_asked"]
    store.mark_asked.assert_awaited_once_with(3, now=_NOW)
    request, decision = _audited(audit)
    assert request.action is AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY
    assert request.target_person_id == _OWNER
    assert {item.value for item in request.visibility} == {"personal"}
    assert {item.value for item in request.sensitivity} == {"normal"}
    assert request.consent is ConsentStatus.NOT_REQUIRED
    assert request.correlation_id == _CORRELATION
    assert decision.decision is AuthorizationStatus.ALLOWED
    assert _outcomes(caplog) == ["asked"]
    assert "banco" not in caplog.text
    assert "2026-11-11" not in caplog.text


async def test_a_continued_session_reads_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _Store(monkeypatch)
    assert await _prepare(session=_CONTINUED) is None
    store.asked_today.assert_not_awaited()
    store.due_topic.assert_not_awaited()


async def test_a_suspended_session_reads_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _Store(monkeypatch)
    assert await _prepare(session=ContinuityTurn((), None, 0)) is None
    store.due_topic.assert_not_awaited()


async def test_not_twice_the_same_day(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    store = _Store(monkeypatch, asked=True)
    assert await _prepare() is None
    store.due_topic.assert_not_awaited()
    assert _outcomes(caplog) == ["already_today"]


async def test_nothing_due_says_nothing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    _Store(monkeypatch, due=None)
    assert await _prepare() is None
    assert _outcomes(caplog) == ["none_due"]


@pytest.mark.parametrize(
    "actor",
    [
        _actor(IdentityEvidenceSource.MANUAL),
        _actor(IdentityEvidenceSource.LOCAL_UNLOCK),
        _actor(IdentityEvidenceSource.FACE, role=HouseholdRole.ADULT),
        _actor(),
    ],
    ids=["manual", "token", "another-adult", "unknown"],
)
async def test_only_the_face_identified_owner_is_ever_asked(
    monkeypatch: pytest.MonkeyPatch, actor: ActivePersonContext
) -> None:
    store = _Store(monkeypatch)
    assert await _prepare(actor) is None
    store.asked_today.assert_not_awaited()
    store.due_topic.assert_not_awaited()


async def test_a_medical_topic_needs_the_closed_alta(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    store = _Store(monkeypatch, due=_DOCTOR)
    audit = AsyncMock()

    open_alta = await _prepare(alta=False)
    assert open_alta is not None
    assert await commit_follow_up(open_alta, now=_NOW, audit=audit) is None
    store.mark_asked.assert_not_awaited()
    assert _audited(audit)[1].decision is AuthorizationStatus.DENIED
    assert _audited(audit)[0].consent is ConsentStatus.MISSING

    closed_alta = await _prepare(alta=True)
    assert closed_alta is not None
    assert await commit_follow_up(closed_alta, now=_NOW, audit=audit) == (
        "¿Cómo te fue anteayer con el médico?"
    )
    assert _audited(audit)[0].consent is ConsentStatus.GRANTED
    assert {item.value for item in _audited(audit)[0].sensitivity} == {"medical"}
    assert _outcomes(caplog) == ["denied", "asked"]


async def test_a_policy_refusal_says_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _Store(monkeypatch)
    prepared = await _prepare()
    assert prepared is not None
    refuse = Mock(
        return_value=Mock(spec=AuthorizationDecision, decision=AuthorizationStatus.DENIED)
    )

    assert await commit_follow_up(prepared, now=_NOW, policy=refuse, audit=AsyncMock()) is None
    store.mark_asked.assert_not_awaited()


async def test_a_failed_audit_says_nothing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    store = _Store(monkeypatch)
    prepared = await _prepare()
    assert prepared is not None

    audit = AsyncMock(side_effect=RuntimeError("zzauditzz banco"))
    assert await commit_follow_up(prepared, now=_NOW, audit=audit) is None

    store.mark_asked.assert_not_awaited()
    assert _outcomes(caplog) == ["audit_failed"]
    assert "zzauditzz" not in caplog.text


async def test_a_lost_compare_and_set_says_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    _Store(monkeypatch, marked=False)
    prepared = await _prepare()
    assert prepared is not None
    assert await commit_follow_up(prepared, now=_NOW, audit=AsyncMock()) is None


async def test_a_failing_store_read_prepares_nothing_and_never_raises(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    store = _Store(monkeypatch)
    store.due_topic.side_effect = RuntimeError("zzstorezz banco")

    assert await _prepare() is None
    assert "zzstorezz" not in caplog.text
