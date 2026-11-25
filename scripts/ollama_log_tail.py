"""Print the last lines of Ollama's own log, beside the server's (Plan 0089 D-11).

Ollama writes why it could not load a model (memory) or why it evicted one in its own log, which
the server never sees. On Windows it lives at ``%LOCALAPPDATA%\\Ollama\\server.log``. The lines
are printed for the operator or the agent to read; they are never copied into the repository.

Usage:
    uv run python scripts/ollama_log_tail.py --lines 50
    uv run python scripts/ollama_log_tail.py --path some/other/server.log
"""

from __future__ import annotations

import argparse
from collections import deque
import os
from pathlib import Path
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

_DEFAULT_LINES = 50


def default_log_path(environ: Mapping[str, str]) -> Path | None:
    """Return Ollama's log path on Windows, or ``None`` when ``LOCALAPPDATA`` is not set.

    Args:
        environ: The environment to read (``os.environ`` at the command line).
    """
    local = environ.get("LOCALAPPDATA")
    return None if not local else Path(local) / "Ollama" / "server.log"


def tail_lines(path: Path, count: int) -> list[str]:
    """Return the last *count* lines of *path*, without their line ends.

    Args:
        path: A text log file.
        count: How many lines to keep.
    """
    with path.open(encoding="utf-8", errors="replace") as handle:
        return [line.rstrip("\r\n") for line in deque(handle, maxlen=count)]


def main(argv: Sequence[str] | None = None) -> int:
    """Print the tail of Ollama's log; return 1 when the log is not there.

    Args:
        argv: Command-line arguments (``sys.argv[1:]`` when ``None``).
    """
    parser = argparse.ArgumentParser(description="Show the last lines of Ollama's own log.")
    parser.add_argument("--lines", type=int, default=_DEFAULT_LINES)
    parser.add_argument("--path", type=Path, default=None)
    args = parser.parse_args(argv)
    path: Path | None = args.path or default_log_path(os.environ)
    if path is None or not path.is_file():
        sys.stderr.write(f"Ollama log not found: {path}\n")
        return 1
    for line in tail_lines(path, max(args.lines, 1)):
        sys.stdout.write(f"{line}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
