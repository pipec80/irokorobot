# 0067 — The reply to a memory offer: a dedicated listening mode, better words

> **Status:** `Ready` and `NOW` — promoted by Pipec on 2026-10-19 and executed in the same session
> (his choice: «todo tiene relación»), after Plan 0066 merged (PR #196). Written 2026-10-19 after Pipec's first hardware session with Plan 0066 (the
> short answer promoted 1 of 2 times; the other fell to ordinary conversation). Pipec chose the
> order: (1) a dedicated listening mode, (2) wider words and hotwords only in that mode, (3) measure
> silence trimming and short voice references for the speaker check (that third item is the
> separate [Plan 0068](0068-short-clip-speaker-measurement.md); this plan does not touch the voice
> thresholds). The face-only fallback was **removed from scope** by Pipec. Task 8 also records the
> hardware counts Plan 0066 left open (its Task 6). **Not rehearsed** in a scratch copy:
> the tasks below are specifications (files, rules, tests to write first), not rehearsed diffs.

> **For agentic workers:** if the status above does not say `Ready`, stop: Pipec has not promoted
> this plan. REQUIRED SUB-SKILLS: `superpowers:executing-plans`,
> `superpowers:test-driven-development`, `superpowers:verification-before-completion`,
> `superpowers:finishing-a-development-branch`. **Pipec's rules win over the skills:** one plain
> branch from `main` (`git checkout -b`), never a git worktree, subagents only if Pipec asks, and
> this plan lives under `docs/plans/`. Implement exactly the tasks below, in order, one commit per
> task, each code test observed RED for the stated reason first (the text-only Task 7 has no RED).
> If evidence contradicts the plan, stop and report the conflict instead of redesigning. Pipec runs
> every local process (server, robot, Ollama, anything that uses the camera or the microphone);
> record outcomes only, never a sentence, a value or a name. The Bash tool of this environment loses
> backslashes and non-ASCII characters in heredocs: create and edit files with the Write and Edit
> tools. Run the suite with `MEMORY_ENABLED=false` (CI does). **Pipec's standing policy:** every
> finding met while executing is fixed, not left open (Task 6 collects the ones already known).

**Goal:** After the robot speaks a memory offer, the next thing it listens to is a *reply*: it waits
longer for the end of the speech (so «sí… acepto» is one clip, not two turns), gives up after a short
window, and helps the speech-to-text with the few words a reply uses. The grammar also accepts the
words people actually say («acepto», «guárdala»). No change to who may answer, to the voice
thresholds, or to what is stored.

**Why:** The 2026-10-19 log shows three separate failures around one answer. (1) The robot closes a
clip after 800 ms of silence, so a pause inside «sí… acepto» becomes two requests and neither is an
answer. (2) Whisper wrote «Si,autorizo» for the owner and could as easily write «acerto»; the grammar
is closed and nothing biases the recognizer toward the few words expected. (3) The grammar has no
«acepto» or «guárdala». A fourth cause, the speaker check returning `unknown` on short clips, is
measured in Plan 0068, not here.

**Architecture:** The server tells the client, in an additive field of the stream's `done` event,
that the turn ended with a spoken offer (`expects_short_reply`). The client then listens once in
*reply mode*: parameters that belong to the robot (`VAD_REPLY_SILENCE_MS`, `REPLY_WAIT_S`), so the
server never knows what a robot is and the robot never knows what a memory is (the same stance as
`vision_requested`). The robot sends a matching additive request field (`short_reply`) on the
reply's request; its only effect on the server is a fixed list of hotwords for the speech-to-text.
Nothing else reads it: identity, the open-offer lookup, the grammar and the writer behave exactly as
for any other turn, so a client that sets the field gains nothing (no oracle, no wider grammar).

**Tech Stack:** Python 3.12, FastAPI, faster-whisper, sounddevice/Silero (robot), pytest. No new
dependency.

