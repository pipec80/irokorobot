"""Whisper prompt-echo guard (Plan 0056, Task 5; Plan 0055 decision D-4)."""

import pytest
from server.stt import is_prompt_echo

from server import stt

_PROMPT = "Conversación con un robot doméstico llamado Iroko."


@pytest.mark.unit
@pytest.mark.parametrize(
    "transcript",
    [
        _PROMPT,
        "conversacion con un robot domestico llamado iroko",
        "Conversación con un robot doméstico",
        f"{_PROMPT} {_PROMPT}",
    ],
)
def test_the_prompt_or_part_of_it_is_an_echo(transcript: str) -> None:
    assert is_prompt_echo(transcript, _PROMPT) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "transcript",
    [
        "",
        "Iroko",
        "Hola Iroko",
        "robot doméstico",
        "un robot doméstico",
        "Conversación con un robot",
        "Hola Iroko, ¿cómo estás hoy?",
        f"{_PROMPT}, apaga la luz de la sala",
    ],
)
def test_ordinary_speech_is_not_treated_as_an_echo(transcript: str) -> None:
    """Four of the prompt's seven words or fewer, or anything longer, passes through."""
    assert is_prompt_echo(transcript, _PROMPT) is False


@pytest.mark.unit
def test_a_short_prompt_never_triggers_the_guard() -> None:
    """A one- or two-word prompt is a name or a greeting a user may really say."""
    assert is_prompt_echo("Iroko", "Iroko") is False
    assert is_prompt_echo("Hola Iroko", "Hola Iroko") is False


@pytest.mark.unit
def test_a_three_word_prompt_echoed_exactly_is_discarded() -> None:
    assert is_prompt_echo("Habla con Iroko", "Habla con Iroko") is True


@pytest.mark.unit
def test_documented_limit_five_consecutive_prompt_words_are_discarded() -> None:
    """ACCEPTED FALSE POSITIVE (Plan 0056 D-1): the guard is a heuristic.

    A user who says five or more consecutive words of the prompt, verbatim, is
    discarded like an echo. Nobody says that sentence by chance, and the cost is a
    "no speech understood" turn, never a wrong answer.
    """
    assert is_prompt_echo("Un robot doméstico llamado Iroko", _PROMPT) is True


@pytest.mark.unit
def test_there_is_no_echo_without_a_prompt() -> None:
    assert is_prompt_echo("algo largo aquí", None) is False
    assert is_prompt_echo("algo largo aquí", "") is False


class _Segment:
    def __init__(self, text: str) -> None:
        self.text = text
        self.start = 0.0
        self.end = 1.0
        self.avg_logprob = -0.5
        self.no_speech_prob = 0.1
        self.temperature = 0.0


class _Info:
    language = "es"
    language_probability = 1.0
    duration = 1.3
    duration_after_vad = 1.0


class _FakeModel:
    def __init__(self, text: str) -> None:
        self._text = text

    def transcribe(self, *_args: object, **_kwargs: object) -> tuple[list[_Segment], _Info]:
        return [_Segment(self._text)], _Info()


@pytest.mark.unit
@pytest.mark.parametrize(
    "heard, expected",
    [(_PROMPT, ""), ("Enciende la luz de la sala", "Enciende la luz de la sala")],
)
def test_transcribe_sync_discards_only_an_echo(
    monkeypatch: pytest.MonkeyPatch, heard: str, expected: str
) -> None:
    monkeypatch.setattr(stt, "_get_model", lambda: _FakeModel(heard))
    monkeypatch.setattr(stt.settings, "whisper_initial_prompt", _PROMPT)

    assert stt._transcribe_sync(b"\x00" * 64, None) == expected


@pytest.mark.unit
def test_the_discard_is_logged_without_the_transcript(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(stt, "_get_model", lambda: _FakeModel(_PROMPT))
    monkeypatch.setattr(stt.settings, "whisper_initial_prompt", _PROMPT)

    with caplog.at_level("WARNING", logger="server.stt"):
        stt._transcribe_sync(b"\x00" * 64, None)

    assert "discarded" in caplog.text
    assert "robot" not in caplog.text
