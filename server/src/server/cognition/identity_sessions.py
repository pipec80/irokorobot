"""Process-local registry for explicit active-person session selections."""

from collections.abc import Callable as _Callable
from datetime import datetime as _datetime, timedelta as _timedelta
from uuid import uuid4 as _uuid4

from server.cognition.identity import IdentityEvidence, IdentityEvidenceSource, PersonRecord
from server.cognition.models import Confidence, ConfidenceBasis

type PersonLookup = _Callable[[int], PersonRecord | None]
type Clock = _Callable[[], _datetime]

_PERSON_ENTITY_TYPE = "person"
_SELECTION_REFERENCE = "session-selection"

__all__ = ["IdentitySessionRegistry", "SessionIdentityRegistry"]


class IdentitySessionRegistry:
    """Retain safe, expiring evidence from explicit local person selections."""

    def __init__(self, *, lookup_person: PersonLookup, clock: Clock, ttl: _timedelta) -> None:
        """Create a registry with injected person lookup and clock boundaries.

        Args:
            lookup_person: Boundary that verifies an existing person record.
            clock: Source of aware selection timestamps.
            ttl: Positive lifetime of a local session selection.

        Raises:
            ValueError: If the session lifetime is not positive.
        """
        if ttl <= _timedelta():
            raise ValueError("ttl must be positive")
        self._lookup_person = lookup_person
        self._clock = clock
        self._ttl = ttl
        self._evidence_by_token: dict[str, IdentityEvidence] = {}

    def select_person(self, person_id: int) -> str | None:
        """Record a manual session selection only for an existing person ID.

        Args:
            person_id: Existing integer person/entity ID selected locally.

        Returns:
            An opaque token, or ``None`` when the entity is not a person.

        Raises:
            ValueError: If the supplied ID is not a strict integer.
        """
        if type(person_id) is not int:
            raise ValueError("person_id must be an integer")
        person = self._lookup_person(person_id)
        if (
            person is None
            or person.person_id != person_id
            or person.entity_type != _PERSON_ENTITY_TYPE
        ):
            return None
        observed_at = self._clock()
        evidence = IdentityEvidence(
            evidence_id=_uuid4(),
            source=IdentityEvidenceSource.MANUAL,
            candidate_person_id=person_id,
            confidence=Confidence(
                score=1.0,
                basis=ConfidenceBasis.ASSERTED,
                calibrated=True,
                reason="Explicit local selection",
            ),
            observed_at=observed_at,
            expires_at=observed_at + self._ttl,
            reference=_SELECTION_REFERENCE,
        )
        token = _uuid4().hex
        self._evidence_by_token[token] = evidence
        return token

    def evidence_for(self, token: str) -> IdentityEvidence | None:
        """Return unexpired safe selection evidence for an opaque token.

        Args:
            token: Opaque session token returned by :meth:`select_person`.

        Returns:
            Immutable evidence when still fresh, otherwise ``None``.
        """
        evidence = self._evidence_by_token.get(token)
        if evidence is None:
            return None
        if evidence.expires_at is not None and evidence.expires_at <= self._clock():
            self.clear(token)
            return None
        return evidence

    def clear(self, token: str) -> None:
        """Remove a session selection by its opaque token.

        Args:
            token: Opaque session token returned by :meth:`select_person`.
        """
        self._evidence_by_token.pop(token, None)

    def issue_for_person(self, person: PersonRecord, *, source: IdentityEvidenceSource) -> str:
        """Issue one-use evidence for an already-verified person record.

        Args:
            person: A person record verified by the caller (e.g. a successful
                local-unlock PIN check), not re-verified here.
            source: The evidence source to record, e.g. ``LOCAL_UNLOCK``.

        Returns:
            An opaque token that must be redeemed exactly once via
            :meth:`consume_evidence`.

        Raises:
            ValueError: If the supplied record is not a person entity.
        """
        if person.entity_type != _PERSON_ENTITY_TYPE:
            raise ValueError("issued evidence requires a person entity")
        observed_at = self._clock()
        evidence = IdentityEvidence(
            evidence_id=_uuid4(),
            source=source,
            candidate_person_id=person.person_id,
            confidence=Confidence(
                score=1.0,
                basis=ConfidenceBasis.ASSERTED,
                calibrated=True,
                reason="Explicit local issuance",
            ),
            observed_at=observed_at,
            expires_at=observed_at + self._ttl,
            reference=_SELECTION_REFERENCE,
        )
        token = _uuid4().hex
        self._evidence_by_token[token] = evidence
        return token

    def consume_evidence(self, token: str) -> IdentityEvidence | None:
        """Redeem one-use evidence exactly once, then invalidate the token.

        Args:
            token: Opaque token returned by :meth:`issue_for_person` or
                :meth:`select_person`.

        Returns:
            The evidence if the token was present and unexpired, else
            ``None``. The token is removed either way — a second call with
            the same token always returns ``None``.
        """
        evidence = self._evidence_by_token.pop(token, None)
        if evidence is None:
            return None
        if evidence.expires_at is not None and evidence.expires_at <= self._clock():
            return None
        return evidence


# Compatibility for the implementation name used before Plan 0002 review.
SessionIdentityRegistry = IdentitySessionRegistry
