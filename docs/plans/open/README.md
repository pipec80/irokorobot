# Open plan index

> **Status:** Work not yet closed. A plan can be implemented, partially
> implemented, deferred, or only designed and still belong here. Presence in
> this directory does not grant permission to implement.

## Audited disposition

The following status was checked against the executable code, tests, current
Git ancestry, and recorded runtime evidence on 2026-08-25 (updated after the
combined P0-C operator runbook passed and Plan 0013's STT-accuracy debt
closed), and re-audited 2026-09-01 after Plan 0030 closed. Existing
components named under **Reuse** must not be rebuilt by a later plan.

For daily work, do not choose a plan from this inventory. Follow the
single-WIP [operational board](../README.md#operational-board) — **`NOW` is
empty; nothing is currently authorized.** Use the
[personal-companion delivery map](../../roadmap/personal-companion-delivery-map.md)
to see the code, tests, verified gap, and accountable plan for each outcome.

| Plan | Implementation reality | Reuse | Remaining closure |
|---|---|---|---|
| [0015](0015-personal-companion-design.md) | Approved product design; PC-1 code and acceptance are both complete (Plans 0025–0028); PC-2 code, tests, and real-camera acceptance are complete (Plans 0029/0030) | Controller, policy/audit, v4 child tools, identity-session seam, onboarding primitives, STT/TTS, face engine, calibrated face-authentication threshold | Speaker evidence (PC-3), fusion (PC-4), visual companion acceptance (PC-5), and family profile expansion (PC-6) remain later slices |
| [0031](0031-server-production-baseline-design.md) | Audited reference-only server capsule; no production implementation | Existing FastAPI/Starlette/Uvicorn, HTTP/audio contracts, tests and server/robot boundary | Children 0032–0037 closed; 0038–0042 remain, one at a time, pending Pipec's explicit authorization to promote 0038 |

## Queued server-production capsule

Plan 0030 closed 2026-09-01, lifting the blocker Queue rule 7 named — but
promotion is not automatic. These plans remain **not authorized** until
Pipec explicitly promotes the first one. Plan 0031 locks their order; only
the first unfinished child may be promoted after a narrow assumption
recheck.

[Plan 0043](../completed/0043-dependency-refresh.md) ran before this chain and
closed on 2026-09-02. It already reshaped two children: 0034 dropped its
hand-written raw body limit in favor of Starlette 1.6.0's native
`RequestBodyLimitMiddleware`, and 0038 inherits the `filterwarnings` blind spot
it found. Its acceptance run also corrected 0032's file list.

[Plan 0034](../completed/0034-upload-and-multipart-security.md) closed
2026-09-02 (PR #98): a raw ASGI body-limit middleware plus per-file bounded
reads, with a real gap found by its own RED test — an oversized `frame` field
was invisible to every per-file check whenever face auth was off, the
default.

[Plan 0035](../completed/0035-sqlite-transaction-owner.md) closed 2026-09-02
(PR #99): the `db.transaction()` primitive, unused by any repository yet.
Its own RED test found the lock's design was wrong — bound to whichever event
loop first awaited it — fixed by giving it the connection's own lifecycle.

[Plan 0036](../completed/0036-sqlite-write-migration-and-outbox-removal.md)
closed 2026-09-02 (PR #101): every runtime repository write now goes through
`db.transaction()`; the unused outbox writer is removed. Its own concurrency
test found a worse bug than the one it went looking for — a write with no
transaction of its own silently committed another function's still-open
transaction, so a caller's rollback on failure had nothing left to roll back.
Verified live: seven voice turns, zero errors, the migrated audit write
firing correctly under the real server.

[Plan 0037](../completed/0037-deterministic-ci-baseline.md) closed
2026-09-03 (PR #103): CI was silently excluding a third of the suite
(`integration`, 353 of 997 tests) with no coverage floor — the marker's own
"needs real hardware/APIs" description never matched any test using it. Its
first CI push then caught a real bug the local run couldn't see: two tests
only mocked STT, silently relying on a local Ollama and Piper CI doesn't
have. All five CI checks green after the fix; 998 tests, 90% coverage.

| Order | Plan | Outcome |
|---:|---|---|
| 1 | [0038](0038-uvicorn-runtime-baseline.md) | Explicit one-worker runtime defaults |
| 2 | [0039](0039-application-lifecycle-and-http-resources.md) | Failure-safe lifespan and shared HTTP transport |
| 3 | [0040](0040-fastapi-contract-and-openapi-baseline.md) | Typed dependencies, OpenAPI, health/readiness |
| 4 | [0041](0041-streaming-terminal-contract.md) | Coordinated terminal stream error |
| 5 | [0042](0042-server-baseline-closure.md) | Full gates, runtime evidence, ADR review, and closure |
| 6 | [0044](0044-official-fastapi-conventions.md) | Alignment with the official FastAPI conventions the audit predated |

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

Canonical execution order: **none — `NOW` is empty.** The server capsule is
queued, beginning with 0038 only once Pipec authorizes promotion.

## Status rule

- `implemented` describes code, not product acceptance;
- `partial` means some named slices are reusable and others remain open;
- `design` or `ready` is not implementation evidence;
- a plan moves to `completed/` only when its own automated, review, and real
  runtime completion criteria are recorded.
