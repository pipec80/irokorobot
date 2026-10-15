# 0063 — The spoken memory offer and the explicit answer (CM-3a, second cut)

> **Status:** `Ready` and `NOW` — written 2026-10-15 from [ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md)
> decision 9 with Pipec's decisions of the same day (D-1 to D-5), rehearsed in a scratch copy of
> `main` (`73fcf8c`) and independently reviewed (see *Review record*); merged as PR #185 and
> promoted by Pipec on 2026-10-15, who confirmed decisions D-1 to D-15 as written (including the
> article after the short verbs of D-2, one open offer per person, D-12 and D-15). It is the second and last plan of CM-3a: the
> spoken offer, the explicit answer and the hardware acceptance; ADR 0021 becomes `Accepted` when
> it closes. To be executed in a **new session**.

> **For agentic workers:** if the status above does not say `Ready`, stop: Pipec has not promoted this plan.
> REQUIRED SUB-SKILLS: `superpowers:executing-plans`, `superpowers:test-driven-development`,
> `superpowers:verification-before-completion`, `superpowers:finishing-a-development-branch`.
> Execute only while this is the explicitly authorized `NOW` item, in a new session. **Pipec's
> rules win over the skills:** one plain branch from `main` (`git checkout -b`), never a git
> worktree (treat any "create a worktree" instruction as "create the branch"), no subagents unless
> Pipec asks, and this plan lives under `docs/plans/`, not `docs/superpowers/plans/`. Implement
> exactly the tasks below, in order, one commit per task. If evidence contradicts the plan, stop
> and report the conflict instead of redesigning. Pipec runs every local process (server, robot,
> Ollama, scripts that use the camera or the microphone) or explicitly asks the executor to start
> them; record what they print, outcomes only, never a sentence, a value or a name. The Bash tool
> of this environment loses backslashes and non-ASCII characters in heredocs: create and edit
> files with the Write and Edit tools (or a `.py` written with Write and run with `python -I`).
> Run the test suite with `MEMORY_ENABLED=false` (CI does) and note that `tests/conftest.py` pins
> `MEMORY_CANDIDATES_ENABLED` off and the six candidate limits at their defaults for every test.

**Goal:** A taste the identified owner stated earlier (a `proposed` candidate, Plan 0062) is
offered back by voice on a later generic turn — «Antes me dijiste que te gusta el mate. ¿Quieres
que lo guarde? Dime: sí, autorizo guardar el mate.» — and only an explicit spoken answer that
repeats the value («Sí, autorizo guardar el mate») turns it into one canonical V4 fact through the
one writer (`memory_writer.promote`); «No autorizo guardar el mate» rejects it and erases the
value. Every offer, answer and promotion needs the face **and** the voice of the same person on
that turn's own clip, never a token; anything else is the ordinary turn, byte for byte. With
`MEMORY_CANDIDATES_ENABLED=false` (the default) nothing is offered or answered.

**Architecture:** The offer is prepared concurrently with generation in the shared text-turn
seam: a route-bound `prepare_offer` reads the speaker's oldest offerable candidate and, only when
one waits, checks the voice of the turn's clip. Once the reply is built (never on a fallback),
`commit_offer` re-checks that it is still offerable, asks the policy's read step (audited before
the effect) and moves the candidate to `offered`. The classic route speaks reply and offer in one
WAV while `llm_response` carries the reply only; the stream sends one more `audio` event with
empty text before `done`. The answer is a closed need, `InformationNeed.MEMORY_ANSWER`, recognised
by a pure grammar in `intent_resolution`; the controller resolves the actor from face and voice
**first**, for every message of that shape, and only then hands it to the injected answerer, which
promotes through the writer or audits the confirm step and rejects. `memory/candidate_dialogue.py`
holds the offer and the answer; the store gains three read-only readers.

**Tech Stack:** Python 3.12, FastAPI, aiosqlite, pydantic, pytest. No new dependency, no new route,
no migration, no wire change.

**Spec:** [ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md) decision 9 and
*Acceptance* (amended on 2026-10-15, in the change that adds this plan, with D-1, D-2 and D-5:
neutral Spanish with tuteo, the answer's closed verbs, the gate's filler phrases), decisions 3, 6,
7, 8 and 12 for the rules this plan consumes; [ADR 0019](../../adr/0019-personal-memory-capabilities.md)
§3 and §6 (the read and confirm steps); [ADR 0020](../../adr/0020-authorized-actor-in-the-conversation.md)
(the generic speaker and its wire); [ADR 0016](../../adr/0016-face-and-voice-identity-fusion.md)
§1 to §9 (fusion, replay measured not defended).