**Spec:** [ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md) decision 9 and the
Plan 0066 amendment, the Plan 0066 execution record
([Plan 0066](../completed/0066-verb-only-answer.md)), the stream wire notes in
[ADR 0012](../../adr/0012-line-delimited-stream-terminal-events.md), and the repository rules in
`.claude/rules/` (not tracked; read them from the working copy).

## Task overview

| # | Task | Closes |
|---:|---|---|
| 0 | Revalidate the baseline | — |
| 1 | The stream says an offer was spoken | the server half of the hint |
| 2 | The robot can listen in reply mode | longer pause tolerance, short window |
| 3 | The robot enters reply mode after an offer | the client half of the hint, the request field |
| 4 | The server biases the recognizer for a reply | hotwords only when asked |
| 5 | The grammar accepts the words people say | «acepto», «guárdala», emphatic trailers |
| 6 | Loose ends found in Plan 0066 | claim guard, offer guard, stale wording |
| 7 | Documentation truth | ADR note, manual, current state, indexes |
| 8 | Hardware acceptance (Pipec) | the counts |

## Global Constraints

- No real household data in any tracked file, test, prompt, doc or commit message: invented canaries
  only (`scripts/check_reserved_terms.py` guards it).
- The firewall of ADR 0021 decisions 3 and 9 is untouched: only the face-and-voice composite of the
  same person on that turn's own clip answers; the actor is resolved **first** for every message of
  the answer shape; a token never answers; anything that is not a valid answer falls through to
  ordinary generation, byte-identical. A bare «sí» still resolves nothing (decided in Plan 0066).
