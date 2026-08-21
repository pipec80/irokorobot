# Open plan index

> **Status:** Work not yet closed. A plan can be implemented, partially
> implemented, deferred, or only designed and still belong here. Presence in
> this directory does not grant permission to implement.

## Audited disposition

The following status was checked against the executable code, tests, current
Git ancestry, and recorded runtime evidence on 2026-08-21 (updated after Plan
0028's real-hardware acceptance run and PR #65's documentation closure).
Existing components named under **Reuse** must not be rebuilt by a later plan.

For daily work, do not choose a plan from this inventory. Follow the single-WIP
[operational board](../README.md#operational-board), whose current `NOW` item
is Plan 0023. Use the
[personal-companion delivery map](../../roadmap/personal-companion-delivery-map.md)
to see the code, tests, verified gap, and accountable plan for each outcome.

| Plan | Implementation reality | Reuse | Remaining closure |
|---|---|---|---|
| [0013](0013-p0-voice-controller-bridge.md) | Implemented and merged by PR #51 | Classic `/transcribe` controller bridge, unknown public actor, deterministic/protected routes | Plan 0028 ran R1-01–R1-03: R1-01/R1-02 passed, R1-03 failed (Whisper cannot reliably transcribe the proper noun "Iroko", 5/5 attempts). Needs an STT fix (e.g. hotwords/`initial_prompt`) and a clean re-run before this plan can close. |
| [0014](0014-p0-runtime-policy-hardening-design.md) | Partial umbrella: C1–C6 implemented | Plans 0016–0019, 0021, and 0022 | C7 and combined P0 operator acceptance |
| [0015](0015-personal-companion-design.md) | Approved product design; PC-1 code and acceptance are both complete (Plans 0025–0028) | Controller, policy/audit, v4 child tools, identity-session seam, onboarding primitives, STT/TTS, face engine | Biometrics (face/voice fusion, PC-2/PC-3) remain later slices |
| [0020](0020-p0-operator-qa-remediation-design.md) | Partial umbrella: C5/C6 complete; C7 not executed | Reliable streaming output from completed Plan 0022; typed intent resolution from completed Plan 0021 | Execute 0023, then combined P0-C acceptance |
| [0023](0023-p0-grounded-visual-dialogue.md) | Plan-specific grounding not started | Existing vision controller parity, scene perception/VLM transport, image validation, Piper, enrollment quarantine | Add typed visual decisions, preflight before frame access, direct grounded VLM-to-TTS, migrate triggers, and accept physically |
| [0024](0024-owner-authenticated-memory-mvp-design.md) | Approved design; fully delivered by Plans 0025–0028 | Existing identity, authorization, child-memory, and channel seams | None — design delivered |

Plans 0025, 0026, 0027, and 0028 (all merged/executed, PC-1 accepted
2026-08-21) closed with no remaining acceptance debt of their own — see
[completed/0025](../completed/0025-personal-owner-bootstrap-and-pin-setup.md),
[completed/0026](../completed/0026-one-use-owner-authenticated-classic-turn.md),
[completed/0027](../completed/0027-one-use-owner-streaming-parity.md), and
[completed/0028](../completed/0028-owner-authenticated-memory-runtime-acceptance.md).
Plan 0021 (C5 typed intent resolution, operator-confirmed 2026-08-21) closed
the same way — see
[completed/0021](../completed/0021-p0-typed-intent-resolution.md).
Plan 0013's own R1 debt is tracked independently (see its row above) and is
not a PC-1 blocker.

Canonical execution order: **0023**.

## Status rule

- `implemented` describes code, not product acceptance;
- `partial` means some named slices are reusable and others remain open;
- `design` or `ready` is not implementation evidence;
- a plan moves to `completed/` only when its own automated, review, and real
  runtime completion criteria are recorded.