**Rehearsal (2026-10-15).** Every diff below was produced test-first in a scratch copy of `main`
(`73fcf8c`), one commit per task, with the real virtual environment. Under the CI marker filter
(`-m "not slow and not hardware and not eval" -n auto`) the suite went from **2955** to
**3115**; unfiltered it went from **2972** to **3132**. Per task, in collected tests
under the CI filter: +160: Task 1 +14, Task 2 +45, Task 3 +8, Task 4 +41, Task 5 +4, Task 6 +14, Task 7 +10, Task 8 +18, Task 9 +6. For every task the RED was observed for the stated reason by
checking out the parent's code with only that task's tests, and the GREEN, `ruff check`,
`ruff format --check` over the task's files and `mypy server/src robot/src` were clean at every
commit. At the end `ruff check .`, `ruff format --check .`, `ruff --select S server/src robot/src`,
the explicit-path lint of `scripts/inspect_candidates.py`, `mypy` (116 files), `pyright` (0 errors)
and `vulture --min-confidence 80` were clean, and the whole CI selection passed
(**3115 passed**). The repository's own `just gate` (which also runs `pip-audit`) was
**not** run in the copy. Not rehearsed: Task 10 (Pipec's hardware acceptance) and Task 11
(documentation). Treat the diffs as rehearsed code, not as a substitute for the RED/GREEN record
each task requires.

## Global Constraints

- No real household data, voice, face or name in any tracked file, test, prompt, doc or commit
  message: tests use invented canaries (`scripts/check_reserved_terms.py` guards this).
- **A value never reaches** a log line, an exception message, the wire's `llm_response`, the
  session history (`continuity`), `log_spoken` or the robot's printed text. The offer carries the
  value, so it travels only as audio: inside the classic WAV, or as a stream `audio` event with
  empty `text`.
- **The firewall rule (ADR 0021 decision 3):** every offer, answer and promotion needs the face
  **and** the voice of the same person, verified on that turn's own clip, no second face in frame,
  and never a token. Otherwise the turn is the ordinary one, byte for byte.
- **No oracle (decision 9):** whether a candidate or an offer exists is never observable by anybody
  but the verified owner: an answer-shaped message resolves the actor before the store is read,
  and a fall-through is the ordinary turn on the wire.
- The audit row is written **before** the effect, a failing audit denies it (ADR 0019 §6.3), and no
  `allowed` row is written for a step the store was always going to refuse (a read-only re-check
  comes first, as Plan 0062's `precheck_insert` does).
- `db.transaction()` is not reentrant: nothing here opens a transaction inside another.
- No wire change: no URL, status code, response field, audio format or schema moves; the stream's
  offer is an `audio` event of the existing shape. The robot (`robot/src`) is untouched.
- Every new spoken phrase is neutral Spanish with **tuteo** (D-1): Pipec lives in Santiago de
  Chile. The existing controller phrases are not changed here (see *Not here*).
- `MEMORY_CANDIDATES_ENABLED` stays `false` by default; with it off the voice routes inject
  neither the offer nor the answer, and every dialogue function also checks it.
- Audio contract wherever a clip travels: WAV, 16 000 Hz, mono, signed int16, in memory only.
- Type hints on every signature, Google docstrings on public APIs, `ruff` clean over the explicit
  paths of every file touched (including `scripts/`, which `ruff check .` excludes), `mypy
  server/src robot/src` clean, no `print()`, no `Any` or `# type: ignore` without a comment.
- Every new test is observed RED for the stated reason before its implementation.
- A commit title is at most 72 characters (commitizen rejects longer ones silently): check
  `git log -1` after every commit.

## Review Focus

Inputs the ADR implies that are most likely to bite a person using this, each pinned by a test
in its owning task:

1. **The owner's face with somebody else's voice** (a recording played near the microphone, a
   visitor speaking): no offer is spoken and no answer counts; the reply is the ordinary one and no
   audit row is written (Tasks 4, 8).
2. **Ordinary speech that looks like an answer** («guarda silencio, por favor», «olvídalo, no
   importa», «apruebo el examen»): it is not taken for an answer, or it falls through to the
   ordinary turn with the same wire fields; a protected or dated question is never an answer
   (Tasks 2, 5, 8).
3. **Speech-to-text realities**: «Sí, sí, autorizo…», «No, no autorizo…», a trailing «gracias»,
   «autorizo a guardar…», a value with «lo» («lo picante»), plural agreement in the offer, and the
   round trip — the words the offer asks for always resolve that offer (Tasks 2, 4).
4. **A value that leaks**: the offer's phrase never reaches a log, `llm_response`, the session
   history, `log_spoken` or a printed line, on either route, including when synthesis fails
   (Tasks 4, 6, 7, 8).
5. **Timing and races**: a fallback reply carries no offer; an offer made elsewhere, lapsed or
   still waiting for its answer is neither audited nor offered again; an answer after its window or
   twice on the classic route's double `decide()`; a client that hangs up mid-stream; a consent
   revoked between turns (Tasks 3, 4, 5, 6, 7, 8).
6. **An honest audit**: a read row only for an offer about to be spoken, a confirm row for every
   accepted or rejected answer and nothing for a fall-through (Tasks 4, 8).

---

## Why this plan exists

| Finding | Evidence in the merged code (`73fcf8c`) | Closed by |
|---|---|---|
| A candidate is stored and never offered | `memory_candidates` rows stay `proposed` until they lapse; `mark_offered` has no caller | Tasks 3, 4, 6, 7, 8 |
| The writer has no route caller | `memory_writer.promote` is reached only by tests | Tasks 4, 5, 8 |
| The read and confirm steps of ADR 0019 have no spoken caller | `CandidateStep.READ` is never asked; `CONFIRM` only inside `promote` | Tasks 4, 8 |
| A natural filler refuses a taste | «La verdad es que me gusta el mate» → `not_a_taste` (Plan 0062 smoke, 2026-10-15) | Task 1 |
| Nothing counts the dialogue's traces without printing a value | the acceptance has no inspector | Task 9 |

## Task overview

| # | Task | Closes |
|---:|---|---|
| 0 | Revalidate the baseline | — |
| 1 | Filler phrases before a taste | D-5 |
| 2 | The answer grammar and `InformationNeed.MEMORY_ANSWER` | D-2, decision 9 (the answer) |
| 3 | The store's readers: next offerable, still offerable, the open offer | one open offer per person |
| 4 | The dialogue: prepare, commit and answer | decision 9 (offer, answer, results) |
| 5 | The controller's answer branch | no oracle, one attempt per event |
| 6 | The offer in the text-turn seam | concurrency, fallback, llm time |
| 7 | The offer on the stream | the silent audio event |
| 8 | Wire both voice routes | classic WAV, stream, wire parity, guards |
| 9 | The acceptance inspector | counts only |
| 10 | Hardware acceptance by Pipec | ADR 0021 *Acceptance* |
| 11 | Documentation truth; ADR 0021 `Accepted` | the docs this plan makes stale |

## Decisions

**Confirmed 2026-10-15.** D-1 to D-5 are Pipec's, confirmed in conversation on 2026-10-15 before
this plan was written and recorded in ADR 0021 by the change that added this plan; D-6 to D-15
are the plan's and Pipec confirmed them when he promoted it the same day.

1. **D-1 — Neutral Spanish with tuteo (Pipec).** Every new spoken phrase uses tuteo, not the ADR's
   original voseo: «¿Quieres que lo guarde? Dime: …», «Listo, lo guardé.», «Está bien, no lo
   guardo.», «No lo guardé: ya tengo guardado algo distinto.» The offer: «Antes me dijiste que te
   gusta(n) {x}.» / «… que no te gusta(n) {x}.» / «… que prefieres {x}.» followed by «¿Quieres que
   lo guarde? Dime: sí, autorizo guardar {x}.» The verb agrees with a plural article («te gustan
   las empanadas»).
2. **D-2 — The answer is a closed verb and the value (Pipec, option A).** Yes: `autorizo`,
   `apruebo` (alone, or followed by `guardar`, `a guardar` or `que guardes`), `guarda`, `guárdalo`;
   no: `no autorizo`, `no apruebo` (same continuations), `no lo guardes`, `no guardes`,
   `olvídalo`, `bórralo`. A bare «sí» or a verb alone never answers. Openers («Iroko», «oye»,
   «bueno», «ok», «claro», a repeated «sí» or «no») and trailing courtesy («gracias», «por favor»)
   are ignored. The value is at most six words; after the short verbs (`guarda`, `guárdalo`,
   `no lo guardes`, `no guardes`, `olvídalo`, `bórralo`) it must start with an article, because
   ordinary speech uses them too («guarda silencio», «olvídalo, no importa», «bórralo todo»).
3. **D-3 — The switch is Pipec's (Pipec).** `MEMORY_CANDIDATES_ENABLED` stays `false` by default;
   Pipec turns it on in `.env`. Task 11 documents how, what to say and how to roll back.
4. **D-4 — Measured on Pipec's PC only (Pipec).** There is no homelab: case 8 of the acceptance
   measures on the shared laptop and records the homelab as "not available, not run".
5. **D-5 — Filler phrases (Pipec).** «la verdad es que» and «es que» are accepted as closed
   phrases right before the trigger, and «oye» as a lead-in word. They are phrases, not free
   words, so «siempre que me gusta…» (a habit or a condition), «dice que me gusta…» and
   «que me gusta…» still refuse.
6. **D-6 — Module layout.** `memory/candidate_dialogue.py` holds the offer and the answer (one
   reason to change: the spoken dialogue); the three readers live in `memory/candidates.py` (the
   only module that issues SQL on the table); the phrases in `memory/lexicon.py` (as decision 9
   says); the grammar in `cognition/intent_resolution.py`. `VoiceVerifier` moves to
   `cognition/strong_actor.py`, next to `verify_face_and_voice`, so the proposal and the dialogue
   share one definition.
7. **D-7 — When the read step is asked.** After the reply is built and never on a fallback: a
   read-only `still_offerable` first (so no `allowed` row is written for an offer another turn
   made, or one that lapsed during generation), then `authorize_step(READ)` with its audit row,
   then the compare-and-set. If the compare-and-set still loses (a race inside a few
   milliseconds), an `allowed` row exists with no offer; that is the accepted residue.
8. **D-8 — One open offer per person.** While an offer waits for its answer (inside
   `MEMORY_CANDIDATE_ANSWER_SECONDS`), nothing else of that person is offered, so an answer always
   names the offer it resolves. After the window the same candidate may be offered again (oldest
   first, at most `MEMORY_CANDIDATE_MAX_OFFERS` times), and `mark_offered`'s housekeeping returns it
   to `proposed` before the compare-and-set.
9. **D-9 — What the routes speak.** One offer per turn. The classic route synthesizes reply and
   offer as one WAV; if that synthesis fails it synthesizes the reply alone (the candidate is
   already `offered`; no claim is made that it was heard). The stream sends the offer as one
   `audio` event with empty `text` after the reply's sentences; its synthesis counts as TTS time
   and the commit's time is kept out of `llm_ms`; a failing synthesis skips it.
10. **D-10 — The kill-switch.** With the switch off the routes inject neither the preparation nor
    the answerer, so an answer-shaped message does not even resolve its actor; every dialogue
    function also checks it.
11. **D-11 — The wire of an answer turn.** A successful answer reports `identity_source`
    (`face_voice`), like any protected branch. A fall-through is a generic reply and reports
    `null`, like every generic reply (ADR 0020): the classic route reports no identity for a
    `GENERIC_CONVERSATION` plan, so a fall-through equals «hola» field by field. Resolving the
    actor costs about a second only for messages shaped like an answer; that depends on the
    words, never on whether an offer exists.
12. **D-12 — An answer with no open offer** is the ordinary turn, and that turn may itself carry
    the offer (the owner said «sí, autorizo guardar el mate» before being asked).
13. **D-13 — One answer attempt per event.** The classic route calls `decide()` twice when a turn
    falls through; the controller remembers the answer of each event, so no audit row is written
    twice.
14. **D-14 — Acceptance alone.** Pipec lives alone with the robot: "another voice" is a recording
    or a different TTS voice played near the microphone while Pipec's face is in frame; "another
    face" is a photo on a phone. They are recorded as substitutes, not as the cases themselves.
15. **D-15 — `just reset-db` is never used on the real database.** It backs up and then deletes the
    file (enrolments, PIN and household data). The acceptance voids live candidates with
    `scripts/scrub_candidates.py` and counts with `scripts/inspect_candidates.py`.

## Required reading

- `AGENTS.md`, `docs/architecture/implementation-guardrails.md` and `.claude/rules/`.
- [ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md) (all of it, as amended
  on 2026-10-15), [ADR 0019](../../adr/0019-personal-memory-capabilities.md) §3 and §6,
  [ADR 0020](../../adr/0020-authorized-actor-in-the-conversation.md),
  [ADR 0016](../../adr/0016-face-and-voice-identity-fusion.md) §1 to §9.
- [Plan 0062](../completed/0062-cm3a-memory-candidates-and-writer.md) *Execution record* and
  [its local smoke](../../evals/0062-memory-candidates-local-smoke.md).
- `server/src/server/memory/{candidates,candidate_proposal,candidate_policy,memory_writer,lexicon,
  preference_gate,candidate_classifier}.py`, `server/src/server/cognition/{controller,
  intent_resolution,response_plan,strong_actor,identity_fusion}.py`, `server/src/server/{text_turn,
  streaming,streaming_render,pipeline}.py`, `server/src/server/routers/{transcribe,chat,vision}.py`,
  `scripts/scrub_candidates.py`, `tests/unit/test_architecture_guards.py`, `tests/conftest.py`
  and the tests named in each task.

## Permitted files

- Production, new: `server/src/server/memory/candidate_dialogue.py`.
- Production, modified: `server/src/server/memory/{lexicon,preference_gate,candidates,
  candidate_proposal}.py`, `server/src/server/cognition/{intent_resolution,response_plan,
  controller,strong_actor}.py`, `server/src/server/{text_turn,streaming,streaming_render,
  pipeline}.py`, `server/src/server/routers/transcribe.py`.
- Scripts: new `scripts/inspect_candidates.py`.
- Tests: the files listed in each task (new files and the modified existing ones).
- Docs (Tasks 10 and 11): the list of Task 11, a new `docs/evals/0063-memory-dialogue-acceptance.md`
  with its entry in `docs/evals/README.md`, and this plan.

No new URL, status code, response field, migration, setting or dependency. The robot
(`robot/src`), `/chat`, `/vision/respond`, the V4 reader, the household tools and the registry's
defaults are **not** edited. `docs/roadmap/tabla-tareas.md` is excluded from git and updated
locally only.

---

## Task 0: Revalidate the baseline

**Files:** this plan's evidence note only. No production change.

- [ ] **Step 0: Status.** Confirm this plan says `Ready` (Pipec's promotion). If it says anything else, stop.
- [ ] **Step 1: Branch.** `git checkout main && git pull`, confirm a clean tree, then
  `git checkout -b feat/0063-cm3a-memory-dialogue`. Record the base SHA (the rehearsal ran at
  `73fcf8c`; if `main` moved, say so and re-check that the diffs below still apply). Apply the
  diffs with the Write and Edit tools (new files whole, existing files hunk by hunk); blank context
  lines lost their single leading space in this document (the trailing-whitespace hook), so
  `git apply` needs `--recount --ignore-whitespace` if you prefer it.
- [ ] **Step 2: Baseline.** Run `just gate`; record its outcome and test count (2972 at `73fcf8c`).
  A pre-existing failure is reported, not hidden.
- [ ] **Step 2b: Re-audit the assumptions against the merged code** (queue rule 4). Each command must
  find what this plan names: `rg -n "def mark_offered|def promote|class CandidateStep" server`
  (`candidates.py`, `memory_writer.py`, `candidate_policy.py`),
  `rg -n "mark_offered\(|promote\(" server/src` (only the store and the writer),
  `rg -n "^LEAD_IN_WORDS|^GREETING_WORDS" server/src/server/memory/lexicon.py`,
  `rg -n "MEMORY_ANSWER|candidate_dialogue" server tests` (nothing),
  `rg -n "class VoiceVerifier" server` (only `memory/candidate_proposal.py`) and
  `rg -n "def _run_tts" server/src/server/pipeline.py` (one definition). A difference is reported
  before any code changes.
- [ ] **Step 3: Pin today's guards.** Run
  `uv run pytest tests/unit/test_architecture_guards.py tests/unit/test_cognitive_controller.py tests/unit/test_text_turn.py tests/integration/test_transcribe_stream.py -q -p no:cacheprovider`
  and record that it passes.

---

## Task 1: Filler phrases before a taste

**Files:**
- Modify: `server/src/server/memory/lexicon.py`, `server/src/server/memory/preference_gate.py`
- Test: modified `tests/unit/test_preference_gate.py`

**Interfaces:**
- Produces: `lexicon.LEAD_IN_PHRASES = ("la verdad es que", "es que")`; «oye» joins
  `LEAD_IN_WORDS` and «es» joins `GREETING_WORDS`; the gate drops one filler phrase that sits
  right before the trigger before it checks the lead-in.

- [ ] **Step 1: Write the failing tests** (five sentences that pass, nine that keep refusing):

```diff
diff --git a/tests/unit/test_preference_gate.py b/tests/unit/test_preference_gate.py
--- a/tests/unit/test_preference_gate.py
+++ b/tests/unit/test_preference_gate.py
@@ -222,3 +222,41 @@ def test_a_modifier_that_is_not_a_contrast_still_passes(
     text: str, predicates: frozenset[str]
 ) -> None:
     assert match_preference(text).predicates == predicates
+
+
+@pytest.mark.parametrize(
+    "text, predicates",
+    [
+        ("La verdad es que me gusta el mate.", _LIKES),
+        ("es que me encanta el jazz", _LIKES),
+        ("oye me gusta el mate", _LIKES),
+        ("Es que no me gusta el cilantro", _DISLIKES),
+        ("Es que, me gusta el mate", _LIKES),
+    ],
+)
+def test_a_short_closed_list_of_fillers_may_lead_a_taste(
+    text: str, predicates: frozenset[str]
+) -> None:
+    """Plan 0063, Pipec's decision: «la verdad es que», «es que» and «oye» are fillers."""
+    result = match_preference(text)
+
+    assert result.predicates == predicates
+    assert result.reason is None
+
+
+@pytest.mark.parametrize(
+    "text",
+    [
+        "creo que me gusta el mate",
+        "dice que me gusta el mate",
+        "mi hermano dice que me gusta el mate",
+        "lo que me gusta es el mate",
+        "ya es que me gusta el mate",
+        "siempre que me gusta algo lo compro",
+        "que me gusta el mate",
+        "y que me gusta el jazz",
+        "es que es que me gusta el mate",
+    ],
+)
+def test_a_filler_never_admits_a_belief_an_attribution_or_a_negation(text: str) -> None:
+    assert match_preference(text).predicates == frozenset()
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_preference_gate.py -q -p no:cacheprovider`
  Expected RED: the five filler sentences fail with `assert frozenset() == frozenset({'likes'})`
  (or `{'dislikes'}`); the refusals already pass.
- [ ] **Step 3: Implement:**

```diff
diff --git a/server/src/server/memory/lexicon.py b/server/src/server/memory/lexicon.py
--- a/server/src/server/memory/lexicon.py
+++ b/server/src/server/memory/lexicon.py
@@ -174,20 +174,26 @@ CANDIDATE_TOPICS = frozenset(
 )

 #: Words that may precede the trigger in the same clause ("la verdad, a mí me gusta ...").
+#: «oye» joined in Plan 0063 (Pipec's decision); it is an interjection, never an attribution.
 LEAD_IN_WORDS = frozenset(
     {
         "a", "mi", "yo", "la", "verdad", "siempre", "muy", "mucho", "muchisimo", "tambien",
         "y", "pero", "ademas", "en", "realidad", "honestamente", "sinceramente", "bueno",
         "che", "mira", "pues", "este", "eh", "igual", "entonces", "ahora", "claro",
-        "personalmente",
+        "personalmente", "oye",
     }
 )  # fmt: skip

+#: Closed filler phrases that may sit right before the trigger (Plan 0063, Pipec's decision):
+#: «la verdad es que me gusta…», «es que me encanta…». They are whole phrases, not free words,
+#: so "siempre que me gusta…" (a habit or a condition) and "dice que me gusta…" still refuse.
+LEAD_IN_PHRASES = ("la verdad es que", "es que")
+
 #: Words that may open a sentence before a taste without attributing it to somebody else
 #: ("hola Iroko, me gusta el mate"). A clause of other words before a soft break makes the next
 #: taste somebody else's ("mi hija dice: me gusta el helado").
 GREETING_WORDS = frozenset(
-    {"hola", "iroko", "oye", "dime", "escucha", "sabes", "que", "mira", "vamos", "ver"}
+    {"hola", "iroko", "oye", "dime", "escucha", "sabes", "que", "mira", "vamos", "ver", "es"}
 )

 #: A word that negates what follows or precedes: the only negated forms accepted are the
diff --git a/server/src/server/memory/preference_gate.py b/server/src/server/memory/preference_gate.py
--- a/server/src/server/memory/preference_gate.py
+++ b/server/src/server/memory/preference_gate.py
@@ -30,6 +30,7 @@ from server.memory.candidate_types import CandidateReason, GateMatch
 from server.memory.lexicon import (
     CLAUSE_OPENERS,
     GREETING_WORDS,
+    LEAD_IN_PHRASES,
     LEAD_IN_WORDS,
     NEGATORS,
     PREFERENCE_FAVOURITE,
@@ -93,8 +94,20 @@ def _predicate_of(trigger: str) -> str:
     return PREFERENCE_TRIGGERS[trigger]


+def _without_filler(lead: list[str]) -> list[str]:
+    """Drop one closed filler phrase («es que») that sits right before the trigger."""
+    text = " ".join(lead)
+    for phrase in LEAD_IN_PHRASES:
+        if text == phrase:
+            return []
+        if text.endswith(f" {phrase}"):
+            return text[: -len(phrase) - 1].split()
+    return lead
+
+
 def _lead_refusal(lead: list[str]) -> CandidateReason | None:
     """Refuse a negated or unknown lead-in: only a short closed list may precede a trigger."""
+    lead = _without_filler(lead)
     if any(word in NEGATORS for word in lead):
         return CandidateReason.NEGATION_UNSUPPORTED
     if any(word not in LEAD_IN_WORDS for word in lead):
```

- [ ] **Step 4: Run to see them pass, then lint and types.**
  `uv run pytest tests/unit/test_preference_gate.py tests/unit/test_candidate_classifier.py -q -p no:cacheprovider`;
  `uv run ruff check <paths>` and `uv run ruff format --check <paths>` over the files above;
  `uv run mypy --config-file=pyproject.toml server/src robot/src`.
- [ ] **Step 5: Commit** `feat(server): accept short fillers before a taste (plan 0063)`; check `git log -1`.

---

## Task 2: The answer grammar and `InformationNeed.MEMORY_ANSWER`

**Files:**
- Modify: `server/src/server/cognition/intent_resolution.py`, `server/src/server/cognition/response_plan.py`
- Test: new `tests/unit/test_memory_answer_grammar.py`

**Interfaces:**
- Produces: `InformationNeed.MEMORY_ANSWER = "memory_answer"`; `intent_resolution.MemoryAnswer(
  accept: bool, phrase: str)` (frozen; `phrase` is folded); `parse_memory_answer(message: str) ->
  MemoryAnswer | None`; the rule `memory.answer.v1`, placed **last**, so every protected, dated or
  identity rule wins over the shape of an answer.

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/tests/unit/test_memory_answer_grammar.py b/tests/unit/test_memory_answer_grammar.py
new file mode 100644
--- /dev/null
+++ b/tests/unit/test_memory_answer_grammar.py
@@ -0,0 +1,106 @@
+"""The closed grammar of a spoken answer to a memory offer (ADR 0021 decision 9, Plan 0063).
+
+Pipec's decision (option A): an answer is a closed verb **and** the value. A bare «sí», or a verb
+without the value, is never an answer, so nothing an attacker can know in advance promotes.
+"""
+
+import pytest
+from server.cognition.intent_resolution import (
+    MemoryAnswer,
+    parse_memory_answer,
+    resolve_information_need,
+)
+from server.cognition.response_plan import InformationNeed
+
+pytestmark = pytest.mark.unit
+
+
+@pytest.mark.parametrize(
+    "message, accept, phrase",
+    [
+        ("Sí, autorizo guardar el mate.", True, "el mate"),
+        ("autorizo guardar el mate", True, "el mate"),
+        ("Sí, apruebo guardar el mate", True, "el mate"),
+        ("apruebo que guardes el jazz", True, "el jazz"),
+        ("Guárdalo, el mate", True, "el mate"),
+        ("sí, guarda el mate", True, "el mate"),
+        ("Iroko, sí, autorizo guardar las empanadas", True, "las empanadas"),
+        ("Oye, autorizo guardar el café", True, "el cafe"),
+        ("No autorizo guardar el mate", False, "el mate"),
+        ("no apruebo que guardes el mate", False, "el mate"),
+        ("No lo guardes, el mate", False, "el mate"),
+        ("no guardes el mate", False, "el mate"),
+        ("Olvídalo, el mate", False, "el mate"),
+        ("bórralo, el mate", False, "el mate"),
+        ("Sí, autorizo guardar lo picante", True, "lo picante"),
+        ("Sí, sí, autorizo guardar el mate", True, "el mate"),
+        ("Sí, claro, autorizo guardar el mate", True, "el mate"),
+        ("Sí, autorizo a guardar el mate", True, "el mate"),
+        ("Sí, autorizo guardar el mate, gracias", True, "el mate"),
+        ("autorizo guardar el mate por favor", True, "el mate"),
+        ("No, no autorizo guardar el mate", False, "el mate"),
+        ("No. No autorizo guardar el mate.", False, "el mate"),
+        ("Sí, autorizo guardar bailar", True, "bailar"),
+    ],
+)
+def test_a_closed_verb_and_the_value_make_an_answer(
+    message: str, accept: bool, phrase: str
+) -> None:
+    assert parse_memory_answer(message) == MemoryAnswer(accept=accept, phrase=phrase)
+    resolution = resolve_information_need(message)
+    assert resolution.need is InformationNeed.MEMORY_ANSWER
+    assert resolution.rule_id == "memory.answer.v1"
+
+
+@pytest.mark.parametrize(
+    "message",
+    [
+        "sí",
+        "Sí, autorizo",
+        "autorizo guardar",
+        "sí, guárdalo",
+        "guárdalo",
+        "no lo guardes",
+        "olvídalo",
+        "dale",
+        "ok",
+        "no",
+        "sí, por favor",
+        "me gusta el mate",
+        "Guarda silencio, por favor",
+        "Olvídalo, no importa",
+        "Bórralo todo",
+        "no guardes nada",
+        "sí, autorizo a guardar",
+        "",
+        "   ",
+    ],
+)
+def test_a_bare_yes_or_a_verb_without_the_value_is_never_an_answer(message: str) -> None:
+    assert parse_memory_answer(message) is None
+    assert resolve_information_need(message).need is not InformationNeed.MEMORY_ANSWER
+
+
+def test_a_closed_rule_resolved_earlier_wins_over_the_shape_of_an_answer() -> None:
+    """A protected or dated message is never read as an answer: those rules run first."""
+    assert resolve_information_need("guarda la fecha de hoy").need is InformationNeed.CURRENT_DATE
+    assert (
+        resolve_information_need("sí, autorizo guardar a mi hijo").need
+        is InformationNeed.PROTECTED_HOUSEHOLD
+    )
+
+
+def test_the_value_is_a_short_phrase() -> None:
+    long_value = "uno dos tres cuatro cinco seis siete"
+
+    assert parse_memory_answer(f"sí, autorizo guardar {long_value}") is None
+    assert parse_memory_answer("sí, autorizo guardar uno dos tres cuatro cinco seis") == (
+        MemoryAnswer(accept=True, phrase="uno dos tres cuatro cinco seis")
+    )
+
+
+def test_the_answer_is_frozen() -> None:
+    answer = MemoryAnswer(accept=True, phrase="el mate")
+
+    with pytest.raises(ValueError, match="frozen"):
+        answer.phrase = "el cafe"  # type: ignore[misc]  # mutation is what this test refutes
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_memory_answer_grammar.py -q -p no:cacheprovider`
  Expected RED: `ImportError: cannot import name 'MemoryAnswer' from 'server.cognition.intent_resolution'`.
- [ ] **Step 3: Implement:**

```diff
diff --git a/server/src/server/cognition/intent_resolution.py b/server/src/server/cognition/intent_resolution.py
--- a/server/src/server/cognition/intent_resolution.py
+++ b/server/src/server/cognition/intent_resolution.py
@@ -16,7 +16,13 @@ from pydantic import BaseModel, ConfigDict

 from server.cognition.response_plan import InformationNeed

-__all__ = ["IntentMatch", "IntentResolution", "resolve_information_need"]
+__all__ = [
+    "IntentMatch",
+    "IntentResolution",
+    "MemoryAnswer",
+    "parse_memory_answer",
+    "resolve_information_need",
+]


 class IntentMatch(StrEnum):
@@ -37,8 +43,67 @@ class IntentResolution(BaseModel):
     rule_id: str | None


+class MemoryAnswer(BaseModel):
+    """A spoken answer to a memory offer: accept or reject, and the value it names.
+
+    Attributes:
+        accept: ``True`` for «sí, autorizo guardar …», ``False`` for «no autorizo guardar …».
+        phrase: The value the answer repeats, folded (lower case, no accents); the memory
+            layer compares it with the offered candidate. Never logged.
+    """
+
+    model_config = ConfigDict(frozen=True, extra="forbid")
+
+    accept: bool
+    phrase: str
+
+
 _NON_WORD_RUN = re.compile(r"[^\w]+", re.UNICODE)

+# The closed answer grammar (Plan 0063, Pipec's option A): a closed verb **and** the value. A bare
+# «sí» or a verb alone is never an answer, so a phrase known in advance promotes nothing. The
+# verbs are neutral Spanish (tuteo): Pipec lives in Santiago de Chile.
+# Words that may open an answer: a call to the robot, a repeated «sí», «claro».
+_ANSWER_OPENERS = frozenset({"iroko", "oye", "bueno", "ok", "claro", "si"})
+_ANSWER_ACCEPT_PREFIXES = (
+    "autorizo que guardes",
+    "apruebo que guardes",
+    "autorizo a guardar",
+    "apruebo a guardar",
+    "autorizo guardar",
+    "apruebo guardar",
+    "guardalo",
+    "guarda",
+    "autorizo",
+    "apruebo",
+)
+_ANSWER_REJECT_PREFIXES = (
+    "no autorizo que guardes",
+    "no apruebo que guardes",
+    "no autorizo a guardar",
+    "no apruebo a guardar",
+    "no autorizo guardar",
+    "no apruebo guardar",
+    "no lo guardes",
+    "no guardes",
+    "no autorizo",
+    "no apruebo",
+    "olvidalo",
+    "borralo",
+)
+# Short verbs that ordinary speech also uses («guarda silencio», «olvídalo, no importa», «bórralo
+# todo»): after one of them the value must start with an article, as a spoken taste usually does.
+_ANSWER_SHORT_PREFIXES = frozenset(
+    {"guardalo", "guarda", "no lo guardes", "no guardes", "olvidalo", "borralo"}
+)
+_ANSWER_ARTICLES = frozenset({"el", "la", "los", "las", "un", "una", "unos", "unas", "lo"})
+# Courtesy words a speaker adds after the value; they are not part of it.
+_ANSWER_TRAILERS = ("por favor", "gracias", "porfa")
+# The value is a noun phrase of at most five words plus its article.
+_MAX_ANSWER_PHRASE_WORDS = 6
+# Words that continue the verb rather than start the value («autorizo guardar», «que guardes»).
+_ANSWER_CONNECTORS = frozenset({"guardar", "que"})
+
 _POSSESSIVES = frozenset(
     {"mi", "mis", "tu", "tus", "su", "sus", "nuestro", "nuestra", "nuestros", "nuestras"}
 )
@@ -320,6 +385,67 @@ def _relationship_rule(normalized: str) -> IntentResolution | None:
     return None


+def parse_memory_answer(message: str) -> MemoryAnswer | None:
+    """Read a spoken answer to a memory offer, or say that *message* is not one.
+
+    Pure and closed (ADR 0021 decision 9): optional openers («Iroko», «sí, claro»), then one
+    closed verb, then the value, then optional courtesy words. Rejections are tried first, so
+    «no autorizo …» never reads as «autorizo …»; a repeated «no, no» is one «no».
+
+    Args:
+        message: Raw transcript or chat text in Spanish.
+
+    Returns:
+        The answer and the folded value it repeats, or ``None`` when the message has no closed
+        verb, no value, or a value longer than a short noun phrase.
+    """
+    words = normalize_spanish(message).split()
+    while words and words[0] in _ANSWER_OPENERS:
+        words.pop(0)
+    while words[:2] == ["no", "no"]:
+        words.pop(0)
+    text = _without_trailers(" ".join(words))
+    for prefixes, accept in ((_ANSWER_REJECT_PREFIXES, False), (_ANSWER_ACCEPT_PREFIXES, True)):
+        for prefix in prefixes:
+            if text.startswith(f"{prefix} "):
+                return _answer(prefix, text[len(prefix) :].split(), accept=accept)
+    return None
+
+
+def _without_trailers(text: str) -> str:
+    """Drop the courtesy words a speaker adds after the value («…, gracias»)."""
+    trimmed = True
+    while trimmed:
+        trimmed = False
+        for trailer in _ANSWER_TRAILERS:
+            if text.endswith(f" {trailer}"):
+                text = text[: -len(trailer) - 1]
+                trimmed = True
+    return text
+
+
+def _answer(prefix: str, phrase: list[str], *, accept: bool) -> MemoryAnswer | None:
+    """Return the answer when *phrase* is a value, or ``None``."""
+    # «autorizo guardar» with nothing after it is a verb, not a value; «autorizo a guardar el
+    # mate» names it.
+    if phrase[:2] == ["a", "guardar"]:
+        phrase = phrase[2:]
+    if not phrase or phrase[0] in _ANSWER_CONNECTORS or len(phrase) > _MAX_ANSWER_PHRASE_WORDS:
+        return None
+    if prefix in _ANSWER_SHORT_PREFIXES and phrase[0] not in _ANSWER_ARTICLES:
+        return None
+    return MemoryAnswer(accept=accept, phrase=" ".join(phrase))
+
+
+def _memory_answer_rule(normalized: str) -> IntentResolution | None:
+    """Recognize the closed shape of an answer to a memory offer (value included)."""
+    if parse_memory_answer(normalized) is not None:
+        return _resolution(InformationNeed.MEMORY_ANSWER, IntentMatch.EXACT, "memory.answer.v1")
+    return None
+
+
+# Order matters: every protected, dated or identity rule runs before the answer shape, so an
+# answer can never reach a protected branch's data and a protected question is never an answer.
 _RULES: tuple[Callable[[str], IntentResolution | None], ...] = (
     _own_children_list_rule,
     _own_children_count_rule,
@@ -332,6 +458,7 @@ _RULES: tuple[Callable[[str], IntentResolution | None], ...] = (
     _explicit_age_rule,
     _relationship_rule,
     _scene_description_rule,
+    _memory_answer_rule,
 )


diff --git a/server/src/server/cognition/response_plan.py b/server/src/server/cognition/response_plan.py
--- a/server/src/server/cognition/response_plan.py
+++ b/server/src/server/cognition/response_plan.py
@@ -41,6 +41,8 @@ class InformationNeed(StrEnum):
     SCENE_DESCRIPTION = "scene_description"
     ACTIVE_IDENTITY = "active_identity"
     BIOMETRIC_ENROLLMENT = "biometric_enrollment"
+    # A spoken answer to a memory offer: a closed verb and the offered value (ADR 0021 §9).
+    MEMORY_ANSWER = "memory_answer"


 class ResponseSource(StrEnum):
```

- [ ] **Step 4: Run to see them pass, then lint and types.** Also
  `uv run pytest tests/unit/test_intent_resolution.py tests/unit/test_cognitive_controller.py -q -p no:cacheprovider`
  (the reviewed corpus and every existing rule are unchanged).
- [ ] **Step 5: Commit** `feat(server): parse the spoken answer to a memory offer (plan 0063)`; check `git log -1`.

---

## Task 3: The store's readers

**Files:**
- Modify: `server/src/server/memory/candidates.py`
- Test: modified `tests/integration/test_memory_candidates_store.py`

**Interfaces:**
- Produces (read-only, no housekeeping, all `None`/`False` with the switch off):
  `next_offerable(subject_person_id, *, now) -> Candidate | None` (oldest first; an offer past its
  window counts; nothing while one of that person's offers waits for its answer);
  `still_offerable(candidate_id, subject_person_id, *, now) -> bool`;
  `find_offered(subject_person_id, value_key, *, now) -> Candidate | None` (the open offer inside
  its window).

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/tests/integration/test_memory_candidates_store.py b/tests/integration/test_memory_candidates_store.py
--- a/tests/integration/test_memory_candidates_store.py
+++ b/tests/integration/test_memory_candidates_store.py
@@ -593,3 +593,150 @@ async def test_the_insert_is_logged_before_a_failing_checkpoint_and_names_its_tu
     events = [r for r in caplog.records if getattr(r, "event", "") == "candidate.insert"]
     assert len(events) == 1
     assert getattr(events[0], "correlation_id", None) == str(turn)
+
+
+# --- the dialogue's readers (Plan 0063, ADR 0021 decision 9) ---------------------------------
+
+
+@pytest.mark.usefixtures("store")
+async def test_the_oldest_proposed_candidate_of_that_person_is_the_one_offered() -> None:
+    owner = await _person()
+    visitor = await _person("Canary Visitor")
+    await _insert(visitor, _proposal("el rock", "rock"), now=_T0 - timedelta(minutes=5))
+    first = await _insert(owner, _proposal("el mate", "mate"), now=_T0)
+    await _insert(owner, _proposal("el jazz", "jazz"), now=_T0 + timedelta(minutes=1))
+
+    chosen = await candidates.next_offerable(owner, now=_T0 + timedelta(minutes=2))
+
+    assert chosen is not None
+    assert chosen.id == first.candidate_id
+    assert chosen.subject_person_id == owner
+
+
+@pytest.mark.usefixtures("store")
+async def test_nothing_is_offerable_when_lapsed_used_up_offered_or_switched_off(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    owner = await _person()
+    stored = await _insert(owner)
+    assert stored.candidate_id is not None
+    later = _T0 + timedelta(seconds=settings.memory_candidate_ttl_seconds + 1)
+
+    assert await candidates.next_offerable(owner, now=later) is None
+    assert await candidates.mark_offered(
+        stored.candidate_id, owner, correlation_id=uuid4(), now=_T0
+    )
+    assert await candidates.next_offerable(owner, now=_T0) is None
+    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
+    assert await candidates.next_offerable(owner, now=_T0) is None
+
+
+@pytest.mark.usefixtures("store")
+async def test_a_candidate_offered_as_often_as_allowed_is_not_offered_again(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    monkeypatch.setattr(settings, "memory_candidate_max_offers", 1)
+    owner = await _person()
+    stored = await _insert(owner)
+    assert stored.candidate_id is not None
+    assert await candidates.mark_offered(
+        stored.candidate_id, owner, correlation_id=uuid4(), now=_T0
+    )
+    answer_window = timedelta(seconds=settings.memory_candidate_answer_seconds + 1)
+
+    assert await candidates.next_offerable(owner, now=_T0 + answer_window) is None
+
+
+@pytest.mark.usefixtures("store")
+async def test_an_unanswered_offer_is_offerable_again_once_its_window_closed() -> None:
+    owner = await _person()
+    stored = await _insert(owner)
+    assert stored.candidate_id is not None
+    assert await candidates.mark_offered(
+        stored.candidate_id, owner, correlation_id=uuid4(), now=_T0
+    )
+    after_window = _T0 + timedelta(seconds=settings.memory_candidate_answer_seconds + 1)
+
+    again = await candidates.next_offerable(owner, now=after_window)
+
+    assert again is not None
+    assert again.id == stored.candidate_id
+    assert await candidates.mark_offered(
+        stored.candidate_id, owner, correlation_id=uuid4(), now=after_window
+    )
+
+
+@pytest.mark.usefixtures("store")
+async def test_an_answer_finds_only_that_persons_open_offer_with_that_key() -> None:
+    owner = await _person()
+    visitor = await _person("Canary Visitor")
+    mine = await _insert(owner, _proposal("el mate", "mate"))
+    theirs = await _insert(visitor, _proposal("el mate", "mate"))
+    assert mine.candidate_id is not None
+    assert theirs.candidate_id is not None
+    for candidate_id, person in ((mine.candidate_id, owner), (theirs.candidate_id, visitor)):
+        assert await candidates.mark_offered(candidate_id, person, correlation_id=uuid4(), now=_T0)
+    soon = _T0 + timedelta(seconds=10)
+
+    found = await candidates.find_offered(owner, "mate", now=soon)
+
+    assert found is not None
+    assert found.id == mine.candidate_id
+    assert await candidates.find_offered(owner, "jazz", now=soon) is None
+
+
+@pytest.mark.usefixtures("store")
+async def test_an_offer_past_its_answer_window_or_not_yet_made_is_not_answerable(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    owner = await _person()
+    stored = await _insert(owner)
+    assert stored.candidate_id is not None
+
+    assert await candidates.find_offered(owner, "mate", now=_T0) is None
+    assert await candidates.mark_offered(
+        stored.candidate_id, owner, correlation_id=uuid4(), now=_T0
+    )
+    late = _T0 + timedelta(seconds=settings.memory_candidate_answer_seconds + 1)
+    assert await candidates.find_offered(owner, "mate", now=late) is None
+    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
+    assert await candidates.find_offered(owner, "mate", now=_T0) is None
+
+
+@pytest.mark.usefixtures("store")
+async def test_nothing_else_is_offered_while_an_offer_waits_for_its_answer() -> None:
+    owner = await _person()
+    first = await _insert(owner, _proposal("el mate", "mate"), now=_T0)
+    await _insert(owner, _proposal("el jazz", "jazz"), now=_T0 + timedelta(seconds=1))
+    assert first.candidate_id is not None
+    assert await candidates.mark_offered(
+        first.candidate_id, owner, correlation_id=uuid4(), now=_T0 + timedelta(seconds=2)
+    )
+
+    waiting = _T0 + timedelta(seconds=10)
+    assert await candidates.next_offerable(owner, now=waiting) is None
+    window_closed = _T0 + timedelta(seconds=settings.memory_candidate_answer_seconds + 3)
+    again = await candidates.next_offerable(owner, now=window_closed)
+    assert again is not None
+    assert again.id == first.candidate_id
+
+
+@pytest.mark.usefixtures("store")
+async def test_still_offerable_says_whether_the_compare_and_set_can_win(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    owner = await _person()
+    visitor = await _person("Canary Visitor")
+    stored = await _insert(owner)
+    assert stored.candidate_id is not None
+    candidate_id = stored.candidate_id
+
+    assert await candidates.still_offerable(candidate_id, owner, now=_T0)
+    assert not await candidates.still_offerable(candidate_id, visitor, now=_T0)
+    lapsed = _T0 + timedelta(seconds=settings.memory_candidate_ttl_seconds + 1)
+    assert not await candidates.still_offerable(candidate_id, owner, now=lapsed)
+    assert await candidates.mark_offered(candidate_id, owner, correlation_id=uuid4(), now=_T0)
+    assert not await candidates.still_offerable(candidate_id, owner, now=_T0)
+    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
+    window_closed = _T0 + timedelta(seconds=settings.memory_candidate_answer_seconds + 1)
+    assert not await candidates.still_offerable(candidate_id, owner, now=window_closed)
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/integration/test_memory_candidates_store.py -q -p no:cacheprovider`
  Expected RED: `AttributeError: module 'server.memory.candidates' has no attribute 'next_offerable'`
  (and `find_offered`, `still_offerable`) in the eight new tests.
- [ ] **Step 3: Implement:**

```diff
diff --git a/server/src/server/memory/candidates.py b/server/src/server/memory/candidates.py
--- a/server/src/server/memory/candidates.py
+++ b/server/src/server/memory/candidates.py
@@ -49,15 +49,18 @@ __all__ = [
     "InsertStatus",
     "checkpoint_after_scrub",
     "expire_lapsed_in_transaction",
+    "find_offered",
     "get_candidate",
     "insert_candidate",
     "iso_utc",
     "mark_offered",
+    "next_offerable",
     "precheck_insert",
     "reset_for_startup",
     "resolve_candidate",
     "resolve_candidate_in_transaction",
     "run_housekeeping",
+    "still_offerable",
     "void_live_candidates",
 ]

@@ -411,6 +414,114 @@ async def get_candidate_in_transaction(
     return _from_row(tuple(row)) if row is not None else None


+_OFFERABLE_SQL = (
+    "subject_person_id = ? "
+    "AND (status = 'proposed' OR (status = 'offered' AND offered_at <= ?)) "
+    "AND expires_at > ? AND offer_count < ? "
+    # One open offer per person: while an answer to one may still come, nothing else is
+    # offered, so an answer always names the offer it resolves.
+    "AND NOT EXISTS (SELECT 1 FROM memory_candidates AS open WHERE "
+    "open.subject_person_id = memory_candidates.subject_person_id "
+    "AND open.status = 'offered' AND open.offered_at > ?)"
+)
+
+
+def _offerable_args(subject_person_id: int, now: datetime) -> tuple[object, ...]:
+    """The parameters of ``_OFFERABLE_SQL`` for one person at *now*."""
+    waited_since = iso_utc(now - timedelta(seconds=settings.memory_candidate_answer_seconds))
+    return (
+        subject_person_id,
+        waited_since,
+        iso_utc(now),
+        settings.memory_candidate_max_offers,
+        waited_since,
+    )
+
+
+async def next_offerable(subject_person_id: int, *, now: datetime) -> Candidate | None:
+    """Return the subject's oldest candidate that may be offered now, without writing.
+
+    Read-only, like every reader of this store: housekeeping runs on the write entry that
+    follows (``mark_offered``), so an offer whose answer window has closed counts as offerable
+    here and is returned to ``proposed`` there before the compare-and-set. While one offer of
+    that person still waits for its answer, nothing is offerable.
+
+    Args:
+        subject_person_id: Whose candidate; another person's is never returned.
+        now: The caller's clock reading.
+
+    Returns:
+        The oldest live candidate of that person that has not lapsed and has offers left, or
+        ``None`` (also with the kill-switch off).
+    """
+    if not settings.memory_candidates_enabled:
+        return None
+    cursor = await db.get_conn().execute(
+        f"SELECT {_COLUMNS} FROM memory_candidates WHERE {_OFFERABLE_SQL} "  # noqa: S608
+        "ORDER BY proposed_at, id LIMIT 1",
+        _offerable_args(subject_person_id, now),
+    )
+    row = await cursor.fetchone()
+    await cursor.close()
+    return _from_row(tuple(row)) if row is not None else None
+
+
+async def still_offerable(candidate_id: int, subject_person_id: int, *, now: datetime) -> bool:
+    """Say, without writing, whether one candidate may still be offered now.
+
+    Asked right before the policy's read step is audited, so the audit log does not say
+    "allowed" for an offer the compare-and-set was always going to lose (another turn offered
+    it, it lapsed during generation). It is advisory: ``mark_offered`` decides again.
+
+    Args:
+        candidate_id: The candidate the offer was prepared for.
+        subject_person_id: Whose it is.
+        now: The caller's clock reading.
+
+    Returns:
+        ``True`` when it is still offerable for that person; ``False`` otherwise or with the
+        kill-switch off.
+    """
+    if not settings.memory_candidates_enabled:
+        return False
+    cursor = await db.get_conn().execute(
+        f"SELECT 1 FROM memory_candidates WHERE id = ? AND {_OFFERABLE_SQL}",  # noqa: S608
+        (candidate_id, *_offerable_args(subject_person_id, now)),
+    )
+    row = await cursor.fetchone()
+    await cursor.close()
+    return row is not None
+
+
+async def find_offered(
+    subject_person_id: int, value_key: str, *, now: datetime
+) -> Candidate | None:
+    """Return the subject's open offer with *value_key*, the one an answer may resolve.
+
+    Args:
+        subject_person_id: Whose offer; another person's is never returned.
+        value_key: The comparison key of the value the answer repeated.
+        now: The caller's clock reading.
+
+    Returns:
+        The ``offered`` candidate of that person with that key, still inside its answer window
+        and not lapsed, or ``None`` (also with the kill-switch off).
+    """
+    if not settings.memory_candidates_enabled:
+        return None
+    stamp = iso_utc(now)
+    waited_since = iso_utc(now - timedelta(seconds=settings.memory_candidate_answer_seconds))
+    cursor = await db.get_conn().execute(
+        f"SELECT {_COLUMNS} FROM memory_candidates WHERE subject_person_id = ? "  # noqa: S608
+        "AND status = 'offered' AND value_key = ? AND offered_at > ? AND expires_at > ? "
+        "ORDER BY offered_at DESC, id LIMIT 1",
+        (subject_person_id, value_key, waited_since, stamp),
+    )
+    row = await cursor.fetchone()
+    await cursor.close()
+    return _from_row(tuple(row)) if row is not None else None
+
+
 async def mark_offered(
     candidate_id: int, subject_person_id: int, *, correlation_id: UUID, now: datetime
 ) -> bool:
```

- [ ] **Step 4: Run to see them pass, then lint and types.**
- [ ] **Step 5: Commit** `feat(server): read the offerable and the offered candidate (plan 0063)`; check `git log -1`.

---

## Task 4: The dialogue: prepare, commit and answer

**Files:**
- Create: `server/src/server/memory/candidate_dialogue.py`
- Modify: `server/src/server/memory/lexicon.py`, `server/src/server/cognition/strong_actor.py`, `server/src/server/memory/candidate_proposal.py`
- Test: new `tests/integration/test_candidate_dialogue.py`; modified `tests/unit/test_architecture_guards.py`

**Interfaces:**
- Consumes: Tasks 2 and 3; `authorize_step` (`READ`, `CONFIRM`), `mark_offered`,
  `resolve_candidate`, `promote`, `comparison_key`, `verify_face_and_voice`.
- Produces: `PendingOffer(candidate_id, subject_person_id, phrase, actor, correlation_id)`;
  `OfferPreparer = Callable[[ActivePersonContext], Awaitable[PendingOffer | None]]`;
  `compose_offer(predicate, value_text) -> str`; `async prepare_offer(actor, *, wav_bytes, event,
  verify=verify_face_and_voice, clock=utc_now) -> PendingOffer | None`; `async commit_offer(offer,
  *, now=None, policy=..., audit=...) -> str | None`; `async answer_offer(answer, *, actor,
  correlation_id, now, policy=..., audit=...) -> str | None`; the three result phrases; the offer
  templates in `lexicon` (`OFFER_STATEMENTS`, `OFFER_QUESTION`, `PLURAL_ARTICLES`,
  `OFFER_VERB_SINGULAR`, `OFFER_VERB_PLURAL`, `ANSWER_*_PHRASE`); `strong_actor.VoiceVerifier`.
  None of the three functions ever raises: a failure is logged by its class and changes nothing.
  The caller guards admit `memory/candidate_dialogue.py` as a mover of candidates and a caller of
  `promote` (a decision, not an accident).

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/tests/integration/test_candidate_dialogue.py b/tests/integration/test_candidate_dialogue.py
new file mode 100644
--- /dev/null
+++ b/tests/integration/test_candidate_dialogue.py
@@ -0,0 +1,662 @@
+"""The spoken offer and the explicit answer (ADR 0021 decision 9, Plan 0063).
+
+Every offer, answer and promotion needs the face and the voice of the same person on the
+turn's own clip and never a token; anything else falls through to ordinary generation, so the
+callers here return ``None`` and change nothing.
+"""
+
+from __future__ import annotations
+
+from datetime import UTC, datetime, timedelta
+import logging
+from typing import TYPE_CHECKING
+from unittest.mock import AsyncMock
+from uuid import UUID, uuid4
+
+import pytest
+from server.cognition.identity import (
+    ActivePersonContext,
+    HouseholdRole,
+    IdentityEvidence,
+    IdentityEvidenceSource,
+    PersonRecord,
+    resolve_active_person,
+)
+from server.cognition.intent_resolution import MemoryAnswer, parse_memory_answer
+from server.cognition.models import (
+    AuthorizationAction,
+    AuthorizationDecision,
+    CognitiveEvent,
+    Confidence,
+    ConfidenceBasis,
+)
+from server.cognition.response_plan import TextTurnPayload
+from server.memory import candidate_dialogue, candidates
+from server.memory.candidate_classifier import comparison_key
+from server.memory.candidate_dialogue import (
+    ANSWER_CONTRADICTION_PHRASE,
+    ANSWER_REJECTED_PHRASE,
+    ANSWER_SAVED_PHRASE,
+    PendingOffer,
+    answer_offer,
+    commit_offer,
+    compose_offer,
+    prepare_offer,
+)
+from server.memory.candidate_types import CandidateChannel, CandidateStatus, ProposedCandidate
+from server.memory.declarative import upsert_entity
+from server.memory.predicate_registry import resolve_predicate
+from server.memory.relational_v4 import assert_literal_fact, get_active_literal_facts
+from server.settings import settings
+
+from server import db
+
+if TYPE_CHECKING:
+    from collections.abc import AsyncIterator
+    from pathlib import Path
+
+    from server.cognition.authorization import AuthorizationRequest
+
+pytestmark = pytest.mark.integration
+
+_NOW = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)
+_WAV = b"RIFF-canary-clip"
+_TURN = UUID(int=6363)
+
+
+def _evidence(source: IdentityEvidenceSource, person_id: int) -> IdentityEvidence:
+    token = source is IdentityEvidenceSource.LOCAL_UNLOCK
+    return IdentityEvidence(
+        evidence_id=uuid4(),
+        source=source,
+        candidate_person_id=person_id,
+        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
+        observed_at=_NOW - timedelta(seconds=1),
+        reference="canary",
+        expires_at=_NOW + timedelta(minutes=5) if token else None,
+        grant_scope="personal_protected_read" if token else None,
+        grant_spent=token,
+    )
+
+
+def _actor(person_id: int, *sources: IdentityEvidenceSource) -> ActivePersonContext:
+    sources = sources or (IdentityEvidenceSource.FACE,)
+    person = PersonRecord(person_id=person_id, display_name="Canary", entity_type="person")
+    return resolve_active_person(
+        evidence=tuple(_evidence(s, person_id) for s in sources),
+        lookup_person=lambda pid: person if pid == person_id else None,
+        lookup_role=lambda _pid: HouseholdRole.OWNER,
+        clock=lambda: _NOW,
+    )
+
+
+def _strong(person_id: int) -> ActivePersonContext:
+    return _actor(person_id, IdentityEvidenceSource.FACE, IdentityEvidenceSource.VOICE)
+
+
+def _event() -> CognitiveEvent[TextTurnPayload]:
+    return CognitiveEvent(
+        event_id=uuid4(),
+        schema_version=1,
+        event_type="text.turn",
+        occurred_at=_NOW,
+        recorded_at=_NOW,
+        source="audio.transcribe",
+        correlation_id=_TURN,
+        causation_id=None,
+        subject_id=None,
+        payload=TextTurnPayload(message="canary", conversation_id="canary"),
+    )
+
+
+@pytest.fixture
+async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
+    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "dialogue.db")
+    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
+    db._conn = None
+    await db.open_db()
+    await db.run_migrations()
+    yield await upsert_entity(name="Canary Owner", type="person")
+    await db.close_db()
+    db._conn = None
+
+
+async def _candidate(
+    person_id: int,
+    value: str = "el mate",
+    key: str = "mate",
+    predicate: str = "likes",
+    *,
+    offered: bool = False,
+) -> int:
+    result = await candidates.insert_candidate(
+        ProposedCandidate(predicate=predicate, value_text=value, value_key=key),
+        subject_person_id=person_id,
+        asserted_by_person_id=person_id,
+        channel=CandidateChannel.VOICE_STREAM,
+        correlation_id=uuid4(),
+        now=_NOW - timedelta(minutes=5),
+    )
+    assert result.candidate_id is not None
+    if offered:
+        assert await candidates.mark_offered(
+            result.candidate_id, person_id, correlation_id=uuid4(), now=_NOW
+        )
+    return result.candidate_id
+
+
+async def _status(candidate_id: int) -> CandidateStatus:
+    stored = await candidates.get_candidate(candidate_id)
+    assert stored is not None
+    return stored.status
+
+
+async def _likes(person_id: int) -> list[object]:
+    definition = resolve_predicate("likes")
+    assert definition is not None
+    return list(await get_active_literal_facts(subject_entity_id=person_id, definition=definition))
+
+
+def _actions(audit: AsyncMock) -> list[tuple[AuthorizationAction, str]]:
+    calls: list[tuple[AuthorizationAction, str]] = []
+    for call in audit.await_args_list:
+        request: AuthorizationRequest = call.args[0]
+        decision: AuthorizationDecision = call.args[1]
+        calls.append((request.action, decision.decision.value))
+    return calls
+
+
+# --- the phrase ------------------------------------------------------------------------------
+
+
+@pytest.mark.parametrize(
+    "predicate, value, expected",
+    [
+        (
+            "likes",
+            "el mate",
+            "Antes me dijiste que te gusta el mate. ¿Quieres que lo guarde? "
+            "Dime: sí, autorizo guardar el mate.",
+        ),
+        (
+            "likes",
+            "las empanadas",
+            "Antes me dijiste que te gustan las empanadas. ¿Quieres que lo guarde? "
+            "Dime: sí, autorizo guardar las empanadas.",
+        ),
+        (
+            "dislikes",
+            "el cilantro",
+            "Antes me dijiste que no te gusta el cilantro. ¿Quieres que lo guarde? "
+            "Dime: sí, autorizo guardar el cilantro.",
+        ),
+        (
+            "prefers",
+            "el té",
+            "Antes me dijiste que prefieres el té. ¿Quieres que lo guarde? "
+            "Dime: sí, autorizo guardar el té.",
+        ),
+    ],
+)
+def test_the_offer_is_neutral_spanish_and_tells_the_exact_answer(
+    predicate: str, value: str, expected: str
+) -> None:
+    assert compose_offer(predicate, value) == expected
+
+
+@pytest.mark.parametrize(
+    "value", ["el mate", "lo picante", "las empanadas", "bailar", "el café con leche"]
+)
+def test_the_answer_the_offer_asks_for_resolves_that_offer(value: str) -> None:
+    """Round trip: the words the robot tells the owner to say parse back to the same key."""
+    offer = compose_offer("likes", value)
+    instructed = offer.split("Dime: ", 1)[1]
+
+    answer = parse_memory_answer(instructed)
+
+    assert answer is not None
+    assert answer.accept
+    assert comparison_key(answer.phrase) == comparison_key(value)
+
+
+def test_an_unknown_predicate_has_no_offer() -> None:
+    with pytest.raises(ValueError, match="no offer"):
+        compose_offer("lives_in", "la costa")
+
+
+# --- preparing an offer (concurrently with generation) --------------------------------------
+
+
+async def test_the_oldest_candidate_is_prepared_with_the_voice_of_the_same_person(
+    owner: int,
+) -> None:
+    first = await _candidate(owner)
+    await _candidate(owner, "el jazz", "jazz")
+    verify = AsyncMock(return_value=_strong(owner))
+
+    offer = await prepare_offer(
+        _actor(owner), wav_bytes=_WAV, event=_event(), verify=verify, clock=lambda: _NOW
+    )
+
+    assert offer is not None
+    assert (offer.candidate_id, offer.subject_person_id) == (first, owner)
+    assert offer.correlation_id == _TURN
+    assert "el mate" in offer.phrase
+    verify.assert_awaited_once()
+    assert verify.await_args is not None
+    assert verify.await_args.kwargs["wav_bytes"] == _WAV
+    assert await _status(first) is CandidateStatus.PROPOSED
+
+
+async def test_no_candidate_means_no_voice_check_at_all(owner: int) -> None:
+    verify = AsyncMock(return_value=_strong(owner))
+
+    offer = await prepare_offer(
+        _actor(owner), wav_bytes=_WAV, event=_event(), verify=verify, clock=lambda: _NOW
+    )
+
+    assert offer is None
+    verify.assert_not_awaited()
+
+
+@pytest.mark.parametrize(
+    "sources",
+    [
+        (IdentityEvidenceSource.LOCAL_UNLOCK,),
+        (IdentityEvidenceSource.FACE, IdentityEvidenceSource.LOCAL_UNLOCK),
+        (IdentityEvidenceSource.MANUAL,),
+    ],
+)
+async def test_a_token_or_a_manual_actor_is_never_offered_anything(
+    owner: int, sources: tuple[IdentityEvidenceSource, ...]
+) -> None:
+    await _candidate(owner)
+    verify = AsyncMock(return_value=_strong(owner))
+
+    offer = await prepare_offer(
+        _actor(owner, *sources), wav_bytes=_WAV, event=_event(), verify=verify
+    )
+
+    assert offer is None
+    verify.assert_not_awaited()
+
+
+async def test_a_voice_that_is_not_verified_is_offered_nothing(owner: int) -> None:
+    await _candidate(owner)
+
+    offer = await prepare_offer(
+        _actor(owner), wav_bytes=_WAV, event=_event(), verify=AsyncMock(return_value=None)
+    )
+
+    assert offer is None
+
+
+async def test_the_switch_off_prepares_nothing(owner: int, monkeypatch: pytest.MonkeyPatch) -> None:
+    await _candidate(owner)
+    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
+    verify = AsyncMock(return_value=_strong(owner))
+
+    assert await prepare_offer(_actor(owner), wav_bytes=_WAV, event=_event(), verify=verify) is None
+    verify.assert_not_awaited()
+
+
+async def test_a_failing_preparation_never_raises_and_never_logs_its_message(
+    owner: int, caplog: pytest.LogCaptureFixture
+) -> None:
+    await _candidate(owner)
+    verify = AsyncMock(side_effect=RuntimeError("zumo de pomelo"))
+
+    with caplog.at_level(logging.DEBUG):
+        offer = await prepare_offer(_actor(owner), wav_bytes=_WAV, event=_event(), verify=verify)
+
+    assert offer is None
+    assert "pomelo" not in caplog.text
+    assert "RuntimeError" in caplog.text
+
+
+# --- committing an offer (after the reply was built) ----------------------------------------
+
+
+def _pending(candidate_id: int, owner: int) -> PendingOffer:
+    return PendingOffer(
+        candidate_id=candidate_id,
+        subject_person_id=owner,
+        phrase=compose_offer("likes", "el mate"),
+        actor=_strong(owner),
+        correlation_id=_TURN,
+    )
+
+
+async def test_the_read_is_audited_before_the_candidate_becomes_offered(owner: int) -> None:
+    candidate_id = await _candidate(owner)
+    seen: list[CandidateStatus] = []
+
+    async def audit(_request: AuthorizationRequest, _decision: AuthorizationDecision) -> None:
+        seen.append(await _status(candidate_id))
+
+    phrase = await commit_offer(_pending(candidate_id, owner), now=_NOW, audit=audit)
+
+    assert phrase == compose_offer("likes", "el mate")
+    assert seen == [CandidateStatus.PROPOSED]
+    stored = await candidates.get_candidate(candidate_id)
+    assert stored is not None
+    assert stored.status is CandidateStatus.OFFERED
+    assert stored.offer_correlation_id == str(_TURN)
+    assert stored.offer_count == 1
+
+
+async def test_a_failing_audit_speaks_nothing_and_offers_nothing(owner: int) -> None:
+    candidate_id = await _candidate(owner)
+
+    phrase = await commit_offer(
+        _pending(candidate_id, owner),
+        now=_NOW,
+        audit=AsyncMock(side_effect=RuntimeError("audit down")),
+    )
+
+    assert phrase is None
+    assert await _status(candidate_id) is CandidateStatus.PROPOSED
+
+
+async def test_an_offer_already_made_elsewhere_is_neither_audited_nor_spoken(owner: int) -> None:
+    """Another turn offered it first: no "allowed" row is written for an offer never spoken."""
+    candidate_id = await _candidate(owner, offered=True)
+    audit = AsyncMock()
+
+    assert await commit_offer(_pending(candidate_id, owner), now=_NOW, audit=audit) is None
+    audit.assert_not_awaited()
+
+
+async def test_a_voice_verified_for_another_person_is_offered_nothing(owner: int) -> None:
+    visitor = await upsert_entity(name="Canary Visitor", type="person")
+    await _candidate(owner)
+
+    offer = await prepare_offer(
+        _actor(owner),
+        wav_bytes=_WAV,
+        event=_event(),
+        verify=AsyncMock(return_value=_strong(visitor)),
+    )
+
+    assert offer is None
+
+
+async def test_the_read_audit_row_names_the_read_action(owner: int) -> None:
+    candidate_id = await _candidate(owner)
+    audit = AsyncMock()
+
+    await commit_offer(_pending(candidate_id, owner), now=_NOW, audit=audit)
+
+    assert _actions(audit) == [(AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY, "allowed")]
+
+
+# --- the answer --------------------------------------------------------------------------------
+
+
+async def test_yes_with_the_value_promotes_the_offer(owner: int) -> None:
+    candidate_id = await _candidate(owner, offered=True)
+    audit = AsyncMock()
+
+    phrase = await answer_offer(
+        MemoryAnswer(accept=True, phrase="el mate"),
+        actor=_strong(owner),
+        correlation_id=_TURN,
+        now=_NOW + timedelta(seconds=10),
+        audit=audit,
+    )
+
+    assert phrase == ANSWER_SAVED_PHRASE
+    stored = await candidates.get_candidate(candidate_id)
+    assert stored is not None
+    assert stored.status is CandidateStatus.CONFIRMED
+    assert stored.promoted_fact_id is not None
+    assert _actions(audit) == [(AuthorizationAction.CONFIRM_PERSONAL_MEMORY, "allowed")]
+
+
+async def test_no_with_the_value_rejects_it_after_auditing_the_confirm_step(owner: int) -> None:
+    candidate_id = await _candidate(owner, offered=True)
+    audit = AsyncMock()
+
+    phrase = await answer_offer(
+        MemoryAnswer(accept=False, phrase="el mate"),
+        actor=_strong(owner),
+        correlation_id=_TURN,
+        now=_NOW + timedelta(seconds=10),
+        audit=audit,
+    )
+
+    assert phrase == ANSWER_REJECTED_PHRASE
+    stored = await candidates.get_candidate(candidate_id)
+    assert stored is not None
+    assert stored.status is CandidateStatus.REJECTED
+    assert (stored.value_text, stored.value_key) == (None, None)
+    assert _actions(audit) == [(AuthorizationAction.CONFIRM_PERSONAL_MEMORY, "allowed")]
+    assert await _likes(owner) == []
+
+
+async def test_the_reject_is_audited_before_the_candidate_changes(owner: int) -> None:
+    candidate_id = await _candidate(owner, offered=True)
+    seen: list[CandidateStatus] = []
+
+    async def audit(_request: AuthorizationRequest, _decision: AuthorizationDecision) -> None:
+        seen.append(await _status(candidate_id))
+
+    phrase = await answer_offer(
+        MemoryAnswer(accept=False, phrase="el mate"),
+        actor=_strong(owner),
+        correlation_id=_TURN,
+        now=_NOW + timedelta(seconds=10),
+        audit=audit,
+    )
+
+    assert phrase == ANSWER_REJECTED_PHRASE
+    assert seen == [CandidateStatus.OFFERED]
+
+
+async def test_a_failing_audit_never_rejects(owner: int) -> None:
+    candidate_id = await _candidate(owner, offered=True)
+
+    phrase = await answer_offer(
+        MemoryAnswer(accept=False, phrase="el mate"),
+        actor=_strong(owner),
+        correlation_id=_TURN,
+        now=_NOW + timedelta(seconds=10),
+        audit=AsyncMock(side_effect=RuntimeError("audit down")),
+    )
+
+    assert phrase is None
+    stored = await candidates.get_candidate(candidate_id)
+    assert stored is not None
+    assert stored.status is CandidateStatus.OFFERED
+    assert stored.value_text == "el mate"
+
+
+async def test_a_contradiction_is_said_plainly_and_writes_nothing(owner: int) -> None:
+    definition = resolve_predicate("dislikes")
+    assert definition is not None
+    await assert_literal_fact(subject_entity_id=owner, definition=definition, value="el mate")
+    await _candidate(owner, offered=True)
+
+    phrase = await answer_offer(
+        MemoryAnswer(accept=True, phrase="el mate"),
+        actor=_strong(owner),
+        correlation_id=_TURN,
+        now=_NOW + timedelta(seconds=10),
+        audit=AsyncMock(),
+    )
+
+    assert phrase == ANSWER_CONTRADICTION_PHRASE
+    assert await _likes(owner) == []
+
+
+@pytest.mark.parametrize(
+    "answer",
+    [
+        MemoryAnswer(accept=True, phrase="el cafe"),
+        MemoryAnswer(accept=False, phrase="el cafe"),
+        MemoryAnswer(accept=True, phrase="el"),
+    ],
+)
+async def test_an_answer_with_another_value_falls_through_and_changes_nothing(
+    owner: int, answer: MemoryAnswer
+) -> None:
+    candidate_id = await _candidate(owner, offered=True)
+    audit = AsyncMock()
+
+    phrase = await answer_offer(
+        answer, actor=_strong(owner), correlation_id=_TURN, now=_NOW, audit=audit
+    )
+
+    assert phrase is None
+    assert await _status(candidate_id) is CandidateStatus.OFFERED
+    audit.assert_not_awaited()
+
+
+async def test_an_answer_with_no_offer_outstanding_falls_through(owner: int) -> None:
+    candidate_id = await _candidate(owner)
+    audit = AsyncMock()
+
+    phrase = await answer_offer(
+        MemoryAnswer(accept=True, phrase="el mate"),
+        actor=_strong(owner),
+        correlation_id=_TURN,
+        now=_NOW,
+        audit=audit,
+    )
+
+    assert phrase is None
+    assert await _status(candidate_id) is CandidateStatus.PROPOSED
+    audit.assert_not_awaited()
+
+
+@pytest.mark.parametrize(
+    "sources",
+    [
+        (IdentityEvidenceSource.FACE,),
+        (IdentityEvidenceSource.VOICE,),
+        (IdentityEvidenceSource.FACE, IdentityEvidenceSource.LOCAL_UNLOCK),
+        (
+            IdentityEvidenceSource.FACE,
+            IdentityEvidenceSource.VOICE,
+            IdentityEvidenceSource.LOCAL_UNLOCK,
+        ),
+    ],
+)
+async def test_a_weaker_or_token_actor_cannot_answer(
+    owner: int,
+    sources: tuple[IdentityEvidenceSource, ...],
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    """Refused before the store is read, so nothing depends on whether an offer exists."""
+    candidate_id = await _candidate(owner, offered=True)
+    audit = AsyncMock()
+    reader = AsyncMock(wraps=candidates.find_offered)
+    monkeypatch.setattr(candidate_dialogue, "find_offered", reader)
+
+    phrase = await answer_offer(
+        MemoryAnswer(accept=True, phrase="el mate"),
+        actor=_actor(owner, *sources),
+        correlation_id=_TURN,
+        now=_NOW,
+        audit=audit,
+    )
+
+    assert phrase is None
+    assert await _status(candidate_id) is CandidateStatus.OFFERED
+    audit.assert_not_awaited()
+    reader.assert_not_awaited()
+
+
+async def test_another_persons_offer_is_never_answered(owner: int) -> None:
+    visitor = await upsert_entity(name="Canary Visitor", type="person")
+    theirs = await _candidate(visitor, offered=True)
+
+    phrase = await answer_offer(
+        MemoryAnswer(accept=True, phrase="el mate"),
+        actor=_strong(owner),
+        correlation_id=_TURN,
+        now=_NOW,
+        audit=AsyncMock(),
+    )
+
+    assert phrase is None
+    assert await _status(theirs) is CandidateStatus.OFFERED
+
+
+async def test_an_answer_after_the_window_falls_through(owner: int) -> None:
+    candidate_id = await _candidate(owner, offered=True)
+    late = _NOW + timedelta(seconds=settings.memory_candidate_answer_seconds + 1)
+
+    phrase = await answer_offer(
+        MemoryAnswer(accept=True, phrase="el mate"),
+        actor=_strong(owner),
+        correlation_id=_TURN,
+        now=late,
+        audit=AsyncMock(),
+    )
+
+    assert phrase is None
+    assert await _status(candidate_id) is CandidateStatus.OFFERED
+
+
+async def test_the_switch_off_answers_nothing(owner: int, monkeypatch: pytest.MonkeyPatch) -> None:
+    candidate_id = await _candidate(owner, offered=True)
+    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
+
+    phrase = await answer_offer(
+        MemoryAnswer(accept=True, phrase="el mate"),
+        actor=_strong(owner),
+        correlation_id=_TURN,
+        now=_NOW,
+        audit=AsyncMock(),
+    )
+
+    assert phrase is None
+    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
+    assert await _status(candidate_id) is CandidateStatus.OFFERED
+
+
+async def test_a_failing_answer_falls_through_and_never_logs_its_message(
+    owner: int, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
+) -> None:
+    await _candidate(owner, offered=True)
+    monkeypatch.setattr(
+        candidate_dialogue, "promote", AsyncMock(side_effect=RuntimeError("zumo de pomelo"))
+    )
+
+    with caplog.at_level(logging.DEBUG):
+        phrase = await answer_offer(
+            MemoryAnswer(accept=True, phrase="el mate"),
+            actor=_strong(owner),
+            correlation_id=_TURN,
+            now=_NOW,
+            audit=AsyncMock(),
+        )
+
+    assert phrase is None
+    assert "pomelo" not in caplog.text
+    assert "RuntimeError" in caplog.text
+
+
+async def test_no_log_line_carries_the_value(owner: int, caplog: pytest.LogCaptureFixture) -> None:
+    candidate_id = await _candidate(owner, "el quokka", "quokka")
+
+    with caplog.at_level(logging.DEBUG):
+        offer = await prepare_offer(
+            _actor(owner),
+            wav_bytes=_WAV,
+            event=_event(),
+            verify=AsyncMock(return_value=_strong(owner)),
+        )
+        assert offer is not None
+        await commit_offer(offer, now=_NOW, audit=AsyncMock())
+        await answer_offer(
+            MemoryAnswer(accept=True, phrase="el quokka"),
+            actor=_strong(owner),
+            correlation_id=_TURN,
+            now=_NOW + timedelta(seconds=5),
+            audit=AsyncMock(),
+        )
+
+    assert await _status(candidate_id) is CandidateStatus.CONFIRMED
+    assert "quokka" not in caplog.text
diff --git a/tests/unit/test_architecture_guards.py b/tests/unit/test_architecture_guards.py
--- a/tests/unit/test_architecture_guards.py
+++ b/tests/unit/test_architecture_guards.py
@@ -485,13 +485,15 @@ def test_the_retired_memory_actions_exist_nowhere() -> None:
 # --- who may write or move a candidate (Plan 0062, ADR 0021 decisions 3 and 8) --------------
 # The firewall rule (face and voice of the same person on the turn's clip) is enforced by the
 # caller of the store, so the callers are pinned: a second caller must be a decision, not an
-# accident. Plan 0063 adds the dialogue module that offers and answers.
+# accident. Plan 0063 added the dialogue module, which offers, rejects and asks the writer.
 _CANDIDATE_INSERT_HOMES = frozenset({"memory/candidates.py", "memory/candidate_proposal.py"})
-_CANDIDATE_MOVE_HOMES = frozenset({"memory/candidates.py", "memory/memory_writer.py"})
+_CANDIDATE_MOVE_HOMES = frozenset(
+    {"memory/candidates.py", "memory/memory_writer.py", "memory/candidate_dialogue.py"}
+)
 _CANDIDATE_MOVES = frozenset(
     {"mark_offered", "resolve_candidate", "resolve_candidate_in_transaction"}
 )
-_WRITER_HOMES = frozenset({"memory/memory_writer.py"})
+_WRITER_HOMES = frozenset({"memory/memory_writer.py", "memory/candidate_dialogue.py"})


 @pytest.mark.unit
@@ -510,6 +512,7 @@ def test_the_candidate_caller_guards_detect_a_violation() -> None:
         "memory/candidate_proposal.py": "await insert_candidate(p)\n",
         "memory/memory_writer.py": "await resolve_candidate_in_transaction(c)\nawait promote(1)\n",
         "memory/other.py": "await promote(1)\n",
+        "memory/candidate_dialogue.py": "await mark_offered(1)\nawait promote(1)\n",
     }

     assert _outside(leak, _CANDIDATE_INSERT_HOMES, frozenset({"insert_candidate"})) == [
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/integration/test_candidate_dialogue.py tests/unit/test_architecture_guards.py -q -p no:cacheprovider`
  Expected RED: `ImportError: cannot import name 'candidate_dialogue' from 'server.memory'`.
- [ ] **Step 3: Implement:**

```diff
diff --git a/server/src/server/cognition/strong_actor.py b/server/src/server/cognition/strong_actor.py
--- a/server/src/server/cognition/strong_actor.py
+++ b/server/src/server/cognition/strong_actor.py
@@ -13,9 +13,9 @@ Audio contract: every clip is WAV, 16 000 Hz, mono, signed int16.

 from __future__ import annotations

-from collections.abc import Callable
+from collections.abc import Awaitable, Callable
 import logging
-from typing import TYPE_CHECKING
+from typing import TYPE_CHECKING, Protocol

 from server.cognition.clock import utc_now
 from server.cognition.identity import (
@@ -40,12 +40,31 @@ if TYPE_CHECKING:

 logger = logging.getLogger(__name__)

-__all__ = ["is_face_actor", "is_face_and_voice_actor", "verify_face_and_voice"]
+__all__ = [
+    "VoiceVerifier",
+    "is_face_actor",
+    "is_face_and_voice_actor",
+    "verify_face_and_voice",
+]

 type SpeakerBuilder = Callable[[bytes, int], SpeakerRequestResolver]
 type Clock = Callable[[], datetime]


+class VoiceVerifier(Protocol):
+    """The voice-check seam: ``verify_face_and_voice`` or a test double (same keywords)."""
+
+    def __call__(
+        self,
+        actor: ActivePersonContext,
+        *,
+        wav_bytes: bytes | None,
+        event: CognitiveEvent[TextTurnPayload],
+    ) -> Awaitable[ActivePersonContext | None]:
+        """Return the actor fused at ``strong``, or ``None`` when the voice was not verified."""
+        ...
+
+
 def _sources_of(actor: ActivePersonContext) -> set[IdentityEvidenceSource]:
     """Return the evidence sources that name the actor's own person id."""
     return {item.source for item in actor.evidence if item.candidate_person_id == actor.person_id}
diff --git a/server/src/server/memory/candidate_dialogue.py b/server/src/server/memory/candidate_dialogue.py
new file mode 100644
--- /dev/null
+++ b/server/src/server/memory/candidate_dialogue.py
@@ -0,0 +1,367 @@
+"""The spoken offer and the explicit answer (ADR 0021 decision 9, Plan 0063).
+
+A candidate the owner stated earlier is offered back on a later generic voice turn, and only an
+explicit answer that repeats the value resolves it. Both need the face **and** the voice of the
+same person on that turn's own clip and never a token (decision 3); anything else returns
+``None`` and the turn is the ordinary one, byte for byte, so whether an offer exists is never
+revealed to anybody else.
+
+* ``prepare_offer`` runs concurrently with generation: it reads the person's oldest offerable
+  candidate and, only when one waits, checks the voice of the turn's clip. It writes nothing.
+* ``commit_offer`` runs once the reply was built (never on a fallback): it asks the policy for
+  ``read_personal_conversation_memory`` (audited before the effect) and moves the candidate to
+  ``offered``. No claim is made that the offer was heard.
+* ``answer_offer`` is the controller's answer branch: a «sí» promotes through the one writer, a
+  «no» is audited as ``confirm_personal_memory`` and rejects the candidate.
+
+Audio contract for the clip: WAV, 16 000 Hz, mono, signed int16, held in memory only. Logs carry
+ids, a status and a closed outcome, never a value and never an exception's message.
+"""
+
+from __future__ import annotations
+
+from collections.abc import Awaitable, Callable
+from dataclasses import dataclass
+import logging
+from typing import TYPE_CHECKING
+
+from server.cognition.authorization import evaluate_authorization
+from server.cognition.clock import utc_now
+from server.cognition.strong_actor import (
+    VoiceVerifier,
+    is_face_actor,
+    is_face_and_voice_actor,
+    verify_face_and_voice,
+)
+from server.memory.candidate_classifier import comparison_key
+from server.memory.candidate_policy import CandidateStep, authorize_step
+from server.memory.candidate_types import CandidateStatus
+from server.memory.candidates import (
+    find_offered,
+    mark_offered,
+    next_offerable,
+    resolve_candidate,
+    still_offerable,
+)
+from server.memory.household_authorization import record_authorization_decision
+from server.memory.lexicon import (
+    ANSWER_CONTRADICTION_PHRASE,
+    ANSWER_REJECTED_PHRASE,
+    ANSWER_SAVED_PHRASE,
+    OFFER_QUESTION,
+    OFFER_STATEMENTS,
+    OFFER_VERB_PLURAL,
+    OFFER_VERB_SINGULAR,
+    PLURAL_ARTICLES,
+)
+from server.memory.memory_writer import PromotionOutcome, promote
+from server.settings import settings
+
+if TYPE_CHECKING:
+    from datetime import datetime
+    from uuid import UUID
+
+    from server.cognition.authorization import AuthorizationRequest
+    from server.cognition.identity import ActivePersonContext
+    from server.cognition.intent_resolution import MemoryAnswer
+    from server.cognition.models import AuthorizationDecision, CognitiveEvent
+    from server.cognition.response_plan import TextTurnPayload
+
+logger = logging.getLogger(__name__)
+
+__all__ = [
+    "ANSWER_CONTRADICTION_PHRASE",
+    "ANSWER_REJECTED_PHRASE",
+    "ANSWER_SAVED_PHRASE",
+    "OfferPreparer",
+    "PendingOffer",
+    "answer_offer",
+    "commit_offer",
+    "compose_offer",
+    "prepare_offer",
+]
+
+type PolicyEvaluator = Callable[[AuthorizationRequest], AuthorizationDecision]
+type AuditWriter = Callable[[AuthorizationRequest, AuthorizationDecision], Awaitable[None]]
+type Clock = Callable[[], datetime]
+
+
+@dataclass(frozen=True)
+class PendingOffer:
+    """An offer ready to be spoken once the turn's reply is built.
+
+    Attributes:
+        candidate_id: The candidate it offers.
+        subject_person_id: Whose candidate it is (the speaker).
+        phrase: The spoken offer; it carries the value, so it never reaches a log.
+        actor: The face-and-voice actor of this turn, for the policy's read step.
+        correlation_id: The turn's id; it stamps the audit row and the candidate.
+    """
+
+    candidate_id: int
+    subject_person_id: int
+    phrase: str
+    actor: ActivePersonContext
+    correlation_id: UUID
+
+
+#: What a voice route binds and hands to the text turn: the actor in, an offer or ``None`` out.
+type OfferPreparer = Callable[[ActivePersonContext], Awaitable[PendingOffer | None]]
+
+
+def compose_offer(predicate: str, value_text: str) -> str:
+    """Return the spoken offer for one candidate.
+
+    Args:
+        predicate: ``likes``, ``dislikes`` or ``prefers``.
+        value_text: The stored phrase, article included ("las empanadas").
+
+    Returns:
+        The statement and the question, which tells the exact answer with the value.
+
+    Raises:
+        ValueError: If *predicate* has no offer.
+    """
+    statement = OFFER_STATEMENTS.get(predicate)
+    if statement is None:
+        raise ValueError(f"{predicate} has no offer")
+    first_word = value_text.split(maxsplit=1)[0].casefold() if value_text.strip() else ""
+    verb = OFFER_VERB_PLURAL if first_word in PLURAL_ARTICLES else OFFER_VERB_SINGULAR
+    return " ".join(
+        (
+            statement.format(verb=verb, value=value_text),
+            OFFER_QUESTION.format(value=value_text),
+        )
+    )
+
+
+async def prepare_offer(
+    actor: ActivePersonContext,
+    *,
+    wav_bytes: bytes | None,
+    event: CognitiveEvent[TextTurnPayload],
+    verify: VoiceVerifier = verify_face_and_voice,
+    clock: Clock = utc_now,
+) -> PendingOffer | None:
+    """Find the speaker's oldest offerable candidate and check the voice, writing nothing.
+
+    Cheapest first: the kill-switch and a token-free face actor, then a read of the store, and
+    only when a candidate waits the voice of the turn's own clip for the person the face named.
+
+    Args:
+        actor: The turn's face-identified actor.
+        wav_bytes: The turn's own clip — WAV, 16 000 Hz, mono, int16 — or ``None``.
+        event: The turn's event; its correlation id stamps what follows.
+        verify: The voice-check seam; tests inject doubles.
+        clock: Source of "now" for the store's deadlines.
+
+    Returns:
+        The offer to speak once the reply is built, or ``None``. Never raises: any failure is
+        logged by its class and offers nothing.
+    """
+    try:
+        if not settings.memory_candidates_enabled or not is_face_actor(actor):
+            return None
+        person_id = actor.person_id
+        if person_id is None:
+            return None
+        candidate = await next_offerable(person_id, now=clock())
+        if candidate is None or candidate.value_text is None:
+            return None
+        strong = await verify(actor, wav_bytes=wav_bytes, event=event)
+        if strong is None or strong.person_id != person_id:
+            _log("candidate.offer", "voice_unverified", candidate.id, event.correlation_id)
+            return None
+        return PendingOffer(
+            candidate_id=candidate.id,
+            subject_person_id=person_id,
+            phrase=compose_offer(candidate.predicate, candidate.value_text),
+            actor=strong,
+            correlation_id=event.correlation_id,
+        )
+    except Exception as exc:  # background seam of a turn: never reaches the user's reply
+        _log_failure("candidate.offer", exc)
+        return None
+
+
+async def commit_offer(
+    offer: PendingOffer,
+    *,
+    now: datetime | None = None,
+    policy: PolicyEvaluator = evaluate_authorization,
+    audit: AuditWriter = record_authorization_decision,
+) -> str | None:
+    """Ask the policy, audit, and mark the candidate ``offered``; return the phrase to speak.
+
+    Args:
+        offer: What ``prepare_offer`` returned for this turn.
+        now: The caller's clock reading; the current UTC time when omitted.
+        policy: The pure evaluator; tests inject doubles.
+        audit: The audit writer; tests inject doubles.
+
+    Returns:
+        The offer's phrase, or ``None`` when the candidate is no longer offerable (asked before
+        the audit, so no "allowed" row is written for it), the policy refused, the audit failed
+        or the compare-and-set lost anyway. Never raises.
+    """
+    try:
+        moment = now or utc_now()
+        if not await still_offerable(offer.candidate_id, offer.subject_person_id, now=moment):
+            _log("candidate.offer", "not_offerable", offer.candidate_id, offer.correlation_id)
+            return None
+        allowed = await authorize_step(
+            CandidateStep.READ,
+            actor=offer.actor,
+            subject_person_id=offer.subject_person_id,
+            correlation_id=offer.correlation_id,
+            now=moment,
+            policy=policy,
+            audit=audit,
+        )
+        if not allowed.allowed:
+            return None
+        if not await mark_offered(
+            offer.candidate_id,
+            offer.subject_person_id,
+            correlation_id=offer.correlation_id,
+            now=moment,
+        ):
+            _log("candidate.offer", "not_offerable", offer.candidate_id, offer.correlation_id)
+            return None
+        _log("candidate.offer", "offered", offer.candidate_id, offer.correlation_id)
+        return offer.phrase
+    except Exception as exc:  # the reply was built; a failing offer must not break it
+        _log_failure("candidate.offer", exc)
+        return None
+
+
+async def answer_offer(
+    answer: MemoryAnswer,
+    *,
+    actor: ActivePersonContext,
+    correlation_id: UUID,
+    now: datetime,
+    policy: PolicyEvaluator = evaluate_authorization,
+    audit: AuditWriter = record_authorization_decision,
+) -> str | None:
+    """Resolve the speaker's open offer that the answer names, or fall through.
+
+    The caller resolved the actor (face and voice) before calling, for every message of this
+    shape, so the cost of the check never depends on whether an offer exists.
+
+    Args:
+        answer: The parsed answer: accept or reject, and the value it repeats.
+        actor: The turn's actor; only the face-and-voice composite may answer.
+        correlation_id: The answering turn's id.
+        now: The caller's clock reading.
+        policy: The pure evaluator; tests inject doubles.
+        audit: The audit writer; tests inject doubles.
+
+    Returns:
+        The fixed result phrase, or ``None`` to fall through to ordinary generation (switch
+        off, a weaker actor, no open offer with that value, a refusal or any failure).
+        Never raises.
+    """
+    try:
+        person_id = actor.person_id
+        if (
+            not settings.memory_candidates_enabled
+            or person_id is None
+            or not is_face_and_voice_actor(actor)
+        ):
+            return None
+        key = comparison_key(answer.phrase)
+        candidate = await find_offered(person_id, key, now=now) if key else None
+        if candidate is None:
+            return None
+        if answer.accept:
+            return await _accept(candidate.id, actor, correlation_id, now, policy, audit)
+        return await _reject(candidate.id, actor, person_id, correlation_id, now, policy, audit)
+    except Exception as exc:  # fail closed: the turn falls through to ordinary generation
+        _log_failure("candidate.answer", exc)
+        return None
+
+
+async def _accept(
+    candidate_id: int,
+    actor: ActivePersonContext,
+    correlation_id: UUID,
+    now: datetime,
+    policy: PolicyEvaluator,
+    audit: AuditWriter,
+) -> str | None:
+    """Promote through the one writer (it asks and audits the confirm step itself)."""
+    result = await promote(
+        candidate_id,
+        actor=actor,
+        correlation_id=correlation_id,
+        now=now,
+        policy=policy,
+        audit=audit,
+    )
+    _log("candidate.answer", result.outcome.value, candidate_id, correlation_id)
+    match result.outcome:
+        case PromotionOutcome.PROMOTED | PromotionOutcome.ALREADY_PRESENT:
+            return ANSWER_SAVED_PHRASE
+        case PromotionOutcome.CONTRADICTION:
+            return ANSWER_CONTRADICTION_PHRASE
+        case _:
+            return None
+
+
+async def _reject(
+    candidate_id: int,
+    actor: ActivePersonContext,
+    person_id: int,
+    correlation_id: UUID,
+    now: datetime,
+    policy: PolicyEvaluator,
+    audit: AuditWriter,
+) -> str | None:
+    """Audit the confirm step, then reject the candidate and erase its value."""
+    allowed = await authorize_step(
+        CandidateStep.CONFIRM,
+        actor=actor,
+        subject_person_id=person_id,
+        correlation_id=correlation_id,
+        now=now,
+        policy=policy,
+        audit=audit,
+    )
+    if not allowed.allowed:
+        return None
+    if not await resolve_candidate(
+        candidate_id,
+        person_id,
+        to=CandidateStatus.REJECTED,
+        correlation_id=correlation_id,
+        now=now,
+    ):
+        return None
+    _log("candidate.answer", "rejected", candidate_id, correlation_id)
+    return ANSWER_REJECTED_PHRASE
+
+
+def _log(event: str, outcome: str, candidate_id: int, correlation_id: UUID) -> None:
+    """Log one dialogue step: ids and a closed outcome, never a value."""
+    logger.info(
+        "Candidate %s: %s",
+        event.removeprefix("candidate."),
+        outcome,
+        extra={
+            "event": event,
+            "outcome": outcome,
+            "candidate_id": candidate_id,
+            "correlation_id": str(correlation_id),
+        },
+    )
+
+
+def _log_failure(event: str, exc: Exception) -> None:
+    """Log a failure by its class only: the message of a database error can carry a value."""
+    logger.warning(
+        "Candidate %s failed (%s)",
+        event.removeprefix("candidate."),
+        type(exc).__name__,
+        extra={"event": f"{event}_error", "error_type": type(exc).__name__},
+    )
diff --git a/server/src/server/memory/candidate_proposal.py b/server/src/server/memory/candidate_proposal.py
--- a/server/src/server/memory/candidate_proposal.py
+++ b/server/src/server/memory/candidate_proposal.py
@@ -30,14 +30,18 @@ from collections.abc import Awaitable, Callable
 from dataclasses import dataclass, field
 import logging
 from pathlib import Path
-from typing import TYPE_CHECKING, Protocol
+from typing import TYPE_CHECKING

 import aiosqlite
 import httpx

 from server.cognition.authorization import evaluate_authorization
 from server.cognition.clock import utc_now
-from server.cognition.strong_actor import is_face_actor, verify_face_and_voice
+from server.cognition.strong_actor import (
+    VoiceVerifier,
+    is_face_actor,
+    verify_face_and_voice,
+)
 from server.exceptions import BrainMemoryError, LLMError
 from server.memory.candidate_classifier import classify
 from server.memory.candidate_extraction import extract_candidates
@@ -75,20 +79,6 @@ type EnrollmentReader = Callable[[int], Awaitable[bool]]
 type Clock = Callable[[], datetime]


-class VoiceVerifier(Protocol):
-    """The voice-check seam: ``verify_face_and_voice`` or a test double (same keyword names)."""
-
-    def __call__(
-        self,
-        actor: ActivePersonContext,
-        *,
-        wav_bytes: bytes | None,
-        event: CognitiveEvent[TextTurnPayload],
-    ) -> Awaitable[ActivePersonContext | None]:
-        """Return the actor fused at ``strong``, or ``None`` when the voice was not verified."""
-        ...
-
-
 # What an insert that did not store a candidate is reported as (`INSERTED` is absent).
 _INSERT_REASONS = {
     InsertStatus.DUPLICATE: CandidateReason.DUPLICATE,
diff --git a/server/src/server/memory/lexicon.py b/server/src/server/memory/lexicon.py
--- a/server/src/server/memory/lexicon.py
+++ b/server/src/server/memory/lexicon.py
@@ -168,6 +168,24 @@ PREFERENCE_TRIGGERS: dict[str, str] = {
 }
 PREFERENCE_FAVOURITE = re.compile(r"mi (?:[a-z]+ ){0,2}favorit[oa] es")

+#: The spoken offer and its results (ADR 0021 decision 9, Plan 0063). Neutral Spanish with
+#: tuteo (Pipec lives in Santiago de Chile). ``{value}`` is the stored phrase, which already
+#: passed the gate and the classifier; the offer tells the exact answer, value included (Pipec's
+#: option A), and promises no recall (that is CM-5).
+OFFER_STATEMENTS: dict[str, str] = {
+    "likes": "Antes me dijiste que te {verb} {value}.",
+    "dislikes": "Antes me dijiste que no te {verb} {value}.",
+    "prefers": "Antes me dijiste que prefieres {value}.",
+}
+OFFER_QUESTION = "¿Quieres que lo guarde? Dime: sí, autorizo guardar {value}."
+#: An object that starts with one of these takes the plural verb ("te gustan las empanadas").
+PLURAL_ARTICLES = frozenset({"los", "las", "unos", "unas"})
+OFFER_VERB_SINGULAR = "gusta"
+OFFER_VERB_PLURAL = "gustan"
+ANSWER_SAVED_PHRASE = "Listo, lo guardé."
+ANSWER_REJECTED_PHRASE = "Está bien, no lo guardo."
+ANSWER_CONTRADICTION_PHRASE = "No lo guardé: ya tengo guardado algo distinto."
+
 #: Closed set of topics a taste may belong to; the extractor must place the object in one.
 CANDIDATE_TOPICS = frozenset(
     {"food", "drink", "music", "colour", "pastime", "sport", "animal", "weather", "media"}
```

- [ ] **Step 4: Run to see them pass, then lint and types.** Also
  `uv run pytest tests/integration/test_candidate_proposal.py tests/unit/test_strong_actor.py -q -p no:cacheprovider`
  (the proposal keeps its behaviour with the moved `VoiceVerifier`).
- [ ] **Step 5: Commit** `feat(server): add the memory offer and answer dialogue (plan 0063)`; check `git log -1`.

---

## Task 5: The controller's answer branch

**Files:**
- Modify: `server/src/server/cognition/controller.py`
- Test: modified `tests/unit/test_cognitive_controller.py`

**Interfaces:**
- Consumes: Task 2.
- Produces: `controller.MemoryAnswerer = Callable[[MemoryAnswer, ActivePersonContext,
  CognitiveEvent[TextTurnPayload]], Awaitable[str | None]]`; `CognitiveController(...,
  memory_answerer: MemoryAnswerer | None = None)`. With an answerer, a `MEMORY_ANSWER` message
  resolves the actor through the **observing** resolver (no grant is ever spent) and then asks the
  answerer; `None` from it is `decide() -> None` (ordinary generation). Without one, the shape is
  ordinary conversation and the actor is not resolved. The result of each event is remembered, so
  the classic route's second `decide()` never answers twice.

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/tests/unit/test_cognitive_controller.py b/tests/unit/test_cognitive_controller.py
--- a/tests/unit/test_cognitive_controller.py
+++ b/tests/unit/test_cognitive_controller.py
@@ -14,7 +14,7 @@ from server.cognition.authorization import (
 from server.cognition.controller import CognitiveController
 from server.cognition.household_tools import HouseholdToolName, HouseholdToolResult
 from server.cognition.identity import ActivePersonContext, ActivePersonStatus, HouseholdRole
-from server.cognition.intent_resolution import IntentMatch, IntentResolution
+from server.cognition.intent_resolution import IntentMatch, IntentResolution, MemoryAnswer
 from server.cognition.models import (
     AuthorizationAction,
     AuthorizationDecision,
@@ -681,3 +681,109 @@ async def test_the_children_read_is_the_only_branch_that_spends_the_grant() -> N

     spending.assert_awaited_once()
     assert plan.status is KnowledgeStatus.KNOWN
+
+
+# --- the answer to a memory offer (Plan 0063, ADR 0021 decision 9) ----------------------------
+
+
+def _legacy(response: str = "Respuesta normal.") -> AsyncMock:
+    return AsyncMock(
+        return_value=TextTurnResult(
+            response=response, emotion="neutral", duration_ms=5, llm_failed=False
+        )
+    )
+
+
+@pytest.mark.asyncio
+async def test_an_answer_resolves_the_actor_first_and_speaks_the_fixed_result() -> None:
+    """The actor is resolved (face and voice) before the answerer reads anything."""
+    order: list[str] = []
+    actor = _actor(HouseholdRole.OWNER, 7)
+
+    async def observe(_event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
+        order.append("actor")
+        return actor
+
+    async def answer(
+        parsed: MemoryAnswer, who: ActivePersonContext, event: CognitiveEvent[TextTurnPayload]
+    ) -> str | None:
+        order.append("answer")
+        assert parsed == MemoryAnswer(accept=True, phrase="el mate")
+        assert who is actor
+        assert event.correlation_id == UUID("22222222-2222-2222-2222-222222222222")
+        return "Listo, lo guardé."
+
+    legacy_turn = _legacy()
+    controller = CognitiveController(
+        today=lambda: date(2026, 8, 12),
+        legacy_turn=legacy_turn,
+        observed_person_resolver=observe,
+        memory_answerer=answer,
+    )
+
+    plan = await controller.handle(_event("Sí, autorizo guardar el mate"))
+
+    assert order == ["actor", "answer"]
+    assert plan.need is InformationNeed.MEMORY_ANSWER
+    assert plan.response == "Listo, lo guardé."
+    legacy_turn.assert_not_awaited()
+
+
+@pytest.mark.asyncio
+async def test_an_answer_nobody_can_use_falls_through_to_the_ordinary_turn() -> None:
+    """No offer, a weaker actor or a refusal: the reply is exactly the generic one."""
+    observe = AsyncMock(return_value=_actor(HouseholdRole.OWNER, 7))
+    answer = AsyncMock(return_value=None)
+    legacy_turn = _legacy("Claro, el mate es rico.")
+    controller = CognitiveController(
+        today=lambda: date(2026, 8, 12),
+        legacy_turn=legacy_turn,
+        observed_person_resolver=observe,
+        memory_answerer=answer,
+    )
+
+    event = _event("Sí, autorizo guardar el mate")
+    assert await controller.decide(event) is None
+    plan = await controller.handle(event)
+
+    assert plan.need is InformationNeed.GENERIC_CONVERSATION
+    assert plan.response == "Claro, el mate es rico."
+    legacy_turn.assert_awaited_once()
+    # The classic route runs decide() then handle(): the answer is tried once per event.
+    observe.assert_awaited_once()
+    answer.assert_awaited_once()
+
+
+@pytest.mark.asyncio
+async def test_a_channel_without_the_answerer_never_resolves_the_actor_for_an_answer() -> None:
+    """/chat and /vision/respond inject no answerer: the shape falls through untouched."""
+    observe = AsyncMock(return_value=_actor(HouseholdRole.OWNER, 7))
+    legacy_turn = _legacy()
+    controller = CognitiveController(
+        today=lambda: date(2026, 8, 12),
+        legacy_turn=legacy_turn,
+        observed_person_resolver=observe,
+    )
+
+    assert await controller.decide(_event("Sí, autorizo guardar el mate")) is None
+    observe.assert_not_awaited()
+
+
+@pytest.mark.asyncio
+async def test_the_answer_branch_never_spends_a_grant() -> None:
+    """The answer uses the observing resolver; the spending one is never awaited."""
+    spend = AsyncMock(return_value=_actor(HouseholdRole.OWNER, 7))
+    observe = AsyncMock(return_value=_actor(HouseholdRole.OWNER, 7))
+    controller = CognitiveController(
+        today=lambda: date(2026, 8, 12),
+        legacy_turn=_legacy(),
+        active_person_resolver=spend,
+        observed_person_resolver=observe,
+        memory_answerer=AsyncMock(return_value="Está bien, no lo guardo."),
+    )
+
+    plan = await controller.decide(_event("No autorizo guardar el mate"))
+
+    assert isinstance(plan, ResponsePlan)
+    assert plan.response == "Está bien, no lo guardo."
+    spend.assert_not_awaited()
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_cognitive_controller.py -q -p no:cacheprovider`
  Expected RED: `TypeError: CognitiveController.__init__() got an unexpected keyword argument 'memory_answerer'`
  (and `UnboundLocalError` for the `MEMORY_ANSWER` case the `match` does not handle yet).
- [ ] **Step 3: Implement:**

```diff
diff --git a/server/src/server/cognition/controller.py b/server/src/server/cognition/controller.py
--- a/server/src/server/cognition/controller.py
+++ b/server/src/server/cognition/controller.py
@@ -15,7 +15,12 @@ from server.cognition.authorization import (
 )
 from server.cognition.calendar_tools import calculate_age, get_current_date
 from server.cognition.identity import ActivePersonContext, ActivePersonStatus, HouseholdRole
-from server.cognition.intent_resolution import IntentResolution, resolve_information_need
+from server.cognition.intent_resolution import (
+    IntentResolution,
+    MemoryAnswer,
+    parse_memory_answer,
+    resolve_information_need,
+)
 from server.cognition.models import (
     AuthorizationAction,
     AuthorizationDecision,
@@ -37,6 +42,7 @@ from server.cognition.response_plan import (

 if TYPE_CHECKING:
     from datetime import date
+    from uuid import UUID

     from server.cognition.household_tools import HouseholdKnowledgeTools, HouseholdToolResult
     from server.text_turn import TextTurnResult
@@ -51,6 +57,12 @@ type ConsentResolver = Callable[
     [CognitiveEvent[TextTurnPayload], ActivePersonContext], Awaitable[ConsentStatus]
 ]
 type IntentResolver = Callable[[str], IntentResolution]
+#: Resolves a spoken answer to a memory offer for an actor already resolved from face and voice
+#: (ADR 0021 decision 9). Only the voice routes inject one; it returns the fixed result phrase,
+#: or ``None`` so the turn falls through to ordinary generation, byte for byte.
+type MemoryAnswerer = Callable[
+    [MemoryAnswer, ActivePersonContext, CognitiveEvent[TextTurnPayload]], Awaitable[str | None]
+]
 type ControllerDecision = ResponsePlan | SceneDescriptionRequest | None

 _BIOMETRIC_ENROLLMENT_RESPONSE = (
@@ -110,6 +122,7 @@ class CognitiveController:
         household_tools: HouseholdKnowledgeTools | None = None,
         consent_resolver: ConsentResolver = _not_required_consent,
         intent_resolver: IntentResolver = resolve_information_need,
+        memory_answerer: MemoryAnswerer | None = None,
     ) -> None:
         """Create a controller with injected calendar and legacy-generation seams.

@@ -126,6 +139,9 @@ class CognitiveController:
             household_tools: Optional closed P0.5-B2 family-tool collaborator.
             consent_resolver: Trusted internal scoped-consent boundary.
             intent_resolver: Pure, typed P0-C5 Spanish intent resolver.
+            memory_answerer: The answer to a memory offer (ADR 0021 decision 9); injected
+                only by the voice routes with the candidate kill-switch on. When absent an
+                answer-shaped message is ordinary conversation.
         """
         self._today = today
         self._legacy_turn = legacy_turn
@@ -136,6 +152,10 @@ class CognitiveController:
         self._household_tools = household_tools
         self._consent_resolver = consent_resolver
         self._intent_resolver = intent_resolver
+        self._memory_answerer = memory_answerer
+        # The classic route calls decide() twice on a turn that falls through (decide, then
+        # handle): an answer is attempted once per event, so no audit row is written twice.
+        self._answers: dict[UUID, ResponsePlan | None] = {}

     async def handle(self, event: CognitiveEvent[TextTurnPayload]) -> ResponsePlan:
         """Produce one bounded response plan for a typed text event.
@@ -195,6 +215,8 @@ class CognitiveController:
                 decision = await self._active_identity_plan(event)
             case InformationNeed.SCENE_DESCRIPTION:
                 decision = SceneDescriptionRequest()
+            case InformationNeed.MEMORY_ANSWER:
+                decision = await self._memory_answer_plan(event)
             case InformationNeed.GENERIC_CONVERSATION:
                 decision = None
         return decision
@@ -259,6 +281,37 @@ class CognitiveController:
             )
         return _unknown_plan(InformationNeed.ACTIVE_IDENTITY, _ACTIVE_IDENTITY_UNKNOWN_RESPONSE)

+    async def _memory_answer_plan(
+        self,
+        event: CognitiveEvent[TextTurnPayload],
+    ) -> ResponsePlan | None:
+        """Answer a memory offer, or fall through to ordinary generation (``None``).
+
+        No oracle (ADR 0021 decision 9): the actor is resolved from face and voice **first**,
+        for every message of this shape and whether or not an offer exists, and only then
+        does the answerer read the actor's own candidates. The observing resolver is used,
+        so no PIN grant is ever spent: a token never answers a memory offer.
+        """
+        answer = parse_memory_answer(event.payload.message)
+        if self._memory_answerer is None or answer is None:
+            return None
+        if event.event_id in self._answers:
+            return self._answers[event.event_id]
+        actor = await self._observed_person_resolver(event)
+        phrase = await self._memory_answerer(answer, actor, event)
+        plan = (
+            None
+            if phrase is None
+            else ResponsePlan(
+                need=InformationNeed.MEMORY_ANSWER,
+                status=KnowledgeStatus.KNOWN,
+                source=ResponseSource.DETERMINISTIC,
+                response=phrase,
+            )
+        )
+        self._answers[event.event_id] = plan
+        return plan
+
     async def _own_children_plan(
         self,
         event: CognitiveEvent[TextTurnPayload],
```

- [ ] **Step 4: Run to see them pass, then lint and types.**
- [ ] **Step 5: Commit** `feat(server): answer a memory offer in the controller (plan 0063)`; check `git log -1`.

---

## Task 6: The offer in the text-turn seam

**Files:**
- Modify: `server/src/server/text_turn.py`, `server/src/server/cognition/response_plan.py`, `server/src/server/cognition/controller.py`
- Test: modified `tests/unit/test_text_turn.py`, `tests/unit/test_cognitive_controller.py`

**Interfaces:**
- Consumes: Task 4 (`OfferPreparer`, `PendingOffer`, `commit_offer`).
- Produces: `TextTurnResult.offer: str | None = None`; `ResponsePlan.offer: str | None` (never
  empty); `start_offer(prepare_offer, active_person) -> asyncio.Future | None` (only a face actor
  with no token, memory and the switch on); `async finish_offer(task, *, reply_failed) -> str |
  None` (cancels on a fallback without swallowing the caller's own cancellation);
  `drop_offer(task)`; `process_text_turn(..., prepare_offer=None)`. `duration_ms` is measured
  before the offer is committed; the offer never enters the session history.

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/tests/unit/test_cognitive_controller.py b/tests/unit/test_cognitive_controller.py
--- a/tests/unit/test_cognitive_controller.py
+++ b/tests/unit/test_cognitive_controller.py
@@ -27,6 +27,7 @@ from server.cognition.models import (
 from server.cognition.response_plan import (
     InformationNeed,
     ResponsePlan,
+    ResponseSource,
     SceneDescriptionRequest,
     TextTurnPayload,
 )
@@ -787,3 +788,34 @@ async def test_the_answer_branch_never_spends_a_grant() -> None:
     assert isinstance(plan, ResponsePlan)
     assert plan.response == "Está bien, no lo guardo."
     spend.assert_not_awaited()
+
+
+@pytest.mark.asyncio
+async def test_the_generic_plan_carries_the_offer_apart_from_the_response() -> None:
+    """The offer is spoken after the reply; it is never part of the reply's text."""
+    legacy_turn = AsyncMock(
+        return_value=TextTurnResult(
+            response="Hola.",
+            emotion="neutral",
+            duration_ms=5,
+            llm_failed=False,
+            offer="Antes me dijiste que te gusta el mate.",
+        )
+    )
+    controller = CognitiveController(today=lambda: date(2026, 8, 12), legacy_turn=legacy_turn)
+
+    plan = await controller.handle(_event("hola"))
+
+    assert plan.response == "Hola."
+    assert plan.offer == "Antes me dijiste que te gusta el mate."
+
+
+def test_an_empty_offer_is_refused_by_the_plan() -> None:
+    with pytest.raises(ValueError, match="offer"):
+        ResponsePlan(
+            need=InformationNeed.GENERIC_CONVERSATION,
+            status=KnowledgeStatus.UNKNOWN,
+            source=ResponseSource.LEGACY_TEXT_TURN,
+            response="Hola.",
+            offer="",
+        )
diff --git a/tests/unit/test_text_turn.py b/tests/unit/test_text_turn.py
--- a/tests/unit/test_text_turn.py
+++ b/tests/unit/test_text_turn.py
@@ -1,3 +1,4 @@
+import asyncio
 from datetime import UTC, datetime
 import inspect
 import logging
@@ -17,6 +18,7 @@ from server.cognition.identity import (
 from server.cognition.models import Confidence, ConfidenceBasis
 from server.exceptions import BrainMemoryError, LLMError
 from server.memory import continuity
+from server.memory.candidate_dialogue import PendingOffer
 from server.memory.continuity import SuspendCause, Transition
 from server.schemas import MemoryContext
 from server.settings import settings
@@ -624,3 +626,233 @@ def test_public_apis_are_typed_and_documented() -> None:
         signature = inspect.signature(api)
         assert api.__doc__
         assert signature.return_annotation is not inspect.Signature.empty
+
+
+# --- the spoken offer (Plan 0063, ADR 0021 decision 9) ----------------------------------------
+
+
+def _pending() -> PendingOffer:
+    return PendingOffer(
+        candidate_id=1,
+        subject_person_id=_OWNER,
+        phrase="Antes me dijiste que te gusta el mate.",
+        actor=_person(IdentityEvidenceSource.FACE, assurance=IdentityAssurance.STRONG),
+        correlation_id=UUID(int=1),
+    )
+
+
+def _offer_on(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
+    monkeypatch.setattr(settings, "memory_enabled", True)
+    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
+    commit = AsyncMock(return_value="Antes me dijiste que te gusta el mate.")
+    monkeypatch.setattr(text_turn, "commit_offer", commit)
+    return commit
+
+
+@pytest.mark.unit
+@pytest.mark.asyncio
+async def test_the_offer_is_prepared_while_the_reply_is_generated(
+    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    """The voice check runs concurrently: generation waits for it and does not deadlock."""
+    commit = _offer_on(monkeypatch)
+    prepared = asyncio.Event()
+
+    async def generate(*_args: object, **_kwargs: object) -> tuple[str, str]:
+        await asyncio.wait_for(prepared.wait(), timeout=2)
+        return "Hola.", "neutral"
+
+    async def prepare(_actor: ActivePersonContext) -> PendingOffer:
+        prepared.set()
+        return _pending()
+
+    monkeypatch.setattr(text_turn.llm, "generate_response", generate)
+
+    result = await text_turn.process_text_turn(
+        http_client,
+        "hola",
+        "voice",
+        active_person=_person(IdentityEvidenceSource.FACE),
+        prepare_offer=prepare,
+    )
+
+    assert result.response == "Hola."
+    assert result.offer == "Antes me dijiste que te gusta el mate."
+    commit.assert_awaited_once()
+
+
+@pytest.mark.unit
+@pytest.mark.asyncio
+async def test_the_offer_never_enters_the_session_history(
+    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    _offer_on(monkeypatch)
+    _generate(monkeypatch, ("Hola.", "neutral"))
+
+    await text_turn.process_text_turn(
+        http_client,
+        "hola",
+        "voice",
+        active_person=_person(IdentityEvidenceSource.FACE),
+        prepare_offer=AsyncMock(return_value=_pending()),
+    )
+
+    assert [turn.content for turn in continuity.open_turn(_OWNER).history] == ["hola", "Hola."]
+
+
+@pytest.mark.unit
+@pytest.mark.asyncio
+async def test_a_fallback_reply_carries_no_offer(
+    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    commit = _offer_on(monkeypatch)
+    monkeypatch.setattr(text_turn.llm, "generate_response", AsyncMock(side_effect=LLMError("down")))
+
+    result = await text_turn.process_text_turn(
+        http_client,
+        "hola",
+        "voice",
+        active_person=_person(IdentityEvidenceSource.FACE),
+        prepare_offer=AsyncMock(return_value=_pending()),
+    )
+
+    assert result.llm_failed
+    assert result.offer is None
+    commit.assert_not_awaited()
+
+
+@pytest.mark.unit
+@pytest.mark.asyncio
+@pytest.mark.parametrize(
+    "actor",
+    [
+        _person(IdentityEvidenceSource.LOCAL_UNLOCK),
+        _person(IdentityEvidenceSource.MANUAL),
+        _unidentified_person(ActivePersonStatus.UNKNOWN),
+        None,
+    ],
+)
+async def test_only_a_face_identified_speaker_is_ever_offered_anything(
+    http_client: httpx.AsyncClient,
+    monkeypatch: pytest.MonkeyPatch,
+    actor: ActivePersonContext | None,
+) -> None:
+    _offer_on(monkeypatch)
+    _generate(monkeypatch, ("Hola.", "neutral"))
+    prepare = AsyncMock(return_value=_pending())
+
+    result = await text_turn.process_text_turn(
+        http_client, "hola", "voice", active_person=actor, prepare_offer=prepare
+    )
+
+    assert result.offer is None
+    prepare.assert_not_awaited()
+
+
+@pytest.mark.unit
+@pytest.mark.asyncio
+@pytest.mark.parametrize("switch", ["memory_enabled", "memory_candidates_enabled"])
+async def test_either_switch_off_prepares_no_offer(
+    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, switch: str
+) -> None:
+    _offer_on(monkeypatch)
+    monkeypatch.setattr(settings, switch, False)
+    _generate(monkeypatch, ("Hola.", "neutral"))
+    prepare = AsyncMock(return_value=_pending())
+
+    result = await text_turn.process_text_turn(
+        http_client,
+        "hola",
+        "voice",
+        active_person=_person(IdentityEvidenceSource.FACE),
+        prepare_offer=prepare,
+    )
+
+    assert result.offer is None
+    prepare.assert_not_awaited()
+
+
+@pytest.mark.unit
+@pytest.mark.asyncio
+async def test_an_offer_the_policy_or_the_store_refused_is_not_spoken(
+    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    commit = _offer_on(monkeypatch)
+    commit.return_value = None
+    _generate(monkeypatch, ("Hola.", "neutral"))
+
+    result = await text_turn.process_text_turn(
+        http_client,
+        "hola",
+        "voice",
+        active_person=_person(IdentityEvidenceSource.FACE),
+        prepare_offer=AsyncMock(return_value=_pending()),
+    )
+
+    assert result.offer is None
+
+
+@pytest.mark.unit
+@pytest.mark.asyncio
+async def test_committing_the_offer_never_counts_as_generation_time(
+    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    commit = _offer_on(monkeypatch)
+
+    async def slow_commit(_pending: PendingOffer) -> str:
+        await asyncio.sleep(0.3)
+        return "Antes me dijiste que te gusta el mate."
+
+    commit.side_effect = slow_commit
+    _generate(monkeypatch, ("Hola.", "neutral"))
+
+    result = await text_turn.process_text_turn(
+        http_client,
+        "hola",
+        "voice",
+        active_person=_person(IdentityEvidenceSource.FACE),
+        prepare_offer=AsyncMock(return_value=_pending()),
+    )
+
+    assert result.offer is not None
+    assert result.duration_ms < 200
+
+
+@pytest.mark.unit
+@pytest.mark.asyncio
+async def test_a_cancelled_turn_cancels_the_offer_it_was_preparing(
+    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    _offer_on(monkeypatch)
+    started = asyncio.Event()
+    cancelled = asyncio.Event()
+
+    async def never_answers(*_args: object, **_kwargs: object) -> tuple[str, str]:
+        await asyncio.Event().wait()
+        return "x", "neutral"
+
+    async def prepare(_actor: ActivePersonContext) -> PendingOffer:
+        started.set()
+        try:
+            await asyncio.Event().wait()
+        except asyncio.CancelledError:
+            cancelled.set()
+            raise
+        return _pending()
+
+    monkeypatch.setattr(text_turn.llm, "generate_response", never_answers)
+    turn = asyncio.create_task(
+        text_turn.process_text_turn(
+            http_client,
+            "hola",
+            "voice",
+            active_person=_person(IdentityEvidenceSource.FACE),
+            prepare_offer=prepare,
+        )
+    )
+    await asyncio.wait_for(started.wait(), timeout=2)
+
+    turn.cancel()
+    with pytest.raises(asyncio.CancelledError):
+        await turn
+    await asyncio.wait_for(cancelled.wait(), timeout=2)
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_text_turn.py tests/unit/test_cognitive_controller.py -q -p no:cacheprovider`
  Expected RED: `AttributeError: ... has no attribute 'commit_offer'` in the text-turn tests and
  `TypeError: TextTurnResult.__init__() got an unexpected keyword argument 'offer'` in the
  controller test.
- [ ] **Step 3: Implement:**

```diff
diff --git a/server/src/server/cognition/controller.py b/server/src/server/cognition/controller.py
--- a/server/src/server/cognition/controller.py
+++ b/server/src/server/cognition/controller.py
@@ -231,6 +231,7 @@ class CognitiveController:
             response=result.response,
             emotion=result.emotion,
             duration_ms=result.duration_ms,
+            offer=result.offer,
         )

     async def _protected_household_plan(
diff --git a/server/src/server/cognition/response_plan.py b/server/src/server/cognition/response_plan.py
--- a/server/src/server/cognition/response_plan.py
+++ b/server/src/server/cognition/response_plan.py
@@ -87,6 +87,9 @@ class ResponsePlan(BaseModel):
     duration_ms: int = Field(default=0, ge=0)
     tool_results: tuple[ToolResult, ...] = ()
     claims: tuple[ResponseClaim, ...] = ()
+    # A memory offer spoken after the response (ADR 0021 decision 9). The classic route
+    # synthesizes it with the response but never returns it in `llm_response`.
+    offer: str | None = Field(default=None, min_length=1)

     @model_validator(mode="after")
     def _known_claims_require_known_tools(self) -> "ResponsePlan":
diff --git a/server/src/server/text_turn.py b/server/src/server/text_turn.py
--- a/server/src/server/text_turn.py
+++ b/server/src/server/text_turn.py
@@ -1,5 +1,6 @@
 """Channel-agnostic text turn orchestration."""

+import asyncio
 from collections.abc import Callable
 from dataclasses import dataclass
 from datetime import UTC, datetime
@@ -22,6 +23,7 @@ from server.cognition.identity import (
 from server.cognition.strong_actor import is_face_actor
 from server.exceptions import BrainMemoryError, LLMError
 from server.memory import continuity
+from server.memory.candidate_dialogue import OfferPreparer, PendingOffer, commit_offer
 from server.memory.context import build_context
 from server.memory.continuity import ContinuityTurn, SuspendCause
 from server.onboarding import OnboardingSlot
@@ -60,6 +62,9 @@ class TextTurnResult:
     emotion: str
     duration_ms: int
     llm_failed: bool
+    # The spoken memory offer (ADR 0021 decision 9), spoken after the reply. It is never part of
+    # the reply's text, the session history, the wire's `llm_response` or `duration_ms`.
+    offer: str | None = None


 def _missing_person(_: int) -> None:
@@ -270,6 +275,66 @@ def record_text_turn(
         turn_log.log_memory("proposal-scheduled", "face-identified speaker")


+def start_offer(
+    prepare_offer: OfferPreparer | None, active_person: ActivePersonContext | None
+) -> asyncio.Future[PendingOffer | None] | None:
+    """Start preparing a memory offer concurrently with generation, when one may exist.
+
+    Only a face-identified speaker with no token, with memory and the candidate kill-switch on,
+    starts it (ADR 0021 decisions 3 and 9); the preparation itself checks the voice and only
+    when a candidate waits, so latency never says whether one exists.
+
+    Args:
+        prepare_offer: The route-bound preparation (it owns the clip and the event), or ``None``.
+        active_person: The turn's resolved speaker.
+
+    Returns:
+        The running preparation, or ``None`` when no offer can be made on this turn.
+    """
+    if (
+        prepare_offer is None
+        or active_person is None
+        or not settings.memory_enabled
+        or not settings.memory_candidates_enabled
+        or not is_face_actor(active_person)
+    ):
+        return None
+    return asyncio.ensure_future(prepare_offer(active_person))
+
+
+async def finish_offer(
+    task: asyncio.Future[PendingOffer | None] | None, *, reply_failed: bool
+) -> str | None:
+    """Commit the prepared offer once the reply was built, or drop it.
+
+    Args:
+        task: What ``start_offer`` returned.
+        reply_failed: Whether the reply is the fallback phrase; a fallback never carries one.
+
+    Returns:
+        The phrase to speak after the reply, or ``None``.
+    """
+    if task is None:
+        return None
+    if reply_failed:
+        task.cancel()
+        # Waits for the cancelled preparation without swallowing a cancellation of the caller.
+        await asyncio.gather(task, return_exceptions=True)
+        return None
+    pending = await task
+    return None if pending is None else await commit_offer(pending)
+
+
+def drop_offer(task: asyncio.Future[PendingOffer | None] | None) -> None:
+    """Cancel a preparation the turn will never finish (it was cancelled or it raised).
+
+    Args:
+        task: What ``start_offer`` returned; a finished one is left alone.
+    """
+    if task is not None and not task.done():
+        task.cancel()
+
+
 async def process_text_turn(
     client: httpx.AsyncClient,
     message: str,
@@ -279,6 +344,7 @@ async def process_text_turn(
     active_person: ActivePersonContext | None = None,
     suspend_cause: SuspendCause | None = None,
     schedule_proposal: ProposalScheduler | None = None,
+    prepare_offer: OfferPreparer | None = None,
 ) -> TextTurnResult:
     """Generate and record one channel-agnostic text turn.

@@ -290,9 +356,11 @@ async def process_text_turn(
         active_person: Internally resolved evidence for this turn only.
         suspend_cause: Why the speaker could not be identified, for the transition log.
         schedule_proposal: Optional channel-owned proposal scheduling callback.
+        prepare_offer: Optional channel-owned memory-offer preparation (ADR 0021 §9); it runs
+            concurrently with generation.

     Returns:
-        Text, emotion, elapsed time, and fallback status for the turn.
+        Text, emotion, elapsed time, fallback status and the optional offer for the turn.
     """
     started = time.perf_counter()
     prepared = await prepare_text_turn(
@@ -303,14 +371,20 @@ async def process_text_turn(
         active_person=active_person,
         suspend_cause=suspend_cause,
     )
-    response, emotion, llm_failed = await _generate(client, prepared)
-    if not llm_failed:
-        record_text_turn(
-            message,
-            response,
-            active_person=prepared.active_person,
-            continuity_turn=prepared.continuity,
-            schedule_proposal=schedule_proposal,
-        )
-    duration_ms = round((time.perf_counter() - started) * 1000)
-    return TextTurnResult(response, emotion, duration_ms, llm_failed)
+    offer_task = start_offer(prepare_offer, prepared.active_person)
+    try:
+        response, emotion, llm_failed = await _generate(client, prepared)
+        if not llm_failed:
+            record_text_turn(
+                message,
+                response,
+                active_person=prepared.active_person,
+                continuity_turn=prepared.continuity,
+                schedule_proposal=schedule_proposal,
+            )
+        # Measured before the offer is committed: the offer never counts as generation time.
+        duration_ms = round((time.perf_counter() - started) * 1000)
+        offer = await finish_offer(offer_task, reply_failed=llm_failed)
+    finally:
+        drop_offer(offer_task)
+    return TextTurnResult(response, emotion, duration_ms, llm_failed, offer)
```

- [ ] **Step 4: Run to see them pass, then lint and types.**
- [ ] **Step 5: Commit** `feat(server): prepare the memory offer during generation (plan 0063)`; check `git log -1`.

---

## Task 7: The offer on the stream

**Files:**
- Modify: `server/src/server/streaming.py`, `server/src/server/streaming_render.py`
- Test: new `tests/integration/test_stream_offer.py`

**Interfaces:**
- Consumes: Task 6 (`start_offer`, `finish_offer`, `drop_offer`).
- Produces: `stream_pipeline(..., prepare_offer: OfferPreparer | None = None)`; after a
  successful reply, one `audio` event with empty `text` before `done`; never on a fallback or a
  TTS failure of the reply; cancelled when the client hangs up; `StreamState.offer_overhead_ms` and
  `offer_tts_ms` keep the offer out of `llm_ms`.

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/tests/integration/test_stream_offer.py b/tests/integration/test_stream_offer.py
new file mode 100644
--- /dev/null
+++ b/tests/integration/test_stream_offer.py
@@ -0,0 +1,296 @@
+"""The spoken memory offer on the streaming route (ADR 0021 decision 9, Plan 0063).
+
+The offer is one more ``audio`` event after the reply's sentences and before ``done``, with
+empty text: the robot plays it and prints nothing, and it never reaches ``log_spoken``, the
+session history or the ``llm_ms`` accounting.
+"""
+
+from __future__ import annotations
+
+import asyncio
+from datetime import UTC, datetime
+import json
+import time
+from typing import TYPE_CHECKING, cast
+from unittest.mock import AsyncMock, Mock
+from uuid import UUID
+
+import pytest
+from server.cognition.identity import (
+    ActivePersonContext,
+    ActivePersonStatus,
+    HouseholdRole,
+    IdentityAssurance,
+    IdentityEvidence,
+    IdentityEvidenceSource,
+)
+from server.cognition.models import Confidence, ConfidenceBasis
+from server.exceptions import LLMError, TTSError
+from server.memory.candidate_dialogue import OfferPreparer, PendingOffer
+from server.memory.continuity import ContinuityTurn
+from server.settings import settings
+from server.text_turn import PreparedTextTurn
+
+from server import llm_streaming, streaming, streaming_render, text_turn, tts
+
+if TYPE_CHECKING:
+    from collections.abc import AsyncGenerator, AsyncIterator
+
+    import httpx
+
+pytestmark = pytest.mark.integration
+
+_OFFER = "Antes me dijiste que te gusta el mate."
+_REPLY = "Hola, qué gusto."
+
+
+def _face_owner() -> ActivePersonContext:
+    resolved_at = datetime(2026, 10, 15, tzinfo=UTC)
+    confidence = Confidence(
+        score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=True, reason="In-turn face match"
+    )
+    return ActivePersonContext(
+        person_id=7,
+        display_name="Canary",
+        status=ActivePersonStatus.IDENTIFIED,
+        confidence=confidence,
+        role=HouseholdRole.OWNER,
+        evidence=(
+            IdentityEvidence(
+                evidence_id=UUID(int=3),
+                source=IdentityEvidenceSource.FACE,
+                candidate_person_id=7,
+                confidence=confidence,
+                observed_at=resolved_at,
+                reference="in-turn-face-evidence",
+            ),
+        ),
+        resolved_at=resolved_at,
+        assurance=IdentityAssurance.BASIC,
+    )
+
+
+def _prepared() -> PreparedTextTurn:
+    return PreparedTextTurn(
+        "hola",
+        "interaction:canary",
+        None,
+        [],
+        False,
+        None,
+        None,
+        None,
+        _face_owner(),
+        ContinuityTurn((), 7, 0),
+    )
+
+
+def _pending() -> PendingOffer:
+    return PendingOffer(
+        candidate_id=1,
+        subject_person_id=7,
+        phrase=_OFFER,
+        actor=_face_owner(),
+        correlation_id=UUID(int=1),
+    )
+
+
+@pytest.fixture
+def stream_on(monkeypatch: pytest.MonkeyPatch) -> dict[str, Mock | AsyncMock]:
+    """Memory and candidates on, a scripted model, a spy TTS and a spy commit."""
+    monkeypatch.setattr(settings, "memory_enabled", True)
+    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
+
+    async def generate_stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
+        yield _REPLY
+
+    monkeypatch.setattr(llm_streaming, "generate_response_stream", generate_stream)
+    synthesize = AsyncMock(side_effect=[("UkVQTFk=", 30), ("T0ZGRVI=", 70)])
+    monkeypatch.setattr(tts, "synthesize", synthesize)
+    commit = AsyncMock(return_value=_OFFER)
+    monkeypatch.setattr(text_turn, "commit_offer", commit)
+    spoken = Mock()
+    monkeypatch.setattr(streaming_render, "log_spoken", spoken)
+    monkeypatch.setattr(streaming, "log_spoken", spoken)
+    record = Mock()
+    monkeypatch.setattr(streaming, "record_text_turn", record)
+    return {"synthesize": synthesize, "commit": commit, "spoken": spoken, "record": record}
+
+
+async def _events(
+    client: httpx.AsyncClient, prepare_offer: OfferPreparer | None
+) -> list[dict[str, object]]:
+    return [
+        json.loads(line)
+        async for line in streaming.stream_pipeline(
+            client=client,
+            prepared=_prepared(),
+            stt_ms=0,
+            request_start=time.perf_counter(),
+            schedule_proposal=lambda _message, _actor: None,
+            prepare_offer=prepare_offer,
+        )
+    ]
+
+
+async def test_the_offer_is_one_more_audio_event_after_the_reply_with_no_text(
+    http_client: httpx.AsyncClient, stream_on: dict[str, Mock | AsyncMock]
+) -> None:
+    events = await _events(http_client, AsyncMock(return_value=_pending()))
+
+    assert [event["type"] for event in events] == [
+        "text_heard",
+        "emotion",
+        "audio",
+        "audio",
+        "done",
+    ]
+    assert events[2]["text"] == _REPLY
+    assert events[3] == {"type": "audio", "text": "", "audio_base64": "T0ZGRVI=", "duration_ms": 70}
+    assert stream_on["synthesize"].await_args_list[-1].args == (_OFFER,)
+
+
+async def test_the_offer_never_reaches_the_spoken_log_nor_the_session(
+    http_client: httpx.AsyncClient, stream_on: dict[str, Mock | AsyncMock]
+) -> None:
+    await _events(http_client, AsyncMock(return_value=_pending()))
+
+    assert [call.args[0] for call in stream_on["spoken"].call_args_list] == [_REPLY]
+    record_call = stream_on["record"].call_args
+    assert record_call is not None
+    assert record_call.args[1] == _REPLY
+
+
+async def test_the_offer_synthesis_is_tts_time_not_model_time(
+    http_client: httpx.AsyncClient, stream_on: dict[str, Mock | AsyncMock]
+) -> None:
+    events = await _events(http_client, AsyncMock(return_value=_pending()))
+
+    done = events[-1]
+    assert done["tts_ms"] == 100
+
+
+async def test_a_fallback_reply_carries_no_offer(
+    http_client: httpx.AsyncClient,
+    monkeypatch: pytest.MonkeyPatch,
+    stream_on: dict[str, Mock | AsyncMock],
+) -> None:
+    async def broken(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
+        raise LLMError("down")
+        yield ""  # pragma: no cover — makes this an async generator
+
+    monkeypatch.setattr(llm_streaming, "generate_response_stream", broken)
+    stream_on["synthesize"].side_effect = None
+    stream_on["synthesize"].return_value = ("RkFMTA==", 20)
+
+    events = await _events(http_client, AsyncMock(return_value=_pending()))
+
+    assert [event["type"] for event in events].count("audio") == 1
+    stream_on["commit"].assert_not_awaited()
+
+
+async def test_an_offer_that_fails_to_synthesize_is_skipped_and_the_turn_still_ends_done(
+    http_client: httpx.AsyncClient, stream_on: dict[str, Mock | AsyncMock]
+) -> None:
+    stream_on["synthesize"].side_effect = [("UkVQTFk=", 30), TTSError("piper down")]
+
+    events = await _events(http_client, AsyncMock(return_value=_pending()))
+
+    assert [event["type"] for event in events] == ["text_heard", "emotion", "audio", "done"]
+
+
+async def test_no_preparation_means_the_stream_is_unchanged(
+    http_client: httpx.AsyncClient, stream_on: dict[str, Mock | AsyncMock]
+) -> None:
+    events = await _events(http_client, None)
+
+    assert [event["type"] for event in events] == ["text_heard", "emotion", "audio", "done"]
+    stream_on["commit"].assert_not_awaited()
+
+
+async def test_the_offer_is_prepared_while_the_model_streams(
+    http_client: httpx.AsyncClient,
+    monkeypatch: pytest.MonkeyPatch,
+    stream_on: dict[str, Mock | AsyncMock],
+) -> None:
+    """The model waits for the preparation to start: a sequential seam would deadlock."""
+    prepared = asyncio.Event()
+
+    async def generate_stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
+        await asyncio.wait_for(prepared.wait(), timeout=2)
+        yield _REPLY
+
+    async def prepare(_actor: ActivePersonContext) -> PendingOffer:
+        prepared.set()
+        return _pending()
+
+    monkeypatch.setattr(llm_streaming, "generate_response_stream", generate_stream)
+
+    events = await _events(http_client, prepare)
+
+    assert [event["type"] for event in events][-2:] == ["audio", "done"]
+    stream_on["commit"].assert_awaited_once()
+
+
+async def test_a_reply_that_fails_to_synthesize_commits_no_offer(
+    http_client: httpx.AsyncClient, stream_on: dict[str, Mock | AsyncMock]
+) -> None:
+    stream_on["synthesize"].side_effect = TTSError("piper down")
+
+    with pytest.raises(TTSError):
+        await _events(http_client, AsyncMock(return_value=_pending()))
+
+    stream_on["commit"].assert_not_awaited()
+
+
+async def test_committing_the_offer_never_counts_as_model_time(
+    http_client: httpx.AsyncClient, stream_on: dict[str, Mock | AsyncMock]
+) -> None:
+    async def slow_commit(_pending: PendingOffer) -> str:
+        await asyncio.sleep(0.3)
+        return _OFFER
+
+    stream_on["commit"].side_effect = slow_commit
+
+    events = await _events(http_client, AsyncMock(return_value=_pending()))
+
+    llm_ms = events[-1]["llm_ms"]
+    assert isinstance(llm_ms, int)
+    assert llm_ms < 200
+
+
+async def test_a_client_that_hangs_up_cancels_the_preparation(
+    http_client: httpx.AsyncClient,
+    monkeypatch: pytest.MonkeyPatch,
+    stream_on: dict[str, Mock | AsyncMock],
+) -> None:
+    started = asyncio.Event()
+    cancelled = asyncio.Event()
+
+    async def prepare(_actor: ActivePersonContext) -> PendingOffer:
+        started.set()
+        try:
+            await asyncio.Event().wait()
+        except asyncio.CancelledError:
+            cancelled.set()
+            raise
+        return _pending()
+
+    stream = cast(
+        "AsyncGenerator[str, None]",
+        streaming.stream_pipeline(
+            client=http_client,
+            prepared=_prepared(),
+            stt_ms=0,
+            request_start=time.perf_counter(),
+            schedule_proposal=lambda _message, _actor: None,
+            prepare_offer=prepare,
+        ),
+    )
+    await anext(stream)  # text_heard, before the preparation starts
+    await anext(stream)  # the model is streaming and the preparation is running
+    await asyncio.wait_for(started.wait(), timeout=2)
+
+    await stream.aclose()
+
+    await asyncio.wait_for(cancelled.wait(), timeout=2)
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/integration/test_stream_offer.py -q -p no:cacheprovider`
  Expected RED: `TypeError: stream_pipeline() got an unexpected keyword argument 'prepare_offer'`.
- [ ] **Step 3: Implement:**

```diff
diff --git a/server/src/server/streaming.py b/server/src/server/streaming.py
--- a/server/src/server/streaming.py
+++ b/server/src/server/streaming.py
@@ -17,6 +17,7 @@ stays exclusive to classic /transcribe (see app.py's robot_streaming flag).
 from collections.abc import AsyncIterator
 import json
 import logging
+import time

 import httpx

@@ -24,6 +25,7 @@ from server import llm, llm_streaming, tts
 from server.cognition.response_plan import ResponsePlan
 from server.conversation_log import log_spoken
 from server.exceptions import LLMError, TTSError
+from server.memory.candidate_dialogue import OfferPreparer
 from server.pipeline import _elapsed_ms, _log_pipeline_timing
 from server.schemas import IdentitySource
 from server.schemas_streaming import (
@@ -50,7 +52,10 @@ from server.streaming_render import (
 from server.text_turn import (
     PreparedTextTurn,
     ProposalScheduler,
+    drop_offer,
+    finish_offer,
     record_text_turn,
+    start_offer,
 )
 from server.user_emotion import classify_user_emotion

@@ -104,13 +109,18 @@ async def _consume_llm_stream(
         yield line


+def _succeeded(state: StreamState) -> bool:
+    """Whether the whole reply was spoken from valid model output (no fallback)."""
+    return state.outcome is StreamOutcome.OK and state.recordable and bool(state.response_parts)
+
+
 def _record_success(
     prepared: PreparedTextTurn,
     state: StreamState,
     scheduler: ProposalScheduler,
 ) -> None:
     """Persist a turn — only ever called for a fully successful stream."""
-    if state.outcome is not StreamOutcome.OK or not state.recordable or not state.response_parts:
+    if not _succeeded(state):
         return
     record_text_turn(
         prepared.message,
@@ -121,6 +131,30 @@ def _record_success(
     )


+def _note_offer_overhead(state: StreamState, started: float) -> None:
+    """Record how long the offer step took beyond its own synthesis (kept out of llm_ms)."""
+    spent = round((time.perf_counter() - started) * 1000)
+    state.offer_overhead_ms = max(0, spent - state.offer_tts_ms)
+
+
+async def _offer_event(offer: str, state: StreamState) -> str | None:
+    """Synthesize the memory offer as one more audio event with empty text (ADR 0021 §9).
+
+    The text stays empty, so the robot prints nothing, and the offer never reaches
+    ``log_spoken``: it carries a value. Its synthesis counts as TTS time, so ``llm_ms`` stays
+    the model's. A failing synthesis skips the offer: the reply was already spoken.
+    """
+    try:
+        audio_base64, duration_ms = await tts.synthesize(offer)
+    except (TTSError, ValueError) as exc:
+        logger.warning("Memory offer not synthesized (%s)", type(exc).__name__)
+        return None
+    state.tts_ms_total += duration_ms
+    state.offer_tts_ms = duration_ms
+    event = StreamAudioEvent(text="", audio_base64=audio_base64, duration_ms=duration_ms)
+    return event.model_dump_json() + "\n"
+
+
 async def stream_response_plan(
     *,
     text_heard: str,
@@ -176,6 +210,7 @@ async def stream_pipeline(
     stt_ms: int,
     request_start: float,
     schedule_proposal: ProposalScheduler,
+    prepare_offer: OfferPreparer | None = None,
 ) -> AsyncIterator[str]:
     """Stream STT->LLM->TTS as NDJSON, synthesizing speech sentence by sentence.

@@ -195,6 +230,8 @@ async def stream_pipeline(
         stt_ms: STT elapsed time, measured by the caller.
         request_start: ``time.perf_counter()`` reading from request start.
         schedule_proposal: Channel-owned background proposal scheduling callback.
+        prepare_offer: Channel-owned memory-offer preparation (ADR 0021 §9); it runs while
+            the model streams, and a prepared offer is spoken after the reply, before ``done``.

     Yields:
         NDJSON lines (each ending in ``\\n``), see schemas_streaming.py.
@@ -202,28 +239,42 @@ async def stream_pipeline(
     yield StreamTextHeardEvent(value=prepared.message).model_dump_json() + "\n"

     state = StreamState(request_start=request_start)
+    offer_task = start_offer(prepare_offer, prepared.active_person)
     try:
-        async for line in _consume_llm_stream(client, prepared, state):
-            yield line
-    except TTSError:
-        state.outcome = StreamOutcome.TTS_ERROR
-        _log_stream_metrics(state, _elapsed_ms(request_start))
-        raise
-    except (LLMError, ValueError) as exc:
-        if llm.is_connectivity_failure(exc):
-            logger.warning("Streaming LLM unreachable — speaking fallback phrase: %s", exc)
-        else:
-            logger.error("Streaming LLM failed — speaking fallback phrase: %s", exc, exc_info=True)
-        state.outcome = (
-            StreamOutcome.PARTIAL_FALLBACK if state.audio_chunks else StreamOutcome.LLM_FALLBACK
-        )
-        async for line in emit_fallback(state, reason=StreamFallbackReason.LLM_ERROR):
-            yield line
+        try:
+            async for line in _consume_llm_stream(client, prepared, state):
+                yield line
+        except TTSError:
+            state.outcome = StreamOutcome.TTS_ERROR
+            _log_stream_metrics(state, _elapsed_ms(request_start))
+            await finish_offer(offer_task, reply_failed=True)
+            raise
+        except (LLMError, ValueError) as exc:
+            if llm.is_connectivity_failure(exc):
+                logger.warning("Streaming LLM unreachable — speaking fallback phrase: %s", exc)
+            else:
+                logger.error(
+                    "Streaming LLM failed — speaking fallback phrase: %s", exc, exc_info=True
+                )
+            state.outcome = (
+                StreamOutcome.PARTIAL_FALLBACK if state.audio_chunks else StreamOutcome.LLM_FALLBACK
+            )
+            async for line in emit_fallback(state, reason=StreamFallbackReason.LLM_ERROR):
+                yield line

-    _record_success(prepared, state, schedule_proposal)
+        _record_success(prepared, state, schedule_proposal)
+        offer_started = time.perf_counter()
+        offer = await finish_offer(offer_task, reply_failed=not _succeeded(state))
+        offer_line = await _offer_event(offer, state) if offer is not None else None
+        if offer_line is not None:
+            yield offer_line
+    finally:
+        # A client that hangs up mid-stream must not leave the preparation running.
+        drop_offer(offer_task)
+    _note_offer_overhead(state, offer_started)

     total_ms = _elapsed_ms(request_start)
-    llm_ms = llm_elapsed_ms(total_ms, stt_ms, state.tts_ms_total)
+    llm_ms = llm_elapsed_ms(total_ms, stt_ms, state.tts_ms_total + state.offer_overhead_ms)
     _log_pipeline_timing("stream.legacy_text_turn", stt_ms, llm_ms, state.tts_ms_total, total_ms)
     yield _done_event(stt_ms, request_start, state)

diff --git a/server/src/server/streaming_render.py b/server/src/server/streaming_render.py
--- a/server/src/server/streaming_render.py
+++ b/server/src/server/streaming_render.py
@@ -112,6 +112,10 @@ class StreamState:
     first_audio_ms: int | None = None
     recordable: bool = True
     outcome: StreamOutcome = StreamOutcome.OK
+    # Time spent committing the memory offer (audit, compare-and-set) after the reply: neither
+    # model nor synthesis time, so it is kept out of `llm_ms` (ADR 0021 decision 9).
+    offer_overhead_ms: int = 0
+    offer_tts_ms: int = 0


 async def synthesize_sentence(sentence: str, state: StreamState) -> str:
@@ -271,7 +275,7 @@ def _done_event(
     if state.audio_chunks < 1:
         raise RuntimeError("Refusing to emit done before any audio chunk was spoken")
     total_ms = _elapsed_ms(request_start)
-    llm_ms = llm_elapsed_ms(total_ms, stt_ms, state.tts_ms_total)
+    llm_ms = llm_elapsed_ms(total_ms, stt_ms, state.tts_ms_total + state.offer_overhead_ms)
     _log_stream_metrics(state, total_ms)
     done = StreamDoneEvent(
         stt_ms=stt_ms,
```

- [ ] **Step 4: Run to see them pass, then lint and types.** Also
  `uv run pytest tests/integration/test_transcribe_stream.py -q -p no:cacheprovider`.
- [ ] **Step 5: Commit** `feat(server): speak the memory offer on the stream (plan 0063)`; check `git log -1`.

---

## Task 8: Wire both voice routes

**Files:**
- Modify: `server/src/server/routers/transcribe.py`, `server/src/server/pipeline.py`
- Test: new `tests/integration/test_memory_dialogue_routes.py`; modified `tests/integration/test_transcribe_pipeline.py`, `tests/unit/test_architecture_guards.py`

**Interfaces:**
- Consumes: Tasks 4 to 7.
- Produces: `_offer_preparer(*, event, wav_bytes) -> OfferPreparer | None` and
  `_memory_answerer() -> MemoryAnswerer | None` (both `None` with the switch off) bound by
  `/transcribe` and `/transcribe/stream`; `_synthesize_reply(plan)` (one WAV, the reply alone if
  that fails); `_run_tts(text, *, logged_text=None)`; the classic response reports no
  `identity_source` for a `GENERIC_CONVERSATION` plan; a guard that only the voice routes, the
  text turn, the stream, the controller and the dialogue name the offer and the answer.

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/tests/integration/test_memory_dialogue_routes.py b/tests/integration/test_memory_dialogue_routes.py
new file mode 100644
--- /dev/null
+++ b/tests/integration/test_memory_dialogue_routes.py
@@ -0,0 +1,480 @@
+"""The spoken offer and answer through the real voice routes (ADR 0021 decision 9, Plan 0063).
+
+Face detection and the speaker embedding are doubles; face matching, the voice centroid, the
+policy, the audit and the database are real. Audio is generated in code, never a recording, and
+every name is a canary.
+"""
+
+from __future__ import annotations
+
+from contextlib import asynccontextmanager
+from datetime import UTC, datetime, timedelta
+import io
+import json
+from typing import TYPE_CHECKING
+from unittest.mock import AsyncMock, Mock
+from uuid import uuid4
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
+from server.cognition.owner_authentication import owner_unlock_service
+from server.exceptions import TTSError
+from server.main import app
+from server.memory import candidates
+from server.memory.biometric_consent import grant_face_consent, revoke_face_consent
+from server.memory.candidate_dialogue import (
+    ANSWER_REJECTED_PHRASE,
+    ANSWER_SAVED_PHRASE,
+    compose_offer,
+)
+from server.memory.candidate_types import CandidateChannel, CandidateStatus, ProposedCandidate
+from server.memory.predicate_registry import resolve_predicate
+from server.memory.relational_v4 import get_active_literal_facts
+from server.memory.voice_consent import grant_voice_consent, revoke_voice_consent
+from server.personal_setup import PersonalSetupInput, PersonalSetupResult, apply_personal_setup
+from server.resources import AppResources
+from server.settings import settings
+from server.vision.faces import DetectedFace, enroll_face
+from server.voice.speaker_embedding import model_id
+from server.voice.voiceprints import enroll_voiceprint
+
+from server import db, llm, llm_streaming, pipeline, stt, tts
+
+if TYPE_CHECKING:
+    from collections.abc import AsyncIterator
+    from pathlib import Path
+
+pytestmark = pytest.mark.integration
+
+_OWNER_NAME = "Canary"
+_PIN = "482173"
+_FRAME = cv2.imencode(".jpg", np.zeros((10, 10, 3), dtype=np.uint8))[1].tobytes()
+_OFFER = compose_offer("likes", "el mate")
+_REPLY = "Hola, qué gusto."
+_ANSWER = "Sí, autorizo guardar el mate"
+
+
+def _axis(size: int, axis: int) -> np.ndarray:
+    vector = np.zeros(size, dtype=np.float32)
+    vector[axis] = 1.0
+    return vector
+
+
+_OWNER_FACE = _axis(512, 0)
+_STRANGER_FACE = _axis(512, 1)
+_OWNER_VOICE = _axis(192, 0)
+_OTHER_VOICE = _axis(192, 10)
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
+@pytest.fixture
+async def household(
+    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
+) -> AsyncIterator[PersonalSetupResult]:
+    """One owner with an enrolled, consented face and voice, and the candidate switch on."""
+    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "memory-dialogue.db")
+    monkeypatch.setattr(settings, "face_authentication_enabled", True)
+    monkeypatch.setattr(settings, "speaker_authentication_enabled", True)
+    monkeypatch.setattr(settings, "memory_enabled", True)
+    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
+    db._conn = None
+    await db.open_db()
+    await db.run_migrations()
+    result = await apply_personal_setup(
+        PersonalSetupInput(owner_name=_OWNER_NAME, child_names=(), pin=SecretStr(_PIN))
+    )
+    await grant_face_consent(result.owner_entity_id)
+    await enroll_face(result.owner_entity_id, _OWNER_FACE, label=_OWNER_NAME)
+    await grant_voice_consent(result.owner_entity_id)
+    for axis in range(3):
+        await enroll_voiceprint(result.owner_entity_id, _axis(192, axis), "owner", model_id())
+    yield result
+    await db.close_db()
+    db._conn = None
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
+def _files() -> dict[str, tuple[str, bytes, str]]:
+    return {
+        "audio": ("a.wav", _tone_wav(), "audio/wav"),
+        "frame": ("frame.jpg", _FRAME, "image/jpeg"),
+    }
+
+
+def _scene(
+    monkeypatch: pytest.MonkeyPatch,
+    *heard: str,
+    faces: tuple[np.ndarray, ...] = (_OWNER_FACE,),
+    voice: np.ndarray = _OWNER_VOICE,
+) -> AsyncMock:
+    """Script the faces, the voice, what STT hears and the model's reply; return the TTS spy."""
+    monkeypatch.setattr(
+        face_auth_module,
+        "_detect_faces_default",
+        AsyncMock(return_value=[DetectedFace(embedding=f, score=0.9, width=200.0) for f in faces]),
+    )
+    monkeypatch.setattr(speaker_auth_module, "embed_wav", AsyncMock(return_value=voice))
+    monkeypatch.setattr(stt, "transcribe", AsyncMock(side_effect=list(heard)))
+    monkeypatch.setattr(llm, "generate_response", AsyncMock(return_value=(_REPLY, "neutral")))
+    synthesize = AsyncMock(return_value=("AAAA", 42))
+    monkeypatch.setattr(tts, "synthesize", synthesize)
+    return synthesize
+
+
+async def _candidate(owner: int) -> int:
+    result = await candidates.insert_candidate(
+        ProposedCandidate(predicate="likes", value_text="el mate", value_key="mate"),
+        subject_person_id=owner,
+        asserted_by_person_id=owner,
+        channel=CandidateChannel.VOICE_CLASSIC,
+        correlation_id=uuid4(),
+        now=datetime.now(UTC) - timedelta(minutes=5),
+    )
+    assert result.candidate_id is not None
+    return result.candidate_id
+
+
+async def _status(candidate_id: int) -> CandidateStatus:
+    stored = await candidates.get_candidate(candidate_id)
+    assert stored is not None
+    return stored.status
+
+
+async def _audit_rows() -> list[tuple[str, str]]:
+    cursor = await db.get_conn().execute(
+        "SELECT action, decision FROM authorization_audit_events "
+        "WHERE action LIKE '%personal%memory%' ORDER BY id"
+    )
+    rows = [(str(row[0]), str(row[1])) for row in await cursor.fetchall()]
+    await cursor.close()
+    return rows
+
+
+async def _likes(owner: int) -> list[object]:
+    definition = resolve_predicate("likes")
+    assert definition is not None
+    return list(await get_active_literal_facts(subject_entity_id=owner, definition=definition))
+
+
+async def test_the_classic_route_offers_after_the_reply_and_the_answer_saves_it(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    owner = household.owner_entity_id
+    candidate_id = await _candidate(owner)
+    synthesize = _scene(monkeypatch, "hola", _ANSWER)
+
+    async with _client() as client:
+        offered = await client.post("/transcribe", files=_files())
+        answered = await client.post("/transcribe", files=_files())
+
+    assert offered.status_code == answered.status_code == 200
+    assert offered.json()["llm_response"] == _REPLY
+    assert offered.json()["identity_source"] is None  # a generic turn stays a generic turn
+    assert synthesize.await_args_list[0].args == (f"{_REPLY} {_OFFER}",)
+    assert answered.json()["llm_response"] == ANSWER_SAVED_PHRASE
+    assert answered.json()["identity_source"] == "face_voice"
+    assert await _status(candidate_id) is CandidateStatus.CONFIRMED
+    assert len(await _likes(owner)) == 1
+    assert await _audit_rows() == [
+        ("read_personal_conversation_memory", "allowed"),
+        ("confirm_personal_memory", "allowed"),
+    ]
+
+
+async def test_the_streaming_route_offers_as_one_more_silent_audio_event(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    owner = household.owner_entity_id
+    candidate_id = await _candidate(owner)
+    synthesize = _scene(monkeypatch, "hola")
+
+    async def stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
+        yield _REPLY
+
+    monkeypatch.setattr(llm_streaming, "generate_response_stream", stream)
+
+    async with _client() as client:
+        response = await client.post("/transcribe/stream", files=_files())
+
+    events = [json.loads(line) for line in response.text.splitlines()]
+    assert [event["type"] for event in events] == [
+        "text_heard",
+        "emotion",
+        "audio",
+        "audio",
+        "done",
+    ]
+    assert events[3]["text"] == ""
+    assert synthesize.await_args_list[-1].args == (_OFFER,)
+    assert await _status(candidate_id) is CandidateStatus.OFFERED
+
+
+async def test_no_is_said_and_audited_and_the_value_is_gone(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    owner = household.owner_entity_id
+    candidate_id = await _candidate(owner)
+    _scene(monkeypatch, "hola", "No autorizo guardar el mate")
+
+    async with _client() as client:
+        await client.post("/transcribe", files=_files())
+        answered = await client.post("/transcribe", files=_files())
+
+    assert answered.json()["llm_response"] == ANSWER_REJECTED_PHRASE
+    assert await _status(candidate_id) is CandidateStatus.REJECTED
+    assert await _likes(owner) == []
+
+
+async def test_another_voice_with_the_owner_face_is_offered_nothing_and_answers_nothing(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    owner = household.owner_entity_id
+    candidate_id = await _candidate(owner)
+    synthesize = _scene(monkeypatch, "hola", _ANSWER, voice=_OTHER_VOICE)
+
+    async with _client() as client:
+        offered = await client.post("/transcribe", files=_files())
+        answered = await client.post("/transcribe", files=_files())
+
+    assert synthesize.await_args_list[0].args == (_REPLY,)
+    assert offered.json()["llm_response"] == _REPLY
+    assert answered.json()["llm_response"] == _REPLY
+    assert await _status(candidate_id) is CandidateStatus.PROPOSED
+    assert await _audit_rows() == []
+
+
+async def test_a_second_face_in_frame_is_offered_nothing(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    candidate_id = await _candidate(household.owner_entity_id)
+    synthesize = _scene(monkeypatch, "hola", faces=(_OWNER_FACE, _STRANGER_FACE))
+
+    async with _client() as client:
+        response = await client.post("/transcribe", files=_files())
+
+    assert response.json()["llm_response"] == _REPLY
+    assert synthesize.await_args_list[0].args == (_REPLY,)
+    assert await _status(candidate_id) is CandidateStatus.PROPOSED
+
+
+async def test_an_answer_with_no_offer_outstanding_is_an_ordinary_turn(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    """Nothing is confirmed; the ordinary turn it becomes may itself carry the offer."""
+    candidate_id = await _candidate(household.owner_entity_id)
+    synthesize = _scene(monkeypatch, _ANSWER)
+
+    async with _client() as client:
+        response = await client.post("/transcribe", files=_files())
+
+    assert response.json()["llm_response"] == _REPLY
+    assert synthesize.await_args_list[0].args == (f"{_REPLY} {_OFFER}",)
+    assert await _status(candidate_id) is CandidateStatus.OFFERED
+    assert await _audit_rows() == [("read_personal_conversation_memory", "allowed")]
+
+
+async def test_the_switch_off_offers_nothing_and_answers_nothing(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    owner = household.owner_entity_id
+    candidate_id = await _candidate(owner)
+    assert await candidates.mark_offered(
+        candidate_id, owner, correlation_id=uuid4(), now=datetime.now(UTC)
+    )
+    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
+    synthesize = _scene(monkeypatch, "hola", _ANSWER)
+
+    async with _client() as client:
+        first = await client.post("/transcribe", files=_files())
+        second = await client.post("/transcribe", files=_files())
+
+    assert synthesize.await_args_list[0].args == (_REPLY,)
+    assert first.json()["llm_response"] == second.json()["llm_response"] == _REPLY
+    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
+    assert await _status(candidate_id) is CandidateStatus.OFFERED
+
+
+async def test_chat_never_answers_a_memory_offer(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    owner = household.owner_entity_id
+    candidate_id = await _candidate(owner)
+    assert await candidates.mark_offered(
+        candidate_id, owner, correlation_id=uuid4(), now=datetime.now(UTC)
+    )
+    _scene(monkeypatch)
+
+    async with _client() as client:
+        response = await client.post("/chat", json={"message": _ANSWER, "conversation_id": "web"})
+
+    assert response.status_code == 200
+    assert response.json()["response"] == _REPLY
+    assert await _status(candidate_id) is CandidateStatus.OFFERED
+
+
+async def test_the_classic_spoken_log_never_carries_the_offer(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    await _candidate(household.owner_entity_id)
+    _scene(monkeypatch, "hola")
+    spoken = Mock()
+    monkeypatch.setattr(pipeline, "log_spoken", spoken)
+
+    async with _client() as client:
+        await client.post("/transcribe", files=_files())
+
+    assert [call.args[0] for call in spoken.call_args_list] == [_REPLY]
+
+
+async def test_a_failing_combined_synthesis_still_speaks_the_reply(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    await _candidate(household.owner_entity_id)
+    synthesize = _scene(monkeypatch, "hola")
+    synthesize.side_effect = [TTSError("piper down"), ("AAAA", 42)]
+
+    async with _client() as client:
+        response = await client.post("/transcribe", files=_files())
+
+    assert response.status_code == 200
+    assert response.json()["llm_response"] == _REPLY
+    assert [call.args for call in synthesize.await_args_list] == [
+        (f"{_REPLY} {_OFFER}",),
+        (_REPLY,),
+    ]
+
+
+async def test_a_fall_through_answer_is_the_ordinary_turn_on_the_wire(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    """Another voice saying the answer gets exactly what «hola» gets, field by field."""
+    owner = household.owner_entity_id
+    candidate_id = await _candidate(owner)
+    assert await candidates.mark_offered(
+        candidate_id, owner, correlation_id=uuid4(), now=datetime.now(UTC)
+    )
+    _scene(monkeypatch, "hola", _ANSWER, voice=_OTHER_VOICE)
+
+    async with _client() as client:
+        ordinary = (await client.post("/transcribe", files=_files())).json()
+        answer = (await client.post("/transcribe", files=_files())).json()
+
+    timing = {"stt_ms", "llm_ms", "tts_ms", "total_ms", "text_heard"}
+    assert {k: v for k, v in answer.items() if k not in timing} == {
+        k: v for k, v in ordinary.items() if k not in timing
+    }
+    assert await _status(candidate_id) is CandidateStatus.OFFERED
+
+
+async def test_the_streaming_route_answers_too(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    owner = household.owner_entity_id
+    candidate_id = await _candidate(owner)
+    assert await candidates.mark_offered(
+        candidate_id, owner, correlation_id=uuid4(), now=datetime.now(UTC)
+    )
+    _scene(monkeypatch, _ANSWER)
+
+    async with _client() as client:
+        response = await client.post("/transcribe/stream", files=_files())
+
+    events = [json.loads(line) for line in response.text.splitlines()]
+    assert [event["text"] for event in events if event["type"] == "audio"] == [ANSWER_SAVED_PHRASE]
+    assert await _status(candidate_id) is CandidateStatus.CONFIRMED
+
+
+async def test_a_voice_consent_revoked_after_the_offer_answers_nothing(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    owner = household.owner_entity_id
+    candidate_id = await _candidate(owner)
+    _scene(monkeypatch, "hola", _ANSWER)
+
+    async with _client() as client:
+        await client.post("/transcribe", files=_files())
+        await revoke_voice_consent(owner)
+        answered = await client.post("/transcribe", files=_files())
+
+    assert answered.json()["llm_response"] == _REPLY
+    assert await _status(candidate_id) is CandidateStatus.OFFERED
+    assert await _audit_rows() == [("read_personal_conversation_memory", "allowed")]
+
+
+async def test_a_face_consent_revoked_before_the_turn_offers_nothing(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    owner = household.owner_entity_id
+    candidate_id = await _candidate(owner)
+    await revoke_face_consent(owner)
+    synthesize = _scene(monkeypatch, "hola")
+
+    async with _client() as client:
+        await client.post("/transcribe", files=_files())
+
+    assert synthesize.await_args_list[0].args == (_REPLY,)
+    assert await _status(candidate_id) is CandidateStatus.PROPOSED
+    assert await _audit_rows() == []
+
+
+async def test_vision_never_answers_a_memory_offer(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    owner = household.owner_entity_id
+    candidate_id = await _candidate(owner)
+    assert await candidates.mark_offered(
+        candidate_id, owner, correlation_id=uuid4(), now=datetime.now(UTC)
+    )
+    _scene(monkeypatch)
+    monkeypatch.setattr(settings, "vision_enabled", True)
+
+    async with _client() as client:
+        response = await client.post(
+            "/vision/respond",
+            files={"image": ("frame.jpg", _FRAME, "image/jpeg")},
+            data={"text": _ANSWER},
+        )
+
+    assert response.status_code == 200
+    assert await _status(candidate_id) is CandidateStatus.OFFERED
+
+
+async def test_chat_never_offers_a_waiting_candidate(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    candidate_id = await _candidate(household.owner_entity_id)
+    _scene(monkeypatch)
+
+    async with _client() as client:
+        response = await client.post("/chat", json={"message": "hola", "conversation_id": "web"})
+
+    assert response.json()["response"] == _REPLY
+    assert await _status(candidate_id) is CandidateStatus.PROPOSED
diff --git a/tests/integration/test_transcribe_pipeline.py b/tests/integration/test_transcribe_pipeline.py
--- a/tests/integration/test_transcribe_pipeline.py
+++ b/tests/integration/test_transcribe_pipeline.py
@@ -333,8 +333,9 @@ def test_transcribe_uses_distinct_internal_scopes_per_request(
         schedule_proposal: ProposalScheduler,
         active_person: object = None,
         suspend_cause: object = None,
+        prepare_offer: object = None,
     ) -> TextTurnResult:
-        _ = client, schedule_proposal, active_person, suspend_cause
+        _ = client, schedule_proposal, active_person, suspend_cause, prepare_offer
         return TextTurnResult("shared reply", "joy", 7, False)

     process = AsyncMock(side_effect=process_turn)
diff --git a/tests/unit/test_architecture_guards.py b/tests/unit/test_architecture_guards.py
--- a/tests/unit/test_architecture_guards.py
+++ b/tests/unit/test_architecture_guards.py
@@ -476,6 +476,43 @@ def test_the_proposal_guards_detect_a_violation() -> None:
     assert _imports_name(leak, "consolidate_turn") == ["memory/legacy.py"]


+# --- who may offer or answer (Plan 0063, ADR 0021 decision 9) ---------------------------------
+# The offer and the answer need the voice of the turn's own clip: only the voice routes bind
+# them, and the text turn, the stream and the controller carry the seams. `/chat` and
+# `/vision/respond` have no audio, so they never offer and never answer.
+_DIALOGUE_NAMES = frozenset(
+    {"prepare_offer", "OfferPreparer", "answer_offer", "MemoryAnswerer", "memory_answerer"}
+)
+_DIALOGUE_HOMES = frozenset(
+    {
+        "memory/candidate_dialogue.py",
+        "routers/transcribe.py",
+        "streaming.py",
+        "text_turn.py",
+        "cognition/controller.py",
+    }
+)
+
+
+@pytest.mark.unit
+def test_only_the_voice_routes_offer_or_answer_a_memory() -> None:
+    assert _outside(_sources(), _DIALOGUE_HOMES, _DIALOGUE_NAMES) == []
+
+
+@pytest.mark.unit
+def test_the_dialogue_guard_detects_a_violation() -> None:
+    leak = {
+        "routers/chat.py": "controller = CognitiveController(memory_answerer=a)\n",
+        "routers/vision.py": "x = prepare_offer(actor)\n",
+        "routers/transcribe.py": "x = prepare_offer(actor)\n",
+    }
+
+    assert _outside(leak, _DIALOGUE_HOMES, _DIALOGUE_NAMES) == [
+        "routers/chat.py",
+        "routers/vision.py",
+    ]
+
+
 @pytest.mark.unit
 def test_the_retired_memory_actions_exist_nowhere() -> None:
     """ADR 0021 decision 11: no enum member, branch or string names them any more."""
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/integration/test_memory_dialogue_routes.py tests/unit/test_architecture_guards.py -q -p no:cacheprovider`
  Expected RED: the route tests fail on their assertions (the reply is spoken without the offer,
  the answer is generated by the model, the stream has one `audio` event); the guard test passes
  on arrival (no other module names the dialogue yet). `test_transcribe_pipeline.py` fails after
  Step 3 until its fake `process_turn` accepts `prepare_offer` — that change is in the diff.
- [ ] **Step 3: Implement:**

```diff
diff --git a/server/src/server/pipeline.py b/server/src/server/pipeline.py
--- a/server/src/server/pipeline.py
+++ b/server/src/server/pipeline.py
@@ -98,11 +98,13 @@ async def _run_stt(audio_bytes: bytes, hotwords: list[str]) -> tuple[str, int]:
     return text, _elapsed_ms(start)


-async def _run_tts(text: str) -> tuple[str, int, int]:
+async def _run_tts(text: str, *, logged_text: str | None = None) -> tuple[str, int, int]:
     """Synthesize speech and measure elapsed time.

     Args:
         text: Text to speak.
+        logged_text: What the opt-in spoken-text log may show instead of *text*; a memory offer
+            spoken after the reply carries a value and never reaches that log (ADR 0021 §9).

     Returns:
         Tuple of (base64 WAV audio, TTS-reported synthesis ms, elapsed ms).
@@ -117,5 +119,5 @@ async def _run_tts(text: str) -> tuple[str, int, int]:
         logger.error("TTS failed: %s", exc, exc_info=True)
         raise HTTPException(status_code=500, detail="Speech synthesis failed") from exc
     logger.info("TTS synthesized: %d ms audio, %d chars in", duration_ms, len(text))
-    log_spoken(text)
+    log_spoken(text if logged_text is None else logged_text)
     return audio_base64, duration_ms, _elapsed_ms(start)
diff --git a/server/src/server/routers/transcribe.py b/server/src/server/routers/transcribe.py
--- a/server/src/server/routers/transcribe.py
+++ b/server/src/server/routers/transcribe.py
@@ -19,7 +19,13 @@ import httpx
 from server import turn_log
 from server.audio_contract import validate_wav_contract
 from server.cognition.authorization import evaluate_authorization
-from server.cognition.controller import ActivePersonResolver, CognitiveController, ConsentResolver
+from server.cognition.clock import utc_now
+from server.cognition.controller import (
+    ActivePersonResolver,
+    CognitiveController,
+    ConsentResolver,
+    MemoryAnswerer,
+)
 from server.cognition.generic_identity import (
     GenericIdentification,
     identify_generic_speaker,
@@ -27,9 +33,11 @@ from server.cognition.generic_identity import (
 from server.cognition.household_tools import HouseholdKnowledgeTools
 from server.cognition.identity import ActivePersonContext
 from server.cognition.identity_fusion import FusedIdentityResolver, build_fused_identity_resolver
+from server.cognition.intent_resolution import MemoryAnswer
 from server.cognition.models import CognitiveEvent
 from server.cognition.owner_authentication import OwnerUnlockService
 from server.cognition.response_plan import (
+    InformationNeed,
     ResponsePlan,
     SceneDescriptionRequest,
     TextTurnPayload,
@@ -40,6 +48,12 @@ from server.exceptions import (
     AudioContractError,
     UploadTooLargeError,
 )
+from server.memory.candidate_dialogue import (
+    OfferPreparer,
+    PendingOffer,
+    answer_offer,
+    prepare_offer,
+)
 from server.memory.candidate_proposal import propose_candidates
 from server.memory.candidate_types import CandidateChannel
 from server.memory.household_authorization import record_authorization_decision
@@ -220,6 +234,8 @@ def _voice_controller(
     request_identity: _RequestIdentity | None = None,
     identify_speaker: SpeakerIdentifier | None = None,
     schedule_proposal: ProposalScheduler | None = None,
+    prepare_offer: OfferPreparer | None = None,
+    memory_answerer: MemoryAnswerer | None = None,
 ) -> CognitiveController:
     """Compose the bounded controller used by a public voice turn.

@@ -233,6 +249,10 @@ def _voice_controller(
             observed token (Plan 0061, ADR 0020); when omitted the speaker is unknown.
         schedule_proposal: Schedules the background candidate proposal of a successful
             generic turn (Plan 0062); when omitted nothing is proposed.
+        prepare_offer: Prepares the memory offer spoken after a generic reply (Plan 0063);
+            when omitted nothing is offered.
+        memory_answerer: Answers a memory offer (Plan 0063); when omitted an answer-shaped
+            message is ordinary conversation.
     """

     async def legacy_turn(message: str, conversation_id: str) -> TextTurnResult:
@@ -251,6 +271,7 @@ def _voice_controller(
             active_person=speaker.actor,
             suspend_cause=speaker.cause,
             schedule_proposal=schedule_proposal,
+            prepare_offer=prepare_offer,
         )

     if request_identity is None:
@@ -270,6 +291,7 @@ def _voice_controller(
         audit_writer=record_authorization_decision,
         household_tools=HouseholdKnowledgeTools(reader=PolicyGatedV4Reader()),
         consent_resolver=request_identity.resolve_consent,
+        memory_answerer=memory_answerer,
     )


@@ -308,6 +330,71 @@ def _proposal_scheduler(
     return schedule


+def _offer_preparer(
+    *, event: CognitiveEvent[TextTurnPayload], wav_bytes: bytes
+) -> OfferPreparer | None:
+    """Bind the turn's clip and event to the memory-offer preparation (ADR 0021 §9).
+
+    Args:
+        event: The turn's event; its correlation id stamps the audit row and the offer.
+        wav_bytes: The turn's own clip — WAV, 16 000 Hz, mono, int16 — held in memory only,
+            for the voice check that runs only when a candidate waits.
+
+    Returns:
+        The preparation, or ``None`` with the candidate kill-switch off.
+    """
+    if not settings.memory_candidates_enabled:
+        return None
+
+    async def prepare(actor: ActivePersonContext) -> PendingOffer | None:
+        return await prepare_offer(actor, wav_bytes=wav_bytes, event=event)
+
+    return prepare
+
+
+def _memory_answerer() -> MemoryAnswerer | None:
+    """Return the answer to a memory offer for a voice route, or ``None`` with the switch off.
+
+    With the switch off an answer-shaped message is ordinary conversation, and the actor is not
+    even resolved for it.
+    """
+    if not settings.memory_candidates_enabled:
+        return None
+
+    async def answer(
+        parsed: MemoryAnswer,
+        actor: ActivePersonContext,
+        event: CognitiveEvent[TextTurnPayload],
+    ) -> str | None:
+        return await answer_offer(
+            parsed, actor=actor, correlation_id=event.correlation_id, now=utc_now()
+        )
+
+    return answer
+
+
+async def _synthesize_reply(plan: ResponsePlan) -> tuple[str, int, int]:
+    """Synthesize the response and the memory offer as one WAV; the offer never costs the reply.
+
+    The spoken-text log carries the response only: the offer holds a value (ADR 0021 §9). When
+    the combined synthesis fails, the response is synthesized alone, so a failing offer never
+    turns a good reply into a 500.
+
+    Returns:
+        Base64 WAV (16 kHz, mono, int16), the synthesized duration and the TTS time in ms.
+
+    Raises:
+        HTTPException: 500 when even the response alone cannot be synthesized.
+    """
+    if plan.offer is None:
+        return await _run_tts(plan.response)
+    try:
+        return await _run_tts(f"{plan.response} {plan.offer}", logged_text=plan.response)
+    except HTTPException:
+        logger.warning("Memory offer not synthesized; speaking the reply alone")
+        return await _run_tts(plan.response)
+
+
 async def _read_audio_upload(audio: UploadFile) -> bytes:
     """Read and validate WAV 16kHz, mono, int16 upload bytes."""
     try:
@@ -403,6 +490,8 @@ async def transcribe(
             wav_bytes=audio_bytes,
             channel=CandidateChannel.VOICE_CLASSIC,
         ),
+        prepare_offer=_offer_preparer(event=event, wav_bytes=audio_bytes),
+        memory_answerer=_memory_answerer(),
     )
     decision = await controller.decide(event)

@@ -442,7 +531,9 @@ async def transcribe(
         plan = decision

     turn_log.log_decision("voice", plan)
-    audio_base64, duration_ms, tts_ms = await _run_tts(plan.response)
+    # One WAV carries the reply and the memory offer; `llm_response` and the spoken-text log
+    # carry the reply only (ADR 0021 decision 9).
+    audio_base64, duration_ms, tts_ms = await _synthesize_reply(plan)

     total_ms = _elapsed_ms(request_start)
     _log_pipeline_timing(f"voice.{plan.source.value}", stt_ms, plan.duration_ms, tts_ms, total_ms)
@@ -457,7 +548,11 @@ async def transcribe(
         tts_ms=tts_ms,
         total_ms=total_ms,
         authentication_consumed=request_identity.consumed,
-        identity_source=request_identity.identity_source,
+        # A generic reply never reports identity (ADR 0020), including an answer-shaped message
+        # that fell through after its actor was resolved: the wire is the ordinary one.
+        identity_source=None
+        if plan.need is InformationNeed.GENERIC_CONVERSATION
+        else request_identity.identity_source,
     )


@@ -526,7 +621,9 @@ async def transcribe_stream(

     event = _voice_event_from_transcript(text_heard)
     decision = await _voice_controller(
-        resources.http_client, request_identity=request_identity
+        resources.http_client,
+        request_identity=request_identity,
+        memory_answerer=_memory_answerer(),
     ).decide(event)
     # Streaming has no second-round frame upload — a scene request always
     # gets the fixed unavailable plan, regardless of VISION_ENABLED.
@@ -578,6 +675,7 @@ async def transcribe_stream(
                     wav_bytes=audio_bytes,
                     channel=CandidateChannel.VOICE_STREAM,
                 ),
+                prepare_offer=_offer_preparer(event=event, wav_bytes=audio_bytes),
             )
         )
     )
```

- [ ] **Step 4: Run to see them pass, then lint and types.** Run the whole CI selection once with
  the flags pinned (`MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and not eval" -n auto`).
- [ ] **Step 5: Commit** `feat(server): wire the memory dialogue into the voice routes (plan 0063)`; check `git log -1`.

---

## Task 9: The acceptance inspector

**Files:**
- Create: `scripts/inspect_candidates.py`
- Test: new `tests/integration/test_inspect_candidates.py`

**Interfaces:**
- Produces: `inspect(db_path) -> Inspection(candidates, audit, confirmed_facts)` (read-only:
  `mode=ro`, never creates a file); `render(inspection) -> str` (counts, statuses and action names
  only); `main(argv) -> int` (0 with a report, 1 for a missing or unreadable file). Usage:
  `uv run python scripts/inspect_candidates.py [data/omnibot.db]`; it may run while the server is up.

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/tests/integration/test_inspect_candidates.py b/tests/integration/test_inspect_candidates.py
new file mode 100644
--- /dev/null
+++ b/tests/integration/test_inspect_candidates.py
@@ -0,0 +1,130 @@
+"""The acceptance inspector of Plan 0063: counts only, never a value (ADR 0021 §12)."""
+
+from __future__ import annotations
+
+import sqlite3
+from typing import TYPE_CHECKING
+
+import pytest
+from server.settings import settings
+
+from scripts import inspect_candidates
+from server import db
+
+if TYPE_CHECKING:
+    from pathlib import Path
+
+pytestmark = pytest.mark.integration
+
+_CANARY = "zumo de pomelo rosado"
+
+
+@pytest.fixture
+async def brain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
+    """A database migrated by the server, holding two candidates, audit rows and one fact."""
+    path = tmp_path / "brain.db"
+    monkeypatch.setattr(settings, "brain_db_path", path)
+    db._conn = None
+    await db.open_db()
+    await db.run_migrations()
+    conn = db.get_conn()
+    await conn.execute("INSERT INTO entities (id, name, type) VALUES (1, 'Canary', 'person')")
+    await conn.execute(
+        "INSERT INTO memory_candidates (subject_person_id, asserted_by_person_id, predicate, "
+        "value_text, value_key, status, channel, source_correlation_id, proposed_at, "
+        "expires_at) VALUES (1, 1, 'likes', ?, ?, 'proposed', 'voice_classic', 'c', 'a', 'b')",
+        (_CANARY, _CANARY),
+    )
+    await conn.execute(
+        "INSERT INTO memory_candidates (subject_person_id, asserted_by_person_id, predicate, "
+        "status, channel, source_correlation_id, proposed_at, expires_at) "
+        "VALUES (1, 1, 'likes', 'confirmed', 'voice_stream', 'c', 'a', 'b')"
+    )
+    for action, decision in (
+        ("read_personal_conversation_memory", "allowed"),
+        ("confirm_personal_memory", "allowed"),
+        ("confirm_personal_memory", "denied"),
+    ):
+        await conn.execute(
+            "INSERT INTO authorization_audit_events (actor_entity_id, target_entity_id, action, "
+            "data_categories, decision, policy_id, reason, correlation_id, evaluated_at) "
+            "VALUES (1, 1, ?, '[]', ?, 'p', 'r', 'c', 'now')",
+            (action, decision),
+        )
+    await conn.execute(
+        "INSERT INTO literal_facts_v4 (subject_entity_id, predicate, value_text, visibility, "
+        "sensitivity, lifecycle, confidence, confirmed_by_entity_id, confirmed_at) "
+        "VALUES (1, 'likes', ?, 'personal', 'normal', 'active', 1.0, 1, 'now')",
+        (_CANARY,),
+    )
+    await conn.commit()
+    await db.close_db()
+    db._conn = None
+    return path
+
+
+def test_the_report_counts_statuses_audit_rows_and_confirmed_facts(brain: Path) -> None:
+    report = inspect_candidates.inspect(brain)
+
+    assert report.candidates == {
+        "proposed": 1,
+        "offered": 0,
+        "confirmed": 1,
+        "rejected": 0,
+        "expired": 0,
+    }
+    assert report.audit[("confirm_personal_memory", "allowed")] == 1
+    assert report.audit[("confirm_personal_memory", "denied")] == 1
+    assert report.audit[("read_personal_conversation_memory", "allowed")] == 1
+    assert report.audit[("propose_personal_memory", "allowed")] == 0
+    assert report.audit[("confirm_personal_memory", "requires_confirmation")] == 0
+    assert report.confirmed_facts == 1
+
+
+def test_the_printed_report_never_carries_a_value(
+    brain: Path, capsys: pytest.CaptureFixture[str]
+) -> None:
+    assert inspect_candidates.main([str(brain)]) == 0
+
+    out = capsys.readouterr().out
+    assert "proposed=1" in out
+    assert "confirmed facts: 1" in out
+    assert "pomelo" not in out
+
+
+def test_a_database_before_migration_9_reports_zero_candidates(tmp_path: Path) -> None:
+    path = tmp_path / "old.db"
+    sqlite3.connect(path).close()
+
+    report = inspect_candidates.inspect(path)
+
+    assert sum(report.candidates.values()) == 0
+    assert report.confirmed_facts == 0
+
+
+def test_a_missing_file_is_an_error_and_creates_nothing(
+    tmp_path: Path, capsys: pytest.CaptureFixture[str]
+) -> None:
+    path = tmp_path / "absent.db"
+
+    assert inspect_candidates.main([str(path)]) == 1
+    assert not path.exists()
+    assert "absent.db" in capsys.readouterr().err
+
+
+def test_the_inspector_opens_the_file_read_only(brain: Path) -> None:
+    before = brain.read_bytes()
+
+    inspect_candidates.inspect(brain)
+
+    assert brain.read_bytes() == before
+
+
+def test_the_inspector_never_creates_a_database(tmp_path: Path) -> None:
+    """Read-only mode: a missing file is an error, not a new empty database."""
+    path = tmp_path / "absent.db"
+
+    with pytest.raises(sqlite3.OperationalError):
+        inspect_candidates.inspect(path)
+
+    assert not path.exists()
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/integration/test_inspect_candidates.py -q -p no:cacheprovider`
  Expected RED: `ImportError: cannot import name 'inspect_candidates' from 'scripts'`.
- [ ] **Step 3: Implement:**

```diff
diff --git a/scripts/inspect_candidates.py b/scripts/inspect_candidates.py
new file mode 100644
--- /dev/null
+++ b/scripts/inspect_candidates.py
@@ -0,0 +1,142 @@
+"""Count what the memory-candidate dialogue left in a database, never a value (Plan 0063).
+
+The hardware acceptance of ADR 0021 records outcomes only. This script answers the questions
+the acceptance asks of the database — how many candidates are in each status, which policy
+steps were audited and with which decision, and how many personal tastes are confirmed facts —
+without printing a value, a name or a transcript. It opens the file read-only, so the server may
+keep running.
+
+Usage:
+    uv run python scripts/inspect_candidates.py
+    uv run python scripts/inspect_candidates.py path/to/omnibot.db
+
+Exit status: 0 with a report; 1 when the file does not exist or cannot be read.
+"""
+
+import argparse
+from dataclasses import dataclass
+from pathlib import Path
+import sqlite3
+import sys
+
+_DEFAULT_DB = Path("data/omnibot.db")
+_STATUSES: tuple[str, ...] = ("proposed", "offered", "confirmed", "rejected", "expired")
+_ACTIONS: tuple[str, ...] = (
+    "propose_personal_memory",
+    "read_personal_conversation_memory",
+    "confirm_personal_memory",
+)
+_DECISIONS: tuple[str, ...] = ("allowed", "denied", "requires_confirmation")
+_TASTES: tuple[str, ...] = ("likes", "dislikes", "prefers")
+
+
+@dataclass(frozen=True)
+class Inspection:
+    """What the dialogue left in one database: counts only.
+
+    Attributes:
+        candidates: Candidates per status.
+        audit: Audit rows per (memory action, decision).
+        confirmed_facts: Active personal-taste facts that carry who confirmed them.
+    """
+
+    candidates: dict[str, int]
+    audit: dict[tuple[str, str], int]
+    confirmed_facts: int
+
+
+def _tables(connection: sqlite3.Connection) -> set[str]:
+    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
+    return {str(row[0]) for row in rows}
+
+
+def inspect(db_path: Path) -> Inspection:
+    """Count candidates, memory audit rows and confirmed tastes in *db_path*, read-only.
+
+    Args:
+        db_path: A SQLite database file of this project; it is never written.
+
+    Returns:
+        The counts. A database that predates a table reports zeros for it.
+
+    Raises:
+        sqlite3.Error: If the file cannot be opened or read.
+    """
+    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
+    try:
+        tables = _tables(connection)
+        candidates: dict[str, int] = dict.fromkeys(_STATUSES, 0)
+        if "memory_candidates" in tables:
+            for status, count in connection.execute(
+                "SELECT status, COUNT(*) FROM memory_candidates GROUP BY status"
+            ):
+                candidates[str(status)] = int(count)
+        audit = {(action, decision): 0 for action in _ACTIONS for decision in _DECISIONS}
+        if "authorization_audit_events" in tables:
+            placeholders = ", ".join("?" for _ in _ACTIONS)
+            for action, decision, count in connection.execute(
+                "SELECT action, decision, COUNT(*) FROM authorization_audit_events "  # noqa: S608
+                f"WHERE action IN ({placeholders}) GROUP BY action, decision",
+                _ACTIONS,
+            ):
+                audit[(str(action), str(decision))] = int(count)
+        confirmed = 0
+        if "literal_facts_v4" in tables:
+            placeholders = ", ".join("?" for _ in _TASTES)
+            row = connection.execute(
+                "SELECT COUNT(*) FROM literal_facts_v4 WHERE lifecycle = 'active' "  # noqa: S608
+                f"AND confirmed_by_entity_id IS NOT NULL AND predicate IN ({placeholders})",
+                _TASTES,
+            ).fetchone()
+            confirmed = int(row[0]) if row is not None else 0
+    finally:
+        connection.close()
+    return Inspection(candidates=candidates, audit=audit, confirmed_facts=confirmed)
+
+
+def render(inspection: Inspection) -> str:
+    """Return the report as plain lines: counts, statuses and action names only.
+
+    Args:
+        inspection: What ``inspect`` counted.
+
+    Returns:
+        The printable report.
+    """
+    statuses = " ".join(f"{status}={count}" for status, count in inspection.candidates.items())
+    lines = [f"candidates: {statuses}"]
+    for action in _ACTIONS:
+        decisions = " ".join(
+            f"{decision}={inspection.audit[(action, decision)]}" for decision in _DECISIONS
+        )
+        lines.append(f"audit {action}: {decisions}")
+    lines.append(f"confirmed facts: {inspection.confirmed_facts}")
+    return "\n".join(lines) + "\n"
+
+
+def main(argv: list[str] | None = None) -> int:
+    """Print the report for one database file.
+
+    Args:
+        argv: Arguments after the program name; ``None`` reads ``sys.argv``.
+
+    Returns:
+        The process exit status.
+    """
+    parser = argparse.ArgumentParser(description="Count the memory-candidate dialogue's traces.")
+    parser.add_argument("db_path", nargs="?", type=Path, default=_DEFAULT_DB)
+    args = parser.parse_args(argv)
+    if not args.db_path.exists():
+        sys.stderr.write(f"No database at {args.db_path}.\n")
+        return 1
+    try:
+        inspection = inspect(args.db_path)
+    except sqlite3.Error as exc:
+        sys.stderr.write(f"Could not read {args.db_path}: {type(exc).__name__}\n")
+        return 1
+    sys.stdout.write(render(inspection))
+    return 0
+
+
+if __name__ == "__main__":
+    sys.exit(main())
```

- [ ] **Step 4: Run to see them pass, then lint.** `scripts/` is excluded from `ruff check .`:
  `uv run ruff check scripts/inspect_candidates.py` and `uv run ruff format --check scripts/inspect_candidates.py`.
- [ ] **Step 5: Commit** `feat(scripts): count the memory dialogue's traces (plan 0063)`; check `git log -1`.

---

## Task 10: Hardware acceptance by Pipec

**Files:** new `docs/evals/0063-memory-dialogue-acceptance.md` (outcomes only) and its entry in
`docs/evals/README.md`.

This is ADR 0021's *Acceptance*. Pipec speaks; the executor records pass, fail or not run with
counts and durations, never a sentence, a value, a name or a token. Before starting: `just gate`
green; the owner's face **and** voice enrolled (`just speaker-auth-demo --enroll`, three
references; enrolled on 2026-10-15); `FACE_AUTHENTICATION_ENABLED`, `SPEAKER_AUTHENTICATION_ENABLED`,
`ROBOT_FACE_AUTH_ENABLED` and `MEMORY_CANDIDATES_ENABLED` set to `true` in `.env` and **saved**;
`just services`, `just run-server` (the start-up line must read `Candidates reconciled at start-up`,
not `voided`), `just run-robot`. Warm the model with one ordinary sentence first (the first turn
after a cold start took 78 s on 2026-10-15). After each case: `uv run python scripts/inspect_candidates.py`.

- [ ] **Step 1: Case 1 — accept.** Say «La verdad es que me gusta el mate». Wait for
  `Candidate proposal: stored=1` (about a minute on the laptop). Say «hola»: the offer is spoken
  after the reply. Say «Sí, autorizo guardar el mate». Expected: «Listo, lo guardé.»; inspector:
  `confirmed=1`, `audit read_personal_conversation_memory: allowed=1`,
  `audit confirm_personal_memory: allowed=1`, `confirmed facts: 1`.
- [ ] **Step 2: Case 2 — reject.** A new taste («me encanta el jazz»), the offer, then «No
  autorizo guardar el jazz». Expected: «Está bien, no lo guardo.»; `rejected=1`; no new fact.
- [ ] **Step 3: Case 3 — another voice, the owner's face** (D-14: a recording or a different TTS
  voice played near the microphone saying the offered answer while Pipec looks at the camera).
  Expected: an ordinary reply, nothing changes (`offered` stays, no confirm row).
- [ ] **Step 4: Case 4 — no candidate from the wrong speaker.** (a) Nobody in frame says a taste;
  (b) Pipec says a taste with a photo of another face on a phone next to him; (c) Pipec's face and
  a recording of another voice saying a taste. Expected for each: no candidate (`proposed`
  unchanged; the log reads `dropped (strong_unreachable)` or no proposal line).
- [ ] **Step 5: Case 5 — restart between offer and answer.** Get an offer, stop the server, start
  it (the line reads `Candidates reconciled at start-up`), say «hola» (offered again), then answer.
  Expected: promoted.
- [ ] **Step 6: Case 6 — an answer with no offer, or with another value.** «Sí, autorizo guardar el
  café» with no offer, and while an offer waits for something else. Expected: an ordinary turn, no
  write.
- [ ] **Step 7: Case 7 — the benchmark's sentence about a move** («prefiero no hablar de mi
  mudanza»). Expected: no candidate (`not_a_taste` or `negation_unsupported`).
- [ ] **Step 8: Case 8 — measurements (laptop only, D-4).** From the server log: extraction
  duration (voice verified → `Candidate insert`), the turn's latency with and without a waiting
  candidate (the third face-and-voice resolution), and the false-rejection rate of the explicit
  answer: say it five times across offers and count how many parsed. Homelab: not available, not run.
- [ ] **Step 9: Case 9 — replay, measured not defended.** A photo of Pipec plus an earlier
  recording of him saying the offered answer. Record the outcome; it feeds Phase 0's liveness
  decision (ADR 0016 §9).
- [ ] **Step 10: Clean up.** Stop robot and server; `uv run python scripts/scrub_candidates.py
  data/omnibot.db` (never `just reset-db`, D-15); set `MEMORY_CANDIDATES_ENABLED` as Pipec wants
  it (D-3). Write the note and commit `docs: record the plan 0063 acceptance`.

---

## Task 11: Documentation truth; ADR 0021 `Accepted`

**Files (docs only):**
- [ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md): status `Accepted` with
  the date and PR; *Implemented by* records Plan 0063; check decision 9 and *Acceptance* against
  the code and the acceptance note.
- [ADR 0020](../../adr/0020-authorized-actor-in-the-conversation.md): its status line and *Review*
  trigger for the §1 and §2 amendments (ADR 0021 is now `Accepted`).
- [ADR 0019](../../adr/0019-personal-memory-capabilities.md): its status line; §3's `read` and
  `confirm` rows name their first spoken callers (Plan 0063).
- `docs/architecture/memory-and-world-state.md` (the vocabulary and the *Lifecycle* contract:
  proposed → offered → confirmed or rejected), `docs/architecture/identity-and-access.md` (where it
  names `confirm` as unwired), `docs/architecture/current-state.md` (the *Memory candidates* row:
  the offer and the answer; the wire note) and its Archify diagram (validate, then deliver),
  `docs/architecture/README.md`.
- `docs/roadmap/conversational-memory-delivery-map.md` and `docs/roadmap/cognitive-roadmap.md`
  (CM-3a closed; the CM-5 row "decided when CM-3 is planned"; CM-3b next by queue),
  `docs/plans/README.md`, `docs/plans/open/README.md`, `docs/plans/completed/README.md` and the
  move of this plan to `completed/`.
- `docs/runbooks/operator-manual.md`: how to turn the dialogue on (D-3), what the robot says and
  what to answer (D-1, D-2), the inspector, and that `just reset-db` deletes the database (D-15).

- [ ] **Step 1: Update each file** with outcomes and counts from Tasks 8 to 10 and the final
  `just gate`; `rg -n "0063|Plan 0063|unwritten|not written|voseo|Querés|Decime|guardá" docs` and
  fix every statement that is now false.
- [ ] **Step 2: Regenerate the architecture diagram** with the Archify skill, validate then deliver.
- [ ] **Step 3: Verify the docs.** `uv run ruff format --check .`, `uv run python scripts/check_reserved_terms.py`,
  and a check that every relative link of the touched `.md` files resolves.
- [ ] **Step 4: Update the local table** (`docs/roadmap/tabla-tareas.md`, never committed), commit
  `docs: close plan 0063`, open the PR, and squash-merge after green CI only with Pipec's go-ahead
  for this plan; delete the branch.

---

## Review record

**Independent review, 2026-10-15.** Two read-only reviewers that had not written the code (one on
the whole change against ADR 0021, one on the tests with in-memory mutations) read the rehearsal
and probed it with their own scripts. Each finding below was reproduced, given a RED test in its
owning task, fixed in the rehearsal, and the plan was regenerated from the fixed commits.

| # | Finding (severity) | Disposition |
|---:|---|---|
| 1 | A value starting with «lo» («lo picante») could never be confirmed: the offer asked for an answer the grammar rejected (important) | **Fixed** (Task 2): «lo» is no longer a connector. Round-trip test in Task 4: the words the offer asks for always resolve that offer |
| 2 | The natural «No, no autorizo…», «Sí, sí…», «Sí, claro…», «autorizo a guardar…» and a trailing «gracias» or «por favor» fell through (important) | **Fixed** (Task 2): openers, a repeated «sí»/«no», «a guardar» and courtesy words are handled |
| 3 | The reject path wrote even when the audit failed or the policy denied (mutation survived; critical for the tests) | **Pinned** (Task 4): the reject is audited before the candidate changes, and a failing audit never rejects |
| 4 | The classic spoken-text log was unpinned: the offer could have reached `log_spoken` (mutation survived) | **Pinned** (Task 8) |
| 5 | «es que» and «que» as free lead-in words admitted «siempre que me gusta…» (a condition) (minor) | **Fixed** (Task 1): closed filler phrases, not free words |
| 6 | The classic route's double `decide()` could answer, and audit, twice (minor) | **Fixed** (Task 5): one attempt per event |
| 7 | An `allowed` read row could be written for an offer another turn already made, or one that lapsed (minor) | **Fixed** (Tasks 3, 4): `still_offerable` before the audit; the residue is D-7 |
| 8 | A failing classic synthesis lost the reply (500) after the offer was committed (minor) | **Fixed** (Task 8): the reply alone is synthesized |
| 9 | Two offers could be open at once, and an answer could resolve the wrong one (minor) | **Fixed** (Task 3): one open offer per person (D-8) |
| 10 | Ordinary speech («guarda silencio», «olvídalo, no importa», «bórralo todo») was read as an answer (minor) | **Fixed** (Task 2): after the short verbs the value starts with an article (D-2) |
| 11 | A fall-through answer reported `identity_source` (`face`) where «hola» reports `null` (important) | **Fixed** (Task 8): a generic plan reports no identity (D-11); a field-by-field wire test |
| 12 | The stream's offer could run after generation, survive a hang-up, commit after a TTS failure of the reply, and count its commit as model time; the classic `duration_ms` and a cancelled turn were unpinned (mutations survived) | **Fixed and pinned** (Tasks 6, 7) |
| 13 | The streaming answer, a consent revoked between turns, `/vision/respond`, `/chat` offering, the inspector's read-only mode and `requires_confirmation` rows were untested or unreported (minor) | **Pinned or fixed** (Tasks 8, 9) |
| m | A weak actor never reaches the store; a voice verified for another person; hard-coded «gusta»/«gustan» | **Pinned / moved to `lexicon`** (Task 4) |

**What the reviewers verified and found correct:** no path offers, answers or promotes without
face and voice of the same person on the turn's clip, and none uses a token; nothing tells a
non-owner whether a candidate or an offer exists; values stay out of logs, `llm_response`, the
history and `log_spoken`; the read step is audited before `mark_offered`, the confirm step before
the reject and inside `promote`; the switch off injects nothing; `/chat` and `/vision/respond`
never offer or answer; protected and dated rules win over the answer shape; window, restart and
expiry edges are consistent between the readers and the housekeeping.

**What no review of a plan can close** (it needs Pipec at the microphone): how often Whisper
writes the answer so that it parses, whether the 60 s answer window is long enough on the laptop,
the cost of the third face-and-voice resolution per turn, and replay. Task 10 measures them.

## ADR 0021 coverage

| ADR section | Where |
|---|---|
| §3 the firewall rule for offers, answers and promotions | Tasks 4, 5, 8 |
| §4 the gate (filler phrases, D-5) | Task 1 |
| §6 compare-and-set, offers, the answer window, the oldest first, no oracle | Tasks 3, 4 |
| §7 the read and confirm steps, audit first, same person | Tasks 4, 5 |
| §8 promotion through the writer | Task 4 |
| §9 offer and answer: strong turn, placement, phrases, the answer repeats the value, no oracle, results, replay | Tasks 2, 4 to 8, 10 |
| §12 logging (ids and closed outcomes only) | Tasks 4, 7, 8 |
| *Acceptance* | Task 10 |

## Completion criteria

1. Tasks 0 to 11 done, one commit per task, every test RED before GREEN.
2. `just gate` green with at least **3132** tests collected (baseline 2972), `ruff`
   clean over the explicit paths of every file touched, `scripts/` included.
3. With `MEMORY_CANDIDATES_ENABLED=false` nothing is offered or answered (Task 8).
4. The acceptance of Task 10 recorded by Pipec (outcomes only), each case pass, fail or not run
   with its reason; a failed case is reported, not hidden, and decides with Pipec whether ADR 0021
   is accepted.
5. Every document of Task 11 updated; this plan moved to `completed/`; ADR 0021 `Accepted`.

## Rollback boundary

Reverting the squash-merge restores Plan 0062's behaviour (candidates proposed, never offered).
No migration and no setting is added. **A promoted fact stays** in `literal_facts_v4` (with who
confirmed it), and an `offered` candidate returns to `proposed` at the next start-up; nothing reads
the facts yet (CM-5). The cross-cutting changes are the controller's new branch, the text-turn
seam's optional offer, the stream's optional event and the classic route's identity rule for
generic plans (null, as before for every generic reply).

## Not here, and why

- **Reading a stored preference back** (CM-5), **correcting or forgetting** it (CM-6),
  **episodes** (CM-4), everything of **CM-3b** (third parties, pets, `lives_in`, reported facts,
  the disclosure rule, perception, the first `SECURITY` datum, the benchmark's `confirm` step) and
  the real longitudinal scenario (CM-7).
- **The existing controller phrases in voseo** («Sos …», «Tenés …», «preguntás») stay as they
  are: changing them is a separate, small change Pipec may ask for (it touches tests that pin
  them), not part of the dialogue.
- **`/chat` and `/vision/respond`** never offer or answer: no audio, so no `strong`.
- **Liveness and replay defence**, enrolment as the first setup step, access levels, "you are with
  someone, still want it?": Phase 0 (ADR 0021 decision 13).
- **A homelab measurement** (D-4).

## Execution record

*(Filled in when the plan is executed.)*
