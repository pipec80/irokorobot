# Implementation plans

> **Status:** Canonical plan router. The roadmap defines order; only an
> explicitly authorized plan under `open/` may be executed.

Start with the [architecture index](../architecture/README.md) and
[current state](../architecture/current-state.md). For the personal-companion
program, the [delivery map](../roadmap/personal-companion-delivery-map.md)
identifies reusable code, verified gaps, and plan ownership. A plan being
present or marked ready is not user authorization.

## Operational board

There is exactly one executable work item in `NOW`. Do not start a blocked,
deferred, umbrella, or product-design plan because it also lives under
`open/`.

| Lane | Plans | Meaning |
|---|---|---|
| **NOW** | [0030 — real-camera face acceptance](open/0030-real-camera-face-acceptance.md) | Written 2026-08-27, satisfying this board's own prior condition ("no further plan is authorized until a real-camera acceptance plan is written and approved"). Measures Pipec's genuine face distance against impostor distances (household members and unrelated photos) with the real webcam, chooses `face_authentication_match_threshold` from that data instead of Plan 0029's unvalidated guess, and confirms it live through `just run-server` + `just run-robot`. Not yet executed. Closing it closes only PC-2's real-camera acceptance — P1.2 still needs speaker evidence (PC-3) and fusion (PC-4). |
| **REFERENCE ONLY** | [0015](open/0015-personal-companion-design.md) | Umbrella/design document; never execute it as an independent implementation batch |

## Queue rules

1. Keep work in progress at one executable plan.
2. Review the `NOW` plan before modifying production code.
3. Move a plan to `completed/` only after its own code, automated gates,
   review, and required real-runtime evidence are recorded.
4. After closing a plan, re-audit only the next plan's assumptions against the
   merged code; do not reopen or rebuild completed slices.
5. A blocker moves the item out of `NOW`; it does not authorize skipping to a
   later dependent plan.
6. Batch compatible physical acceptance cases into one operator session, but
   record each plan's evidence separately.

## Dependency order

| Order | Plan | State | Next gate |
|---:|---|---|---|
| 1 | [0025 — minimal owner/children/PIN setup](completed/0025-personal-owner-bootstrap-and-pin-setup.md) | Merged (PR #56) | Closed |
| 2 | [0026 — one-use classic turn](completed/0026-one-use-owner-authenticated-classic-turn.md) | Merged (PR #57) | Closed |
| 3 | [0027 — streaming parity](completed/0027-one-use-owner-streaming-parity.md) | Merged (PR #64) | Closed |
| 4 | [0028 — runtime acceptance](completed/0028-owner-authenticated-memory-runtime-acceptance.md) | Executed 2026-08-21, PASS | Closed (0013's R1 debt tracked independently below) |
| 5 | [0021 — typed intent](completed/0021-p0-typed-intent-resolution.md) | Implemented and operator-confirmed 2026-08-21 | Closed |
| 6 | [0023 — grounded visual dialogue](completed/0023-p0-grounded-visual-dialogue.md) | Implemented and operator-confirmed 2026-08-25 | Closed |
| 7 | [0013 — voice controller bridge](completed/0013-p0-voice-controller-bridge.md) | R1-03 root cause fixed and confirmed 2026-08-25 | Closed |
| 8 | [0029 — consented local face evidence](open/0029-consented-local-face-evidence.md) | Merged (PR #73, 2026-08-25) | Closed for its own code/tests/review scope. Stays in `open/` per Queue rule 3 — its own real-camera acceptance is owned by Plan 0030, below |
| 9 | [0030 — real-camera face acceptance](open/0030-real-camera-face-acceptance.md) | Written 2026-08-27, not yet executed | The current `NOW` item. Closes PC-2's real-camera acceptance only — P1.2's exit gate still needs speaker evidence (PC-3) and fusion (PC-4) |

Supporting active designs and open acceptance work are listed in the
[open-plan index](open/README.md). Closed execution evidence is isolated in
[completed plans](completed/README.md) and cannot authorize new changes.

## Plan contract

Every executable plan must name its source of truth, required reading,
permitted files, non-goals, RED/GREEN tests, verification commands, rollback
boundary, and exact completion criteria. It may not depend on chat history,
ignored local research, or a completed/historical plan for a current decision.
Promote any still-required decision into an ADR or canonical architecture
document first.
