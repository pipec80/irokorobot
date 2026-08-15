# Current cognitive implementation

> **Observed:** 2026-08-14
>
> **Implementation snapshot:** `docs/personal-family-profiles` worktree after
> P0-C1 through P0-C4. This snapshot is not merged and has not completed
> operator acceptance.
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
> acceptance: [Plan 0013](../plans/0013-p0-voice-controller-bridge.md) now
> routes the classic voice path through the controller with an unknown public
> actor. Its automated evidence and human `just run-server` plus
> `just run-robot` acceptance remain required before this document can claim
> P0 operator acceptance. The subsequent runtime-policy audit confirmed the
> streaming, visual-dialogue, QA-WAV, and protected-wording gaps. They are
> implemented in the current feature worktree under
> [Plan 0014](../plans/0014-p0-runtime-policy-hardening-design.md), but still
> require a combined real operator run.
> Trusted owner runtime access remains an R2 task.
> Prior P0.3/P0-S verification includes `just lint`, `just typecheck`, `just
> test` (514 passed), `just audit`, and `just check`; P0-S2 evidence includes GitHub CI and
> `just services` detecting configured local models. Camera, microphone, LAN,
> biometric enrollment, real Ollama chat, and hardware acceptance were not
> executed in this snapshot.

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
| Text, audio, and streaming paths | Implemented/policy parity worktree | Classic and streaming audio enter the controller; generic stream output keeps its existing NDJSON/TTS path. |
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
| P0 runtime acceptance | Automated P0-C complete; operator acceptance pending | All enabled public audio/stream/visual dialogue routes now enter the controller. The real runbook evidence remains open. R2 trusted-session acceptance remains unimplemented. |
| Vision/VLM | Implemented/on demand with controller parity | One ephemeral frame, free-text scene description; `/vision/respond` enters the controller without face identity. |
| Face profiles | Implemented/sensitive | SQLite-linked embeddings; not an active-person adapter. |
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

See [P0-S hardening audit](p0-s-hardening-audit.md) for evidence and
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

The P0 foundation evidence above does not prove an operator can exercise every
P0 capability via `just run-server` and `just run-robot`. R1 runtime proof is
defined in [Plan 0013](../plans/0013-p0-voice-controller-bridge.md); the
trusted-session R2 acceptance gate remains open in
[Plan 0012](../plans/0012-p0-runtime-acceptance-design.md). P1 remains
unstarted.

These checks do not prove a real Ollama `/chat` request, camera, microphone,
biometric, LAN, or physical hardware behavior.
