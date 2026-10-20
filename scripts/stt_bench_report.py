"""The bench report and the unclear-threshold calibration of Plan 0069 (D-7, D-9, D-11).

Reads run files written by ``stt_bench.run_bench`` and the private manifest, scores every
read take (lexical quality on all its clips joined, turn integrity on the first clip
alone, D-7), and renders Markdown with the sizes of every figure. Spontaneous speech is
reported as counts and pooled rates only: no transcript and no reference is ever printed.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
import math
from statistics import median
from typing import TYPE_CHECKING

import numpy as np

from scripts.speaker_calibration_corpus import resolve_corpus_path
from scripts.stt_bench_configs import split_items
from scripts.stt_corpus_models import MANIFEST_NAME, ScriptItem, Take, load_script, load_takes
from scripts.stt_metrics import (
    CriticalErrors,
    best_reference,
    block_bootstrap_diff,
    calibrate_threshold,
    char_errors,
    critical_errors,
    edge_deletions,
    mapsswe,
    mark_scores,
    pair_correct,
    word_errors,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

_QUESTION = ("?", "¿")
_MIN_WRONG = 30
_MAX_FALSE_REJECT = 0.05
_MIN_CATCH = 0.5
_P90 = 90


@dataclass(frozen=True)
class TakeScore:
    """One read take scored against its reference (D-7)."""

    take_id: str
    item_id: str
    layer: str
    condition: str
    errors: int
    words: int
    char_errors: int
    chars: int
    turn_errors: int
    split: bool
    empty: bool
    pair_ok: bool | None
    is_question_hyp: bool
    is_question_ref: bool | None
    critical: CriticalErrors
    edge_first: bool
    edge_last: bool
    logprob: float | None
    marked_reference: str
    marked_hypothesis: str


@dataclass(frozen=True)
class RunScores:
    """Every figure of one run."""

    run_id: str
    meta: dict[str, object]
    takes: list[TakeScore]
    free_errors: int
    free_words: int
    free_clips: int
    free_inaudible: int
    latencies: list[float]
    repeat_changed: int
    repeat_compared: int


def _load(root: Path, run_id: str) -> tuple[dict[str, object], list[dict[str, object]]]:
    path = resolve_corpus_path(root, f"results/runs/{run_id}.jsonl")
    meta = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return meta, rows


def _joined(rows: Sequence[dict[str, object]]) -> str:
    return " ".join(str(row["text"]).strip() for row in rows if str(row["text"]).strip())


def _score_take(take: Take, item: ScriptItem, rows: Sequence[dict[str, object]]) -> TakeScore:
    references = (take.reference or item.text,) if take.deviated else (item.text, *item.also)
    joined = _joined(rows)
    first = str(rows[0]["text"]) if rows else ""
    reference = best_reference(references, joined)
    errors, words = word_errors(reference, joined)
    chars_wrong, chars = char_errors(reference, joined)
    first_edge, last_edge = edge_deletions(reference, joined)
    logprob = rows[0]["avg_logprob"] if rows else None
    return TakeScore(
        take_id=take.take_id,
        item_id=item.id,
        layer=item.layer,
        condition=take.condition,
        errors=errors,
        words=words,
        char_errors=chars_wrong,
        chars=chars,
        turn_errors=word_errors(reference, first)[0],
        split=len(rows) > 1,
        empty=not joined,
        pair_ok=pair_correct(joined, item.target, item.competitor)
        if item.target and item.competitor
        else None,
        is_question_hyp=any(mark in joined for mark in _QUESTION),
        is_question_ref=(item.kind == "question") if item.layer == "A" else None,
        critical=critical_errors(reference, joined, numbers=item.layer == "E"),
        edge_first=first_edge,
        edge_last=last_edge,
        logprob=float(logprob) if isinstance(logprob, int | float) else None,
        marked_reference=item.text,
        marked_hypothesis=joined,
    )


def score_run(root: Path, run_id: str) -> RunScores:
    """Score one run against the manifest and the script.

    Args:
        root: The corpus root.
        run_id: The run file's stem.

    Returns:
        The run's figures.
    """
    meta, rows = _load(root, run_id)
    takes = {take.take_id: take for take in load_takes(root / MANIFEST_NAME, root)}
    items = {item.id: item for item in load_script()}
    grouped: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in sorted(
        rows, key=lambda r: (str(r["take_id"]), int(r["repeat"]), int(r["clip_index"]))
    ):  # type: ignore[call-overload]  # JSON ints
        grouped[str(row["take_id"]), int(row["repeat"])].append(row)  # type: ignore[call-overload]  # JSON ints
    scored: list[TakeScore] = []
    free = [0, 0, 0, 0]  # errors, words, clips, inaudible
    joined_by_repeat: dict[str, dict[int, str]] = defaultdict(dict)
    for (take_id, repeat), clip_rows in grouped.items():
        take = takes[take_id]
        joined_by_repeat[take_id][repeat] = _joined(clip_rows)
        if repeat != 1:
            continue
        if take.mode == "read" and take.item_id in items:
            scored.append(_score_take(take, items[take.item_id], clip_rows))
            continue
        for row in clip_rows:
            clip = take.clips[int(row["clip_index"])]  # type: ignore[call-overload]  # JSON int
            free[2] += 1
            if clip.inaudible:
                free[3] += 1
            elif clip.reference:
                errors, words = word_errors(clip.reference, str(row["text"]))
                free[0] += errors
                free[1] += words
    compared = [v for v in joined_by_repeat.values() if 1 in v and 2 in v]  # noqa: PLR2004 -- repeat two
    return RunScores(
        run_id=run_id,
        meta=meta,
        takes=scored,
        free_errors=free[0],
        free_words=free[1],
        free_clips=free[2],
        free_inaudible=free[3],
        latencies=[float(row["seconds"]) for row in rows],  # type: ignore[arg-type]  # JSON float
        repeat_changed=sum(v[1] != v[2] for v in compared),
        repeat_compared=len(compared),
    )


def _pct(numerator: float, denominator: float) -> str:
    return "n/a" if not denominator else f"{100 * numerator / denominator:.1f}%"


def _summary(run: RunScores) -> list[str]:
    takes = run.takes
    words = sum(t.words for t in takes)
    pairs = [t.pair_ok for t in takes if t.pair_ok is not None]
    questions = [t for t in takes if t.is_question_ref is not None]
    latencies = sorted(run.latencies)
    p90 = float(np.percentile(latencies, _P90)) if latencies else math.nan
    logprobs = [t.logprob for t in takes if t.logprob is not None]
    lines = [
        f"## {run.run_id}",
        "",
        f"config {run.meta['config']}, half {run.meta['half']}, segmentation "
        f"{run.meta['segmentation'] or 'as captured'}, conditions {run.meta['conditions']}, "
        f"repeat {run.meta['repeat']}; n={len(takes)} read takes, {words} reference words",
    ]
    if run.meta.get("unavailable"):
        return [*lines, "", f"unavailable: {run.meta['unavailable']}", ""]
    lines += [
        "",
        f"- WER {_pct(sum(t.errors for t in takes), words)}; CER "
        f"{_pct(sum(t.char_errors for t in takes), sum(t.chars for t in takes))}",
        f"- exact takes: {sum(t.errors == 0 for t in takes)} of {len(takes)}; empty: "
        f"{sum(t.empty for t in takes)}",
        f"- split turns: {sum(t.split for t in takes)} of {len(takes)}; turn WER (first clip only) "
        f"{_pct(sum(t.turn_errors for t in takes), words)}",
        f"- minimal pairs right: {sum(pairs)} of {len(pairs)}",
        f"- question read right (by «¿?»): "
        f"{sum(t.is_question_hyp == t.is_question_ref for t in questions)} of {len(questions)}",
        f"- flipped «no»: {sum(t.critical.negation_flip for t in takes)}; wrong numbers: "
        f"{sum(t.critical.number_wrong for t in takes)}; «Iroko» lost: "
        f"{sum(t.critical.wake_word_lost for t in takes)}",
        f"- first word lost: {sum(t.edge_first for t in takes)}; last word lost: "
        f"{sum(t.edge_last for t in takes)}",
        f"- seconds per clip: median {median(latencies) if latencies else math.nan:.2f}, p90 "
        f"{p90:.2f}, max {max(latencies) if latencies else math.nan:.2f} (n={len(latencies)})",
        f"- repeatability: {run.repeat_changed} of {run.repeat_compared} takes changed text",
        f"- mean log-probability: {np.mean(logprobs) if logprobs else math.nan:.3f}",
        f"- free clips: {run.free_clips} (inaudible {run.free_inaudible}); WER "
        f"{_pct(run.free_errors, run.free_words)} over {run.free_words} words",
        "",
    ]
    return lines


def _by(runs: Sequence[RunScores], field: str) -> list[str]:
    keys = sorted({getattr(t, field) for run in runs for t in run.takes})
    lines = [f"| {field} | " + " | ".join(run.run_id for run in runs) + " |"]
    lines.append("|---|" + "---|" * len(runs))
    for key in keys:
        cells = []
        for run in runs:
            chosen = [t for t in run.takes if getattr(t, field) == key]
            cells.append(
                f"{_pct(sum(t.errors for t in chosen), sum(t.words for t in chosen))} (n={len(chosen)})"
            )
        lines.append(f"| {key} | " + " | ".join(cells) + " |")
    return [*lines, ""]


def _paired(base: RunScores, other: RunScores) -> tuple[list[TakeScore], list[TakeScore]]:
    shared = {t.take_id for t in base.takes} & {t.take_id for t in other.takes}
    left = sorted((t for t in base.takes if t.take_id in shared), key=lambda t: t.take_id)
    right = sorted((t for t in other.takes if t.take_id in shared), key=lambda t: t.take_id)
    return left, right


def _by_item(takes: Sequence[TakeScore], value: str) -> dict[str, list[tuple[int, int]]]:
    grouped: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for take in takes:
        pair = {
            "wer": (take.errors, take.words),
            "wrong": (int(take.errors > 0), 1),
            "critical": (
                int(
                    take.critical.negation_flip
                    or take.critical.number_wrong
                    or take.critical.wake_word_lost
                ),
                1,
            ),
        }[value]
        grouped[take.item_id].append(pair)
    return grouped


def _compare(base: RunScores, other: RunScores) -> list[str]:
    left, right = _paired(base, other)
    lines = [
        f"### {other.meta['config']} vs {base.meta['config']} ({other.run_id} against {base.run_id})",
        "",
        f"paired takes: {len(left)}, items: {len({t.item_id for t in left})}",
        "",
        "| metric | difference | 95% interval |",
        "|---|---|---|",
    ]
    if not left:
        return [*lines, "| no shared takes | n/a | n/a |", ""]
    for label, value in (("WER", "wer"), ("wrong takes", "wrong"), ("critical takes", "critical")):
        difference, low, high = block_bootstrap_diff(_by_item(left, value), _by_item(right, value))
        lines.append(
            f"| {label} difference | {100 * difference:+.1f} pts | [{100 * low:+.1f}, {100 * high:+.1f}] |"
        )
    z, p = mapsswe([t.errors for t in left], [t.errors for t in right])
    lines += ["", f"MAPSSWE: z {z:+.2f}, p {p:.3f} (negative z favours {other.meta['config']})", ""]
    return lines


def _marks(runs: Sequence[RunScores]) -> list[str]:
    lines = ["| run | «?» F1 | «¿» F1 |", "|---|---|---|"]
    for run in runs:
        scores = mark_scores([(t.marked_reference, t.marked_hypothesis) for t in run.takes])
        lines.append(f"| {run.run_id} | {scores['?'][2]:.2f} | {scores['¿'][2]:.2f} |")
    return [*lines, ""]


def _external(external: Mapping[str, str], label: str) -> list[str]:
    items = {item.id: item for item in load_script()}
    errors = words = 0
    for item_id, text in external.items():
        item = items[item_id]
        wrong, total = word_errors(best_reference((item.text, *item.also), text), text)
        errors += wrong
        words += total
    return [
        f"## Outside reference: {label}",
        "",
        f"outside items: {len(external)}, WER {_pct(errors, words)} over {words} words (no latency)",
        "",
    ]


def render_report(
    root: Path,
    run_ids: Sequence[str],
    baseline: str | None,
    external: Mapping[str, str] | None,
    label: str,
) -> str:
    """Render the Markdown report of one or more runs.

    Args:
        root: The corpus root.
        run_ids: Run file stems.
        baseline: The run every other run is compared with (default: the first).
        external: An outside tool's text per block item (D-20), or ``None``.
        label: The outside tool's name.

    Returns:
        The report; numbers and item ids only, never a spontaneous sentence.
    """
    runs = [score_run(root, run_id) for run_id in run_ids]
    lines = ["# STT bench report (Plan 0069)", ""]
    for run in runs:
        lines += _summary(run)
    lines += [
        "## WER by layer",
        "",
        *_by(runs, "layer"),
        "## WER by condition",
        "",
        *_by(runs, "condition"),
    ]
    lines += ["## Punctuation", "", *_marks(runs)]
    base_id = baseline or run_ids[0]
    base = next(run for run in runs if run.run_id == base_id)
    others = [run for run in runs if run.run_id != base_id]
    if others:
        lines += ["## Against the baseline", ""]
        for other in others:
            lines += _compare(base, other)
    if external:
        lines += _external(external, label)
    return "\n".join(lines)


def _rejected(scored: Sequence[tuple[float, bool]], threshold: float) -> float:
    correct = [score for score, ok in scored if ok]
    return sum(score < threshold for score in correct) / len(correct) if correct else math.nan


def render_calibration(root: Path, run_id: str) -> str:
    """Calibrate the unclear-speech threshold on dev and judge it on test (D-11).

    Args:
        root: The corpus root.
        run_id: The run of the configuration that would be adopted.

    Returns:
        The threshold, the test rates with their sizes and the D-11 verdict.
    """
    run = score_run(root, run_id)
    dev_ids, _test_ids = split_items([item.id for item in load_script()])
    scored = [(t, (t.logprob, t.errors == 0)) for t in run.takes if t.logprob is not None]
    dev = [pair for t, pair in scored if t.item_id in dev_ids]
    test = [pair for t, pair in scored if t.item_id not in dev_ids]
    test_b = [pair for t, pair in scored if t.item_id not in dev_ids and t.layer == "B"]
    result = calibrate_threshold(dev, test, max_false_reject=_MAX_FALSE_REJECT)
    b_false_reject = _rejected(test_b, result.threshold)
    reasons = []
    if result.n_wrong < _MIN_WRONG:
        reasons.append(
            f"fewer than {_MIN_WRONG} clips with a word error in the test half ({result.n_wrong})"
        )
    if not result.false_reject <= _MAX_FALSE_REJECT:
        reasons.append(f"rejects {result.false_reject:.1%} of correct test takes")
    if not (math.isnan(b_false_reject) or b_false_reject <= _MAX_FALSE_REJECT):
        reasons.append(f"rejects {b_false_reject:.1%} of correct short answers (layer B)")
    if not result.catch >= _MIN_CATCH:
        reasons.append(f"catches only {result.catch:.1%} of takes with a word error")
    verdict = (
        "stays off: " + "; ".join(reasons)
        if reasons
        else "meets D-11; it is switched on only when Pipec confirms"
    )
    return "\n".join(
        [
            f"# Unclear-speech calibration ({run_id})",
            "",
            f"threshold (dev, at most {_MAX_FALSE_REJECT:.0%} false rejects): {result.threshold:.3f}",
            f"test: {result.n_correct} correct and {result.n_wrong} wrong takes; false reject "
            f"{result.false_reject:.1%}, catch {result.catch:.1%}; layer B false reject "
            f"{b_false_reject:.1%} (n={len(test_b)})",
            "",
            f"verdict: {verdict}",
        ]
    )
