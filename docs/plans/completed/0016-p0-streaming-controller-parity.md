# P0-C1 streaming controller parity implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Status:** Implemented in the current feature branch — automated gates green;
operator acceptance pending.

**Goal:** Make every `POST /transcribe/stream` turn apply the existing typed
controller and public-unknown policy before it can reach streaming LLM,
memory, consolidation, or a v4 reader, while preserving generic sentence
streaming and the NDJSON contract.

**Architecture:** Split the controller's existing work into a policy/tool
decision phase and a legacy-generation phase. The stream adapter asks the
controller to decide once: a non-generic `ResponsePlan` is rendered as a
single safe NDJSON audio response, while `None` means only generic conversation
may continue through the existing `prepare_text_turn()` and `stream_pipeline()`
path. This keeps classification and authorization in one place rather than
copying them into the stream router.

**Tech stack:** Python 3.12, FastAPI, Pydantic, pytest, existing local Piper,
existing NDJSON schemas; no dependency, migration, model, or HTTP-contract
change.

## Global constraints

- Read `AGENTS.md`, `docs/architecture/implementation-guardrails.md`,
  `docs/architecture/README.md`,
  `docs/architecture/p0-runtime-policy-audit.md`, and
  `docs/plans/0014-p0-runtime-policy-hardening-design.md` completely before
  implementation.
- Preserve WAV 16 kHz, mono, signed int16; multipart field `audio`; and
  `application/x-ndjson` contracts.
- Preserve event order: `text_heard`, exactly one `emotion`, zero or more
  `audio`, then one final `done` event.
- Public stream input is always an unknown actor. Text, name, voice,
  `conversation_id`, face, or an HTTP field cannot establish identity or
  permission.
- A protected/deterministic branch must not call `prepare_text_turn`, the
  streaming LLM, `record_text_turn`, a v4 reader, or consolidation. A protected
  decision must still use the existing safe audit writer.
- Do not alter classic `/transcribe`, robot code, visual routing, data schema,
  enrollment, sessions, consent, P1 identity, or the API response model.
- No commit, push, PR, database mutation outside tests, model download, or
  hardware action is implied by this plan.

## Required reading and permitted files

Read the following current implementation and tests before writing a test:

- `server/src/server/cognition/controller.py`
- `server/src/server/cognition/response_plan.py`
- `server/src/server/routers/transcribe.py`
- `server/src/server/streaming.py`
- `server/src/server/schemas_streaming.py`
- `tests/unit/test_cognitive_controller.py`
- `tests/integration/test_transcribe_stream.py`
- `tests/integration/test_transcribe_stream_resilience.py`
- `robot/src/robot/server_client.py`
- `docs/runbooks/p0-runtime-acceptance.md`

Permitted implementation scope:

- `server/src/server/cognition/controller.py`
- `server/src/server/routers/transcribe.py`
- `server/src/server/streaming.py`
- `tests/unit/test_cognitive_controller.py`
- `tests/integration/test_transcribe_stream.py`
- `docs/plans/0014-p0-runtime-policy-hardening-design.md`
- `docs/architecture/current-state.md`
- `docs/runbooks/p0-runtime-acceptance.md`

Stop instead of widening scope if this requires a new stream event type, a
robot protocol/header change, a session/identity mechanism, a database
migration, a visual-route change, a new model/dependency, or a cloud call.

---

### Task 1: Separate controller decision from generic legacy generation

**Files:**

- Modify: `server/src/server/cognition/controller.py:119-155`
- Modify: `tests/unit/test_cognitive_controller.py`

**Interfaces:**

- Produces: `async CognitiveController.decide(event) -> ResponsePlan | None`.
- `None` means exactly `InformationNeed.GENERIC_CONVERSATION` and never calls
  `legacy_turn`.
- `handle(event) -> ResponsePlan` remains public compatibility behavior: it
  delegates to legacy generation only when `decide()` returns `None`.

