"""Loader and privacy validator for the longitudinal-memory eval suite (Plan 0046).

Task 2 scope only: :func:`load_suite` parses and semantically validates the
versioned YAML suite; :func:`validate_dataset_privacy` rejects unsafe or
reserved content in a dataset file. Scoring, the runtime driver, the CLI and
the Markdown report belong to later tasks. Nothing here touches the runtime,
the network or a real database. The strict typed models live in
:mod:`scripts.longitudinal_eval_models`; this module never mutates their text.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Direct execution (``python scripts/eval_longitudinal_memory.py``) puts
# ``scripts/`` on ``sys.path[0]``, not the repo root, so ``from scripts.…``
# imports fail. Under pytest the repo root is already on the path
# (pyproject ``pythonpath``), so this only matters for the frozen justfile
# entrypoint. Must run before any ``from scripts.…`` import below.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse  # after the sys.path bootstrap, by design
import asyncio
import logging
import re
from typing import TYPE_CHECKING

from pydantic import ValidationError
import yaml

from scripts.longitudinal_eval_models import (
    CliOptions,
    ExpectedObservation,
    LongitudinalCategory,
    LongitudinalSuite,
)

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

    from scripts.longitudinal_eval_models import LongitudinalStep

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DATASET = _REPO_ROOT / "tests" / "evals" / "golden_longitudinal_memory.yaml"
_DEFAULT_OUTPUT = _REPO_ROOT / "docs" / "evals" / "longitudinal-memory-cm0.md"

_ALL_CATEGORIES: frozenset[LongitudinalCategory] = frozenset(LongitudinalCategory)

_EMAIL_RE = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", re.IGNORECASE)
_WINDOWS_PATH_RE = re.compile(r"[a-z]:\\users\\|\\users\\", re.IGNORECASE)
_UNIX_PATH_RE = re.compile(r"/home/[a-z._-]|/users/[a-z._-]", re.IGNORECASE)
_SECRET_RE = re.compile(
    r"\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password|passwd|secret"
    r"|token|bearer)\b\s*[:=]\s*\S",
    re.IGNORECASE,
)
_LONG_DIGIT_RUN_RE = re.compile(r"\d{7,}")
_PHONE_CANDIDATE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_NON_DIGIT_RE = re.compile(r"\D")
_MIN_PHONE_DIGITS = 9

# ISO dates (<= 8 separated digits) stay allowed; a phone-like run needs 9+.
_UNSAFE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email address", _EMAIL_RE),
    ("production Windows path", _WINDOWS_PATH_RE),
    ("production Unix path", _UNIX_PATH_RE),
    ("secret-like assignment", _SECRET_RE),
    ("long digit run", _LONG_DIGIT_RUN_RE),
)

_EXPECTATION_FIELDS: tuple[str, ...] = tuple(ExpectedObservation.model_fields)


def load_suite(path: Path) -> LongitudinalSuite:
    """Load and semantically validate one versioned longitudinal suite.

    Args:
        path: Path to a version-1 YAML suite.

    Returns:
        The parsed, structurally and semantically valid suite.

    Raises:
        ValueError: On a non-version-1 mapping, a schema violation, or a failed
            semantic rule (unique ids, actor refs, sessions, expectations,
            category coverage).
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    _require_version_one(raw)
    try:
        suite = LongitudinalSuite.model_validate(raw)
    except ValidationError as exc:
        msg = f"longitudinal suite does not match the frozen schema: {exc}"
        raise ValueError(msg) from exc
    _check_unique_ids(suite)
    _check_actor_references(suite)
    _check_sessions(suite)
    _check_expectations(suite)
    _check_category_coverage(suite)
    return suite


def _require_version_one(raw: object) -> None:
    if not isinstance(raw, dict) or raw.get("version") != 1:
        raise ValueError('longitudinal suite "version" must be exactly 1')


def _check_unique_ids(suite: LongitudinalSuite) -> None:
    seen_scenarios: set[str] = set()
    for scenario in suite.scenarios:
        if scenario.scenario_id in seen_scenarios:
            raise ValueError(f'scenario_id is not "unique" (duplicate): {scenario.scenario_id}')
        seen_scenarios.add(scenario.scenario_id)
        seen_steps: set[str] = set()
        for step in scenario.steps:
            if step.step_id in seen_steps:
                raise ValueError(
                    f'step_id is not "unique" (duplicate) in {scenario.scenario_id}: {step.step_id}'
                )
            seen_steps.add(step.step_id)


def _check_actor_references(suite: LongitudinalSuite) -> None:
    for scenario in suite.scenarios:
        for step in scenario.steps:
            if step.actor_id not in scenario.actors:
                raise ValueError(
                    f'step {step.step_id} names an "actor" missing from '
                    f"{scenario.scenario_id}: {step.actor_id}"
                )


