"""Speech-to-text metrics and paired statistics (Plan 0069 Task 6, D-7).

Hand-computed values only; no audio.
"""

import math

import pytest

from scripts.stt_metrics import (
    best_reference,
    block_bootstrap_diff,
    calibrate_threshold,
    char_errors,
    critical_errors,
    edge_deletions,
    mapsswe,
    mark_scores,
    marks,
    normalize,
    pair_correct,
    rule_of_three,
    word_errors,
)


@pytest.mark.unit
def test_normalize_drops_punctuation_and_case_and_keeps_accents() -> None:
    assert normalize("¿Qué hora es?") == "qué hora es"
    assert normalize("  Son las 3:30,  ¡ya!  ") == "son las 3 30 ya"
    assert normalize("¿Qué?", fold_accents=True) == "que"


@pytest.mark.unit
def test_word_errors_count_edits_against_the_reference() -> None:
    assert word_errors("Me gusta el helado.", "me gusta de lado") == (2, 4)
    assert word_errors("hola", "") == (1, 1)
    assert word_errors("hola", "hola") == (0, 1)


@pytest.mark.unit
def test_an_accent_is_an_error_unless_folded() -> None:
    assert word_errors("sí", "si") == (1, 1)
    assert word_errors(normalize("sí", fold_accents=True), normalize("si", fold_accents=True)) == (
        0,
        1,
    )


@pytest.mark.unit
def test_char_errors_count_characters() -> None:
    assert char_errors("sabores", "sabore") == (1, 7)


@pytest.mark.unit
def test_the_closest_written_alternative_is_the_reference() -> None:
    refs = ["son las tres y media", "son las 3 y media"]

    assert best_reference(refs, "son las 3 y media") == "son las 3 y media"
    assert best_reference(refs, "son las tres y media") == "son las tres y media"


@pytest.mark.unit
def test_marks_and_their_scores_per_utterance() -> None:
    assert marks("¿Sí? ¡Ya!") == {"¿", "?", "¡", "!"}
    pairs = [("¿Me gusta?", "¿Me gusta?"), ("Me gusta.", "¿Me gusta?"), ("¿Hola?", "Hola.")]

    scores = mark_scores(pairs)

    precision, recall, f1 = scores["?"]
    assert (precision, recall) == (0.5, 0.5)
    assert f1 == pytest.approx(0.5)
    assert math.isnan(scores["!"][0])


@pytest.mark.unit
def test_a_minimal_pair_needs_the_target_and_not_the_competitor() -> None:
    assert pair_correct("dijo de lado", "helado", "de lado") is False
    assert pair_correct("Dijo helado.", "helado", "de lado") is True
    assert pair_correct("me gustan los sabores", "sabores", "sabore") is True
    assert pair_correct("me gustan los sabore", "sabores", "sabore") is False


@pytest.mark.unit
def test_critical_errors_flag_a_lost_no_a_wrong_number_and_a_lost_name() -> None:
    lost_no = critical_errors(
        "No quiero que apagues la luz.", "quiero que apagues la luz", numbers=False
    )
    wrong_number = critical_errors("son las 3 y media", "son las 2 y media", numbers=True)
    lost_name = critical_errors("Iroko, ¿me escuchas?", "y roco me escuchas", numbers=False)
    fine = critical_errors("son las 3 y media", "Son las 3 y media.", numbers=True)

    assert lost_no.negation_flip is True
    assert wrong_number.number_wrong is True
    assert lost_name.wake_word_lost is True
    assert (fine.negation_flip, fine.number_wrong, fine.wake_word_lost) == (False, False, False)


@pytest.mark.unit
def test_edge_deletions_find_a_lost_first_or_last_word() -> None:
    assert edge_deletions("sí autorizo que lo guardes", "autorizo que lo") == (True, True)
    assert edge_deletions("sí autorizo que lo guardes", "si autorizo que lo guardes") == (
        False,
        False,
    )
    assert edge_deletions("me gusta el helado", "me gusta el") == (False, True)


@pytest.mark.unit
def test_the_block_bootstrap_is_reproducible_and_paired() -> None:
    a = {f"i{n}": [(1, 10), (1, 10)] for n in range(40)}
    b = {f"i{n}": [(0, 10), (1, 10)] for n in range(40)}

    first = block_bootstrap_diff(a, b, resamples=500, seed=69)
    again = block_bootstrap_diff(a, b, resamples=500, seed=69)
    same = block_bootstrap_diff(a, a, resamples=500)

    assert first == again
    difference, low, high = first
    assert difference == pytest.approx(-0.05)
    assert low <= -0.05 <= high
    assert same == (0.0, 0.0, 0.0)


@pytest.mark.unit
def test_the_bootstrap_refuses_unpaired_items() -> None:
    with pytest.raises(ValueError, match="same items"):
        block_bootstrap_diff({"a": [(0, 1)]}, {"b": [(0, 1)]})


@pytest.mark.unit
def test_mapsswe_is_zero_for_identical_systems_and_signed_otherwise() -> None:
    assert mapsswe([1, 0, 2], [1, 0, 2]) == (0.0, 1.0)
    z, p = mapsswe([2, 2, 3, 2, 3, 2], [1, 1, 1, 1, 2, 1])
    assert z < 0
    assert p < 0.05


@pytest.mark.unit
def test_rule_of_three() -> None:
    assert rule_of_three(100) == 0.03
    with pytest.raises(ValueError, match="at least one trial"):
        rule_of_three(0)


@pytest.mark.unit
def test_calibration_picks_the_highest_threshold_within_the_false_reject_budget() -> None:
    correct = [(round(-0.1 * i, 1), True) for i in range(1, 21)]  # -0.1 … -2.0
    wrong = [(-1.5, False), (-2.5, False), (-3.0, False)]

    result = calibrate_threshold(correct + wrong, correct + wrong, max_false_reject=0.05)

    assert result.threshold == pytest.approx(-1.9)
    assert result.false_reject == pytest.approx(1 / 20)
    assert result.catch == pytest.approx(2 / 3)
    assert (result.n_correct, result.n_wrong) == (20, 3)


@pytest.mark.unit
def test_calibration_without_a_correct_dev_clip_rejects_nothing() -> None:
    dev = [(-0.2, False), (-0.9, False)]  # no correct clip: no false-reject rate to budget
    test = [(-0.3, True), (-0.8, False)]

    result = calibrate_threshold(dev, test)

    assert result.threshold == float("-inf")
    assert (result.false_reject, result.catch) == (0.0, 0.0)