- [ ] **Step 1: Write the failing unit tests.**

  Add a generic-decision test using the existing `_event("Hola, Iroko")` and
  `legacy_turn = AsyncMock(...)`:

  ```python
  plan = await controller.decide(_event("Hola, Iroko"))

  assert plan is None
  legacy_turn.assert_not_awaited()
  ```

  Add a deterministic-date decision test using `"¿Qué fecha es hoy?"` and an
  injected date of `2026-08-12`. Assert a non-`None` plan whose response is
  exactly `"Hoy es 2026-08-12."`, source is deterministic, and whose legacy
  mock was not awaited. Keep the existing `handle()` generic-delegation test;
  it is the compatibility regression.

- [ ] **Step 2: Run the focused tests and observe RED.**

  Run:

  ```powershell
  uv run pytest -n0 tests/unit/test_cognitive_controller.py -k "decide or delegates_generic" -v
  ```

  Expected: FAIL because `CognitiveController.decide` does not yet exist.

- [ ] **Step 3: Implement the minimal decision seam.**

  Extract the current `need = _classify_information_need(...)` and non-generic
  `match` branches from `handle()` into:

  ```python
  async def decide(
      self,
      event: CognitiveEvent[TextTurnPayload],
  ) -> ResponsePlan | None:
      """Resolve closed policy/tool branches without generic generation."""
      need = _classify_information_need(event.payload.message)
      match need:
          case InformationNeed.GENERIC_CONVERSATION:
              return None
          case InformationNeed.OWN_CHILDREN_LIST | InformationNeed.OWN_CHILDREN_COUNT:
              return await self._own_children_plan(event, need)
          case InformationNeed.PROTECTED_HOUSEHOLD:
              return await self._protected_household_plan(event, need)
          case InformationNeed.RELATIONSHIP_OR_PROFILE:
              return _unknown_plan(need, "No tengo relaciones familiares estructuradas verificadas.")
          case InformationNeed.CURRENT_DATE:
              return _date_plan(get_current_date(self._today()))
          case InformationNeed.EXPLICIT_BIRTH_DATE_AGE:
              return _age_plan(_age_result(event.payload.message, self._today()))
  ```

  Rewrite `handle()` to call `decide()`, return a non-`None` plan unchanged,
  and only then call `_legacy_plan(event.payload)`. Do not move policy,
  matching, audit, or tool behavior to the router.

- [ ] **Step 4: Run the focused tests and observe GREEN.**

  Run the command from Step 2. Expected: PASS; generic `decide()` does not
  generate, while `handle()` retains legacy behavior.

---

### Task 2: Render a safe `ResponsePlan` with the existing NDJSON envelope

**Files:**

- Modify: `server/src/server/streaming.py`
- Modify: `tests/integration/test_transcribe_stream.py`

**Interfaces:**

- Consumes: `ResponsePlan`, STT timing, request start time, and existing
  `StreamTextHeardEvent`, `StreamEmotionEvent`, `StreamAudioEvent`, and
  `StreamDoneEvent`.
- Produces:

  ```python
  async def stream_response_plan(
      *,
      text_heard: str,
      plan: ResponsePlan,
      stt_ms: int,
      request_start: float,
  ) -> AsyncIterator[str]:
  ```

- It must create no memory record and schedule no consolidation.

- [ ] **Step 1: Write failing HTTP integration tests for non-generic stream branches.**

  In `test_transcribe_stream.py`, set STT to each transcript below, monkeypatch
  `transcribe_module._today` to return `date(2026, 8, 12)`, and spy on
  `transcribe_module.prepare_text_turn`,
  `llm_streaming.generate_response_stream`, and `streaming.record_text_turn`.

  | Transcript | Required response | Required absence |
  |---|---|---|
  | `¿Qué fecha es hoy?` | one `audio` event with `Hoy es 2026-08-12.` and neutral emotion | preparation, LLM stream, memory record |
  | `¿Cómo se llaman mis hijos?` | existing non-disclosing authorization denial | preparation, LLM stream, memory record, v4 read/tool call |

  For both, parse NDJSON and assert exact event order, a non-negative `done`
  timing payload, and TTS input equal to the emitted audio text. For the
  protected case, monkeypatch the router audit writer with `AsyncMock`, assert
  it was awaited once, and assert it received no names/birth dates in metadata.

