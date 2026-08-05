# Cognitive contracts

> **Status:** Baseline for staged implementation
>
> **Decision:** [ADR-0004](../adr/0004-local-first-cognitive-policy.md)
>
> **Scope:** Domain models only; no orchestration, persistence, providers, or
> hardware integration.

## Purpose

These contracts give Iroko one typed language for inputs, evidence, active
context, confidence, authorization, and cognitive outcomes. Adapters translate
audio, text, images, simulated sensors, and future hardware into these models.
The cognitive core consumes the models without importing camera, microphone,
database, HTTP, Ollama, or cloud-provider details.

Information flows upward as observations and events. Decisions flow downward
as separately authorized requests. Application code never commands hardware
through these domain models.

## Design rules

1. Models are immutable value objects and serialize predictably to JSON.
2. Envelope and correlation identifiers use UUIDs. References to entities and
   facts use the repository's current SQLite integer IDs; changing that global
   identity strategy requires a separate migration decision. Timestamps are
   timezone-aware UTC values.
3. Observations carry the time of capture and the time of receipt.
4. Payloads are typed; production models do not use unqualified `Any`.
5. Confidence describes evidence quality, never permission.
6. Authorization is evaluated explicitly and defaults to denial when absent.
7. `unknown`, `ambiguous`, `contradictory`, and `unauthorized` are normal
   domain outcomes, not exceptions.
8. Domain construction performs no I/O and never triggers cloud escalation.
9. Sensor-specific and provider-specific data stays behind adapters.
10. Schema evolution is explicit through `schema_version`.

## Shared vocabulary

### `KnowledgeStatus`

| Value | Meaning | Expected caller behavior |
|---|---|---|
| `known` | One result has sufficient supporting evidence. | Continue, subject to authorization. |
| `unknown` | Evidence is missing or insufficient. | State the limitation or request clarification. |
| `ambiguous` | More than one interpretation remains plausible. | Ask a disambiguating question. |
| `contradictory` | Relevant trusted sources disagree. | Expose the conflict; do not select silently. |
| `unauthorized` | Policy forbids processing or disclosure. | Refuse safely without leaking protected data. |

The status is categorical. It must not be inferred solely from a numeric
confidence threshold.

### `Confidence`

`Confidence` describes how strongly evidence supports an observation or result:

| Field | Type | Rule |
|---|---|---|
| `score` | constrained float | Inclusive range `0.0..1.0`. |
| `basis` | `ConfidenceBasis` | `measured`, `estimated`, `asserted`, or `not_applicable`. |
| `calibrated` | bool | Whether the score comes from a calibrated method. |
| `reason` | string or null | Short human-auditable explanation; never chain-of-thought. |

A score is not an authorization signal. `score=1.0` cannot override a denied
policy, and `score=0.0` does not by itself mean `unauthorized`.

### `AuthorizationDecision`

Authorization is an explicit value object:

| Field | Type | Rule |
|---|---|---|
| `decision` | `AuthorizationStatus` | `allowed`, `denied`, or `requires_confirmation`. |
| `action` | string | Stable action name being evaluated. |
| `data_categories` | immutable collection of strings | Categories the decision covers. |
| `policy_id` | string | Policy or rule that produced the decision. |
| `reason` | string | Safe explanation suitable for audit logs. |
| `evaluated_at` | aware datetime | UTC evaluation time. |

No authorization object means no permission. Callers must not interpret a
missing value as `allowed`.

## Core models

### `Observation[PayloadT]`

An immutable fact reported by an adapter, before the cognitive core decides
what it means.

| Field | Type | Purpose |
|---|---|---|
| `observation_id` | UUID | Stable identity for evidence and replay. |
| `schema_version` | positive integer | Serialized contract version; starts at `1`. |
| `source` | `ObservationSource` | Logical adapter identity, independent of hardware brand. |
| `modality` | `ObservationModality` | `text`, `audio`, `visual`, `sensor`, or `system`. |
| `captured_at` | aware datetime | When the source observed the world. |
| `received_at` | aware datetime | When the brain received the observation. |
| `payload` | generic typed payload | Modality-specific value object. |
| `confidence` | `Confidence` | Quality of this observation. |
| `expires_at` | aware datetime or null | Optional freshness boundary for transient state. |

