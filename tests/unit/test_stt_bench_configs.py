"""The bench configurations of Plan 0069 Appendix B, one change each from P0 (Task 7)."""

from dataclasses import fields

import pytest
from server.settings import Settings

from scripts.stt_bench_configs import (
    PR_VOCAB_PROMPT,
    SEGMENTATION_POLICIES,
    BenchConfig,
    configs,
    split_items,
)
from scripts.stt_corpus_models import load_script
from scripts.stt_metrics import normalize
from server import stt

_EXPECTED_CHANGES = {
    "T0": {"temperatures"},
    "NS-off": {"no_speech_threshold"},
    "V-off": {"vad_filter"},
    "V-soft": {"vad_threshold", "vad_speech_pad_ms", "vad_min_speech_ms", "vad_min_silence_ms"},
    "PR-none": {"initial_prompt"},
    "PR-vocab": {"initial_prompt"},
    "HW": {"hotwords"},
    "WT": {"word_timestamps"},
    "B1": {"beam_size"},
    "TH8": {"cpu_threads"},
    "F32": {"compute_type"},
    "NORM": {"input_peak_dbfs"},
    "M-medium": {"model"},
    "M-turbo": {"model"},
    "G-small": {"device", "compute_type"},
    "G-turbo": {"model", "device", "compute_type"},
}


def _base() -> stt.WhisperDecodeOptions:
    return stt.decode_options(Settings(_env_file=None))  # type: ignore[call-arg]  # code defaults


def _changes(config: BenchConfig, p0: BenchConfig) -> set[str]:
    top = {f.name for f in fields(BenchConfig) if f.name not in {"name", "options"}}
    changed = {name for name in top if getattr(config, name) != getattr(p0, name)}
    changed |= {
        f.name
        for f in fields(stt.WhisperDecodeOptions)
        if getattr(config.options, f.name) != getattr(p0.options, f.name)
    }
    return changed


@pytest.mark.unit
def test_p0_is_production_today() -> None:
    p0 = configs(_base())["P0"]

    assert (p0.model, p0.device, p0.compute_type, p0.cpu_threads, p0.hotwords) == (
        "small",
        "cpu",
        "int8",
        0,
        None,
    )
    assert p0.options == _base()


@pytest.mark.unit
def test_every_other_configuration_changes_only_what_appendix_b_names() -> None:
    table = configs(_base())

    assert set(table) == {"P0", *_EXPECTED_CHANGES}
    for name, expected in _EXPECTED_CHANGES.items():
        assert _changes(table[name], table["P0"]) == expected, name
    assert table["T0"].options.temperatures == (0.0,)
    assert table["PR-none"].options.initial_prompt is None
    assert table["PR-vocab"].options.initial_prompt == PR_VOCAB_PROMPT
    assert table["NORM"].options.input_peak_dbfs == -3.0
    assert table["G-turbo"].model == "large-v3-turbo"
    assert table["G-turbo"].compute_type == "int8_float16"


@pytest.mark.unit
def test_the_vocabulary_prompt_names_no_scripted_value() -> None:
    assert "helado" not in PR_VOCAB_PROMPT
    assert "sabores" not in PR_VOCAB_PROMPT


@pytest.mark.unit
def test_the_vocabulary_prompt_holds_no_sentence_of_the_reading_script() -> None:
    prompt = normalize(PR_VOCAB_PROMPT)

    leaked = [
        item.id
        for item in load_script()
        if len(item.text.split()) >= 3 and normalize(item.text) in prompt
    ]

    assert leaked == []  # a prompt that holds a scripted sentence inflates its own score


@pytest.mark.unit
def test_the_split_is_stable_disjoint_and_covers_every_item() -> None:
    ids = [f"X{n:02d}" for n in range(40)]

    dev, test = split_items(ids, seed=69)

    assert (dev, test) == split_items(list(reversed(ids)), seed=69)
    assert dev | test == set(ids)
    assert not dev & test
    assert abs(len(dev) - len(test)) <= 2


@pytest.mark.unit
def test_the_segmentation_policies_include_todays() -> None:
    today = SEGMENTATION_POLICIES["close800-tail800-pre400"]

    assert (today.preroll_ms, today.close_silence_ms, today.upload_tail_ms) == (400, 800, 800)
    assert len(SEGMENTATION_POLICIES) == 6
    assert all(
        p.upload_tail_ms >= 300 and p.preroll_ms >= 300 for p in SEGMENTATION_POLICIES.values()
    )
