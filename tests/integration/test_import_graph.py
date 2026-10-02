"""Import-graph guards (Plan 0050): standalone imports and a pure cognitive core."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

_STANDALONE_PROBE = textwrap.dedent(
    """
    import importlib
    import pathlib
    import sys

    import server

    root = pathlib.Path(server.__file__).parent
    names = sorted(
        ".".join(("server", *path.relative_to(root).with_suffix("").parts)).removesuffix(
            ".__init__"
        )
        for path in root.rglob("*.py")
    )
    for name in names:
        for loaded in [m for m in sys.modules if m == "server" or m.startswith("server.")]:
            del sys.modules[loaded]
        try:
            importlib.import_module(name)
        except ImportError as exc:
            print(f"{name}: {exc}")
    """
)

_PURE_CORE_PROBE = textwrap.dedent(
    """
    import sys

    import server.cognition
    import server.cognition.controller

    for name in sorted(sys.modules):
        outside_core = name.startswith("server.") and not name.startswith("server.cognition")
        if outside_core or name in {"aiosqlite", "fastapi", "httpx"}:
            print(name)
    """
)


def _run_probe(code: str, cwd: Path) -> str:
    """Run one probe in a fresh interpreter, away from the developer's `.env`."""
    completed = subprocess.run(  # noqa: S603 — fixed interpreter and literal probe, no input
        [sys.executable, "-c", code],
        cwd=cwd,
        env={**os.environ, "LOG_TO_FILE": "false"},
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    return completed.stdout.strip()


@pytest.mark.integration
def test_every_server_module_imports_standalone(tmp_path: Path) -> None:
    """No server module may depend on another module having been imported first."""
    assert _run_probe(_STANDALONE_PROBE, tmp_path) == ""


@pytest.mark.integration
def test_cognitive_core_imports_no_storage_http_or_adapter_module(tmp_path: Path) -> None:
    """The controller and domain vocabulary load without SQLite, FastAPI or httpx."""
    assert _run_probe(_PURE_CORE_PROBE, tmp_path) == ""
