# P0-C6 Reliable Streaming Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Status:** Complete and verified. Implemented through commits `a238ab9`,
`0b78529`, `0e2fefe`, `a368d85`, `3f09877`, `4127bdb`, `c2bd789`, `9580fc7`,
`7c24583`, `47870b4`, `96f8721`, and `1927912`. All 4 tasks passed their own
task-scoped review (2 needed one fix round each); the final whole-plan review
found no Critical issues, 3 Important findings (all fixed) and adjudicated 2
residual items — see Execution Evidence below. Real `just run-server` +
`just run-robot` operator acceptance on 2026-08-20 confirmed the headline
invariant on live hardware, including one live reproduction of the exact
2026-08-17 hybrid-output failure mode, this time spoken audibly instead of
silent. It has no technical dependency on Plan 0021.

**Goal:** Make every successful streaming turn audibly speak at least one
contract-valid WAV chunk, reject invalid or incomplete output explicitly, and
prevent character prompts from imposing conflicting classic and streaming
formats.

**Architecture:** Character profiles describe identity and behavior only;
classic and streaming adapters each append exactly one private output contract.
A focused server protocol module validates the incremental emotion preamble, a
render module owns synthesis/fallback/first-audio metrics, and a small robot
state machine validates NDJSON ordering and terminal success. `done` becomes a
success certificate and is never emitted or accepted without prior audio.

**Tech Stack:** Python 3.12, async generators, Pydantic NDJSON schemas, httpx,
Piper, pytest, existing `just` gates; no dependency, wire-schema, database,
environment, model, or endpoint change.

## Global Constraints

- Read `AGENTS.md`, Plan 0020, `.Codex/rules/python-style.md`, the audio rules,
  and all files listed below before editing.
- Preserve classic `POST /transcribe` JSON and streaming NDJSON event types.
- Valid success order is exactly `text_heard` once, `emotion` once, one or
  more non-empty `audio` events, then `done` once and last.
- Every audio event carries WAV 16 kHz, mono, signed int16. Document this in
  every function that touches audio bytes.
- Invalid/empty model output must never be spoken, logged raw at INFO/WARN, or
  persisted. If fallback TTS succeeds it is spoken and `done` follows; if TTS
  or transport fails, the stream ends without `done` and the robot reports an
  error.
- Preserve already-spoken audio on a later LLM failure, append the safe fallback
  if possible, and do not persist the partial turn.
- Do not add an error event, NDJSON field, route, setting, database field,
  dependency, provider, or future emotion modulation.
- Keep functions at most 30 lines and source files at most 200 lines. Split by
  responsibility because `server/src/server/streaming.py` and
  `server/src/server/characters/__init__.py` already exceed that boundary.
- C6 does not change intent rules (C5), visual behavior (C7), identity,
  authorization, memory policy, or consolidation policy.

## File Map

Create:

- `server/src/server/streaming_protocol.py` — pure incremental preamble/body
  validation.
- `server/src/server/streaming_render.py` — stream state, WAV synthesis,
  fallback, safe-plan rendering, and operational metrics.
- `robot/src/robot/stream_validation.py` — typed NDJSON ordering/terminal state.
- `tests/unit/test_llm_streaming.py`
- `tests/unit/test_streaming_protocol.py`
- `tests/unit/test_robot_stream_validation.py`
- `tests/unit/test_robot_app_streaming.py`

Modify:

- `server/src/server/characters/base.py`
- `server/src/server/characters/parser.py`
- `server/src/server/characters/iroko.py`
- `server/src/server/characters/nova.py`
- `server/src/server/characters/profiles/ejemplo_vendedor.md`
- `server/src/server/llm.py`
- `server/src/server/llm_streaming.py`
- `server/src/server/streaming.py`
- `robot/src/robot/app_streaming.py`
- `robot/src/robot/audio_playback.py`
- `robot/src/robot/fsm_types.py`
- `robot/src/robot/app.py`
- existing character, LLM, stream, audio-playback, and robot tests named below.

Do not modify `schemas_streaming.py`, `stream_events.py`,
`llm_transport.py`, public API schemas, or the audio contract.

