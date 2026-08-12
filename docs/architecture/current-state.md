# Current cognitive implementation

> **Observed:** 2026-08-12
>
> **Implementation snapshot:** `5958ee6` (`feat/p04-relational-memory-v4`,
> P0.4 locally verified; pending PR/CI/merge)
>
> **Verification boundary:** P0.3 code, configuration, and local tests were
> inspected. P0.4 passed `just gate` (527 tests), adding an isolated v4
> storage/migration foundation while retaining the v3 runtime reader/writer.
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
P0.3 `/chat` controller
  |-- deterministic date/strict-ISO age
  |-- protected household -> unauthorized
  `-- generic text -> legacy local text turn
                |
                v
response + local Piper + optional legacy consolidation
```

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
| Text, audio, and streaming paths | Implemented | Existing public contracts are preserved. |
| Working memory | Implemented/restricted | Unknown public turns use no persistent history. |
| Episodic/vector memory | Implemented/legacy | SQLite + sqlite-vec; top-k retrieval has no policy filter or threshold. |
| Entities and facts v3 | Implemented/legacy | String relation targets and universal fact supersession remain. |
| Relational memory v4 foundation | Implemented/isolated | Additive SQLite tables, typed predicate registry, entity-ID relations, cardinality/lifecycle repositories, and a dry-run-first local legacy migration ledger. No v4 data reaches runtime prompts before P0.5. |
| Consolidation | Implemented/gated | LLM extraction plus deterministic normalization; requires manual identity. |
| Typed cognitive vocabulary | Implemented | Immutable evidence/event/context/knowledge contracts. |
| Active person context | Implemented/internal | Manual/session evidence only; identity is not authorization. |
| P0.3 cognitive controller | Implemented/chat pilot | Fresh typed event; immutable response plan; no FastAPI, SQLite, or provider dependency in the core. |
| Deterministic calendar tools | Implemented/bounded | Current date and strict ISO birth-date age only; age is derived, never persisted. |
| Vision/VLM | Implemented/on demand | One ephemeral frame, free-text scene description. |
| Face profiles | Implemented/sensitive | SQLite-linked embeddings; not an active-person adapter. |
| Robot client | Implemented/body adapter | PC microphone/webcam/speaker workflow; not cognitive logic. |

## Deliberately absent or deferred

- `ToolRegistry` and deterministic family/profile/relationship tools; P0.3 has
  two closed calendar helpers and deliberately does not justify a registry;
- household authorization, trusted owner bootstrap, and the policy-gated v4
  runtime reader/writer cutover;
- speaker recognition, diarization, and identity fusion;
- typed `SceneObservation`, `WorldState`, tracking, scene graph, and spatial
  memory;
- cognitive memory lifecycle, confirmation, reflection, and forgetting;
- cloud escalation gateway, ROS2, motors, and physical actions.

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
- Plan 0004's relational-memory decision is **Complete**. Plan 0005's P0.4
  foundation is **implemented and locally verified**: migration 4 is additive,
  v4 repositories and a dry-run-first local migration command exist, and the
  legacy runtime reader/writer remains unchanged. GitHub CI and merge remain
  pending; P0.5 authorization still owns any v4 runtime retrieval or writes.

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
- P0.4 local implementation: observed RED tests for the missing registry,
  repository, and migration modules; then focused GREEN coverage for registry,
  schema, repository, migration, and legacy compatibility. Final `just gate`
  passed with 527 tests, Ruff, formatting, mypy, Pyright, security checks, and
  `pip-audit`. The local CLI help confirms dry-run is the default and `--apply`
  is explicit. No real household database migration, hardware, camera,
  microphone, or real Ollama chat request was performed in this slice.

These checks do not prove a real Ollama `/chat` request, camera, microphone,
biometric, LAN, or physical hardware behavior.
