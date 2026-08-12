"""Local-only operator command for explicit household-role bootstrap."""

from __future__ import annotations

import argparse
import asyncio
import logging

from server.memory.household_authorization import bootstrap_initial_owner

from server import db

logger = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    """Build the local operator command parser without any HTTP surface."""
    parser = argparse.ArgumentParser(description="Manage local Iroko household roles")
    subparsers = parser.add_subparsers(dest="command", required=True)
    bootstrap = subparsers.add_parser("bootstrap-owner", help="Set the sole initial owner")
    bootstrap.add_argument("--person-id", type=int, required=True)
    bootstrap.add_argument("--confirm-person-id", type=int, required=True)
    return parser


async def _bootstrap_owner(person_id: int, confirm_person_id: int) -> None:
    """Run one explicit local initial-owner bootstrap against the configured DB."""
    await db.open_db()
    try:
        await db.run_migrations()
        assignment = await bootstrap_initial_owner(
            person_entity_id=person_id,
            confirmed_person_entity_id=confirm_person_id,
        )
        logger.info(
            "Initial household owner assignment created: entity_id=%d", assignment.person_entity_id
        )
    finally:
        await db.close_db()


def main() -> None:
    """Parse one local command and execute its explicit role operation."""
    args = _parser().parse_args()
    if args.command == "bootstrap-owner":
        asyncio.run(_bootstrap_owner(args.person_id, args.confirm_person_id))


if __name__ == "__main__":
    main()
