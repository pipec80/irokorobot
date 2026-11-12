# 0083 — One reader of spoken time, and when a told event happened

> **Status:** `Ready` and `NOW` — **promoted by Pipec on 2026-11-12**: D-1 to D-15 confirmed as
> written, and D-16 added from his review (the speaker the grammars are written for). Written as
> `Draft` the same day from
> [ADR 0037](../../adr/0037-the-time-of-memories-and-a-contacts-phone.md) (`Proposed`), decisions
> 3 and 4 only, plus decision 6 for the switch, and the code of `main` at `4cca2a7` (Plan 0082
> merged). Executed **inline** in a new Claude Code session (the builder's choice, which Pipec
> left to it: the tasks share interfaces end to end, from the reader to the store to the answer,
> and one executor holding them all is the cheaper path; independent reviewers check the whole
> branch in Task 8). Queue rule 4 applies at execution: Task 0 re-verifies every claim below
> against the merged code before any code, and **stops and reports** if one is false. ADR 0037
> stays `Proposed` until Plan 0084 (the pending topics, decision 2) closes too. Written for an
> executor who has not seen this repository.

> **For agentic workers:** if the status above does not say `Ready`, stop. Read `CLAUDE.md` and
> every file of `.claude/rules/` in full first. REQUIRED SUB-SKILLS: `superpowers:executing-plans`
> (inline), `superpowers:test-driven-development` for every task,
> `superpowers:verification-before-completion` before any claim of done,
> `superpowers:requesting-code-review` and `superpowers:receiving-code-review` for Task 8, and
> `superpowers:finishing-a-development-branch` for Task 9. The review agents of Task 8 and any
> other subagent run on the `sonnet` model and read `.claude/` (CLAUDE.md and `.claude/rules/`) in
> full before reading code. **Pipec's rules win over the skills:** one plain branch from `main`
> (`feat/0083-when-it-happened`), never a git worktree, this plan lives under `docs/plans/`. One
> commit per task; every test seen RED for the stated reason first. If evidence contradicts the
> plan, stop and report instead of redesigning. The Bash tool loses backslashes and non-ASCII
> characters in heredocs and arguments: use the Write and Edit tools, and put every Spanish test
> phrase in a YAML fixture. Commit titles: Conventional Commits, at most 72 characters, check
> `git log` after each commit (the hook rejects silently); never pipe `git commit`; `git add` with
> explicit paths. Run the suite with `MEMORY_ENABLED=false` as CI does; each test that needs memory
> sets `settings.memory_enabled` itself. Never run `uv sync` without `--extra cuda` (a plain
> `uv sync --all-packages --all-groups` removes the GPU build of Whisper). Do not run `just gate` in
> the background while Pipec rehearses (about 3.5 GB of RAM). The server and the robot are started
> by Pipec, never by the agent. Before pushing, run `pyright`, `ruff` and `mypy` over the **whole**
> project, lint `scripts/` with explicit paths and `uv run ruff format --check .` (CI also checks
> python blocks in `docs/*.md`).

## Decisions

Pipec's decisions are ADR 0037 decisions 3, 4 and 6 and its table *Pipec's decisions* row 4 («the
occurred time enters this ADR, with the same reader as the future»). The calls below fill in what
the ADR leaves to the builder (*Not decided here*: «the grammar's word lists and the switch
names»); they are confirmed or changed when Pipec promotes the plan. **D-6 to D-9, D-12 and D-13
are the ones most worth his eye** (the list under *Self-review*, *Open for Pipec*).

- **D-1 The switch.** `OCCURRED_TIME_ENABLED` (`occurred_time_enabled: bool = False`). It works only
  with `MEMORY_ENABLED` **and** `RECALL_ENABLED` (which itself needs the conversation record): one
  function, `recall_store.occurred_time_on() -> bool`, is the only place that combines the three,
  and every consumer asks it. Off, every route, prompt, reply and log line is byte-identical to
  `main`, including on a database whose units already carry an occurred interval (written while the
  switch was on). The migration of D-8 runs whatever the switch says: it only adds two empty
  columns.
