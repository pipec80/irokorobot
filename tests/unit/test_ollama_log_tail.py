"""Plan 0089 D-11: ``just ollama-log`` shows the last lines of Ollama's own log."""

from pathlib import Path

import pytest

from scripts.ollama_log_tail import default_log_path, main, tail_lines

pytestmark = pytest.mark.unit


def test_tail_lines_returns_the_last_lines(tmp_path: Path) -> None:
    log = tmp_path / "server.log"
    log.write_text("uno\ndos\ntres\ncuatro\n", encoding="utf-8")

    assert tail_lines(log, 2) == ["tres", "cuatro"]
    assert tail_lines(log, 10) == ["uno", "dos", "tres", "cuatro"]


def test_the_default_path_is_under_localappdata() -> None:
    path = default_log_path({"LOCALAPPDATA": "C:/Users/canary/AppData/Local"})

    assert path == Path("C:/Users/canary/AppData/Local") / "Ollama" / "server.log"
    assert default_log_path({}) is None


def test_main_prints_the_tail(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log = tmp_path / "server.log"
    log.write_text("a\nb\nc\n", encoding="utf-8")

    assert main(["--lines", "2", "--path", str(log)]) == 0
    assert capsys.readouterr().out == "b\nc\n"


def test_a_missing_log_says_so_and_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--path", str(tmp_path / "missing.log")]) == 1
    assert "not found" in capsys.readouterr().err


def test_debug_lines_are_hidden_and_counted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Review of plan 0089: with OLLAMA_DEBUG on, Ollama logs prompts; they are never shown."""
    log = tmp_path / "server.log"
    log.write_text(
        'time=1 level=INFO msg="loaded runners"\n'
        'time=2 level=DEBUG msg="chat request" prompt="qqprivadoqq"\n'
        'time=3 level=WARN msg="evicting"\n',
        encoding="utf-8",
    )

    assert main(["--path", str(log)]) == 0
    out = capsys.readouterr().out
    assert "qqprivadoqq" not in out
    assert "loaded runners" in out
    assert "evicting" in out
    assert "1 debug line(s) hidden" in out
