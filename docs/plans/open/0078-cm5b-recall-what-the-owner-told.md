# 0078 — CM-5b + R3: recall what the owner told, and read the relatives of the alta

> **Status:** `Ready` and `NOW` (2026-11-03). Written the same day as its design,
> [ADR 0028](../../adr/0028-recall-what-the-owner-told.md) (`Proposed`), whose eleven decisions Pipec
> confirmed in the design session, and **promoted by Pipec the same day** (D-1 to D-11 below
> confirmed as written). It is executed in a new session, on `feat/0078-recall`; ADR 0028 moves to
> `Accepted` when it closes. Detailed against `main` at `fb32672`; queue rule 4 applies at
> execution: Task 0 re-verifies every claim below against the merged code before any code, and
> **stops and reports** if one is false. Written for an executor who has not seen this repository.

> **For agentic workers:** if the status above does not say `Ready`, stop. REQUIRED SUB-SKILLS:
> `superpowers:executing-plans`, `superpowers:test-driven-development`,
> `superpowers:verification-before-completion`, `superpowers:finishing-a-development-branch`.
> **Pipec's rules win over the skills:** one plain branch from `main` (`feat/0078-recall`), never a
> git worktree, subagents only if Pipec asks, this plan lives under `docs/plans/`. One commit per
> task; every test seen RED for the stated reason first. If evidence contradicts the plan, stop and
> report instead of redesigning. The Bash tool of this environment loses backslashes and non-ASCII
> characters in heredocs and command arguments: use the Write and Edit tools, and put Spanish test
> phrases in files. Commit messages: Conventional Commits, title at most 72 characters, check
> `git log` after each commit (the hook rejects silently); do not pipe `git commit`; `git add` with
> explicit paths. Run the suite with `MEMORY_ENABLED=false` as CI does, and have each test that needs
> memory set `settings.memory_enabled` itself. Never run `uv sync --all-packages --all-groups` (it
> removes the optional `cuda` extra). **Do not run `just gate` in the background while Pipec
> rehearses** (about 3.5 GB of RAM). **The server and the robot are started by Pipec**, never by the
> agent. Before pushing, run `pyright`, `ruff` and `mypy` over the **whole** project and lint
> `scripts/` with explicit paths (`ruff check .` skips it, the pre-commit hook does not).

## Decisions

Confirmed by Pipec on 2026-11-03, in ADR 0028: the eleven decisions of its *Pipec's decisions*
table. The author's calls below were confirmed by Pipec on promotion (2026-11-03), as written:

- **D-1 The cue grammar.** A message is a recall question only when it is a question: it carries
  «?» or opens (after the fillers `_LEADING_FILLERS` of `household_request.py`) with an
  interrogative or a cue word. **Strong** cue phrases (folded by `normalize_spanish`): `te conte`,
  `te dije`, `te habia contado`, `te habia dicho`, `te comente`, `como te dije`, `que hice`,
  `que hicimos`. **Weak** cue phrases: `te acuerdas`, `recuerdas`, `te recuerdas`, `acuerdate`,
  `te acordai`. «me acuerdo», «no me acuerdo» and «recuerdo que» are never cues. A strong phrase
  wins over a weak one in the same message.
- **D-2 Rule order.** In `intent_resolution._RULES` the new `_relatives_rule` and `_recall_rule` go
  **before** `_protected_household_rule`; every other rule keeps its place. `_profile_summary_rule`
  keeps the bare questions («¿qué sabes de mí?», «¿qué te conté?» with nothing after it): it runs
  before `_recall_rule`, which therefore needs a date or a content word after the cue.
- **D-3 The threshold.** `RECALL_MAX_DISTANCE` (cosine distance) starts at **0.30**: the midpoint of
  `granite-embedding:278m`'s mean distance between paraphrases (0.161) and between unrelated
  phrases (0.431) in Plan 0075. A question is farther from a statement than a paraphrase is, so the
  value is calibrated in Task 12 from the logged distances of Pipec's real questions.
- **D-4 The search constants.** `RRF_K = 60`; `RECALL_VECTOR_K = 20` (neighbours asked of `vec0`
  before the date and expiry filters); `RECALL_MAX_RESULTS = 3`; `RECALL_MAX_PER_RECORD = 2`;
  `RECALL_MAX_TERMS = 8` (content words sent to FTS5, joined with `OR`, each in double quotes).
  Code constants, not settings.
- **D-5 The word classifier** (`memory/recall_sensitivity.py`), folded words, a match on a whole
  word or phrase: **medical** `doctor`, `doctora`, `medico`, `medica`, `hospital`, `clinica`,
  `remedio`, `remedios`, `pastilla`, `pastillas`, `medicamento`, `enfermedad`, `enfermo`,
  `enferma`, `dolor`, `presion`, `diabetes`, `cancer`, `examen`, `examenes`, `operacion`,
  `cirugia`, `diagnostico`, `tratamiento`, `depresion`, `ansiedad`; **location** `direccion`,
  `vivo en`, `vivimos en`, `mi casa queda`, `calle`, `avenida`, `pasaje`, `departamento numero`,
  `numero de casa`; **security** `clave`, `contrasena`, `codigo`, `pin`, `alarma`, `llave`,
  `llaves`, `porton`. Several categories → `security` > `medical` > `location`. Nothing → `normal`.
- **D-6 The fixed phrases** (tuteo, no voseo): `NO_MEMORY = "No me acuerdo de eso."`;
  `NOT_REGISTERED = "No tengo registrado eso."`; the fallback template
  `"{label} me contaste esto: {body}"` (capitalized label); a recall or relatives question from
  anyone who is not the face-identified owner answers the existing `_PROFILE_SUMMARY_UNKNOWN_RESPONSE`
  of `controller.py`, so every refusal sounds the same.
