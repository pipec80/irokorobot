# P0-C7 Grounded Visual Dialogue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Status:** Complete and operator-confirmed on real hardware (2026-08-25) — see
[Execution Evidence](#execution-evidence) below. `ACTIVE_IDENTITY` consumes the
same request-scoped owner grant a household read already uses: it greets the
owner by name when fresh authenticated evidence resolves one, and speaks the
fixed unknown copy otherwise.

## Current code audit and reuse boundary

This plan has not been executed as specified. The current `/vision/respond`
route already creates a typed event, applies controller/policy parity, validates
the image contract, obtains one ephemeral scene through `perceive_scene`, and
synthesizes through Piper. The existing VLM description transport, enrollment
quarantine, and robot camera workflow are reusable production foundations.

The remaining C7 gap is precise: visual intent is still owned partly by
`vision/triggers.py`; `/vision/respond` reads the frame before the planned typed
intent preflight; no `SceneDescriptionRequest` decision union exists; and the
planned direct, grounded VLM-to-TTS path and physical acceptance are absent.
Implementation must migrate those seams, not replace vision, the controller,
Piper, image validation, or the robot workflow. Delete the trigger module only
after every caller is proven migrated.

**Goal:** Route visual, active-identity, and biometric-enrollment requests
through typed cognition so scene descriptions are spoken directly from one
local VLM call while identity/enrollment receive safe deterministic responses
without camera or model use.

**Architecture:** Extend the C5 resolver with three bounded needs and one
`SceneDescriptionRequest` capability type. The controller returns either a
closed `ResponsePlan`, that capability request, or `None`; each channel adapter
handles the union exhaustively. Only `/vision/respond` may fulfill a scene
request by reading one ephemeral frame. Its VLM description goes unchanged to
Piper, bypassing the textual LLM and memory.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, existing Ollama VLM and Piper,
pytest, existing HTTP/image/audio contracts; no dependency, database,
biometric, WorldState, scene-graph, or API-breaking change.

## Global Constraints

- C5 is a hard dependency: use its `IntentResolution` service and do not build
  a second authority in `vision/triggers.py`.
- Revalidate C6 because stream safe-plan rendering and terminal rules must
  remain green.
- Recognition is evidence, not authorization. P0 does not perform face/voice
  recognition, enrollment, fusion, persistence, or identity grant.
- `ACTIVE_IDENTITY` says exactly `Todavía no puedo confirmar quién sos.` when no
  fresh authenticated evidence resolves. After PC-1 lands, an explicitly
  authenticated owner is greeted instead; specify that branch when this plan
  is picked up.
- `BIOMETRIC_ENROLLMENT` says exactly
  `Todavía no puedo registrar rostros: hace falta administración local y consentimiento.`
  This spoken text is separate from the stable `/vision/enroll` HTTP detail.
- Scene-unavailable copy is exactly
  `Ahora mismo no puedo mirar desde este canal.`
- VLM-failure copy is exactly
  `Perdón, ahora mismo no pude ver la escena.`
- In typed dialogue adapters, only `SCENE_DESCRIPTION` may request/read/decode
  a frame or call the VLM. The existing dedicated `/vision/describe` endpoint
  remains a valid direct image-description API. All other dialogue needs run
  preflight first, including when `VISION_ENABLED=false`.
- A scene description is current perception with `KnowledgeStatus.UNKNOWN`,
  not household truth. Raw frames/descriptions remain ephemeral and are never
  added to memory, consolidation, audit payloads, or a prompt for the text LLM.
- The VLM prompt receives a fixed code-owned task, never the raw user utterance.
  P0 promises a general scene description, including for `qué tengo en la mano`.
- Preserve image contract (one JPEG/PNG/WebP/GIF/BMP frame, max 1280x720), WAV
  16 kHz mono signed-int16, classic/streaming response envelopes, and the
  server/robot boundary.
- `PERCEPTION_FAILED` remains a legacy meta-instruction; do not speak it or use
  it as the new user-facing fallback.

## File Map

Modify:

- `server/src/server/cognition/intent_resolution.py`
- `server/src/server/cognition/response_plan.py`
- `server/src/server/cognition/controller.py`
- `server/src/server/cognition/__init__.py`
- `server/src/server/routers/transcribe.py`
- `server/src/server/routers/chat.py`
- `server/src/server/routers/vision.py`
- `server/src/server/vision/describe.py`
- `server/src/server/vision/__init__.py` — remove obsolete trigger exports.
- C5/C6 tests plus vision tests named below.

Create:

- `tests/unit/test_vision_describe.py` for fixed prompt/payload transport.

Delete after all callers move to typed cognition:

- `server/src/server/vision/triggers.py`
- `tests/unit/test_vision_triggers.py`

Do not modify face recognition/enrollment services, embeddings, database
schema, robot camera workflow, WorldState, sensor code, or model settings.

---

### Task 1A: Extend typed cognition with visual needs and one scene capability

**Files:**

- Modify: `server/src/server/cognition/intent_resolution.py`
- Modify: `server/src/server/cognition/response_plan.py`
- Modify: `server/src/server/cognition/controller.py`
- Modify: `server/src/server/cognition/__init__.py`
- Modify: `tests/fixtures/intent_resolution_es.json`
- Modify: `tests/unit/test_intent_resolution.py`
- Modify: `tests/unit/test_cognitive_controller.py`
- Modify: `tests/unit/test_cognitive_models.py`

**Interfaces:**

Add enum values:

```python
SCENE_DESCRIPTION = "scene_description"
ACTIVE_IDENTITY = "active_identity"
BIOMETRIC_ENROLLMENT = "biometric_enrollment"
```

Add contracts:

```python
class SceneDescriptionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    need: Literal[InformationNeed.SCENE_DESCRIPTION] = InformationNeed.SCENE_DESCRIPTION


type ControllerDecision = ResponsePlan | SceneDescriptionRequest | None
```

Add `ResponseSource.CURRENT_PERCEPTION`. Change
`CognitiveController.decide(event: CognitiveEvent[TextTurnPayload]) ->
ControllerDecision`. `handle()` must raise
a bounded `RuntimeError` if it receives `SceneDescriptionRequest`; an adapter
must fulfill or reject that capability instead of leaking it to legacy text.

- [ ] **Step 1: Add resolver RED cases and precedence tests.**

  Migrate every current trigger variant into the reviewed resolver corpus
  before deleting the legacy module. Scene variants are `qué ves`, `qué estás
  viendo`, `qué miras`, `qué observas`, `mira esto`, `mira lo que`, `puedes
  ver`, `podés ver`, `ves esto`, `ves algo`, `qué tengo en la mano`, `describe
  lo que ves`, `dime qué ves`, and `decime qué ves`. Identity variants are
  `quién soy`, `me reconoces`, `me conoces`, `sabes quién soy`, `quién está
  aquí`, and `quién está frente`; classify the last two as ACTIVE_IDENTITY in
  bounded P0 rather than claiming who is visible. Biometric variants are
  `aprende`, `recuerda`, or `memoriza` `mi/su/la cara`; `mírame/mírala/míralo
  bien`; `te presento a`; and `conoce a`.

  Any unequivocal biometric cue resolves to BIOMETRIC_ENROLLMENT even when no
  name is present, so `aprende mi cara` cannot fall through to the LLM. With or
  without `soy PersonaDePrueba`, the resolver neither extracts nor retains a
  name and returns the same non-sensitive rule ID. Retain the legacy module's
  existing negative controls as generic corpus cases. Fix and test total precedence as:
  own-child/protected household; biometric enrollment; active identity;
  ambiguous/current date; explicit age; relationship/profile; scene; generic.
  Include mixed cases `¿Me reconoces? Aprende mi cara, soy PersonaDePrueba`
  -> enrollment, `¿Qué ves y cómo se llaman mis hijos?` -> protected, and
  `¿Qué fecha ves hoy?` -> current date. Assert enrollment `rule_id` contains
  neither the utterance nor `personadeprueba`.

- [ ] **Step 2: Add controller RED tests.**

  Assert scene returns `SceneDescriptionRequest` without legacy/policy/memory;
  identity/enrollment return the exact fixed ResponsePlans with no legacy call;
  `handle(scene_event)` raises rather than delegating. Extend enum/export/model
  assertions.

- [ ] **Step 3: Run RED.**

  ```powershell
  uv run pytest -n0 tests/unit/test_intent_resolution.py tests/unit/test_cognitive_controller.py tests/unit/test_cognitive_models.py -k "scene or identity or biometric or enroll or reexports" -v
  ```

  Expected: enum/capability types and resolution rules are missing.

- [ ] **Step 4: Implement the minimal union and rules.**

  Extend only the existing C5 resolver. Do not touch old trigger files in this
  task; Task 1C removes them atomically with their final callers. Add a
  parametrized equivalence test covering every migrated positive and negative
  variant listed above. In controller
  `decide()`, return fixed
  plans for identity/enrollment, the capability for scene, and preserve all
  existing policy/tool branches. Keep the capability type specific; do not
  introduce a generic framework or registry.

- [ ] **Step 5: Run the unit checkpoint without committing.**

  ```powershell
  uv run pytest -n0 tests/unit/test_intent_resolution.py tests/unit/test_cognitive_controller.py tests/unit/test_cognitive_models.py -v
  ```

  Expected: typed cognition is locally GREEN, but the repository is
  intentionally not committed because `/vision/respond` still uses `handle()`.
  Keep 1A-1C as one atomic working-tree change; do not claim integrated GREEN.

---

### Task 1B: Handle the decision union in non-camera channels

**Files:**

- Modify: `server/src/server/routers/transcribe.py`
- Modify: `server/src/server/routers/chat.py`
- Modify: `tests/integration/test_transcribe_pipeline.py`
- Modify: `tests/integration/test_transcribe_stream.py`
- Modify: `tests/integration/test_chat_endpoint.py`
- Modify: `tests/integration/test_vision_dialog.py`

**Interfaces and channel matrix:**

| Need | `/transcribe` | `/transcribe/stream` | `/chat` |
|---|---|---|---|
| closed `ResponsePlan` | exact plan, TTS, no frame | `stream_response_plan` | exact plan |
| scene + vision on | existing cue, `vision_requested=true` | fixed unavailable plan | fixed unavailable plan |
| scene + vision off | fixed unavailable, false | fixed unavailable plan | fixed unavailable plan |
| generic `None` | existing generic handling | existing `stream_pipeline` | existing generic handling |

Identity/enrollment/protected/date are closed plans and must never request a
frame regardless of `VISION_ENABLED`. Parametrize `VISION_ENABLED=True/False`
for scene, identity, and enrollment in every channel; classic-disabled scene is
required to prove it cannot fall through to the text LLM.

- [ ] **Step 1: Write classic/stream/chat matrix tests.**

  Assert scene cue only on classic with vision enabled. Assert scene unavailable
  text on classic-disabled, stream, and chat. For identity and enrollment on all
  three channels and both vision settings assert exact fixed copy,
  `vision_requested=false` where present, audible TTS on audio routes, and no
  VLM, text LLM, frame cue,
  enrollment, memory, or consolidation. Replace the old test that expected an
  enrollment phrase to request a frame with
  `test_transcribe_enrollment_phrase_is_rejected_without_frame` in
  `test_vision_dialog.py`.

- [ ] **Step 2: Run RED.**

  ```powershell
  uv run pytest -n0 tests/integration/test_chat_endpoint.py tests/integration/test_transcribe_pipeline.py tests/integration/test_transcribe_stream.py tests/integration/test_vision_dialog.py tests/unit/test_vision_triggers.py -k "scene or vision or identity or biometric or enroll" -v
  ```

  Expected: classic bypasses controller for identity/enrollment, stream/chat do
  not handle a scene capability, and the old enrollment test requests a frame.

- [ ] **Step 3: Implement exhaustive adapter handling.**

  In classic transcribe create the event and call `decide()` before any visual
  action. Render ResponsePlans directly; translate a scene capability to cue or
  unavailable plan based on setting; only `None` calls `handle()`/legacy. In
  streaming translate scene capability to a deterministic unavailable
  ResponsePlan and use C6 `stream_response_plan`. In chat do the same without
  TTS. Put `scene_unavailable_plan() -> ResponsePlan` in
  `cognition/response_plan.py` and re-export it; routers import this public
  helper rather than each other's private constants. Remove trigger usage from
  transcribe/chat now, but retain the trigger module/export solely for the
  existing `/vision/respond` caller until Task 1C removes that final use and
  deletes the obsolete module atomically. The typed resolver does not extract a
  person's name.

- [ ] **Step 4: Run the non-camera checkpoint without committing.**

  ```powershell
  uv run pytest -n0 tests/integration/test_chat_endpoint.py tests/integration/test_transcribe_pipeline.py tests/integration/test_transcribe_stream.py -k "scene or identity or biometric or enroll" -v
  uv run pytest -n0 tests/integration/test_vision_dialog.py::test_transcribe_enrollment_phrase_is_rejected_without_frame -v
  ```

  Do not run or claim direct visual-dialogue
  GREEN until Task 1C migrates that endpoint. Do not commit this intermediate
  state.

---

### Task 1C: Ground `/vision/respond` and commit the atomic C7 core

**Files:**

- Modify: `server/src/server/routers/vision.py`
- Modify: `server/src/server/vision/__init__.py`
- Delete: `server/src/server/vision/triggers.py`
- Delete: `tests/unit/test_vision_triggers.py`
- Modify: `tests/integration/test_vision_dialog.py`
- Test: `tests/integration/test_vision_endpoint.py`
- Test: `tests/integration/test_vision_enroll_service.py`

**Interfaces:**

- Build event and call controller `decide()` before `settings.vision_enabled`
  and before `_read_contract_image()`.
- A closed ResponsePlan returns 200 and TTS even with vision disabled or invalid
  unused image bytes; the application never calls `_read_contract_image`,
  decode, or a model. FastAPI has already received the multipart upload.
- A scene capability alone checks vision, validates the frame, calls
  `perceive_scene()` once, and returns a `ResponsePlan` with
  `source=CURRENT_PERCEPTION`, `status=UNKNOWN`, exact description, and neutral
  emotion.
- A generic direct non-scene request may use legacy conversation with
  `perception=None`; it never reads the supplied image and is not blocked by
  `VISION_ENABLED=false`.
- Only scene + disabled returns the existing 503.

- [ ] **Step 1: Rewrite visual-dialogue RED tests.**

  Replace the test that expects an in-character second LLM transformation. Use
  perception text exactly
  `Una persona con gafas sostiene una esfera roja cerca de su boca.` and assert
  response and TTS input match byte-for-text, with no `relajada`, `concentrada`,
  or `sostienes las gafas`; `process_text_turn`/text LLM are not called. Add VLM
  error -> exact spoken fallback. Add identity/enrollment/protected/date direct
  requests, with vision enabled and disabled, asserting no application
  upload read/decode,
  perception, legacy, or enrollment. Add direct generic non-scene behavior and
  retain scene image-contract 422 tests.

- [ ] **Step 2: Run RED.**

  ```powershell
  uv run pytest -n0 tests/integration/test_vision_dialog.py tests/integration/test_vision_endpoint.py tests/integration/test_vision_enroll_service.py -v
  ```

  Expected: current endpoint checks vision/reads/VLM before typed preflight and
  sends scene perception through a second textual LLM.

- [ ] **Step 3: Implement preflight and direct grounding.**

  Refactor `_vision_controller` so generic legacy receives no perception. Put
  `current_perception_plan(description: str) -> ResponsePlan` beside
  `scene_unavailable_plan()` in `cognition/response_plan.py`. In `vision_respond`,
  validate non-empty text, decide, render closed plan immediately, reject or
  fulfill scene capability, and call `handle()` only for `None`. On
  `VisionError`, render the exact user-facing fallback directly. Never pass the
  description or fallback meta-instruction into `process_text_turn`. Remove the
  final `wants_enroll` call/export, delete `vision/triggers.py` and its obsolete
  unit test, and verify `rg -n "wants_vision|wants_enroll" server/src tests`
  returns no callers.

- [ ] **Step 4: Run integrated GREEN and commit Tasks 1A-1C together.**

  ```powershell
  uv run pytest -n0 tests/unit/test_intent_resolution.py tests/unit/test_cognitive_controller.py tests/unit/test_cognitive_models.py tests/integration/test_chat_endpoint.py tests/integration/test_transcribe_pipeline.py tests/integration/test_transcribe_stream.py tests/integration/test_vision_dialog.py tests/integration/test_vision_endpoint.py tests/integration/test_vision_enroll_service.py -v
  just lint
  git add server/src/server/cognition server/src/server/routers/transcribe.py server/src/server/routers/chat.py server/src/server/routers/vision.py server/src/server/vision/__init__.py tests/fixtures/intent_resolution_es.json tests/unit/test_intent_resolution.py tests/unit/test_cognitive_controller.py tests/unit/test_cognitive_models.py tests/integration/test_chat_endpoint.py tests/integration/test_transcribe_pipeline.py tests/integration/test_transcribe_stream.py tests/integration/test_vision_dialog.py tests/integration/test_vision_endpoint.py tests/integration/test_vision_enroll_service.py
  git add -u server/src/server/vision/triggers.py tests/unit/test_vision_triggers.py
  git commit -m "fix(vision): ground typed visual dialogue"
  ```

---

### Task 2: Harden the fixed local VLM task as secondary defense

**Files:**

- Modify: `server/src/server/vision/describe.py`
- Create: `tests/unit/test_vision_describe.py`

**Interfaces:**

The fixed `_DESCRIBE_PROMPT` must require Spanish neutral visible evidence,
explicit uncertainty, and prohibit unsupported identity, gender, relationship,
intent, emotion/mental state, and hidden-container/content claims. The Ollama
payload keeps one image and preserves the current temperature; changing model
sampling is not part of the approved cause/fix. The caller's raw question
never enters this prompt.

- [ ] **Step 1: Write payload transport tests.**

  Mock the local Ollama request and inspect `json`. Assert the
  `describe_image(image: bytes)` signature has no question parameter, payload
  content equals the fixed code-owned prompt, contains every grounded rule,
  sends one image, uses configured model and `stream=false`, and preserves the
  current temperature value.
  Preserve tests for empty/unexpected backend responses.

- [ ] **Step 2: Run RED.**

  ```powershell
  uv run pytest -n0 tests/unit/test_vision_describe.py -v
  ```

  Expected: tests/module are absent and current prompt lacks grounded limits.

- [ ] **Step 3: Implement the fixed prompt and run GREEN.**

  Keep the prompt concise and code-owned; do not add a second model, output
  validator, or sampling change.

  ```powershell
  uv run pytest -n0 tests/unit/test_vision_describe.py -v
  git add server/src/server/vision/describe.py tests/unit/test_vision_describe.py
  git commit -m "fix(vision): constrain local scene descriptions"
  ```

---

### Task 3: Run full regression and physical visual acceptance

**Files:**

- Modify only after evidence: current-state, runtime-policy audit, Plan 0014,
  plans README, runtime runbook, and this plan.

- [ ] **Step 1: Run focused and repository gates.**

  ```powershell
  uv run pytest -n0 tests/unit/test_intent_resolution.py tests/unit/test_cognitive_controller.py tests/unit/test_vision_describe.py tests/unit/test_perception.py tests/unit/test_robot_app.py tests/integration/test_chat_endpoint.py tests/integration/test_transcribe_pipeline.py tests/integration/test_transcribe_stream.py tests/integration/test_transcribe_stream_resilience.py tests/integration/test_vision_dialog.py tests/integration/test_vision_endpoint.py tests/integration/test_vision_enroll_service.py -v
  just lint
  just typecheck
  just test
  just audit
  just check
  git diff --check
  ```

  Request independent review of Plan 0020, this plan, code/diff, RED/GREEN
  logs, channel matrix, no-frame/no-model assertions, and C5/C6 regression.
  Address every P0/P1 finding with a failing regression, rerun affected gates,
  and record explicit PASS before physical acceptance.

- [ ] **Step 2: Run real classic visual acceptance.**

  Use disposable DB, loopback, `ROBOT_STREAMING=false`, and
  `VISION_ENABLED=true`; run `just services`, `just run-server`, and
  `just run-robot`. Record literal STT, response, audible output, HTTP/model
  calls/timings, and pass/fail:

  | Spoken request | Required result |
  |---|---|
  | `¿Quién soy?` | fixed `quién sos` response; no cue/camera/VLM/LLM; audible |
  | `¿Qué ves?` while holding a red ball | cue then one VLM description; no `server.llm`; relation preserved; audible |
  | scene while VLM unavailable | exact spoken visual fallback; no second LLM |
  | `Aprende mi cara, soy PersonaDePrueba.` | fixed Spanish enrollment rejection; `vision_requested=false`; no frame/VLM/LLM/enrollment |
  | `¿Cómo se llaman mis hijos?` | existing denial; no camera |

  A scene description may use the grammatically feminine noun `persona`; fail
  only unsupported gender/identity/mental-state claims, not Spanish grammar.

  Reproduce VLM failure locally without disabling vision or editing tracked
  configuration: stop the server, set
  `$env:VLM_MODEL='iroko-p0-qa-model-does-not-exist'` in that server terminal,
  run `just run-server`, ask `¿Qué ves?`, and verify the exact audible fallback.
  Stop that process, run `Remove-Item Env:VLM_MODEL`, restart normally, and
  confirm `just services` again lists the configured real VLM. Do not pull the
  intentionally missing model.

- [ ] **Step 3: Update evidence and commit.**

  Mark C7 implemented only after the real run passes. Then execute the complete
  combined P0 runbook for C5+C6+C7; only that separate evidence can close P0.

  ```powershell
  git add docs/architecture/current-state.md docs/architecture/p0-runtime-policy-audit.md docs/plans/open/0014-p0-runtime-policy-hardening-design.md docs/plans/README.md docs/runbooks/p0-runtime-acceptance.md docs/plans/open/0023-p0-grounded-visual-dialogue.md
  git commit -m "docs(p0): record C7 verification"
  ```

  Run:

  ```powershell
  uv run pre-commit run --files docs/architecture/current-state.md docs/architecture/p0-runtime-policy-audit.md docs/plans/open/0014-p0-runtime-policy-hardening-design.md docs/plans/README.md docs/runbooks/p0-runtime-acceptance.md docs/plans/open/0023-p0-grounded-visual-dialogue.md
  git diff --check
  git status --short
  ```

  Final status must be clean; hook changes require
  inspection, a follow-up commit, and a rerun.

## Rollback and Stop Conditions

- Revert C7 commits; no schema/data rollback is needed because frames and
  descriptions are ephemeral.
- Stop for explicit architecture/privacy approval if implementation requires
  recognition, biometric enrollment, face/voice fusion, identity sessions,
  consent changes, perception persistence, WorldState, scene graph, tracking,
  free-form VLM question injection, or a public admin API.
- A face match must never authorize data access in this slice.

## Completion Criteria

- All channel adapters exhaustively handle closed plan, scene capability, and
  generic outcomes.
- Identity/enrollment never request a frame and speak exact safe copy.
- Scene dialogue makes one VLM call, no text-LLM call, and speaks the grounded
  description or local fallback exactly.
- Vision-disabled and direct `/vision/respond` matrix behavior is tested.
- Image/audio/API/privacy contracts, C5, and C6 remain green.
- Full gates, physical visual acceptance, and the final combined P0 runbook are
  recorded before P0 is called closed.

## Execution Evidence

- Typed-cognition, channel-matrix, and grounded-prompt RED→GREEN: run task by
  task (Tasks 1A–1C, 2); each checkpoint confirmed GREEN before the next task,
  with the intentionally non-atomic 1A/1B intermediate states never committed
  — see commits `b5528eb` (`fix(vision): ground typed visual dialogue`,
  Tasks 1A–1C atomic) and `0978388` (`fix(vision): constrain local scene
  descriptions`, Task 2).
- Repository gates on `feat/p0-c7-grounded-visual-dialogue` at `0978388`:
  `just lint`, `just typecheck` (mypy + pyright, 0 errors), `just test`
  (835/835), `just audit`, `just check`, `git diff --check` — all green.
- Independent review: performed directly (no subagent was requested for this
  session) against the plan's completion criteria — channel matrix
  exhaustiveness, no-frame/no-model assertions for identity/enrollment,
  single-VLM-call/no-second-LLM for scene dialogue, and C5/C6 regression (all
  covered by the 835/835 full-suite run). No findings.
- Physical acceptance: executed 2026-08-21 (identity/enrollment/protected
  cases) and 2026-08-25 (grounded scene description + VLM-down fallback) on
  real hardware — **PASS**, all 5 required table cases confirmed with literal
  transcripts. Full untracked evidence:
  `project-history/acceptance/2026-08-25-grounded-visual-dialogue.md`.
- Combined P0 runbook (C5+C6+C7 together, the separate P0-closing evidence):
  not yet executed — tracked as the next required step before P0 as a whole
  can be called closed.
