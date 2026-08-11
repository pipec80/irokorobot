# Plan 0002 execution runbook — Active-person context

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development`; use
> `superpowers:executing-plans` only when sequential execution is necessary.
> This runbook is subordinate to
> [Plan 0002](0002-active-person-context.md) and may not widen its scope.

## Preconditions

- [ ] Work in a local feature branch in the primary checkout; do not use a Git
  worktree for this repository.
- [ ] Read the canonical plan, approved design, required architecture sources,
  `AGENTS.md`, and `.codex/rules/` in full.
- [ ] Confirm `git status --short` has no unrelated changes. Preserve any
  pre-existing user artifacts if present.
- [ ] Confirm Plan 0001 is `Complete` and no other plan is `Ready`.
- [ ] Do not install dependencies, use cloud services, change branches, or
  modify files outside the canonical permitted scope.

## Worker protocol for every task

- [ ] Assign exactly the listed file ownership. Workers are not alone in the
  repository: they must preserve unrelated changes and accommodate adjacent
  completed tasks; they must not revert others' work.
- [ ] Add or alter the named test first.
- [ ] Run the stated focused command and record the observed RED failure.
- [ ] Implement only the smallest behavior required to make that test green.
- [ ] Run the same focused command and record GREEN.
- [ ] Review the diff for strict typing, Google docstrings on public APIs,
  local-first boundaries, no `Any`/bare `except`/`print`, and permitted scope.
- [ ] Commit only the completed task after review if the execution session is
  using task commits; use Conventional Commits and never commit to `main`.

## Task 1 — Immutable identity contracts

**Files:**

```text
server/src/server/cognition/__init__.py
server/src/server/cognition/identity.py                 (new)
tests/unit/test_active_person_identity.py               (new)
```

- [ ] Write tests for exact enum values; strict integer entity IDs; UUID
  evidence IDs; frozen models; `extra="forbid"`; aware-to-UTC timestamps;
  rejection of naive datetimes; expiry; and JSON round trips.
- [ ] Include evidence-source vocabulary for `session`, `manual`, `face`,
  `voice`, and `context`, but assert only P0.2 semantics for the first two.
- [ ] Run RED:

  ```powershell
  uv run pytest -n0 tests/unit/test_active_person_identity.py -q
  ```

- [ ] Implement `IdentityEvidenceSource`, `ActivePersonStatus`,
  `HouseholdRole`, `IdentityEvidence`, and `ActivePersonContext` in the new
  module. Reuse Plan 0001 `Confidence`; do not duplicate it.
- [ ] Run the same focused command for GREEN.
- [ ] Verify imports are explicit and no existing `ActiveContext` contract is
  silently repurposed or weakened.

## Task 2 — Deterministic resolver and session registry

**Files:**

```text
server/src/server/cognition/identity.py
server/src/server/cognition/identity_sessions.py        (new)
tests/unit/test_active_person_identity.py
tests/unit/test_identity_sessions.py                    (new)
```

- [ ] Add resolver tests first. Inject lookup and clock dependencies; do not
  open SQLite or start an app in these tests.
- [ ] Cover: one verified manual person -> `identified`; one verified session
  candidate -> `probable`; no evidence/expired/missing/non-person -> `unknown`;
  distinct candidates -> `ambiguous`; exact evidence preservation; role always
  `unknown`.
- [ ] Add registry tests first. Cover manual selection only by existing integer
  person ID, opaque session token, expiry, clear, no display-name key, and no
  raw biometric fields.
- [ ] Run RED:

  ```powershell
  uv run pytest -n0 tests/unit/test_active_person_identity.py tests/unit/test_identity_sessions.py -q
  ```

- [ ] Implement the pure resolver and process-local registry with an injected
  `person_id -> person record | None` boundary. The registry may retain safe
  immutable evidence only; it must have no FastAPI router and no SQLite write.
- [ ] Run the same command for GREEN.
- [ ] Review that no source can infer a person from text, face matching, voice,
  `conversation_id`, or an LLM result.

## Task 3 — Apply active-person state before memory and history

**Files:**

```text
server/src/server/text_turn.py
server/src/server/memory/consolidation.py
server/src/server/memory/normalize.py
tests/unit/test_text_turn.py
tests/integration/test_chat_endpoint.py
tests/integration/test_transcribe_memory.py
tests/integration/test_memory_integration.py
tests/integration/test_onboarding_checklist.py
tests/integration/test_memory_relational.py
```

- [ ] First change tests to make the new safety behavior explicit: unknown,
  probable, and ambiguous turns do not call `build_context`, onboarding lookup,
  history/emotion read, or consolidation scheduler, and they leave no reusable
  working history.
- [ ] Add a manually identified internal test context proving a history key is
  scoped by opaque session plus integer person ID, not display name or public
  `conversation_id`.
- [ ] Add regression tests that `me llamo …` does not write the `owner_name`
  flag and that a non-identified turn cannot cause persistent consolidation.
- [ ] Run RED:

  ```powershell
  uv run pytest -n0 tests/unit/test_text_turn.py tests/integration/test_chat_endpoint.py tests/integration/test_transcribe_memory.py tests/integration/test_memory_integration.py tests/integration/test_onboarding_checklist.py tests/integration/test_memory_relational.py -q
  ```

- [ ] Thread `ActivePersonContext` through `PreparedTextTurn`, preparation,
  recording, and scheduling. Resolve it before calculating history scope or
  persistent inputs.
- [ ] Gate legacy persistent context/consolidation on `identified` manual
  evidence only. Suppress legacy onboarding at the text-turn boundary until
  P1.1 replaces its global-owner model.
- [ ] Remove `_maybe_anchor_owner` and its call. Preserve existing metadata but
  never write `owner_name` from a turn. Rename local normalization semantics to
  an explicit turn-local active-person reference where needed; do not claim it
  is authorization.
- [ ] Clear working history/emotions on expiry, clear, ambiguity, and after a
  one-turn non-identified response.
- [ ] Run the same command for GREEN.
- [ ] Review that `conversation_id` is never used as identity, permission, or
  an input to entity lookup.

## Task 4 — Replace owner prompt assertion and streaming propagation

**Files:**

```text
server/src/server/characters/__init__.py
server/src/server/llm.py
server/src/server/llm_streaming.py
server/src/server/streaming.py
tests/unit/test_llm_generate.py
tests/unit/test_eval_chat.py
tests/integration/test_transcribe_stream.py
tests/integration/test_vision_memoria.py
tests/evals/golden_chat_faithfulness.yaml
tests/evals/golden_conversations.yaml
```

- [ ] Replace owner-identity tests first with tests proving no prompt asserts
  that the configured owner is speaking. Add one explicit-manual-context test
  for neutral presentation guidance that does not say `owner` or grant access.
- [ ] Add streaming/non-streaming parity tests: the same prepared identity
  context controls prompt inputs, history eligibility, and recordability.
- [ ] Update evaluation fixtures and their typed test adapter to use the new
  explicit active-person input or no identity; do not preserve `owner_name` as
  a hidden alias.
- [ ] Run RED:

  ```powershell
  uv run pytest -n0 tests/unit/test_llm_generate.py tests/unit/test_eval_chat.py tests/integration/test_transcribe_stream.py tests/integration/test_vision_memoria.py -q
  ```

- [ ] Remove `owner_name` parameters and `OWNER IDENTITY` template from
  character, standard-generation, and streaming-generation boundaries.
- [ ] Pass optional display guidance only from an explicitly `identified`
  active-person context. Preserve response formatting, local fallback, and
  emotion protocol.
- [ ] Run the same command for GREEN.
- [ ] Search changed production code for `owner_name` and confirm every
  remaining occurrence is legacy persistence/migration evidence, not a
  current-speaker assertion.

## Task 5 — Isolate unresolved voice and vision requests

**Files:**

```text
server/src/server/settings.py
server/src/server/routers/transcribe.py
server/src/server/routers/vision.py
server/src/server/text_turn.py
server/src/server/streaming.py
tests/integration/test_transcribe_pipeline.py
tests/integration/test_transcribe_memory.py
tests/integration/test_transcribe_stream.py
tests/integration/test_vision_dialog.py
```

- [ ] Write tests first showing two unresolved audio requests receive distinct
  opaque internal scopes; `/transcribe/stream` uses one scope consistently
  within its request; `/vision/respond` also has a fresh scope; and no live
  path uses literal `voice-primary`.
- [ ] Retain exact public JSON, multipart, WAV, and NDJSON schemas in tests.
- [ ] Run RED:

  ```powershell
  uv run pytest -n0 tests/integration/test_transcribe_pipeline.py tests/integration/test_transcribe_memory.py tests/integration/test_transcribe_stream.py tests/integration/test_vision_dialog.py -q
  ```

- [ ] Replace the `voice_conversation_id` setting and every router use with a
  single explicit opaque-scope factory. Scope creation is internal and must not
  leak into any public response.
- [ ] Pass the same turn inputs into streaming recording so it obeys Task 3's
  policy exactly.
- [ ] Run the same command for GREEN.
- [ ] Run a focused search over production modules for `voice-primary` and
  `voice_conversation_id`; any remaining live use is a stop condition.

## Task 6 — Documentation, final review, and completion gate

**Files:**

```text
docs/plans/README.md
docs/plans/0002-active-person-context.md
docs/plans/0002-active-person-context-execution.md
all files changed by Tasks 1-5 only
```

- [ ] Run the combined focused suite before documentation status changes:

  ```powershell
  uv run pytest -n0 tests/unit/test_active_person_identity.py tests/unit/test_identity_sessions.py tests/unit/test_text_turn.py tests/unit/test_llm_generate.py tests/unit/test_eval_chat.py tests/integration/test_chat_endpoint.py tests/integration/test_transcribe_memory.py tests/integration/test_transcribe_pipeline.py tests/integration/test_transcribe_stream.py tests/integration/test_vision_dialog.py tests/integration/test_vision_memoria.py tests/integration/test_memory_integration.py tests/integration/test_onboarding_checklist.py tests/integration/test_memory_relational.py -q
  ```

- [ ] Run the mandatory repository gates:

  ```powershell
  just lint
  just typecheck
  just test
  ```

- [ ] Review public OpenAPI/audio/NDJSON contracts, `git diff --check`, and
  `git diff --name-only` against Plan 0002's permitted scope.
- [ ] Confirm no dependency, cloud, DB migration, biometric behavior, endpoint,
  role grant, or production multi-agent component was introduced.
- [ ] Change Plan 0002 from `Ready` to `Complete` and change the index only
  after all prior checkboxes and gates are evidenced green.
- [ ] Produce a handoff with the exact RED/GREEN commands, full verification
  results, changed files, known limitations, and the unchanged next phase:
  P0.3 remains Draft.

## Final stop conditions

Stop and request a new documented decision instead of improvising if:

- a public identity-selection route, login, role mapping, consent decision, or
  protected-data policy is needed;
- manual selection needs persistence beyond the process lifetime;
- a face/voice/context evidence source must influence identity;
- relational facts need integer object IDs, cardinality, time, or migration;
- an existing audio/API contract would need to change; or
- a file outside canonical scope is required.

These conditions belong to P0.4, P0.5, P1, or a new ADR/plan, not Plan 0002.

## Recorded completion — 2026-08-10

Tasks 1–5 completed with the following observed test-first evidence. Initial
sandbox runs that could not read the local `uv` cache were repeated with the
normal local cache; the listed RED and GREEN results are the runs that reached
pytest.

| Task | RED observed | GREEN observed | Commit(s) |
| --- | --- | --- | --- |
| 1 | `ModuleNotFoundError` for `server.cognition.identity` (1 collection error); expiry follow-up: 2 failed, 8 passed | 10 passed | `dc9e398`, `985cf90` |
| 2 | missing `PersonRecord` import (2 collection errors) | 21 passed | `cdb9c30` |
| 3 | 17 failed, 42 passed; scheduler correction: 1 failed, 58 passed; stale-scope follow-up: 3 failed, 14 passed | 62 passed in the required suite | `9f36219`, `08b4a34`, `005f50e` |
| 4 | 5 failed, 48 passed | 55 passed; final scoped follow-up: 68 passed | `abcc3a1`, `fe75e9d`, `b564e8d`, `9be02fa` |
| 5 | 3 failed, 31 passed | 34 passed | `d8b3394` |
| final gate | 3 Pyright errors; then stale public-export expectation | `just typecheck` green; `just test`: 482 passed | `b309643`, `cbf64d4` |

The final combined focused command was run before documentation status changes:

```powershell
uv run pytest -n0 tests/unit/test_active_person_identity.py tests/unit/test_identity_sessions.py tests/unit/test_text_turn.py tests/unit/test_llm_generate.py tests/unit/test_eval_chat.py tests/integration/test_chat_endpoint.py tests/integration/test_transcribe_memory.py tests/integration/test_transcribe_pipeline.py tests/integration/test_transcribe_stream.py tests/integration/test_vision_dialog.py tests/integration/test_vision_memoria.py tests/integration/test_memory_integration.py tests/integration/test_onboarding_checklist.py tests/integration/test_memory_relational.py -q
# 159 passed in 3.99s

