# P0-C2 — Visual dialogue controller parity

> **Status:** Implemented in the current feature branch — automated gates
> green; operator acceptance pending.
> **Scope:** P0-C2 only. This is not facial identity, enrollment, trusted
> sessions, household onboarding, or P1.

## Objective

Route `POST /vision/respond` through the existing small typed
`CognitiveController` before generic text generation. The route may obtain a
local, one-frame scene description, but that description remains ephemeral
perception: it is not identity evidence, authorization, or durable memory.

## Evidence revalidated

- The prior route called `process_text_turn(...)` directly after
  `perceive_scene(...)`; C2 replaces that bypass with the controller boundary.
- `server/src/server/vision/perception.py::perceive_scene` is the scene-only
  path. `perceive()` includes face handling and must remain unused by public
  visual dialogue.
- `server/src/server/routers/transcribe.py` composes the public unknown actor,
  `CognitiveController`, authorization audit writer, and v4 tool seam for the
  audio route. C2 uses the same service boundary with an independent
  `vision.respond` event source.

## Invariants

1. Preserve the existing multipart image input and `TranscribeResponse` output.
2. Use one fresh opaque interaction scope per visual request.
3. Every visual question creates a typed `CognitiveEvent[TextTurnPayload]` with
   source `vision.respond` and an UNKNOWN public actor.
4. Deterministic or denied controller plans must not call
   `process_text_turn`, the LLM, legacy memory retrieval, or consolidation.
5. Generic visual questions retain the existing `process_text_turn` closure and
   pass only the current scene text as `perception`.
6. `perceive_scene` remains the only public visual perception function;
   `perceive`, face matching, and enrollment remain disconnected.
7. Enrollment phrases retain their existing quarantine response and never read
   an image for biometric enrollment or write a biometric profile.
8. Vision/VLM failure retains the existing blind-turn fallback
   `PERCEPTION_FAILED`; it is not persisted.

## Non-goals

- No changes to `/transcribe`, `/transcribe/stream`, robot audio, WAV, or
  NDJSON behaviour.
- No identity resolution from a face, image, name, VLM response, or question.
- No P0-C3 audio-script work or P0-C4 vocabulary expansion in this slice.
- No schema, migration, cloud, UI, or new dependency.

## Data flow

```text
image + text
  -> validate image
  -> perceive_scene (or ephemeral PERCEPTION_FAILED / enrollment notice)
  -> CognitiveEvent(source=vision.respond, scope=interaction:<uuid>)
  -> CognitiveController.handle
       -> deterministic/denied ResponsePlan -> TTS -> response
       -> generic legacy closure(perception=current scene) -> TTS -> response
```

## TDD slices

### 1. RED — controller decision before legacy visual turn

Add integration tests in `tests/integration/test_vision_dialog.py` proving:

- `"¿Qué fecha es hoy?"` returns the deterministic date plan, neutral emotion,
  and never awaits `process_text_turn`.
- `"¿Cómo se llaman mis hijos?"` is denied before legacy generation, writes a
  safe authorization audit event with no person or protected value, and never
  awaits `process_text_turn`.
- Existing generic `"¿qué ves?"` still calls legacy processing once with the
  current `perception`, uses a fresh internal scope, and never calls
  `vision.perceive`.

Run the focused tests and retain their expected RED failures: visual deterministic
and denied requests currently reach `process_text_turn`.

### 2. GREEN — smallest visual adapter

In `server/src/server/routers/vision.py`:

- add only route-local composition helpers matching the public audio adapter:
  typed event creation, public UNKNOWN actor, date boundary, and controller
  composition;
- make the generic closure call `process_text_turn(message, scope,
  perception=perception)`;
- replace the direct call in `vision_respond` with controller handling;
- preserve `_run_tts` and the response envelope.

Do not refactor common audio/vision helpers in this slice; deduplication is a
separate low-risk follow-up after all public-route parity is proven.

### 3. Regression and inspection

Run the focused vision dialogue and image-contract tests, the cognitive
controller tests, then full quality gates. Inspect the diff for direct public
calls from `vision_respond` to `process_text_turn` and verify no route calls
`vision.perceive`.

## Verification

Automated gates:

```powershell
uv run pytest -n0 tests/integration/test_vision_dialog.py -v
uv run pytest -n0 tests/integration/test_vision_endpoint.py -v
uv run pytest -n0 tests/unit/test_cognitive_controller.py -v
just lint
just typecheck
just test
just audit
just check
git diff --check
```

Operator acceptance remains part of the combined P0-C runbook, after C1–C4:
with `VISION_ENABLED=true`, ask through the real `just run-server` +
`just run-robot` path for a scene, then record literal STT text, response,
audible output, route, and pass/fail. Do not call C2 or P0 accepted before that
evidence exists.

## Rollback

The change is adapter-local and has no schema/data migration. Revert the C2
commit only if the public visual contract regresses; no stored data requires
repair.

## Execution evidence

Observed on 2026-08-14 before merge or operator-acceptance claims:

- **RED:** visual date and protected-family requests reached the legacy text
  delegate; the initial date seam did not exist.
- **GREEN:** the two new C2 cases passed, then `12` visual-dialogue tests and
  `34` focused visual/controller tests passed. The final combined full suite
  passed `589` tests.
- **Independent review:** no P0 blocker. The recommended event-contract and
  no-v4-reader/tool assertions were added; the visual-dialogue suite was run
  again with `12 passed`.
- **Static gates:** final `just lint`, `just typecheck`, `just audit`, and
  `just check` passed. `git diff --check` passed.

Still required: the documented real camera/voice operator run through
`just run-server` and `just run-robot`. This plan does not re-enable facial
identity or enrollment.
