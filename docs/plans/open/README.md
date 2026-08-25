# Open plan index

> **Status:** Work not yet closed. A plan can be implemented, partially
> implemented, deferred, or only designed and still belong here. Presence in
> this directory does not grant permission to implement.

## Audited disposition

The following status was checked against the executable code, tests, current
Git ancestry, and recorded runtime evidence on 2026-08-25 (updated after the
combined P0-C operator runbook passed and Plan 0013's STT-accuracy debt
closed). Existing components named under **Reuse** must not be rebuilt by a
later plan.

For daily work, do not choose a plan from this inventory. Follow the
single-WIP [operational board](../README.md#operational-board) — **P0 is
fully accepted and no plan is currently authorized.** Use the
[personal-companion delivery map](../../roadmap/personal-companion-delivery-map.md)
to see the code, tests, verified gap, and accountable plan for each outcome.

| Plan | Implementation reality | Reuse | Remaining closure |
|---|---|---|---|
| [0014](0014-p0-runtime-policy-hardening-design.md) | Complete umbrella: C1–C7 implemented, reviewed, and operator-confirmed | Plans 0016–0023 | None — combined P0-C operator acceptance passed 2026-08-25 |
| [0015](0015-personal-companion-design.md) | Approved product design; PC-1 code and acceptance are both complete (Plans 0025–0028) | Controller, policy/audit, v4 child tools, identity-session seam, onboarding primitives, STT/TTS, face engine | Biometrics (face/voice fusion, PC-2/PC-3) remain later slices |
| [0020](0020-p0-operator-qa-remediation-design.md) | Complete umbrella: C5/C6/C7 all implemented, reviewed, and operator-confirmed | Typed intent resolution (0021), reliable streaming (0022), grounded visual dialogue (0023) | None — its own "required real acceptance rerun" passed 2026-08-25 |
| [0024](0024-owner-authenticated-memory-mvp-design.md) | Approved design; fully delivered by Plans 0025–0028 | Existing identity, authorization, child-memory, and channel seams | None — design delivered |

Plans 0025, 0026, 0027, and 0028 (all merged/executed, PC-1 accepted
2026-08-21) closed with no remaining acceptance debt of their own — see
[completed/0025](../completed/0025-personal-owner-bootstrap-and-pin-setup.md),
[completed/0026](../completed/0026-one-use-owner-authenticated-classic-turn.md),
[completed/0027](../completed/0027-one-use-owner-streaming-parity.md), and
[completed/0028](../completed/0028-owner-authenticated-memory-runtime-acceptance.md).
Plans 0021 (C5, operator-confirmed 2026-08-21), 0023 (C7, operator-confirmed
2026-08-25), and 0013 (voice-controller bridge, R1 complete 2026-08-25 after
fixing the Whisper prompt's stale "Omnibot" name) closed the same way — see
[completed/0021](../completed/0021-p0-typed-intent-resolution.md),
[completed/0023](../completed/0023-p0-grounded-visual-dialogue.md), and
[completed/0013](../completed/0013-p0-voice-controller-bridge.md).

Canonical execution order: **none — P0 is fully accepted.**

## Status rule

- `implemented` describes code, not product acceptance;
- `partial` means some named slices are reusable and others remain open;
- `design` or `ready` is not implementation evidence;
- a plan moves to `completed/` only when its own automated, review, and real
  runtime completion criteria are recorded.
