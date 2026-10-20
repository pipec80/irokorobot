"""The capture auditor CLI (Plan 0069 Task 4): devices, saved takes and Whisper options.

A fake sounddevice and a fake recorder stand in for the microphone; nothing is recorded.
Audio contract: WAV · 16000 Hz · mono · int16.
"""

from collections.abc import Generator
from contextlib import contextmanager
import json
import logging
from pathlib import Path
from types import SimpleNamespace
import wave

import numpy as np
import pytest
from server.settings import Settings

from scripts import mic_test
from server import stt

_DEVICES = [
    {"name": "Speakers", "hostapi": 0, "max_input_channels": 0, "default_samplerate": 48_000.0},
    {
        "name": "Microphone Array",
        "hostapi": 0,
        "max_input_channels": 4,
        "default_samplerate": 44_100.0,
    },
    {
        "name": "Microphone Array",
        "hostapi": 1,
        "max_input_channels": 4,
        "default_samplerate": 48_000.0,
    },
]
_HOST_APIS = [{"name": "MME"}, {"name": "Windows WASAPI"}]


def _fake_sd() -> SimpleNamespace:
    return SimpleNamespace(
        query_devices=lambda: _DEVICES,
        query_hostapis=lambda index: _HOST_APIS[index],
        default=SimpleNamespace(device=(1, 0)),
    )


def _never(*_args: object) -> tuple[np.ndarray, int]:
    raise AssertionError("nothing may be recorded")


def _silence(_api: str, seconds: float) -> tuple[np.ndarray, int]:
    return np.zeros(int(seconds * 16_000), dtype=np.int16), 16_000


class _Events(logging.Handler):
    """Keeps what the operator is shown, in order, beside what the stream reads."""

    def __init__(self, events: list[str]) -> None:
        super().__init__(logging.INFO)
        self.events = events

    def emit(self, record: logging.LogRecord) -> None:
        self.events.append(record.getMessage().strip())


class _FakeStream:
    """A started stream that returns silence and notes every read."""

    def __init__(self, events: list[str]) -> None:
        self.events = events

    def read(self, frames: int) -> tuple[np.ndarray, bool]:
        self.events.append(f"read {frames}")
        return np.zeros((frames, 1), dtype=np.int16), False


@pytest.fixture
def corpus_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "stt"
    monkeypatch.setattr(mic_test, "STT_CORPUS_ROOT", root)
    monkeypatch.setattr(mic_test, "sd", _fake_sd())
    return root


@pytest.mark.unit
@pytest.mark.usefixtures("corpus_root")
def test_devices_lists_every_input_with_its_host_api_and_the_default() -> None:
    inputs = mic_test.list_inputs()

    assert [(d.index, d.host_api, d.channels, d.default_rate, d.is_default) for d in inputs] == [
        (1, "MME", 4, 44_100, True),
        (2, "Windows WASAPI", 4, 48_000, False),
    ]


@pytest.mark.unit
def test_devices_save_writes_the_dump_under_the_corpus_root(corpus_root: Path) -> None:
    assert mic_test.main(["devices", "--save"]) == 0

    dump = json.loads((corpus_root / "mic" / "devices.json").read_text(encoding="utf-8"))
    assert [entry["host_api"] for entry in dump] == ["MME", "Windows WASAPI"]


@pytest.mark.unit
def test_a_save_name_that_escapes_the_corpus_root_is_refused_before_recording(
    corpus_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mic_test, "record", _never)

    with pytest.raises(SystemExit):
        mic_test.main(["record", "--save", "../escape"])
    assert not corpus_root.exists() or not any(corpus_root.rglob("*"))


