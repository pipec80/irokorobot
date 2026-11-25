# 0089 — The vision model diagnosed, measured and tuned, then «¿qué ves?» over streaming

> **Status:** **Draft, for Pipec's review** (written 2026-11-24). Not `Ready`: it becomes executable
> only when Pipec answers *Pipec's decisions* at the end and promotes it. Source: the PC-5 row of the
> [roadmap](../../roadmap/cognitive-roadmap.md) («it decides whether scene description must work in
> streaming mode») and its row *Vision on the streaming route*, which names this plan. Plan 0088's
> reading had to run on the slow classic route, because the robot's startup guard refuses streaming
> with server vision. Its hardware sitting
> ([0088b acceptance](../../evals/0088b-documents-acceptance.md)) ran the laptop out of memory and
> left three findings: the vision model's memory and time budget, clearer camera phrases, and a
> thorough reading test. Pipec added three requests on 2026-11-24:
> - logs detailed enough to know why the model failed;
> - a stress test of the vision model, which has never been measured;
> - a tuning of the model's allowed settings (no fine-tuning, no other model).
>
> **One plan, in this order (Pipec's decision):** diagnose, measure, tune, then streaming. Only the
> vision model is tuned, but its coexistence with Whisper, the 3B text model and Piper (the same RAM
> and the same 2 GB GPU) is measured. No new ADR (ADR **0041** stays free). One plain branch from
> `main` (`feat/0089-vision-and-streaming`), one PR.

> **For agentic workers:** if the status above does not say `Ready`, stop. Read `CLAUDE.md`,
> `AGENTS.md` and every file of `.claude/rules/` in full first. REQUIRED SUB-SKILLS:
> `superpowers:executing-plans` (inline), `superpowers:test-driven-development` for every task,
> `superpowers:verification-before-completion` before any claim of done,
> `superpowers:requesting-code-review` and `superpowers:receiving-code-review` for Task 10, and
> `superpowers:finishing-a-development-branch` at the end. Review agents run on `sonnet` and read
> `.claude/` in full before reading code. **Pipec's rules win over the skills:** one plain branch
> from `main`, never a git worktree; this plan lives under `docs/plans/`. One commit per task; every
> test seen RED for the stated reason first. If evidence contradicts the plan, stop and report; **a
> discovery this plan's goal does not need is recorded, not built.** The Bash tool loses
> backslashes and non-ASCII characters in heredocs: use the Write and Edit tools. Commit titles:
> Conventional Commits, at most 72 characters, check `git log` after each commit; never pipe
> `git commit`; `git add` with explicit paths. Run the suite with `MEMORY_ENABLED=false` as CI does.
> Never `uv sync` without `--extra cuda`. No `just gate` or full suite in the background while
> Pipec rehearses (15.7 GB of RAM). Pipec starts the server and the robot. Before pushing:
> `pyright`, `ruff` and `mypy` over the whole project, `uv run ruff format --check .`, and `ruff`
> with explicit paths over any file under `scripts/` (the hook lints them, `ruff check .` does not).

## What the code does today (verified 2026-11-24 on `main` at `515595f`, Plan 0088 merged)

Re-verify each item on `main` in Task 0; **stop and report** if one is false.

1. **The robot refuses streaming with server vision.** `robot/src/robot/app.py`
   `_guard_streaming_vision_compat()` runs first in `_run()`: with `settings.robot_streaming` it
   awaits `server_client.check_vision_enabled()` (`GET /health`, field `vision_enabled`, a missing
   field read as `False`) and, when true, logs an error and raises `SystemExit(1)`. Its docstring
   gives the reason of the July 2026 forensic audit (F-08): «this combination would silently drop
   "what do you see?" turns». Three unit tests in `tests/unit/test_robot_app.py` and two in
   `tests/unit/test_server_client.py` pin it.
2. **That reason no longer holds.** `server/src/server/routers/transcribe.py` `transcribe_stream`
   turns every `SceneDescriptionRequest` into `scene_unavailable_plan()` («Ahora mismo no puedo
   mirar desde este canal.»), whatever `VISION_ENABLED` says; it is spoken and recorded like any
   fixed reply. `tests/integration/test_transcribe_stream.py`
   `test_stream_scene_request_always_gets_the_fixed_unavailable_plan` pins it for both values of
   the switch. Nothing is dropped: the guard only blocks valid combinations, such as Plan 0088's
   «Iroko, lee esto» over streaming.
3. **Both voice routes already carry the turn's own frame.** With `FACE_AUTHENTICATION_ENABLED`
   the route validates the optional `frame` field (`read_contract_image`, a bad frame degrades to
   none) into `frame_bytes`; the robot attaches one frame per turn only with
   `ROBOT_FACE_AUTH_ENABLED` (`app_streaming.capture_face_frame_if_enabled`, shared by both
   modes). Plan 0088 D-17 reads that frame for «lee esto» on both routes through the per-request
   `_text_reader` seam (`vision/read_text.py`), behind `_reading_on()` (memory, documents, vision
   and face authentication).
4. **The scene capability exists, classic-only.** `vision/describe.py` `describe_image(client,
   image)` sends one fixed prompt to `settings.vlm_model` and returns `(description, ms)`;
   `vision/perception.py` `perceive_scene` wraps it and lets `VisionError` through;
   `cognition/response_plan.py` `current_perception_plan(description)` speaks it with
   `ResponseSource.CURRENT_PERCEPTION`, never through the text model. Only `routers/vision.py`
   `vision_respond` (the classic second round, after `vision_requested=True` and the cue
   `settings.vision_look_phrase`) calls them; its VLM failure is `_vlm_failure_plan()` («Perdón,
   ahora mismo no pude ver la escena.»), private to that router. The classic first round is not
   recorded, and `vision_respond` records nothing.
5. **The scene prompt is in voseo.** `_DESCRIBE_PROMPT` says «decilo», and its output goes straight
   to Piper. `tests/unit/test_no_voseo_in_spoken_strings.py` misses it: «decilo» is not in
   `_VOSEO_WORDS`, and `vision/describe.py` is not allowlisted.
6. **Stale comments around the guard:** `app.py`'s module docstring, `app_streaming.py` (line
   190, «No LOOKING transition here»), `.env.example` (the `ROBOT_STREAMING` block, «NOT compatible
   with VISION_ENABLED=true yet», and the `VISION_ENABLED` block, «NOT compatible with
   ROBOT_STREAMING=true yet»), `routers/system.py` `health()` docstring (the flag «the robot
   reads»), `docs/runbooks/operator-manual.md` («The one real startup guard», §4, and its
   cross-reference in the owner-unlock section), the PC-5 row of the roadmap. Also stale, found on
   the way: `robot/settings.py`'s comment and `_prompt_owner_unlock`'s docstring say the PIN prompt
   is «classic mode only», but `_run()` prompts in both modes and `app_streaming` sends the token
   (Plan 0027; the operator manual already says so).
