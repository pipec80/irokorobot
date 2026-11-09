"""Task 0 (Plan 0080): one row of closed values per turn, read from the server log.

Reads ``logs/server.log`` (JSON lines) and groups the events of each request:
``stt.transcribed`` (characters heard), ``turn.decision`` (need, status, source;
a turn the controller left to the channel is ``generic_conversation``) and
``recall.read`` (route, when, outcome, hits, best distance). Only closed values are kept:
the ``msg`` field and every other free-text field are never read, so the report
cannot carry what anybody said.

Usage:
    uv run python scripts/mvp_session_report.py --since 2026-11-09T10:00:00

Audio contract: this script never touches audio.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import logging
from pathlib import Path
import re
import sys
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

logger = logging.getLogger(__name__)

__all__ = ["TurnRow", "main", "summarize_turns"]

_DEFAULT_LOG: Final = Path("logs/server.log")
_NO_REQUEST: Final = "-"
_GENERIC_NEED: Final = "generic_conversation"
_MISSING_NEED: Final = "none"
_BLANK: Final = "-"
_EVENT_STT: Final = "stt.transcribed"
_EVENT_DECISION: Final = "turn.decision"
_EVENT_RECALL: Final = "recall.read"
_TURN_EVENTS: Final = frozenset({_EVENT_STT, _EVENT_DECISION})
# A closed value is a short lowercase token (enum values, outcomes, routes).
_CLOSED_VALUE: Final = re.compile(r"[a-z0-9_-]{1,48}")


@dataclass(frozen=True)
class TurnRow:
    """The closed values of one turn; never a message text."""

    ts: str
    request_id: str
    stt_chars: int | None
    need: str
    status: str | None
    source: str | None
    recall_outcome: str | None
    recall_hits: int | None
    best_distance: float | None
    recall_route: str | None = None
    when: str | None = None


def _closed(value: object) -> str | None:
    """Return *value* only when it is a short closed token, else ``None``."""
    if isinstance(value, str) and _CLOSED_VALUE.fullmatch(value):
        return value
    return None


def _count(value: object) -> int | None:
    """Return *value* when it is a real integer (not a bool), else ``None``."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _distance(value: object) -> float | None:
    """Return *value* when it is a real number (not a bool), else ``None``."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _parse_time(text: str) -> datetime:
    """Parse an ISO time; a time without offset is read as local time."""
    moment = datetime.fromisoformat(text)
    return moment if moment.tzinfo is not None else moment.astimezone()


def _record(line: str) -> dict[str, object] | None:
    """Return the JSON object of *line*, or ``None`` when it is not one."""
    try:
        payload: object = json.loads(line)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    return {str(key): value for key, value in payload.items()}


def _event_time(record: dict[str, object]) -> tuple[str, datetime] | None:
    """Return the ``ts`` text and its parsed time, or ``None`` when unusable."""
    ts = record.get("ts")
    if not isinstance(ts, str):
        return None
    try:
        return ts, _parse_time(ts)
    except ValueError:
        return None


def _row(request_id: str, ts: str, events: dict[str, dict[str, object]]) -> TurnRow:
    """Build the closed row of one request from its first event of each kind."""
    stt = events.get(_EVENT_STT, {})
    decision = events.get(_EVENT_DECISION, {})
    recall = events.get(_EVENT_RECALL, {})
    need = _closed(decision.get("need"))
    if need is None and decision.get("outcome") == "no-plan-channel-generates":
        need = _GENERIC_NEED
    return TurnRow(
        ts=ts,
        request_id=request_id,
        stt_chars=_count(stt.get("chars")),
        need=need or _MISSING_NEED,
        status=_closed(decision.get("status")),
        source=_closed(decision.get("source")),
        recall_outcome=_closed(recall.get("outcome")),
        recall_hits=_count(recall.get("hits")),
        best_distance=_distance(recall.get("best_distance")),
        recall_route=_closed(recall.get("route")),
        when=_closed(recall.get("when")),
    )


def summarize_turns(lines: Iterable[str], *, since: str) -> list[TurnRow]:
    """Tabulate one row per turn from server log lines.

    Args:
        lines: JSON log lines; lines that are not JSON objects are dropped.
        since: ISO time; lines stamped before it are ignored. A time without an
            offset is read as local time.

    Returns:
        One row per request that logged a transcription or a decision, in the
        order the requests first appear. Only closed values are kept.
    """
    start = _parse_time(since)
    first_ts: dict[str, str] = {}
    events: dict[str, dict[str, dict[str, object]]] = {}
    for line in lines:
        record = _record(line)
        if record is None:
            continue
        stamped = _event_time(record)
        request_id = record.get("request_id")
        event = record.get("event")
        if stamped is None or stamped[1] < start:
            continue
        if not isinstance(request_id, str) or request_id == _NO_REQUEST:
            continue
        if not isinstance(event, str):
            continue
        first_ts.setdefault(request_id, stamped[0])
        events.setdefault(request_id, {}).setdefault(event, record)
    return [
        _row(request_id, first_ts[request_id], kinds)
        for request_id, kinds in events.items()
        if _TURN_EVENTS & kinds.keys()
    ]


def _cell(value: object) -> str:
    """Render an optional value as one table cell."""
    return _BLANK if value is None else str(value)


def _render(rows: Sequence[TurnRow]) -> list[str]:
    """Render *rows* as aligned text lines, header first."""
    header = (
        "ts", "request", "chars", "need", "status", "source", "route", "when", "recall", "hits",
        "best",
    )  # fmt: skip
    table = [header] + [
        (
            row.ts,
            row.request_id[:8],
            _cell(row.stt_chars),
            row.need,
            _cell(row.status),
            _cell(row.source),
            _cell(row.recall_route),
            _cell(row.when),
            _cell(row.recall_outcome),
            _cell(row.recall_hits),
            _cell(row.best_distance),
        )
        for row in rows
    ]
    widths = [max(len(line[column]) for line in table) for column in range(len(header))]
    return [
        "  ".join(cell.ljust(width) for cell, width in zip(line, widths, strict=True)).rstrip()
        for line in table
    ]


def main(
    argv: Sequence[str] | None = None,
    *,
    write_text: Callable[[str], object] | None = None,
) -> int:
    """Print one aligned line per turn found in the server log.

    Args:
        argv: Arguments after the program name; ``None`` reads ``sys.argv``.
        write_text: Sink for the report text; ``None`` writes to standard output.

    Returns:
        The process exit status: 0, or 1 when the log cannot be read or ``--since`` is not an
        ISO time.
    """
    parser = argparse.ArgumentParser(description="One row of closed values per turn (Plan 0080).")
    parser.add_argument("--log", type=Path, default=_DEFAULT_LOG, help="server log (JSON lines)")
    parser.add_argument("--since", required=True, help="ISO time; earlier log lines are ignored")
    args = parser.parse_args(argv)
    write = write_text if write_text is not None else sys.stdout.write
    try:
        _parse_time(args.since)
    except ValueError:
        logger.error("--since must be an ISO time such as 2026-11-09T10:00:00")
        return 1
    try:
        text = args.log.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Could not read %s: %s", args.log, type(exc).__name__)
        return 1
    rows = summarize_turns(text.splitlines(), since=args.since)
    for line in _render(rows):
        write(line + "\n")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
