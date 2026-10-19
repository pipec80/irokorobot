# 0066 — The answer to a memory offer: a closed verb alone is enough

> **Status:** `Ready` and `NOW` — promoted by Pipec on 2026-10-19, who confirmed D-1 to D-7 (D-1 is
> his decision of that day, after the Plan 0064 hardware session; D-2 to D-7 he confirmed after an
> example of each, and that a bare «sí» stays out). Written the same day. **Not rehearsed** in a
> scratch copy: the tasks below are specifications (files, rules, tests to write first), not
> rehearsed diffs. To be executed in a **new session**. It does not depend on Plan 0065 and Plan
> 0065 does not depend on it.

> **For agentic workers:** if the status above does not say `Ready`, stop: Pipec has not promoted
> this plan. REQUIRED SUB-SKILLS: `superpowers:executing-plans`,
> `superpowers:test-driven-development`, `superpowers:verification-before-completion`,
> `superpowers:finishing-a-development-branch`. **Pipec's rules win over the skills:** one plain
> branch from `main` (`git checkout -b`), never a git worktree, subagents only if Pipec asks, and
> this plan lives under `docs/plans/`. Implement exactly the tasks below, in order, one commit per
> task, each code test observed RED for the stated reason first (the text-only Task 5 has no RED).
> If evidence contradicts the plan, stop and report the conflict instead of redesigning. Pipec runs
> every local process (server, robot, Ollama, anything that uses the camera or the microphone);
> record outcomes only, never a sentence, a value or a name. The Bash tool of this environment loses
> backslashes and non-ASCII characters in heredocs: create and edit files with the Write and Edit
> tools. Run the suite with `MEMORY_ENABLED=false` (CI does). **Dates:** a test that builds data at a
> fixed date must also pin the clock (`clock=lambda: ...`).

**Goal:** Accepting an offered memory takes one short phrase: «sí, autorizo.» A closed verb alone
(«autorizo», «sí, autorizo», «apruebo», «sí, guarda», «no autorizo») resolves the one open offer of
the verified speaker, without repeating the value. A bare «sí» still resolves nothing. The spoken
offer teaches the short answer. No wire change, no migration, no new route, no new setting.

**Why:** In the Plan 0064 hardware session the answer that repeated the value («sí, autorizo
guardar el chocolate») was understood 1 of 2 times; the one that failed was transcribed with an extra
word inside the value («autorizo comer, guardar chocolate») and fell through to ordinary
conversation. Pipec found repeating the value cumbersome and decided (D-1, 2026-10-19) that the verb
is enough. Fewer words means fewer chances for the speech-to-text to garble them.

**Architecture:** Three small changes in the order of the data. (1) The store: `find_offered` takes
`value_key: str | None`; `None` means «the one open offer of that person» and returns it only when
exactly one is open inside the answer window (zero or more than one: nothing). (2) The grammar:
`parse_memory_answer` returns `MemoryAnswer(accept, phrase="")` when the message has a closed verb and
no value; `""` means «the open offer». (3) The dialogue: `_find_open_offer` calls `find_offered` with
`None` for such an answer. Everything else is unchanged: the controller still resolves face and voice
**first** for every message of this shape, `strong` is still required, a value that is present must
still match the open offer, and anything that is not a valid answer falls through byte-identical. Then
the offer's last sentence changes to «Dime: sí, autorizo.».

**Tech Stack:** Python 3.12, FastAPI, SQLite (aiosqlite), pytest. No new dependency.

**Spec:** [ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md) decision 9 (the
answer grammar; this plan amends the sentence that makes the value mandatory — Pipec's option A of
2026-10-15 — with his decision D-1 of 2026-10-19), the Plan 0064 execution record
([Plan 0064](../completed/0064-speech-and-dialogue-quality.md)) for the hardware numbers, and the
repository rules in `.claude/rules/` (not tracked; read them from the working copy).

## Task overview

| # | Task | Closes |
|---:|---|---|
| 0 | Revalidate the baseline | — |
| 1 | The store finds the one open offer | the lookup the short answer needs |
| 2 | The grammar accepts a closed verb alone | D-1, D-2, D-3 |
| 3 | The dialogue resolves the one open offer | the short answer works end to end |
| 4 | The offer teaches the short answer | D-5 |
| 5 | Documentation truth | ADR 0021 amendment and the docs it makes stale |
| 6 | Hardware acceptance (Pipec) | the count of understood answers |

