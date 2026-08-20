# P0 Voice Controller Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Status:** Implemented and merged through PR #51 (`8e6d23f`). The mandatory
> human R1 runtime checkpoint remains open, so this plan is not yet closed.

**Goal:** Route the existing non-streaming `/transcribe` voice turn through the
typed `CognitiveController` while preserving the published audio API contract.

**Architecture:** The router remains the channel adapter: it validates WAV,
runs STT, turns the transcript into a `CognitiveEvent[TextTurnPayload]`, and
asks a freshly composed controller for a `ResponsePlan`.  The public voice
actor is always `unknown` in this slice.  Generic conversation remains a
controller-owned delegation to `process_text_turn`; deterministic and
protected branches never enter that delegate.

**Tech Stack:** FastAPI, Pydantic v2, Python 3.12, existing SQLite policy/audit
services, pytest, Ruff, mypy, and the existing Faster Whisper/Piper runtime.

## Global constraints

- Implement R1 only from [Plan 0012](../completed/0012-p0-runtime-acceptance-design.md).
- Preserve `POST /transcribe` request/response fields, timing meanings, and
  WAV 16 kHz mono int16 contract exactly.
- Do not modify `/transcribe/stream`, robot transport, database schema,
  migrations, settings, legacy memory, or P1 onboarding.
- Do not derive identity from voice text, name, face, HTTP data, or a
  conversation ID.  R1 public voice is always `unknown`.
- Do not add dependencies, a public session/admin API, or a model.
- A private household request must be authorized and audited before any legacy
  text delegate or v4 reader can receive it.
- Tests are regression evidence; product completion also requires the manual
  `just run-server` plus `just run-robot` cases in the runbook.

## Read before implementation

- `docs/plans/completed/0012-p0-runtime-acceptance-design.md`
- `docs/runbooks/p0-runtime-acceptance.md`
- `server/src/server/routers/transcribe.py`
- `server/src/server/routers/chat.py`
- `server/src/server/cognition/controller.py`
- `server/src/server/cognition/response_plan.py`
- `server/src/server/text_turn.py`
- `tests/integration/test_transcribe_pipeline.py`
- `tests/integration/test_chat_endpoint.py`

---

### Task 1: Prove the voice deterministic and protected routes are missing

**Files:**

- Modify: `tests/integration/test_transcribe_pipeline.py`
- Modify: `tests/integration/test_transcribe_memory.py`

**Interfaces:**

- Consumes: the existing `POST /transcribe` endpoint and its test client.
- Produces: regression tests that require voice to use a `ResponsePlan`, not a
  direct unclassified `process_text_turn` call.

- [x] **Step 1: Write a failing voice-date test.**

  Set STT to return `"¿Qué fecha es hoy?"`, patch the adapter-owned date to
  `date(2026, 8, 12)`, and patch `process_text_turn` with an `AsyncMock`.
  Assert a 200 response whose `llm_response` is exactly
  `"Hoy es 2026-08-12."`, whose `emotion` is `"neutral"`, whose `llm_ms` is
  `0`, and whose audio is synthesized from that exact response.  Assert the
  legacy delegate was not awaited.

- [x] **Step 2: Run the focused test and observe RED.**

  Run: `uv run pytest tests/integration/test_transcribe_pipeline.py -k voice_date -v`

  Expected: it fails because `/transcribe` currently sends the transcript
  directly to `process_text_turn`.

- [x] **Step 3: Write a failing private-family voice test.**

  Set STT to return `"¿Cómo se llaman mis hijos?"`. Patch the legacy delegate,
  `record_authorization_decision`, `PolicyGatedV4Reader`, and
  `HouseholdKnowledgeTools`. Assert the response contains the existing
  non-disclosing authorization denial, the audit writer is awaited once, the
  legacy delegate is not awaited, neither tool is awaited, and the reader mock
  has no calls.

- [x] **Step 4: Run the focused test and observe RED.**

  Run: `uv run pytest tests/integration/test_transcribe_memory.py -k private_family -v`

  Expected: it fails because the legacy delegate still receives the protected
  transcript.

### Task 2: Add the minimal typed voice adapter inside the existing router

**Files:**

- Modify: `server/src/server/routers/transcribe.py`
- Test: `tests/integration/test_transcribe_pipeline.py`
- Test: `tests/integration/test_transcribe_memory.py`

