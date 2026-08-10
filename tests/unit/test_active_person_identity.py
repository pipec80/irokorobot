"""Contract tests for immutable active-person identity vocabulary."""

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

from pydantic import ValidationError
import pytest
from server.cognition import Confidence, ConfidenceBasis
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityEvidence,
    IdentityEvidenceSource,
)


def _confidence() -> Confidence:
    return Confidence(
        score=0.9,
        basis=ConfidenceBasis.ASSERTED,
        calibrated=True,
        reason="Explicit selection",
    )


def _evidence(*, expires_at: datetime | None = None) -> IdentityEvidence:
    return IdentityEvidence(
        evidence_id=uuid4(),
        source=IdentityEvidenceSource.MANUAL,
        candidate_person_id=42,
        confidence=_confidence(),
        observed_at=datetime(2026, 8, 10, 15, 30, tzinfo=UTC),
        reference="operator-selection:42",
        expires_at=expires_at,
    )


def test_identity_contract_enums_expose_documented_values() -> None:
    """Reject a vocabulary change that makes valid identity evidence ambiguous."""
    assert {source.value for source in IdentityEvidenceSource} == {
        "session",
        "manual",
        "face",
        "voice",
        "context",
    }
    assert {status.value for status in ActivePersonStatus} == {
        "identified",
        "probable",
        "unknown",
        "ambiguous",
    }
    assert {role.value for role in HouseholdRole} == {
        "owner",
        "adult",
        "child",
        "guest",
        "unknown",
    }


def test_identity_evidence_preserves_manual_selection_contract() -> None:
    """Reject a manual selection that loses its immutable typed evidence."""
    evidence = _evidence(expires_at=datetime(2026, 8, 10, 16, 30, tzinfo=UTC) + timedelta(hours=3))

    assert evidence.candidate_person_id == 42
    assert evidence.source is IdentityEvidenceSource.MANUAL
    assert evidence.observed_at == datetime(2026, 8, 10, 15, 30, tzinfo=UTC)
    assert evidence.expires_at == datetime(2026, 8, 10, 19, 30, tzinfo=UTC)
    with pytest.raises(ValidationError):
        evidence.candidate_person_id = 7


@pytest.mark.parametrize("invalid_person_id", ["42", True, 42.0])
def test_identity_evidence_rejects_non_strict_person_ids(
    invalid_person_id: object,
) -> None:
    """Reject coercion that could turn an external value into an entity ID."""
    payload = _evidence().model_dump()
    payload["candidate_person_id"] = invalid_person_id

    with pytest.raises(ValidationError):
        IdentityEvidence.model_validate(payload)


def test_identity_evidence_normalizes_aware_timestamps_and_requires_uuid() -> None:
    """Reject evidence that can lose its UTC ordering or opaque identifier."""
    utc_minus_four = timezone(timedelta(hours=-4))
    evidence = _evidence(expires_at=datetime(2026, 8, 10, 16, 30, tzinfo=utc_minus_four))
    payload = evidence.model_dump()
    payload["observed_at"] = datetime(2026, 8, 10, 15, 30, tzinfo=utc_minus_four)
    normalized = IdentityEvidence.model_validate(payload)

    assert evidence.expires_at == datetime(2026, 8, 10, 20, 30, tzinfo=UTC)
    assert normalized.observed_at == datetime(2026, 8, 10, 19, 30, tzinfo=UTC)
    with pytest.raises(ValidationError):
        IdentityEvidence.model_validate({**payload, "evidence_id": "not-a-uuid"})


@pytest.mark.parametrize(
    "expires_at",
    [
        datetime(2026, 8, 10, 15, 29, tzinfo=UTC),
        datetime(2026, 8, 10, 15, 30, tzinfo=UTC),
    ],
)
def test_identity_evidence_rejects_expiry_not_after_observation(
    expires_at: datetime,
) -> None:
    """Reject evidence whose expiry cannot be later than its observation."""
    with pytest.raises(ValidationError, match="expires_at must be after observed_at"):
        _evidence(expires_at=expires_at)


def test_identity_evidence_rejects_naive_datetimes_and_extra_fields() -> None:
    """Reject timestamps and fields that are unsafe for identity evidence."""
    payload = _evidence().model_dump()
    payload["observed_at"] = datetime(2026, 8, 10, 15, 30)

    with pytest.raises(ValidationError, match="timezone-aware"):
        IdentityEvidence.model_validate(payload)

    with pytest.raises(ValidationError):
        IdentityEvidence.model_validate({**_evidence().model_dump(), "raw_voice": "x"})


def test_active_person_context_is_immutable_utc_and_json_round_trips() -> None:
    """Reject a context that loses its typed identity evidence across JSON."""
    evidence = _evidence()
    context = ActivePersonContext(
        person_id=42,
        display_name="Ada",
        status=ActivePersonStatus.IDENTIFIED,
        confidence=_confidence(),
        role=HouseholdRole.UNKNOWN,
        evidence=(evidence,),
        resolved_at=datetime(2026, 8, 10, 12, 30, tzinfo=UTC),
    )

    restored = ActivePersonContext.model_validate_json(context.model_dump_json())

    assert restored == context
    assert isinstance(restored.evidence[0].evidence_id, UUID)
    with pytest.raises(ValidationError):
        context.person_id = 7
    with pytest.raises(ValidationError, match="timezone-aware"):
        ActivePersonContext(
            person_id=None,
            display_name=None,
            status=ActivePersonStatus.UNKNOWN,
            confidence=_confidence(),
            role=HouseholdRole.UNKNOWN,
            evidence=(),
            resolved_at=datetime(2026, 8, 10, 12, 30),
        )