## Global Constraints

- No real household data in any tracked file, test, prompt, doc or commit message: invented
  canaries only (`scripts/check_reserved_terms.py` guards it).
- The firewall of ADR 0021 decisions 3 and 9 is untouched: only the face-and-voice composite of
  the same person on that turn's own clip answers; the actor is resolved **first** for every message
  of the answer shape, whether or not an offer exists (no oracle); a token never answers; anything
  that is not a valid answer of that actor falls through to ordinary generation, byte-identical.
- A bare «sí», «ya», «dale» or «po» alone, or a verb with a **different** value, resolves nothing.
- The audio contract is untouched (WAV, 16 000 Hz, mono, int16); no `print()`; Google docstrings;
  type hints; `ruff` clean over the explicit paths of every file touched (including `scripts/`);
  `mypy server/src robot/src` clean.
- A commit title is at most 72 characters; check `git log -1` after every commit.
- `MEMORY_CANDIDATES_ENABLED` stays `false` by default.

## Decisions

1. **D-1 — A closed verb alone is enough (Pipec, 2026-10-19).** A bare «sí» is still not (his
   choice among «verbo solo», «sí suelto» and «como está»). Face and voice verified on that turn stay
   mandatory.
2. **D-2 — Which verbs stand alone (Pipec, 2026-10-19).** The long verbs `autorizo`, `autoriza`,
   `apruebo`, `aprueba`, alone or followed by `guardar`, `a guardar` or `que guardes` («autorizo
   guardar» is a verb phrase, not a value). The short verbs `guarda` and `guárdalo` stand alone
   **only after a leading «sí»**: they are ordinary imperatives («guarda silencio»), and the «sí»
   marks the intent.
3. **D-3 — Rejections alone (Pipec, 2026-10-19).** `no autorizo`, `no apruebo`, `no autoriza`, `no
   aprueba` (long forms included), `no lo guardes` and `no guardes` stand alone, because they carry
   their own «no». `olvídalo` and `bórralo` keep requiring the value: alone they are ordinary speech
   («olvídalo, no importa») and would erase a candidate by accident.
4. **D-4 — Exactly one open offer (Pipec, 2026-10-19).** A valueless answer resolves the person's open
   offer only when exactly one is open inside the answer window
   (`MEMORY_CANDIDATE_ANSWER_SECONDS`, 60 s). Zero or more than one falls through, which cannot be
   told apart from any other non-answer. The store already offers at most one per person, so more
   than one is defensive.
5. **D-5 — The offer says the short answer (Pipec, 2026-10-19).** `OFFER_QUESTION` becomes «¿Quieres
   que lo guarde? Dime: sí, autorizo.» The statement before it already names the value.
6. **D-6 — A value that is present must still match (Pipec, 2026-10-19).** «Autorizo guardar el chocolate» with an open
   offer for another value resolves nothing, and a garbled value (the failed attempt of the hardware
   session) still falls through. The short answer is the fix for that failure, not a rescue of it.
7. **D-7 — The cost is stated in the ADR, not hidden (Pipec, 2026-10-19).** The value no longer has to be known to
   answer. A recording of the owner saying «autorizo» played in front of the robot, together with the
   owner's face, inside the 60 s window of an open offer, can now promote that offer without knowing
   its value. Replay was already undefended (ADR 0016 §9) and a recording of the full phrase worked
   the same way once the offer had been spoken aloud; the window, the single open offer, the face and
   voice of the same person and the audit stay as they are. The ADR amendment says so.

## Required reading

- `AGENTS.md`, `docs/architecture/implementation-guardrails.md`, `.claude/rules/`.
- [ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md) decision 9 and
  *Acceptance*; [the Plan 0064 execution record](../completed/0064-speech-and-dialogue-quality.md).
- `server/src/server/cognition/{intent_resolution,controller}.py`,
  `server/src/server/memory/{candidates,candidate_dialogue,lexicon}.py`.
- The tests named in each task.

## Permitted files

