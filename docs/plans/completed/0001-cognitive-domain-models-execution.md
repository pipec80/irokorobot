# Cognitive domain models execution runbook

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this runbook task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Plan 0001's immutable, pure cognitive domain models with
observed test-driven development and no integration into existing runtime paths.

**Architecture:** `server.cognition.models` is a self-contained Pydantic v2
value-object module. It owns domain enums, validation, and generic envelopes;
`server.cognition.__init__` exports that public vocabulary. No route, provider,
database, hardware, memory, or settings module participates in model creation.

**Tech stack:** Python 3.12, Pydantic 2.13, pytest, mypy, Ruff, and the root
`justfile` commands.

## Global constraints

- The canonical authority is [Plan 0001](0001-cognitive-domain-models.md), not
  this execution runbook.
- Permitted implementation files are exactly `server/src/server/cognition/__init__.py`,
  `server/src/server/cognition/models.py`, `tests/unit/test_cognitive_models.py`,
  and the canonical plan's status line after final verification.
- Preserve integer IDs for SQLite entity and fact references; use UUID only for
  envelopes, observations, events, and correlation.
- Every public class and enum has a Google-style docstring; production models
  use no unqualified `Any` and perform no I/O.
- All datetimes are timezone-aware and serialize normalized UTC values.
- Use `ConfigDict(frozen=True, extra="forbid")`; exposed collections are tuples
  or frozensets, never mutable lists or sets.
- Do not add dependencies, alter existing routes or audio contracts, invoke a
  provider, or use a production multi-agent architecture.
- Execute tasks serially. A fresh worker owns its task's changes; the primary
  agent completes review before dispatching the next worker. Workers must not
  revert prior accepted changes.

## Worker protocol

- [ ] Dispatch each task with `superpowers:subagent-driven-development`.
- [ ] Give the worker only that task's files and the interfaces listed there.
- [ ] Require the worker to record the observed RED command and focused GREEN
  command in its handoff.
- [ ] Review the worker's diff for scope, type safety, and contract compliance.
- [ ] Run the task's focused command in the primary session before accepting it.
- [ ] If workers are unavailable, use `superpowers:executing-plans` sequentially
  with the same RED, GREEN, review, and handoff checkpoints.

---

### Task 1: Establish the pure cognition package and confidence vocabulary

**Files:**

- Create: `server/src/server/cognition/__init__.py`
- Create: `server/src/server/cognition/models.py`
- Create: `tests/unit/test_cognitive_models.py`

**Interfaces:**

- Produces `KnowledgeStatus`, `ConfidenceBasis`, `AuthorizationStatus`,
  `ObservationModality`, and `Confidence` from `server.cognition.models`.
- Produces the same five symbols from `server.cognition`.
- Later tasks import only from `server.cognition.models` while testing and add
  re-export assertions to the same test file.

- [ ] **Step 1: Write the failing enum and confidence tests.**

```python
import pytest
from pydantic import ValidationError
from server.cognition.models import Confidence, ConfidenceBasis, KnowledgeStatus


def test_knowledge_status_serializes_to_contract_values() -> None:
    assert [item.value for item in KnowledgeStatus] == [
        "known",
        "unknown",
        "ambiguous",
        "contradictory",
        "unauthorized",
    ]


def test_confidence_accepts_inclusive_bounds_and_rejects_outside_range() -> None:
    assert Confidence(score=0.0, basis=ConfidenceBasis.MEASURED, calibrated=True).score == 0.0
    assert Confidence(score=1.0, basis=ConfidenceBasis.ASSERTED, calibrated=False).score == 1.0
    with pytest.raises(ValidationError):
        Confidence(score=1.01, basis=ConfidenceBasis.ESTIMATED, calibrated=False)
```

- [ ] **Step 2: Run RED.**

Run: `uv run pytest -n0 tests/unit/test_cognitive_models.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'server.cognition'`.

- [ ] **Step 3: Implement the smallest vocabulary.**

```python
class KnowledgeStatus(str, Enum):
    """Categorical evidence outcome for a cognitive result."""

    KNOWN = "known"
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"
    CONTRADICTORY = "contradictory"
    UNAUTHORIZED = "unauthorized"


class ConfidenceBasis(str, Enum):
    """Origin category for a confidence score."""

    MEASURED = "measured"
    ESTIMATED = "estimated"
    ASSERTED = "asserted"
    NOT_APPLICABLE = "not_applicable"


class AuthorizationStatus(str, Enum):
    """Explicit policy result for an intended use."""

    ALLOWED = "allowed"
    DENIED = "denied"
    REQUIRES_CONFIRMATION = "requires_confirmation"


class ObservationModality(str, Enum):
    """Input modality of adapter evidence."""

    TEXT = "text"
    AUDIO = "audio"
    VISUAL = "visual"
    SENSOR = "sensor"
    SYSTEM = "system"


class Confidence(BaseModel):
    """Evidence quality without authorization semantics."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    score: float = Field(ge=0.0, le=1.0)
    basis: ConfidenceBasis
    calibrated: bool
    reason: str | None = None
```