- [ ] **Step 2: Run the focused integration tests and observe RED.**

  Run:

  ```powershell
  uv run pytest -n0 tests/integration/test_transcribe_stream.py -k "stream_date or stream_private" -v
  ```

  Expected: FAIL because the endpoint currently prepares a legacy text turn
  before making any controller decision.

- [ ] **Step 3: Implement the plan renderer.**

  Import `ResponsePlan` in `streaming.py`. Add a separate generator that emits
  precisely one safe, non-streamed spoken response:

  ```python
  async def stream_response_plan(...):
      """Render an already-authorized plan without LLM or memory work."""
      yield StreamTextHeardEvent(value=text_heard).model_dump_json() + "\n"
      yield StreamEmotionEvent(value=plan.emotion).model_dump_json() + "\n"
      audio_base64, duration_ms = await tts.synthesize(plan.response)
      yield StreamAudioEvent(
          text=plan.response,
          audio_base64=audio_base64,
          duration_ms=duration_ms,
      ).model_dump_json() + "\n"
      total_ms = _elapsed_ms(request_start)
      _log_pipeline_timing(stt_ms, plan.duration_ms, duration_ms, total_ms)
      yield StreamDoneEvent(
          stt_ms=stt_ms,
          llm_ms=plan.duration_ms,
          tts_ms=duration_ms,
          total_ms=total_ms,
      ).model_dump_json() + "\n"
  ```

  Do not call `record_text_turn`, `prepare_text_turn`, an LLM, or a
  consolidation scheduler from this function.

- [ ] **Step 4: Run the focused integration tests and observe GREEN.**

  Run the command from Step 2. Expected: PASS with the exact existing NDJSON
  envelope and no generic-stream collaborators used by safe plans.

---

### Task 3: Route streaming through the controller without changing generic streaming

**Files:**

- Modify: `server/src/server/routers/transcribe.py:222-261`
- Modify: `tests/integration/test_transcribe_stream.py`

**Interfaces:**

- Consumes: `_voice_event_from_transcript()`, `_voice_controller()`,
  `CognitiveController.decide()`, `stream_response_plan()`, and the existing
  `stream_pipeline()`.
- Generic input keeps the existing `PreparedTextTurn` and sentence-streaming
  code path, with the event's one generated internal scope.

- [ ] **Step 1: Extend the existing generic scope regression before implementation.**

  In `test_stream_prepares_shared_voice_turn`, assert the router constructs one
  event and that the `conversation_id` passed to `prepare_text_turn` is the
  same `interaction:...` value held in that event. Preserve its assertion that
  `record_text_turn` receives the same scope after streamed generation.

- [ ] **Step 2: Run the generic scope test and observe RED.**

  Run:

  ```powershell
  uv run pytest -n0 tests/integration/test_transcribe_stream.py -k prepares_shared_voice_turn -v
  ```

  Expected: FAIL only after the new assertion is added, because stream routing
  still constructs a bare `new_interaction_scope()` instead of an event.

- [ ] **Step 3: Make the smallest router change.**

  After successful STT, replace the direct preparation with this sequence:

  ```python
  event = _voice_event_from_transcript(text_heard)
  plan = await _voice_controller(background_tasks).decide(event)
  if plan is not None:
      return StreamingResponse(
          stream_response_plan(
              text_heard=event.payload.message,
              plan=plan,
              stt_ms=stt_ms,
              request_start=request_start,
          ),
          media_type="application/x-ndjson",
      )

  prepared = await prepare_text_turn(
      event.payload.message,
      event.payload.conversation_id,
  )
  ```

  Keep the existing `stream_pipeline(...)` call and its consolidation scheduler
  unchanged below that branch. Import only `stream_response_plan`; do not
  create a router-level classifier, actor, tool, or audit copy.

