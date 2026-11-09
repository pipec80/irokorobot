# 0028 — Recall what the owner told: search the diary on a recall cue, and answer only from what was found

- **Status:** Accepted (2026-11-04), with the amendments of *Amendments at acceptance*, which
  win over the decision text where they differ. Proposed on 2026-11-03; every decision below was
  confirmed by Pipec in the design session of that day (the eleven decisions of the step 2 freeze,
  all option A, with decision 3 changed to option B after the measurement in *Context*, item 6).
  Implemented by [Plan 0078](../plans/completed/0078-cm5b-recall-what-the-owner-told.md); hardware
  acceptance in [docs/evals/0078-recall-acceptance.md](../evals/0078-recall-acceptance.md).
- **Date:** 2026-11-03
- **Builds on:** [ADR 0016](0016-face-and-voice-identity-fusion.md),
  [ADR 0019](0019-personal-memory-capabilities.md),
  [ADR 0020](0020-authorized-actor-in-the-conversation.md),
  [ADR 0026](0026-owner-profile-card-and-the-read-side-of-memory.md),
  [ADR 0027](0027-conversation-record-and-the-diary.md)
- **Amends:** [ADR 0027](0027-conversation-record-and-the-diary.md) decision 5 («no voice path and
  no prompt ever reads a record»): the owner's verified words may be read back through the recall
  units of decision 1, and through nothing else. [ADR 0026](0026-owner-profile-card-and-the-read-side-of-memory.md)
  decision 5: the structured questions about the owner's `normal` relatives are answered here
  (decision 9), not by a later plan. [RAG §26](../architecture/rag-and-memory-retrieval.md#26-decisiones-que-requieren-adr-futuro):
  the embedding model, the lexical search and the fusion method are decided here.
- **Delivers:** row 9 of the roadmap, **CM-5b + R3**, step 2 of the
  [closing path of conversational memory](../roadmap/cognitive-roadmap.md#closing-path-of-conversational-memory)
  («block A, it remembers»).

## Context

The goal is a robot that, after a pause, a day or a restart, answers «¿te acuerdas qué te conté
ayer?», «¿qué hice el sábado con mi hijo?» or «¿cómo se llaman mis papás?» from what it was told,
and says «no me acuerdo» instead of inventing when it does not know. What holds today (verified in
code on `main` at `fb32672`, 2026-11-03):

1. **The diary exists and nothing reads it.** Plan 0076 keeps every spoken exchange in
   `conversation_records` (one JSON array of turns per segment, each turn with its voice verdict)
   and writes one summary per eligible record into `conversation_episodes` (at most
   `CONVERSATION_EPISODE_MAX_CHARS` = 600 characters, with a sensitivity chosen by the model and the
   record's expiry). Only `VERIFIED` turns — the owner's face **and** the owner's voice on that
   clip — feed it (`conversation_types.owner_part`).
2. **The summary loses detail.** Six hundred characters for a long conversation can drop the year
   in «el verano de 2015 fui con mi papá». The record keeps the full text for a year, but ADR 0027
   decision 5 forbids any voice path to read it.
3. **Short-term continuity covers «¿qué te dije recién?»** (ADR 0020: 3000 characters, 180 s of
   silence). Between the end of that window and the diary job (which writes only while nobody is
   talking) there is a gap where a recent sentence is in neither.
4. **The search pieces exist, unassembled.** SQLite 3.49.1 ships FTS5 (`unicode61` with
   `remove_diacritics 2`); `sqlite-vec` 0.1.9 is loaded by `db.open_db()` and its `vec0` tables
   accept a partition key and metadata columns filtered inside the KNN query; `memory/embeddings.py`
   embeds with a cache. The legacy vector index (`vec_memories`) was dropped by migration 013, so
   the diary's index starts empty. Verified on 2026-11-03 on an in-memory database: a foreign-key
   cascade plus `AFTER DELETE` triggers removes a unit's FTS row and its vector, and an
   `AFTER UPDATE` trigger moves its metadata.
5. **The embedding model was measured** ([Plan 0075](../plans/completed/0075-cm4-pre-measurement.md)):
   `nomic-embed-text` separates Spanish at ROC-AUC 0.98; `granite-embedding:278m` reaches 1.00, 768
   dimensions, 185 MB loaded, fully on the laptop GPU, context 512 tokens. On 2026-11-03 it embedded
   a Spanish question in 0.25–0.30 s warm and 6–10 s cold, and stayed resident beside `qwen2.5:3b`.
   A simulated year (12,000 units, 768-d) searched in about 10 ms (FTS5) and 28 ms (vector filtered
   by owner), 44 MB on disk.
6. **The owner's voice almost never verifies on a question.** Plan 0075 measured 0 of 7 questions
   and 1 of 14 short answers verified, against 58 % of turns over 3 s. A recall question is a short
   question. The policy already reads the owner's `normal` personal memory with the face alone
   (`READ_PERSONAL_CONVERSATION_MEMORY`, minimum `basic`, ADR 0019), and ADR 0016 accepts the face
   for the children list.
7. **A keyword list deciding the route of a live turn misfires.** Before Plan 0077, «hoy vamos a
   cocinar sushi porque les gusta a mis hijos» took the protected route. Plan 0077 fixed it by
   routing only the *requests*; this ADR applies the same lesson to recall cues.
8. **The generic prompt reads no household store**
   ([guardrails](../architecture/implementation-guardrails.md), Plan 0077,
   `test_the_generic_prompt_reads_no_household_store`). A diary summary may name the owner's
   children.
9. **The seed load keeps the owner's parents as a list without telling the mother from the father**
   (`seed_file.py`, `has_parent`); relatives are stored `normal` (`seed-data-pool.md`). Today
   «¿cómo se llama mi mamá?» answers «todavía no está conectada» (`controller.py`).
10. **Two timestamp formats coexist** in the database (`YYYY-MM-DD HH:MM:SS` from SQLite defaults
    and ISO 8601 with offset from the code), and «hoy» comes from the machine's clock while
    timestamps are UTC. A homelab running in UTC would cut «ayer» at the wrong midnight.

## Decision

### 1. What can be recalled: recall units, indexed twice, deleted with their conversation

A new table, `recall_units` (migration 014), holds one row per thing that can be recalled:

| Kind | Body | Written |
|---|---|---|
| `turn` | **Only the owner's words** (`heard`) of one `VERIFIED` turn — never the robot's reply, never a turn with any other verdict | Right after the turn is appended to the record, in the background task that already runs after the reply |
| `episode` | The diary summary of a conversation | When the job writes the episode |

Each row carries the owner, the source record (`ON DELETE CASCADE`), the episode for an `episode`
unit (`ON DELETE CASCADE`), the time it was said (ISO 8601 UTC), the sensitivity, the visibility
(`personal`, the only value today; the column exists so the family stage reuses the search) and the
turn's correlation id. Two indexes follow the table through triggers:

- `recall_units_fts`, an external-content FTS5 table with `unicode61 remove_diacritics 2`;
- `recall_units_vec`, a `vec0` table of 768 dimensions with the owner as partition key and the
  sensitivity as a metadata column.

Deleting a record — by expiry, by the owner through `iroko-admin`, or later by CM-6 — deletes its
units, their FTS rows and their vectors. The record stays the source of truth (ADR 0027 decision
1): every unit can be rebuilt from it.

### 2. When a unit becomes searchable

A `turn` unit is written in the same transaction as the append and is searchable **by words at
once**. Its vector is computed in the same background task, after the reply; if the embedding
model is unreachable the unit stays lexical-only and the conversation job fills the vector later,
while nobody is talking. An `episode` unit is written with its episode. A text longer than the
model's window is embedded on its first window; the lexical index keeps the whole text.

### 3. Sensitivity: decided on the way in, and it only goes up

An episode carries the sensitivity the model chose when it summarized. A `turn` unit gets its own
from a **deterministic** word classifier (health, address and whereabouts, codes and keys) that
picks the more protective category when in doubt. When the episode of that record is written, each
of its `turn` units takes the more protective of its own sensitivity and the episode's; it never
goes down. Block A reads only `normal` units (decision 5). A sentence marked too protectively is
simply not recalled now; it is never lost and never changes the conversation.

### 4. Recall cues: only a question searches, and only a question about what the owner said answers «no me acuerdo»

A closed rule in `intent_resolution` (no model) sorts a message into one of three cases:

| Case | Examples | What the robot does |
|---|---|---|
| **Strong cue** — a question about what the owner told or did | «¿qué te conté ayer?», «¿te dije algo del viaje?», «¿qué hice el sábado con mi hijo?» | Searches; with no qualifying result it answers the fixed «No me acuerdo de eso.» |
| **Weak cue** — a question that may be memory or general knowledge | «¿te acuerdas de Mozart?», «¿recuerdas el mundial del 2010?» | Searches; with no qualifying result it **falls through to ordinary conversation**, never to the fixed phrase |
| **Not a question** — a story, a comment, a long sentence | «hoy vamos a cocinar sushi porque les gusta a mis hijos», «me acuerdo que de chico…» | Ordinary conversation, as today; nothing searches or blocks |

The order against the existing routes: a strong cue about something told goes to the diary; a
question about a stored relative's name goes to the structured reader (decision 9); every other
household request keeps the protected route of Plan 0077 unchanged. A wrong route never produces a
false datum: at worst a strong cue says «no me acuerdo», and a weak cue converses. The route of
every turn is logged as a closed value, never with its text.

### 5. Who may recall, and what

The speaker is resolved by the face, as on every generic turn (ADR 0020), and never spends a grant.
Only the owner reads, only their own units, only visibility `personal`, only sensitivity `normal`,
only units not expired, through `READ_PERSONAL_CONVERSATION_MEMORY` with its audit row before the
read. **The face alone is enough, and a recalled unit may name the owner's family**: the voice
cannot be required on a question (*Context*, item 6), the policy already reads `normal` personal
memory at `basic`, and ADR 0016 accepts the face for the children list. A visitor, an unknown face
and two faces get the existing generic denial, the same phrase whatever is stored, so a refusal is
no oracle. The replay risk this accepts (a photograph of the owner) is the one the children list
already carries; its defence is decided with the first sensitive read (*Not decided here*).

### 6. The search: filter first, two rankings, an absolute gate, at most three

1. **Filters inside the query, before any ranking:** owner, visibility, sensitivity, expiry and,
   when the cue has a date, the window (decision 7). Nothing that fails them is compared.
2. **Two searches:** FTS5 on the content words of the question (cue words and stop words removed,
   each token quoted so no input is FTS syntax) and `vec0` KNN on the question's embedding.
3. **An absolute gate:** a unit qualifies only if its vector distance is under `RECALL_MAX_DISTANCE`
   **or** it shares a content word with the question. Zero qualifying units is a valid result.
4. **Reciprocal Rank Fusion** (`k = 60`) orders the qualifying units, without pretending the two
   scores share a scale.
5. **At most three results, at most two from one conversation.**
6. **A date-only question** («¿qué te conté ayer?») has nothing to compare: it returns the episodes
   of that window, newest first, at most three.
7. **Degradation:** without the embedding model the search is lexical only and the log says so;
   a database error answers «No me acuerdo de eso.» Neither fails the turn.

### 7. Dates: when it was said, not when it happened

The household time zone is a setting, `HOUSEHOLD_TIMEZONE` (default `America/Santiago`).
Timestamps stay UTC; a spoken day is cut at local midnight. A small parser turns «hoy», «ayer»,
«anteayer», a weekday («el martes»), «la semana pasada», «el mes pasado» and a day with its month
(«el 3 de marzo») into a window on **when the owner said it**. A time inside the story («el verano
de 2015», «cuando era chico») is not a window: it is searched as words in the text. A date the
parser does not understand filters nothing; it is never guessed. The same parser is reused by
step 3 of the closing path (`lives_in` with its spoken start).

### 8. The answer: the model words it, only from what was found; the fixed phrase when nothing was

With one to three results, one short call to the local model with its **own** prompt — one line of
Iroko's persona in neutral tuteo, the found units quoted as data with a date label computed by code
(«ayer», «el martes 28 de octubre»), and the rules: use only these memories, one or two sentences,
in Spanish, and if they do not answer the question write exactly «No me acuerdo de eso.». It
answers like «Sí, el martes me contaste que fuiste al parque con Zeta.» Then:

- if the model fails or times out, a template answers with the memory: «El martes me contaste
  esto: …»;
- if the model writes the fixed phrase, the fixed phrase is spoken;
- `claim_guard` still replaces a sentence that claims a save.

The generic prompt does not change: the recall answer is a controller branch, so the household rule
of Plan 0077 stays as it is. The recall answer does **not** enter short-term continuity (like a
protected answer, ADR 0020), so a visitor who speaks next cannot drag it along; the cost is that
«¿y qué más?» right after needs the cue again. The robot's replies are never indexed (decision 1),
so it cannot quote its own old answers as the owner's words.

### 9. The relatives loaded at the alta are read by a fixed template

«¿Cómo se llama mi mamá / mi papá?», «¿cómo se llaman mis papás / mis hermanos / mis abuelos / mis
nietos?», «¿cómo se llama mi pareja?» and «¿cómo se llama mi mascota / mi perro?» are answered by a
closed reader of the owner's active `normal` relations (`has_parent`, `has_sibling`,
`has_grandparent`, `has_grandchild`, `partner_of`, `pet_of`) with a fixed template and no model:
«Tus papás se llaman Zeta y Omega.» Because the alta does not tell the mother from the father, a
question about either answers with both. Nothing loaded answers «No tengo registrado eso.». The
same identity and denial as decision 5 apply. The children keep their existing route; dates,
address and health are block B.

### 10. Switches and settings

| Setting | Default | Purpose |
|---|---|---|
| `RECALL_ENABLED` | `false` in code, `true` on a delivered robot (like `PROFILE_CARD_ENABLED`) | With `false` every turn behaves as today, byte for byte; it also needs the conversation record on |
| `EMBEDDING_MODEL` | `granite-embedding:278m` | The model of decision 1; same dimension, so no table changes |
| `HOUSEHOLD_TIMEZONE` | `America/Santiago` | Decision 7 |
| `RECALL_MAX_DISTANCE` | The initial value from Plan 0075's separation, then calibrated with Pipec's real recall phrases and recorded in the plan's evaluation | Decision 6 |

The embedding model is warmed at start-up, like the face and voice models, so the first recall
after a restart does not pay the cold load. The migration also adds the missing indexes on
`conversation_records (owner_entity_id)`, `conversation_records (previous_id)` and
`conversation_episodes (owner_entity_id)`, and the connection runs `PRAGMA optimize` when it
closes.

## Pipec's decisions and where they land

Confirmed on 2026-11-03:

| # | Decision | Where it is written |
|---|---|---|
| 1 | Embedding model `granite-embedding:278m` | Decisions 1 and 10 |
| 2 | Block A reads only `normal` memories; the rest stays stored for block B | Decisions 3 and 5 |
| 3 | The face is enough to recall and to name the family (option B, after the 0 % measurement of questions) | Decision 5 |
| 4 | A question with a date or a topic goes to the diary; «¿qué sabes de mí?» stays with the card | Decision 4 |
| 5 | Calibrate with Pipec's real recall phrases and a week of recorded conversations | Decision 10 and *Test consequences* |
| 6 | Search the summaries **and** the owner's verified words | Decision 1 |
| 7 | Read the `normal` relatives of the alta by voice, in this block | Decision 9 |
| 8 | The model words the answer only from what was found; nothing found is a fixed phrase | Decision 8 |
| 9 | The owner's words are searchable as soon as they are said | Decision 2 |
| 10 | The sensitive read, liveness and «¿estás con alguien?» go together to block B, before CM-7 | *Not decided here* |
| 11 | One row per unit, FTS5 without accents, a vector per owner, UTC times, a household time zone, deletion in cascade | Decisions 1, 2 and 7 |

Pipec also asked, during the design, that a list of words never again turn a story into a refusal:
decision 4 lets only a question search and only a strong cue speak the fixed phrase.

## Amendments at acceptance

Decided by Pipec during Plan 0078's calibration and hardware runs (2026-11-03 and 2026-11-04),
each from a finding on his hardware; the evaluation record lists the commits.

| # | Amends | Amendment |
|---|---|---|
| A1 | Decision 1 | A `turn` unit is built only from the owner's words of an ordinary verified turn: a turn whose words resolve to any closed route (a recall or relatives question, «¿qué sabes de mí?», a protected request) is recorded but never becomes a unit. The owner's questions were being read back as «me contaste…» |
| A2 | Decision 3 | The diary's sensitivity has written criteria: daily life (family, outings, meals, activities, plans, tastes) is `normal`; `private` is the couple, sexuality, conflicts, money and secrets; doubt chooses only among the four protective values. A summary of a conversation made only of questions gets its diary entry but no unit |
| A3 | Decision 4 | Two speech-to-text slips are tolerated, one in a strong cue («se conté» for «te conté») and one in the relatives question («se llama a mis» for «se llaman mis»); both are ungrammatical, so they catch no story; «hoy día» is a day word, not a topic. With recall on, «¿cómo se llama mi hijo/hija?» and «¿quién es mi hijo/hija?» answer with the children list, as the parents' question names both parents |
| A4 | Decision 8 | The recall prompt has **no** «no me acuerdo» exit: it runs only when something qualified, so the robot always answers from what was found (the 3B model took the exit 12 of 12 times with two hits in front of it). A model that still writes the fixed phrase, says nothing, fails, answers in the owner's first person («fui», «yo», «mi», «mis») or says «hoy» of an older memory gets the template that quotes the first memory. «No me acuerdo de eso.» is spoken only when nothing qualified. The prompt asks for tú without naming «tuteo» |
| A5 | Decision 10 | `RECALL_MAX_DISTANCE = 0.43`, calibrated from Pipec's questions: true hits at 0.395 and 0.414, misses from 0.469. The data are thin; revisit with use |

## Implemented in Plan 0080

[Plan 0080](../plans/open/0080-mvp-recall-phrasings.md) (2026-11-09) builds what the MVP questions
needed. It changes no decision above except where this section says so; the status stays
`Accepted`.

- **Decision 9, the sides.** The mother and the father, the daughter and the son are told apart as
  relationships, with no migration: `has_mother` and `has_father` from the owner (`has_parent` now
  means a parent whose side is not recorded) and `daughter_of` and `son_of` from the child to the
  owner, a marker beside the one `child_of` row. They are not a `sex` literal because the writer
  keeps «name and relationship only» for parents, the partner and adult children (the marker is
  stored for an adult child too, whose facts stay refused). A side that is not recorded is never
  guessed: «No tengo claro cuál de ellos es tu mamá. Tus papás se llaman Zeta y Omega.». The seed
  file and `iroko-admin label-parent` / `label-child` record the side
  ([ADR 0024](0024-seed-load-senses-secrets-and-channels.md) decision 10).
- **Amendment A3 is superseded for the singular child question.** «¿Cómo se llama mi hija?» and
  «¿cómo se llama mi hijo?» now ask for one side: «Tu hija se llama Zeta.». The plural «mis hijos»
  keeps the whole list, and so does a message naming both singular words.
- **Request shapes.** «¿Cuál es el nombre de mi X?», «¿cuáles son los nombres de mi/mis X?», «dime
  el nombre de mi X» and «dime los nombres de mis X» are relatives questions when they **open** the
  sentence (after the fillers), so «no sé cuál es el nombre de mi tía» stays a story. They are
  recall-only: with the flag off they keep today's route.
- **The told-not-happened rule (decision 7).** «¿Cuándo …?» questions are answered by a fixed table
  over the first hit, with no model, and say the day it was **told** (`said_at`), never the date of
  the event: «¿cuándo fui…?» opens «No tengo registrado cuándo fue. Sí recuerdo que {día} me
  contaste esto: …». A bare «cuándo» is a cue only before a first-person past verb of a closed list
  and with a question mark or an opening accented «cuándo»; the time of the event itself stays
  unstored ([ADR 0031](0031-the-memory-engine-boundary.md) decision 5).
- **Delivery filters (decision 6, item 1).** The statement that returns a unit's text re-applies
  owner, `personal`, `normal` and the record's expiry
  ([ADR 0031](0031-the-memory-engine-boundary.md) Context item 8).

## Not decided here

| Subject | Why not now | Owner |
|---|---|---|
| Reading sensitive data by voice (health, address, birthdays, the `SECURITY` datum), the liveness defence, «¿estás con alguien?» | One concept, the audience, that needs its own decisions; CM-7 requires it | Block B (step 3 of the closing path, with CM-3b tranche B) |
| Correcting and forgetting by voice | The cascade of decision 1 is ready; the commands are CM-6 | Block C |
| Turning a spoken third-party fact into a structured one («mi tía se llama Zeta») | Large and fragile; the diary already lets it be recalled | After CM-7: a resting job may propose it from the diary (ADR 0025 decision 5) |
| ~~Telling the mother from the father in the alta~~ | Done by Plan 0080 (*Implemented in Plan 0080*): the seed file and `iroko-admin` record the side | Closed |
| «¿Y qué más?» without repeating the cue | Needs the recall answer inside continuity, which decision 8 keeps out | Revisit with real use |
| A reranker | Not measured as needed | R4, only if the metrics ask for it |
| Documents (laws, manuals, books) | Not memory | R2/R4, its own ADR; decision 1's units already carry a kind |
| Unifying the older timestamp format and the other database hygiene | Not needed for recall, needed before CM-6 compares times | The database-hygiene row of the roadmap |

## Alternatives considered

- **Put the found memories in the generic prompt.** More natural wording and less code, but it
  breaks the household rule of Plan 0077 (that would first need the rule made broad again) and
  mixes recall with continuity and the card, which the 3B model already confuses.
- **Search on every turn.** Recalls unasked, but costs an embedding per turn, adds noise a small
  model uses badly (the research of 2026-10-28) and reads the diary on every turn.
- **Search only the summaries.** Simpler, but loses the detail the owner will ask for.
- **Face and voice to name the family (the first recommendation).** Safer against a photograph, but
  the voice verifies on 0 of 7 questions: the feature would not work.
- **Hide the names when only the face matched.** It can hide only the names the alta knows; a
  relative mentioned in conversation would leak anyway.
- **A language model classifying every turn's sensitivity.** More accurate, but one model call per
  turn while the person talks; the episode's classification corrects the word classifier later.
- **Weighted sum of the two scores.** Needs normalisation and calibrated weights; RRF needs neither.
- **Keep `nomic-embed-text`.** Adequate, but the index starts empty, so the better model costs
  nothing now and a full re-embedding later.

## Consequences

### Positive

The robot answers from what it was told, with dates, and admits not knowing with a fixed phrase,
which also closes the confabulation left open by CM-2. A story never becomes a refusal. The generic
prompt and its household rule stay untouched. Forgetting already reaches the index. The search is
neutral to its source, so the family stage and a later document library reuse it.

### Negative

A photograph of the owner can draw a `normal` memory, the same exposure the children list has
today. The owner's words are read back by voice for the first time, so the word classifier and the
`normal`-only filter carry the privacy of block A. The question about the mother answers with both
parents. A recall answer is a separate model call, a little less conversational than an ordinary
turn. The database grows by about 44 MB a year.

## Test consequences

Offline and deterministic, with invented canaries: a corpus of sentences with their expected route
(Pipec's real recall phrases and the traps: the sushi story, «¿te acuerdas de Mozart?», «me acuerdo
que…», «¿qué te conté de mis hijos?»); the date parser across a daylight-saving change and an
unknown date; the word classifier and the rule that sensitivity only goes up; the gate, RRF, the
caps and zero results; another person's units, sensitive units and expired units never returned;
deleting a record removes its units, FTS rows and vectors; a property test that no unit is ever
built from a turn that is not `VERIFIED` or from the robot's reply; the architecture guards (the
generic prompt reads no household store; the recall prompt receives only the found units); no log
carries a text; with `RECALL_ENABLED=false` every route is byte for byte today's. The longitudinal
benchmark keeps its `recall` steps `unsupported`, with the reason updated: they follow a restart or
need a voice-verified turn, and the harness has no seam that produces either without imitating it
(the driver forbids imitation); CM-7 connects them together with the restart seam. Hardware
acceptance by Pipec, outcomes only: a strong cue that finds; a strong cue that does not; «¿te
acuerdas de Mozart?» converses; the sushi story converses; «¿qué te conté ayer?»; no face is
denied; «¿cómo se llaman mis papás?»; a health sentence is not recalled; a cold or absent embedding
model still finds by words.

## Docs to update

With `Proposed`: the ADR index, the roadmap (row 9; the closing path regrouped into blocks A to D
with decision 10 placed in block B; a database-hygiene row), the memory map (CM-5) and RAG §25–26.
With `Accepted`: `current-state.md` and its diagram, the operator manual (the settings, the recall
phrases), ADR 0027 (decision 5 amended) and ADR 0026 (decision 5 answered).

## Review

Revisit when the calibrated threshold or the hardware run shows wrong recalls or missed ones, when
the voice verifies questions on the Pi's microphone (decision 5 could then ask for it), when block B
decides liveness, when the family stage needs visibility `household`, or when a document source
opens.

## Follow-up

- The implementing plan is the next free plan number, 0078 (split in two if it grows beyond about
  twelve tasks: data and search, then cues, answer and reader).
- The next free ADR number is 0029.