7. **Timeouts.** The server's VLM call waits `settings.ollama_timeout_s` (120 s). The robot's HTTP
   client waits `settings.server_timeout_s` for each read, the first one included: **120 s by
   default** in `robot/settings.py`, but **300** in `.env.example`; the real value is read in
   Task 0. The streaming route sends no byte before its plan is decided.
8. **Why a failure leaves us blind** (`server/src/server/llm_transport.py`):
   - `ollama_chat` calls `resp.raise_for_status()`. The `HTTPStatusError` carries the status code
     but not Ollama's body, which is where Ollama says the cause (for example, that the model needs
     more memory than is available).
   - `ollama_chat_stream` raises «Ollama reported an error mid-stream» and drops the text of the
     line's `error` field.
   - The metrics Ollama returns with every answer (`total_duration`, `load_duration`,
     `prompt_eval_count`, `prompt_eval_duration`, `eval_count`, `eval_duration`) are discarded.
   - `describe_image` logs `vision.described` on success and **nothing** on failure; the callers log
     `str(exc)` at best. Since `27e215d`, `read_text` logs `vision.read_failed` with the exception's
     class name only, or `nothing_read`.
   - Nothing reads Ollama's own log (on Windows, `%LOCALAPPDATA%\Ollama\server.log`), where an
     out-of-memory load and a model eviction show.
9. **The vision model is called with Ollama's defaults.** `describe_image` sends
   `options={"temperature": 0.3}` and `read_text` `{"temperature": 0.0}`: no `num_ctx`,
   `num_predict`, `keep_alive` or `num_gpu`, and no warm-up call. The image goes as the robot sent
   it, up to 1280x720 (`robot/camera_capture.py`); the image tokens of `qwen3-vl` grow with its
   pixels. `describe.py` already imports PIL, and Pillow is a server dependency.
10. **The budget, measured twice and never managed.** Plan 0050 measured a cold scene turn at
    **116.6 s**. Plan 0088's sitting (2026-11-24, classic route) measured a cold reading at
    **102 s**. Later, three readings failed with `VisionError` after **137 to 152 s**, a generic turn
    took **73 s** (usually 8 to 20 s), and Pipec had to restart the PC: the 15.7 GB ran out. How
    long Ollama keeps a model and how many it keeps at once is whatever the installed Ollama does.
11. **The streaming doubt is settled.** Plans 0056 to 0059 measured a 29 % fallback on the stream
    (the emotion tag inside the JSON) and Plan 0059 fixed it (0 of 60). `ROBOT_STREAMING=false` in
    `.env.example` is only the default that goes with the F-08 guard. What is left is item 8: an
    error in the middle of a stream loses its text.
12. **The camera phrases.** The reading is a closed grammar anchored on the whole utterance
    (`cognition/document_cues.py` `_READING`: «lee esto», «léeme esto», «lee lo que dice», «¿qué
    dice aquí / acá?», with «Iroko», «oye», «a ver», «por favor» around them). The STT once wrote
    «Iroko, le esto», which matches nothing. The scene is `_SCENE_DESCRIPTION_PATTERNS` in
    `cognition/intent_resolution.py`, word-padded substrings («qué ves», «mira esto», «mira lo
    que», «qué tengo en la mano», …), so «mira lo que tengo» is already a scene. The reading rule
    runs before the scene rule (`_rules_for`), so a reading shape wins.

## Decisions

Each is Claude's recommendation; Pipec confirms or changes it (*Pipec's decisions*).

- **D-1 Where it belongs.** PC-5 owns the question «must scene description work in streaming?»;
  this plan answers it early, standalone, before block D, because Pipec wants streaming with vision
  as the normal mode and Plan 0088's reading already needs it. Block D's plan then measures it with
  the rest of PC-5 (the integrated visual scenario and the RAM budget on the home server); the PC-5
  row is amended at close to «decided by Plan 0089».
- **D-2 No cue phrase on streaming.** The streaming route decides the plan, then streams it; a
  scene turn calls the VLM before the first event, exactly as the reading of Plan 0088 does. No
  «A ver, déjame mirar...» first: it would need a second shape of `_stream_plan` (cue audio, then
  the description) for a latency not yet measured with the tuned settings. *Trigger to add it:* the
  warm scene turns of Task 11 take more than 10 s from end of speech to first audio.
- **D-3 The same switches, no new switch.** A streaming scene turn reads the frame only with
  `VISION_ENABLED` and `FACE_AUTHENTICATION_ENABLED` on the server (the second is what carries the
  frame) and `ROBOT_FACE_AUTH_ENABLED` on the robot. No memory, documents or identity are needed:
  a scene description reads no household store, exactly as on the classic route.
