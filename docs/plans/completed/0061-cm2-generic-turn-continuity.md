# 0061 — Short-term continuity for the identified person (CM-2)

> **Status:** `Closed 2026-10-13` — written 2026-10-13 from [ADR 0020](../../adr/0020-authorized-actor-in-the-conversation.md),
> rehearsed in a scratch copy of `main` (`2385981`), independently reviewed (see *Review record*),
> promoted by Pipec the same day (decisions D-1 to D-12 confirmed as written), executed in a new
> session on one plain branch, and accepted on real hardware by Pipec
> ([record](../../evals/0061-generic-turn-continuity-acceptance.md)). ADR 0020 is `Accepted`.
> See *Execution record* at the end.

> **For agentic workers:** if the status above says `Queued`, stop: Pipec has not promoted this plan.
> REQUIRED SUB-SKILLS: `superpowers:executing-plans`,
> `superpowers:test-driven-development`, `superpowers:verification-before-completion`,
> `superpowers:finishing-a-development-branch`. Execute only while this is the explicitly
> authorized `NOW` item, in a new session. **Pipec's rules win over the skills:** one plain branch
> from `main` (`git checkout -b`), never a git worktree (treat any "create a worktree" instruction
> as "create the branch"), no subagents unless Pipec asks, and this plan lives under `docs/plans/`,
> not `docs/superpowers/plans/`. Implement exactly the tasks below, in order, one commit per task.
> If evidence contradicts the plan, stop and report the conflict instead of redesigning. Pipec runs
> every local process (server, robot, Ollama, scripts that use the camera or the microphone); you
> record what they print, outcomes only. The Bash tool of this environment loses backslashes and
> non-ASCII characters in heredocs: create and edit files with the Write and Edit tools.

**Goal:** The person the face (or a presented owner token) identifies on a *generic* turn gets
short-term continuity: the last turns of the conversation reach the next turn, in one in-process
session slot that lasts 3000 characters and 180 seconds of silence, is replaced by another
identified person, and is **suspended** (neither read nor written) by an unknown or ambiguous
speaker. No name enters the prompt, no grant widens, no durable memory opens, no wire field changes.

**Architecture:** A new pure module `server/memory/continuity.py` (the slot, with an injectable
clock) replaces `memory/working.py`. A new `cognition/generic_identity.py` names the speaker of a
generic turn by reusing the fusion resolver with no audio and `peek_actor` (the token is observed,
never spent); it runs in the routers after the controller decided the turn is generic and hands
`active_person` and a closed suspension cause to `text_turn`, which opens the slot before generation
and writes the exchange after it. The persistent context, vector retrieval, consolidation and the
presentation guidance keep their `MANUAL` gate. One sentence of the prompt changes and a new
history-bearing measurement gates it.

**Tech Stack:** Python 3.12, FastAPI, pydantic, pytest (+ xdist), httpx. No new dependency, no
migration, no new route.

**Spec:** [ADR 0020](../../adr/0020-authorized-actor-in-the-conversation.md) (this plan implements
it), [ADR 0016](../../adr/0016-face-and-voice-identity-fusion.md) §1–§5 and §9,
[ADR 0019](../../adr/0019-personal-memory-capabilities.md) (attribution stays with CM-3),
[ADR 0018](../../adr/0018-user-emotion-decided-apart.md) (the emotion event is untouched),
[ADR 0015](../../adr/0015-owner-grant-scope-and-speaker-binding.md) decision 1 and
[ADR 0009](../../adr/0009-locked-posture-and-scoped-capabilities.md); the CM-2 row of the
[roadmap](../../roadmap/cognitive-roadmap.md#canonical-pre-electronics-delivery-portfolio) and of the
[conversational-memory map](../../roadmap/conversational-memory-delivery-map.md).

**Rehearsal (2026-10-13).** Every diff below was produced test-first in a scratch copy of `main`
(`2385981`), one commit per task, with the real virtual environment, and then corrected once after an
independent review (see *Review record*). Under the CI marker filter
(`-m "not slow and not hardware and not eval" -n auto`) the suite went from **2498** to **2580**
(+82: Task 1 +24, Task 2 +14, Task 3 −3, Task 4 +7, Task 5 +4, Task 6 +24, Task 7 +4, Task 8 +8);
unfiltered, `pytest -n auto` went from 2515 to **2597** (2587 passed and 10 skipped).
`ruff check .`, `ruff format --check .` (415 files), `mypy server/src robot/src` (104 files),
pyright (0 errors) and `ruff --select S server/src robot/src` were clean at the end. The RED of every
task was observed for the stated reason (Task 3: 13 failures such as `TypeError: process_text_turn()
got an unexpected keyword argument 'suspend_cause'` and `[None, None] == [[], ['primero', 'Uno']]`).
Four things are green on arrival by design and prove themselves by a mutation step: the Task 7
guards (a synthetic offender trips each), the Task 7 owner → stranger scenario (forcing the person id
in `text_turn` fails 10 tests), the Task 2 observe-only checks (swapping `peek_actor` for
`resolve_actor`, or passing audio, fails 2) and the Task 4 visual-route test (identifying a visual
turn as the owner fails it alone). One unfiltered run reported a failure of
`tests/slow/test_speaker_embedding_real_model.py` under xdist load that did not reproduce (3 of 3
passed alone, in the copy and in the repository, and the later full runs were green): the same class
as the unidentified failure Plan 0050 recorded; it is reported, not hidden. Not rehearsed: Task 9
(real hardware) and Task 10 (documentation). Treat the diffs as rehearsed code, not as a substitute
for the RED/GREEN record each task requires.

## Global Constraints

- No real household data, voice, face or name in any tracked file, test, prompt, doc or commit
  message: tests use invented canaries (`scripts/check_reserved_terms.py` guards this).
- The PIN and the token are never logged or echoed. Logs carry closed reasons, a person id and
  durations only; conversation text stays out of logs unless `LOG_CONVERSATION_TEXT` is on.
- **No wire change.** A generic turn keeps reporting `identity_source = null` and
  `authentication_consumed = false` on every channel; no URL, status code, schema or field moves.
- A generic turn **never spends a grant and never computes a voice embedding**: the token is only
  observed (`peek_actor`) and the resolver is built with `wav_bytes=None`.
- Face and voice stay identity evidence, never authorization (ADR 0006, ADR 0009). A photograph of
  the owner still identifies at `basic` (ADR 0016 §9) and gets the owner's session: a documented
  limit, not a regression.
- Durable memory stays blocked (writes CM-3, episodes CM-4, retrieval CM-5): continuity opens the
  turn **history only**; the `MANUAL` gate of context, retrieval, consolidation and presentation
  guidance is unchanged.
- `ASSURANCE_RANK` is the only way to compare assurance (`IdentityAssurance` is a `str` enum and
  `basic < none` alphabetically).
- Limits (settings, `.env.example`): `WORKING_MEMORY_MAX_CHARS=3000`, `WORKING_MEMORY_IDLE_SECONDS=180`;
  `WORKING_MEMORY_SIZE=20` stays as an upper bound on messages.
- Type hints on every signature, Google docstrings on public APIs, `ruff` clean over the **explicit
  paths** of every file touched, `mypy server/src robot/src` clean, no `Any` without a comment, no
  `# type: ignore` without an explanation, no `print()`, no `time.sleep()` in async code.
- Every new test is observed RED for the stated reason before its implementation (Task 7's
  guards and scenario are the documented exception, proven by a mutation step).
- A commit title is at most 72 characters (commitizen rejects longer ones silently): check
  `git log -1` after every commit.

## Review Focus

Inputs the spec implies that are most likely to bite, each pinned by a test in its owning task:

1. **A suspended turn never reads, never writes and never drops the owner's session**: unknown,
   probable, ambiguous, no frame, a failed detector, a second face. A suspension does not move the
   generation, so a stranger's turn cannot kill the owner's write in flight (Tasks 1, 3, 4).
2. **Observing is not spending**: a presented default-scope token names its owner on a generic turn
   and stays spendable; an identified face leaves a presented token untouched; vetoes keep it
   (Tasks 2, 4).
3. **No voice and no audio on a generic turn**: the resolver is built with `wav_bytes=None`, the
   embedding is never awaited on the real route, and a guard keeps it so (Tasks 2, 4, 7).
4. **A protected answer never enters the session**: after "who are my children?" the next generic
   turn's history holds no trace of it, and the spent token makes the next `/chat` turn a suspension,
   not a loss (Task 4).
5. **Failures never fail the turn**: a face-store error, a token-store error, a failed detector and
   an unexpected exception all degrade to an unknown speaker with a closed cause; `MEMORY_ENABLED`
   off touches nothing (Tasks 2, 3).
6. **Continuity opens history only**: a face- or token-identified turn gets no persistent context, no
   onboarding, no consolidation and no tone directive; an identified context whose assurance is
   `none` has no continuity at all (Task 3).
7. **The conversation id is not identity**: two public ids share the person's session, one id shared
   by two people does not (Tasks 3, 4).
8. **An expired session cannot be written into**: a stale generation drops the write, and silence is
   measured from the last written turn, a suspended session ageing like any other (Task 1).

---

## Why this plan exists

| Finding | Evidence in the merged code | Closed by |
|---|---|---|
| A generic turn never identifies its speaker | `routers/chat.py`, `routers/transcribe.py` (classic and stream) and `routers/vision.py` call `process_text_turn` / `prepare_text_turn` with no `active_person`; resolution is lazy and runs only in protected branches | Tasks 2, 4 |
| Even a resolved actor would get no history | `text_turn.py` opens working history only for `IdentityEvidenceSource.MANUAL`, which no production code emits; `record_text_turn` clears it at once | Task 3 |
| The working memory has no limits of its own | `memory/working.py`: two module dictionaries keyed by an arbitrary string, no lock, no clock, no character cap | Tasks 1, 3 |
| A detector failure is indistinguishable from "nobody there", and a store error looks like no evidence | `FaceRequestResolver._detected_faces` returns `[]`; `FusedIdentityResolver` reports `no_evidence` for both | Task 2 |
| The prompt says the memory block is the *only* source of truth | `_MEMORY_DISCIPLINE` in `characters/__init__.py` | Task 5 |
| A history-bearing streamed turn has never been measured, and nothing checks the language | `golden_chat_faithfulness.yaml` has one case with a history; no language check exists in the evaluators; one French reply is an open finding of Plan 0059 | Task 6 |
| `just chat-test` cannot present a token, so its continuity probe can never pass | `scripts/chat_test.py` posts `{message, conversation_id}` only | Task 8 |
| `forget` is unreachable with a face (ADR 0016 §5) | ADR 0019 follow-up | **Not here**: decision 6 of ADR 0020 is implemented by the plan that wires the first operation with its own scope (CM-6) |

## Task overview

| # | Task | Closes |
|---:|---|---|
| 0 | Revalidate the baseline | — |
| 1 | The continuity slot | limits, transitions, generation, closed reasons |
| 2 | Identify the speaker of a generic turn | no voice, no grant, failures degrade, closed causes |
| 3 | Wire the slot into `text_turn` | history for the identified, nothing else opens |
| 4 | Identify in the three routes | the speaker reaches the turn on every channel |
| 5 | One sentence of the prompt | the conversation is a source of truth |
| 6 | Measure history-bearing streams and the reply language | the gate of ADR 0020 §7 |
| 7 | Guards and the no-token scenario | only `text_turn` reads the slot; a stranger gets nothing |
| 8 | `just chat-test` carries the owner token | the smoke can check continuity |
| 9 | Real runtime acceptance | the four cases of ADR 0020 §10 and the measurement |
| 10 | Documentation truth | ADR 0020 `Accepted`, the docs it lists |

## Decisions

Proposed 2026-10-13 and **confirmed by Pipec on 2026-10-13, when he promoted the plan**, exactly
as written below. D-3 and D-7 are choices he made in the session that wrote it. They are not
asked again.

1. **D-1 — A new module, not an edit of `working.py`.** The slot lives in `memory/continuity.py`
   and `working.py` is deleted in Task 3, so every task commits green. The ADR's
   `test_working_memory.py` ("new limits and API") becomes `test_continuity.py`.
2. **D-2 — Identification lives in the routers, after the controller decided the turn is generic.**
   `identify_generic_speaker` reuses `build_fused_identity_resolver(pin, frame=frame,
   wav_bytes=None).peek_actor`: face first, then an observed token, in ADR 0016 §5 order, with no
   speaker factory. Nothing in `cognition/controller.py` changes, and `/vision/respond` keeps
   passing nothing (an existing test already pins `call.kwargs == {}`).
3. **D-3 — `backend_unavailable` is emitted for real (Pipec, 2026-10-13).**
   `FaceRequestResolver.detection_failed` (additive) and `FusionReason.ERROR` (additive) let the
   fusion tell a failed detector (`backend_unavailable`) and a store error (`error`) from "no
   evidence". Consequences, accepted: on a **protected** turn the logged reason of those two cases
   changes from `no_evidence`, and `backend_unavailable` (ADR 0016 §8: a voice backend that is down)
   now also names a face detector that failed. ADR 0016 §8 is a closed set of an accepted
   decision, so ADR 0020 gains an *Amends* line and §5 says so (done in the same PR that queued
   this plan), and Task 10 updates ADR 0016 §8 and the operator manual's reason table. One
   existing test is updated on purpose.
4. **D-4 — Expiry is checked on every generic turn, whatever its speaker.** `open_turn` drops an
   expired slot first (and logs `expired`); a suspended turn does not extend the silence;
   deterministic and protected turns do not touch the slot. A turn admitted before expiry may still
   write after it if nobody opened the slot in between (a slow generation is activity); the next
   `open_turn` sees the fresh silence.
5. **D-5 — The recent-emotion buffer is removed**, as ADR 0020 §2 requires, and with it the
   `emotion` and `conversation_id` parameters of `record_text_turn` (unused). `PreparedTextTurn.user_emotion`
   and the prompt plumbing stay (always `None`): removing them belongs to the tone-policy follow-up.
6. **D-6 — The prompt change.** The first bullet of `_MEMORY_DISCIPLINE` names the memory block and
   what the person said earlier in this same conversation as the only sources of truth; the second
   bullet's "that memory" becomes "those sources" (three words that would otherwise contradict the
   first). Read ADR 0020 §7's "one sentence" as this single change.
7. **D-7 — The language check is a word-list heuristic of its own (Pipec chose a heuristic).**
   `STOPWORDS_ES` turned out to be a list of 4+ character conversation words made for entity
   filtering, useless for telling Spanish from French, so `scripts/reply_language.py` carries small
   function-word lists, returns *undetermined* for fewer than four words or a tie, and the report
   gives counts only, never text.
8. **D-8 — Twelve invented dialogues feed the measurement.** The golden suite has one case with a
   history, which cannot support a 5 % gate; the evaluator gets a `history` source of twelve
   one- or two-exchange dialogues whose question depends on the history (12 turns × 5 runs = 60
   observations per run).
9. **D-9 — The gate.** In two independent runs of `just eval-chat --provider ollama --mode stream
   --runs 5`, the `history` row's fallback rate is at most 5 % and the number of replies the
   heuristic judges not Spanish is recorded; a non-zero count is read by Pipec (the heuristic has
   limits) before the plan closes. A rate above 5 % does **not** close the plan: it reports back
   and a repair is its own plan, as with Plan 0058.
10. **D-10 — `chat-test`.** The PIN is read with `getpass` (never echoed, never logged); an empty or
    rejected PIN means "continuity not checked" (`SKIP`, exit 0), never a failure; the token is the
    default scope, so it is only observed. A closed stdin counts as an empty PIN. Interactive mode
    asks the same way; the token lasts `OWNER_UNLOCK_TTL_SECONDS` (300 s).
12. **D-12 — `/vision/respond` is pinned end to end, not by a mock.** The route keeps passing
    nothing, so its turns are the public unknown and suspend. Task 4 adds a real-route test (the
    owner writes an exchange, a visual question gets no history and writes nothing, the owner
    resumes); `test_vision_dialog.py`, which ADR 0020 lists among the tests that change on
    purpose, needs no edit because its `call.kwargs == {}` pin is the guarantee the ADR keeps.
11. **D-11 — Decision 6 of the ADR is not built.** Nothing here consults a token of a declared
    scope after a face match; the existing guard that the personal-memory scopes have no consumer
    keeps it so until CM-6.

## Required reading

- `AGENTS.md`, `docs/architecture/implementation-guardrails.md` and `.claude/rules/`.
- [ADR 0020](../../adr/0020-authorized-actor-in-the-conversation.md) (all of it),
  [ADR 0016](../../adr/0016-face-and-voice-identity-fusion.md), ADR 0019, ADR 0018, ADR 0015, ADR 0009
  and ADR 0006.
- `docs/architecture/identity-and-access.md` (*Fusion rules*, *Conversation isolation*) and the
  working-memory rows of `docs/architecture/current-state.md`.
- `server/src/server/{text_turn,streaming,settings}.py`, `server/src/server/memory/working.py`,
  `server/src/server/cognition/{identity_fusion,face_authentication,owner_authentication,identity}.py`,
  `server/src/server/routers/{chat,transcribe,vision}.py`,
  `server/src/server/characters/__init__.py`, `scripts/{eval_chat,eval_stream_protocol,chat_test}.py`
  and the tests named in each task.

## Permitted files

- Production: new `server/src/server/memory/continuity.py` and
  `server/src/server/cognition/generic_identity.py`; modified `settings.py`, `text_turn.py`,
  `streaming.py`, `cognition/face_authentication.py`, `cognition/identity_fusion.py`,
  `routers/chat.py`, `routers/transcribe.py`, `characters/__init__.py` and `.env.example`; deleted
  `memory/working.py`.
- Scripts: new `scripts/reply_language.py`; modified `scripts/eval_stream_protocol.py`,
  `scripts/eval_chat.py` and `scripts/chat_test.py`.
- Tests: the files listed in each task (new `test_continuity.py`, `test_generic_identity.py`,
  `test_generic_turn_continuity.py`, `test_memory_discipline.py`, `test_reply_language.py`; deleted
  `test_working_memory.py`).
- Docs (Tasks 9 and 10): the list of Task 10, a new
  `docs/evals/0061-generic-turn-continuity-acceptance.md` with `docs/evals/README.md`, and this plan.

No new URL, status code, response field, audio contract, database schema, migration or dependency.
The robot (`robot/src`), the controller, the V4 reader and the authorization policy are **not**
edited. `docs/roadmap/tabla-tareas.md` is excluded from git and is updated locally only.

---

## Task 0: Revalidate the baseline

**Files:** this plan's evidence note only. No production change.

