"""Tests for process-local, explicitly selected identity sessions."""

from datetime import UTC, datetime, timedelta

import pytest
from server.cognition import identity_sessions
from server.cognition.identity import (
    ActivePersonStatus,
    IdentityEvidenceSource,
    PersonRecord,
    resolve_active_person,
)
from server.cognition.identity_sessions import SessionIdentityRegistry

_NOW = datetime(2026, 8, 10, 16, 0, tzinfo=UTC)


def _person(person_id: int) -> PersonRecord:
    return PersonRecord(person_id=person_id, display_name="Ada", entity_type="person")


def _lookup(records: dict[int, PersonRecord]):
    def lookup(person_id: int) -> PersonRecord | None:
        return records.get(person_id)

    return lookup


def test_registry_records_manual_selection_only_for_existing_integer_person_id() -> None:
    """Reject a registry that selects a name, coerced ID, or missing entity."""
    registry = SessionIdentityRegistry(
        lookup_person=_lookup({42: _person(42)}),
        clock=lambda: _NOW,
        ttl=timedelta(minutes=5),
    )

    token = registry.select_person(42)

    assert isinstance(token, str)
    assert token
    assert registry.select_person(99) is None
    with pytest.raises(ValueError, match="integer"):
        registry.select_person("Ada")  # type: ignore[arg-type]  # Deliberately invalid runtime input.


def test_registry_uses_an_opaque_token_and_retains_safe_evidence_only() -> None:
    """Reject a registry that exposes a display-name key or raw biometric content."""
    registry = SessionIdentityRegistry(
        lookup_person=_lookup({42: _person(42)}),
        clock=lambda: _NOW,
        ttl=timedelta(minutes=5),
    )

    token = registry.select_person(42)
    assert token is not None
    evidence = registry.evidence_for(token)
    assert evidence is not None
    assert token != str(evidence.candidate_person_id)
    assert evidence.source is IdentityEvidenceSource.MANUAL
    assert evidence.candidate_person_id == 42
    assert set(evidence.model_dump()) == {
        "evidence_id",
        "source",
        "candidate_person_id",
        "confidence",
        "observed_at",
        "reference",
        "expires_at",
        "grant_scope",
        "grant_spent",
    }


def test_registry_expires_and_clears_session_evidence() -> None:
    """Reject a registry that returns expired or explicitly cleared selections."""
    now = _NOW

    def clock() -> datetime:
        return now

    registry = SessionIdentityRegistry(
        lookup_person=_lookup({42: _person(42)}),
        clock=clock,
        ttl=timedelta(minutes=5),
    )
    token = registry.select_person(42)

    assert token is not None
    now = _NOW + timedelta(minutes=5)
    assert registry.evidence_for(token) is None

    replacement = registry.select_person(42)
    assert replacement is not None
    registry.clear(replacement)
    assert registry.evidence_for(replacement) is None


def test_trusted_selection_resolves_as_identified_manual_evidence() -> None:
    """A trusted explicit registry selection must not degrade to probable."""
    registry = SessionIdentityRegistry(
        lookup_person=_lookup({42: _person(42)}),
        clock=lambda: _NOW,
        ttl=timedelta(minutes=5),
    )
    token = registry.select_person(42)

    assert token is not None
    evidence = registry.evidence_for(token)
    assert evidence is not None
    context = resolve_active_person(
        evidence=(evidence,),
        lookup_person=_lookup({42: _person(42)}),
        clock=lambda: _NOW,
    )

    assert context.status is ActivePersonStatus.IDENTIFIED
    assert context.person_id == 42


def test_legacy_registry_name_remains_a_compatibility_alias() -> None:
    """Existing internal imports keep working after aligning the plan's class name."""
    assert identity_sessions.IdentitySessionRegistry is SessionIdentityRegistry


def test_issue_for_person_consumes_evidence_exactly_once() -> None:
    """Consuming issued evidence must pop it — a replay must fail closed."""
    registry = SessionIdentityRegistry(
        lookup_person=_lookup({42: _person(42)}),
        clock=lambda: _NOW,
        ttl=timedelta(seconds=60),
    )

    token = registry.issue_for_person(_person(42), source=IdentityEvidenceSource.LOCAL_UNLOCK)

    first = registry.consume_evidence(token)
    assert first is not None
    assert first.source is IdentityEvidenceSource.LOCAL_UNLOCK
    assert first.candidate_person_id == 42

    assert registry.consume_evidence(token) is None
    assert registry.evidence_for(token) is None


def test_consume_evidence_rejects_an_expired_grant() -> None:
    """An expired but not-yet-consumed grant must not resolve identity."""
    now = _NOW

    def clock() -> datetime:
        return now

    registry = SessionIdentityRegistry(
        lookup_person=_lookup({42: _person(42)}),
        clock=clock,
        ttl=timedelta(seconds=60),
    )
    token = registry.issue_for_person(_person(42), source=IdentityEvidenceSource.LOCAL_UNLOCK)

    now = _NOW + timedelta(seconds=61)

    assert registry.consume_evidence(token) is None


