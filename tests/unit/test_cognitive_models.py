"""Tests for the pure cognitive domain vocabulary."""

from datetime import UTC, datetime, timedelta, timezone
import inspect
from typing import Never
from uuid import UUID, uuid4

from pydantic import BaseModel, ValidationError
import pytest
from server.cognition import (
    ActiveContext,
    ActivePersonContext,
    ActivePersonStatus,
    AuthorizationAction,
    AuthorizationDecision,
    AuthorizationRequest,
    AuthorizationStatus,
    CognitiveController,
    CognitiveEvent,
    Confidence,
    ConfidenceBasis,
    ConsentStatus,
    DataSensitivity,
    DataVisibility,
    HouseholdKnowledgeTools,
    HouseholdRole,
    HouseholdToolName,
    HouseholdToolResult,
    IdentityEvidence,
    IdentityEvidenceSource,
    InformationNeed,
    KnowledgeStatus,
    Observation,
    ObservationModality,
    PreferencePredicate,
    ResponseClaim,
    ResponsePlan,
    ResponseSource,
    TextTurnPayload,
    ToolResult,
    evaluate_authorization,
    models,
)

from server import cognition


class TextPayload(BaseModel):
    """Text carried by a cognitive envelope in tests."""

    text: str


def _confidence() -> Confidence:
    """Build a confidence value for envelope test fixtures."""
    return Confidence(
        score=1.0,
        basis=ConfidenceBasis.ASSERTED,
        calibrated=False,
    )


def _allowed_authorization() -> AuthorizationDecision:
    """Build an authorization decision for active-context test fixtures."""
    return AuthorizationDecision(
        decision=AuthorizationStatus.ALLOWED,
        action=AuthorizationAction.READ_HOUSEHOLD_DATA,
        data_categories=frozenset({"household"}),
        policy_id="local-v1",
        reason="authorized household access",
        evaluated_at=datetime(2026, 8, 4, 12, tzinfo=UTC),
        correlation_id=UUID("44444444-4444-4444-4444-444444444444"),
    )


def _active_context_values() -> dict[str, object]:
    """Build valid active-context input values with typed identifiers."""
    return {
        "context_id": UUID("22222222-2222-2222-2222-222222222222"),
        "conversation_id": "web-a",
        "created_at": datetime(2026, 8, 4, 12, tzinfo=UTC),
        "active_person_id": 12,
        "observation_ids": (UUID("33333333-3333-3333-3333-333333333333"),),
        "fact_ids": (7, 8),
        "knowledge_status": KnowledgeStatus.KNOWN,
        "confidence": _confidence(),
        "authorization": _allowed_authorization(),
    }


def _observation_values() -> dict[str, object]:
    """Build valid observation input values with UTC timestamps."""
    return {
        "observation_id": UUID("11111111-1111-1111-1111-111111111111"),
        "schema_version": 1,
        "source": "web.chat",
        "modality": ObservationModality.TEXT,
        "captured_at": datetime(2026, 8, 4, 12, tzinfo=UTC),
        "received_at": datetime(2026, 8, 4, 12, 1, tzinfo=UTC),
        "payload": TextPayload(text="hola"),
        "confidence": _confidence(),
    }


def _event_values() -> dict[str, object]:
    """Build valid cognitive-event input values with UTC timestamps."""
    return {
        "event_id": uuid4(),
        "schema_version": 1,
        "event_type": "text.received",
        "occurred_at": datetime(2026, 8, 4, 12, tzinfo=UTC),
        "recorded_at": datetime(2026, 8, 4, 12, 1, tzinfo=UTC),
        "source": "web.chat",
        "correlation_id": uuid4(),
        "causation_id": None,
        "subject_id": 12,
        "payload": TextPayload(text="hola"),
    }


@pytest.mark.parametrize(
    "enum_type, expected_values",
    [
        (
            KnowledgeStatus,
            ["known", "unknown", "ambiguous", "contradictory", "unauthorized"],
        ),
        (ConfidenceBasis, ["measured", "estimated", "asserted", "not_applicable"]),
        (AuthorizationStatus, ["allowed", "denied", "requires_confirmation"]),
        (
            AuthorizationAction,
            [
                "general_conversation",
                "read_household_data",
                "execute_household_tool",
                "propose_memory",
                "commit_memory",
                "manage_household_role",
                "enroll_biometric",
                "export_household_data",
                "delete_household_data",
                "consider_cloud_escalation",
                "propose_physical_action",
            ],
        ),
        (ObservationModality, ["text", "audio", "visual", "sensor", "system"]),
    ],
)
def test_enums_serialize_to_exact_lowercase_contract_values(
    enum_type: type[
        KnowledgeStatus
        | ConfidenceBasis
        | AuthorizationStatus
        | AuthorizationAction
        | ObservationModality
    ],
    expected_values: list[str],
) -> None:
    """Every cognitive enum preserves its wire-level contract values."""
    assert [item.value for item in enum_type] == expected_values