---

### Task 1: Give each LLM adapter sole ownership of its output contract

**Files:**

- Modify: `server/src/server/characters/base.py`
- Modify: `server/src/server/characters/parser.py`
- Modify: `server/src/server/characters/iroko.py`
- Modify: `server/src/server/characters/nova.py`
- Modify: `server/src/server/characters/profiles/ejemplo_vendedor.md`
- Modify: `server/src/server/llm.py`
- Modify: `server/src/server/llm_streaming.py`
- Modify: `tests/unit/test_character_parser.py`
- Modify: `tests/integration/test_character_registry.py`
- Modify: `tests/unit/test_llm_generate.py`
- Create: `tests/unit/test_llm_streaming.py`

**Interfaces:**

- `build_system_prompt` remains format-neutral and unchanged in
  signature.
- `llm._classic_system_prompt(base_prompt: str) -> str` appends exactly one
  classic JSON contract.
- `llm_streaming._streaming_system_prompt(base_prompt: str) -> str` appends
  exactly one `EMOTION:<emotion>\n` plus plain-text contract.
- `CharacterProfile.__post_init__()` rejects a base prompt containing both
  legacy markers `"response"` and `"emotion"`.

- [ ] **Step 1: Write failing profile and prompt-ownership tests.**

  Assert a format-free Markdown profile parses; a direct `CharacterProfile`
  with both JSON markers raises `ValueError`; built-in Iroko, Nova, and the
  tracked example contain neither JSON markers nor `EMOTION:`. Capture classic
  Ollama messages and assert one JSON contract, no streaming contract, and the
  existing `_OLLAMA_RESPONSE_SCHEMA`. Capture streaming messages for built-in
  and dynamic profiles and assert one streaming contract, no JSON markers, and
  no structured `format` argument.

- [ ] **Step 2: Run RED.**

  ```powershell
  uv run pytest -n0 tests/unit/test_character_parser.py tests/integration/test_character_registry.py tests/unit/test_llm_generate.py tests/unit/test_llm_streaming.py -k "contract or profile" -v
  ```

  Expected: format-free profiles are rejected, legacy profiles are accepted,
  and streaming prompts contain contradictory contracts.

- [ ] **Step 3: Migrate profile validation atomically.**

  Add `CharacterProfile.__post_init__()` with a named tuple of forbidden marker
  pairs and a concise exception. Remove `_CONTRACT_MARKERS` and its requirement
  from `parse_character()`. Remove all format paragraphs from built-ins,
  example profile, and test fixtures. Do not silently strip format from an
  unsafe profile; reject it so registry fallback behavior remains visible.
  Extract `_parse_frontmatter(content: str, name: str) -> tuple[dict[str,
  object], str]` so modified `parse_character()` stays within 30 lines.

- [ ] **Step 4: Add private adapter contracts.**

  In `llm.py`, define `_CLASSIC_OUTPUT_CONTRACT` with JSON keys and valid
  emotions, then append it once after `build_system_prompt`. Keep
  `_OLLAMA_RESPONSE_SCHEMA` unchanged. In `llm_streaming.py`, replace the suffix
  concatenation with `_streaming_system_prompt`, whose input is the
  format-neutral prompt and whose output contains exactly one streaming
  protocol instruction. Extract prompt preparation and provider transport so
  modified `generate_response()` and `generate_response_stream()` are each at
  most 30 lines. Use these exact seams:

  - `_classic_system_prompt(base_prompt: str) -> str`, appending only the JSON
    response contract.
  - `_streaming_system_prompt(base_prompt: str) -> str`, appending only the
    emotion-line/plain-text contract.
  - `_build_classic_base_prompt` and `_build_streaming_base_prompt`, each
    returning `str`, accepting the same typed context/onboarding/emotion/
    active-person arguments as its public entry point, and only calling
    `build_system_prompt`.
  - `_stream_local_response(messages: list[dict[str, str]]) ->
    AsyncIterator[str]`, owning only the Ollama streaming transport.

  Do not add a channel boolean to `build_system_prompt`.