Define the remaining three `str, Enum` types with exactly the lowercase values
from `cognitive-contracts.md`, then re-export all five public symbols from
`server.cognition.__init__`.

- [ ] **Step 4: Run GREEN.**

Run: `uv run pytest -n0 tests/unit/test_cognitive_models.py -q`
Expected: PASS for enum serialization and inclusive confidence bounds.

- [ ] **Step 5: Review and commit task scope.**

Run: `uv run ruff check server/src/server/cognition tests/unit/test_cognitive_models.py`
Run: `uv run ruff format --check server/src/server/cognition tests/unit/test_cognitive_models.py`
Commit: `feat(cognition): add confidence domain models`

---

### Task 2: Add authorization and UTC datetime invariants

**Files:**

- Modify: `server/src/server/cognition/models.py`
- Modify: `tests/unit/test_cognitive_models.py`

**Interfaces:**

- Consumes `AuthorizationStatus` and `Confidence` from Task 1.
- Produces immutable `AuthorizationDecision` with `decision`, `action`,
  `data_categories`, `policy_id`, `reason`, and `evaluated_at`.
- Later tasks reuse the same aware-datetime validation helper for every
  envelope timestamp.

- [ ] **Step 1: Write the failing authorization tests.**

```python
from datetime import UTC, datetime
from pydantic import ValidationError
from server.cognition.models import AuthorizationDecision, AuthorizationStatus


def test_authorization_decision_requires_aware_utc_time_and_is_immutable() -> None:
    decision = AuthorizationDecision(
        decision=AuthorizationStatus.ALLOWED,
        action="memory.read",
        data_categories=frozenset({"household"}),
        policy_id="local-v1",
        reason="authorized household access",
        evaluated_at=datetime.now(UTC),
    )
    assert decision.data_categories == frozenset({"household"})
    with pytest.raises(ValidationError):
        AuthorizationDecision.model_validate(
            {**decision.model_dump(), "evaluated_at": datetime(2026, 8, 4)}
        )
```

- [ ] **Step 2: Run RED.**

Run: `uv run pytest -n0 tests/unit/test_cognitive_models.py::test_authorization_decision_requires_aware_utc_time_and_is_immutable -q`
Expected: FAIL with `ImportError` because `AuthorizationDecision` does not yet exist.

- [ ] **Step 3: Implement explicit authorization and reusable timestamps.**

```python
from pydantic import field_validator


def _require_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


class AuthorizationDecision(BaseModel):
    """Permission decision scoped to one action and data category set."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    decision: AuthorizationStatus
    action: str
    data_categories: frozenset[str]
    policy_id: str
    reason: str
    evaluated_at: datetime

    _validate_evaluated_at = field_validator("evaluated_at")(_require_aware_utc)
```

- [ ] **Step 4: Run GREEN.**

Run: `uv run pytest -n0 tests/unit/test_cognitive_models.py::test_authorization_decision_requires_aware_utc_time_and_is_immutable -q`
Expected: PASS; naive datetimes are rejected and accepted offsets normalize to UTC.

- [ ] **Step 5: Review and commit task scope.**

Run: `uv run ruff check server/src/server/cognition tests/unit/test_cognitive_models.py`
Commit: `feat(cognition): add authorization decision model`

---

### Task 3: Add typed observation and event envelopes

**Files:**

- Modify: `server/src/server/cognition/models.py`
- Modify: `tests/unit/test_cognitive_models.py`

**Interfaces:**

- Consumes `Confidence`, `KnowledgeStatus`, and `_require_aware_utc`.
- Produces generic `Observation[PayloadT]` and `CognitiveEvent[PayloadT]`.
- `Observation` exposes UUID `observation_id`, typed payload, source,
  modality, `captured_at`, `received_at`, `confidence`, and optional
  `expires_at`.
- `CognitiveEvent` exposes UUID event/correlation IDs and optional integer
  `subject_id`; it never introduces a UUID person identifier.

- [ ] **Step 1: Write failing round-trip and identifier tests.**

