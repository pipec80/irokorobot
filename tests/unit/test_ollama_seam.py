"""Architecture guard (Plan 0050): every Ollama HTTP call goes through llm_transport."""

import ast
from pathlib import Path

import pytest

import server

_SERVER_ROOT = Path(server.__file__).resolve().parent
_ALLOWED = {_SERVER_ROOT / "settings.py", _SERVER_ROOT / "llm_transport.py"}


def _modules_reading_the_ollama_url() -> list[str]:
    """Return every server module, besides the allowed two, that reads `ollama_url`."""
    offenders: list[str] = []
    for path in sorted(_SERVER_ROOT.rglob("*.py")):
        if path in _ALLOWED:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(
            isinstance(node, ast.Attribute) and node.attr == "ollama_url" for node in ast.walk(tree)
        ):
            offenders.append(path.relative_to(_SERVER_ROOT).as_posix())
    return offenders


@pytest.mark.unit
def test_only_the_transport_reads_the_ollama_url() -> None:
    """Chat, streaming, vision and embeddings share one seam to Ollama."""
    assert _modules_reading_the_ollama_url() == []
