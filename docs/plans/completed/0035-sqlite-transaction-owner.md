# SQLite Transaction Owner Implementation Plan

> **Status:** Completed 2026-09-02. Historical evidence only — this document
> is not an instruction and authorizes nothing.

**Goal:** Introduce one safe runtime transaction primitive without yet
migrating every repository write.

**Architecture:** One async lock protects a complete runtime write transaction.
Composite operations accept the active connection so nested transactions are
unnecessary. Startup migrations remain explicitly separate.

**Tech Stack:** Python 3.12, asyncio, aiosqlite, pytest.

**Spec:** Accepted ADR
[0011](../../adr/0011-sqlite-transaction-ownership.md).

## Permitted files

- `server/src/server/db.py`
- New focused unit/integration DB transaction tests
- Documentation execution notes inside this plan only

No repository write path, schema, migration, retention behavior, or outbox
call changes in this plan.

## Interfaces

```python
@asynccontextmanager
async def transaction() -> AsyncIterator[aiosqlite.Connection]: ...
```

The primitive executes `BEGIN IMMEDIATE`, yields the connection, commits only
on normal exit, and rolls back on `BaseException` before re-raising. It is not
reentrant; callers composing writes pass the yielded connection downward.

## Task 1: Freeze the inventory

- [x] Recorded every current hit from:

  ```powershell
  rg -n "\.commit\(|\.rollback\(|BEGIN( IMMEDIATE| TRANSACTION)?|get_conn\(" server/src/server
  ```

  ~140 hits across 15 files. Read every call site (not just the grep line) to
  classify correctly — several files import `get_conn` for read-only queries
  and only some of their functions write.

- [x] Classified each hit as startup migration, runtime repository write,
  retention, offline script support, or read-only access.

  | File | Category | Notes |
  |---|---|---|
  | `db.py` | startup migration | `open_db` (pragmas + one commit), `run_migrations` (one `executescript` + commit per pending version). `get_conn` is the read-only accessor every other file calls. |
  | `memory/biometric_consent.py` | runtime write | `grant_face_consent` commits with no explicit `BEGIN`; `revoke_face_consent` already uses `BEGIN IMMEDIATE`/commit/rollback across three statements. `has_active_face_consent` is read-only. |
  | `memory/declarative.py` | runtime write | `upsert_entity` and `assert_fact` each commit, then call `write_outbox` in a **second**, unrelated commit — not atomic today. No `BEGIN IMMEDIATE`. Lookup helpers are read-only. |
  | `memory/embeddings.py` | runtime write | Cache insert + commit inside `embed()`; the SELECT-then-maybe-INSERT is not currently atomic. |
  | `memory/entity_labels.py` | read-only | `get_person_label` only. |
  | `memory/household_authorization.py` | runtime write | `bootstrap_initial_owner` and `assign_household_role` use `BEGIN IMMEDIATE`/commit/rollback around an INSERT plus an audit-event insert. `revoke_active_role` commits with no `BEGIN`, and calls `.rollback()` on its not-found path with no transaction open — a pre-existing oddity, left untouched; 0036 owns repository behavior. Every `_entity_type`/`_active_owner_exists`/`_get_assignment`/`get_active_role` helper is read-only. |
  | `memory/legacy_v4_migration.py` | offline script support | Only imported by `scripts/migrate_memory_v4.py` — never by a router or any runtime path. `_write_decision` already runs one `BEGIN IMMEDIATE` around a record plus its migration-ledger row, composing `relational_v4.py`'s writers via their existing `manage_transaction=False` flag. |
  | `memory/meta.py` | runtime write | `set_flag` commits (upsert). `get_flag` is read-only. |
  | `memory/outbox.py` | runtime write | `write_outbox` commits alone, decoupled from the mutation it logs (see `declarative.py`). The baseline architecture doc marks the outbox itself for removal in Plan 0036 — not touched here. |
  | `memory/owner_credentials.py` | runtime write | `save_owner_pin_credential` uses `BEGIN IMMEDIATE`/commit/rollback. `revoke_owner_pin_credential` commits with no `BEGIN` and has the same rollback-without-a-transaction shape as `revoke_active_role`. `get_active_owner_pin_credential` is read-only. |
  | `memory/relational_v4.py` | runtime write | `assert_literal_fact` and `assert_entity_relation` both take `manage_transaction: bool = True` and only issue `BEGIN IMMEDIATE`/commit/rollback when it is true — an existing, working precedent for composability, done with a boolean flag rather than by passing the active connection. 0036 decides whether to keep the flag or move to the plan's connection-passing shape. Every `get_*` accessor is read-only. |
  | `memory/relations.py` | read-only | `find_facts_by_predicate`, `load_entity_by_id`. |
  | `memory/retention.py` | retention | `_run_once` issues four `DELETE`s and one commit inside a caught-and-logged `try`; never re-raises, by design (a failing purge must not crash the background loop). |
  | `memory/semantic.py` | runtime write | `store_memory` commits two related INSERTs (`memories` + `vec_memories`) together — already the pattern this plan wants. `search_memories` commits a trailing access-count `UPDATE` — a side-effecting read, not pure. |
  | `personal_setup.py` | offline script support | `main()`/`_run()` are the sole entrypoint, invoked only by `scripts/onboard.py`; never imported by `server/src/server/routers/` or `main.py`. `check_db_available` issues `BEGIN IMMEDIATE` then a literal `"ROLLBACK"` as a non-blocking lock probe, not a real write. Its own module docstring already states "Each repository keeps its own transaction; this module does not wrap them in a second outer transaction" — an existing convention already compatible with this plan's non-reentrant design. |
  | `vision/faces.py` | runtime write | `enroll_face` commits two related INSERTs (`face_profiles` + `vec_faces`) with no `BEGIN IMMEDIATE` — same non-atomic shape as `declarative.py`. `match_face` is read-only. |
  | `vision/perception.py` | runtime write | `_record_unknown_face` commits one INSERT inside a caught-and-logged `try`, best-effort by design — same non-crashing philosophy as retention. |

  No hit was left unclassified.