```python
from datetime import UTC, datetime
from uuid import uuid4
from pydantic import BaseModel
from server.cognition.models import (
    CognitiveEvent,
    Confidence,
    ConfidenceBasis,
    Observation,
    ObservationModality,
)


class TextPayload(BaseModel):
    text: str


def test_observation_round_trips_with_uuid_and_utc_timestamps() -> None:
    observed = Observation[TextPayload](
        observation_id=uuid4(),
        schema_version=1,
        source="web.chat",
        modality=ObservationModality.TEXT,
        captured_at=datetime.now(UTC),
        received_at=datetime.now(UTC),
        payload=TextPayload(text="hola"),
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.ASSERTED, calibrated=False),
    )
    assert Observation[TextPayload].model_validate_json(observed.model_dump_json()) == observed


def test_event_uses_integer_subject_id_and_uuid_correlation() -> None:
    event = CognitiveEvent[TextPayload](
        event_id=uuid4(),
        schema_version=1,
        event_type="text.received",
        occurred_at=datetime.now(UTC),
        recorded_at=datetime.now(UTC),
        source="web.chat",
        correlation_id=uuid4(),
        causation_id=None,
        subject_id=12,
        payload=TextPayload(text="hola"),
    )
    assert event.subject_id == 12
```

- [ ] **Step 2: Run RED.**

Run: `uv run pytest -n0 tests/unit/test_cognitive_models.py -q`
Expected: FAIL with `ImportError` for `Observation` and `CognitiveEvent`.

- [ ] **Step 3: Implement generic immutable envelopes.**

```python
PayloadT = TypeVar("PayloadT", bound=BaseModel)


class Observation(BaseModel, Generic[PayloadT]):
    """Immutable, timestamped adapter evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    observation_id: UUID
    schema_version: int = Field(ge=1)
    source: str
    modality: ObservationModality
    captured_at: datetime
    received_at: datetime
    payload: PayloadT
    confidence: Confidence
    expires_at: datetime | None = None
```

Apply `_require_aware_utc` to every datetime field in both envelope models.
Give `CognitiveEvent` the exact fields described in the canonical contract,
including `subject_id: int | None`, `correlation_id: UUID`, and
`causation_id: UUID | None`.

- [ ] **Step 4: Run GREEN.**

Run: `uv run pytest -n0 tests/unit/test_cognitive_models.py -q`
Expected: PASS; JSON round-trip preserves UUIDs, payload, modality, and UTC
timestamps, while naive envelope datetimes raise `ValidationError`.

- [ ] **Step 5: Review and commit task scope.**

Run: `uv run ruff check server/src/server/cognition tests/unit/test_cognitive_models.py`
Commit: `feat(cognition): add observation and event envelopes`

---

### Task 4: Add active context, public exports, and import-boundary checks

**Files:**

- Modify: `server/src/server/cognition/__init__.py`
- Modify: `server/src/server/cognition/models.py`
- Modify: `tests/unit/test_cognitive_models.py`

**Interfaces:**

- Consumes `AuthorizationDecision`, `Confidence`, `KnowledgeStatus`, UUID, and
  the integer entity/fact identifier boundary from earlier tasks.
- Produces immutable `ActiveContext` with required authorization.
- Produces package-level re-exports of every public enum and model in Plan 0001.

- [ ] **Step 1: Write failing context and purity tests.**

```python
import inspect
from datetime import UTC, datetime
from uuid import uuid4
import pytest
from pydantic import ValidationError
import server.cognition.models as models
from server.cognition.models import ActiveContext


def _allowed_authorization() -> models.AuthorizationDecision:
    return models.AuthorizationDecision(
        decision=models.AuthorizationStatus.ALLOWED,
        action="memory.read",
        data_categories=frozenset({"household"}),
        policy_id="local-v1",
        reason="authorized household access",
        evaluated_at=datetime.now(UTC),
    )


def test_active_context_keeps_uuid_evidence_and_integer_fact_ids_immutable() -> None:
    context = ActiveContext(
        context_id=uuid4(),
        conversation_id="web-a",
        created_at=datetime.now(UTC),
        active_person_id=12,
        observation_ids=(uuid4(),),
        fact_ids=(7, 8),
        knowledge_status=models.KnowledgeStatus.KNOWN,
        confidence=models.Confidence(
            score=1.0, basis=models.ConfidenceBasis.MEASURED, calibrated=True
        ),
        authorization=_allowed_authorization(),
    )
    assert context.fact_ids == (7, 8)
    with pytest.raises(ValidationError):
        ActiveContext.model_validate(
            {key: value for key, value in context.model_dump().items() if key != "authorization"}
        )


def test_models_module_has_no_runtime_adapter_imports() -> None:
    source = inspect.getsource(models)
    for forbidden in (
        "server.db",
        "server.llm",
        "server.settings",
        "server.routers",
        "server.vision",
    ):
        assert forbidden not in source
```

- [ ] **Step 2: Run RED.**

