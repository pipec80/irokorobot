"""The retrieval bench of the diary's recall (Plan 0088 Part A, D-4): the fixture and its loader.

The bench is invented and tracked (``tests/evals/recall_bench_v1.yaml``): diary units of one
invented owner and the questions asked of them, each with its class, its half (``tune`` or
``check``, D-3) and the units it should find, or none. The loader refuses a bench that could not
measure what D-3 asks before any run: an expected unit that does not exist, a class below its
minimum or missing a half, a duplicated id.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Direct execution (just recall-bench) puts scripts/ on sys.path[0]; the server imports below
# need the repo root (pytest adds it via pyproject).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse  # after the sys.path bootstrap, by design
import asyncio
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, time
import itertools
import json
import logging
import tempfile
from time import perf_counter
from typing import TYPE_CHECKING, Final, Literal
from uuid import uuid4

import httpx
from server.cognition.recall_cues import CueStrength, classify_recall_cue
from server.llm_transport import ollama_embed
from server.memory import recall_store
from server.memory.conversation_types import RecordedTurn, TurnVerdict
from server.memory.declarative import upsert_entity
from server.memory.household_time import household_zone
from server.memory.recall_search import search_recall
from server.memory.retrieval import Gate, GateSignals, gate_or
from server.settings import settings
from server.timestamps import instant_text
import yaml

from scripts import recall_bench_gates
from scripts.recall_bench_gates import PARAMETERS
from server import db

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

logger = logging.getLogger(__name__)

__all__ = [
    "CLASS_MINIMUMS",
    "HARD_CLASSES",
    "MIN_CAPITALIZED_COMMON_NOUNS",
    "NEGATIVE_CLASSES",
    "Bench",
    "BenchError",
    "BenchQuestion",
    "BenchUnit",
    "Candidate",
    "HalfSummary",
    "Midpoint",
    "QuestionScore",
    "choose",
    "class_metrics",
    "load_bench",
    "midpoints",
    "score",
    "summarize",
]

type Half = Literal["tune", "check"]
type UnitKind = Literal["turn", "episode"]

#: The classes of D-4 and their minimum size, over both halves.
CLASS_MINIMUMS: Final[dict[str, int]] = {
    "direct_words": 6,
    "direct_meaning": 8,
    "named_never_told": 6,
    "common_no_name": 6,
    "common_with_name": 4,
    "lexical_only": 4,
    "lexical_only_no_name": 3,
    "window": 4,
    "plural_variant": 4,
    "name_misheard": 3,
}
#: Questions of *direct by meaning* that ask with a capitalized common noun (D-4).
MIN_CAPITALIZED_COMMON_NOUNS: Final = 3
#: D-3: Recall@3 = 100 % on these classes, on both halves.
HARD_CLASSES: Final = ("direct_words", "direct_meaning", "lexical_only", "window")
#: D-3: the classes whose right answer is none.
NEGATIVE_CLASSES: Final = ("named_never_told", "common_no_name", "common_with_name")
#: The hits each question is scored on (the search returns at most three).
TOP_K: Final = 3
_DECIMALS: Final = 3
# A record of the bench never expires during a run.
_NEVER: Final = "2099-01-01T00:00:00.000000+00:00"
#: The top of the ``T_w`` sweep (D-2).
_SWEEP_HIGH: Final = 0.70
#: ``--gates production``: the default gate of ``search_recall`` (Task A5 Step 5).
PRODUCTION: Final = "production"
_DEFAULT_FIXTURE: Final = Path("tests/evals/recall_bench_v1.yaml")
_HALVES: Final[frozenset[str]] = frozenset({"tune", "check"})
_KINDS: Final[frozenset[str]] = frozenset({"turn", "episode"})


class BenchError(ValueError):
    """The bench fixture cannot measure what Plan 0088 D-3 asks."""


@dataclass(frozen=True)
class BenchUnit:
    """One invented diary unit: a turn's words or an episode's summary, told on *day*."""

    id: str
    kind: UnitKind
    day: date
    body: str


@dataclass(frozen=True)
class BenchQuestion:
    """One invented recall question and what it should find.

    Attributes:
        id: Unique id.
        klass: Its class of D-4.
        half: ``tune`` (``T_w`` is swept on it) or ``check`` (held out).
        raw: The transcript, capitalized as the speech-to-text writes it.
        strength: The cue strength ``classify_recall_cue`` must give.
        expected: The unit ids it should find; empty when the right answer is none.
        vector_off: Whether it runs with the embedding model unreachable.
        capitalized_common_noun: Whether it asks with a capitalized common noun (D-4).
    """

    id: str
    klass: str
    half: Half
    raw: str
    strength: CueStrength
    expected: frozenset[str]
    vector_off: bool = False
    capitalized_common_noun: bool = False


@dataclass(frozen=True)
class Bench:
    """The whole bench: the household day of the run, its owner, units and questions."""

    today: date
    owner: str
    units: tuple[BenchUnit, ...]
    questions: tuple[BenchQuestion, ...]


def _unit(entry: dict[str, object]) -> BenchUnit:
    kind = str(entry["kind"])
    if kind not in _KINDS:
        raise BenchError(f"unit {entry['id']!r} has an unknown kind {kind!r}")
    return BenchUnit(
        id=str(entry["id"]),
        kind="episode" if kind == "episode" else "turn",
        day=date.fromisoformat(str(entry["day"])),
        body=str(entry["body"]),
    )


def _question(entry: dict[str, object]) -> BenchQuestion:
    qid, klass, half = str(entry["id"]), str(entry["class"]), str(entry["half"])
    if klass not in CLASS_MINIMUMS:
        raise BenchError(f"question {qid!r} has an unknown class {klass!r}")
    if half not in _HALVES:
        raise BenchError(f"question {qid!r} has an unknown half {half!r}")
    expected = entry.get("expected") or []
    if not isinstance(expected, list):
        raise BenchError(f"question {qid!r} must list its expected units")
    return BenchQuestion(
        id=qid,
        klass=klass,
        half="tune" if half == "tune" else "check",
        raw=str(entry["raw"]),
        strength=CueStrength(str(entry["strength"])),
        expected=frozenset(str(unit_id) for unit_id in expected),
        vector_off=bool(entry.get("vector_off", False)),
        capitalized_common_noun=bool(entry.get("capitalized_common_noun", False)),
    )


def _entries(data: dict[str, object], key: str) -> list[dict[str, object]]:
    entries = data.get(key)
    if not isinstance(entries, list) or not entries:
        raise BenchError(f"the bench needs a non-empty {key!r} list")
    return [entry for entry in entries if isinstance(entry, dict)]


def _check_ids(units: tuple[BenchUnit, ...], questions: tuple[BenchQuestion, ...]) -> None:
    counts = Counter([unit.id for unit in units] + [question.id for question in questions])
    duplicated = sorted(identifier for identifier, count in counts.items() if count > 1)
    if duplicated:
        raise BenchError(f"duplicated ids: {', '.join(duplicated)}")
    unit_ids = {unit.id for unit in units}
    for question in questions:
        absent = sorted(question.expected - unit_ids)
        if absent:
            raise BenchError(f"question {question.id!r} expects absent units: {', '.join(absent)}")


def _check_classes(questions: tuple[BenchQuestion, ...]) -> None:
    for klass, minimum in CLASS_MINIMUMS.items():
        of_class = [question for question in questions if question.klass == klass]
        if len(of_class) < minimum:
            raise BenchError(f"class {klass!r} has {len(of_class)} questions, needs {minimum}")
        if {question.half for question in of_class} != _HALVES:
            raise BenchError(f"class {klass!r} needs questions in both halves")
    capitalized = sum(
        question.capitalized_common_noun
        for question in questions
        if question.klass == "direct_meaning"
    )
    if capitalized < MIN_CAPITALIZED_COMMON_NOUNS:
        raise BenchError(
            f"class 'direct_meaning' needs {MIN_CAPITALIZED_COMMON_NOUNS} capitalized common nouns"
        )


def load_bench(path: Path) -> Bench:
    """Load and validate the bench fixture.

    Args:
        path: The fixture YAML.

    Returns:
        The bench.

    Raises:
        BenchError: If an expected unit does not exist, a class is below its minimum or misses a
            half, *direct by meaning* has too few capitalized common nouns, an id is duplicated,
            or an entry is malformed.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise BenchError("the bench must be a mapping")
    units = tuple(_unit(entry) for entry in _entries(data, "units"))
    questions = tuple(_question(entry) for entry in _entries(data, "questions"))
    _check_ids(units, questions)
    _check_classes(questions)
    return Bench(
        today=date.fromisoformat(str(data["today"])),
        owner=str(data["owner"]),
        units=units,
        questions=questions,
    )