## Task 2: Write RED transaction tests

- [x] Against a temporary real SQLite DB, proved normal exit commits, exception
  rolls back, cancellation rolls back, and the lock covers the entire yielded
  interval.
- [x] Used two controlled coroutines to prove the second `BEGIN` cannot enter
  until the first owner exits.
- [x] Proved a helper accepting the yielded connection can issue multiple
  statements without reacquiring the lock.
- [x] Also proved (beyond the plan's list, directly required by the
  Interfaces section's "not reentrant"): calling `transaction()` again from
  inside an open one on the same task hangs, not just misbehaves.
- [x] Observed RED before `transaction()` existed — see execution notes for a
  hazard found in the RED tests themselves.

## Task 3: Implement the primitive

- [x] Added the module-owned async lock and transaction context manager.
- [x] Configured `PRAGMA busy_timeout = 5000` when opening the connection —
  see execution notes: this was already the effective value.
- [x] Kept migration ownership unchanged and documented in code; startup
  migrations do not touch the runtime lock in this plan.
- [x] `close_db()` cannot leave the module pointing at a closed connection —
  already true before this plan; also resets the lock now (see notes).

## Task 4: Verify

- [x] Ran:

  ```powershell
  uv run pytest -n0 tests/integration/test_db_transaction.py tests/integration/test_db.py -q
  just lint
  just typecheck
  just test
  git diff --check
  ```

## Rollback

The primitive is unused by production repositories at this boundary. Revert
the PR with no data/schema rollback.

## Completion criteria

- Transaction commit, exception, cancellation, and concurrency semantics are
  covered by real SQLite tests.
- Existing repositories behave identically because migration belongs to 0036.
- Independent review approves the inventory and nested-transaction contract.

## Execution notes

Executed 2026-09-02 on branch `feat/0035-sqlite-transaction-owner`, test-first
throughout: every one of the 13 new tests was watched failing against real
code before any production line changed.

### The lock's own design was wrong, and only a real event loop caught it

The concurrency test passed alone but failed when run after another test in
the same file:

```text
RuntimeError: <asyncio.locks.Lock object at 0x...> is bound to a different event loop
```

`_write_lock = asyncio.Lock()` was created once at module-import time. An
`asyncio.Lock` binds to whichever event loop is running the first time it is
actually awaited — and pytest-asyncio gives every test function its own loop.
The first test to use the lock bound it to loop A; the next test's loop B
then crashed trying to reuse it. In production this is a non-issue (one
process, one Uvicorn event loop, for the whole server lifetime) — but the
design was still wrong: the lock's lifecycle was independent of the
connection's, when it should track it exactly.

Fixed by owning the lock the same way `_conn` already is: `_write_lock:
asyncio.Lock | None = None` at module scope, created inside `open_db()`
right after the connection opens, and reset to `None` in `close_db()`. This
is also the correct production semantics, not just a test fix — the lock's
job is to guard the connection, so it should be born and die with it.

### Two coroutines is not proof by itself — it has to be a barrier proof

The first version of the lock-contention test just asserted
`order.index("second-entered") > order.index("first-exited")`. That is weak:
it would also pass if the lock simply happened to be fast rather than
genuinely exclusive. Rewritten as a real barrier: the test polls (bounded, no
sleep-based timing assumption) until `second()` has provably reached the
lock and is blocked there, asserts it has **not** entered yet, only then
releases the first transaction, and checks the **exact** resulting order —
not just a relative comparison.

### A hazard in the RED tests themselves, not in `db.py`

Before `transaction()` existed, `db.transaction()` raised `AttributeError`
synchronously inside a spawned task. Two tests (`test_cancellation_rolls_back`
and the concurrency test) had the main test coroutine `await` an
`asyncio.Event` that only the crashed task was supposed to set — with no
timeout. The very first full-file RED run hung for over two minutes with zero
output instead of failing fast. Every cross-task `Event.wait()` in this file
now goes through `asyncio.wait_for(..., timeout=_GUARD_TIMEOUT_S)`, so a
genuine future regression fails in seconds with a clear message instead of
hanging the suite.

### `busy_timeout` was already 5000 — the RED case doesn't exist

Probed the value on a fresh connection before touching `db.py`: `PRAGMA
busy_timeout` already reported `5000`, not SQLite's own documented default of
`0`. Python's stdlib `sqlite3.connect()` defaults `timeout=5.0` seconds, which
`aiosqlite` inherits, and that already issues the equivalent
`sqlite3_busy_timeout()` call. A black-box test asserting `busy_timeout ==
5000` before and after the change would pass in both cases — a test with no
power to fail, and therefore not a real test (see
`superpowers:test-driven-development`'s "name the break" rule). Set the
`PRAGMA` explicitly anyway, not for behavior but so the value is a decision
visible in `db.py`, not an implicit stdlib default an unrelated future change
could silently move.

### `close_db()`'s own completion criterion was already met

"Ensure `close_db()` cannot leave the module pointing at a closed connection"
was already true before this plan — it unconditionally sets `_conn = None`
after closing. `test_close_db_leaves_get_conn_raising` in the new `test_db.py`
locks this down directly; `close_db()` additionally resets `_write_lock =
None` now, matching the lock's new connection-scoped lifecycle.

### Filled a real, pre-existing test gap

`open_db`, `close_db`, `get_conn`, and `run_migrations` had no direct tests —
every existing test only exercised them indirectly as setup/teardown for some
other module's fixture. `tests/integration/test_db.py` closes that gap for
the one production file this plan is allowed to touch: idempotency of open
and close, `get_conn` raising before open and after close, and
`run_migrations` reaching and holding the latest schema version. All seven
passed immediately, since none of this behavior changed — closing an
untested gap, not chasing a regression.

### Verification

- `just test` — **1000 passed** (987 before, 13 added)
- `just lint` — clean
- `just typecheck` — mypy (91 files) and pyright, 0 errors
- `just audit` — Ruff S and pip-audit, no known vulnerabilities
- Real acceptance: not applicable — the primitive is unused by any production
  repository at this boundary (Plan 0036 migrates callers). No voice-path
  behavior changes, so no `just run-server` / `just run-robot` turn is
  required to close this plan. Pipec confirmed this explicitly, rather than
  the step being silently skipped.

## Closure

Merged as PR #99 (`8c1a975`). No real-runtime acceptance applies, by design —
confirmed above. The capsule's next child is Plan 0036, which migrates
repositories onto this primitive. Closing this plan does not authorize it.
