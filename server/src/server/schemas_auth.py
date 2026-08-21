"""Request/response contracts for the local owner unlock endpoint."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, SecretStr

__all__ = ["OwnerUnlockRequest", "OwnerUnlockResponse"]


class OwnerUnlockRequest(BaseModel):
    """Local owner unlock request — the PIN is never echoed or logged."""

    model_config = ConfigDict(extra="forbid")

    pin: SecretStr


class OwnerUnlockResponse(BaseModel):
    """Opaque one-use grant returned after a successful local unlock."""

    model_config = ConfigDict(extra="forbid")

    token: str
    expires_at: datetime
