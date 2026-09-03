# Async Test Client Resources Parity Plan

> **Status:** Completed 2026-09-03. Historical evidence only — this document
> is not an instruction and authorizes nothing.

**Goal:** Make every hand-rolled async `ASGITransport` test client set
`app.state.resources` the same way the already-fixed sibling files do, so
`ResourcesDep`-dependent routes stop 500ing whenever no earlier test in the
same process happened to set that global first.

**Architecture:** No design change. `ResourcesDep` (`server/resources.py`,
Plan 0039) and `OwnerUnlockServiceDep` (`server/dependencies.py`, Plan 0040)
both read `request.app.state.resources`, which only the real lifespan or a
test fixture populates. The shared synchronous `tests/conftest.py::client`
fixture, and two of seven files using a hand-rolled async client
(`test_chat_endpoint.py`, `test_face_authenticated_turn.py`), already assign
a lightweight `AppResources` themselves. Four sibling files never adopted
that pattern and instead rely on `app.state.resources` already being set as
a leftover side effect of whichever test — in any file, in the same
process — happened to run first. Bring the four in line with the two correct
ones; no new pattern.

**Tech Stack:** pytest, pytest-asyncio, httpx `ASGITransport`/`AsyncClient`.

**Spec:** Finding from Plan 0042 Task 2 (`docs/plans/completed/` once 0042
closes) — the deterministic gate `just test` fails non-deterministically
depending on `pytest-xdist` worker scheduling.

## Finding (evidence, recorded once, not repeated in Task 1)

Running the full suite (`just test`, `-n auto`) surfaced 16 failures, all
`AttributeError: 'State' object has no attribute 'resources'`, in three
files. Running each candidate file in isolation is what actually determines
truth here — `just test`'s xdist scheduling makes a file's pass/fail
non-deterministic depending on which other file's lifespan-setting test
happened to run first **in the same worker process**:

| File | Isolated run | Root cause |
|---|---|---|
| `tests/integration/test_owner_authenticated_stream.py` | 6 fail | `_client()` never sets `app.state.resources`; `/transcribe/stream` also declares its own direct `resources: ResourcesDep` (Plan 0039's shared httpx client), never overridden |
| `tests/integration/test_owner_authenticated_turn.py` | 8 fail | same `_client()` gap; hits `/chat` and `/transcribe`, both declaring `resources: ResourcesDep` directly |
| `tests/integration/test_owner_face_enrollment.py` | 2 fail | same `_client()` gap; the two failing tests are exactly the ones that never call `monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, ...)`, so the real `get_owner_unlock_service(resources: ResourcesDep)` resolves and needs the state that was never set |
| `tests/integration/test_household_authorization_runtime.py` | 1 fail (its only test) | same `_client()` gap; hits `/chat` |

All four in isolation: **17 failed, 14 passed**. Confirmed NOT broken (already
correct, or structurally exempt):

- `tests/integration/test_chat_endpoint.py` — `_client()` already assigns
  `app.state.resources = AppResources(...)` (Plan 0039/0040 pattern).
- `tests/integration/test_face_authenticated_turn.py` — same, already correct.
- `tests/integration/test_owner_unlock_endpoint.py` — `/auth/owner/unlock`
  has no separate `resources: ResourcesDep` parameter of its own, and every
  test overrides `get_owner_unlock_service` directly via
  `app.dependency_overrides`, so `get_resources` is never reached.

CI's own `pytest -m "not slow and not hardware and not eval" ...` (no
`-n auto`, single process, `.github/workflows/ci.yml:129`) has stayed green
only because collection order happens to run a lifespan-setting test before
these four files in that single process — an accident of ordering, not
evidence the four files work. `just test`'s `-n auto` exposed it because
`pytest-xdist` does not guarantee which files land in the same worker.

## Non-goals

- No new shared fixture/abstraction for async test clients — direct parity
  with the two already-correct files is the smallest fix; do not invent a
  fixture only these four would use pending a real third occurrence.
- No change to `server/resources.py`, `server/dependencies.py`, or any
  router — this is a test-only gap, not a production defect.
- No change to what each test asserts — only how its client is constructed.

## Permitted files

- `tests/integration/test_owner_authenticated_stream.py`
- `tests/integration/test_owner_authenticated_turn.py`
- `tests/integration/test_owner_face_enrollment.py`
- `tests/integration/test_household_authorization_runtime.py`
- Documentation execution notes inside this plan only

No production code, no other test file.

## Task 1: RED — prove the gap under `-n0` in isolation

- [x] Confirmed each of the four files fails in isolation with
  `AttributeError`, 17 failures total (6 + 8 + 2 + 1); no new test written —
  the existing tests are the RED, per `superpowers:test-driven-development`'s
  existing-code exception (fixing a fixture, not adding a behavior).

## Task 2: Fix — match the correct sibling pattern

