"""A personal-memory decision is appended to the audit table unchanged (ADR 0019 §6)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from server.cognition.authorization import (
    AuthorizationRequest,
    ConsentStatus,
    DataSensitivity,
    DataVisibility,
    evaluate_authorization,
)
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityAssurance,
    IdentityEvidence,
    IdentityEvidenceSource,
)
from server.cognition.models import (
    AuthorizationAction,
    AuthorizationStatus,
    Confidence,
    ConfidenceBasis,
)
from server.memory.declarative import upsert_entity
from server.memory.household_authorization import record_authorization_decision
from server.settings import settings

from server import db

_AT = datetime(2026, 10, 8, 12, tzinfo=UTC)
_CORRELATION_ID = UUID("44444444-4444-4444-4444-444444444444")


@pytest.fixture
async def audit_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Open a fresh temporary database with every migration applied."""
    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "personal-memory-audit.db")
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield
    await db.close_db()
    db._conn = None


@pytest.mark.integration
@pytest.mark.parametrize(
    "action",
    [
        AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY,
        AuthorizationAction.PROPOSE_PERSONAL_MEMORY,
        AuthorizationAction.CONFIRM_PERSONAL_MEMORY,
        AuthorizationAction.CORRECT_PERSONAL_MEMORY,
        AuthorizationAction.FORGET_PERSONAL_MEMORY,
    ],
)
async def test_each_new_action_is_recorded_with_its_value_and_a_cm1_policy_id(
    audit_db: None, action: AuthorizationAction
) -> None:
    """The audit `action` column is free text: the new values need no migration."""
    owner_id = await upsert_entity(name="Ada", type="person")
    # Forget alone needs a PIN grant spent for it (ADR 0019 §4); the others need none.
    grant = IdentityEvidence(
        evidence_id=UUID("55555555-5555-5555-5555-555555555555"),
        source=IdentityEvidenceSource.LOCAL_UNLOCK,
        candidate_person_id=owner_id,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.ASSERTED, calibrated=True),
        observed_at=_AT,
        reference="session-selection",
        grant_scope="personal_memory_forget",
        grant_spent=True,
    )
    owner = ActivePersonContext(
        person_id=owner_id,
        display_name="Ada",
        status=ActivePersonStatus.IDENTIFIED,
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.ASSERTED, calibrated=False),
        role=HouseholdRole.OWNER,
        evidence=(grant,) if action is AuthorizationAction.FORGET_PERSONAL_MEMORY else (),
        resolved_at=_AT,
        assurance=IdentityAssurance.STRONG,
    )
    request = AuthorizationRequest(
        actor=owner,
        action=action,
        target_person_id=owner_id,
        visibility=frozenset({DataVisibility.PERSONAL}),
        sensitivity=frozenset({DataSensitivity.MEDICAL}),
        consent=ConsentStatus.GRANTED,
        correlation_id=_CORRELATION_ID,
        requested_at=_AT,
    )
    decision = evaluate_authorization(request)

    await record_authorization_decision(request, decision)

    cursor = await db.get_conn().execute(
        "SELECT actor_entity_id, target_entity_id, action, data_categories, decision, policy_id "
        "FROM authorization_audit_events"
    )
    rows = list(await cursor.fetchall())
    await cursor.close()
    assert len(rows) == 1
    actor_id, target_id, stored_action, categories, stored_decision, policy_id = rows[0]
    assert (actor_id, target_id) == (owner_id, owner_id)
    assert stored_action == action.value
    assert categories == "medical,personal"
    assert stored_decision == AuthorizationStatus.ALLOWED.value
    assert policy_id == "cm1.personal-memory.allowed"
