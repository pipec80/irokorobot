# Personal companion delivery map

> **Status:** Canonical cross-plan traceability map.
>
> **Observed:** 2026-08-21 on `main` after PR #56 (Plan 0025), PR #57
> (Plan 0026), and PR #64 (Plan 0027) merged, and Plan 0028's real-hardware
> runtime acceptance executed with a PASS verdict for the PC-1 slice.
>
> **Execution authority:** None. This map explains what exists, what is
> missing, and which bounded plan owns each gap. Only the single `NOW` item in
> the [plan router](../plans/README.md) may be considered for execution, and
> only after explicit user approval.

## North-star outcome

The first personal-companion proof is complete only when the real local path
can demonstrate both sides of the same privacy boundary:

```text
fresh authenticated Pipec
  -> “¿Quiénes son mis hijos?”
  -> authorized structured retrieval
  -> “Tus hijos son Máximo y Dominga.”
  -> audible Piper output

no fresh authentication
  -> the same question
  -> non-disclosing denial before protected retrieval
  -> no names, count, hint, or confirmation that the data exists
```

This result is not documentary RAG. The answer comes from the existing typed
v4 relationship/tool path after identity, authentication, and authorization
have succeeded. RAG remains a later memory-retrieval capability.

## Locked-posture invariant

Without fresh authentication, Iroko remains able to perceive, transcribe,
converse generally, and speak, but the actor is `unknown`: protected memory is
not read or mutated, unknown statements are not attached to Pipec, and
protected tools do not execute. A denial explains that the speaker cannot be
confirmed without revealing whether the requested fact exists.

Authentication is capability-scoped rather than a global unlock. Plans
0025–0028 create and accept only one consume-once
`personal_protected_read`/`child_data` grant. Home control, PC restart,
biometric administration, memory mutation, and actuators require future,
separately authorized capabilities and are not implied by this delivery chain.
See [ADR 0009](../adr/0009-locked-posture-and-scoped-capabilities.md).

## How the open reference documents fit

These documents describe the program but are not independent implementation
batches:

| Reference | Role | Implemented content it preserves | Open outcome it governs |
|---|---|---|---|
| [0014](../plans/completed/0014-p0-runtime-policy-hardening-design.md) | P0 runtime-policy umbrella | C1–C7, all implemented and operator-confirmed | None — combined P0 acceptance passed 2026-08-25 |
| [0015](../plans/open/0015-personal-companion-design.md) | Product direction | Reuse of the existing local cognitive/audio/memory foundations | Personal-companion stages PC-1 through PC-6 |
| [0020](../plans/completed/0020-p0-operator-qa-remediation-design.md) | Operator-QA defect umbrella | C5 via completed Plan 0021, C6 via completed Plan 0022, C7 via completed Plan 0023 | None — its own required real acceptance rerun passed 2026-08-25 |
| [0024](../plans/completed/0024-owner-authenticated-memory-mvp-design.md) | PC-1 integration design | Existing identity, policy, child-memory, and channel seams; Plans 0025–0028 merged/executed | Delivery complete — PC-1 accepted |
| [0031](../plans/open/0031-server-production-baseline-design.md) | Cross-cutting server reference capsule | Existing FastAPI/Starlette/Uvicorn and accepted server/robot contracts | Children 0032–0042, queued after Plan 0030 and before the next new identity capability |

Do not execute these reference documents from top to bottom. Their job is to retain
decisions and acceptance boundaries while the smaller plans deliver the gaps.
Three of them (0014, 0020, 0024) now live under `plans/completed/` — they
never had their own executable code or gates, and moved there once every
slice they governed closed elsewhere. 0015 remains under `plans/open/` because
PC-3 through PC-6 are still real, unstarted work. Plan 0031 remains open and
reference-only until its queued child portfolio closes.

## Code-to-outcome traceability

Evidence priority is executable code, tests, configuration, then
documentation. “Implemented” below means the named foundation exists; it does
not mean the north-star path is connected or accepted.

