# Plan 0002 — Active-person context design

## Status

Approved design. This document authorizes drafting and reviewing the canonical
Plan 0002 only. It does not authorize production implementation.

## Purpose

P0.2 removes the unsafe inference that the configured household owner is the
person speaking in every turn. It introduces a small, typed active-person
boundary before the future controller and authorization phases.

The design implements only session evidence and explicit, manual selection.
It does not add speaker recognition, diarization, automatic face use, biometric
enrollment, biometric storage, a cognitive framework, or a production
multi-agent runtime.

## Authority and dependencies

- [`cognitive-roadmap.md`](../../roadmap/cognitive-roadmap.md) defines P0.2 after
  completed Plan 0001 and before P0.3, P0.4, and P0.5.
- [`identity-and-access.md`](../../architecture/identity-and-access.md) defines
  identity evidence, active-person status, expiry, and the rule that identity
  is not authorization.
- [`cognitive-contracts.md`](../../architecture/cognitive-contracts.md) preserves
  the typed, local-first contract and valid uncertainty results.
- [`0001-cognitive-domain-models.md`](0001-cognitive-domain-models.md)
  supplies the immutable cognitive vocabulary, including `Confidence` and
  `KnowledgeStatus`.
- [`p0-cognitive-plan-portfolio-design.md`](p0-cognitive-plan-portfolio-design.md)
  defines the portfolio ordering and common execution rules.

The current implementation requires this phase: `text_turn.py` loads the
persisted `owner_name` and passes it to generation, while
`characters/__init__.py` tells the model that this owner is the current
speaker. Voice and visual dialogue use the fixed
`settings.voice_conversation_id` value (`voice-primary`). `conversation_id`
must remain a working-history identifier rather than an identity or an
authorization credential.

## Decision

### 1. Typed identity boundary

Plan 0002 adds a focused identity module alongside the existing cognitive
models. It introduces immutable, `extra="forbid"` Pydantic contracts:

| Contract | Required contents | P0.2 meaning |
|---|---|---|
| `IdentityEvidence` | UUID evidence reference, source, candidate SQLite `person_id` or null, `Confidence`, observed UTC timestamp, safe reference, expiry | Immutable evidence, never a raw image, audio sample, embedding, or voiceprint. |
| `ActivePersonStatus` | `identified`, `probable`, `unknown`, `ambiguous` | A result of conservative resolution, not a permission. |
| `HouseholdRole` | `owner`, `adult`, `child`, `guest`, `unknown` | Vocabulary only; P0.2 resolves no role beyond `unknown`. P0.5 owns policy. |
| `ActivePersonContext` | person ID/display name when valid, status, confidence, role, immutable evidence, resolved UTC timestamp | The turn-local identity result consumed by the text path. |

SQLite entity identifiers remain strict `int` values. UUIDs identify evidence
and correlations only. All timestamps are timezone-aware and normalized to
UTC. Expired evidence is ignored on each new resolution.

The contract may name the documented evidence sources `session`, `manual`,
`face`, `voice`, and `context`, but the Plan 0002 adapters accept only
`session` and `manual`. Unsupported future sources must not become an implicit
fallback or change a status to identified.

### 2. Conservative resolver

A small, explicit resolver has one responsibility: turn validated, unexpired
evidence into an `ActivePersonContext`. It uses an adapter to verify that a
candidate integer still resolves to an existing `person` entity; it does not
write memory, infer permissions, call an LLM, or inspect biometrics.

The initial deterministic rules are:

| Evidence result | Active-person status |
|---|---|
| No valid candidate, expired evidence, or a missing/non-person entity | `unknown` |
| One explicitly confirmed manual candidate that resolves to a person | `identified` |
| One valid non-manual session candidate below manual-confirmation strength | `probable` |
| Two or more distinct valid candidates | `ambiguous` |

The resolver preserves the source-specific confidence and returns an explicit
uncertain outcome rather than choosing a person. It must be independently
unit-testable without SQLite, time, web, audio, or model I/O.

### 3. Ephemeral manual-session registry

P0.2 adds a process-local registry keyed by an opaque session token. It stores
only safe, expiring `IdentityEvidence`; it stores neither biometric material
nor persistent identity claims. It exposes a narrow server-side operation to:

1. record an explicit manual selection of an existing person entity for one
   session;
2. resolve current session evidence; and
3. clear or expire that evidence.

There is deliberately no HTTP identity-selection endpoint and no chat-UI work
in this phase. A public operation to claim an identity would require an
authorization and operator-authentication design that belongs after P0.2. The
registry is an adapter seam for a future trusted local UI or voice interaction
adapter; its behavior is fully covered by tests now.

### 4. Conversation and history isolation

`conversation_id` remains the public, ephemeral working-history identifier.
It does not select a person, provide evidence, or authorize retrieval.

- Existing `/chat` request and response schemas stay unchanged. A chat request
  without separately resolved internal evidence is `unknown`.