- [ ] **Step 0: Status.** Confirm this plan says `Ready` (Pipec's promotion). If it says `Queued`, stop.
- [ ] **Step 1: Branch.** `git checkout main && git pull`, confirm a clean tree, then
  `git checkout -b feat/0061-cm2-generic-turn-continuity`. Record the base SHA (the rehearsal ran
  at `2385981`; if `main` moved, say so and re-check that the diffs below still apply). The diffs
  are applied by hand with the Write and Edit tools (new files whole, existing files hunk by hunk);
  blank context lines in the blocks lost their single leading space in this document (the
  trailing-whitespace hook), so `git apply` needs `--recount --ignore-whitespace` if you prefer it.
- [ ] **Step 2: Baseline.** Run `just gate`; record its outcome and test count (2515 at `2385981`).
  A pre-existing failure is reported, not hidden.
- [ ] **Step 2b: Re-audit the assumptions against the merged code** (queue rule 4). Each command
  must find what this plan names:
  `rg -n "from server.memory import working|working\.(get_|add_|clear)" server/src` (only
  `text_turn.py`; comments in `logging_setup.py` and `declarative.py` also say "working"),
  `rg -n "process_text_turn|prepare_text_turn" server/src/server/routers` (`chat.py`, `transcribe.py`
  twice, `vision.py`), `rg -n "history_scope|_manual_evidence" server/src` (only `text_turn.py` and
  `streaming.py`), `rg -n "_MEMORY_DISCIPLINE" server/src` (two hits in `characters/__init__.py`),
  `rg -n "def peek_actor" server/src/server/cognition` (fusion and the PIN resolver),
  `rg -n "wav_bytes" server/src/server/cognition/identity_fusion.py`, and
  `rg -n "interaction:" server/src` (the opaque conversation labels stay). A difference is reported
  before any code changes.
- [ ] **Step 3: Pin today's guards.** Run
  `uv run pytest tests/unit/test_architecture_guards.py tests/integration/test_owner_stranger_matrix.py tests/unit/test_identity_fusion.py tests/integration/test_vision_dialog.py -q -p no:cacheprovider`
  and record that it passes.

---

## Task 1: The continuity slot

**Files:**
- Create: `server/src/server/memory/continuity.py`
- Modify: `server/src/server/settings.py`, `.env.example`
- Test: new `tests/unit/test_continuity.py`

**Interfaces:**
- Produces: `ContinuitySession(clock=time.monotonic)` with `open_turn(person_id: int | None,
  cause: SuspendCause | None = None) -> ContinuityTurn`, `record_pair(turn, user: str,
  assistant: str) -> bool` and `clear()`; the process-wide `open_turn`, `record_pair` and `reset()`;
  `ContinuityTurn(history: tuple[ConversationTurn, ...], person_id: int | None, generation: int)`
  with `.writable`; the closed `Transition` (`continued`, `started`, `replaced`, `suspended`,
  `expired`) and `SuspendCause` (`no_evidence`, `veto_other_person`, `veto_multiple_faces`,
  `backend_unavailable`, `error`).

- [ ] **Step 1: Write the failing tests** — create the file from this diff (24 tests: who has a
  session, suspension, silence with a fake clock, size, a message limit below one exchange,
  logging, the process-wide slot):

```diff
diff --git a/tests/unit/test_continuity.py b/tests/unit/test_continuity.py
new file mode 100644
--- /dev/null
+++ b/tests/unit/test_continuity.py
@@ -0,0 +1,306 @@
+"""Unit tests for server.memory.continuity — the short-term continuity slot (ADR 0020).
+
+One session slot for the identified person: bounded by characters and by silence, replaced by
+another identified person, suspended (never read or written) by an unknown or ambiguous turn.
+"""
+
+from collections.abc import Generator
+import logging
+
+import pytest
+from server.memory import continuity
+from server.memory.continuity import ContinuitySession, SuspendCause, Transition
+from server.schemas import ConversationTurn
+from server.settings import settings
+
+pytestmark = pytest.mark.unit
+
+_OWNER = 7
+_VISITOR = 8
+_IDLE_S = 180.0
+
+
+class _Clock:
+    """A hand-driven monotonic clock."""
+
+    def __init__(self) -> None:
+        self.now = 1000.0
+
+    def __call__(self) -> float:
+        return self.now
+
+
+@pytest.fixture(autouse=True)
+def _clean_session() -> Generator[None, None, None]:
+    """Start and finish every test with an empty process-wide slot."""
+    continuity.reset()
+    yield
+    continuity.reset()
+
+
+@pytest.fixture
+def clock() -> _Clock:
+    return _Clock()
+
+
+@pytest.fixture
+def session(clock: _Clock) -> ContinuitySession:
+    return ContinuitySession(clock=clock)
+
+
+def _say(session: ContinuitySession, person_id: int, user: str, reply: str) -> bool:
+    """Open a turn for *person_id* and record one exchange; return whether it was written."""
+    return session.record_pair(session.open_turn(person_id), user, reply)
+
+
+def _contents(turn: continuity.ContinuityTurn) -> list[str]:
+    return [item.content for item in turn.history]
+
+
+# --- who has a session ----------------------------------------------------
+
+
+def test_the_first_identified_turn_starts_an_empty_session(session: ContinuitySession) -> None:
+    turn = session.open_turn(_OWNER)
+
+    assert turn.history == ()
+    assert turn.person_id == _OWNER
+    assert turn.writable
+
+
+def test_the_same_person_continues_with_the_previous_exchange(session: ContinuitySession) -> None:
+    assert _say(session, _OWNER, "hola", "hola humano")
+
+    turn = session.open_turn(_OWNER)
+
+    assert all(isinstance(item, ConversationTurn) for item in turn.history)
+    assert [(item.role, item.content) for item in turn.history] == [
+        ("user", "hola"),
+        ("assistant", "hola humano"),
+    ]
+
+
+def test_another_identified_person_replaces_the_session_and_reads_nothing(
+    session: ContinuitySession,
+) -> None:
+    _say(session, _OWNER, "mi clave es COBALTO", "anotado")
+
+    visitor = session.open_turn(_VISITOR)
+
+    assert visitor.history == ()
+    assert session.open_turn(_OWNER).history == ()  # the owner's session is gone, not hidden
+
+
+def test_a_turn_of_the_replaced_person_cannot_write_into_the_new_session(
+    session: ContinuitySession,
+) -> None:
+    in_flight = session.open_turn(_OWNER)
+    session.open_turn(_VISITOR)  # replaces: the generation moves on
+
+    assert not session.record_pair(in_flight, "pregunta", "respuesta")
+    assert _contents(session.open_turn(_VISITOR)) == []
+
+
+# --- suspension -----------------------------------------------------------
+
+
+@pytest.mark.parametrize("cause", list(SuspendCause))
+def test_a_suspended_turn_reads_nothing_and_cannot_write(
+    session: ContinuitySession, cause: SuspendCause
+) -> None:
+    _say(session, _OWNER, "dato privado", "ok")
+
+    suspended = session.open_turn(None, cause)
+
+    assert suspended.history == ()
+    assert suspended.person_id is None
+    assert not suspended.writable
+    assert not session.record_pair(suspended, "otra cosa", "respuesta")
+
+
+def test_the_owner_resumes_after_a_suspension(session: ContinuitySession) -> None:
+    _say(session, _OWNER, "primero", "uno")
+    session.open_turn(None, SuspendCause.NO_EVIDENCE)
+    session.open_turn(None, SuspendCause.VETO_MULTIPLE_FACES)
+
+    turn = session.open_turn(_OWNER)
+
+    assert _contents(turn) == ["primero", "uno"]
+
+
+def test_a_suspension_does_not_invalidate_a_write_in_flight(session: ContinuitySession) -> None:
+    """A stranger's turn never drops the owner's concurrent write (ADR 0020 §3)."""
+    in_flight = session.open_turn(_OWNER)
+    session.open_turn(None, SuspendCause.NO_EVIDENCE)
+
+    assert session.record_pair(in_flight, "pregunta", "respuesta")
+    assert _contents(session.open_turn(_OWNER)) == ["pregunta", "respuesta"]
+
+
+def test_two_overlapping_turns_of_the_same_person_both_write_in_order(
+    session: ContinuitySession,
+) -> None:
+    first = session.open_turn(_OWNER)
+    second = session.open_turn(_OWNER)
+
+    assert session.record_pair(first, "uno", "1")
+    assert session.record_pair(second, "dos", "2")
+    assert _contents(session.open_turn(_OWNER)) == ["uno", "1", "dos", "2"]
+
+
+# --- silence --------------------------------------------------------------
+
+
+def test_a_session_survives_just_under_the_idle_limit(
+    session: ContinuitySession, clock: _Clock
+) -> None:
+    _say(session, _OWNER, "hola", "hola")
+    clock.now += _IDLE_S - 0.1
+
+    assert _contents(session.open_turn(_OWNER)) == ["hola", "hola"]
+
+
+def test_a_session_expires_at_the_idle_limit(session: ContinuitySession, clock: _Clock) -> None:
+    _say(session, _OWNER, "hola", "hola")
+    clock.now += _IDLE_S
+
+    assert session.open_turn(_OWNER).history == ()
+
+
+def test_a_suspended_session_keeps_ageing(session: ContinuitySession, clock: _Clock) -> None:
+    _say(session, _OWNER, "hola", "hola")
+    clock.now += 100
+    session.open_turn(None, SuspendCause.NO_EVIDENCE)  # does not extend the silence
+    clock.now += 80
+
+    assert session.open_turn(_OWNER).history == ()
+
+
+def test_a_suspended_turn_drops_an_expired_session(
+    session: ContinuitySession, clock: _Clock
+) -> None:
+    in_flight = session.open_turn(_OWNER)
+    clock.now += _IDLE_S
+    session.open_turn(None, SuspendCause.NO_EVIDENCE)
+
+    assert not session.record_pair(in_flight, "tarde", "tarde")  # the generation moved on
+
+
+def test_writing_extends_the_silence(session: ContinuitySession, clock: _Clock) -> None:
+    _say(session, _OWNER, "uno", "1")
+    clock.now += 150
+    _say(session, _OWNER, "dos", "2")
+    clock.now += 150
+
+    assert _contents(session.open_turn(_OWNER)) == ["uno", "1", "dos", "2"]
+
+
+# --- size -----------------------------------------------------------------
+
+
+def test_whole_pairs_leave_oldest_first_when_the_character_cap_is_exceeded(
+    session: ContinuitySession, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    monkeypatch.setattr(settings, "working_memory_max_chars", 20)
+    _say(session, _OWNER, "aaaaa", "bbbbb")  # 10 chars
+    _say(session, _OWNER, "ccccc", "ddddd")  # 20 chars in total: still fits
+
+    assert _say(session, _OWNER, "eeeee", "fffff")  # 30: the oldest pair leaves whole
+
+    assert _contents(session.open_turn(_OWNER)) == ["ccccc", "ddddd", "eeeee", "fffff"]
+
+
+def test_a_single_pair_larger_than_the_cap_is_not_kept(
+    session: ContinuitySession, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    monkeypatch.setattr(settings, "working_memory_max_chars", 10)
+    _say(session, _OWNER, "ok", "ok")
+
+    assert not _say(session, _OWNER, "x" * 8, "y" * 8)
+
+    assert _contents(session.open_turn(_OWNER)) == ["ok", "ok"]
+
+
+def test_the_message_limit_is_an_upper_bound(
+    session: ContinuitySession, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    monkeypatch.setattr(settings, "working_memory_size", 4)
+    for index in range(4):
+        _say(session, _OWNER, f"u{index}", f"a{index}")
+
+    assert _contents(session.open_turn(_OWNER)) == ["u2", "a2", "u3", "a3"]
+
+
+# --- logging --------------------------------------------------------------
+
+
+def test_every_transition_is_logged_with_a_closed_reason_and_no_content(
+    session: ContinuitySession, clock: _Clock, caplog: pytest.LogCaptureFixture
+) -> None:
+    said = "mi clave es COBALTO"
+    with caplog.at_level(logging.INFO, logger=continuity.logger.name):
+        _say(session, _OWNER, said, "anotado")  # started
+        session.open_turn(_OWNER)  # continued
+        session.open_turn(None, SuspendCause.VETO_OTHER_PERSON)  # suspended
+        session.open_turn(_VISITOR)  # replaced
+        clock.now += _IDLE_S
+        session.open_turn(_VISITOR)  # expired, then started
+
+    reasons = [getattr(record, "reason", None) for record in caplog.records]
+    assert reasons == [
+        Transition.STARTED,
+        Transition.CONTINUED,
+        Transition.SUSPENDED,
+        Transition.REPLACED,
+        Transition.EXPIRED,
+        Transition.STARTED,
+    ]
+    assert said not in caplog.text
+    assert "anotado" not in caplog.text
+    suspended = next(
+        record
+        for record in caplog.records
+        if getattr(record, "reason", None) is Transition.SUSPENDED
+    )
+    assert getattr(suspended, "cause", None) is SuspendCause.VETO_OTHER_PERSON
+
+
+def test_the_suspension_causes_are_the_closed_set_of_the_adr() -> None:
+    assert {cause.value for cause in SuspendCause} == {
+        "no_evidence",
+        "veto_other_person",
+        "veto_multiple_faces",
+        "backend_unavailable",
+        "error",
+    }
+    assert {reason.value for reason in Transition} == {
+        "continued",
+        "started",
+        "replaced",
+        "suspended",
+        "expired",
+    }
+
+
+# --- the process-wide slot ------------------------------------------------
+
+
+def test_the_module_functions_use_one_process_wide_slot() -> None:
+    first = continuity.open_turn(_OWNER)
+    assert continuity.record_pair(first, "hola", "hola")
+
+    assert [item.content for item in continuity.open_turn(_OWNER).history] == ["hola", "hola"]
+
+    continuity.reset()
+    assert continuity.open_turn(_OWNER).history == ()
+
+
+def test_a_message_limit_that_cannot_hold_one_exchange_keeps_nothing(
+    session: ContinuitySession, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    """`WORKING_MEMORY_SIZE` counts messages: below 2 no exchange fits, and nothing is reported kept."""
+    monkeypatch.setattr(settings, "working_memory_size", 1)
+
+    assert not _say(session, _OWNER, "hola", "hola")
+
+    assert session.open_turn(_OWNER).history == ()
```

- [ ] **Step 2: Run it to see it fail.**
  `uv run pytest tests/unit/test_continuity.py -q -p no:cacheprovider`
  Expected RED: `ModuleNotFoundError: No module named 'server.memory.continuity'`.
- [ ] **Step 3: Implement** the slot, its two settings and the corrected comment of `.env.example`
  (the old one said public turns get request-local scopes, which stops being true):

```diff
diff --git a/.env.example b/.env.example
--- a/.env.example
+++ b/.env.example
@@ -128,10 +128,14 @@ CONSOLIDATION_MODEL=qwen3:4b-instruct-2507-q4_K_M

 # Memory tuning
 WORKING_MEMORY_SIZE=20
+# Short-term continuity of the identified person (ADR 0020): characters kept and seconds of
+# silence after which the conversation is forgotten.
+WORKING_MEMORY_MAX_CHARS=3000
+WORKING_MEMORY_IDLE_SECONDS=180
 SEMANTIC_TOP_K=6

-# Public voice and visual turns receive fresh request-local interaction scopes.
-# They do not inherit another person's working memory.
+# The short-term session belongs to the identified person (ADR 0020). A voice, chat or
+# visual turn whose speaker is unknown or ambiguous neither reads nor writes it.

 # Re-read character markdown profiles on change (prompt-engineering aid).
 # Keep false in production so behavior is reproducible from a commit; set
diff --git a/server/src/server/memory/continuity.py b/server/src/server/memory/continuity.py
new file mode 100644
--- /dev/null
+++ b/server/src/server/memory/continuity.py
@@ -0,0 +1,233 @@
+"""In-process short-term continuity for the identified person (ADR 0020).
+
+One session slot: the device has one microphone and a half-duplex loop, so at most one
+conversation is alive. The slot belongs to a person id, never to a ``conversation_id`` (a
+client-chosen string that is not identity), and it is never persisted.
+
+Rules: bounded by characters and by silence; another identified person replaces it; an
+unknown or ambiguous turn *suspends* it (that turn neither reads nor writes it); a write
+carries the generation it read and is dropped when another turn changed the session
+meanwhile. Only closed reasons and a person id are logged, never conversation text.
+
+asyncio runs on one thread and every method is synchronous, so no lock is needed.
+"""
+
+from __future__ import annotations
+
+from collections import deque
+from dataclasses import dataclass
+from enum import StrEnum
+import logging
+import time
+from typing import TYPE_CHECKING
+
+from server.schemas import ConversationTurn
+from server.settings import settings
+
+if TYPE_CHECKING:
+    from collections.abc import Callable
+
+logger = logging.getLogger(__name__)
+
+_USER_AND_ASSISTANT = 2
+
+
+class Transition(StrEnum):
+    """Closed reason of one session transition — the only thing logged about it."""
+
+    CONTINUED = "continued"
+    STARTED = "started"
+    REPLACED = "replaced"
+    SUSPENDED = "suspended"
+    EXPIRED = "expired"
+
+
+class SuspendCause(StrEnum):
+    """Closed cause of a suspension, so suspensions can be counted by origin."""
+
+    NO_EVIDENCE = "no_evidence"
+    VETO_OTHER_PERSON = "veto_other_person"
+    VETO_MULTIPLE_FACES = "veto_multiple_faces"
+    BACKEND_UNAVAILABLE = "backend_unavailable"
+    ERROR = "error"
+
+
+@dataclass(frozen=True)
+class ContinuityTurn:
+    """What one generic turn may read and write of the session.
+
+    Attributes:
+        history: The previous exchanges, oldest first; empty when the turn is suspended.
+        person_id: The person the session belongs to, or ``None`` for a suspended turn.
+        generation: The session generation this turn read; a stale write is dropped.
+    """
+
+    history: tuple[ConversationTurn, ...]
+    person_id: int | None
+    generation: int
+
+    @property
+    def writable(self) -> bool:
+        """Whether this turn may write an exchange (it is not suspended)."""
+        return self.person_id is not None
+
+
+@dataclass
+class _Slot:
+    person_id: int
+    pairs: deque[tuple[str, str]]
+    last_written: float
+
+
+class ContinuitySession:
+    """The single short-term conversation of the identified person."""
+
+    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
+        """Create an empty session.
+
+        Args:
+            clock: Monotonic seconds; injectable so silence can be tested without sleeping.
+        """
+        self._clock = clock
+        self._slot: _Slot | None = None
+        self._generation = 0
+
+    def open_turn(self, person_id: int | None, cause: SuspendCause | None = None) -> ContinuityTurn:
+        """Apply the transition for one generic turn's speaker and return what it may read.
+
+        Args:
+            person_id: The identified person, or ``None`` when the speaker is unknown,
+                ambiguous or could not be identified (the turn is suspended).
+            cause: Why the turn is suspended; ``NO_EVIDENCE`` when omitted.
+
+        Returns:
+            The turn's view of the session. A suspended turn has no history and cannot write.
+        """
+        self._drop_if_idle()
+        if person_id is None:
+            self._log(Transition.SUSPENDED, cause=cause or SuspendCause.NO_EVIDENCE)
+            return ContinuityTurn((), None, self._generation)
+        slot = self._slot
+        if slot is None:
+            self._slot = _Slot(person_id, deque(), self._clock())
+            self._log(Transition.STARTED, person_id=person_id)
+            return ContinuityTurn((), person_id, self._generation)
+        if slot.person_id != person_id:
+            self._generation += 1
+            self._slot = _Slot(person_id, deque(), self._clock())
+            self._log(Transition.REPLACED, person_id=person_id)
+            return ContinuityTurn((), person_id, self._generation)
+        self._log(Transition.CONTINUED, person_id=person_id)
+        history: list[ConversationTurn] = []
+        for user, assistant in slot.pairs:
+            history.append(ConversationTurn(role="user", content=user))
+            history.append(ConversationTurn(role="assistant", content=assistant))
+        return ContinuityTurn(tuple(history), person_id, self._generation)
+
+    def record_pair(self, turn: ContinuityTurn, user: str, assistant: str) -> bool:
+        """Append one exchange read through *turn*, unless the turn can no longer write.
+
+        Args:
+            turn: The view returned by :meth:`open_turn` for this same turn.
+            user: What the person said.
+            assistant: What was answered.
+
+        Returns:
+            ``True`` when the exchange was kept. ``False`` for a suspended turn, a stale
+            generation (another person replaced the session, or it expired), a message
+            limit that cannot hold one exchange (``WORKING_MEMORY_SIZE`` below 2) or a
+            single exchange larger than ``WORKING_MEMORY_MAX_CHARS``.
+        """
+        slot = self._slot
+        if turn.person_id is None:
+            return False
+        if slot is None or slot.person_id != turn.person_id or turn.generation != self._generation:
+            logger.info("Continuity: write dropped (stale session)")
+            return False
+        if settings.working_memory_size < _USER_AND_ASSISTANT:
+            logger.info("Continuity: write dropped (WORKING_MEMORY_SIZE keeps no exchange)")
+            return False
+        if len(user) + len(assistant) > settings.working_memory_max_chars:
+            logger.info("Continuity: write dropped (exchange larger than the cap)")
+            return False
+        slot.pairs.append((user, assistant))
+        self._trim(slot)
+        slot.last_written = self._clock()
+        return True
+
+    def clear(self) -> None:
+        """Forget the session and its generation (used by tests)."""
+        self._slot = None
+        self._generation = 0
+
+    def _drop_if_idle(self) -> None:
+        """Delete a session that has not been written for ``WORKING_MEMORY_IDLE_SECONDS``."""
+        slot = self._slot
+        if slot is None:
+            return
+        if self._clock() - slot.last_written >= settings.working_memory_idle_seconds:
+            self._slot = None
+            self._generation += 1
+            self._log(Transition.EXPIRED)
+
+    @staticmethod
+    def _trim(slot: _Slot) -> None:
+        """Drop whole oldest exchanges until the character and message caps hold."""
+        max_pairs = settings.working_memory_size // _USER_AND_ASSISTANT
+        while slot.pairs and (
+            len(slot.pairs) > max_pairs
+            or sum(len(user) + len(assistant) for user, assistant in slot.pairs)
+            > settings.working_memory_max_chars
+        ):
+            slot.pairs.popleft()
+
+    @staticmethod
+    def _log(
+        reason: Transition, *, person_id: int | None = None, cause: SuspendCause | None = None
+    ) -> None:
+        """Log one transition with its closed reason; never any conversation text."""
+        logger.info(
+            "Continuity: %s",
+            reason.value,
+            extra={
+                "event": "continuity.transition",
+                "reason": reason,
+                "cause": cause,
+                "person_id": person_id,
+            },
+        )
+
+
+_session = ContinuitySession()
+
+
+def open_turn(person_id: int | None, cause: SuspendCause | None = None) -> ContinuityTurn:
+    """Apply one generic turn's transition on the process-wide session.
+
+    Args:
+        person_id: The identified person, or ``None`` to suspend the turn.
+        cause: Why the turn is suspended; ``NO_EVIDENCE`` when omitted.
+
+    Returns:
+        What the turn may read and write.
+    """
+    return _session.open_turn(person_id, cause)
+
+
+def record_pair(turn: ContinuityTurn, user: str, assistant: str) -> bool:
+    """Append one exchange to the process-wide session; see :meth:`ContinuitySession.record_pair`.
+
+    Args:
+        turn: The view returned by :func:`open_turn` for this turn.
+        user: What the person said.
+        assistant: What was answered.
+
+    Returns:
+        Whether the exchange was kept.
+    """
+    return _session.record_pair(turn, user, assistant)
+
+
+def reset() -> None:
+    """Forget the process-wide session (used by tests)."""
+    _session.clear()
diff --git a/server/src/server/settings.py b/server/src/server/settings.py
--- a/server/src/server/settings.py
+++ b/server/src/server/settings.py
@@ -108,7 +108,11 @@ class Settings(BaseSettings):

     consolidation_model: str = "qwen2.5:3b"

+    # Short-term continuity of the identified person (ADR 0020): at most this many messages,
+    # this many characters of turn content, and this long without a written turn.
     working_memory_size: int = 20
+    working_memory_max_chars: PositiveInt = 3000
+    working_memory_idle_seconds: PositiveInt = 180
     semantic_top_k: int = 6

     memory_enabled: bool = True
```

- [ ] **Step 4: Run, lint, commit.** `uv run pytest tests/unit/test_continuity.py -q
  -p no:cacheprovider` (24 passed); `ruff check` and `ruff format --check` over the three Python
  files; `uv run mypy server/src`; commit `feat(server): add the continuity session slot (plan 0061)`.

---

## Task 2: Identify the speaker of a generic turn

**Files:**
- Create: `server/src/server/cognition/generic_identity.py`
- Modify: `server/src/server/cognition/face_authentication.py`,
  `server/src/server/cognition/identity_fusion.py`
- Test: new `tests/unit/test_generic_identity.py`; modified `tests/unit/test_face_authentication.py`
  and `tests/unit/test_identity_fusion.py`

**Interfaces:**
- Consumes: `build_fused_identity_resolver`, `FusedIdentityResolver.peek_actor` and `.last_reason`,
  `OwnerUnlockService.for_request`, `SuspendCause` (Task 1).
- Produces: `GenericIdentification(actor: ActivePersonContext | None, cause: SuspendCause | None)`
  and `async identify_generic_speaker(for_request, *, token, frame, event, build_resolver=...)`;
  `FaceRequestResolver.detection_failed: bool`; `FusionReason.ERROR`.

- [ ] **Step 1: Write the failing tests.** The new file (12 tests, including the elapsed-time log),
  one test of the face resolver's flag, and two fusion tests (one existing assertion moves from
  `no_evidence` to `error`, D-3):

