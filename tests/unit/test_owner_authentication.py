"""Unit tests for the process-local owner unlock service and request resolver."""

import asyncio
from datetime import UTC, datetime, timedelta
import logging
from uuid import UUID

import pytest
from server.cognition.authorization import ConsentStatus
from server.cognition.identity import ActivePersonStatus, HouseholdRole, PersonRecord
from server.cognition.identity_sessions import IdentitySessionRegistry
from server.cognition.models import CognitiveEvent
from server.cognition.owner_authentication import (
    _MAX_FAILURES,
    OwnerUnlockRateLimitedError,
    OwnerUnlockScope,
    OwnerUnlockService,
)
from server.cognition.pin_credentials import hash_pin
from server.cognition.response_plan import TextTurnPayload
from server.memory.owner_credentials import OwnerPinCredential

_NOW = datetime(2026, 8, 21, 10, 0, tzinfo=UTC)
_OWNER_ID = 1
_PIN = "482173"


def _credential(pin: str = _PIN) -> OwnerPinCredential:
    encoded = hash_pin(pin, salt=b"0" * 16)
    return OwnerPinCredential(id=1, person_entity_id=_OWNER_ID, encoded=encoded)


def _event(message: str = "¿Quiénes son mis hijos?") -> CognitiveEvent[TextTurnPayload]:
    return CognitiveEvent(
        event_id=UUID("11111111-1111-1111-1111-111111111111"),
        schema_version=1,
        event_type="text.turn",
        occurred_at=_NOW,
        recorded_at=_NOW,
        source="web.chat",
        correlation_id=UUID("22222222-2222-2222-2222-222222222222"),
        causation_id=None,
        subject_id=None,
        payload=TextTurnPayload(message=message, conversation_id="acceptance-owner"),
    )


async def _sync_to_thread(fn):
    return fn()


def _service(
    *,
    clock=lambda: _NOW,
    credential: OwnerPinCredential | None = None,
    role: HouseholdRole = HouseholdRole.OWNER,
    ttl: timedelta = timedelta(seconds=60),
) -> OwnerUnlockService:
    registry = IdentitySessionRegistry(lookup_person=lambda _pid: None, clock=clock, ttl=ttl)

    async def read_credential() -> OwnerPinCredential | None:
        return credential

    async def read_role(_person_entity_id: int) -> HouseholdRole:
        return role

    async def read_person(person_entity_id: int) -> PersonRecord | None:
        return PersonRecord(person_id=person_entity_id, display_name="Pipec", entity_type="person")

    return OwnerUnlockService(
        clock=clock,
        registry=registry,
        read_credential=read_credential,
        read_role=read_role,
        read_person=read_person,
        to_thread=_sync_to_thread,
    )


@pytest.mark.unit
async def test_valid_pin_issues_a_sixty_second_token() -> None:
    """A correct PIN issues an opaque token with the exact registry TTL."""
    service = _service(credential=_credential())

    result = await service.unlock(_PIN)

    assert result is not None
    assert isinstance(result.token, str)
    assert result.token
    assert result.expires_at == _NOW + timedelta(seconds=60)


@pytest.mark.unit
async def test_invalid_pin_returns_none_without_revealing_profile_existence() -> None:
    """A wrong PIN and a missing credential must be indistinguishable publicly."""
    with_credential = _service(credential=_credential())
    without_credential = _service(credential=None)

    assert await with_credential.unlock("000000") is None
    assert await without_credential.unlock(_PIN) is None


@pytest.mark.unit
async def test_non_owner_role_is_rejected_like_an_invalid_pin() -> None:
    """A credential whose person lost the owner role must not unlock."""
    service = _service(credential=_credential(), role=HouseholdRole.ADULT)

    assert await service.unlock(_PIN) is None


