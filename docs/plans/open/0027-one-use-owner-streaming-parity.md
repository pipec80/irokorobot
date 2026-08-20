# One-Use Owner Streaming Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Status:** Ready for owner review. Depends on merged Plans 0025 and 0026 and
revalidation of Plan 0022's reliable-streaming contracts.

**Goal:** Carry the same one-use owner grant through
`POST /transcribe/stream`, preserving exact NDJSON/audio success rules and
clearing the robot token only from the terminal `done` certificate.

**Architecture:** The streaming route receives the same optional identity
header and request-local resolver as classic audio. A protected deterministic
plan consumes the token before rendering. The existing terminal `done` event
adds one backward-compatible boolean; older clients ignore it and the updated
robot clears local state only after parsing it.

**Tech Stack:** FastAPI streaming response, Pydantic NDJSON schemas, async
generators, httpx streaming client, existing Plan 0022 render/protocol modules,
pytest.

**Spec:** [Plan 0024 — owner-authenticated personal-memory MVP
design](0024-owner-authenticated-memory-mvp-design.md)

## Global Constraints

- Read Plans 0022, 0024, 0026 and every streaming file/test before editing.
- Preserve the success order exactly: `text_heard` once, `emotion` once, one or
  more valid WAV `audio` events, then `done` once and last.
- Every audio chunk remains WAV 16 kHz, mono, signed int16.
- Do not add a new event type. Add only
  `authentication_consumed: bool = false` to the existing `done` event.
- No `done` is emitted or accepted without prior audio.
- A token consumed server-side remains consumed even if transport/TTS fails.
  If the robot never receives `done`, it may retain the stale token; replay is
  safely denied by the server on the next attempt.
- Generic streaming does not resolve the actor and does not consume the token.
- Streaming carries exactly the same `PERSONAL_PROTECTED_READ`/`child_data`
  capability as classic mode. Transport parity must not widen it into memory
  mutation, biometric, home-control, PC-administration, or actuator authority.
- Do not relax Plan 0022 fallback, partial-audio, persistence, logging, or EOF
  semantics.
- No visual streaming support, face/voice identity, PIN changes, RAG, database,
  dependency, or environment change.

---

## File map

| File | Responsibility |
|---|---|
| `server/src/server/routers/transcribe.py` | Accept token header and compose resolver in streaming. |
| `server/src/server/schemas_streaming.py` | Add consumed boolean to terminal event. |
| `server/src/server/streaming_render.py` | Serialize terminal consumed state. |
| `server/src/server/streaming.py` | Propagate consumed state for deterministic plan rendering. |
| `robot/src/robot/server_client.py` | Send optional token on streaming request. |
| `robot/src/robot/stream_events.py` | Parse additive terminal boolean. |
| `robot/src/robot/app_streaming.py` | Clear token after terminal certificate. |
| streaming tests | Preserve protocol and one-use behavior. |

---

### Task 1: Extend the terminal NDJSON contract additively

**Files:**

- Modify: `server/src/server/schemas_streaming.py`
- Modify: `robot/src/robot/stream_events.py`
- Modify: `tests/unit/test_streaming_protocol.py`

**Interfaces:**

```python
class StreamDoneEvent(BaseModel):
    ...
    authentication_consumed: bool = False


@dataclass(frozen=True)
class DoneEvent:
    ...
    authentication_consumed: bool = False
```

- [ ] **Step 1: Write RED compatibility tests**

Assert an old done payload without the field parses as `False`, a new payload
parses `True`, and extra future fields remain tolerated. Preserve rejection of
unknown event types and bad ordering.

- [ ] **Step 2: Observe RED**

```powershell
uv run pytest -n0 tests/unit/test_streaming_protocol.py -q
```

- [ ] **Step 3: Add the defaulted field only**

Do not rename events or timings. In the robot parser use
`bool(data.get("authentication_consumed", False))`.

- [ ] **Step 4: Run protocol tests**

```powershell
uv run pytest -n0 tests/unit/test_streaming_protocol.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add server/src/server/schemas_streaming.py robot/src/robot/stream_events.py tests/unit/test_streaming_protocol.py
git commit -m "feat(streaming): report consumed owner grant"
```

---

### Task 2: Propagate consumed state through server rendering

**Files:**

- Modify: `server/src/server/streaming_render.py`
- Modify: `server/src/server/streaming.py`
- Modify: `tests/integration/test_transcribe_stream.py`
- Modify: `tests/integration/test_transcribe_stream_resilience.py`

**Interfaces:**

```python
def stream_response_plan(
    *,
    text_heard: str,
    plan: ResponsePlan,
    stt_ms: int,
    request_start: float,
    authentication_consumed: bool = False,
) -> AsyncIterator[str]: ...
```

- [ ] **Step 1: Write RED renderer tests**

For a deterministic protected plan, parse emitted lines and assert the final
event contains `authentication_consumed=true`; all preceding events do not.
For generic/fallback paths assert false. Re-run no-done-without-audio and exact
terminal ordering assertions.

- [ ] **Step 2: Observe RED**

```powershell
uv run pytest -n0 tests/integration/test_transcribe_stream.py tests/integration/test_transcribe_stream_resilience.py -q
```

- [ ] **Step 3: Thread one boolean to `_done_event`**

Do not put authentication state in audio/text/emotion events. Preserve all
existing timing/outcome fields and fallback behavior. The boolean is request
metadata, not speech content and never enters TTS or persistence.

- [ ] **Step 4: Run Plan 0022 streaming regression**