- Production: `server/src/server/cognition/intent_resolution.py`,
  `server/src/server/memory/{candidates,candidate_dialogue,lexicon}.py`.
- Tests: `tests/unit/test_memory_answer_grammar.py`, `tests/unit/test_cognitive_controller.py`,
  `tests/integration/{test_memory_candidates_store,test_candidate_dialogue,test_memory_dialogue_routes}.py`.
- Docs (Task 5): ADR 0021 (amendment), `docs/runbooks/operator-manual.md`,
  `docs/architecture/current-state.md`, `docs/roadmap/cognitive-roadmap.md`, the plan index files and
  this plan.

No new URL, field, migration, setting or dependency. The controller, the routers and the robot are
not edited: the answerer seam already passes the parsed answer through.

## Review Focus

The inputs the tasks' tests do not name but a person will meet; each has its test in the task that
owns the code.

1. A casual «autorizo» (or «sí, guarda») with **no** open offer: it must fall through to ordinary
   conversation (Task 3), costing only the face-and-voice check.
2. Two live offers of the same person, or an offer past its 60 s window: nothing is resolved (Task 1).
3. «Guarda» or «guárdalo» **without** «sí», and «olvídalo» or «bórralo» alone: still refused
   (Task 2).
4. Another person's open offer, or a weaker actor (face only, a token): never answered, with or
   without a value (Task 3).
5. A valueless answer on the classic route, where the answerer is absent (`/chat`,
   `/vision/respond`): falls through unchanged (Task 3).

---

## Task 0: Revalidate the baseline

- [ ] **Step 0: Status.** This plan says `Ready`; otherwise stop.
- [ ] **Step 1: Branch.** `git checkout main && git pull`, clean tree, then
  `git checkout -b feat/0066-verb-only-answer`; record the base SHA.
- [ ] **Step 2: Baseline.** `just gate`; record the outcome and test count (3327 at the close of
  Plan 0064). A pre-existing failure is reported, not hidden.
- [ ] **Step 3: Re-audit.** `rg -n "def find_offered" server/src`, `rg -n "def parse_memory_answer"
  server/src`, `rg -n "OFFER_QUESTION" server/src` and `rg -n "_find_open_offer" server/src` each find
  what this plan names. A difference is reported before code.

## Task 1: The store finds the one open offer

**Files:** modify `server/src/server/memory/candidates.py`; tests modified
`tests/integration/test_memory_candidates_store.py`.

**Interfaces.** Produces: `find_offered(subject_person_id: int, value_key: str | None, *, now:
datetime) -> Candidate | None`. With a `str`, exactly today's behavior. With `None`: the person's
`offered` candidate that is inside the answer window and not lapsed, **only if there is exactly one**;
`None` otherwise (also with the kill-switch off). `tests/unit/test_architecture_guards.py` already
pins `find_offered` to the store and the dialogue; no name is added.

