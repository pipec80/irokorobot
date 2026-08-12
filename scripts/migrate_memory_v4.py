"""Run the local, dry-run-first legacy-fact migration into memory v4."""

from __future__ import annotations

import argparse
import asyncio
import logging

from server.memory.legacy_v4_migration import migrate_active_legacy_facts

from server import db

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    """Parse the explicit local-write acknowledgement."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write deterministic v4 records and local ledger rows. Default: dry run.",
    )
    return parser.parse_args()


async def _run(*, apply: bool) -> None:
    """Open the configured local database and report aggregate migration counts."""
    await db.open_db()
    try:
        await db.run_migrations()
        counts = await migrate_active_legacy_facts(apply=apply)
    finally:
        await db.close_db()
    mode = "apply" if apply else "dry-run"
    logger.info(
        "Memory v4 migration %s: scanned=%d migrated=%d deferred=%d rejected=%d ledger_rows=%d",
        mode,
        counts.scanned,
        counts.migrated,
        counts.deferred,
        counts.rejected,
        counts.ledger_rows_written,
    )


def main() -> None:
    """Execute the local migration command."""
    args = _parse_args()
    asyncio.run(_run(apply=args.apply))


if __name__ == "__main__":
    main()