def test_confidence_accepts_inclusive_bounds_and_rejects_outside_range() -> None:
    """Confidence accepts inclusive bounds and rejects out-of-range scores."""
    assert (
        Confidence(
            score=0.0,
            basis=ConfidenceBasis.MEASURED,
            calibrated=True,
        ).score
        == 0.0
    )
    assert (
        Confidence(
            score=1.0,
            basis=ConfidenceBasis.ASSERTED,
            calibrated=False,
        ).score
        == 1.0
    )
    for invalid_score in (-0.01, 1.01):
        with pytest.raises(ValidationError):
            Confidence(
                score=invalid_score,
                basis=ConfidenceBasis.ESTIMATED,
                calibrated=False,
            )


def test_confidence_forbids_extra_values_and_is_immutable() -> None:
    """Confidence rejects uncontracted fields and cannot grant authorization."""
    confidence = _confidence()

    with pytest.raises(ValidationError):
        confidence.score = 0.5

    with pytest.raises(ValidationError):
        Confidence.model_validate({**confidence.model_dump(), "authorization": "allowed"})


def test_authorization_decision_requires_aware_utc_time_and_is_immutable() -> None:
    """Authorization decisions retain immutable categories and reject naive times."""
    decision = AuthorizationDecision(
        decision=AuthorizationStatus.ALLOWED,
        action=AuthorizationAction.READ_HOUSEHOLD_DATA,
        data_categories=frozenset({"household"}),
        policy_id="local-v1",
        reason="authorized household access",
        evaluated_at=datetime.now(UTC),
        correlation_id=UUID("44444444-4444-4444-4444-444444444444"),
    )

    assert decision.data_categories == frozenset({"household"})
    assert isinstance(decision.data_categories, frozenset)

    with pytest.raises(ValidationError):
        decision.action = AuthorizationAction.COMMIT_MEMORY

    with pytest.raises(ValidationError):
        AuthorizationDecision.model_validate(
            {**decision.model_dump(), "evaluated_at": datetime(2026, 8, 4)}
        )

    with pytest.raises(ValidationError):
        AuthorizationDecision.model_validate({**decision.model_dump(), "unexpected": "value"})


def test_authorization_decision_normalizes_aware_offsets_to_utc() -> None:
    """Authorization decisions convert aware timestamps to UTC."""
    decision = AuthorizationDecision(
        decision=AuthorizationStatus.ALLOWED,
        action=AuthorizationAction.READ_HOUSEHOLD_DATA,
        data_categories=frozenset({"household"}),
        policy_id="local-v1",
        reason="authorized household access",
        evaluated_at=datetime(2026, 8, 4, 3, tzinfo=timezone(timedelta(hours=-4))),
        correlation_id=UUID("44444444-4444-4444-4444-444444444444"),
    )

    assert decision.evaluated_at == datetime(2026, 8, 4, 7, tzinfo=UTC)
    assert decision.evaluated_at.tzinfo is UTC


def test_observation_round_trips_uuid_payload_modality_and_utc_timestamps() -> None:
    """Observations retain typed envelope data through JSON serialization."""
    observed = Observation[TextPayload].model_validate(_observation_values())

    round_tripped = Observation[TextPayload].model_validate_json(observed.model_dump_json())

    assert round_tripped.observation_id == observed.observation_id
    assert round_tripped.payload == TextPayload(text="hola")
    assert round_tripped.modality is ObservationModality.TEXT
    assert round_tripped.captured_at == datetime(2026, 8, 4, 12, tzinfo=UTC)
    assert round_tripped.received_at == datetime(2026, 8, 4, 12, 1, tzinfo=UTC)