- [ ] **Step 5: Run GREEN and commit.**

  ```powershell
  uv run pytest -n0 tests/unit/test_character_parser.py tests/integration/test_character_registry.py tests/unit/test_llm_generate.py tests/unit/test_llm_streaming.py -k "contract or profile" -v
  just lint
  git add server/src/server/characters server/src/server/llm.py server/src/server/llm_streaming.py tests/unit/test_character_parser.py tests/integration/test_character_registry.py tests/unit/test_llm_generate.py tests/unit/test_llm_streaming.py
  git commit -m "refactor(streaming): separate character output contracts"
  ```

---

### Task 2: Validate the streaming model protocol independently

**Files:**

- Create: `server/src/server/streaming_protocol.py`
- Modify: `server/src/server/llm_streaming.py`
- Create: `tests/unit/test_streaming_protocol.py`
- Modify: `tests/unit/test_llm_streaming.py`

**Interfaces:**

```python
def parse_streaming_emotion(
    buffer: str,
    *,
    final: bool = False,
) -> tuple[str, str] | None:
    """Parse one complete emotion preamble or reject an invalid protocol."""


def validate_streaming_body_start(body: str) -> None:
    """Reject structured metadata or a repeated protocol tag before speech."""
```

- Incomplete input with `final=False` returns `None`.
- A valid complete line returns normalized emotion and remainder; an unknown
  emotion becomes neutral.
- `final=True` without a complete valid line raises `LLMError` without raw
  model content in the message.
- A body beginning with `{`, `[`, a code fence, or another `EMOTION:` raises
  `LLMError` before any emotion/audio event is emitted.

- [ ] **Step 1: Write the pure protocol matrix.**

  Import `server.llm_streaming` as a module so missing attributes fail inside
  a test assertion rather than during collection. Add exact tests
  `test_parse_emotion_waits_for_fragmented_line`,
  `test_parse_emotion_rejects_incomplete_final_line`,
  `test_validate_body_rejects_structured_json`, and
  `test_validate_body_rejects_repeated_protocol`. Cover token-fragmented valid
  tags, unknown emotion, missing newline,
  `EMOTION: joy {"response":"hola"}`,
  `EMOTION:joy\n{"response":"hola"}`, empty
  final stream, code fence, list, and repeated tag. Assert exception text is
  bounded and never includes the raw candidate.

- [ ] **Step 2: Run RED.**

  ```powershell
  uv run pytest -n0 tests/unit/test_streaming_protocol.py -v
  ```

  Expected: assertion failures because the existing
  `llm_streaming.parse_streaming_emotion` has no `final` behavior and
  `llm_streaming.validate_streaming_body_start` is absent. Test collection must
  succeed.

- [ ] **Step 3: Implement and re-export compatibility.**

  Move the regex/parser from `llm_streaming.py` into the new module. Import and
  re-export both protocol functions from `llm_streaming.py` temporarily so
  tests exercise the existing seam while Task 3 moves orchestration.
  Use only bounded exception strings such as
  `Invalid streaming response protocol`.

- [ ] **Step 4: Run GREEN and commit.**

  ```powershell
  uv run pytest -n0 tests/unit/test_streaming_protocol.py tests/unit/test_llm_streaming.py -v
  git add server/src/server/streaming_protocol.py server/src/server/llm_streaming.py tests/unit/test_streaming_protocol.py tests/unit/test_llm_streaming.py
  git commit -m "feat(streaming): validate model response protocol"
  ```

---

### Task 3: Guarantee audible server success and safe fallback

**Files:**

- Create: `server/src/server/streaming_render.py`
- Modify: `server/src/server/streaming.py`
- Modify: `tests/integration/test_transcribe_stream.py`
- Modify: `tests/integration/test_transcribe_stream_resilience.py`

**Interfaces:**

