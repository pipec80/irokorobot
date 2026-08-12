"""Regression tests for P0-S2 desktop configuration and operator guidance."""

from pathlib import Path

import pytest

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _read_repository_file(relative_path: str) -> str:
    """Return UTF-8 tracked operator guidance from the repository root."""
    return (_REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")


@pytest.mark.unit
def test_desktop_example_is_loopback_and_has_no_legacy_voice_scope() -> None:
    """The sample environment must expose LAN only through explicit opt-in."""
    example = _read_repository_file(".env.example")

    assert "SERVER_HOST=127.0.0.1" in example
    assert "SERVER_HOST=0.0.0.0" in example
    assert "VOICE_CONVERSATION_ID" not in example


@pytest.mark.unit
def test_services_reads_local_model_configuration() -> None:
    """Service guidance must derive its model requirements from local config."""
    script = _read_repository_file("scripts/services.ps1")

    assert "Get-ConfiguredValue" in script
    assert '".env.example"' in script
    assert "OLLAMA_MODEL" in script
    assert "EMBEDDING_MODEL" in script
    assert "CONSOLIDATION_MODEL" in script
    assert "$null = & ollama list 2>$null" in script
    assert "Invoke-WebRequest" not in script


@pytest.mark.unit
def test_public_demos_do_not_promise_private_memory_or_face_enrollment() -> None:
    """Operator demos must match P0.2 unknown turns and P0-S1 quarantine."""
    memory_demo = _read_repository_file("scripts/memory_test.py")
    faces_demo = _read_repository_file("scripts/faces_demo.py")
    task_runner = _read_repository_file("justfile")

    assert "--introduce" not in memory_demo
    assert "--recall" not in memory_demo
    assert "unknown public turns" in memory_demo
    assert "/vision/enroll" not in faces_demo
    assert "--enroll" not in faces_demo
    assert "--who" not in faces_demo
    assert "scene-only" in faces_demo
    assert "Verifica persistencia de memoria" not in task_runner
    assert "enrolar y reconocer caras" not in task_runner


@pytest.mark.unit
def test_iroko_memory_language_is_authorized_and_nonpermanent() -> None:
    """Operational prompt language must not conflict with privacy policy."""
    iroko = _read_repository_file("server/src/server/characters/iroko.py")
    prompt_builder = _read_repository_file("server/src/server/characters/__init__.py")

    assert "tu dueño" not in iroko
    assert "memoria permanente" not in iroko
    assert "Memoria activa autorizada" in prompt_builder
    assert "the owner's life" not in prompt_builder