```diff
diff --git a/tests/unit/test_face_authentication.py b/tests/unit/test_face_authentication.py
--- a/tests/unit/test_face_authentication.py
+++ b/tests/unit/test_face_authentication.py
@@ -340,6 +340,27 @@ async def test_vision_error_degrades_to_unknown_without_raising() -> None:
     assert actor.person_id is None


+@pytest.mark.unit
+async def test_a_failed_detector_is_flagged_and_a_clean_run_is_not() -> None:
+    """The flag lets a caller tell "the backend failed" from "nobody was there" (ADR 0020 §5)."""
+
+    async def failing_detect(_frame: bytes) -> list[DetectedFace]:
+        raise VisionError("model unavailable")
+
+    async def detect_nobody(_frame: bytes) -> list[DetectedFace]:
+        return []
+
+    failed = _resolver(frame=_FRAME, detect_faces=failing_detect)
+    nobody = _resolver(frame=_FRAME, detect_faces=detect_nobody)
+    assert not failed.detection_failed
+
+    await failed.resolve_actor(_event())
+    await nobody.resolve_actor(_event())
+
+    assert failed.detection_failed
+    assert not nobody.detection_failed
+
+
 @pytest.mark.unit
 async def test_no_frame_embedding_or_token_appears_in_logs(
     caplog: pytest.LogCaptureFixture,
diff --git a/tests/unit/test_generic_identity.py b/tests/unit/test_generic_identity.py
new file mode 100644
--- /dev/null
+++ b/tests/unit/test_generic_identity.py
@@ -0,0 +1,278 @@
+"""Unit tests for identifying the speaker of a generic turn (ADR 0020 §1).
+
+Face first, then a presented default-scope token that is only observed; never the voice, never a
+spent grant, and never a failed turn.
+"""
+
+from datetime import UTC, datetime, timedelta
+import logging
+from unittest.mock import AsyncMock
+from uuid import UUID
+
+import aiosqlite
+import numpy as np
+import pytest
+from server.cognition.face_authentication import FaceRequestResolver
+from server.cognition.generic_identity import GenericIdentification, identify_generic_speaker
+from server.cognition.identity import (
+    ActivePersonStatus,
+    HouseholdRole,
+    IdentityAssurance,
+    IdentityEvidenceSource,
+    PersonRecord,
+)
+from server.cognition.identity_fusion import FusedIdentityResolver
+from server.cognition.identity_sessions import IdentitySessionRegistry
+from server.cognition.models import CognitiveEvent
+from server.cognition.owner_authentication import OwnerRequestResolver, OwnerUnlockScope
+from server.cognition.response_plan import TextTurnPayload
+from server.exceptions import BrainMemoryError, VisionError
+from server.memory.continuity import SuspendCause
+from server.settings import settings
+from server.vision.faces import DetectedFace, FaceMatch
+
+pytestmark = pytest.mark.unit
+
+_NOW = datetime(2026, 10, 13, 10, 0, tzinfo=UTC)
+_OWNER_ID = 7
+_OWNER = PersonRecord(person_id=_OWNER_ID, display_name="Canary", entity_type="person")
+_FRAME = b"fake-jpeg-bytes"
+
+
+def _event() -> CognitiveEvent[TextTurnPayload]:
+    return CognitiveEvent(
+        event_id=UUID("33333333-3333-3333-3333-333333333333"),
+        schema_version=1,
+        event_type="text.turn",
+        occurred_at=_NOW,
+        recorded_at=_NOW,
+        source="audio.transcribe",
+        correlation_id=UUID("44444444-4444-4444-4444-444444444444"),
+        causation_id=None,
+        subject_id=None,
+        payload=TextTurnPayload(message="canary", conversation_id="canary-scope"),
+    )
+
+
+class _World:
+    """One request's doubles: a face resolver, a token registry and what the builder saw."""
+
+    def __init__(
+        self,
+        *,
+        faces: int = 1,
+        role: HouseholdRole = HouseholdRole.OWNER,
+        detect_error: Exception | None = None,
+        match_error: Exception | None = None,
+        person_error: Exception | None = None,
+        with_token: bool = False,
+    ) -> None:
+        self.builder_calls: list[dict[str, object]] = []
+        self.registry = IdentitySessionRegistry(
+            lookup_person=lambda _pid: None, clock=lambda: _NOW, ttl=timedelta(seconds=60)
+        )
+        self.token = (
+            self.registry.issue_for_person(
+                _OWNER,
+                source=IdentityEvidenceSource.LOCAL_UNLOCK,
+                scope=OwnerUnlockScope.PERSONAL_PROTECTED_READ.value,
+            )
+            if with_token
+            else None
+        )
+
+        async def detect(_frame: bytes) -> list[DetectedFace]:
+            if detect_error is not None:
+                raise detect_error
+            return [
+                DetectedFace(embedding=np.zeros(512, dtype=np.float32), score=0.9, width=200.0)
+            ] * faces
+
+        async def match(_embedding: np.ndarray) -> FaceMatch | None:
+            if match_error is not None:
+                raise match_error
+            return FaceMatch(entity_id=_OWNER_ID, name="Canary", distance=0.1)
+
+        async def read_person(person_id: int) -> PersonRecord | None:
+            if person_error is not None:
+                raise person_error
+            return _OWNER if person_id == _OWNER_ID else None
+
+        self._face = FaceRequestResolver(
+            frame=_FRAME,
+            clock=lambda: _NOW,
+            read_role=AsyncMock(return_value=role),
+            read_person=AsyncMock(side_effect=read_person),
+            detect_faces=AsyncMock(side_effect=detect),
+            match_face=AsyncMock(side_effect=match),
+            read_consent=AsyncMock(return_value=True),
+        )
+        self._pin_person_error = person_error
+
+    def for_request(self, token: str | None) -> OwnerRequestResolver:
+        async def read_person(_pid: int) -> PersonRecord | None:
+            if self._pin_person_error is not None:
+                raise self._pin_person_error
+            return _OWNER
+
+        return OwnerRequestResolver(
+            token=token,
+            registry=self.registry,
+            read_role=AsyncMock(return_value=HouseholdRole.OWNER),
+            read_person=AsyncMock(side_effect=read_person),
+            clock=lambda: _NOW,
+        )
+
+    def build(
+        self, pin: OwnerRequestResolver, *, frame: bytes | None, wav_bytes: bytes | None
+    ) -> FusedIdentityResolver:
+        self.builder_calls.append({"frame": frame, "wav_bytes": wav_bytes})
+        return FusedIdentityResolver(
+            pin=pin,
+            face=self._face if frame is not None else None,
+            speaker_factory=None,
+            clock=lambda: _NOW,
+        )
+
+    def token_is_unspent(self) -> bool:
+        assert self.token is not None
+        return self.registry.evidence_for(self.token) is not None
+
+
+async def _identify(
+    world: _World, *, frame: bytes | None = _FRAME, token: str | None = None
+) -> GenericIdentification:
+    return await identify_generic_speaker(
+        world.for_request,
+        token=token if token is not None else world.token,
+        frame=frame,
+        event=_event(),
+        build_resolver=world.build,
+    )
+
+
+async def test_the_face_of_the_owner_identifies_at_basic_without_voice() -> None:
+    world = _World()
+
+    result = await _identify(world)
+
+    assert result.cause is None
+    assert result.actor is not None
+    assert result.actor.status is ActivePersonStatus.IDENTIFIED
+    assert result.actor.person_id == _OWNER_ID
+    assert result.actor.assurance is IdentityAssurance.BASIC
+    assert world.builder_calls == [{"frame": _FRAME, "wav_bytes": None}]
+
+
+async def test_without_frame_or_token_the_speaker_is_unknown_for_lack_of_evidence() -> None:
+    world = _World()
+
+    result = await _identify(world, frame=None)
+
+    assert result.actor is not None
+    assert result.actor.status is ActivePersonStatus.UNKNOWN
+    assert result.cause is SuspendCause.NO_EVIDENCE
+
+
+async def test_a_presented_token_names_the_owner_and_is_never_spent() -> None:
+    world = _World(with_token=True)
+
+    result = await _identify(world, frame=None)
+
+    assert result.actor is not None
+    assert result.actor.status is ActivePersonStatus.IDENTIFIED
+    assert result.actor.person_id == _OWNER_ID
+    assert world.token_is_unspent()
+
+
+async def test_an_identified_face_leaves_a_presented_token_untouched() -> None:
+    world = _World(with_token=True)
+
+    result = await _identify(world)
+
+    assert result.actor is not None
+    assert result.actor.assurance is IdentityAssurance.BASIC
+    assert world.token_is_unspent()
+
+
+async def test_another_enrolled_person_suspends_and_keeps_the_token() -> None:
+    world = _World(role=HouseholdRole.ADULT, with_token=True)
+
+    result = await _identify(world)
+
+    assert result.actor is not None
+    assert result.actor.status is ActivePersonStatus.AMBIGUOUS
+    assert result.cause is SuspendCause.VETO_OTHER_PERSON
+    assert world.token_is_unspent()
+
+
+async def test_two_faces_suspend() -> None:
+    world = _World(faces=2, with_token=True)
+
+    result = await _identify(world)
+
+    assert result.cause is SuspendCause.VETO_MULTIPLE_FACES
+    assert world.token_is_unspent()
+
+
+async def test_a_failed_detector_is_reported_as_an_unavailable_backend() -> None:
+    world = _World(detect_error=VisionError("model unavailable"))
+
+    result = await _identify(world)
+
+    assert result.actor is not None
+    assert result.actor.status is ActivePersonStatus.UNKNOWN
+    assert result.cause is SuspendCause.BACKEND_UNAVAILABLE
+
+
+@pytest.mark.parametrize(
+    "error", [BrainMemoryError("db"), aiosqlite.Error("db")], ids=lambda error: type(error).__name__
+)
+async def test_a_store_error_in_the_face_path_never_fails_the_turn(error: Exception) -> None:
+    world = _World(match_error=error)
+
+    result = await _identify(world)
+
+    assert result.actor is not None
+    assert result.actor.status is ActivePersonStatus.UNKNOWN
+    assert result.cause is SuspendCause.ERROR
+
+
+async def test_a_store_error_in_the_token_path_never_fails_the_turn() -> None:
+    world = _World(person_error=BrainMemoryError("db"), with_token=True)
+
+    result = await _identify(world, frame=None)
+
+    assert result.actor is None
+    assert result.cause is SuspendCause.ERROR
+
+
+async def test_identification_is_skipped_when_memory_is_off(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    monkeypatch.setattr(settings, "memory_enabled", False)
+    world = _World(with_token=True)
+
+    result = await _identify(world)
+
+    assert result == GenericIdentification(actor=None, cause=None)
+    assert world.builder_calls == []
+    assert world.token_is_unspent()
+
+
+async def test_the_outcome_and_the_elapsed_time_are_logged_without_personal_data(
+    caplog: pytest.LogCaptureFixture,
+) -> None:
+    """ADR 0020 §10 d: the cost of the face check is measured from the log."""
+    world = _World()
+
+    with caplog.at_level(logging.INFO, logger="server.cognition.generic_identity"):
+        await _identify(world)
+
+    records = [r for r in caplog.records if getattr(r, "event", None) == "identity.generic"]
+    assert len(records) == 1
+    assert getattr(records[0], "outcome", None) == "identified"
+    elapsed = getattr(records[0], "elapsed_ms", None)
+    assert isinstance(elapsed, int)
+    assert elapsed >= 0
+    assert "Canary" not in caplog.text
diff --git a/tests/unit/test_identity_fusion.py b/tests/unit/test_identity_fusion.py
--- a/tests/unit/test_identity_fusion.py
+++ b/tests/unit/test_identity_fusion.py
@@ -38,7 +38,7 @@ from server.cognition.models import (
 from server.cognition.owner_authentication import OwnerRequestResolver, OwnerUnlockScope
 from server.cognition.response_plan import TextTurnPayload
 from server.cognition.speaker_authentication import SpeakerVerdict
-from server.exceptions import BrainMemoryError
+from server.exceptions import BrainMemoryError, VisionError
 from server.vision.faces import DetectedFace, FaceMatch

 if TYPE_CHECKING:
@@ -432,7 +432,7 @@ async def test_a_store_error_in_face_resolution_degrades_to_unknown(
     assert actor.status is ActivePersonStatus.UNKNOWN
     assert again is actor
     assert fused.source is None
-    assert fused.last_reason is FusionReason.NO_EVIDENCE
+    assert fused.last_reason is FusionReason.ERROR
     assert factory.owner_ids == []
     assert detect_calls == [1]
     assert await fused.resolve_consent(event, actor) is ConsentStatus.NOT_REQUIRED
@@ -442,6 +442,35 @@ async def test_a_store_error_in_face_resolution_degrades_to_unknown(
     assert "secret-canary" not in warnings[0]


+async def test_a_failed_face_detector_is_reported_as_an_unavailable_backend() -> None:
+    """ADR 0020 §5: a detector failure is not "no evidence", and a valid token still works."""
+
+    async def failing_detect(_frame: bytes) -> list[DetectedFace]:
+        raise VisionError("model unavailable")
+
+    face = FaceRequestResolver(
+        frame=_FRAME,
+        clock=lambda: _NOW,
+        read_role=AsyncMock(return_value=HouseholdRole.OWNER),
+        read_person=AsyncMock(return_value=_OWNER),
+        detect_faces=AsyncMock(side_effect=failing_detect),
+        match_face=AsyncMock(),
+        read_consent=AsyncMock(return_value=True),
+    )
+    fused = _fused(face=face)
+
+    actor = await fused.peek_actor(_event())
+
+    assert actor.status is ActivePersonStatus.UNKNOWN
+    assert fused.last_reason is FusionReason.BACKEND_UNAVAILABLE
+
+    with_token = _pin(with_token=True)
+    fused_with_token = _fused(face=face, pin=with_token.resolver)
+
+    assert (await fused_with_token.peek_actor(_event())).status is ActivePersonStatus.IDENTIFIED
+    assert fused_with_token.last_reason is FusionReason.PIN
+
+
 @pytest.mark.parametrize("with_token", [True, False], ids=["token", "no-token"])
 @pytest.mark.parametrize("error", _STORE_FAILURES, ids=lambda e: type(e).__name__)
 async def test_a_consent_error_does_not_erase_a_confirmed_other_person_veto(
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_generic_identity.py tests/unit/test_face_authentication.py tests/unit/test_identity_fusion.py -q -p no:cacheprovider`
  Expected RED: `ModuleNotFoundError: No module named 'server.cognition.generic_identity'`, then (with
  that file moved aside) `AttributeError: 'FaceRequestResolver' object has no attribute
  'detection_failed'` and `AttributeError: type object 'FusionReason' has no attribute 'ERROR'`.
- [ ] **Step 3: Implement.**

```diff
diff --git a/server/src/server/cognition/face_authentication.py b/server/src/server/cognition/face_authentication.py
--- a/server/src/server/cognition/face_authentication.py
+++ b/server/src/server/cognition/face_authentication.py
@@ -201,6 +201,9 @@ class FaceRequestResolver:
         self._read_consent = read_consent
         self.consumed = False
         self.last_verdict: FaceAuthenticationVerdict | None = None
+        # True when the detector itself failed (as opposed to finding no face), so a caller
+        # can tell "the backend is down" from "nobody was in frame" (ADR 0020 §5).
+        self.detection_failed = False
         self._cached_context: ActivePersonContext | None = None

     async def resolve_actor(self, event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
@@ -262,6 +265,7 @@ class FaceRequestResolver:
             return await self._detect_faces(self._frame)
         except VisionError as exc:
             logger.warning("Face detection failed, degrading to unknown: %s", exc)
+            self.detection_failed = True
             return []

     async def _match_when_singular(
diff --git a/server/src/server/cognition/generic_identity.py b/server/src/server/cognition/generic_identity.py
new file mode 100644
--- /dev/null
+++ b/server/src/server/cognition/generic_identity.py
@@ -0,0 +1,119 @@
+"""Identify the speaker of a generic turn without side effects (ADR 0020 §1).
+
+A generic turn (conversation that no protected branch claimed) tries to name its speaker so
+the identified person can have short-term continuity. It uses only what the request already
+carries: the face in the frame and, when the face did not resolve, a presented default-scope
+token that is *observed* and never spent. The voice is never consulted (the embedding would
+cost about half a second on every chat turn), so no audio is touched here.
+
+A failure never fails the turn: any error degrades the speaker to unknown.
+"""
+
+from collections.abc import Callable
+from dataclasses import dataclass
+import logging
+import time
+
+from server.cognition.identity import ActivePersonContext, ActivePersonStatus
+from server.cognition.identity_fusion import (
+    FusedIdentityResolver,
+    FusionReason,
+    build_fused_identity_resolver,
+)
+from server.cognition.models import CognitiveEvent
+from server.cognition.owner_authentication import OwnerRequestResolver
+from server.cognition.response_plan import TextTurnPayload
+from server.memory.continuity import SuspendCause
+from server.settings import settings
+
+logger = logging.getLogger(__name__)
+
+__all__ = ["GenericIdentification", "identify_generic_speaker"]
+
+type RequestPinResolver = Callable[[str | None], OwnerRequestResolver]
+type ResolverBuilder = Callable[..., FusedIdentityResolver]
+
+_CAUSES: dict[FusionReason, SuspendCause] = {
+    FusionReason.VETO_OTHER_PERSON: SuspendCause.VETO_OTHER_PERSON,
+    FusionReason.VETO_MULTIPLE_FACES: SuspendCause.VETO_MULTIPLE_FACES,
+    FusionReason.BACKEND_UNAVAILABLE: SuspendCause.BACKEND_UNAVAILABLE,
+    FusionReason.ERROR: SuspendCause.ERROR,
+}
+
+
+@dataclass(frozen=True)
+class GenericIdentification:
+    """The outcome of identifying one generic turn's speaker.
+
+    Attributes:
+        actor: The resolved actor, or ``None`` when identification was skipped or failed
+            before producing one (the turn is then an unknown speaker).
+        cause: Why the turn cannot use the session, from the closed set; ``None`` when the
+            speaker is identified or identification was skipped on purpose.
+    """
+
+    actor: ActivePersonContext | None
+    cause: SuspendCause | None
+
+
+async def identify_generic_speaker(
+    for_request: RequestPinResolver,
+    *,
+    token: str | None,
+    frame: bytes | None,
+    event: CognitiveEvent[TextTurnPayload],
+    build_resolver: ResolverBuilder = build_fused_identity_resolver,
+) -> GenericIdentification:
+    """Name the speaker of a generic turn from the face and an observed token.
+
+    Args:
+        for_request: Builds the request-scoped PIN resolver for a token
+            (``OwnerUnlockService.for_request``).
+        token: The one-use owner token the request presented, or ``None``. It is observed
+            only: this function never spends it.
+        frame: The validated webcam frame, or ``None``. No audio is ever passed.
+        event: The generic turn's event.
+        build_resolver: Composition seam for the fused resolver; tests inject doubles.
+
+    Returns:
+        The speaker and, when it cannot use the session, the closed cause. Never raises.
+    """
+    if not settings.memory_enabled:
+        return GenericIdentification(actor=None, cause=None)
+    started = time.perf_counter()
+    result = await _identify(for_request, token, frame, event, build_resolver)
+    elapsed_ms = round((time.perf_counter() - started) * 1000)
+    outcome = "identified" if result.cause is None else result.cause.value
+    # Closed outcome and a duration only: this is how the cost of the face check on a
+    # generic turn is measured on real hardware (ADR 0020 §10 d).
+    logger.info(
+        "Generic identification: %s (%d ms)",
+        outcome,
+        elapsed_ms,
+        extra={"event": "identity.generic", "outcome": outcome, "elapsed_ms": elapsed_ms},
+    )
+    return result
+
+
+async def _identify(
+    for_request: RequestPinResolver,
+    token: str | None,
+    frame: bytes | None,
+    event: CognitiveEvent[TextTurnPayload],
+    build_resolver: ResolverBuilder,
+) -> GenericIdentification:
+    """Resolve the speaker without side effects; any failure degrades to unknown."""
+    try:
+        fused = build_resolver(for_request(token), frame=frame, wav_bytes=None)
+        actor = await fused.peek_actor(event)
+    except Exception as exc:
+        # Identification must never fail a conversation turn (ADR 0020 §1): whatever the face
+        # model, the identity store or an executor raises, the speaker is simply unknown.
+        logger.warning("Generic identification degraded to unknown: %s", type(exc).__name__)
+        return GenericIdentification(actor=None, cause=SuspendCause.ERROR)
+    if actor.status is ActivePersonStatus.IDENTIFIED:
+        return GenericIdentification(actor=actor, cause=None)
+    reason = fused.last_reason
+    return GenericIdentification(
+        actor=actor, cause=_CAUSES.get(reason, SuspendCause.NO_EVIDENCE) if reason else None
+    )
diff --git a/server/src/server/cognition/identity_fusion.py b/server/src/server/cognition/identity_fusion.py
--- a/server/src/server/cognition/identity_fusion.py
+++ b/server/src/server/cognition/identity_fusion.py
@@ -69,6 +69,7 @@ class FusionReason(StrEnum):
     VETO_OTHER_PERSON = "veto_other_person"
     VETO_MULTIPLE_FACES = "veto_multiple_faces"
     BACKEND_UNAVAILABLE = "backend_unavailable"
+    ERROR = "error"
     NO_EVIDENCE = "no_evidence"


@@ -98,6 +99,7 @@ class FusedIdentityResolver:
         self._clock = clock
         self._cached: ActivePersonContext | None = None
         self._peeked: ActivePersonContext | None = None
+        self._face_store_failed = False
         self.last_reason: FusionReason | None = None
         self.source: IdentitySource | None = None

@@ -195,9 +197,17 @@ class FusedIdentityResolver:
             self.last_reason = FusionReason.PIN
             self.source = "local_unlock"
         else:
-            self.last_reason = FusionReason.NO_EVIDENCE
+            self.last_reason = self._reason_without_identification()
         return pin_context

+    def _reason_without_identification(self) -> FusionReason:
+        """Return why nothing identified the actor: a failing face path, or no evidence."""
+        if self._face_store_failed:
+            return FusionReason.ERROR
+        if self._face is not None and self._face.detection_failed:
+            return FusionReason.BACKEND_UNAVAILABLE
+        return FusionReason.NO_EVIDENCE
+
     async def _resolve_face(
         self, event: CognitiveEvent[TextTurnPayload]
     ) -> ActivePersonContext | None:
@@ -209,6 +219,7 @@ class FusedIdentityResolver:
         except _STORE_ERRORS as exc:
             # Fail closed: neither a veto nor an identification, and nothing personal logged.
             logger.warning("Face identity degraded to unknown: %s", type(exc).__name__)
+            self._face_store_failed = True
             return None
         verdict = self._face.last_verdict
         if verdict is FaceAuthenticationVerdict.AMBIGUOUS:
```

- [ ] **Step 4: Run, mutate, lint, commit.** The three files pass (68 tests). **Mutation:**
  change `fused.peek_actor(event)` to `fused.resolve_actor(event)` and `wav_bytes=None` to
  `wav_bytes=b"x"` in `generic_identity.py`; two tests fail
  (`test_the_face_of_the_owner_identifies_at_basic_without_voice` and
  `test_a_presented_token_names_the_owner_and_is_never_spent`). Revert it. `ruff check`, `ruff format
  --check`, `mypy`; commit `feat(server): identify the speaker of a generic turn (plan 0061)`.

---

## Task 3: Wire the slot into `text_turn`

**Files:**
- Modify: `server/src/server/text_turn.py`, `server/src/server/streaming.py`
- Delete: `server/src/server/memory/working.py`, `tests/unit/test_working_memory.py`
- Test: `tests/unit/test_text_turn.py` (rewritten), `tests/conftest.py`, `tests/unit/test_continuity.py`,
  `tests/integration/test_chat_endpoint.py`, `test_memory_integration.py`,
  `test_transcribe_onboarding.py`, `test_transcribe_stream.py`, `test_vision_memoria.py`

**Interfaces:**
- Consumes: `continuity.open_turn` / `record_pair`, `SuspendCause`, `ASSURANCE_RANK`.
- Produces: `prepare_text_turn(client, message, conversation_id, *, perception=None,
  active_person=None, suspend_cause=None)`; `process_text_turn(..., suspend_cause=None, ...)`;
  `record_text_turn(message, response, *, active_person=None, continuity_turn=None,
  schedule_consolidation=None)`; `PreparedTextTurn.continuity: ContinuityTurn | None` (replaces
  `history_scope`). Eligibility: `IDENTIFIED`, a person id and `ASSURANCE_RANK >= basic`.

