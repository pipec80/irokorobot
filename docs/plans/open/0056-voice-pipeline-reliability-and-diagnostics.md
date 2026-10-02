# 0056 — Voice-pipeline reliability and truthful diagnostics

> **Status:** `Draft` — written 2026-10-02 after Plan 0050 closed. Not `Ready`:
> Pipec promotes it (and confirms decisions D-2 to D-7 below) before anyone executes
> it. Queue position: the first row after the audit repairs in the
> [canonical portfolio](../../roadmap/cognitive-roadmap.md#canonical-pre-electronics-delivery-portfolio),
> ahead of CM-1 / Plan 0051.

> **For agentic workers:** REQUIRED SUB-SKILLS: `superpowers:test-driven-development`,
> `superpowers:verification-before-completion`. Execute only while this is the
> explicitly authorized `NOW` item. Implement exactly the tasks below, in order, one
> commit per task. If evidence contradicts the plan, stop and report the conflict
> instead of redesigning. Pipec runs every local process (Ollama, server, robot,
> probes that load a model); you record what they print, outcomes only.

**Goal:** Make the voice pipeline stop failing in the ways Pipec has already heard
(a Whisper transcript that is its own prompt, a classic reply that is not text, a
streaming reply that drops to the fallback phrase) and make its diagnostics say what
they really test, by repairing the deterministic defects and by **measuring** the
ones whose frequency nobody knows.

**Architecture:** No wire change, no schema change, no new dependency. Three small
repairs inside existing modules (`llm.py`, `stt.py`, `scripts/pipeline_test.py`), two
extensions of existing evaluators (`eval-chat` gets a streaming mode, the
longitudinal evaluator gets staged verdicts through a dataset version bump), and two
measurement probes. Every measurement has its decision rule written **before** it is
run; a failed rule opens a named follow-up plan, it is never fixed inside this one.

**Tech Stack:** Python 3.12, faster-whisper, httpx, pydantic, pytest (+ xdist), numpy.
Same pins as the current lock.

**Spec:** the roadmap row
[*Voice-pipeline reliability and truthful diagnostics*](../../roadmap/cognitive-roadmap.md#canonical-pre-electronics-delivery-portfolio),
[0049 O-04](0049-server-objective-conformance-audit.md) (streaming protocol fallback),
decision D-4 of [Plan 0055](../completed/0055-pc4-identity-fusion-followups.md)
(Whisper prompt echo), the *Non-goals* of
[Plan 0050](../completed/0050-server-audit-repairs.md) (classic parser, `test-pipeline`)
and the staged-acceptance section of the
[longitudinal evaluation spec](../../architecture/longitudinal-conversational-memory-evaluation.md#cm-0-measured-baseline).

**Rehearsal (2026-10-02, before Plan 0056 was promoted).** Tasks 1 to 6 were applied
from the code blocks below onto a scratch copy of the working tree at `main` (`9d4cb0e`)
and reverted. With them applied: `just gate` passed **1766 tests** (baseline 1695),
`ruff check`, `ruff format --check`, `mypy` and `pyright` were clean, and the 31
existing longitudinal tests that the dataset bump breaks were fixed by exactly the edits
listed in Task 3 Step 7. The RED of Task 1 was observed against the old parser: 15
failures (7 "did not raise", 4 `TypeError`, 4 `AttributeError`). The other tasks' RED
steps were **not** separately observed in the rehearsal and must be observed during
execution; Tasks 0, 7 and 8 need Pipec's machine or the merged state and were not
rehearsed. Treat the blocks as rehearsed code, not as a substitute for the fresh
RED/GREEN record each task requires.

## Global Constraints

- Audio contract everywhere: WAV · 16 000 Hz · mono · int16. Any new function that
  touches audio documents it in its docstring.
- No real household data, voice or name in any tracked file, test, prompt, doc or
  commit message; probes use synthetic noise and Piper-synthesized phrases only
  (`scripts/check_reserved_terms.py` guards this).
- Ollama stays the only LLM runtime; no cloud provider (ADR-0004).
- No `print()` in `server/src` or `robot/src`; scripts under `scripts/` may print with
  `# noqa: T201` as the existing scripts do.
- Type hints on every signature, Google docstrings on public APIs, `ruff` and
  `mypy server/src robot/src` clean, `Annotated` for FastAPI parameters (none are added).
- Log lines never carry a transcript or model output (Plan 0032): only counts, lengths
  and closed reasons.
- Every new test is observed RED for the stated reason before its implementation.

## Review Focus

Inputs the spec implies that are most likely to bite, each pinned by a test in its
owning task:

1. A user who says only "Iroko", or "Hola Iroko", or a real utterance that merely
   contains the prompt's words, must **not** be discarded as an echo (Task 5).
2. `{"response": "Hola"}` with no `emotion`, and a valid `response` with a non-text
   `emotion`, must still be spoken (Task 1).
3. A malformed-JSON reply must keep falling to raw text exactly as today; this plan
   does not decide that question (Task 1).
4. A streamed reply that is only an `EMOTION:` line, with no body, counts as a
   protocol failure in the measurement, as it does in production (Task 4).
5. A provider error during a measurement is reported separately and never counted as
   a protocol failure or as a pass (Task 4).
6. The staged verdicts must agree with `determine_exit_code` on the full suite, and an
   `--only` smoke run of one scope must not claim the other scope passed (Task 3).

---

## Why this plan exists

Evidence already recorded (nothing here is a new claim):

| Defect | Evidence | Kind |
|---|---|---|
| Whisper returns its own initial prompt from a noise clip | Seen four times; reproduced on a 1.3 s clip in Plan 0055's hardware session (D-4) | repair + measure |
| The first utterance after a restart is mis-transcribed | Plan 0028 acceptance (2026-08-21), "repeatable first-utterance-after-restart STT mis-transcription pattern"; Plan 0055 later warmed the face and speaker models at start-up but not Whisper inference | measure only |
| Classic parser accepts `{"response": []}` | `llm._parse_llm_output` returns `data["response"]` unchecked; `None` or a list reaches TTS | repair |
| `just test-pipeline` does not run | `scripts/pipeline_test.py:139` calls `llm.generate_response(text_heard)` without the HTTP client Plan 0039 made mandatory | repair |
| Streaming drops to the fallback phrase | 0049 O-04, and again on 2026-10-01 with "Te presenta mi amigo Tom": `Stream fallback: reason=invalid_protocol`; frequency never measured | measure |
| `eval-chat` measures the classic generator only | `scripts/eval_chat.py::_run_case` calls `llm.generate_response`; the `EMOTION:` stream protocol is untested by it | extend |
| The longitudinal evaluator has one verdict | `determine_exit_code` fails on any unsupported scenario (the right *full-suite* verdict); the staged personal/family verdicts decided on 2026-09-30 are not implemented | extend |

## Task overview

| # | Task | Closes | Decision |
|---:|---|---|---|
| 0 | Revalidate the baseline | — | — |
| 1 | Classic parser rejects a non-text `response` | parser defect | D-2, D-3, D-7 |
| 2 | `just test-pipeline` runs again and says what it tests | broken script | — |
| 3 | Staged longitudinal verdicts (dataset version 2) | staged acceptance | D-4 |
| 4 | `eval-chat --mode stream` measures the streaming protocol | O-04 instrument | D-5 |
| 5 | Whisper prompt-echo guard | D-4 of Plan 0055 | D-1 |
| 6 | STT probes: synthetic noise and first turn | measurement instruments | D-5, D-6 |
| 7 | Run the measurements, record them, apply the rules | O-04, echo, first turn | D-5, D-6 |
| 8 | Documentation truth | — | — |

## Decisions

Confirmed by Pipec during design on 2026-10-02: **D-1**, **D-5** (thresholds) and the
"one plan, repair and measure" scope. The rest are proposed here and must be
confirmed when the plan is promoted.

1. **D-1 — The echo guard discards the transcript** (the route then answers "no speech
   understood", the same path as silence). No retry, no added latency.
2. **D-2 — A non-text `emotion` keeps the response and becomes `neutral`.** The emotion
   is cosmetic; an unknown emotion already degrades to `neutral`.
3. **D-3 — A blank `response` is rejected like a non-text one.** Text-to-speech raises
   on empty text, so a blank reply can only become a spoken failure later.
4. **D-4 — The longitudinal dataset moves to version 2.** It adds one required field,
   `scope` (`personal` or `family`), to each scenario; scenario content is identical.
   `recipient_only_message` and `two_adult_private_facts` are `family`, as the
   evaluation spec already states. The 0046 baseline report stays the historical
   measurement of version 1.
5. **D-5 — O-04 rule.** `eval-chat --mode stream --runs 5` gives 120 observations
   (60 context turns + 60 public turns). If the **fallback rate** (invalid protocol
   plus empty body, over valid + invalid + empty) is **above 5 %**, a follow-up plan
   for the fallback is opened; at or below 5 % the observation is closed with the
   number recorded. A rate from 3 % to 8 % is repeated once with `--runs 10` (240) and
   the second run decides.
6. **D-6 — Echo and first-turn rules.** Noise probe: if the share of transcripts that
   are non-empty, not a prompt echo and not empty after the guard exceeds 5 % of the
   probe clips, a hallucination-filter plan is opened. First-turn probe, five fresh
   processes: if the mean word error rate of call 1 exceeds the mean of the later
   calls by more than 0.15 (absolute), a plan for a Whisper warm-up inference at
   start-up is opened.
7. **D-7 — Malformed JSON still falls back to raw text.** Whether that fallback should
   exist is a separate, explicit decision and stays outside this plan.

## Required reading

- `AGENTS.md` and `docs/architecture/implementation-guardrails.md`.
- ADR-0004 (local-only runtime), ADR-0012 (streaming terminal contract).
- `docs/architecture/current-state.md` (streaming rows, Plan 0050 row).
- 0049 §13 O-04; Plan 0055 decision D-4; Plan 0050 *Non-goals*.
- `server/src/server/{stt,llm,llm_streaming,streaming,streaming_protocol,streaming_render}.py`,
  `scripts/{pipeline_test,eval_chat,eval_longitudinal_memory,longitudinal_eval_*}.py`.

## Permitted files

- `server/src/server/llm.py`, `server/src/server/stt.py`
- `scripts/pipeline_test.py`, `scripts/eval_chat.py`, new `scripts/eval_stream_protocol.py`,
  new `scripts/stt_probes.py`
- `scripts/longitudinal_eval_models.py`, `longitudinal_eval_aggregation.py`,
  `longitudinal_eval_report.py`, `longitudinal_eval_runner.py`,
  `longitudinal_eval_metadata.py`, `eval_longitudinal_memory.py`
- `tests/evals/golden_longitudinal_memory.yaml`
- `justfile` (comments and one `probe-stt` recipe)
- Tests: `tests/unit/test_llm_parsing.py`, `test_llm_generate.py`, new
  `test_pipeline_test_script.py`, `test_longitudinal_staged_verdicts.py`,
  `test_eval_stream_protocol.py`, `test_stt_echo_guard.py`, `test_stt_probes.py`;
  edits to `test_eval_longitudinal_memory.py` and `test_eval_chat.py`
- Docs: `docs/architecture/current-state.md`,
  `docs/architecture/longitudinal-conversational-memory-evaluation.md`,
  `docs/architecture/diagrams/current-state.{json,html}` (only if a row changes the
  picture), `docs/runbooks/operator-manual.md`, `docs/evals/README.md`, new
  `docs/evals/0056-voice-pipeline-measurements.md`, `docs/roadmap/cognitive-roadmap.md`,
  `docs/plans/README.md`, `docs/plans/open/README.md`, this plan

No URL, status code, response field, streaming event, audio contract, database schema
or migration changes. `server/src/server/streaming*.py` and `llm_streaming.py` are
**read-only** here: the fallback itself is not repaired by this plan (see *Non-goals*).

---

## Task 0: Revalidate the baseline

**Files:** this plan's evidence note only. No production change.

- [ ] Record branch, base SHA and `git status`. Work on `fix/0056-voice-pipeline`
  created from the merged `main`; do not discard other uncommitted work.
- [ ] Run `just gate`; record its outcome and test count (the baseline after Plan 0050
  was 1695). A pre-existing failure is reported, not hidden.
- [ ] Re-read each symbol this plan names against the tree and note differences:
  `llm._parse_llm_output`, `stt._transcribe_sync` (the slow test
  `tests/slow/test_stt_transcription.py` monkeypatches it, keep that name),
  `pipeline_test.run_pipeline`, `eval_chat.CliOptions/run_cli`,
  `longitudinal_eval_*` call sites (`rg "score_step\(|LongitudinalScenario\(|Literal\[1\]|version.*== 1|dataset_version" scripts tests`).
- [ ] Record `rg -n "test-pipeline|invalid_protocol|prompt echo" docs --glob "*.md"` so
  Task 8 knows every sentence to correct.

---

## Task 1: Classic parser rejects a non-text `response`

**Files:**

- Modify: `server/src/server/llm.py` (`_parse_llm_output`, two small helpers)
- Test: `tests/unit/test_llm_parsing.py`, `tests/unit/test_llm_generate.py`

**Interfaces:** `_parse_llm_output(raw: str) -> tuple[str, str]` keeps its signature.
It now raises `LLMError` when the JSON is an object whose `response` is not non-blank
text, or when the JSON is valid but not an object. `generate_response` already turns
`LLMError` into the audible fallback phrase (`text_turn.py`), so no caller changes.

- [ ] **Step 1: Write the failing tests.** Append to `tests/unit/test_llm_parsing.py`
  (add `from server.exceptions import LLMError` to its imports):

```python
@pytest.mark.unit
@pytest.mark.parametrize(
    "raw",
    [
        '{"response": [], "emotion": "joy"}',
        '{"response": null, "emotion": "joy"}',
        '{"response": 7, "emotion": "joy"}',
        '{"response": {"text": "hola"}, "emotion": "joy"}',
        '{"response": "", "emotion": "joy"}',
        '{"response": "   ", "emotion": "joy"}',
    ],
)
def test_a_non_text_or_blank_response_is_rejected(raw: str) -> None:
    with pytest.raises(LLMError):
        _parse_llm_output(raw)


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["[]", '"hola"', "7", "null"])
def test_valid_json_that_is_not_an_object_is_rejected(raw: str) -> None:
    with pytest.raises(LLMError):
        _parse_llm_output(raw)


@pytest.mark.unit
@pytest.mark.parametrize("emotion", ["7", "null", '["joy"]', '{"a": 1}'])
def test_a_non_text_emotion_keeps_the_response_and_defaults_to_neutral(emotion: str) -> None:
    response, got = _parse_llm_output(f'{{"response": "Hola", "emotion": {emotion}}}')
    assert response == "Hola"
    assert got == "neutral"


@pytest.mark.unit
def test_a_response_without_an_emotion_is_still_spoken() -> None:
    assert _parse_llm_output('{"response": "Hola"}') == ("Hola", "neutral")
```

  Append to `tests/unit/test_llm_generate.py` (it already imports `llm`; add what is
  missing: `AsyncMock`, `httpx`, `pytest`, `LLMError`):

```python
@pytest.mark.unit
async def test_generate_response_raises_llm_error_for_a_non_text_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model that answers `{"response": []}` becomes the audible fallback, not TTS input."""
    monkeypatch.setattr(
        llm, "ollama_chat", AsyncMock(return_value='{"response": [], "emotion": "joy"}')
    )
    async with httpx.AsyncClient() as client:  # no request is sent: ollama_chat is stubbed
        with pytest.raises(LLMError):
            await llm.generate_response(client, "hola")
```

- [ ] **Step 2: Watch them fail.** Run
  `uv run pytest tests/unit/test_llm_parsing.py tests/unit/test_llm_generate.py -v -n0`.
  Expected: the six non-text cases fail (a list, `None`, `7`, a dict and blank strings
  come back as the "response" instead of raising), the four non-object cases fail with
  a raw `TypeError` instead of `LLMError`, the four emotion cases fail with
  `AttributeError`, and `test_generate_response_raises_llm_error_for_a_non_text_response`
  fails (the list reaches the caller); only
  `test_a_response_without_an_emotion_is_still_spoken` already passes (a guard).

- [ ] **Step 3: Implement.** Replace `_parse_llm_output` and add two helpers in `llm.py`:

```python
def _coerce_emotion(value: object) -> str:
    """Return a valid emotion; anything else (unknown or non-text) becomes neutral."""
    if isinstance(value, str):
        emotion = value.lower()
        if emotion in VALID_EMOTIONS:
            return emotion
        logger.warning("Unknown emotion '%s' from LLM — defaulting to neutral", emotion)
    else:
        logger.warning("Non-text emotion from LLM — defaulting to neutral")
    return FALLBACK_EMOTION


def _salvage_or_raw(raw: str, text: str, exc: Exception) -> tuple[str, str]:
    """Malformed-JSON fallback (unchanged behaviour): salvage the field, else raw text."""
    match = _RESPONSE_RE.search(text)
    if match:
        logger.warning("LLM returned malformed JSON (%s) — salvaged response field", exc)
        try:
            salvaged: str = json.loads(f'"{match.group(1)}"')
        except json.JSONDecodeError:
            salvaged = match.group(1)
        return salvaged, FALLBACK_EMOTION
    logger.warning("LLM returned non-JSON output (%s) — using raw text", exc)
    return raw, FALLBACK_EMOTION


def _parse_llm_output(raw: str) -> tuple[str, str]:
    """Extract response text and emotion from the classic JSON contract.

    Malformed JSON, or an object without a ``response`` key, keeps falling back to
    raw text (a separate decision, Plan 0056 D-7). A well-formed object whose
    ``response`` is not non-blank text, or valid JSON that is not an object, is
    rejected: nothing speakable can be recovered from it.

    Args:
        raw: Raw string from the model, expected to be valid JSON.

    Returns:
        Tuple of (response_text, emotion).

    Raises:
        LLMError: If the output is valid JSON but carries no speakable text.
    """
    text = strip_json_fences(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return _salvage_or_raw(raw, text, exc)
    if not isinstance(data, dict):
        raise LLMError("Classic response is not a JSON object")
    if "response" not in data:
        return _salvage_or_raw(raw, text, KeyError("response"))
    response_text = data["response"]
    if not isinstance(response_text, str) or not response_text.strip():
        raise LLMError("Classic response field is not non-blank text")
    return response_text, _coerce_emotion(data.get("emotion", FALLBACK_EMOTION))
```

- [ ] **Step 4: GREEN.** The two files above, then `tests/unit/test_llm_streaming.py`,
  `tests/integration/test_transcribe_pipeline.py`, `test_chat_endpoint.py`, then
  `just test`, `just typecheck`.

- [ ] **Step 5: Commit** — `fix(llm): reject a non-text classic response`.

---

## Task 2: `just test-pipeline` runs again and says what it tests

**Files:**

- Modify: `scripts/pipeline_test.py`, `justfile` (one comment line)
- Create: `tests/unit/test_pipeline_test_script.py`

**Interfaces:** `run_pipeline(wav_bytes, input_text, play, save)` keeps its signature.
It now owns one `httpx.AsyncClient` for the LLM step. `sounddevice` is imported inside
the three functions that use it, so the module (and `run_pipeline --text`) loads on a
machine without PortAudio, the same lazy-import pattern the repo uses for `cv2`.

- [ ] **Step 1: Write the failing test.** `tests/unit/test_pipeline_test_script.py`:

```python
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
```

- [ ] **Step 2: Watch it fail.** `uv run pytest tests/unit/test_pipeline_test_script.py -v -n0`.
  Expected: FAIL — the first positional argument is the string `"hola robot"`, not a
  client (on a machine without PortAudio the import itself fails first, which is the
  second reason for the lazy import).

- [ ] **Step 3: Implement.**
  1. Delete the module-level `import sounddevice as sd`; in `list_devices`, `record`
     and `play_wav` add `import sounddevice as sd  # noqa: PLC0415 — PortAudio is only needed with a microphone`
     as their first statement.
  2. Add `import httpx` and `from server.settings import settings` to the imports.
  3. Wrap the LLM call in `run_pipeline`:

```python
    _header("2/3  LLM  (Ollama)")
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=settings.ollama_timeout_s) as client:
        llm_response, emotion = await llm.generate_response(client, text_heard)
    elapsed = time.perf_counter() - t0
```

  4. Say what it is. Module docstring first line becomes
     `"""Smoke test: mic → STT → LLM → TTS → speaker — the three model seams only."""`
     with the sentence "It does not run the cognitive controller, identity, memory or
     the HTTP API; use `just chat-test` or the robot for those." added to the body.
     In `justfile`, the comment above `test-pipeline` becomes
     `# Humo STT → LLM → TTS (el micrófono es opcional con --text). No recorre el controlador, la identidad ni la API: para eso, chat-test o el robot`.

- [ ] **Step 4: GREEN.** The new test, `uv run ruff check . && uv run ruff format --check .`,
  `just test`. Manual check by Pipec at acceptance: `just test-pipeline --text hola robot --no-play`.

- [ ] **Step 5: Commit** — `fix(scripts): make test-pipeline pass the http client`.

---

## Task 3: Staged longitudinal verdicts (dataset version 2)

**Files:**

- Modify: `scripts/longitudinal_eval_models.py`, `longitudinal_eval_aggregation.py`,
  `longitudinal_eval_report.py`, `longitudinal_eval_runner.py`,
  `longitudinal_eval_metadata.py`, `eval_longitudinal_memory.py`,
  `tests/evals/golden_longitudinal_memory.yaml`
- Create: `tests/unit/test_longitudinal_staged_verdicts.py`
- Modify: `tests/unit/test_eval_longitudinal_memory.py` (version literals and any
  builder of `LongitudinalScenario`/`LongitudinalSuite` found in Task 0)

**Interfaces:**

- Produces in `longitudinal_eval_models`: `ScenarioScope = Literal["personal", "family"]`;
  `LongitudinalScenario.scope: ScenarioScope` (required);
  `StagedVerdict` (`StrEnum`: `PASS`, `FAIL`, `PENDING`, `ERROR`, `NOT_RUN`);
  `StagedVerdicts(personal, family, full_suite: StagedVerdict)`;
  `LongitudinalEvaluationResult.staged: StagedVerdicts | None = None`.
- Produces in `longitudinal_eval_aggregation`:
  `staged_verdicts(scored: Sequence[ScoredStep], scopes: Mapping[str, ScenarioScope], *, gating: bool) -> StagedVerdicts`.
  `determine_exit_code` keeps its exact 0/1/2 behaviour and now shares one private
  `_verdict` helper with it.
- `score_step`, `StepResult` and `ScoredStep` do **not** change (the frozen scoring
  contract and the dozens of tests that call `score_step` stay as they are).

Verdict rules (per scope, the same rules `determine_exit_code` applies to the whole run):
`ERROR` if any step errored; `PASS` if no step failed or is unsupported and, on a
gating run, the four frozen strict gates hold over **that scope's steps** with
non-empty denominators; otherwise `FAIL`. `family` is `PENDING` while any family step is
unsupported and none errored. A scope with no steps is `FAIL` on a gating run and
`NOT_RUN` on an `--only` run. `full_suite` is the existing exit-code verdict.

- [ ] **Step 1: Write the failing tests.** `tests/unit/test_longitudinal_staged_verdicts.py`:

```python
"""Staged personal / family / full-suite verdicts (Plan 0056, Task 3)."""

from pathlib import Path

import pytest

from scripts.eval_longitudinal_memory import load_suite
from scripts.longitudinal_eval_aggregation import staged_verdicts
from scripts.longitudinal_eval_models import (
    LongitudinalStep,
    ProbeObservation,
    ScenarioScope,
    ScoredStep,
    StagedVerdict,
    StagedVerdicts,
)
from scripts.longitudinal_eval_report import _staged_section
from scripts.longitudinal_eval_scoring import score_step

_SCOPES: dict[str, ScenarioScope] = {"mine": "personal", "theirs": "family"}


def _expected(required_any: list[list[str]] | None = None) -> dict[str, object]:
    return {
        "required_any": required_any or [],
        "forbidden": [],
        "expected_items": [],
        "forbidden_items": [],
        "expected_provenance": {},
        "required_absent_derivatives": [],
    }


def _scored(scenario_id: str, status: str = "pass", *, fails: bool = False) -> ScoredStep:
    step = LongitudinalStep.model_validate(
        {
            "step_id": "s1",
            "category": "extraction",
            "operation": "extract",
            "session": 1,
            "actor_id": "aria",
            "message": "m",
            "expected": _expected([["zzz"]] if fails else None),
        }
    )
    observation = ProbeObservation.model_validate(
        {
            "status": status,
            "response": "",
            "observed_items": (),
            "observed_provenance": {},
            "latency_ms": 1.0,
            "reason": None,
            "inspected_derivatives": {},
        }
    )
    return score_step(scenario_id, step, observation)


@pytest.mark.unit
def test_personal_passes_while_family_is_pending_and_the_suite_still_fails() -> None:
    verdicts = staged_verdicts(
        [_scored("mine"), _scored("theirs", "unsupported")], _SCOPES, gating=False
    )

    assert verdicts.personal is StagedVerdict.PASS
    assert verdicts.family is StagedVerdict.PENDING
    assert verdicts.full_suite is StagedVerdict.FAIL


@pytest.mark.unit
def test_everything_passing_passes_every_stage() -> None:
    verdicts = staged_verdicts([_scored("mine"), _scored("theirs")], _SCOPES, gating=False)

    assert (verdicts.personal, verdicts.family, verdicts.full_suite) == (
        StagedVerdict.PASS,
        StagedVerdict.PASS,
        StagedVerdict.PASS,
    )


@pytest.mark.unit
def test_an_unsupported_personal_step_fails_personal() -> None:
    verdicts = staged_verdicts(
        [_scored("mine", "unsupported"), _scored("theirs")], _SCOPES, gating=False
    )

    assert verdicts.personal is StagedVerdict.FAIL
    assert verdicts.family is StagedVerdict.PASS


@pytest.mark.unit
def test_a_failed_family_step_is_a_failure_not_pending() -> None:
    verdicts = staged_verdicts(
        [_scored("mine"), _scored("theirs", fails=True)], _SCOPES, gating=False
    )

    assert verdicts.family is StagedVerdict.FAIL


@pytest.mark.unit
def test_a_harness_error_is_reported_as_error_in_its_scope_only() -> None:
    verdicts = staged_verdicts([_scored("mine"), _scored("theirs", "error")], _SCOPES, gating=False)

    assert verdicts.personal is StagedVerdict.PASS
    assert verdicts.family is StagedVerdict.ERROR
    assert verdicts.full_suite is StagedVerdict.ERROR


@pytest.mark.unit
def test_a_smoke_run_of_one_scope_does_not_claim_the_other_passed() -> None:
    verdicts = staged_verdicts([_scored("mine")], _SCOPES, gating=False)

    assert verdicts.personal is StagedVerdict.PASS
    assert verdicts.family is StagedVerdict.NOT_RUN


@pytest.mark.unit
def test_a_gating_run_needs_the_frozen_gates_so_clean_steps_alone_do_not_pass() -> None:
    """Extraction-only steps leave every strict-gate denominator empty: that fails."""
    verdicts = staged_verdicts([_scored("mine"), _scored("theirs")], _SCOPES, gating=True)

    assert verdicts.personal is StagedVerdict.FAIL
    assert verdicts.full_suite is StagedVerdict.FAIL


@pytest.mark.unit
def test_a_gating_run_with_an_empty_scope_fails_that_scope() -> None:
    verdicts = staged_verdicts([_scored("mine")], _SCOPES, gating=True)

    assert verdicts.family is StagedVerdict.FAIL


@pytest.mark.unit
def test_the_frozen_dataset_declares_a_scope_for_every_scenario() -> None:
    suite = load_suite(Path("tests/evals/golden_longitudinal_memory.yaml"))

    scopes = {scenario.scenario_id: scenario.scope for scenario in suite.scenarios}

    assert suite.version == 2
    assert {sid for sid, scope in scopes.items() if scope == "family"} == {
        "two_adult_private_facts",
        "recipient_only_message",
    }
    assert set(scopes.values()) == {"personal", "family"}


@pytest.mark.unit
def test_the_report_section_lists_the_three_verdicts() -> None:
    section = _staged_section(
        StagedVerdicts(
            personal=StagedVerdict.PASS,
            family=StagedVerdict.PENDING,
            full_suite=StagedVerdict.FAIL,
        )
    )

    assert section is not None
    assert "| Personal acceptance (CM-7 exit evidence) | PASS |" in section
    assert "| Family acceptance (pending until P3.2) | PENDING |" in section
    assert "| Full suite | FAIL |" in section
    assert _staged_section(None) is None
```

- [ ] **Step 2: Watch them fail.** `uv run pytest tests/unit/test_longitudinal_staged_verdicts.py -v -n0`
  — collection error: `cannot import name 'staged_verdicts'` / `StagedVerdict`. Expected.

- [ ] **Step 3: Models.** In `longitudinal_eval_models.py`:

```python
ScenarioScope = Literal["personal", "family"]


class StagedVerdict(enum.StrEnum):
    """Verdict of one acceptance stage; ``PENDING`` and ``NOT_RUN`` never mean PASS."""

    PASS = "PASS"  # noqa: S105  # enum member, not a credential
    FAIL = "FAIL"
    PENDING = "PENDING"
    ERROR = "ERROR"
    NOT_RUN = "NOT_RUN"


class StagedVerdicts(BaseModel):
    """Personal, family and full-suite verdicts, computed separately."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    personal: StagedVerdict
    family: StagedVerdict
    full_suite: StagedVerdict
```

  Then: `LongitudinalScenario` gains `scope: ScenarioScope` (after `scenario_id`);
  `LongitudinalSuite.version: Literal[2]`; `RunMetadata.dataset_version: Literal[2]`;
  `LongitudinalEvaluationResult` gains `staged: StagedVerdicts | None = None`.
  `longitudinal_eval_metadata.py:66` becomes `dataset_version=2`.
  `eval_longitudinal_memory.py`: rename `_require_version_one` to
  `_require_supported_version` and make it require `raw.get("version") == 2` with the
  message `'longitudinal suite "version" must be exactly 2'`.

- [ ] **Step 4: Dataset.** In `tests/evals/golden_longitudinal_memory.yaml` set
  `version: 2`, change the header comment to "version 2 (Plan 0056: version 1 plus a
  `scope` per scenario; scenario content unchanged)", and add one line
  `    scope: personal` under each `- scenario_id:` line — `scope: family` under
  `two_adult_private_facts` and `recipient_only_message`. A throwaway script is the
  safest way (run it, check `git diff --stat` shows 9 insertions plus the header and
  version lines, delete it):

```python
import pathlib, re

path = pathlib.Path("tests/evals/golden_longitudinal_memory.yaml")
family = {"two_adult_private_facts", "recipient_only_message"}
text = path.read_text(encoding="utf-8")
text = re.sub(
    r"^(  - scenario_id: (\w+)\n)",
    lambda m: m.group(1) + f"    scope: {'family' if m.group(2) in family else 'personal'}\n",
    text,
    flags=re.MULTILINE,
)
path.write_text(text.replace("\nversion: 1\n", "\nversion: 2\n", 1), encoding="utf-8", newline="")
```

- [ ] **Step 5: Aggregation.** In `longitudinal_eval_aggregation.py` (add `Mapping` to the
  `TYPE_CHECKING` collections import and the new model names to the models import):

```python
_EXIT_CODE = {StagedVerdict.PASS: 0, StagedVerdict.FAIL: 1, StagedVerdict.ERROR: 2}


def _strict_gates_pass(summary: BenchmarkSummary) -> bool:
    return (
        summary.forbidden_disclosure_rate == 0.0
        and summary.complete_deletion_rate == 1.0
        and summary.truth_current_accuracy == 1.0
        and summary.provenance_accuracy == 1.0
    )


def _verdict(summary: BenchmarkSummary, *, gating: bool) -> StagedVerdict:
    """PASS / FAIL / ERROR for one population of steps (the exit-code rules)."""
    if summary.errors > 0:
        return StagedVerdict.ERROR
    clean = summary.failed == 0 and summary.unsupported == 0
    if clean and (not gating or _strict_gates_pass(summary)):
        return StagedVerdict.PASS
    return StagedVerdict.FAIL


def _scope_verdict(steps: Sequence[ScoredStep], *, gating: bool) -> StagedVerdict:
    if not steps:
        return StagedVerdict.FAIL if gating else StagedVerdict.NOT_RUN
    return _verdict(aggregate_results(steps), gating=gating)


def _family_verdict(steps: Sequence[ScoredStep], *, gating: bool) -> StagedVerdict:
    if steps:
        summary = aggregate_results(steps)
        if summary.errors == 0 and summary.unsupported > 0:
            return StagedVerdict.PENDING
    return _scope_verdict(steps, gating=gating)


def staged_verdicts(
    scored: Sequence[ScoredStep],
    scopes: Mapping[str, ScenarioScope],
    *,
    gating: bool,
) -> StagedVerdicts:
    """Compute the personal, family and full-suite verdicts separately.

    Args:
        scored: Every scored step of the run, in run order.
        scopes: ``scenario_id`` to its declared scope.
        gating: Whether this was a full gating run.

    Returns:
        The three verdicts. Pending family scenarios stay visible and are never
        excluded from the full suite.

    Raises:
        KeyError: If a scored step belongs to a scenario with no declared scope.
    """
    personal = [s for s in scored if scopes[s.result.scenario_id] == "personal"]
    family = [s for s in scored if scopes[s.result.scenario_id] == "family"]
    return StagedVerdicts(
        personal=_scope_verdict(personal, gating=gating),
        family=_family_verdict(family, gating=gating),
        full_suite=_scope_verdict(list(scored), gating=gating),
    )
```

  and replace the body of `determine_exit_code` (keep its docstring) with:

```python
    return _EXIT_CODE[_verdict(result.summary, gating=result.gating)]
```

- [ ] **Step 6: Runner and report.** In `longitudinal_eval_runner._execute`, build the
  result with the verdicts (import `staged_verdicts`):

```python
return LongitudinalEvaluationResult(
    metadata=metadata,
    results=[step.result for step in scored],
    summary=aggregate_results(scored),
    gating=gating,
    staged=staged_verdicts(scored, {s.scenario_id: s.scope for s in selected}, gating=gating),
)
```

  In `longitudinal_eval_report.py` add the section and insert it after
  `_headline_section` (a result without `staged` renders exactly as before):

```python
def _staged_section(staged: StagedVerdicts | None) -> str | None:
    if staged is None:
        return None
    return (
        "## Staged acceptance\n\n"
        "Computed separately; `PENDING` and `NOT_RUN` are never a pass.\n\n"
        "| Stage | Verdict |\n|---|---|\n"
        f"| Personal acceptance (CM-7 exit evidence) | {staged.personal.value} |\n"
        f"| Family acceptance (pending until P3.2) | {staged.family.value} |\n"
        f"| Full suite | {staged.full_suite.value} |"
    )
```

  Add `StagedVerdicts` to the `TYPE_CHECKING` models import of the report module and
  `staged_verdicts` to the aggregation import of the runner. In `render_report`,
  `sections` drops the `None` entries:
  `"\n\n".join(section for section in sections if section is not None) + "\n"`.
  (The report-section test is the last test of the file above.)

- [ ] **Step 7: Existing tests.** `uv run pytest tests/unit/test_eval_longitudinal_memory.py -n0`
  fails in 31 tests (rehearsed) because of the bump. Make exactly these edits, nothing
  else (the frozen scoring tests must pass unedited):
  - `_scenario()` and `_lscenario()` add `"scope": "personal"` after `"scenario_id"`;
  - `_suite_doc()` returns `{"version": 2, ...}`;
  - `test_load_suite_rejects_a_non_version_one_document` becomes
    `test_load_suite_rejects_a_document_that_is_not_version_two` and sets
    `doc["version"] = 1`;
  - `assert suite.version == 1` becomes `== 2`; `"dataset_version": 1` becomes `2`;
    `assert first.dataset_version == 1` becomes `== 2`;
  - in `test_cli_full_red_run_writes_a_report_and_returns_one` add
    `assert "## Staged acceptance" in report` and
    `assert "| Full suite | FAIL |" in report` (this proves the runner wires the verdicts).

- [ ] **Step 8: GREEN.** The new file, `test_eval_longitudinal_memory.py`, then
  `just test`, `just typecheck`, `uv run ruff check . && uv run ruff format --check .`.
  Do **not** run `just eval-longitudinal`: it needs live Ollama and is not part of this
  task's evidence.

- [ ] **Step 9: Commit** — `feat(eval): report staged longitudinal verdicts (dataset v2)`.

---

## Task 4: `eval-chat --mode stream` measures the streaming protocol

**Files:**

- Create: `scripts/eval_stream_protocol.py`, `tests/unit/test_eval_stream_protocol.py`
- Modify: `scripts/eval_chat.py`, `tests/unit/test_eval_chat.py`, `justfile` (comment)

**Interfaces:**

- Produces in `scripts/eval_stream_protocol.py`: `StreamOutcome` (`StrEnum`: `VALID`,
  `INVALID_PROTOCOL`, `EMPTY`, `ERROR`); `classify_stream_text(text: str) -> StreamOutcome`
  (pure; never `ERROR`); `StreamTurn` (frozen dataclass: `label`, `source`
  `Literal["context", "public"]`, `text`, `context`, `history`, `active_person`);
  `public_turns() -> list[StreamTurn]`; `StreamProtocolResult` (frozen dataclass of
  counts per source with `fallback_rate` and `graded`);
  `async measure_stream_protocol(turns, *, client, runs, generate=...) -> StreamProtocolResult`;
  `render_stream_report(result, *, model, runs) -> str`;
  `stream_exit_code(result, *, max_fallback_rate) -> int`.
- `eval_chat.CliOptions` gains `mode: Literal["classic", "stream"] = "classic"` and
  `max_fallback_rate: float | None = Field(default=None, ge=0, le=1)`.

The classification applies the production rules to the whole text:
`parse_streaming_emotion(text, final=True)` then `validate_streaming_body_start(body)`;
an empty body is `EMPTY`. The **fallback rate** is `(INVALID_PROTOCOL + EMPTY) /
(VALID + INVALID_PROTOCOL + EMPTY)`; `ERROR` runs are reported but excluded from it.

- [ ] **Step 1: Write the failing tests.** `tests/unit/test_eval_stream_protocol.py`:

```python
"""Streaming-protocol measurement (Plan 0056, Task 4)."""

from collections.abc import AsyncIterator
from typing import cast
from unittest.mock import Mock

import httpx
import pytest
from server.exceptions import LLMError

from scripts.eval_stream_protocol import (
    StreamOutcome,
    StreamProtocolResult,
    StreamTurn,
    classify_stream_text,
    measure_stream_protocol,
    public_turns,
    render_stream_report,
    stream_exit_code,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "text, outcome",
    [
        ("EMOTION:joy\nHola, ¿cómo estás?", StreamOutcome.VALID),
        ("EMOTION:joy\n", StreamOutcome.EMPTY),
        ("EMOTION:joy\n   ", StreamOutcome.EMPTY),
        ("Hola sin etiqueta", StreamOutcome.INVALID_PROTOCOL),
        ('EMOTION:joy\n{"response": "x"}', StreamOutcome.INVALID_PROTOCOL),
        ("EMOTION:joy\nEMOTION:anger\nhola", StreamOutcome.INVALID_PROTOCOL),
        ("EMOTION:joy", StreamOutcome.INVALID_PROTOCOL),
        ("", StreamOutcome.INVALID_PROTOCOL),
    ],
)
def test_classify_stream_text_applies_the_production_rules(
    text: str, outcome: StreamOutcome
) -> None:
    assert classify_stream_text(text) is outcome


def _client() -> httpx.AsyncClient:
    return cast("httpx.AsyncClient", Mock(spec=httpx.AsyncClient))


def _turn(source: str = "public") -> StreamTurn:
    return StreamTurn(
        label="t", source=source, text="hola", context=None, history=None, active_person=None
    )


def _generator(replies: list[str | Exception]):
    queue = list(replies)

    async def generate(
        _client: httpx.AsyncClient, _text: str, **_kwargs: object
    ) -> AsyncIterator[str]:
        reply = queue.pop(0)
        if isinstance(reply, Exception):
            raise reply
        midpoint = len(reply) // 2
        yield reply[:midpoint]
        yield reply[midpoint:]

    return generate


@pytest.mark.unit
async def test_measure_counts_each_outcome_and_keeps_errors_out_of_the_rate() -> None:
    result = await measure_stream_protocol(
        [_turn(), _turn(), _turn(), _turn()],
        client=_client(),
        runs=1,
        generate=_generator(
            ["EMOTION:joy\nHola", "sin etiqueta", "EMOTION:joy\n", LLMError("boom")]
        ),
    )

    assert (result.valid, result.invalid_protocol, result.empty, result.errors) == (1, 1, 1, 1)
    assert result.graded == 3
    assert result.fallback_rate == pytest.approx(2 / 3)


@pytest.mark.unit
async def test_measure_splits_the_counts_by_turn_source() -> None:
    result = await measure_stream_protocol(
        [_turn("context"), _turn("public")],
        client=_client(),
        runs=2,
        generate=_generator(
            ["EMOTION:joy\nHola", "EMOTION:joy\nHola", "sin etiqueta", "sin etiqueta"]
        ),
    )

    assert result.by_source["context"].fallback_rate == 0.0
    assert result.by_source["public"].fallback_rate == 1.0


@pytest.mark.unit
def test_the_fallback_rate_is_none_when_nothing_was_graded() -> None:
    assert StreamProtocolResult.none().fallback_rate is None


@pytest.mark.unit
def test_public_turns_are_synthetic_and_context_free() -> None:
    turns = public_turns()

    assert len(turns) == 12
    assert all(t.source == "public" and t.context is None and t.history is None for t in turns)
    assert any("Tom" in t.text for t in turns)


@pytest.mark.unit
def test_exit_code_applies_the_threshold_and_provider_errors() -> None:
    clean = StreamProtocolResult(valid=19, invalid_protocol=1, empty=0, errors=0, by_source={})
    errored = StreamProtocolResult(valid=19, invalid_protocol=0, empty=0, errors=1, by_source={})

    assert stream_exit_code(clean, max_fallback_rate=None) == 0
    assert stream_exit_code(clean, max_fallback_rate=0.10) == 0
    assert stream_exit_code(clean, max_fallback_rate=0.04) == 1
    assert stream_exit_code(errored, max_fallback_rate=None) == 1


@pytest.mark.unit
def test_the_report_states_the_rate_and_never_prints_model_output() -> None:
    report = render_stream_report(
        StreamProtocolResult(valid=57, invalid_protocol=3, empty=0, errors=0, by_source={}),
        model="qwen2.5:3b",
        runs=5,
    )

    assert "fallback rate" in report.lower()
    assert "5.00 %" in report
    assert "qwen2.5:3b" in report
```

  Append to `tests/unit/test_eval_chat.py`:

```python
@pytest.mark.unit
def test_parse_cli_args_accepts_the_stream_mode() -> None:
    options = parse_cli_args(["--mode", "stream", "--runs", "5", "--max-fallback-rate", "0.05"])

    assert options.mode == "stream"
    assert options.max_fallback_rate == 0.05
    assert parse_cli_args([]).mode == "classic"


@pytest.mark.unit
async def test_run_cli_stream_mode_measures_and_never_calls_the_classic_generator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    measured = AsyncMock(
        return_value=StreamProtocolResult(
            valid=60, invalid_protocol=0, empty=0, errors=0, by_source={}
        )
    )
    monkeypatch.setattr(eval_chat, "measure_stream_protocol", measured)
    classic = AsyncMock()
    monkeypatch.setattr(eval_chat.llm, "generate_response", classic)
    factory = _RecordingClientCM
    output = tmp_path / "stream.md"

    code = await run_cli(
        eval_chat.CliOptions(mode="stream", runs=5, output=output), client_factory=factory
    )

    assert code == 0
    measured.assert_awaited_once()
    classic.assert_not_called()
    assert output.read_text(encoding="utf-8")
```

- [ ] **Step 2: Watch them fail.** `uv run pytest tests/unit/test_eval_stream_protocol.py tests/unit/test_eval_chat.py -v -n0`
  — import error for the new module; the two `eval_chat` tests fail on the missing option.

- [ ] **Step 3: Implement the module.** `scripts/eval_stream_protocol.py`:

```python
"""Streaming-protocol measurement for `just eval-chat --mode stream` (Plan 0056).

Runs real turns through the production streaming generator and applies the production
protocol rules (`server.streaming_protocol`) to the text it produces. It measures how
often a reply would drop to the fallback phrase (0049 O-04); it never prints or stores
model output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import enum
import logging
from typing import TYPE_CHECKING

from server.exceptions import LLMError
from server.streaming_protocol import parse_streaming_emotion, validate_streaming_body_start

from server import llm_streaming

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Sequence

    import httpx
    from server.cognition.identity import ActivePersonContext
    from server.schemas import ConversationTurn, MemoryContext

    type StreamGenerator = Callable[..., AsyncIterator[str]]

logger = logging.getLogger(__name__)

_PERCENT = 100
_SOURCES = ("context", "public")
_PUBLIC_UTTERANCES = (
    "Hola, ¿cómo estás?",
    "Te presento a mi amigo Tom.",
    "¿Qué opinas del clima hoy?",
    "Cuéntame algo interesante.",
    "Estoy un poco cansado hoy.",
    "¿Qué sabes hacer?",
    "Buenas noches, Iroko.",
    "Gracias por la ayuda.",
    "¿Puedes decirme un chiste?",
    "Hoy fue un día largo.",
    "¿Cómo se prepara un té?",
    "Me gusta la música tranquila.",
)


class StreamOutcome(enum.StrEnum):
    """How one streamed reply ends under the production protocol rules."""

    VALID = "valid"
    INVALID_PROTOCOL = "invalid_protocol"
    EMPTY = "empty"
    ERROR = "error"


def classify_stream_text(text: str) -> StreamOutcome:
    """Classify a complete streamed reply with the production protocol rules.

    Args:
        text: The whole reply, deltas concatenated.

    Returns:
        ``VALID``, ``EMPTY`` (a valid tag with no body) or ``INVALID_PROTOCOL``.
    """
    try:
        parsed = parse_streaming_emotion(text, final=True)
        if parsed is None:
            return StreamOutcome.INVALID_PROTOCOL
        _emotion, body = parsed
        validate_streaming_body_start(body)
    except LLMError:
        return StreamOutcome.INVALID_PROTOCOL
    return StreamOutcome.VALID if body.strip() else StreamOutcome.EMPTY


@dataclass(frozen=True)
class StreamTurn:
    """One user turn to stream; ``source`` says where it came from."""

    label: str
    source: str
    text: str
    context: MemoryContext | None
    history: list[ConversationTurn] | None
    active_person: ActivePersonContext | None

    def __post_init__(self) -> None:
        """Reject an unknown source so a typo cannot create a silent third bucket."""
        if self.source not in _SOURCES:
            raise ValueError(f"source must be one of {_SOURCES}, got {self.source!r}")


def public_turns() -> list[StreamTurn]:
    """Return the synthetic, context-free chit-chat turns (public-channel shape)."""
    return [
        StreamTurn(f"public_{index}", "public", text, None, None, None)
        for index, text in enumerate(_PUBLIC_UTTERANCES, start=1)
    ]


@dataclass(frozen=True)
class StreamProtocolResult:
    """Outcome counts of one measurement, overall and per turn source."""

    valid: int
    invalid_protocol: int
    empty: int
    errors: int
    by_source: dict[str, StreamProtocolResult] = field(default_factory=dict)

    @classmethod
    def none(cls) -> StreamProtocolResult:
        """Return a result with no observations."""
        return cls(0, 0, 0, 0)

    @property
    def graded(self) -> int:
        """Observations that count toward the rate (provider errors excluded)."""
        return self.valid + self.invalid_protocol + self.empty

    @property
    def fallback_rate(self) -> float | None:
        """Share of graded replies that would drop to the fallback phrase."""
        if not self.graded:
            return None
        return (self.invalid_protocol + self.empty) / self.graded


def _tally(outcomes: Sequence[StreamOutcome]) -> StreamProtocolResult:
    return StreamProtocolResult(
        valid=outcomes.count(StreamOutcome.VALID),
        invalid_protocol=outcomes.count(StreamOutcome.INVALID_PROTOCOL),
        empty=outcomes.count(StreamOutcome.EMPTY),
        errors=outcomes.count(StreamOutcome.ERROR),
    )


async def _stream_once(
    turn: StreamTurn, client: httpx.AsyncClient, generate: StreamGenerator
) -> StreamOutcome:
    try:
        text = "".join(
            [
                delta
                async for delta in generate(
                    client,
                    turn.text,
                    context=turn.context,
                    history=turn.history,
                    active_person=turn.active_person,
                )
            ]
        )
    except Exception as exc:
        logger.warning("Provider call failed for %s (%s)", turn.label, type(exc).__name__)
        return StreamOutcome.ERROR
    return classify_stream_text(text)


async def measure_stream_protocol(
    turns: Sequence[StreamTurn],
    *,
    client: httpx.AsyncClient,
    runs: int,
    generate: StreamGenerator = llm_streaming.generate_response_stream,
) -> StreamProtocolResult:
    """Stream every turn ``runs`` times sequentially and tally the protocol outcomes.

    Args:
        turns: Synthetic turns, in execution order.
        client: Run-owned HTTP client, passed first to the generator (Plan 0039).
        runs: Repetitions per turn.
        generate: Streaming generator; the production one unless a test injects one.

    Returns:
        Overall and per-source counts. Provider errors are counted separately and
        never as a protocol failure or a pass.
    """
    outcomes: list[StreamOutcome] = []
    by_source: dict[str, list[StreamOutcome]] = {}
    for turn in turns:
        for _ in range(runs):
            outcome = await _stream_once(turn, client, generate)
            outcomes.append(outcome)
            by_source.setdefault(turn.source, []).append(outcome)
    overall = _tally(outcomes)
    return StreamProtocolResult(
        overall.valid,
        overall.invalid_protocol,
        overall.empty,
        overall.errors,
        {source: _tally(items) for source, items in by_source.items()},
    )


def _percent(rate: float | None) -> str:
    return "n/a" if rate is None else f"{rate * _PERCENT:.2f} %"


def render_stream_report(result: StreamProtocolResult, *, model: str, runs: int) -> str:
    """Render the measurement as Markdown: counts and rates only, never model output."""
    rows = [
        "| Set | Valid | Invalid protocol | Empty body | Provider errors | Fallback rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, part in (("all", result), *sorted(result.by_source.items())):
        rows.append(
            f"| {label} | {part.valid} | {part.invalid_protocol} | {part.empty} | "
            f"{part.errors} | {_percent(part.fallback_rate)} |"
        )
    return (
        "# Streaming protocol measurement\n\n"
        f"- model: {model}\n- runs per turn: {runs}\n"
        f"- graded observations: {result.graded}\n"
        f"- fallback rate (invalid protocol + empty body, over graded): "
        f"{_percent(result.fallback_rate)}\n\n" + "\n".join(rows) + "\n"
    )


def stream_exit_code(result: StreamProtocolResult, *, max_fallback_rate: float | None) -> int:
    """Return 1 on a provider error or a fallback rate above the optional limit, else 0."""
    if result.errors:
        return 1
    rate = result.fallback_rate
    if max_fallback_rate is not None and rate is not None and rate > max_fallback_rate:
        return 1
    return 0
```


  The `5.00 %` assertion of the report test needs `invalid_protocol=3` over 60 graded.
  The broad `except Exception` in `_stream_once` mirrors `eval_chat._run_case` (a
  provider failure of any kind is an `ERROR` observation).

- [ ] **Step 4: Wire the CLI.** In `scripts/eval_chat.py`: import
  `StreamTurn, measure_stream_protocol, public_turns, render_stream_report, stream_exit_code`
  from `scripts.eval_stream_protocol` (right after `from server import llm`; let
  `ruff --fix` sort it), and in `tests/unit/test_eval_chat.py` add
  `from scripts.eval_stream_protocol import StreamProtocolResult` to the top-level
  imports (the appended tests use it); add the two `CliOptions` fields; add to
  `parse_cli_args`:

```python
    parser.add_argument("--mode", choices=("classic", "stream"), default="classic")
    parser.add_argument("--max-fallback-rate", type=float)
```

  passing `mode=namespace.mode, max_fallback_rate=namespace.max_fallback_rate` to
  `CliOptions`; and in `run_cli`, right after the `factory = client_factory or ...` line:

```python
    if options.mode == "stream":
        return await _run_stream_mode(options, cases, factory)
```

```python
async def _run_stream_mode(
    options: CliOptions, cases: list[GoldenCase], factory: ClientFactory
) -> int:
    """Measure the streaming protocol on the golden context turns plus public turns."""
    turns = [
        StreamTurn(
            case.id,
            "context",
            case.question,
            case.context,
            case.history,
            case.active_person.to_context() if case.active_person else None,
        )
        for case in cases
    ]
    async with factory() as client:
        result = await measure_stream_protocol(
            [*turns, *public_turns()], client=client, runs=options.runs
        )
    stamp = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")
    output = options.output or _REPORT_DIRECTORY / f"{stamp}-chat-stream-ollama.md"
    write_report(output, render_stream_report(result, model=_effective_model(), runs=options.runs))
    logger.info(
        "Stream measurement complete: fallback_rate=%s report=%s", result.fallback_rate, output
    )
    return stream_exit_code(result, max_fallback_rate=options.max_fallback_rate)
```

  Update the `justfile` comment of `eval-chat` to
  `# Eval de fidelidad del LLM (clásico) o, con --mode stream, del protocolo EMOTION: del streaming; requiere Ollama real, no usa STT/retrieval/TTS`.

- [ ] **Step 5: GREEN.** Both test files, the existing `test_eval_chat.py` unedited
  cases, `uv run ruff check . && uv run ruff format --check .`, `just test`.

- [ ] **Step 6: Commit** — `feat(eval): measure the streaming protocol in eval-chat`.

---

## Task 5: Whisper prompt-echo guard

**Files:**

- Modify: `server/src/server/stt.py`
- Create: `tests/unit/test_stt_echo_guard.py`

**Interfaces:**

- Produces: `stt.is_prompt_echo(transcript: str, prompt: str | None) -> bool` (public,
  pure) and `stt._whisper_text(audio: bytes, hotwords: str | None) -> str` (the raw
  inference, the body `_transcribe_sync` has today). `_transcribe_sync` keeps its
  name and signature (a slow test patches it) and now discards an echo.

A transcript is an echo when, after folding case, accents and punctuation, it has at
least three words and either is a contiguous part of the normalized prompt, or is the
prompt repeated and nothing else.

- [ ] **Step 1: Write the failing tests.** `tests/unit/test_stt_echo_guard.py`:

```python
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
        "Hola Iroko, ¿cómo estás hoy?",
        f"{_PROMPT}, apaga la luz de la sala",
    ],
)
def test_real_speech_is_never_an_echo(transcript: str) -> None:
    assert is_prompt_echo(transcript, _PROMPT) is False


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
```

- [ ] **Step 2: Watch them fail.** `uv run pytest tests/unit/test_stt_echo_guard.py -v -n0`
  — `cannot import name 'is_prompt_echo'`. Expected.

- [ ] **Step 3: Implement.** In `stt.py` add `import re`, `import unicodedata`, a module
  constant `_MIN_ECHO_WORDS = 3  # shorter phrases ("Iroko", "robot doméstico") are real speech`
  and:

```python
def _normalize_words(text: str) -> str:
    """Fold case, accents and punctuation so two spellings of one phrase compare equal."""
    folded = unicodedata.normalize("NFKD", text.casefold())
    unaccented = "".join(c for c in folded if not unicodedata.combining(c))
    return " ".join(re.sub(r"[\W_]+", " ", unaccented).split())


def is_prompt_echo(transcript: str, prompt: str | None) -> bool:
    """Return whether Whisper merely repeated its own initial prompt.

    On a noise clip Whisper can return the ``initial_prompt`` as if it were speech.
    Short phrases are never treated as an echo: the prompt contains real words a
    user may say ("Iroko").

    Args:
        transcript: Text Whisper returned.
        prompt: The ``initial_prompt`` it was given, if any.

    Returns:
        True when the transcript has at least three words and is a contiguous part
        of the prompt, or the prompt repeated and nothing else.
    """
    if not prompt:
        return False
    heard = _normalize_words(transcript)
    if len(heard.split()) < _MIN_ECHO_WORDS:
        return False
    reference = _normalize_words(prompt)
    if f" {heard} " in f" {reference} ":
        return True
    return reference in heard and not heard.replace(reference, " ").strip()
```

  Rename the current `_transcribe_sync` body to `_whisper_text` (same signature,
  docstring, `ValueError` and `TranscriptionError` behaviour) and add:

```python
def _transcribe_sync(audio: bytes, hotwords: str | None) -> str:
    """Run Whisper inference and discard a transcript that is the prompt itself.

    Args:
        audio: Raw WAV bytes at 16kHz mono int16.
        hotwords: Merged hotwords string, or ``None``.

    Returns:
        Transcribed text, or ``""`` when Whisper only echoed its initial prompt.

    Raises:
        TranscriptionError: If audio cannot be processed.
        ValueError: If audio is empty.
    """
    text = _whisper_text(audio, hotwords)
    if is_prompt_echo(text, settings.whisper_initial_prompt):
        logger.warning("Whisper returned its own initial prompt — transcript discarded")
        return ""
    return text
```

  Both routes already answer an empty transcript with `422` (`routers/transcribe.py`)
  and the robot says "No speech understood — listening again"; nothing else changes.

- [ ] **Step 4: GREEN.** The new file, `tests/unit/test_stt_hotwords.py`,
  `tests/slow/test_stt_transcription.py` (skips without the model; the
  `_transcribe_sync` monkeypatch still works), `tests/integration/test_transcribe_validation.py`,
  `just test`, `just typecheck`.

- [ ] **Step 5: Commit** — `fix(stt): discard a transcript that echoes the initial prompt`.

---

## Task 6: STT probes — synthetic noise and first turn

**Files:**

- Create: `scripts/stt_probes.py`, `tests/unit/test_stt_probes.py`
- Modify: `justfile` (one recipe)

**Interfaces:** `scripts/stt_probes.py` has two subcommands. Pure, unit-tested helpers:
`noise_clip(kind: str, seconds: float, seed: int) -> bytes` (a 16 kHz mono int16 WAV;
kinds `white`, `hiss`, `pink`, `hum`; deterministic per seed),
`word_error_rate(reference: str, hypothesis: str) -> float`,
`summarize_noise(transcripts: Sequence[str], prompt: str | None) -> NoiseSummary`,
`first_turn_decision(first: Sequence[float], later: Sequence[float]) -> bool`.
Model-loading parts are not unit-tested; they are exercised in Task 7.

- [ ] **Step 1: Write the failing tests.** `tests/unit/test_stt_probes.py`:

```python
"""Pure helpers of the STT probes (Plan 0056, Task 6)."""

import io
import wave

import pytest

from scripts.stt_probes import (
    first_turn_decision,
    noise_clip,
    summarize_noise,
    word_error_rate,
)

_PROMPT = "Conversación con un robot doméstico llamado Iroko."


@pytest.mark.unit
@pytest.mark.parametrize("kind", ["white", "hiss", "pink", "hum"])
def test_noise_clips_honour_the_audio_contract(kind: str) -> None:
    with wave.open(io.BytesIO(noise_clip(kind, 1.5, 1))) as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2)
        assert wav.getnframes() == 24000


@pytest.mark.unit
def test_noise_clips_are_deterministic_per_seed_and_differ_across_seeds() -> None:
    assert noise_clip("white", 1.0, 1) == noise_clip("white", 1.0, 1)
    assert noise_clip("white", 1.0, 1) != noise_clip("white", 1.0, 2)


@pytest.mark.unit
def test_an_unknown_noise_kind_is_rejected() -> None:
    with pytest.raises(ValueError, match="kind"):
        noise_clip("brown", 1.0, 1)


@pytest.mark.unit
@pytest.mark.parametrize(
    "reference, hypothesis, rate",
    [
        ("a b c", "a b c", 0.0),
        ("a b c", "a x c", 1 / 3),
        ("a b c", "", 1.0),
        ("Qué hora es", "que HORA es.", 0.0),
    ],
)
def test_word_error_rate(reference: str, hypothesis: str, rate: float) -> None:
    assert word_error_rate(reference, hypothesis) == pytest.approx(rate)


@pytest.mark.unit
def test_word_error_rate_needs_a_reference() -> None:
    with pytest.raises(ValueError, match="reference"):
        word_error_rate("", "hola")


@pytest.mark.unit
def test_summarize_noise_separates_empty_echo_and_other() -> None:
    summary = summarize_noise(["", _PROMPT, "Gracias por ver el video", ""], _PROMPT)

    assert (summary.clips, summary.empty, summary.echo, summary.other) == (4, 2, 1, 1)
    assert summary.other_rate == pytest.approx(0.25)
    assert summary.needs_follow_up is True  # 25 % is above the 5 % rule


@pytest.mark.unit
def test_noise_follow_up_needs_more_than_five_percent_of_clips_to_be_other() -> None:
    assert summarize_noise(["x y z"] * 6 + [""] * 94, _PROMPT).needs_follow_up is True
    assert summarize_noise(["x y z"] * 5 + [""] * 95, _PROMPT).needs_follow_up is False


@pytest.mark.unit
def test_first_turn_decision_compares_the_means_with_a_fixed_margin() -> None:
    assert first_turn_decision([0.5, 0.4], [0.1, 0.1, 0.2]) is True
    assert first_turn_decision([0.2, 0.2], [0.1, 0.1, 0.2]) is False
    assert first_turn_decision([0.3], [0.15]) is False  # exactly +0.15 is not "more than"
```

- [ ] **Step 2: Watch them fail.** `uv run pytest tests/unit/test_stt_probes.py -v -n0`
  — import error. Expected.

- [ ] **Step 3: Implement.** `scripts/stt_probes.py`:

```python
"""STT probes (Plan 0056): synthetic-noise echo/hallucination and first-turn accuracy.

Usage:
    just probe-stt noise [--clips 100] [--seconds 1.5] [--wav local_clip.wav ...]
    just probe-stt first-turn [--processes 5] [--calls 4]

Both load the real Whisper model through the production `server.stt` module, so run
them with the server stopped. Audio contract: WAV · 16000 Hz · mono · int16. Noise is
synthetic; first-turn speech is synthesized by Piper from fixed Spanish phrases. No
household voice or name is used. A `--wav` file stays local and is never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
from dataclasses import dataclass
import io
import json
import logging
from pathlib import Path
import statistics
import subprocess
import sys
from typing import TYPE_CHECKING
import wave

import numpy as np
from server.settings import settings

from server import stt, tts

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 16_000
_NOISE_KINDS = ("white", "hiss", "pink", "hum")
_NOISE_FOLLOW_UP_RATE = 0.05  # Plan 0056 D-6
_FIRST_TURN_MARGIN = 0.15  # Plan 0056 D-6
_PHRASES = (
    "¿Qué hora es en este momento?",
    "Enciende la luz de la sala, por favor.",
    "Cuéntame un chiste corto.",
)
_PEAK = 0.05


def noise_clip(kind: str, seconds: float, seed: int) -> bytes:
    """Build a deterministic synthetic noise WAV.

    Args:
        kind: One of ``white``, ``hiss``, ``pink``, ``hum``.
        seconds: Clip length.
        seed: RNG seed; the same seed gives the same bytes.

    Returns:
        WAV bytes — 16000 Hz · mono · int16.

    Raises:
        ValueError: If ``kind`` is unknown.
    """
    if kind not in _NOISE_KINDS:
        raise ValueError(f"unknown noise kind {kind!r}; expected one of {_NOISE_KINDS}")
    rng = np.random.default_rng(seed)
    count = int(seconds * _SAMPLE_RATE)
    if kind == "white":
        signal = rng.normal(0, _PEAK, count)
    elif kind == "hiss":
        signal = rng.normal(0, _PEAK / 10, count)
    elif kind == "pink":
        walk = np.cumsum(rng.normal(0, 1, count))
        walk -= np.convolve(walk, np.ones(800) / 800, mode="same")
        signal = _PEAK * walk / (np.abs(walk).max() or 1.0)
    else:
        t = np.arange(count) / _SAMPLE_RATE
        signal = _PEAK * np.sin(2 * np.pi * 60 * t) + rng.normal(0, _PEAK / 10, count)
    pcm = (np.clip(signal, -1, 1) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(_SAMPLE_RATE)
        wav.writeframes(pcm.tobytes())
    return buffer.getvalue()


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Return the word-level edit distance over the reference length.

    Raises:
        ValueError: If the reference has no words.
    """
    ref = stt._normalize_words(reference).split()
    hyp = stt._normalize_words(hypothesis).split()
    if not ref:
        raise ValueError("reference must contain at least one word")
    previous = list(range(len(hyp) + 1))
    for i, ref_word in enumerate(ref, start=1):
        current = [i]
        for j, hyp_word in enumerate(hyp, start=1):
            cost = previous[j - 1] + (ref_word != hyp_word)
            current.append(min(previous[j] + 1, current[j - 1] + 1, cost))
        previous = current
    return previous[-1] / len(ref)


@dataclass(frozen=True)
class NoiseSummary:
    """Counts of what Whisper returned for clips that contain no speech."""

    clips: int
    empty: int
    echo: int
    other: int

    @property
    def other_rate(self) -> float:
        """Share of clips with a non-empty, non-echo transcript (a hallucination)."""
        return self.other / self.clips if self.clips else 0.0

    @property
    def needs_follow_up(self) -> bool:
        """Plan 0056 D-6: more than 5 % hallucinated transcripts opens a follow-up."""
        return self.other_rate > _NOISE_FOLLOW_UP_RATE


def summarize_noise(transcripts: Sequence[str], prompt: str | None) -> NoiseSummary:
    """Classify raw Whisper transcripts of noise clips as empty, echo or other."""
    empty = sum(1 for text in transcripts if not text.strip())
    echo = sum(1 for text in transcripts if text.strip() and stt.is_prompt_echo(text, prompt))
    return NoiseSummary(len(transcripts), empty, echo, len(transcripts) - empty - echo)


def first_turn_decision(first: Sequence[float], later: Sequence[float]) -> bool:
    """Plan 0056 D-6: True when call 1 is worse than the later calls by more than 0.15."""
    return statistics.fmean(first) - statistics.fmean(later) > _FIRST_TURN_MARGIN


def _run_noise(args: argparse.Namespace) -> int:
    stt.preload()
    clips = [
        noise_clip(_NOISE_KINDS[i % len(_NOISE_KINDS)], args.seconds, seed=i)
        for i in range(args.clips)
    ]
    clips += [Path(path).read_bytes() for path in args.wav]
    transcripts = [stt._whisper_text(clip, None) for clip in clips]  # raw, before the guard
    summary = summarize_noise(transcripts, settings.whisper_initial_prompt)
    print(  # noqa: T201
        f"clips={summary.clips} empty={summary.empty} echo={summary.echo} "
        f"other={summary.other} other_rate={summary.other_rate:.3f} "
        f"follow_up={'YES' if summary.needs_follow_up else 'no'}"
    )
    return 0


async def _first_turn_child(calls: int) -> list[float]:
    stt.preload()
    tts.preload()
    audio_base64, _duration_ms = await tts.synthesize(_PHRASES[0])
    wav = base64.b64decode(audio_base64)
    return [word_error_rate(_PHRASES[0], await stt.transcribe(wav)) for _ in range(calls)]


def _run_first_turn(args: argparse.Namespace) -> int:
    runs = [
        json.loads(
            subprocess.run(  # noqa: S603 — fixed interpreter and our own script
                [sys.executable, __file__, "first-turn-child", "--calls", str(args.calls)],
                capture_output=True,
                text=True,
                check=True,
            )
            .stdout.strip()
            .splitlines()[-1]
        )
        for _ in range(args.processes)
    ]
    first = [run[0] for run in runs]
    later = [wer for run in runs for wer in run[1:]]
    print(  # noqa: T201
        f"processes={args.processes} calls={args.calls} "
        f"first_mean_wer={statistics.fmean(first):.3f} later_mean_wer={statistics.fmean(later):.3f} "
        f"follow_up={'YES' if first_turn_decision(first, later) else 'no'}"
    )
    return 0


def main() -> int:
    """Entry point: ``noise``, ``first-turn`` or the internal ``first-turn-child``."""
    parser = argparse.ArgumentParser(description="STT probes (Plan 0056)")
    sub = parser.add_subparsers(dest="command", required=True)
    noise = sub.add_parser("noise")
    noise.add_argument("--clips", type=int, default=100)
    noise.add_argument("--seconds", type=float, default=1.5)
    noise.add_argument("--wav", action="append", default=[])
    first = sub.add_parser("first-turn")
    first.add_argument("--processes", type=int, default=5)
    first.add_argument("--calls", type=int, default=4)
    child = sub.add_parser("first-turn-child")
    child.add_argument("--calls", type=int, default=4)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    if args.command == "noise":
        return _run_noise(args)
    if args.command == "first-turn":
        return _run_first_turn(args)
    print(json.dumps(asyncio.run(_first_turn_child(args.calls))))  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

  The `first-turn` parent reads only the last stdout line of each child (model loaders
  log to stdout/stderr). `justfile`:

```
# Sondas de STT del Plan 0056 (cargan Whisper real; con el servidor detenido): noise | first-turn
probe-stt *ARGS:
    uv run --env-file .env python scripts/stt_probes.py {{ARGS}}
```

- [ ] **Step 4: GREEN.** `tests/unit/test_stt_probes.py`, `tests/unit/test_stt_echo_guard.py`,
  `uv run ruff check . && uv run ruff format --check .`, `just test`. Smoke by hand
  (Pipec): `just probe-stt noise --clips 4` prints one summary line.

- [ ] **Step 5: Commit** — `feat(scripts): add STT noise and first-turn probes`.

---

## Task 7: Run the measurements, record them, apply the rules

**Files:** Create `docs/evals/0056-voice-pipeline-measurements.md`; modify
`docs/roadmap/cognitive-roadmap.md` (a conditional row per triggered rule),
`docs/evals/README.md`, this plan (execution record). No production code.

Pipec runs these on the development laptop with Ollama up and the server **stopped**;
the executor records the output lines, never a transcript. Raw reports go under
`docs/evals/` through `--output`; only the curated document below is linked.

- [ ] **Step 1: Streaming protocol (O-04).**
  `just eval-chat --mode stream --runs 5 --output docs/evals/0056-stream-protocol-run1.md`
  (120 observations). Apply D-5: above 5 % → follow-up; 3 % to 8 % → repeat with
  `--runs 10 --output docs/evals/0056-stream-protocol-run2.md` and let that run decide.
- [ ] **Step 2: Echo and hallucination on noise.** `just probe-stt noise --clips 100`,
  once. The probe reads the raw transcript (`_whisper_text`, before the guard) and
  counts echoes itself, so the guard does not hide what Whisper did. Apply D-6 (more
  than 5 % "other" opens a hallucination-filter plan). If Pipec has a local clip that
  reproduced the echo, add `--wav` with it (the file stays local; only counts print).
- [ ] **Step 3: First turn.** `just probe-stt first-turn --processes 5 --calls 4`.
  Apply D-6 (mean call-1 error rate more than 0.15 above the later calls opens a
  warm-up plan).
- [ ] **Step 4: Record.** `docs/evals/0056-voice-pipeline-measurements.md` holds: date,
  commit SHA, hardware line ("non-dedicated laptop, CPU, Whisper `small`, `qwen2.5:3b`"),
  one table per measurement (command, counts, rate, rule, decision) and an honest
  limitations paragraph (synthetic noise is a proxy for the robot's room; the first-turn
  probe isolates STT from the server's other start-up work; 120 observations give a wide
  interval). Numbers only — no transcript, no name.
- [ ] **Step 5: Apply the rules.** For each triggered rule add one `Unplanned` row to the
  roadmap portfolio naming its measured trigger (streaming-protocol fallback;
  hallucination filter; Whisper warm-up). For each rule that did not trigger, write
  "closed with measured rate X %" in the measurements document and in
  `0049 O-04`'s status. Do not fix anything in this plan.
- [ ] **Step 6: Commit** — `docs(evals): record the voice-pipeline measurements`.

---

## Task 8: Documentation truth

**Files:** the docs listed under *Permitted files*. No production code.

- [ ] **Step 1: `current-state.md`.** Add one row, *Voice-pipeline reliability
  (Plan 0056)*, stating only delivered behaviour: the classic parser's contract, the
  echo guard (discards, three-word minimum), `test-pipeline` as a smoke test,
  `eval-chat --mode stream`, the staged verdicts and dataset version 2, and the
  measured numbers with their limitations. Preserve the Plan 0050 and PC-4 rows.
- [ ] **Step 2: Evaluation spec.** In the longitudinal evaluation spec change "(decided
  2026-09-30; not implemented yet)" to the implemented state, describe dataset version 2
  (`scope`), and keep the 0046 baseline described as the version-1 measurement.
- [ ] **Step 3: Operator manual.** Say what `just test-pipeline`, `just probe-stt` and
  `just eval-chat --mode stream` do and do not prove; correct any sentence found by the
  Task 0 grep that still calls `test-pipeline` the full pipeline.
- [ ] **Step 4: Roadmap, board, README.** The roadmap row becomes `Complete` with the
  PR/SHA recorded after merge; the portfolio keeps the conditional rows from Task 7;
  `docs/plans/README.md` and `open/README.md` move 0056 to closed, `NOW` empty again.
  Correct the inconsistent "Plan 0051 is written" sentence in the roadmap: Plan 0051 is
  **not** drafted.
- [ ] **Step 7: Architecture diagram.** Only if a row changed what the diagram says,
  regenerate with Archify `validate` then `deliver`; otherwise record "no diagram change".
- [ ] **Step 8: Verify and commit.** Markdown link check over the touched docs,
  `scripts/check_reserved_terms.py`, `git diff --check`, then
  `docs: align current-state and roadmap with plan 0056`.

## Non-goals

Each exclusion has an owner so that nothing is left as text only:

- **Repairing the streaming fallback** (retry once, rescue the useful text, change the
  model). Owner: a follow-up plan opened only if Task 7 measures above 5 %; the rows
  exist in the roadmap before then as conditional. `server/src/server/streaming*.py`
  and `llm_streaming.py` are not edited here.
- **What to do with malformed JSON on the classic path** (raw-text fallback or
  rejection). Owner: an explicit decision of its own; this plan only keeps today's
  behaviour pinned by tests (D-7).
- **A hallucination filter** for non-echo Whisper output on noise
  (`no_speech_prob`, `avg_logprob` thresholds). Owner: follow-up plan if D-6 triggers.
- **A Whisper warm-up inference at start-up.** Owner: follow-up plan if D-6 triggers.
- **Streaming together with scene description** (today the server answers "scene not
  available" in streaming and the robot refuses to start with both on). Owner: PC-5,
  or a short plan if Pipec brings it forward; its first step would measure the warm
  VLM latency.
- **Grants bound to an operation and speaker binding.** Owner: Plan 0051 (CM-1).
- **Changing the chat model, the streaming protocol or any wire contract.** Owner: not
  in the current queue.
- **Real recordings of people in the repository.** Probes use synthetic audio; a
  local `--wav` stays on the machine and is never printed.

## Verification

Run before claiming done, in this order:

```powershell
uv lock --check
just lint
just typecheck
just test
just audit
just check
uv run ruff format --check .
uv build --all-packages
git diff --check
```

Plus the exact deterministic CI coverage command:

```powershell
uv run pytest -m "not slow and not hardware and not eval" `
  --cov=server/src --cov=robot/src --cov-report=term --cov-fail-under=80
```

## Completion criteria

- `_parse_llm_output` raises `LLMError` for a non-text or blank `response` and for valid
  non-object JSON; a non-text `emotion` becomes `neutral`; malformed JSON still falls
  back to raw text (Task 1).
- `run_pipeline` passes an HTTP client to the LLM and the module loads without
  PortAudio; `just test-pipeline` and the justfile describe a smoke test (Task 2).
- The dataset is version 2 with a scope per scenario; the report carries personal,
  family and full-suite verdicts; the exit code is unchanged (Task 3).
- `just eval-chat --mode stream` reports counts and the fallback rate, never model
  output, and excludes provider errors from the rate (Task 4).
- A transcript that is the prompt (or a three-word-or-longer part of it, or the prompt
  repeated) is discarded; "Iroko" and "Hola Iroko" pass (Task 5).
- Both probes exist with unit-tested pure helpers (Task 6).
- The three measurements are recorded with their rules applied, and every triggered
  follow-up is a named roadmap row (Task 7).
- `current-state.md`, the operator manual, the evaluation spec and the board match the
  code; all gates above pass; coverage ≥ 80 % (Task 8).

## Real runtime acceptance

With Pipec, one session after the gates pass (outcomes and timings only):

1. `just test-pipeline --text hola robot --no-play` completes (STT skipped, LLM and TTS run).
2. The Task 7 commands produced their summary lines (recorded in the measurements
   document, not re-run).
3. `just run-server` + `just run-robot`, classic and streaming: one generic turn and
   one protected turn each (`outcome=ok`; the protected child question is answered
   through the face or a fresh PIN as in Plan 0050's acceptance). Record the active flags.
4. Stay silent with the room's normal noise for a few turns: the robot says "No speech
   understood" and never speaks or answers the prompt text.

## Rollback

Revert the squash-merged PR as one unit. No schema migration, wire change or new
dependency. Reverting the dataset bump restores version 1; the 0046 baseline report
was never rewritten.

## Closure

One PR from `fix/0056-voice-pipeline`, based on `main` after the Task 0 revalidation.
On merge: move this file to `completed/`, update the board, the roadmap row,
`current-state.md` and 0049 O-04, and record the PR number and squash SHA in a small
documentation PR (as for Plans 0050 and 0055).
