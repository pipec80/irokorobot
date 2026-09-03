"""Integration tests for `db.transaction()` against a real temporary SQLite DB.

No mocks: every test opens the real `aiosqlite` connection through
`db.open_db()` + `db.run_migrations()`, exactly like production, and writes
through the real `meta` key/value table (migration 002) rather than inventing
test-only schema.
"""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest
from server.settings import settings

from server import db

# Guards every cross-task `Event.wait()` below. Without a bound, a coroutine
# that crashes before signaling (for instance `db.transaction()` raising
# `AttributeError` before it exists) leaves the waiter suspended forever
# instead of failing the test — this turned an early RED run into a hang.
_GUARD_TIMEOUT_S = 5.0


@pytest.fixture
async def real_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Path]:
    """Open a fresh temporary real SQLite DB with the full app schema applied."""
    db_path = tmp_path / "transaction-test.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield db_path
    await db.close_db()
    db._conn = None


async def _meta_value(key: str) -> str | None:
    """Read one `meta` row through the module connection, bypassing any transaction."""
    cursor = await db.get_conn().execute("SELECT value FROM meta WHERE key = ?", (key,))
    row = await cursor.fetchone()
    await cursor.close()
    return str(row[0]) if row is not None else None


@pytest.mark.integration
async def test_normal_exit_commits(real_db: Path) -> None:
    """A transaction that exits normally must persist its writes."""
    async with db.transaction() as conn:
        await conn.execute("INSERT INTO meta (key, value) VALUES (?, ?)", ("t1", "committed"))

    assert await _meta_value("t1") == "committed"


async def _write_then_raise() -> None:
    """Write inside an open transaction, then blow it up before it can exit."""
    async with db.transaction() as conn:
        await conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?)", ("t2", "should-not-persist")
        )
        raise RuntimeError("simulated failure mid-transaction")


@pytest.mark.integration
async def test_exception_rolls_back(real_db: Path) -> None:
    """A transaction that raises must leave no trace of its writes."""
    with pytest.raises(RuntimeError, match="simulated failure"):
        await _write_then_raise()

    assert await _meta_value("t2") is None


@pytest.mark.integration
async def test_cancellation_rolls_back(real_db: Path) -> None:
    """A cancelled transaction must leave no trace of its writes either.

    Cancellation delivers `asyncio.CancelledError` at the next await point —
    a plain `except Exception` would miss it, since `CancelledError` derives
    from `BaseException`. The primitive must catch that too.
    """
    started = asyncio.Event()
    never_set = asyncio.Event()

    async def doomed_write() -> None:
        async with db.transaction() as conn:
            await conn.execute("INSERT INTO meta (key, value) VALUES (?, ?)", ("t3", "cancelled"))
            started.set()
            await never_set.wait()  # suspended here when cancelled

    task = asyncio.create_task(doomed_write())
    await asyncio.wait_for(started.wait(), timeout=_GUARD_TIMEOUT_S)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert await _meta_value("t3") is None


@pytest.mark.integration
async def test_a_second_transaction_waits_for_the_first_to_release_the_lock(
    real_db: Path,
) -> None:
    """The lock must cover the whole yielded interval, not just `BEGIN`.

    Two coroutines. The first opens a transaction and holds it open past its
    own write. The second must not even begin executing its own transaction
    body until the first has fully exited (committed and released the lock).
    """
    order: list[str] = []
    first_holds = asyncio.Event()
    first_may_finish = asyncio.Event()

    async def first() -> None:
        async with db.transaction() as conn:
            order.append("first-entered")
            await conn.execute("INSERT INTO meta (key, value) VALUES (?, ?)", ("t4", "first"))
            first_holds.set()
            await first_may_finish.wait()
        order.append("first-exited")

    async def second() -> None:
        await first_holds.wait()
        order.append("second-waiting")
        async with db.transaction() as conn:
            order.append("second-entered")
            await conn.execute("INSERT INTO meta (key, value) VALUES (?, ?)", ("t5", "second"))
        order.append("second-exited")

    first_task = asyncio.create_task(first())
    second_task = asyncio.create_task(second())

    await asyncio.wait_for(first_holds.wait(), timeout=_GUARD_TIMEOUT_S)
    for _ in range(50):
        if "second-waiting" in order:
            break
        await asyncio.sleep(0)
    assert "second-waiting" in order, "second() never reached the lock"
    assert "second-entered" not in order, (
        "second() entered its transaction while the first still held the lock"
    )

    first_may_finish.set()
    await asyncio.wait_for(asyncio.gather(first_task, second_task), timeout=_GUARD_TIMEOUT_S)

    assert order == [
        "first-entered",
        "second-waiting",
        "first-exited",
        "second-entered",
        "second-exited",
    ]
    assert await _meta_value("t4") == "first"
    assert await _meta_value("t5") == "second"


async def _insert_two_rows(conn: aiosqlite.Connection) -> None:
    """Stand in for a composite repository helper accepting the active connection."""
    await conn.execute("INSERT INTO meta (key, value) VALUES (?, ?)", ("t6a", "a"))
    await conn.execute("INSERT INTO meta (key, value) VALUES (?, ?)", ("t6b", "b"))


@pytest.mark.integration
async def test_a_composed_helper_can_issue_multiple_statements_without_reacquiring_the_lock(
    real_db: Path,
) -> None:
    """A helper accepting the yielded connection needs no `transaction()` of its own."""
    async with db.transaction() as conn:
        await _insert_two_rows(conn)

    assert await _meta_value("t6a") == "a"
    assert await _meta_value("t6b") == "b"


@pytest.mark.integration
async def test_nested_transaction_calls_deadlock_by_design(real_db: Path) -> None:
    """The lock is not reentrant — composing writes must pass the connection down.

    Calling `transaction()` again from inside an already-open transaction on
    the same task hangs forever: the module-owned lock has no notion of "the
    same caller". `relational_v4.py`'s `manage_transaction` flag exists
    specifically to avoid this trap (see the Plan 0035 inventory).
    """
    async with db.transaction():
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.2), db.transaction():
                pass