- **D-4 The phrases.** Scene with vision off, face authentication off or no valid frame: the
  existing «Ahora mismo no puedo mirar desde este canal.» (honest, pinned today, no new string). A
  VLM failure or timeout: the classic route's «Perdón, ahora mismo no pude ver la escena.», moved
  to `response_plan.scene_failed_plan()` so both routes share one definition (DRY). The
  description itself: the VLM's words, as on the classic route.
- **D-5 What the record keeps.** The streaming route records every decided plan, so a description
  would enter the conversation record, the diary input and an export. It is current perception, not
  something the owner told («not stored in memory either», `describe.py`). The record keeps the
  marker «[escena descrita por la cámara]» in place of a described scene (beside Plan 0088's
  markers in `recorded_exchange`); the two fixed phrases are recorded as they are. The heard
  question is kept. The frame is never stored or logged.
- **D-6 The robot: the guard goes.** `_guard_streaming_vision_compat`, `check_vision_enabled` and
  their five tests are removed: with D-3 nothing is left to guard, and a warning about a working
  combination is noise. `/health` keeps its `vision_enabled` field (removing a field is a breaking
  change of the contract; it stays as static config). *Alternative:* keep `check_vision_enabled`
  and log one warning when streaming, server vision on and `ROBOT_FACE_AUTH_ENABLED` off (visual
  questions will hear the fixed phrase).
- **D-7 The scene prompt in tuteo.** «decilo» becomes «dilo», and «decilo» joins the voseo guard's
  closed list, so the guard sees it first (the VLM's words are spoken as they come). No other word
  of the prompt changes; the prompt's own tests pin the rest.
- **D-8 The vision model measured, with numbers, under load.** A bench, `scripts/vlm_bench.py`,
  calls `describe_image` and `read_text` directly (no route, no robot) over a small local set of
  canary images: a printed card and a phone screen showing «Lista qqcanarioqq: pan, té, fósforos»,
  and a cup on the desk.
  - **Where things live:** the images stay outside the repository, in `.superpowers/sdd/0089/`; the
    tracked record holds numbers only.
  - **Load:** it runs with the four models resident, as on a normal day: the server up (Whisper
    `medium` on the GPU, Piper, the face and speaker models) and `qwen2.5:3b` and
    `granite-embedding:278m` loaded in Ollama. Between cells it calls the 3B model once with a fixed
    canary question and times it, to see whether the VLM evicted it.
  - **A small matrix**, one variable at a time from today's settings, never the full product:
    - image long side: 1280 (today), 768, 512;
    - `num_ctx`: Ollama's own, 4096, 2048;
    - `num_predict`: no cap (today), about 120 tokens for the scene and 400 for the reading;
    - cold (the VLM stopped with `ollama stop`) against warm (a load-only `/api/generate` call
      first);
    - `keep_alive`: as installed, against an explicit value passed per request.
  - **Ollama's own switches**, tried once each and undone: `OLLAMA_FLASH_ATTENTION=1`,
    `OLLAMA_KV_CACHE_TYPE=q8_0`, `OLLAMA_MAX_LOADED_MODELS`, and whether `num_gpu` (layers on the
    MX450) helps or fights Whisper for the 2 GB.
  - **Each cell records:**
    - latency, and the Ollama metrics of D-11;
    - available RAM (`Get-Counter '\Memory\Available MBytes'`), VRAM (`nvidia-smi`) and `ollama ps`;
    - failures, with D-11's cause;
    - the 3B model's next latency;
    - quality: whether the reading returns the canary list character by character (a closed
      comparison, no judge model), and whether the scene names the cup.
  - **Safety stop:** available RAM under 1 GB, or one call over 120 s, ends the cell at once; no
    third attempt, so the PC is not restarted again. What was measured is recorded.
- **D-9 The classic route does not change** beyond what D-11 and D-12 change inside the vision
  calls. It keeps its two rounds (cue, `vision_requested`, `/vision/respond`), even when the turn
  already carries a frame. *Recorded, not built:* the classic route could answer from the turn's
  frame in one round; trigger: Pipec asks for classic parity, or the classic route becomes the daily
  one again.
- **D-10 Clearer camera phrases, still a closed grammar.** Two verbs, one per capability, so a
  phrase never means both: **«lee»** reads the text, **«mira» / «foto»** describes the scene.
  - Reading (`_READING`, anchored): adds the observed STT variant «le esto», and «lee lo que tengo»,
    «lee este papel», «lee esta pantalla», with today's fillers around them.
  - Scene (`_SCENE_DESCRIPTION_PATTERNS`, word-padded): adds «saca una foto» and «toma una foto»;
    «mira lo que tengo» already describes.
  - Each new shape gets a trap test of a sentence that must not match: «dile esto a mi hermano» and
    «le esto» inside a longer sentence (reading, anchored); «saca una fotocopia», «no le saques una
    foto», «toma una foto de la boleta y guárdala como documento» (the last one a scene, never a
    document: recorded in the test as the accepted reading).
  No fuzzy matching: a phrase the STT bends further is recorded in Task 11 and added by name.
  *Recorded, not built:* the tolerant spoken-command research (a corpus of real turns, bounded
  tolerance, confirming a near match).
- **D-11 Diagnose first: detailed logs, never a private text.**
  - **An Ollama error is logged with its cause:** the HTTP status and the `error` field of Ollama's
    body, cut to 300 characters (Ollama puts its own diagnosis there, never the user's text). It is
    logged once in `llm_transport`, with the phase that failed (`connect`, `first_byte` or `read`),
    the model, the elapsed time and, for a vision call, the image's pixel size. The exception raised
    stays the same type, so no caller changes behavior.
  - **A mid-stream error keeps its text**, the same way.
  - **A good answer is measured:** every vision answer logs `vision.metrics` with Ollama's
    `load_duration`, `prompt_eval_count` and `_duration`, `eval_count` and `_duration`, and
    `total_duration`, in milliseconds and counts. These numbers separate «it loaded the model» from
    «it thought».
  - **The scene's failure is logged:** `vision.describe_failed`, the twin of `vision.read_failed`.
    Both carry the cause: the exception's class, Ollama's error (above) or `nothing_described` /
    `nothing_read`.
  - **Ollama's own log beside ours:** `just ollama-log` (a short script) copies the last lines of
    `%LOCALAPPDATA%\Ollama\server.log` next to the sitting's record, for the agent to read; it is
    never tracked.
  - **The privacy lock:** a description, a read text, the prompt, a message or the image never reach
    a log line; a test sends a canary through every new log path and searches the captured records.
- **D-12 The chosen settings become configuration.**
  - **New settings, one per lever:** `VLM_IMAGE_MAX_SIDE`, `VLM_NUM_CTX`, `VLM_NUM_PREDICT_SCENE`,
    `VLM_NUM_PREDICT_READING` and `VLM_KEEP_ALIVE`. Each is documented in `.env.example`; no model
    name or number is written into the code.
  - **Neutral until chosen:** their defaults reproduce today's behavior (no resize, Ollama's own
    values, nothing sent), so Task 2 changes nothing on its own.
  - **The resize** happens in memory with PIL before the image reaches the VLM, keeping its aspect
    ratio and never upscaling. The API contract stays 1280x720, the face and speaker models still
    see the full frame, and the robot does not change.
  - **Pipec chooses** each value with the bench's table in hand (Task 4); the chosen values become
    the defaults and `.env.example`'s examples.
  - **A VLM warm-up at start** enters only if the bench shows a cold call past the robot's timeout
    or a warm one under half of a cold one; it is then a call to the existing warm-up of
    `server/main.py` (the one Plan 0055 added for the face and speaker models), not a new
    mechanism.
  - **Ollama's own switches** (flash attention, KV cache type, loaded-model limit) are recorded in
    the operator manual as a measured recommendation; the code never sets them.

## Deferred, with their triggers

- The cue phrase on streaming (D-2): warm scene turns over 10 s to first audio.
- One-round classic scene from the turn's frame (D-9): Pipec asks, or classic becomes daily.
- Tolerant spoken commands (D-10): a camera phrase the STT bends in more than one way in real use.
- Another vision model or a quantization of it: the tuned `qwen3-vl:2b-instruct` still fails the
  safety stop of D-8 with every setting of the matrix.
- Tuning Whisper, Piper or the 3B text model: the bench shows one of them, not the VLM, is what
  breaks the budget.
- Handwriting (R4, by measurement, after the line): Plan 0088's card was misread («COMPARAR LECHRE
  TRAN»); printed text and screens are this plan's reading test.
