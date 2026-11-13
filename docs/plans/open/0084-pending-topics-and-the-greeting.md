# 0084 — Pending topics: what the owner said they would do, picked up by a greeting

> **Status:** **Implemented, acceptance in progress** — merged 2026-11-13 (`6a17e38`, PR #264),
> `just gate` 8118 passed (baseline 7887); day 1 of the hardware acceptance passed and the greeting
> days run 2026-11-16 to 2026-11-19 ([record](../../evals/0084-pending-topics-acceptance.md)); the
> plan moves to `completed/` and ADR 0037 becomes `Accepted` then.
>
> **Was:** `Ready` and `NOW` — **promoted by Pipec on 2026-11-12**: D-1 to D-16 confirmed as
> written, the departures from the ADR included (D-4, D-8, D-9, D-12); finer points of grammar and
> wording are tuned later from longer real sessions (D-16 of Plan 0083). Written as `Draft` the
> same day from
> [ADR 0037](../../adr/0037-the-time-of-memories-and-a-contacts-phone.md) (`Proposed`), decision 2
> only, plus decision 6 for the switch, and the code of `main` at `8973b5c` (Plan 0083 merged). It
> is executed in a new Claude Code session, inline (as Plan 0083 was), with the whole-branch
> reviews of Task 8. Queue rule 4 applies at execution: Task 0 re-verifies every claim below
> against the merged code before any code, and **stops and reports** if one is false. ADR 0037
> becomes `Accepted` when this plan closes (its decisions 1, 3, 4 and 5 are closed by Plans 0082
> and 0083). Written for an executor who has not seen this repository.

> **For agentic workers:** if the status above does not say `Ready`, stop. Read `CLAUDE.md` and
> every file of `.claude/rules/` in full first. REQUIRED SUB-SKILLS: `superpowers:executing-plans`
> (inline), `superpowers:test-driven-development` for every task,
> `superpowers:verification-before-completion` before any claim of done,
> `superpowers:requesting-code-review` and `superpowers:receiving-code-review` for Task 8, and
> `superpowers:finishing-a-development-branch` for Task 9. The review agents of Task 8 and any
> other subagent run on the `sonnet` model and read `.claude/` (CLAUDE.md and `.claude/rules/`) in
> full before reading code. **Pipec's rules win over the skills:** one plain branch from `main`
> (`feat/0084-pending-topics`), never a git worktree, this plan lives under `docs/plans/`. One
> commit per task; every test seen RED for the stated reason first. If evidence contradicts the
> plan, stop and report instead of redesigning. The Bash tool loses backslashes and non-ASCII
> characters in heredocs and arguments: use the Write and Edit tools (or a Python script written
> with Write), and put every accented Spanish test phrase in a YAML fixture. Commit titles:
> Conventional Commits, at most 72 characters, check `git log` after each commit (the hook rejects
> silently; a reformatting hook unstages the commit); never pipe `git commit`; `git add` with
> explicit paths. Run the suite with `MEMORY_ENABLED=false` as CI does; each test that needs memory
> sets `settings.memory_enabled` itself. Never run `uv sync` without `--extra cuda`. Do not run
> `just gate` or the full suite in the background while Pipec rehearses (about 3.5 GB of RAM). The
> server and the robot are started by Pipec, never by the agent. Before pushing, run `pyright`,
> `ruff` and `mypy` over the **whole** project, lint `scripts/` with explicit paths and
> `uv run ruff format --check .` (CI also checks python blocks in `docs/*.md`).

## Decisions

Pipec's decisions are ADR 0037 decision 2 and its table *Pipec's decisions* rows 2 and 3 (a fixed
sentence plus a topic the local model names; a health topic only when the owner is alone in view),
and decision 16 of Plan 0083 (the grammars serve an ordinary speaker). The calls below fill in what
the ADR leaves to the builder (*Not decided here*: «the exact templates, the grammar's word lists
and the switch names»), and its *author's calls* (one follow-up per new session, an open offer
winning, two days of grace, the topic deleted with its record). **Pipec confirmed all of them as
written on 2026-11-12**; the *For Pipec* notes below record what he was asked.

- **D-1 The switch.** `PENDING_TOPICS_ENABLED` (`pending_topics_enabled: bool = False`). It works
  only with `MEMORY_ENABLED` **and** `CONVERSATION_RECORD_ENABLED` (a topic references the record
  of the turn that said it, and only turns that feed the diary yield topics): one function,
  `pending_store.pending_topics_on() -> bool`, combines the three and every consumer asks it. Off,
  every route, prompt, reply, record and log line is byte-identical to `main`; migration 016 runs
  whatever the switch says (one empty table).
