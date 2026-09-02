"""Request/response contracts for the local owner unlock and face endpoints."""

from datetime import datetime
import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, SecretStr

__all__ = ["FaceEnrollResponse", "OwnerUnlockRequest", "OwnerUnlockResponse"]

# ASCII decimal digits only. `str.isdigit()` also accepts Arabic-Indic and other
# Unicode digits, which can never derive the stored verifier — accepting them
# would only spend a deliberately slow scrypt round on impossible input.
_PIN_PATTERN = re.compile(r"^[0-9]{6,12}$")


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
    if not _PIN_PATTERN.fullmatch(pin.get_secret_value()):
        raise ValueError("PIN must be 6 to 12 ASCII digits")
    return pin


class OwnerUnlockRequest(BaseModel):
    """Local owner unlock request — the PIN is never echoed or logged."""

    model_config = ConfigDict(extra="forbid")

    pin: Annotated[
        SecretStr,
        AfterValidator(_require_pin_shape),
        Field(description="Local owner PIN — 6 to 12 ASCII digits."),
    ]


class OwnerUnlockResponse(BaseModel):
    """Opaque one-use grant returned after a successful local unlock."""

    model_config = ConfigDict(extra="forbid")

    token: str
    expires_at: datetime


class FaceEnrollResponse(BaseModel):
    """Result of a successful authenticated owner face enrollment."""

    model_config = ConfigDict(extra="forbid")

    profile_id: int
    enrolled_at: datetime