def test_issue_for_person_rejects_a_non_person_record() -> None:
    """The registry must never issue trusted evidence for a non-person entity."""
    registry = SessionIdentityRegistry(
        lookup_person=_lookup({}),
        clock=lambda: _NOW,
        ttl=timedelta(seconds=60),
    )
    pet = PersonRecord(person_id=7, display_name="Rex", entity_type="pet")

    with pytest.raises(ValueError, match="person"):
        registry.issue_for_person(pet, source=IdentityEvidenceSource.LOCAL_UNLOCK)


def _scoped_registry(now: list[datetime]) -> SessionIdentityRegistry:
    return SessionIdentityRegistry(
        lookup_person=_lookup({42: _person(42)}),
        clock=lambda: now[0],
        ttl=timedelta(minutes=5),
    )


def test_a_token_issued_for_one_scope_is_refused_for_another_and_survives() -> None:
    """Presenting a grant to the wrong operation never burns it (ADR-0015, Plan 0051)."""
    now = [_NOW]
    registry = _scoped_registry(now)
    token = registry.issue_for_person(
        _person(42), source=IdentityEvidenceSource.LOCAL_UNLOCK, scope="read"
    )

    assert registry.consume_evidence(token, scope="admin") is None
    assert registry.evidence_for(token, scope="admin") is None

    assert registry.evidence_for(token, scope="read") is not None
    assert registry.consume_evidence(token, scope="read") is not None
    assert registry.consume_evidence(token, scope="read") is None


def test_evidence_for_never_consumes_and_respects_the_scope() -> None:
    now = [_NOW]
    registry = _scoped_registry(now)
    token = registry.issue_for_person(
        _person(42), source=IdentityEvidenceSource.LOCAL_UNLOCK, scope="read"
    )

    assert registry.evidence_for(token, scope="read") is not None
    assert registry.evidence_for(token, scope="read") is not None
    assert registry.evidence_for(token) is not None  # no scope asked: legacy behaviour


def test_a_token_without_a_recorded_scope_is_refused_when_a_scope_is_required() -> None:
    now = [_NOW]
    registry = _scoped_registry(now)
    token = registry.select_person(42)
    assert token is not None

    assert registry.consume_evidence(token, scope="read") is None
    assert registry.consume_evidence(token) is not None  # unscoped callers are unchanged


def test_an_expired_scoped_token_is_gone_for_every_scope() -> None:
    now = [_NOW]
    registry = _scoped_registry(now)
    token = registry.issue_for_person(
        _person(42), source=IdentityEvidenceSource.LOCAL_UNLOCK, scope="read"
    )

    now[0] = _NOW + timedelta(minutes=6)

    assert registry.consume_evidence(token, scope="read") is None
    assert registry.evidence_for(token) is None


def test_clearing_a_token_forgets_its_scope() -> None:
    now = [_NOW]
    registry = _scoped_registry(now)
    token = registry.issue_for_person(
        _person(42), source=IdentityEvidenceSource.LOCAL_UNLOCK, scope="read"
    )

    registry.clear(token)

    assert registry.evidence_for(token, scope="read") is None
    assert registry.consume_evidence(token, scope="read") is None


def test_a_scoped_token_cannot_be_spent_by_a_caller_that_names_no_scope() -> None:
    """Spending fails closed: a grant bound to an operation is never redeemed unscoped."""
    now = [_NOW]
    registry = _scoped_registry(now)
    token = registry.issue_for_person(
        _person(42), source=IdentityEvidenceSource.LOCAL_UNLOCK, scope="read"
    )

    assert registry.consume_evidence(token) is None
    assert registry.evidence_for(token, scope="read") is not None  # refused, not spent
    assert registry.consume_evidence(token, scope="read") is not None


# --- Plan 0060: the evidence carries the scope of its grant and whether it was spent ----------


def test_issued_evidence_carries_its_scope_and_is_unspent_until_consumed() -> None:
    now = [_NOW]
    registry = _scoped_registry(now)
    token = registry.issue_for_person(
        _person(42), source=IdentityEvidenceSource.LOCAL_UNLOCK, scope="read"
    )

    peeked = registry.evidence_for(token, scope="read")
    assert peeked is not None
    assert (peeked.grant_scope, peeked.grant_spent) == ("read", False)

    spent = registry.consume_evidence(token, scope="read")
    assert spent is not None
    assert (spent.grant_scope, spent.grant_spent) == ("read", True)
    assert spent.evidence_id == peeked.evidence_id
    assert peeked.grant_spent is False  # the object peeked earlier is never mutated


def test_a_grant_issued_without_a_scope_carries_none_and_a_selection_is_not_a_grant() -> None:
    now = [_NOW]
    registry = _scoped_registry(now)
    unscoped = registry.issue_for_person(_person(42), source=IdentityEvidenceSource.LOCAL_UNLOCK)
    selected = registry.select_person(42)
    assert selected is not None

    unscoped_evidence = registry.consume_evidence(unscoped)
    selection_evidence = registry.evidence_for(selected)

    assert unscoped_evidence is not None
    assert (unscoped_evidence.grant_scope, unscoped_evidence.grant_spent) == (None, True)
    assert selection_evidence is not None
    assert (selection_evidence.grant_scope, selection_evidence.grant_spent) == (None, False)
