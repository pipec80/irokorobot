"""Process-local owner PIN unlock service and per-request grant resolver.

Verifies the persistent PIN credential from the ``personal`` setup, issues an
opaque one-use token, and exposes a request-scoped resolver that the
controller awaits only for protected branches. Authentication here never
substitutes for the existing authorization/consent evaluation — it only
supplies fresh, consumable identity evidence and a consent signal bound to one
named operation (`OwnerUnlockScope`, ADR-0015): a grant issued for one operation
never authorizes another.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from enum import StrEnum
import logging
from math import ceil

from pydantic import BaseModel, ConfigDict

from server.cognition.authorization import ConsentStatus
from server.cognition.clock import utc_now
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityEvidence,
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

logger = logging.getLogger(__name__)

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
    """Raised when the process-local PIN attempt limit is currently active.

    Attributes:
        retry_after_seconds: Whole seconds until the block expires, rounded up
            so a caller retrying exactly then is never still blocked.
    """

    def __init__(self, retry_after_seconds: int) -> None:
        """Record how long the caller must wait.

        Args:
            retry_after_seconds: Whole seconds remaining on the active block.
        """
        super().__init__("Owner unlock attempts are rate limited")
        self.retry_after_seconds = retry_after_seconds


class OwnerUnlockScope(StrEnum):
    """Closed set of operations one owner unlock can be bound to (ADR-0015 decision 1).

    Attributes:
        PERSONAL_PROTECTED_READ: One protected read of the owner's confirmed child data
            (the default, so every existing client is unchanged).
        BIOMETRIC_ADMIN: Enrolling or revoking the owner's face or voice.
        PERSONAL_MEMORY_READ: Reading the owner's own personal conversation memory
            (ADR 0019). It does not unlock child data and the child-data grant does not
            unlock it.
        PERSONAL_MEMORY_FORGET: One erasure of the owner's own personal memory (ADR 0019).
    """

    PERSONAL_PROTECTED_READ = "personal_protected_read"
    BIOMETRIC_ADMIN = "biometric_admin"
    PERSONAL_MEMORY_READ = "personal_memory_read"
    PERSONAL_MEMORY_FORGET = "personal_memory_forget"


class OwnerUnlockResult(BaseModel):
    """Opaque one-use grant returned after a successful PIN verification."""

    model_config = ConfigDict(frozen=True)

    token: str
    expires_at: datetime
    scope: OwnerUnlockScope = OwnerUnlockScope.PERSONAL_PROTECTED_READ


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
    """Request-scoped actor/consent resolver bound to one optional token and one operation."""

    def __init__(
        self,
        *,
        token: str | None,
        registry: IdentitySessionRegistry,
        read_role: RoleReader,
        read_person: PersonReader,
        clock: Clock,
        scope: OwnerUnlockScope = OwnerUnlockScope.PERSONAL_PROTECTED_READ,
    ) -> None:
        """Create a resolver for exactly one HTTP request.

        Args:
            token: Optional opaque token carried by the current request.
            registry: Shared process-local one-use evidence registry.
            read_role: Boundary that reads a person's active household role.
            read_person: Boundary that reads a person's safe display record.
            clock: Source of the resolution timestamp.
            scope: The one operation this request authorizes. A token issued for another
                operation is refused and left unspent.
        """
        self._token = token
        self._registry = registry
        self._read_role = read_role
        self._read_person = read_person
        self._clock = clock
        self._scope = scope
        self.consumed = False

    @property
    def scope(self) -> frozenset[str]:
        """Return the exact granted capability, or empty before consumption."""
        if not self.consumed:
            return frozenset()
        if self._scope is OwnerUnlockScope.PERSONAL_PROTECTED_READ:
            return frozenset({self._scope.value, _CHILD_DATA_CATEGORY})
        return frozenset({self._scope.value})

    async def peek_actor(self, event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        """Name the owner behind the token without spending the grant.

        Used by branches that only need to know who is asking ("who am I", a household
        question that reads nothing): a bystander or a harmless question never burns the
        owner's one-use grant.

        Args:
            event: The event this observation is scoped to.

        Returns:
            The identified owner context, or the safe unknown actor when the token is
            absent, expired, unknown or issued for another operation.
        """
        if self._token is None:
            return _unknown_active_person(event)
        evidence = self._registry.evidence_for(self._token, scope=self._scope.value)
        if evidence is None:
            self._log_scope_mismatch()
            return _unknown_active_person(event)
        return await self._context_for(evidence, event)

    async def resolve_actor(self, event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
        """Consume the bound token at most once and resolve the owner actor.

        Args:
            event: The protected event this resolution is scoped to.

        Returns:
            The identified owner context, or the safe unknown actor when the
            token is absent, already consumed, expired, invalid or issued for
            another operation (in which case it is not consumed).
        """
        if self._token is None:
            return _unknown_active_person(event)
        evidence = self._registry.consume_evidence(self._token, scope=self._scope.value)
        if evidence is None:
            self._log_scope_mismatch()
            return _unknown_active_person(event)
        context = await self._context_for(evidence, event)
        self.consumed = context.person_id is not None
        return context

    async def _context_for(
        self, evidence: IdentityEvidence, event: CognitiveEvent[TextTurnPayload]
    ) -> ActivePersonContext:
        """Resolve the owner context a piece of grant evidence stands for."""
        if evidence.candidate_person_id is None:
            return _unknown_active_person(event)
        person = await self._read_person(evidence.candidate_person_id)
        if person is None:
            return _unknown_active_person(event)
        role = await self._read_role(person.person_id)

        def _lookup_person(person_id: int) -> PersonRecord | None:
            return person if person_id == person.person_id else None

        return resolve_active_person(
            evidence=(evidence,),
            lookup_person=_lookup_person,
            lookup_role=lambda _person_id: role,
            clock=self._clock,
        )

    def _log_scope_mismatch(self) -> None:
        """Log a closed reason when a live token was refused for another operation."""
        if self._token is not None and self._registry.evidence_for(self._token) is not None:
            logger.info("Owner grant refused: scope_mismatch")

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
        # One complete attempt — limiter check, credential and role reads,
        # scrypt verification, and the failure/success mutation — runs under
        # this lock. Without it every await between the check and the update
        # is a scheduling point where a concurrent caller can pass a limiter
        # that nobody has invalidated yet (Plan 0033).
        self._attempt_lock = asyncio.Lock()
        self._failures: list[datetime] = []
        self._blocked_until: datetime | None = None

    def _prune_and_check_block(self, now: datetime) -> None:
        """Clear an expired block and drop failures outside the rolling window.

        Raises:
            OwnerUnlockRateLimitedError: If the local block is still active.
        """
        if self._blocked_until is not None:
            if now < self._blocked_until:
                remaining = (self._blocked_until - now).total_seconds()
                raise OwnerUnlockRateLimitedError(retry_after_seconds=ceil(remaining))
            self._blocked_until = None
        cutoff = now - _FAILURE_WINDOW
        self._failures = [attempt for attempt in self._failures if attempt > cutoff]

    def _record_failure(self, now: datetime) -> None:
        """Record one failed attempt and activate the block at the exact threshold."""
        self._failures.append(now)
        if len(self._failures) >= _MAX_FAILURES:
            self._blocked_until = now + _BLOCK_DURATION
            self._failures.clear()

    async def unlock(
        self, pin: str, scope: OwnerUnlockScope = OwnerUnlockScope.PERSONAL_PROTECTED_READ
    ) -> OwnerUnlockResult | None:
        """Verify a candidate PIN and issue one opaque one-use grant for one operation.

        Args:
            pin: Candidate PIN from the local unlock request.
            scope: The one operation the grant may authorize.

        Returns:
            The opaque token and its expiry, or ``None`` for any failure —
            wrong PIN, missing credential, or a non-owner role — without
            revealing which case occurred.

        Raises:
            OwnerUnlockRateLimitedError: If five recent failures still block
                new attempts within the last 60 seconds.
        """
        async with self._attempt_lock:
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
            token = self._registry.issue_for_person(
                person, source=IdentityEvidenceSource.LOCAL_UNLOCK, scope=scope.value
            )
            evidence = self._registry.evidence_for(token)
            if evidence is None or evidence.expires_at is None:
                return None
            return OwnerUnlockResult(token=token, expires_at=evidence.expires_at, scope=scope)

    def for_request(
        self,
        token: str | None,
        scope: OwnerUnlockScope = OwnerUnlockScope.PERSONAL_PROTECTED_READ,
    ) -> OwnerRequestResolver:
        """Build a fresh resolver scoped to exactly one HTTP request and one operation.

        Args:
            token: Optional opaque token carried by the current request.
            scope: The operation this request authorizes; a token issued for another
                operation is refused and left unspent.

        Returns:
            A resolver that consumes the token at most once.
        """
        return OwnerRequestResolver(
            token=token,
            registry=self._registry,
            read_role=self._read_role,
            read_person=self._read_person,
            clock=self._clock,
            scope=scope,
        )


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
        clock=utc_now,
        ttl=timedelta(seconds=settings.owner_unlock_ttl_seconds),
    )
    return OwnerUnlockService(
        clock=utc_now,
        registry=registry,
        read_credential=get_active_owner_pin_credential,
        read_role=get_active_role,
        read_person=_read_person_record,
    )


owner_unlock_service: OwnerUnlockService = build_default_owner_unlock_service()
