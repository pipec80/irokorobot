# P0 Closure and Acceptance Evidence Plan

> **Status:** Draft — promote to Ready only after Plan 0010 is merged and
> `main` is revalidated.

**Goal:** Produce evidence that the P0 foundation is safe, deterministic,
local-first, and ready to hand off to P1 planning without claiming P1 exists.

**Architecture:** This is evidence-only. It adds no runtime feature, schema,
provider, endpoint, identity adapter, consent persistence, or hardware
behavior. It consumes the merged P0.5-B2 acceptance suite and records exact
local/CI evidence and remaining boundaries.

## Promotion conditions

Promote this plan to Ready only when all are true on updated `main`:

- Plan 0010 merged with a recorded green GitHub CI result.
- Current state, roadmap, and portfolio accurately distinguish B2 from P1.
- Offline tests cover unknown identity, authorization-before-v4-read,
  consent-gated child data, relationship count, multi-value preferences,
  deterministic age, and public-chat non-disclosure.
- No open PR contains unfinished P0 code or evidence.

## Execution outline after promotion

1. Revalidate Git state, guardrails, P0 plans 0001–0010, and actual P0
   acceptance paths.
2. Run `just lint`, `just typecheck`, `just test`, `just audit`, `just check`,
   and `git diff --check`; record only actual outputs.
3. Run the named P0 acceptance suites and inspect audit rows to prove data
   values never reach authorization audit metadata.
4. Review that public `/chat` remains unknown and cannot supply identity or
   consent; controller tools are bounded; no legacy/v3, vector, prompt,
   provider, or hardware path handles family truth.
5. Update canonical evidence docs, open a documentation PR, and merge it only
   after green CI.

## Explicit non-goals

- P1 onboarding, WorldState, structured perception, face/voice evidence,
  speaker recognition, diarization, identity fusion, or object detection.
- Public login/admin/consent UX, persistent consent, name resolution,
  relationship queries beyond Plan 0010, semantic retrieval, memory lifecycle,
  cloud escalation, ROS2, or physical actions.
