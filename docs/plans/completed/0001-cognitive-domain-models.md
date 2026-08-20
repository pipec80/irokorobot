# Plan 0001 — Cognitive domain models

- **Status:** Complete
- **Depends on:** [ADR-0004](../../adr/0004-local-first-cognitive-policy.md)
- **Contract:** [Cognitive contracts](../../architecture/cognitive-contracts.md)
- **Architecture index:** [Canonical architecture index](../../architecture/README.md)
- **Type:** Pure domain-model implementation

## Objective

Implement the smallest immutable Python model layer that represents cognitive
events, observations, active context, confidence, authorization, and knowledge
status exactly as defined by the cognitive contract.

The result is a vocabulary for later orchestration. It must not connect these
models to the current voice, memory, vision, HTTP, or provider pipelines.

## Required reading

Read these files completely before editing:

1. `docs/architecture/implementation-guardrails.md`
2. `docs/architecture/README.md`
3. `docs/adr/0004-local-first-cognitive-policy.md`
4. `docs/adr/0005-small-typed-cognitive-controller.md`
5. `docs/architecture/cognitive-contracts.md`
6. root `pyproject.toml`
7. `server/src/server/schemas.py`
8. `server/src/server/schemas_chat.py`

Do not scan the rest of the repository unless a listed verification command
fails and its output identifies a specific file that must be inspected.

## Permitted implementation files

Create or modify only:

- `server/src/server/cognition/__init__.py`
- `server/src/server/cognition/models.py`
- `tests/unit/test_cognitive_models.py`
- `docs/plans/0001-cognitive-domain-models.md`, only to change its status from
  `Ready` to `Complete` after all checks pass.

Dependency or configuration changes are not expected. Stop and explain the
need before editing any other file.

## Deliverables

Implement:

- `KnowledgeStatus`
- `ConfidenceBasis`
- `AuthorizationStatus`
- `ObservationModality`
- `Confidence`
- `AuthorizationDecision`
- generic `Observation[PayloadT]`
- generic `CognitiveEvent[PayloadT]`
- `ActiveContext`

Use the project's installed Pydantic version and existing schema conventions.
Use strict types, immutable/frozen models, UUIDs for envelopes/correlation,
current SQLite integer IDs for entity and fact references, and timezone-aware
datetimes. Do not use `Any`; define a bounded generic payload type compatible
with Pydantic. Do not introduce or migrate persistence in this plan.

Public models and enums must be re-exported from
`server.cognition.__init__` and have Google-style docstrings.

## Behavioral requirements

Tests must prove:

1. Every enum serializes to the exact lowercase values in the contract.
2. Confidence accepts `0.0` and `1.0` and rejects values outside that range.
3. Naive datetimes are rejected in every datetime field.
4. A valid observation round-trips through JSON without changing IDs, UTC
   timestamps, payload, modality, or confidence.
5. A valid cognitive event preserves correlation and optional causation IDs.
6. Active context keeps UUID observation IDs and integer entity/fact IDs
   immutable.
7. Missing authorization is rejected; it never defaults to allowed.
8. Model construction performs no I/O and imports no database, HTTP, hardware,
   LLM, or provider module.

If Pydantic cannot enforce payload immutability for arbitrary user-defined
generic payloads, document that boundary in the model docstring and test the
immutability of the envelope. Do not add a framework to solve it.

## Non-goals

- Do not integrate the models into `text_turn.py`, memory, vision, routers, or
  the robot package.
- Do not add persistence, migrations, repositories, services, or endpoints.
- Do not call Ollama, Anthropic, Codex, or any cloud service.
- Do not implement provider fallback or escalation policy.
- Do not create agents, tools, plugins, behavior trees, or action execution.
- Do not modify the existing `/transcribe` or `/chat` contracts.
- Do not anticipate concrete payload models for future sensors.

## Verification

Run in this order:

```powershell
just lint
just typecheck
just test
```

All commands must pass without weakening existing checks. Tests must run
offline and deterministically.

## Completion criteria

The plan is complete only when all listed models and invariants exist, the
three verification commands pass, and no file outside the permitted scope was
changed. After verification, change this plan's status from `Ready` to
`Complete` in the implementation commit.
