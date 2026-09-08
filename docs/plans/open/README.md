# Open plan index

> **Status:** Work not yet closed. A plan can be implemented, partially
> implemented, deferred, or only designed and still belong here. Presence in
> this directory does not grant permission to implement.

## Audited disposition

The following status was checked against the executable code, tests, current
Git ancestry, and recorded runtime evidence on 2026-08-25 (updated after the
combined P0-C operator runbook passed and Plan 0013's STT-accuracy debt
closed), re-audited 2026-09-01 after Plan 0030 closed, aligned on
2026-09-07 with the longitudinal-memory design and its first two bounded
plans, updated 2026-09-08 after Plan 0046 closed CM-0, and again 2026-09-08
after Plan 0047 (PC-3A) was promoted to `Ready`/`NOW` on Pipec's explicit
decision (readiness amendment + independent review APPROVE WITH MINOR FIXES
both complete), with Tasks 0–3 authorized to execute and Tasks 4–6 held.
Existing components named under **Reuse** must not be rebuilt by a later plan.

For daily work, do not choose a plan from this inventory. Follow the
single-WIP [operational board](../README.md#operational-board) — **CM-0
(Plan 0046) closed 2026-09-08; Plan 0047 (PC-3A) was promoted to `Ready`/`NOW`
on Pipec's explicit decision 2026-09-08.** Execution is staged: Tasks 0–3
(numeric layer, corpus CLI, frozen backend + p95 gate) run now on
`feat/0047-speaker-calibration`; Tasks 4–6 (household capture) are held with no
date until three consenting adults are confirmed. Use the
[personal-companion delivery map](../../roadmap/personal-companion-delivery-map.md)
and [conversational-memory delivery map](../../roadmap/conversational-memory-delivery-map.md)
to see the code, tests, verified gaps, and future delivery sequence.

| Plan | Implementation reality | Reuse | Remaining closure |
|---|---|---|---|
| [0015](0015-personal-companion-design.md) | Approved product design; PC-1 is complete and PC-2 has a provisional calibrated acceptance | Controller, policy/audit, V4 household tools, identity/session seam, working memory, legacy extraction/vector storage, STT/TTS, face engine | PC-3 speaker, PC-4 fusion, CM-1…CM-7 longitudinal memory, PC-5 integrated personal acceptance, and PC-6 family remain open (CM-0 closed) |
| [0047](0047-speaker-evidence-calibration-study.md) | **Ready / NOW** (promoted 2026-09-08). Tasks 0–3 executing on `feat/0047-speaker-calibration`; Tasks 4–6 held for consented-adult confirmation | WAV/audio contract, microphone capture, face-calibration numeric/corpus pattern | Finish Tasks 0–3 (frozen backend + p95 gate), then capture + measure PC-3A once adults confirmed; PC-3B and PC-4 remain separate |

## Server-production capsule — CLOSED 2026-09-03

[Plan 0031](../completed/0031-server-production-baseline-design.md) locked
the execution order of its children; all of them (0032–0045,
including Plan 0043's dependency refresh which ran first, and Plan 0045, a
test-isolation gap Plan 0042's own gate found) are closed. Full per-plan
evidence lives in each plan's own file under [`completed/`](../completed/)
and in the [dependency-order table](../README.md#dependency-order) — not
duplicated here, since nothing in this capsule is still open. **No child
plan remains queued.**

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

Plans 0029 (consented local face evidence, merged PR #73, 2026-08-25) and
0030 (real-camera face acceptance, executed 2026-09-01 — **provisional
PASS**: 36 genuine + 18 impostor real samples, zero false accepts/rejects,
threshold `0.5815` confirmed by 3 accepted + 3 denied live turns) closed
PC-2 completely — see
[completed/0029](../completed/0029-consented-local-face-evidence.md) and
[completed/0030](../completed/0030-real-camera-face-acceptance.md).

Plan 0046 (CM-0 reproducible longitudinal-memory baseline) closed 2026-09-08 —
the benchmark harness is GREEN and the measured baseline is a reproducible
cognitive RED (`ac43c58`, exit 1); it changed no runtime memory. See
[completed/0046](../completed/0046-reproducible-longitudinal-memory-baseline.md).

Canonical execution order: **Plan 0047 (PC-3A) is `Ready`/`NOW`**, promoted
2026-09-08 on Pipec's explicit decision; Tasks 0–3 execute now on
`feat/0047-speaker-calibration`, Tasks 4–6 wait for consented-adult
confirmation. The server capsule (Plan 0031, children 0032–0045) is fully
closed.

[Plan 0048](../completed/0048-fastapi-baseline-final-hardening.md) closed
2026-09-07: a bounded follow-up to a second independent audit of the server
(semantic `max_length` on free-text fields, a real one-terminal-event
guarantee in `guarantee_terminal_event`, the `/transcribe/stream` 200
documented as `application/x-ndjson`, `/health` wording + a
settings-injectable `create_app`). 1073 tests, 90.10% coverage, all gates
green. The "how should FastAPI do this?" phase is over; the server baseline
is done. Only Uvicorn concurrency calibration remains, deferred to its own
`perf(...)` plan pending measurement on real homelab hardware; it does not
replace or compete with the canonical `NOW` item.

## Status rule

- `implemented` describes code, not product acceptance;
- `partial` means some named slices are reusable and others remain open;
- `design` or `ready` is not implementation evidence;
- a plan moves to `completed/` only when its own automated, review, and real
  runtime completion criteria are recorded.