def test_cognitive_event_accepts_integer_subject_id_and_uuid_identifiers() -> None:
    """Events use SQLite integer subjects and UUID envelope identifiers."""
    values = _event_values()
    event = CognitiveEvent[TextPayload].model_validate(values)

    assert event.subject_id == 12
    assert event.event_id == values["event_id"]
    assert event.correlation_id == values["correlation_id"]


@pytest.mark.parametrize("timestamp_field", ["captured_at", "received_at", "expires_at"])
def test_observation_rejects_naive_datetime_fields(timestamp_field: str) -> None:
    """Observations reject naive required and optional datetime values."""
    values = _observation_values()
    values[timestamp_field] = datetime(2026, 8, 4, 12)

    with pytest.raises(ValidationError):
        Observation[TextPayload].model_validate(values)


@pytest.mark.parametrize("timestamp_field", ["occurred_at", "recorded_at"])
def test_cognitive_event_rejects_naive_datetime_fields(timestamp_field: str) -> None:
    """Events reject naive datetime values."""
    values = _event_values()
    values[timestamp_field] = datetime(2026, 8, 4, 12)

    with pytest.raises(ValidationError):
        CognitiveEvent[TextPayload].model_validate(values)


def test_observation_normalizes_aware_offset_timestamp_to_utc() -> None:
    """Observations convert aware non-UTC timestamps to UTC."""
    values = _observation_values()
    values["captured_at"] = datetime(
        2026,
        8,
        4,
        8,
        tzinfo=timezone(timedelta(hours=-4)),
    )

    observed = Observation[TextPayload].model_validate(values)

    assert observed.captured_at == datetime(2026, 8, 4, 12, tzinfo=UTC)
    assert observed.captured_at.tzinfo is UTC


def test_active_context_preserves_authorized_uuid_evidence_and_integer_fact_ids() -> None:
    """Active context keeps the evidence and SQLite fact-ID boundaries."""
    context = ActiveContext.model_validate(_active_context_values())

    assert context.observation_ids == (UUID("33333333-3333-3333-3333-333333333333"),)
    assert context.fact_ids == (7, 8)
    assert isinstance(context.observation_ids, tuple)
    assert isinstance(context.fact_ids, tuple)

    with pytest.raises(ValidationError):
        context.fact_ids += (9,)


def test_active_context_requires_authorization() -> None:
    """Active context cannot be constructed without a policy decision."""
    values = _active_context_values()
    del values["authorization"]

    with pytest.raises(ValidationError):
        ActiveContext.model_validate(values)


def test_active_context_keeps_confidence_and_authorization_as_separate_evidence() -> None:
    """High confidence does not convert a denied decision into authorization."""
    values = _active_context_values()
    values["authorization"] = AuthorizationDecision(
        decision=AuthorizationStatus.DENIED,
        action=AuthorizationAction.READ_HOUSEHOLD_DATA,
        data_categories=frozenset({"household"}),
        policy_id="local-v1",
        reason="consent absent",
        evaluated_at=datetime(2026, 8, 4, 12, tzinfo=UTC),
        correlation_id=UUID("44444444-4444-4444-4444-444444444444"),
    )

    context = ActiveContext.model_validate(values)

    assert context.confidence.score == 1.0
    assert context.authorization.decision is AuthorizationStatus.DENIED


def test_active_context_rejects_naive_created_at() -> None:
    """Active context rejects a naive turn timestamp."""
    values = _active_context_values()
    values["created_at"] = datetime(2026, 8, 4, 12)

    with pytest.raises(ValidationError):
        ActiveContext.model_validate(values)


def test_authorization_request_is_immutable_and_rejects_untyped_categories() -> None:
    """Requests bind a closed action and scope without carrying protected content."""
    actor = ActivePersonContext(
        person_id=12,
        display_name="Ada",
        status=ActivePersonStatus.IDENTIFIED,
        confidence=_confidence(),
        role=HouseholdRole.OWNER,
        evidence=(),
        resolved_at=datetime(2026, 8, 4, 12, tzinfo=UTC),
    )
    request = AuthorizationRequest(
        actor=actor,
        action=AuthorizationAction.READ_HOUSEHOLD_DATA,
        target_person_id=12,
        visibility=frozenset({DataVisibility.PERSONAL}),
        sensitivity=frozenset({DataSensitivity.NORMAL}),
        consent=ConsentStatus.NOT_REQUIRED,
        correlation_id=UUID("55555555-5555-5555-5555-555555555555"),
        requested_at=datetime(2026, 8, 4, 12, tzinfo=UTC),
    )

    with pytest.raises(ValidationError):
        request.action = AuthorizationAction.COMMIT_MEMORY
    with pytest.raises(ValidationError):
        AuthorizationRequest.model_validate(
            {**request.model_dump(), "visibility": frozenset({"unclassified"})}
        )