# --- The metrics and the selection rule of D-3, fixed before the bench runs. ---


@dataclass(frozen=True)
class QuestionScore:
    """One question's result over its top three hits.

    Attributes:
        recall: Share of the expected units found; ``None`` when nothing is expected.
        precision: Share of the hits that were expected; ``None`` with no hit.
        reciprocal_rank: ``1 / rank`` of the first expected hit, 0 when none; ``None`` when
            nothing is expected.
        correct_zero: Whether nothing was found, for a question expecting nothing; else ``None``.
    """

    recall: float | None
    precision: float | None
    reciprocal_rank: float | None
    correct_zero: bool | None


def score(question: BenchQuestion, hits: Sequence[str]) -> QuestionScore:
    """Score one question's hits (bench unit ids, best first) at three."""
    top = list(hits[:TOP_K])
    found = [hit for hit in top if hit in question.expected]
    precision = len(found) / len(top) if top else None
    if not question.expected:
        return QuestionScore(None, precision, None, correct_zero=not top)
    ranks = [rank for rank, hit in enumerate(top, start=1) if hit in question.expected]
    return QuestionScore(
        recall=len(set(found)) / len(question.expected),
        precision=precision,
        reciprocal_rank=1.0 / ranks[0] if ranks else 0.0,
        correct_zero=None,
    )