- **D-7 The date labels**, local time in `HOUSEHOLD_TIMEZONE`: `hoy`, `ayer`, `anteayer`; within the
  last 6 days `el {weekday}`; the same year `el {d} de {month}`; another year
  `el {d} de {month} de {yyyy}`. Spanish weekday and month names in a constant tuple (never the
  locale).
- **D-8 The recall prompt** (Task 8 pins it in a golden test): system = one persona line
  («Eres Iroko, un robot de compañía de la casa. Hablas español neutro, con tuteo.») plus the rules
  of ADR 0028 decision 8; user = `Pregunta: «…»` and `Recuerdos:` with one line per unit
  `- ({label}) «{body}»`, at most 1200 characters of bodies. Model `settings.ollama_model`,
  temperature 0.1, timeout `settings.ollama_timeout_s`. The answer is cut at its first two
  sentences and passed through `claim_guard.neutralize_memory_claims`.
- **D-9 The relatives templates.** `has_parent`: one → «Tu papá o tu mamá se llama A.», several →
  «Tus papás se llaman A y B.»; `has_sibling`: «Tu hermano o hermana se llama A.» / «Tus hermanos
  se llaman A y B.»; `has_grandparent`: «Tu abuelo o abuela…» / «Tus abuelos…»; `has_grandchild`:
  «Tu nieto o nieta…» / «Tus nietos…»; `partner_of`: «Tu pareja se llama A.»; `pet_of`: «Tu mascota
  se llama A.» / «Tus mascotas se llaman A y B.». Names joined with `_spanish_join` of
  `controller.py`. The relation words that trigger each: `mama`, `papa`, `papas`, `padres`,
  `madre`, `padre` → parents; `hermano`, `hermana`, `hermanos`, `hermanas` → siblings; `abuelo`,
  `abuela`, `abuelos` → grandparents; `nieto`, `nieta`, `nietos`, `nietas` → grandchildren;
  `pareja`, `esposa`, `esposo`, `marido`, `senora` → partner; `mascota`, `mascotas`, `perro`,
  `perra`, `perrito`, `perrita`, `gato`, `gata`, `gatito`, `gatita` → pets. The question shape:
  `como se llama mi X`, `como se llaman mis X`, `quien es mi X`, `quienes son mis X`.
- **D-10 Calibration without a script.** Each recall turn logs `best_distance` (a number rounded to
  three decimals, never a text) and its route. Pipec asks his real questions in Task 12; the
  threshold is set from those numbers and written in the record.
- **D-11 The opt-in text log** shows a fixed marker instead of a recall answer or a relatives
  answer, like the profile summary (`spoken_log_text`).

**Goal.** On a recall question, the robot searches the owner's diary and own verified words —
filtered by owner, sensitivity `normal` and date before any ranking — and answers only from what it
found, or with «No me acuerdo de eso.»; «¿cómo se llaman mis papás?» and the other `normal`
relatives of the alta are read by a fixed template. A story never becomes a refusal, a visitor
learns nothing, and with `RECALL_ENABLED=false` every turn is byte for byte today's.

**Architecture.** Migration 014 adds `recall_units` with an FTS5 index and a `vec0` index kept by
triggers and deleted in cascade with the record. The capture writes a `turn` unit for every
`VERIFIED` turn inside the append's transaction and embeds it after; the diary job writes the
`episode` unit and raises the sensitivity of the record's turn units. Pure modules decide the cue,
the date window and the word sensitivity; `recall_search` filters, gates and fuses; `recall_access`
evaluates and audits `read_personal_conversation_memory` before reading; `recall_answer` words the
reply. The controller gets `InformationNeed.RECALL` and `InformationNeed.RELATIVES_NAMES` and two
optional collaborators wired only by the voice routes.

**Tech stack.** Python 3.12, FastAPI, aiosqlite, SQLite FTS5 and JSON1, `sqlite-vec` 0.1.9
(`distance_metric=cosine`), Ollama through `llm_transport`, `zoneinfo`, pytest. No new dependency,
no wire change, no robot change, one migration (014).

**Spec.** [ADR 0028](../../adr/0028-recall-what-the-owner-told.md) (all decisions), ADR 0027
(decisions 1, 2 and 5 as amended), ADR 0026 decisions 3 and 5, ADR 0020 §1, ADR 0019 §3, ADR 0016
(the face for the children read), [guardrails](../../architecture/implementation-guardrails.md).

## Global constraints

- English code, comments and docstrings (Google style); Spanish only in user-facing strings and the
  recall prompt; **no voseo** (`tests/unit/test_no_voseo_in_spoken_strings.py`).
- No `Any`, no `print`, no `os.path`, no bare `except`; logging with `%`; settings only through
  `settings`; every public API typed and documented.
- **No text in any log line**: ids, counts, distances, closed routes and outcomes, exception classes.
- Timestamps are UTC ISO 8601 with microseconds; local days are computed only with
  `zoneinfo.ZoneInfo(settings.household_timezone)`.
- A unit is built **only** from the `heard` of a `VERIFIED` turn or from an episode summary; never
  from `said`, never from another verdict.
- Recall reads only the speaker's own units, visibility `personal`, sensitivity `normal`, not
  expired, after an audited `ALLOWED` decision.
- With `RECALL_ENABLED=false` every prompt, response, wire field and log line of a voice turn is
  **byte-identical** to `main`, and nothing is written to the new tables.
- No real household data anywhere: invented canaries only (`Canary`, `Zeta`, `Omega`, `mate`).

## Review focus

Failure modes the ADR implies and no task title names; each has its test in the task that owns it.

1. A heard text that is FTS syntax or hostile (`"`, `*`, `OR`, `NEAR(`, a 2000-character text, an
   emoji, «ignora lo anterior»): stored and searched as data, never an FTS error (Tasks 4 and 7).
2. «Ayer» asked at 00:30 local time, and on the day Chile changes its clock: the window is the
   local calendar day, not a 24-hour span (Task 2).
