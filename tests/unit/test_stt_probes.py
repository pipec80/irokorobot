"""Pure helpers of the STT probes (Plan 0056, Task 6)."""

import io
import wave

import pytest

from scripts.stt_probes import (
    noise_clip,
    summarize_first_turn,
    summarize_noise,
    word_error_rate,
)

_PROMPT = "Conversación con un robot doméstico llamado Iroko."


@pytest.mark.unit
@pytest.mark.parametrize("kind", ["white", "hiss", "pink", "hum"])
def test_noise_clips_honour_the_audio_contract(kind: str) -> None:
    with wave.open(io.BytesIO(noise_clip(kind, 1.5, 1))) as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2)
        assert wav.getnframes() == 24000


@pytest.mark.unit
def test_noise_clips_are_deterministic_per_seed_and_differ_across_seeds() -> None:
    assert noise_clip("white", 1.0, 1) == noise_clip("white", 1.0, 1)
    assert noise_clip("white", 1.0, 1) != noise_clip("white", 1.0, 2)


@pytest.mark.unit
def test_an_unknown_noise_kind_is_rejected() -> None:
    with pytest.raises(ValueError, match="kind"):
        noise_clip("brown", 1.0, 1)


@pytest.mark.unit
@pytest.mark.parametrize(
    "reference, hypothesis, rate",
    [
        ("a b c", "a b c", 0.0),
        ("a b c", "a x c", 1 / 3),
        ("a b c", "", 1.0),
        ("Qué hora es", "que HORA es.", 0.0),
    ],
)
def test_word_error_rate(reference: str, hypothesis: str, rate: float) -> None:
    assert word_error_rate(reference, hypothesis) == pytest.approx(rate)


@pytest.mark.unit
def test_word_error_rate_needs_a_reference() -> None:
    with pytest.raises(ValueError, match="reference"):
        word_error_rate("", "hola")


@pytest.mark.unit
def test_summarize_noise_separates_empty_echo_and_other() -> None:
    summary = summarize_noise(["", _PROMPT, "Gracias por ver el video", ""], _PROMPT)

    assert (summary.clips, summary.empty, summary.echo, summary.other) == (4, 2, 1, 1)
    assert summary.other_rate == pytest.approx(0.25)
    assert summary.needs_follow_up is True  # 25 % is above the 5 % rule


@pytest.mark.unit
def test_noise_follow_up_needs_more_than_five_percent_of_clips_to_be_other() -> None:
    assert summarize_noise(["x y z"] * 6 + [""] * 94, _PROMPT).needs_follow_up is True
    assert summarize_noise(["x y z"] * 5 + [""] * 95, _PROMPT).needs_follow_up is False


def _run(first: float, later: float, *, rounds: int = 2) -> list[tuple[int, float]]:
    """One fresh process: three phrases per round, the first call scoring ``first``."""
    calls = [(index % 3, later) for index in range(3 * rounds)]
    calls[0] = (0, first)
    return calls


@pytest.mark.unit
def test_first_turn_follow_up_needs_the_first_call_to_be_clearly_worse() -> None:
    worse = summarize_first_turn([_run(0.75, 0.5), _run(0.75, 0.5)])
    close = summarize_first_turn([_run(0.625, 0.5), _run(0.625, 0.5)])

    assert worse.delta_mean == pytest.approx(0.25)
    assert worse.needs_follow_up is True
    assert close.delta_mean == pytest.approx(0.125)
    assert close.needs_follow_up is False


@pytest.mark.unit
def test_the_comparison_is_the_same_phrase_inside_the_same_process() -> None:
    """A hard phrase that is hard on every call is not a first-turn effect."""
    run = [(0, 0.5), (1, 0.0), (2, 0.0), (0, 0.5), (1, 0.0), (2, 0.0)]

    assert summarize_first_turn([run]).delta_mean == pytest.approx(0.0)


@pytest.mark.unit
def test_uniformly_bad_transcription_is_flagged_as_accuracy_not_as_a_first_turn_effect() -> None:
    """Every call equally wrong never opens the warm-up follow-up, but is reported."""
    summary = summarize_first_turn([_run(0.75, 0.75)] * 3)

    assert summary.needs_follow_up is False
    assert summary.accuracy_flag is True
    assert summary.overall_mean == pytest.approx(0.75)


@pytest.mark.unit
def test_good_transcription_raises_no_flag() -> None:
    summary = summarize_first_turn([_run(0.0, 0.0)] * 3)

    assert (summary.needs_follow_up, summary.accuracy_flag) == (False, False)


@pytest.mark.unit
def test_a_process_with_no_later_call_of_the_first_phrase_is_rejected() -> None:
    with pytest.raises(ValueError, match="later"):
        summarize_first_turn([[(0, 0.1), (1, 0.1), (2, 0.1)]])
