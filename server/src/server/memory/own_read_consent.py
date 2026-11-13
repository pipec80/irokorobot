"""The consent of a read of the owner's own data (Plan 0079 D-9).

The one rule the sensitive read and the pending-topic follow-up (Plan 0084 D-9) share: a
``medical``, ``location`` or ``security`` datum needs the face's grant and a closed alta; anything
else needs no consent. Kept apart from both readers so neither imports the other.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Final

from server.cognition.authorization import ConsentStatus

__all__ = ["CONSENT_SENSITIVITIES", "AltaChecker", "own_read_consent"]

type AltaChecker = Callable[[], Awaitable[bool]]

#: Sensitivities whose read needs the person's consent and a closed alta.
CONSENT_SENSITIVITIES: Final = frozenset({"medical", "location", "security"})


async def own_read_consent(
    sensitivities: frozenset[str], *, face_consent: ConsentStatus, alta_closed: AltaChecker
) -> ConsentStatus:
    """Return the consent of a read of the owner's own data.

    Args:
        sensitivities: The sensitivities of the data read.
        face_consent: The consent the face path resolved for the speaker.
        alta_closed: Whether a commissioning is closed; asked only when consent is needed.

    Returns:
        ``NOT_REQUIRED`` unless a sensitivity needs consent; then ``GRANTED`` for the face's grant
        and a closed alta, else ``MISSING``.
    """
    if not sensitivities & CONSENT_SENSITIVITIES:
        return ConsentStatus.NOT_REQUIRED
    if face_consent is ConsentStatus.GRANTED and await alta_closed():
        return ConsentStatus.GRANTED
    return ConsentStatus.MISSING
