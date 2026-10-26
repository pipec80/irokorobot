"""The database resolution and the backup copy of `scripts/reset_db.ps1` (Plan 0071, ADR 0024 dec. 13).

The script itself deletes a database, so these tests never run it: PowerShell parses it and
defines only the two functions under test, which then run on files in a temporary folder.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.integration

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "reset_db.ps1"
_SHELL = shutil.which("pwsh") or shutil.which("powershell")
_DEFINE = """
$ast = [System.Management.Automation.Language.Parser]::ParseFile('{script}', [ref]$null, [ref]$null)
foreach ($name in @('Resolve-DbPath', 'Copy-DbWithSidecars')) {{
    $found = $ast.FindAll({{
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name
    }}, $true) | Select-Object -First 1
    if (-not $found) {{ throw "missing function $name" }}
    . ([scriptblock]::Create($found.Extent.Text))
}}
"""

needs_powershell = pytest.mark.skipif(_SHELL is None, reason="PowerShell is not installed")


def _powershell(body: str, cwd: Path, env: dict[str, str]) -> str:
    """Define the two functions, run *body* and return its output."""
    assert _SHELL is not None
    script = _DEFINE.format(script=str(_SCRIPT).replace("'", "''")) + body
    completed = subprocess.run(  # noqa: S603 — a found PowerShell and a literal script
        [_SHELL, "-NoProfile", "-NonInteractive", "-Command", script],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    return completed.stdout.strip()


def _environment(**extra: str) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key != "BRAIN_DB_PATH"}
    env.update(extra)
    return env


@needs_powershell
def test_the_database_comes_from_the_environment_first(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("BRAIN_DB_PATH=data/from-env-file.db\n", encoding="utf-8")

    resolved = _powershell(
        "Resolve-DbPath -EnvFilePath '.env'",
        tmp_path,
        _environment(BRAIN_DB_PATH="data/scratch.db"),
    )

    assert Path(resolved) == (tmp_path / "data" / "scratch.db").resolve()


@needs_powershell
def test_the_database_comes_from_the_env_file_without_quotes(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text('BRAIN_DB_PATH="data/from-env-file.db"\n', encoding="utf-8")

    resolved = _powershell("Resolve-DbPath -EnvFilePath '.env'", tmp_path, _environment())

    assert Path(resolved) == (tmp_path / "data" / "from-env-file.db").resolve()


@needs_powershell
def test_the_database_defaults_to_the_usual_file(tmp_path: Path) -> None:
    resolved = _powershell("Resolve-DbPath -EnvFilePath '.env'", tmp_path, _environment())

    assert Path(resolved) == (tmp_path / "data" / "omnibot.db").resolve()


@needs_powershell
def test_the_backup_holds_the_write_ahead_log_and_the_shared_memory(tmp_path: Path) -> None:
    database = tmp_path / "scratch.db"
    database.write_bytes(b"main")
    Path(f"{database}-wal").write_bytes(b"wal")
    Path(f"{database}-shm").write_bytes(b"shm")
    backup = tmp_path / "backups" / "scratch_pre-reset.db"
    backup.parent.mkdir()

    _powershell(
        f"Copy-DbWithSidecars -DbPath '{database}' -BackupPath '{backup}'",
        tmp_path,
        _environment(),
    )

    assert backup.read_bytes() == b"main"
    assert Path(f"{backup}-wal").read_bytes() == b"wal"
    assert Path(f"{backup}-shm").read_bytes() == b"shm"
    assert database.exists()


@needs_powershell
def test_a_backup_without_sidecars_copies_the_main_file_only(tmp_path: Path) -> None:
    database = tmp_path / "scratch.db"
    database.write_bytes(b"main")
    backup = tmp_path / "scratch_pre-reset.db"

    _powershell(
        f"Copy-DbWithSidecars -DbPath '{database}' -BackupPath '{backup}'",
        tmp_path,
        _environment(),
    )

    assert backup.read_bytes() == b"main"
    assert not Path(f"{backup}-wal").exists()
    assert not Path(f"{backup}-shm").exists()