Run: `uv run pytest -n0 tests/unit/test_cognitive_models.py -q`
Expected: FAIL with `ImportError` for `ActiveContext`.

- [ ] **Step 3: Implement context and exports.**

```python
class ActiveContext(BaseModel):
    """Immutable, authorized evidence snapshot for one cognitive turn."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    context_id: UUID
    conversation_id: str
    created_at: datetime
    active_person_id: int | None
    observation_ids: tuple[UUID, ...]
    fact_ids: tuple[int, ...]
    knowledge_status: KnowledgeStatus
    confidence: Confidence
    authorization: AuthorizationDecision
```

Validate `created_at` through `_require_aware_utc`. Re-export all public
models and enums from `server.cognition.__init__`; do not re-export internal
helpers.

- [ ] **Step 4: Run GREEN.**

Run: `uv run pytest -n0 tests/unit/test_cognitive_models.py -q`
Expected: PASS; missing authorization fails validation, IDs preserve their
types, and the source has no prohibited runtime adapter imports.

- [ ] **Step 5: Review and commit task scope.**

Run: `uv run ruff check server/src/server/cognition tests/unit/test_cognitive_models.py`
Run: `uv run ruff format --check server/src/server/cognition tests/unit/test_cognitive_models.py`
Commit: `feat(cognition): add active context model`

---

### Task 5: Complete Plan 0001's full verification and status handoff

**Files:**

- Modify: `tests/unit/test_cognitive_models.py`
- Modify after all checks pass: `docs/plans/0001-cognitive-domain-models.md`

**Interfaces:**

- Consumes the complete public API from Tasks 1 through 4.
- Produces final offline evidence that construction has no I/O, public exports
  exist, and all canonical behavioral requirements are covered.

- [ ] **Step 1: Write the final failing boundary tests.**

```python
from datetime import UTC, datetime
from uuid import uuid4
from pydantic import BaseModel
from server.cognition import (
    ActiveContext,
    AuthorizationDecision,
    CognitiveEvent,
    Confidence,
    ConfidenceBasis,
    Observation,
    ObservationModality,
)


class TextPayload(BaseModel):
    text: str


def _make_observation() -> Observation[TextPayload]:
    return Observation[TextPayload](
        observation_id=uuid4(),
        schema_version=1,
        source="web.chat",
        modality=ObservationModality.TEXT,
        captured_at=datetime.now(UTC),
        received_at=datetime.now(UTC),
        payload=TextPayload(text="hola"),
        confidence=Confidence(score=1.0, basis=ConfidenceBasis.ASSERTED, calibrated=False),
    )


def test_public_package_exports_every_canonical_model() -> None:
    assert all((ActiveContext, AuthorizationDecision, CognitiveEvent, Confidence, Observation))


def test_model_construction_has_no_io(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_io(*args: object, **kwargs: object) -> None:
        raise AssertionError("domain construction performed I/O")

    monkeypatch.setattr("builtins.open", fail_io)
    _make_observation()
```

- [ ] **Step 2: Run RED.**

Run: `uv run pytest -n0 tests/unit/test_cognitive_models.py -q`
Expected: FAIL until the public exports and test helpers are complete.

- [ ] **Step 3: Complete only missing tests or model declarations.**

Do not add integration code. Make the final test helpers construct only
in-memory Pydantic payloads. Ensure the test suite covers each item in
Plan 0001's Behavioral requirements 1 through 8, including lower-case enums,
all datetime fields, JSON round trips, integer IDs, mandatory authorization,
and prohibited adapter imports.

- [ ] **Step 4: Run focused GREEN and full repository verification.**

Run: `uv run pytest -n0 tests/unit/test_cognitive_models.py -q`
Expected: PASS.

Run in this exact order:

```powershell
just lint
just typecheck
just test
```

Expected: all three commands pass without changing dependencies or unrelated
files. If any command identifies an out-of-scope defect, stop and report it;
do not broaden this plan.

- [ ] **Step 5: Update status, review, and commit.**

After all commands pass, change only Plan 0001's status from `Ready` to
`Complete`. Review `git diff --check`, `git diff --stat`, and `git status
--short --branch` to prove no file outside canonical scope changed.

Commit: `feat(cognition): add typed cognitive domain models`

## Plan self-review

- [ ] Each canonical behavioral requirement maps to Tasks 1 through 5.
- [ ] Every task has explicit file ownership, RED, GREEN, and review steps.
- [ ] No task expands Plan 0001's implementation scope or adds a dependency.
- [ ] Identifiers, enums, fields, and UTC validation match
  `cognitive-contracts.md`.
- [ ] No execution step depends on ignored `docs/local/` content or chat history.