- **D-2 One reader, one table.** `cognition/spoken_dates.py` keeps **one** ordered table of
  phrases; each entry carries its direction (`past`, `future`, `either` or `dated`, D-4) and whether
  it belongs to the legacy set Plan 0078 reads today. `parse_spoken_window` and
  `strip_window_words` keep their signatures and their results **exactly** (they walk the legacy
  entries only, in today's order: the whole of `tests/unit/test_spoken_dates.py` passes unchanged);
  the new `read_spoken_time` and `strip_time_words` walk every entry. No second date parser is
  written anywhere (a guard says so, Task 8). The module grows past the 200-line guideline on
  purpose: it has one responsibility, spoken time, and the ADR names it.
- **D-3 The phrases** (folded by `normalize_spanish`, so «año» is `ano` and «mañana» `manana`;
  whole words; a longer phrase is tried before the shorter one inside it):

  | Direction | Phrases |
  |---|---|
  | past | `ayer`; `anteayer`, `antes de ayer`; `la semana pasada`; `el mes pasado`; `el ano pasado`; `el {weekday} pasado`; `el {season} pasado`, `la primavera pasada` |
  | future | `manana` (not after `la`, `esta`, `por la`, `en la`, `de la`: those are the morning); `pasado manana`; `el proximo {weekday}`, `el {weekday} que viene`; `la proxima semana`, `la semana que viene`; `el proximo mes`, `el mes que viene`; `el proximo ano`, `el ano que viene`; `el proximo {season}`, `la proxima primavera`, `el {season} que viene`, `la primavera que viene` |
  | either | `hoy`, `hoy dia`; `esta manana`, `esta tarde`, `esta noche` (today); `el {weekday}`, `este {weekday}`, a bare `{weekday}`; `el {d} de {month}`, `{d} de {month}`; `en {month}`; `en {season}`, `en el {season}`, `el {season}` |
  | dated | `el {d} de {month} de {yyyy}`, `el {d} de {month} del {yyyy}`; `en {month} de {yyyy}`, `{month} de {yyyy}`, `en {month} del {yyyy}`; `el {season} de {yyyy}`, `en el {season} de {yyyy}`, `en {season} de {yyyy}` (and `del`); `en {yyyy}`, `el {yyyy}`, `en el {yyyy}`, `el ano {yyyy}`, `en el ano {yyyy}` |

  `{weekday}` is `lunes` … `domingo`, `{month}` `enero` … `diciembre`, `{season}` `verano`,
  `otono`, `invierno`, `primavera`; `{d}` one or two digits, `{yyyy}` four digits. A year needs its
  lead word (`en`, `el`, `del`, `de`, `ano`), so «pagué 2015 pesos» is no time.
- **D-4 How a phrase resolves** against `today` (the household's local date) and the direction
  asked (`Toward.PAST` or `Toward.FUTURE`). A `past` phrase asked toward the future, or a `future`
  phrase asked toward the past, is no time. An `either` phrase resolves toward the direction asked
  and is marked `ambiguous`. A `dated` phrase is its own window; toward the past it is a time only
  when the window starts on or before `today`, toward the future only when it ends on or after
  `today`, and it is `ambiguous` when it contains `today`. The windows:
  - a weekday: the last occurrence before today (past) or the next after today (future), today
    excluded both ways (as today's `_weekday`); `pasado` / `proximo` / `que viene` fix the direction;
  - a day and month without a year: the last occurrence on or before today (past, as today's
    `_day_of_month`) or the first on or after today (future); an invalid day («31 de febrero») is
    no time;
  - a week: Monday to Sunday; `la semana pasada` the one before the current week, `la proxima
    semana` the one after;
  - a month: its first to its last day; `en {month}` the last one that started on or before today
    (past, the current month included) or the next one that ends on or after today (future);
  - a season: D-5; `en {season}` like a month; `el {season} pasado` the last whole season that
    ended before today; `el proximo {season}` the first that starts after today;
  - a year: 1 January to 31 December; `{yyyy}` from 1900 to `today.year + 5`, anything else is no
    time; `el ano pasado` `today.year - 1`, `el proximo ano` `today.year + 1`;
  - `hoy`, `esta manana`, `esta tarde`, `esta noche`: today; `ayer` 1 day back, `anteayer` 2,
    `manana` 1 ahead, `pasado manana` 2.
- **D-5 The seasons** are the household's (Chile, southern hemisphere), by whole months, fixed in
  the module (a setting would be YAGNI while the household is one): `verano` of year *Y* is
  1 December *Y−1* to the last day of February *Y* («el verano de 2015» is the summer of
  January 2015); `otono` 1 March to 31 May; `invierno` 1 June to 31 August; `primavera`
  1 September to 30 November.
- **D-6 Not in the reader** (a phrase it does not know is no time, never a guess): «hace dos años»
  and every `hace {n} …`, «este año», «este mes», «este verano», years said in words («dos mil
  quince»), «el fin de semana», a weekday in the plural («los lunes» is a habit), hours and times
  of day other than D-3's, «antier», ranges («del 3 al 5»), «cuando era chico». *For Pipec:* add any of these now, or leave them for a measured
  session (the builder's call: leave them out; Whisper writes years as digits).
- **D-7 The occurred interval of a turn** (a pure `cognition/occurred_time.occurred_window`):
  only a **turn** unit gets one (the owner's own verified words; ADR 0031 decision 5 forbids an
  occurred time nobody said); an **episode** unit never does (a summary is the model's
  transformation, ADR 0031 decision 6). The turn's words must hold **exactly one** time phrase
  (`count_spoken_times == 1`: «ayer fui al médico y mañana voy al cine» gets none); it is read
  toward the past against the household day of the turn's own `at` (not the capture's clock);
  an `ambiguous` phrase needs one verb of the closed `TOLD_PAST_VERBS` in the words («el sábado fui
  a la playa» yes, «el sábado salimos a pasear» no). `TOLD_PAST_VERBS` (folded): `fui`, `fuimos`,
  `fue`, `fueron`, `estuve`, `estuvimos`, `estuvo`, `hice`, `hicimos`, `hizo`, `tuve`, `tuvimos`,
  `vi`, `vimos`, `comi`, `comimos`, `conoci`, `conocimos`, `volvi`, `volvimos`, `sali`, `naci`,
  `nacio`, `vivi`, `jugue`, `fallecio`, `murio`, `hubo`. It is its own list, not
  `recall_cues._WHEN_VERBS`: folded, a statement must leave out every form that is also a present
  (`salimos`, `viajamos`, `vivimos`, `paso`: «el sábado paso a verte»), a subjunctive (`compre`,
  `hable`, `llegue`, `trabaje`, `estudie`, `visite`: «cuando llegue el sábado») or a noun (`viaje`,
  `pase`). *For Pipec:* confirm the list.
- **D-8 The migration** (015, `memory/migration_015_occurred_interval.sql`), designed here because
  the ADR's *Consequences* name it: two nullable columns on `recall_units`, `occurred_start TEXT`
  and `occurred_end TEXT`, each a **local household calendar day** in ISO form (`2025-11-08`), not
  a UTC instant (a told day is a day; a later change of `HOUSEHOLD_TIMEZONE` does not move it).
  The second `ADD COLUMN` carries the table's rule as a `CHECK` (proved on the installed SQLite
  3.49.1 while writing this plan; `IS`, not `=`, so an invalid date is refused instead of passing
  as `NULL`):
  `CHECK ((occurred_start IS NULL) = (occurred_end IS NULL) AND (occurred_end IS NULL OR
  (date(occurred_start) IS occurred_start AND date(occurred_end) IS occurred_end AND
  occurred_start <= occurred_end)))`; one index `recall_units_owner_occurred_idx (owner_entity_id,
  occurred_start)`; `PRAGMA user_version = 15`; atomic like 011 to 014; no down-step; FTS5, `vec0`
  and the triggers are untouched (no column of theirs changes). **No backfill:** units written
  before the switch keep only `said_at` (re-reading old words is a new decision; *for Pipec:*
  confirm).
- **D-9 Which units a recall window matches** (with the switch on): a unit with an occurred
  interval matches when the interval **overlaps** the window's local days (`occurred_start <=
  last_day AND occurred_end >= first_day`); a unit without one matches by `said_at` as today. An
  **episode follows its turns:** an episode said in the window is left out when its record has at
  least one turn unit with an occurred interval and **no** turn unit of the record matches the
  window (so yesterday's diary entry of a story about last year is not «what you did yesterday»);
  a record with no turn units keeps its episode as today. Without this rule the measurement of ADR
  0037 decision 3 fails through the diary. *For Pipec:* overlap (not containment) means «¿qué hice
  en 2014?» also finds «el verano de 2015» (it starts in December 2014); confirm.
- **D-10 The «¿cuándo fui…?» answer** (`WhenKind.HAPPENED`, fixed templates, no model, over the
  first hit as today): when that unit has an occurred interval, «Fue {occurred}. Me lo contaste
  {told}.» («Fue el sábado 7 de noviembre. Me lo contaste ayer.», «Fue en 2015. Me lo contaste el
  3 de marzo.»), and «Fue {occurred}, el mismo día que me lo contaste.» when the interval is one day
  and that day is the told day; without one, today's answer unchanged («No tengo registrado cuándo
  fue. Sí recuerdo que …»). `WhenKind.TOLD` («¿cuándo te conté…?») is unchanged: it already names
  the told day. Every answer names which time it reports («Fue» is when it happened, «me lo
  contaste» / «me contaste» when it was told).
- **D-11 The occurred labels** (`spoken_dates.occurred_label(window, *, today)`; the told label
  stays `date_label`): a day «hoy», «ayer», «anteayer», else «el {weekday con tilde} {d} de
  {month}» in the current year and «el {d} de {month} de {yyyy}» in another; a week «la semana del
  lunes {d} de {month}» (+ « de {yyyy}» in another year); a month «en {month}» (+ « de {yyyy}»); a
  season «en el {season con tilde} de {yyyy}» (*yyyy* as in D-5: «en el verano de 2015»); a year
  «en {yyyy}». A window none of these describes raises `ValueError` (no date in the message) and
  the answer falls back to the told-day sentence.
- **D-12 The model-worded recall answer is unchanged**, also with the switch on: its prompt keeps
  labelling each memory with the day it was told and the rule that says so (the golden digests do
  not move). It already names the time it reports; adding a second date to the 3B model's prompt
  is the risk Plan 0080 measured. The occurred interval changes **which** units it receives (D-9),
  not how it words them. *For Pipec:* confirm, or ask for the occurred label in the prompt lines.
- **D-13 The question forms found on Plan 0082's hardware** join the recall grammar behind the
  switch (`classify_recall_cue(…, occurred=True)`): usted, «le» for «te», and Whisper's «tiene» for
  «tienes». Strong phrases `le conte`, `le comente`, `le habia contado`, `le habia dicho`,
  `como le dije` (not a bare `le dije`: «le dije a mi hija…» is a story about telling someone
  else); weak phrases `se acuerda`, `recuerda`; request openers `me puede decir`, `cuenteme`,
  `recuerdeme`, `me dice`, `sabe`, `digame`, `tienes registrado`, `tiene registrado`. With the
  switch on, a recall question's window comes from `read_spoken_time(…, toward=PAST)` (so «¿qué
  hice el año pasado?» and «¿qué hice en 2015?» have a window) and its query from
  `strip_time_words`. *For Pipec:* these forms could go in unconditionally as a grammar fix; behind
  the switch keeps decision 6's byte-identity.
- **D-14 Logs, never a date.** With the switch on, `conversation.capture` gains `occurred: bool`
  (the turn's unit got an interval) and `recall.read` gains `occurred_first: bool` (the first hit
  had one); off, neither field exists. No log line, exception message, audit row or `repr` carries
  a told date, an interval or the words around it.
- **D-15 The measurement of ADR 0037 decision 3** («a told-yesterday story about last year is no
  longer returned for «¿qué hice ayer?»») is an integration test on a migrated database with a
  fixed clock: the turn unit and its episode said yesterday, the story «el año pasado fui a la
  nieve», the question «¿qué hice ayer?»: found with the switch off (today's behaviour, the
  before), not found with it on (the after); both outcomes are written in the PR. On hardware the
  same is measured within a day with «¿qué hice hoy?» (Task 9).
- **D-16 The speaker the grammars are written for** (*Pipec, 2026-11-12*). Spanish says time with
  its tenses and many idioms, and people do not all conjugate well: some drop the ends of words,
  some say «s» for «c» or «z», and sometimes Whisper simply does not understand. The reader and the
  grammars are written for an ordinary adult speaker of Chilean Spanish in the usual forms (the
  phrases of D-3, the verbs of D-7, the question forms of D-13), not for every way of speaking. A
  form outside them is no time and no cue: the robot says the told day or answers as ordinary
  conversation, and never guesses (decision 4). Edge cases are not chased in the abstract: a form
  that a real hardware session shows to be common (Task 9) joins the YAML fixture and the closed
  list in a fix commit, recorded as counts only, as Plans 0079 to 0082 did.

**Goal.** With `OCCURRED_TIME_ENABLED` on, a story the owner tells with a time («el sábado fui a la
playa», «en 2015 viví en el norte», «el verano pasado») keeps when it happened next to when it was
told; «¿cuándo fui a la playa?» says «Fue el sábado 7 de noviembre. Me lo contaste ayer.»; «¿qué
hice el sábado?» finds what happened on Saturday, and a story about last year told yesterday is no
longer «what you did yesterday»; one reader of spoken time serves the past and the future.

**Architecture.** Pure and closed where it decides: `cognition/spoken_dates.py` grows one table of
phrases with a direction each and a `read_spoken_time` beside the legacy functions; a pure
`cognition/occurred_time.py` decides a turn's interval; the recall store (migration 015) writes and
filters by it; `recall_answer.word_when` words it. The capture computes the interval in the
background job that already writes the unit; the controller and the resolver pass one more flag.

**Tech stack.** Python 3.12, FastAPI, aiosqlite, SQLite 3.49 (FTS5, `sqlite-vec`), pytest. No new
dependency, no wire change, no robot change, no prompt change; one migration.

**Spec.** [ADR 0037](../../adr/0037-the-time-of-memories-and-a-contacts-phone.md) decisions 3, 4
and 6 and its *Test consequences*; [ADR 0031](../../adr/0031-the-memory-engine-boundary.md)
decision 5 (the four meanings of time; amended by ADR 0037 decision 3) and decision 6 (a summary is
never the person's words); [ADR 0028](../../adr/0028-recall-what-the-owner-told.md) decisions 1
(the units), 6 (the search) and 7 (dates in `HOUSEHOLD_TIMEZONE`);
[ADR 0027](../../adr/0027-conversation-record-and-the-diary.md) (only verified turns feed the
diary and the units); [current state](../../architecture/current-state.md), the recall rows (Plans
0078 and 0080); [guardrails](../../architecture/implementation-guardrails.md).

**Required reading.** The above, then the code: `server/src/server/cognition/spoken_dates.py`,
`cognition/recall_cues.py`, `cognition/intent_resolution.py` (`_recall_rule`, `_rules_for`),
`cognition/controller.py` (`_recall_decision`, the resolver flags), `memory/recall_store.py`,
`memory/recall_search.py`, `memory/recall_answer.py`, `memory/recall_access.py`,
`memory/conversation_capture.py` (`_recall_indexer`), `memory/migration_014_recall_units.sql`,
`db.py` (`_MIGRATIONS`), `routers/transcribe.py` (the controller's flags).

## Global constraints

- English code, comments and docstrings (Google style); Spanish only in user-facing strings;
  **no voseo** (`tests/unit/test_no_voseo_in_spoken_strings.py` covers the new phrases).
- No `Any`, no `print`, no `os.path`, no bare `except`; logging with `%`; settings only through
  `settings`, and the cognitive core reads none (the import-graph guard): the zone and the flags
  are passed in.
- Pure and closed: a phrase the reader does not know is no time; nothing is inferred from what the
  owner did not say; no model call is added to any path.
- One date reader: no regular expression over month, weekday or year words outside
  `spoken_dates.py` (Task 8 guard).
- One migration (015); `recall_store.py` stays the only SQL on `recall_units`.
- No date, interval or text in a log line, an audit row, an exception message or a `repr`.
- With `OCCURRED_TIME_ENABLED=false` every route, prompt, reply and log line is byte-identical to
  `main`; with `MEMORY_ENABLED=false` every turn is.
- No real household data: invented canaries only (stories such as «fui a la nieve», «viví en el
  norte», a sister without a name); `scripts/check_reserved_terms.py` passes.

## Review focus

Failure modes the ADR implies and no task title names; each has its test in the task that owns it.

1. **«Mañana» that is the morning.** «esta mañana fui al médico» is today and past; «en la mañana
   fui», «por la mañana» are no time; «mañana en la mañana voy» is tomorrow; «pasado mañana» is
   never «mañana» (Task 1).
2. **The year turns and February ends.** On 2026-12-30 «el próximo mes» is January 2027 and
   «pasado mañana» 2027-01-01; on 2027-01-15 (inside a summer) «el verano pasado» is December 2025
   to February 2026; the summer of 2028 ends on 29 February (Task 1).
3. **The household day, not the UTC day.** A story said at 23:30 local (02:30 UTC the next day)
   resolves «ayer» against the local day it was said, and the capture uses the turn's `at`, not the
   job's clock (Task 7).
4. **A future or a habit read as the past.** «el sábado salimos a pasear», «el jueves voy al
   médico», «los lunes juego fútbol», a story with two time phrases, and «¿cuándo fui?» or
   «¿cuándo fue eso?» (a short question with no topic: ordinary conversation, never a search of
   everything) get no interval and no search (Tasks 2 and 5).
5. **Usted and Whisper's «tiene».** «¿se acuerda cuándo fui a la playa?», «¿tiene registrado cuándo
   fui al cine?», «cuénteme cuándo fui al lago» are when-questions with the switch on; «le dije a
   mi hija que…» stays a story (Task 5).

---

## File structure

| File | Responsibility | Task |
|---|---|---|
| `cognition/spoken_dates.py` | The one table of phrases; `read_spoken_time`, `strip_time_words`, `count_spoken_times`, `occurred_label`; the legacy functions over its legacy entries | 1 |
| `cognition/occurred_time.py` (new) | `TOLD_PAST_VERBS`, `occurred_window` | 2 |
| `memory/migration_015_occurred_interval.sql` (new), `db.py`, `memory/recall_store.py` (write side) | The two columns, `RecallUnit.occurred`, `insert_turn_unit(…, occurred=)`, `occurred_time_on` | 3 |
| `memory/recall_store.py` (read side) | The window by occurred interval and the episode rule | 4 |
| `cognition/recall_cues.py`, `cognition/intent_resolution.py`, `cognition/controller.py` | The question side behind `occurred` | 5 |
| `memory/recall_search.py`, `memory/recall_answer.py`, `memory/recall_access.py` | The search's window days; the when-answer | 6 |
| `memory/conversation_capture.py`, `settings.py`, `.env.example`, `routers/transcribe.py` | The capture writes the interval; the switch and its wiring | 7 |
| `tests/unit/test_architecture_guards.py` | One date reader; purity | 8 |
| `docs/…` | Truth, acceptance, close | 9 |

---

### Task 0: Re-audit and baseline

**Files:** none changed.

- [ ] **Step 1:** `git checkout main && git pull`, then create `feat/0083-when-it-happened`.
- [ ] **Step 2:** Verify, and **stop and report** if any is false (throwaway scripts under
  `.superpowers/sdd/0083/`, never in the shell: it mangles accents):
  - `spoken_dates.parse_spoken_window(normalized, today)` walks `_PATTERNS` in the order
    day-of-month, `la semana pasada`, `el mes pasado`, `anteayer`, `ayer`, `hoy`, weekday, and
    returns the first match; `strip_window_words` removes every legacy match; nothing outside
    `recall_cues.py` imports either (`date_label` is read by `recall_answer.py`).
  - `normalize_spanish` folds «año» to `ano` and «mañana» to `manana` (NFD, combining marks
    dropped).
  - `recall_units` has the columns of migration 014 and no `occurred_*`; `db._MIGRATIONS` ends at
    `(14, "migration_014_recall_units.sql")`; `memory/schema.sql` is the version-1 base and does
    not need the new columns (if a test compares the full schema, list it).
  - The `CHECK` of D-8 works on the SQLite the venv loads (`sqlite3.sqlite_version`, 3.49.1 when
    written): a lone start, a start after the end and `2025-13-01` are refused.
  - `insert_turn_unit` is called only by `conversation_capture._recall_indexer`, inside the append
    transaction; `RecordedTurn.at` is timezone-aware; `insert_episode_unit` only by
    `conversation_episodes`.
  - Every read of `recall_store` (`lexical_hits`, `vector_hits`, `units_by_id`, `recent_units`)
    applies `_READABLE`; `search_recall` is their only caller besides tests (the guard of Plan 0080
    for `units_by_id`).
  - `word_when` is reached only through `recall_access._search_and_word`; `build_recall_messages`
    reads `said_at` only.
  - `classify_recall_cue(message, *, today)` is called by `controller._recall_decision` (with
    `self._today()`) and `intent_resolution._recall_rule` (with `date.today()`); `_rules_for` is
    cached over the four booleans of Plan 0082; `tells_something` passes `recall=True`.
  - `routers/transcribe.py` builds the controller with `alta_read=…` for both voice routes;
    `/chat` builds no recall answerer.
  - No module under `server/src/server` other than `spoken_dates.py` holds a list or a pattern of
    weekday or month words (the Task 8 guard); list any that does (a template that only formats a
    stored date through `day_month_label` is fine) and stop if one parses spoken dates.
- [ ] **Step 3:** Run the baseline and write the count in the PR:
  `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and not eval" -q -n auto`.

---

### Task 1: The one reader of spoken time

**Files:** Modify `server/src/server/cognition/spoken_dates.py`; create
`tests/unit/test_spoken_time.py`, `tests/fixtures/spoken_times.yaml`; `tests/unit/test_spoken_dates.py`
must pass unchanged.

**Interfaces:**
- Produces: `class Toward(StrEnum): PAST = "past"; FUTURE = "future"`;
  `@dataclass(frozen=True) class SpokenTime: window: DayWindow; ambiguous: bool`;
  `def read_spoken_time(normalized: str, today: date, *, toward: Toward) -> SpokenTime | None`
  (the first phrase of the table that resolves, D-3 and D-4);
  `def strip_time_words(normalized: str) -> str` (every phrase of the table);
  `def count_spoken_times(normalized: str) -> int` (each phrase counted once, a longer phrase
  winning over a shorter one inside it: «pasado mañana» is one, «el sábado pasado» is one);
  `def occurred_label(window: DayWindow, *, today: date) -> str` (D-11; `ValueError` without the
  date for a window no span describes). `parse_spoken_window`, `strip_window_words`, `DayWindow`,
  `date_label`, `day_month_label` and `window_utc_bounds` keep their signatures and results.

- [ ] **Step 1: Write the failing tests** over the fixture (each case: `today`, the phrase, the
  direction, then `start`, `end` and `ambiguous`, or `null`): every D-3 row with `today` =
  2026-11-12 (a Thursday): «el sábado» past 2026-11-07 / future 2026-11-14 (ambiguous); «el jueves»
  past 2026-11-05 / future 2026-11-19; «la semana pasada» 2026-11-02 to 2026-11-08; «la próxima
  semana» 2026-11-16 to 2026-11-22; «el próximo mes» 2026-12-01 to 2026-12-31; «el verano pasado»
  2025-12-01 to 2026-02-28; «el verano de 2015» 2014-12-01 to 2015-02-28; «en 2015» 2015-01-01 to
  2015-12-31 past and `null` future; «en 2026» ambiguous both ways; «en 2040» `null` (beyond
  `today.year + 5`); «el 31 de febrero» `null`; «ayer» future `null`; «mañana» past `null`.
  `test_morning_is_not_tomorrow` (Review focus 1); `test_the_year_turns_and_february_ends` (Review
  focus 2: `today` 2026-12-30 and 2027-01-15; the summer of 2028); `test_a_year_needs_its_lead_word`
  («pagué 2015 pesos»); `test_unknown_phrases_are_no_time` (every D-6 example);
  `test_count_spoken_times` (zero, one, «pasado mañana» one, «ayer … y mañana …» two);
  `test_strip_time_words` (every phrase leaves its sentence); `test_occurred_labels` (each span of
  D-11, the current year and another, `ValueError` for 2026-11-03 to 2026-11-05 without the date
  in the message); `test_the_legacy_window_is_unchanged` (every phrase of the fixture through
  `parse_spoken_window` and `strip_window_words` equals the result `main` gives: the expected values
  are recorded in the fixture from `main` in Step 1, before any change).
- [ ] **Step 2:** Run `uv run pytest tests/unit/test_spoken_time.py tests/unit/test_spoken_dates.py -q`
  → the new tests FAIL (names missing), the old ones PASS.
- [ ] **Step 3:** Implement: one table of entries `(pattern, resolver, direction, walks)`, where
  `walks` says whether the legacy functions, the new ones or both read the entry. The legacy walk
  is today's seven patterns, unchanged and in today's order; an entry both walks share is written
  once (`ayer`, `anteayer`, `la semana pasada`, `el mes pasado`, `hoy`); today's weekday pattern
  (`(?:el |este )?{weekday}(?: pasado)?`) stays legacy-only, and the new walk reads the weekday
  through its three D-3 entries instead (past, future, either). Every new-walk pattern refuses a
  plural weekday (`los {weekday}`).
- [ ] **Step 4:** Run → PASS; the no-voseo test passes.
- [ ] **Step 5:** commit `feat: read spoken time past and future (plan 0083)`.

---

### Task 2: The occurred interval of a told turn

**Files:** Create `server/src/server/cognition/occurred_time.py`,
`tests/unit/test_occurred_time.py`, `tests/fixtures/occurred_times.yaml`.

**Interfaces:**
- Consumes: Task 1.
- Produces: `TOLD_PAST_VERBS: Final[frozenset[str]]` (D-7);
  `def occurred_window(heard: str, *, said_day: date) -> DayWindow | None` (pure: folds, requires
  `count_spoken_times == 1`, reads toward the past, requires a `TOLD_PAST_VERBS` word for an
  ambiguous phrase).

- [ ] **Step 1: Write the failing tests** over the fixture (statement, `said_day`, expected window
  or `null`): «el sábado fui a la playa» → 2026-11-07; «ayer estuve en el hospital» → 2026-11-11
  (past phrases need no verb); «en 2015 viví en el norte» → the year; «el verano pasado fuimos al
  lago» → the season; «el año pasado fui a la nieve» → 2025; «hoy fui al cine» → 2026-11-12; «hoy
  estoy cansado» → `null`; «el sábado salimos a pasear», «el jueves voy al médico», «mañana voy al
  cine», «los lunes juego fútbol» → `null`; «ayer fui al médico y mañana voy al cine» → `null`;
  «fui al cine con mi hermana» → `null`; «el sábado tengo un viaje» → `null`.
  `test_the_verb_list_is_closed` (no form of D-7's exclusions is in it).
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** commit `feat: tell when a told event happened (plan 0083)`.

---

### Task 3: Migration 015 and the written interval

**Files:** Create `server/src/server/memory/migration_015_occurred_interval.sql`,
`tests/integration/test_migration_015_occurred_interval.py`; modify `server/src/server/db.py`,
`server/src/server/memory/recall_store.py`, `tests/integration/test_recall_store.py`,
`tests/integration/test_recall_schema.py`.

**Interfaces:**
- Produces: the migration of D-8; `RecallUnit.occurred: DayWindow | None = None` (`repr=False`);
  `insert_turn_unit(conn, *, record_id, owner_entity_id, turn, occurred: DayWindow | None = None)`
  writes the two columns (ISO days) or `NULL`; `insert_episode_unit` never writes them;
  `def occurred_time_on() -> bool` (D-1: `settings.memory_enabled and settings.recall_enabled and
  settings.occurred_time_enabled`; the setting itself is added here with its default, wired in
  Task 7).

- [ ] **Step 1: Write the failing tests:** `test_migration_015_adds_two_empty_columns` (a 014
  database with units migrates, every old unit has both `NULL`, `user_version` 15, FTS and vectors
  still find the old units); `test_the_check_refuses_a_bad_interval` (a lone start, a start after
  the end, `2025-13-01`); `test_a_turn_unit_stores_its_interval`;
  `test_an_episode_unit_never_has_one`; `test_a_deleted_record_takes_its_interval_along` (cascade,
  as today); `test_occurred_time_on_needs_memory_and_recall` (the eight combinations).
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS; the whole recall
  integration suite.
- [ ] **Step 5:** commit `feat: store when a told event happened (plan 0083)`.

---

### Task 4: Recall windows by the occurred interval

**Files:** Modify `server/src/server/memory/recall_store.py`,
`tests/integration/test_recall_store.py`.

**Interfaces:**
- Consumes: Task 3.
- Produces: `lexical_hits`, `vector_hits`, `units_by_id` and `recent_units` gain
  `first_day: str | None = None`, `last_day: str | None = None` (the window's local ISO days) and
  `occurred: bool = False`. With `occurred=False` the SQL text, the parameters and the results are
  today's, and `RecallUnit.occurred` is `None` whatever the column holds; with `occurred=True` the
  window clause is D-9's (the overlap, the `said_at` fallback, the episode rule) and every returned
  unit carries its interval.

- [ ] **Step 1: Write the failing tests** (a migrated database, canary units, fixed `now`):
  `test_with_the_flag_off_the_sql_and_results_are_unchanged` (each read, a database whose units
  carry intervals); `test_a_unit_matches_by_its_interval` (said today, «el sábado» interval →
  found for Saturday's window, not for today's); `test_a_unit_without_one_matches_by_said_at`;
  `test_overlap_not_containment` (a season against one of its days; a year against a week);
  `test_an_episode_follows_its_turns` (the record's only turn is about last year → the episode is
  not in yesterday's window; a record with one turn about yesterday keeps it; a record with no
  turn units keeps it); `test_the_last_year_story_told_yesterday` (D-15: `recent_units` for
  yesterday returns it with `occurred=False` and nothing with `occurred=True`; the counts go in the
  PR); `test_units_by_id_still_applies_every_filter` (owner, `normal`, expiry, as Plan 0080 pins).
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** commit `feat: match a recall window by when it happened (plan 0083)`.

---

### Task 5: The question side behind the flag

**Files:** Modify `server/src/server/cognition/recall_cues.py`,
`server/src/server/cognition/intent_resolution.py`, `server/src/server/cognition/controller.py`,
`server/src/server/memory/recall_store.py` (`tells_something`); tests
`tests/unit/test_recall_cues.py`, `tests/fixtures/recall_cues_occurred.yaml` (new),
`tests/unit/test_intent_resolution.py`, `tests/unit/test_controller_recall.py`,
`tests/unit/test_recall_tells_something.py`.

**Interfaces:**
- Consumes: Task 1, Task 3 (`occurred_time_on`).
- Produces: `classify_recall_cue(message, *, today, occurred: bool = False)`: with `occurred`, the
  window is `read_spoken_time(…, toward=Toward.PAST).window`, the query is stripped with
  `strip_time_words`, and the phrases of D-13 join the strong, weak and opener lists;
  `RecallCue` is unchanged. `resolve_information_need(message, *, recall=False, sensitive=False,
  secrets=False, alta=False, occurred=False)`; `_rules_for` caches over the five booleans and
  passes `occurred` to the recall rule; `occurred` without `recall` changes nothing.
  `CognitiveController(…, occurred_time: bool = False)` passes `occurred=True` to the resolver and
  to `classify_recall_cue` only when set (the bare calls of today stay). `tells_something` passes
  `occurred=occurred_time_on()`.

- [ ] **Step 1: Write the failing tests:** `test_with_the_flag_off_cues_are_unchanged` (the whole
  existing recall-cue fixture, byte-identical); over the new fixture, with `occurred=True`: «¿qué
  hice el año pasado?», «¿qué hice en 2015?», «¿qué hice el verano pasado?» have a window and no
  date words in the query; «¿se acuerda cuándo fui a la playa?», «¿tiene registrado cuándo fui al
  cine?», «¿tienes registrado cuándo fui al cine?», «cuénteme cuándo fui al lago», «dígame cuándo
  fui a la nieve», «¿le conté que fui a la playa?» are cues with their kind (Review focus 5); and
  `None` for «le dije a mi hija que fuera a la playa», «¿cuándo fui?», «¿cuándo fue eso?», «¿qué
  voy a hacer mañana?» (Review focus 4); the same phrases with `occurred=False` give today's
  result. `test_the_resolver_flag_needs_recall`; `test_the_controller_passes_the_flag_only_when_set`;
  `test_tells_something_follows_the_switch` (a usted recall question is no unit with the switch on).
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS;
  `uv run pytest tests/unit -q -k "recall or intent or controller"`.
- [ ] **Step 5:** commit `feat: hear when-questions with usted and years (plan 0083)`.

---

### Task 6: The search's days and the when-answer

**Files:** Modify `server/src/server/memory/recall_search.py`,
`server/src/server/memory/recall_answer.py`, `server/src/server/memory/recall_access.py`; tests
`tests/integration/test_recall_search.py`, `tests/unit/test_recall_answer.py`,
`tests/unit/test_recall_access.py`.

**Interfaces:**
- Consumes: Tasks 1, 3 and 4.
- Produces: `search_recall` passes the window's `first_day` / `last_day` (ISO) and
  `occurred=occurred_time_on()` to every store read; `word_when(hits, kind, *, today, tz)` keeps its
  signature and, for `WhenKind.HAPPENED`, words D-10 when `hits[0].unit.occurred` is set (an
  `occurred_label` error falls back to today's sentence); `recall.read` gains `occurred_first` with
  the switch on only (D-14). `build_recall_messages` is untouched (D-12).

- [ ] **Step 1: Write the failing tests:** `test_when_it_happened_is_said` («Fue el sábado 7 de
  noviembre. Me lo contaste ayer.»; «Fue en 2015. Me lo contaste el 3 de marzo.»; «Fue en el verano
  de 2015. …»; the same-day form); `test_without_an_interval_the_answer_is_unchanged` (the exact
  sentences of Plan 0080 D-9); `test_an_episode_hit_keeps_the_told_day`; `test_told_is_unchanged`;
  `test_a_bad_window_falls_back` (no date in the warning); `test_the_recall_prompt_is_unchanged`
  (the messages of `build_recall_messages` equal, switch on and off, for units with intervals; a
  digest recorded from `main` when no golden one exists); `test_the_search_passes_the_days`
  (integration, «¿qué hice el sábado?» finds the Saturday story told today with the switch on, and
  not with it off); `test_the_log_has_no_date` (caplog over each outcome).
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** commit `feat: answer when a told event happened (plan 0083)`.

---

### Task 7: The capture, the switch and the wiring

**Files:** Modify `server/src/server/memory/conversation_capture.py`,
`server/src/server/settings.py`, `.env.example`, `server/src/server/routers/transcribe.py`; tests
`tests/unit/test_conversation_capture.py`, `tests/api/` (the recall route tests and the voice-route
byte-identity tests), `tests/integration/test_recall_routes.py`.

**Interfaces:**
- Consumes: Tasks 2 to 6.
- Produces: `_recall_indexer` passes `occurred=occurred_window(turn.heard,
  said_day=turn.at.astimezone(household_zone()).date())` to `insert_turn_unit` when
  `occurred_time_on()`, else nothing (today's call); `conversation.capture` gains `occurred` with
  the switch on only (D-14). `occurred_time_enabled: bool = False` documented in `settings.py` and
  `.env.example` (`OCCURRED_TIME_ENABLED`, its two prerequisites). Both voice routes build the
  controller with `occurred_time=occurred_time_on()`; `/chat` and `/vision/respond` unchanged.

- [ ] **Step 1: Write the failing tests:** `test_the_capture_writes_the_interval_with_the_switch`
  (on: the unit has it; off: `NULL`, and the log line of today); `test_the_household_day_not_utc`
  (Review focus 3: `at` 2026-11-13T02:30Z, «ayer fui al cine» → 2026-11-11 with
  `America/Santiago`); `test_a_capture_failure_still_touches_nothing_else` (an error in
  `occurred_window` is the capture's existing boundary: the turn is recorded or not, as today);
  `test_with_the_switch_off_every_route_is_byte_identical` (classic and streaming; a story with a
  date, a when-question and a generic turn; `RECALL_ENABLED` on and off);
  `test_the_switch_needs_recall` (on without recall: today's behaviour);
  `test_when_on_each_voice_route` (a told story then «¿cuándo fui a la playa?»: the D-10 sentence,
  no model call for it, the `done` event has no new field); D-15 end to end on a migrated database
  (before and after counts in the PR).
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS; the unit, API and
  integration suites with `MEMORY_ENABLED=false`.
- [ ] **Step 5:** commit `feat: wire the occurred time switch (plan 0083)`.

---

### Task 8: The guards and the full verification

**Files:** Modify `tests/unit/test_architecture_guards.py`.

- [ ] **Step 1: Write the failing tests:** `test_one_reader_of_spoken_time` (no module under
  `server/src/server` but `spoken_dates.py` holds a pattern with a month name, a weekday name or
  `pasado manana`); `test_occurred_time_is_pure` (`occurred_time` and `spoken_dates` import no
  `settings`, `db`, `aiosqlite`, `httpx` or `memory`); `test_only_the_store_touches_the_columns`
  (`occurred_start` / `occurred_end` appear only in `recall_store.py` and the migration).
- [ ] **Step 2:** Run → FAIL where a guard is new and its rule already holds, see it fail once by
  a throwaway breach, then remove the breach.
- [ ] **Step 3:** Run `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and not eval"
  -q -n auto`, `uv run pyright`, `uv run mypy server/src robot/src`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run ruff check scripts/*.py`,
  `uv run python scripts/check_reserved_terms.py`, `just gate` (not in the background if Pipec is
  rehearsing) — all pass. Write the count in the PR.
- [ ] **Step 4:** commit `test: one reader of spoken time (plan 0083)`.
- [ ] **Step 5: Simplify, then review the whole branch** (`git diff main...HEAD`), each agent on
  `sonnet`, reading `.claude/` first, read-only, briefed with this plan and the review focus:
  the `simplify` skill (reuse, altitude, dead code); then, in parallel,
  `architect-reviewer` (the cognitive core stays pure, one reader, the store the only SQL, SOLID
  and the layering), `pr-review-toolkit:code-reviewer` (the rules of `.claude/rules/`, docstrings,
  no magic strings), `pr-review-toolkit:silent-failure-hunter` (the capture's background boundary,
  the fallbacks of D-10 and D-11), `pr-review-toolkit:type-design-analyzer` (`SpokenTime`,
  `Toward`, `RecallUnit.occurred`), `pr-review-toolkit:pr-test-analyzer` (the review focus and
  D-15 pinned) and the `security-review` skill (migration 015, no date in a log, the window SQL is
  parameterized). Each finding is verified against the code with
  `superpowers:receiving-code-review` before it is fixed; everything found is fixed (Pipec's
  standing rule), each fix with its RED test, in commits `fix: … (plan 0083)`; then Step 3 again.

---

### Task 9: Truth, acceptance and close

**Files:** `docs/architecture/current-state.md` (the recall rows) and its Archify memory diagram
(validate → deliver), `docs/runbooks/operator-manual.md` (`OCCURRED_TIME_ENABLED`, the phrases),
`docs/evals/0083-when-it-happened-acceptance.md` (new, outcomes only), ADR 0037 (an *Implemented in
Plan 0083* note for decisions 3 and 4), ADR 0031 decision 5 (an *Amended by ADR 0037* note), ADR
0028 decision 7 (a pointer to the occurred interval), the plan board, the roadmap row 7.

- [ ] **Step 1: Hardware acceptance by Pipec** (streaming route; `MEMORY_ENABLED`, the record and
  the diary, `RECALL_ENABLED` and `OCCURRED_TIME_ENABLED` on; his face alone in view). The agent
  runs the backup, reads `logs/server.log` after each phrase (the capture's `verdict` and
  `occurred`, the `recall.read` outcome; values only) and gives Pipec this script, «Yo» the agent's
  check and «Tú» what Pipec says. A story counts only when its turn was `verified` (about one turn
  in three on the laptop, more above 3 s): if not, Pipec says it again.
  1. Tú: «El sábado fui a la playa con mi hermana.» Yo: `verified`, `occurred=true`.
  2. Tú: «El año pasado fui a la nieve.» Yo: `verified`, `occurred=true`.
  3. Tú: «Fui al cine y lo pasé muy bien.» Yo: `verified`, `occurred=false`.
  4. Tú: «Ayer fui al médico y mañana voy al dentista.» Yo: `occurred=false`.
  5. Tú: «¿Cuándo fui a la playa?» → «Fue el sábado {d} de noviembre. Me lo contaste hoy.»
  6. Tú: «¿Se acuerda cuándo fui a la nieve?» → «Fue en {año pasado}. Me lo contaste hoy.»
  7. Tú: «¿Cuándo fui al cine?» → «No tengo registrado cuándo fue. Sí recuerdo que hoy me
     contaste esto: …».
  8. Tú: «¿Qué hice hoy?» → the cinema (or the doctor) story, **not** the snow nor the beach: both
     happened on another day (D-15 on hardware).
  9. Tú: «¿Qué hice el año pasado?» → the snow story.
  10. Tú: «¿Tiene registrado cuándo fui al médico?» → the told-day answer (case 4 has no interval).
  11. Tú: «¿Cuándo fue eso?» → an ordinary reply, no `recall.read` line.
  12. With `OCCURRED_TIME_ENABLED=false` and a restart: case 5 → today's told-day answer.
  Phrasings that missed the grammar go into the Task 2 or Task 5 fixture and the grammar in a fix
  commit, recorded as counts only.
- [ ] **Step 2:** Update the documents above; move the plan to `completed/`; the board's NOW names
  Plan 0084 as next.
- [ ] **Step 3:** commit `docs: close plan 0083, when a told event happened`, push, open the PR,
  squash-merge with green CI (GitHub is delegated), delete the branch, return to `main`.

---

## Non-goals

The pending topics and the greeting that picks one up (Plan 0084; this plan builds the future half
of the reader and tests it, and no runtime path reads the future yet); correcting or forgetting an
occurred time by voice (ADR 0032, block C); a backfill of old units (D-8); an occurred time for a
diary episode (D-7); the occurred label in the recall prompt (D-12); the phrases of D-6; a reminder
at a time of day; any wire, robot, prompt or dependency change.

## Self-review (2026-11-12)

- **Spec coverage.** ADR 0037 decision 3 (an interval next to `said_at` when a diary-feeding turn
  tells a past event the reader resolves; never inferred; «¿cuándo fui…?» with the interval or the
  told day, naming which; the window by the interval, else `said_at`; the yesterday-versus-last-year
  measurement) → D-7 to D-12, D-15 and Tasks 2, 3, 4, 6, 7 and 9; decision 4 (one reader, past and
  future, «mañana», «pasado mañana», «el jueves», «la próxima semana», «el próximo mes», years and
  seasons, household day and zone, pure and closed, every consumer, no second parser) → D-2 to
  D-6 and Tasks 1 and 8 (the pending topics consume it in Plan 0084); decision 6 (its own
  default-off switch needing `MEMORY_ENABLED`, byte-identical off) → D-1 and Tasks 3, 4, 5, 7; the
  ADR's *Consequences* (a migration for the occurred interval) → D-8 and Task 3; *Test
  consequences* for the reader and the occurred time → Tasks 1, 2, 4, 6 and 7. The Plan 0082
  hardware lessons (usted, «tiene», short questions) → D-13 and Review focus 4 and 5.
- **Type consistency.** `Toward`, `SpokenTime`, `DayWindow`, `TOLD_PAST_VERBS`,
  `RecallUnit.occurred` and `occurred_time_on` are each defined once and named the same in every
  later task; `read_spoken_time(…, toward=)`, `classify_recall_cue(…, occurred=)`,
  `resolve_information_need(…, occurred=)`, `CognitiveController(…, occurred_time=)`,
  `insert_turn_unit(…, occurred=)` and the store reads' `first_day`, `last_day`, `occurred` are the
  only new parameters.
- **Proportion.** No function body is written out; each step names its tests and values, and the
  decisions carry the word lists and templates the ADR leaves to the plan.
- **Open for Pipec.** D-6 (phrases left out), D-7 (the verb list), D-8 (no backfill), D-9 (overlap
  and the episode rule), D-12 (the prompt unchanged), D-13 (the usted forms behind the switch); every
  other decision is the builder's call to confirm as written.
- **Pipec's review (2026-11-12).** D-1 to D-15 confirmed as written, the six above included. D-16
  added from his review: the grammars serve an ordinary speaker, and an edge form joins a fixture
  only when a real session shows it. Execution inline with the Task 8 reviews, chosen by the
  builder at his request. A search of the skills registry and of the account's skills found
  nothing to add for this plan (date parsing in Spanish, SQLite migrations, pytest): the installed
  superpowers, review agents and `simplify` / `security-review` cover it. Nothing is left open.
