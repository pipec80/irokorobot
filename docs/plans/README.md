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
| **NOW** | [0028](open/0028-owner-authenticated-memory-runtime-acceptance.md) | The real north-star physical acceptance — starts from merged `main` (Plans 0025, 0026, and 0027 closed) |
| **AFTER PC-1** | [0021](open/0021-p0-typed-intent-resolution.md) → [0023](open/0023-p0-grounded-visual-dialogue.md) | Remaining P0-C intent and visual grounding |
| **ACCEPTANCE DEBT** | [0013](open/0013-p0-voice-controller-bridge.md), [0026](open/0026-one-use-owner-authenticated-classic-turn.md), [0027](open/0027-one-use-owner-streaming-parity.md) | Code merged (PR #51, PR #57, and 0027's PR); Plan 0028 explicitly executes the repeated real microphone/speaker acceptance and records the independent verdict for all three. 0026's classic flow was informally confirmed once with real hardware on 2026-08-21 (see its Evidence section); 0027's streaming parity has automated evidence only, no real-microphone run yet — neither is a substitute for 0028's required 3x recorded runs. |
| **REFERENCE ONLY** | [0014](open/0014-p0-runtime-policy-hardening-design.md), [0015](open/0015-personal-companion-design.md), [0020](open/0020-p0-operator-qa-remediation-design.md), [0024](open/0024-owner-authenticated-memory-mvp-design.md) | Umbrella/design documents; never execute them as independent implementation batches |

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
| 2 | [0026 — one-use classic turn](open/0026-one-use-owner-authenticated-classic-turn.md) | Merged (PR #57); acceptance debt to Plan 0028 | Closed |
| 3 | [0027 — streaming parity](open/0027-one-use-owner-streaming-parity.md) | Merged; acceptance debt to Plan 0028 | Closed |
| 4 | [0028 — runtime acceptance](open/0028-owner-authenticated-memory-runtime-acceptance.md) | Executable now | Real microphone/speaker acceptance for 0013, 0026, 0027 |
| 5 | [0021 — typed intent](open/0021-p0-typed-intent-resolution.md) | Deferred | PC-1 accepted |
| 6 | [0023 — grounded visual dialogue](open/0023-p0-grounded-visual-dialogue.md) | Deferred | 0021 complete |

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