@dataclass(frozen=True)
class Midpoint:
    """A swept ``T_w``: the midpoint of two consecutive observed distances, and their gap."""

    value: float
    margin: float


def midpoints(distances: Sequence[float], *, low: float, high: float) -> list[Midpoint]:
    """The ``T_w`` candidates of D-2: midpoints between consecutive distances in ``[low, high]``.

    The range's ends count as observed points, so the regimes below the first distance and above
    the last one are candidates too.
    """
    points = sorted({low, high, *(value for value in distances if low <= value <= high)})
    return [
        Midpoint(value=(first + second) / 2, margin=second - first)
        for first, second in itertools.pairwise(points)
    ]


@dataclass(frozen=True)
class HalfSummary:
    """What D-3 reads of one rule on one half.

    Attributes:
        hard_recall_min: The lowest Recall@3 of the hard-constraint classes (1.0 meets them).
        correct_zero: The correct-zero rate pooled over the three negative classes.
        common_no_name: The correct-zero rate of *common word, no name*.
    """

    hard_recall_min: float
    correct_zero: float
    common_no_name: float


@dataclass(frozen=True)
class Candidate:
    """One rule, its chosen ``T_w`` and margin (``None`` without a second gate), on both halves."""

    rule: str
    words: float | None
    margin: float | None
    tune: HalfSummary
    check: HalfSummary


def _meets_hard(candidate: Candidate) -> bool:
    return candidate.tune.hard_recall_min >= 1.0 and candidate.check.hard_recall_min >= 1.0


