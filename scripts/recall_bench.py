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

from collections import Counter  # after the sys.path bootstrap, by design
from dataclasses import dataclass
from datetime import date
from typing import Final, Literal

from server.cognition.recall_cues import CueStrength
import yaml

__all__ = [
    "CLASS_MINIMUMS",
    "MIN_CAPITALIZED_COMMON_NOUNS",
    "Bench",
    "BenchError",
    "BenchQuestion",
    "BenchUnit",
    "load_bench",
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
