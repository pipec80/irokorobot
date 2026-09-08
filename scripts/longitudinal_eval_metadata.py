"""Run-metadata collection for the longitudinal-memory eval (Plan 0046, Task 4).

``collect_run_metadata`` records everything needed to reproduce a run and
nothing that could leak a secret or a local credential:

* the dataset is hashed (deterministic ``sha256`` of the file bytes);
* the Ollama URL is stripped of user info and query string;
* every ``--reserved-term <value>`` in the command is replaced with
  ``--reserved-term <redacted>`` and only the reserved-term *count* is kept --
  never the literal term, never a reversible hash;
* git facts (branch, commit, porcelain status) come from ``subprocess`` and
  degrade to ``"unknown"`` / empty rather than raising.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path
import platform
import shutil
import subprocess
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

from server.settings import settings

from scripts.longitudinal_eval_models import RunMetadata

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GIT_TIMEOUT_S = 10.0
_RESERVED_FLAG = "--reserved-term"
_REDACTED = "<redacted>"  # placeholder token, not a credential
# Mirrors ``server.memory.consolidation._extract_via_ollama`` (options temperature).
_EXTRACTION_TEMPERATURE = 0.1


def collect_run_metadata(
    dataset_path: Path,
    argv: Sequence[str],
    reserved_terms: Collection[str],
) -> RunMetadata:
    """Collect metadata and redact every reserved-term value from ``argv``.

    Args:
        dataset_path: The dataset file the run loaded; hashed for reproducibility.
        argv: The process arguments (``sys.argv[1:]``); reserved-term values are
            redacted before storage.
        reserved_terms: Reserved identifiers -- only their count is recorded.

    Returns:
        A fully redacted :class:`RunMetadata`. ``service_preflight`` is ``"pass"``
        because metadata is only collected on the post-preflight success path.
    """
    branch, commit, status = _git_facts()
    return RunMetadata(
        generated_at=datetime.now(tz=UTC),
        branch=branch,
        source_commit=commit,
        worktree_dirty=bool(status),
        worktree_status=status,
        dataset_path=_relative_dataset_path(dataset_path),
        dataset_version=1,
        dataset_sha256=hashlib.sha256(Path(dataset_path).read_bytes()).hexdigest(),
        python_version=platform.python_version(),
        provider="ollama",
        ollama_url=sanitize_url(settings.ollama_url),
        chat_model=settings.ollama_model,
        consolidation_model=settings.consolidation_model,
        model_settings=_model_settings(),
        sanitized_command=sanitize_command(argv, reserved_terms),
        reserved_term_count=sum(1 for term in reserved_terms if term and term.strip()),
        temporary_database_name=settings.brain_db_path.name,
        service_preflight="pass",
    )


def _relative_dataset_path(dataset_path: Path) -> str:
    """Return ``dataset_path`` as a repo-relative POSIX string.

    Args:
        dataset_path: The dataset file the run loaded (often an absolute path).

    Returns:
        The path relative to the repository root rendered with forward slashes,
        or the bare file name when the dataset lives outside the repo -- never an
        absolute path, so a published report cannot leak a local directory tree.
    """
    resolved = dataset_path.resolve()
    try:
        return resolved.relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        return resolved.name


def _model_settings() -> dict[str, str | int | float | bool]:
    """Return the small dict of effective model knobs for the report."""
    return {
        "ollama_timeout_s": settings.ollama_timeout_s,
        "embedding_model": settings.embedding_model,
        "extraction_temperature": _EXTRACTION_TEMPERATURE,
    }


def sanitize_url(url: str) -> str:
    """Return ``url`` with user info and query string removed (host:port kept)."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    netloc = f"{host}:{parts.port}" if parts.port is not None else host
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def sanitize_command(argv: Sequence[str], reserved_terms: Collection[str]) -> list[str]:
    """Return ``argv`` with every reserved-term value replaced by ``<redacted>``."""
    needles = [term.strip().lower() for term in reserved_terms if term and term.strip()]
    out: list[str] = []
    redact_next = False
    for token in argv:
        if redact_next:
            out.append(_REDACTED)
            redact_next = False
        elif token == _RESERVED_FLAG:
            out.append(token)
            redact_next = True
        elif token.startswith(f"{_RESERVED_FLAG}="):
            out.append(f"{_RESERVED_FLAG}={_REDACTED}")
        else:
            lowered = token.lower()
            out.append(_REDACTED if any(needle in lowered for needle in needles) else token)
    return out


def _git_facts() -> tuple[str, str, list[str]]:
    """Return ``(branch, commit, porcelain_status_lines)`` from git."""
    branch = _git("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    commit = _git("rev-parse", "HEAD") or "unknown"
    status = [line for line in _git("status", "--porcelain").splitlines() if line.strip()]
    return branch, commit, status


def _git(*args: str) -> str:
    """Run ``git <args>`` in the repo root; return stdout or ``""`` on any failure."""
    git = shutil.which("git")
    if git is None:
        return ""
    try:
        completed = subprocess.run(  # noqa: S603  # fixed literal argv, no shell, repo-root cwd
            [git, *args],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout.strip()