- [ ] **Step 4: Run all stream integration and resilience tests.**

  Run:

  ```powershell
  uv run pytest -n0 tests/integration/test_transcribe_stream.py tests/integration/test_transcribe_stream_resilience.py tests/integration/test_transcribe_validation.py -v
  ```

  Expected: PASS. The generic happy path must still generate sentence-sized
  audio and record a safe generic turn; date and protected paths must not.

---

### Task 4: Update P0 evidence and perform acceptance in the real route

**Files:**

- Modify: `docs/plans/0014-p0-runtime-policy-hardening-design.md`
- Modify: `docs/architecture/current-state.md`
- Modify: `docs/runbooks/p0-runtime-acceptance.md`

- [ ] **Step 1: Record only verified implementation evidence.**

  Mark P0-C1 complete only after Tasks 1–3 and final gates pass. State that
  classic and stream public audio use the controller; do not state that visual
  dialogue, client QA audio normalization, bounded phrase coverage, P1
  identity, or family access is complete.

- [ ] **Step 2: Run focused and repository gates.**

  ```powershell
  uv run pytest -n0 tests/unit/test_cognitive_controller.py tests/integration/test_transcribe_stream.py tests/integration/test_transcribe_stream_resilience.py tests/integration/test_transcribe_validation.py -v
  just lint
  just typecheck
  just test
  just audit
  just check
  git diff --check
  ```

  Record exact command outcomes and counts. `just check` must run from the
  feature branch, never `main`.

- [ ] **Step 3: Perform the mandatory local operator acceptance.**

  Use a disposable acceptance database and loopback server. Set
  `ROBOT_STREAMING=true` and `VISION_ENABLED=false`, run `just services`, then
  `just run-server` and `just run-robot` in separate terminals. Record literal
  STT, returned text, audible Piper output, route, and pass/fail for:

  | Case | Spoken text | Required result |
  |---|---|---|
  | S1 | `¿Qué día es hoy?` | Local date only; no LLM/family response. |
  | S2 | `¿Cómo se llaman mis hijos?` | Non-disclosing authorization denial; no protected value. |
  | S3 | `Hola, Iroko.` | Normal sentence-streamed generic reply and audible output. |

  If STT produces a materially different transcript, record the literal text
  and fail the case; do not reinterpret it as a pass. Restore the local setting
  after the run. This is a local operator note, not a tracked household record.

## Final completion criteria

- Controller decision and compatibility tests are green.
- `/transcribe/stream` reaches the controller exactly once per successful STT
  transcript.
- Safe plans render valid NDJSON with one audio response and no LLM/memory
  side effect.
- Generic turns retain existing incremental LLM/TTS behavior and scope
  isolation.
- All listed checks, a clean diff check, and the S1–S3 operator evidence pass.
- P0-C2, P0-C3, and P0-C4 remain explicitly open; this plan alone does not
  close P0.

## Execution evidence

The following evidence was observed on 2026-08-14 in the feature branch before
any merge or operator acceptance claim:

- **RED:** `CognitiveController.decide()` tests failed with `AttributeError`
  before the decision seam existed. Streaming date and protected-request tests
  then failed because the legacy stream emitted `joy` rather than the required
  neutral deterministic/policy response.
- **Focused GREEN:** controller decision compatibility: `3 passed`; protected
  and deterministic streaming branches: `2 passed`; full stream, stream
  resilience, and validation selection: `29 passed`; complete controller unit
  suite: `11 passed`.
- **Repository gates:** C1 alone completed with `578 passed`; after C2–C4 the
  combined final `just test` completed with `589 passed`. `just audit`
  reported no known vulnerabilities; `just check` passed all hooks, including
  Ruff, formatting, mypy, pyright, deptry, vulture, and secret detection.
- **Independent review:** no P0 blocker found. The review-required assertions
  for NDJSON shape, timings, TTS input, and safe audit arguments were added and
  re-executed successfully.

Still required: execute S1–S3 through the real `just services`,
`just run-server`, and `just run-robot` path on a disposable database after the
remaining P0-C slices are complete. Do not call P0-C1 or P0 closed before that
record exists.
