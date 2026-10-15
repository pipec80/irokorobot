"""Unit tests for the candidate policy check (ADR 0021 decision 7): audit first, deny on doubt."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from server.cognition.authorization import (
    AuthorizationRequest,
    ConsentStatus,
    DataSensitivity,
    DataVisibility,
    evaluate_authorization,
)
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
    Confidence,
    ConfidenceBasis,
)
from server.memory.candidate_policy import CandidateStep, PolicyOutcome, authorize_step
from server.memory.candidate_types import CandidateReason
from server.settings import settings

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
_OWNER = 7
_CORRELATION = UUID(int=77)


def _evidence(source: IdentityEvidenceSource, *, scope: str | None = None) -> IdentityEvidence:
    return IdentityEvidence(
        evidence_id=uuid4(),
        source=source,
        candidate_person_id=_OWNER,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
        observed_at=_NOW - timedelta(seconds=1),
        reference="canary",
        expires_at=_NOW + timedelta(minutes=5) if scope else None,
        grant_scope=scope,
        grant_spent=bool(scope),
    )


def _actor(
    *sources: IdentityEvidenceSource, role: HouseholdRole = HouseholdRole.OWNER
) -> ActivePersonContext:
    person = PersonRecord(person_id=_OWNER, display_name="Canary", entity_type="person")
    return resolve_active_person(
        evidence=tuple(
            _evidence(s, scope="personal_protected_read")
            if s is IdentityEvidenceSource.LOCAL_UNLOCK
            else _evidence(s)
            for s in sources
        ),
        lookup_person=lambda pid: person if pid == _OWNER else None,
        lookup_role=lambda _pid: role,
        clock=lambda: _NOW,
    )


def _strong(role: HouseholdRole = HouseholdRole.OWNER) -> ActivePersonContext:
    return _actor(IdentityEvidenceSource.FACE, IdentityEvidenceSource.VOICE, role=role)


@pytest.fixture(autouse=True)
def _candidates_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "memory_candidates_enabled", True)


async def _authorize(
    step: CandidateStep,
    actor: ActivePersonContext,
    *,
    subject: int = _OWNER,
    audit: AsyncMock | None = None,
    policy: Mock | None = None,
) -> PolicyOutcome:
    return await authorize_step(
        step,
        actor=actor,
        subject_person_id=subject,
        correlation_id=_CORRELATION,
        now=_NOW,
        audit=audit or AsyncMock(),
        policy=policy or evaluate_authorization,
    )


@pytest.mark.parametrize(
    "step, action",
    [
        (CandidateStep.PROPOSE, AuthorizationAction.PROPOSE_PERSONAL_MEMORY),
        (CandidateStep.READ, AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY),
        (CandidateStep.CONFIRM, AuthorizationAction.CONFIRM_PERSONAL_MEMORY),
    ],
)
async def test_each_step_asks_its_own_action_about_the_subjects_ordinary_personal_data(
    step: CandidateStep, action: AuthorizationAction
) -> None:
    audit = AsyncMock()

    outcome = await _authorize(step, _strong(), audit=audit)

    assert outcome.allowed
    assert outcome.policy_id == "cm1.personal-memory.allowed"
    request, decision = audit.call_args.args
    assert isinstance(request, AuthorizationRequest)
    assert request.action is action
    assert request.target_person_id == _OWNER
    assert request.visibility == frozenset({DataVisibility.PERSONAL})
    assert request.sensitivity == frozenset({DataSensitivity.NORMAL})
    assert request.consent is ConsentStatus.NOT_REQUIRED
    assert request.correlation_id == _CORRELATION
    assert request.requested_at == _NOW
    assert decision.action is action


async def test_the_audit_row_is_written_before_the_step_is_reported_allowed() -> None:
    order: list[str] = []

    def policy(request: AuthorizationRequest) -> AuthorizationDecision:
        order.append("policy")
        return evaluate_authorization(request)

    async def audit(_request: AuthorizationRequest, _decision: AuthorizationDecision) -> None:
        order.append("audit")

    outcome = await authorize_step(
        CandidateStep.PROPOSE,
        actor=_strong(),
        subject_person_id=_OWNER,
        correlation_id=_CORRELATION,
        now=_NOW,
        policy=policy,
        audit=audit,
    )
    order.append("effect")

    assert outcome.allowed
    assert order == ["policy", "audit", "effect"]


@pytest.mark.parametrize("step", list(CandidateStep))
async def test_a_failing_audit_denies_the_step(
    step: CandidateStep, caplog: pytest.LogCaptureFixture
) -> None:
    audit = AsyncMock(side_effect=RuntimeError("disk full: zumo de pomelo"))

    with caplog.at_level("DEBUG"):
        outcome = await _authorize(step, _strong(), audit=audit)

    assert not outcome.allowed
    assert outcome.reason is CandidateReason.DENIED
    assert "pomelo" not in caplog.text


@pytest.mark.parametrize(
    "sources",
    [
        (IdentityEvidenceSource.FACE,),
        (IdentityEvidenceSource.LOCAL_UNLOCK,),
        (IdentityEvidenceSource.MANUAL,),
        (IdentityEvidenceSource.VOICE,),
        (
            IdentityEvidenceSource.FACE,
            IdentityEvidenceSource.VOICE,
            IdentityEvidenceSource.LOCAL_UNLOCK,
        ),
        (),
    ],
)
@pytest.mark.parametrize("step", list(CandidateStep))
async def test_only_the_face_and_voice_composite_passes_and_a_refusal_is_not_audited(
    step: CandidateStep, sources: tuple[IdentityEvidenceSource, ...]
) -> None:
    audit = AsyncMock()
    policy = Mock(side_effect=evaluate_authorization)

    outcome = await _authorize(step, _actor(*sources), audit=audit, policy=policy)

    assert not outcome.allowed
    assert outcome.reason is CandidateReason.STRONG_UNREACHABLE
    policy.assert_not_called()
    audit.assert_not_awaited()


async def test_another_persons_memory_is_denied_and_the_denial_is_audited() -> None:
    audit = AsyncMock()

    outcome = await _authorize(CandidateStep.PROPOSE, _strong(), subject=_OWNER + 1, audit=audit)

    assert not outcome.allowed
    assert outcome.policy_id == "cm1.personal-memory.own-data-only"
    audit.assert_awaited_once()
    assert audit.call_args.args[1].decision.value == "denied"


@pytest.mark.parametrize("role", [HouseholdRole.ADULT, HouseholdRole.CHILD, HouseholdRole.GUEST])
async def test_a_non_owner_is_denied_and_audited(role: HouseholdRole) -> None:
    audit = AsyncMock()

    outcome = await _authorize(CandidateStep.CONFIRM, _strong(role), audit=audit)

    assert not outcome.allowed
    assert outcome.policy_id == "cm1.personal-memory.owner-only"
    audit.assert_awaited_once()


@pytest.mark.parametrize("step", list(CandidateStep))
async def test_the_kill_switch_denies_every_step_before_anything_is_asked(
    step: CandidateStep, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
    audit = AsyncMock()
    policy = Mock(side_effect=evaluate_authorization)

    outcome = await _authorize(step, _strong(), audit=audit, policy=policy)

    assert not outcome.allowed
    policy.assert_not_called()
    audit.assert_not_awaited()
