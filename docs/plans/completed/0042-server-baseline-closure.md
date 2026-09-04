# Server Production Baseline Closure Plan

> **Status:** Completed 2026-09-03. Historical evidence only — this document
> is not an instruction and authorizes nothing.

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:verification-before-completion`. This is verification and
> documentation work, not a container for deferred implementation.

**Goal:** Prove the complete server baseline through automated and real runtime
evidence, confirm the accepted ADRs still match the merged code, and close the capsule
without overstating product completion.

**Architecture:** Re-audit invariants with focused searches and complete gates;
update canonical docs from evidence. Any behavior defect opens a bounded
remediation plan instead of being fixed opportunistically here.

**Tech Stack:** repository `just` gates, pytest/OpenAPI, real server/robot
runtime, Markdown/ADR indexes.

**Spec:**
[`server-production-baseline.md`](../../architecture/server-production-baseline.md)

## Permitted files

- `server/README.md`, `SECURITY.md`
- `docs/architecture/server-production-baseline.md`
- `docs/architecture/current-state.md`, `docs/architecture/README.md`
- `docs/adr/README.md`, ADR 0010-0013 status only after Pipec review
- `docs/plans/README.md`, `docs/plans/open/README.md`
- Roadmap/delivery map only to record this baseline's own completion

No production or test code change is allowed. A failing gate blocks closure.

## Task 1: Static invariant audit

- [x] Sensitive logs:

  ```powershell
  rg -n "STT heard|LLM response|Server response:|Heard:|Speaking:|scene description" server/src robot/src
  ```

  **PASS** — every match logs a length (`%d chars`) or is a docstring/label;
  no raw content.
- [x] Transaction ownership:

  ```powershell
  rg -n "\.commit\(|\.rollback\(|BEGIN( IMMEDIATE| TRANSACTION)?" server/src/server
  ```

  **PASS** — `db.py` owns runtime transactions; `personal_setup.py`
  (`check_db_available`, the offline onboarding wizard) and
  `memory/legacy_v4_migration.py` (only ever imported by
  `scripts/migrate_memory_v4.py`, never a router) are the only exceptions,
  both outside the runtime request path.
- [x] HTTP resources:

  ```powershell
  rg -n "httpx\.AsyncClient\(" server/src/server
  ```

  **PASS** — exactly one construction site, `main.py`'s lifespan (Plan 0039).
- [x] Upload reads:

  ```powershell
  rg -n "await .*\.read\(\)" server/src/server/routers
  ```

  **PASS** — no matches; no unbounded upload read.

## Task 2: Complete automated gates

- [x] Ran:

  ```powershell
  uv lock --check
  just lint
  just typecheck
  just test
  just audit
  just check
  uv build --all-packages
  git diff --check
  ```

  All pass. `just test` (`-n auto`): 1068 passed. A real, reproducible gap
  found mid-run (17 failures, order-dependent under `pytest-xdist`) was
  fixed by the bounded Plan 0045 before this task closed — see execution
  notes.
- [x] Ran the exact deterministic CI coverage command
  (`pytest -m "not slow and not hardware and not eval" --cov=server/src
  --cov=robot/src --cov-report=term --cov-fail-under=80`): **1059 passed, 9
  deselected, 90.03% coverage** (required 80%).
- [x] Ran `tests/integration/test_api_contract.py` and
  `tests/integration/test_openapi_contract.py` separately: **10 passed**.

## Task 3: Runtime acceptance

- [x] Started the real `just run-server` and `just run-robot` path (Pipec,
  2026-09-03).
- [x] Executed the repeatable cases — see execution notes for the full
  outcome table. All 7 pass, one non-blocking Windows-dev-terminal
  observation recorded (not a defect).
- [x] Recorded outcomes/timings/status only — no PINs, tokens, transcripts,
  household values, frames, or database dumps.
- [x] Real Linux supervisor verification is explicitly deferred to the
  homelab deployment — not fabricated from Windows, per this task's own
  instruction.

## Task 4: Accept decisions and close documentation

- [x] ADR 0010-0013 were presented to Pipec and accepted on 2026-09-02, ahead
  of this plan. Re-confirmed: each of the four still matches the merged
  code exactly (one Uvicorn worker + loopback default + no proxy trust +
  no CORS for 0010/0013; `db.transaction()` + offline-only exceptions for
  0011; the preserved `application/x-ndjson` transport + terminal `error`
  event, with native JSON Lines measured-and-deferred for 0012). None
  reopened.
- [x] Filled `server/README.md` with role, a Mermaid request-flow diagram,
  setup/run, a configuration table, docs URLs, health/readiness, the
  streaming contract, testing, and deployment posture — the pre-existing
  Plan 0038 capacity-policy section is preserved unchanged.
- [x] Added a "Network posture", "Upload limits", and "Logging rules"
  section to `SECURITY.md`.
- [x] Updated `docs/architecture/current-state.md` (streaming terminal-error
  row + new capsule-closure row), `docs/architecture/README.md` (stale
  "Plan 0030 remains ahead" line), and
  `docs/architecture/server-production-baseline.md` (Status/Authority
  sections, current test counts, the Plan 0045 gap added to "Verified
  baseline", the JSON-Lines-not-adopted finding already recorded during
  Plan 0041's closure).
- [x] No PC-3/PC-4/PC-5/PC-6 or physical-robot claim appears anywhere in
  this plan's evidence — confirmed by re-reading every file this task
  touched before closing.

## Execution notes

### Task 2 found a real, order-dependent test gap — closed by Plan 0045

`just test` (`-n auto`) first ran green, but a repeat surfaced 16 (later
confirmed 17) failures across 4 integration test files, all
`AttributeError: 'State' object has no attribute 'resources'`. Root cause:
these files construct their own `ASGITransport(app=app)` and never run the
app lifespan, so any `ResourcesDep`-dependent route 500s unless an earlier
test in the same `pytest-xdist` worker happened to set
`app.state.resources` first as a side effect — CI stayed green only because
its single-process run's collection order masked it by accident. Per this
plan's own "any behavior defect opens a bounded remediation plan" rule, this
was **not** fixed here — see
[Plan 0045](../completed/0045-async-test-client-resources-parity.md)
(merged as PR #113), executed as its own coordinated commit boundary before
this task's gate was re-run and confirmed clean.

### Task 3 — real runtime acceptance (Pipec, 2026-09-03)

| Case | Result |
|---|---|
| Health | `GET /health` → `200` |
| Readiness | `GET /ready` → `200` |
| Valid stream (×2, via `just run-robot`'s own mic loop) | `POST /transcribe/stream` → `200` both times, first turn logged `Stream done: outcome=ok`; timings 17.6s and 4.9s |
| Malformed PIN | `POST /auth/owner/unlock` with a non-digit PIN → `422`, `"PIN must be 6 to 12 ASCII digits"` |
| Wrong PIN | Correctly-formatted but wrong PIN → `401`, `"Owner authentication failed"` |
| Oversized audio | 60 MB WAV → `413` in 4 ms — rejected before STT, not after a slow attempt |
| Classic voice (`POST /transcribe`) | A generated contract-compliant (16 kHz/mono/int16) 1-second silent WAV → `422`, `"No speech detected in audio"`. No real speech sample was available, so this exercises upload→STT→VAD plumbing on the classic route rather than the full happy path — the happy path itself is already covered by the automated suite's mocked-STT integration tests. |
| Graceful shutdown at idle | `Ctrl+C` with no turn in flight logged a clean, ordered lifespan unwind (`Shutting down` → `Waiting for application shutdown` → `OMNiBot 2000 shutting down.` → `Retention background job stopped` → `Application shutdown complete` → `Finished server process`), no traceback. `just` itself reported `exit code 1` for the recipe — a Windows foreground-`Ctrl+C` characteristic of the dev workflow (the shell surfaces the interrupt as a non-zero recipe exit regardless of how cleanly the app's own lifespan unwound), not an application defect. Recorded here rather than hidden; does not block closure. The real production supervisor (systemd or equivalent) is verified separately on the Linux homelab deployment per this task's own instruction — not fabricated from Windows. |

The first curl attempts at the two PIN cases initially returned `422 "JSON
decode error"` instead of testing the intended path — a PowerShell quoting
issue (`\"` inside a double-quoted `-d` argument does not escape the way it
does in `cmd.exe`), not a server defect. Re-run with single-quoted JSON
bodies produced the correct, intended results shown above.

## Rollback

Documentation/status changes are one explicit commit. Revert it if evidence or
ADR approval was recorded incorrectly; completed implementation PRs remain
independent.

## Completion criteria

- All child plans 0032-0041 meet their own criteria and reviews.
- Full deterministic gates and real runtime cases pass.
- ADR status matches explicit Pipec decisions.
- Canonical docs describe current code, not the original audit snapshot.
- No unresolved finding is hidden inside closure documentation.

## Closure

Documentation/verification-only close, one commit. Every child plan in the
0031 capsule (0032–0041, plus 0045, a gap this plan's own Task 2 gate found
and routed to its own bounded plan rather than fixing here) meets its own
criteria; every automated gate and real runtime case in this plan's own
Tasks 1–3 passed; all four ADRs were re-confirmed against the merged code;
`server/README.md`, `SECURITY.md`, `current-state.md`,
`architecture/README.md`, and `server-production-baseline.md` now describe
measured current behavior. Only Plan 0044 remains in the 0031 capsule,
queued separately and not authorized by this closure.