- [ ] **Step 1: Failing tests** (next to the existing `find_offered` tests; pin the clock with the
  file's `_T0`): (a) one open offer → returned with `None`; (b) no open offer → `None`; (c) two open
  offers of the same person (insert both and `mark_offered` both directly) → `None`; (d) the open
  offer of **another** person is never returned; (e) an offer past the answer window → `None`; (f) the
  kill-switch off → `None`; (g) a value-keyed call behaves exactly as before. Expected RED: `TypeError`
  or a wrong result, because `None` is not a valid key today.
- [ ] **Step 2: Implement.** Query with `LIMIT 2` when `value_key is None` (no `value_key` filter),
  return the row only if exactly one came back; keep the SQL, ordering and `LIMIT 1` for a key.
  Update the docstring (Args, Returns) and the module docstring's list of readers if it names
  arguments.
- [ ] **Step 3:** run `tests/integration/test_memory_candidates_store.py
  tests/unit/test_architecture_guards.py`; lint and types over the files.
- [ ] **Step 4: Commit** `feat(server): find a person's one open offer without a value (plan 0066)`.

## Task 2: The grammar accepts a closed verb alone

**Files:** modify `server/src/server/cognition/intent_resolution.py`; tests modified
`tests/unit/test_memory_answer_grammar.py` and `tests/unit/test_intent_resolution.py` (run only).

**Interfaces.** `MemoryAnswer(accept: bool, phrase: str)` keeps its shape; `phrase == ""` now means
«the open offer» (document it on the class). `parse_memory_answer(message: str) -> MemoryAnswer | None`
keeps its signature.

- [ ] **Step 1: Failing tests** (parametrized; `message → (accept, phrase)`, `phrase` folded).
  Accepted after this task: «Autorizo.» → `(True, "")`; «Sí, autorizo.» → `(True, "")`; «Autoriza» →
  `(True, "")`; «Apruebo, gracias» → `(True, "")`; «Aprueba po» → `(True, "")`; «Dale, apruebo» →
  `(True, "")`; «Sí, autorizo guardar» → `(True, "")`; «Autorizo a guardar» → `(True, "")`; «Autoriza
  que guardes» → `(True, "")`; «Sí, guarda» → `(True, "")`; «Sí po, guárdalo» → `(True, "")`; «No
  autorizo» → `(False, "")`; «No, no apruebo» → `(False, "")`; «No autoriza guardar» → `(False, "")`;
  «No lo guardes» → `(False, "")`; «No guardes» → `(False, "")`. Unchanged and still accepted with a
  value: «Sí, autorizo guardar el mate» → `(True, "el mate")` and every case of the existing tables.
  Still refused (`None`): «Sí», «Sí po», «Ya», «Dale», «Ok», «Guarda», «Guárdalo», «Guarda
  silencio», «Sí, guarda silencio», «Olvídalo», «Bórralo», «Olvídalo, no importa», «Bórralo todo»,
  «Sí, olvídalo», and «Autorizo guardar» followed by seven words (the six-word limit). «Autorizo
  comer» is **not** refused: it parses with the value «comer» and falls through later because no
  offer has that value (D-6). Expected RED: the accepted valueless cases fail
  with `assert None == MemoryAnswer(...)`.
  Run first: `uv run pytest tests/unit/test_memory_answer_grammar.py -q -p no:cacheprovider`.
- [ ] **Step 2: Implement** in `intent_resolution.py`. `parse_memory_answer` remembers whether a
  leading «sí» (folded `si`) was consumed among the openers and passes it to `_answer`. In `_answer`,
  when no value remains (after dropping `a guardar` and one leading `mi`/`mis`): a **long** prefix
  (D-2) returns `MemoryAnswer(accept, "")`; a **short** prefix returns it only for `guarda` and
  `guardalo` with the leading «sí», and for `no lo guardes` and `no guardes` always (D-3); `olvidalo`
  and `borralo` return `None`. The value rules are untouched (articles for short verbs, at most six
  words, no value starting with «guardar» or «que»). A prefix now also matches when the text **equals**
  it (today it needs a following space), longest prefix first as before. Update the module comment, the
  `parse_memory_answer` docstring and the `MemoryAnswer` docstring.
- [ ] **Step 3:** run `tests/unit/test_memory_answer_grammar.py tests/unit/test_intent_resolution.py`
  (expected: green, the 64 fixtures of `intent_resolution_es.json` unchanged); lint and types.
- [ ] **Step 4: Commit** `feat(server): accept a closed verb alone as the memory answer (plan 0066)`.

## Task 3: The dialogue resolves the one open offer

**Files:** modify `server/src/server/memory/candidate_dialogue.py`; tests modified
`tests/integration/test_candidate_dialogue.py`, `tests/unit/test_cognitive_controller.py` (run, and
one added case) and `tests/integration/test_memory_dialogue_routes.py`.

**Interfaces.** Consumes: `candidates.find_offered(person_id, None, now=...)` from Task 1 and
`MemoryAnswer(..., phrase="")` from Task 2. `answer_offer`, `MemoryAnswerer` and the controller
signatures are unchanged.

- [ ] **Step 1: Failing tests** in `test_candidate_dialogue.py` (reuse `owner`, `_candidate(...,
  offered=True)`, `_strong`, `_status`, `_likes`; pin `_NOW`): (a) `MemoryAnswer(True, "")` with one
  open offer promotes it, says `ANSWER_SAVED_PHRASE` and writes one fact; (b) `MemoryAnswer(False, "")`
  rejects it after auditing the confirm step and erases the value; (c) `MemoryAnswer(True, "")` with
  **no** open offer returns `None` and changes nothing; (d) with two open offers returns `None` and
  changes nothing; (e) another person's open offer is never answered; (f) a weaker actor (face only)
  and a token get `None`; (g) past the 60 s window returns `None`; (h) `MemoryAnswer(True, "otra
  cosa")` with an open offer for another value still returns `None` (D-6); (i) the log line of a
  valueless answer carries ids and an outcome and no value (reuse the existing no-value log
  assertion). In `test_cognitive_controller.py`: a valueless answer still resolves the actor
  **before** the answerer (extend the order test with the message «Sí, autorizo.»). In
  `test_memory_dialogue_routes.py`: «Sí, autorizo.» on the stream and on the classic voice route
  promotes the offer through the route, and the same message on `/chat` (no answerer) falls through to
  the ordinary reply. Expected RED: (a), (b) and the route cases return `None` because an empty key is
  rejected today.
- [ ] **Step 2: Implement** in `_find_open_offer`: `key = comparison_key(answer.phrase)`; when
  `answer.phrase == ""` call `find_offered(person_id, None, now=now)`, otherwise `find_offered(person_id,
  key, now=now)` as today (an empty key from a non-empty phrase, such as a phrase of stop-words, still
  returns `None`). Update the `answer_offer` docstring.
- [ ] **Step 3:** run `tests/integration/test_candidate_dialogue.py tests/unit/test_cognitive_controller.py
  tests/integration/test_memory_dialogue_routes.py tests/unit/test_architecture_guards.py`; lint and
  types.
- [ ] **Step 4: Commit** `feat(server): answer the one open offer without its value (plan 0066)`.

## Task 4: The offer teaches the short answer

**Files:** modify `server/src/server/memory/lexicon.py` (`OFFER_QUESTION`) and
`server/src/server/memory/candidate_dialogue.py` (`compose_offer` docstring); tests modified
`tests/integration/test_candidate_dialogue.py` and `tests/integration/test_memory_dialogue_routes.py`.

- [ ] **Step 1: Failing tests:** the four parametrized offer cases of
  `test_the_offer_is_neutral_spanish_and_tells_the_exact_answer` (rename it to `...tells_the_short_
  answer`) now expect «Antes me dijiste que te gusta el mate. ¿Quieres que lo guarde? Dime: sí,
  autorizo.» and the like; the round-trip test parses the instructed words («sí, autorizo.») to
  `MemoryAnswer(True, "")`, and that answer resolves the offer made by `compose_offer` (use the
  `_candidate` helper with `offered=True`); any route test that asserts the old last sentence follows.
  Expected RED: `AssertionError` on the old text.
- [ ] **Step 2: Implement:** `OFFER_QUESTION = "¿Quieres que lo guarde? Dime: sí, autorizo."` (the
  `{value}` placeholder goes; `compose_offer` stops formatting it into the question). Update the
  docstring: the question dictates the short answer.
- [ ] **Step 3:** run the two test files; lint and types.
- [ ] **Step 4: Commit** `feat(server): offer the short answer to the owner (plan 0066)`.

## Task 5: Documentation truth (text only, no RED)

- [ ] ADR 0021 decision 9: amend the *answer repeats the value* bullet (the closed verb alone
  resolves the one open offer; the value stays optional, a present value must match; the bare «sí»
  still resolves nothing; the short verbs and the rejections of D-2 and D-3), the *Phrases* bullet
  (the offer ends with «Dime: sí, autorizo.»), and add D-7's cost (a recording of «autorizo» inside
  the window) next to the replay bullet; add a dated line to its status.
