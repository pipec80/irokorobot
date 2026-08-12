# P0-S hardening and consistency design

## Status

**Approved design — documentation only.** This document records the bounded
hardening work that must complete before Plan 0003 is promoted to `Ready`. It
does not authorize runtime changes by itself.

## Objective

Close confirmed security and configuration drift without introducing household
authorization, a public administration API, a new dependency, or any P0.3
controller behavior.

## Current evidence

The following was revalidated on `main` at `a936cf8`:

| Finding | Evidence | Decision |
|---|---|---|
| Public biometric enrollment | `routers/vision.py` exposes `/vision/enroll`; `vision/faces.py:enroll_person()` upserts a person and persists a face embedding. | Quarantine public enrollment before P0.5. |
| Conversational biometric enrollment | `/vision/respond` recognizes an enrollment phrase and calls `enroll_from_frame()`. | Quarantine this second public path in the same slice. |
| Desktop network exposure | `Settings.server_host` and `.env.example` default to `0.0.0.0`. | Make loopback the default; LAN exposure becomes explicit configuration. |
| Obsolete voice scope configuration | `.env.example` still declares `VOICE_CONVERSATION_ID=voice-primary`; P0.2 creates request-local interaction scopes. | Remove the obsolete variable and explain the current scope boundary. |
| Model/service drift | `services.ps1` checks a hard-coded model list that differs from active example configuration. | Derive or clearly align the checked local model requirements. |
| Documentation drift | `current-state.md` predates P0.2 and Plan 0002a. | Replace its snapshot with a commit-bounded current description. |
| Owner-centric language | Character and prompt text retain owner/permanent-memory wording. | Neutralize only the conflicting operational language; preserve Iroko's fiction. |

The former direct-cloud-provider finding is resolved by Plan 0002a: the
runtime accepts only Ollama. P0-S must not re-open a cloud provider switch or
implement a `CognitiveEscalationGateway`.

## Design

P0-S is deliberately split into two independently reviewable plans.

### P0-S1 — Biometric enrollment quarantine

The application must not create or attach a face profile through an unauthenticated
HTTP request or an unresolved conversational visual turn. This covers both
`POST /vision/enroll` and the enrollment phrase route in `/vision/respond`.

The minimal safe behavior is to return a clear, non-sensitive unavailable
outcome that explains that face enrollment is temporarily disabled pending a
local administrative and consent policy. Existing profile matching/storage
schemas and non-enrollment scene description remain outside this slice.

This is not P0.5. It does not define roles, login, consent records, an owner
bootstrap flow, a LAN admin API, or a new enrollment client. It prevents a
known poisoning path until those prerequisites exist.

### P0-S2 — Desktop exposure and documentation/configuration consistency

The normal developer default binds only to `127.0.0.1`. A user who needs a LAN
robot or homelab client explicitly sets `SERVER_HOST=0.0.0.0`; no automatic
network discovery or authentication system is added.

This plan also aligns active configuration, scripts, current-state
documentation, and demonstrations with actual P0.2/P0002a behavior. It may
correct operational language that falsely implies permanent retention or that
the active person is always an owner. It does not rewrite Iroko's character or
rename packages.

## Invariants

- Preserve the WAV audio contract and every existing public response field.
- Preserve the server/robot boundary and SQLite data compatibility.
- Do not delete existing face profiles, entities, facts, or memories.
- Do not add a dependency, cloud route, model download, authentication system,
  authorization policy, controller, tool registry, migration, ROS2, or action
  capability.
- Keep `VISION_ENABLED` as an availability setting, not an authorization
  substitute.
- Record exact runtime and test evidence; an unexecuted test is not a pass.

## Documentation architecture

The tracked architecture set remains the source of truth:

- `docs/architecture/cognitive-architecture.md` retains permanent principles;
- `docs/architecture/current-state.md` records a dated, commit-bounded runtime
  snapshot;
- `docs/architecture/p0-s-hardening-audit.md` records the current evidence and
  disposition of every P0-S finding;
- `docs/roadmap/cognitive-roadmap.md` records order and dependencies;
- `docs/plans/` contains one canonical executable plan per bounded PR.

No giant master prompt is added to runtime or duplicated as a second canonical
architecture document. A short operational prompt may point to these files.

## Planned sequence

1. Write and execute P0-S1 only; merge it after its independent quality gates.
2. Revalidate `main`, then write and execute P0-S2 only; merge it after its
   independent quality gates.
3. Revalidate `main` and promote Plan 0003 only if both P0-S plans are
   complete and no new boundary conflict exists.

## Promotion and stop conditions

Each P0-S plan must contain exact file scope, RED/GREEN tests, rollback,
documentation updates, and final `just lint`, `just typecheck`, `just test`,
and `just audit` gates.

Stop and request a new decision if a minimal fix requires a public admin API,
login, household authorization, destructive biometric cleanup, schema
migration, cloud processing, an audio/API contract change, or a new global ID
strategy.