`ObservationSource` is a stable logical name such as `robot.microphone`,
`web.chat`, `sim.temperature`, or `camera.front`. It must not expose driver
objects or provider clients.

Concrete payloads are introduced only when a feature needs them. For example,
a future `VisualObservationPayload` may contain typed people and objects, while
the shared envelope remains unchanged for webcam, simulator, or another camera.

### `CognitiveEvent[PayloadT]`

An immutable event envelope used to correlate what happened across adapters
and the cognitive core.

| Field | Type | Purpose |
|---|---|---|
| `event_id` | UUID | Unique event identity. |
| `schema_version` | positive integer | Serialized contract version; starts at `1`. |
| `event_type` | stable string | Names the domain occurrence, not a Python class. |
| `occurred_at` | aware datetime | Source time of the occurrence. |
| `recorded_at` | aware datetime | Time recorded by this process. |
| `source` | string | Logical producer identity. |
| `correlation_id` | UUID | Groups one turn or causal flow. |
| `causation_id` | UUID or null | Identifies the event that directly caused this one. |
| `subject_id` | integer or null | Existing entity concerned, when represented in SQLite. |
| `payload` | generic typed payload | Event-specific immutable value object. |

Events describe completed occurrences. Commands or action requests must use a
separate contract and pass authorization before reaching an actuator adapter.

### `ActiveContext`

An immutable snapshot assembled for one cognitive turn. It is not a global
blackboard and does not read the database by itself.

| Field | Type | Purpose |
|---|---|---|
| `context_id` | UUID | Identity of this assembled snapshot. |
| `conversation_id` | string | Working-conversation boundary. |
| `created_at` | aware datetime | Snapshot creation time. |
| `active_person_id` | integer or null | Resolved SQLite person/entity, if known. |
| `observation_ids` | immutable collection of UUIDs | Evidence available to this turn. |
| `fact_ids` | immutable collection of integers | Retrieved persistent facts. |
| `knowledge_status` | `KnowledgeStatus` | Current evidence state. |
| `confidence` | `Confidence` | Confidence in the resolved context. |
| `authorization` | `AuthorizationDecision` | Permission applicable to the intended use. |

`conversation_id` separates short working histories. It is not a user account,
identity proof, or authorization grant.

The richer `ActivePersonContext`, including identity state and its evidence, is
defined in [Identity, household access, and consent](identity-and-access.md).
`ActiveContext` consumes its resolved outcome; it must not reimplement identity
fusion.

## Required invariants

- Naive datetimes are rejected; values are normalized to UTC for serialization.
- Confidence scores outside `0.0..1.0` are rejected.
- `schema_version` is at least `1`.
- Collections exposed by the models are immutable.
- An authorized result still carries its `KnowledgeStatus` and `Confidence`.
- An unauthorized result does not serialize protected payload data.
- Constructing or validating any model has no database, network, model, or
  hardware side effects.

## Boundary examples

```text
Microphone adapter ──> Observation[AudioPayload]
Web adapter ─────────> Observation[TextPayload]
Camera adapter ──────> Observation[VisualPayload]
Sensor simulator ────> Observation[SensorPayload]
                              │
                              v
                    small typed orchestrator
                              │
                     KnowledgeStatus + evidence
                              │
                     authorization boundary
```

Cloud escalation is deliberately absent from these models. A later policy
service may consume a cognitive result and an authorization decision, but model
validation itself never selects or invokes a provider.

## Deferred work

This baseline does not define:

- a behavior tree, autonomous agent loop, or plugin registry;
- database tables or event persistence;
- HTTP endpoints or changes to the existing audio contract;
- concrete face, voice, location, medical, or child-data policies;
- cloud-provider clients, redaction, retries, or billing;
- actuator commands, ROS2 topics, or physical safety controls.

Those capabilities require separate plans and, where the trust boundary
changes, separate ADRs.
