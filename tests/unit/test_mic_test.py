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
_HOST_APIS = [
    {"name": "MME", "default_input_device": 1},
    {"name": "Windows WASAPI", "default_input_device": 2},
]


class _OpenedStream:
    """Stands in for ``sd.InputStream`` once opened: only its rate is read."""

    def __init__(self, samplerate: float) -> None:
        self.samplerate = samplerate

    def __enter__(self) -> "_OpenedStream":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _fake_sd(opened: list[dict[str, object]] | None = None) -> SimpleNamespace:
    def _input_stream(**kwargs: object) -> _OpenedStream:
        if opened is not None:
            opened.append(kwargs)
        return _OpenedStream(float(str(kwargs["samplerate"])))

    return SimpleNamespace(
        query_devices=lambda: _DEVICES,
        query_hostapis=lambda index=None: _HOST_APIS if index is None else _HOST_APIS[index],
        default=SimpleNamespace(device=(1, 0)),
        InputStream=_input_stream,
        WasapiSettings=lambda **settings: settings,
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
    """A started mono stream that returns silence, notes every read and can overflow."""

    channels = 1

    def __init__(self, events: list[str], overflowing_reads: frozenset[int] = frozenset()) -> None:
        self.events = events
        self.overflowing_reads = overflowing_reads

    def read(self, frames: int) -> tuple[np.ndarray, bool]:
        self.events.append(f"read {frames}")
        overflowed = len(self.events) in self.overflowing_reads
        return np.zeros((frames, 1), dtype=np.int16), overflowed


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
def test_record_warns_when_the_stream_lost_audio(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    ticks = iter([0.0, 30.0])

    @contextmanager
    def _open(_api: str) -> Generator[tuple[_FakeStream, int]]:
        yield _FakeStream([], overflowing_reads=frozenset({2})), 16_000

    monkeypatch.setattr(mic_test, "open_input", _open)
    monkeypatch.setattr(mic_test, "_clock", lambda: next(ticks))
    caplog.set_level(logging.INFO, logger=mic_test.logger.name)

    mic_test.record("mme", 2.0)

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "1 overflow" in warnings[0]
    assert "5.0 s of audio took 30.0 s" in warnings[0]


@pytest.mark.unit
def test_wasapi_opens_the_device_in_its_native_format(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[dict[str, object]] = []
    monkeypatch.setattr(mic_test, "sd", _fake_sd(opened))

    with mic_test.open_input("wasapi") as (_stream, rate):
        pass

    assert rate == 48_000
    assert opened == [{"device": 2, "samplerate": 48_000, "channels": 4, "dtype": "float32"}]


@pytest.mark.unit
def test_a_native_multichannel_capture_becomes_the_contract() -> None:
    seconds = np.arange(48_000) / 48_000
    tone = (0.25 * np.sin(2 * np.pi * 440 * seconds)).astype(np.float32)

    samples = mic_test.as_contract(np.stack([tone, tone], axis=1), "wasapi", 48_000, 2)

    assert samples.dtype == np.int16
    assert len(samples) == 16_000
    assert abs(20 * np.log10(np.abs(samples).max() / 32768) - 20 * np.log10(0.25)) < 0.5


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
