# SQLite Write Migration and Outbox Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:test-driven-development` and
> `superpowers:verification-before-completion`.

**Goal:** Move every runtime SQLite write under the transaction owner from
Plan 0035 and remove unused outbox runtime writes.

**Architecture:** Repository functions either own `transaction()` or accept an
explicit active `aiosqlite.Connection` for composition. No nested transaction
acquisition is permitted.

**Tech Stack:** asyncio, aiosqlite, pytest.

**Spec:** Accepted ADR
[0011](../../adr/0011-sqlite-transaction-ownership.md).

## Permitted files

- `server/src/server/memory/` modules identified by Plan 0035's inventory
- `server/src/server/vision/faces.py` and `vision/perception.py` only when the
  inventory proves runtime writes
- `server/src/server/personal_setup.py` only for explicit transaction
  composition
- `server/src/server/db.py` only for a defect proven while migrating
- Corresponding unit/integration tests

No schema redesign, SQLAlchemy, connection pool, new outbox consumer, or
automatic destructive migration is allowed.

## Task 1: Add cross-repository concurrency RED tests

- [x] Use a temporary DB and controlled `asyncio.gather()` to overlap
  representative declarative/semantic/credential writes with retention.
- [x] Assert no `cannot start a transaction within a transaction`, no foreign
  commit, and all successful logical operations are complete.
- [x] Add rollback tests for every composite write selected by the inventory.
- [x] Observe at least one RED failure or demonstrate with deterministic hooks
  that the old implementation permits interleaving; do not rely on a flaky
  stress loop.

## Task 2: Migrate write owners in reviewable groups

- [x] Group A: owner credentials, biometric consent, faces/perception.
- [x] Group B: declarative, semantic, relational/household authorization.
- [x] Group C: retention and offline/personal setup composition.
- [x] For each group: add focused RED, migrate minimal code, observe GREEN,
  run that group's existing integration tests, and create a separate commit.
- [x] Functions called inside a broader unit accept a keyword-only active
  connection and do not commit it.

## Task 3: Remove outbox runtime behavior

- [x] Confirm again that no runtime reader/consumer exists:

  ```powershell
  rg -n "outbox|write_outbox" server/src robot/src scripts tests
  ```

- [x] Remove calls and the runtime writer module when no remaining import
  requires it. Preserve historical migration/table creation unless a separate
  forward-only migration is demonstrably safer.
- [x] Update tests to assert domain mutation no longer creates unused outbox
  rows; do not add a replacement queue.

## Task 4: Prove ownership closure

- [x] Run:

  ```powershell
  rg -n "\.commit\(|\.rollback\(|BEGIN( IMMEDIATE| TRANSACTION)?" server/src/server
  ```

- [x] Expected: transaction control exists only in `db.py` and classified
  startup/offline migration code. Every exception must carry a code comment
  and test proving exclusive ownership.
- [x] Run `just lint`, `just typecheck`, `just test`, `just audit`, and
  `git diff --check`.

## Rollback

Commits are grouped by repository family. Revert the failing family without
reverting the transaction primitive. No schema/table deletion occurs, so old
code remains able to read the database after rollback.

## Completion criteria

- Deterministic concurrent writes pass.
- Runtime repositories do not commit or roll back outside `db.py`.
- Retention follows the same discipline.
- No runtime outbox writer/import/call remains.
- Existing migration and household-memory tests pass.

## Execution notes

Executed 2026-09-02 on branch `feat/0036-sqlite-write-migration-and-outbox-removal`,
test-first throughout.

### Task 1's concurrency proof found a worse bug than the one it went looking for

The first deterministic test (`assign_household_role` paused mid-transaction,
`save_owner_pin_credential` started concurrently) reproduced the expected
`sqlite3.OperationalError: cannot start a transaction within a transaction` —
confirmed RED for the documented reason.

A second test went looking for the same collision between a Group A write
(`vision.faces.enroll_face`, no `BEGIN IMMEDIATE` of its own) and a paused
`assign_household_role`. It found something worse: `enroll_face`'s own bare
`conn.commit()` — issued while `assign_household_role`'s transaction was still
open on the one shared connection — committed *that* transaction too, early
and out from under its owner. When `assign_household_role` then hit its
(simulated) failure and called `conn.rollback()`, there was nothing left open
to roll back: the supposedly-failed role assignment silently survived. Not a
loud crash — a silent correctness bug, worse than the loud
`OperationalError` case. Both tests live in
`tests/integration/test_sqlite_concurrent_writes.py`; the second now asserts
real isolation (the failed write rolls back, the unrelated write still
succeeds on its own) now that both sides route through `db.transaction()`.

