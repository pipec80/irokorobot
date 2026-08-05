"""Pure, immutable cognitive domain vocabulary."""

from datetime import UTC as _UTC, datetime as _datetime
from enum import Enum as _Enum
from typing import Annotated as _Annotated
from uuid import UUID as _UUID

from pydantic import (
    BaseModel as _BaseModel,
    ConfigDict as _ConfigDict,
    Field as _Field,
    field_validator as _field_validator,
)

_StrictUUID = _Annotated[_UUID, _Field(strict=True)]
_StrictInteger = _Annotated[int, _Field(strict=True)]

__all__ = [
    "ActiveContext",
    "AuthorizationDecision",
    "AuthorizationStatus",
    "CognitiveEvent",
    "Confidence",
    "ConfidenceBasis",
    "KnowledgeStatus",
    "Observation",
    "ObservationModality",
]


class KnowledgeStatus(str, _Enum):  # noqa: UP042
    """Categorical evidence outcome for a cognitive result."""

    KNOWN = "known"
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"
    CONTRADICTORY = "contradictory"
    UNAUTHORIZED = "unauthorized"


class ConfidenceBasis(str, _Enum):  # noqa: UP042
    """Origin category for a confidence score."""

    MEASURED = "measured"
    ESTIMATED = "estimated"
    ASSERTED = "asserted"
    NOT_APPLICABLE = "not_applicable"


class AuthorizationStatus(str, _Enum):  # noqa: UP042
    """Explicit policy result for an intended use."""

    ALLOWED = "allowed"
    DENIED = "denied"
    REQUIRES_CONFIRMATION = "requires_confirmation"


class ObservationModality(str, _Enum):  # noqa: UP042
    """Input modality of adapter evidence."""

    TEXT = "text"
    AUDIO = "audio"
    VISUAL = "visual"
    SENSOR = "sensor"
    SYSTEM = "system"


class Confidence(_BaseModel):
    """Evidence quality without authorization semantics."""

    model_config = _ConfigDict(frozen=True, extra="forbid")

    score: float = _Field(ge=0.0, le=1.0)
    basis: ConfidenceBasis
    calibrated: bool
    reason: str | None = None


def _require_aware_utc(value: _datetime) -> _datetime:
    """Reject naive timestamps and normalize aware timestamps to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(_UTC)


def _normalize_optional_aware_utc(value: _datetime | None) -> _datetime | None:
    """Preserve absent optional timestamps and normalize supplied values to UTC."""
    if value is None:
        return None
    return _require_aware_utc(value)


class AuthorizationDecision(_BaseModel):
    """Permission decision scoped to one action and data category set."""

    model_config = _ConfigDict(frozen=True, extra="forbid")

    decision: AuthorizationStatus
    action: str
    data_categories: frozenset[str]
    policy_id: str
    reason: str
    evaluated_at: _datetime

    _validate_evaluated_at = _field_validator("evaluated_at")(_require_aware_utc)


class Observation[PayloadT: _BaseModel](_BaseModel):
    """Immutable, timestamped adapter evidence."""

    model_config = _ConfigDict(frozen=True, extra="forbid")

    observation_id: _UUID
    schema_version: int = _Field(ge=1)
    source: str
    modality: ObservationModality
    captured_at: _datetime
    received_at: _datetime
    payload: PayloadT
    confidence: Confidence
    expires_at: _datetime | None = None

    _validate_captured_at = _field_validator("captured_at")(_require_aware_utc)
    _validate_received_at = _field_validator("received_at")(_require_aware_utc)
    _validate_expires_at = _field_validator("expires_at")(_normalize_optional_aware_utc)


class CognitiveEvent[PayloadT: _BaseModel](_BaseModel):
    """Immutable event envelope correlated across the cognitive flow."""

    model_config = _ConfigDict(frozen=True, extra="forbid")

    event_id: _UUID
    schema_version: int = _Field(ge=1)
    event_type: str
    occurred_at: _datetime
    recorded_at: _datetime
    source: str
    correlation_id: _UUID
    causation_id: _UUID | None
    subject_id: int | None
    payload: PayloadT

    _validate_occurred_at = _field_validator("occurred_at")(_require_aware_utc)
    _validate_recorded_at = _field_validator("recorded_at")(_require_aware_utc)


class ActiveContext(_BaseModel):
    """Immutable, authorized evidence snapshot for one cognitive turn."""

    model_config = _ConfigDict(frozen=True, extra="forbid")

    context_id: _StrictUUID
    conversation_id: str
    created_at: _datetime
    active_person_id: _StrictInteger | None
    observation_ids: tuple[_StrictUUID, ...]
    fact_ids: tuple[_StrictInteger, ...]
    knowledge_status: KnowledgeStatus
    confidence: Confidence
    authorization: AuthorizationDecision

    _validate_created_at = _field_validator("created_at")(_require_aware_utc)
