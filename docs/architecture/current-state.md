# Current cognitive implementation

> **Observed:** 2026-08-21
>
> **Implementation snapshot:** `main` at `9b7662a`.
> Plan 0022 (P0-C6 reliable streaming output) is **complete and verified**:
> all 4 tasks passed task-scoped review, a whole-plan review found no
> Critical issues, and real `just run-server`/`just run-robot` operator
> evidence on 2026-08-20 confirmed the headline invariant on live hardware —
> see [Plan 0022](../plans/completed/0022-p0-reliable-streaming-output.md#execution-evidence).
> Plans 0025, 0026, 0027, and 0028 (owner-authenticated memory MVP, PC-1) are
> merged/executed; **PC-1 is accepted** — classic and streaming
> allowed/denied/replay/expiry scenarios each passed 3x with real hardware on
> 2026-08-21 (Plan 0028). Plan 0021 (P0-C5 typed intent resolution) is
> **complete and operator-confirmed**: 6/6 classic and 5/5 streaming
> acceptance cases passed on real hardware on 2026-08-21, all deterministic
> cases at `llm_ms=0` — see [Plan
> 0021](../plans/completed/0021-p0-typed-intent-resolution.md#execution-evidence).
> Plan 0023 (P0-C7 grounded visual dialogue) is **complete and
> operator-confirmed**: real hardware proved identity, enrollment,
> protected-household, grounded scene description, and VLM-down fallback,
> all 5 required cases PASS on 2026-08-21/2026-08-25 — see [Plan
> 0023](../plans/completed/0023-p0-grounded-visual-dialogue.md#execution-evidence).
> **P0 is fully operator-accepted (2026-08-25)**: the combined P0 runbook
> (R1+C1-S+C2-V+C3-Q, C5+C6+C7 together) passed, and Plan 0013's own R1
> debt closed the same day after fixing `WHISPER_INITIAL_PROMPT`/
> `WHISPER_HOTWORDS` (they still referenced the pre-rename "Omnibot" name,
> never "Iroko") — see [Plan
> 0013](../plans/completed/0013-p0-voice-controller-bridge.md#execution-evidence).
>
> **Plan 0029 (PC-2 — consented local face evidence)** merged 2026-08-25 (PR
> #73, squash, commit `4633685`): all 7 tasks complete, one commit per task
> plus one small test-maintenance follow-up commit, each independently
> code-reviewed. Full repository gates passed at merge time: `just lint`,
> `just typecheck` (mypy 89 files clean, pyright 0 errors), `just test` (905
> passed, 0 failed), `just audit`, and `just check` (16 hooks); the focused
> face-authentication scenario (161 tests) and the PC-1 PIN regression (45
> tests, proving the PIN path from Plans 0026/0027 is unmodified) both
> passed. **This plan has no liveness or anti-spoofing defense: a
> photograph of the owner held up to the camera authenticates under this
> slice.** The real mitigation is PC-4 (voice fusion), which is not yet
> built. A first real-hardware proof of concept ran 2026-08-27 via the new
> unified `just onboard` flow — one successful live enrollment and
> face-authenticated turn on Pipec's own webcam, not a calibrated study.
> Calibrated real-camera acceptance (threshold tuning, false-accept/
> false-reject rates, lighting, distance, glasses) remains open under a
> future real-camera acceptance plan (Plan 0030) — see [Plan
> 0029](../plans/open/0029-consented-local-face-evidence.md).
>
> **Verification boundary:** P0.3/P0.4 code and P0.5-A policy seams were
> inspected. P0.4 passed `just gate` (527 tests) before PR #40 merged it,
> adding an isolated v4 storage/migration foundation while retaining the v3
> runtime reader/writer. P0.5-A later passed its local 546-test gate and
> GitHub CI before PR #42 merged its policy/role/audit foundation. P0.5-B1
> later passed its local 555-test gate and GitHub CI before PR #45 merged its
> policy-gated, internal v4 reader. P0.5-B2 then passed `just lint`, `just
> typecheck`, `just test` (571 passed), `just audit`, `just check`, and five
> green GitHub CI checks before PR #48 merged its bounded internal family-tool
> seam. The P0 closure revalidation on merged `main` repeated the focused
> acceptance suite (20 passed), all five local gates, and `git diff --check`
> before this evidence update. This verifies the P0 foundation, not operator
> acceptance: [Plan 0013](../plans/completed/0013-p0-voice-controller-bridge.md)
> routes the classic voice path through the controller with an unknown public
> actor; its automated evidence and human `just run-server` plus
> `just run-robot` acceptance are now complete (2026-08-25), see above. The
> subsequent runtime-policy audit confirmed the streaming, visual-dialogue,
> QA-WAV, and protected-wording gaps. They were bounded by [Plan
> 0014](../plans/open/0014-p0-runtime-policy-hardening-design.md), whose every
> slice (C1–C7) and the combined real operator run are now complete.
> Prior P0.3/P0-S verification includes `just lint`, `just typecheck`, `just
> test` (514 passed), `just audit`, and `just check`; P0-S2 evidence includes GitHub CI and
> `just services` detecting configured local models. Camera, microphone, LAN,
> biometric enrollment, real Ollama chat, and hardware acceptance were not
> executed in this snapshot.
>
> **Latest repository test audit:** `just test` on 2026-08-20 completed with
> 635 passed and 6 failed. All six failures were in
> `tests/unit/test_robot_app.py`: the tracked tests assumed classic mode while
> the local `.env` supplied `ROBOT_STREAMING=true`. Re-running that unit file
> with `ROBOT_STREAMING=false` produced 20 passed. A subsequent full baseline
> with that same explicit override produced **641 passed in 29.81s**. This
> confirms the code baseline is green under the intended classic test posture
> while leaving an open test-isolation/configuration-drift defect: an unrelated
> local `.env` must not silently change unit-test mode.

## Accurate description

Iroko is a **typed, local-first conversational runtime with persistent legacy
memory and on-demand visual adapters**. It is more than `STT -> LLM -> TTS`,
but it is not yet a situated multimodal cognitive system.

```text
audio, text, or one requested frame
                |
                v
      channel adapter / request scope
                |
                v
unknown ActivePersonContext by default
                |
      unknown -> no persistent retrieval or consolidation
                |
                v
P0 controller adapters (`/chat`, classic `/transcribe`, streaming audio, and visual dialogue)
  |-- deterministic date/strict-ISO age
  |-- public protected household -> unauthorized
  |-- trusted internal child list/count -> policy-gated v4 tools
  `-- generic text -> legacy local text turn
                |
                v
response + local Piper + optional legacy consolidation
```

`/transcribe/stream` and `/vision/respond` now create a fresh typed event and
ask the controller to decide before legacy generation. Safe plans never reach
the LLM, legacy memory, or consolidation. Since Plan 0023 (P0-C7), the
controller's `decide()` can also return a `SceneDescriptionRequest`
capability instead of a closed plan; only `/vision/respond`'s scene branch
may fulfill it by reading a frame and calling the VLM, and that description
goes directly to Piper — never through the legacy text LLM. A generic
non-scene visual request delegates to legacy generation with no perception
at all. This does not establish face identity, authorization, or durable
visual memory.

The shared text path is `server/src/server/text_turn.py`. Public channels use
fresh interaction scopes. A trusted manual/session `ActivePersonContext` exists
as an internal seam, but public adapters do not yet supply one; that deliberate
gap prevents owner-by-default memory disclosure.

## Implemented capabilities

| Capability | State | Boundary |
|---|---|---|
| STT | Implemented | Faster Whisper, CPU/int8 path. |
| TTS | Implemented | Piper local synthesis. |
| LLM | Implemented/local only | Ollama is the only accepted runtime provider. |
| Text, audio, and streaming paths | Implemented/policy parity worktree | Classic and streaming audio enter the controller; generic stream output keeps its existing NDJSON/TTS path. P0-C6 (Plan 0022) closed the silent-success gap: `done` is architecturally guarded behind at least one prior audio chunk, confirmed by 641 tests and a 2026-08-20 real microphone run. |
| Working memory | Implemented/restricted | Unknown public turns use no persistent history. |
| Episodic/vector memory | Implemented/legacy | SQLite + sqlite-vec; top-k retrieval has no policy filter or threshold. |
| Entities and facts v3 | Implemented/legacy | String relation targets and universal fact supersession remain. |
| Relational memory v4 foundation | Implemented/isolated | Additive SQLite tables, typed predicate registry, entity-ID relations, cardinality/lifecycle repositories, a dry-run-first local legacy migration ledger, and a bounded raw target-ID relation filter. |
| Consolidation | Implemented/gated | LLM extraction plus deterministic normalization; requires manual identity. |
| Typed cognitive vocabulary | Implemented | Immutable evidence/event/context/knowledge contracts. |
| Active person context | Implemented/internal | Manual/session evidence only; persisted role can be carried as context but identity is not authorization. |
| P0.3 cognitive controller | Implemented/chat and classic-voice bridge | Fresh typed event; immutable response plan; no FastAPI, SQLite, or provider dependency in the core. Classic voice enters with a public unknown actor. |
| Deterministic calendar tools | Implemented/bounded | Current date and strict ISO birth-date age only; age is derived, never persisted. |
| Household authorization P0.5-A | Implemented/foundation | Pure fail-closed policy; additive role/audit SQLite records; explicit local owner bootstrap; `/chat` evaluates/audits protected branches as unknown before legacy delegation. |
| Household authorization P0.5-B1 reader | Implemented/internal | Closed-predicate v4 literal/relation reads evaluate and audit policy before storage; outputs are frozen `known`, `unknown`, or non-disclosing `unauthorized`. B2 trusted internal tools invoke it; no public HTTP, prompt, or LLM path does. |
| Household tools P0.5-B2 | Implemented/internal | Typed child list/count, preferences, birth date, and derived age tools authorize and audit before B1 reads; child relation/birth data require injected consent. |
| B2 controller dispatch | Implemented/trusted-only | Two self-child question patterns produce deterministic response plans through injected actor/consent seams. Public `/chat` cannot provide either and never reaches the v4 reader. |
| Personal owner/children/PIN setup (Plan 0025) | Implemented/local-only | `just setup-personal` bootstraps Pipec as sole owner, confirms Máximo/Dominga as active v4 `child_of` relations, and stores one scrypt-hashed PIN credential (`owner_pin_credentials`, migration 006). Idempotent rerun and PIN rotation are covered. |
| One-use owner-authenticated classic turn (Plan 0026) | Implemented; real-hardware acceptance closed | `POST /auth/owner/unlock` (loopback-only, rate-limited) issues a 60s one-use `LOCAL_UNLOCK` grant; `X-Iroko-Identity-Token` is accepted by classic `/chat` and `/transcribe`; the controller awaits actor/consent resolution only for protected branches; a valid grant authorizes exactly one `personal_protected_read` of `child_data` through the existing v4 tool. Absent/expired/replayed/malformed tokens deny without disclosure, without calling the v4 reader, and the safe audit trail never carries the PIN/token/names. The robot can opt into one startup PIN prompt (`ROBOT_OWNER_UNLOCK_PROMPT`) and clears the token only on `authentication_consumed=true`. Plan 0028 (2026-08-21) proved the classic flow 3x on real microphone/speaker hardware, including expiry and generic non-consumption, cross-checked against the `authorization_audit_events` table directly. |
| One-use owner streaming parity (Plan 0027) | Implemented; real-hardware acceptance closed | `POST /transcribe/stream` accepts the same optional `X-Iroko-Identity-Token` and composes one `OwnerRequestResolver` per request before `decide(event)`, reusing Plan 0026's `OwnerUnlockService` unchanged. The terminal NDJSON `done` event gains an additive `authentication_consumed` boolean (default `false`); older robots parsing it without the field default safely to `false`. Generic/legacy streaming never resolves an actor and always reports `false`. The robot's `transcribe_stream()` sends the header when a token is held and clears `ctx.identity_token` only on a `done` with `authentication_consumed=true`; an EOF before `done` leaves it untouched (replay denied server-side). `ROBOT_OWNER_UNLOCK_PROMPT` now works with `ROBOT_STREAMING` — the prior startup guard pointing at this plan was removed. Plan 0028 (2026-08-21) proved the streaming flow 3x on real hardware; measured total latency was consistently lower than classic mode for the same answer (~1.9s vs ~2.0s) since audio starts on the first NDJSON chunk. |
| Owner-authenticated memory runtime acceptance (Plan 0028) | Executed 2026-08-21 — **PASS** for the PC-1 slice | Ran the full classic and streaming allowed/denied/replay/expiry/generic-non-consumption matrix 3x each on real hardware (`ntbk-pipec-2`), plus a direct SQLite inspection of `authorization_audit_events` (36 rows) confirming exact `execute_household_tool → read_household_data` ordering on every disclosure and no PIN/token/name leakage anywhere outside the `entities` table. Also ran Plan 0013's R1-01/R1-02/R1-03 cases: R1-01 and R1-02 passed; R1-03 failed after 5 attempts — Whisper "small" could not reliably transcribe the proper noun "Iroko" — so Plan 0013 stays open on that independently tracked finding, per this plan's own rule that R1 does not gate the PC-1 verdict. Surfaced two other findings, neither blocking: a repeatable first-utterance-after-restart STT mis-transcription pattern, and a garbled `protected_household`-pattern match that can consume a fresh grant without disclosing or denying cleanly (no leak observed). Full untracked evidence: `project-history/acceptance/2026-08-21-owner-authenticated-memory.md`. |
| Typed intent resolution (Plan 0021 / P0-C5) | Executed 2026-08-21 — operator-confirmed | New pure `cognition/intent_resolution.py`: a closed, deterministic Spanish rule set (no LLM/VLM/embedding/database) with an `IntentResolution(need, match, rule_id)` contract, injected into `CognitiveController` as `intent_resolver` (default `resolve_information_need`), replacing the former inline `_classify_information_need`. `rule_id` is privacy-safe static metadata, never the utterance or a name. Precedence: own-child list/count → protected household/birth → supervised ambiguous STT aliases → current-date STT alias → current date → explicit age → relationship/profile → generic. Real hardware proved 6/6 classic and 5/5 streaming acceptance cases (`ntbk-pipec-2`), all deterministic cases at `llm_ms=0`, audibly confirmed. C6/C7 untouched (confirmed by `git diff --stat`). |
| P0 runtime acceptance | **Complete (2026-08-25)** | Enabled public routes enter the controller. Plans 0022 (streaming reliability), 0021 (typed intent, C5), 0023 (grounded visual dialogue, C7), and 0013 (voice-controller bridge, R1) are all complete with real operator evidence. The authenticated-owner proof (PC-1) is complete via Plan 0028. The combined P0-C runbook (R1+C1-S+C2-V+C3-Q) passed on commit `a07b731` — see [`p0-runtime-acceptance.md`](../runbooks/p0-runtime-acceptance.md). |
| Vision/VLM (Plan 0023 / P0-C7) | Executed 2026-08-21/2026-08-25 — operator-confirmed | Extracted C5's resolver with `SCENE_DESCRIPTION`, `ACTIVE_IDENTITY`, and `BIOMETRIC_ENROLLMENT` needs and one `SceneDescriptionRequest` capability type. Only `/vision/respond`'s scene branch reads a frame or calls the VLM; the grounded description goes directly to Piper (`ResponseSource.CURRENT_PERCEPTION`), never through the text LLM. Identity/enrollment speak exact fixed copy without ever touching the camera, even with vision disabled. `vision/triggers.py`'s parallel intent authority was deleted. Real hardware confirmed all 5 required cases: identity denial, grounded scene description with no second LLM, VLM-down exact fallback, enrollment rejection, and household denial. |
| Consented local face evidence (Plan 0029 / PC-2) | Implemented on branch `feat/consented-local-face-evidence`; pending review/merge and real-camera acceptance | Migration 007 (`face_consent_grants`) plus `memory/biometric_consent.py` grant/revoke/read consent, with revocation performing a real purge of `face_profiles` and `vec_faces` rows, not a soft flag. `IdentityEvidenceSource.FACE` is now trusted as identified (`cognition/identity.py`); `VOICE`/`CONTEXT` remain unresolved (PC-3/PC-4). `cognition/face_authentication.py` adds a pure verdict function (0 faces -> unknown, 2+ faces -> ambiguous and terminal — never falls through to the PIN, 1 face variations -> unknown/identified by match+consent+role), a lazy single-inference-per-turn `FaceRequestResolver`, and `compose_face_then_pin_resolver()`, which tries face first and falls through to the existing PIN resolver (Plan 0026) only on a non-ambiguous unresolved face result. A stricter, separate `settings.face_authentication_match_threshold` (default `0.25`) applies on top of the existing generic `settings.face_match_threshold` (`0.4`). `POST /auth/owner/face/enroll` and `/revoke` (loopback-only, requiring a fresh PIN-consumed token) always enroll the token's own owner, never a request-supplied name; the pre-existing quarantined public `POST /vision/enroll` is untouched and still returns 503. Classic and streaming `/transcribe` accept an optional multipart `frame` field gated by `settings.face_authentication_enabled` (default `False` — with it off, the frame is never even read) and report which evidence source authenticated the turn via an additive `identity_source: "face" \| "local_unlock" \| null` field, never a name or protected value. The robot opts in via `settings.robot_face_auth_enabled` (default `False`), attaching a captured frame to every turn when enabled (a camera failure degrades silently to no frame). **No liveness/anti-spoofing defense exists**: a photograph of the owner held up to the camera authenticates under this slice; the real mitigation is PC-4 (voice fusion), not yet built. Real-camera calibration and acceptance are open under a future real-camera acceptance plan (Plan 0030). |
| Face profiles | Implemented/sensitive/consent-gated | SQLite-linked embeddings and recognition functions exist; Plan 0029 adds a consented, in-request runtime adapter behind `FACE_AUTHENTICATION_ENABLED` (default off) — see the row above. |
| Speaker recognition | Absent | STT and VAD exist; no speaker enrollment, voiceprint, verification model, or calibrated identity adapter exists. |
| Robot client | Implemented/body adapter | PC microphone/webcam/speaker workflow; not cognitive logic. |

## Deliberately absent or deferred

- a generic `ToolRegistry`; P0 uses closed typed tools and does not justify a
  registry or framework;
- public trusted identity, public consent input, name grounding, or any public
  route from `/chat` to protected v4 data. B2 is an internal test/application
  seam only: no protected value reaches a prompt, LLM, or public endpoint;
- speaker recognition, diarization, and identity fusion;
- liveness/anti-spoofing defense for face evidence (Plan 0029): a photograph
  of the owner currently authenticates under that slice; the accepted
  mitigation is PC-4 voice fusion, not yet built; real-camera
  calibration/acceptance is separately open under a future real-camera
  acceptance plan (Plan 0030);
- typed `SceneObservation`, `WorldState`, tracking, scene graph, and spatial
  memory;
- cognitive memory lifecycle, confirmation, reflection, and forgetting;
- cloud escalation gateway, ROS2, motors, and physical actions.

The next product target after P0-C is the personal Iroko-and-Pipec companion
defined in [ADR 0006](../adr/0006-personal-and-family-companion-profiles.md).
General UI and family onboarding are deliberately later work.

## Active hardening status

The P0-S audit is authoritative for immediate pre-controller work:

- Plan 0002a completed the direct-cloud-provider quarantine.
- Plan 0002b **completed** public biometric-enrollment quarantine: direct
  enrollment returns a fixed 503 before any upload read or biometric write, and
  conversational enrollment phrases provide fixed guidance without enrollment.
  Existing biometric data is preserved; P0.5 owns the future policy.
- Plan 0002c **completed** desktop hardening and guidance alignment: Python and
  sample configuration bind loopback by default, LAN exposure requires an
  explicit untracked override, stale `VOICE_CONVERSATION_ID` guidance is gone,
  and diagnostics no longer promise public memory recall, enrollment, or face
  identity. The face threshold values remain intentionally unchanged pending a
  reproducible calibration.
- P0-S and Plan 0003 are **Complete**. P0.3 pilots a bounded `/chat`
  controller with immutable response planning plus deterministic current-date
  and strict ISO-birth-date age tools. It does not alter P0.4/P0.5 boundaries.
- Plan 0004's relational-memory decision and Plan 0005's P0.4 foundation are
  **Complete**. PR #40 merged as `3b01b58` after the final 527-test quality
  gate: migration 4 is additive, v4 repositories and a dry-run-first local
  migration command exist, and the legacy runtime reader/writer remains
  unchanged. Plan 0007 P0.5-A passed its local 546-test gate on
  `feat/p05-household-authorization`: migration 5 adds local roles/audit, and
  protected `/chat` requests are denied and audited before legacy generation.
  GitHub CI passed and PR #42 merged as `960f160`. Authorization still owns
  any v4 runtime retrieval or writes.
- Plan 0009 P0.5-B1 is **Complete**. PR #45 merged as `a7550d0` after local
  `just lint`, `just typecheck`, `just test` (555 passed in 54.17s), `just
  audit`, and `just check`, plus green GitHub title, quality/security, test,
  Python analysis, and CodeQL checks. It adds an internal policy-gated v4
  reader and inverse target-ID filter only. B2 tools/controller wiring,
  public trusted identity, consent persistence, and P1 onboarding remain
  deliberately unimplemented.
- Plan 0010 P0.5-B2 is **Complete**. PR #48 merged as `0d16969` after local
  `just lint`, `just typecheck`, `just test` (571 passed), `just audit`, and
  `just check`, plus green GitHub title, quality/security, test, Python
  analysis, and CodeQL checks. It adds a closed internal tool seam only;
  public identity/consent, broader family queries, prompts/LLM retrieval, and
  P1 remain deliberately unimplemented.

See [P0-S hardening audit](../history/audits/p0-s-hardening-audit.md) for evidence and
[plans](../plans/README.md) for execution status.

## Latest verification evidence

- P0.3 implementation: `just lint`, `just typecheck`, final `just test` (514
  passed in 36.25s), `just audit`, and `just check` passed. Focused response-plan,
  calendar, controller, and `/chat` tests were run as a RED/GREEN sequence.
- P0-S2 historical evidence: `just lint`, `just typecheck`, `just test` (500
  passed), and `just audit` passed. `just services` reported the configured
  chat, embedding, consolidation, and enabled VLM models available through the
  local Ollama daemon.
- Earlier P0-S evidence remains historical: `just test` passed 496 tests before
  PR #32, and a local `text -> LLM -> Piper` pipeline completed through Piper.
- P0.4 implementation: observed RED tests for the missing registry,
  repository, and migration modules; then focused GREEN coverage for registry,
  schema, repository, migration, and legacy compatibility. Final `just gate`
  passed with 527 tests, Ruff, formatting, mypy, Pyright, security checks, and
  `pip-audit`. The local CLI help confirms dry-run is the default and `--apply`
  is explicit. PR #40 merged after its GitHub CI checks. No real household
  database migration, hardware, camera, microphone, or real Ollama chat request
  was performed in this slice.

- P0 closure revalidation on merged `main` (`0d16969`): the policy-gated
  household acceptance, reader, authorization-runtime, and chat suites passed
  20 tests in 0.91s. `just lint` passed with 211 files unchanged; `just
  typecheck` reported no issues in 75 sources and Pyright reported zero errors;
  `just test` passed 571 tests in 42.64s; `just audit` found no known
  vulnerabilities; and `just check` passed every configured pre-commit hook.

- Plan 0022 (P0-C6) closure on `1927912`: `just lint`, `just typecheck` (mypy
  81 files + pyright, 0 errors), `just test` (641 passed), `just audit`, and
  `just check` (17 hooks) all passed. A whole-plan review over the full
  8-commit range found no Critical issues and traced the "every `done` has
  prior audio" invariant true across all 6 named invalid-output cases plus
  mid-stream provider failure; 3 Important findings were fixed in one
  combined fix wave with a scoped re-review, and one residual TTS-double-failure
  edge case was explicitly parked (see the plan's Execution Evidence). Real
  `just run-server`/`just run-robot` acceptance on 2026-08-20 with a
  disposable local DB confirmed zero silent successes across 4 live turns,
  including one live reproduction of the 2026-08-17 hybrid-output failure
  mode ending in an audible fallback instead of silence, and one correct
  non-disclosing family denial with `llm_ms=0`.

- Plan 0029 (PC-2) closure, merged 2026-08-25 (PR #73, squash, commit
  `4633685`): the focused face-authentication scenario (161 tests:
  `test_biometric_consent_schema.py`, `test_active_person_identity.py`,
  `test_face_authentication.py`, `test_owner_face_enrollment.py`,
  `test_face_authenticated_turn.py`, `test_server_client.py`,
  `test_robot_app.py`, `test_robot_app_streaming.py`) and the PC-1 PIN
  regression (45 tests: `test_owner_authenticated_turn.py`,
  `test_owner_authenticated_stream.py`, `test_vision_enroll_service.py`,
  `test_cognitive_controller.py`) both passed with no failures — the PIN
  path is unmodified. Full repository gates: `just lint` (clean), `just
  typecheck` (mypy 89 files clean, pyright 0 errors), `just test` (905
  passed, 0 failed), `just audit` (clean), `just check` (16/16 hooks
  passed), and `git diff --check` (clean) all passed on 2026-08-25. Every
  named threat case (unknown face, ambiguous/2+ faces terminal denial,
  revoked consent, non-owner role, expired evidence, no frame supplied,
  flag-disabled parity with `main`, no face detection on non-protected turns,
  enrollment without a fresh token, enrollment non-loopback, and no
  secret/embedding/frame in any log or audit row) has a real, specific
  covering test, sampled and confirmed passing. **This plan has no
  liveness/anti-spoofing defense**: a photograph of the owner authenticates
  under this slice; the accepted mitigation is PC-4 (voice fusion), not yet
  built. A first real-hardware proof of concept ran 2026-08-27 (`just
  onboard` enrollment + a `just run-robot` face-authenticated turn,
  correctly identified, no PIN) — one successful live run, not a calibrated
  study. Calibrated real camera/hardware acceptance (threshold tuning,
  false-accept/false-reject rates, lighting, distance, glasses) is that
  future real-camera acceptance plan's (Plan 0030) job.

R1 runtime proof is complete — see
[Plan 0013](../plans/completed/0013-p0-voice-controller-bridge.md); the
authenticated-owner acceptance gate is defined in
[Plan 0024](../plans/open/0024-owner-authenticated-memory-mvp-design.md). Its
executable sequence is
[0025](../plans/completed/0025-personal-owner-bootstrap-and-pin-setup.md) (merged) →
[0026](../plans/completed/0026-one-use-owner-authenticated-classic-turn.md) (merged) →
[0027](../plans/completed/0027-one-use-owner-streaming-parity.md) (merged) →
[0028](../plans/completed/0028-owner-authenticated-memory-runtime-acceptance.md)
(executed 2026-08-21, **PASS**), which completed the formal repeated
real-runtime acceptance for 0026/0027's classic and streaming flows. It also
executed R1 (Plan 0013): R1-01/R1-02 passed, R1-03 failed on STT accuracy —
Plan 0013 remains open on that one finding, independently of the now-closed
PC-1 (0025-0028) verdict.

These checks do not prove a real Ollama `/chat` request, camera, microphone,
biometric, LAN, or physical hardware behavior.