```python
class StreamOutcome(StrEnum):
    OK = "ok"
    PROTOCOL_FALLBACK = "protocol_fallback"
    LLM_FALLBACK = "llm_fallback"
    PARTIAL_FALLBACK = "partial_fallback"
    TTS_ERROR = "tts_error"


class StreamFallbackReason(StrEnum):
    INVALID_PROTOCOL = "invalid_protocol"
    EMPTY_STREAM = "empty_stream"
    LLM_ERROR = "llm_error"


@dataclass
class StreamState:
    request_start: float
    pending_emotion: str | None = None
    emotion: str | None = None
    response_parts: list[str] = field(default_factory=list)
    tts_ms_total: int = 0
    audio_chunks: int = 0
    first_audio_ms: int | None = None
    recordable: bool = True
    outcome: StreamOutcome = StreamOutcome.OK


async def synthesize_sentence(sentence: str, state: StreamState) -> str:
    """Return one NDJSON audio event with WAV 16 kHz mono int16."""


async def emit_fallback(
    state: StreamState,
    *,
    reason: StreamFallbackReason,
) -> AsyncIterator[str]:
    """Emit neutral when absent, then one safe fallback audio event."""


async def stream_response_plan(
    *,
    text_heard: str,
    plan: ResponsePlan,
    stt_ms: int,
    request_start: float,
) -> AsyncIterator[str]:
    """Render an authorized plan as emotion, WAV audio, and certified done."""
```

`server.streaming` continues to re-export `stream_response_plan` so the router
import remains unchanged. `streaming.py` stays an orchestration module below
200 lines after moving state/render helpers.

- [ ] **Step 1: Replace vacuous tests with behavioral RED tests.**

  Add exact tests named `test_stream_hybrid_json_uses_audible_protocol_fallback`,
  `test_stream_structured_body_uses_audible_protocol_fallback`,
  `test_stream_truncated_emotion_uses_audible_protocol_fallback`,
  `test_stream_empty_model_output_uses_audible_protocol_fallback`,
  `test_stream_emotion_only_uses_audible_protocol_fallback`,
  `test_stream_plain_text_uses_audible_protocol_fallback`,
  `test_stream_partial_llm_failure_preserves_audio_then_fallback`,
  `test_stream_protocol_fallback_tts_failure_has_no_done`,
  `test_stream_invalid_output_is_not_logged_raw`, and
  `test_every_done_has_prior_contract_valid_audio`.

  For each invalid output below, assert exact order
  `text_heard, emotion(neutral), audio(fallback), done`, exactly one fallback
  TTS call, `tts_ms > 0`, no record/consolidation, and raw output absent from
  `caplog`:

  - the observed one-line hybrid JSON output;
  - a valid emotion line followed by JSON;
  - truncated emotion tag;
  - empty stream;
  - valid `EMOTION: joy\n` followed by empty/whitespace-only body;
  - plain text without a tag.

  Preserve as characterization GREEN the existing fragmented valid protocol,
  provider failure after one spoken sentence, and WAV validation. Strengthen
  the partial-failure assertion to exact order
  `text_heard, emotion(joy), audio(normal), audio(fallback), done`, with no
  second emotion and no persistence. For fallback-TTS RED, feed an invalid
  protocol, make TTS raise `TTSError`, collect the generator inside
  `pytest.raises(TTSError)`, and assert no collected line is `done`.

  Add this test helper next to the existing `_post_stream` helper; use the
  file's existing valid WAV fixture and monkeypatch target:

  ```python
  def _post_stream_with_deltas(
      client: TestClient,
      monkeypatch: pytest.MonkeyPatch,
      audio: bytes,
      deltas: list[str],
  ) -> list[dict[str, object]]:
      async def fake_generate(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
          for delta in deltas:
              yield delta

      monkeypatch.setattr(llm_streaming, "generate_response_stream", fake_generate)
      response = _post_stream(client, audio)
      assert response.status_code == 200
      return _parse_ndjson(response.text)
  ```

  The hybrid regression must assemble the exact observed output and use the
  existing `streaming.record_text_turn` spy:

  ```python
  deltas = ['EMOTION: joy {"response": "¡Qué emocionante!", "emotion": "joy"}']
  record = Mock()
  monkeypatch.setattr(streaming, "record_text_turn", record)
  events = _post_stream_with_deltas(client, monkeypatch, wav_bytes, deltas)
  assert [event["type"] for event in events] == ["text_heard", "emotion", "audio", "done"]
  assert events[1]["value"] == "neutral"
  assert events[2]["text"] == settings.llm_fallback_phrase
  record.assert_not_called()
  ```