def _check_sessions(suite: LongitudinalSuite) -> None:
    for scenario in suite.scenarios:
        previous = 0
        for step in scenario.steps:
            if step.session < 1:
                raise ValueError(f'step {step.step_id} "session" must be a positive integer')
            if step.session < previous:
                raise ValueError(
                    f'step {step.step_id} "session" decreases within {scenario.scenario_id}'
                )
            previous = step.session


def _check_expectations(suite: LongitudinalSuite) -> None:
    for scenario in suite.scenarios:
        for step in scenario.steps:
            if _expectation_is_empty(step):
                raise ValueError(
                    f'step {step.step_id} has no "assertion": every "expectation" set is empty'
                )


def _expectation_is_empty(step: LongitudinalStep) -> bool:
    return not any(getattr(step.expected, name) for name in _EXPECTATION_FIELDS)


def _check_category_coverage(suite: LongitudinalSuite) -> None:
    covered = {step.category for scenario in suite.scenarios for step in scenario.steps}
    missing = _ALL_CATEGORIES - covered
    if missing:
        names = ", ".join(sorted(category.value for category in missing))
        raise ValueError(f'suite does not cover all nine "categories"; missing: {names}')


def validate_dataset_privacy(path: Path, reserved_terms: Collection[str]) -> None:
    """Reject reserved personal terms and unsafe content in a dataset file.

    A case-insensitive scan of the raw file text, covering keys and values
    alike. Reserved-term values stay memory-only: a violation names the file
    and line, never the term itself.

    Args:
        path: Path to the dataset file to inspect.
        reserved_terms: Invented reserved identifiers barred from the dataset.

    Raises:
        ValueError: If a reserved term, email address, phone-like digit run,
            production path or secret-like assignment is present.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    _reject_reserved_terms(lines, reserved_terms, path.name)
    _reject_unsafe_content(lines, path.name)


def _reject_reserved_terms(lines: list[str], reserved_terms: Collection[str], name: str) -> None:
    needles = [term.strip().lower() for term in reserved_terms if term and term.strip()]
    for lineno, line in enumerate(lines, start=1):
        lowered = line.lower()
        if any(needle in lowered for needle in needles):
            raise ValueError(f"reserved term found in {name} at line {lineno}")


def _reject_unsafe_content(lines: list[str], name: str) -> None:
    for lineno, line in enumerate(lines, start=1):
        label = _unsafe_label(line)
        if label is not None:
            raise ValueError(f"{label} found in {name} at line {lineno}")


def _unsafe_label(line: str) -> str | None:
    for label, pattern in _UNSAFE_PATTERNS:
        if pattern.search(line):
            return label
    if _has_phone_like_number(line):
        return "phone-like digit run"
    return None


def _has_phone_like_number(line: str) -> bool:
    return any(
        len(_NON_DIGIT_RE.sub("", match.group())) >= _MIN_PHONE_DIGITS
        for match in _PHONE_CANDIDATE_RE.finditer(line)
    )


# ---------------------------------------------------------------------------
# CLI (Task 4) — the frozen ``just eval-longitudinal`` entrypoint
# ---------------------------------------------------------------------------


def parse_cli_args(argv: Sequence[str]) -> CliOptions:
    """Parse ``argv`` into validated :class:`CliOptions`.

    Args:
        argv: Argument list without the program name (``sys.argv[1:]``).

    Returns:
        The parsed options. A provider other than ``ollama`` or ``--runs < 1``
        exits the process with code 2 (argparse convention).
    """
    parser = argparse.ArgumentParser(
        description="Reproducible longitudinal-memory capability baseline (Plan 0046, CM-0)."
    )
    parser.add_argument("--dataset", type=Path, default=_DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--only", nargs="+", default=None, metavar="SCENARIO_ID")
    parser.add_argument("--reserved-term", action="append", default=None, metavar="TERM")
    parser.add_argument("--provider", default="ollama", choices=("ollama",))
    args = parser.parse_args(list(argv))
    if args.runs < 1:
        parser.error("--runs must be >= 1")
    return CliOptions(
        dataset_path=args.dataset,
        output_path=args.output,
        runs=args.runs,
        only=tuple(args.only or ()),
        reserved_terms=tuple(args.reserved_term or ()),
        provider=args.provider,
    )


def main() -> None:
    """CLI entry point for ``just eval-longitudinal``."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    options = parse_cli_args(sys.argv[1:])
    # Local import: the runner imports load_suite/validate_dataset_privacy from
    # this module, so importing run_cli at module scope would be circular.
    from scripts.longitudinal_eval_runner import run_cli  # noqa: PLC0415

    raise SystemExit(asyncio.run(run_cli(options)))


if __name__ == "__main__":
    main()