@pytest.mark.unit
async def test_five_failures_block_new_attempts_for_sixty_seconds() -> None:
    """The exact five-strikes/sixty-second local rate limit must apply."""
    now = _NOW

    def clock() -> datetime:
        return now

    service = _service(clock=clock, credential=_credential())

    for _ in range(5):
        assert await service.unlock("000000") is None

    with pytest.raises(OwnerUnlockRateLimitedError):
        await service.unlock(_PIN)

    now = _NOW + timedelta(seconds=30)
    with pytest.raises(OwnerUnlockRateLimitedError):
        await service.unlock(_PIN)

    now = _NOW + timedelta(seconds=61)
    result = await service.unlock(_PIN)
    assert result is not None


@pytest.mark.unit
async def test_successful_verification_clears_failure_state() -> None:
    """A correct PIN resets the failure counter for the next attempts."""
    now = _NOW

    def clock() -> datetime:
        return now

    service = _service(clock=clock, credential=_credential())

    for _ in range(4):
        assert await service.unlock("000000") is None
    assert await service.unlock(_PIN) is not None

    for _ in range(4):
        assert await service.unlock("000000") is None
    assert await service.unlock(_PIN) is not None


@pytest.mark.unit
async def test_for_request_without_a_token_resolves_unknown() -> None:
    """A missing token must resolve the public unknown actor, never an owner."""
    service = _service(credential=_credential())
    resolver = service.for_request(None)

    actor = await resolver.resolve_actor(_event())

    assert actor.status is ActivePersonStatus.UNKNOWN
    assert actor.person_id is None
    assert resolver.consumed is False


@pytest.mark.unit
async def test_first_resolver_call_consumes_the_token_and_identifies_the_owner() -> None:
    """The first protected resolution consumes the grant and returns the owner."""
    service = _service(credential=_credential())
    unlock = await service.unlock(_PIN)
    assert unlock is not None

    resolver = service.for_request(unlock.token)
    actor = await resolver.resolve_actor(_event())

    assert actor.status is ActivePersonStatus.IDENTIFIED
    assert actor.person_id == _OWNER_ID
    assert actor.role is HouseholdRole.OWNER
    assert resolver.consumed is True


@pytest.mark.unit
async def test_a_replayed_token_resolves_unknown_on_a_second_resolver() -> None:
    """A second resolver built from the same already-consumed token is unknown."""
    service = _service(credential=_credential())
    unlock = await service.unlock(_PIN)
    assert unlock is not None

    first_resolver = service.for_request(unlock.token)
    await first_resolver.resolve_actor(_event())

    second_resolver = service.for_request(unlock.token)
    actor = await second_resolver.resolve_actor(_event())

    assert actor.status is ActivePersonStatus.UNKNOWN
    assert actor.person_id is None
    assert second_resolver.consumed is False


@pytest.mark.unit
async def test_consent_is_granted_only_after_this_resolver_consumed_a_valid_grant() -> None:
    """Scoped consent requires this exact resolver to have consumed evidence."""
    service = _service(credential=_credential())
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    resolver = service.for_request(unlock.token)
    event = _event()

    actor = await resolver.resolve_actor(event)
    consent = await resolver.resolve_consent(event, actor)

    assert consent is ConsentStatus.GRANTED

    unknown_resolver = service.for_request(None)
    unknown_actor = await unknown_resolver.resolve_actor(event)
    unknown_consent = await unknown_resolver.resolve_consent(event, unknown_actor)
    assert unknown_consent is not ConsentStatus.GRANTED


@pytest.mark.unit
async def test_granted_scope_is_exactly_personal_protected_read_and_child_data() -> None:
    """The resolver never exposes a broader capability than the named scope."""
    service = _service(credential=_credential())
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    resolver = service.for_request(unlock.token)

    await resolver.resolve_actor(_event())

    assert resolver.scope == frozenset(
        {OwnerUnlockScope.PERSONAL_PROTECTED_READ.value, "child_data"}
    )