- [ ] **Step 2: Run RED.**

  ```powershell
  uv run pytest -n0 tests/integration/test_transcribe_stream.py tests/integration/test_transcribe_stream_resilience.py -k "hybrid or structured_body or truncated or empty_stream or emotion_only or without_emotion or fragmented or partial or fallback_tts or event_order or operational_log or wav_contract" -v
  ```

  Expected RED applies to hybrid/structured-body/truncated/empty/emotion-only/plain,
  no-audio postcondition, bounded logs, and metrics. Fragmented valid, existing
  partial-provider failure, and WAV checks are characterization GREEN. Current
  invalid cases can end with `tts=0`; raw tail is logged; the plain-text case
  is incorrectly spoken as success.

- [ ] **Step 3: Move render responsibility and enforce the postcondition.**

  Implement typed `StreamState`, synthesis, fallback, safe-plan rendering, first
  audio measurement (`request_start` to first ready AudioEvent), chunk count,
  and bounded completion logging in `streaming_render.py`. In
  `_consume_llm_stream`, do not emit emotion until the body start validates.
  At EOF call the parser with `final=True`; convert protocol `LLMError` into the
  same fallback path as provider failure. Store a parsed preamble in
  `pending_emotion`; promote it to emitted `emotion` only after the first
  non-whitespace body content passes `validate_streaming_body_start`.
  EOF with only a preamble is invalid. A pre-audio fallback ignores
  `pending_emotion` and emits neutral. `emit_fallback()` emits neutral only
  when `state.emotion is None`; after partial audio it preserves the already
  emitted emotion and adds only fallback audio. Mark every fallback/partial
  outcome non-recordable. Emit `done` only when `audio_chunks >= 1`.

  Keep touched functions under 30 lines by extracting:

  - `_consume_preamble(buffer: str, state: StreamState) -> tuple[str, bool]`
    validates and removes the first complete protocol line.
  - `_consume_body(buffer: str, state: StreamState) -> tuple[str, list[str]]`
    returns the unsplit tail and complete sentence strings.
  - `_finalize_model_output(buffer: str, state: StreamState) ->
    AsyncIterator[str]` validates EOF and emits final sentence or fallback.
  - `_record_success(prepared: PreparedTextTurn, state: StreamState,
    scheduler: ConsolidationScheduler) -> None` records only outcome OK.
  - `_done_event(stt_ms: int, request_start: float, state: StreamState) -> str`
    requires at least one audio chunk and serializes final timing.

  Split prompt assembly from long LLM entry points into
  `_classic_system_prompt()` and `_streaming_system_prompt()` with separate
  transport helpers. Split `parse_character()` into `_parse_frontmatter()` plus
  existing `_split_body()` and `_build_personality()`. Do not grow
  `characters/__init__.py`.

- [ ] **Step 4: Keep operational logs useful and private.**

  Log sentence text selected for synthesis, plus typed outcome,
  `first_audio_ms`, and chunk count. For invalid output log only the bounded
  reason; remove `%r` tail logging. If TTS fails, log `first_audio_ms=None` or
  current count and re-raise without emitting `done`.
  Before commit, inspect every touched source: no modified function may exceed
  30 lines and no new source file may exceed 200 lines. Refactor through the
  named helpers rather than waive the local rule.

- [ ] **Step 5: Run GREEN and commit.**

  ```powershell
  uv run pytest -n0 tests/unit/test_streaming_protocol.py tests/integration/test_transcribe_stream.py tests/integration/test_transcribe_stream_resilience.py -v
  git add server/src/server/streaming.py server/src/server/streaming_render.py tests/integration/test_transcribe_stream.py tests/integration/test_transcribe_stream_resilience.py
  git commit -m "fix(streaming): guarantee audible protocol fallback"
  ```

---

### Task 4: Reject incomplete or invalid streams on the robot