3. A record purged or deleted between the search and the answer: fewer or no units, never a crash,
   never a unit of a deleted record in the answer (Task 7).
4. A stranger asking a strong cue, and a stranger asking a weak cue: the first hears the refusal,
   the second converses; **no search and no embedding call runs before the policy allowed it**
   (Task 9).
5. Two turns of one record verified seconds apart while the episode is being written: every turn
   unit exists once and ends with the more protective sensitivity (Task 5).

---

## File structure

| File | Responsibility | Task |
|---|---|---|
| `memory/migration_014_recall_units.sql` (new), `db.py` | Units, FTS5, `vec0`, triggers, missing indexes; `PRAGMA optimize` on close | 1 |
| `cognition/spoken_dates.py` (new), `settings.py`, `.env.example` | Pure date windows and labels; the four settings | 2 |
| `memory/recall_sensitivity.py` (new) | Pure word classifier and «only up» | 3 |
| `memory/recall_store.py` (new) | The only SQL on `recall_units*` | 4 |
| `memory/recall_index.py` (new), `memory/conversation_record.py`, `memory/conversation_capture.py`, `memory/conversation_episodes.py`, `memory/conversation_jobs.py`, `main.py`, `routers/transcribe.py` | Writing units, embedding, backfill, warm-up | 5 |
| `cognition/recall_cues.py` (new), `cognition/intent_resolution.py`, `cognition/response_plan.py` | Cue grammar, the two needs, the route corpus | 6 |
| `memory/recall_search.py` (new) | Filters, gate, RRF, caps, date-only | 7 |
| `memory/recall_access.py` (new), `memory/recall_answer.py` (new) | Policy and audit before read; the worded answer | 8 |
| `cognition/controller.py`, `routers/transcribe.py`, `cognition/response_plan.py` | The recall branch and its wiring | 9 |
| `cognition/household_tools.py`, `cognition/controller.py`, `routers/transcribe.py` | The relatives reader | 10 |
| `scripts/longitudinal_eval_driver.py`, `tests/unit/test_architecture_guards.py` | Benchmark reason, guards | 11 |
| `docs/…` | Truth, acceptance, close | 12 |

---

### Task 0: Re-audit and baseline

**Files:** none changed.

- [ ] **Step 1:** `git checkout main && git pull`, then create `feat/0078-recall`.
- [ ] **Step 2:** Verify, and **stop and report** if any is false:
  - `db._MIGRATIONS` ends at `(13, "migration_013_conversation_record.sql")`, and `open_db()` loads
    `sqlite-vec` **before** `run_migrations` (migration 014 creates a `vec0` table).
  - `conversation_record.append_turn(turn, *, owner_entity_id, now) -> int` owns its
    `db.transaction()`; `conversation_capture.capture_turn` calls it once per turn after
    `turn_verdict`; `conversation_episodes.write_episode` inserts the episode and sets `DONE` in one
    transaction.
  - `routers/transcribe._turn_recorder` schedules `capture_turn` as a background task, and both
    voice routes hold `resources.http_client`.
  - Short-term continuity is written only by `text_turn` (`continuity.record_pair`), so a plan the
    controller returns never enters it.
  - `intent_resolution._RULES` starts `_own_children_list_rule`, `_own_children_count_rule`,
    `_protected_household_rule`; `_profile_summary_rule` matches only a message equal to or ending
    in its pattern; today «¿cómo se llaman mis papás?» and «¿qué hice el sábado con mi hijo?»
    resolve to `PROTECTED_HOUSEHOLD` and «¿qué te conté ayer?» to `GENERIC_CONVERSATION` (check
    with a throwaway script in the scratchpad: the shell mangles accents).
  - The canonical writer stores `has_parent`, `has_sibling`, `has_grandparent`, `has_grandchild`
    as `personal` / `normal` from the owner, and `partner_of` / `pet_of` as `household` with the
    registry's sensitivity (`canonical_writer._classify_relation`); `HouseholdKnowledgeTools`
    authorizes through `_authorize_tool` with `EXECUTE_HOUSEHOLD_TOOL`, and that action **allows the
    face-identified owner at `basic`** for `personal`/`normal` and for `household`/`normal`
    (write a throwaway policy check). If it does not, stop: the relatives reader needs a policy
    change the ADR did not decide.
  - `ollama_chat(client, messages, *, model, format_schema=None, options=None, timeout=None) -> str`
    and `ollama_embed(client, text, *, model, timeout=None) -> list[float]` exist;
    `claim_guard.neutralize_memory_claims(text) -> str` exists; `response_plan.spoken_log_text`
    returns a marker for the profile summary.
- [ ] **Step 3:** Run the baseline and write the count in the PR:
  `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and not eval" -q -n auto`.

---

### Task 1: Migration 014

**Files:** Create `server/src/server/memory/migration_014_recall_units.sql`,
`tests/integration/test_recall_schema.py`; modify `db.py` (`(14, "migration_014_recall_units.sql")`;
`close_db()` runs `PRAGMA optimize` before closing, errors logged by class and swallowed).

The migration, atomic like 011 to 013:

