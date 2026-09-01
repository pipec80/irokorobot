# Server Production Baseline Closure Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:verification-before-completion`. This is verification and
> documentation work, not a container for deferred implementation.

**Goal:** Prove the complete server baseline through automated and real runtime
evidence, accept or reject proposed ADRs explicitly, and close the capsule
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

- [ ] Sensitive logs:

  ```powershell
  rg -n "STT heard|LLM response|Server response:|Heard:|Speaking:|scene description" server/src robot/src
  ```

  Expected: no raw-content logging occurrence.
- [ ] Transaction ownership:

  ```powershell
  rg -n "\.commit\(|\.rollback\(|BEGIN( IMMEDIATE| TRANSACTION)?" server/src/server
  ```

  Expected: `db.py` plus documented startup/offline-exclusive exceptions only.
- [ ] HTTP resources:

  ```powershell
  rg -n "httpx\.AsyncClient\(" server/src/server
  ```

  Expected: lifecycle/resource construction only.
- [ ] Upload reads:

  ```powershell
  rg -n "await .*\.read\(\)" server/src/server/routers
  ```

  Expected: no unbounded upload read.

## Task 2: Complete automated gates

- [ ] Run:

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

- [ ] Run the exact deterministic CI coverage command and record tests/coverage.
- [ ] Run OpenAPI contract/security tests separately and archive their literal
  pass result in this plan's execution evidence.

## Task 3: Runtime acceptance

- [ ] Start the real `just run-server` and `just run-robot` path.
- [ ] Execute repeatable cases: valid classic voice, valid stream, malformed
  PIN, wrong PIN, oversized audio rejected before STT, health/readiness, and
  graceful shutdown during idle.
- [ ] Record outcomes/timings/status only—never PINs, tokens, transcripts,
  household values, frames, or database dumps.
- [ ] On the intended Linux server, verify the actual supervisor separately if
  one exists. Do not create a fictional systemd PASS from Windows.

## Task 4: Accept decisions and close documentation

- [ ] Present ADR 0010-0013 to Pipec. Change each to `Accepted` only with
  explicit approval; otherwise leave `Proposed` and keep the dependent baseline
  open.
- [ ] Fill `server/README.md` with role, Mermaid flow, setup/run, configuration,
  docs URLs, health/readiness, streaming, testing, and deployment posture.
- [ ] Update `SECURITY.md` with loopback/LAN/proxy/upload/logging rules.
- [ ] Update current state and plan indexes with measured evidence, moving
  completed children according to repository rules.
- [ ] Never claim PC-3/PC-4/PC-5/PC-6 or physical robot completion from server
  baseline evidence.

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