**Interfaces:**

- Consumes: `CognitiveController.handle(event) -> ResponsePlan`,
  `process_text_turn(message, conversation_id, schedule_consolidation=...)`,
  `evaluate_authorization`, `record_authorization_decision`, and
  `HouseholdKnowledgeTools(PolicyGatedV4Reader())`.
- Produces: `_voice_event_from_transcript(message) -> CognitiveEvent[TextTurnPayload]`,
  `_public_unknown_voice_actor(event) -> ActivePersonContext`, and
  `_voice_controller(background_tasks) -> CognitiveController` local router
  helpers.

- [x] **Step 1: Add the voice event factory.**

  In `transcribe.py`, import `UTC`, `date`, `datetime`, and `uuid4`, plus the
  existing cognitive contracts.  Create a new event for every successful STT
  result with:

  ```python
  event_type = "text.turn"
  source = "audio.transcribe"
  payload = TextTurnPayload(
      message=message,
      conversation_id=new_interaction_scope(),
  )
  ```

  Set `occurred_at` and `recorded_at` from one `datetime.now(UTC)` value.
  Generate fresh `event_id` and `correlation_id`; do not expose either in the
  HTTP response.

- [x] **Step 2: Add the unknown actor and controller composition helpers.**

  The actor helper returns `ActivePersonContext` with `person_id=None`,
  `display_name=None`, `status=ActivePersonStatus.UNKNOWN`,
  `role=HouseholdRole.UNKNOWN`, no evidence, and a zero
  `ConfidenceBasis.NOT_APPLICABLE` confidence.  Its explanatory reason must
  state that public voice has no trusted identity evidence.

  The controller helper injects `today=date.today`, the unknown actor, existing
  policy/audit collaborators, and
  `HouseholdKnowledgeTools(reader=PolicyGatedV4Reader())`.  Its `legacy_turn`
  closure calls `process_text_turn` with the event's opaque conversation scope
  and `_consolidation_scheduler(background_tasks)`.  It must not pass an
  `active_person` argument or manufacture consent.

- [x] **Step 3: Replace only classic post-STT turn construction.**

  Replace the direct `process_text_turn(...)` call in `transcribe()` with:

  ```python
  plan = await _voice_controller(background_tasks).handle(_voice_event_from_transcript(text_heard))
  ```

  Synthesize `plan.response`, log `plan.duration_ms` as the LLM/controller
  timing field, and map response/emotion/duration fields from the plan exactly
  as the old endpoint mapped `TextTurnResult`.  Keep the vision early return
  and the streaming endpoint byte-for-byte behaviorally unchanged.

- [x] **Step 4: Run the two RED tests and observe GREEN.**

  Run:

  ```powershell
  uv run pytest tests/integration/test_transcribe_pipeline.py -k voice_date -v
  uv run pytest tests/integration/test_transcribe_memory.py -k private_family -v
  ```

  Expected: both pass.  Confirm the date test never awaits legacy generation,
  and the protected test never invokes a tool or reader.

- [x] **Step 5: Add an event-contract regression test.**

  Test `_voice_event_from_transcript("hola")` directly. Assert text payload,
  `source == "audio.transcribe"`, `event_type == "text.turn"`, a fresh opaque
  `interaction:` conversation scope, UTC timestamps, and different IDs for
  two invocations.  Do not assert generated UUID values.

- [x] **Step 6: Run the router-focused suite.**

  Run: `uv run pytest tests/integration/test_transcribe_pipeline.py tests/integration/test_transcribe_memory.py tests/integration/test_transcribe_validation.py -v`

  Expected: all selected endpoint, validation, unknown-memory, and new R1
  cases pass.

### Task 3: Preserve the robot-facing integration and update acceptance docs

**Files:**

- Modify: `docs/runbooks/p0-runtime-acceptance.md`
- Modify: `docs/plans/open/0013-p0-voice-controller-bridge.md`
- Modify: `docs/architecture/current-state.md`
- Test: `tests/integration/test_transcribe_pipeline.py`

**Interfaces:**

- Consumes: unchanged `TranscribeResponse` and classic robot client transport.
- Produces: an executable R1 runbook section and an evidence-backed current
  state statement; it does not produce an R2 session or onboarding command.