```sql
BEGIN;
CREATE TABLE recall_units (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_entity_id   INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    source_record_id  INTEGER NOT NULL REFERENCES conversation_records(id) ON DELETE CASCADE,
    episode_id        INTEGER REFERENCES conversation_episodes(id) ON DELETE CASCADE,
    kind              TEXT NOT NULL CHECK (kind IN ('turn', 'episode')),
    body              TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 2000),
    said_at           TEXT NOT NULL,
    visibility        TEXT NOT NULL CHECK (visibility = 'personal'),
    sensitivity       TEXT NOT NULL
                      CHECK (sensitivity IN ('normal', 'private', 'medical', 'location', 'security')),
    correlation_id    TEXT,
    embedding_model   TEXT,
    CHECK ((kind = 'episode') = (episode_id IS NOT NULL)),
    CHECK ((kind = 'turn') = (correlation_id IS NOT NULL))
);
CREATE INDEX recall_units_owner_time_idx ON recall_units (owner_entity_id, said_at);
CREATE INDEX recall_units_record_idx ON recall_units (source_record_id);
CREATE INDEX recall_units_episode_idx ON recall_units (episode_id);
CREATE INDEX recall_units_unembedded_idx ON recall_units (id) WHERE embedding_model IS NULL;
CREATE VIRTUAL TABLE recall_units_fts USING fts5(
    body, content='recall_units', content_rowid='id', tokenize='unicode61 remove_diacritics 2'
);
CREATE VIRTUAL TABLE recall_units_vec USING vec0(
    owner_entity_id integer partition key, sensitivity text,
    embedding float[768] distance_metric=cosine
);
CREATE TRIGGER recall_units_ai AFTER INSERT ON recall_units BEGIN
    INSERT INTO recall_units_fts (rowid, body) VALUES (new.id, new.body);
END;
CREATE TRIGGER recall_units_ad AFTER DELETE ON recall_units BEGIN
    INSERT INTO recall_units_fts (recall_units_fts, rowid, body) VALUES ('delete', old.id, old.body);
    DELETE FROM recall_units_vec WHERE rowid = old.id;
END;
CREATE TRIGGER recall_units_au_sensitivity AFTER UPDATE OF sensitivity ON recall_units BEGIN
    UPDATE recall_units_vec SET sensitivity = new.sensitivity WHERE rowid = new.id;
END;
CREATE INDEX conversation_records_owner_idx ON conversation_records (owner_entity_id);
CREATE INDEX conversation_records_previous_idx ON conversation_records (previous_id);
CREATE INDEX conversation_episodes_owner_idx ON conversation_episodes (owner_entity_id);
PRAGMA user_version = 14;
COMMIT;
```

- [ ] **Step 1: Write the failing tests** in `test_recall_schema.py` (a temporary database through
  the existing fixtures): `test_migration_014_sets_user_version_14`;
  `test_deleting_a_record_deletes_its_units_fts_rows_and_vectors` (insert a record, a unit and its
  vector; delete the record; zero rows in all three); `test_raising_sensitivity_moves_the_vector_out_of_a_normal_search`;
  `test_fts_finds_a_word_without_its_accent` (stored «papá», searched `papa`);
  `test_vector_distance_is_cosine` (two unit vectors at 90° give distance 1.0 ± 0.001);
  `test_a_turn_unit_needs_a_correlation_id_and_no_episode` and its episode twin (CHECK fails).
- [ ] **Step 2:** Run → FAIL (no table). **Step 3:** add the migration and the `db.py` lines.
- [ ] **Step 4:** Run → PASS; also `tests/integration/test_conversation_schema.py` still passes.
- [ ] **Step 5:** commit `feat: migration 014, the recall units and their indexes (plan 0078)`.

---

### Task 2: Settings and spoken dates

**Files:** Create `server/src/server/cognition/spoken_dates.py`, `tests/unit/test_spoken_dates.py`;
modify `settings.py`, `.env.example`, `tests/conftest.py` (pin `recall_enabled=False`).

**Interfaces — produces:**
- `settings.recall_enabled: bool = False`; `settings.household_timezone: str = "America/Santiago"`
  (validated by `zoneinfo.ZoneInfo` at construction); `settings.recall_max_distance: float =
  Field(default=0.30, gt=0.0, lt=2.0)`; `settings.embedding_model` default becomes
  `"granite-embedding:278m"`.
- `@dataclass(frozen=True) class DayWindow: start: date; end: date` (inclusive local days).
- `parse_spoken_window(normalized: str, today: date) -> DayWindow | None` — D-7's spoken forms
  («hoy», «ayer», «anteayer», a weekday = its most recent past occurrence, today excluded, «la
  semana pasada» = the seven days before the current week's Monday, «el mes pasado», «el 3 de
  marzo» = the most recent past 3 March).
- `window_utc_bounds(window: DayWindow, tz: ZoneInfo) -> tuple[str, str]` — half-open
  `[start 00:00 local, end+1 00:00 local)` as UTC ISO strings with microseconds.
- `date_label(said_at: datetime, *, today: date, tz: ZoneInfo) -> str` — D-7.
- `strip_window_words(normalized: str) -> str` — the message without the words that made the window.

- [ ] **Step 1: Write the failing tests:** `test_ayer_at_half_past_midnight_is_the_previous_local_day`;
  `test_the_window_on_the_day_chile_changes_its_clock_spans_the_whole_local_day` (pick the 2026
  dates from `zoneinfo` in the test, never hard-code an offset);
  `test_el_martes_on_a_tuesday_is_last_week`; `test_la_semana_pasada_is_monday_to_sunday`;
  `test_el_3_de_marzo_in_january_is_last_year`; `test_an_unknown_date_is_no_window`
  («el día del cumple de la Zeta» → `None`); `test_el_verano_de_2015_is_no_window`;
  `test_labels` (hoy, ayer, anteayer, `el jueves`, `el 3 de marzo`, `el 3 de marzo de 2025`);
  `test_the_timezone_setting_rejects_an_unknown_zone`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement; add the four settings with comments and the
  four lines of `.env.example` (`RECALL_ENABLED=false`, `HOUSEHOLD_TIMEZONE=America/Santiago`,
  `RECALL_MAX_DISTANCE=0.30`, `EMBEDDING_MODEL=granite-embedding:278m`).
- [ ] **Step 4:** Run → PASS; `test_no_voseo_in_spoken_strings.py` passes.
- [ ] **Step 5:** commit `feat: spoken date windows and the recall settings (plan 0078)`.

---

### Task 3: The word sensitivity of a turn

**Files:** Create `server/src/server/memory/recall_sensitivity.py`,
`tests/unit/test_recall_sensitivity.py`.