def choose(candidates: Sequence[Candidate]) -> Candidate | None:
    """Apply D-3: the hard constraints on both halves, then the rule that wins on ``tune``.

    Among the rules that meet Recall@3 = 100 % on the hard classes in both halves and improve on
    G0 in *common word, no name*: the highest correct-zero rate, then the fewest parameters, then
    the widest margin of a swept ``T_w``. ``tune`` ranks; ``check`` only has to hold.

    Returns:
        The winner, or ``None``: no rule is adopted and Pipec decides.
    """
    baseline = next((c for c in candidates if c.rule == "G0"), None)
    floor = -1.0 if baseline is None else baseline.tune.common_no_name
    eligible = [c for c in candidates if _meets_hard(c) and c.tune.common_no_name > floor]
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda c: (-c.tune.correct_zero, PARAMETERS[c.rule], -(c.margin or 0.0)),
    )


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def summarize(scores: Mapping[BenchQuestion, QuestionScore], half: Half) -> HalfSummary:
    """D-3's view of one half: the hard classes' lowest recall and the negative classes' zeros."""
    of_half = {q: s for q, s in scores.items() if q.half == half}
    hard = [
        _mean([s.recall or 0.0 for q, s in of_half.items() if q.klass == klass])
        for klass in HARD_CLASSES
    ]
    zeros = [bool(s.correct_zero) for q, s in of_half.items() if q.klass in NEGATIVE_CLASSES]
    common = [bool(s.correct_zero) for q, s in of_half.items() if q.klass == "common_no_name"]
    return HalfSummary(
        hard_recall_min=min(hard),
        correct_zero=_mean([float(zero) for zero in zeros]),
        common_no_name=_mean([float(zero) for zero in common]),
    )


def class_metrics(scores: Mapping[BenchQuestion, QuestionScore]) -> dict[str, dict[str, object]]:
    """Every class x half: questions, Recall@3, Precision@3, MRR and correct-zero rate."""
    table: dict[str, dict[str, object]] = {}
    for klass in CLASS_MINIMUMS:
        for half in ("tune", "check"):
            rows = [s for q, s in scores.items() if q.klass == klass and q.half == half]
            table.setdefault(klass, {})[half] = {
                "n": len(rows),
                "recall_at_3": _rate([s.recall for s in rows]),
                "precision_at_3": _rate([s.precision for s in rows]),
                "mrr": _rate([s.reciprocal_rank for s in rows]),
                "correct_zero": _rate([s.correct_zero for s in rows]),
            }
    return table


def _rate(values: Sequence[float | bool | None]) -> float | None:
    defined = [float(value) for value in values if value is not None]
    return round(_mean(defined), _DECIMALS) if defined else None


# --- The run: a temporary database, real embeddings, the production search (D-4, D-5). ---


@dataclass(frozen=True)
class _Loaded:
    """The bench written into the temporary database."""

    owner: int
    bench_ids: dict[int, str]


def _noon(day: date) -> datetime:
    """Noon of a household day, as an aware instant (a unit is told at noon)."""
    return datetime.combine(day, time(12), tzinfo=household_zone())


async def _record(owner: int, at: datetime) -> int:
    async with db.transaction() as conn:
        cursor = await conn.execute(
            "INSERT INTO conversation_records (owner_entity_id, started_at, last_turn_at, "
            "closed_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (owner, instant_text(at), instant_text(at), instant_text(at), _NEVER),
        )
        record_id = int(cursor.lastrowid or 0)
        await cursor.close()
    return record_id


async def _insert(owner: int, unit: BenchUnit) -> int:
    at = _noon(unit.day)
    record_id = await _record(owner, at)
    async with db.transaction() as conn:
        if unit.kind == "turn":
            turn = RecordedTurn(
                at=at,
                heard=unit.body,
                said="ok",
                voice=TurnVerdict.VERIFIED,
                correlation_id=uuid4(),
            )
            return await recall_store.insert_turn_unit(
                conn, record_id=record_id, owner_entity_id=owner, turn=turn
            )
        cursor = await conn.execute(
            "INSERT INTO conversation_episodes (source_record_id, owner_entity_id, visibility, "
            "sensitivity, summary, model, created_at, expires_at) "
            "VALUES (?, ?, 'personal', 'normal', ?, 'bench', ?, ?)",
            (record_id, owner, unit.body, instant_text(at), _NEVER),
        )
        episode_id = int(cursor.lastrowid or 0)
        await cursor.close()
        return await recall_store.insert_episode_unit(
            conn,
            record_id=record_id,
            episode_id=episode_id,
            owner_entity_id=owner,
            summary=unit.body,
            sensitivity="normal",
            said_at=instant_text(at),
        )


