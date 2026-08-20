# Plan 0002 — Active-person context and conversation isolation

- **Status:** Complete
- **Roadmap phase:** P0.2
- **Prerequisite:** Plan 0001 is Complete.
- **Approved design:** [0002-active-person-context-design.md](0002-active-person-context-design.md)
- **Execution runbook:** [0002-active-person-context-execution.md](0002-active-person-context-execution.md)

## Objective

Replace the implicit current-speaker assumption with a small, typed,
local-first active-person boundary. The implementation begins with expiring
session and manual evidence only. It isolates uncertain interactions, stops
using `owner_name` as current-speaker identity, and blocks persistent retrieval
and automatic consolidation for non-identified contexts.

It is not an authorization system. P0.5 owns roles, permission policy, data
categories, consent, and auditable protected-data decisions.

## Required reading

Read, in order, before editing:

1. [`AGENTS.md`](../../../AGENTS.md) and every applicable `.codex/rules/` file.
2. [`implementation-guardrails.md`](../../architecture/implementation-guardrails.md)
   and [`README.md`](../../architecture/README.md).
3. [`0005-small-typed-cognitive-controller.md`](../../adr/0005-small-typed-cognitive-controller.md).
4. [`cognitive-roadmap.md`](../../roadmap/cognitive-roadmap.md), P0.2 and P0.5.
5. [`identity-and-access.md`](../../architecture/identity-and-access.md) and
   [`cognitive-contracts.md`](../../architecture/cognitive-contracts.md).
6. [`0001-cognitive-domain-models.md`](0001-cognitive-domain-models.md) and
   the approved [Plan 0002 design](0002-active-person-context-design.md).
7. This plan and its execution runbook in full.

`docs/local/` is historical evidence only and must not supply operational
instructions or authority.

## Architectural decisions locked by this plan

- One small typed Python boundary; no production agent framework, multi-agent
  runtime, autonomous loop, plugin system, or cloud fallback.
- SQLite entity IDs remain strict integers. UUIDs identify opaque sessions,
  evidence, and correlations only.
- `conversation_id` remains public working-history input. It is not identity,
  permission, a user ID, or a tenant ID.
- Only `session` and explicit `manual` evidence adapters are active. Face,
  voice, and context sources are vocabulary for later phases and must not
  identify a person in P0.2.
- `identified`, `probable`, `unknown`, and `ambiguous` are explicit results.
  Expired, invalid, missing, and conflicting evidence never becomes a guessed
  identity.
- Identity and authorization remain distinct. An explicit manual selection is
  identity evidence, never a role grant or authorization decision.
- `unknown`, `probable`, and `ambiguous` receive a one-turn working scope and
  must not retrieve persistent memory or schedule consolidation.
- Existing `owner_name` is legacy household metadata only. It must never say
  who is speaking, and `me llamo …` must not set or replace it.
- No HTTP identity-selection endpoint, chat UI change, database migration,
  biometric change, onboarding redesign, audio-contract change, or public API
  schema change belongs to this plan.

## Permitted implementation files

Only these production files may change:

```text
server/src/server/cognition/__init__.py
server/src/server/cognition/identity.py                 (new)
server/src/server/cognition/identity_sessions.py        (new)
server/src/server/text_turn.py
server/src/server/streaming.py
server/src/server/llm.py
server/src/server/llm_streaming.py
server/src/server/characters/__init__.py
server/src/server/memory/consolidation.py
server/src/server/memory/normalize.py
server/src/server/routers/transcribe.py
server/src/server/routers/vision.py
server/src/server/settings.py
server/src/server/vision/perception.py                 (final remediation,
                                                         user-authorized)
```

Permitted tests and canonical documentation:

```text
tests/unit/test_active_person_identity.py               (new)
tests/unit/test_identity_sessions.py                    (new)
tests/unit/test_text_turn.py
tests/unit/test_llm_generate.py
tests/unit/test_eval_chat.py
tests/integration/test_chat_endpoint.py
tests/integration/test_transcribe_memory.py
tests/integration/test_transcribe_stream.py
tests/integration/test_transcribe_pipeline.py
tests/integration/test_vision_dialog.py
tests/integration/test_vision_memoria.py
tests/integration/test_memory_integration.py
tests/integration/test_onboarding_checklist.py
tests/integration/test_memory_relational.py
tests/evals/golden_chat_faithfulness.yaml
tests/evals/golden_conversations.yaml
docs/plans/README.md
docs/plans/0002-active-person-context.md
docs/plans/0002-active-person-context-execution.md
```

If a change outside this list is needed, stop. Re-read the architecture and
write a follow-up plan or ADR; do not widen this plan during implementation.

## Deliverables

### 1. Identity contracts and resolver