- A scene that names who is in view (the face recognition of `perception.perceive`): never by this
  route; identity is the policy's, and the prompt forbids it.

## Global constraints

- English code and docstrings; no `Any` without its comment, no `print`, no `os.path`, no bare
  `except`; logging with `%`, counts, causes and durations only (D-11's privacy lock).
- The API contract is unchanged: no field added, removed or renamed on `/transcribe`,
  `/transcribe/stream`, `/vision/respond` or `/health`; the stream keeps `text_heard`, `emotion`,
  `audio`, `done`. The OpenAPI document is byte-identical (the existing contract test).
- The robot learns nothing about STT, LLM, TTS or the VLM; it only stops asking `/health` at start.
- Every non-scene turn and the reading's own flow are byte-identical to `main`, except that the
  reading hears D-10's new shapes and the vision calls carry D-12's chosen settings.
- Ollama stays the only runtime (ADR 0004); no cloud provider, no new model pulled in the runtime
  path.
- Spoken strings in neutral tuteo (Santiago de Chile, no voseo). No real household data: invented
  canaries only (a «taza amarilla qqtazaqq» description in tests, the «qqcanarioqq» card and screen
  on hardware); `scripts/check_reserved_terms.py` passes.

## Review focus

1. **A private text in a log:** no description, read text, prompt or image in any new log line,
   Ollama's error included (Task 1).
2. **A setting that changes today by accident:** with D-12's defaults, every vision payload is
   byte-identical to `main`'s (Task 2).
3. **A frame where it should not be:** with vision off, face authentication off, or a frame the
   route rejected, the VLM is never awaited (Task 8).
4. **The description in the record:** the conversation record, the diary input and an export hold
   the marker, never the description (Task 5, Task 8).
5. **The reading and the scene apart:** «¿qué dice aquí?» and «lee lo que tengo» still read, «¿qué
   ves?» and «saca una foto» describe, in the same session; no new phrase steals a recall, a
   document or a secret turn (Task 7, Task 8, Task 11).
6. **The robot starts** in streaming with server vision on, and makes no `/health` call at start
   (Task 9).

---

## Permitted files

Paths under `server/src/server/` unless they start with `robot/`, `scripts/`, `tests/`, `docs/` or
the root; a need outside the list stops the plan for Pipec.

| Task | Files |
|---|---|
| 1 | `llm_transport.py`, `vision/describe.py`, `vision/read_text.py`, `scripts/ollama_log_tail.py` (new), `justfile` (the `ollama-log` task); `tests/unit/test_llm_transport.py`, `tests/unit/test_vision_describe.py`, `tests/unit/test_read_text.py` (or the existing reading test file), `tests/unit/test_vision_log_privacy.py` (new) |
| 2 | `settings.py`, `vision/frame_resize.py` (new), `vision/describe.py`, `vision/read_text.py`, `.env.example`; `tests/unit/test_frame_resize.py` (new), `tests/unit/test_settings.py`, the two vision test files of Task 1 |
| 3 | `scripts/vlm_bench.py` (new); `tests/unit/test_vlm_bench.py` (new) |
| 4 | `settings.py` and `.env.example` (the chosen values), `docs/evals/0089-vlm-bench.md` (new) |
| 5 | `cognition/response_plan.py`, `routers/vision.py`; `tests/unit/test_cognitive_models.py`, `tests/integration/test_vision_dialog.py` |
| 6 | `vision/describe.py`; `tests/unit/test_no_voseo_in_spoken_strings.py`, `tests/unit/test_vision_describe.py` |
| 7 | `cognition/document_cues.py`, `cognition/intent_resolution.py`; `tests/unit/test_document_cues.py`, `tests/unit/test_intent_resolution.py` |
| 8 | `routers/transcribe.py`; `tests/integration/test_transcribe_stream.py`, `tests/integration/test_stream_scene.py` (new) |
| 9 | `robot/src/robot/app.py`, `robot/src/robot/server_client.py`, `robot/src/robot/app_streaming.py` (docstring), `robot/src/robot/settings.py` (comments), `routers/system.py` (docstring), `.env.example` (comments); `tests/unit/test_robot_app.py`, `tests/unit/test_server_client.py` |
| 11 | `docs/runbooks/operator-manual.md` (the guard paragraph, the camera phrases, the vision settings and Ollama's recommended switches), `docs/architecture/current-state.md`, the Archify voice-turn diagram (`docs/architecture/diagrams/current-state-voice-turn.json` and `.html`, validate then deliver), `docs/evals/0089-streaming-scene-acceptance.md` (new), the roadmap (the PC-5 row, *Vision on the streaming route* and the budget row), the plan board, `docs/plans/open/README.md`, `docs/plans/completed/README.md`, Pipec's local `docs/roadmap/tabla-tareas.md` |

The exact test file names are confirmed in Task 0 (`rg --files tests | rg "vision|llm_transport|read_text|settings"`); a file named here that does not exist is the closest existing one, not a new one, unless marked new.

**Rollback boundary.** Before the merge, the branch. After it, a revert: no migration, no stored
data; a revert brings the guard back, the fixed phrase on streaming, today's phrases and Ollama's
defaults for the vision model.

---

## Task 0: Re-audit and baseline

- [ ] **Step 1:** `git switch main && git pull`, create `feat/0089-vision-and-streaming`.
- [ ] **Step 2:** verify items 1 to 12 of *What the code does today* on `main`; read the real
  `SERVER_TIMEOUT_S` of Pipec's `.env` (its value only); confirm the test file names of the
  permitted list. **Stop and report** if an item is false.
- [ ] **Step 3:** baseline: `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and
  not eval" -q -n auto`; note the count.

## Task 1: Diagnostic logs (D-11)

**Interfaces:** in `llm_transport.py`, one private helper that turns an `httpx.HTTPStatusError`
into a log line with the status, Ollama's `error` (at most 300 characters), the phase, the model
and the elapsed milliseconds, then re-raises the same exception; the same for a mid-stream `error`
line (the `LLMError` message keeps «mid-stream», the log line adds Ollama's text). A small frozen
dataclass `OllamaMetrics` read from a response body (milliseconds and counts, missing fields as
`None`). In `vision/`, `vision.metrics` after a good call and `vision.describe_failed` with its
cause.

- [ ] **Step 1: Write the failing tests:**
  - an Ollama 500 whose body says `{"error": "model requires more system memory (5.1 GiB) than is
    available (3.2 GiB)"}` logs one record with status 500, that text, phase `read` and the model,
    and still raises `httpx.HTTPStatusError`;
  - a connection refused logs phase `connect`, a read timeout phase `first_byte` or `read`;
  - a mid-stream `{"error": "…"}` line logs its text and still raises `LLMError`;
  - a good vision answer with Ollama's duration fields logs `vision.metrics` with those numbers in
    milliseconds;
  - `describe_image` on a timeout and on an empty answer logs `vision.describe_failed` with cause
    `ReadTimeout` and `nothing_described`;
  - **privacy:** a canary «qqprivadoqq» in the prompt, the description, the read text and the image
    bytes' base64 appears in no captured record of any of the cases above.
- [ ] **Step 2:** FAIL (no record, or the text missing). **Step 3:** implement. **Step 4:** PASS;
  every existing transport, streaming and vision test unchanged.
- [ ] **Step 5:** `scripts/ollama_log_tail.py` and `just ollama-log [N]`: print the last N lines of
  Ollama's log (path from `%LOCALAPPDATA%`, a clear message when it is missing); a smoke test with a
  temporary file. Lint it with explicit paths.
- [ ] **Step 6:** commit `feat: log why an Ollama call failed and what it cost (plan 0089)`.

## Task 2: The vision model's settings, neutral by default (D-12)

**Interfaces:** `settings.vlm_image_max_side: PositiveInt | None = None`, `vlm_num_ctx`,
`vlm_num_predict_scene`, `vlm_num_predict_reading` (each `PositiveInt | None = None`),
`vlm_keep_alive: str | None = None`; `vision/frame_resize.py` `fit_long_side(image: bytes,
max_side: int | None) -> tuple[bytes, int, int]` (the image, possibly re-encoded as JPEG, and its
width and height; `None` returns the bytes untouched). `describe_image` and `read_text` build their
`options` from the settings, adding a key only when its setting is set, and `keep_alive` at the top
of the payload only when set (the transport gains an optional `keep_alive` argument).

- [ ] **Step 1: Write the failing tests:** with every new setting unset, the payload sent to the
  fake Ollama is byte-identical to today's (the golden payload of each call); each setting, set
  alone, adds exactly its key; `fit_long_side` keeps the ratio, never upscales, returns the original
  bytes for `None` and for an image already small enough; an invalid image still raises the
  existing `ImageContractError` path.
- [ ] **Step 2:** FAIL. **Step 3:** implement; `.env.example` documents the five settings,
  commented out, with what each one trades. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: the vision model's settings, neutral until chosen (plan 0089)`.

## Task 3: The vision bench (D-8)

**Interfaces:** `uv run python scripts/vlm_bench.py --images .superpowers/sdd/0089/images
--cell <name> --out .superpowers/sdd/0089/bench.jsonl`. A cell is one combination of D-8's matrix,
named in a small table inside the script; each run appends one JSON line per call: the cell, the
capability (`scene` or `reading`), cold or warm, latency, the `OllamaMetrics`, available RAM before
and after, the VRAM used (`nvidia-smi --query-gpu=memory.used`, `None` when absent), the 3B model's
probe latency, the failure cause, and the quality result (`canary_ok` for a reading, `cup_named` for
a scene). Never the text itself. `--summary` prints a Markdown table of the file, one row per cell.
The safety stop of D-8 is in the script: it checks the RAM before each call and stops.

- [ ] **Step 1: Write the failing tests** with a fake Ollama and fake meters: one cell writes the
  expected fields and no text; the RAM stop ends the run before the next call; `--summary` renders
  the table; the canary comparison is closed (exact list, folded accents).
- [ ] **Step 2:** FAIL. **Step 3:** implement, reusing `describe_image`, `read_text`,
  `fit_long_side` and `OllamaMetrics`, never a second Ollama client. **Step 4:** PASS; lint the
  script with explicit paths.
- [ ] **Step 5:** commit `feat: a bench for the vision model under load (plan 0089)`.

## Task 4: The bench on hardware, and Pipec's choice

**Setup.** Good light on the desk. The agent prepares the canary card (printed), the phone screen
and the cup; Pipec photographs them once with the robot's camera (the capture path Task 0 names,
`robot/src/robot/camera_capture.py`, so the bench sees the frames the robot sends) into
`.superpowers/sdd/0089/images/`. Pipec starts the server with every model of a normal day; the
agent loads `qwen2.5:3b` and `granite-embedding:278m` with one call each, and records Ollama's
version and its `OLLAMA_*` variables.

- [ ] **Step 1:** run the cells in this order, each cold then warm, stopping at the safety stop:
  1. today (every setting unset);
  2. image side 768, then 512;
  3. `num_ctx` 4096, then 2048, on the best side;
  4. the two `num_predict` caps;
  5. `keep_alive` explicit;
  6. Ollama's switches, one at a time, each undone;
  7. the best combination, three times.

  After each cell, `just ollama-log 50` is read for an out-of-memory or an eviction line.
- [ ] **Step 2:** the record `docs/evals/0089-vlm-bench.md`: the `--summary` table, Ollama's
  version and variables, every failure with its cause, and what each lever bought. Numbers and
  outcomes only.
- [ ] **Step 3:** Pipec chooses the values (and whether the warm-up at start enters, D-12). They
  become the defaults and `.env.example`'s example values, with a test that pins them; Ollama's
  recommended switches go to the operator manual in Task 11.
- [ ] **Step 4:** commit `feat: the vision model's settings, chosen on the bench (plan 0089)`.

## Task 5: One failure plan for a scene, and the scene's marker in the record

**Interfaces:** `response_plan.scene_failed_plan() -> ResponsePlan` (need `SCENE_DESCRIPTION`,
status `UNKNOWN`, source `CURRENT_PERCEPTION`, «Perdón, ahora mismo no pude ver la escena.»);
`SCENE_FAILED_PHRASE` and `SCENE_RECORDED_TEXT: Final = "[escena descrita por la cámara]"`;
`recorded_exchange` returns `(heard, SCENE_RECORDED_TEXT)` for a `SCENE_DESCRIPTION` plan from
`CURRENT_PERCEPTION` whose response is not `SCENE_FAILED_PHRASE`.

- [ ] **Step 1: Write the failing tests:** `scene_failed_plan()` has exactly that need, source and
  text; `recorded_exchange(current_perception_plan("Una taza amarilla qqtazaqq."), "¿Qué ves?")`
  is `("¿Qué ves?", SCENE_RECORDED_TEXT)`; `scene_failed_plan()` and `scene_unavailable_plan()` are
  recorded verbatim; the classic `/vision/respond` failure still speaks the same text (existing
  `test_vision_dialog.py` cases, importing the shared plan).
- [ ] **Step 2:** FAIL (no `scene_failed_plan`, the description recorded as is). **Step 3:**
  implement; `routers/vision.py` drops `_vlm_failure_plan` for the shared one. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: one scene failure plan and its record marker (plan 0089)`.

## Task 6: The scene prompt in tuteo

- [ ] **Step 1: Write the failing test:** «decilo» added to `_VOSEO_WORDS`, so
  `test_no_spoken_string_or_prompt_uses_voseo` fails on `vision/describe.py`.
- [ ] **Step 2:** FAIL for that reason only. **Step 3:** «decilo» → «dilo» in `_DESCRIBE_PROMPT`.
  **Step 4:** PASS, and the prompt's existing rules still pass.
- [ ] **Step 5:** commit `fix: the scene prompt speaks in tuteo (plan 0089)`.

## Task 7: Clearer camera phrases (D-10)

- [ ] **Step 1: Write the failing tests:** in `test_document_cues.py`, `is_reading_request` is true
  for «Iroko, le esto», «lee lo que tengo», «oye, lee este papel», «lee esta pantalla por favor»,
  and false for «dile esto a mi hermano», «le esto lo otro mañana» and «lee este papel mañana en la
  oficina»; in `test_intent_resolution.py`, «saca una foto» and «Iroko, toma una foto» resolve to
  `SCENE_DESCRIPTION`, «saca una fotocopia» and «no le saques una foto al perro» do not, «lee lo que
  tengo» resolves to `READ_TEXT` with the reading on and to no scene with it off, and «toma una foto
  de la boleta y guárdala como documento» resolves to `SCENE_DESCRIPTION` (the accepted reading of
  D-10).
- [ ] **Step 2:** FAIL (the new shapes unmatched). **Step 3:** add them to `_READING` and
  `_SCENE_DESCRIPTION_PATTERNS`; update `is_reading_request`'s docstring. **Step 4:** PASS, with
  every existing intent, recall, document and secret test unchanged.
- [ ] **Step 5:** commit `feat: clearer camera phrases for reading and the scene (plan 0089)`.

## Task 8: The streaming route describes the scene from the turn's frame

**Interfaces:** in `routers/transcribe.py`, `_scene_on() -> bool` (`vision_enabled and
face_authentication_enabled`) and `async def _stream_scene_plan(client, frame: bytes | None) ->
ResponsePlan`: `scene_unavailable_plan()` when `_scene_on()` is false or `frame` is `None`;
otherwise `current_perception_plan(await perceive_scene(client, frame))`, and
`scene_failed_plan()` on `VisionError` (Task 1 logged its cause). `transcribe_stream` calls it for a
`SceneDescriptionRequest`; the comment «Streaming has no second-round frame upload» is replaced. The
classic `transcribe` is not touched.

- [ ] **Step 1: Write the failing tests** in `tests/integration/test_stream_scene.py` (the face and
  VLM doubles of `test_reading_routes.py`; a blank JPEG canary frame):
  - switches on, frame sent, «¿Qué ves?»: `perceive_scene` awaited once with exactly the frame's
    bytes; events `text_heard`, `emotion`, `audio`, `done` with the canary description; the text
    model never called; the record holds «¿Qué ves?» and `SCENE_RECORDED_TEXT`;
  - the VLM raises `VisionError`: «Perdón, ahora mismo no pude ver la escena.», recorded verbatim;
  - no frame; vision off with a frame; face authentication off with a frame: the fixed phrase,
    `perceive_scene` never awaited (parametrized);
  - a non-scene turn with a frame and «¿qué dice aquí?» with the reading on: unchanged events, the
    reading still reads (the scene double never awaited);
  - the frame's bytes and the description reach neither the database file nor a captured log line.
  The existing `test_stream_scene_request_always_gets_the_fixed_unavailable_plan` stays as it is
  (no frame in it) and its docstring says why.
- [ ] **Step 2:** FAIL (the fixed phrase for the first two cases). **Step 3:** implement.
  **Step 4:** PASS, with `test_transcribe_stream.py`, `test_reading_routes.py` and the OpenAPI
  contract test unchanged.
- [ ] **Step 5:** commit `feat: describe the scene over streaming from the turn frame (plan 0089)`.

## Task 9: The robot starts in streaming with server vision on

- [ ] **Step 1: Write the failing test** in `tests/unit/test_robot_app.py`:
  `test_streaming_robot_starts_with_server_vision_on`: `robot_streaming` true, an HTTP double whose
  `/health` says `vision_enabled: true`, `tick` patched to stop the loop after its first call;
  `_run()` reaches `tick` and never calls `/health`.
- [ ] **Step 2:** FAIL (`SystemExit`). **Step 3:** remove `_guard_streaming_vision_compat`, its call
  and `check_vision_enabled`; delete their five tests; update the docstrings and comments of item 6
  (`app.py`, `app_streaming.py`, `settings.py` and `_prompt_owner_unlock`, `system.py`,
  `.env.example`). **Step 4:** PASS; `rg "check_vision_enabled|_guard_streaming_vision_compat|F-08"
  robot server .env.example` finds nothing.
- [ ] **Step 5:** commit `feat: the robot starts in streaming with server vision on (plan 0089)`.

## Task 10: Verification and review

- [ ] **Step 1:** the CI selection, `uv run pyright`, `uv run mypy server/src robot/src`,
  `uv run ruff check .`, `uv run ruff format --check .`, `ruff` with explicit paths over the new
  scripts, `uv run python scripts/check_reserved_terms.py`, `just gate` (not while Pipec
  rehearses).
- [ ] **Step 2:** the `simplify` skill, then `security-auditor` and
  `pr-review-toolkit:code-reviewer` on `git diff main...HEAD` (`sonnet`, `.claude/` first,
  read-only) with the *Review focus* above; each accepted finding fixed with its RED test; Step 1
  again. Push, PR, CI green.

## Task 11: Hardware acceptance, and close

**Setup.** Merge. The settings Pipec chose in Task 4. Server: `VISION_ENABLED`,
`FACE_AUTHENTICATION_ENABLED` and Plan 0088's switches (memory, documents) on; robot:
`ROBOT_STREAMING` and `ROBOT_FACE_AUTH_ENABLED` on. Good light, the canaries of Task 4. Pipec
starts the server and the robot; the agent reads `logs/server.log` (`vision.described`,
`vision.read`, `vision.metrics`, `vision.*_failed` with their cause) and `just ollama-log`, runs
`ollama ps` and reads available memory at each «Yo» step. **Safety stop:** available memory under
1 GB, or a turn over 120 s, ends the sitting at once and is recorded; nothing is retried a third
time.

**Part A — the scene over streaming.**

| # | Who | Step | Expected |
|---|---|---|---|
| A1 | Tú | Start the robot | It starts in streaming; no `/health` refusal in its log |
| A2 | Yo | `ollama ps`, available memory | Baseline recorded |
| A3 | Tú | «Hola Iroko, ¿cómo estás?» | An ordinary reply; its latency is the generic baseline |
| A4 | Tú | «¿Qué ves?» (first of the day) | Two or three sentences in Spanish about what is in front, no identity, no voseo; latency and memory within the bench's numbers |
| A5 | Tú | Hold the cup: «Iroko, saca una foto» | The cup is described |
| A6 | Tú | «Cuéntame algo breve.» | An ordinary reply; latency against A3 |

**Part B — the phrases and the reading.**

| # | Who | Step | Expected |
|---|---|---|---|
| B1 | Tú | The printed card: «Iroko, lee esto» | It reads the canary list and offers «sí, guárdalo» |
| B2 | Tú | The phone screen, same canary: «lee esta pantalla» | It reads the list |
| B3 | Tú | The printed card: «Iroko, lee lo que tengo» | It reads the list |
| B4 | Tú | «Iroko, le esto» said quickly (the STT variant) | If the STT writes «le esto», it reads; the heard text recorded |
| B5 | Tú | «Mira lo que tengo» with the cup | A scene description, not a reading |
| B6 | Yo | `iroko-admin conversations` (PIN) | The scene turns show «[escena descrita por la cámara]», never the description; the readings show Plan 0088's marker |

**Part C — the fallbacks and the classic route.**

| # | Who | Step | Expected |
|---|---|---|---|
| C1 | Tú | Restart the robot with `ROBOT_FACE_AUTH_ENABLED=false`: «¿Qué ves?» | «Ahora mismo no puedo mirar desde este canal.» |
| C2 | Tú | Restart the server with `VLM_MODEL` set to a model not pulled: «¿Qué ves?» | «Perdón, ahora mismo no pude ver la escena.»; `vision.describe_failed` with Ollama's own error text; then restore `VLM_MODEL` |
| C3 | Tú | Robot with `ROBOT_STREAMING=false`: «¿Qué ves?» | The classic cue, then the description |

A step that fails is fixed with its RED test and repeated; a phrase the STT bent is recorded with
its heard text.

- [ ] **Step 1:** the script above; the record `docs/evals/0089-streaming-scene-acceptance.md`
  (outcomes, heard phrases, latencies, memory, `ollama ps`, metrics and failure causes only; no
  description, no read text, no frame).
- [ ] **Step 2:** when Pipec accepts, the documents of the permitted list updated:
  - the guard paragraph replaced by the three switches of D-3;
  - the camera phrases of D-10;
  - the vision settings and Ollama's recommended switches, with the bench's numbers;
  - the PC-5 row «decided by Plan 0089»; *Vision on the streaming route* closed; the budget row
    gets the measured numbers.

  The Archify voice-turn diagram is validated and delivered; the plan moves to `completed/`; commit
  `docs: close plan 0089, the vision model and the scene`, push, PR, squash-merge, delete the
  branch.

---

## Completion criteria

1. A failed Ollama call says why in `logs/server.log` (status, Ollama's error, phase, model, time),
   and a good vision call says what it cost; no private text in any of it.
2. The bench record holds the matrix's numbers under load; Pipec chose the settings with it, and
   they are the defaults.
3. The script of Task 11 passes on hardware, with its record written.
4. A streaming «¿qué ves?» is described from the turn's own frame with the three switches on, and
   says the fixed phrase without them; the record keeps the marker; the classic route and every
   other turn are unchanged beyond the chosen settings.
5. The new camera phrases of D-10 work and their traps do not match; printed text and a phone
   screen are read in good light.
6. The robot starts in streaming with server vision on; no `check_vision_enabled` is left.
7. The CI selection, `just gate`, the type checkers, `ruff` and the reserved-terms guard pass.
8. The documents of Task 11 updated; the plan in `completed/`.

## Non-goals

Everything in *Deferred, with their triggers*; fine-tuning, another model or a cloud provider;
tuning Whisper, Piper or the 3B text model; setting Ollama's own switches from the code; any change
to `/vision/*` beyond the shared failure plan, to the reading's own flow of Plan 0088 (only its
phrases grow) or to a timeout; fuzzy or tolerant phrase matching; handwriting; a new field on any
route; face recognition in a scene answer; the robot's `LOOKING` state; the home-server budget
(PC-5).

## Self-review (2026-11-24)

- **Spec coverage.** The server change (Task 8, D-3, D-4), the robot change (Task 9, D-6), the RAM
  budget (D-8, Tasks 3 and 4), the PC-5 placement (D-1), TDD per task, permitted files, non-goals
  and a hardware acceptance are each present.
- **Plan 0088's three findings:**
  - the budget: item 10, D-8 and Task 4, with keep-alive and the warm-up measured;
  - the phrases: D-10, Task 7 and Part B;
  - the reading test: Part B, with printed text and a phone screen in good light.
- **Pipec's three requests of 2026-11-24:**
  - why it falls: item 8, D-11 and Task 1, with Ollama's own error and log;
  - the stress test: D-8 and Tasks 3 and 4, under the four models' load;
  - the tuning: D-12 and Tasks 2 and 4, allowed settings only.

  The streaming doubt is answered by item 11.
- **Found on the way and folded in, each with its reason:**
  - the voseo in the VLM prompt (D-7): a spoken defect the guard missed;
  - the duplicated failure phrase (D-4): DRY once two routes speak it;
  - the description entering the record (D-5): a defect the change would create;
  - the stale «classic mode only» PIN comments (item 6): wrong documentation;
  - the robot timeout's two values (item 7): a measurement that depends on it.
- **No placeholder:** every phrase, marker, switch, setting and test name is written out; exact
  test file names are confirmed in Task 0.

## Pipec's decisions (to answer before `Ready`)

1. **D-1:** a standalone plan now, before block D (recommended), or folded into block D's plan?
2. **D-2:** no cue phrase on streaming (recommended), or «A ver, déjame mirar...» streamed first?
3. **D-4:** the existing «Ahora mismo no puedo mirar desde este canal.» for «no frame»
   (recommended), or a new phrase that says the camera sent nothing?
4. **D-5:** the record keeps «[escena descrita por la cámara]» (recommended), or the description?
5. **D-6:** remove the guard and `check_vision_enabled` (recommended), or keep a startup warning?
6. **D-8 / D-12:** the matrix of D-8 (recommended), or a lever to add or drop (for example, try a
   second quantization of the same model)?
7. **D-10:** «lee» reads and «mira» / «saca una foto» / «toma una foto» describe (recommended), or
   should «saca una foto» read the text instead? Any other phrase you want by name?
8. **D-12:** Ollama's own switches (flash attention, KV cache in `q8_0`) recorded in the operator
   manual as a measured recommendation (recommended), or set by a start script?