@pytest.mark.unit
async def test_no_secret_appears_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    """Neither the PIN nor the issued token may be written to any log record."""
    service = _service(credential=_credential())

    with caplog.at_level(logging.DEBUG):
        unlock = await service.unlock(_PIN)
        assert unlock is not None
        resolver = service.for_request(unlock.token)
        await resolver.resolve_actor(_event())

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert _PIN not in joined
    assert unlock.token not in joined


# --- Plan 0033: the limiter must hold under concurrency -------------------


@pytest.mark.unit
async def test_concurrent_wrong_attempts_cannot_outrun_the_limiter() -> None:
    """Six simultaneous wrong PINs must not all get a verification.

    `unlock` checks the limiter, then awaits the credential read, the role
    read and the scrypt verification before recording the failure. Every
    await is a scheduling point, so N coroutines can all pass a check that
    none of them has yet invalidated — and scrypt is deliberately slow, which
    widens the window rather than narrowing it.

    The limiter blocks at five failures, so the sixth attempt must never
    reach the verifier.
    """
    attempts = 6
    verifications = 0
    release = asyncio.Event()

    async def gated_to_thread(fn):
        """Hold every attempt at the verifier until all of them have arrived."""
        nonlocal verifications
        verifications += 1
        await release.wait()
        return False  # every candidate is wrong

    service = _service(credential=_credential())
    service._to_thread = gated_to_thread

    tasks = [asyncio.create_task(service.unlock("999999")) for _ in range(attempts)]
    await asyncio.sleep(0)  # let every task run up to its first await
    release.set()
    results = await asyncio.gather(*tasks, return_exceptions=True)

    rate_limited = [r for r in results if isinstance(r, OwnerUnlockRateLimitedError)]
    assert verifications <= _MAX_FAILURES, (
        f"{verifications} attempts reached the verifier; the limiter blocks at "
        f"{_MAX_FAILURES}, so a concurrent caller bypassed it"
    )
    assert rate_limited, "at least one attempt past the threshold must be rate limited"


@pytest.mark.unit
async def test_the_rate_limit_error_reports_when_to_retry() -> None:
    """A 429 is only actionable if it says how long the block lasts."""
    service = _service(credential=_credential())
    service._to_thread = _always_wrong

    for _ in range(_MAX_FAILURES):
        await service.unlock("999999")

    with pytest.raises(OwnerUnlockRateLimitedError) as caught:
        await service.unlock("999999")

    assert caught.value.retry_after_seconds > 0


async def _always_wrong(fn):
    """Stand in for the verifier, always rejecting the candidate."""
    return False


# --- Plan 0051: every grant is bound to one named operation (ADR-0015) --------


@pytest.mark.unit
async def test_unlock_defaults_to_the_read_scope_and_can_ask_for_biometric_admin() -> None:
    service = _service(credential=_credential())

    default = await service.unlock(_PIN)
    admin = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)

    assert default is not None
    assert default.scope is OwnerUnlockScope.PERSONAL_PROTECTED_READ
    assert admin is not None
    assert admin.scope is OwnerUnlockScope.BIOMETRIC_ADMIN


@pytest.mark.unit
async def test_a_read_grant_cannot_authorize_biometric_admin_and_is_not_burned() -> None:
    service = _service(credential=_credential())
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    event = _event()

    admin = service.for_request(unlock.token, scope=OwnerUnlockScope.BIOMETRIC_ADMIN)
    refused = await admin.resolve_actor(event)
    refused_consent = await admin.resolve_consent(event, refused)

    assert refused.status is ActivePersonStatus.UNKNOWN
    assert admin.consumed is False
    assert refused_consent is not ConsentStatus.GRANTED

    read = service.for_request(unlock.token)
    owner = await read.resolve_actor(event)
    assert owner.status is ActivePersonStatus.IDENTIFIED
    assert read.consumed is True


