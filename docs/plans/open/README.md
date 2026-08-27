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
single-WIP [operational board](../README.md#operational-board) — **Plan 0030
is the current `NOW` item.** Use the
[personal-companion delivery map](../../roadmap/personal-companion-delivery-map.md)
to see the code, tests, verified gap, and accountable plan for each outcome.

| Plan | Implementation reality | Reuse | Remaining closure |
|---|---|---|---|
| [0015](0015-personal-companion-design.md) | Approved product design; PC-1 code and acceptance are both complete (Plans 0025–0028); PC-2 code/tests/review complete (Plan 0029) | Controller, policy/audit, v4 child tools, identity-session seam, onboarding primitives, STT/TTS, face engine | PC-2's real-camera acceptance (Plan 0030); speaker evidence (PC-3), fusion (PC-4), visual companion acceptance (PC-5), and family profile expansion (PC-6) remain later slices |
| [0029](0029-consented-local-face-evidence.md) | Merged (PR #73); a first real-hardware proof of concept ran 2026-08-27 via `just onboard` | Face engine, biometric consent repository, in-turn face resolver | Calibrated real-camera acceptance — owned by Plan 0030, below |
| [0030](0030-real-camera-face-acceptance.md) | Written 2026-08-27, not yet executed | `face_auth_demo.py`'s enrollment flow, `detect_faces`, `capture_frame` | The current `NOW` item — see the [operational board](../README.md#operational-board) |

Plans 0014 (P0 runtime-policy umbrella), 0020 (operator-QA remediation
umbrella), and 0024 (owner-authenticated memory MVP design) closed with no
remaining code or gates of their own — each was reference material for
already-completed slices — and moved to `completed/`; see
[completed/0014](../completed/0014-p0-runtime-policy-hardening-design.md),
[completed/0020](../completed/0020-p0-operator-qa-remediation-design.md), and
[completed/0024](../completed/0024-owner-authenticated-memory-mvp-design.md).
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

Canonical execution order: **Plan 0030 (real-camera face acceptance) — the
only executable item in `NOW`.**

## Status rule

- `implemented` describes code, not product acceptance;
- `partial` means some named slices are reusable and others remain open;
- `design` or `ready` is not implementation evidence;
- a plan moves to `completed/` only when its own automated, review, and real
  runtime completion criteria are recorded.
