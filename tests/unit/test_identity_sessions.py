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