async def _load(bench: Bench, client: httpx.AsyncClient) -> _Loaded:
    """Write every unit and embed it with the configured model (Ollama must answer)."""
    owner = await upsert_entity(name=bench.owner, type="person")
    bench_ids: dict[int, str] = {}
    for unit in bench.units:
        unit_id = await _insert(owner, unit)
        vector = await ollama_embed(
            client, unit.body, model=settings.embedding_model, timeout=settings.ollama_timeout_s
        )
        await recall_store.store_vector(unit_id, vector, model=settings.embedding_model)
        bench_ids[unit_id] = unit.id
    return _Loaded(owner=owner, bench_ids=bench_ids)


def _refuse(request: httpx.Request) -> httpx.Response:
    """The embedding model unreachable: the search's own degradation path runs (D-4)."""
    raise httpx.ConnectError("vector side off for the bench", request=request)


@dataclass(frozen=True)
class _Runner:
    """Everything one search of the bench needs."""

    bench: Bench
    loaded: _Loaded
    online: httpx.AsyncClient
    offline: httpx.AsyncClient

    async def ask(self, question: BenchQuestion, gate: Gate | None) -> tuple[list[str], float]:
        """Run one question through the production ``search_recall``: its hits and latency."""
        cue = classify_recall_cue(question.raw, today=self.bench.today)
        if cue is None:
            raise BenchError(f"question {question.id!r} is not a recall cue")
        client = self.offline if question.vector_off else self.online
        started = perf_counter()
        found = await search_recall(
            self.loaded.owner, cue, client=client, now=_noon(self.bench.today), gate=gate
        )
        elapsed_ms = (perf_counter() - started) * 1000
        return [self.loaded.bench_ids[hit.unit.id] for hit in found.hits], elapsed_ms

    async def run(
        self, gate: Gate | None, questions: Sequence[BenchQuestion]
    ) -> tuple[dict[BenchQuestion, QuestionScore], list[float]]:
        """Score *questions* under *gate* (``None``: the production rule) and time each search."""
        scores: dict[BenchQuestion, QuestionScore] = {}
        latencies: list[float] = []
        for question in questions:
            hits, elapsed_ms = await self.ask(question, gate)
            scores[question] = score(question, hits)
            latencies.append(elapsed_ms)
        return scores, latencies

    async def word_hit_distances(self) -> list[float]:
        """The distances of the word hits of the ``tune`` half: where a second gate can cut."""
        seen: list[float] = []
        base = gate_or(vector=settings.recall_max_distance)

        def recording(signals: GateSignals) -> bool:
            if signals.by_words and signals.distance is not None:
                seen.append(signals.distance)
            return base(signals)

        await self.run(recording, [q for q in self.bench.questions if q.half == "tune"])
        return seen


def _percentile(values: Sequence[float], share: float) -> float:
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(share * len(ordered)))], 1)


@dataclass(frozen=True)
class RuleResult:
    """One rule measured on the whole bench: the candidate D-3 reads and the full record."""

    candidate: Candidate
    classes: dict[str, dict[str, object]]
    latency_ms: dict[str, float]
    sweep: tuple[dict[str, float], ...] = ()


async def _measure(
    runner: _Runner, rule: str, gate: Gate | None, words: float | None, margin: float | None
) -> RuleResult:
    scores, latencies = await runner.run(gate, runner.bench.questions)
    return RuleResult(
        candidate=Candidate(
            rule, words, margin, summarize(scores, "tune"), summarize(scores, "check")
        ),
        classes=class_metrics(scores),
        latency_ms={"p50": _percentile(latencies, 0.5), "p95": _percentile(latencies, 0.95)},
    )