just lint
# passed; 171 files left unchanged
just typecheck
# mypy: 65 source files, no issues; pyright: 0 errors, 0 warnings
just test
# 482 passed in 42.52s
```

`git diff --check 9ec3afd..cbf64d4` passed. The name review matched the
canonical permitted production/test scope plus the explicit user-authorized
additions: `tests/integration/test_transcribe_onboarding.py` (Task 3);
`server/src/server/text_turn.py`, `scripts/eval_chat.py`, and
`scripts/eval_consolidation.py` (Task 4); `tests/integration/test_transcribe_memory.py`
(Task 4 follow-up); and the final-gate test-only corrections
`tests/unit/test_owner_anchor.py` and `tests/unit/test_cognitive_models.py`.
The last two align obsolete coverage with the completed P0.2 behavior and its
intentional public reexports.

Contract review found no new public identity-selection endpoint or field, role
grant, authentication, biometric identification behavior, dependency, cloud
service, database migration, production multi-agent component, audio-contract
change, OpenAPI change, or NDJSON change. Tests retain `/chat` identity-field
rejection and exact response checks; voice/stream/vision regressions retain the
published JSON, multipart WAV, and NDJSON schemas while using opaque internal
scopes.

Known limitation: the manual-session registry is intentionally process-local,
expiring, and cleared by restart. No authentication, public identity endpoint,
biometric identity, or authorization decision exists in P0.2. P0.3 remains
**Draft** and is not promoted by this completion record.