Create immutable, strict Pydantic identity contracts that reuse `Confidence`
from Plan 0001:

- `IdentityEvidenceSource`: `session`, `manual`, `face`, `voice`, `context`.
- `ActivePersonStatus`: `identified`, `probable`, `unknown`, `ambiguous`.
- `HouseholdRole`: `owner`, `adult`, `child`, `guest`, `unknown`; P0.2 only
  returns `unknown`.
- `IdentityEvidence`: UUID, source, optional strict integer candidate,
  `Confidence`, aware observed time, safe reference, optional aware expiry.
- `ActivePersonContext`: optional existing-person integer and presentation
  name, status, confidence, role, immutable evidence, aware resolution time.

Implement a deterministic resolver with injected entity lookup. It must remain
independent from HTTP, SQLite connection setup, LLM, audio, and wall-clock
time. Valid explicit manual evidence for one existing `person` entity produces
`identified`; one valid session candidate produces `probable`; no valid
candidate produces `unknown`; distinct valid candidates produce `ambiguous`.

### 2. Expiring internal manual-session seam

Create a process-local `IdentitySessionRegistry` with opaque session tokens.
It accepts only explicit selection of a verified existing person entity,
retains safe expiring evidence, resolves active evidence, and clears a session.
It must not persist raw biometric material, write SQLite, expose a FastAPI
route, accept a display name as an identity key, or infer a role.

The registry exists for a future trusted local adapter. Unit tests may invoke
it directly. Existing `/chat`, `/transcribe`, and `/vision/respond` clients
receive no new public identity field or endpoint.

### 3. Turn-local safety policy

Thread an `ActivePersonContext` through preparation, generation, streaming,
recording, and optional consolidation scheduling. Resolve the identity before
selecting working history or persistent prompt inputs.

- An identified manual session receives a history key derived from its opaque
  session plus verified person ID.
- Unknown, probable, and ambiguous turns have a fresh one-turn key; clear it
  after the response is recorded so it cannot become a later speaker's
  history.
- Only identified manual contexts may follow the explicitly documented legacy
  compatibility path for persistent context and consolidation. This is not an
  authorization decision and must be easy for P0.5 to replace.
- Non-identified contexts skip `build_context`, onboarding lookup, semantic
  retrieval, relation retrieval, and consolidation scheduling. They still get
  a normal local LLM response and safe fallback.
- The streaming path must apply exactly the same identity, history, and
  recording policy as non-streaming text turns.

### 4. Legacy owner removal

Remove `owner_name` from generation and streaming generation inputs and replace
the prompt block with optional presentation guidance based only on an
explicitly identified active person. It must not call that person an owner or
turn identity evidence into a permission.

Delete the automatic self-introduction anchoring path in consolidation. Do not
write the `owner_name` metadata flag from an incoming turn. When a manually
identified turn is permitted to consolidate under the temporary compatibility
path, normalization receives that active person's validated display name as a
turn-local subject reference, not the global owner flag.

The legacy onboarding path relies on the global owner flag. Suppress it at the
P0.2 text-turn boundary rather than redesigning it; P1.1 will replace it with
confirmed multi-channel household onboarding.

### 5. Voice and visual interaction scopes

Remove the fixed `settings.voice_conversation_id` / `voice-primary` use from
voice and visual dialogue. Each unresolved `/transcribe`, `/transcribe/stream`,
and `/vision/respond` request receives a newly generated opaque interaction
scope. The same scope stays valid for all work inside that one request only.

This preserves the public audio response and NDJSON contracts while ensuring a
new visitor cannot inherit the preceding visitor's audio history. `/chat`
retains its existing request/response shape, but without explicit internal
identity evidence it follows the non-identified one-turn policy.

## Acceptance tests

The execution runbook must demonstrate observed RED before implementation and
focused GREEN afterward. At minimum it must prove:

1. Identity evidence and active-person contexts are immutable, reject wrong
   integer/UUID/timestamp types and extra fields, normalize UTC, and serialize
   round-trip.
2. The resolver covers identified, probable, unknown, ambiguous, expired,
   missing-entity, and conflicting-evidence cases deterministically.
3. The session registry expires and clears evidence, verifies integer person
   candidates, and stores no raw biometric data.
4. The public `/chat` contract is unchanged and still rejects identity fields;
   its `conversation_id` cannot create identity or authorization.
5. Unknown, probable, and ambiguous turns do not read persistent context,
   onboarding, history, emotion state, or consolidation, and do not leave
   reusable working history.
6. An explicitly manual identified test context gets an isolated person/session
   history and is the only covered legacy-compatible persistent path.
7. No prompt says the configured household owner is the current speaker, and a
   self-introduction does not mutate the owner flag.