async def _swept(runner: _Runner, rule: str, sweep: Sequence[Midpoint]) -> RuleResult:
    """Choose ``T_w`` on ``tune`` only (D-3), then measure the rule on both halves with it.

    The order is D-3's: the hard constraints met (the lowest hard recall, 1.0 meets them), then
    the correct-zero rate, then the widest margin; when no ``T_w`` meets them, the same order
    names the closest one, and ``choose`` still refuses the rule.
    """
    tune = [q for q in runner.bench.questions if q.half == "tune"]
    rows: list[tuple[HalfSummary, Midpoint]] = []
    for point in sweep:
        gate = recall_bench_gates.build(
            rule, vector=settings.recall_max_distance, words=point.value
        )
        rows.append((summarize((await runner.run(gate, tune))[0], "tune"), point))
    _, point = max(
        rows, key=lambda row: (row[0].hard_recall_min, row[0].correct_zero, row[1].margin)
    )
    gate = recall_bench_gates.build(rule, vector=settings.recall_max_distance, words=point.value)
    result = await _measure(runner, rule, gate, point.value, point.margin)
    table = tuple(
        {"t_w": round(p.value, _DECIMALS), "margin": round(p.margin, _DECIMALS), **asdict(s)}
        for s, p in rows
    )
    return replace(result, sweep=table)


async def _bench(bench: Bench, rules: Sequence[str]) -> dict[str, object]:
    async with (
        httpx.AsyncClient() as online,
        httpx.AsyncClient(transport=httpx.MockTransport(_refuse)) as offline,
    ):
        runner = _Runner(bench, await _load(bench, online), online, offline)
        sweep = midpoints(
            await runner.word_hit_distances(), low=settings.recall_max_distance, high=_SWEEP_HIGH
        )
        results: dict[str, RuleResult] = {}
        for rule in rules:
            if rule == PRODUCTION:
                results[rule] = await _measure(runner, rule, None, None, None)
            elif rule in recall_bench_gates.SWEPT:
                results[rule] = await _swept(runner, rule, sweep)
            else:
                gate = recall_bench_gates.build(rule, vector=settings.recall_max_distance)
                results[rule] = await _measure(runner, rule, gate, None, None)
    chosen = choose([r.candidate for k, r in results.items() if k != PRODUCTION])
    return {
        "embedding_model": settings.embedding_model,
        "t_v": settings.recall_max_distance,
        "sweep_points": len(sweep),
        "chosen": None if chosen is None else {"rule": chosen.rule, "t_w": chosen.words},
        "rules": {rule: _record_of(result) for rule, result in results.items()},
    }


def _record_of(result: RuleResult) -> dict[str, object]:
    candidate = result.candidate
    return {
        "t_w": candidate.words,
        "margin": None if candidate.margin is None else round(candidate.margin, _DECIMALS),
        "tune": asdict(candidate.tune),
        "check": asdict(candidate.check),
        "classes": result.classes,
        "latency_ms": result.latency_ms,
        "sweep": list(result.sweep),
    }


async def _run(fixture: Path, rules: Sequence[str]) -> dict[str, object]:
    """Run the bench against a fresh temporary database, then remove it."""
    bench = load_bench(fixture)
    with tempfile.TemporaryDirectory(prefix="recall-bench-") as folder:
        settings.brain_db_path = Path(folder) / "bench.db"
        settings.occurred_time_enabled = False  # the windows of ADR 0028 decision 7, by said day
        await db.open_db()
        try:
            await db.run_migrations()
            return await _bench(bench, rules)
        finally:
            await db.close_db()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the recall bench and write its counts and rates as JSON (no text of any unit).

    Usage:
        just recall-bench --gates G0,G1,G2,G3 --out .superpowers/recall-bench.json
        just recall-bench --gates production --out .superpowers/recall-bench-production.json
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per embedding otherwise
    parser = argparse.ArgumentParser(description="The recall bench of Plan 0088 Part A.")
    parser.add_argument("--gates", required=True, help="G0,G1,G2,G3 or production")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, default=_DEFAULT_FIXTURE)
    args = parser.parse_args(argv)
    rules = [rule.strip() for rule in str(args.gates).split(",") if rule.strip()]
    unknown = sorted(set(rules) - {*recall_bench_gates.RULES, PRODUCTION})
    if unknown:
        parser.error(f"unknown gates: {', '.join(unknown)}")
    record = asyncio.run(_run(args.fixture, rules))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Recall bench: %s rule(s), chosen %s -> %s", len(rules), record["chosen"], args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
