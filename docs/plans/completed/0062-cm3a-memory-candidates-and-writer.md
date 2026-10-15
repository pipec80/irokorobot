# 0062 — Memory candidates and the canonical writer, first cut (CM-3a)

> **Status:** `Closed` 2026-10-15 — executed on branch `feat/0062-cm3a-candidates-and-writer`
> (PR #183), see *Execution record*. It is the first of the two plans of CM-3a: it has **no spoken
> dialogue and no hardware**; the offer, the answer and the hardware acceptance are Plan 0063
> (free), and [ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md) stays
> `Proposed` until it closes.
>
> History: written 2026-10-14 from ADR 0021, rehearsed in a scratch copy of `main` (`f92e43d`) and
> independently reviewed (see *Review record*); promoted to `Ready` and `NOW` by Pipec on
> 2026-10-14, who confirmed decisions D-1 to D-14 as written.

> **For agentic workers:** this plan is closed. While it was open, the rule was: if the status did not say `Ready`, stop (Pipec had not promoted it).
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
> non-ASCII characters in heredocs: create and edit files with the Write and Edit tools. Run the
> test suite with `MEMORY_ENABLED=false` (CI does; a developer's `.env` may switch things on) and
> note that `tests/conftest.py` pins `MEMORY_CANDIDATES_ENABLED` off for every test.

**Goal:** What the identified owner says about their own tastes (`me gusta el mate`) is kept as a
short-lived **candidate**, in its own table, only when the face **and** the voice of that same
person are verified on that turn's own clip; one deterministic writer can promote an offered
candidate into one canonical V4 literal fact with who confirmed it and when. Nothing is spoken,
nothing is offered, no route calls the writer, and with `MEMORY_CANDIDATES_ENABLED=false` (the
default) nothing is proposed, stored or promoted and every live value is voided at the next
start-up that opens the database (`MEMORY_ENABLED=true`).

**Architecture:** A background task replaces `consolidate_turn`. After a successful generic voice
turn, `text_turn` hands the user's words and the face-identified actor to a scheduler that the
voice route builds around the turn's clip, event and channel. The task runs, cheapest first: the
**preference gate** (pure), a token-free face actor, the **voice check** of the turn's own clip for
the person the face named, a one-at-a-time and per-hour **limiter**, the **extractor** (one model
call that sees only the user's words, no retry), the pure **classifier**, a re-check that both
consents are still active, the **policy check** (`propose_personal_memory`, audited before the
effect) and the **store** (`memory_candidates`, migration 009). The **writer** (`promote`) is
proven with doubles and left as a seam. `consolidate_turn`, `PROPOSE_MEMORY` and `COMMIT_MEMORY`
leave the runtime; the benchmark's extraction seam stays.

**Tech Stack:** Python 3.12, FastAPI background tasks, aiosqlite (one connection, `secure_delete`),
pydantic, pytest. No new dependency, no new route, no wire change; one migration (009).

**Spec:** [ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md) (this plan
implements decisions 1 to 8, 10, 11 and 12; decision 9 is Plan 0063),
[ADR 0019](../../adr/0019-personal-memory-capabilities.md) (the policy this plan finally consumes),
[ADR 0020](../../adr/0020-authorized-actor-in-the-conversation.md) (the generic speaker and the
amendments of ADR 0021), [ADR 0016](../../adr/0016-face-and-voice-identity-fusion.md) §1 to §9,
[ADR 0011](../../adr/0011-sqlite-transaction-ownership.md) and
[ADR 0009](../../adr/0009-locked-posture-and-scoped-capabilities.md); the CM-3a row of the
[conversational-memory map](../../roadmap/conversational-memory-delivery-map.md) and of the
[roadmap](../../roadmap/cognitive-roadmap.md#canonical-pre-electronics-delivery-portfolio).

**Rehearsal (2026-10-14).** Every diff below was produced test-first in a scratch copy of `main`
(`f92e43d`), one commit per task, with the real virtual environment. Under the CI marker filter
(`-m "not slow and not hardware and not eval" -n auto`) the suite went from **2580** to
**2888**; unfiltered it went from **2597** to **2905**. Per task, in collected
tests: +308: Task 1 +10, Task 2 +61, Task 3 +63, Task 4 +10, Task 5 +16, Task 6 +25, Task 7 +5, Task 8 +18, Task 9 +32, Task 10 +25, Task 11 +29, Task 12 +9, Task 13 +6, Task 14 -1. `ruff check .`, `ruff format --check .`, the explicit-path lint of `scripts/`
that the pre-commit hook runs, `ruff --select S server/src robot/src`,
`mypy server/src robot/src` (115 files), `pyright` (0 errors) and
`vulture --min-confidence 80` were clean at the end. The RED of every task was observed for the
stated reason by checking out the parent's code with only that task's tests (Task 13's RED is an
`ImportError` at collection: the new names do not exist yet). The plan's own blocks were then
re-applied to a clean copy of `main` and reproduced all 68 changed files byte for byte. Twenty
**mutations** were applied to the finished code and each was killed by a named test:
removing the checkpoint after a scrub, removing `PRAGMA secure_delete`, skipping the
contradiction check, removing the face-and-voice requirement from the policy, removing the
in-flight check, scheduling a proposal for any identified turn, dropping the token exclusion of
the composite actor, removing the cap check, ignoring known names, echoing the model's
answer in the extractor's error, and, after the review, dropping the same-predicate grounding,
the attribution rule, the kinship check of the favourite trigger, the capitalised-name rule, the
handling of a checkpoint that raises, of one that is busy and of the owed retry, the retention
expiry, the enrolment re-check and the script's busy check. (An eleventh review mutation,
replacing the writer's checkpoint call by the checkpoint itself, is equivalent now that the
checkpoint never raises, and is not counted.)
The repository's own `just gate` (which also runs `pip-audit`) was **not** run in the copy. The
CI selection passed in full (**2888 passed**, nothing else running). An unfiltered run that
overlapped another heavy process failed
`tests/slow/test_speaker_embedding_real_model.py::test_the_real_encoder_returns_the_frozen_shape`,
which passed alone together with the import-graph test (5 passed): the same class of load flake
Plan 0050 and Plan 0061 recorded.
Not rehearsed: Task 15 (a local smoke run by Pipec) and Task 16 (documentation). Treat the diffs
as rehearsed code, not as a substitute for the RED/GREEN record each task requires.

## Global Constraints

- No real household data, voice, face or name in any tracked file, test, prompt, doc or commit
  message: tests use invented canaries (`scripts/check_reserved_terms.py` guards this).
- **A value never reaches a log, an exception message, a model-visible prompt other than the
  extractor's, or a file after it is resolved.** Logs carry ids, the canonical predicate, a status,
  a channel and a closed reason. `aiosqlite` is held at `WARNING` because at `DEBUG` it prints each
  statement with its parameters.
- **The firewall rule (ADR 0021 decision 3):** every candidate, spoken value, answer and promotion
  needs the face **and** the voice of the same person, verified on that turn's own clip, and never a
  token. Otherwise the robot behaves as for a stranger.
- The audit row is written **before** the effect, and a failing audit denies it (ADR 0019 §6.3).
- `db.transaction()` is not reentrant: nothing opens a transaction inside another; the writer is one
  transaction and compares folded keys instead of relying on an `IntegrityError`.
- One clock for the candidate store: aware UTC datetimes supplied by the caller, stored as
  `YYYY-MM-DDTHH:MM:SS.ffffff+00:00`; never `datetime('now')`.
- No wire change: no URL, status code, response field, audio format or schema of the API moves; the
  robot (`robot/src`) is untouched. A generic turn keeps reporting `identity_source = null`.
- The predicate registry's defaults do not change (they are the household reader's read contract);
  the writer passes visibility `personal` and sensitivity `normal` explicitly.
- Audio contract wherever a clip travels: WAV, 16 000 Hz, mono, signed int16; the clip stays in
  memory and is never written to disk.
- Type hints on every signature, Google docstrings on public APIs, `ruff` clean over the **explicit
  paths** of every file touched (including `scripts/`, which `ruff check .` excludes and the
  pre-commit hook does not), `mypy server/src robot/src` clean, no `Any` without a comment, no
  `# type: ignore` without an explanation, no `print()`, no `time.sleep()` in async code.
- Every new test is observed RED for the stated reason before its implementation.
- A commit title is at most 72 characters (commitizen rejects longer ones silently): check
  `git log -1` after every commit.

## Review Focus

Inputs the ADR implies that are most likely to bite, each pinned by a test in its owning task:

1. **A voice that is not the owner's, with the owner's face in frame.** Nothing is extracted,
   stored or audited as allowed; a token, a manual session, a voice that is not verified (another
   speaker, a clip below the floor, no enrolment, a failing backend) are all refused before the
   model is called (Tasks 8, 9, 11, 13).
2. **A value that outlives its life.** After a rejection, an expiry, a void or a restart the bytes
   are not in the database file or its write-ahead log, and no log line or exception message carries
   a value or a model answer — including `aiosqlite` at `DEBUG` (Tasks 4, 5, 6, 12).
3. **The same taste said again** (another article, case or accent) is one candidate, the per-person
   cap refuses and never evicts, and a canonical duplicate or a contradiction is a *result*, not an
   `IntegrityError` (Tasks 6, 10).
4. **A sentence that is an instruction or a disclosure, or that the model "improves".** The
   benchmark's own sentence about a move, `prefiero no hablar de mi divorcio`, `ya no me gusta`,
   an object the user did not say, a person, a pet, a place or a model-chosen
   topic never become a candidate (Tasks 2, 3, 11). Nor does `no me gusta el mate` become a
   *like*, nor `prefiero no hablar de ...` a preference. `no, me gusta el mate` (with the comma) **is**
   a `likes` candidate by design: the comma makes it a spoken correction of what was just said, and
   the owner must still confirm it in Plan 0063 before any fact exists.
5. **Somebody else's taste, or the model's polarity.** `mi hija dice: me gusta el helado`,
   `mi hijo favorito es ...`, `me gusta el mate pero odio el cafe` with the model answering
   "likes cafe", `odio a Rodrigo`: the gate ties every object to the words after its own trigger and
   the classifier accepts it only under that trigger's predicate (Tasks 2, 3).
6. **Anything that can hang, pile up or outlive the process.** A nested transaction, two
   confirmations at once, two extractions, a cancelled task, a revoked consent during the model
   call, a kill-switch flipped off, a restart between offer and answer, or a checkpoint that SQLite
   cannot finish because something else holds the file (Tasks 5, 6, 10, 11, 12).

---

## Why this plan exists

| Finding | Evidence in the merged code (`f92e43d`) | Closed by |
|---|---|---|
| Nothing durable is written for the owner | `consolidate_turn` returns unless the turn carries `MANUAL` evidence, which no production code emits; if it ran it would write the legacy tables around the policy and store the whole turn as an episode | Tasks 11, 13 |
| V4 has no place for a claim | `literal_facts_v4.lifecycle` accepts `active`, `superseded`, `disputed`, `revoked`, `expired` only (a `CHECK`); `confirmed_by_entity_id` and `confirmed_at` exist and no Python reads or writes them | Tasks 5, 6, 7 |
| The policy exists and nothing consumes it | `propose_personal_memory` and `confirm_personal_memory` have no caller; `PROPOSE_MEMORY` and `COMMIT_MEMORY` have none either | Tasks 9, 10, 14 |
| `strong` has no single reader | the face keeps its consent in one table and the voice in another, each revoked and purged on its own, and no reader asks for both | Task 8 |
| A write inside a write hangs, and a duplicate raises | `db.transaction()` is not reentrant; `assert_literal_fact` opens its own by default; a duplicate active literal raises `IntegrityError` (a test pins it) | Tasks 7, 10 |
| Scrubbed bytes are not gone | the connection never sets `secure_delete`, so a value survives in free pages and in the write-ahead log; `just reset-db` copies the live file | Tasks 5, 6, 12 |
| Third-party code can log a value | at `DEBUG`, `aiosqlite` prints each statement with its parameters; `_extract_via_ollama` put the model's output into an exception message | Tasks 6, 13 |
| Extraction is slow and unbounded | about 41 s per call on the shared laptop; nothing limits concurrency or rate | Task 11 |

## Task overview

| # | Task | Closes |
|---:|---|---|
| 0 | Revalidate the baseline | — |
| 1 | Settings, `.env.example`, the flag pin and the shared folding function | the seven settings, one kill-switch |
| 2 | The candidate vocabulary, the lexicon tables and the preference gate | gate grammar, closed reasons |
| 3 | The candidate classifier | the pure accept-or-drop, the comparison key |
| 4 | The candidate extractor | user words only, no retry, closed enums |
| 5 | Migration 009, `secure_delete` and the log checkpoint | the table, the scrub as a schema rule |
| 6 | The candidate store | compare-and-set, cap, expiry, physical scrub, log level |
| 7 | Literal facts carry classification and confirmation | the two fields and the explicit visibility |
| 8 | The face-and-voice actor and the enrollment reader | the composite and its readers |
| 9 | The candidate policy check | propose / read / confirm, audit first |
| 10 | The canonical memory writer | `promote`, one transaction |
| 11 | The background proposal and its limits | the orchestrator, one in flight, the budget |
| 12 | Reclaim, void and scrub | retention, start-up, `just reset-db` |
| 13 | Wire the proposal and retire `consolidate_turn` | the scheduler, the routes, the retired writer |
| 14 | Retire `propose_memory` and `commit_memory` | the two unused actions |
| 15 | Local smoke by Pipec | outcomes only; not the hardware acceptance (Plan 0063) |
| 16 | Documentation truth | the docs this plan makes stale |

## Decisions

**Proposed 2026-10-14 and confirmed as written by Pipec when he promoted the plan the same
day.** The recommendation is the text of each item. None of them contradicts the ADR; the ones that fill a gap
the ADR left to the plan say so.

1. **D-1 — Module layout.** `memory/candidate_types.py` (the closed vocabulary, pure),
   `preference_gate.py` (pure), `candidate_classifier.py` (pure), `candidate_extraction.py` (the model
   call), `candidates.py` (the only module that issues SQL on `memory_candidates`),
   `candidate_policy.py`, `memory_writer.py`, `candidate_limits.py`, `candidate_proposal.py` (the
   orchestrator that replaces `consolidate_turn`), `enrollment.py`, and `cognition/strong_actor.py`.
   The ADR names five modules and says the plan names the rest; the orchestrator, the limiter, the
   vocabulary and the two readers are the plan's names. The closed word lists live in
   `memory/lexicon.py`, as the ADR says.
2. **D-2 — The scheduler carries the words and the actor; the route binds the rest.** ADR 0021 §10
   says the callback "gains the turn's correlation id and clip". `text_turn` is channel-agnostic and
   has neither, so `ProposalScheduler = Callable[[str, ActivePersonContext], None]` and
   `routers/transcribe.py` closes over the event, the clip and the channel. The callback never
   receives the assistant's reply. The parameter is renamed `schedule_proposal`, so the tests that
   pin the old signature change on purpose.
3. **D-3 — Only the voice half runs in the background.** The face already named the person in the
   foreground (ADR 0020), so the background task runs the speaker check for that person and fuses it
   with the face evidence it already has; the face model is not run a second time (about 0.9 s on
   the shared laptop). The fusion rule is extracted from `FusedIdentityResolver._with_voice` into
   `fuse_face_and_voice` so it exists once.
4. **D-4 — "Enrolled" is both consents, read again right before the policy and its audit row.**
   The model call takes tens of seconds; a revocation in that window must stop the write, and the
   audit log must never say "allowed" for something that was not stored. `is_enrolled_for_strong` reads
   `has_active_face_consent` and `has_active_voice_consent`, the two readers that exist (revoking
   either purges its data). The composite *actor* predicate is `is_face_and_voice_actor` (identified,
   `strong`, face and voice evidence of the same person, **no** `LOCAL_UNLOCK` item: a token also
   reaches `strong`, so assurance alone says nothing).
5. **D-5 — Order of the cheap checks.** gate, face actor, "is one running?", voice, budget and slot,
   model. A speaker who is not the owner can therefore cost voice embeddings (about 0.5 s of CPU
   each, in the background) but never extraction budget or model time. Counting the budget before
   the voice check would let a bystander spend the owner's hour.
6. **D-6 — The grammar is conservative and closed.** The object must be a noun phrase of at most
   five words, letters only, or an infinitive from a short list, placed by the extractor in nine
   topics, free of person, role, place, health, money, credential and disclosure words, not a known
   name, not capitalised inside a sentence (speech-to-text capitalises names, places and brands),
   and literally in the words after a trigger of its **own predicate** (the model never chooses
   the polarity, and a taste somebody else voiced earlier is not in this trigger's words). **Cost, accepted:** a taste that follows an attribution after a soft break (`mi hija dice: me
   gusta el helado`) is not the speaker's and is dropped, and so are bare short or clitic infinitives
   (`ser`, `ir`, `callarme`) that are not on the list. `RELATION_TRIGGERS` keys
   (`perro`, `gato`, `mascota`, `hijo`, ...) are third parties by the ADR's own words, so "me gustan
   los gatos" is **not** captured in CM-3a; pets are CM-3b's. The lists are small on purpose and
   grow only by a reviewed change. **Further costs, accepted after execution (the independent
   review of 2026-10-15):** a contrast inside one taste is refused whole (`todo menos X`,
   `excepto`, `salvo`, and after `prefiero` an `al`, `en vez de` or `en lugar de`), so
   `prefiero el mate al cafe` is dropped while `me gusta el pollo al horno` passes and
   `me gusta el cafe sin azucar` passes; the deny lists cover the plural and the diminutive of
   each entry; places and names that Whisper writes in lower case rely on the closed topic set
   (the capitalisation rule cannot see them); and `No, me gusta el mate` (with the comma) is a
   `likes` candidate by design, a spoken correction that the owner must still confirm in Plan 0063
   before any fact exists.
7. **D-7 — `secure_delete=ON` for the whole connection, a `TRUNCATE` checkpoint after every
   scrub, and `aiosqlite` held at `WARNING`.** `ON`, not `FAST`; the cost is a little I/O on
   deletes of a small local database. The `aiosqlite` line is a finding of the rehearsal, not of the
   ADR: at `DEBUG` the driver printed the candidate's value with each statement. A checkpoint
   SQLite cannot finish (another process reads the file, a cursor is open on the shared
   connection) returns `False`, never raises, waits 0.5 s instead of 5 s while it holds the write
   lock, and is retried at the next store entry and at every hourly run: the operation that erased
   the value has already committed and must not fail because of it.
8. **D-8 — `just reset-db` scrubs before it copies, and refuses to copy when it cannot.**
   `scripts/scrub_candidates.py` (the file is opened with the standard library's `sqlite3`) voids
   live candidates, overwrites the bytes and truncates the log, then the script copies; if the log
   cannot be truncated because a reader holds it, the scrub exits 1 and nothing is copied. The 14 backups already in `data/backups`
   predate migration 009 and hold no candidate table; this plan does not touch them.
9. **D-9 — `promote` asks and audits the policy itself.** The writer is "the only place that
   inserts a V4 fact from a candidate", so it also runs `authorize_step(CONFIRM)` before its
   transaction: no caller can promote unaudited. The audit row comes first by design, so a call for a
   candidate that does not exist still leaves an `allowed` row: Plan 0063's answer branch calls
   `promote` only after an answer matched an offer, never speculatively (the ADR's no-oracle rule). Plan 0063's answer branch calls it once.
10. **D-10 — The kill-switch is checked in the scheduler gate, the proposal, the policy, the
    store and the writer; retention and start-up run whatever it says (start-up reads the settings
    object of the app, which is the global `settings` in production).** Defence in depth, and the
    reason a stale value cannot outlive a switch turned off.
11. **D-11 — What leaves, and what stays of the old path.** Leaves: `consolidate_turn`, its retry
    helper `_extract`, the `MANUAL`-only scheduling, `PROPOSE_MEMORY` and `COMMIT_MEMORY` (enum
    members, policy branches and the two policy ids; the characterization pins go from eleven
    actions to nine). Stays: `_extract_via_ollama`, its prompt and
    `scripts/eval_consolidation.extract_case_items` (the CM-0 benchmark and `just eval-memory`),
    unchanged except that its error no longer carries the model's output; `normalize_extraction`,
    `store_memory`, `assert_fact` and `upsert_entity` (benchmark, legacy retrieval and their own
    tests; `vulture --min-confidence 80` reports nothing).
12. **D-12 — Tests that pinned `consolidate_turn`.** Three in `test_memory_integration.py`, one in
    `test_memory_relational.py`, one in `test_onboarding_checklist.py` and the correction and
    onboarding scenarios of `test_vision_memoria.py` are deleted: they pinned a function that no
    longer exists, and what each protected has a test of its own (the supersede rule in
    `test_memory_integration.py`, the normaliser's unit tests, the retrieval scenarios, which stay
    and are now seeded straight through the repositories).
13. **D-13 — `memory_candidates.predicate` has no `CHECK`.** CM-3b adds predicates and SQLite cannot
    alter a `CHECK` without rebuilding the table; the classifier enforces the closed set, and the
    status and channel columns are the closed sets the schema owns.
14. **D-14 — Known names.** `entity_labels.list_known_names()` returns every name and alias of
    `person` and `other` (pet) entities; the classifier folds them and drops an object that is one.

## Required reading

- `AGENTS.md`, `docs/architecture/implementation-guardrails.md` and `.claude/rules/`.
- [ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md) (all of it),
  [ADR 0019](../../adr/0019-personal-memory-capabilities.md),
  [ADR 0020](../../adr/0020-authorized-actor-in-the-conversation.md),
  [ADR 0016](../../adr/0016-face-and-voice-identity-fusion.md) §1 to §9,
  [ADR 0011](../../adr/0011-sqlite-transaction-ownership.md) and
  [ADR 0009](../../adr/0009-locked-posture-and-scoped-capabilities.md).
- [`conversational-memory-delivery-map.md`](../../roadmap/conversational-memory-delivery-map.md),
  [`memory-and-world-state.md`](../../architecture/memory-and-world-state.md) and
  [`identity-and-access.md`](../../architecture/identity-and-access.md).
- `server/src/server/memory/{consolidation,relational_v4,predicate_registry,lexicon,retention,
  entity_labels,biometric_consent,voice_consent}.py`, `server/src/server/{text_turn,streaming,db,
  settings,main,logging_setup}.py`,
  `server/src/server/cognition/{authorization,identity,identity_fusion,generic_identity,
  speaker_authentication,face_authentication,intent_resolution}.py`,
  `server/src/server/routers/{transcribe,chat,vision}.py`, `scripts/reset_db.ps1`,
  `scripts/eval_consolidation.py`, `tests/unit/test_architecture_guards.py`, `tests/conftest.py` and
  the tests named in each task.

## Permitted files

- Production, new: `server/src/server/memory/{candidate_types,preference_gate,candidate_classifier,
  candidate_extraction,candidates,candidate_policy,memory_writer,candidate_limits,
  candidate_proposal,enrollment}.py`, `server/src/server/memory/migration_009_memory_candidates.sql`,
  `server/src/server/cognition/strong_actor.py`.
- Production, modified: `settings.py`, `db.py`, `main.py`, `logging_setup.py`, `text_turn.py`,
  `streaming.py`, `routers/transcribe.py`, `memory/{lexicon,relational_v4,retention,
  entity_labels,consolidation}.py`, `cognition/{intent_resolution,identity_fusion,authorization,
  models}.py` and `.env.example`.
- Scripts: new `scripts/scrub_candidates.py`; modified `scripts/reset_db.ps1`.
- Tests: the files listed in each task (new files and the modified existing ones).
- Docs (Tasks 15 and 16): the list of Task 16, a new `docs/evals/0062-memory-candidates-local-smoke.md`
  with its entry in `docs/evals/README.md`, and this plan.

No new URL, status code, response field, audio contract or dependency. The robot (`robot/src`), the
controller, `/chat`, `/vision/respond`, the V4 reader, the household tools and the registry's
defaults are **not** edited. `docs/roadmap/tabla-tareas.md` is excluded from git and updated locally
only.

---

## Task 0: Revalidate the baseline

**Files:** this plan's evidence note only. No production change.

- [ ] **Step 0: Status.** Confirm this plan says `Ready` (Pipec's promotion). If it says anything else, stop.
- [ ] **Step 1: Branch.** `git checkout main && git pull`, confirm a clean tree, then
  `git checkout -b feat/0062-cm3a-candidates-and-writer`. Record the base SHA (the rehearsal ran at
  `f92e43d`; if `main` moved, say so and re-check that the diffs below still apply). The diffs are
  applied by hand with the Write and Edit tools (new files whole, existing files hunk by hunk);
  blank context lines in the blocks lost their single leading space in this document (the
  trailing-whitespace hook), so `git apply` needs `--recount --ignore-whitespace` if you prefer it.
- [ ] **Step 2: Baseline.** Run `just gate`; record its outcome and test count (2597 at
  `f92e43d`). A pre-existing failure is reported, not hidden.
- [ ] **Step 2b: Re-audit the assumptions against the merged code** (queue rule 4). Each command must
  find what this plan names:
  `rg -n "consolidate_turn|schedule_consolidation|ConsolidationScheduler" server scripts` (only
  `memory/consolidation.py`, `text_turn.py`, `streaming.py` and `routers/transcribe.py`),
  `rg -n "PROPOSE_MEMORY|COMMIT_MEMORY" server` (only `cognition/models.py` and
  `cognition/authorization.py`), `rg -n "assert_literal_fact" server` (only `relational_v4.py` and
  `legacy_v4_migration.py`), `rg -n "has_active_face_consent|has_active_voice_consent" server` (the
  two repositories and the two resolvers that read them), `rg -n "_with_voice" server` (one
  method in `identity_fusion.py`), `rg -n "PRAGMA user_version|_MIGRATIONS" server/src/server/db.py`
  (the list ends at version 8) and
  `rg -n "def _normalize" server/src/server/cognition/intent_resolution.py` (private, one definition).
  A difference is reported before any code changes.
- [ ] **Step 3: Pin today's guards.** Run
  `uv run pytest tests/unit/test_architecture_guards.py tests/integration/test_owner_stranger_matrix.py tests/unit/test_text_turn.py tests/unit/test_authorization_characterization.py -q -p no:cacheprovider`
  and record that it passes.

---

## Task 1: Settings, `.env.example`, the flag pin and the shared folding function

**Files:**
- Modify: `.env.example`, `server/src/server/cognition/intent_resolution.py`, `server/src/server/settings.py`
- Test: new `tests/unit/test_memory_candidate_settings.py`; modified `tests/conftest.py`

**Interfaces:**
- Produces: `settings.memory_candidates_enabled: bool = False` and the six limits
  (`memory_candidate_ttl_seconds` 86 400, `_max_live` 5, `_value_max_chars` 80, `_max_offers` 2,
  `_answer_seconds` 60, `_extractions_per_hour` 12; all `PositiveInt`); a public
  `normalize_spanish(message: str) -> str` (the former private `_normalize`: accent and case folding
  plus punctuation collapse, defined once; the ADR forbids a seventh copy); an autouse fixture that
  pins the flag off for every test.

- [ ] **Step 1: Write the failing tests** — one new file (defaults read from the field definitions
  so a shell or `.env` cannot change the answer, zero is refused, the suite pins the flag, every
  setting is documented, the folding example):

```diff
diff --git a/tests/conftest.py b/tests/conftest.py
--- a/tests/conftest.py
+++ b/tests/conftest.py
@@ -31,6 +31,16 @@ def _continuity_session_empty() -> Generator[None, None, None]:
     continuity.reset()


+@pytest.fixture(autouse=True)
+def _memory_candidates_off(monkeypatch: pytest.MonkeyPatch) -> None:
+    """Start every test with the candidate kill-switch off (ADR 0021).
+
+    A developer's `.env` may switch candidates on; without this pin a test that never asked for
+    them would schedule proposals. A test that wants them sets the flag itself.
+    """
+    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
+
+
 @pytest.fixture(autouse=True)
 def _conversation_text_logs_off() -> None:
     """Start every test with both opt-in conversation loggers disabled (Plan 0052).
diff --git a/tests/unit/test_memory_candidate_settings.py b/tests/unit/test_memory_candidate_settings.py
new file mode 100644
--- /dev/null
+++ b/tests/unit/test_memory_candidate_settings.py
@@ -0,0 +1,48 @@
+"""Settings of the memory-candidate subsystem (ADR 0021 decision 10)."""
+
+from pathlib import Path
+
+from pydantic import ValidationError
+import pytest
+from server.cognition.intent_resolution import normalize_spanish
+from server.settings import Settings, settings
+
+pytestmark = pytest.mark.unit
+
+_DEFAULTS = {
+    "memory_candidates_enabled": False,
+    "memory_candidate_ttl_seconds": 86_400,
+    "memory_candidate_max_live": 5,
+    "memory_candidate_value_max_chars": 80,
+    "memory_candidate_max_offers": 2,
+    "memory_candidate_answer_seconds": 60,
+    "memory_candidate_extractions_per_hour": 12,
+}
+_LIMITS = [name for name in _DEFAULTS if name != "memory_candidates_enabled"]
+
+
+def test_the_candidate_defaults_are_the_ones_of_the_adr() -> None:
+    """Field defaults, so neither the shell nor a local `.env` can change the answer."""
+    assert {name: Settings.model_fields[name].default for name in _DEFAULTS} == _DEFAULTS
+
+
+@pytest.mark.parametrize("name", _LIMITS)
+def test_a_limit_of_zero_is_refused(name: str) -> None:
+    with pytest.raises(ValidationError):
+        Settings.model_validate({name: 0})
+
+
+def test_the_test_suite_pins_the_kill_switch_off() -> None:
+    """The autouse fixture of `tests/conftest.py` keeps a developer's `.env` out of the tests."""
+    assert settings.memory_candidates_enabled is False
+
+
+def test_env_example_documents_every_candidate_setting() -> None:
+    text = (Path(__file__).resolve().parents[2] / ".env.example").read_text(encoding="utf-8")
+
+    for name in _DEFAULTS:
+        assert f"{name.upper()}=" in text
+
+
+def test_normalize_spanish_folds_accents_case_and_punctuation() -> None:
+    assert normalize_spanish("¡Me GUSTÓ el café,  ñandú!") == "me gusto el cafe nandu"
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_memory_candidate_settings.py -q -p no:cacheprovider`
  Expected RED: `ImportError: cannot import name 'normalize_spanish'`.
- [ ] **Step 3: Implement.** The seven fields, their comment in `.env.example`, the public name of
  the folding function (two internal call sites) and the autouse fixture:

```diff
diff --git a/.env.example b/.env.example
--- a/.env.example
+++ b/.env.example
@@ -144,6 +144,23 @@ CHARACTER_HOT_RELOAD=false

 # Kill-switch (set false to debug without memory)
 MEMORY_ENABLED=true
+
+# Memory candidates (ADR 0021, CM-3a). Off by default: with it off nothing is proposed,
+# offered, answered or promoted, and every live candidate is voided at start-up. With it on
+# a candidate needs the owner's enrolled face AND voice on that turn's own clip
+# (FACE_AUTHENTICATION_ENABLED and SPEAKER_AUTHENTICATION_ENABLED must be on).
+MEMORY_CANDIDATES_ENABLED=false
+# A candidate that is not resolved lapses after this many seconds (and its value is scrubbed).
+MEMORY_CANDIDATE_TTL_SECONDS=86400
+# Live (proposed or offered) candidates per person; at the cap a new one is refused.
+MEMORY_CANDIDATE_MAX_LIVE=5
+# Longest accepted value, in characters.
+MEMORY_CANDIDATE_VALUE_MAX_CHARS=80
+# Times one candidate may be offered before it lapses, and seconds an offer waits for an answer.
+MEMORY_CANDIDATE_MAX_OFFERS=2
+MEMORY_CANDIDATE_ANSWER_SECONDS=60
+# Extractions that may start in a rolling hour (one at a time; about 41 s each on a laptop).
+MEMORY_CANDIDATE_EXTRACTIONS_PER_HOUR=12
 # Character profile loaded from the profiles/*.md files
 ROBOT_CHARACTER=iroko

diff --git a/server/src/server/cognition/intent_resolution.py b/server/src/server/cognition/intent_resolution.py
--- a/server/src/server/cognition/intent_resolution.py
+++ b/server/src/server/cognition/intent_resolution.py
@@ -164,7 +164,7 @@ def resolve_information_need(message: str) -> IntentResolution:
         The closed, deterministic resolution — need, match kind, and a
         privacy-safe rule identifier (``None`` only for generic conversation).
     """
-    normalized = _normalize(message)
+    normalized = normalize_spanish(message)
     for rule in _RULES:
         resolution = rule(normalized)
         if resolution is not None:
@@ -238,7 +238,7 @@ def _contains_word_phrase(normalized: str, pattern: str) -> bool:
     Plain substring checks would let "que ves" false-hit inside "aunque
     vestirse" (the "que ves" letters span the word boundary). Padding both
     sides with a single space reproduces the old regex ``\\b...\\b``
-    guarantee cheaply, since `_normalize` already collapses every non-word
+    guarantee cheaply, since `normalize_spanish` already collapses every non-word
     run to exactly one space.
     """
     return f" {pattern} " in f" {normalized} "
@@ -335,12 +335,20 @@ _RULES: tuple[Callable[[str], IntentResolution | None], ...] = (
 )


-def _normalize(message: str) -> str:
+def normalize_spanish(message: str) -> str:
     """Fold accents/case and collapse punctuation for closed Spanish matching.

     NFD-decomposes, strips combining accents, casefolds, replaces each
     non-word run with one space, then trims — so surrounding punctuation and
-    inconsistent whitespace never affect classification.
+    inconsistent whitespace never affect classification. Public because the
+    memory layer's closed grammars (ADR 0021) fold text the same way; it is the one
+    folding function they share rather than another copy.
+
+    Args:
+        message: Raw transcript or chat text.
+
+    Returns:
+        The folded text: lower case, no accents, words separated by single spaces.
     """
     decomposed = unicodedata.normalize("NFD", message)
     stripped = "".join(
diff --git a/server/src/server/settings.py b/server/src/server/settings.py
--- a/server/src/server/settings.py
+++ b/server/src/server/settings.py
@@ -116,6 +116,18 @@ class Settings(BaseSettings):
     semantic_top_k: int = 6

     memory_enabled: bool = True
+    # Memory candidates (ADR 0021, CM-3a): what the identified owner says about their own
+    # tastes is kept as a short-lived candidate and promoted only by the one writer. Off by
+    # default and a kill-switch for every path (proposal, offer, answer, promotion).
+    memory_candidates_enabled: bool = False
+    memory_candidate_ttl_seconds: PositiveInt = 86_400
+    memory_candidate_max_live: PositiveInt = 5
+    memory_candidate_value_max_chars: PositiveInt = 80
+    memory_candidate_max_offers: PositiveInt = 2
+    memory_candidate_answer_seconds: PositiveInt = 60
+    # Extraction is one local-model call (about 41 s on the shared laptop): at most one is in
+    # flight and at most this many start in any rolling hour.
+    memory_candidate_extractions_per_hour: PositiveInt = 12
     robot_character: str = "iroko"
     # Re-read character markdown profiles from disk on every request when
     # they change (prompt-engineering aid). OFF by default: production loads
```

- [ ] **Step 4: Run to see them pass, then lint and types.**
  `uv run pytest tests/unit/test_memory_candidate_settings.py tests/unit/test_intent_resolution.py -q -p no:cacheprovider`;
  `uv run ruff check <paths>` and `uv run ruff format --check <paths>` over the files above;
  `uv run mypy --config-file=pyproject.toml server/src robot/src`.
- [ ] **Step 5: Commit** `feat(server): add the memory-candidate settings (plan 0062)`; check `git log -1`.

---

## Task 2: The candidate vocabulary, the lexicon tables and the preference gate

**Files:**
- Create: `server/src/server/memory/candidate_types.py`, `server/src/server/memory/preference_gate.py`
- Modify: `server/src/server/memory/lexicon.py`
- Test: new `tests/unit/test_preference_gate.py`

**Interfaces:**
- Produces: `candidate_types.{CandidateReason, CandidateStatus, CandidateChannel, GateMatch, RawCandidate,
  ProposedCandidate}` (the ADR's closed reasons are `gate_no_match`, `not_a_taste`,
  `negation_unsupported`, `sensitive_topic`, `gate_mismatch`, `strong_unreachable`, `not_grounded`,
  `busy`, `budget`, `capacity`, `contradiction`, `duplicate`, `expired`, `denied`);
  `lexicon.{PREFERENCE_TRIGGERS, PREFERENCE_FAVOURITE, CANDIDATE_TOPICS, LEAD_IN_WORDS, NEGATORS,
  CLAUSE_OPENERS, GREETING_WORDS, ARTICLES, ALLOWED_INFINITIVES, PERSON_WORDS,
  SENSITIVE_WORDS, candidate_denied_words()}`; `preference_gate.match_preference(text) ->
  GateResult(matches, reason)` with `.predicates`; a `GateMatch(predicate, words)` is one taste tied
  to the folded words that follow its own trigger.

The gate is matched **clause by clause** (punctuation ends a clause; `pero`, `y`, `e`, `ni`,
`aunque`, `sino` end a taste inside one), so `no, me gusta el mate` is a like and not a dislike
(folding the comma away would read it as `no me gusta`), and a refused clause does not veto a clean
one. Words that are not a greeting or a lead-in before a soft break (`, ; :`) make the next taste
somebody else's (`mi hija dice: me gusta el helado`); a hard stop (`. ! ?`) forgets the
attribution. The words inside the favourite trigger (`mi hijo favorito es`) are checked like any
lead, and an object that opens with `a`/`al` (`odio a Rodrigo`) or carries a relative clause
(`sin que me mires`) is a person or an event, never a thing.

- [ ] **Step 1: Write the failing tests** — 17 sentences that pass with their predicates, 24 that
  are refused with their closed reason (including both of the benchmark's sentences), and the
  clause rules:

```diff
diff --git a/tests/unit/test_preference_gate.py b/tests/unit/test_preference_gate.py
new file mode 100644
--- /dev/null
+++ b/tests/unit/test_preference_gate.py
@@ -0,0 +1,172 @@
+"""Unit tests for the preference gate (ADR 0021 decision 4): a closed, refusing grammar."""
+
+import pytest
+from server.memory.candidate_types import CandidateReason
+from server.memory.preference_gate import match_preference
+
+pytestmark = pytest.mark.unit
+
+_LIKES = frozenset({"likes"})
+_DISLIKES = frozenset({"dislikes"})
+_PREFERS = frozenset({"prefers"})
+
+
+@pytest.mark.parametrize(
+    "text, predicates",
+    [
+        ("Me gusta el mate.", _LIKES),
+        ("me encantan las empanadas", _LIKES),
+        ("Amo el jazz", _LIKES),
+        ("adoro el chocolate amargo", _LIKES),
+        ("No me gusta el cilantro", _DISLIKES),
+        ("no soporto el ruido de la licuadora", _DISLIKES),
+        ("odio el brócoli", _DISLIKES),
+        ("detesto la lluvia fría", _DISLIKES),
+        ("Prefiero el té sin azúcar", _PREFERS),
+        ("mi color favorito es el verde", _PREFERS),
+        ("Mi comida favorita es la pizza", _PREFERS),
+        ("la verdad me gusta el rock", _LIKES),
+        ("a mí me gusta el mate", _LIKES),
+        ("No, me gusta el mate", _LIKES),
+        ("me gusta el mate, pero odio el café", frozenset({"likes", "dislikes"})),
+        ("me gusta el mate y odio el café", frozenset({"likes", "dislikes"})),
+        ("me gusta cantar en la ducha", _LIKES),
+    ],
+)
+def test_a_first_person_taste_passes_with_its_predicates(
+    text: str, predicates: frozenset[str]
+) -> None:
+    result = match_preference(text)
+
+    assert result.predicates == predicates
+    assert result.reason is None
+
+
+@pytest.mark.parametrize(
+    "text, reason",
+    [
+        # not a statement
+        ("hola robot", CandidateReason.GATE_NO_MATCH),
+        ("", CandidateReason.GATE_NO_MATCH),
+        ("¿Te gusta el mate?", CandidateReason.NOT_A_TASTE),
+        ("me gusta el mate?", CandidateReason.NOT_A_TASTE),
+        ("me gustaría viajar a Japón", CandidateReason.GATE_NO_MATCH),
+        ("me gustó la película", CandidateReason.GATE_NO_MATCH),
+        # not the speaker's own taste
+        ("a mi vecino le gusta el mate", CandidateReason.GATE_NO_MATCH),
+        ("mi hermano dice que me gusta el mate", CandidateReason.NOT_A_TASTE),
+        ("creo que me gusta el mate", CandidateReason.NOT_A_TASTE),
+        # a clause is an instruction to the robot, not a thing
+        (
+            "Prefiero que no menciones mi mudanza reciente delante de visitas",
+            CandidateReason.NOT_A_TASTE,
+        ),
+        ("me gusta que me hables despacio", CandidateReason.NOT_A_TASTE),
+        ("odio cuando llueve", CandidateReason.NOT_A_TASTE),
+        ("me gusta", CandidateReason.NOT_A_TASTE),
+        # negated forms other than the two triggers
+        ("prefiero no hablar de mi divorcio", CandidateReason.NEGATION_UNSUPPORTED),
+        ("ya no me gusta el mate", CandidateReason.NEGATION_UNSUPPORTED),
+        ("nunca me gusta madrugar", CandidateReason.NEGATION_UNSUPPORTED),
+        ("tampoco me gusta el café", CandidateReason.NEGATION_UNSUPPORTED),
+        ("odio no poder dormir", CandidateReason.NEGATION_UNSUPPORTED),
+        # sensitive vocabulary
+        ("odio mi medicación", CandidateReason.SENSITIVE_TOPIC),
+        ("amo a mi hijo", CandidateReason.NOT_A_TASTE),
+        ("me gusta mi casa", CandidateReason.SENSITIVE_TOPIC),
+        ("me gusta vivir en la costa", CandidateReason.SENSITIVE_TOPIC),
+        ("prefiero que no digas mi clave", CandidateReason.NOT_A_TASTE),
+        ("me gusta mi perro", CandidateReason.SENSITIVE_TOPIC),
+    ],
+)
+def test_everything_else_is_refused_with_a_closed_reason(
+    text: str, reason: CandidateReason
+) -> None:
+    result = match_preference(text)
+
+    assert result.predicates == frozenset()
+    assert result.reason is reason
+
+
+def test_the_sentences_of_the_longitudinal_benchmark_are_refused() -> None:
+    """The two sentences the benchmark's disclosure scenario uses never become candidates."""
+    for text in (
+        "Prefiero que no menciones mi mudanza reciente delante de visitas.",
+        "prefiero no hablar de mi divorcio",
+    ):
+        assert match_preference(text).predicates == frozenset()
+
+
+def test_a_refused_clause_does_not_veto_a_clean_one() -> None:
+    result = match_preference("me gusta el mate, prefiero que no hables de mi casa")
+
+    assert result.predicates == _LIKES
+
+
+def test_a_leading_negation_is_a_separate_clause_not_a_dislike() -> None:
+    """ "No, me gusta el mate" restates a like; folding the comma away would read it as a dislike."""
+    assert match_preference("No, me gusta el mate").predicates == _LIKES
+
+
+def test_the_gate_is_pure_text_in_and_data_out() -> None:
+    first = match_preference("me gusta el mate")
+    second = match_preference("me gusta el mate")
+
+    assert first == second
+
+
+@pytest.mark.parametrize(
+    "text",
+    [
+        "mi hija dice: me gusta el helado",
+        "El doctor dijo: no me gusta el azúcar",
+        "mi hermano comentó, me gusta el mate",
+        "dice mi vecino; odio el café",
+    ],
+)
+def test_a_taste_after_an_attribution_and_a_soft_break_is_not_the_speakers(text: str) -> None:
+    result = match_preference(text)
+
+    assert result.predicates == frozenset()
+    assert result.reason is CandidateReason.NOT_A_TASTE
+
+
+def test_a_hard_stop_forgets_the_attribution() -> None:
+    result = match_preference("Mi hermano odia el café. Me gusta el mate")
+
+    assert result.predicates == frozenset({"likes"})
+
+
+@pytest.mark.parametrize(
+    "text", ["hola Iroko, me gusta el mate", "oye, me gusta el mate", "no, me gusta el mate"]
+)
+def test_a_greeting_or_a_bare_no_before_a_taste_is_not_an_attribution(text: str) -> None:
+    assert match_preference(text).predicates == frozenset({"likes"})
+
+
+@pytest.mark.parametrize(
+    "text",
+    ["mi hijo favorito es Pedro", "mi jefe favorito es Pedro", "mi perro favorito es el negro"],
+)
+def test_a_kinship_word_inside_the_favourite_trigger_is_refused(text: str) -> None:
+    result = match_preference(text)
+
+    assert result.predicates == frozenset()
+    assert result.reason is CandidateReason.SENSITIVE_TOPIC
+
+
+@pytest.mark.parametrize(
+    "text",
+    ["odio a Rodrigo", "amo a mi esposa", "me gusta sin que me mires", "adoro el té que me hace"],
+)
+def test_a_person_or_a_relative_clause_is_not_a_thing(text: str) -> None:
+    assert match_preference(text).predicates == frozenset()
+
+
+def test_each_taste_carries_the_words_after_its_own_trigger() -> None:
+    result = match_preference("me gusta el mate verde, pero odio el cilantro")
+
+    assert [(m.predicate, m.words) for m in result.matches] == [
+        ("likes", ("el", "mate", "verde")),
+        ("dislikes", ("el", "cilantro")),
+    ]
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_preference_gate.py -q -p no:cacheprovider`
  Expected RED: `ModuleNotFoundError: No module named 'server.memory.candidate_types'`.
- [ ] **Step 3: Implement** the vocabulary, the tables and the gate:

```diff
diff --git a/server/src/server/memory/candidate_types.py b/server/src/server/memory/candidate_types.py
new file mode 100644
--- /dev/null
+++ b/server/src/server/memory/candidate_types.py
@@ -0,0 +1,104 @@
+"""Closed vocabulary of memory candidates (ADR 0021): reasons, statuses, channels, shapes.
+
+Pure data, no I/O. The preference gate and the classifier are pure functions over text and
+return these types; the store and the writer persist them. Keeping the vocabulary in one
+module lets the pure units stay free of any storage import.
+"""
+
+from __future__ import annotations
+
+from dataclasses import dataclass
+from enum import StrEnum
+
+__all__ = [
+    "CandidateChannel",
+    "CandidateReason",
+    "CandidateStatus",
+    "GateMatch",
+    "ProposedCandidate",
+    "RawCandidate",
+]
+
+
+class CandidateReason(StrEnum):
+    """Closed memory-layer reason: the only explanation any log line or counter may carry.
+
+    These are separate from ADR 0016 §8's identity reasons. None of them carries a value, a
+    person's name or an exception message.
+    """
+
+    GATE_NO_MATCH = "gate_no_match"
+    NOT_A_TASTE = "not_a_taste"
+    NEGATION_UNSUPPORTED = "negation_unsupported"
+    SENSITIVE_TOPIC = "sensitive_topic"
+    GATE_MISMATCH = "gate_mismatch"
+    STRONG_UNREACHABLE = "strong_unreachable"
+    NOT_GROUNDED = "not_grounded"
+    BUSY = "busy"
+    BUDGET = "budget"
+    CAPACITY = "capacity"
+    CONTRADICTION = "contradiction"
+    DUPLICATE = "duplicate"
+    EXPIRED = "expired"
+    DENIED = "denied"
+
+
+class CandidateStatus(StrEnum):
+    """Lifecycle of one stored candidate; the value exists only in the first two."""
+
+    PROPOSED = "proposed"
+    OFFERED = "offered"
+    CONFIRMED = "confirmed"
+    REJECTED = "rejected"
+    EXPIRED = "expired"
+
+
+class CandidateChannel(StrEnum):
+    """The voice route a candidate came from; `/chat` and `/vision/respond` have none."""
+
+    VOICE_CLASSIC = "voice_classic"
+    VOICE_STREAM = "voice_stream"
+
+
+@dataclass(frozen=True)
+class GateMatch:
+    """One taste the preference gate accepted, tied to its own trigger.
+
+    Attributes:
+        predicate: Canonical registry id the trigger declares (`likes`, `dislikes`, `prefers`).
+        words: The folded words that follow the trigger inside its own part of the sentence.
+            An object is grounded only here, so the model cannot move a thing to another polarity.
+    """
+
+    predicate: str
+    words: tuple[str, ...]
+
+
+@dataclass(frozen=True)
+class RawCandidate:
+    """One triple as the extractor returned it: untrusted, to be classified.
+
+    Attributes:
+        predicate: Whatever predicate word the model chose.
+        object: The thing liked, as the model copied it.
+        topic: The topic the model placed it in.
+    """
+
+    predicate: str
+    object: str
+    topic: str
+
+
+@dataclass(frozen=True)
+class ProposedCandidate:
+    """A candidate that passed the classifier, ready for the policy and the store.
+
+    Attributes:
+        predicate: Canonical registry id (`likes`, `dislikes` or `prefers`).
+        value_text: The spoken phrase, article included.
+        value_key: Comparison key: folded, without a leading article.
+    """
+
+    predicate: str
+    value_text: str
+    value_key: str
diff --git a/server/src/server/memory/lexicon.py b/server/src/server/memory/lexicon.py
--- a/server/src/server/memory/lexicon.py
+++ b/server/src/server/memory/lexicon.py
@@ -8,6 +8,7 @@ that answers them via reverse fact lookup (see memory/relations.py).
 from __future__ import annotations

 import re
+import unicodedata

 # Common Spanish conversation words (4+ chars) that are never entity names.
 # Without this filter every greeting fires LIKE queries against `entities`.
@@ -137,3 +138,132 @@ def predicates_in(text: str) -> set[str]:
     """
     words = set(_WORD_RE.findall(text.casefold()))
     return {pred for word, pred in RELATION_TRIGGERS.items() if word in words}
+
+
+# --- Memory candidates (ADR 0021, CM-3a) -----------------------------------------------
+# Every word below is already folded the way `normalize_spanish` folds text: lower case, no
+# accents, punctuation gone. The grammar is a closed, positive list — on doubt a phrase is
+# dropped, so each table can only grow by a reviewed change.
+
+#: The first-person phrases that may declare a taste, mapped to the canonical predicate.
+#: `mi favorit[oa] es` may carry up to two words between `mi` and `favorito` ("mi color
+#: favorito es", "mi comida favorita es"); that case is handled by `PREFERENCE_FAVOURITE`.
+PREFERENCE_TRIGGERS: dict[str, str] = {
+    "no me gusta": "dislikes",
+    "no me gustan": "dislikes",
+    "no soporto": "dislikes",
+    "me gusta": "likes",
+    "me gustan": "likes",
+    "me encanta": "likes",
+    "me encantan": "likes",
+    "amo": "likes",
+    "adoro": "likes",
+    "odio": "dislikes",
+    "detesto": "dislikes",
+    "prefiero": "prefers",
+}
+PREFERENCE_FAVOURITE = re.compile(r"mi (?:[a-z]+ ){0,2}favorit[oa] es")
+
+#: Closed set of topics a taste may belong to; the extractor must place the object in one.
+CANDIDATE_TOPICS = frozenset(
+    {"food", "drink", "music", "colour", "pastime", "sport", "animal", "weather", "media"}
+)
+
+#: Words that may precede the trigger in the same clause ("la verdad, a mí me gusta ...").
+LEAD_IN_WORDS = frozenset(
+    {
+        "a", "mi", "yo", "la", "verdad", "siempre", "muy", "mucho", "muchisimo", "tambien",
+        "y", "pero", "ademas", "en", "realidad", "honestamente", "sinceramente", "bueno",
+        "che", "mira", "pues", "este", "eh", "igual", "entonces", "ahora", "claro",
+        "personalmente",
+    }
+)  # fmt: skip
+
+#: Words that may open a sentence before a taste without attributing it to somebody else
+#: ("hola Iroko, me gusta el mate"). A clause of other words before a soft break makes the next
+#: taste somebody else's ("mi hija dice: me gusta el helado").
+GREETING_WORDS = frozenset(
+    {"hola", "iroko", "oye", "dime", "escucha", "sabes", "que", "mira", "vamos", "ver"}
+)
+
+#: A word that negates what follows or precedes: the only negated forms accepted are the
+#: triggers `no me gusta(n)` and `no soporto` themselves.
+NEGATORS = frozenset({"no", "ya", "nunca", "jamas", "tampoco", "ni"})
+
+#: A word that opens a clause instead of naming a thing ("me gusta que ...", "prefiero que ...").
+CLAUSE_OPENERS = frozenset({"que", "cuando", "si", "como", "donde", "porque", "aunque", "para"})
+
+#: Articles a spoken object may begin with; the comparison key drops them.
+ARTICLES = frozenset({"el", "la", "los", "las", "un", "una", "unos", "unas", "lo"})
+
+#: A bare infinitive object ("me gusta cantar") is accepted only from this list; "vivir",
+#: "hablar" or "mudarme" describe a life, not a taste.
+ALLOWED_INFINITIVES = frozenset(
+    {
+        "cantar", "bailar", "correr", "caminar", "leer", "escribir", "cocinar", "nadar", "viajar",
+        "dibujar", "pintar", "jugar", "pescar", "escuchar", "pasear", "manejar", "hornear",
+        "tejer", "coser", "meditar", "esquiar", "surfear", "acampar", "madrugar", "dormir",
+        "comer", "beber", "mirar",
+    }
+)  # fmt: skip
+
+#: Kinship, role and person words: an object that names one is never a taste (CM-3b owns
+#: third parties). The keys of `RELATION_TRIGGERS` (hijo, mascota, perro, gato, esposa, ...)
+#: join this set by `candidate_denied_words`, so a pet is a third party here too.
+PERSON_WORDS = frozenset(
+    {
+        "mama", "papa", "madre", "padre", "hermano", "hermana", "abuelo", "abuela", "tio",
+        "tia", "primo", "prima", "suegro", "suegra", "cunado", "cunada", "nieto", "nieta",
+        "sobrino", "sobrina", "novio", "novia", "marido", "mujer", "bebe", "nino", "nina",
+        "familia", "jefe", "jefa", "amigo", "amiga", "vecino", "vecina", "companero",
+        "companera", "colega", "profesor", "profesora", "maestro", "maestra", "doctor",
+        "doctora", "medico", "medica", "persona", "gente",
+    }
+)  # fmt: skip
+
+#: Place, health, money, credential, life-event and disclosure vocabulary: a clause that
+#: contains one is never a taste. A second layer under the closed topic set.
+SENSITIVE_WORDS = frozenset(
+    {
+        # place and address
+        "casa", "hogar", "ciudad", "pueblo", "barrio", "pais", "trabajo", "oficina", "escuela",
+        "colegio", "calle", "departamento", "direccion", "domicilio", "mudanza", "mudarme",
+        "mude", "vivir", "vivo",
+        # health and body
+        "salud", "enfermedad", "enfermo", "enferma", "medicina", "medicacion", "medicamento",
+        "medicamentos", "pastilla", "pastillas", "hospital", "diagnostico", "dolor", "cancer",
+        "depresion", "ansiedad", "terapia", "alergia", "alergico", "embarazo", "cuerpo", "peso",
+        # money
+        "dinero", "plata", "sueldo", "salario", "deuda", "deudas", "banco", "tarjeta", "cuenta",
+        "prestamo", "credito", "ahorros", "impuestos", "factura",
+        # credentials and contact
+        "clave", "contrasena", "password", "pin", "codigo", "token", "usuario", "correo",
+        "email", "telefono", "celular", "dni", "pasaporte",
+        # life events
+        "divorcio", "separacion", "funeral", "muerte", "murio", "fallecio", "boda", "despido",
+        # disclosure vocabulary: an instruction to the robot is CM-3b's, never a taste
+        "menciones", "mencion", "mencionar", "digas", "hables", "cuentes", "secreto",
+        "secretos", "privado", "privada", "confidencial", "delante", "visitas", "invitados",
+        "robot", "iroko",
+        # religion, politics, sexuality, drugs and violence: never a taste of an ordinary thing
+        "dios", "iglesia", "misa", "religion", "catolico", "catolicos", "catolicismo",
+        "evangelico", "musulman", "judio", "politica", "politico", "partido", "gobierno",
+        "voto", "votar", "gay", "lesbiana", "homosexual", "sexo", "sexual", "droga", "drogas",
+        "cocaina", "marihuana", "heroina", "suicidio", "suicidarme", "matar", "inmigrantes",
+        "extranjeros", "raza", "racista",
+    }
+)  # fmt: skip
+
+
+def candidate_denied_words() -> frozenset[str]:
+    """Return every folded word a candidate's object may never contain.
+
+    Returns:
+        Person and role words, place/health/money/credential/disclosure words and the folded
+        keys of ``RELATION_TRIGGERS`` (hijo, mascota, perro, gato, esposa, edad, ...).
+    """
+    relation_words = {
+        unicodedata.normalize("NFD", word).encode("ascii", "ignore").decode("ascii")
+        for word in RELATION_TRIGGERS
+    }
+    return PERSON_WORDS | SENSITIVE_WORDS | frozenset(relation_words)
diff --git a/server/src/server/memory/preference_gate.py b/server/src/server/memory/preference_gate.py
new file mode 100644
--- /dev/null
+++ b/server/src/server/memory/preference_gate.py
@@ -0,0 +1,159 @@
+"""The preference gate: does this text declare a first-person taste, and under which predicates?
+
+Pure and cheap (ADR 0021 decision 4): a closed list of Spanish patterns matched clause by
+clause after case and accent folding. The gate decides nothing durable. It only says whether
+spending a voice check and a model call is worth it, and it refuses on doubt:
+
+* a question or conditional;
+* a clause rather than a thing (``me gusta que ...``, ``prefiero que ...``), which is an
+  instruction to the robot and belongs to CM-3b;
+* any negation other than the triggers ``no me gusta(n)`` and ``no soporto``, so ``ya no me
+  gusta`` (a correction, CM-6) and ``prefiero no hablar de ...`` never pass;
+* a third person or a lead-in the grammar does not know (``mi hermano dice que me gusta``), and a
+  taste that follows an attribution after a soft break (``mi hija dice: me gusta el helado``);
+* a clause that names a person, a place, health, money, a credential or a disclosure.
+
+Each accepted taste is returned with the words that follow its own trigger, so the classifier can
+tie the model's object to a trigger of the same predicate (the model never decides the polarity).
+"""
+
+from __future__ import annotations
+
+from dataclasses import dataclass
+import re
+
+from server.cognition.intent_resolution import normalize_spanish
+from server.memory.candidate_types import CandidateReason, GateMatch
+from server.memory.lexicon import (
+    CLAUSE_OPENERS,
+    GREETING_WORDS,
+    LEAD_IN_WORDS,
+    NEGATORS,
+    PREFERENCE_FAVOURITE,
+    PREFERENCE_TRIGGERS,
+    candidate_denied_words,
+)
+
+__all__ = ["GateMatch", "GateResult", "match_preference"]
+
+# Punctuation ends a clause; a coordinating word ends a taste inside a clause ("me gusta el
+# mate pero odio el café"). A hard stop forgets an attribution, a soft break keeps it.
+_CLAUSE_SPLIT = re.compile(r"([,;:.!?¿¡…\n]+)")
+_HARD_STOP = re.compile(r"[.!?¿¡…\n]")
+_COORDINATION = re.compile(r"\s(?:pero|y|e|ni|aunque|sino)\s")
+_PREFERS = "prefers"
+_OBJECT_OPENING_PREPOSITIONS = frozenset({"a", "al"})
+_PREFIX_WORDS = LEAD_IN_WORDS | GREETING_WORDS | NEGATORS
+
+
+def _trigger_pattern() -> re.Pattern[str]:
+    """Build one alternation, longest phrase first, bounded by whole words."""
+    phrases = sorted(PREFERENCE_TRIGGERS, key=len, reverse=True)
+    alternatives = "|".join(
+        [*(re.escape(phrase) for phrase in phrases), PREFERENCE_FAVOURITE.pattern]
+    )
+    return re.compile(rf"(?<![a-z])(?:{alternatives})(?![a-z])")
+
+
+_TRIGGER = _trigger_pattern()
+_DENIED = candidate_denied_words()
+
+
+@dataclass(frozen=True)
+class GateResult:
+    """Outcome of the gate for one transcript.
+
+    Attributes:
+        matches: Each accepted taste with the words after its own trigger; empty when refused.
+        reason: Why the text was refused; ``None`` exactly when ``matches`` is not empty.
+    """
+
+    matches: tuple[GateMatch, ...]
+    reason: CandidateReason | None
+
+    @property
+    def predicates(self) -> frozenset[str]:
+        """The canonical predicates the text may carry."""
+        return frozenset(match.predicate for match in self.matches)
+
+
+def _predicate_of(trigger: str) -> str:
+    """Return the canonical predicate a matched trigger declares."""
+    if PREFERENCE_FAVOURITE.fullmatch(trigger):
+        return _PREFERS
+    return PREFERENCE_TRIGGERS[trigger]
+
+
+def _lead_refusal(lead: list[str]) -> CandidateReason | None:
+    """Refuse a negated or unknown lead-in: only a short closed list may precede a trigger."""
+    if any(word in NEGATORS for word in lead):
+        return CandidateReason.NEGATION_UNSUPPORTED
+    if any(word not in LEAD_IN_WORDS for word in lead):
+        return CandidateReason.NOT_A_TASTE
+    return None
+
+
+def _object_refusal(trigger_and_object: list[str], trailing: list[str]) -> CandidateReason | None:
+    """Refuse what follows a trigger unless it is a plain, positive, non-sensitive thing."""
+    if not trailing or trailing[0] in CLAUSE_OPENERS or "que" in trailing:
+        return CandidateReason.NOT_A_TASTE
+    if trailing[0] in NEGATORS:
+        return CandidateReason.NEGATION_UNSUPPORTED
+    if trailing[0] in _OBJECT_OPENING_PREPOSITIONS:
+        return CandidateReason.NOT_A_TASTE  # "odio a Rodrigo": a person, never a thing
+    if any(word in _DENIED for word in trigger_and_object):
+        return CandidateReason.SENSITIVE_TOPIC
+    return None
+
+
+def _match_part(folded: str) -> GateMatch | CandidateReason | None:
+    """Return a taste, the reason this part was refused, or ``None`` for no trigger."""
+    found = _TRIGGER.search(folded)
+    if found is None:
+        return None
+    lead = folded[: found.start()].split()
+    trailing = folded[found.end() :].split()
+    # The favourite trigger carries words ("mi hijo favorito es"): they are checked too.
+    refusal = _lead_refusal(lead) or _object_refusal(folded[found.start() :].split(), trailing)
+    if refusal is not None:
+        return refusal
+    return GateMatch(predicate=_predicate_of(found.group(0)), words=tuple(trailing))
+
+
+def match_preference(text: str) -> GateResult:
+    """Decide whether *text* may declare a first-person taste.
+
+    Args:
+        text: The user's own transcript for this turn (never the assistant's reply).
+
+    Returns:
+        The tastes a part of the text declares, each with the words after its trigger, or the
+        first closed reason the text was refused for. A text with no trigger at all is
+        ``GATE_NO_MATCH``.
+    """
+    if "?" in text or "¿" in text:
+        return GateResult((), CandidateReason.NOT_A_TASTE)
+    matches: list[GateMatch] = []
+    refusal: CandidateReason | None = None
+    attributed = False  # words that are not a lead-in preceded this clause after a soft break
+    pieces = _CLAUSE_SPLIT.split(text)
+    for index in range(0, len(pieces), 2):
+        folded_clause = normalize_spanish(pieces[index])
+        delimiter = pieces[index + 1] if index + 1 < len(pieces) else ""
+        outcomes = [_match_part(part) for part in _COORDINATION.split(folded_clause)]
+        has_trigger = any(outcome is not None for outcome in outcomes)
+        if has_trigger and attributed:
+            refusal = refusal or CandidateReason.NOT_A_TASTE
+        else:
+            for outcome in outcomes:
+                if isinstance(outcome, CandidateReason):
+                    refusal = refusal or outcome
+                elif outcome is not None:
+                    matches.append(outcome)
+        if not has_trigger and any(word not in _PREFIX_WORDS for word in folded_clause.split()):
+            attributed = True
+        if _HARD_STOP.search(delimiter):
+            attributed = False
+    if matches:
+        return GateResult(tuple(matches), None)
+    return GateResult((), refusal or CandidateReason.GATE_NO_MATCH)
```

- [ ] **Step 4: Run to see them pass, then lint and types** (as in Task 1, over these paths).
- [ ] **Step 5: Commit** `feat(server): add the preference gate (plan 0062)`; check `git log -1`.

---

## Task 3: The candidate classifier

**Files:**
- Create: `server/src/server/memory/candidate_classifier.py`
- Test: new `tests/unit/test_candidate_classifier.py`

**Interfaces:**
- Consumes: `resolve_predicate`, `normalize_spanish`, `CANDIDATE_TOPICS`, `candidate_denied_words()`.
- Produces: `classify(actor, raw, user_text, *, matches, known_person_names) ->
  ProposedCandidate | CandidateReason`; `comparison_key(phrase) -> str`;
  `CANDIDATE_VISIBILITY = PERSONAL` and `CANDIDATE_SENSITIVITY = NORMAL`.

The subject is the identified actor; the model's triple has no subject field at all. An object is
kept only as a short noun phrase of letters (or an infinitive from the list), in the closed topic
set, free of the denied words (person, place, health, money, credential, disclosure, religion,
politics, sexuality, drugs and violence), not a known name, not capitalised inside a sentence and
literally present in the words after a trigger of **its own predicate**, so the model never
chooses the polarity. A bare infinitive, short or with a clitic (`ser`, `ir`, `callarme`), passes
only from the closed list.

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/tests/unit/test_candidate_classifier.py b/tests/unit/test_candidate_classifier.py
new file mode 100644
--- /dev/null
+++ b/tests/unit/test_candidate_classifier.py
@@ -0,0 +1,293 @@
+"""Unit tests for the candidate classifier (ADR 0021 decision 5): pure, on doubt drop."""
+
+from datetime import UTC, datetime
+
+import pytest
+from server.cognition.authorization import DataSensitivity, DataVisibility
+from server.cognition.identity import (
+    ActivePersonContext,
+    ActivePersonStatus,
+    HouseholdRole,
+    IdentityAssurance,
+)
+from server.cognition.intent_resolution import normalize_spanish
+from server.cognition.models import Confidence, ConfidenceBasis
+from server.memory.candidate_classifier import (
+    CANDIDATE_SENSITIVITY,
+    CANDIDATE_VISIBILITY,
+    classify,
+    comparison_key,
+)
+from server.memory.candidate_types import (
+    CandidateReason,
+    GateMatch,
+    ProposedCandidate,
+    RawCandidate,
+)
+from server.memory.preference_gate import match_preference
+from server.settings import settings
+
+pytestmark = pytest.mark.unit
+
+_OWNER = 7
+_PREDICATES = ("likes", "dislikes", "prefers")
+
+
+def _everywhere(text: str) -> tuple[GateMatch, ...]:
+    """Every predicate matched over all the words of *text*: the grounding rule alone is tested."""
+    words = tuple(normalize_spanish(text).split())
+    return tuple(GateMatch(predicate=predicate, words=words) for predicate in _PREDICATES)
+
+
+_NAMES = frozenset({"Aldana Quiroga", "Tomasito"})
+_REFERENCE = datetime(2026, 10, 14, tzinfo=UTC)
+
+
+def _actor(
+    status: ActivePersonStatus = ActivePersonStatus.IDENTIFIED, person_id: int | None = _OWNER
+) -> ActivePersonContext:
+    return ActivePersonContext(
+        person_id=person_id if status is ActivePersonStatus.IDENTIFIED else None,
+        display_name="Canary" if status is ActivePersonStatus.IDENTIFIED else None,
+        status=status,
+        confidence=Confidence(
+            score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False, reason="canary"
+        ),
+        role=HouseholdRole.OWNER,
+        evidence=(),
+        resolved_at=_REFERENCE,
+        assurance=IdentityAssurance.BASIC,
+    )
+
+
+def _raw(obj: str, *, predicate: str = "likes", topic: str = "food") -> RawCandidate:
+    return RawCandidate(predicate=predicate, object=obj, topic=topic)
+
+
+def _classify(
+    obj: str,
+    text: str,
+    *,
+    predicate: str = "likes",
+    topic: str = "food",
+    matches: tuple[GateMatch, ...] | None = None,
+    names: frozenset[str] = _NAMES,
+    actor: ActivePersonContext | None = None,
+) -> ProposedCandidate | CandidateReason:
+    return classify(
+        actor or _actor(),
+        _raw(obj, predicate=predicate, topic=topic),
+        text,
+        matches=_everywhere(text) if matches is None else matches,
+        known_person_names=names,
+    )
+
+
+def test_a_grounded_taste_is_accepted_with_its_phrase_and_key() -> None:
+    result = _classify("el mate", "me gusta el mate")
+
+    assert result == ProposedCandidate(predicate="likes", value_text="el mate", value_key="mate")
+
+
+def test_the_candidate_is_always_the_owners_own_ordinary_data() -> None:
+    assert CANDIDATE_VISIBILITY is DataVisibility.PERSONAL
+    assert CANDIDATE_SENSITIVITY is DataSensitivity.NORMAL
+
+
+@pytest.mark.parametrize(
+    "alias, canonical",
+    [("le_gusta", "likes"), ("odia", "dislikes"), ("prefiere", "prefers"), ("LIKES", "likes")],
+)
+def test_the_predicate_resolves_through_the_registry(alias: str, canonical: str) -> None:
+    result = _classify("el mate", "me gusta el mate", predicate=alias)
+
+    assert isinstance(result, ProposedCandidate)
+    assert result.predicate == canonical
+
+
+def test_a_predicate_the_gate_did_not_return_is_a_mismatch() -> None:
+    assert (
+        _classify(
+            "el mate",
+            "me gusta el mate",
+            predicate="dislikes",
+            matches=match_preference("me gusta el mate").matches,
+        )
+        is CandidateReason.GATE_MISMATCH
+    )
+
+
+@pytest.mark.parametrize("predicate", ["lives_in", "child_of", "birth_date", "inventado"])
+def test_a_predicate_outside_the_three_is_a_mismatch(predicate: str) -> None:
+    assert _classify("el mate", "me gusta el mate", predicate=predicate) is (
+        CandidateReason.GATE_MISMATCH
+    )
+
+
+@pytest.mark.parametrize("topic", ["health", "family", "place", "", "FOOD"])
+def test_a_topic_outside_the_closed_set_is_dropped(topic: str) -> None:
+    assert _classify("el mate", "me gusta el mate", topic=topic) is CandidateReason.SENSITIVE_TOPIC
+
+
+def test_the_model_cannot_choose_the_subject() -> None:
+    """A subject is not even part of the model's triple: the identified actor is the subject."""
+    assert "subject" not in RawCandidate.__dataclass_fields__
+
+
+def test_an_actor_who_is_not_identified_gets_nothing() -> None:
+    assert (
+        _classify("el mate", "me gusta el mate", actor=_actor(ActivePersonStatus.UNKNOWN))
+        is CandidateReason.DENIED
+    )
+
+
+@pytest.mark.parametrize(
+    "obj",
+    ["mi hijo", "mi perro", "los gatos", "mi jefe", "la casa", "mi medicación", "la clave"],
+)
+def test_a_person_a_pet_a_place_or_a_sensitive_word_is_dropped(obj: str) -> None:
+    text = f"me gusta {obj}"
+
+    assert _classify(obj, text) is CandidateReason.SENSITIVE_TOPIC
+
+
+def test_the_name_of_a_known_person_is_dropped() -> None:
+    assert _classify("Tomasito", "me gusta Tomasito") is CandidateReason.SENSITIVE_TOPIC
+    assert _classify("el pilar", "me gusta el pilar", names=frozenset({"Pilar"})) is (
+        CandidateReason.SENSITIVE_TOPIC
+    )
+
+
+def test_an_object_the_user_did_not_say_is_not_grounded() -> None:
+    assert _classify("el té", "me gusta el mate") is CandidateReason.NOT_GROUNDED
+
+
+def test_grounding_ignores_case_accents_and_punctuation() -> None:
+    result = _classify("el CAFÉ", "Me gusta el café, la verdad.")
+
+    assert isinstance(result, ProposedCandidate)
+    assert result.value_key == "cafe"
+
+
+def test_grounding_is_by_whole_words() -> None:
+    assert _classify("mate", "me gusta el cogollo de matear") is CandidateReason.NOT_GROUNDED
+
+
+@pytest.mark.parametrize(
+    "obj",
+    [
+        "el mate 2",
+        "el mate\u200b",
+        "el mate\u202e",
+        "el_mate",
+        "el mate!",
+        "https mate",
+        "uno dos tres cuatro cinco seis",
+        "el mate y el cafe",
+        "x",
+    ],
+)
+def test_an_object_that_is_not_a_short_noun_phrase_of_letters_is_dropped(obj: str) -> None:
+    result = _classify(obj, f"me gusta {obj}")
+
+    assert result in {CandidateReason.NOT_A_TASTE, CandidateReason.SENSITIVE_TOPIC}
+
+
+def test_a_value_longer_than_the_setting_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
+    monkeypatch.setattr(settings, "memory_candidate_value_max_chars", 10)
+
+    assert _classify("el dulce de leche", "me gusta el dulce de leche") is (
+        CandidateReason.NOT_A_TASTE
+    )
+
+
+@pytest.mark.parametrize("obj", ["cantar", "bailar en la cocina"])
+def test_an_allowed_infinitive_is_a_thing(obj: str) -> None:
+    result = _classify(obj, f"me gusta {obj}", topic="pastime")
+
+    assert isinstance(result, ProposedCandidate)
+
+
+@pytest.mark.parametrize("obj", ["vivir en la costa", "mudarme", "hablar de política"])
+def test_an_infinitive_outside_the_list_is_dropped(obj: str) -> None:
+    result = _classify(obj, f"me gusta {obj}", topic="pastime")
+
+    assert isinstance(result, CandidateReason)
+
+
+def test_a_noun_that_ends_like_an_infinitive_is_kept_with_its_article() -> None:
+    result = _classify("el mar", "me gusta el mar", topic="weather")
+
+    assert isinstance(result, ProposedCandidate)
+
+
+def test_the_comparison_key_drops_the_article_and_folds() -> None:
+    assert comparison_key("El Café") == "cafe"
+    assert comparison_key("las empanadas") == "empanadas"
+    assert comparison_key("la") == ""
+    assert comparison_key("Té   verde") == "te verde"
+
+
+def test_value_text_keeps_the_spoken_phrase_with_its_article() -> None:
+    result = _classify("  la   pizza ", "mi comida favorita es la pizza", predicate="prefers")
+
+    assert isinstance(result, ProposedCandidate)
+    assert result.value_text == "la pizza"
+    assert result.value_key == "pizza"
+
+
+def test_classification_is_pure() -> None:
+    assert _classify("el mate", "me gusta el mate") == _classify("el mate", "me gusta el mate")
+
+
+def test_an_object_must_sit_after_a_trigger_of_its_own_predicate() -> None:
+    """The model never chooses the polarity: "el cafe" follows "odio", not "me gusta"."""
+    text = "me gusta el mate pero odio el cafe"
+    matches = match_preference(text).matches
+
+    assert _classify("el cafe", text, predicate="likes", matches=matches) is (
+        CandidateReason.NOT_GROUNDED
+    )
+    assert isinstance(
+        _classify("el cafe", text, predicate="dislikes", matches=matches), ProposedCandidate
+    )
+    assert isinstance(
+        _classify("el mate", text, predicate="likes", matches=matches), ProposedCandidate
+    )
+
+
+def test_a_taste_somebody_else_voiced_earlier_in_the_text_is_not_the_speakers() -> None:
+    text = "me gusta el mate. Mi hermano odia el cafe"
+    matches = match_preference(text).matches
+
+    assert _classify("el cafe", text, predicate="dislikes", matches=matches) is (
+        CandidateReason.GATE_MISMATCH
+    )
+    assert _classify("el cafe", text, predicate="likes", matches=matches) is (
+        CandidateReason.NOT_GROUNDED
+    )
+
+
+@pytest.mark.parametrize("obj", ["Rodrigo", "Madrid", "Café Martínez"])
+def test_a_capitalised_word_inside_a_sentence_is_a_name_not_a_thing(obj: str) -> None:
+    result = _classify(obj, f"Me gusta {obj}", topic="drink")
+
+    assert result is CandidateReason.SENSITIVE_TOPIC
+
+
+def test_a_capital_that_only_opens_a_sentence_is_not_a_name() -> None:
+    result = _classify("el mate", "Me gusta el mate. Gracias")
+
+    assert isinstance(result, ProposedCandidate)
+
+
+@pytest.mark.parametrize("obj", ["callarme", "quedarme en silencio", "ser", "ir", "cantarte"])
+def test_a_short_or_clitic_infinitive_is_dropped_unless_listed(obj: str) -> None:
+    result = _classify(obj, f"me gusta {obj}", topic="pastime")
+
+    assert result is CandidateReason.NOT_A_TASTE
+
+
+@pytest.mark.parametrize("obj", ["el catolicismo", "la cocaína", "los inmigrantes", "la política"])
+def test_religion_politics_drugs_and_hate_vocabulary_is_dropped(obj: str) -> None:
+    assert _classify(obj, f"me gusta {obj}") is CandidateReason.SENSITIVE_TOPIC
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_candidate_classifier.py -q -p no:cacheprovider`
  Expected RED: `ModuleNotFoundError: No module named 'server.memory.candidate_classifier'`.
- [ ] **Step 3: Implement:**

```diff
diff --git a/server/src/server/memory/candidate_classifier.py b/server/src/server/memory/candidate_classifier.py
new file mode 100644
--- /dev/null
+++ b/server/src/server/memory/candidate_classifier.py
@@ -0,0 +1,191 @@
+"""The candidate classifier: accept or drop one extracted pair and fix its classification.
+
+Pure (ADR 0021 decision 5): ``classify`` reads nothing but its arguments, so the model's
+untrusted output is judged by a deterministic function and nobody else assigns the
+classification. The model's subject is never read: the subject is the identified actor.
+
+The rule everywhere is *on doubt, drop*. An object is kept only as a short noun phrase (or an
+infinitive from a closed list) made of letters, placed by the extractor in a closed topic set,
+free of person, role, place, health, money, credential and disclosure words, not the name of
+anyone the household knows, and literally present in what the user said.
+"""
+
+from __future__ import annotations
+
+import re
+import unicodedata
+
+from server.cognition.authorization import DataSensitivity, DataVisibility
+from server.cognition.identity import ActivePersonContext, ActivePersonStatus
+from server.cognition.intent_resolution import normalize_spanish
+from server.memory.candidate_types import (
+    CandidateReason,
+    GateMatch,
+    ProposedCandidate,
+    RawCandidate,
+)
+from server.memory.lexicon import (
+    ALLOWED_INFINITIVES,
+    ARTICLES,
+    CANDIDATE_TOPICS,
+    candidate_denied_words,
+)
+from server.memory.predicate_registry import PredicateDefinition, resolve_predicate
+from server.settings import settings
+
+__all__ = ["CANDIDATE_SENSITIVITY", "CANDIDATE_VISIBILITY", "classify", "comparison_key"]
+
+#: What a CM-3a candidate becomes: the owner's own, ordinary data. The writer passes these
+#: explicitly because the registry defaults are the household reader's read contract.
+CANDIDATE_VISIBILITY = DataVisibility.PERSONAL
+CANDIDATE_SENSITIVITY = DataSensitivity.NORMAL
+
+_MAX_WORDS = 5
+_MIN_CHARS = 2
+_PHRASE = re.compile(rf"[^\W\d_]+(?: [^\W\d_]+){{0,{_MAX_WORDS - 1}}}")
+# An infinitive, with or without a clitic ("cantar", "ser", "ir", "callarme"): a bare verb is an
+# activity or a state of the speaker's life, so it passes only from the closed list.
+_INFINITIVE = re.compile(r"[a-z]*(?:ar|er|ir)(?:me|te|se|lo|la|le|nos)?")
+_WORD = re.compile(r"[^\W\d_]+")
+_SENTENCE_END = re.compile(r"[.!?¿¡…\n]+")
+_POSSESSIVES = frozenset(
+    {"mi", "mis", "tu", "tus", "su", "sus", "nuestro", "nuestra", "nuestros", "nuestras"}
+)
+_COORDINATORS = frozenset({"y", "e", "ni", "o", "u"})
+_URL_WORDS = frozenset({"www", "http", "https", "com", "net", "org"})
+_DENIED = candidate_denied_words() | _POSSESSIVES | _URL_WORDS
+
+
+def comparison_key(phrase: str) -> str:
+    """Return the key two spoken phrases are compared by: folded, without a leading article.
+
+    Args:
+        phrase: A spoken object ("El Café").
+
+    Returns:
+        The folded words without leading articles ("cafe"); empty when nothing remains.
+    """
+    words = normalize_spanish(phrase).split()
+    while words and words[0] in ARTICLES:
+        words.pop(0)
+    return " ".join(words)
+
+
+def _shape_refusal(phrase: str, words: list[str]) -> CandidateReason | None:
+    """Refuse an object that is not a short noun phrase of letters (the positive grammar)."""
+    if not _MIN_CHARS <= len(phrase) <= settings.memory_candidate_value_max_chars:
+        return CandidateReason.NOT_A_TASTE
+    if _PHRASE.fullmatch(phrase) is None or _COORDINATORS & set(words):
+        return CandidateReason.NOT_A_TASTE
+    first = words[0]
+    if first not in ARTICLES and _INFINITIVE.fullmatch(first) and first not in ALLOWED_INFINITIVES:
+        return CandidateReason.NOT_A_TASTE
+    return None
+
+
+def _capitalized_inside_sentences(user_text: str) -> frozenset[str]:
+    """Return the folded words the user wrote with a capital that do not open a sentence.
+
+    Speech-to-text capitalizes names of people, places and brands; a taste in one of them
+    ("me gusta Rodrigo", "me gusta Madrid") is a third party or a place, never a thing.
+    """
+    found: set[str] = set()
+    for sentence in _SENTENCE_END.split(user_text):
+        for word in _WORD.findall(sentence)[1:]:
+            if word[0].isupper():
+                found.add(normalize_spanish(word))
+    return frozenset(found)
+
+
+def _names_a_known_person(words: list[str], known_person_names: frozenset[str]) -> bool:
+    """Return whether any word of the object is a word of a name the household knows."""
+    name_words = {
+        part for name in known_person_names for part in normalize_spanish(name).split() if part
+    }
+    return bool(name_words & set(words))
+
+
+def _pair_refusal(
+    actor: ActivePersonContext,
+    definition: PredicateDefinition | None,
+    topic: str,
+    matches: tuple[GateMatch, ...],
+) -> CandidateReason | None:
+    """Refuse a triple whose subject, predicate or topic is not acceptable."""
+    if actor.status is not ActivePersonStatus.IDENTIFIED or actor.person_id is None:
+        return CandidateReason.DENIED
+    if definition is None or definition.canonical_id not in {m.predicate for m in matches}:
+        return CandidateReason.GATE_MISMATCH
+    if topic not in CANDIDATE_TOPICS:
+        return CandidateReason.SENSITIVE_TOPIC
+    return None
+
+
+def _phrase_refusal(
+    phrase: str,
+    words: list[str],
+    predicate: str,
+    user_text: str,
+    matches: tuple[GateMatch, ...],
+    known_person_names: frozenset[str],
+) -> CandidateReason | None:
+    """Refuse an object that is malformed, sensitive, a name or not grounded in its own trigger."""
+    if not words:
+        return CandidateReason.NOT_A_TASTE
+    refusal = _shape_refusal(phrase, words)
+    if refusal is not None:
+        return refusal
+    if (
+        _DENIED & set(words)
+        or _capitalized_inside_sentences(user_text) & set(words)
+        or _names_a_known_person(words, known_person_names)
+    ):
+        return CandidateReason.SENSITIVE_TOPIC
+    joined = f" {' '.join(words)} "
+    # Grounded only after a trigger of the SAME predicate: the model never chooses the polarity,
+    # and a taste somebody else voiced earlier in the text is not in this trigger's words.
+    if not any(
+        match.predicate == predicate and joined in f" {' '.join(match.words)} " for match in matches
+    ):
+        return CandidateReason.NOT_GROUNDED
+    return None
+
+
+def classify(
+    actor: ActivePersonContext,
+    raw: RawCandidate,
+    user_text: str,
+    *,
+    matches: tuple[GateMatch, ...],
+    known_person_names: frozenset[str],
+) -> ProposedCandidate | CandidateReason:
+    """Accept or drop one extracted pair.
+
+    Args:
+        actor: The identified actor; their id is the subject, whatever the model said.
+        raw: The extractor's untrusted triple.
+        user_text: What the user said this turn (never the assistant's reply).
+        matches: The tastes the preference gate accepted, each with the words after its own
+            trigger: the object must sit there, under the same predicate.
+        known_person_names: Names of the people and pets the household knows (an argument,
+            so this function stays pure).
+
+    Returns:
+        A ``ProposedCandidate`` that carries only the canonical predicate, the spoken phrase
+        and its comparison key, or the closed reason it was dropped for.
+    """
+    definition = resolve_predicate(raw.predicate)
+    refusal = _pair_refusal(actor, definition, raw.topic, matches)
+    if refusal is not None or definition is None:
+        return refusal or CandidateReason.GATE_MISMATCH
+    phrase = " ".join(unicodedata.normalize("NFC", raw.object).split())
+    words = normalize_spanish(phrase).split()
+    refusal = _phrase_refusal(
+        phrase, words, definition.canonical_id, user_text, matches, known_person_names
+    )
+    if refusal is not None:
+        return refusal
+    key = comparison_key(phrase)
+    if not key:
+        return CandidateReason.NOT_A_TASTE
+    return ProposedCandidate(predicate=definition.canonical_id, value_text=phrase, value_key=key)
```

- [ ] **Step 4: Run to see them pass, then lint and types.**
- [ ] **Step 5: Commit** `feat(server): add the candidate classifier (plan 0062)`; check `git log -1`.

---

## Task 4: The candidate extractor

**Files:**
- Create: `server/src/server/memory/candidate_extraction.py`
- Test: new `tests/unit/test_candidate_extraction.py`

**Interfaces:**
- Consumes: `llm_transport.ollama_chat`, `strip_json_fences`, `candidate_types.RawCandidate`.
- Produces: `async extract_candidates(client, user_text) -> tuple[RawCandidate, ...]` (at most three
  triples; raises `LLMError` with a fixed message and no cause, or `httpx.HTTPError`).

The model sees a system prompt and `Frase: <the user's words>` and nothing else (the function does
not even take the assistant's reply). A pydantic error quotes its input, which here is the model's
own output about the household, so the error is raised `from None` with a fixed message.

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/tests/unit/test_candidate_extraction.py b/tests/unit/test_candidate_extraction.py
new file mode 100644
--- /dev/null
+++ b/tests/unit/test_candidate_extraction.py
@@ -0,0 +1,132 @@
+"""Unit tests for the candidate extractor (ADR 0021 decision 4): user text only, no retry."""
+
+import json
+import logging
+from typing import get_args
+from unittest.mock import AsyncMock
+
+import httpx
+import pytest
+from server.exceptions import LLMError
+from server.memory import candidate_extraction
+from server.memory.candidate_extraction import _Triple, extract_candidates
+from server.memory.candidate_types import RawCandidate
+from server.memory.lexicon import CANDIDATE_TOPICS
+from server.settings import settings
+
+pytestmark = pytest.mark.unit
+
+_TEXT = "me gusta el mate y odio el cilantro"
+
+
+def _answer(*triples: dict[str, str]) -> str:
+    return json.dumps({"candidates": list(triples)})
+
+
+def _chat(monkeypatch: pytest.MonkeyPatch, reply: str | Exception) -> AsyncMock:
+    mock = (
+        AsyncMock(side_effect=reply)
+        if isinstance(reply, Exception)
+        else AsyncMock(return_value=reply)
+    )
+    monkeypatch.setattr(candidate_extraction, "ollama_chat", mock)
+    return mock
+
+
+async def test_the_model_sees_only_the_users_words(
+    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    chat = _chat(monkeypatch, _answer())
+
+    await extract_candidates(http_client, _TEXT)
+
+    messages = chat.call_args.args[1]
+    assert [message["role"] for message in messages] == ["system", "user"]
+    assert _TEXT in messages[1]["content"]
+    assert "[assistant]" not in messages[1]["content"]
+    assert chat.call_args.kwargs["options"] == {"temperature": 0.1}
+    assert chat.call_args.kwargs["timeout"] == settings.ollama_timeout_s
+    assert "format_schema" in chat.call_args.kwargs
+
+
+async def test_the_answer_is_returned_as_untrusted_triples(
+    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    _chat(
+        monkeypatch,
+        _answer(
+            {"predicate": "likes", "object": "el mate", "topic": "drink"},
+            {"predicate": "dislikes", "object": "el cilantro", "topic": "food"},
+        ),
+    )
+
+    result = await extract_candidates(http_client, _TEXT)
+
+    assert result == (
+        RawCandidate(predicate="likes", object="el mate", topic="drink"),
+        RawCandidate(predicate="dislikes", object="el cilantro", topic="food"),
+    )
+
+
+async def test_at_most_three_triples_are_kept(
+    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    triple = {"predicate": "likes", "object": "el mate", "topic": "drink"}
+    _chat(monkeypatch, _answer(triple, triple, triple, triple, triple))
+
+    assert len(await extract_candidates(http_client, _TEXT)) == 3
+
+
+async def test_a_fenced_answer_is_accepted(
+    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    fence = "`" * 3  # built, not written: this file also lives inside a Markdown code fence
+    _chat(monkeypatch, f"{fence}json\n" + _answer() + f"\n{fence}")
+
+    assert await extract_candidates(http_client, _TEXT) == ()
+
+
+@pytest.mark.parametrize(
+    "reply",
+    [
+        "not json",
+        _answer({"predicate": "lives_in", "object": "la costa", "topic": "food"}),
+        _answer({"predicate": "likes", "object": "el mate", "topic": "health"}),
+        '{"candidates": "el mate"}',
+    ],
+)
+async def test_an_invalid_answer_raises_without_echoing_it_and_is_not_retried(
+    http_client: httpx.AsyncClient,
+    monkeypatch: pytest.MonkeyPatch,
+    reply: str,
+    caplog: pytest.LogCaptureFixture,
+) -> None:
+    chat = _chat(monkeypatch, reply)
+
+    with caplog.at_level(logging.DEBUG), pytest.raises(LLMError) as excinfo:
+        await extract_candidates(http_client, _TEXT)
+
+    assert chat.await_count == 1
+    assert str(excinfo.value) == "Candidate extraction returned invalid JSON"
+    assert excinfo.value.__cause__ is None
+    assert excinfo.value.__suppress_context__
+    for fragment in ("mate", "lives_in", "health"):
+        assert fragment not in str(excinfo.value)
+        assert fragment not in caplog.text
+
+
+async def test_a_transport_failure_propagates_once(
+    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    chat = _chat(monkeypatch, httpx.ConnectError("down"))
+
+    with pytest.raises(httpx.ConnectError):
+        await extract_candidates(http_client, _TEXT)
+
+    assert chat.await_count == 1
+
+
+def test_the_schema_topics_are_the_closed_set_of_the_lexicon() -> None:
+    topics = set(get_args(_Triple.model_fields["topic"].annotation))
+
+    assert topics == CANDIDATE_TOPICS
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_candidate_extraction.py -q -p no:cacheprovider`
  Expected RED: `ImportError: cannot import name 'candidate_extraction' from 'server.memory'`.
- [ ] **Step 3: Implement:**

```diff
diff --git a/server/src/server/memory/candidate_extraction.py b/server/src/server/memory/candidate_extraction.py
new file mode 100644
--- /dev/null
+++ b/server/src/server/memory/candidate_extraction.py
@@ -0,0 +1,103 @@
+"""The candidate extractor: one local-model call that structures a matched turn (ADR 0021 §4).
+
+The model receives **only the user's text** — never the assistant's reply, which is the
+model's own words — and answers with at most three ``{predicate, object, topic}`` triples whose
+predicate and topic are closed enums. Whatever it returns is untrusted: the classifier judges
+it. There is no retry (a missed candidate is restated, and a retry would double a worst case
+of tens of seconds) and no exception message that could carry the model's output.
+"""
+
+from __future__ import annotations
+
+import logging
+from typing import TYPE_CHECKING, Literal
+
+from pydantic import BaseModel, Field, ValidationError
+
+from server.exceptions import LLMError
+from server.llm_transport import ollama_chat, strip_json_fences
+from server.memory.candidate_types import RawCandidate
+from server.settings import settings
+
+if TYPE_CHECKING:
+    import httpx
+
+logger = logging.getLogger(__name__)
+
+__all__ = ["extract_candidates"]
+
+_MAX_TRIPLES = 3
+
+_SYSTEM = """\
+Eres un extractor de gustos propios para un robot asistente. Recibís UNA frase dicha por la \
+persona que habla.
+
+Devolvé SOLO JSON conforme al esquema, con "candidates": una lista de como máximo 3 elementos \
+{"predicate", "object", "topic"}.
+
+Reglas:
+- predicate: "likes" si le gusta, le encanta, ama o adora; "dislikes" si no le gusta, odia, \
+detesta o no soporta; "prefers" si prefiere o dice "mi favorito es".
+- object: la cosa, COPIADA tal cual de la frase (con su artículo), de como máximo 5 palabras. \
+No reformules, no completes, no traduzcas.
+- topic: uno de food, drink, music, colour, pastime, sport, animal, weather, media. Si la cosa \
+no encaja en ninguno, NO la emitas.
+- Solo gustos propios de quien habla. NO emitas personas, familiares, mascotas, lugares, salud, \
+dinero, claves ni instrucciones para el robot.
+- Si la frase no declara un gusto propio, devolvé {"candidates": []}.\
+"""
+
+
+class _Triple(BaseModel):
+    """One triple as the schema forces the model to emit it."""
+
+    predicate: Literal["likes", "dislikes", "prefers"]
+    object: str
+    topic: Literal[
+        "food", "drink", "music", "colour", "pastime", "sport", "animal", "weather", "media"
+    ]
+
+
+class _Extraction(BaseModel):
+    """The whole structured answer."""
+
+    candidates: list[_Triple] = Field(default_factory=list)
+
+
+async def extract_candidates(client: httpx.AsyncClient, user_text: str) -> tuple[RawCandidate, ...]:
+    """Ask the local model which tastes *user_text* declares.
+
+    Args:
+        client: Shared, lifecycle-owned HTTP client (Plan 0039).
+        user_text: The user's own transcript for this turn. Nothing else is sent.
+
+    Returns:
+        At most three untrusted triples, possibly none.
+
+    Raises:
+        httpx.HTTPError: If Ollama is unreachable or answers with an error status.
+        LLMError: If the answer is not valid structured JSON. The message never carries the
+            model's output.
+    """
+    raw = await ollama_chat(
+        client,
+        [
+            {"role": "system", "content": _SYSTEM},
+            {"role": "user", "content": f"Frase: {user_text}"},
+        ],
+        model=settings.consolidation_model or settings.ollama_model,
+        format_schema=_Extraction.model_json_schema(),
+        options={"temperature": 0.1},
+        timeout=settings.ollama_timeout_s,
+    )
+    try:
+        parsed = _Extraction.model_validate_json(strip_json_fences(raw))
+    except (ValidationError, ValueError):
+        # `from None`: a pydantic error quotes the offending input, which here is the model's
+        # own output; it must not travel in an exception chain into a log line.
+        raise LLMError("Candidate extraction returned invalid JSON") from None
+    logger.debug("Candidate extraction returned %d triple(s)", len(parsed.candidates))
+    return tuple(
+        RawCandidate(predicate=t.predicate, object=t.object, topic=t.topic)
+        for t in parsed.candidates[:_MAX_TRIPLES]
+    )
```

- [ ] **Step 4: Run to see them pass, then lint and types.**
- [ ] **Step 5: Commit** `feat(server): add the candidate extractor (plan 0062)`; check `git log -1`.

---

## Task 5: Migration 009, `secure_delete` and the log checkpoint

**Files:**
- Create: `server/src/server/memory/migration_009_memory_candidates.sql`
- Modify: `server/src/server/db.py`
- Test: new `tests/integration/test_memory_candidates_schema.py`; modified `tests/integration/test_biometric_consent_schema.py`, `tests/integration/test_household_authorization_schema.py`, `tests/integration/test_memory_v4_schema.py`, `tests/integration/test_owner_credentials_schema.py`

**Interfaces:**
- Produces: table `memory_candidates` (the ADR's columns; `CHECK` that `value_text` and `value_key`
  are non-null exactly in `proposed` and `offered`; a unique partial index on
  `(subject_person_id, predicate, value_key)` over the live statuses); `PRAGMA secure_delete = ON`
  on the connection; `async db.checkpoint_wal() -> bool` (takes the write lock, waits at most 0.5 s, runs
  `PRAGMA wal_checkpoint(TRUNCATE)` and returns `False` instead of raising when a reader or an open
  cursor blocks it); `_MIGRATIONS` ends at `(9, ...)`.

- [ ] **Step 1: Write the failing tests.** A new schema file (columns, the `CHECK` both ways,
  resolving without scrubbing is refused, closed status and channel, the partial index, `CASCADE`,
  `SET NULL`, `secure_delete` is 1 and not 2, a checkpoint empties the log) and the four existing
  schema tests that pin `user_version`:

```diff
diff --git a/tests/integration/test_biometric_consent_schema.py b/tests/integration/test_biometric_consent_schema.py
--- a/tests/integration/test_biometric_consent_schema.py
+++ b/tests/integration/test_biometric_consent_schema.py
@@ -82,7 +82,7 @@ async def test_migration_seven_creates_face_consent_grants_table(memory_db: Path
     """Migration 7 must create face_consent_grants with the expected columns."""
     conn = db.get_conn()
     version_cursor = await conn.execute("PRAGMA user_version")
-    assert await version_cursor.fetchone() == (8,)
+    assert await version_cursor.fetchone() == (9,)
     await version_cursor.close()

     tables_cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
diff --git a/tests/integration/test_household_authorization_schema.py b/tests/integration/test_household_authorization_schema.py
--- a/tests/integration/test_household_authorization_schema.py
+++ b/tests/integration/test_household_authorization_schema.py
@@ -44,7 +44,7 @@ async def test_migration_five_adds_role_and_safe_audit_tables(authorization_db:
     """Authorization storage must be additive and keep legacy/v4 data intact."""
     conn = db.get_conn()
     version_cursor = await conn.execute("PRAGMA user_version")
-    assert await version_cursor.fetchone() == (8,)
+    assert await version_cursor.fetchone() == (9,)
     await version_cursor.close()

     tables_cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
diff --git a/tests/integration/test_memory_candidates_schema.py b/tests/integration/test_memory_candidates_schema.py
new file mode 100644
--- /dev/null
+++ b/tests/integration/test_memory_candidates_schema.py
@@ -0,0 +1,235 @@
+"""Migration 009 and the connection's physical-scrub settings (ADR 0021 decision 6)."""
+
+from __future__ import annotations
+
+import sqlite3
+from typing import TYPE_CHECKING
+
+import pytest
+from server.memory.declarative import upsert_entity
+from server.memory.predicate_registry import resolve_predicate
+from server.memory.relational_v4 import assert_literal_fact
+from server.settings import settings
+
+from server import db
+
+if TYPE_CHECKING:
+    from collections.abc import AsyncIterator
+    from pathlib import Path
+
+pytestmark = pytest.mark.integration
+
+_INSERT = (
+    "INSERT INTO memory_candidates "
+    "(subject_person_id, asserted_by_person_id, predicate, value_text, value_key, status, "
+    "channel, source_correlation_id, proposed_at, expires_at) "
+    "VALUES (?, ?, 'likes', ?, ?, ?, 'voice_classic', 'corr-1', "
+    "'2026-10-14T10:00:00+00:00', '2026-10-15T10:00:00+00:00')"
+)
+
+
+@pytest.fixture
+async def candidate_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Path]:
+    """Open a fresh database with every migration applied."""
+    db_path = tmp_path / "candidates-schema.db"
+    monkeypatch.setattr(settings, "brain_db_path", db_path)
+    db._conn = None
+    await db.open_db()
+    await db.run_migrations()
+    yield db_path
+    await db.close_db()
+    db._conn = None
+
+
+async def _owner() -> int:
+    return await upsert_entity(name="Canary Owner", type="person")
+
+
+async def _insert(owner: int, value: str | None, key: str | None, status: str) -> None:
+    conn = db.get_conn()
+    await conn.execute(_INSERT, (owner, owner, value, key, status))
+    await conn.commit()
+
+
+async def test_the_schema_is_at_version_nine_with_the_candidate_table(candidate_db: Path) -> None:
+    conn = db.get_conn()
+    cursor = await conn.execute("PRAGMA user_version")
+    assert await cursor.fetchone() == (9,)
+    await cursor.close()
+
+    cursor = await conn.execute("PRAGMA table_info(memory_candidates)")
+    columns = [str(row[1]) for row in await cursor.fetchall()]
+    await cursor.close()
+
+    assert columns == [
+        "id",
+        "subject_person_id",
+        "asserted_by_person_id",
+        "predicate",
+        "value_text",
+        "value_key",
+        "status",
+        "channel",
+        "source_correlation_id",
+        "offer_correlation_id",
+        "resolution_correlation_id",
+        "proposed_at",
+        "offered_at",
+        "resolved_at",
+        "expires_at",
+        "offer_count",
+        "promoted_fact_id",
+    ]
+
+
+@pytest.mark.parametrize("status", ["proposed", "offered"])
+async def test_a_live_candidate_must_carry_its_value_and_key(
+    candidate_db: Path, status: str
+) -> None:
+    owner = await _owner()
+
+    await _insert(owner, "el mate", "mate", status)
+    for value, key in ((None, None), ("el mate", None), (None, "mate")):
+        with pytest.raises(sqlite3.IntegrityError):
+            await _insert(owner, value, key, status)
+
+
+@pytest.mark.parametrize("status", ["confirmed", "rejected", "expired"])
+async def test_a_resolved_candidate_cannot_keep_a_value(candidate_db: Path, status: str) -> None:
+    owner = await _owner()
+
+    await _insert(owner, None, None, status)
+    for value, key in (("el mate", "mate"), ("el mate", None), (None, "mate")):
+        with pytest.raises(sqlite3.IntegrityError):
+            await _insert(owner, value, key, status)
+
+
+async def test_resolving_a_row_without_scrubbing_it_is_refused(candidate_db: Path) -> None:
+    owner = await _owner()
+    await _insert(owner, "el mate", "mate", "proposed")
+
+    with pytest.raises(sqlite3.IntegrityError):
+        await db.get_conn().execute("UPDATE memory_candidates SET status = 'confirmed'")
+
+
+async def test_status_and_channel_are_closed_sets(candidate_db: Path) -> None:
+    owner = await _owner()
+    conn = db.get_conn()
+
+    with pytest.raises(sqlite3.IntegrityError):
+        await conn.execute(_INSERT, (owner, owner, None, None, "disputed"))
+    with pytest.raises(sqlite3.IntegrityError):
+        await conn.execute(
+            "INSERT INTO memory_candidates (subject_person_id, asserted_by_person_id, predicate, "
+            "status, channel, source_correlation_id, proposed_at, expires_at) VALUES "
+            "(?, ?, 'likes', 'expired', 'chat', 'c', 'a', 'b')",
+            (owner, owner),
+        )
+
+
+async def test_the_same_live_value_cannot_be_stored_twice_but_may_return_after_resolving(
+    candidate_db: Path,
+) -> None:
+    owner = await _owner()
+    conn = db.get_conn()
+    await _insert(owner, "el mate", "mate", "proposed")
+
+    with pytest.raises(sqlite3.IntegrityError):
+        await _insert(owner, "El Mate", "mate", "offered")
+    await conn.execute(
+        "UPDATE memory_candidates SET status = 'rejected', value_text = NULL, value_key = NULL"
+    )
+    await conn.commit()
+    await _insert(owner, "el mate", "mate", "proposed")
+
+
+async def test_deleting_the_subject_removes_its_candidates(candidate_db: Path) -> None:
+    owner = await _owner()
+    await _insert(owner, "el mate", "mate", "proposed")
+    conn = db.get_conn()
+
+    await conn.execute("DELETE FROM entities WHERE id = ?", (owner,))
+    await conn.commit()
+
+    cursor = await conn.execute("SELECT COUNT(*) FROM memory_candidates")
+    assert await cursor.fetchone() == (0,)
+    await cursor.close()
+
+
+async def test_deleting_the_promoted_fact_only_clears_the_link(candidate_db: Path) -> None:
+    owner = await _owner()
+    likes = resolve_predicate("likes")
+    assert likes is not None
+    fact = await assert_literal_fact(subject_entity_id=owner, definition=likes, value="el mate")
+    conn = db.get_conn()
+    await conn.execute(_INSERT, (owner, owner, None, None, "confirmed"))
+    await conn.execute("UPDATE memory_candidates SET promoted_fact_id = ?", (fact.id,))
+    await conn.commit()
+
+    await conn.execute("DELETE FROM literal_facts_v4 WHERE id = ?", (fact.id,))
+    await conn.commit()
+
+    cursor = await conn.execute("SELECT promoted_fact_id FROM memory_candidates")
+    assert await cursor.fetchone() == (None,)
+    await cursor.close()
+
+
+async def test_the_connection_overwrites_deleted_content(candidate_db: Path) -> None:
+    """`secure_delete` is ON (1), not FAST (2): a scrubbed value must not survive in free pages."""
+    cursor = await db.get_conn().execute("PRAGMA secure_delete")
+
+    assert await cursor.fetchone() == (1,)
+    await cursor.close()
+
+
+async def test_a_checkpoint_empties_the_write_ahead_log(candidate_db: Path) -> None:
+    owner = await _owner()
+    await _insert(owner, "el mate", "mate", "proposed")
+    wal = candidate_db.with_name(candidate_db.name + "-wal")
+    assert wal.exists()
+    assert wal.stat().st_size > 0
+
+    assert await db.checkpoint_wal() is True
+
+    assert wal.stat().st_size == 0
+
+
+async def test_a_checkpoint_pinned_by_another_reader_reports_false_and_does_not_raise(
+    candidate_db: Path,
+) -> None:
+    """An operator's shell reading the file only postpones the scrub; it must not fail a caller."""
+    owner = await _owner()
+    await _insert(owner, "el mate", "mate", "proposed")
+    reader = sqlite3.connect(candidate_db)
+    reader.execute("BEGIN")
+    reader.execute("SELECT COUNT(*) FROM memory_candidates").fetchall()
+    try:
+        assert await db.checkpoint_wal() is False
+    finally:
+        reader.close()
+
+    assert await db.checkpoint_wal() is True
+
+
+async def test_a_checkpoint_with_a_cursor_open_on_the_shared_connection_does_not_raise(
+    candidate_db: Path,
+) -> None:
+    owner = await _owner()
+    await _insert(owner, "el mate", "mate", "proposed")
+    # Many rows and one fetch: the statement stays active, as a coroutine between an execute\n    # and its fetchall would leave it.
+    cursor = await db.get_conn().execute("SELECT * FROM sqlite_master")
+    await cursor.fetchone()
+
+    outcome = await db.checkpoint_wal()
+    await cursor.close()
+
+    assert isinstance(outcome, bool)
+    assert await db.checkpoint_wal() is True
+
+
+async def test_a_checkpoint_restores_the_normal_busy_timeout(candidate_db: Path) -> None:
+    await db.checkpoint_wal()
+
+    cursor = await db.get_conn().execute("PRAGMA busy_timeout")
+    assert await cursor.fetchone() == (5000,)
+    await cursor.close()
diff --git a/tests/integration/test_memory_v4_schema.py b/tests/integration/test_memory_v4_schema.py
--- a/tests/integration/test_memory_v4_schema.py
+++ b/tests/integration/test_memory_v4_schema.py
@@ -36,7 +36,7 @@ async def test_v4_schema_is_additive_and_preserves_legacy_facts(v4_db: None) ->
     version_cursor = await conn.execute("PRAGMA user_version")
     version_row = await version_cursor.fetchone()
     await version_cursor.close()
-    assert version_row == (8,)
+    assert version_row == (9,)

     tables_cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
     tables = {str(row[0]) for row in await tables_cursor.fetchall()}
diff --git a/tests/integration/test_owner_credentials_schema.py b/tests/integration/test_owner_credentials_schema.py
--- a/tests/integration/test_owner_credentials_schema.py
+++ b/tests/integration/test_owner_credentials_schema.py
@@ -46,7 +46,7 @@ async def test_migration_six_adds_owner_pin_credentials_table(credentials_db: No
     # The fixture runs every pending migration, so this reflects the latest
     # registered version (7, since migration_007_biometric_consent.sql),
     # not specifically "6" — migration 6's table presence is asserted below.
-    assert await version_cursor.fetchone() == (8,)
+    assert await version_cursor.fetchone() == (9,)
     await version_cursor.close()

     tables_cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/integration/test_memory_candidates_schema.py tests/integration/test_biometric_consent_schema.py tests/integration/test_household_authorization_schema.py tests/integration/test_memory_v4_schema.py tests/integration/test_owner_credentials_schema.py -q -p no:cacheprovider`
  Expected RED: `assert (8,) == (9,)` in four files and no `memory_candidates` table.
- [ ] **Step 3: Implement** the migration, the migration list, the pragma and the checkpoint:

```diff
diff --git a/server/src/server/db.py b/server/src/server/db.py
--- a/server/src/server/db.py
+++ b/server/src/server/db.py
@@ -33,9 +33,15 @@ _MIGRATIONS: tuple[tuple[int, str], ...] = (
     (6, "migration_006_owner_credentials.sql"),
     (7, "migration_007_biometric_consent.sql"),
     (8, "migration_008_voice_consent.sql"),
+    (9, "migration_009_memory_candidates.sql"),
 )
 _conn: aiosqlite.Connection | None = None

+# How long a statement waits for a lock held by another connection. A checkpoint waits less:
+# it holds the write lock while it waits, and giving up only postpones the scrub.
+_BUSY_TIMEOUT_MS = 5000
+_CHECKPOINT_BUSY_MS = 500
+
 # Owns every runtime write transaction (Plan 0035, ADR 0011). Startup
 # migrations run before any request can arrive and never touch this lock —
 # `run_migrations` keeps its own commit-per-script discipline, unchanged.
@@ -75,6 +81,10 @@ async def open_db() -> None:
         await _conn.execute("PRAGMA journal_mode = WAL")
         await _conn.execute("PRAGMA synchronous = NORMAL")
         await _conn.execute("PRAGMA foreign_keys = ON")
+        # ON, not FAST: a scrubbed candidate value must be overwritten with zeros in the file
+        # and in every page the write-ahead log re-writes (ADR 0021 decision 6). The cost is a
+        # little extra I/O on deletes, and this database is small and local.
+        await _conn.execute("PRAGMA secure_delete = ON")
         # Defends against contention from a process outside our own lock
         # (an offline script, an operator's sqlite3 shell) — it does not
         # replace `transaction()`'s coroutine-level ownership, which is what
@@ -82,13 +92,53 @@ async def open_db() -> None:
         # sqlite3 already defaults `connect(timeout=5.0)` to the same 5000ms,
         # so this line changes no observed behavior; it exists so the value
         # is a decision made here, not an implicit stdlib default.
-        await _conn.execute("PRAGMA busy_timeout = 5000")
+        await _conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
         await _conn.commit()
     except Exception as exc:
         raise BrainMemoryError("Failed to open SQLite") from exc
     _write_lock = asyncio.Lock()


+async def checkpoint_wal() -> bool:
+    """Fold the write-ahead log into the database file and truncate it, if SQLite lets it.
+
+    A scrub overwrites the page it changed, but the write-ahead log keeps the earlier frames
+    until a checkpoint copies them out and the log is reset. Callers that erase a protected
+    value call this after the transaction that erased it commits (ADR 0021 decision 6).
+
+    The module's write lock is held so no transaction of this connection is open (a checkpoint
+    inside one is refused). The checkpoint never raises for a lock: another connection reading
+    the file (an operator's shell) or a cursor left open on this one only postpones it, and the
+    caller must not fail an operation that already committed because of it.
+
+    Returns:
+        ``True`` when the log was truncated; ``False`` when it was busy or locked (try again at
+        the next store entry or retention run).
+
+    Raises:
+        BrainMemoryError: If the database is not open.
+    """
+    conn = get_conn()
+    if _write_lock is None:
+        raise BrainMemoryError("DB not open — call open_db() first")
+    async with _write_lock:
+        try:
+            await conn.execute(f"PRAGMA busy_timeout = {_CHECKPOINT_BUSY_MS}")
+            cursor = await conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
+            row = await cursor.fetchone()
+            await cursor.close()
+        except aiosqlite.Error as exc:
+            logger.warning("WAL checkpoint postponed (%s)", type(exc).__name__)
+            return False
+        finally:
+            await conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
+    # (busy, log frames, checkpointed frames): busy is 1 when a reader pinned the log.
+    if row is None or int(row[0]) != 0:
+        logger.warning("WAL checkpoint postponed (busy)")
+        return False
+    return True
+
+
 async def close_db() -> None:
     """Close the global connection. Idempotent."""
     global _conn, _write_lock  # noqa: PLW0603
diff --git a/server/src/server/memory/migration_009_memory_candidates.sql b/server/src/server/memory/migration_009_memory_candidates.sql
new file mode 100644
--- /dev/null
+++ b/server/src/server/memory/migration_009_memory_candidates.sql
@@ -0,0 +1,54 @@
+-- Migration 9 — memory candidates (Plan 0062, CM-3a, ADR 0021).
+-- A candidate is a claim the identified owner made about their own taste, kept until the
+-- owner confirms it or it lapses. It is NOT canonical memory: the one writer promotes it into
+-- literal_facts_v4 (whose lifecycle CHECK has no `proposed` state and cannot be altered
+-- without rebuilding the table), and every row of V4 stays canonical.
+--
+-- The value exists only while the candidate is live. The CHECK makes the scrub a schema rule:
+-- value_text and value_key are non-null exactly in `proposed` and `offered`, so a resolution
+-- that forgets to erase the value is refused by the database itself. Timestamps are written
+-- by the caller from one clock as UTC ISO 8601 (never datetime('now')), so expiry and the
+-- audit compare like with like.
+-- No raw utterance, no source_memory_id (episodes are CM-4) and no assurance column: in
+-- CM-3a a candidate always needs face and voice of the same person (decision 3).
+
+CREATE TABLE IF NOT EXISTS memory_candidates (
+    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
+    subject_person_id           INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
+    asserted_by_person_id       INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
+    predicate                   TEXT NOT NULL,
+    value_text                  TEXT,
+    value_key                   TEXT,
+    status                      TEXT NOT NULL CHECK (
+        status IN ('proposed', 'offered', 'confirmed', 'rejected', 'expired')
+    ),
+    channel                     TEXT NOT NULL CHECK (channel IN ('voice_classic', 'voice_stream')),
+    source_correlation_id       TEXT NOT NULL,
+    offer_correlation_id        TEXT,
+    resolution_correlation_id   TEXT,
+    proposed_at                 TEXT NOT NULL,
+    offered_at                  TEXT,
+    resolved_at                 TEXT,
+    expires_at                  TEXT NOT NULL,
+    offer_count                 INTEGER NOT NULL DEFAULT 0 CHECK (offer_count >= 0),
+    promoted_fact_id            INTEGER REFERENCES literal_facts_v4(id) ON DELETE SET NULL,
+    CHECK (
+        (status IN ('proposed', 'offered') AND value_text IS NOT NULL AND value_key IS NOT NULL)
+        OR
+        (status NOT IN ('proposed', 'offered') AND value_text IS NULL AND value_key IS NULL)
+    )
+);
+
+-- One live candidate per (person, predicate, comparison key): a repeated statement is a
+-- no-op insert, never a second offer.
+CREATE UNIQUE INDEX IF NOT EXISTS memory_candidates_live_value_idx
+    ON memory_candidates (subject_person_id, predicate, value_key)
+    WHERE status IN ('proposed', 'offered');
+
+CREATE INDEX IF NOT EXISTS memory_candidates_subject_status_idx
+    ON memory_candidates (subject_person_id, status);
+
+-- The retention job and every store entry look up what has lapsed.
+CREATE INDEX IF NOT EXISTS memory_candidates_live_expiry_idx
+    ON memory_candidates (expires_at)
+    WHERE status IN ('proposed', 'offered');
```

- [ ] **Step 4: Run to see them pass, then lint and types.** Also
  `uv run pytest tests/integration/test_db.py tests/integration/test_db_transaction.py -q -p no:cacheprovider`.
- [ ] **Step 5: Commit** `feat(server): add migration 009 and secure delete (plan 0062)`; check `git log -1`.

---

## Task 6: The candidate store

**Files:**
- Create: `server/src/server/memory/candidates.py`
- Modify: `server/src/server/logging_setup.py`
- Test: new `tests/integration/test_memory_candidates_store.py`, `tests/unit/test_aiosqlite_logging.py`

**Interfaces:**
- Consumes: `db.transaction`, `db.checkpoint_wal`, the vocabulary of Task 2.
- Produces (`memory/candidates.py`, the only module that issues SQL on `memory_candidates`):
  `iso_utc(moment)`, `Candidate`, `InsertStatus`, `InsertResult`,
  `async insert_candidate(proposal, *, subject_person_id, asserted_by_person_id, channel,
  correlation_id, now)`, `get_candidate`, `get_candidate_in_transaction`,
  `async mark_offered(candidate_id, subject_person_id, *, correlation_id, now) -> bool`,
  `async resolve_candidate(...)` and `resolve_candidate_in_transaction(conn, ...)` (to `confirmed` or
  `rejected`, scrubbing the value), `run_housekeeping(conn, now)`,
  `expire_lapsed_in_transaction(conn, now)`, `async checkpoint_after_scrub(scrubbed)` (truncates the
  log after a transaction that erased a value, or retries the checkpoint a busy log postponed),
  `void_live_candidates(now)`,
  `reset_for_startup(now, *, enabled)`, and `VOID_LIVE_SQL`. Also
  `logging_setup`: the `aiosqlite` logger at `WARNING`.

Transitions are compare-and-set and always filtered by the subject; every store entry first expires
what lapsed and returns unanswered offers to `proposed`; a repeated statement is a no-op, the cap
refuses and never evicts, and every store path returns `DISABLED`/`False` with the kill-switch off.

- [ ] **Step 1: Write the failing tests.** The store over a temporary SQLite (24 tests, including
  the physical scrub in three ways, with a control that the value *is* found while live), and the
  driver log level:

```diff
diff --git a/tests/integration/test_memory_candidates_store.py b/tests/integration/test_memory_candidates_store.py
new file mode 100644
--- /dev/null
+++ b/tests/integration/test_memory_candidates_store.py
@@ -0,0 +1,472 @@
+"""Integration tests for the candidate store (ADR 0021 decision 6) over a temporary SQLite."""
+
+from __future__ import annotations
+
+from datetime import UTC, datetime, timedelta, timezone
+import logging
+import sqlite3
+from typing import TYPE_CHECKING
+from uuid import UUID, uuid4
+
+import pytest
+from server.memory import candidates
+from server.memory.candidate_types import CandidateChannel, CandidateStatus, ProposedCandidate
+from server.memory.candidates import InsertStatus, iso_utc
+from server.memory.declarative import upsert_entity
+from server.settings import settings
+
+from server import db
+
+if TYPE_CHECKING:
+    from collections.abc import AsyncIterator
+    from pathlib import Path
+
+pytestmark = pytest.mark.integration
+
+_T0 = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
+_CANARY = "zumo de pomelo rosado"
+
+
+def _proposal(
+    value: str = "el mate", key: str = "mate", predicate: str = "likes"
+) -> ProposedCandidate:
+    return ProposedCandidate(predicate=predicate, value_text=value, value_key=key)
+
+
+@pytest.fixture
+async def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Path]:
+    """A fresh database, with the candidate subsystem on."""
+    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "candidates.db")
+    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
+    db._conn = None
+    await db.open_db()
+    await db.run_migrations()
+    yield tmp_path / "candidates.db"
+    await db.close_db()
+    db._conn = None
+
+
+async def _person(name: str = "Canary Owner") -> int:
+    return await upsert_entity(name=name, type="person")
+
+
+async def _insert(
+    owner: int, proposal: ProposedCandidate | None = None, *, now: datetime = _T0
+) -> candidates.InsertResult:
+    return await candidates.insert_candidate(
+        proposal or _proposal(),
+        subject_person_id=owner,
+        asserted_by_person_id=owner,
+        channel=CandidateChannel.VOICE_CLASSIC,
+        correlation_id=uuid4(),
+        now=now,
+    )
+
+
+async def _status(candidate_id: int) -> CandidateStatus:
+    candidate = await candidates.get_candidate(candidate_id)
+    assert candidate is not None
+    return candidate.status
+
+
+@pytest.mark.usefixtures("store")
+async def test_an_accepted_candidate_is_stored_live_with_its_deadline() -> None:
+    owner = await _person()
+    correlation = UUID(int=42)
+
+    result = await candidates.insert_candidate(
+        _proposal(),
+        subject_person_id=owner,
+        asserted_by_person_id=owner,
+        channel=CandidateChannel.VOICE_STREAM,
+        correlation_id=correlation,
+        now=_T0,
+    )
+
+    assert result.status is InsertStatus.INSERTED
+    assert result.candidate_id is not None
+    stored = await candidates.get_candidate(result.candidate_id)
+    assert stored is not None
+    assert (stored.predicate, stored.value_text, stored.value_key) == ("likes", "el mate", "mate")
+    assert stored.status is CandidateStatus.PROPOSED
+    assert stored.channel is CandidateChannel.VOICE_STREAM
+    assert stored.subject_person_id == stored.asserted_by_person_id == owner
+    assert stored.source_correlation_id == str(correlation)
+    assert stored.proposed_at == iso_utc(_T0)
+    assert stored.expires_at == iso_utc(
+        _T0 + timedelta(seconds=settings.memory_candidate_ttl_seconds)
+    )
+    assert stored.offer_count == 0
+    assert stored.promoted_fact_id is None
+
+
+def test_the_one_clock_is_utc_iso_and_refuses_a_naive_moment() -> None:
+    assert iso_utc(_T0) == "2026-10-14T10:00:00.000000+00:00"
+    assert iso_utc(_T0.astimezone(timezone(timedelta(hours=-3)))) == iso_utc(_T0)
+    with pytest.raises(ValueError, match="timezone-aware"):
+        iso_utc(datetime(2026, 10, 14, 10, 0))
+
+
+@pytest.mark.usefixtures("store")
+async def test_a_repeated_statement_is_a_no_op_insert() -> None:
+    owner = await _person()
+    first = await _insert(owner, _proposal("el mate", "mate"))
+
+    second = await _insert(owner, _proposal("El Mate", "mate"))
+
+    assert first.status is InsertStatus.INSERTED
+    assert second.status is InsertStatus.DUPLICATE
+    assert second.candidate_id is None
+    cursor = await db.get_conn().execute("SELECT COUNT(*) FROM memory_candidates")
+    assert await cursor.fetchone() == (1,)
+    await cursor.close()
+
+
+@pytest.mark.usefixtures("store")
+async def test_the_same_key_under_another_predicate_is_a_different_candidate() -> None:
+    owner = await _person()
+    await _insert(owner, _proposal("el mate", "mate", "likes"))
+
+    other = await _insert(owner, _proposal("el mate", "mate", "dislikes"))
+
+    assert other.status is InsertStatus.INSERTED
+
+
+@pytest.mark.usefixtures("store")
+async def test_at_the_cap_a_new_candidate_is_refused_and_nothing_is_evicted(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    monkeypatch.setattr(settings, "memory_candidate_max_live", 2)
+    owner = await _person()
+    first = await _insert(owner, _proposal("el mate", "mate"))
+    second = await _insert(owner, _proposal("el jazz", "jazz"))
+
+    refused = await _insert(owner, _proposal("el rock", "rock"))
+
+    assert refused.status is InsertStatus.CAPACITY
+    assert first.candidate_id is not None
+    assert second.candidate_id is not None
+    assert await _status(first.candidate_id) is CandidateStatus.PROPOSED
+    assert await _status(second.candidate_id) is CandidateStatus.PROPOSED
+
+
+@pytest.mark.usefixtures("store")
+async def test_a_duplicate_at_the_cap_is_still_a_duplicate(monkeypatch: pytest.MonkeyPatch) -> None:
+    monkeypatch.setattr(settings, "memory_candidate_max_live", 1)
+    owner = await _person()
+    await _insert(owner, _proposal("el mate", "mate"))
+
+    again = await _insert(owner, _proposal("el mate", "mate"))
+
+    assert again.status is InsertStatus.DUPLICATE
+
+
+@pytest.mark.usefixtures("store")
+async def test_the_cap_counts_each_person_apart(monkeypatch: pytest.MonkeyPatch) -> None:
+    monkeypatch.setattr(settings, "memory_candidate_max_live", 1)
+    owner = await _person("Canary Owner")
+    visitor = await _person("Canary Visitor")
+    await _insert(owner, _proposal("el mate", "mate"))
+
+    other = await _insert(visitor, _proposal("el jazz", "jazz"))
+
+    assert other.status is InsertStatus.INSERTED
+
+
+@pytest.mark.usefixtures("store")
+async def test_a_lapsed_candidate_is_expired_and_scrubbed_at_the_next_store_entry() -> None:
+    owner = await _person()
+    stale = await _insert(owner, _proposal("el mate", "mate"))
+    later = _T0 + timedelta(seconds=settings.memory_candidate_ttl_seconds)
+
+    await _insert(owner, _proposal("el jazz", "jazz"), now=later)
+
+    assert stale.candidate_id is not None
+    expired = await candidates.get_candidate(stale.candidate_id)
+    assert expired is not None
+    assert expired.status is CandidateStatus.EXPIRED
+    assert (expired.value_text, expired.value_key) == (None, None)
+    assert expired.resolved_at == iso_utc(later)
+
+
+@pytest.mark.usefixtures("store")
+async def test_an_offer_moves_a_proposed_candidate_once() -> None:
+    owner = await _person()
+    stored = await _insert(owner)
+    assert stored.candidate_id is not None
+    offer = uuid4()
+
+    first = await candidates.mark_offered(
+        stored.candidate_id, owner, correlation_id=offer, now=_T0 + timedelta(seconds=5)
+    )
+    second = await candidates.mark_offered(
+        stored.candidate_id, owner, correlation_id=uuid4(), now=_T0 + timedelta(seconds=6)
+    )
+
+    assert (first, second) == (True, False)
+    candidate = await candidates.get_candidate(stored.candidate_id)
+    assert candidate is not None
+    assert candidate.status is CandidateStatus.OFFERED
+    assert candidate.offer_count == 1
+    assert candidate.offer_correlation_id == str(offer)
+    assert candidate.offered_at == iso_utc(_T0 + timedelta(seconds=5))
+
+
+@pytest.mark.usefixtures("store")
+async def test_an_unanswered_offer_returns_to_proposed_on_the_next_access() -> None:
+    owner = await _person()
+    stored = await _insert(owner)
+    assert stored.candidate_id is not None
+    await candidates.mark_offered(stored.candidate_id, owner, correlation_id=uuid4(), now=_T0)
+    after_window = _T0 + timedelta(seconds=settings.memory_candidate_answer_seconds)
+
+    await _insert(owner, _proposal("el jazz", "jazz"), now=after_window)
+
+    candidate = await candidates.get_candidate(stored.candidate_id)
+    assert candidate is not None
+    assert candidate.status is CandidateStatus.PROPOSED
+    assert candidate.offered_at is None
+    assert candidate.offer_correlation_id is None
+    assert candidate.offer_count == 1
+
+
+@pytest.mark.usefixtures("store")
+async def test_a_candidate_is_offered_at_most_the_configured_times_and_then_lapses(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    monkeypatch.setattr(settings, "memory_candidate_max_offers", 2)
+    owner = await _person()
+    stored = await _insert(owner)
+    assert stored.candidate_id is not None
+    window = timedelta(seconds=settings.memory_candidate_answer_seconds)
+    moment = _T0
+    for _ in range(2):
+        assert await candidates.mark_offered(
+            stored.candidate_id, owner, correlation_id=uuid4(), now=moment
+        )
+        moment += window
+
+    third = await candidates.mark_offered(
+        stored.candidate_id, owner, correlation_id=uuid4(), now=moment
+    )
+
+    assert third is False
+    candidate = await candidates.get_candidate(stored.candidate_id)
+    assert candidate is not None
+    assert candidate.status is CandidateStatus.EXPIRED
+    assert candidate.value_text is None
+
+
+@pytest.mark.usefixtures("store")
+@pytest.mark.parametrize("outcome", [CandidateStatus.CONFIRMED, CandidateStatus.REJECTED])
+async def test_resolving_an_offered_candidate_erases_its_value(outcome: CandidateStatus) -> None:
+    owner = await _person()
+    stored = await _insert(owner)
+    assert stored.candidate_id is not None
+    await candidates.mark_offered(stored.candidate_id, owner, correlation_id=uuid4(), now=_T0)
+    answer = uuid4()
+    moment = _T0 + timedelta(seconds=10)
+
+    resolved = await candidates.resolve_candidate(
+        stored.candidate_id, owner, to=outcome, correlation_id=answer, now=moment
+    )
+    again = await candidates.resolve_candidate(
+        stored.candidate_id, owner, to=outcome, correlation_id=uuid4(), now=moment
+    )
+
+    assert (resolved, again) == (True, False)
+    candidate = await candidates.get_candidate(stored.candidate_id)
+    assert candidate is not None
+    assert candidate.status is outcome
+    assert (candidate.value_text, candidate.value_key) == (None, None)
+    assert candidate.resolution_correlation_id == str(answer)
+    assert candidate.resolved_at == iso_utc(moment)
+
+
+@pytest.mark.usefixtures("store")
+async def test_only_an_offered_candidate_can_be_resolved() -> None:
+    owner = await _person()
+    stored = await _insert(owner)
+    assert stored.candidate_id is not None
+
+    resolved = await candidates.resolve_candidate(
+        stored.candidate_id, owner, to=CandidateStatus.CONFIRMED, correlation_id=uuid4(), now=_T0
+    )
+
+    assert resolved is False
+    assert await _status(stored.candidate_id) is CandidateStatus.PROPOSED
+
+
+@pytest.mark.usefixtures("store")
+async def test_another_person_can_neither_offer_nor_resolve_a_candidate() -> None:
+    owner = await _person("Canary Owner")
+    visitor = await _person("Canary Visitor")
+    stored = await _insert(owner)
+    assert stored.candidate_id is not None
+
+    stolen_offer = await candidates.mark_offered(
+        stored.candidate_id, visitor, correlation_id=uuid4(), now=_T0
+    )
+    await candidates.mark_offered(stored.candidate_id, owner, correlation_id=uuid4(), now=_T0)
+    stolen_answer = await candidates.resolve_candidate(
+        stored.candidate_id, visitor, to=CandidateStatus.REJECTED, correlation_id=uuid4(), now=_T0
+    )
+
+    assert (stolen_offer, stolen_answer) == (False, False)
+    assert await _status(stored.candidate_id) is CandidateStatus.OFFERED
+
+
+@pytest.mark.usefixtures("store")
+async def test_a_resolution_must_name_confirmed_or_rejected() -> None:
+    owner = await _person()
+    stored = await _insert(owner)
+    assert stored.candidate_id is not None
+
+    with pytest.raises(ValueError, match="confirmed or rejected"):
+        await candidates.resolve_candidate(
+            stored.candidate_id, owner, to=CandidateStatus.EXPIRED, correlation_id=uuid4(), now=_T0
+        )
+
+
+@pytest.mark.usefixtures("store")
+async def test_the_kill_switch_covers_every_store_path(monkeypatch: pytest.MonkeyPatch) -> None:
+    owner = await _person()
+    stored = await _insert(owner)
+    assert stored.candidate_id is not None
+    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
+
+    insert = await _insert(owner, _proposal("el jazz", "jazz"))
+    offered = await candidates.mark_offered(
+        stored.candidate_id, owner, correlation_id=uuid4(), now=_T0
+    )
+    resolved = await candidates.resolve_candidate(
+        stored.candidate_id, owner, to=CandidateStatus.REJECTED, correlation_id=uuid4(), now=_T0
+    )
+
+    assert insert.status is InsertStatus.DISABLED
+    assert (offered, resolved) == (False, False)
+    cursor = await db.get_conn().execute("SELECT COUNT(*) FROM memory_candidates")
+    assert await cursor.fetchone() == (1,)
+    await cursor.close()
+
+
+@pytest.mark.usefixtures("store")
+async def test_start_up_with_the_kill_switch_on_returns_offers_to_proposed() -> None:
+    owner = await _person()
+    stored = await _insert(owner)
+    assert stored.candidate_id is not None
+    await candidates.mark_offered(stored.candidate_id, owner, correlation_id=uuid4(), now=_T0)
+
+    await candidates.reset_for_startup(_T0 + timedelta(seconds=1), enabled=True)
+
+    candidate = await candidates.get_candidate(stored.candidate_id)
+    assert candidate is not None
+    assert candidate.status is CandidateStatus.PROPOSED
+    assert candidate.value_text == "el mate"
+    assert candidate.offer_count == 1
+
+
+@pytest.mark.usefixtures("store")
+async def test_start_up_with_the_kill_switch_off_voids_every_live_candidate(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    owner = await _person()
+    first = await _insert(owner, _proposal("el mate", "mate"))
+    second = await _insert(owner, _proposal("el jazz", "jazz"))
+    assert second.candidate_id is not None
+    await candidates.mark_offered(second.candidate_id, owner, correlation_id=uuid4(), now=_T0)
+    await candidates.reset_for_startup(_T0 + timedelta(seconds=1), enabled=False)
+
+    assert first.candidate_id is not None
+    for candidate_id in (first.candidate_id, second.candidate_id):
+        candidate = await candidates.get_candidate(candidate_id)
+        assert candidate is not None
+        assert candidate.status is CandidateStatus.EXPIRED
+        assert (candidate.value_text, candidate.value_key) == (None, None)
+
+
+async def _housekeeping(now: datetime) -> None:
+    """What the retention job does with candidates, without the rest of the job."""
+    async with db.transaction() as conn:
+        scrubbed = await candidates.run_housekeeping(conn, now)
+    await candidates.checkpoint_after_scrub(scrubbed)
+
+
+def _file_bytes(db_path: Path) -> bytes:
+    """Concatenate the database file and its write-ahead log, as an attacker would read them."""
+    pieces = [db_path.read_bytes()]
+    wal = db_path.with_name(db_path.name + "-wal")
+    if wal.exists():
+        pieces.append(wal.read_bytes())
+    return b"".join(pieces)
+
+
+@pytest.mark.parametrize(
+    "scrub",
+    ["reject", "expire", "void"],
+)
+async def test_a_scrubbed_value_is_gone_from_the_file_and_the_log(
+    store: Path, scrub: str, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    """The scrub is physical: the canary value is found while live and never after."""
+    owner = await _person()
+    stored = await _insert(owner, _proposal(_CANARY, "zumo de pomelo rosado"))
+    assert stored.candidate_id is not None
+    await db.get_conn().commit()
+    assert _CANARY.encode() in _file_bytes(store)
+
+    if scrub == "reject":
+        await candidates.mark_offered(stored.candidate_id, owner, correlation_id=uuid4(), now=_T0)
+        await candidates.resolve_candidate(
+            stored.candidate_id, owner, to=CandidateStatus.REJECTED, correlation_id=uuid4(), now=_T0
+        )
+    elif scrub == "expire":
+        await _housekeeping(_T0 + timedelta(seconds=settings.memory_candidate_ttl_seconds))
+    else:
+        await candidates.reset_for_startup(_T0, enabled=False)
+
+    assert _CANARY.encode() not in _file_bytes(store)
+
+
+@pytest.mark.usefixtures("store")
+async def test_no_log_line_carries_a_value(caplog: pytest.LogCaptureFixture) -> None:
+    owner = await _person()
+    with caplog.at_level(logging.DEBUG, logger="server"):
+        stored = await _insert(owner, _proposal(_CANARY, "zumo de pomelo rosado"))
+        assert stored.candidate_id is not None
+        await candidates.mark_offered(stored.candidate_id, owner, correlation_id=uuid4(), now=_T0)
+        await candidates.resolve_candidate(
+            stored.candidate_id, owner, to=CandidateStatus.REJECTED, correlation_id=uuid4(), now=_T0
+        )
+        await _housekeeping(_T0)
+        await candidates.reset_for_startup(_T0, enabled=True)
+
+    assert "pomelo" not in caplog.text
+
+
+async def test_a_scrub_whose_checkpoint_was_blocked_is_finished_at_the_next_entry(
+    store: Path,
+) -> None:
+    """A reader pinned the log: the page was erased, the old frames stay until a later retry."""
+    owner = await _person()
+    stored = await _insert(owner, _proposal(_CANARY, "zumo de pomelo rosado"))
+    assert stored.candidate_id is not None
+    await candidates.mark_offered(stored.candidate_id, owner, correlation_id=uuid4(), now=_T0)
+    reader = sqlite3.connect(store)
+    reader.execute("BEGIN")
+    reader.execute("SELECT COUNT(*) FROM memory_candidates").fetchall()
+    try:
+        resolved = await candidates.resolve_candidate(
+            stored.candidate_id,
+            owner,
+            to=CandidateStatus.REJECTED,
+            correlation_id=uuid4(),
+            now=_T0,
+        )
+    finally:
+        reader.close()
+
+    assert resolved is True  # the resolution committed; the postponed checkpoint did not fail it
+    await candidates.checkpoint_after_scrub(0)
+
+    assert _CANARY.encode() not in _file_bytes(store)
diff --git a/tests/unit/test_aiosqlite_logging.py b/tests/unit/test_aiosqlite_logging.py
new file mode 100644
--- /dev/null
+++ b/tests/unit/test_aiosqlite_logging.py
@@ -0,0 +1,26 @@
+"""SQL parameters never reach a log (ADR 0021 decision 12): aiosqlite is held at WARNING."""
+
+from collections.abc import Generator
+import logging
+
+import pytest
+from server.logging_setup import configure_logging
+from server.settings import Settings, settings
+
+pytestmark = pytest.mark.unit
+
+
+@pytest.fixture
+def _restore_logging() -> Generator[None, None, None]:
+    """Configure logging again from the process settings after the test."""
+    yield
+    configure_logging(settings)
+
+
+@pytest.mark.usefixtures("_restore_logging")
+def test_the_sql_driver_is_held_at_warning_even_when_the_app_logs_debug() -> None:
+    """At DEBUG aiosqlite prints each statement with its parameters: a taste would be logged."""
+    configure_logging(Settings(log_level="DEBUG", log_to_file=False))
+
+    assert logging.getLogger().getEffectiveLevel() == logging.DEBUG
+    assert logging.getLogger("aiosqlite").getEffectiveLevel() == logging.WARNING
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/integration/test_memory_candidates_store.py tests/unit/test_aiosqlite_logging.py -q -p no:cacheprovider`
  Expected RED: `ImportError: cannot import name 'candidates' from 'server.memory'`.
- [ ] **Step 3: Implement:**

```diff
diff --git a/server/src/server/logging_setup.py b/server/src/server/logging_setup.py
--- a/server/src/server/logging_setup.py
+++ b/server/src/server/logging_setup.py
@@ -158,6 +158,9 @@ def configure_logging(settings: "Settings") -> None:
             "uvicorn": {"propagate": True},
             "uvicorn.access": {"propagate": True},
             "uvicorn.error": {"propagate": True},
+            # aiosqlite logs every statement with its parameters at DEBUG. A value the household
+            # told the robot (a candidate, a fact) must never reach a log, whatever LOG_LEVEL is.
+            "aiosqlite": {"level": "WARNING", "propagate": True},
             # Console only and never the file: the opt-in transcript log (Plan 0052).
             # Without the opt-in it has no handler, so a record goes nowhere.
             CONVERSATION_LOGGER_NAME: {
diff --git a/server/src/server/memory/candidates.py b/server/src/server/memory/candidates.py
new file mode 100644
--- /dev/null
+++ b/server/src/server/memory/candidates.py
@@ -0,0 +1,522 @@
+"""The candidate store: claims the owner made about their own taste, until they lapse or resolve.
+
+A candidate is **not** canonical memory (ADR 0021 decision 6). This module is the only place
+that issues SQL against ``memory_candidates`` (an architecture guard pins it) and it
+guarantees, in code and in the schema:
+
+* **The value is scrubbed on resolution.** ``value_text`` and ``value_key`` exist only while a
+  candidate is ``proposed`` or ``offered``; a resolution that forgot to erase them is refused
+  by the table's ``CHECK``. A scrub is followed by a write-ahead-log checkpoint, so the old
+  bytes are not left in the log.
+* **Transitions are compare-and-set** (``UPDATE ... WHERE status = ?`` and a row count) and
+  always filtered by the subject, so another person can neither resolve nor lapse a candidate.
+* **One clock.** Every timestamp is supplied by the caller as an aware datetime and stored as
+  UTC ISO 8601; the store never uses SQLite's ``datetime('now')``.
+* **Bounded and idempotent.** A repeated statement is a no-op insert; at the per-person cap a
+  new candidate is refused and an old one is never evicted.
+* **Housekeeping on every entry.** Lapsed candidates are expired and unanswered offers return
+  to ``proposed`` inside the entry's own transaction, whatever the retention job did.
+
+Logs carry ids, the predicate, a status and a closed reason, never a value.
+"""
+
+from __future__ import annotations
+
+from dataclasses import dataclass
+from datetime import UTC, datetime, timedelta
+from enum import StrEnum
+import logging
+from typing import TYPE_CHECKING
+
+from server import db
+from server.memory.candidate_types import CandidateChannel, CandidateStatus, ProposedCandidate
+from server.settings import settings
+
+if TYPE_CHECKING:
+    from uuid import UUID
+
+    import aiosqlite
+
+logger = logging.getLogger(__name__)
+
+__all__ = [
+    "VOID_LIVE_SQL",
+    "Candidate",
+    "InsertResult",
+    "InsertStatus",
+    "checkpoint_after_scrub",
+    "expire_lapsed_in_transaction",
+    "get_candidate",
+    "insert_candidate",
+    "iso_utc",
+    "mark_offered",
+    "reset_for_startup",
+    "resolve_candidate",
+    "resolve_candidate_in_transaction",
+    "run_housekeeping",
+    "void_live_candidates",
+]
+
+_LIVE = ("proposed", "offered")
+_COLUMNS = (
+    "id, subject_person_id, asserted_by_person_id, predicate, value_text, value_key, status, "
+    "channel, source_correlation_id, offer_correlation_id, resolution_correlation_id, "
+    "proposed_at, offered_at, resolved_at, expires_at, offer_count, promoted_fact_id"
+)
+
+#: Void every live candidate. Used by start-up with the kill-switch off, and by
+#: ``scripts/scrub_candidates.py`` (stdlib ``sqlite3``) before ``just reset-db`` copies the
+#: database to ``data/backups``. One parameter: the resolution timestamp.
+VOID_LIVE_SQL = (
+    "UPDATE memory_candidates SET status = 'expired', value_text = NULL, value_key = NULL, "
+    "resolved_at = ? WHERE status IN ('proposed', 'offered')"
+)
+
+
+class InsertStatus(StrEnum):
+    """Closed outcome of one insert attempt."""
+
+    INSERTED = "inserted"
+    DUPLICATE = "duplicate"
+    CAPACITY = "capacity"
+    DISABLED = "disabled"
+
+
+@dataclass(frozen=True)
+class InsertResult:
+    """What ``insert_candidate`` did.
+
+    Attributes:
+        status: The closed outcome.
+        candidate_id: The new row's id when ``status`` is ``INSERTED``.
+    """
+
+    status: InsertStatus
+    candidate_id: int | None = None
+
+
+@dataclass(frozen=True)
+class Candidate:
+    """One stored candidate. ``value_text`` and ``value_key`` are ``None`` once resolved."""
+
+    id: int
+    subject_person_id: int
+    asserted_by_person_id: int
+    predicate: str
+    value_text: str | None
+    value_key: str | None
+    status: CandidateStatus
+    channel: CandidateChannel
+    source_correlation_id: str
+    offer_correlation_id: str | None
+    resolution_correlation_id: str | None
+    proposed_at: str
+    offered_at: str | None
+    resolved_at: str | None
+    expires_at: str
+    offer_count: int
+    promoted_fact_id: int | None
+
+
+def iso_utc(moment: datetime) -> str:
+    """Return *moment* as fixed-width UTC ISO 8601, the only timestamp format stored here.
+
+    Args:
+        moment: An aware datetime.
+
+    Returns:
+        ``YYYY-MM-DDTHH:MM:SS.ffffff+00:00``; fixed width, so strings sort like instants.
+
+    Raises:
+        ValueError: If *moment* is naive.
+    """
+    if moment.tzinfo is None or moment.utcoffset() is None:
+        raise ValueError("candidate timestamps must be timezone-aware")
+    return moment.astimezone(UTC).isoformat(timespec="microseconds")
+
+
+def _from_row(row: tuple[object, ...]) -> Candidate:
+    """Build the immutable model from one ``_COLUMNS`` row."""
+    return Candidate(
+        id=int(str(row[0])),
+        subject_person_id=int(str(row[1])),
+        asserted_by_person_id=int(str(row[2])),
+        predicate=str(row[3]),
+        value_text=None if row[4] is None else str(row[4]),
+        value_key=None if row[5] is None else str(row[5]),
+        status=CandidateStatus(str(row[6])),
+        channel=CandidateChannel(str(row[7])),
+        source_correlation_id=str(row[8]),
+        offer_correlation_id=None if row[9] is None else str(row[9]),
+        resolution_correlation_id=None if row[10] is None else str(row[10]),
+        proposed_at=str(row[11]),
+        offered_at=None if row[12] is None else str(row[12]),
+        resolved_at=None if row[13] is None else str(row[13]),
+        expires_at=str(row[14]),
+        offer_count=int(str(row[15])),
+        promoted_fact_id=None if row[16] is None else int(str(row[16])),
+    )
+
+
+async def _rowcount(cursor: aiosqlite.Cursor) -> int:
+    """Read and close a cursor, returning how many rows its statement changed."""
+    changed = cursor.rowcount
+    await cursor.close()
+    return changed
+
+
+async def expire_lapsed_in_transaction(conn: aiosqlite.Connection, now: datetime) -> int:
+    """Expire (and scrub) every live candidate past its deadline or out of offers.
+
+    Args:
+        conn: The connection of an open ``db.transaction()``.
+        now: The caller's clock reading.
+
+    Returns:
+        How many candidates were expired. The caller checkpoints the log when this is not 0.
+    """
+    stamp = iso_utc(now)
+    cursor = await conn.execute(
+        "UPDATE memory_candidates SET status = 'expired', value_text = NULL, value_key = NULL, "
+        "resolved_at = ? WHERE status IN ('proposed', 'offered') AND expires_at <= ?",
+        (stamp, stamp),
+    )
+    lapsed = await _rowcount(cursor)
+    cursor = await conn.execute(
+        "UPDATE memory_candidates SET status = 'expired', value_text = NULL, value_key = NULL, "
+        "resolved_at = ? WHERE status = 'proposed' AND offer_count >= ?",
+        (stamp, settings.memory_candidate_max_offers),
+    )
+    return lapsed + await _rowcount(cursor)
+
+
+async def run_housekeeping(conn: aiosqlite.Connection, now: datetime) -> int:
+    """Expire what lapsed and return unanswered offers to ``proposed``.
+
+    Args:
+        conn: The connection of an open ``db.transaction()``.
+        now: The caller's clock reading.
+
+    Returns:
+        How many candidates were scrubbed (expired); the caller checkpoints when not 0.
+    """
+    waited_since = iso_utc(now - timedelta(seconds=settings.memory_candidate_answer_seconds))
+    cursor = await conn.execute(
+        "UPDATE memory_candidates SET status = 'proposed', offered_at = NULL, "
+        "offer_correlation_id = NULL WHERE status = 'offered' AND offered_at <= ?",
+        (waited_since,),
+    )
+    await cursor.close()
+    return await expire_lapsed_in_transaction(conn, now)
+
+
+# A checkpoint that SQLite postponed (a reader pinned the log) is owed to the next entry: the
+# value was erased in the page but its old frames are still in the log until it is truncated.
+_checkpoint_pending = False
+
+
+async def checkpoint_after_scrub(scrubbed: int) -> None:
+    """Truncate the write-ahead log after a transaction that erased a value, or retry one owed.
+
+    Args:
+        scrubbed: How many values the transaction that just committed erased. ``0`` only
+            retries a checkpoint a previous call could not complete. Never raises for a busy
+            log: the operation that erased the value has already committed.
+    """
+    global _checkpoint_pending  # noqa: PLW0603 — one owed checkpoint per process, like the slot
+    if not scrubbed and not _checkpoint_pending:
+        return
+    _checkpoint_pending = not await db.checkpoint_wal()
+
+
+async def insert_candidate(
+    proposal: ProposedCandidate,
+    *,
+    subject_person_id: int,
+    asserted_by_person_id: int,
+    channel: CandidateChannel,
+    correlation_id: UUID,
+    now: datetime,
+) -> InsertResult:
+    """Store one accepted candidate, unless it repeats a live one or the person is at the cap.
+
+    Args:
+        proposal: The classifier's output.
+        subject_person_id: Whose memory it would become.
+        asserted_by_person_id: Who said it (the subject in CM-3a).
+        channel: The voice route it came from.
+        correlation_id: The turn's correlation id, so audit rows join to the candidate.
+        now: The caller's clock reading.
+
+    Returns:
+        ``INSERTED`` with the id; ``DUPLICATE`` for a live candidate with the same key;
+        ``CAPACITY`` at the per-person cap (nothing is evicted); ``DISABLED`` with the
+        kill-switch off.
+    """
+    if not settings.memory_candidates_enabled:
+        return InsertResult(InsertStatus.DISABLED)
+    async with db.transaction() as conn:
+        scrubbed = await run_housekeeping(conn, now)
+        result = await _insert_in_transaction(
+            conn, proposal, subject_person_id, asserted_by_person_id, channel, correlation_id, now
+        )
+    await checkpoint_after_scrub(scrubbed)
+    logger.info(
+        "Candidate insert: %s",
+        result.status.value,
+        extra={
+            "event": "candidate.insert",
+            "outcome": result.status,
+            "candidate_id": result.candidate_id,
+            "predicate": proposal.predicate,
+            "channel": channel,
+        },
+    )
+    return result
+
+
+async def _insert_in_transaction(
+    conn: aiosqlite.Connection,
+    proposal: ProposedCandidate,
+    subject_person_id: int,
+    asserted_by_person_id: int,
+    channel: CandidateChannel,
+    correlation_id: UUID,
+    now: datetime,
+) -> InsertResult:
+    """Apply the duplicate and cap rules, then insert, inside an open transaction."""
+    cursor = await conn.execute(
+        "SELECT 1 FROM memory_candidates WHERE subject_person_id = ? AND predicate = ? "
+        "AND value_key = ? AND status IN ('proposed', 'offered')",
+        (subject_person_id, proposal.predicate, proposal.value_key),
+    )
+    duplicate = await cursor.fetchone()
+    await cursor.close()
+    if duplicate is not None:
+        return InsertResult(InsertStatus.DUPLICATE)
+    cursor = await conn.execute(
+        "SELECT COUNT(*) FROM memory_candidates WHERE subject_person_id = ? "
+        "AND status IN ('proposed', 'offered')",
+        (subject_person_id,),
+    )
+    live_row = await cursor.fetchone()
+    await cursor.close()
+    if live_row is not None and int(live_row[0]) >= settings.memory_candidate_max_live:
+        return InsertResult(InsertStatus.CAPACITY)
+    cursor = await conn.execute(
+        "INSERT INTO memory_candidates (subject_person_id, asserted_by_person_id, predicate, "
+        "value_text, value_key, status, channel, source_correlation_id, proposed_at, expires_at) "
+        "VALUES (?, ?, ?, ?, ?, 'proposed', ?, ?, ?, ?)",
+        (
+            subject_person_id,
+            asserted_by_person_id,
+            proposal.predicate,
+            proposal.value_text,
+            proposal.value_key,
+            channel.value,
+            str(correlation_id),
+            iso_utc(now),
+            iso_utc(now + timedelta(seconds=settings.memory_candidate_ttl_seconds)),
+        ),
+    )
+    candidate_id = cursor.lastrowid
+    await cursor.close()
+    if candidate_id is None:
+        raise RuntimeError("INSERT into memory_candidates returned no lastrowid")
+    return InsertResult(InsertStatus.INSERTED, int(candidate_id))
+
+
+async def get_candidate(candidate_id: int) -> Candidate | None:
+    """Return one candidate by id, with no policy applied (callers filter by subject).
+
+    Args:
+        candidate_id: The row id.
+
+    Returns:
+        The candidate, or ``None`` when it does not exist.
+    """
+    cursor = await db.get_conn().execute(
+        f"SELECT {_COLUMNS} FROM memory_candidates WHERE id = ?",  # noqa: S608
+        (candidate_id,),
+    )
+    row = await cursor.fetchone()
+    await cursor.close()
+    return _from_row(tuple(row)) if row is not None else None
+
+
+async def get_candidate_in_transaction(
+    conn: aiosqlite.Connection, candidate_id: int
+) -> Candidate | None:
+    """Return one candidate as seen by an open transaction.
+
+    Args:
+        conn: The connection of an open ``db.transaction()``.
+        candidate_id: The row id.
+
+    Returns:
+        The candidate, or ``None`` when it does not exist.
+    """
+    cursor = await conn.execute(
+        f"SELECT {_COLUMNS} FROM memory_candidates WHERE id = ?",  # noqa: S608
+        (candidate_id,),
+    )
+    row = await cursor.fetchone()
+    await cursor.close()
+    return _from_row(tuple(row)) if row is not None else None
+
+
+async def mark_offered(
+    candidate_id: int, subject_person_id: int, *, correlation_id: UUID, now: datetime
+) -> bool:
+    """Move one ``proposed`` candidate to ``offered`` (compare-and-set).
+
+    Args:
+        candidate_id: The candidate.
+        subject_person_id: Whose it is; another person's id changes nothing.
+        correlation_id: The turn that spoke the offer.
+        now: The caller's clock reading.
+
+    Returns:
+        ``True`` when this call made the transition. ``False`` when the candidate is not
+        ``proposed``, lapsed, belongs to someone else, has used every offer, or the
+        kill-switch is off.
+    """
+    if not settings.memory_candidates_enabled:
+        return False
+    async with db.transaction() as conn:
+        scrubbed = await run_housekeeping(conn, now)
+        cursor = await conn.execute(
+            "UPDATE memory_candidates SET status = 'offered', offered_at = ?, "
+            "offer_correlation_id = ?, offer_count = offer_count + 1 "
+            "WHERE id = ? AND subject_person_id = ? AND status = 'proposed' AND offer_count < ?",
+            (
+                iso_utc(now),
+                str(correlation_id),
+                candidate_id,
+                subject_person_id,
+                settings.memory_candidate_max_offers,
+            ),
+        )
+        changed = await _rowcount(cursor)
+    await checkpoint_after_scrub(scrubbed)
+    return changed == 1
+
+
+async def resolve_candidate_in_transaction(
+    conn: aiosqlite.Connection,
+    candidate_id: int,
+    subject_person_id: int,
+    *,
+    to: CandidateStatus,
+    correlation_id: UUID,
+    now: datetime,
+    promoted_fact_id: int | None = None,
+) -> bool:
+    """Resolve one ``offered`` candidate and erase its value, inside an open transaction.
+
+    Args:
+        conn: The connection of an open ``db.transaction()``.
+        candidate_id: The candidate.
+        subject_person_id: Whose it is; another person's id changes nothing.
+        to: ``CONFIRMED`` or ``REJECTED``.
+        correlation_id: The turn that resolved it.
+        now: The caller's clock reading.
+        promoted_fact_id: The canonical fact it became, for ``CONFIRMED``.
+
+    Returns:
+        ``True`` when this call resolved it; ``False`` when it was not ``offered`` for that
+        subject (the compare-and-set lost, or someone else's candidate).
+
+    Raises:
+        ValueError: If *to* is not a resolution.
+    """
+    if to not in {CandidateStatus.CONFIRMED, CandidateStatus.REJECTED}:
+        raise ValueError("a candidate resolves to confirmed or rejected only")
+    cursor = await conn.execute(
+        "UPDATE memory_candidates SET status = ?, value_text = NULL, value_key = NULL, "
+        "resolved_at = ?, resolution_correlation_id = ?, promoted_fact_id = ? "
+        "WHERE id = ? AND subject_person_id = ? AND status = 'offered'",
+        (
+            to.value,
+            iso_utc(now),
+            str(correlation_id),
+            promoted_fact_id,
+            candidate_id,
+            subject_person_id,
+        ),
+    )
+    return await _rowcount(cursor) == 1
+
+
+async def resolve_candidate(
+    candidate_id: int,
+    subject_person_id: int,
+    *,
+    to: CandidateStatus,
+    correlation_id: UUID,
+    now: datetime,
+) -> bool:
+    """Resolve one ``offered`` candidate in its own transaction and checkpoint the log.
+
+    Args:
+        candidate_id: The candidate.
+        subject_person_id: Whose it is.
+        to: ``CONFIRMED`` or ``REJECTED``.
+        correlation_id: The turn that resolved it.
+        now: The caller's clock reading.
+
+    Returns:
+        ``True`` when this call resolved it; ``False`` otherwise or with the kill-switch off.
+    """
+    if not settings.memory_candidates_enabled:
+        return False
+    async with db.transaction() as conn:
+        scrubbed = await run_housekeeping(conn, now)
+        resolved = await resolve_candidate_in_transaction(
+            conn, candidate_id, subject_person_id, to=to, correlation_id=correlation_id, now=now
+        )
+    await checkpoint_after_scrub(scrubbed + int(resolved))
+    return resolved
+
+
+async def void_live_candidates(now: datetime) -> int:
+    """Void every live candidate (start-up with the kill-switch off).
+
+    Args:
+        now: The caller's clock reading.
+
+    Returns:
+        How many candidates were voided.
+    """
+    async with db.transaction() as conn:
+        cursor = await conn.execute(VOID_LIVE_SQL, (iso_utc(now),))
+        voided = await _rowcount(cursor)
+    await checkpoint_after_scrub(voided)
+    return voided
+
+
+async def reset_for_startup(now: datetime, *, enabled: bool) -> None:
+    """Make the store consistent with a process that has just started (ADR 0021 decision 6).
+
+    With the switch off every live candidate is voided. With it on, an ``offered``
+    candidate returns to ``proposed`` (whatever was said in the previous process is gone and
+    the answer window cannot be trusted) and lapsed candidates are expired. Runs before any
+    request is served.
+
+    Args:
+        now: The caller's clock reading.
+        enabled: ``MEMORY_CANDIDATES_ENABLED`` as the application was configured (the lifespan
+            reads it from the app's own settings, not from the module global).
+    """
+    if not enabled:
+        voided = await void_live_candidates(now)
+        logger.info("Candidates voided at start-up: %d", voided)
+        return
+    async with db.transaction() as conn:
+        cursor = await conn.execute(
+            "UPDATE memory_candidates SET status = 'proposed', offered_at = NULL, "
+            "offer_correlation_id = NULL WHERE status = 'offered'"
+        )
+        await cursor.close()
+        scrubbed = await expire_lapsed_in_transaction(conn, now)
+    await checkpoint_after_scrub(scrubbed)
```

- [ ] **Step 4: Run to see them pass, then lint and types.**
- [ ] **Step 5: Commit** `feat(server): add the candidate store (plan 0062)`; check `git log -1`.

---

## Task 7: Literal facts carry classification and confirmation

**Files:**
- Modify: `server/src/server/memory/relational_v4.py`
- Test: modified `tests/integration/test_memory_v4_repository.py`

**Interfaces:**
- Produces: `LiteralFactV4.confirmed_by_entity_id: int | None = None` and `.confirmed_at: str | None
  = None` (defaulted, so older constructions keep working); `assert_literal_fact(..., visibility:
  str | None = None, sensitivity: str | None = None, confirmed_by_entity_id: int | None = None,
  confirmed_at: str | None = None, manage_transaction: bool = True)`. The registry defaults are used
  when the caller does not choose; a bad visibility is refused by the schema.

- [ ] **Step 1: Write the failing tests** (the fifth, a caller-owned transaction, is green on
  arrival by design: it pins the existing behaviour the writer relies on):

```diff
diff --git a/tests/integration/test_memory_v4_repository.py b/tests/integration/test_memory_v4_repository.py
--- a/tests/integration/test_memory_v4_repository.py
+++ b/tests/integration/test_memory_v4_repository.py
@@ -194,3 +194,99 @@ async def test_relation_target_filter_returns_only_active_inverse_matches(

     assert {relation.source_entity_id for relation in relations} == {maximo_id, sofia_id}
     assert {relation.target_entity_id for relation in relations} == {felipe_id}
+
+
+@pytest.mark.integration
+async def test_a_literal_carries_who_confirmed_it_and_when(household_db: None) -> None:
+    """ADR 0021 decision 8: the writer states the confirmation, the repository stores it."""
+    owner_id = await upsert_entity(name="Felipe", type="person")
+    likes = _predicate("likes")
+
+    fact = await assert_literal_fact(
+        subject_entity_id=owner_id,
+        definition=likes,
+        value="el mate",
+        confirmed_by_entity_id=owner_id,
+        confirmed_at="2026-10-14T10:00:00.000000+00:00",
+    )
+
+    assert fact.confirmed_by_entity_id == owner_id
+    assert fact.confirmed_at == "2026-10-14T10:00:00.000000+00:00"
+    stored = await get_literal_fact(fact.id)
+    assert stored == fact
+
+
+@pytest.mark.integration
+async def test_an_unconfirmed_literal_has_no_confirmation(household_db: None) -> None:
+    owner_id = await upsert_entity(name="Felipe", type="person")
+
+    fact = await assert_literal_fact(
+        subject_entity_id=owner_id, definition=_predicate("likes"), value="cafe"
+    )
+
+    assert fact.confirmed_by_entity_id is None
+    assert fact.confirmed_at is None
+
+
+@pytest.mark.integration
+async def test_the_caller_chooses_visibility_and_sensitivity_without_changing_the_registry(
+    household_db: None,
+) -> None:
+    """The registry default is the household reader's read contract and does not move."""
+    owner_id = await upsert_entity(name="Felipe", type="person")
+    likes = _predicate("likes")
+    default_visibility = likes.default_visibility
+
+    explicit = await assert_literal_fact(
+        subject_entity_id=owner_id,
+        definition=likes,
+        value="el mate",
+        visibility="personal",
+        sensitivity="private",
+    )
+    implicit = await assert_literal_fact(
+        subject_entity_id=owner_id, definition=likes, value="el cafe"
+    )
+
+    assert (explicit.visibility, explicit.sensitivity) == ("personal", "private")
+    assert (implicit.visibility, implicit.sensitivity) == (default_visibility, "normal")
+    assert _predicate("likes").default_visibility == default_visibility == "household"
+
+
+@pytest.mark.integration
+async def test_an_unknown_visibility_is_refused_by_the_schema(household_db: None) -> None:
+    owner_id = await upsert_entity(name="Felipe", type="person")
+
+    with pytest.raises(sqlite3.IntegrityError):
+        await assert_literal_fact(
+            subject_entity_id=owner_id,
+            definition=_predicate("likes"),
+            value="el mate",
+            visibility="everyone",
+        )
+
+
+async def _write_inside_a_failing_transaction(owner_id: int, likes: PredicateDefinition) -> None:
+    """Write a literal into a caller-owned transaction, then fail the caller."""
+    async with db.transaction():
+        await assert_literal_fact(
+            subject_entity_id=owner_id,
+            definition=likes,
+            value="el mate",
+            manage_transaction=False,
+        )
+        raise RuntimeError("caller rolled back")
+
+
+@pytest.mark.integration
+async def test_a_caller_owned_transaction_neither_opens_nor_commits_its_own(
+    household_db: None,
+) -> None:
+    """`manage_transaction=False` joins the caller's `db.transaction()` (and is not reentrant)."""
+    owner_id = await upsert_entity(name="Felipe", type="person")
+    likes = _predicate("likes")
+
+    with pytest.raises(RuntimeError, match="caller rolled back"):
+        await _write_inside_a_failing_transaction(owner_id, likes)
+
+    assert await get_active_literal_facts(subject_entity_id=owner_id, definition=likes) == []
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/integration/test_memory_v4_repository.py -q -p no:cacheprovider`
  Expected RED: 4 failures, `TypeError: assert_literal_fact() got an unexpected keyword argument`.
- [ ] **Step 3: Implement:**

```diff
diff --git a/server/src/server/memory/relational_v4.py b/server/src/server/memory/relational_v4.py
--- a/server/src/server/memory/relational_v4.py
+++ b/server/src/server/memory/relational_v4.py
@@ -7,6 +7,7 @@ plan owns any production reader or writer cutover.

 from __future__ import annotations

+from dataclasses import dataclass
 from enum import StrEnum
 from typing import TYPE_CHECKING

@@ -54,6 +55,10 @@ class LiteralFactV4(BaseModel):
     sensitivity: str
     superseded_at: str | None
     superseded_by: int | None
+    # Who confirmed the fact and when (ADR 0021): set by the one candidate writer, absent for
+    # every fact that was never a candidate. Defaulted so older constructions keep working.
+    confirmed_by_entity_id: int | None = None
+    confirmed_at: str | None = None


 class EntityRelationV4(BaseModel):
@@ -170,6 +175,8 @@ def _literal_from_row(row: SqlRow) -> LiteralFactV4:
         sensitivity=_required_text(row[11]),
         superseded_at=_optional_text(row[12]),
         superseded_by=_optional_int(row[13]),
+        confirmed_by_entity_id=_optional_int(row[14]),
+        confirmed_at=_optional_text(row[15]),
     )


@@ -195,7 +202,8 @@ def _relation_from_row(row: SqlRow) -> EntityRelationV4:

 _LITERAL_COLUMNS = """
     id, subject_entity_id, predicate, value_text, confidence, source_memory_id, asserted_at,
-    valid_from, valid_to, lifecycle, visibility, sensitivity, superseded_at, superseded_by
+    valid_from, valid_to, lifecycle, visibility, sensitivity, superseded_at, superseded_by,
+    confirmed_by_entity_id, confirmed_at
 """
 _RELATION_COLUMNS = """
     id, source_entity_id, predicate, target_entity_id, confidence, source_memory_id, asserted_at,
@@ -294,14 +302,27 @@ async def assert_literal_fact(
     confidence: float = 0.9,
     source_memory_id: int | None = None,
     asserted_at: str | None = None,
+    visibility: str | None = None,
+    sensitivity: str | None = None,
+    confirmed_by_entity_id: int | None = None,
+    confirmed_at: str | None = None,
     manage_transaction: bool = True,
 ) -> LiteralFactV4:
     """Persist a typed literal while applying its registry lifecycle rule.

     The function has no runtime authorization semantics. It is limited to v4
     foundation and receives a previously resolved closed-registry definition.
-    ``manage_transaction=False`` is reserved for the local legacy migration,
-    which owns one transaction for a record and its migration ledger entry.
+
+    ``visibility`` and ``sensitivity`` default to the registry's values, which are the
+    household reader's read contract; a caller that stores something else (the candidate
+    writer stores the owner's own ``personal`` data) states it explicitly and the registry
+    does not move. ``confirmed_by_entity_id`` and ``confirmed_at`` record who confirmed the
+    fact and when.
+
+    ``manage_transaction=False`` joins a transaction the caller already owns (the legacy
+    migration, which commits a record with its ledger entry, and the candidate writer, which
+    commits a fact with its candidate's resolution). The call then neither opens, commits
+    nor rolls back, and ``db.transaction()`` is not reentrant, so the caller must not nest.
     """
     await _validate_literal_subject(subject_entity_id, definition)
     normalized_value = normalize_literal(definition, value)
@@ -310,6 +331,12 @@ async def assert_literal_fact(
     if not 0.0 <= confidence <= 1.0:
         raise ValueError("confidence must be between 0 and 1")

+    stamp = _LiteralStamp(
+        visibility=visibility or definition.default_visibility,
+        sensitivity=sensitivity or definition.default_sensitivity,
+        confirmed_by_entity_id=confirmed_by_entity_id,
+        confirmed_at=confirmed_at,
+    )
     if manage_transaction:
         async with db.transaction() as conn:
             literal_fact_id = await _insert_literal_fact(
@@ -320,11 +347,11 @@ async def assert_literal_fact(
                 confidence=confidence,
                 source_memory_id=source_memory_id,
                 asserted_at=asserted_at,
+                stamp=stamp,
             )
     else:
-        # Reserved for the local legacy migration, which owns one transaction
-        # for a record and its migration ledger entry — this call must not
-        # open (or commit/roll back) a transaction of its own.
+        # The caller owns one transaction (a legacy-migration record with its ledger entry, or
+        # a candidate promotion): this call must not open, commit or roll back one of its own.
         literal_fact_id = await _insert_literal_fact(
             get_conn(),
             subject_entity_id=subject_entity_id,
@@ -333,6 +360,7 @@ async def assert_literal_fact(
             confidence=confidence,
             source_memory_id=source_memory_id,
             asserted_at=asserted_at,
+            stamp=stamp,
         )
     result = await get_literal_fact(literal_fact_id)
     if result is None:
@@ -340,6 +368,16 @@ async def assert_literal_fact(
     return result


+@dataclass(frozen=True)
+class _LiteralStamp:
+    """The classification and confirmation one literal is stored with."""
+
+    visibility: str
+    sensitivity: str
+    confirmed_by_entity_id: int | None
+    confirmed_at: str | None
+
+
 async def _insert_literal_fact(
     conn: aiosqlite.Connection,
     *,
@@ -349,14 +387,15 @@ async def _insert_literal_fact(
     confidence: float,
     source_memory_id: int | None,
     asserted_at: str | None,
+    stamp: _LiteralStamp,
 ) -> int:
     """Issue the INSERT (and same-predicate supersede) on an active connection."""
     cursor = await conn.execute(
         "INSERT INTO literal_facts_v4 "
         "(subject_entity_id, predicate, value_text, confidence, source_memory_id, asserted_at, "
-        "visibility, sensitivity, valid_from) "
+        "visibility, sensitivity, valid_from, confirmed_by_entity_id, confirmed_at) "
         "VALUES (?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?, ?, "
-        "CASE WHEN ? THEN COALESCE(?, datetime('now')) ELSE NULL END)",
+        "CASE WHEN ? THEN COALESCE(?, datetime('now')) ELSE NULL END, ?, ?)",
         (
             subject_entity_id,
             definition.canonical_id,
@@ -364,10 +403,12 @@ async def _insert_literal_fact(
             confidence,
             source_memory_id,
             asserted_at,
-            definition.default_visibility,
-            definition.default_sensitivity,
+            stamp.visibility,
+            stamp.sensitivity,
             definition.temporal,
             asserted_at,
+            stamp.confirmed_by_entity_id,
+            stamp.confirmed_at,
         ),
     )
     if cursor.lastrowid is None:
```

- [ ] **Step 4: Run to see them pass, then lint and types.** Also
  `uv run pytest tests/integration/test_memory_v4_migration.py tests/integration/test_policy_gated_v4_reader.py tests/integration/test_personal_setup.py -q -p no:cacheprovider`.
- [ ] **Step 5: Commit** `feat(server): record who confirmed a literal fact (plan 0062)`; check `git log -1`.

---

## Task 8: The face-and-voice actor and the enrollment reader

**Files:**
- Create: `server/src/server/cognition/strong_actor.py`, `server/src/server/memory/enrollment.py`
- Modify: `server/src/server/cognition/identity_fusion.py`
- Test: new `tests/integration/test_memory_enrollment.py`, `tests/unit/test_strong_actor.py`

**Interfaces:**
- Produces: `identity_fusion.fuse_face_and_voice(face_context, voice_context, *, clock) ->
  ActivePersonContext | None` (the rule of `_with_voice`, extracted; `_with_voice` now calls it);
  `strong_actor.is_face_actor(actor)`, `.is_face_and_voice_actor(actor)` and
  `async .verify_face_and_voice(actor, *, wav_bytes, event, build_speaker=..., clock=...)`;
  `memory.enrollment.is_enrolled_for_strong(person_id)`.

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/tests/integration/test_memory_enrollment.py b/tests/integration/test_memory_enrollment.py
new file mode 100644
--- /dev/null
+++ b/tests/integration/test_memory_enrollment.py
@@ -0,0 +1,60 @@
+"""The composite "enrolled for strong" reader (ADR 0021 decision 3) over a temporary SQLite."""
+
+from __future__ import annotations
+
+from typing import TYPE_CHECKING
+
+import pytest
+from server.memory.biometric_consent import (
+    grant_face_consent,
+    revoke_face_consent,
+)
+from server.memory.declarative import upsert_entity
+from server.memory.enrollment import is_enrolled_for_strong
+from server.memory.voice_consent import grant_voice_consent, revoke_voice_consent
+from server.settings import settings
+
+from server import db
+
+if TYPE_CHECKING:
+    from collections.abc import AsyncIterator
+    from pathlib import Path
+
+pytestmark = pytest.mark.integration
+
+
+@pytest.fixture
+async def person(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
+    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "enrollment.db")
+    db._conn = None
+    await db.open_db()
+    await db.run_migrations()
+    yield await upsert_entity(name="Canary Owner", type="person")
+    await db.close_db()
+    db._conn = None
+
+
+async def test_nothing_enrolled_is_not_enrolled(person: int) -> None:
+    assert not await is_enrolled_for_strong(person)
+
+
+async def test_face_alone_or_voice_alone_is_not_enough(person: int) -> None:
+    await grant_face_consent(person)
+    assert not await is_enrolled_for_strong(person)
+
+    await revoke_face_consent(person)
+    await grant_voice_consent(person)
+    assert not await is_enrolled_for_strong(person)
+
+
+async def test_both_consents_enrol_and_revoking_either_unenrols(person: int) -> None:
+    await grant_face_consent(person)
+    await grant_voice_consent(person)
+    assert await is_enrolled_for_strong(person)
+
+    await revoke_voice_consent(person)
+    assert not await is_enrolled_for_strong(person)
+
+    await grant_voice_consent(person)
+    await revoke_face_consent(person)
+    assert not await is_enrolled_for_strong(person)
diff --git a/tests/unit/test_strong_actor.py b/tests/unit/test_strong_actor.py
new file mode 100644
--- /dev/null
+++ b/tests/unit/test_strong_actor.py
@@ -0,0 +1,260 @@
+"""Unit tests for the face-and-voice actor (ADR 0021 decision 3): never a face alone, never a token."""
+
+from datetime import UTC, datetime, timedelta
+from typing import cast
+from uuid import UUID, uuid4
+
+import pytest
+from server.cognition.identity import (
+    ActivePersonContext,
+    ActivePersonStatus,
+    HouseholdRole,
+    IdentityAssurance,
+    IdentityEvidence,
+    IdentityEvidenceSource,
+    PersonRecord,
+    resolve_active_person,
+)
+from server.cognition.models import CognitiveEvent, Confidence, ConfidenceBasis
+from server.cognition.response_plan import TextTurnPayload
+from server.cognition.speaker_authentication import SpeakerRequestResolver, SpeakerVerdict
+from server.cognition.strong_actor import (
+    is_face_actor,
+    is_face_and_voice_actor,
+    verify_face_and_voice,
+)
+from server.settings import settings
+
+pytestmark = pytest.mark.unit
+
+_NOW = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
+_OWNER_ID = 7
+_OTHER_ID = 8
+_WAV = b"RIFF-canary-clip"
+
+
+def _evidence(
+    source: IdentityEvidenceSource, person_id: int = _OWNER_ID, *, scope: str | None = None
+) -> IdentityEvidence:
+    return IdentityEvidence(
+        evidence_id=uuid4(),
+        source=source,
+        candidate_person_id=person_id,
+        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
+        observed_at=_NOW - timedelta(seconds=1),
+        reference="canary",
+        grant_scope=scope,
+    )
+
+
+def _resolve(*items: IdentityEvidence) -> ActivePersonContext:
+    people = {
+        _OWNER_ID: PersonRecord(person_id=_OWNER_ID, display_name="Canary", entity_type="person"),
+        _OTHER_ID: PersonRecord(person_id=_OTHER_ID, display_name="Other", entity_type="person"),
+    }
+    return resolve_active_person(
+        evidence=tuple(items),
+        lookup_person=people.get,
+        lookup_role=lambda _pid: HouseholdRole.OWNER,
+        clock=lambda: _NOW,
+    )
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
+        correlation_id=UUID(int=9),
+        causation_id=None,
+        subject_id=None,
+        payload=TextTurnPayload(message="canary", conversation_id="canary"),
+    )
+
+
+def _face_actor() -> ActivePersonContext:
+    return _resolve(_evidence(IdentityEvidenceSource.FACE))
+
+
+class _Speaker:
+    def __init__(self, verdict: SpeakerVerdict, *items: IdentityEvidence) -> None:
+        self.last_verdict = verdict
+        self._items = items
+
+    async def resolve_actor(self, event: CognitiveEvent[TextTurnPayload]) -> ActivePersonContext:
+        return ActivePersonContext(
+            person_id=None,
+            display_name=None,
+            status=ActivePersonStatus.UNKNOWN,
+            confidence=Confidence(
+                score=0.0, basis=ConfidenceBasis.NOT_APPLICABLE, calibrated=False
+            ),
+            role=HouseholdRole.UNKNOWN,
+            evidence=self._items,
+            resolved_at=event.occurred_at,
+        )
+
+
+class _Builder:
+    """Records how the speaker resolver was built and hands back a scripted one."""
+
+    def __init__(self, speaker: _Speaker) -> None:
+        self.speaker = speaker
+        self.calls: list[tuple[bytes, int]] = []
+
+    def __call__(self, wav_bytes: bytes, owner_person_id: int) -> SpeakerRequestResolver:
+        self.calls.append((wav_bytes, owner_person_id))
+        return cast("SpeakerRequestResolver", self.speaker)
+
+
+@pytest.fixture(autouse=True)
+def _speaker_evidence_on(monkeypatch: pytest.MonkeyPatch) -> None:
+    monkeypatch.setattr(settings, "speaker_authentication_enabled", True)
+
+
+def _verified() -> _Builder:
+    return _Builder(_Speaker(SpeakerVerdict.VERIFIED, _evidence(IdentityEvidenceSource.VOICE)))
+
+
+def test_a_face_alone_is_a_face_actor_and_not_a_face_and_voice_actor() -> None:
+    actor = _face_actor()
+
+    assert is_face_actor(actor)
+    assert not is_face_and_voice_actor(actor)
+    assert actor.assurance is IdentityAssurance.BASIC
+
+
+def test_face_and_voice_of_the_same_person_is_the_composite() -> None:
+    actor = _resolve(
+        _evidence(IdentityEvidenceSource.FACE), _evidence(IdentityEvidenceSource.VOICE)
+    )
+
+    assert actor.assurance is IdentityAssurance.STRONG
+    assert is_face_and_voice_actor(actor)
+
+
+def test_a_token_reaches_strong_but_is_neither_face_actor_nor_composite() -> None:
+    token = _resolve(
+        _evidence(IdentityEvidenceSource.LOCAL_UNLOCK, scope="personal_protected_read")
+    )
+
+    assert token.assurance is IdentityAssurance.STRONG
+    assert not is_face_actor(token)
+    assert not is_face_and_voice_actor(token)
+
+
+def test_a_token_next_to_face_and_voice_still_refuses_the_composite() -> None:
+    actor = _resolve(
+        _evidence(IdentityEvidenceSource.FACE),
+        _evidence(IdentityEvidenceSource.VOICE),
+        _evidence(IdentityEvidenceSource.LOCAL_UNLOCK, scope="personal_protected_read"),
+    )
+
+    assert actor.assurance is IdentityAssurance.STRONG
+    assert not is_face_actor(actor)
+    assert not is_face_and_voice_actor(actor)
+
+
+def test_a_manual_session_is_not_a_face_actor() -> None:
+    assert not is_face_actor(_resolve(_evidence(IdentityEvidenceSource.MANUAL)))
+
+
+def test_voice_alone_and_an_unknown_actor_are_not_actors_at_all() -> None:
+    voice_only = _resolve(_evidence(IdentityEvidenceSource.VOICE))
+    unknown = _resolve()
+
+    assert voice_only.status is ActivePersonStatus.PROBABLE
+    for actor in (voice_only, unknown):
+        assert not is_face_actor(actor)
+        assert not is_face_and_voice_actor(actor)
+
+
+def test_a_voice_that_names_another_person_is_not_the_composite() -> None:
+    actor = _resolve(
+        _evidence(IdentityEvidenceSource.FACE, _OWNER_ID),
+        _evidence(IdentityEvidenceSource.VOICE, _OTHER_ID),
+    )
+
+    assert actor.status is ActivePersonStatus.AMBIGUOUS
+    assert not is_face_and_voice_actor(actor)
+
+
+async def test_a_verified_voice_raises_the_face_actor_to_the_composite() -> None:
+    builder = _verified()
+
+    fused = await verify_face_and_voice(
+        _face_actor(), wav_bytes=_WAV, event=_event(), build_speaker=builder
+    )
+
+    assert fused is not None
+    assert is_face_and_voice_actor(fused)
+    assert fused.person_id == _OWNER_ID
+    assert builder.calls == [(_WAV, _OWNER_ID)]
+
+
+@pytest.mark.parametrize("verdict", [SpeakerVerdict.UNKNOWN, SpeakerVerdict.UNAVAILABLE])
+async def test_a_voice_that_is_not_verified_gives_nothing(verdict: SpeakerVerdict) -> None:
+    builder = _Builder(_Speaker(verdict, _evidence(IdentityEvidenceSource.VOICE)))
+
+    assert (
+        await verify_face_and_voice(
+            _face_actor(), wav_bytes=_WAV, event=_event(), build_speaker=builder
+        )
+        is None
+    )
+
+
+async def test_verified_evidence_of_another_person_gives_nothing() -> None:
+    builder = _Builder(
+        _Speaker(SpeakerVerdict.VERIFIED, _evidence(IdentityEvidenceSource.VOICE, _OTHER_ID))
+    )
+
+    assert (
+        await verify_face_and_voice(
+            _face_actor(), wav_bytes=_WAV, event=_event(), build_speaker=builder
+        )
+        is None
+    )
+
+
+@pytest.mark.parametrize("wav", [None, b""])
+async def test_no_clip_means_no_voice_check_at_all(wav: bytes | None) -> None:
+    builder = _verified()
+
+    result = await verify_face_and_voice(
+        _face_actor(), wav_bytes=wav, event=_event(), build_speaker=builder
+    )
+
+    assert result is None
+    assert builder.calls == []
+
+
+async def test_speaker_evidence_off_means_no_voice_check_at_all(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    monkeypatch.setattr(settings, "speaker_authentication_enabled", False)
+    builder = _verified()
+
+    result = await verify_face_and_voice(
+        _face_actor(), wav_bytes=_WAV, event=_event(), build_speaker=builder
+    )
+
+    assert result is None
+    assert builder.calls == []
+
+
+async def test_a_token_actor_never_reaches_the_voice_check() -> None:
+    builder = _verified()
+    token = _resolve(
+        _evidence(IdentityEvidenceSource.LOCAL_UNLOCK, scope="personal_protected_read")
+    )
+
+    result = await verify_face_and_voice(
+        token, wav_bytes=_WAV, event=_event(), build_speaker=builder
+    )
+
+    assert result is None
+    assert builder.calls == []
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_strong_actor.py tests/integration/test_memory_enrollment.py -q -p no:cacheprovider`
  Expected RED: `ModuleNotFoundError` for `server.cognition.strong_actor` and `server.memory.enrollment`.
- [ ] **Step 3: Implement:**

```diff
diff --git a/server/src/server/cognition/identity_fusion.py b/server/src/server/cognition/identity_fusion.py
--- a/server/src/server/cognition/identity_fusion.py
+++ b/server/src/server/cognition/identity_fusion.py
@@ -54,7 +54,12 @@ logger = logging.getLogger(__name__)
 # The identity store failing is not evidence of anything: the face then says nothing.
 _STORE_ERRORS = (BrainMemoryError, aiosqlite.Error)

-__all__ = ["FusedIdentityResolver", "FusionReason", "build_fused_identity_resolver"]
+__all__ = [
+    "FusedIdentityResolver",
+    "FusionReason",
+    "build_fused_identity_resolver",
+    "fuse_face_and_voice",
+]

 type Clock = Callable[[], datetime]
 type SpeakerFactory = Callable[[int], SpeakerRequestResolver]
@@ -246,27 +251,53 @@ class FusedIdentityResolver:
         if speaker.last_verdict is SpeakerVerdict.UNAVAILABLE:
             self.last_reason = FusionReason.BACKEND_UNAVAILABLE
             return face_context
-        voice_evidence = tuple(
-            item for item in voice_context.evidence if item.candidate_person_id == owner_id
-        )
-        if speaker.last_verdict is not SpeakerVerdict.VERIFIED or not voice_evidence:
+        if speaker.last_verdict is not SpeakerVerdict.VERIFIED:
             return face_context
-        person = PersonRecord(
-            person_id=owner_id, display_name=face_context.display_name or "", entity_type="person"
-        )
-        fused = resolve_active_person(
-            evidence=face_context.evidence + voice_evidence,
-            lookup_person=lambda person_id: person if person_id == owner_id else None,
-            lookup_role=lambda _person_id: face_context.role,
-            clock=self._clock,
-        )
-        if fused.assurance is not IdentityAssurance.STRONG:
+        fused = fuse_face_and_voice(face_context, voice_context, clock=self._clock)
+        if fused is None:
             return face_context
         self.source = "face_voice"
         self.last_reason = FusionReason.FACE_AND_VOICE
         return fused


+def fuse_face_and_voice(
+    face_context: ActivePersonContext, voice_context: ActivePersonContext, *, clock: Clock
+) -> ActivePersonContext | None:
+    """Fuse an identified face with voice evidence of the same person, or say it does not fuse.
+
+    The single place where the face and a verified voice become `strong` (ADR 0016 §2); the
+    fused resolver and the memory writer's background voice check both use it.
+
+    Args:
+        face_context: A context identified by the face.
+        voice_context: The speaker resolver's context, carrying its untrusted `VOICE` evidence.
+        clock: Source of the resolution timestamp.
+
+    Returns:
+        The fused context at assurance `strong`, or `None` when the face is not identified,
+        the voice evidence names nobody or another person, or the fusion is not `strong`.
+    """
+    owner_id = face_context.person_id
+    if owner_id is None:
+        return None
+    voice_evidence = tuple(
+        item for item in voice_context.evidence if item.candidate_person_id == owner_id
+    )
+    if not voice_evidence:
+        return None
+    person = PersonRecord(
+        person_id=owner_id, display_name=face_context.display_name or "", entity_type="person"
+    )
+    fused = resolve_active_person(
+        evidence=face_context.evidence + voice_evidence,
+        lookup_person=lambda person_id: person if person_id == owner_id else None,
+        lookup_role=lambda _person_id: face_context.role,
+        clock=clock,
+    )
+    return fused if fused.assurance is IdentityAssurance.STRONG else None
+
+
 def build_fused_identity_resolver(
     pin: OwnerRequestResolver, *, frame: bytes | None, wav_bytes: bytes | None
 ) -> FusedIdentityResolver:
diff --git a/server/src/server/cognition/strong_actor.py b/server/src/server/cognition/strong_actor.py
new file mode 100644
--- /dev/null
+++ b/server/src/server/cognition/strong_actor.py
@@ -0,0 +1,128 @@
+"""The face-and-voice actor the memory writer demands (ADR 0021 decision 3).
+
+Pipec's rule: nothing private is written on the strength of a face alone. In CM-3a a
+candidate, a spoken value, an answer and a promotion all need the face **and** the voice of
+the same person, verified on that turn's own clip, and never a PIN token.
+
+A generic turn is identified by its face (ADR 0020 §1) before anything is generated. This
+module takes that face-identified actor and, in the background, runs only the voice half of the
+fused resolution for the person the face named: the face is not computed a second time.
+
+Audio contract: every clip is WAV, 16 000 Hz, mono, signed int16.
+"""
+
+from __future__ import annotations
+
+from collections.abc import Callable
+import logging
+from typing import TYPE_CHECKING
+
+from server.cognition.clock import utc_now
+from server.cognition.identity import (
+    ActivePersonContext,
+    ActivePersonStatus,
+    IdentityAssurance,
+    IdentityEvidenceSource,
+)
+from server.cognition.identity_fusion import fuse_face_and_voice
+from server.cognition.speaker_authentication import (
+    SpeakerRequestResolver,
+    SpeakerVerdict,
+    build_default_speaker_resolver,
+)
+from server.settings import settings
+
+if TYPE_CHECKING:
+    from datetime import datetime
+
+    from server.cognition.models import CognitiveEvent
+    from server.cognition.response_plan import TextTurnPayload
+
+logger = logging.getLogger(__name__)
+
+__all__ = ["is_face_actor", "is_face_and_voice_actor", "verify_face_and_voice"]
+
+type SpeakerBuilder = Callable[[bytes, int], SpeakerRequestResolver]
+type Clock = Callable[[], datetime]
+
+
+def _sources_of(actor: ActivePersonContext) -> set[IdentityEvidenceSource]:
+    """Return the evidence sources that name the actor's own person id."""
+    return {item.source for item in actor.evidence if item.candidate_person_id == actor.person_id}
+
+
+def _identified_without_a_token(actor: ActivePersonContext) -> bool:
+    """Return whether the actor is an identified person and no token took part in it."""
+    return (
+        actor.status is ActivePersonStatus.IDENTIFIED
+        and actor.person_id is not None
+        and IdentityEvidenceSource.LOCAL_UNLOCK not in {item.source for item in actor.evidence}
+    )
+
+
+def is_face_actor(actor: ActivePersonContext) -> bool:
+    """Return whether *actor* was identified by its face and carries no token.
+
+    Args:
+        actor: A resolved actor.
+
+    Returns:
+        ``True`` for an identified person whose evidence includes their face and no
+        ``LOCAL_UNLOCK`` item. A token-identified actor, a manual one and an unknown one are
+        ``False``: a PIN grant proves the PIN, not the speaker (ADR 0008, ADR 0015).
+    """
+    return _identified_without_a_token(actor) and IdentityEvidenceSource.FACE in _sources_of(actor)
+
+
+def is_face_and_voice_actor(actor: ActivePersonContext) -> bool:
+    """Return whether *actor* is the composite the memory writer needs.
+
+    Args:
+        actor: A resolved actor.
+
+    Returns:
+        ``True`` only for an identified person at assurance ``strong`` whose evidence names
+        them by face **and** voice and carries no ``LOCAL_UNLOCK`` item (a token also reaches
+        ``strong``, so assurance alone does not say how it was reached).
+    """
+    return (
+        _identified_without_a_token(actor)
+        and actor.assurance is IdentityAssurance.STRONG
+        and {IdentityEvidenceSource.FACE, IdentityEvidenceSource.VOICE} <= _sources_of(actor)
+    )
+
+
+async def verify_face_and_voice(
+    actor: ActivePersonContext,
+    *,
+    wav_bytes: bytes | None,
+    event: CognitiveEvent[TextTurnPayload],
+    build_speaker: SpeakerBuilder = build_default_speaker_resolver,
+    clock: Clock = utc_now,
+) -> ActivePersonContext | None:
+    """Check the voice of the turn's own clip against the person the face named.
+
+    Args:
+        actor: The face-identified actor of the turn (never a token actor).
+        wav_bytes: The turn's own audio — WAV, 16 000 Hz, mono, int16 — or ``None``.
+        event: The turn's event; the speaker resolver stamps its evidence from it.
+        build_speaker: Composition seam for the speaker resolver; tests inject doubles.
+        clock: Source of the fusion timestamp.
+
+    Returns:
+        The actor fused at ``strong`` from face and voice, or ``None`` when speaker evidence is
+        off, there is no clip, the actor is not a face actor, or the voice was not verified
+        (not enrolled, no consent, a clip below the floor, another voice, a backend failure).
+    """
+    if not settings.speaker_authentication_enabled or not wav_bytes:
+        return None
+    if not is_face_actor(actor) or actor.person_id is None:
+        return None
+    speaker = build_speaker(wav_bytes, actor.person_id)
+    voice_context = await speaker.resolve_actor(event)
+    if speaker.last_verdict is not SpeakerVerdict.VERIFIED:
+        return None
+    fused = fuse_face_and_voice(actor, voice_context, clock=clock)
+    if fused is None or not is_face_and_voice_actor(fused):
+        return None
+    return fused
diff --git a/server/src/server/memory/enrollment.py b/server/src/server/memory/enrollment.py
new file mode 100644
--- /dev/null
+++ b/server/src/server/memory/enrollment.py
@@ -0,0 +1,31 @@
+"""Whether a person is enrolled for the strong (face and voice) path (ADR 0021 decision 3).
+
+The composite did not exist as one reader: the face keeps its consent in `face_consent_grants`
+and the voice in `voice_consent_grants`, each revoked (and purged) on its own. A candidate is
+written only while **both** are active, so this reader names the composite and is read again
+right before the store, after a model call that can take tens of seconds.
+"""
+
+from __future__ import annotations
+
+from server.memory.biometric_consent import has_active_face_consent
+from server.memory.voice_consent import has_active_voice_consent
+
+__all__ = ["is_enrolled_for_strong"]
+
+
+async def is_enrolled_for_strong(person_entity_id: int) -> bool:
+    """Return whether the person has an active face consent and an active voice consent.
+
+    Args:
+        person_entity_id: The person to check.
+
+    Returns:
+        ``True`` only when both grants are active (revoking either one purges its data).
+
+    Raises:
+        BrainMemoryError: If the database is unavailable.
+    """
+    return await has_active_face_consent(person_entity_id) and await has_active_voice_consent(
+        person_entity_id
+    )
```

- [ ] **Step 4: Run to see them pass, then lint and types.** The refactor must not move the existing
  fusion behaviour: also
  `uv run pytest tests/unit/test_identity_fusion.py tests/integration/test_identity_fusion_turn.py tests/integration/test_speaker_evidence_turn.py -q -p no:cacheprovider`.
- [ ] **Step 5: Commit** `feat(server): add the face-and-voice actor (plan 0062)`; check `git log -1`.

---

## Task 9: The candidate policy check

**Files:**
- Create: `server/src/server/memory/candidate_policy.py`
- Test: new `tests/unit/test_candidate_policy.py`; modified `tests/unit/test_architecture_guards.py`

**Interfaces:**
- Consumes: `evaluate_authorization`, `record_authorization_decision`, `is_face_and_voice_actor`.
- Produces: `CandidateStep` (`PROPOSE`, `READ`, `CONFIRM`), `PolicyOutcome(allowed, reason,
  policy_id)` and `async authorize_step(step, *, actor, subject_person_id, correlation_id, now,
  policy=..., audit=...)`. The request is `{personal}` × `{normal}`, consent `not_required`,
  targeting the **subject** so the policy's own-data rule fires. A weaker actor is refused before
  the policy is asked and is not audited (nothing was evaluated); a refusal by the policy is audited.
  `candidate_policy.py` joins `_ACTION_HOMES` of the architecture guard.

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/tests/unit/test_architecture_guards.py b/tests/unit/test_architecture_guards.py
--- a/tests/unit/test_architecture_guards.py
+++ b/tests/unit/test_architecture_guards.py
@@ -152,7 +152,11 @@ _LEGACY_MEMORY_ACTION_NAMES = frozenset(
         "export_household_data",
     }
 )
-_ACTION_HOMES = frozenset({"cognition/models.py", "cognition/authorization.py"})
+# The model and the policy, plus the one module that asks the policy about a candidate step
+# (Plan 0062): every other module reaches the actions through it.
+_ACTION_HOMES = frozenset(
+    {"cognition/models.py", "cognition/authorization.py", "memory/candidate_policy.py"}
+)
 _MEMORY_SCOPE_MEMBER_NAMES = frozenset({"PERSONAL_MEMORY_READ", "PERSONAL_MEMORY_FORGET"})
 _MEMORY_SCOPE_VALUES = frozenset({"personal_memory_read", "personal_memory_forget"})
 # Only the enum names its members. The policy table repeats the plain strings because
diff --git a/tests/unit/test_candidate_policy.py b/tests/unit/test_candidate_policy.py
new file mode 100644
--- /dev/null
+++ b/tests/unit/test_candidate_policy.py
@@ -0,0 +1,231 @@
+"""Unit tests for the candidate policy check (ADR 0021 decision 7): audit first, deny on doubt."""
+
+from datetime import UTC, datetime, timedelta
+from unittest.mock import AsyncMock, Mock
+from uuid import UUID, uuid4
+
+import pytest
+from server.cognition.authorization import (
+    AuthorizationRequest,
+    ConsentStatus,
+    DataSensitivity,
+    DataVisibility,
+    evaluate_authorization,
+)
+from server.cognition.identity import (
+    ActivePersonContext,
+    HouseholdRole,
+    IdentityEvidence,
+    IdentityEvidenceSource,
+    PersonRecord,
+    resolve_active_person,
+)
+from server.cognition.models import (
+    AuthorizationAction,
+    AuthorizationDecision,
+    Confidence,
+    ConfidenceBasis,
+)
+from server.memory.candidate_policy import CandidateStep, PolicyOutcome, authorize_step
+from server.memory.candidate_types import CandidateReason
+from server.settings import settings
+
+pytestmark = pytest.mark.unit
+
+_NOW = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
+_OWNER = 7
+_CORRELATION = UUID(int=77)
+
+
+def _evidence(source: IdentityEvidenceSource, *, scope: str | None = None) -> IdentityEvidence:
+    return IdentityEvidence(
+        evidence_id=uuid4(),
+        source=source,
+        candidate_person_id=_OWNER,
+        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
+        observed_at=_NOW - timedelta(seconds=1),
+        reference="canary",
+        expires_at=_NOW + timedelta(minutes=5) if scope else None,
+        grant_scope=scope,
+        grant_spent=bool(scope),
+    )
+
+
+def _actor(
+    *sources: IdentityEvidenceSource, role: HouseholdRole = HouseholdRole.OWNER
+) -> ActivePersonContext:
+    person = PersonRecord(person_id=_OWNER, display_name="Canary", entity_type="person")
+    return resolve_active_person(
+        evidence=tuple(
+            _evidence(s, scope="personal_protected_read")
+            if s is IdentityEvidenceSource.LOCAL_UNLOCK
+            else _evidence(s)
+            for s in sources
+        ),
+        lookup_person=lambda pid: person if pid == _OWNER else None,
+        lookup_role=lambda _pid: role,
+        clock=lambda: _NOW,
+    )
+
+
+def _strong(role: HouseholdRole = HouseholdRole.OWNER) -> ActivePersonContext:
+    return _actor(IdentityEvidenceSource.FACE, IdentityEvidenceSource.VOICE, role=role)
+
+
+@pytest.fixture(autouse=True)
+def _candidates_on(monkeypatch: pytest.MonkeyPatch) -> None:
+    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
+
+
+async def _authorize(
+    step: CandidateStep,
+    actor: ActivePersonContext,
+    *,
+    subject: int = _OWNER,
+    audit: AsyncMock | None = None,
+    policy: Mock | None = None,
+) -> PolicyOutcome:
+    return await authorize_step(
+        step,
+        actor=actor,
+        subject_person_id=subject,
+        correlation_id=_CORRELATION,
+        now=_NOW,
+        audit=audit or AsyncMock(),
+        policy=policy or evaluate_authorization,
+    )
+
+
+@pytest.mark.parametrize(
+    "step, action",
+    [
+        (CandidateStep.PROPOSE, AuthorizationAction.PROPOSE_PERSONAL_MEMORY),
+        (CandidateStep.READ, AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY),
+        (CandidateStep.CONFIRM, AuthorizationAction.CONFIRM_PERSONAL_MEMORY),
+    ],
+)
+async def test_each_step_asks_its_own_action_about_the_subjects_ordinary_personal_data(
+    step: CandidateStep, action: AuthorizationAction
+) -> None:
+    audit = AsyncMock()
+
+    outcome = await _authorize(step, _strong(), audit=audit)
+
+    assert outcome.allowed
+    assert outcome.policy_id == "cm1.personal-memory.allowed"
+    request, decision = audit.call_args.args
+    assert isinstance(request, AuthorizationRequest)
+    assert request.action is action
+    assert request.target_person_id == _OWNER
+    assert request.visibility == frozenset({DataVisibility.PERSONAL})
+    assert request.sensitivity == frozenset({DataSensitivity.NORMAL})
+    assert request.consent is ConsentStatus.NOT_REQUIRED
+    assert request.correlation_id == _CORRELATION
+    assert request.requested_at == _NOW
+    assert decision.action is action
+
+
+async def test_the_audit_row_is_written_before_the_step_is_reported_allowed() -> None:
+    order: list[str] = []
+
+    def policy(request: AuthorizationRequest) -> AuthorizationDecision:
+        order.append("policy")
+        return evaluate_authorization(request)
+
+    async def audit(_request: AuthorizationRequest, _decision: AuthorizationDecision) -> None:
+        order.append("audit")
+
+    outcome = await authorize_step(
+        CandidateStep.PROPOSE,
+        actor=_strong(),
+        subject_person_id=_OWNER,
+        correlation_id=_CORRELATION,
+        now=_NOW,
+        policy=policy,
+        audit=audit,
+    )
+    order.append("effect")
+
+    assert outcome.allowed
+    assert order == ["policy", "audit", "effect"]
+
+
+@pytest.mark.parametrize("step", list(CandidateStep))
+async def test_a_failing_audit_denies_the_step(
+    step: CandidateStep, caplog: pytest.LogCaptureFixture
+) -> None:
+    audit = AsyncMock(side_effect=RuntimeError("disk full: zumo de pomelo"))
+
+    with caplog.at_level("DEBUG"):
+        outcome = await _authorize(step, _strong(), audit=audit)
+
+    assert not outcome.allowed
+    assert outcome.reason is CandidateReason.DENIED
+    assert "pomelo" not in caplog.text
+
+
+@pytest.mark.parametrize(
+    "sources",
+    [
+        (IdentityEvidenceSource.FACE,),
+        (IdentityEvidenceSource.LOCAL_UNLOCK,),
+        (IdentityEvidenceSource.MANUAL,),
+        (IdentityEvidenceSource.VOICE,),
+        (
+            IdentityEvidenceSource.FACE,
+            IdentityEvidenceSource.VOICE,
+            IdentityEvidenceSource.LOCAL_UNLOCK,
+        ),
+        (),
+    ],
+)
+@pytest.mark.parametrize("step", list(CandidateStep))
+async def test_only_the_face_and_voice_composite_passes_and_a_refusal_is_not_audited(
+    step: CandidateStep, sources: tuple[IdentityEvidenceSource, ...]
+) -> None:
+    audit = AsyncMock()
+    policy = Mock(side_effect=evaluate_authorization)
+
+    outcome = await _authorize(step, _actor(*sources), audit=audit, policy=policy)
+
+    assert not outcome.allowed
+    assert outcome.reason is CandidateReason.STRONG_UNREACHABLE
+    policy.assert_not_called()
+    audit.assert_not_awaited()
+
+
+async def test_another_persons_memory_is_denied_and_the_denial_is_audited() -> None:
+    audit = AsyncMock()
+
+    outcome = await _authorize(CandidateStep.PROPOSE, _strong(), subject=_OWNER + 1, audit=audit)
+
+    assert not outcome.allowed
+    assert outcome.policy_id == "cm1.personal-memory.own-data-only"
+    audit.assert_awaited_once()
+    assert audit.call_args.args[1].decision.value == "denied"
+
+
+@pytest.mark.parametrize("role", [HouseholdRole.ADULT, HouseholdRole.CHILD, HouseholdRole.GUEST])
+async def test_a_non_owner_is_denied_and_audited(role: HouseholdRole) -> None:
+    audit = AsyncMock()
+
+    outcome = await _authorize(CandidateStep.CONFIRM, _strong(role), audit=audit)
+
+    assert not outcome.allowed
+    assert outcome.policy_id == "cm1.personal-memory.owner-only"
+    audit.assert_awaited_once()
+
+
+@pytest.mark.parametrize("step", list(CandidateStep))
+async def test_the_kill_switch_denies_every_step_before_anything_is_asked(
+    step: CandidateStep, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
+    audit = AsyncMock()
+    policy = Mock(side_effect=evaluate_authorization)
+
+    outcome = await _authorize(step, _strong(), audit=audit, policy=policy)
+
+    assert not outcome.allowed
+    policy.assert_not_called()
+    audit.assert_not_awaited()
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_candidate_policy.py tests/unit/test_architecture_guards.py -q -p no:cacheprovider`
  Expected RED: `ModuleNotFoundError: No module named 'server.memory.candidate_policy'`.
- [ ] **Step 3: Implement:**

```diff
diff --git a/server/src/server/memory/candidate_policy.py b/server/src/server/memory/candidate_policy.py
new file mode 100644
--- /dev/null
+++ b/server/src/server/memory/candidate_policy.py
@@ -0,0 +1,145 @@
+"""The policy check of a candidate step (ADR 0021 decision 7): evaluate, audit, then act.
+
+Three steps ask ADR 0019's policy a question about the owner's own personal memory:
+
+* ``PROPOSE`` asks ``propose_personal_memory`` before a candidate is stored (Plan 0062);
+* ``READ`` asks ``read_personal_conversation_memory`` before an offer is spoken (Plan 0063);
+* ``CONFIRM`` asks ``confirm_personal_memory`` before an answer is accepted (Plan 0063).
+
+The policy minimums are ``basic`` for propose and read and ``strong`` for confirm, but every
+caller of CM-3a demands more (the firewall rule): the actor must be the composite of face and
+voice of that turn and carry no token. A weaker actor is refused here before the policy is
+even asked, so a bug upstream cannot weaken the rule.
+
+The audit row is written **before** the effect and a failing audit denies (ADR 0019 §6.3).
+Nothing here reads or returns a protected value.
+"""
+
+from __future__ import annotations
+
+from collections.abc import Awaitable, Callable
+from dataclasses import dataclass
+from enum import StrEnum
+import logging
+from typing import TYPE_CHECKING
+
+from server.cognition.authorization import (
+    AuthorizationRequest,
+    ConsentStatus,
+    evaluate_authorization,
+)
+from server.cognition.models import AuthorizationAction, AuthorizationDecision, AuthorizationStatus
+from server.cognition.strong_actor import is_face_and_voice_actor
+from server.memory.candidate_classifier import CANDIDATE_SENSITIVITY, CANDIDATE_VISIBILITY
+from server.memory.candidate_types import CandidateReason
+from server.memory.household_authorization import record_authorization_decision
+from server.settings import settings
+
+if TYPE_CHECKING:
+    from datetime import datetime
+    from uuid import UUID
+
+    from server.cognition.identity import ActivePersonContext
+
+logger = logging.getLogger(__name__)
+
+__all__ = ["CandidateStep", "PolicyOutcome", "authorize_step"]
+
+type PolicyEvaluator = Callable[[AuthorizationRequest], AuthorizationDecision]
+type AuditWriter = Callable[[AuthorizationRequest, AuthorizationDecision], Awaitable[None]]
+
+
+class CandidateStep(StrEnum):
+    """The step of a candidate's life that asks the policy."""
+
+    PROPOSE = "propose"
+    READ = "read"
+    CONFIRM = "confirm"
+
+
+_ACTIONS = {
+    CandidateStep.PROPOSE: AuthorizationAction.PROPOSE_PERSONAL_MEMORY,
+    CandidateStep.READ: AuthorizationAction.READ_PERSONAL_CONVERSATION_MEMORY,
+    CandidateStep.CONFIRM: AuthorizationAction.CONFIRM_PERSONAL_MEMORY,
+}
+
+
+@dataclass(frozen=True)
+class PolicyOutcome:
+    """The result of one step's policy check.
+
+    Attributes:
+        allowed: Whether the step may take effect.
+        reason: ``None`` when allowed, else the closed reason it was refused for.
+        policy_id: The policy's outcome id when the policy was asked, else ``None``.
+    """
+
+    allowed: bool
+    reason: CandidateReason | None = None
+    policy_id: str | None = None
+
+
+def _refused(
+    reason: CandidateReason, step: CandidateStep, policy_id: str | None = None
+) -> PolicyOutcome:
+    logger.info(
+        "Candidate policy: %s refused (%s)",
+        step.value,
+        reason.value,
+        extra={"event": "candidate.policy", "step": step, "reason": reason, "policy_id": policy_id},
+    )
+    return PolicyOutcome(allowed=False, reason=reason, policy_id=policy_id)
+
+
+async def authorize_step(
+    step: CandidateStep,
+    *,
+    actor: ActivePersonContext,
+    subject_person_id: int,
+    correlation_id: UUID,
+    now: datetime,
+    policy: PolicyEvaluator = evaluate_authorization,
+    audit: AuditWriter = record_authorization_decision,
+) -> PolicyOutcome:
+    """Ask the policy whether *actor* may take *step* on the subject's own ordinary memory.
+
+    Args:
+        step: Which step asks.
+        actor: The face-and-voice actor of this turn, never a token actor.
+        subject_person_id: Whose memory the candidate would become. Targeting the subject
+            (not the actor) lets the policy's own-data rule fire.
+        correlation_id: The turn's id, so the audit row joins to the candidate and the fact.
+        now: The caller's clock reading.
+        policy: The pure evaluator; tests inject doubles.
+        audit: The audit writer; tests inject doubles.
+
+    Returns:
+        ``allowed`` only when the kill-switch is on, the actor is the composite, the policy
+        allows and the audit row was written. Any other case is a refusal with a closed
+        reason, and the caller must neither store, speak nor promote.
+    """
+    if not settings.memory_candidates_enabled:
+        return _refused(CandidateReason.DENIED, step)
+    if not is_face_and_voice_actor(actor):
+        return _refused(CandidateReason.STRONG_UNREACHABLE, step)
+    request = AuthorizationRequest(
+        actor=actor,
+        action=_ACTIONS[step],
+        target_person_id=subject_person_id,
+        visibility=frozenset({CANDIDATE_VISIBILITY}),
+        sensitivity=frozenset({CANDIDATE_SENSITIVITY}),
+        consent=ConsentStatus.NOT_REQUIRED,
+        correlation_id=correlation_id,
+        requested_at=now,
+    )
+    decision = policy(request)
+    try:
+        await audit(request, decision)
+    except Exception as exc:
+        # The audit must precede the effect and a failing audit denies it (ADR 0019 §6.3).
+        # Only the class is logged: the exception could carry a row value.
+        logger.warning("Candidate audit failed (%s): the step is denied", type(exc).__name__)
+        return _refused(CandidateReason.DENIED, step, decision.policy_id)
+    if decision.decision is not AuthorizationStatus.ALLOWED:
+        return _refused(CandidateReason.DENIED, step, decision.policy_id)
+    return PolicyOutcome(allowed=True, policy_id=decision.policy_id)
```

- [ ] **Step 4: Run to see them pass, then lint and types.**
- [ ] **Step 5: Commit** `feat(server): add the candidate policy check (plan 0062)`; check `git log -1`.

---

## Task 10: The canonical memory writer

**Files:**
- Create: `server/src/server/memory/memory_writer.py`
- Test: new `tests/integration/test_memory_writer.py`; modified `tests/unit/test_architecture_guards.py`

**Interfaces:**
- Consumes: Tasks 6, 7, 8 and 9.
- Produces: `PromotionOutcome` (`PROMOTED`, `ALREADY_PRESENT`, `CONTRADICTION`, `NOT_OFFERED`,
  `DENIED`), `PromotionResult(outcome, fact_id)` and `async promote(candidate_id, *, actor,
  correlation_id, now, policy=..., audit=...)`. `memory/memory_writer.py` joins
  `_MAY_IMPORT_RAW_V4_READERS` of the architecture guard (it reads the active rows to compare
  folded keys); `_MAY_QUERY_V4_TABLES` and `_V4_TABLE_SQL` do not change because it issues no SQL on
  a V4 table.

Nothing calls `promote` from a route in this plan: it is a seam, proven with doubles. After the
commit it truncates the log only when it resolved the candidate, and a checkpoint that cannot
finish never turns a committed promotion into a failure. `candidates.py`'s callers are pinned by
Task 14's guard.

- [ ] **Step 1: Write the failing tests** (the fact and its stamp, the registry default that does
  not move, audit before the write and the real audit row, a duplicate as a result, an exact
  duplicate that never reaches the unique index, a contradiction, `prefers` has no opposite, only an
  unexpired offered candidate, a second promotion, two at once, the actor's id and never the
  request's, weaker actors, a failing audit, the kill-switch, and a rollback that restores both the
  fact and the candidate):

```diff
diff --git a/tests/integration/test_memory_writer.py b/tests/integration/test_memory_writer.py
new file mode 100644
--- /dev/null
+++ b/tests/integration/test_memory_writer.py
@@ -0,0 +1,458 @@
+"""Integration tests for the canonical writer (ADR 0021 decision 8) over a temporary SQLite."""
+
+from __future__ import annotations
+
+import asyncio
+from datetime import UTC, datetime, timedelta
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
+from server.cognition.models import Confidence, ConfidenceBasis
+from server.memory import candidates, memory_writer
+from server.memory.biometric_consent import grant_face_consent
+from server.memory.candidate_types import CandidateChannel, CandidateStatus, ProposedCandidate
+from server.memory.candidates import iso_utc
+from server.memory.declarative import upsert_entity
+from server.memory.memory_writer import PromotionOutcome, promote
+from server.memory.predicate_registry import PredicateDefinition, resolve_predicate
+from server.memory.relational_v4 import (
+    AssertionLifecycle,
+    assert_literal_fact,
+    get_active_literal_facts,
+    get_literal_fact,
+)
+from server.settings import settings
+
+from server import db
+
+if TYPE_CHECKING:
+    from collections.abc import AsyncIterator
+    from pathlib import Path
+
+pytestmark = pytest.mark.integration
+
+_T0 = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
+_ANSWER = _T0 + timedelta(seconds=20)
+
+
+def _evidence(source: IdentityEvidenceSource, person_id: int) -> IdentityEvidence:
+    return IdentityEvidence(
+        evidence_id=uuid4(),
+        source=source,
+        candidate_person_id=person_id,
+        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
+        observed_at=_T0,
+        reference="canary",
+    )
+
+
+def _actor(person_id: int, *sources: IdentityEvidenceSource) -> ActivePersonContext:
+    sources = sources or (IdentityEvidenceSource.FACE, IdentityEvidenceSource.VOICE)
+    person = PersonRecord(person_id=person_id, display_name="Canary", entity_type="person")
+    return resolve_active_person(
+        evidence=tuple(_evidence(s, person_id) for s in sources),
+        lookup_person=lambda pid: person if pid == person_id else None,
+        lookup_role=lambda _pid: HouseholdRole.OWNER,
+        clock=lambda: _T0,
+    )
+
+
+@pytest.fixture
+async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
+    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "writer.db")
+    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
+    db._conn = None
+    await db.open_db()
+    await db.run_migrations()
+    owner_id = await upsert_entity(name="Canary Owner", type="person")
+    await grant_face_consent(owner_id)
+    yield owner_id
+    await db.close_db()
+    db._conn = None
+
+
+def _definition(name: str) -> PredicateDefinition:
+    definition = resolve_predicate(name)
+    assert definition is not None
+    return definition
+
+
+async def _offered(
+    owner_id: int,
+    value: str = "el mate",
+    key: str = "mate",
+    predicate: str = "likes",
+    *,
+    subject: int | None = None,
+) -> int:
+    """Store a candidate and move it to `offered`."""
+    subject_id = subject or owner_id
+    stored = await candidates.insert_candidate(
+        ProposedCandidate(predicate=predicate, value_text=value, value_key=key),
+        subject_person_id=subject_id,
+        asserted_by_person_id=subject_id,
+        channel=CandidateChannel.VOICE_CLASSIC,
+        correlation_id=uuid4(),
+        now=_T0,
+    )
+    assert stored.candidate_id is not None
+    assert await candidates.mark_offered(
+        stored.candidate_id, subject_id, correlation_id=uuid4(), now=_T0
+    )
+    return stored.candidate_id
+
+
+async def _promote(
+    candidate_id: int,
+    actor: ActivePersonContext,
+    *,
+    audit: AsyncMock | None = None,
+    now: datetime = _ANSWER,
+    correlation: UUID | None = None,
+) -> memory_writer.PromotionResult:
+    return await promote(
+        candidate_id,
+        actor=actor,
+        correlation_id=correlation or uuid4(),
+        now=now,
+        audit=audit or AsyncMock(),
+    )
+
+
+async def _facts(owner_id: int, predicate: str = "likes") -> list[str]:
+    return [
+        fact.value_text
+        for fact in await get_active_literal_facts(
+            subject_entity_id=owner_id, definition=_definition(predicate)
+        )
+    ]
+
+
+async def test_an_offered_candidate_becomes_one_personal_confirmed_fact(owner: int) -> None:
+    candidate_id = await _offered(owner, "el mate", "mate")
+    answer = uuid4()
+
+    result = await _promote(candidate_id, _actor(owner), correlation=answer)
+
+    assert result.outcome is PromotionOutcome.PROMOTED
+    assert result.fact_id is not None
+    fact = await get_literal_fact(result.fact_id)
+    assert fact is not None
+    assert (fact.subject_entity_id, fact.predicate, fact.value_text) == (owner, "likes", "el mate")
+    assert (fact.visibility, fact.sensitivity) == ("personal", "normal")
+    assert fact.confidence == 1.0
+    assert fact.lifecycle is AssertionLifecycle.ACTIVE
+    assert fact.source_memory_id is None
+    assert fact.confirmed_by_entity_id == owner
+    assert fact.confirmed_at == iso_utc(_ANSWER)
+    assert fact.asserted_at == iso_utc(_T0)
+    candidate = await candidates.get_candidate(candidate_id)
+    assert candidate is not None
+    assert candidate.status is CandidateStatus.CONFIRMED
+    assert candidate.promoted_fact_id == fact.id
+    assert candidate.resolution_correlation_id == str(answer)
+    assert (candidate.value_text, candidate.value_key) == (None, None)
+
+
+async def test_the_registry_default_that_the_household_reader_relies_on_does_not_move(
+    owner: int,
+) -> None:
+    likes = _definition("likes")
+    before = (likes.default_visibility, likes.default_sensitivity)
+
+    await _promote(await _offered(owner), _actor(owner))
+
+    after = _definition("likes")
+    assert (
+        (after.default_visibility, after.default_sensitivity) == before == ("household", "normal")
+    )
+
+
+async def test_the_confirmation_is_audited_before_the_write(owner: int) -> None:
+    candidate_id = await _offered(owner)
+    seen_facts: list[int] = []
+
+    async def audit(*_args: object) -> None:
+        seen_facts.append(len(await _facts(owner)))
+
+    result = await promote(
+        candidate_id, actor=_actor(owner), correlation_id=uuid4(), now=_ANSWER, audit=audit
+    )
+
+    assert result.outcome is PromotionOutcome.PROMOTED
+    assert seen_facts == [0]
+    assert await _facts(owner) == ["el mate"]
+
+
+async def test_the_real_audit_row_names_the_action_and_carries_no_value(owner: int) -> None:
+    candidate_id = await _offered(owner, "el zumo de pomelo", "zumo de pomelo")
+    answer = uuid4()
+
+    result = await promote(candidate_id, actor=_actor(owner), correlation_id=answer, now=_ANSWER)
+
+    assert result.outcome is PromotionOutcome.PROMOTED
+    cursor = await db.get_conn().execute(
+        "SELECT action, decision, policy_id, data_categories, actor_entity_id, target_entity_id, "
+        "reason FROM authorization_audit_events WHERE correlation_id = ?",
+        (str(answer),),
+    )
+    rows = list(await cursor.fetchall())
+    await cursor.close()
+    assert len(rows) == 1
+    action, decision, policy_id, categories, actor_id, target_id, reason = rows[0]
+    assert (action, decision, policy_id) == (
+        "confirm_personal_memory",
+        "allowed",
+        "cm1.personal-memory.allowed",
+    )
+    assert categories == "normal,personal"
+    assert (actor_id, target_id) == (owner, owner)
+    assert "pomelo" not in reason
+
+
+async def test_a_duplicate_is_the_result_not_an_error(owner: int) -> None:
+    existing = await assert_literal_fact(
+        subject_entity_id=owner,
+        definition=_definition("likes"),
+        value="El Mate",
+    )
+    candidate_id = await _offered(owner, "el mate", "mate")
+
+    result = await _promote(candidate_id, _actor(owner))
+
+    assert result.outcome is PromotionOutcome.ALREADY_PRESENT
+    assert result.fact_id == existing.id
+    assert await _facts(owner) == ["El Mate"]
+    candidate = await candidates.get_candidate(candidate_id)
+    assert candidate is not None
+    assert candidate.status is CandidateStatus.CONFIRMED
+    assert candidate.promoted_fact_id == existing.id
+
+
+async def test_an_exact_duplicate_does_not_reach_the_unique_index(owner: int) -> None:
+    await assert_literal_fact(
+        subject_entity_id=owner,
+        definition=_definition("likes"),
+        value="el mate",
+    )
+
+    result = await _promote(await _offered(owner, "el mate", "mate"), _actor(owner))
+
+    assert result.outcome is PromotionOutcome.ALREADY_PRESENT
+
+
+async def test_the_opposite_polarity_is_a_contradiction_and_writes_nothing(owner: int) -> None:
+    dislike = await assert_literal_fact(
+        subject_entity_id=owner,
+        definition=_definition("dislikes"),
+        value="el mate",
+    )
+    candidate_id = await _offered(owner, "el mate", "mate", "likes")
+
+    result = await _promote(candidate_id, _actor(owner))
+
+    assert result.outcome is PromotionOutcome.CONTRADICTION
+    assert result.fact_id is None
+    assert await _facts(owner, "likes") == []
+    assert await _facts(owner, "dislikes") == ["el mate"]
+    stored = await get_literal_fact(dislike.id)
+    assert stored is not None
+    assert stored.lifecycle is AssertionLifecycle.ACTIVE
+    candidate = await candidates.get_candidate(candidate_id)
+    assert candidate is not None
+    assert candidate.status is CandidateStatus.REJECTED
+    assert (candidate.value_text, candidate.value_key) == (None, None)
+
+
+async def test_a_prefers_candidate_has_no_opposite(owner: int) -> None:
+    await assert_literal_fact(
+        subject_entity_id=owner,
+        definition=_definition("dislikes"),
+        value="el mate",
+    )
+
+    result = await _promote(await _offered(owner, "el mate", "mate", "prefers"), _actor(owner))
+
+    assert result.outcome is PromotionOutcome.PROMOTED
+    assert await _facts(owner, "prefers") == ["el mate"]
+
+
+@pytest.mark.parametrize("state", ["proposed", "expired", "resolved"])
+async def test_only_an_unexpired_offered_candidate_is_promoted(owner: int, state: str) -> None:
+    stored = await candidates.insert_candidate(
+        ProposedCandidate(predicate="likes", value_text="el mate", value_key="mate"),
+        subject_person_id=owner,
+        asserted_by_person_id=owner,
+        channel=CandidateChannel.VOICE_STREAM,
+        correlation_id=uuid4(),
+        now=_T0,
+    )
+    assert stored.candidate_id is not None
+    now = _ANSWER
+    if state in {"expired", "resolved"}:
+        await candidates.mark_offered(stored.candidate_id, owner, correlation_id=uuid4(), now=_T0)
+    if state == "resolved":
+        await candidates.resolve_candidate(
+            stored.candidate_id,
+            owner,
+            to=CandidateStatus.REJECTED,
+            correlation_id=uuid4(),
+            now=_T0,
+        )
+    if state == "expired":
+        now = _T0 + timedelta(seconds=settings.memory_candidate_ttl_seconds)
+
+    result = await _promote(stored.candidate_id, _actor(owner), now=now)
+
+    assert result.outcome is PromotionOutcome.NOT_OFFERED
+    assert await _facts(owner) == []
+
+
+async def test_a_second_promotion_of_the_same_candidate_writes_nothing(owner: int) -> None:
+    candidate_id = await _offered(owner)
+    first = await _promote(candidate_id, _actor(owner))
+
+    second = await _promote(candidate_id, _actor(owner))
+
+    assert first.outcome is PromotionOutcome.PROMOTED
+    assert second.outcome is PromotionOutcome.NOT_OFFERED
+    assert await _facts(owner) == ["el mate"]
+
+
+async def test_two_confirmations_at_once_promote_exactly_one_fact(owner: int) -> None:
+    candidate_id = await _offered(owner)
+
+    results = await asyncio.gather(
+        _promote(candidate_id, _actor(owner)), _promote(candidate_id, _actor(owner))
+    )
+
+    assert sorted(r.outcome.value for r in results) == ["not_offered", "promoted"]
+    assert await _facts(owner) == ["el mate"]
+
+
+async def test_the_candidate_is_found_by_the_actors_id_never_by_one_the_request_carries(
+    owner: int,
+) -> None:
+    other = await upsert_entity(name="Canary Visitor", type="person")
+    theirs = await _offered(owner, subject=other, value="el jazz", key="jazz")
+
+    result = await _promote(theirs, _actor(owner))
+
+    assert result.outcome is PromotionOutcome.NOT_OFFERED
+    assert await _facts(owner) == []
+    assert await _facts(other) == []
+    candidate = await candidates.get_candidate(theirs)
+    assert candidate is not None
+    assert candidate.status is CandidateStatus.OFFERED
+
+
+@pytest.mark.parametrize(
+    "sources",
+    [
+        (IdentityEvidenceSource.FACE,),
+        (IdentityEvidenceSource.LOCAL_UNLOCK,),
+        (IdentityEvidenceSource.MANUAL,),
+        (),
+    ],
+)
+async def test_a_weaker_actor_promotes_nothing_and_leaves_the_candidate_offered(
+    owner: int, sources: tuple[IdentityEvidenceSource, ...]
+) -> None:
+    candidate_id = await _offered(owner)
+    audit = AsyncMock()
+    actor = _actor(owner, *sources) if sources else _actor(owner, IdentityEvidenceSource.VOICE)
+
+    result = await _promote(candidate_id, actor, audit=audit)
+
+    assert result.outcome is PromotionOutcome.DENIED
+    assert await _facts(owner) == []
+    audit.assert_not_awaited()
+    candidate = await candidates.get_candidate(candidate_id)
+    assert candidate is not None
+    assert candidate.status is CandidateStatus.OFFERED
+    assert candidate.value_text == "el mate"
+
+
+async def test_a_failing_audit_promotes_nothing(owner: int) -> None:
+    candidate_id = await _offered(owner)
+
+    result = await _promote(
+        candidate_id, _actor(owner), audit=AsyncMock(side_effect=RuntimeError("down"))
+    )
+
+    assert result.outcome is PromotionOutcome.DENIED
+    assert await _facts(owner) == []
+    candidate = await candidates.get_candidate(candidate_id)
+    assert candidate is not None
+    assert candidate.status is CandidateStatus.OFFERED
+
+
+async def test_the_kill_switch_stops_promotion(owner: int, monkeypatch: pytest.MonkeyPatch) -> None:
+    candidate_id = await _offered(owner)
+    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
+
+    result = await _promote(candidate_id, _actor(owner))
+
+    assert result.outcome is PromotionOutcome.DENIED
+    assert await _facts(owner) == []
+
+
+async def test_a_failure_inside_the_transaction_rolls_back_fact_and_resolution(
+    owner: int, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    candidate_id = await _offered(owner)
+    real = memory_writer.assert_literal_fact
+    calls: list[bool] = []
+
+    async def failing(**kwargs: object) -> object:
+        calls.append(bool(kwargs["manage_transaction"]))
+        await real(**kwargs)  # type: ignore[arg-type]
+        raise RuntimeError("boom after the insert")
+
+    monkeypatch.setattr(memory_writer, "assert_literal_fact", failing)
+
+    with pytest.raises(RuntimeError, match="boom"):
+        await _promote(candidate_id, _actor(owner))
+
+    assert calls == [False]  # it joined the writer's transaction, it did not open its own
+    assert await _facts(owner) == []
+    candidate = await candidates.get_candidate(candidate_id)
+    assert candidate is not None
+    assert candidate.status is CandidateStatus.OFFERED
+    assert candidate.value_text == "el mate"
+
+
+async def test_a_postponed_checkpoint_does_not_turn_a_committed_promotion_into_a_failure(
+    owner: int,
+) -> None:
+    candidate_id = await _offered(owner)
+    # Many rows and one fetch: the statement stays active, as a coroutine between an execute\n    # and its fetchall would leave it.
+    cursor = await db.get_conn().execute("SELECT * FROM sqlite_master")
+    await cursor.fetchone()
+
+    result = await _promote(candidate_id, _actor(owner))
+    await cursor.close()
+
+    assert result.outcome is PromotionOutcome.PROMOTED
+    assert await _facts(owner) == ["el mate"]
+
+
+async def test_promoting_a_missing_candidate_is_not_offered_and_writes_nothing(
+    owner: int,
+) -> None:
+    """The caller is Plan 0063's answer branch, after an answer matched an offer: the audit row
+    is written first by design, so a speculative call would leave a trace and must not happen."""
+    result = await _promote(987654, _actor(owner))
+
+    assert result.outcome is PromotionOutcome.NOT_OFFERED
+    assert await _facts(owner) == []
diff --git a/tests/unit/test_architecture_guards.py b/tests/unit/test_architecture_guards.py
--- a/tests/unit/test_architecture_guards.py
+++ b/tests/unit/test_architecture_guards.py
@@ -19,8 +19,11 @@ _RAW_V4_READERS = frozenset(
         "get_entity_relation",
     }
 )
-# The policy gate, and the local setup that re-reads what it just wrote.
-_MAY_IMPORT_RAW_V4_READERS = frozenset({"memory/policy_gated_v4_reader.py", "personal_setup.py"})
+# The policy gate, the local setup that re-reads what it just wrote, and the one canonical
+# writer, which compares the active rows' folded keys inside its own transaction (Plan 0062).
+_MAY_IMPORT_RAW_V4_READERS = frozenset(
+    {"memory/policy_gated_v4_reader.py", "personal_setup.py", "memory/memory_writer.py"}
+)
 # The repository itself, and the setup status that counts child links.
 _MAY_QUERY_V4_TABLES = frozenset({"memory/relational_v4.py", "personal_setup.py"})
 _V4_TABLE_SQL = re.compile(
@@ -381,3 +384,37 @@ def test_the_continuity_guards_detect_a_violation() -> None:
     ]
     (wav_value,) = _keyword_values(leak, _GENERIC_IDENTITY_HOME, "wav_bytes")
     assert not (isinstance(wav_value, ast.Constant) and wav_value.value is None)
+
+
+# --- memory candidates (Plan 0062, ADR 0021) ---------------------------------------------
+# The store is the only module that issues SQL against the candidate table, so the scrub, the
+# compare-and-set and the cap cannot be bypassed by a second writer.
+_CANDIDATE_TABLE_SQL = re.compile(
+    r"\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM)\s+memory_candidates\b"
+)
+_MAY_QUERY_CANDIDATES = frozenset({"memory/candidates.py"})
+
+
+def _candidate_table_queriers(sources: Mapping[str, str]) -> list[str]:
+    """Modules, besides the store, that put SQL on `memory_candidates`."""
+    return [
+        name
+        for name, text in sources.items()
+        if name not in _MAY_QUERY_CANDIDATES and _CANDIDATE_TABLE_SQL.search(text)
+    ]
+
+
+@pytest.mark.unit
+def test_the_candidate_table_is_queried_only_by_the_store() -> None:
+    assert _candidate_table_queriers(_sources()) == []
+
+
+@pytest.mark.unit
+def test_the_candidate_guard_detects_a_violation() -> None:
+    leak = {
+        "memory/leak.py": "SQL = \"UPDATE memory_candidates SET status = 'offered'\"\n",
+        "memory/candidates.py": 'SQL = "SELECT 1 FROM memory_candidates"\n',
+        "prose.py": '"""The memory_candidates table is described here."""\n',
+    }
+
+    assert _candidate_table_queriers(leak) == ["memory/leak.py"]
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/integration/test_memory_writer.py tests/unit/test_architecture_guards.py -q -p no:cacheprovider`
  Expected RED: `ImportError: cannot import name 'memory_writer' from 'server.memory'`.
- [ ] **Step 3: Implement:**

```diff
diff --git a/server/src/server/memory/memory_writer.py b/server/src/server/memory/memory_writer.py
new file mode 100644
--- /dev/null
+++ b/server/src/server/memory/memory_writer.py
@@ -0,0 +1,246 @@
+"""The canonical memory writer: the only place a V4 fact is created from a candidate.
+
+One function, ``promote`` (ADR 0021 decision 8), in **one** ``db.transaction()``:
+
+1. housekeeping, then the candidate must be ``offered``, unexpired and the actor's own;
+2. a **contradiction** (the same key under the opposite polarity among the active facts)
+   closes the candidate ``rejected`` and writes nothing;
+3. a **duplicate** (the same folded key among the active facts of that predicate) is the
+   result, idempotently: the candidate is confirmed against the fact already there;
+4. otherwise the fact is inserted through ``assert_literal_fact(manage_transaction=False)``
+   with visibility ``personal``, sensitivity ``normal``, who confirmed it and when;
+5. the candidate is marked ``confirmed`` with its ``promoted_fact_id`` and its value is erased.
+
+The duplicate and the contradiction are decided by comparing folded keys, never by relying on
+the ``IntegrityError`` a duplicate raises (a test pins that error, and it would roll back the
+whole transaction). Nothing here is wired to a route in Plan 0062: it is a seam, proven with
+doubles, that Plan 0063's spoken confirmation will call.
+
+The policy is asked and audited **before** the transaction (ADR 0019 §6.3), through
+``authorize_step``; a refusal writes nothing.
+"""
+
+from __future__ import annotations
+
+from dataclasses import dataclass
+from enum import StrEnum
+import logging
+from typing import TYPE_CHECKING
+
+from server import db
+from server.cognition.authorization import evaluate_authorization
+from server.cognition.strong_actor import is_face_and_voice_actor
+from server.memory.candidate_classifier import (
+    CANDIDATE_SENSITIVITY,
+    CANDIDATE_VISIBILITY,
+    comparison_key,
+)
+from server.memory.candidate_policy import CandidateStep, authorize_step
+from server.memory.candidate_types import CandidateStatus
+from server.memory.candidates import (
+    checkpoint_after_scrub,
+    get_candidate_in_transaction,
+    iso_utc,
+    resolve_candidate_in_transaction,
+    run_housekeeping,
+)
+from server.memory.household_authorization import record_authorization_decision
+from server.memory.predicate_registry import resolve_predicate
+from server.memory.relational_v4 import assert_literal_fact, get_active_literal_facts
+from server.settings import settings
+
+if TYPE_CHECKING:
+    from datetime import datetime
+    from uuid import UUID
+
+    import aiosqlite
+
+    from server.cognition.identity import ActivePersonContext
+    from server.memory.candidate_policy import AuditWriter, PolicyEvaluator
+
+logger = logging.getLogger(__name__)
+
+__all__ = ["PromotionOutcome", "PromotionResult", "promote"]
+
+# Opposite polarity, by canonical predicate. `prefers` has no opposite.
+_OPPOSITE = {"likes": "dislikes", "dislikes": "likes"}
+
+
+class PromotionOutcome(StrEnum):
+    """Closed outcome of one promotion attempt."""
+
+    PROMOTED = "promoted"
+    ALREADY_PRESENT = "already_present"
+    CONTRADICTION = "contradiction"
+    NOT_OFFERED = "not_offered"
+    DENIED = "denied"
+
+
+@dataclass(frozen=True)
+class PromotionResult:
+    """What ``promote`` did.
+
+    Attributes:
+        outcome: The closed outcome.
+        fact_id: The canonical fact the candidate became (``PROMOTED``) or matched
+            (``ALREADY_PRESENT``); ``None`` otherwise.
+    """
+
+    outcome: PromotionOutcome
+    fact_id: int | None = None
+
+
+async def promote(
+    candidate_id: int,
+    *,
+    actor: ActivePersonContext,
+    correlation_id: UUID,
+    now: datetime,
+    policy: PolicyEvaluator = evaluate_authorization,
+    audit: AuditWriter = record_authorization_decision,
+) -> PromotionResult:
+    """Promote one offered candidate of *actor* to a canonical V4 literal fact.
+
+    Args:
+        candidate_id: The candidate. It is looked up by the actor's own person id, never by an
+            id the request carries.
+        actor: The face-and-voice actor of the confirming turn.
+        correlation_id: The confirming turn's id, for the audit row and the candidate.
+        now: The caller's clock reading.
+        policy: The pure policy evaluator; tests inject doubles.
+        audit: The audit writer; tests inject doubles.
+
+    Returns:
+        ``DENIED`` for the kill-switch, a weaker actor, a policy refusal or an audit failure
+        (nothing is written); ``NOT_OFFERED`` for a candidate that is not the actor's, not
+        ``offered`` or lapsed; ``CONTRADICTION`` after closing the candidate; otherwise
+        ``PROMOTED`` or ``ALREADY_PRESENT`` with the fact id.
+    """
+    person_id = actor.person_id
+    if not settings.memory_candidates_enabled or person_id is None:
+        return PromotionResult(PromotionOutcome.DENIED)
+    if not is_face_and_voice_actor(actor):
+        return PromotionResult(PromotionOutcome.DENIED)
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
+        return PromotionResult(PromotionOutcome.DENIED)
+    async with db.transaction() as conn:
+        scrubbed = await run_housekeeping(conn, now)
+        result = await _promote_in_transaction(
+            conn, candidate_id, person_id, correlation_id=correlation_id, now=now
+        )
+    # A resolution erased the candidate's value; a refusal changed nothing.
+    resolved = result.outcome is not PromotionOutcome.NOT_OFFERED
+    await checkpoint_after_scrub(scrubbed + int(resolved))
+    logger.info(
+        "Candidate promotion: %s",
+        result.outcome.value,
+        extra={
+            "event": "candidate.promotion",
+            "outcome": result.outcome,
+            "candidate_id": candidate_id,
+            "fact_id": result.fact_id,
+        },
+    )
+    return result
+
+
+async def _promote_in_transaction(
+    conn: aiosqlite.Connection,
+    candidate_id: int,
+    person_id: int,
+    *,
+    correlation_id: UUID,
+    now: datetime,
+) -> PromotionResult:
+    """Run steps 1 to 5 inside the transaction the caller opened."""
+    candidate = await get_candidate_in_transaction(conn, candidate_id)
+    if (
+        candidate is None
+        or candidate.subject_person_id != person_id
+        or candidate.status is not CandidateStatus.OFFERED
+        or candidate.value_key is None
+        or candidate.value_text is None
+        or candidate.expires_at <= iso_utc(now)
+    ):
+        return PromotionResult(PromotionOutcome.NOT_OFFERED)
+    definition = resolve_predicate(candidate.predicate)
+    if definition is None:
+        return PromotionResult(PromotionOutcome.NOT_OFFERED)
+
+    opposite = _OPPOSITE.get(definition.canonical_id)
+    opposite_definition = resolve_predicate(opposite) if opposite else None
+    if opposite_definition is not None:
+        clashing = await get_active_literal_facts(
+            subject_entity_id=person_id, definition=opposite_definition
+        )
+        if any(comparison_key(fact.value_text) == candidate.value_key for fact in clashing):
+            await _resolve(
+                conn, candidate_id, person_id, CandidateStatus.REJECTED, correlation_id, now, None
+            )
+            return PromotionResult(PromotionOutcome.CONTRADICTION)
+
+    active = await get_active_literal_facts(subject_entity_id=person_id, definition=definition)
+    present = next(
+        (fact for fact in active if comparison_key(fact.value_text) == candidate.value_key), None
+    )
+    if present is not None:
+        await _resolve(
+            conn,
+            candidate_id,
+            person_id,
+            CandidateStatus.CONFIRMED,
+            correlation_id,
+            now,
+            present.id,
+        )
+        return PromotionResult(PromotionOutcome.ALREADY_PRESENT, present.id)
+
+    fact = await assert_literal_fact(
+        subject_entity_id=person_id,
+        definition=definition,
+        value=candidate.value_text,
+        confidence=1.0,
+        source_memory_id=None,
+        asserted_at=candidate.proposed_at,
+        visibility=CANDIDATE_VISIBILITY.value,
+        sensitivity=CANDIDATE_SENSITIVITY.value,
+        confirmed_by_entity_id=person_id,
+        confirmed_at=iso_utc(now),
+        manage_transaction=False,
+    )
+    await _resolve(
+        conn, candidate_id, person_id, CandidateStatus.CONFIRMED, correlation_id, now, fact.id
+    )
+    return PromotionResult(PromotionOutcome.PROMOTED, fact.id)
+
+
+async def _resolve(
+    conn: aiosqlite.Connection,
+    candidate_id: int,
+    person_id: int,
+    to: CandidateStatus,
+    correlation_id: UUID,
+    now: datetime,
+    fact_id: int | None,
+) -> None:
+    """Resolve the candidate in the open transaction; a lost compare-and-set rolls it back."""
+    resolved = await resolve_candidate_in_transaction(
+        conn,
+        candidate_id,
+        person_id,
+        to=to,
+        correlation_id=correlation_id,
+        now=now,
+        promoted_fact_id=fact_id,
+    )
+    if not resolved:
+        raise RuntimeError("candidate resolution lost its compare-and-set inside the transaction")
```

- [ ] **Step 4: Run to see them pass, then lint and types.**
- [ ] **Step 5: Commit** `feat(server): add the canonical memory writer (plan 0062)`; check `git log -1`.

---

## Task 11: The background proposal and its limits

**Files:**
- Create: `server/src/server/memory/candidate_limits.py`, `server/src/server/memory/candidate_proposal.py`
- Modify: `server/src/server/memory/entity_labels.py`
- Test: new `tests/integration/test_candidate_proposal.py`; modified `tests/conftest.py`

**Interfaces:**
- Consumes: Tasks 2, 3, 4, 6, 8 and 9.
- Produces: `candidate_limits.{ExtractionLimiter, limiter}` (`busy`, `try_acquire() ->
  CandidateReason | None`, `release()`, `reset()`; a monotonic injectable clock); `ProposalOutcome(
  stored, reasons)` and `async propose_candidates(client, message, actor, *, event, wav_bytes,
  channel, extract=..., verify=..., read_names=..., enrolled=..., clock=..., policy=..., audit=...)`
  (never raises); `entity_labels.list_known_names()`; an autouse fixture that resets the limiter.

Order, cheapest first: kill-switch, gate, token-free face actor, nothing in flight, voice of the
clip, budget and slot, model (once), classifier, then per accepted triple the enrolment re-check,
the policy with its audit row, and the insert. The slot is released in `finally`, so a failure or a
cancellation frees it; a failed extraction logs the class and never the message.

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/tests/conftest.py b/tests/conftest.py
--- a/tests/conftest.py
+++ b/tests/conftest.py
@@ -15,6 +15,7 @@ from server.cognition.owner_authentication import owner_unlock_service
 from server.conversation_log import CONVERSATION_LOGGER_NAME as SERVER_CONVERSATION_LOGGER
 from server.main import app
 from server.memory import continuity
+from server.memory.candidate_limits import limiter as candidate_limiter
 from server.resources import AppResources
 from server.settings import settings

@@ -31,6 +32,18 @@ def _continuity_session_empty() -> Generator[None, None, None]:
     continuity.reset()


+@pytest.fixture(autouse=True)
+def _candidate_extraction_limiter_idle() -> Generator[None, None, None]:
+    """Start and finish every test with an idle extraction limiter (ADR 0021).
+
+    The limiter is process-wide (one extraction at a time, so many per hour), so a test that
+    leaves a slot taken or an hour spent would otherwise fail the next test of its worker.
+    """
+    candidate_limiter.reset()
+    yield
+    candidate_limiter.reset()
+
+
 @pytest.fixture(autouse=True)
 def _memory_candidates_off(monkeypatch: pytest.MonkeyPatch) -> None:
     """Start every test with the candidate kill-switch off (ADR 0021).
diff --git a/tests/integration/test_candidate_proposal.py b/tests/integration/test_candidate_proposal.py
new file mode 100644
--- /dev/null
+++ b/tests/integration/test_candidate_proposal.py
@@ -0,0 +1,451 @@
+"""Integration tests for the background proposal (ADR 0021 decisions 3, 4, 7, 10)."""
+
+from __future__ import annotations
+
+import asyncio
+from datetime import UTC, datetime, timedelta
+import logging
+from typing import TYPE_CHECKING
+from unittest.mock import AsyncMock
+from uuid import UUID, uuid4
+
+import httpx
+import pytest
+from server.cognition.identity import (
+    ActivePersonContext,
+    HouseholdRole,
+    IdentityEvidence,
+    IdentityEvidenceSource,
+    PersonRecord,
+    resolve_active_person,
+)
+from server.cognition.models import CognitiveEvent, Confidence, ConfidenceBasis
+from server.cognition.response_plan import TextTurnPayload
+from server.exceptions import LLMError
+from server.memory import candidates
+from server.memory.biometric_consent import grant_face_consent
+from server.memory.candidate_limits import limiter
+from server.memory.candidate_proposal import ProposalOutcome, propose_candidates
+from server.memory.candidate_types import CandidateChannel, CandidateReason, RawCandidate
+from server.memory.declarative import upsert_entity
+from server.memory.entity_labels import list_known_names
+from server.memory.household_authorization import record_authorization_decision
+from server.memory.voice_consent import grant_voice_consent
+from server.settings import settings
+
+from server import db
+
+if TYPE_CHECKING:
+    from collections.abc import AsyncIterator
+    from pathlib import Path
+
+pytestmark = pytest.mark.integration
+
+_NOW = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
+_WAV = b"RIFF-canary-clip"
+_CORRELATION = UUID(int=4242)
+
+
+def _evidence(source: IdentityEvidenceSource, person_id: int) -> IdentityEvidence:
+    return IdentityEvidence(
+        evidence_id=uuid4(),
+        source=source,
+        candidate_person_id=person_id,
+        confidence=Confidence(score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=False),
+        observed_at=_NOW - timedelta(seconds=1),
+        reference="canary",
+        expires_at=_NOW + timedelta(minutes=5)
+        if source is IdentityEvidenceSource.LOCAL_UNLOCK
+        else None,
+        grant_scope="personal_protected_read"
+        if source is IdentityEvidenceSource.LOCAL_UNLOCK
+        else None,
+        grant_spent=source is IdentityEvidenceSource.LOCAL_UNLOCK,
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
+def _event() -> CognitiveEvent[TextTurnPayload]:
+    return CognitiveEvent(
+        event_id=uuid4(),
+        schema_version=1,
+        event_type="text.turn",
+        occurred_at=_NOW,
+        recorded_at=_NOW,
+        source="audio.transcribe",
+        correlation_id=_CORRELATION,
+        causation_id=None,
+        subject_id=None,
+        payload=TextTurnPayload(message="canary", conversation_id="canary"),
+    )
+
+
+@pytest.fixture
+async def owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[int]:
+    monkeypatch.setattr(settings, "brain_db_path", tmp_path / "proposal.db")
+    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
+    limiter.reset()
+    db._conn = None
+    await db.open_db()
+    await db.run_migrations()
+    owner_id = await upsert_entity(name="Canary Owner", type="person")
+    await grant_face_consent(owner_id)
+    await grant_voice_consent(owner_id)
+    yield owner_id
+    await db.close_db()
+    db._conn = None
+    limiter.reset()
+
+
+class _Seams:
+    """The doubles of one proposal: what the voice check and the model say."""
+
+    def __init__(
+        self,
+        owner_id: int,
+        *triples: RawCandidate,
+        strong: bool = True,
+        extract_error: Exception | None = None,
+    ) -> None:
+        self.owner_id = owner_id
+        self.extract = AsyncMock(side_effect=extract_error, return_value=triples)
+        self.strong_actor = _actor(
+            owner_id, IdentityEvidenceSource.FACE, IdentityEvidenceSource.VOICE
+        )
+        self.verify = AsyncMock(return_value=self.strong_actor if strong else None)
+        self.audit = AsyncMock()
+        self.client = httpx.AsyncClient()
+
+    async def run(
+        self,
+        message: str = "me gusta el mate",
+        actor: ActivePersonContext | None = None,
+        **overrides: object,
+    ) -> ProposalOutcome:
+        kwargs: dict[str, object] = {
+            "event": _event(),
+            "wav_bytes": _WAV,
+            "channel": CandidateChannel.VOICE_CLASSIC,
+            "extract": self.extract,
+            "verify": self.verify,
+            "audit": self.audit,
+            "clock": lambda: _NOW,
+        }
+        kwargs.update(overrides)
+        return await propose_candidates(
+            self.client,
+            message,
+            actor or _actor(self.owner_id),
+            **kwargs,  # type: ignore[arg-type]
+        )
+
+
+def _taste(obj: str = "el mate", predicate: str = "likes", topic: str = "drink") -> RawCandidate:
+    return RawCandidate(predicate=predicate, object=obj, topic=topic)
+
+
+async def _live() -> list[tuple[str, str]]:
+    cursor = await db.get_conn().execute(
+        "SELECT predicate, value_text FROM memory_candidates WHERE status IN ('proposed','offered')"
+    )
+    rows = [(str(r[0]), str(r[1])) for r in await cursor.fetchall()]
+    await cursor.close()
+    return rows
+
+
+async def test_a_taste_said_with_face_and_voice_becomes_one_proposed_candidate(owner: int) -> None:
+    seams = _Seams(owner, _taste())
+
+    outcome = await seams.run()
+
+    assert outcome == ProposalOutcome(stored=1, reasons=())
+    assert await _live() == [("likes", "el mate")]
+    seams.extract.assert_awaited_once()
+    assert seams.extract.call_args.args[1] == "me gusta el mate"
+    seams.verify.assert_awaited_once()
+    assert seams.verify.call_args.kwargs["wav_bytes"] == _WAV
+    seams.audit.assert_awaited_once()
+    assert seams.audit.call_args.args[0].action.value == "propose_personal_memory"
+    stored = await candidates.get_candidate(1)
+    assert stored is not None
+    assert stored.source_correlation_id == str(_CORRELATION)
+    assert stored.subject_person_id == stored.asserted_by_person_id == owner
+
+
+async def test_the_real_audit_row_is_written_for_the_proposal(owner: int) -> None:
+    seams = _Seams(owner, _taste())
+
+    await seams.run(audit=record_authorization_decision)
+
+    cursor = await db.get_conn().execute(
+        "SELECT action, decision, correlation_id, data_categories FROM authorization_audit_events"
+    )
+    rows = list(await cursor.fetchall())
+    await cursor.close()
+    assert rows == [("propose_personal_memory", "allowed", str(_CORRELATION), "normal,personal")]
+
+
+@pytest.mark.parametrize(
+    "message, reason",
+    [
+        ("hola robot", CandidateReason.GATE_NO_MATCH),
+        ("¿te gusta el mate?", CandidateReason.NOT_A_TASTE),
+        (
+            "Prefiero que no menciones mi mudanza reciente delante de visitas",
+            CandidateReason.NOT_A_TASTE,
+        ),
+        ("prefiero no hablar de mi divorcio", CandidateReason.NEGATION_UNSUPPORTED),
+    ],
+)
+async def test_a_text_the_gate_refuses_costs_no_voice_check_and_no_model_call(
+    owner: int, message: str, reason: CandidateReason
+) -> None:
+    seams = _Seams(owner, _taste())
+
+    outcome = await seams.run(message)
+
+    assert outcome == ProposalOutcome(reasons=(reason,))
+    seams.verify.assert_not_awaited()
+    seams.extract.assert_not_awaited()
+    assert await _live() == []
+
+
+@pytest.mark.parametrize(
+    "sources",
+    [
+        (IdentityEvidenceSource.LOCAL_UNLOCK,),
+        (IdentityEvidenceSource.FACE, IdentityEvidenceSource.LOCAL_UNLOCK),
+        (IdentityEvidenceSource.MANUAL,),
+        (IdentityEvidenceSource.VOICE,),
+    ],
+)
+async def test_an_actor_that_is_not_a_token_free_face_never_reaches_the_voice_or_the_model(
+    owner: int, sources: tuple[IdentityEvidenceSource, ...]
+) -> None:
+    seams = _Seams(owner, _taste())
+
+    outcome = await seams.run(actor=_actor(owner, *sources))
+
+    assert outcome.reasons == (CandidateReason.STRONG_UNREACHABLE,)
+    seams.verify.assert_not_awaited()
+    seams.extract.assert_not_awaited()
+
+
+async def test_a_voice_that_is_not_verified_costs_no_model_call(owner: int) -> None:
+    seams = _Seams(owner, _taste(), strong=False)
+
+    outcome = await seams.run()
+
+    assert outcome.reasons == (CandidateReason.STRONG_UNREACHABLE,)
+    seams.extract.assert_not_awaited()
+    assert await _live() == []
+
+
+async def test_a_failing_voice_check_fails_closed(owner: int) -> None:
+    seams = _Seams(owner, _taste())
+    seams.verify.side_effect = RuntimeError("model exploded")
+
+    outcome = await seams.run()
+
+    assert outcome.reasons == (CandidateReason.DENIED,)
+    seams.extract.assert_not_awaited()
+
+
+async def test_the_kill_switch_does_nothing_at_all(
+    owner: int, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
+    seams = _Seams(owner, _taste())
+
+    await seams.run()
+
+    seams.verify.assert_not_awaited()
+    seams.extract.assert_not_awaited()
+
+
+async def test_a_second_matching_turn_while_one_extracts_is_dropped_as_busy(owner: int) -> None:
+    release = asyncio.Event()
+    started = asyncio.Event()
+    first = _Seams(owner, _taste())
+
+    async def slow(*_args: object) -> tuple[RawCandidate, ...]:
+        started.set()
+        await release.wait()
+        return (_taste(),)
+
+    first.extract = AsyncMock(side_effect=slow)
+    second = _Seams(owner, _taste("el jazz", topic="music"))
+    running = asyncio.create_task(first.run())
+    await started.wait()
+
+    dropped = await second.run("me gusta el jazz")
+    release.set()
+    done = await running
+
+    assert dropped.reasons == (CandidateReason.BUSY,)
+    second.verify.assert_not_awaited()
+    second.extract.assert_not_awaited()
+    assert done.stored == 1
+    assert not limiter.busy
+
+
+async def test_the_hourly_budget_is_spent_then_returns_with_the_clock(
+    owner: int, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    monkeypatch.setattr(settings, "memory_candidate_extractions_per_hour", 1)
+    fake = {"now": 1000.0}
+    monkeypatch.setattr(limiter, "_clock", lambda: fake["now"])
+    seams = _Seams(owner, _taste())
+
+    first = await seams.run()
+    second = await seams.run("me gusta el mate verde")
+    fake["now"] += 3600.0
+    third = await seams.run("me gusta el mate cocido")
+
+    assert first.stored == 1
+    assert second.reasons == (CandidateReason.BUDGET,)
+    assert third.reasons != (CandidateReason.BUDGET,)
+    assert seams.extract.await_count == 2
+
+
+@pytest.mark.parametrize(
+    "error", [LLMError("bad json"), httpx.ConnectError("zumo de pomelo is down")]
+)
+async def test_a_failed_extraction_stores_nothing_and_frees_the_slot_without_logging_the_message(
+    owner: int, error: Exception, caplog: pytest.LogCaptureFixture
+) -> None:
+    seams = _Seams(owner, extract_error=error)
+
+    with caplog.at_level(logging.DEBUG, logger="server"):
+        outcome = await seams.run()
+
+    assert outcome.reasons == (CandidateReason.DENIED,)
+    assert await _live() == []
+    assert not limiter.busy
+    assert "pomelo" not in caplog.text
+    assert "bad json" not in caplog.text
+
+
+async def test_cancelling_the_extraction_frees_the_slot(owner: int) -> None:
+    started = asyncio.Event()
+    seams = _Seams(owner, _taste())
+
+    async def forever(*_args: object) -> tuple[RawCandidate, ...]:
+        started.set()
+        await asyncio.Event().wait()
+        return ()
+
+    seams.extract = AsyncMock(side_effect=forever)
+    task = asyncio.create_task(seams.run())
+    await started.wait()
+    assert limiter.busy
+
+    task.cancel()
+    with pytest.raises(asyncio.CancelledError):
+        await task
+
+    assert not limiter.busy
+
+
+@pytest.mark.parametrize(
+    "triple, message, reason",
+    [
+        (_taste("mi hijo", topic="food"), "me gusta mi hijo", CandidateReason.SENSITIVE_TOPIC),
+        (_taste("el té", topic="drink"), "me gusta el mate", CandidateReason.NOT_GROUNDED),
+        (
+            _taste(predicate="lives_in", topic="food"),
+            "me gusta el mate",
+            CandidateReason.GATE_MISMATCH,
+        ),
+        (_taste(topic="health"), "me gusta el mate", CandidateReason.SENSITIVE_TOPIC),
+        (_taste("Tomasito", topic="animal"), "me gusta Tomasito", CandidateReason.SENSITIVE_TOPIC),
+    ],
+)
+async def test_what_the_classifier_drops_is_never_stored(
+    owner: int, triple: RawCandidate, message: str, reason: CandidateReason
+) -> None:
+    await upsert_entity(name="Tomasito", type="other")
+    seams = _Seams(owner, triple)
+
+    outcome = await seams.run(message)
+
+    assert outcome == ProposalOutcome(stored=0, reasons=(reason,))
+    assert await _live() == []
+    seams.audit.assert_not_awaited()
+
+
+async def test_only_the_triples_the_policy_allows_are_stored(owner: int) -> None:
+    seams = _Seams(owner, _taste("el mate"), _taste("el jazz", topic="music"))
+    seams.audit.side_effect = [None, RuntimeError("down")]
+
+    outcome = await seams.run("me gusta el mate y me gusta el jazz")
+
+    assert outcome.stored == 1
+    assert outcome.reasons == (CandidateReason.DENIED,)
+    assert await _live() == [("likes", "el mate")]
+
+
+async def test_enrolment_is_checked_again_right_before_the_store(owner: int) -> None:
+    seams = _Seams(owner, _taste())
+
+    outcome = await seams.run(enrolled=AsyncMock(return_value=False))
+
+    assert outcome.reasons == (CandidateReason.STRONG_UNREACHABLE,)
+    assert await _live() == []
+    seams.audit.assert_not_awaited()  # no "allowed" row for something that was not stored
+
+
+async def test_a_repeated_statement_and_the_cap_are_reported_not_raised(
+    owner: int, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    monkeypatch.setattr(settings, "memory_candidate_max_live", 1)
+    seams = _Seams(owner, _taste())
+    await seams.run()
+    seams.extract.return_value = (_taste(),)
+
+    again = await seams.run()
+    seams.extract.return_value = (_taste("el jazz", topic="music"),)
+    other = await seams.run("me gusta el jazz")
+
+    assert again.reasons == (CandidateReason.DUPLICATE,)
+    assert other.reasons == (CandidateReason.CAPACITY,)
+    assert await _live() == [("likes", "el mate")]
+
+
+async def test_the_extractor_sees_only_the_users_words(owner: int) -> None:
+    seams = _Seams(owner, _taste())
+
+    await seams.run("me gusta el mate")
+
+    assert seams.extract.call_args.args[1] == "me gusta el mate"
+    assert len(seams.extract.call_args.args) == 2  # a client and the user's text, nothing else
+
+
+async def test_no_value_reaches_a_log_line(owner: int, caplog: pytest.LogCaptureFixture) -> None:
+    seams = _Seams(owner, _taste("el zumo de pomelo", topic="drink"))
+
+    with caplog.at_level(logging.DEBUG, logger="server"):
+        outcome = await seams.run("me gusta el zumo de pomelo")
+
+    assert outcome.stored == 1
+    assert "pomelo" not in caplog.text
+
+
+async def test_the_known_names_are_people_and_pets_with_their_aliases(owner: int) -> None:
+    await upsert_entity(name="Tomasito", type="other", aliases=["Tomi"])
+    await upsert_entity(name="Cafetera", type="object")
+
+    names = await list_known_names()
+
+    assert {"Canary Owner", "Tomasito", "Tomi"} <= names
+    assert "Cafetera" not in names
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/integration/test_candidate_proposal.py -q -p no:cacheprovider`
  Expected RED: `tests/conftest.py` now imports the limiter, so the suite fails to start with
  `ModuleNotFoundError: No module named 'server.memory.candidate_limits'` (pytest exit code 4).
- [ ] **Step 3: Implement:**

```diff
diff --git a/server/src/server/memory/candidate_limits.py b/server/src/server/memory/candidate_limits.py
new file mode 100644
--- /dev/null
+++ b/server/src/server/memory/candidate_limits.py
@@ -0,0 +1,79 @@
+"""How much candidate extraction one process may run: one at a time, and so many per hour.
+
+Extraction is a local-model call of tens of seconds on the shared laptop (ADR 0021 decision 4).
+Two limits keep it from taking the machine from the conversation:
+
+* **one in flight**: a matching turn that finds an extraction running is dropped (``busy``), not
+  queued; a restated taste is easy, a growing queue of 40-second calls is not;
+* **a rolling hourly budget** (``MEMORY_CANDIDATE_EXTRACTIONS_PER_HOUR``) of extraction starts.
+
+Both live in process memory, like the session slot (one worker, ADR 0010). The clock is
+injectable so the hour can be tested without waiting.
+"""
+
+from __future__ import annotations
+
+from collections import deque
+import time
+from typing import TYPE_CHECKING
+
+from server.memory.candidate_types import CandidateReason
+from server.settings import settings
+
+if TYPE_CHECKING:
+    from collections.abc import Callable
+
+__all__ = ["ExtractionLimiter", "limiter"]
+
+_HOUR_SECONDS = 3600.0
+
+
+class ExtractionLimiter:
+    """One extraction at a time and a rolling hourly budget of starts."""
+
+    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
+        """Create an idle limiter.
+
+        Args:
+            clock: Monotonic seconds; injectable so the hour needs no real waiting.
+        """
+        self._clock = clock
+        self._busy = False
+        self._starts: deque[float] = deque()
+
+    @property
+    def busy(self) -> bool:
+        """Whether an extraction is in flight."""
+        return self._busy
+
+    def try_acquire(self) -> CandidateReason | None:
+        """Take the slot for one extraction, if it is free and the hour has budget left.
+
+        Returns:
+            ``None`` when the slot is now held (the caller must ``release`` it), ``BUSY`` when
+            another extraction is running, ``BUDGET`` when the rolling hour is spent. There is
+            no ``await`` between the check and the take, so two turns cannot both pass.
+        """
+        if self._busy:
+            return CandidateReason.BUSY
+        now = self._clock()
+        while self._starts and now - self._starts[0] >= _HOUR_SECONDS:
+            self._starts.popleft()
+        if len(self._starts) >= settings.memory_candidate_extractions_per_hour:
+            return CandidateReason.BUDGET
+        self._busy = True
+        self._starts.append(now)
+        return None
+
+    def release(self) -> None:
+        """Free the slot (idempotent). The start stays counted against the hour."""
+        self._busy = False
+
+    def reset(self) -> None:
+        """Forget the slot and the hour (used by tests)."""
+        self._busy = False
+        self._starts.clear()
+
+
+#: The process-wide limiter.
+limiter = ExtractionLimiter()
diff --git a/server/src/server/memory/candidate_proposal.py b/server/src/server/memory/candidate_proposal.py
new file mode 100644
--- /dev/null
+++ b/server/src/server/memory/candidate_proposal.py
@@ -0,0 +1,307 @@
+"""Propose memory candidates from one successful generic voice turn (ADR 0021 decisions 3, 4, 7, 10).
+
+This replaces ``consolidate_turn``. It runs as a background task after the reply was sent and
+never touches the user's request: every failure is swallowed and logged as a closed reason.
+
+The order is deliberate, cheapest and most protective first:
+
+1. the **gate** (pure) — does the text declare a first-person taste at all?
+2. a **face actor** with no token, and no extraction already in flight;
+3. the **voice** of this turn's own clip, for the person the face named — no clip, a clip below
+   the floor, another voice or a backend failure means no candidate (the firewall rule);
+4. the **limiter** — one extraction at a time, so many per hour;
+5. the **extractor** — one model call that sees only the user's words, no retry;
+6. the **classifier** — each triple is accepted or dropped by a pure function;
+7. per accepted triple, a re-check that both consents are still active (the model call took a
+   while), the **policy** (``propose_personal_memory``) with its audit row, and the **store**.
+
+Audio contract for the clip: WAV, 16 000 Hz, mono, signed int16. It is held in memory only.
+Logs carry ids, the predicate, a status and closed reasons — never a value, a transcript or an
+exception message.
+"""
+
+from __future__ import annotations
+
+from collections.abc import Awaitable, Callable
+from dataclasses import dataclass, field
+import logging
+from typing import TYPE_CHECKING
+
+import httpx
+
+from server.cognition.authorization import evaluate_authorization
+from server.cognition.clock import utc_now
+from server.cognition.strong_actor import is_face_actor, verify_face_and_voice
+from server.exceptions import BrainMemoryError, LLMError
+from server.memory.candidate_classifier import classify
+from server.memory.candidate_extraction import extract_candidates
+from server.memory.candidate_limits import limiter
+from server.memory.candidate_policy import CandidateStep, authorize_step
+from server.memory.candidate_types import (
+    CandidateChannel,
+    CandidateReason,
+    GateMatch,
+    ProposedCandidate,
+    RawCandidate,
+)
+from server.memory.candidates import InsertStatus, insert_candidate
+from server.memory.enrollment import is_enrolled_for_strong
+from server.memory.entity_labels import list_known_names
+from server.memory.household_authorization import record_authorization_decision
+from server.memory.preference_gate import match_preference
+from server.settings import settings
+
+if TYPE_CHECKING:
+    from datetime import datetime
+
+    from server.cognition.identity import ActivePersonContext
+    from server.cognition.models import CognitiveEvent
+    from server.cognition.response_plan import TextTurnPayload
+    from server.memory.candidate_policy import AuditWriter, PolicyEvaluator
+
+logger = logging.getLogger(__name__)
+
+__all__ = ["ProposalOutcome", "propose_candidates"]
+
+type Extractor = Callable[[httpx.AsyncClient, str], Awaitable[tuple[RawCandidate, ...]]]
+type VoiceVerifier = Callable[..., Awaitable[ActivePersonContext | None]]
+type NameReader = Callable[[], Awaitable[frozenset[str]]]
+type EnrollmentReader = Callable[[int], Awaitable[bool]]
+type Clock = Callable[[], datetime]
+
+
+# What an insert that did not store a candidate is reported as (`INSERTED` is absent).
+_INSERT_REASONS = {
+    InsertStatus.DUPLICATE: CandidateReason.DUPLICATE,
+    InsertStatus.CAPACITY: CandidateReason.CAPACITY,
+    InsertStatus.DISABLED: CandidateReason.DENIED,
+}
+
+
+@dataclass(frozen=True)
+class ProposalOutcome:
+    """What one proposal attempt did, in closed terms.
+
+    Attributes:
+        stored: Candidates inserted.
+        reasons: The closed reason of every triple or step that did not become a candidate.
+    """
+
+    stored: int = 0
+    reasons: tuple[CandidateReason, ...] = field(default=())
+
+
+def _dropped(reason: CandidateReason) -> ProposalOutcome:
+    logger.info(
+        "Candidate proposal: dropped (%s)",
+        reason.value,
+        extra={"event": "candidate.proposal", "stored": 0, "reason": reason},
+    )
+    return ProposalOutcome(reasons=(reason,))
+
+
+async def propose_candidates(
+    client: httpx.AsyncClient,
+    message: str,
+    actor: ActivePersonContext,
+    *,
+    event: CognitiveEvent[TextTurnPayload],
+    wav_bytes: bytes | None,
+    channel: CandidateChannel,
+    extract: Extractor = extract_candidates,
+    verify: VoiceVerifier = verify_face_and_voice,
+    read_names: NameReader = list_known_names,
+    enrolled: EnrollmentReader = is_enrolled_for_strong,
+    clock: Clock = utc_now,
+    policy: PolicyEvaluator = evaluate_authorization,
+    audit: AuditWriter = record_authorization_decision,
+) -> ProposalOutcome:
+    """Turn one generic voice turn into at most three stored candidates.
+
+    Args:
+        client: Shared, lifecycle-owned HTTP client (Plan 0039), for the extractor.
+        message: The user's own transcript of this turn — never the assistant's reply.
+        actor: The face-identified actor of the turn.
+        event: The turn's event (its correlation id joins audit rows to candidates).
+        wav_bytes: The turn's own clip — WAV, 16 000 Hz, mono, int16 — or ``None``.
+        channel: The voice route this came from.
+        extract: The extractor seam; tests inject doubles.
+        verify: The voice-check seam; tests inject doubles.
+        read_names: Reader of the names the household knows; tests inject doubles.
+        enrolled: Reader of the composite enrolment; tests inject doubles.
+        clock: Source of every timestamp the store keeps.
+        policy: The pure policy evaluator; tests inject doubles.
+        audit: The audit writer; tests inject doubles.
+
+    Returns:
+        The closed outcome. Never raises: any failure is logged by class and reported as a
+        dropped step, because this runs after the user already got their reply.
+    """
+    try:
+        return await _propose(
+            client,
+            message,
+            actor,
+            event=event,
+            wav_bytes=wav_bytes,
+            channel=channel,
+            extract=extract,
+            verify=verify,
+            read_names=read_names,
+            enrolled=enrolled,
+            clock=clock,
+            policy=policy,
+            audit=audit,
+        )
+    except Exception as exc:  # background boundary: nothing may reach the user's request
+        logger.warning(
+            "Candidate proposal failed (%s)",
+            type(exc).__name__,
+            extra={"event": "candidate.proposal_error", "error_type": type(exc).__name__},
+        )
+        return ProposalOutcome(reasons=(CandidateReason.DENIED,))
+
+
+def _refusal_before_voice(
+    message: str, actor: ActivePersonContext
+) -> tuple[tuple[GateMatch, ...], CandidateReason | None]:
+    """Apply the free checks: kill-switch, gate, a token-free face actor, nothing in flight."""
+    if not settings.memory_candidates_enabled:
+        return (), CandidateReason.DENIED
+    gate = match_preference(message)
+    if gate.reason is not None:
+        return (), gate.reason
+    if not is_face_actor(actor):
+        return (), CandidateReason.STRONG_UNREACHABLE
+    if limiter.busy:
+        return (), CandidateReason.BUSY
+    return gate.matches, None
+
+
+async def _extract_once(
+    client: httpx.AsyncClient, message: str, extract: Extractor
+) -> tuple[RawCandidate, ...] | CandidateReason:
+    """Take the extraction slot, call the model once (no retry) and always release the slot."""
+    refused = limiter.try_acquire()
+    if refused is not None:
+        return refused
+    try:
+        return await extract(client, message)
+    except (LLMError, httpx.HTTPError) as exc:
+        logger.warning("Candidate extraction failed (%s)", type(exc).__name__)
+        return CandidateReason.DENIED
+    finally:
+        limiter.release()
+
+
+async def _propose(
+    client: httpx.AsyncClient,
+    message: str,
+    actor: ActivePersonContext,
+    *,
+    event: CognitiveEvent[TextTurnPayload],
+    wav_bytes: bytes | None,
+    channel: CandidateChannel,
+    extract: Extractor,
+    verify: VoiceVerifier,
+    read_names: NameReader,
+    enrolled: EnrollmentReader,
+    clock: Clock,
+    policy: PolicyEvaluator,
+    audit: AuditWriter,
+) -> ProposalOutcome:
+    """Run the steps in order; each early return is a closed reason."""
+    matches, refusal = _refusal_before_voice(message, actor)
+    if refusal is not None:
+        return _dropped(refusal)
+    strong = await verify(actor, wav_bytes=wav_bytes, event=event)
+    if strong is None or strong.person_id is None:
+        return _dropped(CandidateReason.STRONG_UNREACHABLE)
+    raw = await _extract_once(client, message, extract)
+    if isinstance(raw, CandidateReason):
+        return _dropped(raw)
+    known = await read_names()
+    stored = 0
+    reasons: list[CandidateReason] = []
+    for triple in raw:
+        verdict = classify(
+            strong,
+            triple,
+            message,
+            matches=matches,
+            known_person_names=known,
+        )
+        if isinstance(verdict, CandidateReason):
+            reasons.append(verdict)
+            continue
+        outcome = await _store(
+            verdict,
+            strong,
+            channel=channel,
+            event=event,
+            enrolled=enrolled,
+            clock=clock,
+            policy=policy,
+            audit=audit,
+        )
+        if outcome is None:
+            stored += 1
+        else:
+            reasons.append(outcome)
+    logger.info(
+        "Candidate proposal: stored=%d dropped=%d",
+        stored,
+        len(reasons),
+        extra={
+            "event": "candidate.proposal",
+            "stored": stored,
+            "reasons": [reason.value for reason in reasons],
+            "channel": channel,
+        },
+    )
+    return ProposalOutcome(stored=stored, reasons=tuple(reasons))
+
+
+async def _store(
+    proposal: ProposedCandidate,
+    strong: ActivePersonContext,
+    *,
+    channel: CandidateChannel,
+    event: CognitiveEvent[TextTurnPayload],
+    enrolled: EnrollmentReader,
+    clock: Clock,
+    policy: PolicyEvaluator,
+    audit: AuditWriter,
+) -> CandidateReason | None:
+    """Policy, audit, enrolment re-check, then insert. ``None`` means it was stored."""
+    person_id = strong.person_id
+    if person_id is None:
+        return CandidateReason.DENIED
+    # The model call took a while: a consent revoked meanwhile stops the write, and it is read
+    # before the audit row so the log never says "allowed" for something that was not stored.
+    try:
+        still_enrolled = await enrolled(person_id)
+    except BrainMemoryError:
+        still_enrolled = False
+    if not still_enrolled:
+        return CandidateReason.STRONG_UNREACHABLE
+    allowed = await authorize_step(
+        CandidateStep.PROPOSE,
+        actor=strong,
+        subject_person_id=person_id,
+        correlation_id=event.correlation_id,
+        now=clock(),
+        policy=policy,
+        audit=audit,
+    )
+    if not allowed.allowed:
+        return allowed.reason or CandidateReason.DENIED
+    result = await insert_candidate(
+        proposal,
+        subject_person_id=person_id,
+        asserted_by_person_id=person_id,
+        channel=channel,
+        correlation_id=event.correlation_id,
+        now=clock(),
+    )
+    return _INSERT_REASONS.get(result.status)
diff --git a/server/src/server/memory/entity_labels.py b/server/src/server/memory/entity_labels.py
--- a/server/src/server/memory/entity_labels.py
+++ b/server/src/server/memory/entity_labels.py
@@ -1,10 +1,12 @@
 """Exact entity labels for authorized P0.5-B2 relationship results."""

+import json
+
 from pydantic import BaseModel, ConfigDict

 from server.db import get_conn

-__all__ = ["EntityLabel", "get_person_label"]
+__all__ = ["EntityLabel", "get_person_label", "list_known_names"]


 class EntityLabel(BaseModel):
@@ -34,3 +36,32 @@ async def get_person_label(*, entity_id: int) -> EntityLabel | None:
     if row is None:
         return None
     return EntityLabel(entity_id=int(row[0]), display_name=str(row[1]))
+
+
+async def list_known_names() -> frozenset[str]:
+    """Return every name and alias of the people and pets the household knows.
+
+    Used by the candidate classifier to refuse an object that is somebody's name (ADR 0021
+    decision 5); the folding is the classifier's, so the names are returned as stored.
+
+    Returns:
+        The names and aliases of every ``person`` entity and of every ``other`` entity (pets).
+
+    Raises:
+        BrainMemoryError: If the database is not open.
+    """
+    cursor = await get_conn().execute(
+        "SELECT name, aliases FROM entities WHERE type IN ('person', 'other')"
+    )
+    rows = list(await cursor.fetchall())
+    await cursor.close()
+    names: set[str] = set()
+    for name, aliases in rows:
+        names.add(str(name))
+        try:
+            decoded = json.loads(str(aliases))
+        except ValueError:
+            continue
+        if isinstance(decoded, list):
+            names.update(str(alias) for alias in decoded if isinstance(alias, str))
+    return frozenset(names)
```

- [ ] **Step 4: Run to see them pass, then lint and types.**
- [ ] **Step 5: Commit** `feat(server): propose candidates in the background (plan 0062)`; check `git log -1`.

---

## Task 12: Reclaim, void and scrub

**Files:**
- Create: `scripts/scrub_candidates.py`
- Modify: `scripts/reset_db.ps1`, `server/src/server/main.py`, `server/src/server/memory/retention.py`
- Test: new `tests/integration/test_candidates_startup.py`, `tests/unit/test_scrub_candidates.py`; modified `tests/integration/test_retention.py`

**Interfaces:**
- Consumes: Task 6.
- Produces: the hourly retention job expires lapsed candidates in its own transaction and truncates
  the log, whatever the kill-switch says; the lifespan calls `candidates.reset_for_startup(utc_now(),
  enabled=cfg.memory_candidates_enabled)` after the migrations and before retention starts;
  `scripts/scrub_candidates.py` (`scrub(db_path) -> int`, exit 1 when it cannot scrub or when a
  reader pins the log so it cannot be truncated) and
  `scripts/reset_db.ps1` runs it before the copy and refuses to copy if it fails (D-8).

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/tests/integration/test_candidates_startup.py b/tests/integration/test_candidates_startup.py
new file mode 100644
--- /dev/null
+++ b/tests/integration/test_candidates_startup.py
@@ -0,0 +1,99 @@
+"""Start-up reconciles the candidate store before any request is served (ADR 0021 decision 6)."""
+
+from __future__ import annotations
+
+from datetime import UTC, datetime
+from typing import TYPE_CHECKING
+from uuid import uuid4
+
+import pytest
+from server.main import create_app, lifespan
+from server.memory import candidates
+from server.memory.candidate_types import CandidateChannel, CandidateStatus, ProposedCandidate
+from server.memory.declarative import upsert_entity
+from server.settings import Settings, settings
+
+from server import db, main
+
+if TYPE_CHECKING:
+    from pathlib import Path
+
+pytestmark = pytest.mark.integration
+
+
+async def _seed_an_offered_candidate(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> int:
+    """Leave one `offered` candidate in a database file, as a previous process would have."""
+    monkeypatch.setattr(settings, "brain_db_path", db_path)
+    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
+    db._conn = None
+    await db.open_db()
+    await db.run_migrations()
+    owner = await upsert_entity(name="Canary Owner", type="person")
+    stored = await candidates.insert_candidate(
+        ProposedCandidate(predicate="likes", value_text="el mate", value_key="mate"),
+        subject_person_id=owner,
+        asserted_by_person_id=owner,
+        channel=CandidateChannel.VOICE_CLASSIC,
+        correlation_id=uuid4(),
+        now=datetime.now(UTC),
+    )
+    assert stored.candidate_id is not None
+    assert await candidates.mark_offered(
+        stored.candidate_id, owner, correlation_id=uuid4(), now=datetime.now(UTC)
+    )
+    await db.close_db()
+    db._conn = None
+    return stored.candidate_id
+
+
+async def _candidate_after_a_start(
+    candidate_id: int, db_path: Path, monkeypatch: pytest.MonkeyPatch, *, switch_on: bool
+) -> candidates.Candidate | None:
+    """Run the real lifespan against the file and read the candidate back afterwards."""
+    monkeypatch.setattr(main.stt, "preload", lambda: None)
+    monkeypatch.setattr(main.tts, "preload", lambda: None)
+    monkeypatch.setattr(settings, "memory_enabled", True)
+    monkeypatch.setattr(settings, "memory_candidates_enabled", switch_on)
+    app = create_app(
+        Settings(
+            memory_enabled=True,
+            memory_candidates_enabled=switch_on,
+            brain_db_path=db_path,
+        )
+    )
+    async with lifespan(app):
+        assert app.state.ready is True
+    db._conn = None
+    await db.open_db()
+    try:
+        return await candidates.get_candidate(candidate_id)
+    finally:
+        await db.close_db()
+        db._conn = None
+
+
+async def test_a_start_with_the_switch_on_returns_the_offer_to_proposed(
+    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    db_path = tmp_path / "startup.db"
+    candidate_id = await _seed_an_offered_candidate(db_path, monkeypatch)
+
+    candidate = await _candidate_after_a_start(candidate_id, db_path, monkeypatch, switch_on=True)
+
+    assert candidate is not None
+    assert candidate.status is CandidateStatus.PROPOSED
+    assert candidate.value_text == "el mate"
+    assert candidate.offered_at is None
+
+
+async def test_a_start_with_the_switch_off_voids_every_live_candidate(
+    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    db_path = tmp_path / "startup.db"
+    candidate_id = await _seed_an_offered_candidate(db_path, monkeypatch)
+
+    candidate = await _candidate_after_a_start(candidate_id, db_path, monkeypatch, switch_on=False)
+
+    assert candidate is not None
+    assert candidate.status is CandidateStatus.EXPIRED
+    assert (candidate.value_text, candidate.value_key) == (None, None)
diff --git a/tests/integration/test_retention.py b/tests/integration/test_retention.py
--- a/tests/integration/test_retention.py
+++ b/tests/integration/test_retention.py
@@ -7,10 +7,14 @@ keeps running on the next tick.
 """

 from collections.abc import AsyncIterator
+from datetime import UTC, datetime, timedelta
 from pathlib import Path
+from uuid import uuid4

 import pytest
-from server.memory import retention
+from server.memory import candidates, retention
+from server.memory.candidate_types import CandidateChannel, CandidateStatus, ProposedCandidate
+from server.memory.declarative import upsert_entity
 from server.settings import settings

 from server import db
@@ -61,3 +65,46 @@ async def test_run_once_swallows_a_failure_without_raising(
     monkeypatch.setattr(retention, "_SQL_SENSOR_READINGS", "NOT VALID SQL")

     await retention._run_once()
+
+
+@pytest.mark.integration
+@pytest.mark.usefixtures("real_db")
+async def test_run_once_expires_and_scrubs_a_lapsed_candidate_whatever_the_kill_switch_says(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    """ADR 0021 decision 6: the hourly job reclaims candidate values, switch on or off."""
+    owner = await upsert_entity(name="Canary Owner", type="person")
+    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
+    # The fresh one goes in first: a store entry runs its own housekeeping, so inserting it
+    # after the stale one would expire the stale one before the retention job ever ran.
+    fresh = await candidates.insert_candidate(
+        ProposedCandidate(predicate="likes", value_text="el jazz", value_key="jazz"),
+        subject_person_id=owner,
+        asserted_by_person_id=owner,
+        channel=CandidateChannel.VOICE_CLASSIC,
+        correlation_id=uuid4(),
+        now=datetime.now(UTC),
+    )
+    stale = await candidates.insert_candidate(
+        ProposedCandidate(predicate="likes", value_text="el mate", value_key="mate"),
+        subject_person_id=owner,
+        asserted_by_person_id=owner,
+        channel=CandidateChannel.VOICE_CLASSIC,
+        correlation_id=uuid4(),
+        now=datetime.now(UTC) - timedelta(days=2),
+    )
+    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
+    assert stale.candidate_id is not None
+    assert fresh.candidate_id is not None
+    before = await candidates.get_candidate(stale.candidate_id)
+    assert before is not None
+    assert before.status is CandidateStatus.PROPOSED  # lapsed on the clock, still live in the row
+
+    await retention._run_once()
+
+    expired = await candidates.get_candidate(stale.candidate_id)
+    kept = await candidates.get_candidate(fresh.candidate_id)
+    assert expired is not None
+    assert (expired.status, expired.value_text) == (CandidateStatus.EXPIRED, None)
+    assert kept is not None
+    assert (kept.status, kept.value_text) == (CandidateStatus.PROPOSED, "el jazz")
diff --git a/tests/unit/test_scrub_candidates.py b/tests/unit/test_scrub_candidates.py
new file mode 100644
--- /dev/null
+++ b/tests/unit/test_scrub_candidates.py
@@ -0,0 +1,120 @@
+"""The pre-copy scrub of `just reset-db` (ADR 0021 decision 6): no live value in a backup."""
+
+from __future__ import annotations
+
+from pathlib import Path
+import sqlite3
+
+import pytest
+
+from scripts import scrub_candidates
+
+pytestmark = pytest.mark.unit
+
+_MIGRATION = (
+    Path(scrub_candidates.__file__).resolve().parents[1]
+    / "server/src/server/memory/migration_009_memory_candidates.sql"
+)
+_CANARY = "zumo de pomelo rosado"
+_RESET_SCRIPT = Path(scrub_candidates.__file__).resolve().with_name("reset_db.ps1")
+
+
+def _database(path: Path, *, statuses: tuple[str, ...]) -> Path:
+    """A database file holding one candidate row per status, with WAL like the server's."""
+    connection = sqlite3.connect(path)
+    connection.execute("PRAGMA journal_mode = WAL")
+    connection.executescript(_MIGRATION.read_text(encoding="utf-8"))
+    for index, status in enumerate(statuses):
+        live = status in {"proposed", "offered"}
+        connection.execute(
+            "INSERT INTO memory_candidates (subject_person_id, asserted_by_person_id, predicate, "
+            "value_text, value_key, status, channel, source_correlation_id, proposed_at, "
+            "expires_at) VALUES (1, 1, 'likes', ?, ?, ?, 'voice_classic', 'c', 'a', 'b')",
+            (
+                f"{_CANARY} {index}" if live else None,
+                f"{_CANARY} {index}" if live else None,
+                status,
+            ),
+        )
+    connection.commit()
+    connection.close()
+    return path
+
+
+def _bytes(path: Path) -> bytes:
+    wal = path.with_name(path.name + "-wal")
+    return path.read_bytes() + (wal.read_bytes() if wal.exists() else b"")
+
+
+def test_every_live_candidate_is_voided_and_its_value_leaves_the_file(tmp_path: Path) -> None:
+    db_path = _database(tmp_path / "omnibot.db", statuses=("proposed", "offered", "confirmed"))
+    assert _CANARY.encode() in _bytes(db_path)
+
+    voided = scrub_candidates.scrub(db_path)
+
+    assert voided == 2
+    assert _CANARY.encode() not in _bytes(db_path)
+    connection = sqlite3.connect(db_path)
+    rows = connection.execute(
+        "SELECT status, value_text, value_key FROM memory_candidates ORDER BY id"
+    ).fetchall()
+    connection.close()
+    assert rows == [("expired", None, None), ("expired", None, None), ("confirmed", None, None)]
+
+
+def test_a_database_without_the_table_or_the_file_is_a_clean_no_op(tmp_path: Path) -> None:
+    empty = tmp_path / "older.db"
+    sqlite3.connect(empty).close()
+
+    assert scrub_candidates.scrub(empty) == 0
+    assert scrub_candidates.scrub(tmp_path / "missing.db") == 0
+
+
+def test_main_prints_counts_only_and_exits_zero(
+    tmp_path: Path, capsys: pytest.CaptureFixture[str]
+) -> None:
+    db_path = _database(tmp_path / "omnibot.db", statuses=("proposed",))
+
+    status = scrub_candidates.main([str(db_path)])
+
+    out = capsys.readouterr().out
+    assert status == 0
+    assert "Voided 1 live candidate(s)" in out
+    assert "pomelo" not in out
+
+
+def test_main_fails_when_the_file_is_not_a_database(
+    tmp_path: Path, capsys: pytest.CaptureFixture[str]
+) -> None:
+    broken = tmp_path / "omnibot.db"
+    broken.write_bytes(b"this is not a sqlite database at all" * 20)
+
+    status = scrub_candidates.main([str(broken)])
+
+    assert status == 1
+    assert "Could not scrub" in capsys.readouterr().err
+
+
+def test_reset_db_scrubs_before_it_copies_and_refuses_to_copy_when_it_fails() -> None:
+    text = _RESET_SCRIPT.read_text(encoding="utf-8")
+
+    scrub_at = text.index("scrub_candidates.py")
+    copy_at = text.index("Copy-Item $dbPath")
+    assert scrub_at < copy_at
+    assert "$LASTEXITCODE" in text[scrub_at:copy_at]
+
+
+def test_a_reader_that_pins_the_log_makes_the_scrub_fail_so_nothing_is_copied(
+    tmp_path: Path, capsys: pytest.CaptureFixture[str]
+) -> None:
+    db_path = _database(tmp_path / "omnibot.db", statuses=("proposed",))
+    reader = sqlite3.connect(db_path)
+    reader.execute("BEGIN")
+    reader.execute("SELECT COUNT(*) FROM memory_candidates").fetchall()
+    try:
+        status = scrub_candidates.main([str(db_path)])
+    finally:
+        reader.close()
+
+    assert status == 1
+    assert "Could not scrub" in capsys.readouterr().err
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/integration/test_candidates_startup.py tests/integration/test_retention.py tests/unit/test_scrub_candidates.py -q -p no:cacheprovider`
  Expected RED: `ImportError: cannot import name 'scrub_candidates' from 'scripts'`.
- [ ] **Step 3: Implement:**

```diff
diff --git a/scripts/reset_db.ps1 b/scripts/reset_db.ps1
--- a/scripts/reset_db.ps1
+++ b/scripts/reset_db.ps1
@@ -73,6 +73,14 @@ if (-not (Test-Path $dbPath)) {
     exit 0
 }

+# 1b. A live memory candidate holds something the owner said about themselves (ADR 0021):
+#     void it and overwrite its bytes BEFORE the file is copied to the backup folder.
+uv run python scripts/scrub_candidates.py $dbPath
+if ($LASTEXITCODE -ne 0) {
+    Write-Host "ERROR: could not void live memory candidates - the database was NOT copied."
+    exit 1
+}
+
 # 2. Backup with timestamp before touching anything.
 New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
 $stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
diff --git a/scripts/scrub_candidates.py b/scripts/scrub_candidates.py
new file mode 100644
--- /dev/null
+++ b/scripts/scrub_candidates.py
@@ -0,0 +1,85 @@
+"""Void every live memory candidate in a database file before the file is copied (ADR 0021).
+
+``just reset-db`` copies the live database to ``data/backups`` before deleting it. A live
+candidate holds a value the owner said about themselves, so the copy must not carry one: this
+script voids them in place, overwrites the freed bytes (``secure_delete``) and truncates the
+write-ahead log, and only then does the caller copy.
+
+It talks to the file through the standard library's ``sqlite3`` (no ``aiosqlite``, no
+extension, no model) and must run with the server stopped. It prints counts, never a value.
+
+Usage:
+    uv run python scripts/scrub_candidates.py
+    uv run python scripts/scrub_candidates.py path/to/omnibot.db
+
+Exit status: 0 when no live candidate remains (including a database that has no candidate
+table yet, or no file at all); 1 when the database could not be scrubbed or its log could not
+be truncated (another process holds it) — the caller must not copy it.
+"""
+
+import argparse
+from datetime import UTC, datetime
+from pathlib import Path
+import sqlite3
+import sys
+
+from server.memory.candidates import VOID_LIVE_SQL, iso_utc
+
+_DEFAULT_DB = Path("data/omnibot.db")
+_LOCK_WAIT_S = 1.0
+
+
+def scrub(db_path: Path) -> int:
+    """Void the live candidates of *db_path* and truncate its write-ahead log.
+
+    Args:
+        db_path: A SQLite database file of this project. The server must be stopped.
+
+    Returns:
+        How many live candidates were voided (0 when there is no file or no candidate table).
+    """
+    if not db_path.exists():
+        return 0
+    connection = sqlite3.connect(db_path, timeout=_LOCK_WAIT_S)
+    try:
+        connection.execute("PRAGMA secure_delete = ON")
+        table = connection.execute(
+            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory_candidates'"
+        ).fetchone()
+        if table is None:
+            return 0
+        cursor = connection.execute(VOID_LIVE_SQL, (iso_utc(datetime.now(UTC)),))
+        voided = cursor.rowcount
+        connection.commit()
+        busy = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
+        if busy is None or busy[0] != 0:
+            # A reader pins the log: a copy of the main file could still carry a stale page.
+            raise sqlite3.OperationalError("the write-ahead log could not be truncated")
+    finally:
+        connection.close()
+    return voided
+
+
+def main(argv: list[str] | None = None) -> int:
+    """Run the scrub from the command line.
+
+    Args:
+        argv: Arguments after the program name; ``None`` reads ``sys.argv``.
+
+    Returns:
+        The process exit status.
+    """
+    parser = argparse.ArgumentParser(description="Void live memory candidates in a database file.")
+    parser.add_argument("db_path", nargs="?", type=Path, default=_DEFAULT_DB)
+    args = parser.parse_args(argv)
+    try:
+        voided = scrub(args.db_path)
+    except sqlite3.Error as exc:
+        sys.stderr.write(f"Could not scrub {args.db_path}: {type(exc).__name__}\n")
+        return 1
+    sys.stdout.write(f"Voided {voided} live candidate(s) in {args.db_path}.\n")
+    return 0
+
+
+if __name__ == "__main__":
+    sys.exit(main())
diff --git a/server/src/server/main.py b/server/src/server/main.py
--- a/server/src/server/main.py
+++ b/server/src/server/main.py
@@ -15,11 +15,12 @@ import uvicorn

 from server import stt, tts
 from server.chat_ui import mount_chat_ui
+from server.cognition.clock import utc_now
 from server.cognition.owner_authentication import owner_unlock_service
 from server.db import close_db, open_db, run_migrations
 from server.exceptions import VisionError
 from server.logging_setup import configure_logging
-from server.memory import retention
+from server.memory import candidates, retention
 from server.request_context import RequestContextMiddleware
 from server.resources import AppResources
 from server.routers import auth, chat, system, transcribe, vision
@@ -121,6 +122,9 @@ async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
             await open_db()
             stack.push_async_callback(close_db)
             await run_migrations()
+            # Before any request: offers of the previous process return to `proposed`,
+            # and with the switch off every live candidate value is voided.
+            await candidates.reset_for_startup(utc_now(), enabled=cfg.memory_candidates_enabled)
             retention.start_background_job()
             stack.push_async_callback(retention.stop_background_job)
             logger.info("Brain memory enabled: %s", cfg.brain_db_path)
diff --git a/server/src/server/memory/retention.py b/server/src/server/memory/retention.py
--- a/server/src/server/memory/retention.py
+++ b/server/src/server/memory/retention.py
@@ -8,6 +8,9 @@ Retention windows (all configurable via settings):
   - ``sensor_aggregates_hourly``:  1 year (hardcoded — aggregates are small)
   - ``embeddings_cache``:       30 days (hardcoded)
   - ``outbox`` (synced only):   7 days (hardcoded)
+  - ``memory_candidates``:      past ``expires_at`` or out of offers (ADR 0021),
+    whatever the candidate kill-switch says; the value is scrubbed and the
+    write-ahead log truncated
 """

 from __future__ import annotations
@@ -16,6 +19,8 @@ import asyncio
 import logging

 from server import db
+from server.cognition.clock import utc_now
+from server.memory.candidates import checkpoint_after_scrub, run_housekeeping
 from server.settings import settings

 logger = logging.getLogger(__name__)
@@ -47,6 +52,8 @@ async def _run_once() -> None:
             await conn.execute(_SQL_SENSOR_AGGREGATES)
             await conn.execute(_SQL_EMBEDDINGS_CACHE)
             await conn.execute(_SQL_OUTBOX)
+            scrubbed = await run_housekeeping(conn, utc_now())
+        await checkpoint_after_scrub(scrubbed)
         logger.info("Retention purge complete (sensor_threshold=%s)", sensor_threshold)
     except Exception as exc:
         logger.warning("Retention purge failed: %s", exc)
```

- [ ] **Step 4: Run to see them pass, then lint and types.** `scripts/` is excluded from
  `ruff check .`: lint the two script files with explicit paths
  (`uv run ruff check scripts/scrub_candidates.py` and `uv run ruff format --check scripts/scrub_candidates.py`).
  Also `uv run pytest tests/unit/test_app_lifecycle.py tests/unit/test_main_lifespan.py -q -p no:cacheprovider`.
- [ ] **Step 5: Commit** `feat(server): reclaim and scrub candidates (plan 0062)`; check `git log -1`.

---

## Task 13: Wire the proposal and retire `consolidate_turn`

**Files:**
- Modify: `server/src/server/memory/consolidation.py`, `server/src/server/routers/transcribe.py`, `server/src/server/streaming.py`, `server/src/server/text_turn.py`
- Test: modified `tests/integration/test_generic_turn_continuity.py`, `tests/integration/test_memory_integration.py`, `tests/integration/test_memory_relational.py`, `tests/integration/test_onboarding_checklist.py`, `tests/integration/test_owner_stranger_matrix.py`, `tests/integration/test_transcribe_memory.py`, `tests/integration/test_transcribe_onboarding.py`, `tests/integration/test_transcribe_pipeline.py`, `tests/integration/test_transcribe_stream.py`, `tests/integration/test_vision_memoria.py`, `tests/unit/test_architecture_guards.py`, `tests/unit/test_consolidation_extract.py`, `tests/unit/test_text_turn.py`

**Interfaces:**
- Consumes: Tasks 8 and 11.
- Produces: `text_turn.ProposalScheduler = Callable[[str, ActivePersonContext], None]`;
  `process_text_turn(..., schedule_proposal=...)`, `record_text_turn(..., schedule_proposal=...)`
  and `streaming.stream_pipeline(..., schedule_proposal=...)` (the old `schedule_consolidation`
  parameter and `ConsolidationScheduler` are gone); `routers.transcribe._proposal_scheduler(client,
  background_tasks, *, event, wav_bytes, channel)`; `memory/consolidation.py` keeps only
  `_extract_via_ollama` and its prompt (D-11).

The scheduling gate is `settings.memory_candidates_enabled and is_face_actor(actor)` and a
*successful* turn: a fallback reply, an `unknown`/`ambiguous` speaker, a token, a manual session,
`/chat` and `/vision/respond` never schedule. `_MANUAL_HOMES` loses `memory/consolidation.py`.

- [ ] **Step 1: Write the failing tests.** The tests that pinned the old signature and the retired
  writer change on purpose (D-12). First the new and changed tests as diffs: proposal-scheduling
  tests in `test_text_turn.py`, the background bridge and the stream scheduling in
  `test_transcribe_stream.py`, the route tests in `test_generic_turn_continuity.py` (classic and
  streaming with the clip, the channel and the event; no frame; token; `/chat`; kill-switch off;
  visual dialogue; fallback), the renamed patch targets, the retired retry tests and the new
  no-echo test of `test_consolidation_extract.py`, and the guards:

```diff
diff --git a/tests/integration/test_generic_turn_continuity.py b/tests/integration/test_generic_turn_continuity.py
--- a/tests/integration/test_generic_turn_continuity.py
+++ b/tests/integration/test_generic_turn_continuity.py
@@ -26,13 +26,16 @@ from server.cognition.identity import PersonRecord
 from server.cognition.identity_sessions import IdentitySessionRegistry
 from server.cognition.owner_authentication import OwnerUnlockService, owner_unlock_service
 from server.dependencies import get_owner_unlock_service
+from server.exceptions import LLMError
 from server.main import app
 from server.memory.biometric_consent import grant_face_consent
+from server.memory.candidate_types import CandidateChannel
 from server.memory.entity_labels import get_person_label
 from server.memory.household_authorization import get_active_role
 from server.memory.owner_credentials import get_active_owner_pin_credential
 from server.personal_setup import PersonalSetupInput, PersonalSetupResult, apply_personal_setup
 from server.resources import AppResources
+from server.routers import transcribe as transcribe_module
 from server.settings import settings
 from server.vision.faces import DetectedFace, enroll_face

@@ -340,3 +343,115 @@ async def test_a_visual_dialogue_turn_neither_reads_nor_writes_the_session(
     # The visual turn received no history and wrote nothing: the owner's next turn still finds
     # exactly the first exchange, not the visual one.
     assert _histories(generate) == [[], None, ["Mi clave es COBALTO", "Anotado."]]
+
+
+# --- candidate proposals through the real routes (Plan 0062, ADR 0021 §10) -------------------
+
+
+@pytest.fixture
+def proposals(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
+    """Switch candidates on and replace the background proposal with a spy."""
+    spy = AsyncMock()
+    monkeypatch.setattr(transcribe_module, "propose_candidates", spy)
+    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
+    return spy
+
+
+@pytest.mark.integration
+async def test_a_face_identified_classic_turn_proposes_with_its_own_clip_and_event(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, proposals: AsyncMock
+) -> None:
+    _detect(monkeypatch, _OWNER_FACE)
+    _speak(monkeypatch, "Me gusta el mate")
+    _model(monkeypatch, "Qué bueno.")
+
+    async with _client() as client:
+        response = await client.post("/transcribe", files=_files())
+
+    assert response.status_code == 200
+    proposals.assert_awaited_once()
+    call = proposals.await_args
+    assert call is not None
+    _client_arg, message, actor = call.args
+    assert message == "Me gusta el mate"
+    assert actor.person_id == household.owner_entity_id
+    assert {item.source.value for item in actor.evidence} == {"face"}
+    assert call.kwargs["wav_bytes"] == _tone_wav()
+    assert call.kwargs["channel"] is CandidateChannel.VOICE_CLASSIC
+    assert call.kwargs["event"].payload.message == "Me gusta el mate"
+    assert "Qué bueno." not in str(call)
+
+
+@pytest.mark.integration
+async def test_a_face_identified_streaming_turn_proposes_on_the_stream_channel(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, proposals: AsyncMock
+) -> None:
+    _detect(monkeypatch, _OWNER_FACE)
+    _speak(monkeypatch, "Me gusta el mate")
+
+    async def stream(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
+        yield "Qué bueno."
+
+    monkeypatch.setattr(llm_streaming, "generate_response_stream", stream)
+
+    async with _client() as client:
+        response = await client.post("/transcribe/stream", files=_files())
+
+    assert response.status_code == 200
+    proposals.assert_awaited_once()
+    call = proposals.await_args
+    assert call is not None
+    assert call.kwargs["channel"] is CandidateChannel.VOICE_STREAM
+    assert call.kwargs["wav_bytes"] == _tone_wav()
+
+
+@pytest.mark.integration
+async def test_no_proposal_without_a_face_with_a_token_from_chat_or_with_the_switch_off(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, proposals: AsyncMock
+) -> None:
+    service = _service()
+    monkeypatch.setitem(app.dependency_overrides, get_owner_unlock_service, lambda: service)
+    unlock = await service.unlock(_PIN)
+    assert unlock is not None
+    headers = {"X-Iroko-Identity-Token": unlock.token}
+    _speak(monkeypatch, "Me gusta el mate", "Me gusta el mate", "Me gusta el mate")
+    _model(monkeypatch, "Uno.", "Dos.", "Tres.", "Cuatro.", "Cinco.")
+
+    async with _client() as client:
+        # no frame: the speaker is unknown
+        await client.post("/transcribe", files=_files(with_frame=False))
+        # a token only: a PIN grant proves the PIN, not the speaker
+        await client.post("/transcribe", files=_files(with_frame=False), headers=headers)
+        # /chat has no audio, so it never proposes
+        await client.post(
+            "/chat",
+            headers=headers,
+            json={"message": "Me gusta el mate", "conversation_id": "web"},
+        )
+        # the face is there, the kill-switch is off
+        _detect(monkeypatch, _OWNER_FACE)
+        monkeypatch.setattr(settings, "memory_candidates_enabled", False)
+        await client.post("/transcribe", files=_files())
+
+    proposals.assert_not_awaited()
+
+
+@pytest.mark.integration
+async def test_no_proposal_from_a_visual_dialogue_turn_or_a_fallback_reply(
+    household: PersonalSetupResult, monkeypatch: pytest.MonkeyPatch, proposals: AsyncMock
+) -> None:
+    monkeypatch.setattr(settings, "vision_enabled", True)
+    _detect(monkeypatch, _OWNER_FACE)
+    _speak(monkeypatch, "Me gusta el mate")
+    monkeypatch.setattr(llm, "generate_response", AsyncMock(side_effect=LLMError("down")))
+
+    async with _client() as client:
+        visual = await client.post(
+            "/vision/respond",
+            files={"image": ("frame.jpg", _FRAME, "image/jpeg")},
+            data={"text": "Me gusta el mate"},
+        )
+        fallback = await client.post("/transcribe", files=_files())
+
+    assert visual.status_code == fallback.status_code == 200
+    proposals.assert_not_awaited()
diff --git a/tests/integration/test_owner_stranger_matrix.py b/tests/integration/test_owner_stranger_matrix.py
--- a/tests/integration/test_owner_stranger_matrix.py
+++ b/tests/integration/test_owner_stranger_matrix.py
@@ -165,9 +165,9 @@ def llm_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:

 @pytest.fixture
 def consolidation(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
-    """Replace post-turn consolidation so a scheduled write is observable."""
+    """Replace the post-turn candidate proposal so a scheduled write is observable."""
     mock = AsyncMock()
-    monkeypatch.setattr("server.routers.transcribe.consolidate_turn", mock)
+    monkeypatch.setattr("server.routers.transcribe.propose_candidates", mock)
     return mock


diff --git a/tests/integration/test_transcribe_memory.py b/tests/integration/test_transcribe_memory.py
--- a/tests/integration/test_transcribe_memory.py
+++ b/tests/integration/test_transcribe_memory.py
@@ -73,7 +73,7 @@ def _mock_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
 def memory_on(monkeypatch: pytest.MonkeyPatch) -> None:
     """Enable memory while unresolved requests clean up their own turn scope."""
     monkeypatch.setattr(settings, "memory_enabled", True)
-    monkeypatch.setattr(transcribe_module, "consolidate_turn", AsyncMock())
+    monkeypatch.setattr(transcribe_module, "propose_candidates", AsyncMock())


 @pytest.mark.integration
@@ -84,9 +84,9 @@ def test_fallback_turn_is_not_recorded(
     monkeypatch: pytest.MonkeyPatch,
 ) -> None:
     """A fallback apology should not enter working or persistent memory."""
-    consolidate = AsyncMock()
+    propose = AsyncMock()
     monkeypatch.setattr(llm, "generate_response", AsyncMock(side_effect=LLMError("down")))
-    monkeypatch.setattr(transcribe_module, "consolidate_turn", consolidate)
+    monkeypatch.setattr(transcribe_module, "propose_candidates", propose)
     monkeypatch.setattr(pipeline, "list_entity_names", AsyncMock(return_value=[]))
     monkeypatch.setattr(
         text_turn, "_memory_prompt_state", AsyncMock(return_value=(None, False, None))
@@ -98,7 +98,7 @@ def test_fallback_turn_is_not_recorded(
     )

     assert response.status_code == 200
-    consolidate.assert_not_awaited()
+    propose.assert_not_awaited()


 @pytest.mark.integration
@@ -253,14 +253,14 @@ async def test_consolidation_eval_rejects_legacy_alias_before_provider(

 @pytest.mark.integration
 @pytest.mark.usefixtures("memory_on")
-def test_unidentified_voice_turn_does_not_schedule_consolidation(
+def test_unidentified_voice_turn_does_not_schedule_a_proposal(
     client: TestClient,
     silence_wav_bytes: bytes,
     monkeypatch: pytest.MonkeyPatch,
 ) -> None:
-    """A voice turn with no internal manual evidence must never persist facts."""
-    consolidate = AsyncMock()
-    monkeypatch.setattr(transcribe_module, "consolidate_turn", consolidate)
+    """A voice turn with no face-identified speaker must never propose a candidate."""
+    propose = AsyncMock()
+    monkeypatch.setattr(transcribe_module, "propose_candidates", propose)
     monkeypatch.setattr(pipeline, "list_entity_names", AsyncMock(return_value=[]))

     response = client.post(
@@ -269,7 +269,7 @@ def test_unidentified_voice_turn_does_not_schedule_consolidation(
     )

     assert response.status_code == 200
-    consolidate.assert_not_awaited()
+    propose.assert_not_awaited()


 @pytest.mark.integration
diff --git a/tests/integration/test_transcribe_onboarding.py b/tests/integration/test_transcribe_onboarding.py
--- a/tests/integration/test_transcribe_onboarding.py
+++ b/tests/integration/test_transcribe_onboarding.py
@@ -19,7 +19,7 @@ def _mock_memory_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
     monkeypatch.setattr(llm, "generate_response", AsyncMock(return_value=("hola humano", "joy")))
     monkeypatch.setattr(tts, "synthesize", AsyncMock(return_value=("AAAA", 42)))
     monkeypatch.setattr(pipeline, "list_entity_names", AsyncMock(return_value=[]))
-    monkeypatch.setattr(transcribe_module, "consolidate_turn", AsyncMock())
+    monkeypatch.setattr(transcribe_module, "propose_candidates", AsyncMock())


 @pytest.mark.integration
diff --git a/tests/integration/test_transcribe_pipeline.py b/tests/integration/test_transcribe_pipeline.py
--- a/tests/integration/test_transcribe_pipeline.py
+++ b/tests/integration/test_transcribe_pipeline.py
@@ -9,7 +9,7 @@ import pytest
 from server.exceptions import LLMError, TranscriptionError, TTSError
 from server.routers import transcribe as transcribe_module
 from server.settings import settings
-from server.text_turn import ConsolidationScheduler, TextTurnResult
+from server.text_turn import ProposalScheduler, TextTurnResult

 from server import llm, stt, tts

@@ -330,11 +330,11 @@ def test_transcribe_uses_distinct_internal_scopes_per_request(
         message: str,
         conversation_id: str,
         *,
-        schedule_consolidation: ConsolidationScheduler,
+        schedule_proposal: ProposalScheduler,
         active_person: object = None,
         suspend_cause: object = None,
     ) -> TextTurnResult:
-        _ = client, schedule_consolidation, active_person, suspend_cause
+        _ = client, schedule_proposal, active_person, suspend_cause
         return TextTurnResult("shared reply", "joy", 7, False)

     process = AsyncMock(side_effect=process_turn)
diff --git a/tests/integration/test_transcribe_stream.py b/tests/integration/test_transcribe_stream.py
--- a/tests/integration/test_transcribe_stream.py
+++ b/tests/integration/test_transcribe_stream.py
@@ -17,12 +17,14 @@ from server.cognition.identity import (
     ActivePersonContext,
     ActivePersonStatus,
     HouseholdRole,
+    IdentityAssurance,
     IdentityEvidence,
     IdentityEvidenceSource,
 )
 from server.cognition.models import Confidence, ConfidenceBasis, KnowledgeStatus
 from server.cognition.response_plan import InformationNeed, ResponsePlan, ResponseSource
 from server.exceptions import LLMError, TTSError
+from server.memory.candidate_types import CandidateChannel
 from server.memory.continuity import ContinuityTurn
 from server.routers import transcribe as transcribe_module
 from server.schemas import ConversationTurn
@@ -62,6 +64,33 @@ def _manual_active_person() -> ActivePersonContext:
     )


+def _face_active_person() -> ActivePersonContext:
+    """Create the owner as the face identifies them (ADR 0020), for proposal-scheduling tests."""
+    resolved_at = datetime(2026, 8, 10, tzinfo=UTC)
+    confidence = Confidence(
+        score=1.0, basis=ConfidenceBasis.MEASURED, calibrated=True, reason="In-turn face match"
+    )
+    return ActivePersonContext(
+        person_id=7,
+        display_name="Paula",
+        status=ActivePersonStatus.IDENTIFIED,
+        confidence=confidence,
+        role=HouseholdRole.OWNER,
+        evidence=(
+            IdentityEvidence(
+                evidence_id=UUID("22222222-2222-2222-2222-222222222222"),
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
 _USER_EMOTION = "joy"  # what the stubbed classifier decides for every turn unless a test says so
 _FENCE = "`" * 3  # built, not written: this file also lives inside a Markdown code fence

@@ -238,7 +267,7 @@ def test_stream_prepares_shared_voice_turn(
     assert prepare.await_args is not None
     assert prepare.await_args.args[1:] == ("hola robot", scope)
     assert record.call_args.args == ("hola robot", "Hola. ¿Cómo estás?")
-    assert callable(record.call_args.kwargs["schedule_consolidation"])
+    assert callable(record.call_args.kwargs["schedule_proposal"])


 @pytest.mark.integration
@@ -756,7 +785,7 @@ async def test_stream_partial_llm_failure_preserves_audio_then_fallback(
             prepared=prepared,
             stt_ms=0,
             request_start=time.perf_counter(),
-            schedule_consolidation=lambda *_a, **_k: None,
+            schedule_proposal=lambda *_a, **_k: None,
         )
     ]

@@ -798,7 +827,7 @@ async def test_stream_protocol_fallback_tts_failure_has_no_done(
             prepared=prepared,
             stt_ms=0,
             request_start=time.perf_counter(),
-            schedule_consolidation=lambda *_a, **_k: None,
+            schedule_proposal=lambda *_a, **_k: None,
         ):
             collected.append(line)

@@ -830,7 +859,7 @@ async def test_stream_tts_failure_logs_tts_error_outcome(
             prepared=prepared,
             stt_ms=0,
             request_start=time.perf_counter(),
-            schedule_consolidation=lambda *_a, **_k: None,
+            schedule_proposal=lambda *_a, **_k: None,
         ):
             pass

@@ -1099,7 +1128,7 @@ async def test_streaming_propagates_prepared_identity_history_and_recording_scop
             prepared=prepared,
             stt_ms=0,
             request_start=time.perf_counter(),
-            schedule_consolidation=lambda _message, _response, _active_person: None,
+            schedule_proposal=lambda _message, _active_person: None,
         )
     ]

@@ -1111,14 +1140,14 @@ async def test_streaming_propagates_prepared_identity_history_and_recording_scop

 @pytest.mark.integration
 @pytest.mark.asyncio
-async def test_streaming_schedules_manual_identity_for_consolidation(
+async def test_streaming_schedules_the_proposal_for_a_face_identified_speaker(
     http_client: httpx.AsyncClient,
     monkeypatch: pytest.MonkeyPatch,
 ) -> None:
-    """Streaming must preserve manual identity through its scheduler callback."""
-    active_person = _manual_active_person()
+    """Streaming hands the proposal callback the user's words and the actor, never the reply."""
+    active_person = _face_active_person()
     prepared = PreparedTextTurn(
-        "hola robot",
+        "me gusta el mate",
         "public-id",
         None,
         [],
@@ -1131,6 +1160,7 @@ async def test_streaming_schedules_manual_identity_for_consolidation(
     )
     scheduler = Mock()
     monkeypatch.setattr(settings, "memory_enabled", True)
+    monkeypatch.setattr(settings, "memory_candidates_enabled", True)

     _ = [
         line
@@ -1139,33 +1169,40 @@ async def test_streaming_schedules_manual_identity_for_consolidation(
             prepared=prepared,
             stt_ms=0,
             request_start=time.perf_counter(),
-            schedule_consolidation=scheduler,
+            schedule_proposal=scheduler,
         )
     ]

-    scheduler.assert_called_once_with("hola robot", "Hola. ¿Cómo estás?", active_person)
+    scheduler.assert_called_once_with("me gusta el mate", active_person)


 @pytest.mark.integration
 @pytest.mark.asyncio
-async def test_background_scheduler_forwards_manual_identity(
+@pytest.mark.parametrize("channel", list(CandidateChannel))
+async def test_the_background_bridge_carries_the_clip_the_event_and_the_channel(
     http_client: httpx.AsyncClient,
     monkeypatch: pytest.MonkeyPatch,
+    channel: CandidateChannel,
 ) -> None:
-    """The FastAPI background bridge must pass identity as data, not permission."""
-    active_person = _manual_active_person()
-    consolidate = AsyncMock()
+    """The FastAPI background bridge passes identity as data and keeps the clip in memory."""
+    active_person = _face_active_person()
+    propose = AsyncMock()
     background_tasks = BackgroundTasks()
-    monkeypatch.setattr(transcribe_module, "consolidate_turn", consolidate)
+    monkeypatch.setattr(transcribe_module, "propose_candidates", propose)
+    event = transcribe_module._voice_event_from_transcript("me gusta el mate")

-    scheduler = transcribe_module._consolidation_scheduler(http_client, background_tasks)
-    scheduler("hola robot", "Hola.", active_person)
+    scheduler = transcribe_module._proposal_scheduler(
+        http_client, background_tasks, event=event, wav_bytes=b"canary-clip", channel=channel
+    )
+    scheduler("me gusta el mate", active_person)
     await background_tasks()

-    consolidate.assert_awaited_once_with(
+    propose.assert_awaited_once_with(
         http_client,
-        "hola robot",
-        "Hola.",
-        active_person=active_person,
+        "me gusta el mate",
+        active_person,
+        event=event,
+        wav_bytes=b"canary-clip",
+        channel=channel,
     )
-    assert active_person.role is HouseholdRole.UNKNOWN
+    assert active_person.role is HouseholdRole.OWNER
diff --git a/tests/unit/test_architecture_guards.py b/tests/unit/test_architecture_guards.py
--- a/tests/unit/test_architecture_guards.py
+++ b/tests/unit/test_architecture_guards.py
@@ -167,13 +167,13 @@ _MEMORY_SCOPE_VALUES = frozenset({"personal_memory_read", "personal_memory_forge
 _SCOPE_MEMBER_HOMES = frozenset({"cognition/owner_authentication.py"})
 _SCOPE_VALUE_HOMES = frozenset({"cognition/owner_authentication.py", "cognition/authorization.py"})
 # `manual` evidence counts as `basic`; these are the modules that reference it today (grep on
-# 2026-10-08). A new one must be a decision, not an accident.
+# 2026-10-08, minus `memory/consolidation.py`, whose `consolidate_turn` left in Plan 0062). A new
+# one must be a decision, not an accident.
 _MANUAL_HOMES = frozenset(
     {
         "characters/__init__.py",
         "cognition/identity.py",
         "cognition/identity_sessions.py",
-        "memory/consolidation.py",
         "text_turn.py",
     }
 )
@@ -418,3 +418,59 @@ def test_the_candidate_guard_detects_a_violation() -> None:
     }

     assert _candidate_table_queriers(leak) == ["memory/leak.py"]
+
+
+# --- who may start a candidate proposal (Plan 0062, ADR 0021 decision 1) -----------------
+# Only the two voice routes and the text-turn service they call may name the proposal entry
+# point or its scheduler: `/chat` and `/vision/respond` have no audio, so they have no `strong`
+# and must never create a candidate. `consolidate_turn` is gone for good.
+_PROPOSAL_NAMES = frozenset({"propose_candidates", "schedule_proposal", "ProposalScheduler"})
+_PROPOSAL_HOMES = frozenset(
+    {
+        "memory/candidate_proposal.py",
+        "routers/transcribe.py",
+        "streaming.py",
+        "text_turn.py",
+    }
+)
+
+
+@pytest.mark.unit
+def test_only_the_voice_routes_and_the_text_turn_service_start_a_proposal() -> None:
+    assert _outside(_sources(), _PROPOSAL_HOMES, _PROPOSAL_NAMES) == []
+
+
+def _imports_name(sources: Mapping[str, str], name: str) -> list[str]:
+    """Modules that import *name* (an import alias is not a Name node)."""
+    return [
+        module
+        for module, text in sources.items()
+        if any(
+            isinstance(node, ast.ImportFrom) and any(alias.name == name for alias in node.names)
+            for node in ast.walk(ast.parse(text))
+        )
+    ]
+
+
+@pytest.mark.unit
+def test_the_retired_consolidation_writer_has_no_reference_left() -> None:
+    sources = _sources()
+
+    assert _outside(sources, frozenset(), frozenset({"consolidate_turn"})) == []
+    assert _imports_name(sources, "consolidate_turn") == []
+
+
+@pytest.mark.unit
+def test_the_proposal_guards_detect_a_violation() -> None:
+    leak = {
+        "routers/chat.py": "x = propose_candidates(client, text, actor)\n",
+        "routers/vision.py": "process_text_turn(c, m, i, schedule_proposal=cb)\n",
+        "routers/transcribe.py": "x = propose_candidates\n",
+        "memory/legacy.py": "from x import consolidate_turn\n",
+    }
+
+    assert _outside(leak, _PROPOSAL_HOMES, _PROPOSAL_NAMES) == [
+        "routers/chat.py",
+        "routers/vision.py",
+    ]
+    assert _imports_name(leak, "consolidate_turn") == ["memory/legacy.py"]
diff --git a/tests/unit/test_consolidation_extract.py b/tests/unit/test_consolidation_extract.py
--- a/tests/unit/test_consolidation_extract.py
+++ b/tests/unit/test_consolidation_extract.py
@@ -7,7 +7,6 @@ import pytest
 from server.exceptions import LLMError
 from server.memory import consolidation
 from server.schemas import TurnExtraction
-from server.settings import settings

 _FAKE_EXTRACTION = TurnExtraction(importance=0.3)

@@ -42,50 +41,17 @@ async def test_extract_via_ollama_malformed_json_raises_llmerror(


 @pytest.mark.unit
-async def test_extract_uses_local_backend_after_invalid_runtime_mutation(
+async def test_a_malformed_answer_is_never_echoed_into_the_exception(
     http_client: httpx.AsyncClient,
     monkeypatch: pytest.MonkeyPatch,
 ) -> None:
-    """Consolidation must not select a cloud extractor after runtime corruption."""
-    local_extractor = AsyncMock(return_value=_FAKE_EXTRACTION)
-    monkeypatch.setattr(consolidation, "_extract_via_ollama", local_extractor)
-    monkeypatch.delattr(consolidation, "_extract_via_anthropic", raising=False)
-    monkeypatch.setattr(settings, "llm_provider", "anthropic")
+    """The model's output is about the household: it must not travel in an error message."""
+    answer = '{"entities": "zumo de pomelo", "facts": 7}'
+    monkeypatch.setattr(consolidation, "ollama_chat", AsyncMock(return_value=answer))

-    extraction = await consolidation._extract(http_client, "hola", "hola")
-
-    assert extraction == _FAKE_EXTRACTION
-    local_extractor.assert_awaited_once_with(http_client, "hola", "hola")
-
-
-@pytest.mark.unit
-async def test_extract_retries_once_after_transient_failure(
-    http_client: httpx.AsyncClient,
-    monkeypatch: pytest.MonkeyPatch,
-) -> None:
-    """A single transient failure must be retried, not abandoned."""
-    mock_ollama = AsyncMock(side_effect=[LLMError("model loading"), _FAKE_EXTRACTION])
-    sleep_mock = AsyncMock()
-    monkeypatch.setattr(consolidation, "_extract_via_ollama", mock_ollama)
-    monkeypatch.setattr(consolidation.asyncio, "sleep", sleep_mock)
-
-    extraction = await consolidation._extract(http_client, "hola", "hola")
-
-    assert extraction == _FAKE_EXTRACTION
-    assert mock_ollama.await_count == 2
-    sleep_mock.assert_awaited_once()
-
-
-@pytest.mark.unit
-async def test_extract_gives_up_after_second_failure(
-    http_client: httpx.AsyncClient,
-    monkeypatch: pytest.MonkeyPatch,
-) -> None:
-    mock_ollama = AsyncMock(side_effect=LLMError("still broken"))
-    monkeypatch.setattr(consolidation, "_extract_via_ollama", mock_ollama)
-    monkeypatch.setattr(consolidation.asyncio, "sleep", AsyncMock())
-
-    with pytest.raises(LLMError):
-        await consolidation._extract(http_client, "hola", "hola")
+    with pytest.raises(LLMError) as excinfo:
+        await consolidation._extract_via_ollama(http_client, "hola", "hola")

-    assert mock_ollama.await_count == 2
+    assert str(excinfo.value) == "Extraction returned invalid JSON"
+    assert "pomelo" not in repr(excinfo.value)
+    assert excinfo.value.__cause__ is None
diff --git a/tests/unit/test_text_turn.py b/tests/unit/test_text_turn.py
--- a/tests/unit/test_text_turn.py
+++ b/tests/unit/test_text_turn.py
@@ -242,14 +242,41 @@ async def test_the_session_is_keyed_by_person_id_not_by_name_or_evidence_id(

 @pytest.mark.unit
 @pytest.mark.asyncio
-async def test_manual_identified_turn_schedules_legacy_callback(
+async def test_a_face_identified_turn_schedules_a_proposal_with_the_users_words_only(
     http_client: httpx.AsyncClient,
     monkeypatch: pytest.MonkeyPatch,
 ) -> None:
-    """Only manual identity may reach consolidation and must remain attached."""
+    """ADR 0021 §10: the callback gets the user's text and the actor, never the reply."""
     generate = AsyncMock(return_value=("Veo una taza", "neutral"))
     scheduler = Mock()
     monkeypatch.setattr(settings, "memory_enabled", True)
+    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
+    monkeypatch.setattr(text_turn.llm, "generate_response", generate)
+    person = _person(IdentityEvidenceSource.FACE)
+
+    await text_turn.process_text_turn(
+        http_client,
+        "me gusta el mate",
+        "web",
+        schedule_proposal=scheduler,
+        active_person=person,
+    )
+
+    scheduler.assert_called_once_with("me gusta el mate", person)
+    assert "Veo una taza" not in str(scheduler.call_args)
+
+
+@pytest.mark.unit
+@pytest.mark.asyncio
+async def test_a_manual_identified_turn_keeps_its_history_but_proposes_nothing(
+    http_client: httpx.AsyncClient,
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    """The retired MANUAL gate no longer reaches a writer; the persistent context keeps it."""
+    generate = AsyncMock(return_value=("Veo una taza", "neutral"))
+    scheduler = Mock()
+    monkeypatch.setattr(settings, "memory_enabled", True)
+    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
     _persistent_context(monkeypatch)
     monkeypatch.setattr(text_turn.llm, "generate_response", generate)

@@ -259,7 +286,7 @@ async def test_manual_identified_turn_schedules_legacy_callback(
         "¿Qué ves?",
         "vision-a",
         perception="A blue mug",
-        schedule_consolidation=scheduler,
+        schedule_proposal=scheduler,
         active_person=person,
     )

@@ -268,7 +295,80 @@ async def test_manual_identified_turn_schedules_legacy_callback(
         "¿Qué ves?",
         "Veo una taza",
     ]
-    scheduler.assert_called_once_with("¿Qué ves?", "Veo una taza", person)
+    scheduler.assert_not_called()
+
+
+@pytest.mark.unit
+@pytest.mark.asyncio
+async def test_the_kill_switch_stops_the_proposal_before_it_is_scheduled(
+    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
+) -> None:
+    scheduler = Mock()
+    monkeypatch.setattr(settings, "memory_enabled", True)
+    monkeypatch.setattr(settings, "memory_candidates_enabled", False)
+    _generate(monkeypatch, ("Uno", "neutral"))
+
+    await text_turn.process_text_turn(
+        http_client,
+        "me gusta el mate",
+        "web",
+        schedule_proposal=scheduler,
+        active_person=_person(IdentityEvidenceSource.FACE),
+    )
+
+    scheduler.assert_not_called()
+
+
+@pytest.mark.unit
+@pytest.mark.asyncio
+@pytest.mark.parametrize(
+    "source",
+    [IdentityEvidenceSource.LOCAL_UNLOCK, IdentityEvidenceSource.MANUAL],
+)
+async def test_a_token_or_manual_turn_never_proposes(
+    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, source: IdentityEvidenceSource
+) -> None:
+    """A PIN grant proves the PIN, not the speaker: no candidate from a token (ADR 0021 §3)."""
+    scheduler = Mock()
+    monkeypatch.setattr(settings, "memory_enabled", True)
+    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
+    _persistent_context(monkeypatch)
+    _generate(monkeypatch, ("Uno", "neutral"))
+
+    await text_turn.process_text_turn(
+        http_client,
+        "me gusta el mate",
+        "web",
+        schedule_proposal=scheduler,
+        active_person=_person(source, assurance=IdentityAssurance.STRONG),
+    )
+
+    scheduler.assert_not_called()
+
+
+@pytest.mark.unit
+@pytest.mark.asyncio
+@pytest.mark.parametrize(
+    "status",
+    [ActivePersonStatus.UNKNOWN, ActivePersonStatus.PROBABLE, ActivePersonStatus.AMBIGUOUS],
+)
+async def test_an_unidentified_turn_never_proposes(
+    http_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, status: ActivePersonStatus
+) -> None:
+    scheduler = Mock()
+    monkeypatch.setattr(settings, "memory_enabled", True)
+    monkeypatch.setattr(settings, "memory_candidates_enabled", True)
+    _generate(monkeypatch, ("Uno", "neutral"))
+
+    await text_turn.process_text_turn(
+        http_client,
+        "me gusta el mate",
+        "web",
+        schedule_proposal=scheduler,
+        active_person=_unidentified_person(status),
+    )
+
+    scheduler.assert_not_called()


 @pytest.mark.unit
@@ -301,7 +401,7 @@ async def test_a_face_or_token_identified_turn_has_history_and_nothing_durable(
             message,
             "web",
             active_person=person,
-            schedule_consolidation=scheduler,
+            schedule_proposal=scheduler,
         )

     assert _histories(generate) == [[], ["primero", "Uno"]]
@@ -362,7 +462,7 @@ async def test_a_suspended_turn_reads_nothing_writes_nothing_and_spares_the_sess
         "stranger asks",
         "web",
         active_person=_unidentified_person(status),
-        schedule_consolidation=scheduler,
+        schedule_proposal=scheduler,
     )
     await text_turn.process_text_turn(http_client, "owner again", "web", active_person=owner)

@@ -435,7 +535,7 @@ async def test_llm_fallback_does_not_contaminate_memory(
         "Question",
         "web-a",
         active_person=_identified_person(),
-        schedule_consolidation=scheduler,
+        schedule_proposal=scheduler,
     )

     assert result.response == settings.llm_fallback_phrase
```

  Then the three deletions of D-12, which are not worth a diff. In each file delete the listed
  top-level functions with their decorators, then run
  `uv run ruff check --fix --select F401,F811 <file>` (the imports they leave unused go) and
  `uv run ruff format <file>`:

  - `tests/integration/test_memory_integration.py`: `_identified_person`,
    `test_consolidating_self_intro_does_not_anchor_owner`,
    `test_implicit_active_person_entity_is_person`, `test_consolidate_turn_with_mocked_ollama`;
  - `tests/integration/test_memory_relational.py`: `_identified_person`,
    `test_dirty_extraction_repaired_end_to_end`;
  - `tests/integration/test_onboarding_checklist.py`: `_identified_person`, `_turn`,
    `test_self_introduction_does_not_anchor_legacy_owner`.

  Last, `tests/integration/test_vision_memoria.py` is replaced whole: its onboarding and correction
  scenarios went with the function they drove, and the two retrieval scenarios that stay are seeded
  straight through the repositories.

```python
"""Acceptance exam of the retrieval half of the project vision (F4-D4, docs/audit/04 §5).

Two scenarios against a real temporary SQLite DB:

1. Recall after a process restart (empty working memory) via ``build_context``: the question
   "¿cómo se llaman mis hijos?" / "¿cómo se llama mi mascota?" is answered from the DB alone.
2. A manual identity does not revive the legacy onboarding interview.

The family is seeded straight through the legacy repositories. The scenarios that used to seed
it through ``consolidate_turn`` (extract, normalise, persist) and its correction scenario went
away with that function (ADR 0021 decision 11, Plan 0062); the supersede rule they pinned has its
own tests in ``test_memory_integration.py``, and the normaliser keeps its unit tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch
from uuid import UUID

if TYPE_CHECKING:
    from pathlib import Path

    import httpx

import pytest
from server.characters import build_system_prompt, get_character
from server.cognition.identity import (
    ActivePersonContext,
    ActivePersonStatus,
    HouseholdRole,
    IdentityEvidence,
    IdentityEvidenceSource,
)
from server.cognition.models import Confidence, ConfidenceBasis
from server.memory.context import build_context
from server.memory.declarative import assert_fact, upsert_entity
from server.memory.meta import get_flag
from server.settings import settings

from server import db


def _manual_active_person() -> ActivePersonContext:
    """Create explicit manual identity evidence for memory acceptance tests."""
    resolved_at = datetime(2026, 8, 10, tzinfo=UTC)
    confidence = Confidence(
        score=1.0,
        basis=ConfidenceBasis.ASSERTED,
        calibrated=True,
        reason="Explicit local selection",
    )
    return ActivePersonContext(
        person_id=7,
        display_name="Pipec",
        status=ActivePersonStatus.IDENTIFIED,
        confidence=confidence,
        role=HouseholdRole.UNKNOWN,
        evidence=(
            IdentityEvidence(
                evidence_id=UUID("11111111-1111-1111-1111-111111111111"),
                source=IdentityEvidenceSource.MANUAL,
                candidate_person_id=7,
                confidence=confidence,
                observed_at=resolved_at,
                reference="trusted-local-adapter",
            ),
        ),
        resolved_at=resolved_at,
    )


@pytest.fixture
async def memory_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[misc]
    """Provide a clean temporary DB for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "brain_db_path", db_path)

    # Reset the module-level connection so open_db creates a fresh one
    db._conn = None
    await db.open_db()
    await db.run_migrations()
    yield db_path
    await db.close_db()
    db._conn = None


async def _seed_family() -> None:
    """Persist the family the way the legacy relational retrieval reads it back."""
    await upsert_entity(name="Pipec", type="person")
    for child in ("Valentina", "Joaquín"):
        child_id = await upsert_entity(name=child, type="person")
        await assert_fact(entity_id=child_id, predicate="hijo_de", object_value="Pipec")
    pet_id = await upsert_entity(name="Luna", type="other")
    await assert_fact(entity_id=pet_id, predicate="mascota_de", object_value="Pipec")
    await assert_fact(entity_id=pet_id, predicate="especie", object_value="perro")


@pytest.mark.integration
async def test_recall_after_restart_children_and_pet(
    memory_db: Path, http_client: httpx.AsyncClient
) -> None:
    """Scenario 1 — after a 'restart' (empty working memory) the relational
    retrieval answers "mis hijos" and "mi mascota" from the DB alone."""
    await _seed_family()

    with patch(
        "server.memory.context.search_memories",
        new_callable=AsyncMock,
        return_value=[],
    ):
        children_ctx = await build_context(http_client, "¿cómo se llaman mis hijos?")
        pet_ctx = await build_context(http_client, "¿cómo se llama mi mascota?")

    children = {e.name for e in children_ctx.entities}
    assert {"Valentina", "Joaquín"} <= children
    assert "Luna" in {e.name for e in pet_ctx.entities}


@pytest.mark.integration
async def test_manual_context_does_not_enable_legacy_onboarding(memory_db: Path) -> None:
    """Scenario 2 — manual context must not revive the legacy onboarding owner assertion."""
    await _seed_family()
    assert await get_flag("owner_name") is None

    profile = get_character("iroko")
    prompt = build_system_prompt(
        profile,
        None,
        onboarding=False,
        active_person=_manual_active_person(),
    )
    assert "PRIMER ENCUENTRO" not in prompt
    # Sanity contrast: the sentinel really is what onboarding injects.
    assert "PRIMER ENCUENTRO" in build_system_prompt(profile, None, onboarding=True)
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_text_turn.py tests/integration/test_generic_turn_continuity.py tests/integration/test_transcribe_stream.py tests/unit/test_architecture_guards.py -q -p no:cacheprovider`
  Expected RED: `ImportError: cannot import name 'ProposalScheduler' from 'server.text_turn'`.
- [ ] **Step 3: Implement:**

```diff
diff --git a/server/src/server/memory/consolidation.py b/server/src/server/memory/consolidation.py
--- a/server/src/server/memory/consolidation.py
+++ b/server/src/server/memory/consolidation.py
@@ -1,34 +1,28 @@
-"""Extract entities, facts, and episodic memories from a conversation turn.
+"""The benchmark's extraction seam: one local-model call over a whole exchange.

-Runs as a FastAPI ``BackgroundTask`` — the caller has already returned a
-response to the user. All errors are caught, logged, and swallowed so that
-consolidation failures are never visible to the user.
+``consolidate_turn`` — the ``MANUAL``-gated writer of the legacy tables — is gone (ADR 0021
+decision 11, Plan 0062): it never ran in production, wrote around the authorization policy and
+stored the whole turn as an episode. What stays is the prompt and ``_extract_via_ollama``, which
+the CM-0 benchmark (``just eval-longitudinal``) and ``just eval-memory`` use through
+``scripts/eval_consolidation.extract_case_items``, behaviourally unchanged, so the baseline
+stays comparable until CM-3b replaces it. Nothing under ``server`` calls it at runtime.
+
+The candidate path of CM-3a has its own extractor (``candidate_extraction``), which sees only
+the user's words.
 """

 from __future__ import annotations

-import asyncio
-import logging
-
-import httpx
+from typing import TYPE_CHECKING

-from server.cognition.identity import (
-    ActivePersonContext,
-    ActivePersonStatus,
-    IdentityEvidenceSource,
-)
 from server.exceptions import LLMError
 from server.llm_transport import ollama_chat, strip_json_fences
-from server.memory.declarative import assert_fact, find_entities_by_name, upsert_entity
-from server.memory.normalize import normalize_extraction
-from server.memory.semantic import store_memory
-from server.schemas import EntityType, TurnExtraction
+from server.schemas import TurnExtraction
 from server.settings import settings

-logger = logging.getLogger(__name__)
+if TYPE_CHECKING:
+    import httpx

-_LOW_IMPORTANCE = 0.2
-_RETRY_DELAY_S = 5.0
 _EXTRACTION_SYSTEM = """\
 Eres un extractor de información de conversaciones para la memoria de un \
 robot asistente personal.
@@ -111,173 +105,7 @@ async def _extract_via_ollama(
     text = strip_json_fences(raw)
     try:
         return TurnExtraction.model_validate_json(text)
-    except Exception as exc:
-        raise LLMError(f"Extraction returned invalid JSON: {exc}") from exc
-
-
-async def _extract(
-    client: httpx.AsyncClient, user_text: str, assistant_text: str
-) -> TurnExtraction:
-    """Extract locally with Ollama, retrying once on a transient failure.
-
-    Transient failures (model still loading or a brief local HTTP interruption)
-    get a single retry after a short delay.
-
-    Args:
-        client: Shared, lifecycle-owned HTTP client (Plan 0039).
-        user_text: The user's message.
-        assistant_text: The robot's response.
-
-    Returns:
-        Validated ``TurnExtraction``.
-
-    Raises:
-        LLMError: If both attempts fail with a malformed response.
-        httpx.HTTPError: If both attempts fail reaching Ollama.
-    """
-    try:
-        return await _extract_via_ollama(client, user_text, assistant_text)
-    except (LLMError, httpx.HTTPError) as exc:
-        logger.warning(
-            "Local extraction failed — retrying in %.0fs: %s",
-            _RETRY_DELAY_S,
-            exc,
-        )
-        await asyncio.sleep(_RETRY_DELAY_S)
-        return await _extract_via_ollama(client, user_text, assistant_text)
-
-
-def _manual_active_person_name(active_person: ActivePersonContext | None) -> str | None:
-    """Return a validated turn-local subject reference, never authorization."""
-    if (
-        active_person is None
-        or active_person.status is not ActivePersonStatus.IDENTIFIED
-        or active_person.person_id is None
-        or active_person.display_name is None
-    ):
-        return None
-    if any(
-        evidence.source is IdentityEvidenceSource.MANUAL
-        and evidence.candidate_person_id == active_person.person_id
-        for evidence in active_person.evidence
-    ):
-        return active_person.display_name
-    return None
-
-
-async def consolidate_turn(  # noqa: PLR0912
-    client: httpx.AsyncClient,
-    user_text: str,
-    assistant_text: str,
-    *,
-    active_person: ActivePersonContext | None = None,
-) -> None:
-    """Extract and persist entities, facts, and memories from one turn.
-
-    Designed to run as a ``BackgroundTask`` after the HTTP response has been
-    sent. All exceptions are caught and logged — failures here must never
-    propagate to the user.
-
-    Args:
-        client: Shared, lifecycle-owned HTTP client (Plan 0039). The app's
-            lifespan outlives any single request's background tasks, so
-            this stays valid for the whole call.
-        user_text: The user's message.
-        assistant_text: The robot's response.
-        active_person: Explicit manual identity evidence for this turn only.
-    """
-    active_person_name = _manual_active_person_name(active_person)
-    if active_person_name is None:
-        logger.info("Skipping consolidation without identified manual evidence")
-        return
-    try:
-        extraction = await _extract(client, user_text, assistant_text)
-    except (LLMError, httpx.HTTPError) as exc:
-        logger.warning("Consolidation extraction failed: %s", exc)
-        return
-
-    extraction = normalize_extraction(
-        extraction,
-        active_person_name=active_person_name,
-        user_text=user_text,
-    )
-
-    if extraction.importance < _LOW_IMPORTANCE and not extraction.facts:
-        logger.debug("Turn below importance threshold — skipping consolidation")
-        return
-
-    entity_ids: dict[str, int] = {}
-    for ent in extraction.entities:
-        try:
-            eid = await upsert_entity(
-                name=ent.name,
-                type=ent.type,
-                attributes=ent.attributes,
-                aliases=ent.aliases,
-            )
-            entity_ids[ent.name] = eid
-        except Exception as exc:
-            logger.warning(
-                "Entity upsert failed: type=%s (%s)",
-                ent.type,
-                type(exc).__name__,
-                extra={"event": "entity.upsert_failed", "error_type": type(exc).__name__},
-            )
-
-    memory_id: int | None = None
-    if extraction.episodic_summary:
-        try:
-            memory_id = await store_memory(
-                client,
-                kind="episodic",
-                content=f"[user] {user_text}\n[assistant] {assistant_text}",
-                summary=extraction.episodic_summary,
-                importance=extraction.importance,
-                related_entities=list(entity_ids.values()),
-            )
-        except Exception as exc:
-            logger.warning("Memory store failed: %s", exc)
-
-    for fact in extraction.facts:
-        entity_id: int | None = entity_ids.get(fact.subject)
-        if entity_id is None:
-            matches = await find_entities_by_name(fact.subject, limit=1)
-            if matches:
-                entity_id = int(matches[0]["id"])
-            else:
-                # A validated active person is a person, not an abstract concept.
-                implicit_type: EntityType = (
-                    "person"
-                    if fact.subject.casefold() == active_person_name.casefold()
-                    else "concept"
-                )
-                try:
-                    entity_id = await upsert_entity(name=fact.subject, type=implicit_type)
-                except Exception as exc:
-                    logger.warning(
-                        "Implicit entity creation failed (%s)",
-                        type(exc).__name__,
-                        extra={
-                            "event": "entity.implicit_failed",
-                            "error_type": type(exc).__name__,
-                        },
-                    )
-                    continue
-        try:
-            await assert_fact(
-                entity_id=entity_id,
-                predicate=fact.predicate,
-                object_value=fact.object,
-                confidence=fact.confidence,
-                source_memory_id=memory_id,
-            )
-        except Exception as exc:
-            logger.warning("Fact insert failed: %s", exc)
-
-    logger.info(
-        "Consolidated turn: entities=%d facts=%d memory_id=%s importance=%.2f",
-        len(entity_ids),
-        len(extraction.facts),
-        memory_id,
-        extraction.importance,
-    )
+    except ValueError:
+        # `from None` and no `{exc}`: a pydantic error quotes the offending input, which is the
+        # model's own output about the household; it must not reach a log line.
+        raise LLMError("Extraction returned invalid JSON") from None
diff --git a/server/src/server/routers/transcribe.py b/server/src/server/routers/transcribe.py
--- a/server/src/server/routers/transcribe.py
+++ b/server/src/server/routers/transcribe.py
@@ -40,7 +40,8 @@ from server.exceptions import (
     AudioContractError,
     UploadTooLargeError,
 )
-from server.memory.consolidation import consolidate_turn
+from server.memory.candidate_proposal import propose_candidates
+from server.memory.candidate_types import CandidateChannel
 from server.memory.household_authorization import record_authorization_decision
 from server.memory.policy_gated_v4_reader import PolicyGatedV4Reader
 from server.pipeline import (
@@ -55,7 +56,7 @@ from server.schemas_streaming import StreamEvent
 from server.settings import settings
 from server.streaming import guarantee_terminal_event, stream_pipeline, stream_response_plan
 from server.text_turn import (
-    ConsolidationScheduler,
+    ProposalScheduler,
     TextTurnResult,
     new_interaction_scope,
     prepare_text_turn,
@@ -215,22 +216,23 @@ def _logged_voice_observer(

 def _voice_controller(
     client: httpx.AsyncClient,
-    background_tasks: BackgroundTasks,
     *,
     request_identity: _RequestIdentity | None = None,
     identify_speaker: SpeakerIdentifier | None = None,
+    schedule_proposal: ProposalScheduler | None = None,
 ) -> CognitiveController:
     """Compose the bounded controller used by a public voice turn.

     Args:
         client: Shared, lifecycle-owned HTTP client (Plan 0039), closed over
-            by the legacy-turn delegate and the consolidation scheduler.
-        background_tasks: Queue used to schedule post-turn consolidation.
+            by the legacy-turn delegate.
         request_identity: Optional request-scoped actor/consent resolver over
             the fused face, voice and PIN evidence (Plan 0054). When omitted,
             the controller falls back to its own public-unknown defaults.
         identify_speaker: Names the speaker of a generic turn from the face and an
             observed token (Plan 0061, ADR 0020); when omitted the speaker is unknown.
+        schedule_proposal: Schedules the background candidate proposal of a successful
+            generic turn (Plan 0062); when omitted nothing is proposed.
     """

     async def legacy_turn(message: str, conversation_id: str) -> TextTurnResult:
@@ -248,7 +250,7 @@ def _voice_controller(
             conversation_id,
             active_person=speaker.actor,
             suspend_cause=speaker.cause,
-            schedule_consolidation=_consolidation_scheduler(client, background_tasks),
+            schedule_proposal=schedule_proposal,
         )

     if request_identity is None:
@@ -271,30 +273,36 @@ def _voice_controller(
     )


-def _consolidation_scheduler(
+def _proposal_scheduler(
     client: httpx.AsyncClient,
     background_tasks: BackgroundTasks,
-) -> ConsolidationScheduler:
-    """Adapt FastAPI background tasks to the text service callback.
+    *,
+    event: CognitiveEvent[TextTurnPayload],
+    wav_bytes: bytes,
+    channel: CandidateChannel,
+) -> ProposalScheduler:
+    """Adapt FastAPI background tasks to the text service's proposal callback (ADR 0021 §10).

     Args:
         client: Shared, lifecycle-owned HTTP client (Plan 0039) — safe to
             close over here, since the app's lifespan outlives any single
             request's background tasks.
-        background_tasks: Queue used to schedule post-turn consolidation.
+        background_tasks: Queue used to run the proposal after the response was sent.
+        event: The turn's event; its correlation id joins audit rows to candidates.
+        wav_bytes: The turn's own clip — WAV, 16 000 Hz, mono, int16 — held in memory only,
+            for the voice check that runs before anything is extracted.
+        channel: The voice route the proposal belongs to.
     """

-    def schedule(
-        message: str,
-        response: str,
-        active_person: ActivePersonContext,
-    ) -> None:
+    def schedule(message: str, active_person: ActivePersonContext) -> None:
         background_tasks.add_task(
-            consolidate_turn,
+            propose_candidates,
             client,
             message,
-            response,
-            active_person=active_person,
+            active_person,
+            event=event,
+            wav_bytes=wav_bytes,
+            channel=channel,
         )

     return schedule
@@ -339,7 +347,7 @@ async def transcribe(

     Args:
         audio: WAV at 16kHz, mono, int16, within MAX_AUDIO_UPLOAD_BYTES.
-        background_tasks: Queue for successful voice-turn consolidation.
+        background_tasks: Queue for the candidate proposal of a successful voice turn.
         x_iroko_identity_token: Optional one-use owner unlock token. Absent,
             expired, replayed, or malformed tokens resolve to the public
             unknown actor without disclosing which case occurred.
@@ -380,7 +388,6 @@ async def transcribe(
     event = _voice_event_from_transcript(text_heard)
     controller = _voice_controller(
         resources.http_client,
-        background_tasks,
         request_identity=request_identity,
         identify_speaker=partial(
             identify_generic_speaker,
@@ -389,6 +396,13 @@ async def transcribe(
             frame=frame_bytes,
             event=event,
         ),
+        schedule_proposal=_proposal_scheduler(
+            resources.http_client,
+            background_tasks,
+            event=event,
+            wav_bytes=audio_bytes,
+            channel=CandidateChannel.VOICE_CLASSIC,
+        ),
     )
     decision = await controller.decide(event)

@@ -472,7 +486,7 @@ async def transcribe_stream(

     Args:
         audio: WAV at 16kHz, mono, int16, within MAX_AUDIO_UPLOAD_BYTES.
-        background_tasks: Queue for successful voice-turn consolidation.
+        background_tasks: Queue for the candidate proposal of a successful voice turn.
         x_iroko_identity_token: Optional one-use owner unlock token — same
             contract as classic /transcribe (Plan 0027).
         frame: Optional webcam frame attached for in-request face
@@ -512,7 +526,7 @@ async def transcribe_stream(

     event = _voice_event_from_transcript(text_heard)
     decision = await _voice_controller(
-        resources.http_client, background_tasks, request_identity=request_identity
+        resources.http_client, request_identity=request_identity
     ).decide(event)
     # Streaming has no second-round frame upload — a scene request always
     # gets the fixed unavailable plan, regardless of VISION_ENABLED.
@@ -557,8 +571,12 @@ async def transcribe_stream(
                 prepared=prepared,
                 stt_ms=stt_ms,
                 request_start=request_start,
-                schedule_consolidation=_consolidation_scheduler(
-                    resources.http_client, background_tasks
+                schedule_proposal=_proposal_scheduler(
+                    resources.http_client,
+                    background_tasks,
+                    event=event,
+                    wav_bytes=audio_bytes,
+                    channel=CandidateChannel.VOICE_STREAM,
                 ),
             )
         )
diff --git a/server/src/server/streaming.py b/server/src/server/streaming.py
--- a/server/src/server/streaming.py
+++ b/server/src/server/streaming.py
@@ -48,8 +48,8 @@ from server.streaming_render import (
     synthesize_sentence,
 )
 from server.text_turn import (
-    ConsolidationScheduler,
     PreparedTextTurn,
+    ProposalScheduler,
     record_text_turn,
 )
 from server.user_emotion import classify_user_emotion
@@ -107,7 +107,7 @@ async def _consume_llm_stream(
 def _record_success(
     prepared: PreparedTextTurn,
     state: StreamState,
-    scheduler: ConsolidationScheduler,
+    scheduler: ProposalScheduler,
 ) -> None:
     """Persist a turn — only ever called for a fully successful stream."""
     if state.outcome is not StreamOutcome.OK or not state.recordable or not state.response_parts:
@@ -117,7 +117,7 @@ def _record_success(
         " ".join(state.response_parts),
         active_person=prepared.active_person,
         continuity_turn=prepared.continuity,
-        schedule_consolidation=scheduler,
+        schedule_proposal=scheduler,
     )


@@ -175,7 +175,7 @@ async def stream_pipeline(
     prepared: PreparedTextTurn,
     stt_ms: int,
     request_start: float,
-    schedule_consolidation: ConsolidationScheduler,
+    schedule_proposal: ProposalScheduler,
 ) -> AsyncIterator[str]:
     """Stream STT->LLM->TTS as NDJSON, synthesizing speech sentence by sentence.

@@ -194,7 +194,7 @@ async def stream_pipeline(
         prepared: Shared prompt inputs and internal scope for one voice request.
         stt_ms: STT elapsed time, measured by the caller.
         request_start: ``time.perf_counter()`` reading from request start.
-        schedule_consolidation: Channel-owned background scheduling callback.
+        schedule_proposal: Channel-owned background proposal scheduling callback.

     Yields:
         NDJSON lines (each ending in ``\\n``), see schemas_streaming.py.
@@ -220,7 +220,7 @@ async def stream_pipeline(
         async for line in emit_fallback(state, reason=StreamFallbackReason.LLM_ERROR):
             yield line

-    _record_success(prepared, state, schedule_consolidation)
+    _record_success(prepared, state, schedule_proposal)

     total_ms = _elapsed_ms(request_start)
     llm_ms = llm_elapsed_ms(total_ms, stt_ms, state.tts_ms_total)
diff --git a/server/src/server/text_turn.py b/server/src/server/text_turn.py
--- a/server/src/server/text_turn.py
+++ b/server/src/server/text_turn.py
@@ -19,6 +19,7 @@ from server.cognition.identity import (
     IdentityEvidenceSource,
     resolve_active_person,
 )
+from server.cognition.strong_actor import is_face_actor
 from server.exceptions import BrainMemoryError, LLMError
 from server.memory import continuity
 from server.memory.context import build_context
@@ -29,7 +30,10 @@ from server.settings import settings

 logger = logging.getLogger(__name__)

-ConsolidationScheduler = Callable[[str, str, ActivePersonContext], None]
+#: Channel-owned callback that schedules a background candidate proposal (ADR 0021 §10). It
+#: receives the user's own words and the face-identified actor; the route that owns the clip
+#: and the turn's correlation id binds them. It never receives the assistant's reply.
+ProposalScheduler = Callable[[str, ActivePersonContext], None]


 @dataclass(frozen=True)
@@ -234,9 +238,9 @@ def record_text_turn(
     *,
     active_person: ActivePersonContext | None = None,
     continuity_turn: ContinuityTurn | None = None,
-    schedule_consolidation: ConsolidationScheduler | None = None,
+    schedule_proposal: ProposalScheduler | None = None,
 ) -> None:
-    """Record a successful turn and optionally schedule consolidation.
+    """Record a successful turn and optionally schedule a candidate proposal.

     Args:
         message: Current user message.
@@ -244,8 +248,9 @@ def record_text_turn(
         active_person: Internally resolved evidence for this turn only.
         continuity_turn: The session view this turn read; a suspended or stale turn writes
             nothing.
-        schedule_consolidation: Optional channel-owned scheduling callback; reached only by a
-            manually verified identity, never by a face or a token.
+        schedule_proposal: Optional channel-owned scheduling callback; reached only by a
+            face-identified speaker with no token, and only with the candidate kill-switch on.
+            The callback's own background task checks the voice before anything is extracted.
     """
     if not settings.memory_enabled:
         return
@@ -254,10 +259,15 @@ def record_text_turn(
         turn_log.log_memory("recorded", "identified speaker, exchange kept in the session")
     else:
         turn_log.log_memory("discarded", "no identified speaker, nothing kept")
-    if schedule_consolidation is not None and _manual_evidence(resolved_person) is not None:
-        # Identity gates this legacy callback; it is not an authorization decision.
-        schedule_consolidation(message, response, resolved_person)
-        turn_log.log_memory("consolidation-scheduled", "verified identity")
+    if (
+        schedule_proposal is not None
+        and settings.memory_candidates_enabled
+        and is_face_actor(resolved_person)
+    ):
+        # Identity gates this callback; it is not an authorization decision (the policy is
+        # asked, and audited, in the background task, with the voice of the turn's own clip).
+        schedule_proposal(message, resolved_person)
+        turn_log.log_memory("proposal-scheduled", "face-identified speaker")


 async def process_text_turn(
@@ -268,7 +278,7 @@ async def process_text_turn(
     perception: str | None = None,
     active_person: ActivePersonContext | None = None,
     suspend_cause: SuspendCause | None = None,
-    schedule_consolidation: ConsolidationScheduler | None = None,
+    schedule_proposal: ProposalScheduler | None = None,
 ) -> TextTurnResult:
     """Generate and record one channel-agnostic text turn.

@@ -279,7 +289,7 @@ async def process_text_turn(
         perception: Optional textual visual perception for this turn.
         active_person: Internally resolved evidence for this turn only.
         suspend_cause: Why the speaker could not be identified, for the transition log.
-        schedule_consolidation: Optional channel-owned scheduling callback.
+        schedule_proposal: Optional channel-owned proposal scheduling callback.

     Returns:
         Text, emotion, elapsed time, and fallback status for the turn.
@@ -300,7 +310,7 @@ async def process_text_turn(
             response,
             active_person=prepared.active_person,
             continuity_turn=prepared.continuity,
-            schedule_consolidation=schedule_consolidation,
+            schedule_proposal=schedule_proposal,
         )
     duration_ms = round((time.perf_counter() - started) * 1000)
     return TextTurnResult(response, emotion, duration_ms, llm_failed)
```

- [ ] **Step 4: Run to see them pass, then lint and types.** Run the whole CI selection once with
  the flags pinned (`MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and not eval" -n auto`):
  every test that expects identification must pin `memory_enabled` itself (Plan 0061's lesson).
  Check the benchmark seam still starts: `uv run python scripts/eval_consolidation.py --help` and
  `uv run python scripts/eval_longitudinal_memory.py --help`.
- [ ] **Step 5: Commit** `feat(server): wire proposals, retire consolidate_turn (plan 0062)`; check
  `git log -1`.

---

## Task 14: Retire `propose_memory` and `commit_memory`

**Files:**
- Modify: `server/src/server/cognition/authorization.py`, `server/src/server/cognition/models.py`
- Test: modified `tests/unit/test_architecture_guards.py`, `tests/unit/test_authorization_characterization.py`, `tests/unit/test_cognitive_models.py`, `tests/unit/test_personal_memory_policy.py`

**Interfaces:**
- Produces: `AuthorizationAction` without `PROPOSE_MEMORY` and `COMMIT_MEMORY`; the policy without
  `_evaluate_memory_proposal` and its two ids; nine pre-existing actions pinned by the
  characterization grid (grid size 138 006 to 112 914); a guard that the four names exist nowhere in
  `server`; and a guard that pins who may call `insert_candidate` (`memory/candidates.py` and the
  proposal), `mark_offered` / `resolve_candidate*` (the store and the writer) and `promote` (the
  writer): Plan 0063 adds its dialogue module to those homes as a decision.

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/tests/unit/test_architecture_guards.py b/tests/unit/test_architecture_guards.py
--- a/tests/unit/test_architecture_guards.py
+++ b/tests/unit/test_architecture_guards.py
@@ -142,19 +142,19 @@ _NEW_ACTION_NAMES = frozenset(
         "forget_personal_memory",
     }
 )
-# CM-3 decides what happens to these four; until then only the model and the policy know them.
+# `PROPOSE_MEMORY` and `COMMIT_MEMORY` left in Plan 0062 (nothing consumed them); these two
+# are CM-6's, so until then only the model and the policy know them.
 _LEGACY_MEMORY_ACTION_NAMES = frozenset(
     {
-        "PROPOSE_MEMORY",
-        "COMMIT_MEMORY",
         "DELETE_HOUSEHOLD_DATA",
         "EXPORT_HOUSEHOLD_DATA",
-        "propose_memory",
-        "commit_memory",
         "delete_household_data",
         "export_household_data",
     }
 )
+_RETIRED_ACTION_NAMES = frozenset(
+    {"PROPOSE_MEMORY", "COMMIT_MEMORY", "propose_memory", "commit_memory"}
+)
 # The model and the policy, plus the one module that asks the policy about a candidate step
 # (Plan 0062): every other module reaches the actions through it.
 _ACTION_HOMES = frozenset(
@@ -249,7 +249,7 @@ def test_the_personal_memory_actions_exist_only_in_the_model_and_the_policy() ->

 @pytest.mark.unit
 def test_the_legacy_memory_actions_are_used_only_by_the_model_and_the_policy() -> None:
-    """Nobody else consumes `propose_memory`, `commit_memory`, delete or export (verified)."""
+    """Nobody else consumes delete or export (verified)."""
     assert _outside(_sources(), _ACTION_HOMES, _LEGACY_MEMORY_ACTION_NAMES) == []


@@ -287,7 +287,7 @@ def test_the_personal_memory_guards_detect_a_violation() -> None:
         "routers/leak.py": (
             "from server.cognition.models import AuthorizationAction\n"
             "a = AuthorizationAction.FORGET_PERSONAL_MEMORY\n"
-            "b = AuthorizationAction.COMMIT_MEMORY\n"
+            "b = AuthorizationAction.DELETE_HOUSEHOLD_DATA\n"
             "c = OwnerUnlockScope.PERSONAL_MEMORY_FORGET\n"
             'd = "read_personal_conversation_memory"\n'
             'e = "delete_household_data"\n'
@@ -474,3 +474,46 @@ def test_the_proposal_guards_detect_a_violation() -> None:
         "routers/vision.py",
     ]
     assert _imports_name(leak, "consolidate_turn") == ["memory/legacy.py"]
+
+
+@pytest.mark.unit
+def test_the_retired_memory_actions_exist_nowhere() -> None:
+    """ADR 0021 decision 11: no enum member, branch or string names them any more."""
+    assert _outside(_sources(), frozenset(), _RETIRED_ACTION_NAMES) == []
+
+
+# --- who may write or move a candidate (Plan 0062, ADR 0021 decisions 3 and 8) --------------
+# The firewall rule (face and voice of the same person on the turn's clip) is enforced by the
+# caller of the store, so the callers are pinned: a second caller must be a decision, not an
+# accident. Plan 0063 adds the dialogue module that offers and answers.
+_CANDIDATE_INSERT_HOMES = frozenset({"memory/candidates.py", "memory/candidate_proposal.py"})
+_CANDIDATE_MOVE_HOMES = frozenset({"memory/candidates.py", "memory/memory_writer.py"})
+_CANDIDATE_MOVES = frozenset(
+    {"mark_offered", "resolve_candidate", "resolve_candidate_in_transaction"}
+)
+_WRITER_HOMES = frozenset({"memory/memory_writer.py"})
+
+
+@pytest.mark.unit
+def test_only_the_proposal_inserts_and_only_the_writer_resolves_a_candidate() -> None:
+    sources = _sources()
+
+    assert _outside(sources, _CANDIDATE_INSERT_HOMES, frozenset({"insert_candidate"})) == []
+    assert _outside(sources, _CANDIDATE_MOVE_HOMES, _CANDIDATE_MOVES) == []
+    assert _outside(sources, _WRITER_HOMES, frozenset({"promote"})) == []
+
+
+@pytest.mark.unit
+def test_the_candidate_caller_guards_detect_a_violation() -> None:
+    leak = {
+        "routers/leak.py": "await insert_candidate(p)\nawait candidates.mark_offered(1)\n",
+        "memory/candidate_proposal.py": "await insert_candidate(p)\n",
+        "memory/memory_writer.py": "await resolve_candidate_in_transaction(c)\nawait promote(1)\n",
+        "memory/other.py": "await promote(1)\n",
+    }
+
+    assert _outside(leak, _CANDIDATE_INSERT_HOMES, frozenset({"insert_candidate"})) == [
+        "routers/leak.py"
+    ]
+    assert _outside(leak, _CANDIDATE_MOVE_HOMES, _CANDIDATE_MOVES) == ["routers/leak.py"]
+    assert _outside(leak, _WRITER_HOMES, frozenset({"promote"})) == ["memory/other.py"]
diff --git a/tests/unit/test_authorization_characterization.py b/tests/unit/test_authorization_characterization.py
--- a/tests/unit/test_authorization_characterization.py
+++ b/tests/unit/test_authorization_characterization.py
@@ -1,7 +1,8 @@
-"""Characterization guard: the eleven pre-existing authorization actions never change.
+"""Characterization guard: the nine pre-existing authorization actions never change.

-Plan 0060 adds personal-memory actions to the policy. This file pins the exact decision of
-every action that existed before, over a fixed grid, so a new action cannot shift an old one
+Plan 0060 adds personal-memory actions to the policy (Plan 0062 retires `propose_memory` and
+`commit_memory`, which nothing consumed). This file pins the exact decision of every action
+that remains from before, over a fixed grid, so a new action cannot shift an old one
 by accident. The grid uses literal value tuples (never enum iteration): a new enum member
 therefore cannot silently enter it, and a renamed or removed value fails loudly.

@@ -44,8 +45,6 @@ _LEGACY_ACTIONS = (
     "general_conversation",
     "read_household_data",
     "execute_household_tool",
-    "propose_memory",
-    "commit_memory",
     "manage_household_role",
     "enroll_biometric",
     "export_household_data",
@@ -212,8 +211,6 @@ _EXPECTED_DIGESTS: dict[str, str] = {
     "general_conversation": ("45ae2d0642f8fbfbeb5ea7a2f4cd1e1b5a5487a5ab01e97a5473d52f6461c638"),
     "read_household_data": ("dd378d2f1c75fa7ca09aca3a137fb09aa11d7f35f55ca5d8c9cea9f2b05523c6"),
     "execute_household_tool": ("0b9de2733707a882238b887d99624f5306c0e1394ad7de8b524925b15b9fa7f7"),
-    "propose_memory": ("1a66187ddf8212a1f5a08bae175b8da2236cfb6e59b96564a62ac8acd9743743"),
-    "commit_memory": ("56b0f98d4ae17bb5b5d7e68b266df3f752bf429ff193d950fc88253c18c3407a"),
     "manage_household_role": ("10e8e49deca66537dad7ebc4a05d2181a1e738eae9c16855449ced9ad90176eb"),
     "enroll_biometric": ("fea4b8d850f64302c906f7f7cdb727c2259ec2566c087c67f6c4b9b2bd234902"),
     "export_household_data": ("b585ee06d63c0f07d02b5ad38c97ce087ed8d17062870845dcbd55e8941ff6fe"),
@@ -254,19 +251,6 @@ _EXPECTED_COUNTS: dict[str, dict[tuple[str, str], int]] = {
         ("requires_confirmation", "p0.5.child-public-confirmation"): 9,
         ("requires_confirmation", "p0.5.sensitive-confirmation"): 976,
     },
-    "propose_memory": {
-        ("allowed", "p0.5.owner-memory-proposal"): 2591,
-        ("denied", "p0.5.assurance-required"): 3072,
-        ("denied", "p0.5.default-deny"): 567,
-        ("denied", "p0.5.identity-unresolved"): 1134,
-        ("requires_confirmation", "p0.5.memory-proposal-confirmation"): 5182,
-    },
-    "commit_memory": {
-        ("allowed", "p0.5.owner-administration"): 2591,
-        ("denied", "p0.5.assurance-required"): 3072,
-        ("denied", "p0.5.default-deny"): 5749,
-        ("denied", "p0.5.identity-unresolved"): 1134,
-    },
     "manage_household_role": {
         ("allowed", "p0.5.owner-administration"): 2591,
         ("denied", "p0.5.assurance-required"): 3072,
@@ -306,7 +290,7 @@ _EXPECTED_COUNTS: dict[str, dict[tuple[str, str], int]] = {
         ("denied", "p0.5.identity-unresolved"): 1134,
     },
 }
-_EXPECTED_GRID_SIZE = 138006
+_EXPECTED_GRID_SIZE = 112914


 @pytest.mark.parametrize("action", _LEGACY_ACTIONS)
diff --git a/tests/unit/test_cognitive_models.py b/tests/unit/test_cognitive_models.py
--- a/tests/unit/test_cognitive_models.py
+++ b/tests/unit/test_cognitive_models.py
@@ -134,8 +134,6 @@ def _event_values() -> dict[str, object]:
                 "general_conversation",
                 "read_household_data",
                 "execute_household_tool",
-                "propose_memory",
-                "commit_memory",
                 "manage_household_role",
                 "enroll_biometric",
                 "export_household_data",
@@ -220,7 +218,7 @@ def test_authorization_decision_requires_aware_utc_time_and_is_immutable() -> No
     assert isinstance(decision.data_categories, frozenset)

     with pytest.raises(ValidationError):
-        decision.action = AuthorizationAction.COMMIT_MEMORY
+        decision.action = AuthorizationAction.DELETE_HOUSEHOLD_DATA

     with pytest.raises(ValidationError):
         AuthorizationDecision.model_validate(
@@ -380,7 +378,7 @@ def test_authorization_request_is_immutable_and_rejects_untyped_categories() ->
     )

     with pytest.raises(ValidationError):
-        request.action = AuthorizationAction.COMMIT_MEMORY
+        request.action = AuthorizationAction.DELETE_HOUSEHOLD_DATA
     with pytest.raises(ValidationError):
         AuthorizationRequest.model_validate(
             {**request.model_dump(), "visibility": frozenset({"unclassified"})}
diff --git a/tests/unit/test_personal_memory_policy.py b/tests/unit/test_personal_memory_policy.py
--- a/tests/unit/test_personal_memory_policy.py
+++ b/tests/unit/test_personal_memory_policy.py
@@ -48,8 +48,6 @@ _LEGACY_ACTIONS = frozenset(
         "general_conversation",
         "read_household_data",
         "execute_household_tool",
-        "propose_memory",
-        "commit_memory",
         "manage_household_role",
         "enroll_biometric",
         "export_household_data",
```

- [ ] **Step 2: Run them to see them fail.**
  `uv run pytest tests/unit/test_architecture_guards.py tests/unit/test_cognitive_models.py -q -p no:cacheprovider`
  Expected RED: 3 failures (the guard names `cognition/authorization.py` and `cognition/models.py`;
  the enum snapshot still lists the two members); the caller guard is green on arrival, it pins
  today's callers.
- [ ] **Step 3: Implement:**

```diff
diff --git a/server/src/server/cognition/authorization.py b/server/src/server/cognition/authorization.py
--- a/server/src/server/cognition/authorization.py
+++ b/server/src/server/cognition/authorization.py
@@ -344,30 +344,6 @@ def _evaluate_read(request: AuthorizationRequest) -> AuthorizationDecision:
     return _evaluate_normal_household_read(request)


-def _evaluate_memory_proposal(request: AuthorizationRequest) -> AuthorizationDecision:
-    """Evaluate a proposed durable memory update without persisting it."""
-    if request.actor.role is HouseholdRole.OWNER:
-        return _decision(
-            request,
-            AuthorizationStatus.ALLOWED,
-            "p0.5.owner-memory-proposal",
-            "Owner policy permits a memory proposal.",
-        )
-    if request.actor.role in {HouseholdRole.ADULT, HouseholdRole.CHILD}:
-        return _decision(
-            request,
-            AuthorizationStatus.REQUIRES_CONFIRMATION,
-            "p0.5.memory-proposal-confirmation",
-            "Memory proposals require a scoped confirmation.",
-        )
-    return _decision(
-        request,
-        AuthorizationStatus.DENIED,
-        "p0.5.default-deny",
-        "No policy grants this request.",
-    )
-
-
 def _evaluate_owner_administration(request: AuthorizationRequest) -> AuthorizationDecision:
     """Evaluate an owner-only administrative operation."""
     if request.actor.role is HouseholdRole.OWNER:
@@ -560,10 +536,7 @@ def _evaluate_legacy_request(request: AuthorizationRequest) -> AuthorizationDeci
         AuthorizationAction.EXECUTE_HOUSEHOLD_TOOL,
     }:
         return _evaluate_read(request)
-    if request.action is AuthorizationAction.PROPOSE_MEMORY:
-        return _evaluate_memory_proposal(request)
     if request.action in {
-        AuthorizationAction.COMMIT_MEMORY,
         AuthorizationAction.MANAGE_HOUSEHOLD_ROLE,
         AuthorizationAction.EXPORT_HOUSEHOLD_DATA,
         AuthorizationAction.DELETE_HOUSEHOLD_DATA,
diff --git a/server/src/server/cognition/models.py b/server/src/server/cognition/models.py
--- a/server/src/server/cognition/models.py
+++ b/server/src/server/cognition/models.py
@@ -62,8 +62,6 @@ class AuthorizationAction(str, _Enum):  # noqa: UP042
     GENERAL_CONVERSATION = "general_conversation"
     READ_HOUSEHOLD_DATA = "read_household_data"
     EXECUTE_HOUSEHOLD_TOOL = "execute_household_tool"
-    PROPOSE_MEMORY = "propose_memory"
-    COMMIT_MEMORY = "commit_memory"
     MANAGE_HOUSEHOLD_ROLE = "manage_household_role"
     ENROLL_BIOMETRIC = "enroll_biometric"
     EXPORT_HOUSEHOLD_DATA = "export_household_data"
```

- [ ] **Step 4: Run to see them pass, then lint and types.** Also
  `uv run pytest tests/unit/test_authorization_characterization.py tests/unit/test_personal_memory_policy.py -q -p no:cacheprovider`.
- [ ] **Step 5: Commit** `refactor(server): retire propose_memory and commit_memory (plan 0062)`;
  check `git log -1`.

---

## Task 15: Local smoke by Pipec

**Files:** new `docs/evals/0062-memory-candidates-local-smoke.md` (outcomes only) and its entry in
`docs/evals/README.md`.

This is **not** the hardware acceptance (the offer, the answer and the cases of ADR 0021
*Acceptance* are Plan 0063). It proves, on the real database and the real start-up path, what the
tests prove on temporary ones. Pipec starts every process; record each case as pass, fail or not
run, with counts and durations, never a sentence, a value, a name or a token.

- [ ] **Step 1: `just gate`.** Record its outcome and the test count (the rehearsal's was
  2905 collected).
- [ ] **Step 2: Start-up with the switch off.** With `MEMORY_CANDIDATES_ENABLED=false` (the
  default), `just run-server`. Expected log line: `Candidates voided at start-up: 0`. Stop it.
- [ ] **Step 3: Start-up with the switch on.** `MEMORY_CANDIDATES_ENABLED=true` in `.env`,
  `just run-server`; no candidate line appears and the server is ONLINE. Stop it.
- [ ] **Step 4: A matching sentence without enrolment.** With the switch on and the owner's voice
  **not** enrolled (the state today), say "me gusta el mate". Expected: a normal reply and a log
  line `Candidate proposal: dropped (strong_unreachable)`; the database holds no live candidate
  (`uv run python -c` over `sqlite3`, `SELECT COUNT(*) FROM memory_candidates` is 0).
- [ ] **Step 5: A non-matching sentence.** Say "hola". (Steps 4 and 5 log a `dropped (...)` line
  only when the face resolved the owner on that turn, because scheduling needs a face actor: look
  at the camera.) Expected: `dropped (gate_no_match)`, no
  voice check, no model call.
- [ ] **Step 6 (optional, only if the voice is enrolled): the stored case.** With
  `just speaker-auth-demo --enroll` done and `SPEAKER_AUTHENTICATION_ENABLED=true`,
  `FACE_AUTHENTICATION_ENABLED=true` and `ROBOT_FACE_AUTH_ENABLED=true`, say "me gusta el mate".
  Expected: `Candidate proposal: stored=1`, and the counts per status are `proposed` 1
  (`SELECT status, COUNT(*) FROM memory_candidates GROUP BY status`). Record the extraction duration
  from the log line of the extractor. Do not print the value.
- [ ] **Step 7: `just reset-db` with a live candidate (only if Step 6 ran).** Expected:
  `Voided 1 live candidate(s)`, then the backup is made; the backup file holds no live candidate.
- [ ] **Step 8: Record and commit** the note, `docs: record the plan 0062 local smoke`.

---

## Task 16: Documentation truth

**Files (docs only):**
- [ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md): its *Implemented by*
  line records Plan 0062 as closed with its date and PR; *Follow-up* names Plan 0063 as next. The
  status stays `Proposed` until Plan 0063 closes. Check that decisions 4, 6, 10 and 12 still match
  the code (the setting names are the proposed ones).
- [ADR 0020](../../adr/0020-authorized-actor-in-the-conversation.md): one line in its amendments
  pointing to ADR 0021 §3 (a background voice check on a face-identified generic turn, and a
  candidate extracted from it); ADR 0020 is `Accepted` and ADR 0021 only `Proposed`, and the
  default-off switch is what keeps the two consistent until Plan 0063 closes.
- [ADR 0019](../../adr/0019-personal-memory-capabilities.md): §1's sentence that CM-3 "decides
  whether to retire `PROPOSE_MEMORY` and `COMMIT_MEMORY`" points to ADR 0021 decision 11 and
  Plan 0062 (retired); §3's `confirm` row notes that its first caller is the writer (Plan 0062),
  still unreachable from a route.
- `docs/architecture/current-state.md`: lines that say "consolidation" or "scheduler" for voice
  (the `MANUAL` retrieval row, the episodic row, the longitudinal row, the diagram text); a new row
  *Memory candidates (Plan 0062, CM-3a)*; the migration list (009); the settings. Then regenerate
  the Archify diagram (`docs/architecture/diagrams/current-state.{json,html}`: validate, then
  deliver), as every edit of `current-state.md` requires.
- `docs/architecture/README.md` (the CM sentence), `docs/architecture/memory-and-world-state.md`
  (its *Current baseline* writer bullet), `docs/runbooks/operator-manual.md` (the seven settings,
  `just reset-db` voiding live candidates, the closed reasons of the proposal log lines),
  `docs/roadmap/cognitive-roadmap.md` and `docs/roadmap/conversational-memory-delivery-map.md`
  (the CM-3a row and *Current fracture*: voice no longer passes a consolidation scheduler),
  `docs/plans/README.md`, `docs/plans/open/README.md`, `docs/plans/completed/README.md` and the move
  of this plan to `completed/`.

- [ ] **Step 1: Update each file** with outcomes and test counts from Tasks 13 to 15 and the final
  `just gate`; replace "plans 0062 and 0063 unwritten" wherever it appears
  (`rg -n "0062|CM-3a|consolidat|consolidate_turn|PROPOSE_MEMORY" docs`).
- [ ] **Step 2: Regenerate the architecture diagram** with the Archify skill, validate then deliver.
- [ ] **Step 3: Verify the docs.** `uv run ruff format --check .` (CI formats the Python blocks of
  the Markdown files), `uv run python scripts/check_reserved_terms.py`, and a check that every
  relative link of the touched `.md` files resolves.
- [ ] **Step 4: Update the local table** (`docs/roadmap/tabla-tareas.md`, never committed), commit
  `docs: close plan 0062`, open the PR, squash-merge after green CI, delete the branch.

---

## Review record

**Independent review, 2026-10-14.** One read-only reviewer (a separate agent that had not seen the
plan being written, with the repository, the ADRs and the rehearsal copy and no permission to edit
them) read the plan, ran the rehearsal's tests and probed it with its own scripts: 273 targeted
tests and the whole CI selection (2849 passed) were green before the findings below. Each finding
was reproduced, given a RED test in its owning task, fixed in the rehearsal, and the plan was
regenerated from the fixed commits. Nothing was merged or left for the executor to "decide".

| # | Finding (severity) | Disposition |
|---:|---|---|
| 1 | A third person's taste, or a flipped polarity, becomes the owner's candidate: the gate dropped the attribution at a soft break and the classifier only looked for the object anywhere in the utterance (critical) | **Fixed** (Tasks 2, 3). The gate returns `GateMatch(predicate, words)` per taste, refuses a taste after an attribution and a soft break, and the classifier accepts an object only inside the words of a trigger of **its own predicate**. RED tests: `test_a_taste_after_an_attribution_and_a_soft_break_is_not_the_speakers`, `test_an_object_must_sit_after_a_trigger_of_its_own_predicate`, `test_a_taste_somebody_else_voiced_earlier_in_the_text_is_not_the_speakers` |
| 2 | `checkpoint_wal` raised after the commit when a cursor was open on the shared connection, blocked every writer for seconds when another process read the file, truncated nothing and was never retried; the scrub script exited 0 (critical) | **Fixed** (Tasks 5, 6, 10, 12). It returns a `bool`, never raises, waits 0.5 s, and `candidates.checkpoint_after_scrub` retries the one it owes at the next store entry and every hourly run; `promote` checkpoints only when it resolved the candidate; the scrub script exits 1 when the log cannot be truncated so `reset-db` copies nothing. RED tests: a pinned log, an open cursor, a postponed checkpoint finished later, `promote` with a cursor open, the script with a reader |
| 3 | The retention test was vacuous: the fresh insert expired the stale one before the job ran (important) | **Fixed** (Task 12): the fresh row is inserted first and the stale one is asserted still `proposed` before `_run_once`. The mutation "retention does not expire" is now killed |
| 4 | A kinship word inside the favourite trigger (`mi hijo favorito es Pedro`) bypassed the deny list (important) | **Fixed** (Task 2): the words inside the trigger are checked like a lead-in. RED test: `test_a_kinship_word_inside_the_favourite_trigger_is_refused` |
| 5 | The object grammar leaked: short and clitic infinitives, `a`/`al` objects, relative clauses, capitalised names and places, religion, politics, sexuality, drugs (important) | **Fixed** (Tasks 2, 3): infinitives with or without a clitic pass only from the list, `a`/`al` and `que` clauses are not things, a word capitalised inside a sentence is a name, and the deny list grew. **Accepted cost:** the lists are closed and small; anything not on them is dropped, not guessed (D-6) |
| 6 | Nothing pinned who may call `insert_candidate`, `mark_offered`, `resolve_candidate` or `promote` (important) | **Fixed** (Task 14): a caller guard with its violation test; Plan 0063 adds its module as a decision |
| 7 | The rollback boundary said nothing else is persisted, and the goal said every live value is voided at start-up even when the database is never opened (important) | **Fixed**: *Rollback boundary* tells the operator to void the rows (switch off and start once, or run the scrub script) before reverting, and the goal says "the next start-up that opens the database" |
| m | ADR 0020 is `Accepted` and runtime now does what ADR 0021 (`Proposed`) says | **Recorded** in Task 16 (a pointer in ADR 0020); the default-off switch keeps them consistent until Plan 0063 |
| m | `promote` audits and checkpoints even for a candidate that does not exist | **Recorded** in D-9: Plan 0063 calls it only after an answer matched an offer; checkpoint only when it resolved |
| m | Task 15 steps 4 and 5 need the face to have resolved the owner | **Fixed**: the prerequisite is stated in the step |
| m | `lifespan` reads the app's settings, the runtime paths read the global | **Recorded** in D-10 (the same object in production) |
| m | `scrub_candidates.py` is not "standard library only" (it imports the store's SQL constant) | **Fixed**: the docstring says what is true (the file is opened with `sqlite3`) |
| m | `candidates.expire_lapsed` had no production caller | **Fixed**: removed; retention uses `run_housekeeping` in its own transaction |
| m | D-2 departs from the ADR's wording | **Recorded** (it already was; the reviewer asked for it to stay visible) |
| m | `_store` wrote the `allowed` audit row before the enrolment re-check | **Fixed** (Task 11): re-check first, audit after (D-4) |

**What the reviewer verified and found correct:** the firewall (`is_face_actor` and
`is_face_and_voice_actor` exclude every `LOCAL_UNLOCK` item, a second face vetoes the turn, the
voice check runs on the same clip for the id the face named and demands the owner role),
`fuse_face_and_voice` is behaviour-preserving, `/chat` and `/vision/respond` never schedule, the
proposal never raises and frees its slot in `finally` including on cancellation, the writer is one
transaction with no nested `db.transaction()`, two concurrent promotions give one fact, migration
009 applies over a version-8 database with data, nothing calls the retired code, `aiosqlite` is
held at `WARNING`, the extractor's error is `from None`, and every modified file is inside the
permitted list.

**What no review of a plan can close** (it needs Pipec's hardware or the real model): how many of
Pipec's real sentences the closed grammar keeps (it is conservative on purpose, so the expected
failure is "too few candidates", not "a wrong one"), the extraction cost and quality of the real
model on the shared laptop (about 41 s per call in the benchmark), and the voice check under room
noise. The default-off switch and Task 15 exist for these.

## ADR 0021 coverage

| ADR section | Where |
|---|---|
| §1 scope (predicates, subject, channels, result) | Tasks 2, 3, 10, 13 |
| §2 units, one reason to change each | Tasks 2, 3, 4, 6, 9, 10 (D-1) |
| §3 the firewall rule (voice on the turn's clip, never a token, fail closed, kill-switch) | Tasks 8, 9, 11, 13 |
| §4 gate and extractor, bounded cost | Tasks 2, 4, 11 |
| §5 the classifier assigns the classification | Tasks 3, 10 |
| §6 the store (schema, scrub, one clock, bounded, reclamation, compare-and-set, no oracle) | Tasks 5, 6, 10, 12 |
| §7 the policy check (request, actor, order, same person) | Tasks 8, 9, 10 |
| §8 promotion | Tasks 7, 10 |
| §9 offer and answer | **Plan 0063** (the seam `promote` and the `read`/`confirm` steps exist) |
| §10 where it runs, settings | Tasks 1, 11, 13 |
| §11 what leaves | Tasks 13, 14 (D-11) |
| §12 logging and ADR 0019's seven obligations | Tasks 6, 9, 11 (obligations 1 to 4); 5 to 7 not wired |
| §13 everything left out has an owner | unchanged; see *Not here* |

## Completion criteria

1. Tasks 0 to 16 done, one commit per task, every test RED before GREEN.
2. `just gate` green with at least 2905 tests collected (baseline 2597), `ruff` clean over
   the explicit paths of every file touched, `scripts/` included.
3. With `MEMORY_CANDIDATES_ENABLED=false` (the default) nothing is proposed, stored or promoted, and
   a start-up voids every live candidate (Task 12, Task 15).
4. The local smoke of Task 15 recorded by Pipec (outcomes only); the hardware acceptance is **not**
   a criterion here.
5. Every document of Task 16 updated; this plan moved to `completed/`; ADR 0021 stays `Proposed`.

## Rollback boundary

Reverting the squash-merge restores the previous behaviour (`consolidate_turn` back, never
reachable; no candidate path). Migration 009 only adds a table, and `PRAGMA user_version` stays 9
in a database that already ran it: an older server ignores the extra table. **Live candidate
rows hold values, and nothing in the reverted code voids or expires them:** before reverting, set
`MEMORY_CANDIDATES_ENABLED=false` and start the server once (the start-up voids them) or run
`uv run python scripts/scrub_candidates.py data/omnibot.db` with the server stopped; otherwise a
backup could carry them. Nothing else is persisted. The cross-cutting changes are the explicit `secure_delete` pragma and the `aiosqlite`
log level (both safe to keep), the renamed scheduler parameter, and the two retired actions.

## Not here, and why

- **The offer, the answer, `InformationNeed.MEMORY_ANSWER`, the controller branch, the offer's
  streaming event, the inspection script and the hardware acceptance** (ADR 0021 decision 9 and its
  *Acceptance*): Plan 0063. `promote` and the `read`/`confirm` policy steps are the seam it uses.
- **Reading a stored preference back** (CM-5), **correcting or forgetting** it (CM-6), **episodes**
  (CM-4), **third parties, pets, `lives_in`, reported facts, a disclosure rule, perception, the first
  `SECURITY` datum and a benchmark `confirm` step** (CM-3b), the **real scenario** (CM-7).
- **`/chat` and `/vision/respond`** as a source of candidates: no audio, so no `strong`.
- **A `personal_memory_confirm` PIN scope**, and any change to ADR 0019's policy or to the registry's
  defaults.
- **Enrolling face and voice as the first step of setup**, access levels, "you are with someone,
  still want it?", liveness: Phase 0 (ADR 0021 decision 13). Replay stays measured, not defended.
- **Removing the other legacy writers** (`store_memory`, `assert_fact`, `upsert_entity`): the
  benchmark, the legacy retrieval and their own tests still use them.
- **The 14 existing backups in `data/backups`**: they predate the candidate table.

## Execution record

**Executed 2026-10-15** on the plain branch `feat/0062-cm3a-candidates-and-writer` (from `main`
at `3717dc6`, no worktree); PR #183, squash-merge pending when this record was written. No spoken
dialogue, no hardware, no wire change.

**Commits.** 14 task commits, ordered by dependency waves rather than strictly 1 to 14 (the
tasks inside a wave are independent): Task 1; Tasks 2, 5, 7 and 8; Tasks 3, 4, 6 and 9; Tasks 10
and 12; Task 11; Task 13; Task 14. Then 4 review-fix commits (`4b98eb0`, `507d6be`, `7ab57f7`,
`1d65c01`). Tasks 15 (local smoke) and 16 (documentation) are not code commits.

**Gate.** `just gate` green: **2972** tests unfiltered and **2955** under the CI selection
(baseline 2597 and 2580; the rehearsal counted 2905 and 2888 before the review additions);
`mypy` 115 files, `pyright` 0 errors, `vulture` clean.

**Independent review (4 reviewers, opus, read-only):** whole branch, silent failures, comment
accuracy and test coverage. What it fixed beyond the plan text:

- the deny lists cover plurals and diminutives;
- a contrast inside one taste (`todo menos X`, `excepto`, `salvo`; `al` / `en vez de` /
  `en lugar de` after `prefiero`) is refused;
- a read-only `precheck_insert` runs before the audit row, so a repeated taste or a capped person
  leaves no `allowed` audit row;
- a second consent re-check runs right before the insert;
- start-up always truncates the write-ahead log (an owed checkpoint is not forgotten across a
  restart);
- `checkpoint_wal` never raises for a closed connection;
- retention expires candidates in its own transaction and logs the exception class only;
- `list_known_names` fails closed on malformed aliases;
- early `promote` denials log a closed reason;
- `correlation_id` joins `candidate.insert`, `candidate.proposal` and `candidate.promotion`;
- a catch-all failure of the proposal logs the class and the innermost frame (file, line,
  function), never the message.

**Deviations from the plan text.**

- Commit order by dependency waves instead of strictly 1 to 14.
- The RED of Task 13 was 24 failed tests and 4 errors, not the single `ImportError` the rehearsal
  recorded.
- The RED of Task 14 was 2 failures.
- New log lines and events beyond the plan: `candidate.extraction_failed`,
  `candidate.enrolment_check_failed`, `candidate.proposal_error` (with `error_file`,
  `error_line`, `error_function`) and the start-up line `Candidates reconciled at start-up: N
  expired` (with the switch off the line stays `Candidates voided at start-up: N`).

**Local smoke (Task 15, 2026-10-15; outcomes only).**

| Step | Result |
|---|---|
| 1. `just gate` | pass (2972 unfiltered, 2955 under the CI selection) |
| 2. Switch off, start-up | pass: migration 9 applied over the real database, `Candidates voided at start-up: 0`, server ONLINE |
| 3. Switch on, start-up | pass: server ONLINE, `Candidates reconciled at start-up: 0 expired` (the plan expected no candidate line; this one is new) |
| 4. A matching sentence without enrolment | pass: `dropped (strong_unreachable)`, 0 rows in `memory_candidates` |
| 5. A non-matching sentence | pass: `dropped (gate_no_match)`, no voice check, no model call |
| 6, 7. Stored case and `just reset-db` with a live candidate | not run (optional: they need an enrolled voice) |

**Accepted costs of the closed grammar** (D-6): a taste after an attribution and a soft break is
dropped; bare short or clitic infinitives not on the list are dropped; `me gusta el pollo al
horno` passes but `prefiero el mate al cafe` does not; `me gusta el cafe sin azucar` passes;
places and names that Whisper writes in lower case rely on the topic set; `No, me gusta el mate`
is a `likes` candidate by design and must be confirmed in Plan 0063.

**Follow-ups.**

- **Plan 0063** (free number): the spoken offer, the answer and the hardware acceptance of
  ADR 0021 decision 9; `promote` has no caller in a route yet. ADR 0021 stays `Proposed` until it
  closes; the next free ADR number is 0022.
- Reading a stored preference back is CM-5, correcting and forgetting is CM-6, third parties and
  the rest of decision 13 are CM-3b.
- Steps 4 and 5 of the smoke are pending Pipec's run and are recorded in
  `docs/evals/0062-memory-candidates-local-smoke.md`.
