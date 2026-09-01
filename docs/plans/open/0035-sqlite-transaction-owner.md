# SQLite Transaction Owner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:test-driven-development` and
> `superpowers:verification-before-completion`.

**Goal:** Introduce one safe runtime transaction primitive without yet
migrating every repository write.

**Architecture:** One async lock protects a complete runtime write transaction.
Composite operations accept the active connection so nested transactions are
unnecessary. Startup migrations remain explicitly separate.

**Tech Stack:** Python 3.12, asyncio, aiosqlite, pytest.

**Spec:** Proposed ADR
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

- [ ] Record every current hit from:

  ```powershell
  rg -n "\.commit\(|\.rollback\(|BEGIN( IMMEDIATE| TRANSACTION)?|get_conn\(" server/src/server
  ```

- [ ] Classify each hit as startup migration, runtime repository write,
  retention, offline script support, or read-only access. A missing
  classification blocks implementation.

## Task 2: Write RED transaction tests

- [ ] Against a temporary real SQLite DB, prove normal exit commits, exception
  rolls back, cancellation rolls back, and the lock covers the entire yielded
  interval.
- [ ] Use two controlled coroutines to prove the second `BEGIN` cannot enter
  until the first owner exits.
- [ ] Prove a helper accepting the yielded connection can issue multiple
  statements without reacquiring the lock.
- [ ] Observe RED before `transaction()` exists.

## Task 3: Implement the primitive

- [ ] Add the module-owned async lock and transaction context manager.
- [ ] Configure `PRAGMA busy_timeout = 5000` when opening the connection.
- [ ] Keep migration ownership unchanged and documented in code; do not wrap
  startup migrations in the runtime lock in this plan.
- [ ] Ensure `close_db()` cannot leave the module pointing at a closed
  connection.

## Task 4: Verify

- [ ] Run:

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
