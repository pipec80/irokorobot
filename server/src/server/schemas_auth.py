"""Request/response contracts for the local owner unlock and face endpoints."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, SecretStr

from server.cognition.owner_authentication import OwnerUnlockScope
from server.cognition.pin_credentials import validate_pin

__all__ = [
    "FaceEnrollResponse",
    "OwnerUnlockRequest",
    "OwnerUnlockResponse",
    "VoiceEnrollResponse",
]


def _require_pin_shape(pin: SecretStr) -> SecretStr:
    """Reject a PIN whose shape could never match a stored credential.

    Pydantic cannot apply a `pattern` constraint to `SecretStr`, so the check
    reads the secret here and reports only the rule.

    Args:
        pin: Candidate PIN wrapped so it cannot be printed accidentally.

    Returns:
        The same value, unchanged, when it is 6 to 12 ASCII digits.

    Raises:
        ValueError: If the shape is wrong. The message never contains the
            candidate — it would otherwise be echoed in the 422 body.
    """
    validate_pin(pin.get_secret_value())
    return pin


class OwnerUnlockRequest(BaseModel):
    """Local owner unlock request — the PIN is never echoed or logged."""

    model_config = ConfigDict(extra="forbid")

    pin: Annotated[
        SecretStr,
        AfterValidator(_require_pin_shape),
        Field(description="Local owner PIN — 6 to 12 ASCII digits."),
    ]
    scope: Annotated[
        OwnerUnlockScope,
        Field(
            description=(
                "The one operation the grant may authorize: `personal_protected_read` "
                "(the default), `biometric_admin` (face or voice enrolment and revocation), "
                "`personal_memory_read` (read the owner's own conversation memory) or "
                "`personal_memory_forget` (one erasure of the owner's own memory)."
            )
        ),
    ] = OwnerUnlockScope.PERSONAL_PROTECTED_READ


class OwnerUnlockResponse(BaseModel):
    """Opaque one-use grant returned after a successful local unlock."""

    model_config = ConfigDict(extra="forbid")

    token: str
    expires_at: datetime
    scope: OwnerUnlockScope = Field(description="The operation this grant is bound to.")


class FaceEnrollResponse(BaseModel):
    """Result of a successful authenticated owner face enrollment."""

    model_config = ConfigDict(extra="forbid")

    profile_id: int
    enrolled_at: datetime


class VoiceEnrollResponse(BaseModel):
    """Result of a successful authenticated owner voiceprint enrollment."""

    model_config = ConfigDict(extra="forbid")

    profile_id: int
    enrolled_at: datetime
    reference_count: int
