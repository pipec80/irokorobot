"""`scripts/pipeline_test.py` passes the shared HTTP client to the LLM (Plan 0056)."""

from unittest.mock import AsyncMock

import httpx
import pytest

from scripts import pipeline_test


@pytest.mark.unit
async def test_run_pipeline_passes_an_http_client_to_the_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generate = AsyncMock(return_value=("Hola, ¿cómo estás?", "neutral"))
    monkeypatch.setattr(pipeline_test.llm, "generate_response", generate)
    monkeypatch.setattr(pipeline_test.tts, "synthesize", AsyncMock(return_value=("QUJD", 42)))

    await pipeline_test.run_pipeline(wav_bytes=None, input_text="hola robot", play=False, save=None)

    call = generate.await_args
    assert call is not None
    assert isinstance(call.args[0], httpx.AsyncClient)
    assert call.args[1] == "hola robot"
    assert call.args[0].is_closed