```powershell
uv run pytest -n0 tests/integration/test_transcribe_stream.py tests/integration/test_transcribe_stream_resilience.py tests/unit/test_streaming_protocol.py tests/unit/test_llm_streaming.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add server/src/server/streaming_render.py server/src/server/streaming.py tests/integration/test_transcribe_stream.py tests/integration/test_transcribe_stream_resilience.py
git commit -m "feat(streaming): propagate owner grant outcome"
```

---

### Task 3: Resolve owner evidence in the streaming route

**Files:**

- Modify: `server/src/server/routers/transcribe.py`
- Create: `tests/integration/test_owner_authenticated_stream.py`

**Interfaces:**

- Consumes optional `X-Iroko-Identity-Token` header.
- Produces the same deterministic child response/audio plus terminal consumed
  state.

- [ ] **Step 1: Write the protected streaming RED test**

Seed Plan 0025 data, issue a token, mock STT to return
`¿Quiénes son mis hijos?`, and use real route/controller/tool composition.
Parse NDJSON and assert:

```python
assert event_types == ["text_heard", "emotion", "audio", "done"]
assert audio_events[0]["text"] == "Tus hijos son Máximo y Dominga."
assert done["authentication_consumed"] is True
```

Replay the token and assert only the non-disclosing denial is spoken. Assert no
protected name appears in audit/log fields.

- [ ] **Step 2: Add generic non-consumption RED test**

Send a valid token with generic text. Assert the generic stream path runs,
terminal consumed is false, then use the same token on the protected question
and receive the names once.

- [ ] **Step 3: Observe RED**

```powershell
uv run pytest -n0 tests/integration/test_owner_authenticated_stream.py -q
```

- [ ] **Step 4: Compose request resolver once**

Create one request-local resolver before `decide(event)`, pass its async actor
and consent boundaries to `_voice_controller`, then pass its `consumed` value
to deterministic plan rendering. Generic `stream_pipeline` remains unchanged
and reports false.

- [ ] **Step 5: Run route regression**

```powershell
uv run pytest -n0 tests/integration/test_owner_authenticated_stream.py tests/integration/test_transcribe_stream.py tests/integration/test_transcribe_stream_resilience.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add server/src/server/routers/transcribe.py tests/integration/test_owner_authenticated_stream.py
git commit -m "feat(streaming): authorize one-use owner turn"
```

---

### Task 4: Carry and clear the token in the streaming robot

**Files:**

- Modify: `robot/src/robot/server_client.py`
- Modify: `robot/src/robot/app_streaming.py`
- Modify: `tests/unit/test_server_client.py`
- Modify: `tests/unit/test_robot_app.py`

**Interfaces:**

```python
async def transcribe_stream(
    audio: bytes, *, identity_token: str | None = None
) -> AsyncIterator[StreamEvent]: ...
```

- [ ] **Step 1: Write client RED tests**

Assert the header is absent by default and present exactly once when supplied.
Assert old/new done events parse. No log may contain the token.

- [ ] **Step 2: Write streaming FSM RED tests**

Prove `on_thinking_stream()` passes `ctx.identity_token`, generic done retains
it, consumed done clears it, EOF before done leaves it locally but a replay is
denied server-side, and playback/order error recovery remains unchanged.

- [ ] **Step 3: Observe RED**

```powershell
uv run pytest -n0 tests/unit/test_server_client.py tests/unit/test_robot_app.py -q
```

- [ ] **Step 4: Implement token propagation without transcript inspection**

Pass token directly from `LoopContext`. Let `_audio_chunks()` receive the
context or a narrow callback and clear only on a parsed `DoneEvent` whose field
is true. Do not classify protected intent in robot code.

- [ ] **Step 5: Run robot streaming regression**

```powershell
uv run pytest -n0 tests/unit/test_server_client.py tests/unit/test_robot_app.py tests/unit/test_streaming_protocol.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add robot/src/robot/server_client.py robot/src/robot/app_streaming.py tests/unit/test_server_client.py tests/unit/test_robot_app.py
git commit -m "feat(robot): preserve one-use auth in streaming"
```

---

### Task 5: Close Plan 0027 gates

**Files:**

- Modify: `docs/architecture/current-state.md`
- Modify: `docs/plans/README.md`
- Modify: `docs/plans/open/0027-one-use-owner-streaming-parity.md`

- [ ] **Step 1: Run focused cross-mode parity**

```powershell
uv run pytest -n0 tests/integration/test_owner_authenticated_turn.py tests/integration/test_owner_authenticated_stream.py tests/integration/test_transcribe_stream.py tests/integration/test_transcribe_stream_resilience.py tests/unit/test_server_client.py tests/unit/test_robot_app.py tests/unit/test_streaming_protocol.py -q
```

- [ ] **Step 2: Run repository gates**

```powershell
just lint
just typecheck
just test
just audit
just check
git diff --check
```

- [ ] **Step 3: Compare classic/streaming security matrix**

Both modes must match for valid, absent, expired, replayed, malformed, generic
non-consumption, denial speech, tool invocation, audit redaction, and client
state. Streaming must additionally pass Plan 0022 event/audio/EOF guarantees.

- [ ] **Step 4: Update evidence and request review**

Record automated parity only. Real microphone, Piper playback, operator PIN,
and repeated human scenarios remain open in Plan 0028.

## Completion criteria

Plan 0027 is complete only when classic and streaming modes have the same
one-use owner behavior, Plan 0022 contracts remain green, old robots tolerate
the additive field, neither mode widens the grant beyond the named child-data
read, and no physical/runtime acceptance is claimed.
