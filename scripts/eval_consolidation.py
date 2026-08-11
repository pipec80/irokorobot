"""eval_consolidation.py — memory-extraction quality eval against REAL Ollama (R8).

Runs the production extraction path (``_extract_via_ollama`` followed by
``normalize_extraction``) on every golden conversation in
tests/evals/golden_conversations.yaml and compares the result with the
expected entities/facts. Matching is case- and accent-insensitive, with
containment (predicted "el rock de los 80" matches expected "rock").

Reports precision/recall per predicate and global as a markdown table.
The global fact recall decides — with numbers, not faith — whether the
consolidation model (settings.consolidation_model, default qwen2.5:3b)
is good enough or a bigger model is needed (docs/audit/03 R8).

NOT part of pytest: requires a live Ollama server with the consolidation
model pulled. Start services first: just services

Usage:
    just eval-memory
    just eval-memory --only pareja
    uv run --env-file .env python scripts/eval_consolidation.py

To eval another model, override the env var for one run:
    $env:CONSOLIDATION_MODEL = 'qwen3:4b'; just eval-memory

Exit code: 1 if global fact recall < 0.8 (alarm threshold from doc 03 R8).
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
import logging
from pathlib import Path
import sys
import time
from typing import TYPE_CHECKING, Any

import httpx
from server.exceptions import LLMError
from server.memory.consolidation import _extract_via_ollama
from server.memory.declarative import _fold_name
from server.memory.normalize import normalize_extraction
from server.settings import settings
import yaml

if TYPE_CHECKING:
    from server.schemas import ExtractedFact

logging.basicConfig(level=logging.WARNING, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

_GOLDEN_PATH = Path("tests") / "evals" / "golden_conversations.yaml"
_RECALL_THRESHOLD = 0.8


# ---------------------------------------------------------------------------
# Matching — case/accent-insensitive with containment
# ---------------------------------------------------------------------------


def _as_list(value: str | list[str]) -> list[str]:
    """Return *value* as a list (golden fields accept scalar or list)."""
    return value if isinstance(value, list) else [value]


def _value_matches(predicted: str, expected: str | list[str]) -> bool:
    """True when *predicted* matches any accepted alternative in *expected*.

    Folded (case/accent-insensitive) equality or containment either way,
    so "el 12 de marzo de 1980" matches expected "12 de marzo de 1980".
    """
    folded = _fold_name(str(predicted))
    for alt in _as_list(expected):
        folded_alt = _fold_name(str(alt))
        if folded == folded_alt or folded_alt in folded or folded in folded_alt:
            return True
    return False


def _fact_matches(predicted: ExtractedFact, expected: dict[str, Any]) -> bool:
    """True when a predicted ExtractedFact satisfies an expected triple."""
    return (
        _fold_name(predicted.predicate) == _fold_name(str(expected["predicate"]))
        and _value_matches(predicted.subject, expected["subject"])
        and _value_matches(predicted.object, expected["object"])
    )


def _active_person_display_name(case: dict[str, Any]) -> str | None:
    """Return explicit manual display guidance for one synthetic turn."""
    for legacy_key in ("owner", "owner_name"):
        if legacy_key in case:
            raise ValueError(f"{legacy_key} is not an active-person context")
    active_person = case.get("active_person")
    if active_person is None:
        return None
    if not isinstance(active_person, dict):
        raise ValueError("active_person must be a mapping")
    if active_person.get("source") != "manual":
        raise ValueError("active_person source must be manual")
    person_id = active_person.get("person_id")
    if not isinstance(person_id, int) or isinstance(person_id, bool):
        raise ValueError("active_person person_id must be an integer")
    display_name = active_person.get("display_name")
    if not isinstance(display_name, str) or not display_name.strip():
        raise ValueError("active_person display_name must not be blank")
    return display_name


# ---------------------------------------------------------------------------
# Per-case evaluation
# ---------------------------------------------------------------------------


@dataclass
class CaseResult:
    """Outcome of one golden case."""

    case_id: str
    elapsed_s: float
    matched: list[dict[str, Any]] = field(default_factory=list)
    missed: list[dict[str, Any]] = field(default_factory=list)
    extras: list[ExtractedFact] = field(default_factory=list)
    entities_expected: int = 0
    entities_found: int = 0
    error: str | None = None


async def _eval_case(case: dict[str, Any]) -> CaseResult:
    """Run the real extraction pipeline on one golden case and score it."""
    active_person_name = _active_person_display_name(case)
    expected_facts = case.get("expected_facts") or []
    expected_entities = case.get("expected_entities") or []
    t0 = time.perf_counter()
    try:
        raw = await _extract_via_ollama(case["user"], case["assistant"])
    except (LLMError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
        return CaseResult(
            case_id=case["id"],
            elapsed_s=time.perf_counter() - t0,
            missed=list(expected_facts),
            entities_expected=len(expected_entities),
            error=f"{type(exc).__name__}: {exc}",
        )
    elapsed = time.perf_counter() - t0
    extraction = normalize_extraction(
        raw,
        active_person_name=active_person_name,
        user_text=case["user"],
    )

    result = CaseResult(
        case_id=case["id"], elapsed_s=elapsed, entities_expected=len(expected_entities)
    )
    for exp in expected_facts:
        target = (
            result.matched
            if any(_fact_matches(p, exp) for p in extraction.facts)
            else result.missed
        )
        target.append(exp)
    result.extras = [
        p for p in extraction.facts if not any(_fact_matches(p, exp) for exp in expected_facts)
    ]
    for exp_ent in expected_entities:
        found = any(
            _value_matches(ent.name, exp_ent["name"])
            and ("type" not in exp_ent or ent.type == exp_ent["type"])
            for ent in extraction.entities
        )
        result.entities_found += int(found)
    return result


# ---------------------------------------------------------------------------
# Aggregation + report
# ---------------------------------------------------------------------------


@dataclass
class Tally:
    """Precision/recall counters for one predicate (or the global total)."""

    tp: int = 0
    fn: int = 0
    fp: int = 0

    @property
    def recall(self) -> float:
        """TP / (TP + FN); 1.0 when nothing was expected."""
        total = self.tp + self.fn
        return self.tp / total if total else 1.0

    @property
    def precision(self) -> float:
        """TP / (TP + FP); 1.0 when nothing was predicted."""
        total = self.tp + self.fp
        return self.tp / total if total else 1.0


def _aggregate(results: list[CaseResult]) -> dict[str, Tally]:
    """Fold case results into per-predicate tallies (expected predicates own FNs)."""
    tallies: dict[str, Tally] = defaultdict(Tally)
    for res in results:
        for exp in res.matched:
            tallies[str(exp["predicate"])].tp += 1
        for exp in res.missed:
            tallies[str(exp["predicate"])].fn += 1
        for fact in res.extras:
            tallies[str(fact.predicate)].fp += 1
    return dict(tallies)


def _print_case(res: CaseResult, index: int, total: int) -> None:
    """Print the one-line summary (plus misses/extras) for a finished case."""
    facts_total = len(res.matched) + len(res.missed)
    status = f"facts {len(res.matched)}/{facts_total}  extras {len(res.extras)}"
    if res.entities_expected:
        status += f"  entities {res.entities_found}/{res.entities_expected}"
    print(f"[{index:>2}/{total}] {res.case_id:<32} {res.elapsed_s:>5.1f}s  {status}")  # noqa: T201
    if res.error:
        print(f"         ERROR: {res.error}")  # noqa: T201
    for exp in res.missed:
        alts = " | ".join(str(a) for a in _as_list(exp["object"]))
        print(f"         MISS : {exp['subject']} {exp['predicate']} {alts}")  # noqa: T201
    for fact in res.extras:
        print(f"         EXTRA: {fact.subject} {fact.predicate} {fact.object}")  # noqa: T201


def _print_report(results: list[CaseResult]) -> Tally:
    """Print the markdown report and return the global fact tally."""
    tallies = _aggregate(results)
    total = Tally(
        tp=sum(t.tp for t in tallies.values()),
        fn=sum(t.fn for t in tallies.values()),
        fp=sum(t.fp for t in tallies.values()),
    )
    print("\n## Reporte de extracción — modelo:", settings.consolidation_model)  # noqa: T201
    print("\n| Predicado | TP | FN | FP | Recall | Precision |")  # noqa: T201
    print("|---|---|---|---|---|---|")  # noqa: T201
    for predicate in sorted(tallies):
        t = tallies[predicate]
        print(  # noqa: T201
            f"| {predicate} | {t.tp} | {t.fn} | {t.fp} | {t.recall:.2f} | {t.precision:.2f} |"
        )
    print(  # noqa: T201
        f"| **GLOBAL** | {total.tp} | {total.fn} | {total.fp} "
        f"| **{total.recall:.2f}** | **{total.precision:.2f}** |"
    )
    ent_expected = sum(r.entities_expected for r in results)
    ent_found = sum(r.entities_found for r in results)
    if ent_expected:
        print(f"\nEntidades: recall {ent_found / ent_expected:.2f} ({ent_found}/{ent_expected})")  # noqa: T201
    latencies = [r.elapsed_s for r in results if r.error is None]
    if latencies:
        print(  # noqa: T201
            f"Latencia extracción: avg {sum(latencies) / len(latencies):.1f}s"
            f"  max {max(latencies):.1f}s  ({len(latencies)} casos)"
        )
    return total


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def _run(only: str | None) -> int:
    """Run all (or one) golden cases sequentially; return the exit code."""
    with _GOLDEN_PATH.open(encoding="utf-8") as fh:
        cases: list[dict[str, Any]] = yaml.safe_load(fh)["cases"]
    if only is not None:
        cases = [c for c in cases if c["id"] == only]
        if not cases:
            print(f"No golden case with id {only!r} in {_GOLDEN_PATH}")  # noqa: T201
            return 1
    print(  # noqa: T201
        f"Eval de consolidación — {len(cases)} casos"
        f" · modelo {settings.consolidation_model} · {settings.ollama_url}\n"
    )
    results: list[CaseResult] = []
    for index, case in enumerate(cases, start=1):
        result = await _eval_case(case)
        results.append(result)
        _print_case(result, index, len(cases))
    total = _print_report(results)
    if total.recall < _RECALL_THRESHOLD:
        print(  # noqa: T201
            f"\nFAIL: recall global {total.recall:.2f} < {_RECALL_THRESHOLD}"
            " — considerar un modelo de consolidación más grande (doc 09 §3)."
        )
        return 1
    print(f"\nOK: recall global {total.recall:.2f} >= {_RECALL_THRESHOLD}")  # noqa: T201
    return 0


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Eval de extracción de memoria contra Ollama real (R8)"
    )
    parser.add_argument("--only", default=None, help="Run a single golden case by id")
    args = parser.parse_args()
    try:
        sys.exit(asyncio.run(_run(args.only)))
    except httpx.ConnectError:
        print(  # noqa: T201
            f"Ollama no responde en {settings.ollama_url} — arranca los servicios"
            " primero: just services"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