- [ ] `docs/runbooks/operator-manual.md`: the answer forms and the new offer wording, the
  3-to-4 s face-and-voice check that a bare «autorizo» now triggers when no offer is open.
- [ ] `docs/architecture/current-state.md` (the memory row), `docs/roadmap/cognitive-roadmap.md`
  (close the follow-up row «The explicit answer against the speech-to-text»), the plan index files
  and the local table (never committed); move this plan to `completed/` with its execution record.
- [ ] `uv run ruff format --check .`, `uv run python scripts/check_reserved_terms.py`, and a check
  that every relative link of the touched `.md` files resolves; commit `docs: close plan 0066`; open
  the PR; merge only with Pipec's go-ahead.

## Task 6: Hardware acceptance (Pipec runs everything)

Counts only, never a sentence or a value. With `MEMORY_CANDIDATES_ENABLED=true`, face and voice
enrolled, in a full sentence of about three seconds near the microphone:

- [ ] At least five offers answered «sí, autorizo.»: how many promoted («Listo, lo guardé.»).
- [ ] Two offers answered «no autorizo.»: how many rejected («Está bien, no lo guardo.»).
- [ ] Two offers answered with the old full phrase: still promoted.
- [ ] Three casual uses of «autorizo» or «sí, guarda» in ordinary conversation **with no open
  offer**: nothing is saved and the reply is an ordinary one.