**Files:**

- Create: `robot/src/robot/stream_validation.py`
- Modify: `robot/src/robot/app_streaming.py`
- Modify: `robot/src/robot/audio_playback.py`
- Modify: `robot/src/robot/fsm_types.py`
- Modify: `robot/src/robot/app.py`
- Create: `tests/unit/test_robot_stream_validation.py`
- Create: `tests/unit/test_robot_app_streaming.py`
- Modify: `tests/unit/test_audio_playback.py`
- Modify: `tests/unit/test_robot_app.py`

**Interfaces:**

```python
@dataclass
class StreamValidationState:
    emotion_seen: bool = False
    audio_chunks: int = 0
    done_seen: bool = False

    def accept(self, event: StreamEvent) -> None:
        """Advance valid order or raise ServerError."""

    def finish(self) -> None:
        """Require one audio event and exactly one final done event."""
```

```python
async def play_wav_stream(
    chunks: AsyncIterator[bytes],
    *,
    on_chunk_start: Callable[[int], None] | None = None,
) -> None:
    """Play WAV 16 kHz mono int16 chunks and report each playback start."""
```

`LoopContext` gains `stream_request_start: float | None`; idle resets it and
streaming thinking sets it before requesting/consuming the first event.

- [ ] **Step 1: Write the pure ordering tests.**

  Prove valid emotion/audio/done succeeds. Assert `ServerError` for done before
  audio, EOF before done with zero or partial audio, duplicate emotion/done,
  repeated `TextHeardEvent`, audio before emotion, and any event after done.
  Use exact names `test_valid_stream_finishes`,
  `test_done_before_audio_is_rejected`,
  `test_partial_audio_without_done_is_rejected`,
  `test_duplicate_done_is_rejected`, and
  `test_event_after_done_is_rejected`.

- [ ] **Step 2: Write FSM/playback RED tests.**

  A valid stream must log AudioEvent text, first chunk received, first playback
  start, and chunk count, then return IDLE. Invalid/partial cases return ERROR;
  partial audio may already have played. Assert the playback callback runs
  immediately before each `play_wav` with one-based indices. Assert idle clears
  the timestamp and thinking starts it before the first network iteration.

  The critical EOF regression supplies emotion plus one audio and no done:

  ```python
  ctx.stream_events = _events(EmotionEvent("joy"), _audio_event("Hola."))
  state = await on_speaking_stream(ctx)
  assert state is RobotState.ERROR
  play_wav.assert_awaited_once()
  ```

- [ ] **Step 3: Run RED.**

  ```powershell
  uv run pytest -n0 tests/unit/test_robot_stream_validation.py tests/unit/test_robot_app_streaming.py tests/unit/test_audio_playback.py tests/unit/test_robot_app.py -k "stream or chunk or idle_resets" -v
  ```

  Expected: validation module/callback/timestamp do not exist and current robot
  accepts zero-audio or EOF-without-done as IDLE.

- [ ] **Step 4: Implement the state machine and metrics.**

  Keep protocol policy in `stream_validation.py`; keep decoding/logging in
  `app_streaming.py`. Continue consuming after the first `done` so a duplicate
  or later event is detected, then call `finish()` at EOF. Store the DoneEvent
  and log pipeline success only after `finish()` validates EOF, so a duplicate
  or later event cannot produce a false success log. Log each non-empty
  authorized `AudioEvent.text`; decode only after validation. Use
  `time.perf_counter()` consistently for robot receive/playback measurements.
  Keep `play_wav_stream()` within 30 lines by extracting producer draining or
  callback invocation to a private helper; keep `app_streaming` short by
  delegating transition validation to `StreamValidationState`.

- [ ] **Step 5: Run GREEN and commit.**

  ```powershell
  uv run pytest -n0 tests/unit/test_robot_stream_validation.py tests/unit/test_robot_app_streaming.py tests/unit/test_audio_playback.py tests/unit/test_robot_app.py -v
  git add robot/src/robot/stream_validation.py robot/src/robot/app_streaming.py robot/src/robot/audio_playback.py robot/src/robot/fsm_types.py robot/src/robot/app.py tests/unit/test_robot_stream_validation.py tests/unit/test_robot_app_streaming.py tests/unit/test_audio_playback.py tests/unit/test_robot_app.py
  git commit -m "fix(robot): reject incomplete audio streams"
  ```