8. Voice, streaming, and visual calls do not use `voice-primary`, preserve
   their published audio/NDJSON response schemas, and use a fresh internal
   scope per unresolved request.
9. Existing Plan 0001 cognitive models, server/robot separation, WAV 16 kHz
   mono int16 contract, and local fallback behavior remain intact.

## Non-goals

- P0.3 controller/tool implementation, P0.4 relational schema, P0.5 policy,
  P1 onboarding/world/perception, or P2 lifecycle/cloud work.
- Automatic identity from a face match, a voice match, a name in text, or an
  LLM output.
- Public user, tenant, role, token, identity, or authorization fields in any
  existing endpoint.
- Permission to retrieve protected data based only on a confidence score,
  selected identity, `conversation_id`, or legacy owner metadata.
- Any dependency, provider, cloud, database schema, robot-client, Docker, or
  hardware change.

## Execution and verification

Execute only through the companion runbook using
`superpowers:subagent-driven-development`, or
`superpowers:executing-plans` sequentially when delegation is unavailable.
Those are temporary development techniques, not Iroko production components.

Before claiming completion, run the focused checks named in the runbook, then:

```powershell
just lint
just typecheck
just test
```

Review the final diff against the permitted scope. Update this plan's status
from `Ready` to `Complete` only after every acceptance criterion and the three
commands pass. Do not modify any later plan's status.

## Completion record — 2026-08-10

Plan 0002 is complete. It introduced the strict, local-only active-person
boundary; an expiring process-local manual-session registry; one-turn isolation
for unresolved interactions; manual-only legacy compatibility for persistent
context and consolidation; neutral, non-identifying generation guidance; and
opaque per-request voice and vision interaction scopes. The published `/chat`,
audio, and NDJSON contracts remain unchanged.

Observed final verification before this status update:

```text
combined focused suite: 159 passed in 3.99s
just lint: passed (171 files left unchanged)
just typecheck: mypy 65 source files, no issues; pyright 0 errors, 0 warnings
just test: 482 passed in 42.52s
git diff --check 9ec3afd..cbf64d4: passed
```

The implementation commits are `dc9e398`, `985cf90`, `cdb9c30`, `9f36219`,
`08b4a34`, `005f50e`, `abcc3a1`, `fe75e9d`, `b564e8d`, `9be02fa`, `d8b3394`,
`b309643`, and `cbf64d4`. The baseline scope was widened only by the recorded
user authorizations: `tests/integration/test_transcribe_onboarding.py` for the
unidentified-onboarding regression; `server/src/server/text_turn.py`,
`scripts/eval_chat.py`, and `scripts/eval_consolidation.py` to remove broken
legacy generation/evaluation aliases; `tests/integration/test_transcribe_memory.py`
for the matching regression; and the final-gate test-only corrections in
`tests/unit/test_owner_anchor.py` and `tests/unit/test_cognitive_models.py`.

Known limitation: manual selection is process-local and expires; restarting the
process clears the registry. This plan provides no authentication, biometric
identification, role grant, consent decision, or public identity endpoint.
Face, voice, and context remain future vocabulary only. P0.3 remains **Draft**;
its promotion requires a current-tree review and an updated executable scope.

## Final remediation record — 2026-08-10

Final review approved the remediation in `79258cc`
(`fix(cognition): close active person safety gaps`). It addressed five findings:

1. unresolved audio no longer retrieves persisted entity-name hotwords before
   identity is resolved;
2. unresolved visual dialogue uses scene-only perception rather than injecting
   face-recognition names;
3. verified manual `ActivePersonContext` reaches standard and streaming
   consolidation scheduling without becoming authorization;
4. trusted registry selection emits `manual`, resolves as `identified`, and
   exposes the canonical `IdentitySessionRegistry`; and
5. Python-mode identity timestamps are strict, while JSON round trips remain
   supported; the unused prepared-turn `owner_name` field was also removed.

The user authorized the narrow production-scope addition
`server/src/server/vision/perception.py` for the scene-only visual boundary.
No public endpoint or field, role grant, authentication, biometric identity
integration, dependency, cloud path, database migration, audio, OpenAPI, or
NDJSON contract changed.

The final evidence is: combined Plan 0002 suite, 174 passed in 3.25s; `just
lint` green; `just typecheck` green (Mypy: 65 source files, no issues; Pyright:
0 errors, 0 warnings); and `just test`, 497 passed in 41.67s. `git diff --check`
also passed. The reviewer approved this closure.

Non-blocking follow-up: retire the compatibility alias for the earlier registry
class name only through a separately scoped migration after all consumers have
moved to `IdentitySessionRegistry`. It does not reopen P0.2. P0.3 remains
**Draft**.
