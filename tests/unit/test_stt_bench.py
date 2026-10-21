"""The deterministic STT bench runner (Plan 0069 Task 7).

A fake loader and a fake transcriber stand in for Whisper; the corpus is synthetic.
Audio contract: WAV · 16000 Hz · mono · int16.
"""

import json
from pathlib import Path

import numpy as np
import pytest
from robot.audio_capture import SegmentationPolicy

from scripts import stt_bench
from scripts.stt_corpus_models import load_script
from tests.unit.stt_bench_fixtures import FakeTranscriber, build_corpus


class _Loader:
    def __init__(self, fail_on: str | None = None) -> None:
        self.loads: list[tuple[str, str, str, int]] = []
        self.fail_on = fail_on

    def __call__(self, config: stt_bench.BenchConfig) -> object:
        if config.model == self.fail_on:
            raise RuntimeError("model not available")
        self.loads.append((config.model, config.device, config.compute_type, config.cpu_threads))
        return object()


def _lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def corpus(tmp_path: Path) -> tuple[Path, FakeTranscriber]:
    root = tmp_path / "stt"
    return root, FakeTranscriber(build_corpus(root))


@pytest.mark.unit
def test_run_loads_each_model_once_and_writes_one_line_per_clip_and_repeat(
    corpus: tuple[Path, FakeTranscriber],
) -> None:
    root, transcriber = corpus
    loader = _Loader()

    paths = stt_bench.run_bench(
        ["P0", "T0"],
        root=root,
        half="all",
        repeat=2,
        segmentation=None,
        conditions=["max-perf", "charger"],
        load_model=loader,
        transcribe=transcriber,
        run_id="t",
    )

    assert loader.loads == [("small", "cpu", "int8", 0)]
    rows = [row for path in paths for row in _lines(path)]
    assert len(rows) == 6 * 2 * 2  # six clips, two repeats, two configurations
    assert transcriber.calls == len(rows) + 2  # one untimed warm-up per configuration
    first = rows[0]
    assert {"config", "take_id", "clip_index", "repeat", "text", "avg_logprob", "seconds"} <= set(
        first
    )
    assert "peak_working_set_mb" in first
    assert first["conditions"] == ["max-perf", "charger"]


@pytest.mark.unit
def test_a_model_that_fails_to_load_is_unavailable_not_a_crash(
    corpus: tuple[Path, FakeTranscriber],
) -> None:
    root, transcriber = corpus

    paths = stt_bench.run_bench(
        ["M-medium", "P0"],
        root=root,
        half="all",
        repeat=1,
        segmentation=None,
        conditions=[],
        load_model=_Loader(fail_on="medium"),
        transcribe=transcriber,
        run_id="u",
    )

    meta = json.loads(paths[0].with_suffix(".meta.json").read_text(encoding="utf-8"))
    assert meta["unavailable"] == "RuntimeError"
    assert _lines(paths[0]) == []
    assert len(_lines(paths[1])) == 6


@pytest.mark.unit
def test_a_half_keeps_only_its_items_and_the_free_takes(
    corpus: tuple[Path, FakeTranscriber],
) -> None:
    root, transcriber = corpus
    dev, _test = stt_bench.split_items([item.id for item in load_script()])

    paths = stt_bench.run_bench(
        ["P0"],
        root=root,
        half="dev",
        repeat=1,
        segmentation=None,
        conditions=[],
        load_model=_Loader(),
        transcribe=transcriber,
        run_id="d",
    )

    for row in _lines(paths[0]):
        assert row["item_id"] is None or row["item_id"] in dev


@pytest.mark.unit
def test_the_free_half_runs_only_the_free_takes(corpus: tuple[Path, FakeTranscriber]) -> None:
    root, transcriber = corpus

    paths = stt_bench.run_bench(
        ["P0"],
        root=root,
        half="free",
        repeat=1,
        segmentation=None,
        conditions=[],
        load_model=_Loader(),
        transcribe=transcriber,
        run_id="f",
    )

    rows = _lines(paths[0])
    assert rows
    assert {row["mode"] for row in rows} == {"free"}


@pytest.mark.unit
def test_probe_times_a_synthetic_clip_four_times() -> None:
    transcriber = FakeTranscriber({})

    result = stt_bench.probe("small", "cpu", "int8", load_model=_Loader(), transcribe=transcriber)

    assert len(result.timings) == 4
    assert result.load_s >= 0
    assert result.vram_peak_mb is None
    assert transcriber.calls == 5  # one warm-up, four timed


@pytest.mark.unit
def test_the_external_template_lists_the_block_items_and_reads_back_filled(tmp_path: Path) -> None:
    template = stt_bench.write_external_template(tmp_path, load_script())
    lines = template.read_text(encoding="utf-8").splitlines()
    ids = [line.split("\t")[0] for line in lines if line and not line.startswith("#")]
    assert len(ids) == 24
    filled = template.read_text(encoding="utf-8").replace("A01\t", "A01\tme gusta el helado")

    template.write_text(filled, encoding="utf-8")

    assert stt_bench.load_external(template)["A01"] == "me gusta el helado"


class _LoudVad:
    def detect(self, chunk: np.ndarray) -> bool:
        return bool(np.abs(chunk).max() > 0)


@pytest.mark.unit
def test_speech_gaps_measure_the_pauses_between_bursts() -> None:
    def part(seconds: float, level: int) -> np.ndarray:
        return np.full(int(seconds * 16_000), level, dtype=np.int16)

    raw = np.concatenate(
        [part(0.5, 0), part(0.6, 30_000), part(1.2, 0), part(0.6, 30_000), part(0.5, 0)]
    )

    gaps = stt_bench.speech_gaps(raw, vad_factory=_LoudVad)

    assert len(gaps) == 1
    assert gaps[0] == pytest.approx(1.2, abs=0.065)  # resolution: one 32 ms chunk at each edge


@pytest.mark.unit
def test_segment_writes_the_clips_of_a_policy_and_their_index(
    corpus: tuple[Path, FakeTranscriber],
) -> None:
    root, _transcriber = corpus
    policies = {
        "close800": SegmentationPolicy(preroll_ms=400, close_silence_ms=800, upload_tail_ms=800)
    }

    index = stt_bench.segment_policies(root, policies, vad_factory=_LoudVad)

    assert set(index["close800"]) == {
        "s1-c60-careful-A01-1",
        "s1-c60-careful-A02-2",
        "s1-c60-careful-D01-3",
        "s1-c60-careful-B05-4",
        "s4-free",
    }
    assert all(entry["clips"] == [] for entry in index["close800"].values())  # silent raw takes
    assert (root / "results" / "segments" / "close800.json").exists()