### The deterministic pause pattern needed one more trick to stay deterministic

Pausing `assign_household_role` mid-transaction via a monkeypatched
`_record_event` was the same technique Plan 0035 established. Making the
*second* actor's timing deterministic too (so the test never depends on
`asyncio.sleep(0)` guessing right) required one more step for
`save_owner_pin_credential`: it calls `get_active_role` — a real SELECT
round-trip through aiosqlite's background thread — before its own
`BEGIN IMMEDIATE`. Stubbing that check to return synchronously (no `await`
inside the stub, so the coroutine never yields) makes `BEGIN IMMEDIATE` the
second actor's first genuine suspension point, so `asyncio.create_task(...)`
followed by one `await asyncio.sleep(0)` deterministically gets it there
before the test releases the first actor — no timing race, per the plan's
"do not rely on a flaky stress loop" instruction.

### `test_sensitive_logging.py` and `test_embeddings.py` needed real DBs, and that surfaced a second finding

Both files mocked `get_conn()` directly with a hand-rolled fake connection.
`db.transaction()` needs the module's real `_conn`/`_write_lock` state (set
by `open_db()`), so a bare `get_conn()` mock no longer reaches far enough —
both were rewritten onto the same real-temporary-DB fixture pattern already
used everywhere else in this migration (`test_db.py`, Group A/B/C's own
tests). `test_embed_accepts_correct_dimension_vector` moved from `unit` to
`integration` accordingly, matching the marker's own stated meaning.

Using a real DB then surfaced something the old mocks had been hiding:
`aiosqlite`'s own logger echoes every bound SQL parameter — including a
person's name — at `DEBUG`. `caplog.at_level(logging.DEBUG)` with no logger
filter was capturing that too, failing
`test_storing_an_entity_never_logs_its_name` and
`test_enrolling_a_face_never_logs_the_persons_name` for a reason unrelated to
what either test claims to verify. Fixed by scoping `caplog.at_level` to each
test's own named logger (`server.memory.declarative`,
`server.vision.faces`), matching what each test's docstring already claimed
to check. Left as a documented, out-of-scope finding: if DEBUG logging is
ever enabled in production, `aiosqlite`'s own tracer is a real privacy
surface Plan 0032 did not cover and this plan does not touch.

### `embeddings.py`'s cache write deliberately does not hold the lock across the network call

`embed()`'s SELECT-then-maybe-INSERT cache race was in Plan 0035's inventory
as "not atomic today." Wrapping the whole function (including the Ollama HTTP
round-trip between the SELECT and the INSERT) in `db.transaction()` would
have serialized every other write in the app behind one embedding request —
a bad regression traded for a race that `INSERT OR REPLACE` already makes
harmless (idempotent, at worst a redundant Ollama call). Only the final
INSERT is inside `db.transaction()`; the comment in `embeddings.py` records
why.

### Two deliberate, permanent exceptions to Task 4's ownership grep

- `personal_setup.py`'s `check_db_available` — a lock **probe**, not a write:
  `BEGIN IMMEDIATE` then an unconditional `ROLLBACK`, bypassing
  `db.transaction()`'s asyncio lock on purpose so it can detect an
  *external* OS-level lock (another `just run-server` process) that a
  coroutine-level lock cannot see. Two new tests in `test_personal_setup.py`
  prove it: silent when nothing holds the lock, and — by holding a real
  `db.transaction()` open in a concurrent task — raises `BrainMemoryError`
  when something does, even a lock held by this same process.
- `legacy_v4_migration.py` — offline script support for
  `scripts/migrate_memory_v4.py` only, composing `relational_v4.py`'s
  `assert_literal_fact`/`assert_entity_relation` via their existing
  `manage_transaction=False` parameter inside its own `BEGIN IMMEDIATE`.
  Untouched by this plan; `relational_v4.py`'s `manage_transaction=True`
  branch (the runtime default) now routes through `db.transaction()`, and the
  `False` branch still composes exactly as before.

### Verification

- `just lint` — clean
- `just typecheck` — mypy (90 files — one fewer than Plan 0035's 91, since
  `outbox.py` is now deleted) and pyright, 0 errors
- `just test` — full suite (`not slow`), all passing after the two fixes above
- `just audit` — Ruff `S` and pip-audit, no known vulnerabilities
- Real acceptance: pending — this plan touches every runtime write path used
  by the live voice/auth flow (owner PIN, face consent, entity/fact storage,
  memory), so a `just run-server` + `just run-robot` turn from Pipec is
  required before this plan closes.
