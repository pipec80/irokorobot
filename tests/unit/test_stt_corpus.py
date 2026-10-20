"""The reading script and the private speech-to-text corpus (Plan 0069 Task 5).

Synthetic signals, a fake VAD and a fake recorder: no microphone, no private audio.
Audio contract: WAV · 16000 Hz · mono · int16.
"""

from dataclasses import replace
import io
import logging
from pathlib import Path
import wave

import numpy as np
import pytest
from robot.audio_capture import CHUNK_FRAMES, SegmentationPolicy

from scripts import check_reserved_terms, stt_corpus
from scripts.speaker_calibration_corpus import sha256_of_file
from scripts.stt_audio_levels import level_report, level_verdicts
from scripts.stt_corpus_models import (
    SCRIPT_PATH,
    Clip,
    ScriptItem,
    Take,
    append_take,
    load_script,
    load_takes,
)

_RATE = 16_000
_LOUD = 30_000


class _LoudVad:
    def detect(self, chunk: np.ndarray) -> bool:
        return bool(np.abs(chunk).max() > 0)


def _take(*parts: tuple[float, int]) -> np.ndarray:
    """Concatenate (seconds, level) parts into an int16 take."""
    return np.concatenate([np.full(int(s * _RATE), v, dtype=np.int16) for s, v in parts])


def _policy(close_ms: int) -> SegmentationPolicy:
    return SegmentationPolicy(preroll_ms=400, close_silence_ms=close_ms, upload_tail_ms=800)


def _clips(raw: np.ndarray, close_ms: int) -> list[bytes]:
    return stt_corpus.segment_take(raw, _policy(close_ms), vad_factory=_LoudVad)