- **D-2 Which turns yield a topic.** Only a turn the capture records as `VERIFIED` (the owner's
  face and voice on that clip, ADR 0027) whose words tell something (`recall_store.
  tells_something`, so a question or a closed request never does) and that holds no `?` (a
  question about the future, «¿voy mañana al banco?», is not an announcement). A visitor's words
  never yield one (they are never `VERIFIED`).
- **D-3 The announcement grammar** (pure, `cognition/pending_topics.py`): the folded words hold
  **exactly one** time phrase of the one reader (`count_spoken_times == 1`, Plan 0083), it reads
  **toward the future** (`read_spoken_time(…, toward=Toward.FUTURE)`) to a **single day**
  (`start == end`: «mañana», «pasado mañana», «el jueves», «el próximo jueves», «en 3 días más»,
  «el 20 de noviembre», «hoy»); a week, a month, a season or a year («la próxima semana», «en
  marzo») is too wide for «¿cómo te fue ayer…?» and yields none; and the words hold one verb or
  phrase of the closed `ANNOUNCING_VERBS` (folded): `voy`, `vamos`, `tengo`, `tenemos`, `ire`,
  `iremos`, `salgo`, `salimos`, `viajo`, `viajamos`, `juego`, `jugamos`, `empiezo`, `me toca`,
  `te cuento`, `te aviso`, `le cuento`, `le aviso` (the present used as future, the plain future,
  and the «te cuento» of the ADR, with usted). Third person («mañana viene mi hija») is not the
  owner's plan and yields none (ADR: «a first-person verb or te cuento»). *For Pipec:* confirm the
  list; ordinary-speaker forms join it from a real session (D-16 of Plan 0083).
- **D-4 When a topic is due and when it may be asked.** The due day is the day the phrase names,
  against the household day of the turn (`HOUSEHOLD_TIMEZONE`). A topic may be picked up from the
  day **after** its due day to two days after it: «¿Cómo te fue ayer con el banco?» or «… anteayer
  …». It is **not** asked on its own due day (a «mañana voy al banco» said yesterday would be asked
  this morning, before the owner went). *For Pipec:* the ADR window was «from two days ago to
  today»; this drops «today» to avoid asking before it happened.
- **D-5 Expiry and deletion.** A topic is deleted (not kept as `expired`) once today is more than
  two days after its due day, asked or not, by the conversation job; and in cascade with the record
  of the turn that said it (ADR: «a reminder of a conversation, not a diary»). No state `expired`
  is stored: `open`, `asked` and `unnamed` (D-6) are the states.
- **D-6 Naming the topic.** The local model names it in a background step of the **conversation
  job** (nobody talking, the record closed, as the recall vectors are filled; ADR 0028 decision 2),
  never on the live turn: one call, the owner's words only, at temperature 0, JSON
  `{"topic": "…"}` of one to four words with their article («el banco», «el médico», «la
  reunión»). Untrusted output: kept only when every folded word of the topic appears in the folded
  words of the turn (copied, never invented), it has one to four words and at most 40 characters;
  else the row is deleted (a topic it cannot name is not kept, ADR). Until named, the row keeps the
  turn's words (`heard`) and the state `unnamed`; naming clears `heard` (the words stay only in the
  record, as for every other derivation).
- **D-7 The sensitivity of a topic.** `recall_sensitivity.classify_turn_text(heard)` decides it:
  `normal` and `medical` are kept (the health topics of ADR decision 2); a turn classified
  `private`, `location` or `security` yields no topic (a plan about a key, an address or a code is
  not something to say aloud in a greeting). A topic of a turn later raised by its record's episode
  keeps the level it was stored with (the episode raise of Plan 0078 is about recall units only).
- **D-8 The follow-up turn.** On a generic voice turn whose speaker is the face-identified owner
  (the generic identity, Plan 0061) and whose short-term session is **new** (the turn's
  `ContinuityTurn` has no history: the first turn after 180 s of silence or a change of person),
  the oldest named `open` topic in the window of D-4 is picked up. **At most one follow-up per
  household day** (none when a topic was already asked today), so a day of many short sessions
  hears one. *For Pipec:* the ADR said «one per new session»; this caps it at one per day.
- **D-9 Who may hear it, and the health rule.** Face only (`basic`), as the ADR says for the
  greeting; the policy is asked `READ_PERSONAL_CONVERSATION_MEMORY` for the owner's own data with
  visibility `personal` and the topic's sensitivity (`medical` reads at `basic` for the owner's own
  data, `authorization.OWN_READ_BASIC_CATEGORIES`, Plan 0079), its audit row **before** the topic
  is read, and the consent resolved as the sensitive read resolves it for `medical` (a face grant
  and a closed alta, Plan 0079 D-9). With two faces in view the generic identity is suspended
  (`VETO_MULTIPLE_FACES`), so **no** topic is picked up, `normal` or `medical`: stricter than the
  ADR for a `normal` topic, the same for a health one. *For Pipec:* confirm that a `normal` topic
  also waits when a guest is in view.
