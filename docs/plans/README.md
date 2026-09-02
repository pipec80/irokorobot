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
| **NOW** | none | Plan 0043 closed 2026-09-02 with real-runtime acceptance. Plan 0032 is ready but promotion needs Pipec's explicit authorization. |
| **CLOSED** | [0043 — dependency refresh](completed/0043-dependency-refresh.md) | Merged as PR #92 (`0f69f58`). Lock refreshed to latest stable — 929 tests, typecheck, audit and all hooks green, no pin and no warning filter added. Real voice turn confirmed: Spanish detected at 100%, two spoken sentences, `outcome=ok`, `stt=2644ms llm=17161ms tts=735ms`. The 17 s LLM leg is this machine's known baseline, not a regression. |
| **CLOSED** | [0030 — real-camera face acceptance](completed/0030-real-camera-face-acceptance.md) | Executed 2026-09-01 — **provisional PASS**. 36 real genuine samples (Pipec, 3 lighting × 2 distance × 2 glasses) and 18 real impostor samples (3 unrelated household identities) held zero false accepts and zero false rejects; `face_authentication_match_threshold` moved from Plan 0029's unvalidated `0.25` to a measured `0.5815`, confirmed live with 3 accepted + 3 denied real turns through `just run-server` + `just run-robot`. Explicitly provisional — only 3 impostor identities were measured; a wider round is welcome later, not required to keep this closed. Closes only PC-2's real-camera acceptance — P1.2 still needs speaker evidence (PC-3) and fusion (PC-4); PC-4's anti-spoofing gap is untouched. |
| **QUEUED** | [0032 — server privacy and request observability](open/0032-server-privacy-and-request-observability.md) | First executable child of the audited server-production capsule, and the first plan in this chain that touches production code. Plan 0043 closing removed its blocker; promotion now needs only Pipec's explicit authorization. Its file list was corrected at 0043's closure after the acceptance run logged raw content from three sites the plan could not legally touch. Children 0033–0042 remain transitively queued in the order locked by 0031. |
| **REFERENCE ONLY** | [0015](open/0015-personal-companion-design.md) | Umbrella/design document; never execute it as an independent implementation batch |
| **REFERENCE ONLY** | [0031](open/0031-server-production-baseline-design.md) | Audited FastAPI/Starlette/Uvicorn hardening umbrella; preserves decisions and child order but is never executed as one batch. |

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
7. `QUEUED` documents preserve a reviewed future handoff; they do not compete
   with `NOW` and cannot be promoted until the current item closes or is
   explicitly removed as blocked.

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
| 8 | [0029 — consented local face evidence](completed/0029-consented-local-face-evidence.md) | Merged (PR #73, 2026-08-25) | Closed — its own real-camera acceptance (Plan 0030) closed 2026-09-01 |
| 9 | [0030 — real-camera face acceptance](completed/0030-real-camera-face-acceptance.md) | Executed 2026-09-01, provisional PASS | Closed. PC-2's real-camera acceptance only — P1.2's exit gate still needs speaker evidence (PC-3) and fusion (PC-4) |
| 10 | [0031 — server production baseline design](open/0031-server-production-baseline-design.md) | Audited reference capsule, not executable | Now that 0030 closed, begin only with queued Plan 0032 once Pipec authorizes promotion; then follow children 0033–0042 one at a time |
| 11 | [0043 — dependency refresh](completed/0043-dependency-refresh.md) | Merged 2026-09-02 (PR #92), acceptance recorded | Closed. Plan 0032 is unblocked and awaits explicit promotion |

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
