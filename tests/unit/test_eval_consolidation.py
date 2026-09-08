"""Signature-aware tests for the real-Ollama consolidation evaluator.

These tests never reach Ollama or the network: the extraction seam
(``_extract_via_ollama``) is always replaced with a typed autospec mock,
and the run-owned ``httpx.AsyncClient`` is replaced with a recording fake.
They exist to pin the Plan 0039 shared-client contract onto the evaluator
after the drift introduced when the production signature became explicit.
"""

from pathlib import Path
from typing import cast
from unittest.mock import Mock, create_autospec

import httpx
import pytest
from server.schemas import ExtractedEntity, ExtractedFact, TurnExtraction

from scripts import eval_consolidation


def _fake_client() -> httpx.AsyncClient:
    """Return an identity-stable stand-in for the run-owned HTTP client."""
    return cast("httpx.AsyncClient", Mock(spec=httpx.AsyncClient))


class _RecordingAsyncClient:
    """Fake ``httpx.AsyncClient`` recording its own lifecycle."""

    instances: list["_RecordingAsyncClient"] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.entered = 0
        self.exited = 0
        _RecordingAsyncClient.instances.append(self)

    async def __aenter__(self) -> "_RecordingAsyncClient":
        self.entered += 1
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        self.exited += 1
        return False


@pytest.fixture(autouse=True)
def _reset_recording_clients() -> None:
    _RecordingAsyncClient.instances.clear()


@pytest.mark.unit
async def test_eval_case_uses_the_run_owned_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_eval_case`` must forward the exact client it is handed, first."""
    client = _fake_client()
    extract = create_autospec(eval_consolidation._extract_via_ollama)
    extract.return_value = TurnExtraction()
    monkeypatch.setattr(eval_consolidation, "_extract_via_ollama", extract)

    case = {"id": "c1", "user": "hola", "assistant": "hola"}
    result = await eval_consolidation._eval_case(case, client)

    assert result.case_id == "c1"
    extract.assert_awaited_once_with(client, "hola", "hola")


@pytest.mark.unit
async def test_extract_case_items_threads_client_and_folds_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reusable seam threads the client and returns stable folded keys."""
    client = _fake_client()
    raw = TurnExtraction(
        entities=[ExtractedEntity(name="Sam", type="person")],
        facts=[ExtractedFact(subject="Sam", predicate="edad", object="11")],
    )
    extract = create_autospec(eval_consolidation._extract_via_ollama)
    extract.return_value = raw
    monkeypatch.setattr(eval_consolidation, "_extract_via_ollama", extract)

    items = await eval_consolidation.extract_case_items(
        client, "hola, me llamo sam y tengo 11", "mucho gusto sam"
    )

    extract.assert_awaited_once_with(client, "hola, me llamo sam y tengo 11", "mucho gusto sam")
    assert items == ("entity|sam|person", "fact|sam|edad|11")


@pytest.mark.unit
async def test_extract_case_items_returns_a_tuple(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extract = create_autospec(eval_consolidation._extract_via_ollama)
    extract.return_value = TurnExtraction()
    monkeypatch.setattr(eval_consolidation, "_extract_via_ollama", extract)

    items = await eval_consolidation.extract_case_items(_fake_client(), "hola", "hola")

    assert items == ()


@pytest.mark.unit
async def test_run_owns_a_single_client_across_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_run`` opens exactly one client, threads it to every case, closes it."""
    golden = tmp_path / "golden.yaml"
    golden.write_text(
        "cases:\n"
        "  - id: a\n    user: hola\n    assistant: hola\n"
        "  - id: b\n    user: chau\n    assistant: chau\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(eval_consolidation, "_GOLDEN_PATH", golden)
    monkeypatch.setattr(eval_consolidation.httpx, "AsyncClient", _RecordingAsyncClient)

    seen_clients: list[object] = []

    async def fake_eval_case(
        case: dict[str, object], client: object
    ) -> eval_consolidation.CaseResult:
        seen_clients.append(client)
        return eval_consolidation.CaseResult(case_id=str(case["id"]), elapsed_s=0.0)

    monkeypatch.setattr(eval_consolidation, "_eval_case", fake_eval_case)

    exit_code = await eval_consolidation._run(None)

    assert exit_code == 0
    assert len(_RecordingAsyncClient.instances) == 1
    only_client = _RecordingAsyncClient.instances[0]
    assert only_client.entered == 1
    assert only_client.exited == 1
    assert seen_clients == [only_client, only_client]