- [ ] Turn `MEMORY_CANDIDATES_ENABLED` back to `false` afterwards if the candidates are not wanted.

If fewer than 4 of 5 promote, report the count and stop: the next candidate is the
speech-to-text prompt or the hotwords, which is a separate plan.

## Completion criteria

1. Tasks 0 to 6 done, one commit per task, every code test RED before GREEN.
2. `just gate` green with the baseline plus the new tests.
3. A closed verb alone promotes or rejects the one open offer of the verified speaker, and every
   refusal of Task 2 holds; a valueless answer with no, two or another person's offer, a weaker
   actor, a token, an expired window, or on a route without an answerer changes nothing.
4. The spoken offer ends with «Dime: sí, autorizo.».
5. The hardware counts of Task 6 are recorded.

## Rollback boundary

Each task is one commit. Task 4 (the offer wording) may be reverted alone and the old full phrase
still works. Tasks 1 to 3 are reverted together. Nothing is stored differently and no setting or
migration is added.

## Not here, and why

- A bare «sí» (Pipec decided against it).
- Resolving an offer by the speech-to-text prompt or hotwords: tried only if Task 6 misses.
- A reply that mixes a confirmation with a new request («sí, autorizo, y dime la hora»): the
  six-word limit and the closed grammar refuse it; unplanned.
- Replay or liveness defences: ADR 0016 §9, measured and not closed.
- The CM-3b writer core (Plan 0065) and the household rules (ADR 0022).

## Execution record

Executed 2026-10-19 on `feat/0066-verb-only-answer` (base `0009140`), tasks 0 to 5. **Task 6
(hardware acceptance) is pending: Pipec runs it**, and the plan stays in `open/` and `NOW` until
its counts are recorded here.

- **Baseline:** `just gate` 3326 passed plus one `slow` test (`test_the_real_encoder_returns_the_frozen_shape`)
  that timed out under the parallel load and passed alone (3 of 3), so 3327 as at the close of
  Plan 0064. Not related to this plan.
- **Commits:** one per task (1 to 4), then the review fixes and the documentation.
- **Rulings.** (1) A dangling «mi»/«mis» after a verb («Autorizo mi») is refused, not read as a verb
  alone: it is a garbled value (D-6). (2) The round-trip test of the offer now resolves a real offer
  through `answer_offer`, and the longest-value test keeps covering the full phrase (the value stays
  optional), because the key of an empty phrase is empty.
- **Reviews** (three independent read-only reviewers on the branch): no Critical and no
  correctness finding. Fixed: tests that pinned the «sí» cue of the short verbs, the rejections
  alone, the visitor's offer not making the owner's ambiguous, the vision route with the short
  answer, the rejection and the no-offer case on the streaming route, and the full-phrase round
  trip; the ADR now states the honest-accident cost next to the replay cost.
- **Deferred minors (not done):** a conditional «si» without accent counts as the «sí» cue
  («si guarda»); emphatic phrasings such as «Sí, autorizo, guárdalo» or «Autorizo, sí» parse a
  trailing word as a value and fall through (D-6; a possible follow-up if Task 6 misses);
  `mark_offered` does not repeat the «no other open offer» guard (fails closed, existed before);
  `tests/unit/test_claim_guard.py` still lists the old offer sentence (outside the permitted files);
  `docs/architecture/memory-and-world-state.md` and ADR 0022 still say the answer repeats the value
  (outside the permitted files).
