"""The capture auditor CLI (Plan 0069 Task 4): devices, saved takes and Whisper options.

A fake sounddevice and a fake recorder stand in for the microphone; nothing is recorded.
Audio contract: WAV · 16000 Hz · mono · int16.
"""

import json
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
    def _never(*_args: object) -> tuple[np.ndarray, int]:
        raise AssertionError("nothing may be recorded")

    monkeypatch.setattr(mic_test, "record", _never)

    with pytest.raises(SystemExit):
        mic_test.main(["record", "--save", "../escape"])
    assert not corpus_root.exists() or not any(corpus_root.rglob("*"))


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