- The wire changes are **additive**: one optional field on `done`, one optional request field. No
  new event type (an unknown type is a hard error for today's robot), no renamed or removed field.
  The classic `/transcribe` route and the robot's classic path are unchanged.
- The audio contract is untouched (WAV, 16 000 Hz, mono, int16); a reply clip must not carry more
  trailing silence than a normal one. No `print()`; Google docstrings; type hints; `ruff` clean over
  the explicit paths of every file touched (including `scripts/`); `mypy server/src robot/src` clean.
- Every new setting is read by code (`tests/unit/test_settings_are_read.py`), documented in
  `.env.example`, and pinned by the settings default tests.
- A commit title is at most 72 characters; check `git log -1` after every commit.
- `MEMORY_CANDIDATES_ENABLED` stays `false` by default.

## Decisions

1. **D-1 — The hint is a boolean, the parameters are the robot's.** `done.expects_short_reply:
   bool = False`, true only when the offer's audio event was actually emitted on that turn (not when
   the offer was merely committed and its synthesis then failed). Robot settings:
   `VAD_REPLY_SILENCE_MS=1600` (the end-of-speech silence in reply mode; normal is 800) and
   `REPLY_WAIT_S=15` (how long to wait for speech to start; normal is 30). Both are first values to be
   tuned by Task 8, not measured ones.
2. **D-2 — One shot.** The hint applies to the single capture that follows the turn that carried it.
   If nothing is heard in `REPLY_WAIT_S`, or the turn errors, the robot returns to normal listening;
   the hint is never sticky.
3. **D-3 — A reply clip is no longer than a normal clip.** Reply mode tolerates a longer pause
   *inside* the speech, but the trailing silence it uploads is trimmed to the normal
   `VAD_SILENCE_MS` tail, so the speaker check receives no more silence than today (the longer
   tolerance must not make the voice evidence worse).
4. **D-4 — The request field only chooses hotwords.** `short_reply` (form field, default false) on
   `/transcribe/stream` selects the fixed `SHORT_REPLY_HOTWORDS` for the speech-to-text and nothing
   else. It does not change identity resolution, the open-offer lookup, the grammar or the timing
   profile of the request. A flagged request whose transcript is not an answer is the ordinary turn.
5. **D-5 — Words (Pipec, 2026-10-19: «lo más común es "sí acepto", "sí, guárdala"»).** `acepto` and
   `acepta` are long verbs like `autorizo` (alone or followed by `guardar`, `a guardar`, `que
   guardes`), with `no acepto` and `no acepta` as rejections. `guárdala` is a short verb like
   `guárdalo`: alone only after a leading «sí». After a long verb, `guárdalo`, `guárdala` and `sí` are
   courtesy words, not a value («Sí, autorizo, guárdalo» is an answer). The offer's own wording
   («Dime: sí, autorizo.») does not change.
6. **D-6 — Out of scope, by Pipec.** The face-only fallback is not planned. The speaker thresholds, the
   voice references and silence trimming for the speaker check belong to Plan 0068. A bare «sí» stays
   refused.
7. **D-7 — Plan 0066 leftovers are fixed here (standing policy).** Task 6: the claim guard misses
   the present tense («te tomo nota»), `mark_offered` does not repeat the «no other open offer» guard
   of its read, and two documents still say the answer repeats the value. The conditional «si» without
   an accent is **not** a defect: Whisper wrote «Si,autorizo» for the owner, so the cue must accept it.

## Required reading

- `AGENTS.md`, `docs/architecture/implementation-guardrails.md`, `.claude/rules/`.
- [ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md) decision 9 (and the
  amendments), [ADR 0012](../../adr/0012-line-delimited-stream-terminal-events.md).
- Server: `server/src/server/{schemas_streaming,streaming,streaming_render,stt,pipeline,claim_guard}.py`,
  `server/src/server/routers/transcribe.py`, `server/src/server/cognition/intent_resolution.py`,
  `server/src/server/memory/{candidates,candidate_dialogue}.py`.
- Robot: `robot/src/robot/{audio_capture,app,app_streaming,fsm_types,server_client,stream_events,settings}.py`.
- The tests named in each task, and `tests/unit/test_architecture_guards.py` (the offer lookup and
  commit names may only be used in their homes; this plan adds no call to them).

## Permitted files

- Server production: `schemas_streaming.py`, `streaming.py`, `streaming_render.py`, `stt.py`,
  `routers/transcribe.py`, `claim_guard.py`, `cognition/intent_resolution.py`, `memory/candidates.py`.
- Robot production: `audio_capture.py`, `app.py`, `app_streaming.py`, `fsm_types.py`,
  `server_client.py`, `stream_events.py`, `settings.py`.
- Tests: the ones named in each task, plus `tests/unit/test_settings.py` and
  `tests/unit/test_claim_guard.py`.
- Config and docs: `.env.example`, ADR 0021 (a dated note), `docs/runbooks/operator-manual.md`,
  `docs/architecture/current-state.md`, `docs/architecture/memory-and-world-state.md`, ADR 0022 (one
  wording fix), `docs/roadmap/cognitive-roadmap.md`, the plan index files and this plan.

No new route, event type, migration or dependency. Settings added: the two robot ones of D-1.

## Review Focus

The inputs the tasks' tests do not name but a person will meet; each has its test in the task that
owns the code.

1. The offer is committed but its audio synthesis fails: the stream has no offer event, so `done`
   must not say a reply is expected (Task 1).
2. Reply mode hears nothing for `REPLY_WAIT_S`, or the turn that follows errors: the next capture is
   normal and the hint is gone (Task 3).
3. A server without the field (older) or a robot that ignores it (older): both keep working
   unchanged (Task 1, Task 3).
4. A reply that is not an answer («¿qué hora es?») or a flagged request from an unrelated client:
   the reply is the ordinary turn, and unflagged requests still pass no hotwords (Task 4).
5. A long pause *inside* the reply and a long silence *after* it: one clip for the first, and a clip
   no longer than a normal one for the second (Task 2).

---

## Task 0: Revalidate the baseline

- [ ] **Step 0: Status.** This plan says `Ready` and Plan 0066 is merged, otherwise stop.
- [ ] **Step 1: Branch.** `git checkout main && git pull`, clean tree, then
  `git checkout -b feat/0067-reply-listening-mode`; record the base SHA.
- [ ] **Step 2: Baseline.** `just gate`; record the outcome and test count (3398 at the close of the
  Plan 0066 code). A pre-existing failure is reported, not hidden.
- [ ] **Step 3: Re-audit.** `rg -n "class StreamDoneEvent|def capture_utterance|def _compute_chunk_budget|class DoneEvent|def transcribe_stream|SHORT_REPLY|short_reply" server/src robot/src` finds what this plan names
  (no `short_reply` yet). A difference is reported before code.

## Task 1: The stream says an offer was spoken

**Files:** modify `server/src/server/schemas_streaming.py`, `server/src/server/streaming_render.py`,
`server/src/server/streaming.py`; tests modified `tests/unit/test_schemas_streaming.py` and
`tests/integration/test_stream_offer.py`.

**Interfaces.** Produces: `StreamDoneEvent.expects_short_reply: bool = False` (description: «the turn
ended with a spoken question the client should listen to once, with a short reply in mind»);
`StreamState.offer_spoken: bool = False`, set by `stream_pipeline` exactly when it yields the offer's
audio event, and read by the `done` builder. The deterministic-plan path (`stream_response_plan`) never
sets it.

- [ ] **Step 1: Failing tests:** `test_done_event_defaults_to_no_short_reply_expected` and its JSON
  round trip; in `test_stream_offer.py`, next to the existing offer cases: `test_done_expects_a_short_
  reply_after_a_spoken_offer` (true), `test_done_expects_nothing_without_an_offer` (false),
  `test_done_expects_nothing_when_the_offer_audio_failed` (the offer is committed, its synthesis
  raises `TTSError`, no offer event is emitted, `done` says false). Expected RED: the field does not
  exist (`AttributeError`/missing key).
- [ ] **Step 2: Implement** the field, the state flag and the wiring; update `_STREAM_200_DESCRIPTION`
  in `routers/transcribe.py` (one sentence) so the OpenAPI text stays true.
- [ ] **Step 3:** run `tests/unit/test_schemas_streaming.py tests/integration/test_stream_offer.py
  tests/integration/test_openapi_contract.py tests/integration/test_api_contract.py
  tests/unit/test_architecture_guards.py`; lint and types.
- [ ] **Step 4: Commit** `feat(server): say in done that a spoken offer expects a reply (plan 0067)`.

## Task 2: The robot can listen in reply mode

**Files:** modify `robot/src/robot/audio_capture.py`, `robot/src/robot/settings.py`, `.env.example`;
tests modified `tests/unit/test_audio_capture.py` and `tests/unit/test_settings.py`.

**Interfaces.** Produces: `capture_utterance(max_wait_s: float = 30.0, *, close_silence_ms: int | None
= None) -> bytes`. With `None` the behavior is exactly today's. With a value, the loop closes after
that much silence, and the uploaded frames are then cut back so the trailing silence equals the
normal `settings.vad_silence_ms` tail (D-3). `_compute_chunk_budget` takes the override.
`Settings.vad_reply_silence_ms: int = 1600` and `Settings.reply_wait_s: float = 15.0`.

- [ ] **Step 1: Failing tests** (copy the file's fake-stream pattern; the autouse fixture forces the
  RMS engine): (a) `test_reply_capture_keeps_a_pause_inside_the_speech_in_one_clip` — speech, a gap
  longer than the normal close but shorter than the reply close, more speech: one clip holding both
  parts; (b) `test_reply_capture_uploads_no_more_trailing_silence_than_a_normal_one` — the same
  utterance followed by a long silence yields a clip of the same length as a normal capture;
  (c) `test_reply_capture_without_speech_returns_empty_after_the_wait`;
  (d) `test_capture_without_an_override_is_unchanged` (the existing tests stay as they are); settings
  defaults 1600 and 15.0 in `test_robot_settings_defaults`. Expected RED: `TypeError` on the unknown
  keyword.
- [ ] **Step 2: Implement** the keyword, the budget and the trim; add both settings and their
  `.env.example` lines (`VAD_REPLY_SILENCE_MS`, `REPLY_WAIT_S`) with one comment each.
- [ ] **Step 3:** run `tests/unit/test_audio_capture.py tests/unit/test_settings.py
  tests/unit/test_settings_are_read.py tests/unit/test_vad.py`; lint and types.
- [ ] **Step 4: Commit** `feat(robot): listen in reply mode, longer pause and short wait (plan 0067)`.

## Task 3: The robot enters reply mode after an offer

**Files:** modify `robot/src/robot/stream_events.py`, `fsm_types.py`, `app_streaming.py`, `app.py`,
`server_client.py`; tests modified `tests/unit/test_stream_events.py`,
`tests/unit/test_robot_app_streaming.py`, `tests/unit/test_robot_app.py`,
`tests/unit/test_server_client.py`.

**Interfaces.** Consumes: `capture_utterance(..., close_silence_ms=...)` (Task 2),
`done.expects_short_reply` (Task 1), the form field name `short_reply` (Task 4). Produces:
`DoneEvent.expects_short_reply: bool = False` (parsed with `data.get(..., False)`);
`LoopContext.short_reply_next: bool` (set when a `done` with the flag is drained; survives IDLE) and
`LoopContext.short_reply: bool` (moved from `short_reply_next` by LISTENING for the turn it captures;
reset by IDLE); `transcribe_stream(audio, *, identity_token=None, frame=None, short_reply: bool =
False)` sends the form field `short_reply=true` only when true.

- [ ] **Step 1: Failing tests:** a `done` with the field parses true and without it false; after a
  drained `done` carrying the flag, LISTENING calls `capture_utterance` once with
  `max_wait_s=settings.reply_wait_s` and `close_silence_ms=settings.vad_reply_silence_ms`, and the
  next LISTENING calls it with the defaults (one shot); an empty capture (no speech in the wait)
  returns to IDLE and clears the flag; an ERROR transition clears it; THINKING passes `short_reply=
  True` to `transcribe_stream` for the reply turn and `False` for the next; `transcribe_stream` omits
  the field when false. Expected RED: unknown attribute/keyword.
- [ ] **Step 2: Implement** the parse, the two context fields (IDLE resets only `short_reply`), the
  set at `done`, the move and the call in LISTENING, and the client field.
- [ ] **Step 3:** run the four test files plus `tests/unit/test_robot_stream_validation.py`; lint and
  types.
- [ ] **Step 4: Commit** `feat(robot): listen once for a short reply after a spoken offer (plan 0067)`.

## Task 4: The server biases the recognizer for a reply

**Files:** modify `server/src/server/stt.py` (the constant), `server/src/server/routers/transcribe.py`;
tests modified `tests/integration/test_transcribe_stream.py`,
`tests/integration/test_openapi_contract.py`, `tests/integration/test_memory_dialogue_routes.py`.

**Interfaces.** Produces: `SHORT_REPLY_HOTWORDS: tuple[str, ...] = ("sí", "no", "acepto", "autorizo",
"apruebo", "guárdalo", "guárdala")` in `stt.py` (generic «words of a short reply»; the speech layer
names no memory concept). The stream route accepts `short_reply: Annotated[bool, Form()] = False` and
calls `_run_stt(audio_bytes, list(SHORT_REPLY_HOTWORDS) if short_reply else [])`. The classic route is
unchanged.

- [ ] **Step 1: Failing tests:** with `short_reply=true`, `stt.transcribe` is awaited with
  `extra_hotwords == list(SHORT_REPLY_HOTWORDS)`; without it, `[]` (the two existing tests that pin
  `[]` stay green and unchanged); `list_entity_names` is never awaited in either case; a flagged
  request whose transcript is an ordinary question gets the same reply fields as the unflagged one
  (except timings); the OpenAPI schema lists the field. Expected
  RED: the form field is ignored (the hotwords stay `[]`).
- [ ] **Step 2: Implement** the constant, the parameter and the call.
- [ ] **Step 3:** run the three files plus `tests/unit/test_stt_hotwords.py` and
  `tests/integration/test_transcribe_memory.py`; lint and types.
- [ ] **Step 4: Commit** `feat(server): bias the recognizer toward a short reply when asked (plan 0067)`.

## Task 5: The grammar accepts the words people say

**Files:** modify `server/src/server/cognition/intent_resolution.py`; tests modified
`tests/unit/test_memory_answer_grammar.py` (and the Task 4 test that waited for it).

**Interfaces.** `parse_memory_answer` keeps its signature. D-5 defines the words.

- [ ] **Step 1: Failing tests** (parametrized, `message → (accept, phrase)`): accepted valueless:
  «Acepto», «Sí, acepto», «Acepta», «Acepto guardar», «Acepto a guardar», «Acepto que guardes»,
  «Sí, guárdala», «Sí po, guárdala», «Sí, autorizo, guárdalo», «Sí, autorizo, guárdala», «Autorizo,
  sí», «Apruebo, guárdalo»; rejected valueless: «No acepto», «No, no acepta»; with a value: «Acepto
  guardar el mate» → `(True, "el mate")`; still refused (`None`): «Guárdala», «Ya, guárdala», «Acepto
  mi», «Sí, guárdala silencio» (a short verb followed by a non-article), «Acepto guardar» plus seven
  words. In `test_memory_dialogue_routes.py`, one end-to-end case: a flagged stream request
  (`short_reply=true`) whose transcript is «Sí, acepto» promotes the open offer. Expected RED:
  `assert None == MemoryAnswer(...)`, and the end-to-end case falls through to ordinary conversation.
- [ ] **Step 2: Implement:** `acepto`, `acepta`, `no acepto`, `no acepta` and their `guardar` forms in
  the prefix tuples (longest first, as the existing ones), `guardala` in the short-prefix and
  stand-alone-after-yes sets, and the courtesy words `guardalo`, `guardala`, `si` in the trailers
  that follow a long verb. Update the module comment and the `parse_memory_answer` docstring. The
  cognitive core imports nothing from `server.memory` (the import-graph test).
- [ ] **Step 3:** run `tests/unit/test_memory_answer_grammar.py tests/unit/test_intent_resolution.py
  tests/unit/test_cognitive_controller.py tests/integration/test_import_graph.py
  tests/integration/test_memory_dialogue_routes.py`; lint and types.
- [ ] **Step 4: Commit** `feat(server): accept «acepto» and «guárdala» as the memory answer (plan 0067)`.

## Task 6: Loose ends found in Plan 0066

**Files:** modify `server/src/server/claim_guard.py`, `server/src/server/memory/candidates.py`; tests
modified `tests/unit/test_claim_guard.py`, `tests/integration/test_memory_candidates_store.py`,
`tests/integration/test_candidate_dialogue.py`.

- [ ] **Step 1: Failing tests:** `test_claim_guard`: «Genial, te tomo nota.», «Tomo nota.» and «Ya
  tomo nota de eso.» are claims (replaced by the fixed reply); not claims: «Si quieres, tomo nota.»,
  «No tomo nota de eso.», «¿Quieres que tome nota?»; the offer sentence of `OFFER_QUESTION` replaces
  the old one in the not-a-claim list. `test_memory_candidates_store`: `mark_offered` of a second
  candidate of a person who already has an open offer returns `False` and changes nothing; once the
  first one lapses it succeeds. Expected RED: the claims pass through; the second mark succeeds.
- [ ] **Step 2: Implement:** add the present tense of «tomar nota» to the claim patterns (the
  conditional and negated guards already in the module apply); add the «no other open offer» condition
  to the `mark_offered` UPDATE (`AND NOT EXISTS (...)` over the same person's `offered` rows inside
  the answer window and not lapsed, the same predicate `_OFFERABLE_SQL` reads). The Plan 0066 tests
  that need **two** open offers (store ambiguity cases, dialogue «two open offers», the ambiguity of a
  visitor) now create the second one with a small raw-SQL helper, because the public API can no
  longer produce that state: it stays defended in depth, and the tests keep proving it.
- [ ] **Step 3:** run the three files plus `tests/unit/test_architecture_guards.py`; lint and types.
- [ ] **Step 4: Commit** `fix(server): close the present-tense claim and the double offer (plan 0067)`.

## Task 7: Documentation truth (text only, no RED)

- [ ] ADR 0021: a dated note under decision 9 (the reply hint and its request field are additive and
  change nothing about who answers; the hotwords; the new words).
- [ ] `docs/runbooks/operator-manual.md`: the two robot settings and how to tune them, the words, and
  what the log shows (`Speaker verdict` unchanged).
- [ ] `docs/architecture/current-state.md` (stream `done` field, robot reply mode),
  `docs/architecture/memory-and-world-state.md` (the answer no longer has to repeat the value; the two
  stale sentences) and ADR 0022 (the one wording fix), `.env.example` checked,
  `docs/roadmap/cognitive-roadmap.md`, the plan index files and the local table (never committed).
- [ ] `uv run ruff format --check .`, `uv run python scripts/check_reserved_terms.py`, every relative
  link of the touched `.md` files resolves; commit `docs: close plan 0067`; open the PR; merge only
  with Pipec's go-ahead. Refresh the architecture diagram if `current-state.md` changed what it shows.

## Task 8: Hardware acceptance (Pipec runs everything)

Counts only, never a sentence or a value. With `MEMORY_CANDIDATES_ENABLED=true`, in full sentences
near the microphone, answering the offer **in your own words**:

- [ ] Five offers answered «sí… acepto» or «sí, autorizo» with a visible pause in the middle: how many
  were one turn and promoted.
- [ ] Two offers answered «no acepto»: how many rejected.
- [ ] Two offers answered «sí, guárdala»: how many promoted.
- [ ] Three offers left unanswered for 15 s: how many returned to normal listening on their own.
- [ ] One unrelated question asked as the reply to an offer: it is answered normally.
- [ ] Plan 0066's own counts, in the same session: two offers answered with the old full phrase
  («sí, autorizo guardar …»): how many promoted; three casual «autorizo» or «sí, guarda» with
  **no** open offer: nothing saved, an ordinary reply.

If fewer than 4 of 5 pauses survive as one turn, report the count and the values of
`VAD_REPLY_SILENCE_MS` and `REPLY_WAIT_S` you tried; those are tuning, not a redesign. A `Speaker
verdict: unknown` is **not** a failure of this plan: count it separately (it is Plan 0068).

## Completion criteria

1. Tasks 0 to 8 done, one commit per task, every code test RED before GREEN.
2. `just gate` green with the baseline plus the new tests.
3. After a spoken offer the robot listens once in reply mode; a pause inside the reply stays one clip;
   the clip uploads no more trailing silence than a normal one; silence for `REPLY_WAIT_S` returns to
   normal listening.
4. «Acepto», «sí, guárdala» and the emphatic trailers are answers; every refusal of Task 5 holds.
5. Unflagged requests pass no hotwords; a flagged one changes only the hotwords.
6. The hardware counts of Task 8 are recorded.

## Rollback boundary

Each task is one commit. Tasks 1 to 4 are reverted together (the hint and the flag are additive:
reverting only one half leaves the other inert). Task 5 and Task 6 revert alone. Nothing is stored
differently and no migration is added.

## Not here, and why

- Voice thresholds, voice references, silence trimming for the speaker check: [Plan 0068](0068-short-clip-speaker-measurement.md).
- A face-only fallback: removed by Pipec.
- A bare «sí» as a valid answer: decided against in Plan 0066; it may be reopened after Plan 0068.
- Reply mode on the classic route and the robot's classic path.
- A physical or touch confirmation (button, tablet): a future embodiment concern.

## Execution record

*(Filled in when the plan is executed.)*