@pytest.mark.parametrize(
    "field_name, invalid_value",
    [
        ("context_id", "22222222-2222-2222-2222-222222222222"),
        ("observation_ids", ("33333333-3333-3333-3333-333333333333",)),
        ("active_person_id", "12"),
        ("active_person_id", True),
        ("fact_ids", ("7",)),
        ("fact_ids", (True,)),
    ],
)
def test_active_context_rejects_coerced_identity_values(
    field_name: str,
    invalid_value: object,
) -> None:
    """Active context rejects string and boolean values at identity boundaries."""
    values = _active_context_values()
    values[field_name] = invalid_value

    with pytest.raises(ValidationError):
        ActiveContext.model_validate(values)


def test_active_context_round_trips_typed_identifiers_through_json() -> None:
    """Active context accepts JSON's serialized UUID and integer values."""
    context = ActiveContext.model_validate(_active_context_values())

    round_tripped = ActiveContext.model_validate_json(context.model_dump_json())

    assert round_tripped.context_id == context.context_id
    assert round_tripped.observation_ids == context.observation_ids
    assert round_tripped.active_person_id == 12
    assert round_tripped.fact_ids == (7, 8)


def test_models_module_has_no_runtime_adapter_imports() -> None:
    """Domain models remain independent from runtime adapters."""
    source = inspect.getsource(models)

    for forbidden in (
        "server.db",
        "server.llm",
        "server.settings",
        "server.routers",
        "server.stt",
        "server.text_turn",
        "server.tts",
        "server.vision",
        "httpx",
        "requests",
    ):
        assert forbidden not in source


def test_observation_construction_performs_no_file_io(monkeypatch: pytest.MonkeyPatch) -> None:
    """Constructing an in-memory observation does not access the filesystem."""

    def deny_open(*args: object, **kwargs: object) -> Never:
        """Fail if construction unexpectedly attempts filesystem I/O."""
        raise AssertionError("domain model construction must not open files")

    monkeypatch.setattr("builtins.open", deny_open)

    observed = Observation[TextPayload].model_validate(_observation_values())

    assert observed.payload.text == "hola"


def test_cognition_package_reexports_every_public_domain_type() -> None:
    """The package exposes every public type while hiding validation helpers."""
    expected_exports = {
        "ActiveContext": ActiveContext,
        "ActivePersonContext": ActivePersonContext,
        "ActivePersonStatus": ActivePersonStatus,
        "AuthorizationAction": AuthorizationAction,
        "AuthorizationDecision": AuthorizationDecision,
        "AuthorizationRequest": AuthorizationRequest,
        "AuthorizationStatus": AuthorizationStatus,
        "ConsentStatus": ConsentStatus,
        "CognitiveController": CognitiveController,
        "CognitiveEvent": CognitiveEvent,
        "Confidence": Confidence,
        "ConfidenceBasis": ConfidenceBasis,
        "DataSensitivity": DataSensitivity,
        "DataVisibility": DataVisibility,
        "HouseholdKnowledgeTools": HouseholdKnowledgeTools,
        "HouseholdRole": HouseholdRole,
        "HouseholdToolName": HouseholdToolName,
        "HouseholdToolResult": HouseholdToolResult,
        "IdentityEvidence": IdentityEvidence,
        "IdentityEvidenceSource": IdentityEvidenceSource,
        "KnowledgeStatus": KnowledgeStatus,
        "Observation": Observation,
        "ObservationModality": ObservationModality,
        "PreferencePredicate": PreferencePredicate,
        "InformationNeed": InformationNeed,
        "ResponseClaim": ResponseClaim,
        "ResponsePlan": ResponsePlan,
        "ResponseSource": ResponseSource,
        "TextTurnPayload": TextTurnPayload,
        "ToolResult": ToolResult,
        "evaluate_authorization": evaluate_authorization,
    }

    assert set(cognition.__all__) == set(expected_exports)
    assert all(getattr(cognition, name) is value for name, value in expected_exports.items())
    assert not hasattr(cognition, "_require_aware_utc")
