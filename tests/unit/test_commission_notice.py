"""The biometric notice and the consents step of the alta (Plan 0072, ADR 0024 dec 15, ADR 0025 dec 10).

The notice is a short Spanish text (``tú``), versioned in the repository; the consents step asks the
three operations-plane questions and an optional backup destination. Recording a consent enables
nothing. No audio, no frame and no household value live here.
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest
from server.commission_session import (
    BIOMETRIC_NOTICE_VERSION,
    CommissionError,
    load_biometric_notice,
    read_consents,
)
from server.memory.commissioning import Consents

from server import commission_session

pytestmark = pytest.mark.unit

# A closed list of voseo verb forms (the pattern of tests/integration/test_seed_example.py), so a
# tuteo word like "más" or "estás" is never a false positive.
_VOSEO = re.compile(
    r"\b(tenés|querés|podés|sabés|sos|vivís|decís|escribís|tomás|usás|llamás|preferís|ponés|"
    r"poné|decime|contame|fijate|acordate|mirá|guardás|desplazás|escuchás|entrás|autorizás|"
    r"querrás|elegís|revisás)\b",
    re.IGNORECASE,
)


def _scripted(answers: list[str]):
    """A read_text adapter that returns the queued answers in order; records every prompt."""
    prompts: list[str] = []

    def read_text(prompt: str) -> str:
        prompts.append(prompt)
        return answers.pop(0)

    return read_text, prompts


def _sink():
    lines: list[str] = []
    return lines.append, lines


def test_the_notice_version_is_v_then_digits() -> None:
    assert re.fullmatch(r"v[0-9]+", BIOMETRIC_NOTICE_VERSION)


def test_load_biometric_notice_returns_the_tracked_text() -> None:
    text = load_biometric_notice()

    assert "cara" in text.lower()
    assert "voz" in text.lower()


def test_load_biometric_notice_raises_when_the_file_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(commission_session, "BIOMETRIC_NOTICE_PATH", Path("/does/not/exist.md"))
    with pytest.raises(CommissionError):
        load_biometric_notice()


def test_read_consents_collects_the_three_answers_and_a_destination() -> None:
    read_text, _ = _scripted(["si", "no", "si", "Canary Homelab"])
    write_text, _ = _sink()

    consents = read_consents(read_text=read_text, write_text=write_text)

    assert consents == Consents(
        telemetry=True, remote_support=False, backup=True, backup_destination="Canary Homelab"
    )


def test_an_answer_other_than_si_is_a_no() -> None:
    read_text, _ = _scripted(["quizas", "no", "nope"])
    write_text, _ = _sink()

    consents = read_consents(read_text=read_text, write_text=write_text)

    assert consents == Consents(
        telemetry=False, remote_support=False, backup=False, backup_destination=None
    )


def test_an_empty_destination_is_stored_as_none() -> None:
    read_text, _ = _scripted(["no", "no", "si", "   "])
    write_text, _ = _sink()

    consents = read_consents(read_text=read_text, write_text=write_text)

    assert consents.backup is True
    assert consents.backup_destination is None


def test_the_destination_is_not_asked_when_backup_is_declined() -> None:
    read_text, prompts = _scripted(["no", "no", "no"])
    write_text, _ = _sink()

    consents = read_consents(read_text=read_text, write_text=write_text)

    assert consents.backup is False
    assert consents.backup_destination is None
    assert len(prompts) == 3


def test_the_prompts_and_the_notice_use_tuteo_not_voseo() -> None:
    read_text, prompts = _scripted(["si", "si", "si", "Canary Homelab"])
    write_text, lines = _sink()
    read_consents(read_text=read_text, write_text=write_text)

    for text in [*prompts, *lines, load_biometric_notice()]:
        assert _VOSEO.search(text) is None, text
