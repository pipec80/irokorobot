"""Process-local owner PIN unlock service and per-request grant resolver.

Verifies the persistent PIN credential from the ``personal`` setup, issues an
opaque one-use token, and exposes a request-scoped resolver that the
controller awaits only for protected branches. Authentication here never
substitutes for the existing authorization/consent evaluation — it only
supplies fresh, consumable identity evidence and a narrowly scoped consent
signal for one child-data read.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from server.cognition.authorization import ConsentStatus
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityEvidenceSource,
    PersonRecord,
    resolve_active_person,
)
from server.cognition.identity_sessions import IdentitySessionRegistry
from server.cognition.models import CognitiveEvent, Confidence, ConfidenceBasis
from server.cognition.pin_credentials import verify_pin
from server.cognition.response_plan import TextTurnPayload
from server.memory.entity_labels import get_person_label
from server.memory.household_authorization import get_active_role
from server.memory.owner_credentials import OwnerPinCredential, get_active_owner_pin_credential
from server.settings import settings

__all__ = [
    "OwnerRequestResolver",
    "OwnerUnlockRateLimitedError",
    "OwnerUnlockResult",
    "OwnerUnlockScope",
    "OwnerUnlockService",
]

_MAX_FAILURES = 5
_FAILURE_WINDOW = timedelta(seconds=60)
_BLOCK_DURATION = timedelta(seconds=60)
_CHILD_DATA_CATEGORY = "child_data"

type CredentialReader = Callable[[], Awaitable[OwnerPinCredential | None]]
type PersonReader = Callable[[int], Awaitable[PersonRecord | None]]
type RoleReader = Callable[[int], Awaitable[HouseholdRole]]
type Clock = Callable[[], datetime]
type ToThread = Callable[[Callable[[], bool]], Awaitable[bool]]


class OwnerUnlockRateLimitedError(Exception):
    """Raised when the process-local PIN attempt limit is currently active."""


class OwnerUnlockScope(StrEnum):
    """Closed capability granted by one consumed owner unlock."""

    PERSONAL_PROTECTED_READ = "personal_protected_read"


class OwnerUnlockResult(BaseModel):
    """Opaque one-use grant returned after a successful PIN verification."""

    model_config = ConfigDict(frozen=True)

    token: str
    expires_at: datetime


async def _default_to_thread(fn: Callable[[], bool]) -> bool:
    """Run a blocking boundary off the event loop."""
    return await asyncio.to_thread(fn)


def _unknown_active_person(event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
    """Build the safe public actor without deriving identity from HTTP input."""
    return ActivePersonContext(
        person_id=None,
        display_name=None,
        status=ActivePersonStatus.UNKNOWN,
        confidence=Confidence(
            score=0.0,
            basis=ConfidenceBasis.NOT_APPLICABLE,
            calibrated=False,
            reason="No trusted active-person evidence",
        ),
        role=HouseholdRole.UNKNOWN,
        evidence=(),
        resolved_at=event.occurred_at,
    )


class OwnerRequestResolver:
    """Request-scoped actor/consent resolver bound to one optional token."""

    def __init__(
        self,
        *,
        token: str | None,
        registry: IdentitySessionRegistry,
        read_role: RoleReader,
        read_person: PersonReader,
        clock: Clock,
    ) -> None:
        """Create a resolver for exactly one HTTP request.

        Args:
            token: Optional opaque token carried by the current request.
            registry: Shared process-local one-use evidence registry.
            read_role: Boundary that reads a person's active household role.
            read_person: Boundary that reads a person's safe display record.
            clock: Source of the resolution timestamp.
        """
        self._token = token
        self._registry = registry
        self._read_role = read_role
        self._read_person = read_person
        self._clock = clock
        self.consumed = False

    @property
    def scope(self) -> frozenset[str]:
        """Return the exact granted capability, or empty before consumption."""
        if not self.consumed:
            return frozenset()
        return frozenset({OwnerUnlockScope.PERSONAL_PROTECTED_READ.value, _CHILD_DATA_CATEGORY})

    async def resolve_actor(self, event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        """Consume the bound token at most once and resolve the owner actor.

        Args:
            event: The protected event this resolution is scoped to.

        Returns:
            The identified owner context, or the safe unknown actor when the
            token is absent, already consumed, expired, or invalid.
        """
        if self._token is None:
            return _unknown_active_person(event)
        evidence = self._registry.consume_evidence(self._token)
        if evidence is None or evidence.candidate_person_id is None:
            return _unknown_active_person(event)

        person = await self._read_person(evidence.candidate_person_id)
        if person is None:
            return _unknown_active_person(event)
        role = await self._read_role(person.person_id)

        def _lookup_person(person_id: int) -> PersonRecord | None:
            return person if person_id == person.person_id else None

        context = resolve_active_person(
            evidence=(evidence,),
            lookup_person=_lookup_person,
            lookup_role=lambda _person_id: role,
            clock=self._clock,
        )
        self.consumed = context.person_id is not None
        return context

    async def resolve_consent(
        self,
        event: CognitiveEvent[TextTurnPayload],
        actor: ActivePersonContext,
    ) -> ConsentStatus:
        """Grant scoped consent only after this resolver consumed a valid grant.

        Args:
            event: The protected event being authorized.
            actor: The context produced by :meth:`resolve_actor` for this event.

        Returns:
            ``GRANTED`` only when this exact resolver consumed a fresh owner
            grant; otherwise a status that authorizes nothing.
        """
        del event
        if self.consumed and actor.person_id is not None and actor.role is HouseholdRole.OWNER:
            return ConsentStatus.GRANTED
        return ConsentStatus.NOT_REQUIRED


class OwnerUnlockService:
    """Verify the owner PIN and issue/resolve one-use local unlock grants."""

    def __init__(
        self,
        *,
        clock: Clock,
        registry: IdentitySessionRegistry,
        read_credential: CredentialReader,
        read_role: RoleReader,
        read_person: PersonReader,
        to_thread: ToThread = _default_to_thread,
    ) -> None:
        """Create the service with injected time, storage, and threading boundaries.

        Args:
            clock: Source of the current aware timestamp.
            registry: Shared process-local one-use evidence registry.
            read_credential: Boundary that reads the active owner PIN credential.
            read_role: Boundary that reads a person's active household role.
            read_person: Boundary that reads a person's safe display record.
            to_thread: Boundary that runs the blocking scrypt verify off-loop.
        """
        self._clock = clock
        self._registry = registry
        self._read_credential = read_credential
        self._read_role = read_role
        self._read_person = read_person
        self._to_thread = to_thread
        self._failures: list[datetime] = []
        self._blocked_until: datetime | None = None

    def _prune_and_check_block(self, now: datetime) -> None:
        """Clear an expired block and drop failures outside the rolling window.

        Raises:
            OwnerUnlockRateLimitedError: If the local block is still active.
        """
        if self._blocked_until is not None:
            if now < self._blocked_until:
                raise OwnerUnlockRateLimitedError("too many failed local PIN attempts")
            self._blocked_until = None
            self._failures.clear()
        cutoff = now - _FAILURE_WINDOW
        self._failures = [attempt for attempt in self._failures if attempt > cutoff]

    def _record_failure(self, now: datetime) -> None:
        """Record one failed attempt and activate the block at the exact threshold."""
        self._failures.append(now)
        if len(self._failures) >= _MAX_FAILURES:
            self._blocked_until = now + _BLOCK_DURATION
            self._failures.clear()

    async def unlock(self, pin: str) -> OwnerUnlockResult | None:
        """Verify a candidate PIN and issue one opaque one-use grant.

        Args:
            pin: Candidate PIN from the local unlock request.

        Returns:
            The opaque token and its expiry, or ``None`` for any failure —
            wrong PIN, missing credential, or a non-owner role — without
            revealing which case occurred.

        Raises:
            OwnerUnlockRateLimitedError: If five recent failures still block
                new attempts within the last 60 seconds.
        """
        now = self._clock()
        self._prune_and_check_block(now)

        credential = await self._read_credential()
        if credential is None:
            self._record_failure(now)
            return None
        role = await self._read_role(credential.person_entity_id)
        if role is not HouseholdRole.OWNER:
            self._record_failure(now)
            return None
        matched = await self._to_thread(lambda: verify_pin(pin, credential.encoded))
        if not matched:
            self._record_failure(now)
            return None

        self._failures.clear()
        person = await self._read_person(credential.person_entity_id)
        if person is None:
            return None
        token = self._registry.issue_for_person(person, source=IdentityEvidenceSource.LOCAL_UNLOCK)
        evidence = self._registry.evidence_for(token)
        if evidence is None or evidence.expires_at is None:
            return None
        return OwnerUnlockResult(token=token, expires_at=evidence.expires_at)

    def for_request(self, token: str | None) -> OwnerRequestResolver:
        """Build a fresh resolver scoped to exactly one HTTP request.

        Args:
            token: Optional opaque token carried by the current request.

        Returns:
            A resolver that consumes the token at most once.
        """
        return OwnerRequestResolver(
            token=token,
            registry=self._registry,
            read_role=self._read_role,
            read_person=self._read_person,
            clock=self._clock,
        )


def _utc_now() -> datetime:
    """Return the current aware UTC timestamp for production boundaries."""
    return datetime.now(UTC)


async def _read_person_record(person_entity_id: int) -> PersonRecord | None:
    """Adapt the safe entity-label lookup to the identity `PersonRecord` shape."""
    label = await get_person_label(entity_id=person_entity_id)
    if label is None:
        return None
    return PersonRecord(
        person_id=label.entity_id, display_name=label.display_name, entity_type="person"
    )


def build_default_owner_unlock_service() -> OwnerUnlockService:
    """Compose the production owner unlock service over real repositories.

    Returns:
        A service backed by the Plan 0025 credential/role/label repositories,
        a fresh process-local one-use evidence registry, and real scrypt
        verification off-loaded via `asyncio.to_thread`.
    """
    registry = IdentitySessionRegistry(
        lookup_person=lambda _person_id: None,
        clock=_utc_now,
        ttl=timedelta(seconds=settings.owner_unlock_ttl_seconds),
    )
    return OwnerUnlockService(
        clock=_utc_now,
        registry=registry,
        read_credential=get_active_owner_pin_credential,
        read_role=get_active_role,
        read_person=_read_person_record,
    )


owner_unlock_service: OwnerUnlockService = build_default_owner_unlock_service()