@pytest.mark.unit
def test_an_existing_take_is_refused_before_recording_unless_replaced(
    corpus_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = corpus_root / "mic" / "take1.wav"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"old take")
    monkeypatch.setattr(mic_test, "record", _never)

    with pytest.raises(SystemExit, match="--replace"):
        mic_test.main(["record", "--save", "take1"])
    assert target.read_bytes() == b"old take"

    monkeypatch.setattr(mic_test, "record", _silence)
    assert mic_test.main(["record", "--seconds", "1", "--save", "take1", "--replace"]) == 0
    with wave.open(str(target), "rb") as handle:
        assert handle.getnframes() == 16_000


@pytest.mark.unit
def test_record_shows_the_phrase_to_read_before_the_take(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    shown: list[str] = []

    def _record(api: str, seconds: float) -> tuple[np.ndarray, int]:
        shown.append(caplog.text)
        return _silence(api, seconds)

    monkeypatch.setattr(mic_test, "record", _record)
    caplog.set_level(logging.INFO, logger=mic_test.logger.name)

    mic_test.main(["record", "--seconds", "1"])
    mic_test.main(["record", "--seconds", "1", "--phrase", "Hola", "Iroko"])

    assert mic_test.LEVEL_PHRASE == "Me gusta el helado de chocolate."
    assert mic_test.LEVEL_PHRASE in shown[0]
    assert "Hola Iroko" in shown[1]
    assert ">>> HABLA <<<" in shown[0]


@pytest.mark.unit
def test_record_settles_counts_down_and_cues_before_the_window(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    events: list[str] = []

    @contextmanager
    def _open(_api: str) -> Generator[tuple[_FakeStream, int]]:
        yield _FakeStream(events), 16_000

    monkeypatch.setattr(mic_test, "open_input", _open)
    caplog.set_level(logging.INFO, logger=mic_test.logger.name)
    handler = _Events(events)
    mic_test.logger.addHandler(handler)
    try:
        samples, rate = mic_test.record("mme", 2.0)
    finally:
        mic_test.logger.removeHandler(handler)

    assert events == [
        "read 8000",  # the device settles; nothing is shown and nothing is kept
        "3 ...",
        "read 16000",
        "2 ...",
        "read 16000",
        "1 ...",
        "read 16000",
        ">>> HABLA <<<",
        "read 32000",
        "listo",
    ]
    assert (len(samples), rate) == (3 * 16_000 + 2 * 16_000, 16_000)


@pytest.mark.unit
def test_record_saves_a_contract_wav_and_prints_the_levels(
    corpus_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tone = (3000 * np.sin(2 * np.pi * 440 * np.arange(16_000) / 16_000)).astype(np.int16)
    monkeypatch.setattr(mic_test, "record", lambda _api, _seconds: (tone, 16_000))

    assert mic_test.main(["record", "--seconds", "1", "--save", "take1"]) == 0

    with wave.open(str(corpus_root / "mic" / "take1.wav"), "rb") as handle:
        assert (handle.getframerate(), handle.getnchannels(), handle.getsampwidth()) == (
            16_000,
            1,
            2,
        )
        assert handle.getnframes() == 16_000
    assert "peak" in capsys.readouterr().out


@pytest.mark.unit
def test_free_text_flags_take_several_words() -> None:
    args = mic_test.parse_args(["record", "--prompt", "Hola", "Iroko", "--hotwords", "sí", "no"])

    assert args.prompt == ["Hola", "Iroko"]
    assert args.hotwords == ["sí", "no"]


@pytest.mark.unit
def test_whisper_options_start_from_production_and_apply_only_the_overrides() -> None:
    base = stt.decode_options(Settings(_env_file=None))  # type: ignore[call-arg]  # code defaults
    args = mic_test.parse_args(["record", "--beam-size", "1", "--prompt", "Hola", "Iroko"])

    options = mic_test.whisper_options(args, base)

    assert options.beam_size == 1
    assert options.initial_prompt == "Hola Iroko"
    assert options.vad_min_silence_ms == base.vad_min_silence_ms
    assert mic_test.whisper_options(mic_test.parse_args(["record"]), base) == base