@pytest.mark.unit
async def test_a_biometric_admin_grant_cannot_authorize_a_read_and_is_not_burned() -> None:
    service = _service(credential=_credential())
    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
    assert unlock is not None
    event = _event()

    read = service.for_request(unlock.token)
    refused = await read.resolve_actor(event)

    assert refused.status is ActivePersonStatus.UNKNOWN
    assert read.consumed is False

    admin = service.for_request(unlock.token, scope=OwnerUnlockScope.BIOMETRIC_ADMIN)
    owner = await admin.resolve_actor(event)
    consent = await admin.resolve_consent(event, owner)
    assert owner.status is ActivePersonStatus.IDENTIFIED
    assert admin.consumed is True
    assert consent is ConsentStatus.GRANTED


@pytest.mark.unit
async def test_the_granted_scope_names_only_the_operation_that_consumed_the_grant() -> None:
    service = _service(credential=_credential())
    unlock = await service.unlock(_PIN, OwnerUnlockScope.BIOMETRIC_ADMIN)
    assert unlock is not None
    admin = service.for_request(unlock.token, scope=OwnerUnlockScope.BIOMETRIC_ADMIN)

    assert admin.scope == frozenset()  # nothing before consumption
    await admin.resolve_actor(_event())

    assert admin.scope == frozenset({OwnerUnlockScope.BIOMETRIC_ADMIN.value})


@pytest.mark.unit
async def test_peeking_identifies_the_owner_without_spending_the_grant() -> None:
    service = _service(credential=_credential())
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    event = _event()

    peeking = service.for_request(unlock.token)
    seen = await peeking.peek_actor(event)
    seen_again = await peeking.peek_actor(event)

    assert seen.status is ActivePersonStatus.IDENTIFIED
    assert seen.person_id == _OWNER_ID
    assert seen_again.status is ActivePersonStatus.IDENTIFIED
    assert peeking.consumed is False
    assert peeking.scope == frozenset()

    reading = service.for_request(unlock.token)
    assert (await reading.resolve_actor(event)).status is ActivePersonStatus.IDENTIFIED
    assert reading.consumed is True


@pytest.mark.unit
async def test_peeking_is_unknown_without_a_token_for_this_scope_or_after_expiry() -> None:
    now = _NOW

    def clock() -> datetime:
        return now

    service = _service(clock=clock, credential=_credential())
    unlock = await service.unlock(_PIN)
    assert unlock is not None
    event = _event()

    assert (await service.for_request(None).peek_actor(event)).status is ActivePersonStatus.UNKNOWN
    assert (await service.for_request("not-a-token").peek_actor(event)).status is (
        ActivePersonStatus.UNKNOWN
    )
    admin = service.for_request(unlock.token, scope=OwnerUnlockScope.BIOMETRIC_ADMIN)
    assert (await admin.peek_actor(event)).status is ActivePersonStatus.UNKNOWN

    now = _NOW + timedelta(seconds=61)
    assert (await service.for_request(unlock.token).peek_actor(event)).status is (
        ActivePersonStatus.UNKNOWN
    )


@pytest.mark.unit
async def test_a_scope_mismatch_is_logged_as_a_closed_reason_and_never_the_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = _service(credential=_credential())
    unlock = await service.unlock(_PIN)
    assert unlock is not None

    with caplog.at_level(logging.INFO):
        admin = service.for_request(unlock.token, scope=OwnerUnlockScope.BIOMETRIC_ADMIN)
        await admin.resolve_actor(_event())

    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "scope_mismatch" in joined
    assert unlock.token not in joined


# --- Plan 0060: personal-memory scopes (ADR 0019 §4) ----------------------------------------


@pytest.mark.unit
async def test_the_service_issues_a_grant_for_each_personal_memory_scope() -> None:
    service = _service(credential=_credential())

    for scope in (OwnerUnlockScope.PERSONAL_MEMORY_READ, OwnerUnlockScope.PERSONAL_MEMORY_FORGET):
        unlock = await service.unlock(_PIN, scope)
        assert unlock is not None
        assert unlock.scope is scope
