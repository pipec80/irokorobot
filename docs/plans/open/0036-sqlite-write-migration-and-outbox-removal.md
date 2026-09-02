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

- [ ] Use a temporary DB and controlled `asyncio.gather()` to overlap
  representative declarative/semantic/credential writes with retention.
- [ ] Assert no `cannot start a transaction within a transaction`, no foreign
  commit, and all successful logical operations are complete.
- [ ] Add rollback tests for every composite write selected by the inventory.
- [ ] Observe at least one RED failure or demonstrate with deterministic hooks
  that the old implementation permits interleaving; do not rely on a flaky
  stress loop.

## Task 2: Migrate write owners in reviewable groups

- [ ] Group A: owner credentials, biometric consent, faces/perception.
- [ ] Group B: declarative, semantic, relational/household authorization.
- [ ] Group C: retention and offline/personal setup composition.
- [ ] For each group: add focused RED, migrate minimal code, observe GREEN,
  run that group's existing integration tests, and create a separate commit.
- [ ] Functions called inside a broader unit accept a keyword-only active
  connection and do not commit it.

## Task 3: Remove outbox runtime behavior

- [ ] Confirm again that no runtime reader/consumer exists:

  ```powershell
  rg -n "outbox|write_outbox" server/src robot/src scripts tests
  ```

- [ ] Remove calls and the runtime writer module when no remaining import
  requires it. Preserve historical migration/table creation unless a separate
  forward-only migration is demonstrably safer.
- [ ] Update tests to assert domain mutation no longer creates unused outbox
  rows; do not add a replacement queue.

## Task 4: Prove ownership closure

- [ ] Run:

  ```powershell
  rg -n "\.commit\(|\.rollback\(|BEGIN( IMMEDIATE| TRANSACTION)?" server/src/server
  ```

- [ ] Expected: transaction control exists only in `db.py` and classified
  startup/offline migration code. Every exception must carry a code comment
  and test proving exclusive ownership.
- [ ] Run `just lint`, `just typecheck`, `just test`, `just audit`, and
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
