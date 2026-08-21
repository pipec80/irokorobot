"""Loopback-only local owner PIN unlock endpoint.

Never trusts `X-Forwarded-For` or any other proxy header — the server does
not enable `proxy_headers`, and this route additionally checks the raw ASGI
connection origin before touching the unlock service.
"""

from fastapi import APIRouter, HTTPException, Request, status

from server.cognition.owner_authentication import (
    OwnerUnlockRateLimitedError,
    owner_unlock_service,
)
from server.schemas_auth import OwnerUnlockRequest, OwnerUnlockResponse

router = APIRouter(tags=["Auth"])

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})


def _is_loopback(request: Request) -> bool:
    """Return whether the raw ASGI connection originates from loopback."""
    client = request.client
    return client is not None and client.host in _LOOPBACK_HOSTS


@router.post("/auth/owner/unlock", response_model=OwnerUnlockResponse)
async def unlock_owner(request: OwnerUnlockRequest, http_request: Request) -> OwnerUnlockResponse:
    """Verify the local owner PIN and issue one opaque one-use grant.

    Args:
        request: The candidate PIN — never logged or echoed.
        http_request: Raw ASGI request used only to check loopback origin.

    Returns:
        The opaque token and its expiry on a successful local unlock.

    Raises:
        HTTPException: 403 for a non-loopback caller, 401 for a wrong PIN or
            missing/non-owner profile, 429 while the local rate limit blocks
            new attempts.
    """
    if not _is_loopback(http_request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Local access only")
    try:
        result = await owner_unlock_service.unlock(request.pin.get_secret_value())
    except OwnerUnlockRateLimitedError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many attempts"
        ) from exc
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Owner authentication failed"
        )
    return OwnerUnlockResponse(token=result.token, expires_at=result.expires_at)