- [x] **Step 1: Verify the existing happy path still exercises generic voice.**

  Update the existing happy-path assertion only as needed to make it explicit
  that a generic STT transcript remains a 200 response with unchanged fields
  and audio produced from its controller-delegated text response.

- [x] **Step 2: Run the happy-path test.**

  Run: `uv run pytest tests/integration/test_transcribe_pipeline.py -k happy_path -v`

  Expected: PASS; no robot code changes are needed because its HTTP contract
  is unchanged.

- [x] **Step 3: Update the runbook after automated proof.**

  Mark R1-01 and R1-02 as executable prerequisites, retain all R2 rows as
  pending, and add exact manual commands:

  ```powershell
  just services
  just run-server
  just run-robot
  ```

  Require an operator-recorded transcript, returned text, and audible outcome
  for the two R1 phrases.  Do not claim the family-data cases are executable.

- [x] **Step 4: Update architecture/current plan evidence.**

  State that classic voice now enters the controller with an unknown public
  actor, while trusted owner runtime access remains R2 pending. Mark this plan
  `Complete` only after all automated gates and the human-observed runtime
  cases pass.

### Task 4: Final verification, review, and delivery

**Files:**

- Review: all files modified by Tasks 1–3.

- [x] **Step 1: Run focused P0 cognitive checks.**

  Run:

  The current `just test` recipe intentionally accepts no test-path arguments,
  so run:

  ```powershell
  uv run pytest -n0 tests/unit/test_cognitive_controller.py tests/integration/test_chat_endpoint.py tests/integration/test_transcribe_pipeline.py tests/integration/test_transcribe_memory.py -v
  ```

  Then run `just test` as the full repository gate.

- [x] **Step 2: Run repository quality gates.**

  Run, in this order:

  ```powershell
  just lint
  just typecheck
  just test
  just audit
  just check
  ```

  Record exit status and test totals. Do not claim a green full suite from a
  focused test run.

- [ ] **Step 3: Perform the mandatory human runtime acceptance.**

  With `ROBOT_STREAMING=false`, run `just services`, then `just run-server`
  and `just run-robot` in separate terminals. Speak R1-01 and R1-02 exactly.
  The operator must confirm both the displayed transcript/response and audible
  Piper output. If STT mishears either phrase, record the transcript as a
  hardware/model acceptance failure rather than calling the behavior proved.

- [ ] **Step 4: Review final scope and publish.**

  Inspect `git diff --check`, `git diff --stat`, and `git status -sb`. Confirm
  no stream, robot protocol, schema, configuration, session, onboarding, or
  P1 file changed. Commit with a Conventional Commit message, push a PR, wait
  for green CI/CodeQL, merge only when clean, and verify `main` is clean.

## Stop conditions

Stop and obtain a new plan before adding trusted identity/session evidence,
R2 interview data capture, a public/HTTP administration API, any database
migration, streaming support, robot protocol/header changes, a new dependency,
or a P1 capability.  A manual runtime failure is not a reason to bypass the
controller; record it and debug it with a failing regression test.

## R1 exit criteria

R1 is complete only when:

1. Classic `/transcribe` creates a typed event and calls `CognitiveController`.
2. The public voice actor is always unknown and cannot read household data.
3. Current-date routing is deterministic and does not call the legacy delegate.
4. Generic voice continues through the controller's safe legacy delegate and
   preserves the existing API/audio contract.
5. Focused tests, full repository gates, and PR CI/CodeQL are green.
6. A human completes R1-01 and R1-02 via `just run-server` plus
   `just run-robot`, recording the result in an untracked local acceptance
   note.

## Execution evidence

- RED: the date regression returned `legacy` instead of `Hoy es 2026-08-12.`;
  the private-family regression likewise returned `legacy` before the bridge.
- GREEN: the two focused regressions passed, followed by the focused endpoint
  suite (`33 passed`).
- Final local automation: `just lint`, `just typecheck` (75 sources, zero
  issues), `just test` (574 passed), `just audit`, and `just check` passed.
- Local-model preflight: `just services` confirmed the configured Ollama chat,
  embedding, consolidation, and vision models after the local daemon was
  started.
- Still pending: the operator must perform R1-01 through R1-03 with actual
  microphone, server, robot client, Piper output, and the untracked acceptance
  record. This pending evidence prevents an R1 or P0 completion claim.