- [x] Each of the four files' `_client()` (and `test_owner_face_enrollment.py`'s
  two client helpers, `_loopback_client`/`_remote_client`) now opens a real
  `httpx.AsyncClient()` and assigns `app.state.resources = AppResources(...)`
  before constructing the `ASGITransport`, exactly matching
  `test_chat_endpoint.py`/`test_face_authenticated_turn.py`'s existing shape.
- [x] Imported `AppResources` (from `server.resources`) and
  `owner_unlock_service` (from `server.cognition.owner_authentication`) in
  each file, reusing the import already present where one file already had
  it (`OwnerUnlockService` class import stayed; the module-level singleton
  instance was the missing piece).

## Task 3: Verify

- [x] Each of the four files alone (`-n0`): 6 + 8 + 16 + 1 passed, 0 failures.
- [x] All four together alone (`-n0`): 31 passed, 0 failures.
- [x] `just test` (`-n auto`, full suite): **1068 passed**, run twice
  back-to-back, 0 failures both times.
- [x] `just lint`, `just typecheck` (mypy 92 files + pyright), `git diff --check`
  — all clean.

## Rollback

Test-only change, no wire or schema impact. Revert the PR; no data migration.

## Completion criteria

- All four files pass both in isolation and inside the full `-n auto` suite,
  twice in a row.
- No test's assertions changed — only client construction.
- `just lint`, `just typecheck`, `just test` all pass.
- Plan 0042 is unblocked to re-run its Task 2 gate.

## Execution notes

Executed 2026-09-03 on branch `feat/0045-async-test-client-resources-parity`,
discovered mid-execution of Plan 0042's own Task 2 gate.

### The real scope was 4 files, not the 3 the first `just test` run showed

The initial `just test` (`-n auto`) run reported 16 failures across 3 files.
Before writing this plan, `rg -n "ASGITransport\(app=app"` across `tests/`
found **7** files using the hand-rolled pattern, not 3 — so each of the
remaining 4 was checked in isolation individually. Two
(`test_chat_endpoint.py`, `test_face_authenticated_turn.py`) were already
correct. One (`test_owner_unlock_endpoint.py`) is structurally exempt — its
only route has no separate `resources: ResourcesDep` of its own, and every
test overrides `get_owner_unlock_service` directly. The fourth
(`test_household_authorization_runtime.py`) failed in isolation (1/1) despite
passing in the original `just test` run — proof the bug is genuinely
non-deterministic under `pytest-xdist`, not just under-sampled. Isolating
each candidate file individually, rather than trusting one `-n auto` run's
pass/fail list, is what caught it.

### Two distinct sub-causes, one shared fix

1. Tests that deliberately never call
   `monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, ...)`
   (the "no token" negative-path tests) still trigger FastAPI's eager
   dependency resolution for `owner_unlock_service: OwnerUnlockServiceDep`,
   which internally needs `resources: ResourcesDep` — the request 500s
   before the endpoint body's own "no token" check ever runs.
2. `transcribe.py` (`/transcribe`, `/transcribe/stream`) and `chat.py`
   (`/chat`) each declare their own **separate** `resources: ResourcesDep`
   parameter (Plan 0039's shared httpx client) — never in scope for Plan
   0040's `get_owner_unlock_service` override migration, and never
   overridden by any of the four files.

Both collapse to the same fix: give `app.state.resources` a real value up
front, matching what the two already-correct sibling files do — no need to
distinguish the two causes at the fixture level.

### Why CI stayed green

`.github/workflows/ci.yml`'s `pytest -m "not slow and not hardware and not eval"`
step runs single-process, no `-n auto`. Collection order in that single
process happens to run a lifespan-setting test (the `client` fixture from
`tests/conftest.py`, or one of the two already-correct files) before these
four — leaving `app.state.resources` populated as a global leftover by
accident. `pytest-xdist`'s worker assignment carries no such guarantee,
which is exactly what turned this from "always green in CI" into "16-17
failures" the moment `just test`'s full `-n auto` run was actually executed
as part of Plan 0042's own gate.

### Verification

- `just test` — **1068 passed**, run twice back to back, 0 failures both
  times.
- Each of the four files alone (`-n0`): 6 + 8 + 16 + 1 passed.
- All four together (`-n0`): 31 passed.
- `just lint` — clean. `just typecheck` — mypy (92 files) and pyright, 0
  errors. `git diff --check` — clean, test-only diff.
- No production code touched; no test assertion changed — only how each
  file's async client is constructed.

## Closure

Merged as PR #113. Test-only fix, authored and closed in one coordinated
commit boundary — the plan was discovered, written, implemented, and
verified inside the same sitting, so there is no separate open-plan
authorization step to record. Plan 0042 is unblocked to re-run its Task 2
gate once Pipec re-authorizes continuing it.