- [ ] **Step 1: Write the failing tests.** A single autouse fixture in `tests/conftest.py` resets
  the process-wide slot for the whole suite (so each file's own cleanup disappears); `test_text_turn.py`
  is rewritten (whole file below); the integration tests stop touching `working._buffers`; the
  stream tests pin the new `record_text_turn` arguments:

```diff
diff --git a/tests/conftest.py b/tests/conftest.py
--- a/tests/conftest.py
+++ b/tests/conftest.py
@@ -14,10 +14,23 @@ from robot.conversation_log import CONVERSATION_LOGGER_NAME as ROBOT_CONVERSATIO
 from server.cognition.owner_authentication import owner_unlock_service
 from server.conversation_log import CONVERSATION_LOGGER_NAME as SERVER_CONVERSATION_LOGGER
 from server.main import app
+from server.memory import continuity
 from server.resources import AppResources
 from server.settings import settings


+@pytest.fixture(autouse=True)
+def _continuity_session_empty() -> Generator[None, None, None]:
+    """Start and finish every test with an empty short-term session (ADR 0020).
+
+    The session is one process-wide slot, so a test that leaves a person in it would
+    otherwise hand that person's history to the next test in the same worker.
+    """
+    continuity.reset()
+    yield
+    continuity.reset()
+
+
 @pytest.fixture(autouse=True)
 def _conversation_text_logs_off() -> None:
     """Start every test with both opt-in conversation loggers disabled (Plan 0052).
diff --git a/tests/integration/test_chat_endpoint.py b/tests/integration/test_chat_endpoint.py
--- a/tests/integration/test_chat_endpoint.py
+++ b/tests/integration/test_chat_endpoint.py
@@ -10,7 +10,7 @@ import pytest
 from server.cognition.owner_authentication import owner_unlock_service
 from server.cognition.response_plan import MAX_TURN_MESSAGE_CHARS
 from server.main import app
-from server.memory import working
+from server.memory import continuity
 from server.resources import AppResources
 from server.routers import chat
 from server.settings import settings
@@ -36,13 +36,6 @@ async def _client() -> AsyncIterator[AsyncClient]:
             yield client


-@pytest.fixture(autouse=True)
-def _clear_working_memory() -> None:
-    """Reset process-local conversation buffers before each test."""
-    working._buffers.clear()
-    working._emotion_buffers.clear()
-
-
 @pytest.mark.integration
 @pytest.mark.asyncio
 async def test_chat_returns_exact_contract_and_calls_service_once(
@@ -182,15 +175,11 @@ async def test_chat_openapi_uses_request_and_response_schemas() -> None:
 async def test_chat_without_internal_evidence_is_one_turn_and_stateless(
     monkeypatch: pytest.MonkeyPatch,
 ) -> None:
-    """Public conversation IDs must not unlock history or persistent memory."""
+    """An unidentified chat turn gets no history or persistent memory and leaves nothing."""
     build_context = AsyncMock()
-    get_history = Mock()
-    get_emotion = Mock()
     generate = AsyncMock(side_effect=[("A1", "joy"), ("B1", "sadness"), ("A2", "neutral")])
     monkeypatch.setattr(settings, "memory_enabled", True)
     monkeypatch.setattr(text_turn, "build_context", build_context)
-    monkeypatch.setattr(text_turn.working, "get_history", get_history)
-    monkeypatch.setattr(text_turn.working, "get_recent_emotion", get_emotion)
     monkeypatch.setattr(text_turn.llm, "generate_response", generate)

     async with _client() as client:
@@ -206,12 +195,9 @@ async def test_chat_without_internal_evidence_is_one_turn_and_stateless(
             assert response.status_code == 200

     build_context.assert_not_awaited()
-    get_history.assert_not_called()
-    get_emotion.assert_not_called()
     assert [item.kwargs["context"] for item in generate.await_args_list] == [None, None, None]
     assert [item.kwargs["history"] for item in generate.await_args_list] == [None, None, None]
-    assert working._buffers == {}
-    assert working._emotion_buffers == {}
+    assert continuity.open_turn(7).history == ()


 @pytest.mark.integration
diff --git a/tests/integration/test_memory_integration.py b/tests/integration/test_memory_integration.py
--- a/tests/integration/test_memory_integration.py
+++ b/tests/integration/test_memory_integration.py
@@ -26,7 +26,6 @@ from server.cognition.identity import (
     IdentityEvidenceSource,
 )
 from server.cognition.models import Confidence, ConfidenceBasis
-from server.memory import working
 from server.memory.consolidation import consolidate_turn
 from server.memory.context import build_context
 from server.memory.declarative import (
@@ -87,14 +86,6 @@ async def memory_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: i
     db._conn = None


-@pytest.fixture(autouse=True)
-def _clean_working_memory() -> None:  # type: ignore[misc]
-    """Clear working memory between tests."""
-    working._buffers.clear()
-    yield  # type: ignore[misc]
-    working._buffers.clear()
-
-
 @pytest.mark.integration
 async def test_upsert_entity_returns_positive_id(memory_db: Path) -> None:
     """upsert_entity must return a positive row id."""
diff --git a/tests/integration/test_transcribe_onboarding.py b/tests/integration/test_transcribe_onboarding.py
--- a/tests/integration/test_transcribe_onboarding.py
+++ b/tests/integration/test_transcribe_onboarding.py
@@ -1,11 +1,10 @@
 """Integration tests for onboarding behavior through POST /transcribe."""

-from collections.abc import Generator
 from unittest.mock import AsyncMock

 from fastapi.testclient import TestClient
 import pytest
-from server.memory import meta, working
+from server.memory import meta
 from server.routers import transcribe as transcribe_module
 from server.settings import settings

@@ -13,7 +12,7 @@ from server import llm, onboarding, pipeline, stt, tts


 @pytest.fixture(autouse=True)
-def _mock_memory_pipeline(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
+def _mock_memory_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
     """Enable memory with mocked model boundaries for each onboarding test."""
     monkeypatch.setattr(settings, "memory_enabled", True)
     monkeypatch.setattr(stt, "transcribe", AsyncMock(return_value="hola robot"))
@@ -21,11 +20,6 @@ def _mock_memory_pipeline(monkeypatch: pytest.MonkeyPatch) -> Generator[None, No
     monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("AAAA", 42)))
     monkeypatch.setattr(pipeline, "list_entity_names", AsyncMock(return_value=[]))
     monkeypatch.setattr(transcribe_module, "consolidate_turn", AsyncMock())
-    working._buffers.clear()
-    working._emotion_buffers.clear()
-    yield
-    working._buffers.clear()
-    working._emotion_buffers.clear()


 @pytest.mark.integration
diff --git a/tests/integration/test_transcribe_stream.py b/tests/integration/test_transcribe_stream.py
--- a/tests/integration/test_transcribe_stream.py
+++ b/tests/integration/test_transcribe_stream.py
@@ -23,6 +23,7 @@ from server.cognition.identity import (
 from server.cognition.models import Confidence, ConfidenceBasis, KnowledgeStatus
 from server.cognition.response_plan import InformationNeed, ResponsePlan, ResponseSource
 from server.exceptions import LLMError, TTSError
+from server.memory.continuity import ContinuityTurn
 from server.routers import transcribe as transcribe_module
 from server.schemas import ConversationTurn
 from server.settings import settings
@@ -236,12 +237,7 @@ def test_stream_prepares_shared_voice_turn(
     new_scope.assert_called_once_with()
     assert prepare.await_args is not None
     assert prepare.await_args.args[1:] == ("hola robot", scope)
-    assert record.call_args.args == (
-        "hola robot",
-        scope,
-        "Hola. ¿Cómo estás?",
-        "joy",
-    )
+    assert record.call_args.args == ("hola robot", "Hola. ¿Cómo estás?")
     assert callable(record.call_args.kwargs["schedule_consolidation"])


@@ -898,17 +894,17 @@ def test_stream_neutral_user_message_sends_the_neutral_emotion(


 @pytest.mark.integration
-def test_stream_plain_reply_is_recorded_with_the_users_emotion(
+def test_stream_plain_reply_is_recorded_as_a_normal_turn(
     client: TestClient, silence_wav_bytes: bytes, monkeypatch: pytest.MonkeyPatch
 ) -> None:
-    """A fully spoken plain-text reply is stored as a normal turn with the classified emotion."""
+    """A fully spoken plain-text reply is recorded as one ordinary exchange (ADR 0020)."""
     record = Mock()
     monkeypatch.setattr(streaming, "record_text_turn", record)

     events = _parse_ndjson(_post_stream(client, silence_wav_bytes).text)

     assert events[-1]["type"] == "done"
-    assert record.call_args.args[2:] == ("Hola. ¿Cómo estás?", _USER_EMOTION)
+    assert record.call_args.args[1:] == ("Hola. ¿Cómo estás?",)


 def _assert_one_emotion_before_the_first_audio(events: list[dict[str, object]]) -> None:
@@ -1077,7 +1073,7 @@ async def test_streaming_propagates_prepared_identity_history_and_recording_scop
         None,
         None,
         active_person,
-        "session:11111111111111111111111111111111:person:7",
+        ContinuityTurn((), 7, 0),
     )
     streamed_kwargs: dict[str, object] = {}

@@ -1110,7 +1106,7 @@ async def test_streaming_propagates_prepared_identity_history_and_recording_scop
     record_call = record.call_args
     assert record_call is not None
     assert record_call.kwargs["active_person"] is active_person
-    assert record_call.kwargs["history_scope"] == prepared.history_scope
+    assert record_call.kwargs["continuity_turn"] is prepared.continuity


 @pytest.mark.integration
@@ -1131,7 +1127,7 @@ async def test_streaming_schedules_manual_identity_for_consolidation(
         None,
         None,
         active_person,
-        "session:11111111111111111111111111111111:person:7",
+        ContinuityTurn((), 7, 0),
     )
     scheduler = Mock()
     monkeypatch.setattr(settings, "memory_enabled", True)
diff --git a/tests/integration/test_vision_memoria.py b/tests/integration/test_vision_memoria.py
--- a/tests/integration/test_vision_memoria.py
+++ b/tests/integration/test_vision_memoria.py
@@ -36,7 +36,6 @@ from server.cognition.identity import (
     IdentityEvidenceSource,
 )
 from server.cognition.models import Confidence, ConfidenceBasis
-from server.memory import working
 from server.memory.consolidation import consolidate_turn
 from server.memory.context import build_context
 from server.memory.declarative import find_entities_by_name, get_active_facts
@@ -91,14 +90,6 @@ async def memory_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: i
     db._conn = None


-@pytest.fixture(autouse=True)
-def _clean_working_memory() -> None:  # type: ignore[misc]
-    """Clear working memory between tests (a restart empties it too)."""
-    working._buffers.clear()
-    yield  # type: ignore[misc]
-    working._buffers.clear()
-
-
 async def _consolidate(
     client: httpx.AsyncClient,
     user_text: str,
diff --git a/tests/unit/test_continuity.py b/tests/unit/test_continuity.py
--- a/tests/unit/test_continuity.py
+++ b/tests/unit/test_continuity.py
@@ -4,7 +4,6 @@ One session slot for the identified person: bounded by characters and by silence
 another identified person, suspended (never read or written) by an unknown or ambiguous turn.
 """

-from collections.abc import Generator
 import logging

 import pytest
@@ -30,14 +29,6 @@ class _Clock:
         return self.now


-@pytest.fixture(autouse=True)
-def _clean_session() -> Generator[None, None, None]:
-    """Start and finish every test with an empty process-wide slot."""
-    continuity.reset()
-    yield
-    continuity.reset()
-
-
 @pytest.fixture
 def clock() -> _Clock:
     return _Clock()
```

  `tests/unit/test_text_turn.py`, the whole new file:

```python
from datetime import UTC, datetime
import inspect
import logging
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import httpx
import pytest
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityAssurance,
    IdentityEvidence,
    IdentityEvidenceSource,
)
from server.cognition.models import Confidence, ConfidenceBasis
from server.exceptions import BrainMemoryError, LLMError
from server.memory import continuity
from server.memory.continuity import SuspendCause, Transition
from server.schemas import MemoryContext
from server.settings import settings

from server import text_turn

_DEFAULT_SESSION_ID = UUID("11111111-1111-1111-1111-111111111111")
_OWNER = 7
_VISITOR = 8


def _evidence(
    source: IdentityEvidenceSource,
    *,
    person_id: int = _OWNER,
    session_id: UUID = _DEFAULT_SESSION_ID,
) -> IdentityEvidence:
    """Create one piece of trusted evidence for an internal test adapter."""
    return IdentityEvidence(
        evidence_id=session_id,
        source=source,
        candidate_person_id=person_id,
        confidence=Confidence(
            score=1.0,
            basis=ConfidenceBasis.ASSERTED,
            calibrated=True,
            reason="Explicit local selection",
        ),
        observed_at=datetime(2026, 8, 10, tzinfo=UTC),
        expires_at=None,
        reference="trusted-local-adapter",
    )


def _person(
    source: IdentityEvidenceSource,
    *,
    person_id: int = _OWNER,
    display_name: str = "Paula",
    session_id: UUID = _DEFAULT_SESSION_ID,
    assurance: IdentityAssurance = IdentityAssurance.BASIC,
) -> ActivePersonContext:
    """Create an identified context the way `resolve_active_person` would."""
    return ActivePersonContext(
        person_id=person_id,
        display_name=display_name,
        status=ActivePersonStatus.IDENTIFIED,
        confidence=Confidence(
            score=1.0,
            basis=ConfidenceBasis.ASSERTED,
            calibrated=True,
            reason="Explicit local selection",
        ),
        role=HouseholdRole.UNKNOWN,
        evidence=(_evidence(source, person_id=person_id, session_id=session_id),),
        resolved_at=datetime(2026, 8, 10, tzinfo=UTC),
        assurance=assurance,
    )


def _identified_person(
    *,
    person_id: int = _OWNER,
    display_name: str = "Paula",
    session_id: UUID = _DEFAULT_SESSION_ID,
) -> ActivePersonContext:
    """Create an identified manual context for a trusted internal test adapter."""
    return _person(
        IdentityEvidenceSource.MANUAL,
        person_id=person_id,
        display_name=display_name,
        session_id=session_id,
    )


def _unidentified_person(status: ActivePersonStatus) -> ActivePersonContext:
    """Create an explicit non-identified active-person result for one turn."""
    return ActivePersonContext(
        person_id=None,
        display_name=None,
        status=status,
        confidence=Confidence(
            score=0.0,
            basis=ConfidenceBasis.NOT_APPLICABLE,
            calibrated=False,
            reason="No verified person",
        ),
        role=HouseholdRole.UNKNOWN,
        evidence=(),
        resolved_at=datetime(2026, 8, 10, tzinfo=UTC),
    )


def _generate(monkeypatch: pytest.MonkeyPatch, *replies: tuple[str, str]) -> AsyncMock:
    """Replace the model call with scripted replies and return the mock."""
    generate = AsyncMock(side_effect=list(replies))
    monkeypatch.setattr(text_turn.llm, "generate_response", generate)
    return generate


def _persistent_context(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Replace persistent-context retrieval with a spy returning an empty context."""
    prompt_state = AsyncMock(return_value=(MemoryContext(), False, None))
    monkeypatch.setattr(text_turn, "_memory_prompt_state", prompt_state)
    return prompt_state


def _histories(generate: AsyncMock) -> list[list[str] | None]:
    """Return, per model call, the contents of the history it received (None if none)."""
    return [
        None if call.kwargs["history"] is None else [t.content for t in call.kwargs["history"]]
        for call in generate.await_args_list
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stateless_turn_calls_llm_once(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Disabled memory should still produce one typed text result."""
    generate = AsyncMock(return_value=("Hola", "joy"))
    monkeypatch.setattr(settings, "memory_enabled", False)
    monkeypatch.setattr(text_turn.llm, "generate_response", generate)

    result = await text_turn.process_text_turn(http_client, "Hola", "web-a")

    assert result.response == "Hola"
    assert result.emotion == "joy"
    assert result.duration_ms >= 0
    assert result.llm_failed is False
    generate.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_memory_off_never_touches_the_session(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "memory_enabled", False)
    generate = _generate(monkeypatch, ("Hola", "neutral"))
    opened = Mock()
    monkeypatch.setattr(text_turn.continuity, "open_turn", opened)

    await text_turn.process_text_turn(
        http_client, "Hola", "web-a", active_person=_identified_person()
    )

    opened.assert_not_called()
    assert _histories(generate)[0] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_session_follows_the_person_and_not_the_public_conversation_id(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A client-chosen conversation id is not identity (ADR 0020 §3)."""
    monkeypatch.setattr(settings, "memory_enabled", True)
    _persistent_context(monkeypatch)
    generate = _generate(monkeypatch, ("A1", "joy"), ("B1", "sadness"), ("A2", "neutral"))
    person = _identified_person()

    await text_turn.process_text_turn(http_client, "question-a", "web-a", active_person=person)
    await text_turn.process_text_turn(http_client, "question-b", "web-b", active_person=person)
    await text_turn.process_text_turn(http_client, "follow-up-a", "web-a", active_person=person)

    assert _histories(generate) == [
        [],
        ["question-a", "A1"],
        ["question-a", "A1", "question-b", "B1"],
    ]
    assert all(call.kwargs["user_emotion"] is None for call in generate.await_args_list)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_another_identified_person_starts_a_fresh_session(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "memory_enabled", True)
    _persistent_context(monkeypatch)
    generate = _generate(monkeypatch, ("A1", "neutral"), ("B1", "neutral"), ("A2", "neutral"))
    owner = _identified_person()
    visitor = _identified_person(person_id=_VISITOR, display_name="Mateo")

    await text_turn.process_text_turn(http_client, "owner says", "web", active_person=owner)
    await text_turn.process_text_turn(http_client, "visitor says", "web", active_person=visitor)
    await text_turn.process_text_turn(http_client, "owner again", "web", active_person=owner)

    assert _histories(generate) == [[], [], []]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_session_is_keyed_by_person_id_not_by_name_or_evidence_id(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Display names and evidence ids must not scope the session."""
    monkeypatch.setattr(settings, "memory_enabled", True)
    _persistent_context(monkeypatch)
    generate = _generate(
        monkeypatch, ("Primera", "neutral"), ("Segunda", "neutral"), ("Tercera", "neutral")
    )
    first = _identified_person(display_name="Paula")
    renamed = _identified_person(display_name="Paula Ramírez")
    other_evidence = _identified_person(session_id=UUID("33333333-3333-3333-3333-333333333333"))

    await text_turn.process_text_turn(http_client, "primera", "public-a", active_person=first)
    await text_turn.process_text_turn(http_client, "segunda", "public-b", active_person=renamed)
    await text_turn.process_text_turn(
        http_client, "tercera", "public-a", active_person=other_evidence
    )

    assert _histories(generate)[1] == ["primera", "Primera"]
    assert _histories(generate)[2] == [
        "primera",
        "Primera",
        "segunda",
        "Segunda",
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_manual_identified_turn_schedules_legacy_callback(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only manual identity may reach consolidation and must remain attached."""
    generate = AsyncMock(return_value=("Veo una taza", "neutral"))
    scheduler = Mock()
    monkeypatch.setattr(settings, "memory_enabled", True)
    _persistent_context(monkeypatch)
    monkeypatch.setattr(text_turn.llm, "generate_response", generate)

    person = _identified_person()
    await text_turn.process_text_turn(
        http_client,
        "¿Qué ves?",
        "vision-a",
        perception="A blue mug",
        schedule_consolidation=scheduler,
        active_person=person,
    )

    assert generate.await_args_list[-1].kwargs["perception"] == "A blue mug"
    assert [turn.content for turn in continuity.open_turn(_OWNER).history] == [
        "¿Qué ves?",
        "Veo una taza",
    ]
    scheduler.assert_called_once_with("¿Qué ves?", "Veo una taza", person)


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source, assurance",
    [
        (IdentityEvidenceSource.FACE, IdentityAssurance.BASIC),
        (IdentityEvidenceSource.LOCAL_UNLOCK, IdentityAssurance.STRONG),
    ],
)
async def test_a_face_or_token_identified_turn_has_history_and_nothing_durable(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    source: IdentityEvidenceSource,
    assurance: IdentityAssurance,
) -> None:
    """ADR 0020 §2: continuity opens the history only; the MANUAL gate keeps the rest closed."""
    scheduler = Mock()
    prompt_state = _persistent_context(monkeypatch)
    build_context = AsyncMock()
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(text_turn, "build_context", build_context)
    generate = _generate(monkeypatch, ("Uno", "neutral"), ("Dos", "neutral"))
    person = _person(source, assurance=assurance)

    for message in ("primero", "segundo"):
        await text_turn.process_text_turn(
            http_client,
            message,
            "web",
            active_person=person,
            schedule_consolidation=scheduler,
        )

    assert _histories(generate) == [[], ["primero", "Uno"]]
    for call in generate.await_args_list:
        assert call.kwargs["context"] is None
        assert call.kwargs["onboarding"] is False
        assert call.kwargs["user_emotion"] is None
    prompt_state.assert_not_awaited()
    build_context.assert_not_awaited()
    scheduler.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_an_identified_context_without_assurance_has_no_continuity(
    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rank rule: `none` never reaches the `basic` minimum, whatever the status says."""
    monkeypatch.setattr(settings, "memory_enabled", True)
    generate = _generate(monkeypatch, ("Uno", "neutral"), ("Dos", "neutral"))
    person = _person(IdentityEvidenceSource.FACE, assurance=IdentityAssurance.NONE)

    await text_turn.process_text_turn(http_client, "primero", "web", active_person=person)
    await text_turn.process_text_turn(http_client, "segundo", "web", active_person=person)

    assert _histories(generate) == [None, None]


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        ActivePersonStatus.UNKNOWN,
        ActivePersonStatus.PROBABLE,
        ActivePersonStatus.AMBIGUOUS,
    ],
)
async def test_a_suspended_turn_reads_nothing_writes_nothing_and_spares_the_session(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    status: ActivePersonStatus,
) -> None:
    """An uncertain person gets one stateless answer; the owner's session survives."""
    build_context = AsyncMock()
    scheduler = Mock()
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(text_turn, "build_context", build_context)
    prompt_state = _persistent_context(monkeypatch)
    generate = _generate(
        monkeypatch, ("Owner reply", "neutral"), ("Stranger reply", "neutral"), ("Back", "neutral")
    )
    owner = _identified_person()

    await text_turn.process_text_turn(http_client, "owner says", "web", active_person=owner)
    await text_turn.process_text_turn(
        http_client,
        "stranger asks",
        "web",
        active_person=_unidentified_person(status),
        schedule_consolidation=scheduler,
    )
    await text_turn.process_text_turn(http_client, "owner again", "web", active_person=owner)

    assert _histories(generate) == [
        [],
        None,
        ["owner says", "Owner reply"],
    ]
    build_context.assert_not_awaited()
    assert prompt_state.await_count == 2  # the two MANUAL owner turns, never the stranger
    scheduler.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_suspension_cause_reaches_the_transition_log(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(settings, "memory_enabled", True)
    _generate(monkeypatch, ("Reply", "neutral"))

    with caplog.at_level(logging.INFO, logger=continuity.logger.name):
        await text_turn.process_text_turn(
            http_client,
            "Question",
            "web",
            active_person=_unidentified_person(ActivePersonStatus.AMBIGUOUS),
            suspend_cause=SuspendCause.VETO_MULTIPLE_FACES,
        )

    suspended = [r for r in caplog.records if getattr(r, "reason", None) is Transition.SUSPENDED]
    assert [getattr(r, "cause", None) for r in suspended] == [SuspendCause.VETO_MULTIPLE_FACES]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unknown_turn_leaves_nothing_in_the_session(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A public chat turn is unknown: answered and forgotten."""
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(
        text_turn.llm, "generate_response", AsyncMock(return_value=("Reply", "neutral"))
    )

    await text_turn.process_text_turn(http_client, "Question", "web-a")

    assert continuity.open_turn(_OWNER).history == ()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_fallback_does_not_contaminate_memory(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expected provider failures should return a local fallback without recording."""
    scheduler = Mock()
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(
        text_turn, "_memory_prompt_state", AsyncMock(return_value=(None, False, None))
    )
    monkeypatch.setattr(text_turn.llm, "generate_response", AsyncMock(side_effect=LLMError("down")))

    result = await text_turn.process_text_turn(
        http_client,
        "Question",
        "web-a",
        active_person=_identified_person(),
        schedule_consolidation=scheduler,
    )

    assert result.response == settings.llm_fallback_phrase
    assert result.emotion == "neutral"
    assert result.llm_failed is True
    assert continuity.open_turn(_OWNER).history == ()
    scheduler.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_connection_refused_logs_without_a_traceback(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unreachable Ollama is expected and already handled (fallback phrase)
    — it must log a short, actionable message, never a full httpx/httpcore
    traceback (Plan 0044 Task 6)."""
    error = LLMError("LLM API call failed")
    error.__cause__ = httpx.ConnectError("refused")
    monkeypatch.setattr(text_turn.llm, "generate_response", AsyncMock(side_effect=error))

    with caplog.at_level(logging.WARNING, logger="server.text_turn"):
        result = await text_turn.process_text_turn(http_client, "Question", "web-b")

    assert result.response == settings.llm_fallback_phrase
    records = [r for r in caplog.records if r.name == "server.text_turn"]
    assert records, "expected a log record for the LLM failure"
    assert all(r.exc_info is None for r in records), "must not log a traceback"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_unexpected_failure_still_logs_a_traceback(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A genuinely unexpected LLM failure (not a connectivity issue) must
    keep its full traceback — only the connectivity case gets quieter."""
    monkeypatch.setattr(
        text_turn.llm, "generate_response", AsyncMock(side_effect=LLMError("malformed output"))
    )

    with caplog.at_level(logging.WARNING, logger="server.text_turn"):
        result = await text_turn.process_text_turn(http_client, "Question", "web-c")

    assert result.response == settings.llm_fallback_phrase
    records = [r for r in caplog.records if r.name == "server.text_turn"]
    assert records, "expected a log record for the LLM failure"
    assert any(r.exc_info is not None for r in records), "must keep the traceback"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_memory_failure_degrades_to_generation_without_context(
    http_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persistent memory failure should not prevent a text response."""
    generate = AsyncMock(return_value=("Reply", "neutral"))
    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(
        text_turn, "build_context", AsyncMock(side_effect=BrainMemoryError("db down"))
    )
    monkeypatch.setattr(text_turn.llm, "generate_response", generate)

    result = await text_turn.process_text_turn(
        http_client, "Question", "web-a", active_person=_identified_person()
    )

    assert result.response == "Reply"
    assert generate.await_args_list[-1].kwargs["context"] is None
    assert generate.await_args_list[-1].kwargs["onboarding"] is False


@pytest.mark.unit
def test_public_apis_are_typed_and_documented() -> None:
    """Public service APIs should expose typed signatures and docstrings."""
    for api in (
        text_turn.prepare_text_turn,
        text_turn.record_text_turn,
        text_turn.process_text_turn,
    ):
        signature = inspect.signature(api)
        assert api.__doc__
        assert signature.return_annotation is not inspect.Signature.empty
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_text_turn.py tests/integration/test_chat_endpoint.py tests/integration/test_transcribe_stream.py -q -p no:cacheprovider -p no:xdist`
  Expected RED (with `memory/working.py` still in place): 13 failures such as `TypeError:
  process_text_turn() got an unexpected keyword argument 'suspend_cause'` and `assert [None, None]
  == [[], ['primero', 'Uno']]`.
- [ ] **Step 3: Implement**, then delete the old module and its test with `git rm`:

```diff
diff --git a/server/src/server/streaming.py b/server/src/server/streaming.py
--- a/server/src/server/streaming.py
+++ b/server/src/server/streaming.py
@@ -114,11 +114,9 @@ def _record_success(
         return
     record_text_turn(
         prepared.message,
-        prepared.conversation_id,
         " ".join(state.response_parts),
-        state.emotion or llm.FALLBACK_EMOTION,
         active_person=prepared.active_person,
-        history_scope=prepared.history_scope,
+        continuity_turn=prepared.continuity,
         schedule_consolidation=scheduler,
     )

diff --git a/server/src/server/text_turn.py b/server/src/server/text_turn.py
--- a/server/src/server/text_turn.py
+++ b/server/src/server/text_turn.py
@@ -10,16 +10,19 @@ from uuid import uuid4
 import httpx

 from server import llm, turn_log
+from server.cognition.authorization import ASSURANCE_RANK
 from server.cognition.identity import (
     ActivePersonContext,
     ActivePersonStatus,
+    IdentityAssurance,
     IdentityEvidence,
     IdentityEvidenceSource,
     resolve_active_person,
 )
 from server.exceptions import BrainMemoryError, LLMError
-from server.memory import working
+from server.memory import continuity
 from server.memory.context import build_context
+from server.memory.continuity import ContinuityTurn, SuspendCause
 from server.onboarding import OnboardingSlot
 from server.schemas import ConversationTurn, MemoryContext
 from server.settings import settings
@@ -42,7 +45,7 @@ class PreparedTextTurn:
     user_emotion: str | None
     perception: str | None
     active_person: ActivePersonContext | None = None
-    history_scope: str | None = None
+    continuity: ContinuityTurn | None = None


 @dataclass(frozen=True)
@@ -86,29 +89,26 @@ def _manual_evidence(active_person: ActivePersonContext) -> IdentityEvidence | N


 def new_interaction_scope() -> str:
-    """Create an opaque working-memory scope for one unresolved request.
+    """Create an opaque conversation identifier for one unresolved request.

     Returns:
-        A process-local scope not derived from user input or exposed by a response.
+        A process-local identifier not derived from user input or exposed by a response.
+        It labels an event only: it is never identity and never selects the session.
     """
     return f"interaction:{uuid4().hex}"


-def _history_scope(active_person: ActivePersonContext) -> str:
-    """Return an internal history key without trusting a public conversation ID."""
-    evidence = _manual_evidence(active_person)
-    if evidence is not None:
-        return f"session:{evidence.evidence_id.hex}:person:{active_person.person_id}"
-    return new_interaction_scope()
+def _continuity_person_id(active_person: ActivePersonContext) -> int | None:
+    """Return the person who may use the short-term session, or ``None`` (ADR 0020 §2).

-
-def _clear_evidence_scopes(active_person: ActivePersonContext) -> None:
-    """Clear histories associated with expired, cleared, or ambiguous evidence."""
-    for evidence in active_person.evidence:
-        if evidence.candidate_person_id is not None:
-            working.clear(
-                f"session:{evidence.evidence_id.hex}:person:{evidence.candidate_person_id}"
-            )
+    Only a person identified by a trusted source with an assurance of at least ``basic``
+    has continuity. Assurance is compared through its rank, never alphabetically.
+    """
+    if active_person.status is not ActivePersonStatus.IDENTIFIED or active_person.person_id is None:
+        return None
+    if ASSURANCE_RANK[active_person.assurance] < ASSURANCE_RANK[IdentityAssurance.BASIC]:
+        return None
+    return active_person.person_id


 async def _memory_prompt_state(
@@ -131,16 +131,23 @@ async def prepare_text_turn(
     *,
     perception: str | None = None,
     active_person: ActivePersonContext | None = None,
+    suspend_cause: SuspendCause | None = None,
 ) -> PreparedTextTurn:
     """Resolve shared prompt inputs for one conversation.

+    The speaker decides what the turn may read (ADR 0020): an identified person gets the
+    short-term session's history; an unknown or ambiguous speaker suspends it and the turn
+    reads nothing. Persistent context stays behind the ``MANUAL`` gate, so durable memory is
+    still closed for every other speaker.
+
     Args:
         client: Shared, lifecycle-owned HTTP client (Plan 0039), forwarded
-            to memory retrieval when a verified identity has history.
+            to memory retrieval when a manually verified identity has history.
         message: Current user message.
-        conversation_id: Ephemeral working-memory identifier.
+        conversation_id: Ephemeral conversation label; never identity, never selects history.
         perception: Optional textual visual perception for this turn.
         active_person: Internally resolved evidence for this turn only.
+        suspend_cause: Why the speaker could not be identified, for the transition log.

     Returns:
         Immutable inputs for one LLM generation.
@@ -151,10 +158,6 @@ async def prepare_text_turn(
     if not conversation_id:
         raise ValueError("conversation_id must not be empty")
     resolved_person = _resolve_turn_person(active_person)
-    history_scope = _history_scope(resolved_person)
-    manual_evidence = _manual_evidence(resolved_person)
-    if manual_evidence is None:
-        _clear_evidence_scopes(resolved_person)
     if not settings.memory_enabled:
         turn_log.log_memory("skipped", "MEMORY_ENABLED is off")
         return PreparedTextTurn(
@@ -167,29 +170,21 @@ async def prepare_text_turn(
             user_emotion=None,
             perception=perception,
             active_person=resolved_person,
-            history_scope=history_scope,
         )
-    if manual_evidence is None:
+    person_id = _continuity_person_id(resolved_person)
+    turn = continuity.open_turn(person_id, None if person_id is not None else suspend_cause)
+    history = list(turn.history) if turn.writable else None
+    context: MemoryContext | None = None
+    onboarding = False
+    slot: OnboardingSlot | None = None
+    if _manual_evidence(resolved_person) is not None:
+        context, onboarding, slot = await _memory_prompt_state(client, message)
+        turn_log.log_memory("loaded", f"verified identity, history_turns={len(history or [])}")
+    else:
         turn_log.log_memory(
-            "skipped",
-            "no verified identity — no history, no retrieval, no vector search",
-        )
-        return PreparedTextTurn(
-            message=message,
-            conversation_id=conversation_id,
-            context=None,
-            history=None,
-            onboarding=False,
-            onboarding_slot=None,
-            user_emotion=None,
-            perception=perception,
-            active_person=resolved_person,
-            history_scope=history_scope,
+            "loaded" if turn.writable else "skipped",
+            f"history_turns={len(history or [])}, no retrieval, no vector search",
         )
-    history = working.get_history(history_scope)
-    user_emotion = working.get_recent_emotion(history_scope)
-    turn_log.log_memory("loaded", f"verified identity, history_turns={len(history)}")
-    context, onboarding, slot = await _memory_prompt_state(client, message)
     return PreparedTextTurn(
         message=message,
         conversation_id=conversation_id,
@@ -197,10 +192,10 @@ async def prepare_text_turn(
         history=history,
         onboarding=onboarding,
         onboarding_slot=slot,
-        user_emotion=user_emotion,
+        user_emotion=None,
         perception=perception,
         active_person=resolved_person,
-        history_scope=history_scope,
+        continuity=turn,
     )


@@ -235,38 +230,31 @@ async def _generate(client: httpx.AsyncClient, prepared: PreparedTextTurn) -> tu

 def record_text_turn(
     message: str,
-    _conversation_id: str,
     response: str,
-    emotion: str,
     *,
     active_person: ActivePersonContext | None = None,
-    history_scope: str | None = None,
+    continuity_turn: ContinuityTurn | None = None,
     schedule_consolidation: ConsolidationScheduler | None = None,
 ) -> None:
     """Record a successful turn and optionally schedule consolidation.

     Args:
         message: Current user message.
-        conversation_id: Ephemeral working-memory identifier.
         response: Generated assistant response.
-        emotion: The user's emotion for this turn (the classic path reads it from the model's
-            JSON; the streaming path decides it from the user's text before generating).
         active_person: Internally resolved evidence for this turn only.
-        history_scope: Internal working-memory key calculated during preparation.
-        schedule_consolidation: Optional channel-owned scheduling callback.
+        continuity_turn: The session view this turn read; a suspended or stale turn writes
+            nothing.
+        schedule_consolidation: Optional channel-owned scheduling callback; reached only by a
+            manually verified identity, never by a face or a token.
     """
     if not settings.memory_enabled:
         return
     resolved_person = _resolve_turn_person(active_person)
-    scope = history_scope or _history_scope(resolved_person)
-    working.add_emotion(scope, emotion)
-    working.add_turn(scope, "user", message)
-    working.add_turn(scope, "assistant", response)
-    if _manual_evidence(resolved_person) is None:
-        working.clear(scope)
-        turn_log.log_memory("discarded", "no verified identity — working memory cleared")
-        return
-    if schedule_consolidation is not None:
+    if continuity_turn is not None and continuity.record_pair(continuity_turn, message, response):
+        turn_log.log_memory("recorded", "identified speaker, exchange kept in the session")
+    else:
+        turn_log.log_memory("discarded", "no identified speaker, nothing kept")
+    if schedule_consolidation is not None and _manual_evidence(resolved_person) is not None:
         # Identity gates this legacy callback; it is not an authorization decision.
         schedule_consolidation(message, response, resolved_person)
         turn_log.log_memory("consolidation-scheduled", "verified identity")
@@ -279,6 +267,7 @@ async def process_text_turn(
     *,
     perception: str | None = None,
     active_person: ActivePersonContext | None = None,
+    suspend_cause: SuspendCause | None = None,
     schedule_consolidation: ConsolidationScheduler | None = None,
 ) -> TextTurnResult:
     """Generate and record one channel-agnostic text turn.
@@ -286,9 +275,10 @@ async def process_text_turn(
     Args:
         client: Shared, lifecycle-owned HTTP client (Plan 0039).
         message: Current user message.
-        conversation_id: Ephemeral working-memory identifier.
+        conversation_id: Ephemeral conversation label; never identity.
         perception: Optional textual visual perception for this turn.
         active_person: Internally resolved evidence for this turn only.
+        suspend_cause: Why the speaker could not be identified, for the transition log.
         schedule_consolidation: Optional channel-owned scheduling callback.

     Returns:
@@ -301,16 +291,15 @@ async def process_text_turn(
         conversation_id,
         perception=perception,
         active_person=active_person,
+        suspend_cause=suspend_cause,
     )
     response, emotion, llm_failed = await _generate(client, prepared)
     if not llm_failed:
         record_text_turn(
             message,
-            conversation_id,
             response,
-            emotion,
             active_person=prepared.active_person,
-            history_scope=prepared.history_scope,
+            continuity_turn=prepared.continuity,
             schedule_consolidation=schedule_consolidation,
         )
     duration_ms = round((time.perf_counter() - started) * 1000)
```

- [ ] **Step 4: Run, lint, commit.** `uv run pytest tests/unit tests/integration -q -p no:cacheprovider
  -n auto` passes; `ruff check .`, `ruff format --check .`, `uv run mypy server/src robot/src`;
  commit `feat(server): continuity session for the identified person (plan 0061)`.

---

## Task 4: Identify the speaker in the three routes

**Files:**
- Modify: `server/src/server/routers/chat.py`, `server/src/server/routers/transcribe.py`
- Test: new `tests/integration/test_generic_turn_continuity.py`; modified
  `tests/integration/test_chat_endpoint.py` and `tests/integration/test_transcribe_pipeline.py`

**Interfaces:**
- Consumes: `identify_generic_speaker`, `GenericIdentification` (Task 2),
  `process_text_turn(..., active_person, suspend_cause)` (Task 3).
- Produces: nothing new; `/vision/respond` is untouched on purpose.

- [ ] **Step 1: Write the failing tests.** Seven real-route scenarios (voice and face with no voice
  embedding, a second face suspends and the owner resumes, no frame is stateless, the streaming route,
  a `/chat` token across public ids and never spent, a protected answer spends the token and never
  enters the session, and a `/vision/respond` turn that neither reads nor writes the session) and the
  two older tests that pinned the old call:

```diff
diff --git a/tests/integration/test_chat_endpoint.py b/tests/integration/test_chat_endpoint.py
--- a/tests/integration/test_chat_endpoint.py
+++ b/tests/integration/test_chat_endpoint.py
@@ -7,10 +7,12 @@ from unittest.mock import ANY, AsyncMock, Mock

 from httpx import ASGITransport, AsyncClient
 import pytest
+from server.cognition.identity import ActivePersonStatus
 from server.cognition.owner_authentication import owner_unlock_service
 from server.cognition.response_plan import MAX_TURN_MESSAGE_CHARS
 from server.main import app
 from server.memory import continuity
+from server.memory.continuity import SuspendCause
 from server.resources import AppResources
 from server.routers import chat
 from server.settings import settings
@@ -59,7 +61,14 @@ async def test_chat_returns_exact_contract_and_calls_service_once(
         "conversation_id": "web-primary",
         "authentication_consumed": False,
     }
-    process.assert_awaited_once_with(ANY, "Hello", "web-primary")
+    process.assert_awaited_once()
+    call = process.await_args
+    assert call is not None
+    assert call.args == (ANY, "Hello", "web-primary")
+    # No frame and no token: the speaker is the public unknown, and the turn is suspended
+    # for lack of evidence (ADR 0020 §1).
+    assert call.kwargs["active_person"].status is ActivePersonStatus.UNKNOWN
+    assert call.kwargs["suspend_cause"] is SuspendCause.NO_EVIDENCE


 @pytest.mark.integration
diff --git a/tests/integration/test_generic_turn_continuity.py b/tests/integration/test_generic_turn_continuity.py
new file mode 100644
--- /dev/null
+++ b/tests/integration/test_generic_turn_continuity.py
@@ -0,0 +1,342 @@
+"""Short-term continuity through the real generic-turn routes (Plan 0061, ADR 0020).
+
+Face detection and the speaker embedding are doubles; face matching, the identity store and the
+unlock registry are real. Model replies are scripted: no real model, no recording.
+"""
+
+from collections.abc import AsyncIterator
+from contextlib import asynccontextmanager
+from datetime import UTC, datetime, timedelta
+import io
+import json
+from pathlib import Path
+from unittest.mock import AsyncMock
+import wave
+
+import cv2
+from httpx import ASGITransport, AsyncClient
+import numpy as np
+from pydantic import SecretStr
+import pytest
+from server.cognition import (
+    face_authentication as face_auth_module,
+    speaker_authentication as speaker_auth_module,
+)
+from server.cognition.identity import PersonRecord
+from server.cognition.identity_sessions import IdentitySessionRegistry
+from server.cognition.owner_authentication import OwnerUnlockService, owner_unlock_service
+from server.dependencies import get_owner_unlock_service
+from server.main import app
+from server.memory.biometric_consent import grant_face_consent
+from server.memory.entity_labels import get_person_label
+from server.memory.household_authorization import get_active_role
+from server.memory.owner_credentials import get_active_owner_pin_credential
+from server.personal_setup import PersonalSetupInput, PersonalSetupResult, apply_personal_setup
+from server.resources import AppResources
+from server.settings import settings
+from server.vision.faces import DetectedFace, enroll_face
+
+from server import db, llm, llm_streaming, stt, tts
+
+_PIN = "482173"
+_OWNER_NAME = "Canary"
+_CHILD_QUESTION = "¿Quiénes son mis hijos?"
+_FRAME = cv2.imencode(".jpg", np.zeros((10, 10, 3), dtype=np.uint8))[1].tobytes()
+_OWNER_FACE = np.eye(512, dtype=np.float32)[0]
+_STRANGER_FACE = np.eye(512, dtype=np.float32)[1]
+
+
+def _detected(embedding: np.ndarray) -> DetectedFace:
+    return DetectedFace(embedding=embedding, score=0.9, width=200.0)
+
+
+def _tone_wav(seconds: float = 3.0) -> bytes:
+    t = np.linspace(0.0, seconds, int(16_000 * seconds), endpoint=False)
+    samples = (8_000 * np.sin(2 * np.pi * 220 * t)).astype(np.int16)
+    buffer = io.BytesIO()
+    with wave.open(buffer, "wb") as handle:
+        handle.setnchannels(1)
+        handle.setsampwidth(2)
+        handle.setframerate(16_000)
+        handle.writeframes(samples.tobytes())
+    return buffer.getvalue()
+
+
+def _files(*, with_frame: bool = True) -> dict[str, tuple[str, bytes, str]]:
+    files = {"audio": ("a.wav", _tone_wav(), "audio/wav")}
+    if with_frame:
+        files["frame"] = ("frame.jpg", _FRAME, "image/jpeg")
+    return files
+
+
+@pytest.fixture
+async def household(
+    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
+) -> AsyncIterator[PersonalSetupResult]:
+    """A real database with one enrolled owner whose face is consented."""
+    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "generic-continuity.db")
+    monkeypatch.setattr(settings, "face_authentication_enabled", True)
+    monkeypatch.setattr(settings, "speaker_authentication_enabled", True)
+    monkeypatch.setattr(settings, "memory_enabled", True)
+    db._conn = None
+    await db.open_db()
+    await db.run_migrations()
+    result = await apply_personal_setup(
+        PersonalSetupInput(
+            owner_name=_OWNER_NAME, child_names=("Hija Uno", "Hija Dos"), pin=SecretStr(_PIN)
+        )
+    )
+    await grant_face_consent(result.owner_entity_id)
+    await enroll_face(result.owner_entity_id, _OWNER_FACE, label=_OWNER_NAME)
+    yield result
+    await db.close_db()
+    db._conn = None
+
+
+async def _read_person_record(person_entity_id: int) -> PersonRecord | None:
+    label = await get_person_label(entity_id=person_entity_id)
+    if label is None:
+        return None
+    return PersonRecord(
+        person_id=label.entity_id, display_name=label.display_name, entity_type="person"
+    )
+
+
+def _service() -> OwnerUnlockService:
+    registry = IdentitySessionRegistry(
+        lookup_person=lambda _pid: None, clock=lambda: datetime.now(UTC), ttl=timedelta(seconds=60)
+    )
+    return OwnerUnlockService(
+        clock=lambda: datetime.now(UTC),
+        registry=registry,
+        read_credential=get_active_owner_pin_credential,
+        read_role=get_active_role,
+        read_person=_read_person_record,
+    )
+
+
+@asynccontextmanager
+async def _client() -> AsyncIterator[AsyncClient]:
+    async with AsyncClient() as http_client:
+        app.state.resources = AppResources(
+            http_client=http_client, owner_unlock_service=owner_unlock_service
+        )
+        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
+            yield client
+
+
+def _detect(monkeypatch: pytest.MonkeyPatch, *faces: np.ndarray) -> None:
+    monkeypatch.setattr(
+        face_auth_module,
+        "_detect_faces_default",
+        AsyncMock(return_value=[_detected(face) for face in faces]),
+    )
+
+
+def _speak(monkeypatch: pytest.MonkeyPatch, *sentences: str) -> None:
+    """Script what STT hears on each successive request, and silence the TTS."""
+    monkeypatch.setattr(stt, "transcribe", AsyncMock(side_effect=list(sentences)))
+    monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("AAAA", 42)))
+
+
+def _model(monkeypatch: pytest.MonkeyPatch, *replies: str) -> AsyncMock:
+    """Script the classic model's replies; return the mock to read the histories it got."""
+    generate = AsyncMock(side_effect=[(reply, "neutral") for reply in replies])
+    monkeypatch.setattr(llm, "generate_response", generate)
+    return generate
+
+
+def _histories(generate: AsyncMock) -> list[list[str] | None]:
+    return [
+        None if call.kwargs["history"] is None else [t.content for t in call.kwargs["history"]]
+        for call in generate.await_args_list
+    ]
+
+
+@pytest.mark.integration
+async def test_the_owner_face_gives_a_voice_turn_continuity_without_voice_or_grant(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    embed = AsyncMock()
+    monkeypatch.setattr(speaker_auth_module, "embed_wav", embed)
+    _detect(monkeypatch, _OWNER_FACE)
+    _speak(monkeypatch, "Me llamo Canario", "¿Cómo me llamo?")
+    generate = _model(monkeypatch, "Mucho gusto, Canario.", "Te llamas Canario.")
+
+    async with _client() as client:
+        first = await client.post("/transcribe", files=_files())
+        second = await client.post("/transcribe", files=_files())
+
+    assert first.status_code == second.status_code == 200
+    assert _histories(generate) == [
+        [],
+        ["Me llamo Canario", "Mucho gusto, Canario."],
+    ]
+    for body in (first.json(), second.json()):
+        assert body["identity_source"] is None
+        assert body["authentication_consumed"] is False
+    embed.assert_not_awaited()
+
+
+@pytest.mark.integration
+async def test_a_second_face_suspends_the_session_and_the_owner_resumes_it(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    _speak(monkeypatch, "Mi clave es COBALTO", "¿Cuál es la clave?", "¿Cuál era mi clave?")
+    generate = _model(monkeypatch, "Anotado.", "No lo sé.", "COBALTO.")
+
+    async with _client() as client:
+        _detect(monkeypatch, _OWNER_FACE)
+        await client.post("/transcribe", files=_files())
+        _detect(monkeypatch, _OWNER_FACE, _STRANGER_FACE)
+        suspended = await client.post("/transcribe", files=_files())
+        _detect(monkeypatch, _OWNER_FACE)
+        resumed = await client.post("/transcribe", files=_files())
+
+    assert suspended.status_code == resumed.status_code == 200
+    assert _histories(generate) == [
+        [],
+        None,
+        ["Mi clave es COBALTO", "Anotado."],
+    ]
+
+
+@pytest.mark.integration
+async def test_a_turn_without_frame_or_token_is_stateless_and_leaves_the_session(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    _speak(monkeypatch, "Hola", "¿Quién eres?", "Seguimos")
+    generate = _model(monkeypatch, "Hola.", "Soy Iroko.", "Claro.")
+
+    async with _client() as client:
+        _detect(monkeypatch, _OWNER_FACE)
+        await client.post("/transcribe", files=_files())
+        await client.post("/transcribe", files=_files(with_frame=False))
+        await client.post("/transcribe", files=_files())
+
+    assert _histories(generate) == [[], None, ["Hola", "Hola."]]
+
+
+@pytest.mark.integration
+async def test_the_streaming_route_reads_and_writes_the_same_session(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    _detect(monkeypatch, _OWNER_FACE)
+    _speak(monkeypatch, "Me llamo Canario", "¿Cómo me llamo?")
+    seen: list[list[str] | None] = []
+
+    async def stream(*_args: object, **kwargs: object) -> AsyncIterator[str]:
+        history = kwargs["history"]
+        seen.append(None if history is None else [t.content for t in history])  # type: ignore[attr-defined]  # ConversationTurn items
+        yield "Mucho gusto."
+
+    monkeypatch.setattr(llm_streaming, "generate_response_stream", stream)
+
+    async with _client() as client:
+        first = await client.post("/transcribe/stream", files=_files())
+        second = await client.post("/transcribe/stream", files=_files())
+
+    for response in (first, second):
+        events = [json.loads(line) for line in response.text.splitlines() if line]
+        assert events[-1]["type"] == "done"
+        assert events[-1].get("identity_source") is None
+    assert seen == [[], ["Me llamo Canario", "Mucho gusto."]]
+
+
+@pytest.mark.integration
+async def test_a_chat_token_gives_continuity_across_public_conversation_ids_and_is_never_spent(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    service = _service()
+    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
+    unlock = await service.unlock(_PIN)
+    assert unlock is not None
+    headers = {"X-Iroko-Identity-Token": unlock.token}
+    generate = _model(monkeypatch, "Anotado.", "COBALTO.", "Sigo aquí.")
+
+    async with _client() as client:
+        replies = [
+            await client.post(
+                "/chat", headers=headers, json={"message": text, "conversation_id": conversation}
+            )
+            for text, conversation in (
+                ("Mi clave es COBALTO", "web-a"),
+                ("¿Cuál era mi clave?", "web-b"),
+                ("¿Sigues ahí?", "web-c"),
+            )
+        ]
+
+    assert [reply.status_code for reply in replies] == [200, 200, 200]
+    assert [reply.json()["authentication_consumed"] for reply in replies] == [False] * 3
+    assert _histories(generate) == [
+        [],
+        ["Mi clave es COBALTO", "Anotado."],
+        ["Mi clave es COBALTO", "Anotado.", "¿Cuál era mi clave?", "COBALTO."],
+    ]
+
+
+@pytest.mark.integration
+async def test_a_protected_answer_spends_the_token_and_never_enters_the_session(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    service = _service()
+    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
+    first_unlock = await service.unlock(_PIN)
+    assert first_unlock is not None
+    generate = _model(monkeypatch, "Anotado.", "Aquí sigo.", "Bienvenido.")
+
+    async with _client() as client:
+        await client.post(
+            "/chat",
+            headers={"X-Iroko-Identity-Token": first_unlock.token},
+            json={"message": "Mi clave es COBALTO", "conversation_id": "web"},
+        )
+        protected = await client.post(
+            "/chat",
+            headers={"X-Iroko-Identity-Token": first_unlock.token},
+            json={"message": _CHILD_QUESTION, "conversation_id": "web"},
+        )
+        spent = await client.post(
+            "/chat",
+            headers={"X-Iroko-Identity-Token": first_unlock.token},
+            json={"message": "¿Sigues ahí?", "conversation_id": "web"},
+        )
+        second_unlock = await service.unlock(_PIN)
+        assert second_unlock is not None
+        resumed = await client.post(
+            "/chat",
+            headers={"X-Iroko-Identity-Token": second_unlock.token},
+            json={"message": "Ya volví", "conversation_id": "web"},
+        )
+
+    assert protected.json()["authentication_consumed"] is True
+    assert "Hija Uno" in protected.json()["response"]
+    assert spent.status_code == resumed.status_code == 200
+    # The spent token names nobody: that turn suspends. The new unlock resumes the same
+    # session, which holds the first exchange and nothing of the protected answer.
+    assert _histories(generate) == [[], None, ["Mi clave es COBALTO", "Anotado."]]
+
+
+@pytest.mark.integration
+async def test_a_visual_dialogue_turn_neither_reads_nor_writes_the_session(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    """ADR 0020 §1: `/vision/respond` keeps the public unknown, so it leaves the session alone."""
+    monkeypatch.setattr(settings, "vision_enabled", True)
+    _detect(monkeypatch, _OWNER_FACE)
+    _speak(monkeypatch, "Mi clave es COBALTO", "¿Qué decía mi clave?")
+    generate = _model(monkeypatch, "Anotado.", "Hola.", "COBALTO.")
+
+    async with _client() as client:
+        await client.post("/transcribe", files=_files())
+        visual = await client.post(
+            "/vision/respond",
+            files={"image": ("frame.jpg", _FRAME, "image/jpeg")},
+            data={"text": "Hola, Iroko"},
+        )
+        resumed = await client.post("/transcribe", files=_files())
+
+    assert visual.status_code == resumed.status_code == 200
+    # The visual turn received no history and wrote nothing: the owner's next turn still finds
+    # exactly the first exchange, not the visual one.
+    assert _histories(generate) == [[], None, ["Mi clave es COBALTO", "Anotado."]]
diff --git a/tests/integration/test_transcribe_pipeline.py b/tests/integration/test_transcribe_pipeline.py
--- a/tests/integration/test_transcribe_pipeline.py
+++ b/tests/integration/test_transcribe_pipeline.py
@@ -331,8 +331,10 @@ def test_transcribe_uses_distinct_internal_scopes_per_request(
         conversation_id: str,
         *,
         schedule_consolidation: ConsolidationScheduler,
+        active_person: object = None,
+        suspend_cause: object = None,
     ) -> TextTurnResult:
-        _ = client, schedule_consolidation
+        _ = client, schedule_consolidation, active_person, suspend_cause
         return TextTurnResult("shared reply", "joy", 7, False)

     process = AsyncMock(side_effect=process_turn)
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/integration/test_generic_turn_continuity.py -q -p no:cacheprovider -p no:xdist`
  Expected RED: seven failures such as `assert [None, None] == [[], [...]]` (every turn is still
  stateless).
- [ ] **Step 3: Implement.**

```diff
diff --git a/server/src/server/routers/chat.py b/server/src/server/routers/chat.py
--- a/server/src/server/routers/chat.py
+++ b/server/src/server/routers/chat.py
@@ -8,6 +8,7 @@ from fastapi import APIRouter
 from server import turn_log
 from server.cognition.authorization import evaluate_authorization
 from server.cognition.controller import CognitiveController
+from server.cognition.generic_identity import identify_generic_speaker
 from server.cognition.household_tools import HouseholdKnowledgeTools
 from server.cognition.identity import ActivePersonContext
 from server.cognition.models import CognitiveEvent
@@ -72,6 +73,7 @@ async def chat(
         whether this turn consumed a fresh owner unlock grant.
     """
     request_identity = owner_unlock_service.for_request(x_iroko_identity_token)
+    event = _event_from_request(request)

     async def resolve_actor(event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
         actor = await request_identity.resolve_actor(event)
@@ -85,8 +87,22 @@ async def chat(
         return actor

     async def legacy_turn(message: str, conversation_id: str) -> TextTurnResult:
-        """Delegate to text-turn orchestration with the shared HTTP client."""
-        return await process_text_turn(resources.http_client, message, conversation_id)
+        """Name the speaker (observing the token, never spending it), then converse."""
+        speaker = await identify_generic_speaker(
+            owner_unlock_service.for_request,
+            token=x_iroko_identity_token,
+            frame=None,
+            event=event,
+        )
+        if speaker.actor is not None:
+            turn_log.log_actor("chat", speaker.actor)
+        return await process_text_turn(
+            resources.http_client,
+            message,
+            conversation_id,
+            active_person=speaker.actor,
+            suspend_cause=speaker.cause,
+        )

     controller = CognitiveController(
         today=_today,
@@ -98,7 +114,6 @@ async def chat(
         household_tools=HouseholdKnowledgeTools(reader=PolicyGatedV4Reader()),
         consent_resolver=request_identity.resolve_consent,
     )
-    event = _event_from_request(request)
     decision = await controller.decide(event)
     # Chat has no camera round-trip at all — a scene request always gets the
     # fixed unavailable plan.
diff --git a/server/src/server/routers/transcribe.py b/server/src/server/routers/transcribe.py
--- a/server/src/server/routers/transcribe.py
+++ b/server/src/server/routers/transcribe.py
@@ -3,8 +3,10 @@
 Audio contract: WAV · 16000 Hz · mono · int16.
 """

+from collections.abc import Awaitable, Callable
 from dataclasses import dataclass
 from datetime import UTC, date, datetime
+from functools import partial
 import logging
 import time
 from typing import Annotated
@@ -18,6 +20,10 @@ from server import turn_log
 from server.audio_contract import validate_wav_contract
 from server.cognition.authorization import evaluate_authorization
 from server.cognition.controller import ActivePersonResolver, CognitiveController, ConsentResolver
+from server.cognition.generic_identity import (
+    GenericIdentification,
+    identify_generic_speaker,
+)
 from server.cognition.household_tools import HouseholdKnowledgeTools
 from server.cognition.identity import ActivePersonContext
 from server.cognition.identity_fusion import FusedIdentityResolver, build_fused_identity_resolver
@@ -61,6 +67,8 @@ logger = logging.getLogger(__name__)

 router = APIRouter(prefix="/transcribe", tags=["Audio"])

+type SpeakerIdentifier = Callable[[], Awaitable[GenericIdentification]]
+

 class NDJSONStreamingResponse(StreamingResponse):
     """A streaming response whose media type is `application/x-ndjson`.
@@ -210,6 +218,7 @@ def _voice_controller(
     background_tasks: BackgroundTasks,
     *,
     request_identity: _RequestIdentity | None = None,
+    identify_speaker: SpeakerIdentifier | None = None,
 ) -> CognitiveController:
     """Compose the bounded controller used by a public voice turn.

@@ -220,14 +229,25 @@ def _voice_controller(
         request_identity: Optional request-scoped actor/consent resolver over
             the fused face, voice and PIN evidence (Plan 0054). When omitted,
             the controller falls back to its own public-unknown defaults.
+        identify_speaker: Names the speaker of a generic turn from the face and an
+            observed token (Plan 0061, ADR 0020); when omitted the speaker is unknown.
     """

     async def legacy_turn(message: str, conversation_id: str) -> TextTurnResult:
-        """Delegate generic public conversation through the existing text service."""
+        """Name the speaker, then converse through the existing text service."""
+        speaker = (
+            await identify_speaker()
+            if identify_speaker is not None
+            else GenericIdentification(actor=None, cause=None)
+        )
+        if speaker.actor is not None:
+            turn_log.log_actor("voice", speaker.actor)
         return await process_text_turn(
             client,
             message,
             conversation_id,
+            active_person=speaker.actor,
+            suspend_cause=speaker.cause,
             schedule_consolidation=_consolidation_scheduler(client, background_tasks),
         )

@@ -359,7 +379,16 @@ async def transcribe(

     event = _voice_event_from_transcript(text_heard)
     controller = _voice_controller(
-        resources.http_client, background_tasks, request_identity=request_identity
+        resources.http_client,
+        background_tasks,
+        request_identity=request_identity,
+        identify_speaker=partial(
+            identify_generic_speaker,
+            owner_unlock_service.for_request,
+            token=x_iroko_identity_token,
+            frame=frame_bytes,
+            event=event,
+        ),
     )
     decision = await controller.decide(event)

@@ -505,10 +534,20 @@ async def transcribe_stream(
             )
         )

+    speaker = await identify_generic_speaker(
+        owner_unlock_service.for_request,
+        token=x_iroko_identity_token,
+        frame=frame_bytes,
+        event=event,
+    )
+    if speaker.actor is not None:
+        turn_log.log_actor("voice", speaker.actor)
     prepared = await prepare_text_turn(
         resources.http_client,
         event.payload.message,
         event.payload.conversation_id,
+        active_person=speaker.actor,
+        suspend_cause=speaker.cause,
     )

     return NDJSONStreamingResponse(
```

- [ ] **Step 4: Run, mutate, lint, commit.** The new file passes (7), then the whole suite.
  **Mutation** (the visual test): in `prepare_text_turn` make the person id
  `7 if message.startswith("Hola, Iroko") else _continuity_person_id(resolved_person)`; only
  `test_a_visual_dialogue_turn_neither_reads_nor_writes_the_session` fails. Revert it.
  `ruff check`/`format --check`, `mypy`; commit
  `feat(server): identify the speaker of generic turns (plan 0061)`.

---

## Task 5: One sentence of the prompt

**Files:**
- Modify: `server/src/server/characters/__init__.py`
- Test: new `tests/unit/test_memory_discipline.py`

- [ ] **Step 1: Write the failing tests.**

```diff
diff --git a/tests/unit/test_memory_discipline.py b/tests/unit/test_memory_discipline.py
new file mode 100644
--- /dev/null
+++ b/tests/unit/test_memory_discipline.py
@@ -0,0 +1,60 @@
+"""The memory-discipline block of the system prompt (Plan 0061, ADR 0020 §7).
+
+The block keeps small models from inventing facts. With short-term continuity it must also
+let them rely on what the person said earlier in the same conversation, and it must not carry
+the speaker's identity.
+"""
+
+from datetime import UTC, datetime
+
+import pytest
+from server.characters import _MEMORY_DISCIPLINE, build_system_prompt, get_character
+from server.cognition.identity import (
+    ActivePersonContext,
+    ActivePersonStatus,
+    HouseholdRole,
+    IdentityAssurance,
+)
+from server.cognition.models import Confidence, ConfidenceBasis
+
+pytestmark = pytest.mark.unit
+
+_SPEAKER_NAME = "Canary"
+
+
+def _identified(person_id: int = 7) -> ActivePersonContext:
+    return ActivePersonContext(
+        person_id=person_id,
+        display_name=_SPEAKER_NAME,
+        status=ActivePersonStatus.IDENTIFIED,
+        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=True),
+        role=HouseholdRole.OWNER,
+        evidence=(),
+        resolved_at=datetime(2026, 10, 13, tzinfo=UTC),
+        assurance=IdentityAssurance.BASIC,
+    )
+
+
+def test_the_conversation_counts_as_a_source_of_truth() -> None:
+    assert "earlier in this same conversation" in _MEMORY_DISCIPLINE
+    assert "ONLY sources" in _MEMORY_DISCIPLINE
+
+
+def test_the_admission_rule_names_both_sources_and_still_forbids_inventing() -> None:
+    assert "NOT present in those sources" in _MEMORY_DISCIPLINE
+    assert "NEVER invent or guess" in _MEMORY_DISCIPLINE
+
+
+def test_the_block_is_always_in_the_system_prompt() -> None:
+    prompt = build_system_prompt(get_character("iroko"), None)
+
+    assert _MEMORY_DISCIPLINE in prompt
+
+
+def test_the_speakers_identity_never_enters_the_system_prompt() -> None:
+    profile = get_character("iroko")
+
+    identified = build_system_prompt(profile, None, active_person=_identified())
+
+    assert _SPEAKER_NAME not in identified
+    assert identified == build_system_prompt(profile, None)
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_memory_discipline.py -q -p no:cacheprovider`
  Expected RED: two failures, `assert 'earlier in this same conversation' in ...` and
  `assert 'NOT present in those sources' in ...` (the other two pass: they pin what must not move).
- [ ] **Step 3: Implement.**

```diff
diff --git a/server/src/server/characters/__init__.py b/server/src/server/characters/__init__.py
--- a/server/src/server/characters/__init__.py
+++ b/server/src/server/characters/__init__.py
@@ -75,11 +75,15 @@ _PROFILES_DIR = Path(__file__).parent / "profiles"
 # Anti-confabulation: small models fill memory gaps with invented names said
 # with full confidence, which then get re-consolidated as facts (observed live
 # 2026-07-06). This block is always present, with or without active memory.
+# The same conversation counts as a source because an identified person has
+# short-term continuity (ADR 0020): without it the model answered "I don't
+# remember" to something said a minute earlier.
 _MEMORY_DISCIPLINE = """
 MEMORY DISCIPLINE — non-negotiable:
-- The authorized memory block appended below (when present) is your ONLY source of \
-truth about people, family, pets, dates, and preferences.
-- If asked about something NOT present in that memory, admit you don't \
+- The authorized memory block appended below (when present) and what the person \
+said earlier in this same conversation are your ONLY sources of truth about \
+people, family, pets, dates, and preferences.
+- If asked about something NOT present in those sources, admit you don't \
 remember it yet and ask them to tell you — NEVER invent or guess names, \
 ages, or facts. A wrong confident answer poisons your own memory."""

```

- [ ] **Step 4: Run, lint, commit.** `uv run pytest tests/unit/test_memory_discipline.py
  tests/unit/test_llm_generate.py tests/unit/test_llm_streaming.py tests/unit/test_character_parser.py
  -q -p no:cacheprovider` (50 passed); `ruff`; commit
  `feat(server): let the prompt rely on the same conversation (plan 0061)`.

---

## Task 6: Measure history-bearing streams and the reply language

**Files:**
- Create: `scripts/reply_language.py`
- Modify: `scripts/eval_stream_protocol.py`, `scripts/eval_chat.py`
- Test: new `tests/unit/test_reply_language.py`; modified `tests/unit/test_eval_stream_protocol.py`

**Interfaces:**
- Produces: `judge_language(text) -> bool | None` (`True` Spanish, `False` not, `None` too short or
  a tie; a word two of the three languages share is in no list, and five French sentences that
  borrow `que`, `tu`, `te`, `un`, `y` or `se` are pinned as not Spanish); `history_turns() -> list[StreamTurn]` (12, source `history`); `StreamProtocolResult.not_spanish`
  and `.language_judged`; a report line and a column with the counts. No exit-code rule is added:
  Pipec reads the `history` row (D-9).

- [ ] **Step 1: Write the failing tests.**

```diff
diff --git a/tests/unit/test_eval_stream_protocol.py b/tests/unit/test_eval_stream_protocol.py
--- a/tests/unit/test_eval_stream_protocol.py
+++ b/tests/unit/test_eval_stream_protocol.py
@@ -19,6 +19,7 @@ from scripts.eval_stream_protocol import (
     StreamTurn,
     _StreamClassifier,
     classify_deltas,
+    history_turns,
     measure_stream_protocol,
     public_turns,
     render_stream_report,
@@ -291,6 +292,57 @@ def test_public_turns_are_synthetic_and_context_free() -> None:
     assert any("Tom" in t.text for t in turns)


+@pytest.mark.unit
+def test_history_turns_are_synthetic_dialogues_that_depend_on_their_history() -> None:
+    """ADR 0020 §7: the measurement needs turns that carry a conversation in the prompt."""
+    turns = history_turns()
+
+    assert len(turns) == 12
+    assert len({turn.label for turn in turns}) == 12
+    for turn in turns:
+        assert turn.source == "history"
+        assert turn.context is None
+        assert turn.active_person is None
+        assert turn.history
+        roles = [item.role for item in turn.history]
+        assert roles == ["user", "assistant"] * (len(roles) // 2)
+
+
+@pytest.mark.unit
+async def test_measure_counts_replies_that_are_not_spanish_and_skips_the_undetermined() -> None:
+    spanish = "Claro, tu número favorito es el cuarenta y dos."
+    english = "Of course, your favorite number is forty-two and I am happy to help you."
+    result = await measure_stream_protocol(
+        [_turn("history"), _turn("history"), _turn("history"), _turn("history")],
+        client=_client(),
+        runs=1,
+        generate=_generator([spanish, english, "Hola.", '{"x": 1}']),
+    )
+
+    assert result.language_judged == 2  # the short reply is undetermined, the invalid one skipped
+    assert result.not_spanish == 1
+    assert result.by_source["history"].language_judged == 2
+    assert result.by_source["history"].not_spanish == 1
+
+
+@pytest.mark.unit
+def test_the_report_counts_replies_not_in_spanish_and_never_prints_them() -> None:
+    result = StreamProtocolResult(
+        valid=60,
+        invalid_protocol=0,
+        empty_stream=0,
+        errors=0,
+        by_source={},
+        not_spanish=2,
+        language_judged=58,
+    )
+
+    report = render_stream_report(result, model="qwen2.5:3b", runs=5)
+
+    assert "not in Spanish" in report
+    assert "2 of 58" in report
+
+
 @pytest.mark.unit
 def test_exit_code_applies_the_threshold_and_provider_errors() -> None:
     clean = StreamProtocolResult(
diff --git a/tests/unit/test_reply_language.py b/tests/unit/test_reply_language.py
new file mode 100644
--- /dev/null
+++ b/tests/unit/test_reply_language.py
@@ -0,0 +1,50 @@
+"""Unit tests for the cheap Spanish check used by the streaming evaluator (Plan 0061)."""
+
+import pytest
+
+from scripts.reply_language import judge_language
+
+pytestmark = pytest.mark.unit
+
+
+@pytest.mark.parametrize(
+    "reply",
+    [
+        "Claro, tu número favorito es el cuarenta y dos.",
+        "No lo recuerdo todavía, ¿me lo puedes decir otra vez?",
+        "Dijiste que ibas a cocinar lentejas esta noche, ¡qué buena idea!",
+        "Estoy aquí para ayudarte con lo que necesites.",
+        "Sé que tú quieres que te cuente un secreto y se lo diré mañana.",
+        "Dijiste que te gustaba el té sin azúcar y que tu café es muy amargo.",
+    ],
+)
+def test_a_spanish_reply_is_judged_spanish(reply: str) -> None:
+    assert judge_language(reply) is True
+
+
+@pytest.mark.parametrize(
+    "reply",
+    [
+        "Bien sûr, votre nombre préféré est le quarante-deux et je vous le dis avec plaisir.",
+        "Je suis ici pour vous aider avec ce dont vous avez besoin aujourd'hui.",
+        "Of course, your favorite number is forty-two and I am happy to help you with that.",
+        "I do not remember that yet, could you tell me again what you said?",
+        # French sentences that borrow function words Spanish also has (que, tu, te, un, y, se):
+        "Tu m'as dit que tu aimais le thé sans sucre.",
+        "Il y a un problème, mais je vais y réfléchir.",
+        "Tu veux que je te dise un secret ?",
+        "Tu as dit que ton numéro favori est 42.",
+        "Tu as un rendez-vous demain à neuf heures, je crois.",
+    ],
+)
+def test_a_french_or_english_reply_is_judged_not_spanish(reply: str) -> None:
+    assert judge_language(reply) is False
+
+
+@pytest.mark.parametrize("reply", ["", "   ", "Hola.", "Sí, claro.", "¡Gracias!"])
+def test_a_reply_too_short_to_judge_is_undetermined(reply: str) -> None:
+    assert judge_language(reply) is None
+
+
+def test_the_verdict_ignores_case_and_punctuation() -> None:
+    assert judge_language("CLARO, TU NÚMERO FAVORITO ES EL CUARENTA Y DOS!!!") is True
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_reply_language.py tests/unit/test_eval_stream_protocol.py -q
  -p no:cacheprovider` Expected RED: `ModuleNotFoundError: No module named
  'scripts.reply_language'` and `ImportError: cannot import name 'history_turns'`.
- [ ] **Step 3: Implement.**

```diff
diff --git a/scripts/eval_chat.py b/scripts/eval_chat.py
--- a/scripts/eval_chat.py
+++ b/scripts/eval_chat.py
@@ -50,6 +50,7 @@ import yaml

 from scripts.eval_stream_protocol import (
     StreamTurn,
+    history_turns,
     measure_stream_protocol,
     public_turns,
     render_stream_report,
@@ -652,10 +653,12 @@ def golden_stream_turns(cases: Sequence[GoldenCase]) -> list[StreamTurn]:
 async def _run_stream_mode(
     options: CliOptions, cases: list[GoldenCase], factory: ClientFactory
 ) -> int:
-    """Measure the streaming protocol on the golden context turns plus public turns."""
+    """Measure the streaming protocol on the golden context, public and history turns."""
     async with factory() as client:
         result = await measure_stream_protocol(
-            [*golden_stream_turns(cases), *public_turns()], client=client, runs=options.runs
+            [*golden_stream_turns(cases), *public_turns(), *history_turns()],
+            client=client,
+            runs=options.runs,
         )
     stamp = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")
     output = options.output or _REPORT_DIRECTORY / f"{stamp}-chat-stream-ollama.md"
diff --git a/scripts/eval_stream_protocol.py b/scripts/eval_stream_protocol.py
--- a/scripts/eval_stream_protocol.py
+++ b/scripts/eval_stream_protocol.py
@@ -17,6 +17,7 @@ import logging
 from typing import TYPE_CHECKING

 from server.llm import FALLBACK_EMOTION
+from server.schemas import ConversationTurn
 from server.streaming_protocol import StreamProtocolError
 from server.streaming_render import (
     StreamFallbackReason,
@@ -25,6 +26,7 @@ from server.streaming_render import (
     classify_stream_end,
 )

+from scripts.reply_language import judge_language
 from server import llm_streaming

 if TYPE_CHECKING:
@@ -32,14 +34,14 @@ if TYPE_CHECKING:

     import httpx
     from server.cognition.identity import ActivePersonContext
-    from server.schemas import ConversationTurn, MemoryContext
+    from server.schemas import MemoryContext

     type StreamGenerator = Callable[..., AsyncIterator[str]]

 logger = logging.getLogger(__name__)

 _PERCENT = 100
-_SOURCES = ("context", "public")
+_SOURCES = ("context", "public", "history")
 _PUBLIC_UTTERANCES = (
     "Hola, ¿cómo estás?",
     "Te presento a mi amigo Tom.",
@@ -56,6 +58,93 @@ _PUBLIC_UTTERANCES = (
 )


+# Invented one-line facts followed by a question that only the history answers (ADR 0020
+# §7). Each entry is (labelled exchanges, question): no household data of any kind.
+_HISTORY_DIALOGUES: tuple[tuple[tuple[tuple[str, str], ...], str], ...] = (
+    (
+        (("Mi número favorito es el 42.", "Anotado: tu número favorito es el 42."),),
+        "¿Cuál es mi número favorito?",
+    ),
+    (
+        (
+            (
+                "Esta noche voy a cocinar lentejas.",
+                "¡Qué buena idea! Las lentejas son muy reconfortantes.",
+            ),
+        ),
+        "¿Qué te dije que iba a cocinar?",
+    ),
+    (
+        (
+            (
+                "Tengo una reunión mañana a las nueve.",
+                "Entendido, mañana a las nueve tienes una reunión.",
+            ),
+        ),
+        "¿A qué hora es mi reunión?",
+    ),
+    (
+        (
+            (
+                "Estoy aprendiendo a tocar la guitarra.",
+                "¡Qué genial! La guitarra es un instrumento hermoso.",
+            ),
+        ),
+        "¿Qué instrumento estoy aprendiendo?",
+    ),
+    (
+        (
+            (
+                "Compré una planta nueva para la sala.",
+                "Qué lindo, una planta alegra cualquier sala.",
+            ),
+        ),
+        "¿Dónde puse la planta?",
+    ),
+    (
+        (("Mañana voy a viajar a la playa.", "¡Qué bien! Disfruta mucho de la playa."),),
+        "¿A dónde voy a viajar mañana?",
+    ),
+    (
+        (
+            (
+                "El código de mi bicicleta es Zorro.",
+                "Entendido, el código de tu bicicleta es Zorro.",
+            ),
+        ),
+        "¿Cuál era el código de mi bicicleta?",
+    ),
+    (
+        (
+            (
+                "Hoy me levanté muy temprano.",
+                "Madrugar a veces cuesta, pero rinde mucho.",
+            ),
+        ),
+        "¿Qué te conté sobre mi mañana?",
+    ),
+    (
+        (
+            ("Quiero aprender ajedrez.", "Es un juego excelente para entrenar la mente."),
+            ("Empezaré con las aperturas.", "Buena idea, las aperturas son la base."),
+        ),
+        "¿Qué quiero aprender y por dónde voy a empezar?",
+    ),
+    (
+        (("Mi tortuga se llama Cobalto.", "Qué nombre tan original para una tortuga."),),
+        "¿Cómo se llama mi tortuga?",
+    ),
+    (
+        (("Prefiero el té sin azúcar.", "Anotado, té sin azúcar."),),
+        "¿Cómo prefiero el té?",
+    ),
+    (
+        (("Mañana es mi día libre.", "¡Qué bien, aprovéchalo!"),),
+        "¿Qué te dije sobre mañana?",
+    ),
+)
+
+
 class StreamOutcome(enum.StrEnum):
     """How one streamed reply ends; the fallback reasons mirror production's."""

@@ -81,6 +170,7 @@ class _StreamClassifier:
     def __init__(self) -> None:
         self._state = StreamState(request_start=0.0, pending_emotion=FALLBACK_EMOTION)
         self._buffer = ""
+        self._spoken: list[str] = []
         self.sentences_seen = 0

     def feed(self, delta: str) -> StreamOutcome | None:
@@ -94,6 +184,7 @@ class _StreamClassifier:
             self._buffer, sentences = _consume_body(self._buffer, self._state)
         except StreamProtocolError:
             return StreamOutcome.INVALID_PROTOCOL
+        self._spoken.extend(sentences)
         self.sentences_seen += len(sentences)
         return None

@@ -101,6 +192,10 @@ class _StreamClassifier:
         """Decide the outcome once the stream has ended without an earlier decision."""
         return _classify_end_of_stream(self._buffer, self._state)

+    def reply_text(self) -> str:
+        """Return what production would have spoken, to be judged and then dropped."""
+        return " ".join([*self._spoken, self._buffer]).strip()
+

 def classify_deltas(deltas: Iterable[str]) -> StreamOutcome:
     """Classify one streamed reply the way production consumes it.
@@ -136,6 +231,25 @@ class StreamTurn:
             raise ValueError(f"source must be one of {_SOURCES}, got {self.source!r}")


+def history_turns() -> list[StreamTurn]:
+    """Return synthetic dialogues whose question depends on the history (ADR 0020 §7)."""
+    return [
+        StreamTurn(
+            f"history_{index}",
+            "history",
+            question,
+            None,
+            [
+                ConversationTurn(role=role, content=content)
+                for user, assistant in exchanges
+                for role, content in (("user", user), ("assistant", assistant))
+            ],
+            None,
+        )
+        for index, (exchanges, question) in enumerate(_HISTORY_DIALOGUES, start=1)
+    ]
+
+
 def public_turns() -> list[StreamTurn]:
     """Return the synthetic, context-free chit-chat turns (public-channel shape)."""
     return [
@@ -153,6 +267,8 @@ class StreamProtocolResult:
     empty_stream: int
     errors: int
     by_source: dict[str, StreamProtocolResult] = field(default_factory=dict)
+    not_spanish: int = 0
+    language_judged: int = 0

     @classmethod
     def none(cls) -> StreamProtocolResult:
@@ -172,22 +288,30 @@ class StreamProtocolResult:
         return (self.invalid_protocol + self.empty_stream) / self.graded


-def _tally(outcomes: Sequence[StreamOutcome]) -> StreamProtocolResult:
+def _tally(
+    observations: Sequence[tuple[StreamOutcome, bool | None]],
+) -> StreamProtocolResult:
+    outcomes = [outcome for outcome, _ in observations]
+    languages = [spanish for _, spanish in observations if spanish is not None]
     return StreamProtocolResult(
         valid=outcomes.count(StreamOutcome.VALID),
         invalid_protocol=outcomes.count(StreamOutcome.INVALID_PROTOCOL),
         empty_stream=outcomes.count(StreamOutcome.EMPTY_STREAM),
         errors=outcomes.count(StreamOutcome.ERROR),
+        not_spanish=languages.count(False),
+        language_judged=len(languages),
     )


 async def _stream_once(
     turn: StreamTurn, client: httpx.AsyncClient, generate: StreamGenerator
-) -> StreamOutcome:
+) -> tuple[StreamOutcome, bool | None]:
     """Classify one live stream while it arrives and stop when production would stop.

     A provider error that comes after production has already decided (an invalid body
     start) never happens live, so it must not turn that observation into an ``ERROR``.
+    The second item is the language verdict of a reply that would be spoken
+    (``None`` for anything else, or when the reply is too short to judge).
     """
     classifier = _StreamClassifier()
     stream = generate(
@@ -203,17 +327,20 @@ async def _stream_once(
                 continue
             decided = classifier.feed(delta)
             if decided is not None:
-                return decided
+                return decided, None
     except Exception as exc:
         logger.warning("Provider call failed for %s (%s)", turn.label, type(exc).__name__)
-        return StreamOutcome.ERROR
+        return StreamOutcome.ERROR, None
     finally:
         # Stop the model generating: an abandoned async generator would keep the HTTP
         # stream (and Ollama) running until it is garbage collected.
         aclose = getattr(stream, "aclose", None)
         if aclose is not None:
             await aclose()
-    return classifier.finish()
+    outcome = classifier.finish()
+    if outcome is not StreamOutcome.VALID:
+        return outcome, None
+    return outcome, judge_language(classifier.reply_text())


 async def measure_stream_protocol(
@@ -235,20 +362,22 @@ async def measure_stream_protocol(
         Overall and per-source counts. Provider errors are counted separately and
         never as a protocol failure or a pass.
     """
-    outcomes: list[StreamOutcome] = []
-    by_source: dict[str, list[StreamOutcome]] = {}
+    observations: list[tuple[StreamOutcome, bool | None]] = []
+    by_source: dict[str, list[tuple[StreamOutcome, bool | None]]] = {}
     for turn in turns:
         for _ in range(runs):
-            outcome = await _stream_once(turn, client, generate)
-            outcomes.append(outcome)
-            by_source.setdefault(turn.source, []).append(outcome)
-    overall = _tally(outcomes)
+            observation = await _stream_once(turn, client, generate)
+            observations.append(observation)
+            by_source.setdefault(turn.source, []).append(observation)
+    overall = _tally(observations)
     return StreamProtocolResult(
         overall.valid,
         overall.invalid_protocol,
         overall.empty_stream,
         overall.errors,
         {source: _tally(items) for source, items in by_source.items()},
+        overall.not_spanish,
+        overall.language_judged,
     )


@@ -259,20 +388,24 @@ def _percent(rate: float | None) -> str:
 def render_stream_report(result: StreamProtocolResult, *, model: str, runs: int) -> str:
     """Render the measurement as Markdown: counts and rates only, never model output."""
     rows = [
-        "| Set | Valid | Invalid protocol | Empty stream | Provider errors | Fallback rate |",
-        "|---|---:|---:|---:|---:|---:|",
+        "| Set | Valid | Invalid protocol | Empty stream | Provider errors | Fallback rate "
+        "| Not in Spanish |",
+        "|---|---:|---:|---:|---:|---:|---:|",
     ]
     for label, part in (("all", result), *sorted(result.by_source.items())):
         rows.append(
             f"| {label} | {part.valid} | {part.invalid_protocol} | {part.empty_stream} | "
-            f"{part.errors} | {_percent(part.fallback_rate)} |"
+            f"{part.errors} | {_percent(part.fallback_rate)} | "
+            f"{part.not_spanish} of {part.language_judged} |"
         )
     return (
         "# Streaming protocol measurement\n\n"
         f"- model: {model}\n- runs per turn: {runs}\n"
         f"- graded observations: {result.graded}\n"
         f"- fallback rate (invalid protocol + empty stream, over graded): "
-        f"{_percent(result.fallback_rate)}\n\n" + "\n".join(rows) + "\n"
+        f"{_percent(result.fallback_rate)}\n"
+        f"- replies not in Spanish (word-list heuristic, replies it could judge): "
+        f"{result.not_spanish} of {result.language_judged}\n\n" + "\n".join(rows) + "\n"
     )


diff --git a/scripts/reply_language.py b/scripts/reply_language.py
new file mode 100644
--- /dev/null
+++ b/scripts/reply_language.py
@@ -0,0 +1,76 @@
+"""A cheap, deterministic "is this reply Spanish?" check for the streaming evaluator.
+
+Plan 0059 saw one reply in French although the transcript was Spanish and no contract asked
+for Spanish. The measurement needs a count, not a classifier: this compares how many tokens of
+a reply are very frequent Spanish words against French and English ones. It is a heuristic with
+a documented limit (a reply made only of proper nouns or numbers, or one that is too short, is
+*undetermined*, never a verdict), and it never stores or prints the reply.
+"""
+
+from __future__ import annotations
+
+import re
+
+_MIN_TOKENS = 4
+_TOKEN = re.compile(r"[^\W\d_]+")
+
+# Frequent words that belong to ONE of the three languages. A word that two of them share is
+# left out of every list, so a hit is evidence for one language only: `que`, `tu`, `te`, `un`,
+# `y`, `se`, `son`, `es`, `bien`, `he`, `has`, `me`, `no`, `de`, `la`, `en`, `a` are all absent
+# on purpose. A French sentence full of those words must not be counted as Spanish.
+_SPANISH = frozenset(
+    {
+        "el", "los", "las", "una", "unos", "unas", "del", "al", "lo", "mi", "mis", "su", "sus",
+        "muy", "más", "pero", "porque", "con", "para", "por", "está", "están", "estoy", "estás",
+        "soy", "eres", "somos", "hay", "ser", "tengo", "tienes", "tiene", "quiero", "quieres",
+        "puedo", "puedes", "dijiste", "dije", "cuando", "donde", "dónde", "cómo", "qué", "cuál",
+        "cuáles", "cuándo", "algo", "nada", "todo", "siempre", "nunca", "mucho", "poco",
+        "también", "aquí", "ahora", "todavía", "otra", "vez", "decir", "claro", "gracias",
+        "hola", "sí", "necesites", "buena", "idea", "ayudarte", "favorito", "número", "mañana",
+        "noche", "hoy", "ayer", "casa", "recuerdo", "dime", "sabes", "gusta",
+    }
+)  # fmt: skip
+_FRENCH = frozenset(
+    {
+        "le", "les", "des", "une", "est", "sont", "et", "je", "vous", "nous", "ils", "elle",
+        "pas", "pour", "avec", "dans", "sur", "votre", "vos", "mon", "ma", "mes", "ce", "cette",
+        "ces", "qui", "quoi", "très", "plus", "sûr", "suis", "ici", "aider", "dit", "dis",
+        "dites", "besoin", "avez", "ai", "merci", "bonjour", "oui", "aussi", "mais", "ne", "du",
+        "au", "aux", "veux", "veut", "peux", "peut", "fait", "ton", "ta", "tes", "as", "aimais",
+        "aime", "sucre", "rendez", "demain", "heures", "neuf", "problème", "réfléchir", "j",
+        "qu", "c", "l", "puis", "alors", "voudrais", "comprends", "souviens",
+    }
+)  # fmt: skip
+_ENGLISH = frozenset(
+    {
+        "the", "and", "is", "are", "you", "your", "i", "am", "with", "this", "that", "what",
+        "for", "it", "of", "to", "in", "do", "not", "could", "would", "help", "tell", "again",
+        "yet", "remember", "course", "happy", "number", "favorite", "said", "have", "can", "she",
+        "we", "they", "them", "was", "were", "will", "be", "been", "there", "here", "where",
+        "when", "who", "how", "my", "its", "an", "or", "but", "if", "so", "because", "about",
+    }
+)  # fmt: skip
+
+
+def judge_language(text: str) -> bool | None:
+    """Judge whether a reply is written in Spanish.
+
+    Args:
+        text: The reply, as spoken.
+
+    Returns:
+        ``True`` when Spanish words clearly outnumber French and English ones, ``False`` when
+        another language does, and ``None`` when the reply is too short to say (fewer than four
+        words) or the evidence is a tie.
+    """
+    tokens = _TOKEN.findall(text.lower())
+    if len(tokens) < _MIN_TOKENS:
+        return None
+    spanish = sum(token in _SPANISH for token in tokens)
+    other = max(
+        sum(token in _FRENCH for token in tokens),
+        sum(token in _ENGLISH for token in tokens),
+    )
+    if spanish == other:
+        return None
+    return spanish > other
```

- [ ] **Step 4: Run, lint, commit.** `uv run pytest tests/unit/test_reply_language.py
  tests/unit/test_eval_stream_protocol.py tests/unit/test_eval_chat.py
  tests/unit/test_diagnose_stream_protocol.py -q -p no:cacheprovider` (135 passed). Lint the
  **explicit script paths** (`ruff` excludes `scripts/` in `just lint` but the pre-commit hook lints
  them): `uv run ruff check scripts/reply_language.py scripts/eval_stream_protocol.py
  scripts/eval_chat.py` and `format --check`; commit
  `feat(eval): measure history streams and reply language (plan 0061)`.

---

## Task 7: Guards and the no-token scenario

**Files:**
- Test: `tests/unit/test_architecture_guards.py`, `tests/integration/test_owner_stranger_matrix.py`

- [ ] **Step 1: Add the guards and the scenario.** Green on arrival by design:

```diff
diff --git a/tests/integration/test_owner_stranger_matrix.py b/tests/integration/test_owner_stranger_matrix.py
--- a/tests/integration/test_owner_stranger_matrix.py
+++ b/tests/integration/test_owner_stranger_matrix.py
@@ -383,3 +383,32 @@ async def test_an_administration_grant_is_one_use_even_after_a_refused_read(
     second = await voice.revoke_face(unlock.token)

     assert (first, second) == (204, 401)
+
+
+@pytest.mark.integration
+async def test_what_the_owner_said_is_never_given_to_a_turn_with_no_token(
+    voice: _Voice, llm_calls: list[dict[str, object]]
+) -> None:
+    """ADR 0020: the owner's short-term conversation answers the owner and nobody else.
+
+    The next speaker presents nothing, so they are the public unknown: the model receives no
+    history, and the owner's words cannot be quoted back. The owner, presenting the same
+    token (observed, never spent), picks the conversation up again.
+    """
+    unlock = await voice.service.unlock(_PIN)
+    assert unlock is not None
+
+    await voice.speak("Mi clave temporal es zqx-session-5", token=unlock.token)
+    stranger = await voice.speak("¿Qué dijo la persona anterior?")
+    await voice.speak("¿Qué te dije antes?", token=unlock.token)
+
+    assert len(llm_calls) == 3
+    assert llm_calls[0]["history"] == []
+    assert llm_calls[1]["history"] is None
+    assert "zqx-session-5" not in str(stranger["llm_response"])
+    resumed = llm_calls[2]["history"]
+    assert resumed is not None
+    assert [turn.content for turn in resumed] == [  # type: ignore[attr-defined]  # ConversationTurn items
+        "Mi clave temporal es zqx-session-5",
+        _LLM_REPLY,
+    ]
diff --git a/tests/unit/test_architecture_guards.py b/tests/unit/test_architecture_guards.py
--- a/tests/unit/test_architecture_guards.py
+++ b/tests/unit/test_architecture_guards.py
@@ -313,3 +313,67 @@ def test_the_personal_memory_guards_detect_a_violation() -> None:
     assert _outside(leak, _GRANT_FIELD_HOMES, _GRANT_FIELD_NAMES) == ["routers/leak.py"]
     assert _calls(leak, "select_person") == ["routers/leak.py"]
     assert _issued_as_manual(leak) == ["routers/leak.py"]
+
+
+# --- the short-term continuity session (Plan 0061, ADR 0020) ----------------------------
+_SESSION_HOME = "memory/continuity.py"
+_SESSION_CALLERS = frozenset({_SESSION_HOME, "text_turn.py"})
+_SESSION_PRIVATE_NAMES = frozenset({"_session", "_slot", "ContinuitySession"})
+_GENERIC_IDENTITY_HOME = "cognition/generic_identity.py"
+
+
+def _keyword_values(sources: Mapping[str, str], module: str, keyword: str) -> list[ast.expr]:
+    """The value of every `keyword=...` argument used anywhere in one module."""
+    return [
+        node.value
+        for node in ast.walk(ast.parse(sources[module]))
+        if isinstance(node, ast.keyword) and node.arg == keyword
+    ]
+
+
+@pytest.mark.unit
+def test_the_session_is_opened_and_written_only_by_the_text_turn_service() -> None:
+    """A route or a tool that read the session would bypass the speaker's transition."""
+    sources = _sources()
+
+    assert sorted(_calls(sources, "open_turn")) == sorted(_SESSION_CALLERS)
+    assert sorted(_calls(sources, "record_pair")) == sorted(_SESSION_CALLERS)
+    assert _outside(sources, frozenset({_SESSION_HOME}), _SESSION_PRIVATE_NAMES) == []
+
+
+@pytest.mark.unit
+def test_identifying_a_generic_turn_never_spends_a_grant_or_computes_a_voice() -> None:
+    """ADR 0020 §1: observe the token (`peek_actor`), and pass no audio to the resolver."""
+    sources = _sources()
+
+    assert _calls({_GENERIC_IDENTITY_HOME: sources[_GENERIC_IDENTITY_HOME]}, "resolve_actor") == []
+    assert (
+        _calls({_GENERIC_IDENTITY_HOME: sources[_GENERIC_IDENTITY_HOME]}, "resolve_consent") == []
+    )
+    wav_values = _keyword_values(sources, _GENERIC_IDENTITY_HOME, "wav_bytes")
+    assert wav_values
+    assert all(isinstance(v, ast.Constant) and v.value is None for v in wav_values)
+
+
+@pytest.mark.unit
+def test_the_continuity_guards_detect_a_violation() -> None:
+    leak = {
+        "routers/leak.py": (
+            "turn = continuity.open_turn(7)\n"
+            "ok = continuity.record_pair(turn, 'a', 'b')\n"
+            "slot = continuity._session\n"
+        ),
+        "cognition/generic_identity.py": (
+            "actor = await fused.resolve_actor(event)\n"
+            "fused = build(pin, frame=frame, wav_bytes=audio)\n"
+        ),
+        "memory/continuity.py": "x = _session.open_turn(1)\n",
+    }
+
+    assert _calls(leak, "open_turn") == ["routers/leak.py", "memory/continuity.py"]
+    assert _outside(leak, frozenset({_SESSION_HOME}), _SESSION_PRIVATE_NAMES) == ["routers/leak.py"]
+    assert _calls({_GENERIC_IDENTITY_HOME: leak[_GENERIC_IDENTITY_HOME]}, "resolve_actor") == [
+        _GENERIC_IDENTITY_HOME
+    ]
+    (wav_value,) = _keyword_values(leak, _GENERIC_IDENTITY_HOME, "wav_bytes")
+    assert not (isinstance(wav_value, ast.Constant) and wav_value.value is None)
```

- [ ] **Step 2: Run them.**
  `uv run pytest tests/unit/test_architecture_guards.py tests/integration/test_owner_stranger_matrix.py
  -q -p no:cacheprovider` (33 passed).
- [ ] **Step 3: Prove they bite.** In `text_turn.prepare_text_turn` replace
  `person_id = _continuity_person_id(resolved_person)` by `person_id = 1`; ten tests fail across
  `test_owner_stranger_matrix.py` and `test_generic_turn_continuity.py`. Revert it. The guard
  `test_the_continuity_guards_detect_a_violation` already trips on a synthetic offender.
- [ ] **Step 4: Lint and commit.** `ruff` over both files; commit
  `test(server): guard the continuity session and the no-token owner turn`.

---

## Task 8: `just chat-test` carries the owner token

**Files:**
- Modify: `scripts/chat_test.py`
- Test: `tests/unit/test_chat_test.py`

**Interfaces:**
- Produces: `obtain_owner_token(client, base_url, *, read_pin=...) -> str | None`;
  `post_chat(..., token=None)`; `assess_smoke(..., with_token=True)`; `CheckResult.skipped`;
  `run_smoke(base_url, timeout_s, *, read_pin=..., transport=None)`; `run_interactive(...,
  read_pin=...)`.

- [ ] **Step 1: Write the failing tests** (eight new: the token header, the unlock, an empty and a
  rejected PIN, the skipped continuity, A with the token and B without it, no token not failing, and
  a closed stdin not aborting the run):

```diff
diff --git a/tests/unit/test_chat_test.py b/tests/unit/test_chat_test.py
--- a/tests/unit/test_chat_test.py
+++ b/tests/unit/test_chat_test.py
@@ -1,8 +1,19 @@
 """Tests for the independent M3 chat QA script."""

+import json
+
+import httpx
 import pytest

-from scripts.chat_test import ChatReply, assess_smoke, parse_chat_reply
+from scripts.chat_test import (
+    ChatReply,
+    assess_smoke,
+    obtain_owner_token,
+    parse_chat_reply,
+    run_smoke,
+)
+
+_GRANT = "token-canary-1"


 def test_parse_chat_reply_accepts_the_public_contract() -> None:
@@ -57,3 +68,135 @@ def test_assess_smoke_fails_when_context_leaks_to_another_conversation() -> None
     checks = assess_smoke(intro, leaked, recalled, marker="COBALTO-731")

     assert checks[1].passed is False
+
+
+def test_assess_smoke_without_a_token_reports_continuity_as_not_checked() -> None:
+    """ADR 0020 §9: with no owner token the server cannot give continuity, so it is skipped."""
+    intro = ChatReply("Entendido", "neutral", 10, "qa-a")
+    isolated = ChatReply("DESCONOCIDA", "neutral", 11, "qa-b")
+    recalled = ChatReply("No tengo esa clave", "neutral", 12, "qa-a")
+
+    checks = assess_smoke(intro, isolated, recalled, marker="COBALTO-731", with_token=False)
+
+    assert [check.passed for check in checks] == [True, True, True]
+    assert [check.skipped for check in checks] == [False, False, True]
+    assert "no comprobada" in checks[2].detail
+
+
+def test_assess_smoke_with_a_token_still_requires_the_recall() -> None:
+    intro = ChatReply("Entendido", "neutral", 10, "qa-a")
+    isolated = ChatReply("DESCONOCIDA", "neutral", 11, "qa-b")
+    forgotten = ChatReply("No tengo esa clave", "neutral", 12, "qa-a")
+
+    checks = assess_smoke(intro, isolated, forgotten, marker="COBALTO-731", with_token=True)
+
+    assert checks[2].passed is False
+    assert checks[2].skipped is False
+
+
+def _server(seen: list[tuple[str, str | None]], *, unlock_status: int = 200) -> httpx.MockTransport:
+    """A fake server: records (path, token header); only a request with the token recalls."""
+    remembered: dict[str, str] = {}
+
+    def handle(request: httpx.Request) -> httpx.Response:
+        token = request.headers.get("X-Iroko-Identity-Token")
+        seen.append((request.url.path, token))
+        if request.url.path == "/auth/owner/unlock":
+            body = json.loads(request.content)
+            assert "scope" not in body  # the default scope: the token is only observed
+            if unlock_status != 200:
+                return httpx.Response(unlock_status, json={"detail": "no"})
+            return httpx.Response(200, json={"token": _GRANT, "expires_at": "x", "scope": "x"})
+        payload = json.loads(request.content)
+        message: str = payload["message"]
+        if "exacta: " in message:  # the introduction: remember what was said
+            remembered["marker"] = message.split("exacta: ")[1].split(".", maxsplit=1)[0]
+            reply = "Entendido."
+        elif "clave temporal exacta que te di" in message:  # the recall
+            marker = remembered.get("marker")
+            reply = f"La clave es {marker}" if token and marker else "No tengo esa clave."
+        else:  # the isolation probe
+            reply = "DESCONOCIDA"
+        return httpx.Response(
+            200,
+            json={
+                "response": reply,
+                "emotion": "neutral",
+                "duration_ms": 1,
+                "conversation_id": payload["conversation_id"],
+                "authentication_consumed": False,
+            },
+        )
+
+    return httpx.MockTransport(handle)
+
+
+async def _pin_is(value: str) -> str:
+    return value
+
+
+async def test_obtain_owner_token_unlocks_with_the_default_scope() -> None:
+    seen: list[tuple[str, str | None]] = []
+    async with httpx.AsyncClient(transport=_server(seen), base_url="http://test") as client:
+        token = await obtain_owner_token(client, "http://test", read_pin=lambda: _pin_is("0000"))
+
+    assert token == _GRANT
+    assert seen == [("/auth/owner/unlock", None)]
+
+
+async def test_an_empty_pin_means_no_token_and_no_request() -> None:
+    seen: list[tuple[str, str | None]] = []
+    async with httpx.AsyncClient(transport=_server(seen), base_url="http://test") as client:
+        token = await obtain_owner_token(client, "http://test", read_pin=lambda: _pin_is(""))
+
+    assert token is None
+    assert seen == []
+
+
+async def test_a_rejected_pin_means_no_token_and_the_run_goes_on() -> None:
+    seen: list[tuple[str, str | None]] = []
+    transport = _server(seen, unlock_status=401)
+    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
+        token = await obtain_owner_token(client, "http://test", read_pin=lambda: _pin_is("bad"))
+
+    assert token is None
+
+
+async def test_the_smoke_sends_the_token_to_a_and_nothing_to_b() -> None:
+    seen: list[tuple[str, str | None]] = []
+
+    code = await run_smoke(
+        "http://test", 5.0, read_pin=lambda: _pin_is("0000"), transport=_server(seen)
+    )
+
+    chat = [token for path, token in seen if path == "/chat"]
+    assert chat == [_GRANT, None, _GRANT]  # A introduces, B asks, A recalls
+    assert code == 0
+
+
+async def test_the_smoke_without_a_token_does_not_fail_for_missing_continuity() -> None:
+    seen: list[tuple[str, str | None]] = []
+
+    code = await run_smoke(
+        "http://test", 5.0, read_pin=lambda: _pin_is(""), transport=_server(seen)
+    )
+
+    assert [token for path, token in seen if path == "/chat"] == [None, None, None]
+    assert code == 0
+
+
+async def test_a_closed_stdin_means_no_pin_and_the_smoke_still_runs(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    """`just chat-test < NUL` must skip the continuity check, not abort the run."""
+    seen: list[tuple[str, str | None]] = []
+
+    def closed(_prompt: str) -> str:
+        raise EOFError
+
+    monkeypatch.setattr("scripts.chat_test.getpass.getpass", closed)
+
+    code = await run_smoke("http://test", 5.0, transport=_server(seen))
+
+    assert code == 0
+    assert [path for path, _ in seen].count("/auth/owner/unlock") == 0
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_chat_test.py -q -p no:cacheprovider`
  Expected RED: `ImportError: cannot import name 'obtain_owner_token' from 'scripts.chat_test'`
  (and, once that exists, `EOFError` from `getpass` in the closed-stdin test).
- [ ] **Step 3: Implement.**

```diff
diff --git a/scripts/chat_test.py b/scripts/chat_test.py
--- a/scripts/chat_test.py
+++ b/scripts/chat_test.py
@@ -1,21 +1,34 @@
-"""Mini-QA for M3: ``just chat-test`` or ``just chat-test --interactive``."""
+"""Mini-QA for M3: ``just chat-test`` or ``just chat-test --interactive``.
+
+Short-term continuity belongs to the identified person (ADR 0020), and ``/chat`` identifies
+through a one-use owner token that it only observes. The script asks for the owner PIN with
+a hidden prompt (never echoed, never logged), unlocks once with the default scope and
+presents the token to conversation A; conversation B presents nothing. Without a PIN the
+continuity check is reported as not checked instead of failing.
+"""

 from __future__ import annotations

 import argparse
 import asyncio
 from dataclasses import dataclass
+import getpass
 import logging
-from typing import NoReturn
+from typing import TYPE_CHECKING, NoReturn
 from uuid import uuid4

 import httpx

+if TYPE_CHECKING:
+    from collections.abc import Awaitable, Callable
+
 logger = logging.getLogger(__name__)

 _DEFAULT_URL = "http://localhost:8000"
 _DEFAULT_TIMEOUT_S = 60.0
 _EXIT_COMMANDS = {"/exit", "/quit", "q"}
+_IDENTITY_HEADER = "X-Iroko-Identity-Token"
+_UNLOCK_PATH = "/auth/owner/unlock"
 _INTRO_PROMPT = "Recuerda temporalmente esta clave exacta: {secret}. Responde brevemente."
 _ISOLATION_PROMPT = "¿Te di una clave temporal en esta conversación? Si no, di DESCONOCIDA."
 _RECALL_PROMPT = "¿Cuál es la clave temporal exacta que te di? Inclúyela literalmente."
@@ -38,6 +51,7 @@ class CheckResult:
     name: str
     passed: bool
     detail: str
+    skipped: bool = False


 def _require_text(payload: dict[object, object], field: str) -> str:
@@ -63,16 +77,70 @@ def parse_chat_reply(payload: object, expected_conversation_id: str) -> ChatRepl
     return ChatReply(response, emotion, duration_ms, conversation_id)


+async def _read_pin() -> str:
+    """Read the owner PIN via getpass, off the event loop. Never logged.
+
+    Returns:
+        The PIN, or an empty string when stdin is closed (continuity is then skipped).
+    """
+    try:
+        return await asyncio.to_thread(getpass.getpass, "PIN del dueño (Enter para omitir): ")
+    except EOFError:
+        return ""
+
+
+async def obtain_owner_token(
+    client: httpx.AsyncClient,
+    base_url: str,
+    *,
+    read_pin: Callable[[], Awaitable[str]] = _read_pin,
+) -> str | None:
+    """Unlock once with the default scope and return the one-use token, or ``None``.
+
+    Args:
+        client: HTTP client bound to the server.
+        base_url: Server base URL.
+        read_pin: Source of the PIN; the default prompts without echo.
+
+    Returns:
+        The opaque token, or ``None`` when the PIN was left empty or was rejected (the
+        run then reports continuity as not checked).
+    """
+    pin = await read_pin()
+    if not pin:
+        logger.info("Sin PIN: la continuidad no se comprobará.")
+        return None
+    response = await client.post(f"{base_url.rstrip('/')}{_UNLOCK_PATH}", json={"pin": pin})
+    if response.is_error:
+        logger.warning("PIN rechazado (%s): la continuidad no se comprobará.", response.status_code)
+        return None
+    return str(response.json()["token"])
+
+
 async def post_chat(
     client: httpx.AsyncClient,
     base_url: str,
     message: str,
     conversation_id: str,
+    token: str | None = None,
 ) -> ChatReply:
-    """Send one text turn to the running server and validate its response."""
+    """Send one text turn to the running server and validate its response.
+
+    Args:
+        client: HTTP client bound to the server.
+        base_url: Server base URL.
+        message: The user text.
+        conversation_id: Public conversation label (never identity).
+        token: Optional owner token, presented in the identity header.
+
+    Returns:
+        The validated reply.
+    """
+    headers = {_IDENTITY_HEADER: token} if token else {}
     response = await client.post(
         f"{base_url.rstrip('/')}/chat",
         json={"message": message, "conversation_id": conversation_id},
+        headers=headers,
     )
     response.raise_for_status()
     return parse_chat_reply(response.json(), conversation_id)
@@ -83,8 +151,22 @@ def assess_smoke(
     isolated: ChatReply,
     recalled: ChatReply,
     marker: str,
+    *,
+    with_token: bool = True,
 ) -> tuple[CheckResult, ...]:
-    """Assess contract, cross-conversation isolation, and same-ID continuity."""
+    """Assess contract, cross-conversation isolation, and the owner's continuity.
+
+    Args:
+        intro: Reply to the introduction of the marker (conversation A).
+        isolated: Reply of conversation B, which presents no token.
+        recalled: Reply of conversation A asked to recall the marker.
+        marker: The temporary key that A introduced.
+        with_token: Whether A presented an owner token. Without one the server cannot
+            give continuity, so that check is skipped rather than failed (ADR 0020 §9).
+
+    Returns:
+        The three checks.
+    """
     normalized_marker = marker.casefold()
     ids_are_consistent = (
         intro.conversation_id == recalled.conversation_id
@@ -101,11 +183,25 @@ def assess_smoke(
             normalized_marker not in isolated.response.casefold(),
             "la conversación B no recibió la clave de A",
         ),
-        CheckResult(
+        _continuity_check(recalled, normalized_marker, with_token=with_token),
+    )
+
+
+def _continuity_check(
+    recalled: ChatReply, normalized_marker: str, *, with_token: bool
+) -> CheckResult:
+    """Build the continuity check, or its skipped form when no token was presented."""
+    if not with_token:
+        return CheckResult(
             "Continuidad de A",
-            normalized_marker in recalled.response.casefold(),
-            "la conversación A recordó su clave temporal",
-        ),
+            True,
+            "no comprobada: sin PIN no hay token del dueño ni continuidad que medir",
+            skipped=True,
+        )
+    return CheckResult(
+        "Continuidad de A",
+        normalized_marker in recalled.response.casefold(),
+        "la conversación A recordó su clave temporal",
     )


@@ -120,45 +216,81 @@ async def _run_probes(
     marker: str,
     conversation_a: str,
     conversation_b: str,
+    token: str | None,
 ) -> tuple[ChatReply, ChatReply, ChatReply]:
-    """Send the three ordered requests that exercise M3 context boundaries."""
-    intro = await post_chat(client, base_url, _INTRO_PROMPT.format(secret=marker), conversation_a)
+    """Send the three ordered requests that exercise M3 context boundaries.
+
+    A presents the owner token (when there is one); B presents nothing, so it is the
+    public unknown and cannot see A's session.
+    """
+    intro = await post_chat(
+        client, base_url, _INTRO_PROMPT.format(secret=marker), conversation_a, token
+    )
     isolated = await post_chat(client, base_url, _ISOLATION_PROMPT, conversation_b)
-    recalled = await post_chat(client, base_url, _RECALL_PROMPT, conversation_a)
+    recalled = await post_chat(client, base_url, _RECALL_PROMPT, conversation_a, token)
     return intro, isolated, recalled


-async def run_smoke(base_url: str, timeout_s: float) -> int:
-    """Run the deterministic-shape M3 smoke and return its process status."""
+async def run_smoke(
+    base_url: str,
+    timeout_s: float,
+    *,
+    read_pin: Callable[[], Awaitable[str]] = _read_pin,
+    transport: httpx.AsyncBaseTransport | None = None,
+) -> int:
+    """Run the deterministic-shape M3 smoke and return its process status.
+
+    Args:
+        base_url: Server base URL.
+        timeout_s: Per-request timeout in seconds.
+        read_pin: Source of the owner PIN; the default prompts without echo.
+        transport: Optional transport, so tests need no network.
+
+    Returns:
+        ``0`` when every check passed or was skipped, else ``1``.
+    """
     run_token = uuid4().hex
     marker = f"COBALTO-{run_token[:6].upper()}"
     conversation_a = f"m3qa-a-{run_token[:10]}"
     conversation_b = f"m3qa-b-{run_token[:10]}"
-    async with httpx.AsyncClient(timeout=timeout_s) as client:
+    async with httpx.AsyncClient(timeout=timeout_s, transport=transport) as client:
+        token = await obtain_owner_token(client, base_url, read_pin=read_pin)
         intro, isolated, recalled = await _run_probes(
-            client, base_url, marker, conversation_a, conversation_b
+            client, base_url, marker, conversation_a, conversation_b, token
         )

     _log_reply("A presenta clave", intro)
     _log_reply("B consulta sin contexto", isolated)
     _log_reply("A recuerda clave", recalled)
-    checks = assess_smoke(intro, isolated, recalled, marker)
+    checks = assess_smoke(intro, isolated, recalled, marker, with_token=token is not None)
     for check in checks:
-        logger.info("%s  %s — %s", "PASS" if check.passed else "FAIL", check.name, check.detail)
+        verdict = "SKIP" if check.skipped else ("PASS" if check.passed else "FAIL")
+        logger.info("%s  %s — %s", verdict, check.name, check.detail)
     return 0 if all(check.passed for check in checks) else 1


-async def run_interactive(base_url: str, timeout_s: float, conversation_id: str) -> int:
-    """Run a manual multi-turn text conversation until the user exits."""
+async def run_interactive(
+    base_url: str,
+    timeout_s: float,
+    conversation_id: str,
+    *,
+    read_pin: Callable[[], Awaitable[str]] = _read_pin,
+) -> int:
+    """Run a manual multi-turn text conversation until the user exits.
+
+    The owner token lasts ``OWNER_UNLOCK_TTL_SECONDS``; after that the turns are the public
+    unknown again and the session is suspended, not lost.
+    """
     logger.info("Conversación %s. Escribe /exit para salir.", conversation_id)
     async with httpx.AsyncClient(timeout=timeout_s) as client:
+        token = await obtain_owner_token(client, base_url, read_pin=read_pin)
         while True:
             message = input("Tú> ").strip()
             if message.casefold() in _EXIT_COMMANDS:
                 return 0
             if not message:
                 continue
-            reply = await post_chat(client, base_url, message, conversation_id)
+            reply = await post_chat(client, base_url, message, conversation_id, token)
             _log_reply("Bot", reply)


```

- [ ] **Step 4: Run, lint, commit.** `uv run pytest tests/unit/test_chat_test.py -q
  -p no:cacheprovider` (12 passed); `uv run python scripts/chat_test.py --help`; `ruff` over both
  paths; commit `feat(scripts): chat-test presents the owner token (plan 0061)`.

---

## Task 9: Real runtime acceptance

**Files:** new `docs/evals/0061-generic-turn-continuity-acceptance.md` (outcomes only) and its entry
in `docs/evals/README.md`.

Pipec starts the processes himself. Preconditions: Ollama is up (a down Ollama makes the first
greetings speak the rescue phrase), `MEMORY_ENABLED=true`, `FACE_AUTHENTICATION_ENABLED=true` and
`ROBOT_FACE_AUTH_ENABLED=true` with the owner's face enrolled; **no token is presented** by the
robot. The voice does not need to be enrolled (it is not consulted). Record each case as pass, fail
or not run, with counts and durations; never a name, a PIN, a transcript or a token.

- [ ] **Step 1: `just gate`.** Record the outcome and the test count (2587 passed and 10 skipped, 2597 collected, in the rehearsal).
- [ ] **Step 2: Case (a), continuity.** Say a sentence, then within 180 s a question that depends on
  it ("my favourite number is forty-two" … "what is my favourite number?"). Expected: answered as a
  continuation. The server log shows `Continuity: started` then `Continuity: continued`, and
  `Generic identification: identified`.
- [ ] **Step 3: Case (b), a second person.** (b1) A second person beside the owner asks the same
  question. Expected: not answered from the session, `Continuity: suspended` with cause
  `veto_multiple_faces`, and the owner alone continues afterwards. (b2) A second person **alone** in
  frame. Expected: suspended with cause `no_evidence`; nothing answered from the owner's session.
- [ ] **Step 4: Case (c), silence.** Wait more than 180 s, then ask the follow-up. Expected: the
  context is gone and the log shows `Continuity: expired`.
- [ ] **Step 5: Case (d), cost.** From the log of the runs above, record the number of
  `Generic identification:` lines, their median and maximum `elapsed_ms`, and the count of each
  transition (`started`, `continued`, `replaced`, `expired`, `suspended` by cause). Count only the
  transitions of a turn that has a `Generic identification:` line just before it: a
  `/vision/respond` turn is the public unknown by design, logs `suspended` with `no_evidence` and
  has no such line, and a slot that was opened but never written ends as `expired` without having
  held anything.
- [ ] **Step 6: Measurement of ADR 0020 §7.** Twice, on different runs:
  `just eval-chat --provider ollama --mode stream --runs 5` and record the `history` row (fallback
  rate and "not in Spanish"). Gate (D-9): at most 5 % in both runs; any non-Spanish reply is read by
  Pipec and recorded with the heuristic's limits.
- [ ] **Step 7: `just chat-test`**, once with the PIN and once with an empty PIN. Expected: all three
  checks pass with the PIN; with an empty PIN the continuity check is `SKIP` and the exit status is 0.
- [ ] **Step 8: Record and commit** the acceptance note, `docs: record the plan 0061 acceptance`.

---

## Task 10: Documentation truth

**Files (docs only):**
- ADR 0020: status `Accepted`, `Implemented by` Plan 0061, the *Follow-up* section closed.
  (Its *Amends* line, §3's "a write is not an access" sentence and §5's reasons sentence were
  added when this plan was queued; check they still match the code.)
- [ADR 0016](../../adr/0016-face-and-voice-identity-fusion.md) status line (§5 partially superseded)
  and §8 (the closed log reasons gain `error`; `backend_unavailable` also names a failed face
  detector), and `docs/runbooks/operator-manual.md` (the *Tier 4* reason table and the speaker
  verification list that name `no_evidence` and `backend_unavailable`),
  [ADR 0019](../../adr/0019-personal-memory-capabilities.md) (the attribution sentence and the
  `forget` consequence point to ADR 0020), ADR 0015 ("a public turn reaches the model with no
  history"), ADR 0009 (the request-local note), ADR 0005 (the working-history line) and
  `docs/adr/README.md`.
- `docs/architecture/identity-and-access.md` (fusion paragraph, the locked-posture sentence,
  *Conversation isolation*: the `voice:<session-id>:person:<id>` proposal becomes one session slot),
  `cognitive-contracts.md`, `cognitive-architecture.md`, `memory-and-world-state.md` (working
  context lasts 180 s), `current-state.md` (diagram line and working-memory rows) and the Archify
  diagram (`docs/architecture/diagrams/current-state.{json,html}`: validate, then deliver).
- `docs/roadmap/cognitive-roadmap.md` and `conversational-memory-delivery-map.md` (the CM-2 rows,
  *Current fracture*, reusable capabilities), `docs/evals/0059-user-emotion-apart.md` (its memory
  case is now exercisable), the operator manual's `chat-test` line, `docs/plans/README.md`,
  `docs/plans/open/README.md`, `docs/plans/completed/README.md`, and the move of this plan to
  `completed/`.

- [ ] **Step 1: Update each file** with outcomes and test counts from Task 9 and from the final
  `just gate`; replace "plan to be written" and "not written" wherever it appears
  (`rg -n "0061|CM-2|working memory|working-memory" docs`).
- [ ] **Step 2: Regenerate the architecture diagram** (feedback: every edit of `current-state.md`
  refreshes it) with the Archify skill, validate then deliver.
- [ ] **Step 3: Verify the docs.** `uv run ruff format --check .` (CI formats the Python blocks of
  the Markdown files), `uv run python scripts/check_reserved_terms.py`, and a check that every
  relative link of the touched `.md` files resolves (there is no tracked `mkdocs.yml`, so
  `just docs-build` is not a link check).
- [ ] **Step 4: Update the local table** (`docs/roadmap/tabla-tareas.md`, never committed), commit
  `docs: close plan 0061 and accept adr 0020`, open the PR, squash-merge after green CI, delete the
  branch.

---

## Review record (2026-10-13)

A read-only reviewer (a separate agent, model sonnet) reproduced this document's sixteen code
blocks onto a clean copy of `main`, ran the linters over the result and read the ADR and the code
against the plan. It found no Critical issue and confirmed that the ensayed code has no logic,
privacy or concurrency defect. Its findings and how they were closed:

| # | Finding | Disposition |
|---:|---|---|
| 1 | Important — the Task 4 diff of `test_chat_endpoint.py` was written against the baseline, not against Task 3, so it did not apply | The diff is now taken from Task 3's state |
| 2 | Important — the language heuristic counted French that borrows `que`, `tu`, `te`, `un`, `y`, `se` as Spanish (5 of 5 plausible sentences), so "0 of N" would have been falsely reassuring | Shared words removed from every list, French-only words added, five French and two Spanish canaries pinned in Task 6 |
| 3 | Important — nothing proved `/vision/respond` end to end (its only pin mocks `process_text_turn`) | New real-route test in Task 4, proven by a mutation (D-12) |
| 4 | Important — `FusionReason.ERROR` and the wider `backend_unavailable` amend the closed set of ADR 0016 §8 without saying so | ADR 0020 gains an *Amends* line and the §5 sentence; Task 10 updates ADR 0016 §8 and the operator manual (D-3) |
| 5 | Minor — the blank diff-context lines carry one space, so the first commit of this file is rewritten by the trailing-whitespace hook | The file is committed with the hook's result; Task 0 keeps the `--ignore-whitespace` note |
| 6 | Minor — the Task 0 `rg` for `working` also matched two comments | Narrower pattern |
| 7 | Minor — `/vision/respond` suspensions and never-written slots pollute the Task 9 counts | Counting rule written into Task 9 step 5 |
| 8 | Minor — `chat-test` with a closed stdin aborted with exit 130 instead of `SKIP` | `EOFError` handled and tested (D-10) |
| 9 | Minor — `WORKING_MEMORY_SIZE` below 2 reported a write as kept while trimming it away | `record_pair` returns `False`; tested in Task 1 |
| 10 | Minor — an obsolete comment in `.env.example` | Replaced in Task 1 |
| 11 | Minor — `Proposed` is not a plan lane (queue rule 7 has `QUEUED`; only `Ready` plans execute), and `just docs-build` is not a link check | The plan is `Queued`; promotion marks it `Ready` (Task 0 step 0); Task 10 step 3 reworded |

Two observations about the ADR itself were folded into it: the silence is measured from the last
*written* turn, so a write is not an access (D-4, now a sentence in §3), and the closed reasons of
§5 extend ADR 0016 §8 (finding 4).

## ADR 0020 coverage

| ADR section | Where |
|---|---|
| §1 identification per channel, no voice, own resolver, failures degrade, off when memory is off | Tasks 2, 4 |
| §2 who has continuity, history only, emotion buffer closed, no attribution | Task 3 |
| §3 one slot, 3000 characters, 180 s, generation | Task 1 |
| §4 the transition table, which turns take part, when | Tasks 1, 3, 4 |
| §5 closed reasons, no content | Tasks 1, 2 |
| §6 grant by operation | **Not built** (D-11) |
| §7 prompt and measurement | Tasks 5, 6, 9 |
| §8 no wire change | Task 4 (`identity_source` stays `null`), Global Constraints |
| §9 `just chat-test` | Task 8 |
| §10 acceptance | Tasks 7 (automated), 9 (Pipec) |

## Completion criteria

1. Tasks 0 to 10 done, one commit per task, every test RED before GREEN (Task 7 by mutation).
2. `just gate` green with at least 2597 tests collected (baseline 2515), `ruff` clean over the explicit paths
   of every file touched.
3. The four acceptance cases and the two measurements recorded by Pipec; the `history` row at most
   5 % in both runs.
4. ADR 0020 `Accepted`; every document of Task 10 updated; this plan moved to `completed/`.

## Rollback boundary

Everything is in-process and nothing is persisted: reverting the squash-merge restores the previous
behaviour (stateless generic turns). The only cross-cutting changes are the additive
`FaceRequestResolver.detection_failed`, the additive `FusionReason.ERROR` (its protected-turn log
reason is the one observable difference) and the two settings.

## Not here, and why

- **`forget` reachable with a face** (decision 6): CM-6, with the first operation that declares its
  own scope.
- **Speaker attribution of utterances, extraction, consolidation, promotion** (CM-3 onward).
- **Continuity for an unknown speaker, per-person sessions, a persistent transcript** (P3 family
  profile; ADR 0020 *Review*).
- **Barge-in and the robot's expression** (`Unplanned` rows of the roadmap).
- **Removing the dead `user_emotion` plumbing** until the tone policy is decided (D-5).
- **Voice on the generic turn**: it stays on protected turns that ask for `strong`.

## Execution record

Executed 2026-10-13 on `feat/0061-cm2-generic-turn-continuity` from `main` at `838a44f`, inline
(no subagents, no worktree), one commit per task, every new test observed RED for the stated
reason before its implementation.

| Task | Commit | Result |
|---:|---|---|
| 0 | — | `just gate` 2515 passed; the assumption greps matched; guards 83 passed |
| 1 | `fc0c3c7` | continuity slot, 24 tests |
| 2 | `14f461c` | generic identification, 68 tests; the mutation (`resolve_actor`, `wav_bytes=b"x"`) failed exactly the two named tests |
| 3 | `de918e1` | `text_turn` wired, `working.py` deleted; unit + integration 2533 |
| 4 | `903a799` | three routes; 6 of the 7 new scenarios were RED, the visual one is green by design and its mutation failed it alone |
| 5 | `5941b6a` | prompt sentence, 50 tests |
| 6 | `bf38fd6` | history set and language heuristic, 135 tests |
| 7 | `724922e` | guards and the no-token scenario; 33 tests; the mutation (`person_id = 1`) failed 11 tests |
| 8 | `6cb3299` | `chat-test` carries the token, 12 tests |
| 9 | — | run by Pipec; [acceptance record](../../evals/0061-generic-turn-continuity-acceptance.md) |
| 10 | the closing commit | documents, ADR 0020 `Accepted`, this plan moved to `completed/` |

`just gate` at the end of Task 8: **2597 passed** (baseline 2515, +82 as rehearsed), lint, types,
`ruff --select S` and `pip-audit` clean.

**Rulings.** (1) The plan's Task 7 said ten tests fail under its mutation; eleven did, which bites
at least as much. (2) Task 8's RED showed only the `ImportError` that the plan names first; the
`EOFError` case it names second was masked and passes after the implementation. (3) The whole-branch
review was a self-review by the executor, because Pipec's rules forbid subagents unless he asks; no
Critical or Important finding. (4) Cases b1 and b2 of Task 9 used a face shown on an iPad instead of
a second person (none was available); they are recorded as substitutes. (5) The one `history` reply
the language heuristic judged not Spanish was not located (reports keep counts only) and Pipec
accepted it as the heuristic's limit.

**Deferred minor.** `PreparedTextTurn.user_emotion` and the prompt plumbing stay always `None`
(decision D-5, tone-policy follow-up).

**Follow-ups with no plan** (all in the cross-cutting table of the
[roadmap](../../roadmap/cognitive-roadmap.md#cross-cutting-gates-and-conditional-work)): the cost of
the face check on a generic turn (median about 0.9 s, maximum 1.6 s on the development laptop),
recorded and not judged; the language of the reply and the model inventing a value when the session
is empty; a Whisper echo of its own prompt reaching the controller once.
