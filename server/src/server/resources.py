"""Lifespan-owned application resources (Plan 0039).

`AppResources` groups the process's outbound HTTP transport and the owner
unlock service behind one typed object stored on `app.state.resources`,
so routers depend on `Request`/`Depends`, never on an imported module
singleton or a per-call `httpx.AsyncClient()` construction.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
import httpx

from server.cognition.owner_authentication import OwnerUnlockService


@dataclass(slots=True)
class AppResources:
    """Long-lived resources owned by the app's lifespan, not by any request."""

    http_client: httpx.AsyncClient
    owner_unlock_service: OwnerUnlockService


def get_resources(request: Request) -> AppResources:
    """Return the resources the current app's lifespan constructed.

    Args:
        request: The current request, carrying the app instance.

    Returns:
        The lifespan-owned `AppResources`.
    """
    resources: AppResources = request.app.state.resources
    return resources


ResourcesDep = Annotated[AppResources, Depends(get_resources)]
