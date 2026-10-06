"""Diagnose why the streaming protocol falls back (Plan 0057): ``just diagnose-stream``.

Runs the golden and public turns under several variants against the real local Ollama,
in a seeded shuffled order, then writes a counts-only report. Pipec runs it; nothing in
the report is model text.

Usage:
    just diagnose-stream --runs 5 --output docs/evals/0057-stream-diagnosis-run1.md
    just diagnose-stream --variants full full_repeat no_context --seed 58
"""

from __future__ import annotations

from pathlib import Path
import sys

# Direct execution (``python scripts/diagnose_stream_protocol.py``) puts ``scripts/`` on
# ``sys.path[0]``, not the repo root; see ``scripts/eval_chat.py``. Must run before any
# ``from scripts.…`` import below.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse  # after the sys.path bootstrap, by design
import asyncio
from datetime import UTC, datetime
import logging
from typing import TYPE_CHECKING, NoReturn

import httpx
from pydantic import BaseModel, Field
from server.settings import settings

from scripts.eval_chat import (
    _GOLDEN_PATH,
    _REPORT_DIRECTORY,
    golden_stream_turns,
    load_suite,
    select_cases,
    write_report,
)
from scripts.eval_stream_diagnosis import run_diagnosis
from scripts.eval_stream_protocol import public_turns
from scripts.longitudinal_eval_metadata import sanitize_url
from scripts.stream_diagnosis_probes import fetch_ollama_facts, probe_structured_stream
from scripts.stream_diagnosis_report import ReportContext, render_diagnosis_report
from scripts.stream_diagnosis_stats import baseline_observations, summarize
from scripts.stream_diagnosis_variants import StreamVariant, build_units

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from contextlib import AbstractAsyncContextManager

    type ClientFactory = Callable[[], AbstractAsyncContextManager[httpx.AsyncClient]]

logger = logging.getLogger(__name__)

_MIN_RUNS = 1
_MAX_RUNS = 10
_DEFAULT_SEED = 57
EXIT_OK = 0
EXIT_PROVIDER_ERROR = 1
EXIT_PREFLIGHT = 2


class CliOptions(BaseModel):
    """Validated command-line options for the diagnosis."""

    runs: int = Field(default=5, ge=_MIN_RUNS, le=_MAX_RUNS)
    seed: int = _DEFAULT_SEED
    variants: list[StreamVariant] | None = None
    output: Path | None = None
    structured_runs: int = Field(default=5, ge=0, le=_MAX_RUNS)


def parse_cli_args(argv: Sequence[str] | None = None) -> CliOptions:
    """Parse and validate command-line arguments.

    Args:
        argv: Optional arguments excluding the executable name.

    Returns:
        Typed, validated CLI options.
    """
    parser = argparse.ArgumentParser(description="Diagnose the streaming protocol fallback")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--seed", type=int, default=_DEFAULT_SEED)
    parser.add_argument("--variants", nargs="+", choices=[v.value for v in StreamVariant])
    parser.add_argument("--output")
    parser.add_argument("--structured-runs", type=int, default=5)
    namespace = parser.parse_args(argv)
    output = Path(namespace.output).expanduser().resolve() if namespace.output else None
    return CliOptions(
        runs=namespace.runs,
        seed=namespace.seed,
        variants=[StreamVariant(v) for v in namespace.variants] if namespace.variants else None,
        output=output,
        structured_runs=namespace.structured_runs,
    )


def _default_client_factory() -> AbstractAsyncContextManager[httpx.AsyncClient]:
    """Build the single Ollama HTTP client owned by one CLI invocation."""
    return httpx.AsyncClient(timeout=settings.ollama_timeout_s)


async def run_cli(options: CliOptions, *, client_factory: ClientFactory | None = None) -> int:
    """Run the diagnosis against the local Ollama and write its Markdown report.

    Args:
        options: Validated command-line options.
        client_factory: Optional async context-manager factory for the run-owned HTTP
            client; defaults to a real ``httpx.AsyncClient``.

    Returns:
        ``0`` on success, ``1`` if any provider call failed, ``2`` if Ollama did not
        answer (nothing is written then).
    """
    suite = load_suite(_GOLDEN_PATH)
    golden = golden_stream_turns(select_cases(suite, None))
    units = build_units(golden, public_turns(), options.variants)
    factory = client_factory or _default_client_factory
    async with factory() as client:
        facts = await fetch_ollama_facts(client)
        if not facts.reachable:
            logger.error("Ollama is not answering at %s", sanitize_url(settings.ollama_url))
            return EXIT_PREFLIGHT
        logger.info(
            "Diagnosis: %d units x %d runs = %d streams (seed %d)",
            len(units),
            options.runs,
            len(units) * options.runs,
            options.seed,
        )
        observations = await run_diagnosis(
            units, client=client, runs=options.runs, seed=options.seed
        )
        probe = control = None
        if options.structured_runs:
            probe = await probe_structured_stream(
                client, runs=options.structured_runs, constrained=True
            )
            control = await probe_structured_stream(
                client, runs=options.structured_runs, constrained=False
            )
    context = ReportContext(
        model=facts.model,
        ollama_version=facts.version,
        model_digest=facts.digest,
        runs=options.runs,
        seed=options.seed,
    )
    stamp = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")
    output = options.output or _REPORT_DIRECTORY / f"{stamp}-stream-diagnosis.md"
    write_report(output, render_diagnosis_report(observations, context, probe, control))
    baseline = summarize(baseline_observations(observations))
    logger.info(
        "Diagnosis complete: baseline_fallback_rate=%s report=%s", baseline.fallback_rate, output
    )
    probe_errors = sum(result.errors for result in (probe, control) if result)
    errors = summarize(observations).errors + probe_errors
    return EXIT_PROVIDER_ERROR if errors else EXIT_OK


def main() -> NoReturn:
    """Run the command-line diagnosis and exit with its status."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    raise SystemExit(asyncio.run(run_cli(parse_cli_args())))


if __name__ == "__main__":
    main()
