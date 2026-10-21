"""The bench report and the unclear-threshold calibration (Plan 0069 Task 7, D-7, D-11).

Built from the synthetic corpus and fake transcribers; no private text may leak.
"""

import json
from pathlib import Path

import pytest

from scripts import stt_bench, stt_bench_report
from tests.unit.stt_bench_fixtures import FREE_SENTINEL, FakeTranscriber, build_corpus


def _run(root: Path, name: str, transcriber: FakeTranscriber, run_id: str = "x") -> str:
    path = stt_bench.run_bench(
        [name],
        root=root,
        half="all",
        repeat=2,
        segmentation=None,
        conditions=["max-perf"],
        load_model=lambda _config: object(),
        transcribe=transcriber,
        run_id=run_id,
    )[0]
    return path.stem


@pytest.fixture
def corpus(tmp_path: Path) -> tuple[Path, dict[int, str]]:
    root = tmp_path / "stt"
    return root, build_corpus(root)


@pytest.mark.unit
def test_the_report_states_sizes_and_rates_and_never_free_text(
    corpus: tuple[Path, dict[int, str]],
) -> None:
    root, heard = corpus
    run = _run(root, "P0", FakeTranscriber(heard))

    text = stt_bench_report.render_report(root, [run], None, None, "external")

    assert "WER" in text
    assert "n=4 read takes" in text
    assert "split turns: 1 of 4" in text  # the A02 take came in two clips
    assert "free clips: 1" in text
    assert FREE_SENTINEL not in text
    assert "me dijiste" not in text


@pytest.mark.unit
def test_replayed_free_clips_are_counted_but_not_scored_against_the_captured_references(
    corpus: tuple[Path, dict[int, str]],
) -> None:
    root, heard = corpus
    run = _run(root, "P0", FakeTranscriber(heard))
    runs = root / "results" / "runs"
    meta_path = runs / f"{run}.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["segmentation"] = "close1200-tail300"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    rows = [json.loads(line) for line in (runs / f"{run}.jsonl").read_text("utf-8").splitlines()]
    extra = {**next(row for row in rows if row["mode"] == "free"), "clip_index": 5}
    rows.append(extra)  # a replayed cut can have more clips than the captured one
    (runs / f"{run}.jsonl").write_text(
        chr(10).join(json.dumps(row) for row in rows), encoding="utf-8"
    )

    scores = stt_bench_report.score_run(root, run)

    assert scores.free_clips == 2
    assert (scores.free_errors, scores.free_words) == (0, 0)  # nothing to score the new cut against


@pytest.mark.unit
def test_a_split_take_is_scored_on_its_joined_clips(corpus: tuple[Path, dict[int, str]]) -> None:
    root, heard = corpus
    run = _run(root, "P0", FakeTranscriber(heard))

    scores = stt_bench_report.score_run(root, run)

    joined = next(score for score in scores.takes if score.item_id == "A02")
    assert (joined.errors, joined.split, joined.is_question_hyp) == (0, True, True)
    assert joined.turn_errors > 0  # the robot would have answered «¿Me gusta el» alone
    lost_pair = next(score for score in scores.takes if score.item_id == "D01")
    assert lost_pair.pair_ok is False


@pytest.mark.unit
def test_a_candidate_is_compared_with_the_baseline_by_item(
    corpus: tuple[Path, dict[int, str]],
) -> None:
    root, heard = corpus
    p0 = _run(root, "P0", FakeTranscriber(heard))
    fixed = dict(heard) | {16_480: "dijo helado"}
    t0 = _run(root, "T0", FakeTranscriber(fixed))

    text = stt_bench_report.render_report(root, [p0, t0], p0, None, "external")

    assert "T0 vs P0" in text
    assert "MAPSSWE" in text
    line = next(row for row in text.splitlines() if row.startswith("| WER difference"))
    assert "-" in line.split("|")[2]  # negative favours the candidate


@pytest.mark.unit
def test_an_outside_tool_is_scored_like_a_configuration(
    corpus: tuple[Path, dict[int, str]],
) -> None:
    root, heard = corpus
    run = _run(root, "P0", FakeTranscriber(heard))

    text = stt_bench_report.render_report(
        root, [run], None, {"A01": "Me gusta el helado de chocolate"}, "dictado"
    )

    assert "dictado" in text
    assert "outside items: 1, WER 0.0%" in text


@pytest.mark.unit
def test_the_unclear_reply_stays_off_without_enough_errors(
    corpus: tuple[Path, dict[int, str]],
) -> None:
    root, heard = corpus
    run = _run(root, "P0", FakeTranscriber(heard))

    text = stt_bench_report.render_calibration(root, run)

    assert "stays off" in text
    assert "fewer than 30" in text


@pytest.mark.unit
def test_calibration_pairs_leave_out_split_takes(corpus: tuple[Path, dict[int, str]]) -> None:
    root, heard = corpus
    run = stt_bench_report.score_run(root, _run(root, "P0", FakeTranscriber(heard)))

    pairs = stt_bench_report.calibration_pairs(run)

    split = {take.take_id for take in run.takes if take.split}
    assert split  # the fixture holds one take that came in two clips
    assert {take.take_id for take, _pair in pairs}.isdisjoint(split)
    assert len(pairs) == len([t for t in run.takes if not t.split and t.logprob is not None])