def _wav_bytes(samples: np.ndarray) -> bytes:
    """Int16 samples as WAV bytes — 16 kHz, mono, int16."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(_RATE)
        handle.writeframes(samples.astype(np.int16).tobytes())
    return buffer.getvalue()


@pytest.mark.unit
def test_levels_are_judged_on_the_clips_not_on_the_whole_take() -> None:
    rng = np.random.default_rng(69)

    def noise(seconds: float) -> np.ndarray:
        return rng.normal(0, 30, int(seconds * _RATE))  # about -61 dBFS

    word = 3000 * np.sin(2 * np.pi * 220 * np.arange(int(0.5 * _RATE)) / _RATE)  # -23.8 dBFS
    raw = np.concatenate([noise(3.4), word + noise(0.5), noise(3.1)]).astype(np.int16)
    clip = raw[int(3.0 * _RATE) : int(4.7 * _RATE)]  # pre-roll, the word, the closing silence

    assert level_verdicts(level_report(raw))["speech"] == "low"  # the word is 7 % of the take
    assert stt_corpus.take_verdicts(raw, [_wav_bytes(clip)])["speech"] == "ok"
    assert stt_corpus.take_verdicts(raw, [])["speech"] == "low"  # no clip: the take itself


@pytest.mark.unit
def test_the_reading_script_is_complete_and_consistent() -> None:
    items = load_script()

    assert len({item.id for item in items}) == len(items)
    assert {item.layer for item in items} == set("ABCDEFGH")
    assert sum(item.block for item in items) == 24
    assert sum(item.chat for item in items) == 20
    assert all(item.reps == 5 for item in items if item.layer in "BD")
    assert all(item.target and item.competitor for item in items if item.layer == "D")
    assert all(item.window_s >= 4 for item in items)
    assert sum(item.reps for item in items) == 248
    pairs: dict[str, int] = {}
    for item in items:
        if item.pair:
            pairs[item.pair] = pairs.get(item.pair, 0) + 1
    assert set(pairs.values()) == {2}


@pytest.mark.unit
def test_the_reading_script_holds_no_reserved_term() -> None:
    assert check_reserved_terms.main([str(SCRIPT_PATH)]) == 0


@pytest.mark.unit
def test_a_duplicate_id_is_refused(tmp_path: Path) -> None:
    script = tmp_path / "script.yaml"
    entry = "  - {id: A01, layer: A, kind: statement, text: Hola., reps: 2, window_s: 6}\n"
    script.write_text("version: 1\nitems:\n" + entry + entry, encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate"):
        load_script(script)


@pytest.mark.unit
@pytest.mark.parametrize(
    "gap_s, close_ms, count",
    [(1.2, 800, 2), (1.2, 1600, 1), (2.0, 800, 2), (2.0, 1600, 2)],
)
def test_a_pause_splits_the_take_only_when_it_is_longer_than_the_close(
    gap_s: float, close_ms: int, count: int
) -> None:
    raw = _take((1.0, 0), (0.8, _LOUD), (gap_s, 0), (0.8, _LOUD), (2.0, 0))

    assert len(_clips(raw, close_ms)) == count


@pytest.mark.unit
def test_a_silent_take_gives_no_clip() -> None:
    assert _clips(_take((3.0, 0)), 800) == []


@pytest.mark.unit
def test_speech_that_reaches_the_end_of_the_take_still_closes_one_clip() -> None:
    clips = _clips(_take((1.0, 0), (1.0, _LOUD)), 800)

    assert len(clips) == 1
    assert len(clips[0]) > 44 + 2 * CHUNK_FRAMES * 30  # the whole burst is in it


@pytest.mark.unit
def test_a_take_round_trips_through_the_manifest(tmp_path: Path) -> None:
    take = Take(
        take_id="s1-c60-A01-1",
        session="s1",
        condition="c60",
        style="careful",
        mode="read",
        item_id="A01",
        raw_path="takes/s1-c60-A01-1.wav",
        raw_sha256="ab" * 32,
        clips=(Clip(path="clips/s1-c60-A01-1-1.wav", sha256="cd" * 32),),
        reference="Me gusta el helado de chocolate.",
    )
    manifest = tmp_path / "manifest.jsonl"

    append_take(manifest, tmp_path, take)

    assert load_takes(manifest, tmp_path) == [take]


@pytest.mark.unit
def test_a_take_whose_file_escapes_the_root_is_refused(tmp_path: Path) -> None:
    take = Take(
        take_id="x",
        session="s1",
        condition="c60",
        style="careful",
        mode="read",
        item_id="A01",
        raw_path="../outside.wav",
        raw_sha256="ab" * 32,
        clips=(),
        reference="Hola.",
    )

    with pytest.raises(ValueError, match="escapes"):
        append_take(tmp_path / "root" / "manifest.jsonl", tmp_path / "root", take)


def _item(item_id: str = "A01", **changes: object) -> ScriptItem:
    base = ScriptItem(
        id=item_id, text="Me gusta el helado.", layer="A", kind="statement", reps=2, window_s=4.0
    )
    return replace(base, **changes)  # type: ignore[arg-type]  # field overrides


class _Answers:
    def __init__(self, *answers: str) -> None:
        self._answers = list(answers)
        self.questions: list[str] = []

    def __call__(self, question: str) -> str:
        self.questions.append(question)
        return self._answers.pop(0)


class _Recorder:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, window_s: float, api: str) -> np.ndarray:
        self.calls += 1
        assert api == "mme"
        return _take((1.0, 0), (0.8, _LOUD), (window_s - 0.8, 0))


def _capture(
    root: Path,
    answers: _Answers,
    recorder: _Recorder,
    items: list[ScriptItem] | None = None,
    *,
    block: bool = False,
) -> int:
    return stt_corpus.capture_session(
        items if items is not None else [_item(), _item("A02")],
        root=root,
        session="s1",
        condition="c60",
        style="careful",
        block=block,
        max_takes=1,
        recorder=recorder,
        ask=answers,
        vad_factory=_LoudVad,
    )


@pytest.mark.unit
def test_capture_saves_the_raw_take_its_clips_and_one_manifest_line(tmp_path: Path) -> None:
    root = tmp_path / "stt"

    assert _capture(root, _Answers("", ""), _Recorder()) == 1

    takes = load_takes(root / "manifest.jsonl", root)
    assert len(takes) == 1
    take = takes[0]
    assert (take.session, take.condition, take.style, take.mode) == ("s1", "c60", "careful", "read")
    assert take.deviated is False
    assert take.block is False
    assert sha256_of_file(root / take.raw_path) == take.raw_sha256
    assert len(take.clips) == 1
    assert sha256_of_file(root / take.clips[0].path) == take.clips[0].sha256


@pytest.mark.unit
def test_a_deviated_read_keeps_the_typed_reference(tmp_path: Path) -> None:
    root = tmp_path / "stt"

    _capture(root, _Answers("", "n", "me gusta harto el helado"), _Recorder())

    take = load_takes(root / "manifest.jsonl", root)[0]
    assert take.deviated is True
    assert take.reference == "me gusta harto el helado"


@pytest.mark.unit
def test_a_retake_records_again_and_saves_only_the_kept_take(tmp_path: Path) -> None:
    root = tmp_path / "stt"
    recorder = _Recorder()

    _capture(root, _Answers("r", "", ""), recorder)

    assert recorder.calls == 2
    assert len(load_takes(root / "manifest.jsonl", root)) == 1


@pytest.mark.unit
def test_capture_resumes_where_it_stopped(tmp_path: Path) -> None:
    root = tmp_path / "stt"
    items = [_item(reps=1)]

    _capture(root, _Answers("", ""), _Recorder(), items=items)
    second = _capture(root, _Answers(), _Recorder(), items=items)

    assert second == 0
    assert len(load_takes(root / "manifest.jsonl", root)) == 1


def _read_take(item_id: str, *, session: str, block: bool) -> Take:
    return Take(
        take_id=f"{session}-c60-careful-{item_id}-1",
        session=session,
        condition="c60",
        style="careful",
        mode="read",
        item_id=item_id,
        raw_path="takes/unused.wav",
        raw_sha256="",
        clips=(),
        reference=None,
        block=block,
    )


@pytest.mark.unit
def test_block_takes_do_not_count_toward_the_main_reps() -> None:
    pilot = [_read_take("A01", session="s0", block=True)]

    pending = stt_corpus.pending_items(
        [_item(block=True)], pilot, session="s1", condition="c60", style="careful", block=False
    )

    assert [item.id for item in pending] == ["A01", "A01"]  # D-5: the 248 main takes stay whole


@pytest.mark.unit
def test_the_block_wants_each_item_once_per_condition_over_every_session() -> None:
    items = [_item(block=True), _item("A02", block=True), _item("A03")]
    takes = [
        _read_take("A01", session="s0", block=True),  # the pilot: the block's c60 cell (D-6)
        _read_take("A02", session="s1", block=False),  # a main take is not a block take
    ]

    def block_pending(condition: str) -> list[str]:
        pending = stt_corpus.pending_items(
            items, takes, session="s3", condition=condition, style="careful", block=True
        )
        return sorted(item.id for item in pending)

    assert block_pending("c60") == ["A02"]
    assert block_pending("c30") == ["A01", "A02"]


@pytest.mark.unit
def test_a_block_capture_is_marked_and_validate_leaves_it_out_of_the_main_count(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = tmp_path / "stt"
    items = [_item(reps=1, block=True)]
    caplog.set_level(logging.INFO, logger=stt_corpus.logger.name)

    _capture(root, _Answers("", ""), _Recorder(), items=items, block=True)

    assert load_takes(root / "manifest.jsonl", root)[0].block is True
    assert stt_corpus.validate(root, items) == 0
    assert "main condition: 1 items under their reps" in caplog.text
    assert "block" in caplog.text


@pytest.mark.unit
def test_a_free_session_is_one_take_cut_into_clips(tmp_path: Path) -> None:
    root = tmp_path / "stt"

    def recorder(seconds: float, api: str) -> np.ndarray:
        assert (seconds, api) == (60.0, "mme")
        return _take((1.0, 0), (0.8, _LOUD), (2.0, 0), (0.8, _LOUD), (2.0, 0))

    clips = stt_corpus.free_session(root, "s4", 1.0, recorder, vad_factory=_LoudVad)

    take = load_takes(root / "manifest.jsonl", root)[0]
    assert clips == 2
    assert (take.mode, take.item_id, take.reference, len(take.clips)) == ("free", None, None, 2)


@pytest.mark.unit
def test_annotate_keeps_the_typed_reference_the_continuation_and_inaudible(
    tmp_path: Path,
) -> None:
    root = tmp_path / "stt"
    raw = _take((1.0, 0), (0.8, _LOUD), (2.0, 0), (0.8, _LOUD), (2.0, 0))
    stt_corpus.free_session(root, "s4", 1.0, lambda _s, _a: raw, vad_factory=_LoudVad)
    played: list[Path] = []

    done = stt_corpus.annotate(
        root, "s4", _Answers("", "me gusta", "s", "inaudible", "n"), play=played.append
    )

    clips = load_takes(root / "manifest.jsonl", root)[0].clips
    assert done == 2
    assert len(played) == 3  # an empty answer plays the clip again
    assert (clips[0].reference, clips[0].continued, clips[0].inaudible) == ("me gusta", True, False)
    assert (clips[1].reference, clips[1].continued, clips[1].inaudible) == (None, False, True)


@pytest.mark.unit
def test_validate_finds_a_changed_file(tmp_path: Path) -> None:
    root = tmp_path / "stt"
    _capture(root, _Answers("", ""), _Recorder())
    items = [_item(), _item("A02")]
    assert stt_corpus.validate(root, items) == 0

    take = load_takes(root / "manifest.jsonl", root)[0]
    (root / take.raw_path).write_bytes(b"changed")

    assert stt_corpus.validate(root, items) == 1


@pytest.mark.unit
@pytest.mark.parametrize("answer", ["", "yes", "Delete", "delete "])
def test_cleanup_deletes_nothing_without_the_exact_word(tmp_path: Path, answer: str) -> None:
    root = tmp_path / "stt"
    (root / "takes").mkdir(parents=True)
    (root / "takes" / "a.wav").write_bytes(b"x")

    assert stt_corpus.cleanup(root, ask=lambda _q: answer) == 1
    assert (root / "takes" / "a.wav").exists()


@pytest.mark.unit
def test_cleanup_deletes_the_corpus_on_the_exact_word(tmp_path: Path) -> None:
    root = tmp_path / "stt"
    (root / "takes").mkdir(parents=True)
    (root / "takes" / "a.wav").write_bytes(b"x")

    assert stt_corpus.cleanup(root, ask=lambda _q: "delete") == 0
    assert not root.exists()
