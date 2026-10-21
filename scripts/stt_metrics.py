"""Speech-to-text metrics and paired statistics for Plan 0069 (D-7, D-9, D-11).

Text is normalized the same way on both sides: Unicode NFC, case folding, punctuation
(«¿» and «¡» included) turned into spaces, spaces collapsed; diacritics are kept unless
``fold_accents`` is set («sí» and «si» are different words). Every rate is pooled — the
sum of errors over the sum of reference units — and every comparison is paired by
script item: the bootstrap resamples whole items, because takes of one item by one
speaker are correlated. No new dependency: Levenshtein is written here.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
import re
from typing import TYPE_CHECKING
import unicodedata

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

MARKS: tuple[str, ...] = ("¿", "?", "¡", "!", ".", ",")
_NON_WORD = re.compile(r"[^\w]+")
_DIGITS = re.compile(r"\d+")
_NUMBER_WORDS = frozenset(
    [
        "cero",
        "uno",
        "una",
        "dos",
        "tres",
        "cuatro",
        "cinco",
        "seis",
        "siete",
        "ocho",
        "nueve",
        "diez",
        "once",
        "doce",
        "trece",
        "catorce",
        "quince",
        "dieciséis",
        "diecisiete",
        "dieciocho",
        "diecinueve",
        "veinte",
        "treinta",
        "cuarenta",
        "cincuenta",
        "sesenta",
        "setenta",
        "ochenta",
        "noventa",
        "cien",
        "ciento",
        "doscientos",
        "trescientos",
        "cuatrocientos",
        "quinientos",
        "seiscientos",
        "setecientos",
        "ochocientos",
        "novecientos",
        "mil",
        "media",
        "cuarto",
    ]
)
_WAKE_WORD = "iroko"


@dataclass(frozen=True)
class CriticalErrors:
    """Errors that change an intention (D-7): a flipped «no», a wrong number, a lost name."""

    negation_flip: bool
    number_wrong: bool
    wake_word_lost: bool


@dataclass(frozen=True)
class CalibrationResult:
    """A rejection threshold chosen on the dev half and measured on the test half (D-11)."""

    threshold: float
    false_reject: float
    catch: float
    n_correct: int
    n_wrong: int


def normalize(text: str, *, fold_accents: bool = False) -> str:
    """Normalize a transcript or a reference for comparison.

    Args:
        text: Any transcript.
        fold_accents: Also strip diacritics (the secondary, accent-folded figure).

    Returns:
        Lower case words separated by single spaces.
    """
    folded = unicodedata.normalize("NFC", text).casefold()
    if fold_accents:
        decomposed = unicodedata.normalize("NFD", folded)
        folded = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(_NON_WORD.sub(" ", folded).replace("_", " ").split())


def _alignment(reference: Sequence[str], hypothesis: Sequence[str]) -> list[list[int]]:
    rows, cols = len(reference) + 1, len(hypothesis) + 1
    cost = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        cost[i][0] = i
    for j in range(cols):
        cost[0][j] = j
    for i in range(1, rows):
        for j in range(1, cols):
            same = reference[i - 1] == hypothesis[j - 1]
            cost[i][j] = min(
                cost[i - 1][j - 1] + (0 if same else 1),
                cost[i - 1][j] + 1,
                cost[i][j - 1] + 1,
            )
    return cost


def word_errors(reference: str, hypothesis: str) -> tuple[int, int]:
    """Count word edits (substitutions, deletions, insertions).

    Args:
        reference: What was said.
        hypothesis: What Whisper wrote.

    Returns:
        (edits, reference word count), both on normalized text.
    """
    ref, hyp = normalize(reference).split(), normalize(hypothesis).split()
    return _alignment(ref, hyp)[len(ref)][len(hyp)], len(ref)


def char_errors(reference: str, hypothesis: str) -> tuple[int, int]:
    """Count character edits on normalized text (spaces included).

    Args:
        reference: What was said.
        hypothesis: What Whisper wrote.

    Returns:
        (edits, reference character count).
    """
    ref, hyp = list(normalize(reference)), list(normalize(hypothesis))
    return _alignment(ref, hyp)[len(ref)][len(hyp)], len(ref)


def best_reference(references: Sequence[str], hypothesis: str) -> str:
    """Pick the written alternative closest to the hypothesis (lowest word error rate).

    Args:
        references: The item's text and its accepted alternatives.
        hypothesis: What Whisper wrote.

    Returns:
        The reference to score against; the first one on a tie.
    """

    def rate(reference: str) -> float:
        edits, words = word_errors(reference, hypothesis)
        return edits / max(words, 1)

    return min(references, key=rate)


def marks(text: str) -> frozenset[str]:
    """Return the punctuation marks of ``¿ ? ¡ ! . ,`` present in *text*."""
    return frozenset(mark for mark in MARKS if mark in text)


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else math.nan


def mark_scores(pairs: Sequence[tuple[str, str]]) -> dict[str, tuple[float, float, float]]:
    """Precision, recall and F1 of each mark, judged per utterance (present or not).

    Args:
        pairs: (reference, hypothesis) per clip, with their punctuation.

    Returns:
        For each mark, (precision, recall, F1); ``nan`` where undefined.
    """
    scores: dict[str, tuple[float, float, float]] = {}
    for mark in MARKS:
        hits = Counter((mark in reference, mark in hypothesis) for reference, hypothesis in pairs)
        tp, fp, fn = hits[True, True], hits[False, True], hits[True, False]
        precision, recall = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
        f1 = (
            math.nan
            if math.isnan(precision) or math.isnan(recall) or precision + recall == 0
            else 2 * precision * recall / (precision + recall)
        )
        scores[mark] = (precision, recall, f1)
    return scores


def _has_phrase(text: str, phrase: str) -> bool:
    return f" {normalize(phrase)} " in f" {normalize(text)} "


def pair_correct(hypothesis: str, target: str, competitor: str) -> bool:
    """Judge one minimal-pair take: the target heard and the competitor not.

    Args:
        hypothesis: What Whisper wrote.
        target: The word or words that were said.
        competitor: What they are confused with.

    Returns:
        True only when the target appears as whole words and the competitor does not.
    """
    return _has_phrase(hypothesis, target) and not _has_phrase(hypothesis, competitor)


def _numbers(text: str) -> Counter[str]:
    return Counter(
        word
        for word in normalize(text).split()
        if _DIGITS.fullmatch(word) or word in _NUMBER_WORDS or word.startswith("veinti")
    )


def critical_errors(reference: str, hypothesis: str, *, numbers: bool) -> CriticalErrors:
    """Find the errors that change what was meant.

    Args:
        reference: The best reference (see ``best_reference``).
        hypothesis: What Whisper wrote.
        numbers: Whether the item is a numbers item (layer E).

    Returns:
        A flipped negation (a different count of the word «no»), a wrong number (number
        words or digit groups that differ) and a lost «Iroko».
    """
    ref_words = normalize(reference).split()
    hyp_words = normalize(hypothesis).split()
    folded_hyp = normalize(hypothesis, fold_accents=True).split()
    return CriticalErrors(
        negation_flip=ref_words.count("no") != hyp_words.count("no"),
        number_wrong=numbers and _numbers(reference) != _numbers(hypothesis),
        wake_word_lost=_WAKE_WORD in normalize(reference, fold_accents=True).split()
        and _WAKE_WORD not in folded_hyp,
    )


def edge_deletions(reference: str, hypothesis: str) -> tuple[bool, bool]:
    """Tell whether the first or the last reference word was deleted in the alignment.

    The signature of a silence filter that eats an onset or a tail (D-7). On equal cost the
    alignment prefers a match or a substitution, so only a true deletion counts.

    Args:
        reference: What was said.
        hypothesis: What Whisper wrote.

    Returns:
        (first word deleted, last word deleted).
    """
    ref, hyp = normalize(reference).split(), normalize(hypothesis).split()
    if not ref:
        return False, False
    cost = _alignment(ref, hyp)
    deleted: set[int] = set()
    i, j = len(ref), len(hyp)
    while i > 0:
        diagonal = cost[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]) if j > 0 else math.inf
        if j > 0 and cost[i][j] == diagonal:
            i, j = i - 1, j - 1
        elif cost[i][j] == cost[i - 1][j] + 1:
            deleted.add(i - 1)
            i -= 1
        else:
            j -= 1
    return 0 in deleted, len(ref) - 1 in deleted


def block_bootstrap_diff(
    a: Mapping[str, Sequence[tuple[int, int]]],
    b: Mapping[str, Sequence[tuple[int, int]]],
    *,
    resamples: int = 2000,
    seed: int = 69,
) -> tuple[float, float, float]:
    """Paired bootstrap of a pooled rate's difference, resampling whole items.

    Args:
        a: The baseline (``P0``): per item, per clip (errors, units).
        b: The candidate on the same items and clips.
        resamples: Bootstrap draws.
        seed: Random seed (results are reproducible).

    Returns:
        (rate(b) - rate(a), 2.5th percentile, 97.5th percentile); negative favours *b*.

    Raises:
        ValueError: If the two sides do not cover the same items.
    """
    if set(a) != set(b):
        raise ValueError("the two configurations must cover the same items")
    items = sorted(a)
    sums = np.array(
        [
            [sum(e for e, _ in side[item]), sum(w for _, w in side[item])]
            for side in (a, b)
            for item in items
        ],
        dtype=np.float64,
    ).reshape(2, len(items), 2)
    observed = sums[1, :, 0].sum() / sums[1, :, 1].sum() - sums[0, :, 0].sum() / sums[0, :, 1].sum()
    draws = np.random.default_rng(seed).integers(0, len(items), size=(resamples, len(items)))
    picked = sums[:, draws, :].sum(axis=2)
    diffs = picked[1, :, 0] / picked[1, :, 1] - picked[0, :, 0] / picked[0, :, 1]
    low, high = np.percentile(diffs, [2.5, 97.5])
    return float(observed), float(low), float(high)


def mapsswe(a: Sequence[int], b: Sequence[int]) -> tuple[float, float]:
    """MAPSSWE at utterance level: a paired z test on per-clip word errors.

    Args:
        a: Word errors per clip, baseline.
        b: Word errors per clip, candidate, same clips in the same order.

    Returns:
        (z, two-sided p); negative z favours *b*.
    """
    differences = np.asarray(b, dtype=np.float64) - np.asarray(a, dtype=np.float64)
    mean = float(differences.mean()) if differences.size else 0.0
    spread = float(differences.std(ddof=1)) if differences.size > 1 else 0.0
    if mean == 0.0:
        return 0.0, 1.0
    if spread == 0.0:
        return math.copysign(math.inf, mean), 0.0
    z = mean / (spread / math.sqrt(differences.size))
    return z, math.erfc(abs(z) / math.sqrt(2))


def rule_of_three(n: int) -> float:
    """The 95 % upper bound on a rate after zero events in *n* trials (3 / n).

    Raises:
        ValueError: If *n* is not positive.
    """
    if n <= 0:
        raise ValueError("the rule of three needs at least one trial")
    return 3 / n


def _reject_rates(scored: Sequence[tuple[float, bool]], threshold: float) -> tuple[float, float]:
    correct = [score for score, ok in scored if ok]
    wrong = [score for score, ok in scored if not ok]
    false_reject = _ratio(sum(score < threshold for score in correct), len(correct))
    catch = _ratio(sum(score < threshold for score in wrong), len(wrong))
    return false_reject, catch


def calibrate_threshold(
    dev: Sequence[tuple[float, bool]],
    test: Sequence[tuple[float, bool]],
    *,
    max_false_reject: float = 0.05,
) -> CalibrationResult:
    """Choose the unclear-speech threshold on dev and measure it on test (D-11).

    A clip is rejected when its score (the clip's mean log-probability) is below the
    threshold. The chosen threshold is the highest one whose dev false-reject rate (fully
    correct clips rejected) stays within the budget.

    Args:
        dev: (score, fully correct) per dev clip.
        test: The same for the test clips.
        max_false_reject: The budget, 0.05 in D-11.

    Returns:
        The threshold, the test false-reject and catch rates and the test counts.
    """
    candidates = sorted({score for score, _ in dev} | {-math.inf})
    if not any(ok for _, ok in dev):
        threshold = (
            -math.inf
        )  # no correct dev clip, so no false-reject rate to budget: reject nothing
    else:
        threshold = max(t for t in candidates if not _reject_rates(dev, t)[0] > max_false_reject)
    false_reject, catch = _reject_rates(test, threshold)
    return CalibrationResult(
        threshold=threshold,
        false_reject=false_reject,
        catch=catch,
        n_correct=sum(ok for _, ok in test),
        n_wrong=sum(not ok for _, ok in test),
    )