---

### Task 5: Verify, document, and run repeated real streaming acceptance

**Files:**

- Modify only after evidence: current-state, runtime-policy audit, Plan 0014,
  plans README, runtime runbook, and this plan.

- [ ] **Step 1: Run focused and repository gates.**

  ```powershell
  uv run pytest -n0 tests/unit/test_character_parser.py tests/integration/test_character_registry.py tests/unit/test_llm_generate.py tests/unit/test_llm_streaming.py tests/unit/test_streaming_protocol.py tests/integration/test_transcribe_stream.py tests/integration/test_transcribe_stream_resilience.py tests/unit/test_robot_stream_validation.py tests/unit/test_robot_app_streaming.py tests/unit/test_audio_playback.py tests/unit/test_robot_app.py -v
  just lint
  just typecheck
  just test
  just audit
  just check
  git diff --check
  ```

  If a mutating gate changes files, inspect and commit the change with its
  owning task, then rerun. Request independent review of Plan 0020, this plan,
  contracts, server/robot protocol state machines, RED/GREEN logs, and diff.
  Resolve every P0/P1 finding with a failing regression and record explicit
  PASS before real acceptance.

- [ ] **Step 2: Run real streaming acceptance three times.**

  With disposable DB, loopback, `ROBOT_STREAMING=true`, and
  `VISION_ENABLED=false`, run `just services`, `just run-server`, and
  `just run-robot`. Speak a generic greeting at least three times, then ask one
  deterministic date question and one protected family question. For each
  record literal STT, every logged AudioEvent text, audible playback,
  server first-audio-ready, robot first-chunk/playback, chunks, stage timings,
  outcome, and pass/fail. Date and protected turns must be exact, audible, and
  show `llm=0`. A successful `done` with zero audio or `tts=0` fails.

- [ ] **Step 3: Update evidence and commit.**

  Mark C6 complete only after repeatable real audio. Keep P0 open for C7 and
  combined final acceptance.

  ```powershell
  git add docs/architecture/current-state.md docs/architecture/p0-runtime-policy-audit.md docs/plans/0014-p0-runtime-policy-hardening-design.md docs/plans/README.md docs/runbooks/p0-runtime-acceptance.md docs/plans/0022-p0-reliable-streaming-output.md
  git commit -m "docs(p0): record C6 verification"
  ```

  Run:

  ```powershell
  uv run pre-commit run --files docs/architecture/current-state.md docs/architecture/p0-runtime-policy-audit.md docs/plans/0014-p0-runtime-policy-hardening-design.md docs/plans/README.md docs/runbooks/p0-runtime-acceptance.md docs/plans/0022-p0-reliable-streaming-output.md
  git diff --check
  git status --short
  ```

  Final status must be clean; hook changes require
  inspection, a follow-up commit, and a rerun.

## Rollback and Stop Conditions

- Revert C6 commits; there is no migration/data mutation.
- Stop if the fix requires a new wire event/field, schema-breaking parser,
  remote provider, model change, dependency, persistent transcript log, or
  identity/policy change.
- Do not salvage or speak structured JSON from an invalid streaming response in
  P0; use the fixed local fallback.

## Completion Criteria

- Classic and streaming prompts contain one non-conflicting contract each.
- Invalid, hybrid, truncated, empty, and partial output cannot become silent
  success or persisted memory.
- Every server `done` has prior valid audio; every robot success has one final
  `done`; EOF/duplicates/order errors become ERROR.
- First-audio/chunk evidence is observable without raw invalid-model leakage.
- WAV and public API contracts remain intact; full gates and repeated physical
  acceptance are recorded.

## Execution Evidence