**Interfaces — produces:** `type RecallSensitivity = Literal["normal", "private", "medical",
"location", "security"]` (the same literal as `conversation_summary.EpisodeSensitivity`, imported
from there); `classify_turn_text(text: str) -> RecallSensitivity` (D-5, on `normalize_spanish`);
`most_protective(a: RecallSensitivity, b: RecallSensitivity) -> RecallSensitivity` with the order
`security` > `medical` > `location` > `private` > `normal`.

- [ ] **Step 1: Write the failing tests:** one case per D-5 category; `test_two_categories_keep_the_most_protective`;
  `test_a_story_about_sushi_and_the_children_is_normal`; `test_a_word_inside_another_word_does_not_match`
  («pinto» is not `pin`, «claveles» is not `clave`); `test_most_protective_never_goes_down`
  (all 25 pairs).
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** commit `feat: classify the sensitivity of a recalled turn by its words (plan 0078)`.

---

### Task 4: The recall store

**Files:** Create `server/src/server/memory/recall_store.py`, `tests/integration/test_recall_store.py`.

**Interfaces — produces** (the only SQL on `recall_units*`; times are UTC ISO strings):
- `@dataclass(frozen=True) class RecallUnit: id: int; record_id: int; kind: Literal["turn",
  "episode"]; body: str = field(repr=False); said_at: datetime`
- `async def insert_turn_unit(conn: aiosqlite.Connection, *, record_id: int, owner_entity_id: int,
  turn: RecordedTurn) -> int` — body is `turn.heard`, sensitivity `classify_turn_text(turn.heard)`;
  raises `ValueError` if `turn.voice is not TurnVerdict.VERIFIED`.
- `async def insert_episode_unit(conn, *, record_id: int, episode_id: int, owner_entity_id: int,
  summary: str, sensitivity: RecallSensitivity, said_at: str) -> int`
- `async def raise_record_sensitivity(conn, *, record_id: int, sensitivity: RecallSensitivity) -> int`
  — sets each `turn` unit of the record to `most_protective(own, sensitivity)`; returns rows changed.
- `async def store_vector(unit_id: int, vector: list[float], *, model: str) -> bool` — inserts into
  `recall_units_vec` with the unit's owner and **current** sensitivity and sets `embedding_model`,
  in one transaction; `False` when the unit is gone.
- `async def units_without_vector(limit: int) -> list[tuple[int, str]]`
- `async def lexical_hits(*, owner_entity_id: int, terms: Sequence[str], since: str | None,
  until: str | None, now: str, limit: int) -> list[int]` — FTS5 `MATCH` of the quoted terms joined
  with `OR`, joined to `recall_units` and `conversation_records` for owner, `sensitivity = 'normal'`,
  window and `(expires_at IS NULL OR expires_at > now)`, ordered by `bm25`.
- `async def vector_hits(*, owner_entity_id: int, vector: list[float], since: str | None,
  until: str | None, now: str, k: int) -> list[tuple[int, float]]` — `vec0` KNN with
  `owner_entity_id = ?` and `sensitivity = 'normal'` inside the query, then the same window and
  expiry filters; returns `(unit_id, distance)`.
- `async def units_by_id(ids: Sequence[int]) -> list[RecallUnit]`
- `async def recent_units(*, owner_entity_id: int, since: str, until: str, now: str, limit: int)
  -> list[RecallUnit]` — episodes in the window newest first, then turn units if there are no
  episodes; `normal` only.

- [ ] **Step 1: Write the failing tests:** `test_a_turn_unit_holds_only_the_heard_text`;
  `test_a_not_verified_turn_is_refused`; `test_raising_never_lowers`;
  `test_lexical_hits_ignore_another_owner_a_sensitive_unit_and_an_expired_record`;
  `test_lexical_hits_survive_fts_syntax_in_the_terms` (terms `"`, `*`, `OR`, `NEAR(`, a 2000-character
  word); `test_vector_hits_filter_owner_and_sensitivity_inside_the_query`;
  `test_store_vector_takes_the_current_sensitivity`; `test_store_vector_on_a_deleted_unit_is_false`;
  `test_recent_units_prefer_episodes`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** commit `feat: the recall store, the only SQL on the recall units (plan 0078)`.

---

### Task 5: Writing and embedding the units

**Files:** Create `server/src/server/memory/recall_index.py`, `tests/unit/test_recall_index.py`;
modify `memory/conversation_record.py`, `memory/conversation_capture.py`,
`memory/conversation_episodes.py`, `memory/conversation_jobs.py`, `main.py`,
`routers/transcribe.py`, and their tests.

**Interfaces:**
- `conversation_record.append_turn(turn, *, owner_entity_id, now, index: TurnIndexer | None = None)
  -> int`, `type TurnIndexer = Callable[[aiosqlite.Connection, int, RecordedTurn], Awaitable[int]]`,
  called inside the append's transaction after the update, with the record id.
- `recall_index.embed_unit(client: httpx.AsyncClient, unit_id: int, body: str) -> bool` — one
  `ollama_embed` with `settings.embedding_model`, then `store_vector`; never raises (class logged).
- `recall_index.backfill_vectors(client: httpx.AsyncClient, *, limit: int = 5) -> int`
- `recall_index.warm_up(client: httpx.AsyncClient) -> None` — one embedding of a fixed word.
- `capture_turn(..., client: httpx.AsyncClient | None = None)`: with `settings.recall_enabled` and
  a `VERIFIED` verdict it passes `recall_store.insert_turn_unit` as `index`, then calls `embed_unit`
  with the returned id; `_turn_recorder` passes `resources.http_client`.
- `write_episode` inserts the `episode` unit and calls `raise_record_sensitivity` **in the same
  transaction** as the episode, only with `settings.recall_enabled`.
- `conversation_jobs.run_once` calls `backfill_vectors` after the episode step, only while no
  conversation is open and with `settings.recall_enabled`.
- `main.lifespan` warms the embedding model with `_warm_up("Embedding model", …)` when
  `settings.memory_enabled and settings.recall_enabled`.