- **D-10 The sentence.** «¿Cómo te fue {día} con {tema}?» (the ADR's wording), `{día}` «ayer» or
  «anteayer» (`spoken_dates`' near-day label, made public as `near_day_label`), `{tema}` as named.
  A fixed sentence of the controller, never in the generic prompt (Plan 0077 guard).
- **D-11 Where it is said, and the offer.** After the model's reply, in the slot the memory offer
  uses (ADR 0021 decision 9): prepared concurrently with generation (it reads the store; it writes
  nothing), committed after the reply was built (the audit row, then the state `asked`), never on a
  fallback reply. **An open memory offer on the same turn wins** and the topic waits for a later
  session (the ADR's call). On `/transcribe` the WAV carries reply and sentence and
  `llm_response` the reply only; on `/transcribe/stream` one more `audio` event with empty text
  before `done`, as the offer. No wire field is added.
- **D-12 The record and the session.** The sentence is **not** written to the conversation record
  (as the offer is not; the diary reads the owner's part only). It **is** appended to the
  assistant side of the short-term session (continuity), so that the model's next turn hears the
  owner's answer («bien, me aprobaron el crédito») with the question it answers; the session is the
  owner's own conversation, which the generic prompt already reads (ADR 0020), not a household
  store.
- **D-13 What the owner answers.** Ordinary conversation (the ADR): no closed grammar, no state
  change. *For Pipec:* a later plan may let «no fui» or «se suspendió» move the topic; not here.
- **D-14 The store** (migration 016, `memory/migration_016_pending_topics.sql`; `memory/
  pending_store.py` the only SQL on it, a guard): `pending_topics` with `id`, `owner_entity_id`
  (→ `entities`, cascade), `source_record_id` (→ `conversation_records`, cascade),
  `correlation_id`, `said_day` and `due_day` (local ISO days, `CHECK (date(x) IS x)` and
  `due_day >= said_day`), `topic` (NULL until named; 1 to 40 characters), `heard` (NULL once named;
  1 to 2000), `state` (`unnamed`, `open`, `asked`; `unnamed` exactly when `topic` is NULL),
  `sensitivity` (`normal`, `medical`), `created_at`, `asked_at`; indexes on
  `(owner_entity_id, state, due_day)` and `source_record_id`; `secure_delete` already on; atomic;
  no down-step. One row per turn at most.
- **D-15 Logs, never a topic or a day.** `pending.capture` (closed outcome: `kept`, `no_phrase`,
  `not_single_day`, `no_verb`, `question`, `sensitive`, `not_verified`), `pending.named`
  (`named`, `unnamed_dropped`, `model_failed`), `pending.follow_up` (`asked`, `none_due`,
  `already_today`, `offer_won`, `denied`, `audit_failed`), `pending.expired` (a count). No log
  line, exception message, audit row or `repr` carries a topic, a day or the owner's words.
- **D-16 Acceptance over two days.** A topic is asked from the day after its due day (D-4), so the
  hardware acceptance tells «hoy …» and «mañana …» topics on day 1 and hears the greeting on day 2
  and day 3 (Task 9). The automated tests move the clock instead.

**Goal.** With `PENDING_TOPICS_ENABLED` on, what the owner says they will do on a given day («hoy
voy al banco», «el jueves tengo médico») is kept as a pending topic named in two to four of their
own words, and the first greeting of a later day picks it up once with «¿Cómo te fue ayer con el
banco?», a health topic only with the owner alone in view, after any memory offer, never in the
generic prompt.

**Architecture.** A pure grammar (`cognition/pending_topics.py`) on top of the one reader of
spoken time; a store (migration 016, `memory/pending_store.py`); the capture keeps an `unnamed`
topic from a verified turn; the conversation job names it with the local model and deletes expired
ones; a follow-up seam (`memory/pending_follow_up.py`) prepared and committed beside the memory
offer in the text turn and the stream, with the policy and its audit before the read.

**Tech stack.** Python 3.12, FastAPI, aiosqlite, SQLite 3.49, Ollama (`qwen2.5:3b`, one background
call per topic), pytest. No new dependency, no wire change, no robot change, no prompt change; one
migration.

**Spec.** [ADR 0037](../../adr/0037-the-time-of-memories-and-a-contacts-phone.md) decisions 2 and 6
and its *Test consequences*; [ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md)
decision 9 (the offer's slot, prepared and committed); [ADR 0027](../../adr/0027-conversation-record-and-the-diary.md)
(only verified turns feed the diary); [ADR 0029](../../adr/0029-it-knows-who-is-listening.md)
(levels and the camera check); [ADR 0020](../../adr/0020-authorized-actor-in-the-conversation.md)
(the short-term session); [Plan 0083](../completed/0083-spoken-time-and-when-it-happened.md) (the
one reader and D-16); [current state](../../architecture/current-state.md);
[guardrails](../../architecture/implementation-guardrails.md).

**Required reading.** The above, then the code: `cognition/spoken_dates.py` (`read_spoken_time`,
`count_spoken_times`, `Toward`), `memory/candidate_dialogue.py` (`prepare_offer`, `commit_offer`,
`PendingOffer`), `text_turn.py` (`start_offer`, `finish_offer`, `drop_offer`, `TextTurnResult`,
`process_text_turn`), `streaming.py` (`_offer_event`), `memory/candidate_extraction.py` (the model
call and its rules), `memory/conversation_capture.py` (`capture_turn`, `_recall_indexer`),
`memory/conversation_jobs.py` (`run_once`), `memory/continuity.py`, `cognition/generic_identity.py`,
`memory/sensitive_access.py` (the consent of D-9), `memory/recall_sensitivity.py`,
`routers/transcribe.py` (how both voice routes bind the offer).

## Global constraints

- English code, comments and docstrings (Google style); Spanish only in user-facing strings;
  **no voseo** (`tests/unit/test_no_voseo_in_spoken_strings.py` covers the new sentence).
- No `Any`, no `print`, no `os.path`, no bare `except`; logging with `%`; settings only through
  `settings`, and the cognitive core reads none.
- Pure and closed where it decides: the grammar, the day and the sentence are deterministic; the
  model only names, and its output is checked against the owner's own words.
- One reader of spoken time: the grammar calls `spoken_dates`; no date regex elsewhere (the Plan
  0083 guards).
- One migration (016); `pending_store.py` is the only SQL on `pending_topics`.
- No topic, day or text in a log line, an audit row, an exception message or a `repr`.
- The generic prompt reads no household store (Plan 0077 guard): the sentence is spoken by the
  controller's slot, never put in a prompt.
- With `PENDING_TOPICS_ENABLED=false` every route, prompt, reply, record and log line is
  byte-identical to `main`; with `MEMORY_ENABLED=false` every turn is.
- No real household data: invented canaries only; `scripts/check_reserved_terms.py` passes.

## Review focus

1. **A plan that is not the owner's, or not a plan.** «mañana viene mi hija», «los lunes juego
   fútbol», «¿voy mañana al banco?», «la próxima semana voy al sur» (a week), «ayer fui al banco y
   mañana voy al cine» (two phrases) yield no topic (Task 1).
2. **Asked before it happened, or twice.** A topic due today is not asked today; one asked
   yesterday is not asked again; a second short session the same day hears nothing (Task 5).
3. **A guest in view.** Two faces suspend the identity: no topic, `normal` or `medical`; a health
   topic is never said with anyone else (Task 5, Task 6 route test with a two-face frame).
4. **An invented topic.** A model answer whose words are not the owner's («el teatro» for a turn
   about the cinema) is dropped, never spoken (Task 2).
5. **The offer and the session.** With an open offer the topic waits and stays `open`; the next
   model turn sees the sentence in the session; the record never holds it (Tasks 5 and 6).

---

## File structure

| File | Responsibility | Task |
|---|---|---|
| `cognition/pending_topics.py` (new), `cognition/spoken_dates.py` (`near_day_label` public) | The announcement grammar, the due day, the window, the sentence | 1 |
| `memory/pending_naming.py` (new) | The model names a topic; the copied-words check | 2 |
| `memory/migration_016_pending_topics.sql` (new), `db.py`, `memory/pending_store.py` (new), `settings.py` | The table, the store, `pending_topics_on` | 3 |
| `memory/conversation_capture.py`, `memory/conversation_jobs.py` | Keep an unnamed topic; name it and expire them in the job | 4 |
| `memory/pending_follow_up.py` (new), `text_turn.py`, `streaming.py`, `memory/continuity.py` | Prepare and commit the follow-up beside the offer; the session | 5 |
| `.env.example`, `routers/transcribe.py` | The switch and the wiring | 6 |
| `tests/unit/test_architecture_guards.py` | The store guard, purity | 7 |
| `docs/…` | Truth, acceptance, close | 9 |

---

### Task 0: Re-audit and baseline

**Files:** none changed.

- [ ] **Step 1:** `git checkout main && git pull`, then create `feat/0084-pending-topics`.
- [ ] **Step 2:** Verify, and **stop and report** if any is false (throwaway scripts under
  `.superpowers/sdd/0084/`):
  - `spoken_dates.read_spoken_time(…, toward=Toward.FUTURE)` resolves «mañana», «pasado mañana»,
    «el jueves», «en 3 días más» to one day and «la próxima semana» to seven; `count_spoken_times`
    counts one phrase in each; `_near_label` exists (to be made public).
  - `text_turn.process_text_turn` starts the offer with `start_offer` before generation and
    finishes it with `finish_offer(…, reply_failed=)` after recording the session pair;
    `TextTurnResult.offer` is spoken after the reply on `/transcribe` and as one more `audio`
    event on the stream (`streaming._offer_event`); the offer is not recorded (`record_turn` gets
    the reply only).
  - `continuity.open_turn` returns a `ContinuityTurn` with empty `history` on a started session,
    and `record_pair` writes the pair the next model turn reads.
  - The generic identity suspends a turn with two faces (`FusionReason.VETO_MULTIPLE_FACES` →
    `SuspendCause.VETO_MULTIPLE_FACES`), so no face-identified actor reaches a generic turn then.
  - A throwaway policy check: the face-identified owner at `basic`, own data, visibility
    `{personal}`, sensitivity `{normal}` and `{medical}` with the consent `sensitive_access`
    resolves, is `ALLOWED`; without the closed alta, `medical` is denied.
  - `conversation_capture.capture_turn` appends the turn, then indexes a `VERIFIED` turn that tells
    something; `conversation_jobs.run_once` runs only with no open record; `ExtractionLimiter`
    serialises the candidate extraction (the naming of Task 2 runs in the job, not under it).
  - `db._MIGRATIONS` ends at 15; `recall_sensitivity.classify_turn_text` returns `medical` for «el
    jueves tengo médico».
- [ ] **Step 3:** Baseline (not in the background if Pipec is rehearsing), the count in the PR:
  `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and not eval" -q -n auto`.

---

### Task 1: The announcement grammar and the sentence

**Files:** Create `server/src/server/cognition/pending_topics.py`,
`tests/unit/test_pending_topics.py`, `tests/fixtures/pending_announcements.yaml`; modify
`server/src/server/cognition/spoken_dates.py` (rename `_near_label` to public `near_day_label`).

**Interfaces:**
- Produces: `ANNOUNCING_VERBS: Final[frozenset[str]]` (D-3; multi-word entries matched as whole
  phrases); `class AnnouncementOutcome(StrEnum)` (`kept`, `no_phrase`, `not_single_day`,
  `no_verb`, `question`); `@dataclass(frozen=True) class Announcement: due_day: date | None;
  outcome: AnnouncementOutcome`; `def read_announcement(heard: str, *, said_day: date) ->
  Announcement`; `def may_follow_up(due_day: date, *, today: date) -> bool` (D-4: one or two days
  after); `def follow_up_sentence(topic: str, *, due_day: date, today: date) -> str` (D-10);
  `spoken_dates.near_day_label(back: int) -> str | None`.

- [ ] **Step 1: Write the failing tests** over the fixture (`heard`, `said_day`, `due_day` or null,
  `outcome`): «Mañana voy al banco a pagar una cuenta.» → said+1; «El jueves tengo médico.» → the
  next Thursday; «Hoy voy al cine con unos amigos.» → said; «En 3 días más viajo al sur.» → said+3;
  «Pasado mañana te cuento cómo me fue.» → said+2; «El jueves le cuento.» (usted) → Thursday;
  and none for the traps of Review focus 1 (with their outcome), «Mañana.» (no verb), «En marzo
  voy a la playa.» (`not_single_day`). `test_may_follow_up` (due today no; yesterday and anteayer
  yes; three days no); `test_the_sentence` («¿Cómo te fue ayer con el banco?», «… anteayer …»;
  `ValueError` without a date in the message for any other distance);
  `test_the_verb_list_is_closed`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS; the Plan 0083 reader
  tests and the no-voseo test pass.
- [ ] **Step 5:** commit `feat: read what the owner says they will do (plan 0084)`.

---

### Task 2: The topic named by the local model

**Files:** Create `server/src/server/memory/pending_naming.py`,
`tests/unit/test_pending_naming.py`, `tests/fixtures/pending_names.yaml`.

**Interfaces:**
- Produces: `MAX_TOPIC_WORDS: Final = 4`, `MAX_TOPIC_CHARS: Final = 40`;
  `async def name_topic(client: httpx.AsyncClient, heard: str) -> str | None` (one
  `ollama_chat` call with its own system prompt, tuteo-free neutral Spanish, the owner's words
  only, temperature 0, JSON `{"topic": "…"}`; `None` on any model failure, an empty or invalid
  answer, or a topic that fails `is_copied_topic`); `def is_copied_topic(topic: str, heard: str)
  -> bool` (D-6, pure).

- [ ] **Step 1: Write the failing tests** (the model is a double; fixture rows `heard`, `answer`,
  `kept` or null): a copied topic is kept («el banco»); an invented one is dropped («el teatro» for
  a cinema turn, Review focus 4); five words, 41 characters, an empty string, invalid JSON, a
  model error → `None`; `test_the_prompt_sees_only_the_words` (one user message, the turn's words);
  `test_no_text_reaches_a_log_line`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** commit `feat: name a pending topic in the owner's words (plan 0084)`.

---

### Task 3: Migration 016 and the store

**Files:** Create `server/src/server/memory/migration_016_pending_topics.sql`,
`server/src/server/memory/pending_store.py`, `tests/integration/test_pending_store.py`; modify
`server/src/server/db.py`, `server/src/server/settings.py`.

**Interfaces:**
- Produces: the table of D-14; `pending_topics_enabled: bool = False`; `def pending_topics_on() ->
  bool` (D-1); `@dataclass(frozen=True) class PendingTopic: id: int; topic: str (repr=False);
  due_day: date; sensitivity: Literal["normal", "medical"]`;
  `async def insert_unnamed(conn, *, owner_entity_id, record_id, correlation_id, said_day, due_day,
  heard, sensitivity) -> int` (inside the capture's transaction);
  `async def next_unnamed() -> tuple[int, str] | None`; `async def set_topic(topic_id: int,
  topic: str) -> bool` (clears `heard`, state `open`); `async def drop(topic_id: int) -> None`;
  `async def due_topic(owner_entity_id: int, *, today: date) -> PendingTopic | None` (oldest
  `open` with `may_follow_up`); `async def asked_today(owner_entity_id: int, *, today: date) ->
  bool`; `async def mark_asked(topic_id: int, *, now: datetime) -> bool` (compare-and-set on
  `open`); `async def delete_expired(*, today: date) -> int`.

- [ ] **Step 1: Write the failing tests:** the migration on a 015 database (`user_version` 16, the
  table empty); the CHECKs refuse a bad day, a due day before the said day, a named row with
  `heard`, an unnamed row with a topic; cascade with the record; `due_topic` picks the oldest in
  the window and never a due-today or a three-days-old one; `asked_today`; `mark_asked` once only;
  `delete_expired` counts; another owner's topic is never returned; `pending_topics_on` over the
  eight combinations.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS; `test_db` and the
  schema tests (move a «latest version» assertion to 16 or stop its fixture at 15, as Plan 0083 did).
- [ ] **Step 5:** commit `feat: store pending topics (plan 0084)`.

---

### Task 4: The capture keeps a topic; the job names and expires them

**Files:** Modify `server/src/server/memory/conversation_capture.py`,
`server/src/server/memory/conversation_jobs.py`; tests `tests/unit/test_capture_pending.py`,
`tests/integration/test_pending_capture_db.py`, `tests/unit/test_conversation_jobs_pending.py`.

**Interfaces:**
- Consumes: Tasks 1 to 3.
- Produces: in the capture, for a `VERIFIED` turn that tells something, with the switch on:
  `read_announcement(heard, said_day=turn.at in the household zone)`; on `kept`, the sensitivity of
  D-7, then `insert_unnamed` in the append's transaction (a reader error is a narrow boundary: the
  turn is recorded without a topic and `pending.capture` logs the class); `pending.capture` logs
  the outcome (D-15). In `conversation_jobs.run_once`, with no open record and the switch on:
  `delete_expired`, then at most one `next_unnamed` → `name_topic` → `set_topic` or `drop`.

- [ ] **Step 1: Write the failing tests:** a verified announcement keeps one unnamed row; a
  not-verified one, a question and a `security` turn keep none; the household day, not UTC (02:30Z
  «mañana voy…» resolves against the local day); a reader error keeps the turn; switch off: no row
  and today's log line; the job names one row per tick (double model), drops an invented name,
  deletes the expired, does nothing with an open record or the switch off.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** commit `feat: keep a pending topic and name it in the job (plan 0084)`.

---

### Task 5: The follow-up beside the offer

**Files:** Create `server/src/server/memory/pending_follow_up.py`,
`tests/unit/test_pending_follow_up.py`; modify `server/src/server/text_turn.py`,
`server/src/server/streaming.py`; tests `tests/unit/test_text_turn.py` and the stream tests.

**Interfaces:**
- Consumes: Tasks 1 and 3.
- Produces: `@dataclass(frozen=True) class PendingFollowUp: topic_id: int; sentence: str
  (repr=False); actor (repr=False); correlation_id: UUID`; `type FollowUpPreparer =
  Callable[[ActivePersonContext, ContinuityTurn], Awaitable[PendingFollowUp | None]]`;
  `async def prepare_follow_up(actor, session, *, today, consent) -> PendingFollowUp | None`
  (D-8: face-identified owner, empty session history, not `asked_today`, a `due_topic`; reads only);
  `async def commit_follow_up(follow_up, *, now, policy, audit) -> str | None` (D-9: the request
  and its audit row first, then `mark_asked`; `None` on a refusal, a failed audit or a lost
  compare-and-set; never raises). In `text_turn`: `start_follow_up` beside `start_offer`, and one
  `finish_after_reply(offer_task, follow_up_task, *, reply_failed)` returning the phrase to speak
  (the offer when there is one — the follow-up task is then cancelled and its topic stays `open` —
  else the committed follow-up); `TextTurnResult` gains `follow_up: str | None` (repr hidden) and
  the session pair's assistant side carries the follow-up (D-12); the stream speaks it as the
  offer's extra `audio` event.

- [ ] **Step 1: Write the failing tests:** asked once on a new session and then `asked`; not on a
  continued session; not twice the same day (Review focus 2); not with a topic due today; the offer
  wins and the topic stays `open` (Review focus 5); a fallback reply carries neither; the policy
  refusal and a failed audit say nothing; the audit row precedes `mark_asked`; a `medical` topic
  needs the closed alta; the session's next turn holds the sentence, the record does not;
  `test_no_topic_reaches_a_log_line`; switch off: no preparation runs and `TextTurnResult` is
  today's.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS; the whole offer
  suite (`test_candidate_dialogue`, `test_memory_dialogue_routes`) unchanged.
- [ ] **Step 5:** commit `feat: pick a pending topic up after the reply (plan 0084)`.

---

### Task 6: The switch and the wiring

**Files:** Modify `.env.example`, `server/src/server/routers/transcribe.py`; tests
`tests/integration/test_pending_routes.py` (new).

**Interfaces:**
- Both voice routes bind a `FollowUpPreparer` (the turn's consent resolved as the sensitive read
  does) only when `pending_topics_on()`; `/chat` and `/vision/respond` unchanged.
  `.env.example` documents `PENDING_TOPICS_ENABLED` and its two prerequisites.

- [ ] **Step 1: Write the failing tests** (doubles for face, speech and model; real store, policy
  and audit; a topic stored due yesterday): on each voice route the first turn hears the reply and
  «¿Cómo te fue ayer con el banco?», `llm_response` the reply only, the stream's `done` with no new
  field; a second turn hears none; a two-face frame hears none (Review focus 3); with an open offer
  the offer is said and the topic stays `open`;
  `test_with_the_switch_off_every_route_is_byte_identical` (spies: no preparation, no store read).
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS; the unit, API and
  integration suites with `MEMORY_ENABLED=false`.
- [ ] **Step 5:** commit `feat: wire the pending topics switch (plan 0084)`.

---

### Task 7: The guards

**Files:** Modify `tests/unit/test_architecture_guards.py`.

- [ ] **Step 1: Write the failing tests:** `test_only_the_store_touches_pending_topics` (SQL on
  `pending_topics` only in `pending_store.py`, with a leak test); `pending_topics.py` is pure (the
  Plan 0083 purity guard extended); the generic prompt still reads no household store
  (`pending_store`, `pending_follow_up` added to the forbidden imports of the prompt modules).
- [ ] **Step 2:** Run → FAIL where new, then PASS.
- [ ] **Step 3:** commit `test: guard the pending topics store (plan 0084)`.

---

### Task 8: Verification and the whole-branch review

- [ ] **Step 1:** `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and not eval"
  -q -n auto`, `uv run pyright`, `uv run mypy server/src robot/src`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run ruff check scripts/*.py`,
  `uv run python scripts/check_reserved_terms.py`, `just gate` — all pass; the count in the PR.
- [ ] **Step 2: Simplify, then review the whole branch** (`git diff main...HEAD`), each agent on
  `sonnet`, reading `.claude/` first, read-only, briefed with this plan and its review focus: the
  `simplify` skill (four angles); then, in parallel, `architect-reviewer`,
  `pr-review-toolkit:code-reviewer`, `pr-review-toolkit:silent-failure-hunter`,
  `pr-review-toolkit:type-design-analyzer`, `pr-review-toolkit:pr-test-analyzer` and
  `security-auditor`. Each finding verified against the code (`superpowers:receiving-code-review`)
  and fixed with its RED test (Pipec's fix-everything rule), in `fix: … (plan 0084)` commits; then
  Step 1 again.

---

### Task 9: Truth, acceptance and close

**Files:** `docs/architecture/current-state.md` and the Archify memory diagram (validate → deliver
→ visual-check; a card line must not overflow at 1440×900), `docs/runbooks/operator-manual.md`,
`docs/evals/0084-pending-topics-acceptance.md` (new, outcomes only), ADR 0037 (*Implemented in
Plan 0084* and `Accepted`), ADR 0021 decision 9 (a note: the follow-up shares the offer's slot),
the ADR index, the plan board, `docs/plans/open/README.md`, `docs/plans/completed/README.md`, the
roadmap row 7 and both delivery maps, and Pipec's local `docs/roadmap/tabla-tareas.md`.

- [ ] **Step 1: Hardware acceptance by Pipec over two or three days** (streaming; `MEMORY_ENABLED`,
  the record, the diary and `PENDING_TOPICS_ENABLED` on; his face alone unless the case says). The
  agent backs up the database with the server stopped (migration 016 runs at the next start),
  reads `logs/server.log` (closed values only) and gives a numbered script; stories invented, **no
  health word except in case 3** (a health word marks the whole conversation `medical` in the
  diary, Plan 0078; the topic itself is classified on its own).
  - Day 1: (1) «Hoy voy al banco a pagar una cuenta.» → `pending.capture kept`; (2) «Mañana tengo
    una reunión con unos amigos.» → `kept`; (3) in a separate conversation, «El jueves tengo hora
    con el médico.» (due that Thursday) → `kept`, sensitivity medical; (4) «Mañana viene mi hija.»
    → `no_verb`; (5) «¿Voy mañana al banco?» → no row. The job names the topics within a few
    minutes of silence (`pending.named named`).
  - Day 2: (6) the first «Hola» → the reply and «¿Cómo te fue ayer con el banco?»; (7) another
    «Hola» after three minutes → no sentence (`already_today`); (8) the owner answers and the next
    reply follows the answer (the session holds the question).
  - Day 3: (9) «Hola» → «¿Cómo te fue ayer con la reunión?» (or «anteayer» for the bank if it was
    not asked); (10) with a photo of a second face on a phone, «Hola» → no sentence.
  - The day after the Thursday: (11) alone → «¿Cómo te fue ayer con el médico?»
  - `iroko-admin conversations` shows no follow-up sentence in the record.
  Phrasings that missed the grammar go into the Task 1 fixture in a fix commit, counts only.
- [ ] **Step 2:** Update the documents above; move the plan to `completed/`.
- [ ] **Step 3:** commit `docs: close plan 0084, pending topics`, push, open the PR, squash-merge
  with green CI (GitHub is delegated), delete the branch, return to `main`.

---

## Non-goals

Correcting or forgetting a topic by voice (ADR 0032, block C); a closed answer that moves a topic
(«no fui», D-13); a reminder at a time of day or one not tied to a greeting (P2.3); topics told by
someone other than the owner (the family stage, P3); a topic over a week, a month or a year (D-3);
the topic in any prompt; any wire, robot or dependency change.

## Self-review (2026-11-12)

- **Spec coverage.** ADR 0037 decision 2: the source (the diary-feeding turns, never a visitor) →
  D-2 and Tasks 1, 4; the detection (a future marker of the shared reader plus a first-person verb
  or «te cuento», the model naming two or three words with the extractor's rules, an unnamed topic
  not kept) → D-3, D-6 and Tasks 1, 2, 4; the storage (topic, due day, said day, source record,
  state, classification; cascade; expiry two days after the due day) → D-5, D-7, D-14 and Tasks 3,
  4; the follow-up (first face-identified turn of a new session, at most one topic due in the
  window, a fixed controller sentence after the reply, never in the prompt, the offer winning,
  asked once) → D-4, D-8, D-10, D-11 and Task 5; health (sensitive lexicon, only alone in view) →
  D-7, D-9 and Tasks 5, 6; decision 6 (its own default-off switch needing `MEMORY_ENABLED`,
  byte-identical off) → D-1 and Tasks 3 to 6; *Test consequences* (a visitor's sentence not kept;
  asked once on a new session and never in the prompt; a health topic not mentioned with a second
  face; expiry and cascade) → Tasks 3 to 6.
- **Where the plan departs from the ADR, for Pipec:** the window drops «today» (D-4); one follow-up
  per household day, not per session (D-8); a `normal` topic also waits with a guest in view (D-9);
  the sentence joins the session but not the record (D-12); `expired` is a deletion, not a state
  (D-5).
- **Type consistency.** `ANNOUNCING_VERBS`, `Announcement`, `AnnouncementOutcome`, `PendingTopic`,
  `PendingFollowUp`, `FollowUpPreparer`, `pending_topics_on` and `near_day_label` are each defined
  once and named the same in every later task.
- **Closed by Pipec (2026-11-12).** D-3 (the verb list), D-4, D-8, D-9, D-11 (the offer wins),
  D-12 and D-13 were confirmed as written, with every other decision.
