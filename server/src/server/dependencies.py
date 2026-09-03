"""Typed FastAPI dependencies for the HTTP boundary (Plan 0040).

`ResourcesDep` is re-exported from `resources.py` (Plan 0039) so routers
have one import for every dependency alias. `OwnerUnlockServiceDep` and
`IdentityTokenDep` are new: routers previously imported the
`owner_unlock_service` singleton directly and declared the identity header
as a plain `Header(...)` parameter, invisible to OpenAPI as a security
scheme. Neither changes wire behavior — the header stays optional and no
public endpoint requires it.
"""

from typing import Annotated

from fastapi import Depends, Security
from fastapi.security import APIKeyHeader

from server.cognition.owner_authentication import OwnerUnlockService
from server.resources import ResourcesDep

owner_identity_header = APIKeyHeader(
    name="X-Iroko-Identity-Token", auto_error=False, scheme_name="OwnerIdentityToken"
)


def get_owner_unlock_service(resources: ResourcesDep) -> OwnerUnlockService:
    """Return the lifespan-owned owner unlock service.

    Args:
        resources: The current app's lifespan-owned resources.

    Returns:
        The process-wide `OwnerUnlockService` instance.
    """
    return resources.owner_unlock_service


OwnerUnlockServiceDep = Annotated[OwnerUnlockService, Depends(get_owner_unlock_service)]
IdentityTokenDep = Annotated[str | None, Security(owner_identity_header)]

__all__ = ["IdentityTokenDep", "OwnerUnlockServiceDep", "ResourcesDep"]
