"""The offline owner-PIN check for the local administration (Plan 0073, ADR 0025 decision 4).

A sensitive admin edit (medical, location or security data, a contact, or anyone but the owner)
needs the owner's verification at that moment, with the server stopped. This reuses the single
cryptographic verifier (`cognition.pin_credentials.verify_pin`) over the active owner credential,
so nothing about the PIN is re-implemented: the hash check lives in one place. The command keeps
its own attempt counter; this is a pure yes/no against the stored credential. The PIN never
reaches a log or the error.
"""

from __future__ import annotations

import logging

from server.cognition.pin_credentials import verify_pin
from server.exceptions import AdminPinError
from server.memory.owner_credentials import get_active_owner_pin_credential

__all__ = ["verify_owner_pin"]

logger = logging.getLogger(__name__)

_EVENT = "memory.admin_pin"


async def verify_owner_pin(pin: str) -> None:
    """Verify a candidate PIN against the active owner credential, or raise.

    Args:
        pin: The candidate PIN typed by the operator.

    Raises:
        AdminPinError: If there is no active owner credential, the PIN is malformed, or it does
            not match. The message and every log record hold no part of the PIN.
    """
    credential = await get_active_owner_pin_credential()
    if credential is None:
        logger.info("Admin PIN check: no active credential", extra={"event": _EVENT})
        raise AdminPinError
    try:
        matched = verify_pin(pin, credential.encoded)
    except ValueError as exc:
        logger.info("Admin PIN check: malformed input", extra={"event": _EVENT})
        raise AdminPinError from exc
    if not matched:
        logger.info("Admin PIN check: mismatch", extra={"event": _EVENT})
        raise AdminPinError
