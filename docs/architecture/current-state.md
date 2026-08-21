# Current cognitive implementation

> **Observed:** 2026-08-21
>
> **Implementation snapshot:** `main` at `5ba9f4f`.
> Plan 0022 (P0-C6 reliable streaming output) is **complete and verified**:
> all 4 tasks passed task-scoped review, a whole-plan review found no
> Critical issues, and real `just run-server`/`just run-robot` operator
> evidence on 2026-08-20 confirmed the headline invariant on live hardware —
> see [Plan 0022](../plans/completed/0022-p0-reliable-streaming-output.md#execution-evidence).
> Plans 0025 and 0026 (owner-authenticated memory MVP, PC-1) are merged; the
> classic flow was confirmed once informally with real hardware on 2026-08-21.
> Plans 0021, 0023, 0027, and 0028 remain unimplemented; combined P0 operator
> acceptance remains open.
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
> acceptance: [Plan 0013](../plans/open/0013-p0-voice-controller-bridge.md) now
> routes the classic voice path through the controller with an unknown public
> actor. Its automated evidence and human `just run-server` plus
> `just run-robot` acceptance remain required before this document can claim
> P0 operator acceptance. The subsequent runtime-policy audit confirmed the
> streaming, visual-dialogue, QA-WAV, and protected-wording gaps. They are
> bounded by [Plan
> 0014](../plans/open/0014-p0-runtime-policy-hardening-design.md). Plan 0022's code
> has since landed on this branch, but this documentation task did not rerun its
> automated gates. Typed intent resolution, grounded visual dialogue, explicit
> owner authentication, and the combined real operator run remain open.
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
the LLM, legacy memory, or consolidation. A generic visual request preserves
only its current ephemeral scene text in the legacy closure. This does not
establish face identity, authorization, or durable visual memory.

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
| One-use owner-authenticated classic turn (Plan 0026) | Implemented; classic flow confirmed once with real hardware | `POST /auth/owner/unlock` (loopback-only, rate-limited) issues a 60s one-use `LOCAL_UNLOCK` grant; `X-Iroko-Identity-Token` is accepted by classic `/chat` and `/transcribe`; the controller awaits actor/consent resolution only for protected branches; a valid grant authorizes exactly one `personal_protected_read` of `child_data` through the existing v4 tool. Absent/expired/replayed/malformed tokens deny without disclosure, without calling the v4 reader, and the safe audit trail never carries the PIN/token/names. The robot can opt into one startup PIN prompt (`ROBOT_OWNER_UNLOCK_PROMPT`) and clears the token only on `authentication_consumed=true`. Automated evidence uses the real DB with mocked STT/TTS; the full real-microphone/real-speaker classic loop was run once informally (2026-08-21) with the expected result — Plan 0028 owns the formal 3x recorded acceptance. Streaming parity is Plan 0027. |
| P0 runtime acceptance | Partial; combined operator acceptance pending | Enabled public routes enter the controller. Plan 0022 (streaming reliability) is complete and has real operator evidence (2026-08-20). Plans 0021/0023, the authenticated-owner proof, and the combined runbook evidence across all slices remain open. |
| Vision/VLM | Implemented/on demand with controller parity | One ephemeral frame, free-text scene description; `/vision/respond` enters the controller without face identity. |
| Face profiles | Implemented/sensitive/quarantined | SQLite-linked embeddings and recognition functions exist, but no consented runtime active-person adapter calls them. |
| Speaker recognition | Absent | STT and VAD exist; no speaker enrollment, voiceprint, verification model, or calibrated identity adapter exists. |
| Robot client | Implemented/body adapter | PC microphone/webcam/speaker workflow; not cognitive logic. |

## Deliberately absent or deferred

- a generic `ToolRegistry`; P0 uses closed typed tools and does not justify a
  registry or framework;
- public trusted identity, public consent input, name grounding, or any public
  route from `/chat` to protected v4 data. B2 is an internal test/application
  seam only: no protected value reaches a prompt, LLM, or public endpoint;
- speaker recognition, diarization, and identity fusion;
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

The P0 foundation evidence above does not prove an operator can exercise every
P0 capability via `just run-server` and `just run-robot`. R1 runtime proof is
defined in [Plan 0013](../plans/open/0013-p0-voice-controller-bridge.md); the
authenticated-owner acceptance gate is defined in
[Plan 0024](../plans/open/0024-owner-authenticated-memory-mvp-design.md). Its
executable sequence is
[0025](../plans/completed/0025-personal-owner-bootstrap-and-pin-setup.md) (merged) →
[0026](../plans/open/0026-one-use-owner-authenticated-classic-turn.md) (merged; classic
flow confirmed once informally with real hardware on 2026-08-21) →
[0027](../plans/open/0027-one-use-owner-streaming-parity.md) (next) →
[0028](../plans/open/0028-owner-authenticated-memory-runtime-acceptance.md), which
still owns the formal repeated real-runtime acceptance for both R1 (Plan 0013)
and 0026's classic flow.

These checks do not prove a real Ollama `/chat` request, camera, microphone,
biometric, LAN, or physical hardware behavior.
