# 0011 — Give each SQLite write transaction one coroutine owner

- **Status:** Accepted
- **Date:** 2026-08-31
- **Accepted:** 2026-09-02

## Context

The server uses one process-global `aiosqlite.Connection`. The driver
serializes individual operations, but it does not keep a multi-await
transaction owned by one coroutine. Runtime repositories, retention, and
migrations currently contain several direct `BEGIN`, `commit`, and `rollback`
paths. The current outbox has no consumer and commits separately from some
domain mutations.

## Decision

Keep SQLite and `aiosqlite`, but introduce one explicit runtime write
transaction boundary. It owns the connection from `BEGIN IMMEDIATE` through
commit or rollback under one async lock. Composite repositories receive the
active connection instead of acquiring a nested transaction.

Migrations remain startup-exclusive. Retention uses the runtime transaction
discipline. Add a finite SQLite `busy_timeout` for external contention.

Remove outbox writes from runtime because no consumer or current product
requirement exists. Preserve historical schema/migrations when destructive
removal would add risk.

## Alternatives considered

- **Rely on aiosqlite's queue:** rejected because it orders statements, not
  transaction ownership across coroutine context switches.
- **Add SQLAlchemy/pooling:** rejected as unnecessary for one local process and
  one SQLite database.
- **Open one connection per repository call:** rejected until measured evidence
  justifies the additional connection/locking complexity.
- **Complete a transactional outbox:** rejected under YAGNI without a consumer.

## Consequences

### Positive

- Commits and rollbacks cannot accidentally include another coroutine's work.
- Failure behavior becomes reproducible and testable.
- Persistence remains small and local-first.

### Negative

- Writes are intentionally serialized.
- Existing repository and migration composition must be inventoried carefully.
- A non-reentrant lock makes nested transactions invalid; interfaces must make
  caller-owned transactions explicit.

## Review

Review if a second process writes the database, write latency becomes a
measured problem, or a real synchronization consumer requires an outbox.
