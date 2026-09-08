"""Safe orchestration for the longitudinal-memory eval (Plan 0046, Task 4).

This module owns the three pieces that touch the outside world -- and nothing
else:

* :func:`isolated_evaluation_database` -- an ``@asynccontextmanager`` that owns a
  migrated *temporary* SQLite database for the run and restores
  ``settings.brain_db_path`` unconditionally. It never accepts a ``--database``
  option and never imports or touches ``server.db._conn``.
* :func:`run_cli` -- dataset/config validation, a cheap provider preflight, the
  isolated run, scoring, aggregation, metadata collection and a non-overwriting
  report write.
* the exit-code contract via
  ``scripts.longitudinal_eval_aggregation.determine_exit_code``.

Provider/network failure is a :class:`HarnessError` (exit ``2``), never cognitive
RED and never an invitation to a cloud fallback.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from http import HTTPStatus
import logging
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

import httpx
from server.settings import settings

from scripts.eval_longitudinal_memory import load_suite, validate_dataset_privacy
from scripts.longitudinal_eval_aggregation import aggregate_results, determine_exit_code
from scripts.longitudinal_eval_driver import CurrentRuntimeDriver
from scripts.longitudinal_eval_metadata import collect_run_metadata, sanitize_url
from scripts.longitudinal_eval_models import (
    CapabilityStatus,
    CliOptions,
    LongitudinalCategory,
    LongitudinalDriver,
    LongitudinalEvaluationResult,
    LongitudinalScenario,
    LongitudinalSuite,
)
from scripts.longitudinal_eval_report import render_report
from scripts.longitudinal_eval_scoring import score_step
from server import db

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from scripts.longitudinal_eval_models import ScoredStep

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TEMP_DB_PREFIX = "iroko-cm0-"
_TEMP_DB_NAME = "brain.db"
_PREFLIGHT_TIMEOUT_S = 5.0
_GATING_RUNS = 3
_OUTPUT_DIR = _REPO_ROOT / "docs" / "evals"


class HarnessError(RuntimeError):
    """A harness/provider fault: the run cannot produce a valid baseline (exit 2)."""


# ---------------------------------------------------------------------------
# Database sandbox
# ---------------------------------------------------------------------------


def _prove_isolated(temp_path: Path, original: Path) -> None:
    """Prove the temp DB differs from the configured DB and is outside ``data/``."""
    repo_data = (_REPO_ROOT / "data").resolve()
    if temp_path == original:
        raise HarnessError("temporary database path equals the configured production path")
    if temp_path == repo_data or repo_data in temp_path.parents:
        raise HarnessError("temporary database path is inside the repository data/ directory")


@asynccontextmanager
async def isolated_evaluation_database() -> AsyncIterator[Path]:
    """Own a migrated temporary database and restore global settings.

    Captures ``settings.brain_db_path`` without opening it, refuses to run when a
    global connection is already open, migrates a fresh temporary ``brain.db``,
    yields its path, and on exit always closes the connection and restores the
    original setting -- chaining a cleanup failure with any body failure. The
    temporary directory then removes the ``.db`` / ``-wal`` / ``-shm`` files.

    Yields:
        The resolved path of the temporary database file.

    Raises:
        HarnessError: On a pre-open connection, a failed path proof, a migration
            error or a cleanup error.
    """
    original = settings.brain_db_path.resolve()
    if db.is_open():
        raise HarnessError("a global database connection is already open before the run")
    with TemporaryDirectory(prefix=_TEMP_DB_PREFIX) as tmp_dir:
        temp_path = (Path(tmp_dir) / _TEMP_DB_NAME).resolve()
        _prove_isolated(temp_path, original)
        settings.brain_db_path = temp_path
        try:
            await _open_temp_database()
            yield temp_path
        finally:
            try:
                await _close_temp_database()
            finally:
                settings.brain_db_path = original


async def _open_temp_database() -> None:
    try:
        await db.open_db()
        await db.run_migrations()
    except Exception as exc:  # any open/migration fault -> harness error
        raise HarnessError(f"temporary database setup failed: {type(exc).__name__}") from exc


async def _close_temp_database() -> None:
    try:
        await db.close_db()
    except Exception as exc:  # any close fault -> harness error
        raise HarnessError(f"temporary database cleanup failed: {type(exc).__name__}") from exc


# ---------------------------------------------------------------------------
# CLI orchestration
# ---------------------------------------------------------------------------


async def run_cli(options: CliOptions) -> int:
    """Run preflight, isolated evaluation and non-overwriting report output.

    Args:
        options: Parsed, validated CLI options.

    Returns:
        The process exit code (0 product PASS, 1 valid cognitive RED, 2 harness).
    """
    prepared = _validate_inputs(options)
    if prepared is None:
        return 2
    _suite, selected = prepared
    if not await _preflight_ok():
        logger.error("provider preflight failed for %s", sanitize_url(settings.ollama_url))
        return 2
    try:
        result = await _execute(options, selected)
        _write_report(options.output_path, render_report(result))
    except HarnessError as exc:
        logger.error("harness error, no baseline report written: %s", exc)
        return 2
    except Exception:
        logger.exception("unexpected harness failure, no baseline report written")
        return 2
    return determine_exit_code(result)


def _validate_inputs(
    options: CliOptions,
) -> tuple[LongitudinalSuite, tuple[LongitudinalScenario, ...]] | None:
    """Validate provider, output path, dataset privacy/schema and ``--only`` ids."""
    if options.provider != "ollama":
        logger.error("unsupported provider %r (only 'ollama' is accepted)", options.provider)
        return None
    if not _output_path_is_safe(options.output_path):
        return None
    try:
        validate_dataset_privacy(options.dataset_path, options.reserved_terms)
        suite = load_suite(options.dataset_path)
    except (ValueError, OSError) as exc:
        logger.error("dataset rejected: %s", exc)
        return None
    selected = _select_scenarios(suite, options.only)
    if selected is None:
        return None
    return suite, selected


def _output_path_is_safe(output_path: Path) -> bool:
    """Reject a path outside ``docs/evals/`` or one that already exists."""
    resolved = output_path.resolve()
    allowed = _OUTPUT_DIR.resolve()
    if resolved.parent != allowed and allowed not in resolved.parents:
        logger.error("report path must live under docs/evals/: %s", output_path)
        return False
    if resolved.exists():
        logger.error("refusing to overwrite an existing report: %s", output_path)
        return False
    return True


def _select_scenarios(
    suite: LongitudinalSuite, only: tuple[str, ...]
) -> tuple[LongitudinalScenario, ...] | None:
    """Return the selected scenarios, or ``None`` on an unknown ``--only`` id."""
    if not only:
        return tuple(suite.scenarios)
    known = {scenario.scenario_id: scenario for scenario in suite.scenarios}
    unknown = sorted(set(only) - known.keys())
    if unknown:
        logger.error("unknown --only scenario id(s): %s", ", ".join(unknown))
        return None
    return tuple(known[scenario_id] for scenario_id in only)


async def _preflight_ok() -> bool:
    """Return whether Ollama answers a cheap ``GET /api/version``."""
    url = f"{settings.ollama_url.rstrip('/')}/api/version"
    try:
        async with httpx.AsyncClient(timeout=_PREFLIGHT_TIMEOUT_S) as client:
            response = await client.get(url)
    except httpx.HTTPError:
        return False
    return response.status_code == HTTPStatus.OK


def _build_driver(client: httpx.AsyncClient) -> LongitudinalDriver:
    """Return the concrete CM-0 driver (a seam tests replace with a fake)."""
    return CurrentRuntimeDriver(client)


async def _execute(
    options: CliOptions,
    selected: Sequence[LongitudinalScenario],
) -> LongitudinalEvaluationResult:
    """Run every selected scenario ``runs`` times inside the isolated database."""
    gating = not options.only and options.runs == _GATING_RUNS
    async with isolated_evaluation_database():
        async with httpx.AsyncClient(timeout=settings.ollama_timeout_s) as client:
            driver = _build_driver(client)
            scored = await _run_scenarios(driver, selected, options.runs)
        metadata = collect_run_metadata(options.dataset_path, sys.argv[1:], options.reserved_terms)
    _verify_run(selected, scored, options.runs, gating=gating)
    return LongitudinalEvaluationResult(
        metadata=metadata,
        results=[step.result for step in scored],
        summary=aggregate_results(scored),
        gating=gating,
    )


async def _run_scenarios(
    driver: LongitudinalDriver,
    selected: Sequence[LongitudinalScenario],
    runs: int,
) -> list[ScoredStep]:
    """Execute and score every step, run-major so a CORRECT precedes its RECALLs."""
    scored: list[ScoredStep] = []
    for _run_index in range(runs):
        for scenario in selected:
            for step in scenario.steps:
                observation = await driver.execute_step(scenario, step)
                scored.append(score_step(scenario.scenario_id, step, observation))
    return scored


def _verify_run(
    selected: Sequence[LongitudinalScenario],
    scored: Sequence[ScoredStep],
    runs: int,
    *,
    gating: bool,
) -> None:
    """Raise :class:`HarnessError` on an incomplete run or a mid-run provider error."""
    expected = sum(len(scenario.steps) for scenario in selected) * runs
    # Defensive: today ``_run_scenarios`` appends one ``ScoredStep`` per step per run
    # (``ERROR`` steps included), so this never fires; it guards a future
    # ``_run_scenarios`` that could drop a step. Provider errors are caught by the
    # ``errored`` check just below, not here.
    if len(scored) != expected:
        raise HarnessError(f"incomplete run: scored {len(scored)} of {expected} steps")
    errored = sum(1 for step in scored if step.result.status is CapabilityStatus.ERROR)
    if errored:
        raise HarnessError(f"provider failed on {errored} step(s) mid-run")
    if gating:
        missing = set(LongitudinalCategory) - {step.result.category for step in scored}
        if missing:
            names = ", ".join(sorted(category.value for category in missing))
            raise HarnessError(f"full run did not execute every category; missing: {names}")


def _write_report(output_path: Path, content: str) -> None:
    """Write the report, refusing to overwrite an existing file.

    Uses ``newline="\n"`` so a report generated on Windows commits with LF
    endings and passes the repository's ``mixed-line-ending`` gate unmodified.
    """
    if output_path.exists():
        raise HarnessError(f"refusing to overwrite an existing report: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8", newline="\n")