| Stage | Verified existing foundation | Existing tests | Verified gap | Accountable plan |
|---|---|---|---|---|
| Audio ingress and STT | [`routers/transcribe.py`](../../server/src/server/routers/transcribe.py) creates the classic typed event and preserves the WAV contract, and the streaming route now propagates identity too (Plan 0027) | [`test_transcribe_pipeline.py`](../../tests/integration/test_transcribe_pipeline.py), [`test_transcribe_validation.py`](../../tests/integration/test_transcribe_validation.py) | Real STT accuracy is confirmed with 3x recorded classic and 3x streaming hardware evidence (Plan 0028, 2026-08-21). The repeatable Whisper "small" mis-transcription of "Iroko" (Plan 0013's R1-03) is closed — root cause was a stale "Omnibot" name in `WHISPER_INITIAL_PROMPT`/`WHISPER_HOTWORDS`; fixed and reconfirmed PASS 2x (classic + streaming) on 2026-08-25. The first-utterance-after-restart quirk remains an open, non-blocking follow-up item | — |
| Owner and household setup | **Closed by [0025](../plans/completed/0025-personal-owner-bootstrap-and-pin-setup.md).** `just setup-personal` bootstraps the sole owner, confirms `child_of` v4 relations, and stores a scrypt-hashed PIN (migration 006, [`personal_setup.py`](../../server/src/server/personal_setup.py)) | [`test_personal_setup.py`](../../tests/integration/test_personal_setup.py), [`test_owner_credentials_schema.py`](../../tests/integration/test_owner_credentials_schema.py), [`test_pin_credentials.py`](../../tests/unit/test_pin_credentials.py) | None remaining for this stage | — |
| Typed identity evidence | **Closed by [0026](../plans/completed/0026-one-use-owner-authenticated-classic-turn.md) and [0027](../plans/completed/0027-one-use-owner-streaming-parity.md).** `IdentityEvidenceSource.LOCAL_UNLOCK` and `IdentitySessionRegistry.issue_for_person`/`consume_evidence` give request-bound, authenticated, consume-once evidence in both classic and streaming modes ([`identity.py`](../../server/src/server/cognition/identity.py), [`identity_sessions.py`](../../server/src/server/cognition/identity_sessions.py)) | [`test_active_person_identity.py`](../../tests/unit/test_active_person_identity.py), [`test_identity_sessions.py`](../../tests/unit/test_identity_sessions.py) | None remaining | — |
| Channel actor resolution | **Closed for classic and streaming modes by [0026](../plans/completed/0026-one-use-owner-authenticated-classic-turn.md) and [0027](../plans/completed/0027-one-use-owner-streaming-parity.md).** `X-Iroko-Identity-Token` is accepted by `/chat`, classic `/transcribe`, and `/transcribe/stream`; `OwnerRequestResolver` resolves the actor only for protected branches in every channel | [`test_owner_authenticated_turn.py`](../../tests/integration/test_owner_authenticated_turn.py), [`test_owner_unlock_endpoint.py`](../../tests/integration/test_owner_unlock_endpoint.py), [`test_owner_authenticated_stream.py`](../../tests/integration/test_owner_authenticated_stream.py) | None remaining | — |
| Intent resolution | **Closed by [0021](../plans/completed/0021-p0-typed-intent-resolution.md).** [`cognition/intent_resolution.py`](../../server/src/server/cognition/intent_resolution.py) is a new pure, typed, injected Spanish resolver (no LLM/VLM/embedding/database) with a reviewed corpus and privacy-safe `rule_id`; `cognition/controller.py` consumes it instead of an inline classifier | [`test_intent_resolution.py`](../../tests/unit/test_intent_resolution.py), [`test_cognitive_controller.py`](../../tests/unit/test_cognitive_controller.py) plus route integration suites | None remaining for C5. The garbled `protected_household`-pattern anomaly Plan 0028 surfaced (a mis-transcribed household-adjacent phrase can still consume a fresh grant while returning a stub, non-disclosing response) is unrelated to C5's own corpus and remains open for future classifier hardening | — |
| Authorization and audit | **Closed by [0026](../plans/completed/0026-one-use-owner-authenticated-classic-turn.md).** Classic public turns can now supply fresh authenticated owner evidence before policy evaluation | [`test_household_authorization_policy.py`](../../tests/unit/test_household_authorization_policy.py), [`test_household_authorization_runtime.py`](../../tests/integration/test_household_authorization_runtime.py), [`test_owner_authenticated_turn.py`](../../tests/integration/test_owner_authenticated_turn.py) | None remaining for classic mode | — |
| Structured child retrieval | **Closed by [0026](../plans/completed/0026-one-use-owner-authenticated-classic-turn.md) and [0028](../plans/completed/0028-owner-authenticated-memory-runtime-acceptance.md).** The `household_tools.py` seam is reachable from a fresh authenticated owner turn end to end in both classic and streaming modes, with 3x repeated real-hardware evidence and a direct SQLite audit-trail inspection confirming `execute_household_tool → read_household_data` ordering on every allowed disclosure | [`test_household_knowledge_tools.py`](../../tests/unit/test_household_knowledge_tools.py), [`test_p05b2_household_acceptance.py`](../../tests/integration/test_p05b2_household_acceptance.py), [`test_owner_authenticated_turn.py`](../../tests/integration/test_owner_authenticated_turn.py), [`test_owner_authenticated_stream.py`](../../tests/integration/test_owner_authenticated_stream.py) | None remaining | — |
| Audible response and streaming | Piper TTS is integrated; [`streaming_render.py`](../../server/src/server/streaming_render.py) owns C6 audible fallback and audio-before-`done` behavior; Plan 0027 added the `authentication_consumed` terminal field | [`test_transcribe_stream.py`](../../tests/integration/test_transcribe_stream.py), [`test_transcribe_stream_resilience.py`](../../tests/integration/test_transcribe_stream_resilience.py) | None remaining — Plan 0028 measured streaming as consistently faster than classic for the same answer (~1.9s vs ~2.0s total) since audio starts on the first NDJSON chunk instead of waiting for the full response body | — |
| Grounded visual dialogue (Plan 0023 / P0-C7) | **Closed by [0023](../plans/completed/0023-p0-grounded-visual-dialogue.md).** `routers/vision.py` calls the typed resolver before any frame access; only a `SceneDescriptionRequest` capability reads a frame and calls the VLM; its description goes directly to Piper — no second LLM. Identity/enrollment speak exact fixed copy without ever touching the camera. `vision/triggers.py` deleted. | [`test_vision_dialog.py`](../../tests/integration/test_vision_dialog.py), [`test_vision_endpoint.py`](../../tests/integration/test_vision_endpoint.py), [`test_vision_describe.py`](../../tests/unit/test_vision_describe.py) | None remaining — real hardware confirmed identity, enrollment, protected, grounded scene, and VLM-down fallback (2026-08-21/2026-08-25) | — |

## PC-1 artifacts delivered by Plans 0025–0028

The 2026-08-20 audit found only migrations 002–005 and no production or test
symbol for the planned PIN hash, owner-unlock prompt, request authentication
header, or `authentication_consumed` result. Plans 0025–0027 (merged) closed
every one of those gaps, and Plan 0028 proved them on real hardware:

- PIN hash: migration 006 (`owner_pin_credentials`), `cognition/pin_credentials.py`.
- Owner-unlock prompt: `server/personal_setup.py` (local CLI wizard) and
  `robot/app.py::_prompt_owner_unlock` (opt-in robot startup prompt, now
  usable with `ROBOT_STREAMING` too since Plan 0027 removed the earlier
  `SystemExit` guard).
- Request authentication header: `X-Iroko-Identity-Token`, read by `/chat`,
  classic `/transcribe`, and `/transcribe/stream`.
- `authentication_consumed` result: additive field on `ChatResponse`,
  `TranscribeResponse`, and the streaming NDJSON terminal `done` event.
- Real-hardware proof: Plan 0028 (2026-08-21) — 3x classic + 3x streaming
  allowed/replay cycles, expiry, and generic non-consumption, all audibly
  confirmed and cross-checked against the `authorization_audit_events`
  table directly.

Face recognition functions exist, but no consented runtime adapter converts a
face match into fresh authenticated request evidence. Speaker recognition is
absent; STT and VAD do not identify a speaker. Neither biometric path blocks
PC-1.

## One delivery chain

```text
0025 minimal owner/children/PIN security bootstrap — merged (PR #56)
  -> 0026 one-use authenticated classic turn — merged (PR #57)
  -> 0027 authenticated streaming parity — merged (PR #64)
  -> 0028 physical allowed/denied/replay/expiry acceptance — executed, PASS (2026-08-21)
PC-1 accepted
  -> 0021 typed intent resolution — executed, PASS (2026-08-21)
  -> 0023 grounded visual dialogue — executed, PASS (2026-08-21/2026-08-25)
  -> combined P0-C runbook (R1+C1-S+C2-V+C3-Q) — executed, PASS (2026-08-25)
       `-> 0013 R1 closed same day: root cause of R1-03's STT failure fixed
          (stale "Omnibot" name in the Whisper prompt/hotwords)
P0 fully accepted
  -> 0029 consented local face evidence (PC-2) — merged (PR #73, 2026-08-25)
  -> 0030 real-camera face acceptance — executed, provisional PASS (2026-09-01)
PC-2 accepted (provisional calibration)
```

Plan 0015 remains open as reference; PC-3 through PC-6 are still real,
unstarted work. Plans 0014, 0020, and 0024 moved to `completed/` — they
never had their own executable code or gates, and closed once every slice
they governed closed elsewhere.

## PC-2 artifacts delivered by Plan 0029

Plan 0029 connects the existing local face-recognition engine
(`vision/faces.py`) to the same typed evidence/authorization pipeline the PIN
already uses (Plan 0026), with no change to `controller.py` or
`authorization.py`:

- Biometric consent schema: migration 007 (`face_consent_grants`),
  `memory/biometric_consent.py` (`grant_face_consent`/`revoke_face_consent`/
  `has_active_face_consent`); revocation performs a real purge of
  `face_profiles` and `vec_faces` rows for that person, not a soft flag.
- `IdentityEvidenceSource.FACE` added to `_TRUSTED_IDENTIFIED_SOURCES`
  (`cognition/identity.py`); `VOICE` and `CONTEXT` remain unresolved
  (PC-3/PC-4 territory).
- In-request face resolution: `cognition/face_authentication.py` — a pure
  6-row verdict function (0 faces -> unknown, 2+ faces -> ambiguous and
  terminal — never falls through to the PIN, 1-face variations ->
  unknown/identified by match+consent+role), a lazy single-inference-per-turn
  `FaceRequestResolver`, and `compose_face_then_pin_resolver()`, which tries
  face first and falls through to the existing PIN resolver only on a
  non-ambiguous unresolved face result. A stricter, separate
  `settings.face_authentication_match_threshold` — measured by Plan 0030 at
  `0.5815`, replacing the unvalidated `0.25` default — applies on
  top of the existing generic `settings.face_match_threshold` (`0.4`).
- Authenticated enrollment: `POST /auth/owner/face/enroll` and `/revoke`
  (`routers/auth.py`), loopback-only, requiring a fresh PIN-consumed token;
  the enrolled subject is always the token's own owner, never a
  request-supplied name. The pre-existing quarantined public
  `POST /vision/enroll` is untouched and still returns 503.
- Router wiring: an optional multipart `frame` field on classic and
  streaming `/transcribe`, gated by `settings.face_authentication_enabled`
  (default `false` — with it off, the frame is never even read). An
  additive `identity_source: "face" | "local_unlock" | null` response field
  reports which evidence source authenticated the turn, never a name or
  protected value.
- Robot-side capture: opt-in (`settings.robot_face_auth_enabled`, default
  `false`) webcam frame capture attached to every turn when enabled; a
  camera failure degrades silently to no frame — it never breaks the turn.

**Known limitation, stated plainly:** this plan has no liveness or
anti-spoofing defense. A photograph of the owner held up to the camera
authenticates under this slice, exactly as every task reviewer reported. The
real mitigation is PC-4 (voice fusion), not yet built — closing Plan 0030
did not touch this gap. Real-camera calibration and acceptance (threshold
tuning, false-accept/false-reject rates, lighting, distance, glasses) closed
2026-09-01 as
[Plan 0030](../plans/completed/0030-real-camera-face-acceptance.md):
`face_authentication_match_threshold` moved from the unvalidated `0.25` to a
measured `0.5815`. Provisional — only 3 impostor identities were measured.

**Evidence (2026-08-25):** on `feat/consented-local-face-evidence`, all 7
tasks are implemented, one commit per task plus one small test-maintenance
follow-up commit (`65b8b71`, fixing two stale schema-version test literals
and one unguarded `AsyncMock.await_args` unpack — both pre-existing test
issues surfaced by this plan's own migration, unrelated to face-auth logic
itself), each independently code-reviewed. The focused face-authentication
scenario (161 tests) and the PC-1 PIN regression (45 tests, proving the PIN
path is unmodified) both pass. Full repository gates pass: `just lint`,
`just typecheck` (mypy 89 files clean, pyright 0 errors), `just test` (905
passed), `just audit`, and `just check` (16 hooks) are all green. Merged
(PR #73); real-camera acceptance closed 2026-09-01 as
[Plan 0030](../plans/completed/0030-real-camera-face-acceptance.md).

## Status transition protocol

After each executable plan:

1. Verify the merged code and tests rather than trusting the plan checklist.
2. Record exact commands, counts, commit SHA, and real-runtime evidence required
   by that plan.
3. Update [`current-state.md`](../architecture/current-state.md), this map, and
   the [operational board](../plans/README.md) in the same documentation change.
4. Move only the completed executable plan to `completed/`; never rewrite its
   evidence to describe later work.
5. Revalidate only the next plan's assumptions and interfaces.
6. Keep product, umbrella, and implementation status separate.

This protocol makes the repository—not chat history—the durable handoff for
humans and agents.