- [ ] **Step 1: Write the failing tests:** `test_a_verified_turn_gets_a_unit_in_the_same_transaction`
  (a failing indexer rolls back the append); `test_no_unit_without_recall_enabled`;
  `test_no_unit_for_not_verified_not_owner_or_not_checked` (a property test over the four verdicts);
  `test_the_robot_reply_is_never_a_unit`; `test_an_unreachable_embedding_model_leaves_a_lexical_unit`;
  `test_the_episode_raises_the_sensitivity_of_its_turns`;
  `test_two_turns_verified_while_the_episode_is_written_end_protective` (Review focus 5);
  `test_backfill_waits_for_an_open_conversation`; `test_warm_up_failure_only_logs`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS; the existing capture,
  record, episode and job tests still pass.
- [ ] **Step 5:** commit `feat: index the owner's verified words and the diary (plan 0078)`.

---

### Task 6: Recall cues and the route corpus

**Files:** Create `server/src/server/cognition/recall_cues.py`, `tests/unit/test_recall_cues.py`,
`tests/fixtures/recall_routes.yaml`; modify `cognition/intent_resolution.py`,
`cognition/response_plan.py`, `tests/unit/test_intent_resolution.py`.

**Interfaces — produces:**
- `class CueStrength(StrEnum): STRONG = "strong"; WEAK = "weak"`
- `@dataclass(frozen=True) class RecallCue: strength: CueStrength; query: str; window:
  DayWindow | None` — `query` is the folded message without fillers, cue words and window words.
- `classify_recall_cue(message: str, *, today: date) -> RecallCue | None` (D-1); `None` also when
  neither a window nor a content word remains.
- `InformationNeed.RECALL = "recall"`, `InformationNeed.RELATIVES_NAMES = "relatives_names"`;
  `intent_resolution._recall_rule` (rule id `recall.strong.v1` / `recall.weak.v1`) and
  `_relatives_rule` (`relatives.names.v1`, D-9 shapes) placed per D-2. The rule needs no date to
  classify: it calls `classify_recall_cue` with `date.today()` only to test that a query or a window
  remains.
- `resolve_information_need(message: str, *, recall: bool = False) -> IntentResolution` — the two
  new rules run **only with `recall=True`**, so every existing caller resolves exactly as today
  («¿qué hice el sábado con mi hijo?» stays `PROTECTED_HOUSEHOLD` with the switch off). The
  controller's `IntentResolver` type becomes `Callable[..., IntentResolution]` with that keyword.
- `relation_of(message: str) -> str | None` in `recall_cues.py` — the D-9 predicate of a relatives
  question, `None` otherwise.

`recall_routes.yaml` holds, per line, a phrase and its expected `need`, at least: «¿Qué te conté
ayer?» → `recall`; «¿Te acuerdas qué te conté del viaje?» → `recall`; «¿Qué hice el sábado con mi
hijo?» → `recall`; «¿Te acuerdas de Mozart?» → `recall` (weak); «¿Te acuerdas?» →
`generic_conversation`; «Hoy vamos a cocinar sushi porque les gusta a mis hijos» →
`generic_conversation`; «Me acuerdo que de chico íbamos al cerro» → `generic_conversation`;
«No me acuerdo dónde dejé las llaves» → `generic_conversation`; «¿Qué sabes de mí?» →
`profile_summary`; «¿Qué te conté?» → `profile_summary`; «¿Cómo se llaman mis papás?» →
`relatives_names`; «¿Cómo se llama mi perro?» → `relatives_names`; «¿Cómo se llaman mis hijos?» →
`own_children_list`; «¿Te acuerdas qué comen mis hijos?» → `protected_household`; «¿Cuándo nació mi
hijo?» → `protected_household`. **Before the task closes, Pipec adds his own recall phrases**
(decision 5) with the route he expects; those lines carry no household value.

- [ ] **Step 1: Write the failing tests:** `test_every_corpus_phrase_takes_its_route` (reads the
  YAML, with `recall=True`); `test_without_recall_every_corpus_phrase_resolves_as_on_main`
  (the same phrases with `recall=False` give today's needs: the recall and relatives lines fall
  back to `generic_conversation` or `protected_household` as Task 0 recorded);
  `test_a_strong_phrase_wins_over_a_weak_one`; `test_a_statement_is_never_a_cue`;
  `test_without_a_question_mark_an_opening_interrogative_still_counts`
  («que te conte ayer», as Whisper writes it); `test_the_query_drops_cue_and_window_words`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS; the whole
  `test_intent_resolution.py` and `test_household_request.py` still pass (the 0077 corpus unchanged).
- [ ] **Step 5:** commit `feat: recall cues and the relatives question in the intent rules (plan 0078)`.

---

### Task 7: The search

**Files:** Create `server/src/server/memory/recall_search.py`, `tests/unit/test_recall_fusion.py`,
`tests/integration/test_recall_search.py`.

**Interfaces — produces:**
- `@dataclass(frozen=True) class RecallHit: unit: RecallUnit; distance: float | None`
- `fuse(lexical: Sequence[int], vector: Sequence[tuple[int, float]], *, max_distance: float)
  -> list[int]` — pure: a vector hit qualifies only under `max_distance`, every lexical hit
  qualifies; RRF with `RRF_K`; ties by unit id descending.
- `async def search_recall(owner_entity_id: int, cue: RecallCue, *, client: httpx.AsyncClient,
  now: datetime) -> RecallSearch`, `RecallSearch(hits: tuple[RecallHit, ...], best_distance:
  float | None, lexical_only: bool)` — terms from `cue.query` minus a stop-word list (articles,
  prepositions, pronouns, `que`, `algo`, `eso`), at most `RECALL_MAX_TERMS`; a window gives
  `since`/`until`; with no terms and a window it returns `recent_units`; an embedding failure means
  `lexical_only=True`; caps `RECALL_MAX_RESULTS` and `RECALL_MAX_PER_RECORD`; units whose record
  disappeared between the steps are dropped.

