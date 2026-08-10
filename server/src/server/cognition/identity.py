"""Immutable identity contracts for active-person resolution."""

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

from server.cognition.models import Confidence

_StrictUUID = _Annotated[_UUID, _Field(strict=True)]
_StrictInteger = _Annotated[int, _Field(strict=True)]

__all__ = [
    "ActivePersonContext",
    "ActivePersonStatus",
    "HouseholdRole",
    "IdentityEvidence",
    "IdentityEvidenceSource",
]


class IdentityEvidenceSource(str, _Enum):  # noqa: UP042
    """Documented origin of identity evidence."""

    SESSION = "session"
    MANUAL = "manual"
    FACE = "face"
    VOICE = "voice"
    CONTEXT = "context"


class ActivePersonStatus(str, _Enum):  # noqa: UP042
    """Conservative outcome of active-person resolution."""

    IDENTIFIED = "identified"
    PROBABLE = "probable"
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"


class HouseholdRole(str, _Enum):  # noqa: UP042
    """Household role vocabulary without authorization semantics."""

    OWNER = "owner"
    ADULT = "adult"
    CHILD = "child"
    GUEST = "guest"
    UNKNOWN = "unknown"


def _require_aware_utc(value: _datetime) -> _datetime:
    """Reject naive timestamps and normalize aware timestamps to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(_UTC)


def _normalize_optional_aware_utc(value: _datetime | None) -> _datetime | None:
    """Preserve absent timestamps and normalize supplied values to UTC."""
    if value is None:
        return None
    return _require_aware_utc(value)


class IdentityEvidence(_BaseModel):
    """Immutable, safe evidence supporting an identity candidate."""

    model_config = _ConfigDict(frozen=True, extra="forbid")

    evidence_id: _StrictUUID
    source: IdentityEvidenceSource
    candidate_person_id: _StrictInteger | None
    confidence: Confidence
    observed_at: _datetime
    reference: str
    expires_at: _datetime | None = None

    _validate_observed_at = _field_validator("observed_at")(_require_aware_utc)
    _validate_expires_at = _field_validator("expires_at")(_normalize_optional_aware_utc)


class ActivePersonContext(_BaseModel):
    """Immutable active-person result for a single cognitive turn."""

    model_config = _ConfigDict(frozen=True, extra="forbid")

    person_id: _StrictInteger | None
    display_name: str | None
    status: ActivePersonStatus
    confidence: Confidence
    role: HouseholdRole
    evidence: tuple[IdentityEvidence, ...]
    resolved_at: _datetime

    _validate_resolved_at = _field_validator("resolved_at")(_require_aware_utc)
