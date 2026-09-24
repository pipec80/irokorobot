"""Block commits that carry locally reserved private terms.

Real household data (family names, birth dates, pets) must never enter the
repository: tests use invented canary values and real acceptance runs locally.
The reserved terms live only in a gitignored local file, one per line (``#``
starts a comment), matched case-sensitively as whole words. Without that file
(CI, a fresh clone) the check passes: it guards local commits, not the build.

Usage (pre-commit passes the staged paths, or the commit-message file):
    uv run python scripts/check_reserved_terms.py PATH [PATH ...]
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import re
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

logger = logging.getLogger(__name__)

RESERVED_TERMS_FILE = Path(__file__).resolve().parents[1] / "project-history" / "reserved-terms.txt"


def load_reserved_terms(path: Path = RESERVED_TERMS_FILE) -> list[str]:
    """Return the locally reserved terms.

    Args:
        path: Gitignored list, one term per line; ``#`` lines are comments.

    Returns:
        The terms in file order, or an empty list when the file is absent.
    """
    if not path.is_file():
        return []
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def build_matcher(terms: Iterable[str]) -> re.Pattern[str] | None:
    """Compile one whole-word, case-sensitive matcher for every term.

    Args:
        terms: Reserved terms; duplicates are ignored.

    Returns:
        The compiled matcher, or None when there is nothing to match.
    """
    ordered = sorted(set(terms), key=len, reverse=True)
    if not ordered:
        return None
    return re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, ordered)) + r")(?!\w)")


def offending_lines(text: str, matcher: re.Pattern[str]) -> list[int]:
    """Return the 1-based numbers of the lines that contain a reserved term.

    Args:
        text: Full file or commit-message content.
        matcher: Matcher from `build_matcher`.

    Returns:
        Line numbers in ascending order.
    """
    return [number for number, line in enumerate(text.splitlines(), 1) if matcher.search(line)]


def main(argv: Sequence[str] | None = None) -> int:
    """Report every reserved term in the given files without echoing it.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        1 when any file contains a reserved term, else 0.
    """
    parser = argparse.ArgumentParser(description="Block locally reserved private terms.")
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--terms-file", type=Path, default=RESERVED_TERMS_FILE)
    args = parser.parse_args(argv)

    matcher = build_matcher(load_reserved_terms(args.terms_file))
    if matcher is None:
        return 0
    found = False
    for path in args.paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number in offending_lines(text, matcher):
            logger.error("%s:%d: contains a reserved private term", path, number)
            found = True
    return 1 if found else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(main())