Implemented via `superpowers:subagent-driven-development` — one fresh
implementer subagent per task, a task-scoped reviewer after each, and a final
whole-plan reviewer at the end. Session hit its monthly API spend limit mid-review
of Task 3's original commit; the controller personally re-ran every gate
(`just typecheck`/`lint`/`test`/`audit`/`check`) in place of that one dispatched
review, documented in commit `4127bdb`.

- Prompt/protocol RED/GREEN: Task 1 (`a238ab9`) — 61 tests, format-free
  profiles rejected pre-fix, accepted post-fix; classic/streaming contracts
  confirmed mutually exclusive.
- Streaming protocol parser RED/GREEN: Task 2 (`0e2fefe`, `a368d85`) — 14
  tests covering fragmented tags, unknown emotion, the exact observed
  2026-08-17 hybrid string, code fences, and repeated tags; no raw candidate
  text ever appears in an exception message.
- Server fallback RED/GREEN: Task 3 (`3f09877`, fix round `4127bdb`) — 32
  tests; every named invalid case (hybrid JSON, structured body, truncated
  tag, empty stream, tag-only body, plain text) produces exactly
  `text_heard, emotion(neutral), audio(fallback), done`, never silence.
- Robot validation RED/GREEN: Task 4 (`c2bd789`, fix round `9580fc7`) — 42
  tests; `ServerError` on done-before-audio, EOF-without-done, duplicate
  done, and event-after-done; the critical EOF regression (emotion + one
  audio + no done) confirmed `ERROR` with the partial audio already played.
- Repository gates (final, on `1927912`): `just lint` clean; `just typecheck`
  — mypy 81 files, pyright 0 errors; `just test` 641 passed; `just audit`
  clean; `just check` — 17/17 pre-commit hooks; `git diff --check` clean.
- Independent review: 4 task-scoped reviews (2 clean on first pass, 2 needed
  one fix round each) plus one whole-plan review (model: most capable
  available) over the full 8-commit range. Verdict: "Ready to merge — with
  fixes," no Critical findings, the headline invariant (every `done` has
  prior audio, across all 6 named invalid cases plus mid-stream provider
  failure) traced and confirmed true in the actual code. 3 Important findings
  fixed in one combined fix wave (`7c24583`, `47870b4`, `96f8721`) plus one
  scoped re-review (all addressed, no new breakage); one sibling issue the
  re-review surfaced was fixed directly (`1927912`, zero structural cost).
  One residual item was ruled and parked rather than fixed: a TTS failure
  occurring *inside* the LLM-error fallback's own retry (Ollama and Piper
  failing together) still propagates uncaught and unlogged — real but
  narrow, and closing it needs a deliberate call (raise this file's 200-line
  cap, or extract a shared guard) that is a project decision, not a
  same-session patch. Also flagged, not this plan's defect to fix: the
  Global Constraints name `characters/__init__.py` (350 lines) as needing
  the same split `streaming.py` got, but no task in this plan is scoped to
  touch it.
- Repeated real operator evidence (2026-08-20, `just run-server` +
  `just run-robot`, `ROBOT_STREAMING=true`/`VISION_ENABLED=false`, local
  disposable DB): 4 live turns, every `done` preceded by `chunks>=1` and
  `tts_ms>0` — zero silent successes. One turn reproduced the real
  hybrid/invalid-protocol failure mode live against Ollama (`outcome=protocol_fallback`,
  the fixed fallback phrase spoken audibly, `tts_ms=312`) — a direct field
  confirmation of the fix, not only a synthetic test. One turn (`¿Cómo se
  llaman mis hijos?`) confirmed `source=deterministic`, `llm_ms=0`, the exact
  non-disclosing denial, audible. One turn (a date question) fell through to
  the LLM instead of the deterministic tool — expected: C5 typed intent
  resolution (Plan 0021) is not yet implemented on this branch, this is not a
  C6 regression. The run covered 1 clean generic greeting plus the
  fallback-triggering turn rather than 3 clean repeats of a plain greeting as
  written above; the operator judged this sufficient given real hardware
  constraints (non-dedicated laptop mic) and that the fallback case is the
  higher-value proof.
- Final commit and clean status: clean (`git status --short`, `git diff --check`
  both pass on this branch after every commit above).