- Voice and visual dialogue stop using the process-global `voice-primary`
  history. An unresolved voice/visual interaction receives a fresh opaque
  working scope.
- A manually identified session may retain working history only under a scope
  incorporating both its opaque session and verified integer person ID.
- `unknown`, `probable`, and `ambiguous` interactions are one-turn scopes.
  They must not inherit or leave history that a later person can read.
- Evidence expiry, manual clearing, or a transition to ambiguity clears the
  affected working history before a later turn can reuse it.

This is history isolation, not authorization. P0.5 remains responsible for
data-category policy and protected-data decisions.

### 5. Persistent-memory transition rule

Until P0.5 can evaluate deterministic household policy, persistent memory is
treated as protected for non-identified contexts:

- `unknown`, `probable`, and `ambiguous` contexts do not call persistent
  retrieval and do not schedule automatic consolidation.
- A manually `identified` context is explicit identity evidence, but is still
  not an authorization decision. Plan 0002 must not label it authorized or
  create a role grant.
- Any compatibility behavior for identified legacy memory is documented and
  tested as transitional only; it cannot be used to justify retrieval for an
  uncertain context.

The canonical implementation plan must choose and test the narrowest
compatibility path for identified legacy sessions after re-checking current
`main`. It may not silently broaden access. P0.5 will replace this temporary
boundary with actor, action, category, visibility, sensitivity, consent, and
auditable policy evaluation before protected retrieval.

### 6. Legacy owner metadata

The persisted `owner_name` is household legacy data, not current-speaker
identity. P0.2 removes it from all current-speaker prompt assertions and from
the decision to interpret an incoming utterance as the owner's statement.

Specifically, Plan 0002 must remove the `OWNER IDENTITY` prompt behavior that
says the current speaker is `{owner_name}`. An utterance such as `me llamo …`
cannot automatically establish or replace the household owner. Existing data
is preserved for later migration and onboarding work, but no new incoming turn
may silently mutate it as a side effect of being the presumed owner.

## Integration boundary

The implementation affects only the server's text-turn orchestration boundary:

```text
adapter session/manual evidence
        -> active-person resolver
        -> safe history scope and persistent-memory eligibility
        -> existing text generation
```

The LLM receives presentation guidance only for an explicitly resolved active
person. It cannot resolve identity, establish facts, select a role, grant
permission, alter a session registry, or choose a memory-retrieval policy.

No production multi-agent architecture is introduced. The future P0.3
controller will compose this boundary with deterministic tools and policy;
P0.5 will add authorization before protected data reaches retrieval or model
context.

## Explicit non-goals

- No new database schema, migration, UUID replacement for SQLite entity IDs,
  or change to facts/relations.
- No face recognition integration, speaker recognition, diarization, audio
  retention, embedding persistence, or automatic biometric enrollment.
- No HTTP identity endpoint, UI, browser storage, login, account, tenant, or
  authorization policy.
- No role inference or permission grant.
- No onboarding redesign, household graph migration, or automatic rewrite of
  legacy `owner_name` data.
- No cloud call, dependency installation, hardware control, or change to the
  server/robot boundary or public audio contract.

## Acceptance criteria for the canonical Plan 0002

The eventual implementation plan must require observed RED then GREEN tests
for all of the following:

1. Identity contracts reject wrong ID types, raw biometric payloads, naive
   timestamps, expired evidence used as current evidence, and undeclared
   fields; they are immutable and JSON round-trip safely.
2. The resolver deterministically covers identified, probable, unknown, and
   ambiguous outcomes, including a missing entity and conflicting candidates.
3. Manual selection is expiring, clears correctly, validates the existing
   integer person entity, and never persists raw biometric material.
4. `conversation_id` cannot become identity or authorization; `/chat` keeps
   its existing public schema and rejects identity fields as before.
5. Unknown, probable, and ambiguous turns do not reuse another person's
   working history, do not build persistent memory context, and do not schedule
   consolidation.
6. Audio and visual dialogue no longer use a global `voice-primary` working
   context, while their published response contracts remain unchanged.
7. The prompt has no assertion that the configured owner is the person in
   front of the robot, and `me llamo …` cannot silently set a household owner.
8. Existing server/robot separation and WAV `16 kHz`, mono, int16 contract
   remain unchanged.
9. Focused tests, then `just lint`, `just typecheck`, and `just test` pass
   without adding dependencies.

## Review questions before readiness

Before Plan 0002 becomes `Ready`, re-check the then-current `main` tree and
make these choices explicit in the canonical plan:

1. the exact trusted in-process adapter that invokes manual selection;
2. the transitional behavior for manually identified legacy-memory sessions;
3. the exact new opaque voice interaction-scope lifecycle; and
4. the complete permitted file and test scope.

No answer may turn session IDs, manual selection, face matching, recognition
confidence, or `owner_name` into authorization.