- [ ] **Step 1: Write the failing tests:** `test_a_far_vector_hit_does_not_qualify`;
  `test_rrf_orders_a_unit_found_twice_first`; `test_zero_qualifying_is_an_empty_result`;
  `test_at_most_three_and_two_per_record`; `test_date_only_returns_recent_units`;
  `test_an_embedding_failure_searches_by_words`; `test_a_record_deleted_mid_search_drops_its_units`
  (Review focus 3); `test_another_owner_is_never_returned`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** commit `feat: search the recall units with a gate and RRF (plan 0078)`.

---

### Task 8: Access and the worded answer

**Files:** Create `server/src/server/memory/recall_access.py`, `server/src/server/memory/recall_answer.py`,
`tests/unit/test_recall_access.py`, `tests/unit/test_recall_answer.py`,
`tests/fixtures/recall_prompt_golden.json`.

**Interfaces — produces:**
- `response_plan.RecallReply` (frozen dataclass): `text: str | None`, `denied: bool = False`,
  `found: bool = False`.
- `async def recall_reply(actor: ActivePersonContext, cue: RecallCue, *, correlation_id: UUID,
  now: datetime, client: httpx.AsyncClient, search=search_recall, answer=word_recall,
  policy=evaluate_authorization, audit=record_authorization_decision) -> RecallReply` — the
  `profile_card_access.read_card` order: the same pre-check, made public as
  `profile_card_access.may_read_own_memory(actor) -> bool` (renamed from `_may_be_asked`, one
  definition), the
  `READ_PERSONAL_CONVERSATION_MEMORY` request for `personal`/`normal`, the audit **before** the
  search, then the search and the answer. Denied → `denied=True`; an audit or search failure →
  `text=NO_MEMORY`; no hits → `text=None, found=False`; hits → `found=True`. Logs the route, the hit
  count and `best_distance` (D-10).
- `async def word_recall(client: httpx.AsyncClient, question: str, hits: Sequence[RecallHit], *,
  today: date, tz: ZoneInfo) -> str` — D-8; on `LLMError`/`httpx.HTTPError`/timeout the D-6
  template with the first hit; an answer equal to `NO_MEMORY` after stripping is returned as
  `NO_MEMORY`.
- `NO_MEMORY`, `NOT_REGISTERED` constants in `recall_answer.py`.

- [ ] **Step 1: Write the failing tests:** `test_the_audit_row_is_written_before_any_search`;
  `test_a_denied_actor_triggers_no_search_and_no_embedding` (Review focus 4: a spy on `search`);
  `test_a_token_speaker_is_not_asked`; `test_the_prompt_matches_its_golden`;
  `test_the_prompt_carries_only_the_found_units`; `test_a_model_failure_uses_the_template`;
  `test_the_model_saying_it_does_not_remember_gives_the_fixed_phrase`;
  `test_a_claim_to_have_saved_is_neutralized`; `test_no_log_line_carries_a_body` (caplog with a
  canary body).
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** commit `feat: authorize, audit and word a recall answer (plan 0078)`.

---

### Task 9: The recall branch and its wiring

**Files:** Modify `cognition/controller.py`, `cognition/response_plan.py`, `routers/transcribe.py`,
`tests/unit/test_controller*.py` (the module the profile-summary branch is tested in),
`tests/api/` (the voice-route tests that pin byte identity).

**Interfaces:**
- `type RecallAnswerer = Callable[[ActivePersonContext, RecallCue, CognitiveEvent[TextTurnPayload]],
  Awaitable[RecallReply]]`; `CognitiveController(..., recall_answerer: RecallAnswerer | None = None)`.
- `_resolved_need` calls `self._intent_resolver(message, recall=self._recall_answerer is not None)`,
  so without the collaborator the new needs never appear.
- `_recall_plan(event) -> ResponsePlan | None`: no answerer → `None`; the actor through
  `self._observed_person_resolver` (never spends a grant); a strong cue from anyone not identified
  → `_unknown_plan(RECALL, _PROFILE_SUMMARY_UNKNOWN_RESPONSE)`; a weak cue from anyone not
  identified → `None`; `denied` → the same refusal (strong) or `None` (weak); `found` → a
  `DETERMINISTIC` plan with the text; no hits → `NO_MEMORY` (strong) or `None` (weak).
- `routers/transcribe._recall_answerer(client)` returns `None` unless `settings.memory_enabled and
  settings.recall_enabled`; both voice routes pass it with `resources.http_client`.
- `spoken_log_text` returns `RECALL_LOGGED_TEXT = "[recuerdo leído]"` for a `RECALL` plan with
  `found` (D-11).

- [ ] **Step 1: Write the failing tests:** `test_a_strong_cue_with_hits_answers_from_them`;
  `test_a_strong_cue_without_hits_says_it_does_not_remember`;
  `test_a_weak_cue_without_hits_falls_through_to_conversation`;
  `test_a_stranger_strong_cue_hears_the_refusal_and_a_weak_cue_converses` (Review focus 4);
  `test_recall_never_spends_a_grant`; `test_the_recall_answer_is_not_written_to_continuity`;
  `test_with_recall_disabled_every_route_is_byte_identical` (the classic and the streaming route,
  a recall phrase and a generic phrase, compared with the switch off against `main`'s behaviour);
  `test_the_opt_in_log_shows_the_marker`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS; the whole unit, API and
  integration suites pass.
- [ ] **Step 5:** commit `feat: answer a recall question in the voice routes (plan 0078)`.

---

### Task 10: The relatives reader

**Files:** Modify `cognition/household_tools.py`, `cognition/controller.py`, `routers/transcribe.py`,
`cognition/response_plan.py`, and their tests; create `tests/unit/test_relatives_reader.py`.

**Interfaces:**
- `HouseholdToolName.GET_RELATIVES = "get_relatives"`;
  `HouseholdKnowledgeTools.get_relatives(*, owner_entity_id: int, predicate: str, actor,
  consent, correlation_id, requested_at) -> HouseholdToolResult` — authorizes through
  `_authorize_tool` with the predicate's stored visibility and sensitivity (`personal` for
  relatives, `household` for `partner_of`/`pet_of`), reads with
  `relational_v4.get_active_entity_relations` (relatives: `source_entity_id = owner`; partner and
  pets: `target_entity_id = owner`), and returns the names (`get_person_label` / the entity name)
  sorted.
