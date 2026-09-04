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
| [0031](0031-server-production-baseline-design.md) | Audited reference-only server capsule; no production implementation | Existing FastAPI/Starlette/Uvicorn, HTTP/audio contracts, tests and server/robot boundary | **Fully closed 2026-09-03** — every child (0032–0045) is closed; no work remains under this umbrella |

## Server-production capsule — CLOSED 2026-09-03

Plan 0030 closed 2026-09-01, lifting the blocker Queue rule 7 named. Plan
0031 locked the execution order of its children below; all of them (0032–
0045) are now closed, described here as historical record.

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

[Plan 0038](../completed/0038-uvicorn-runtime-baseline.md) closed
2026-09-03 (PR #105): `uvicorn_workers` is `Literal[1]`, `uvicorn_max_requests`
defaults to unset (the old fixed `1000` self-terminated the process with no
supervisor), and `build_uvicorn_kwargs()` makes every runtime flag a
unit-tested value. Investigated and reverted a fix for the standing
`httpx2` gap Plan 0037 flagged — it works but breaks typing in five files
outside this plan's scope — recorded as Plan 0044's new Task 5 instead of
losing it. 1015 tests, ~90% coverage, all five CI checks green.

[Plan 0039](../completed/0039-application-lifecycle-and-http-resources.md)
closed 2026-09-03 (PR #107): `create_app()` + a failure-safe `lifespan()`
owning a shared `httpx.AsyncClient` via `AsyncExitStack`; every Ollama/VLM/
embedding call site now takes that client as a required parameter instead of
constructing its own. A real bug only the full test suite could catch — the
`client` TestClient fixture never ran the lifespan, so `app.state.resources`
never existed — is fixed in the shared fixtures. 1019 tests, all five CI
checks green. Verified live: a full voice turn completed end-to-end; the
verbose traceback logged for an expected "Ollama down" fallback was recorded
as Plan 0044's new Task 6, not fixed here.

[Plan 0040](../completed/0040-fastapi-contract-and-openapi-baseline.md) closed
2026-09-03 (PR #109): typed FastAPI dependencies (`ResourcesDep`,
`OwnerUnlockServiceDep`, `IdentityTokenDep`) replace `owner_unlock_service`
module-level imports at the HTTP boundary; every route's real error codes
are documented via a shared `ErrorResponse`; `GET /ready` is a new
side-effect-free readiness probe distinct from `/health`; the OpenAPI
version reads the real installed package version instead of a hardcoded
literal that had already drifted from `pyproject.toml`. Fixed 37 tests
across 5 files that monkeypatched `owner_unlock_service` as a module
attribute, migrated to `app.dependency_overrides`. 1039 tests, all five CI
checks green. No live voice-turn acceptance needed — no hot-path body
changed.

[Plan 0041](../completed/0041-streaming-terminal-contract.md) closed
2026-09-03 (PR #111): every started `/transcribe/stream` now ends in exactly
one `done` or privacy-safe `error` event, never a truncated connection (ADR
0012) — `streaming.guarantee_terminal_event()` wraps both stream producers at
their single `StreamingResponse()` call site, classifying a post-header
`TTSError` as retryable and anything else as a generic internal error. Task
0 measured native FastAPI JSON Lines with a throwaway prototype and found a
real blocker: a pre-first-yield `HTTPException` in a generator-endpoint no
longer returns a clean HTTP error once FastAPI owns the streaming response —
kept `application/x-ndjson`, left the question open for Plan 0042. Robot
gained `ErrorEvent` (forward-compatible free-form code) reusing the existing
`RobotState.ERROR` path, no new state machine. 1059 tests, all five CI
checks green. Verified live: two full voice turns through the new code
path, both `outcome=ok`; the synthetic-TTS-failure branch was deferred by
Pipec's own choice, already covered in depth by 6 automated tests at the
unit and HTTP level.

[Plan 0045](../completed/0045-async-test-client-resources-parity.md) closed
2026-09-03 (PR #113): discovered mid-execution of Plan 0042's own Task 2
gate — 4 integration test files' hand-rolled `ASGITransport` clients never
set `app.state.resources`, so any `ResourcesDep`-dependent route 500s
unless an earlier test in the same `pytest-xdist` worker happened to set it
first as a side effect; CI stayed green only by collection-order accident.
Fixed by matching the 2 already-correct sibling files' pattern in all 4
affected files. Test-only change, no production code touched. `just test`
— 1068 passed, run twice back to back, 0 failures.

[Plan 0042](../completed/0042-server-baseline-closure.md) closed 2026-09-03:
full gates and real runtime evidence, closing the whole 0031 capsule. Task 1's
static audit (sensitive logs, transaction ownership, HTTP resources, upload
reads) passed clean. Task 2 re-ran every gate — `just test` 1068 passed, the
exact deterministic CI coverage command 1059 passed at 90.03% coverage,
OpenAPI contract tests 10 passed — finding and routing the Plan 0045 gap
through its own bounded plan rather than fixing it opportunistically here.
Task 3's real runtime acceptance (Pipec) covered all 7 required cases:
health, readiness, two full stream turns, malformed PIN (422), wrong PIN
(401), oversized audio (413 in 4ms), classic `/transcribe` upload→STT→VAD
plumbing, and a clean graceful shutdown. Task 4 re-confirmed ADRs 0010–0013
still match the merged code, filled in `server/README.md` and `SECURITY.md`,
and refreshed `current-state.md`/`architecture/README.md`/
`server-production-baseline.md` from measured evidence.

[Plan 0044](../completed/0044-official-fastapi-conventions.md) closed
2026-09-03, the 0031 capsule's last child: 6 tasks, each RED-tested first.
`chat_ui.py` now uses `app.frontend()` instead of a manual `StaticFiles`
mount — a throwaway prototype proved the manual mount can be shadowed by a
later-registered API route sharing its path, locked in by a permanent
regression test. All four multi-route routers moved to `APIRouter(prefix=
...)` + relative paths, proven identical by the existing route-pinning
test. Removed 2 genuinely redundant `response_model=` declarations
(OpenAPI byte-identical before/after). Found the plan's named stale-rule
file already correct and fixed the real one instead
(`python-style.md`, not `fastapi.md`). Installed `httpx2`, fixed 7 affected
type annotations — the `StarletteDeprecationWarning` is gone from every
test run. Added `llm.is_connectivity_failure()` so an unreachable Ollama
logs `WARNING` with no traceback while a genuinely unexpected LLM failure
still gets `ERROR` with `exc_info=True`, applied identically to both the
streaming and classic paths. 1073 tests, all green. No live voice-turn
acceptance — no wire change, confirmed explicitly by Pipec.

**The 0031 capsule is now fully closed — no child plan remains queued.**

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

Canonical execution order: **none — `NOW` is empty.** The server capsule
(Plan 0031, children 0032–0045) is fully closed; no child plan remains
queued.

## Status rule

- `implemented` describes code, not product acceptance;
- `partial` means some named slices are reusable and others remain open;
- `design` or `ready` is not implementation evidence;
- a plan moves to `completed/` only when its own automated, review, and real
  runtime completion criteria are recorded.
