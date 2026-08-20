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
| **NOW** | [0025](open/0025-personal-owner-bootstrap-and-pin-setup.md) | Minimal owner/children/PIN design and test baseline approved; checkpoint documentation before implementation |
| **NEXT** | [0026](open/0026-one-use-owner-authenticated-classic-turn.md) | Starts only after 0025 is merged and revalidated |
| **THEN** | [0027](open/0027-one-use-owner-streaming-parity.md) → [0028](open/0028-owner-authenticated-memory-runtime-acceptance.md) | Streaming parity, then the real north-star acceptance |
| **AFTER PC-1** | [0021](open/0021-p0-typed-intent-resolution.md) → [0023](open/0023-p0-grounded-visual-dialogue.md) | Remaining P0-C intent and visual grounding |
| **ACCEPTANCE DEBT** | [0013](open/0013-p0-voice-controller-bridge.md) | Code is merged; Plan 0028 explicitly executes R1-01–R1-03 and records their independent verdict |
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
| 1 | [0025 — minimal owner/children/PIN setup](open/0025-personal-owner-bootstrap-and-pin-setup.md) | Code/test preflight green | Recoverable documentation checkpoint, then TDD execution |
| 2 | [0026 — one-use classic turn](open/0026-one-use-owner-authenticated-classic-turn.md) | Blocked | 0025 merged and revalidated |
| 3 | [0027 — streaming parity](open/0027-one-use-owner-streaming-parity.md) | Blocked | 0026 merged and Plan 0022 revalidated |
| 4 | [0028 — runtime acceptance](open/0028-owner-authenticated-memory-runtime-acceptance.md) | Blocked | 0025–0027 green and merged |
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