- `_relatives_plan(event)`: inert without `household_tools` (the protected route answers as today);
  not identified → the D-6 refusal; nothing stored → `NOT_REGISTERED`; else the D-9 template, a
  `DETERMINISTIC` plan; `spoken_log_text` returns `RELATIVES_LOGGED_TEXT = "[parientes leídos]"`.
- Wired only with `settings.memory_enabled and settings.recall_enabled` (the same `recall=True`
  flag of Task 9 enables its rule); otherwise the question keeps `PROTECTED_HOUSEHOLD` and its
  answer of today.

- [ ] **Step 1: Write the failing tests:** `test_parents_are_read_together` («Tus papás se llaman
  Omega y Zeta.»); `test_one_parent_uses_the_singular`; `test_a_pet_and_a_partner_are_read`;
  `test_nothing_stored_is_not_registered`; `test_a_stranger_hears_the_refusal`;
  `test_a_revoked_relation_is_not_read`; `test_with_recall_disabled_the_question_is_protected_as_today`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** commit `feat: read the owner's relatives from the alta by voice (plan 0078)`.

---

### Task 11: Benchmark reason, guards and whole-project checks

**Files:** Modify `scripts/longitudinal_eval_driver.py` (the `RECALL` reason: «recall exists
behind a voice-verified capture and a restart; the harness has neither seam without imitating them
(ADR 0028); CM-7 connects them»), its test, `tests/unit/test_architecture_guards.py`.

- [ ] **Step 1: Write the failing guards:** `test_the_generic_prompt_still_reads_no_household_store`
  (the existing guard, extended: no `recall_*` import in `characters/`, `llm*.py`, `streaming*.py`,
  `text_turn.py`); `test_only_recall_store_touches_the_recall_tables` (no `recall_units` string
  outside `recall_store.py`, the migration and tests); `test_the_record_is_still_read_by_no_route`
  (the 0076 guard keeps passing: units, not records, are read).
- [ ] **Step 2:** Run → FAIL where new. **Step 3:** implement. **Step 4:** Run →
  `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and not eval" -q -n auto`,
  `uv run pyright`, `uv run mypy server/src robot/src`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run ruff check scripts/*.py`, `just gate` — all pass. Write
  the test count in the PR.
- [ ] **Step 5:** commit `test: guard the recall path and update the benchmark reason (plan 0078)`.

---

### Task 12: Truth, calibration, acceptance and close

**Files:** `docs/architecture/current-state.md` and its Archify diagram (validate → deliver), the
operator manual (the four settings, the recall phrases, the log fields), `docs/evals/0078-recall-acceptance.md`
(new, outcomes only), ADR 0028 (`Accepted`), ADR 0027 and ADR 0026 (amendment notes), the plan
board, the roadmap row 9, the memory map.

- [ ] **Step 1: Calibration.** Pipec turns on `RECALL_ENABLED` and keeps the record on for some days
  (decision 5), then asks his real questions; the agent reads only the logged routes, hit counts
  and `best_distance` values he pastes, and proposes `RECALL_MAX_DISTANCE` from them. The value and
  the counts go in the record; no phrase or answer does.
- [ ] **Step 2: Hardware acceptance by Pipec** (classic and streaming), outcomes only: (1) a strong
  cue that finds; (2) a strong cue that does not → «No me acuerdo de eso.»; (3) «¿Te acuerdas de
  Mozart?» converses; (4) the sushi story with «mis hijos» converses; (5) «¿Qué te conté ayer?»;
  (6) without the owner's face → the refusal; (7) «¿Cómo se llaman mis papás?»; (8) a health
  sentence said earlier is not recalled; (9) Ollama's embedding model cold or absent → still found
  by words.
- [ ] **Step 3:** Update the documents above; ADR 0028 → `Accepted`; move the plan to `completed/`.
- [ ] **Step 4:** commit `docs: close plan 0078, recall accepted on hardware`, push, open the PR
  with Pipec's OK.

---

## Non-goals

Reading sensitive memories, the liveness decision and «¿estás con alguien?» (block B); correcting
and forgetting by voice (block C, the cascade is ready); turning a spoken third-party fact into a
structured one; telling the mother from the father in the alta; «¿y qué más?» without the cue; a
reranker; documents; unifying the older timestamp format; recall on `/chat` or `/vision/respond`;
any change to the generic prompt, the wire, the robot or the 0077 household rule.

## Self-review (2026-11-03)

- **Spec coverage.** ADR 0028 decisions 1 and 2 → Tasks 1, 4, 5; 3 → Tasks 3, 5; 4 → Task 6;
  5 → Tasks 8, 9; 6 → Tasks 4, 7; 7 → Task 2; 8 → Task 8; 9 → Task 10; 10 → Tasks 1, 2, 5;
  *Test consequences* → Tasks 6 to 12; the benchmark wording → Task 11.
- **Type consistency.** `RecallSensitivity`, `RecallUnit`, `RecallCue`, `DayWindow`, `RecallHit`,
  `RecallSearch`, `RecallReply` are each defined once and named the same in every later task.
- **Size.** Twelve working tasks after Task 0, at the limit the ADR set for one plan; Tasks 1 to 5
  (data) and 6 to 11 (cues, search, answer, reader) can be split into two plans at promotion if
  Pipec prefers.
