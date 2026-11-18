# 0086 — Block C2: correct and archive a memory by voice, delete it for good with the PIN

> **Status:** **Closed (2026-11-18)**; accepted by Pipec on real hardware, the four cases in one
> sitting ([record](../../evals/0086-c2-acceptance.md)). Code merged as PR #285 (`fac1817`; CI
> selection 8397 passed, baseline 8291) and three fixes the sitting found, each with its RED test:
> PR #286 (a spoken change is never itself a memory), #287 and #288 (a name is tried with and
> without one final «s»). The real database is at schema version 21, `iroko-admin health` exits 0
> on it and a `post-0086` backup was proven. ADR 0039 and ADR 0032 decisions 2 to 6 are
> implemented; the edges Pipec chose to leave open are in *Open points* at the end.
>
> **Was:** **Ready (promoted by Pipec on 2026-11-17)**; `NOW` on the board. Pipec confirmed all
> eleven decisions of *Pipec's decisions* at the end as written («apruebo todo, acepto todo»), and
> asked that the owner's day with an always-on robot (how long an identification lasts, when the
> robot asks for more) be reviewed after this plan closes; it is recorded in the roadmap and in
> *Deferred, with their triggers*, and it changes nothing here. Was: Draft (2026-11-17). Source:
> [ADR 0032](../../adr/0032-block-c-hygiene-correct-forget-and-years.md) decisions 2 to 7 (Pipec,
> 2026-11-11 and 2026-11-13), [ADR 0038](../../adr/0038-the-memory-engines-storage-foundation.md)
> decision 4 and its *Amendment of 2026-11-16* (the pieces deferred to this plan),
> [ADR 0039](../../adr/0039-c2-the-cheapest-forms-of-correct-archive-and-delete.md) (Proposed with
> this plan: the cheapest form of each of those pieces), and Pipec's model of forgetting of
> 2026-11-17: **a person does not erase a memory, they replace it or set it aside; the robot may do
> one thing a person cannot, delete for good, rarely and on purpose.** Its four cases are this
> plan's acceptance scenarios. One plain branch from `main` (`feat/0086-c2-correct-archive-delete`),
> one PR.

> **For agentic workers:** if the status above does not say `Ready`, stop. Read `CLAUDE.md` and
> every file of `.claude/rules/` in full first. REQUIRED SUB-SKILLS: `superpowers:executing-plans`
> (inline), `superpowers:test-driven-development` for every task,
> `superpowers:verification-before-completion` before any claim of done,
> `superpowers:requesting-code-review` and `superpowers:receiving-code-review` for Task 8, and
> `superpowers:finishing-a-development-branch` at the end. Review agents run on `sonnet` and read
> `.claude/` in full before reading code. **Pipec's rules win over the skills:** one plain branch
> from `main`, never a git worktree; this plan lives under `docs/plans/`. One commit per task; every
> test seen RED for the stated reason first. If evidence contradicts the plan, stop and report;
> **a discovery this plan's goal does not need is recorded, not built.** The Bash tool loses
> backslashes and non-ASCII characters in heredocs: use the Write and Edit tools. Commit titles:
> Conventional Commits, at most 72 characters, check `git log` after each commit; never pipe
> `git commit`; `git add` with explicit paths. Run the suite with `MEMORY_ENABLED=false` as CI does.
> Never `uv sync` without `--extra cuda`. No `just gate` or full suite in the background while
> Pipec rehearses. Pipec starts the server and the robot. **The real database is touched only in
> Task 9**, after its backup. Before pushing: `pyright`, `ruff` and `mypy` over the whole project,
> `scripts/` linted with explicit paths, `uv run ruff format --check .`.

## What the code does today (verified 2026-11-17 on `main` at `c4667fe`, schema 20)

1. **Correcting has no caller.** The policy exists (`AuthorizationAction.CORRECT_PERSONAL_MEMORY`,
   `basic`, `cognition/authorization.py`); nothing speaks it. The preference gate refuses
   «ya no me gusta …» on purpose, «a correction, CM-6» (`memory/preference_gate.py`, docstring).
2. **A stated opposite is refused, not corrected.** «No me gusta el té» with an active «le gusta el
   té» becomes a candidate whose promotion ends `CONTRADICTION` («No lo guardé: ya tengo guardado
   algo distinto.», `memory_writer._promote_in_transaction`). `likes`, `dislikes` and `prefers` are
   `MULTI_VALUE`: a second taste never replaces the first.
3. **Archiving does not exist.** No `archived_at` column, no capability (ADR 0019 has five actions).
4. **Deleting exists for whole conversations only.** `iroko-admin conversations delete --id` and
   `consent-revoke` (PIN) delete records, and with them, by `CASCADE`, their turns, episodes,
   recall units, candidates and pending topics. `revoke` on a fact or relation is a supersede to
   `revoked`, never a deletion (`relational_v4.revoke_literal_fact`). A failed or postponed
   checkpoint after these deletions is ignored (`db.checkpoint_wal` returns `False`; the Plan 0085
   ledger recorded it for this plan). There is no deletion register: restoring an older backup
   brings a deleted conversation back.
5. **The diary dies with its record.** `purge_records` deletes expired and over-cap records whole,
   and `recall_store`'s readable rule hides any unit whose record expired.
6. **Only two places hold SQL for these tables:** `relational_v4.py` (facts and relations, five
   readers filter `lifecycle = 'active'`) and `recall_store.py` (one readable rule for lexical,
   vector and window reads); `pending_store.due_topic` is the one reader of a topic to say.
7. **A plan is not an event.** `occurred_time.occurred_window` stores no interval for a phrase toward
   the future («mañana voy a …»), so «¿cuándo jugué …?» answers with the day it was told.
8. **No friend relation.** The registry has relatives, partner, pet and `withhold_from`; a friend the
   owner only talked about lives only in the diary, as ADR 0026 decision 9 says until CM-7.
9. **Candidates live as long as their turn.** `candidates.py` has no `DELETE`; a candidate goes only
   by the `CASCADE` from its turn or its person, so turn → candidate → `promoted_fact_id` names a
   fact confirmed from a story while the story exists (ADR 0039, *Context* 3).
10. **`admin_audit` has closed `CHECK`s** (operations `add`, `change`, `revoke`, `grant`, `export`,
    `delete`; kinds `pool_literal`, `pool_relation`, `care_contact`, `conversation_consent`,
    `conversation_record`).

Task 0 re-verifies each item and **stops and reports** if one is false.

## The four cases (Pipec, 2026-11-17) and what each needs

| # | Case | Today | This plan |
|---|---|---|---|
| 1 | **A plan that did not happen.** «Mañana voy a jugar a la pelota»; two days later the greeting asks, the owner answers «no, se suspendió el partido» | Additive: the answer is a new turn and recall finds both; the plan has no occurred day; the topic is asked once and never read by recall | **No code.** Tests pin it (D-2) |
| 2 | **A taste that changed.** «Ya no me gusta el té» | Refused by the gate; the opposite taste is a contradiction | The correction dialogue (D-4 to D-6) |
| 3 | **A refinement, not a correction.** «Me gusta la comida china del restaurante El Faro», later «fuimos al restaurante La Ola y me gustó más» | «me gustó» is no trigger: a new story in the diary, nothing else | **No code.** Tests pin that only the closed dialogue corrects (D-3) |
| 4 | **A person the owner wants gone.** «Mi mejor amiga Canaria me traicionó; no quiero saber nunca más de ella» | Nothing | Archive by voice (D-7), delete for good with the PIN (D-13) |

Every name and phrase here is an invented canary.

## Decisions

- **D-1 Scope.** ADR 0032 decisions 2 to 6, cut to the four cases; decision 7 (a power cut may lose
  the last turn) is written in the operator manual and tested in block D, as the ADR says.
- **D-2 Case 1 needs nothing new.** Tests pin today's behaviour: a future plan gets no occurred
  interval; «¿cuándo jugué a la pelota?» opens with «No tengo registrado cuándo fue.»
  (`recall_answer._DATE_NOT_RECORDED`) and quotes the plan with the day it was told; the owner's «se suspendió el partido» is its own unit and
  a recall about the match finds both, plan first, answer after; recall never reads
  `pending_topics`. A pending topic marked «did not happen» is deferred (trigger: a recall or a
  greeting that says on hardware that a cancelled plan happened).
- **D-3 Case 3 needs nothing new.** Tests pin: «fuimos al restaurante La Ola y me gustó más»
  matches neither the preference gate nor the change grammar; «me gusta más la comida del
  restaurante La Ola», confirmed, adds a second `likes` and leaves the first active; only the closed
  change dialogue of D-5 supersedes a fact.
- **D-4 The change grammar** (`cognition/memory_change.py`, pure, folded text like the gate). A new
  `InformationNeed.MEMORY_CHANGE`, resolved before generic conversation; a question, a conditional
  or a third person never matches.
  - *Correct a taste:* «ya no me gusta(n) {x}», «ya no me encanta(n) {x}», «ya no prefiero {x}»,
    «ya no odio {x}», «ya no detesto {x}», «ya no soporto {x}», each optionally followed by
    «, ahora me gusta(n) {y}» or «, ahora prefiero {y}»; an opening «me equivoqué» is skipped.
  - *Archive:* «no quiero saber (nunca) más de {x}», «no me hables más de {x}», «no me recuerdes
    más {x}» (or «… más a {x}», «… más lo de {x}»), «olvídate de {x}».
  - *A pronoun* (`ella`, `él`, `ellos`, `ellas`) as `{x}` names the **one** name of the same message
    that follows a word of `PERSON_WORDS` («mi mejor amiga Canaria …») or equals an entity's name;
    zero or two names: no match (ordinary conversation).
- **D-5 The change dialogue** (`memory/memory_change_dialogue.py`). The actor is resolved first for
  every message of this shape (no oracle, ADR 0021 decision 9); only the **owner's face** (`basic`,
  no token) goes on; anything else is ordinary conversation. The robot reads back the change and
  ends «Dime: sí, autorizo.», with `expects_short_reply` true (Plan 0067's reply mode). The pending
  change is **in process**, one per person, for `memory_candidate_answer_seconds` (60 s); a restart
  loses it and changes nothing. While one is pending no memory offer is spoken. The answer is the
  existing closed grammar (`parse_memory_answer`, a verb alone) from the **same face** (`basic`; the
  voice is not required, ADR 0032 decision 3); the pending change is looked up before any open
  offer. The policy is evaluated and audited before the effect: `correct_personal_memory` and a new
  `archive_personal_memory` (ADR 0039 decision 4). Anything above `normal`, and any person of
  D-7's refusals, is refused with a fixed phrase. Fixed phrases (`memory/lexicon.py`, tuteo; the
  taste verb agrees as in the offer, «te gustan» before a plural article; «no te gusta» and
  «prefieres» for the other predicates):

  | Moment | Phrase |
  |---|---|
  | Correct, no new value | «Tenía guardado que te gusta {x}. ¿Lo cambio? Dime: sí, autorizo.» |
  | Correct, a new value | «Tenía guardado que te gusta {x}. Ahora guardo que prefieres {y}. ¿Lo cambio? Dime: sí, autorizo.» |
  | Archive | «Encontré {n} recuerdos de {x}. Los dejo de lado y no te los menciono más. ¿Lo hago? Dime: sí, autorizo.» («un recuerdo» when `n` is 1) |
  | Nothing to correct | «No tenía guardado que te gusta {x}.» |
  | Nothing to archive | «No tengo nada guardado de {x}.» |
  | Above `normal`, or an enrolled person | «Eso se cambia en iroko-admin, con tu PIN.» |
  | Done | «Listo, lo cambié.» / «Listo, lo dejé de lado.» |
  | Declined («no autorizo») | «Está bien, no cambio nada.» |
  | Failed after the owner's change was found | «No pude hacerlo ahora. Dímelo de nuevo en un rato.» |

- **D-6 What a correction writes** (ADR 0032 decision 4). Only the owner's own `likes`, `dislikes`
  and `prefers` of sensitivity `normal`, matched by `comparison_key` among the active, unarchived
  facts of that predicate. One transaction: with a new value, the new fact through
  `canonical_writer.write_literal` (channel of the route, the owner as asserter and confirmer) and
  the old one `superseded` with `superseded_by` and `superseded_at`; without one, the old fact
  `revoked` (`revoke_literal_fact`, history). The diary is never edited.
- **D-7 What an archive sets aside** (ADR 0039 decision 6). `{x}` resolves to: the owner's tastes
  whose key is `{x}`; an entity linked to the owner (a relation or a care contact) whose folded name
  or alias is `{x}`, with its relations and the facts about it; the owner's readable recall units
  (turn and episode) whose body matches every word of `{x}` and of each of that entity's names
  (FTS5, no vector); the owner's pending topics whose topic names it. All of them get one
  `archived_at` instant. **Refused by voice** (the iroko-admin phrase): an entity that is a care
  contact, holds a role, a credential, a face or voice profile or a consent, or any matched fact or
  relation above `normal`. Archiving also clears the short-term session (`continuity.reset()`), so
  the next turn does not carry what was just set aside. A later story that names the person again
  is kept normally: the owner chose to tell it.
- **D-8 Every reader skips what is archived.** The five active readers of `relational_v4`, the
  readable rule and `recent_units` of `recall_store`, and `pending_store.due_topic` add
  `archived_at IS NULL`; the writers' own checks do not (an archived row is still `active`).
- **D-9 A confirmed restatement brings an archived fact back.** `promote` looks for a duplicate
  among the active facts **including archived ones**; an archived duplicate is cleared and the
  candidate confirmed against it (otherwise the unique index of active values would refuse the new
  row).
- **D-10 Migration 021, `ADD COLUMN` only.** `archived_at TEXT` with the exact instant `CHECK` (or
  `NULL`) on `literal_facts_v4`, `entity_relations_v4`, `recall_units` and `pending_topics`. No
  index (four small tables; added when a measured query asks). No episode column: no reader speaks
  an episode except through its unit.
- **D-11 The diary outlives its record** (ADR 0032 decision 5, ADR 0039 decision 2). `purge_records`
  deletes an expired or over-cap record's **turns** (their units, candidates and topics go by
  `CASCADE`) and keeps the record row while its episode is written (`episode_status = 'done'` and a
  `conversation_episodes` row); a record with no written episode goes whole, as today. The cap still
  counts turn bytes and stops when no closed record holds a turn. The readable rule reads an episode
  unit whatever its record's expiry. Withdrawing the consent and a PIN deletion still delete both.
  An episode size cap waits for a measurement (Task 0 counts the episodes; trigger: the diary over
  a measured share of the 200 MB).
- **D-12 The deletion register and protocol** (ADR 0032 decision 6, ADR 0038 decision 4, ADR 0039
  decision 1). `memory/deletion_register.py`. File `deletions.jsonl` in the database's directory
  (`settings.brain_db_path.parent`; no new setting). One line per deleted row:
  `{"seq": int, "kind": str, "id": int, "at": "<instant>"}`, closed kinds `literal_fact`,
  `entity_relation`, `care_contact`, `turn`, `episode` (id = the record), `record`, `owner_records`
  (id = the owner: every record, the consent withdrawn), `entity`; never a value. The protocol, in
  this order: append the lines and `fsync` the file (and its directory where the OS allows it);
  `PRAGMA synchronous=FULL`; one transaction with the deletions and `meta.deletion_register_seq` set
  to the last `seq`; `synchronous` back to `NORMAL`; `db.checkpoint_wal_until_done()` (up to 5 tries,
  0.2 s apart; logs `deletion.checkpoint postponed attempts=5` when it cannot). **Replay**: after
  `open_db`, in the server's lifespan and in `iroko-admin`, every line with `seq` above the marker,
  in order, idempotent, then the marker. A last line without its newline (a cut during the append,
  before any deletion ran) is dropped; any other unreadable line refuses the start with a count,
  never the line. `conversations delete` and `consent-revoke` use the protocol too (the ledger
  item); the expiry purge does not (a restored record expires again at the next run).
- **D-13 `iroko-admin`: delete for good, list and restore** (PIN, server stopped, ADR 0025's local
  path). One `admin_audit` row per command, reusing today's kinds (`delete` on `pool_literal`,
  `pool_relation`, `care_contact`, `conversation_record`; `change` for a restore), so no rebuild of
  the audit table.
  - `forget fact <id>`, `forget relation <id>`: the row, physically, any sensitivity.
  - `forget turn <id>` (turn ids shown by `conversations export`): the turn with its unit, candidate
    and topic, and **the whole episode of its record** (ADR 0032 decision 2); the facts confirmed
    from that turn are named and kept («De esa conversación guardé también: {n} datos. Siguen
    guardados; bórralos con `forget fact`.»). The turn is deleted, not redacted (ADR 0039 decision
    5).
  - `forget episode <record id>`: the episode and its unit; the turns stay.
  - `forget person <entity id>` or `forget person --name <palabras>` (a person only talked about):
    the counts first, then `SI` typed; in this order the care contacts, the turns and episodes whose
    words name the person (folded whole words; their units and topics follow), the facts and
    relations, the entity. Refused, with what blocks it, for the owner and for an enrolled person
    (role, credential, biometric profile or consent).
  - `archive list`: the archived rows grouped by their `archived_at` (per group: counts per kind and
    a short text of each row, under the PIN); `archive restore <instant>` clears that group.
  - «Borra todo» adds no command: `conversations consent-revoke` (the whole record and the diary,
    through the register) and `just reset-db` (everything) exist.
- **D-14 What «a story» is by voice.** Archiving by voice sets aside the units that name `{x}`; an
  episode unit that names it is set aside whole, with the other memories of that day (ADR 0039,
  *Negative*); the read-back count says how many.

## Deferred, with their triggers

| Deferred | Its trigger | Owner |
|---|---|---|
| `uid` on durable rows (ADR 0038 decision 5) | Two databases merged, or a register replayed across a reset | ADR 0039 decision 1 |
| `episode_sources`, the episode's own key to its record | An episode built from turns of more than one record | ADR 0039 decision 2 |
| A fact's own link to its turn (`source_turn_id`) | A job deletes candidate rows before their turn | ADR 0039 decision 3 |
| `redacted_at` on turns | An export or an audit that must show a deleted turn existed | — |
| `archived_at` on episodes; indexes on `archived_at` | A reader that speaks an episode directly; a measured slow query | — |
| A pending topic marked «did not happen» | A recall or greeting that says a cancelled plan happened (hardware) | — |
| Correcting a fact other than a taste by voice (a name, the form, a relative) | Pipec asks for one | Its plan |
| A «borra todo» command | Pipec asks for one beyond `consent-revoke` and `reset-db` | — |
| An episode size cap | The diary over a measured share of the cap | — |
| Archiving a person automatically in later stories | Third parties learned from conversation (after CM-7) | — |
| The contradiction phrase pointing to the correction | An owner stuck at «ya tengo guardado algo distinto» on hardware | — |
| The deletion register in the backups and the restore procedure | ADR 0033 (backups) | ADR 0033 |
| How long the owner stays identified in a day, and when the robot asks for a fresh confirmation or more evidence (a second face, an unknown voice) | This plan closes (Pipec, 2026-11-17) | The roadmap's product gaps |

**Goal.** The owner corrects a taste and sets aside a person by voice, with the face and a closed
verb; nothing set aside is said, offered or searched, and `iroko-admin` brings it back or deletes it
for good with the PIN; a deletion survives a power cut, a restart and a restore; the diary outlives
the raw text.

**Tech stack.** Python 3.12, aiosqlite, FTS5, `sqlite-vec` 0.1.9, pytest. No new dependency or
setting; no wire or robot change (the stream's `done.expects_short_reply` already exists).

**Spec.** ADR 0032 decisions 2 to 7; ADR 0038 decision 4 and its amendment; ADR 0039; ADR 0019 §3;
ADR 0021 decision 9; [guardrails](../../architecture/implementation-guardrails.md);
[data dictionary](../../architecture/data-dictionary.md).

**Required reading.** The above, then the code: `db.py`, `memory/meta.py`, `relational_v4.py`,
`memory_writer.py`, `canonical_writer.py`, `candidates.py`, `candidate_dialogue.py`,
`preference_gate.py`, `lexicon.py`, `recall_store.py`, `recall_search.py`, `pending_store.py`,
`conversation_record.py`, `conversation_episodes.py`, `conversation_consent.py`, `care_contacts.py`,
`declarative.py`, `continuity.py`, `admin_cli.py`, `conversation_admin.py`, `admin_audit.py`,
`cognition/intent_resolution.py`, `cognition/controller.py`, `cognition/authorization.py`,
`cognition/models.py`, `main.py`; the tests of each.

## Global constraints

- English code and docstrings; no `Any`, no `print` (the CLI's existing `# noqa: T201` pattern
  excepted), no `os.path`, no bare `except`; logging with `%`.
- Counts and ids only in logs, the register, the audit and the evidence; never a value.
- Every route, prompt and reply is byte-identical to `main` for every message that is not a
  `MEMORY_CHANGE` or its answer, and for every turn of a store with nothing archived.
- No real household data: invented canaries only (Canaria, El Faro, La Ola, el té, el café);
  `scripts/check_reserved_terms.py` passes.

## Review focus

1. **An archived row reaches a reader** (the card, «¿qué sabes de mí?», a relatives answer, recall,
   the greeting): one test per reader (Task 1).
2. **A restore after a reissued id**: a backup restored, the register replayed, a new row reusing a
   deleted id, a second start: the new row survives (Task 3).
3. **A cut between the append and the deletion**: the next start deletes; a half-written last line
   is ignored (Task 3).
4. **A stranger, a token or a second face says the change phrase** or its answer: ordinary
   conversation, nothing pending, nothing audited as a change (Task 6).
5. **A common word as a name** («Paz», «Rosa») archives more than meant: the read-back count says so
   before the verb, and `archive restore` undoes it (Task 7).

---

## Permitted files

Paths under `server/src/server/` unless they start with `tests/`, `docs/` or the root; a need
outside the list stops the plan for Pipec.

| Task | Files |
|---|---|
| 1 | `memory/migration_021_archive.sql` (new), `db.py` (the migration list), `relational_v4.py`, `recall_store.py`, `pending_store.py`, `memory_writer.py`; `tests/integration/test_migration_021.py` (new), `tests/integration/test_archived_readers.py` (new), the store tests they touch |
| 2 | `conversation_record.py`, `recall_store.py`; `tests/integration/test_diary_outlives_record.py` (new), the record and recall tests |
| 3 | `memory/deletion_register.py` (new), `db.py`, `memory/meta.py`, `main.py`, `conversation_record.py`, `conversation_consent.py`, `admin_cli.py`; `tests/integration/test_deletion_register.py` (new), `tests/integration/test_physical_deletion.py` |
| 4 | `admin_cli.py`, `memory/admin_ops.py`, `conversation_admin.py`, `relational_v4.py`, `recall_store.py`, `pending_store.py`, `conversation_record.py`, `conversation_episodes.py`, `care_contacts.py`, `declarative.py`; `tests/integration/test_admin_forget.py` (new), `tests/integration/test_admin_archive.py` (new) |
| 5 | `cognition/memory_change.py` (new), `cognition/intent_resolution.py`, `cognition/response_plan.py`, `memory/lexicon.py`; `tests/unit/test_memory_change_grammar.py` (new), `tests/unit/test_preference_gate.py` |
| 6–7 | `memory/memory_change_dialogue.py` (new), `cognition/controller.py`, `cognition/authorization.py`, `cognition/models.py`, `memory/candidate_dialogue.py`, the voice-route wiring that injects the memory answerer today, `memory/lexicon.py`; `tests/integration/test_memory_change_dialogue.py` (new), the controller, authorization and candidate-dialogue tests |
| 9 | `docs/architecture/current-state.md`, `docs/architecture/data-dictionary.md`, the Archify memory diagram, `docs/runbooks/operator-manual.md`, `docs/evals/0086-c2-acceptance.md` (new), ADR 0032, 0038, 0039, 0019, 0026, 0027 and the ADR index, the plan board, `docs/plans/open/README.md`, `docs/plans/completed/README.md`, the roadmap (row 8), both delivery maps, Pipec's local `docs/roadmap/tabla-tareas.md` |

**Rollback boundary.** Before the merge, the branch. After it, a revert: migration 021 only adds
nullable columns, which the old code ignores; `deletions.jsonl` stays beside the database and is
read by nothing. The real data: the `pre-0086` backup of Task 9.

---

## Task 0: Re-audit and baseline

- [ ] **Step 1:** `git checkout main && git pull`, create `feat/0086-c2-correct-archive-delete`;
  confirm 021 is the next migration.
- [ ] **Step 2:** verify items 1 to 10 of *What the code does today* and **stop and report** if one
  is false.
- [ ] **Step 3:** with the server stopped, on a copy of the real database opened `immutable=1`
  (deleted the same day), counts only: records, written episodes, records expiring before
  2026-12-31, recall units by kind, active tastes, entities linked to the owner, care contacts.
- [ ] **Step 4:** baseline: `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and
  not eval" -q -n auto`.

## Task 1: Archived rows, and every reader skips them

**Interfaces:** `async def archive_rows(conn, *, facts: Sequence[int], relations: Sequence[int],
units: Sequence[int], topics: Sequence[int], at: str) -> ArchiveCounts` and
`async def restore_archived(conn, *, at: str) -> ArchiveCounts` (each in the owner module of its
table; `ArchiveCounts` a frozen dataclass of ints in `memory/write_types.py`);
`get_active_literal_facts(..., include_archived: bool = False)`.

- [ ] **Step 1: Write the failing tests:** migration 021 adds the four columns and refuses a
  malformed instant; one test per reader of D-8 (an archived taste is not on the card nor in
  «¿qué sabes de mí?»; an archived relation is not in a relatives answer; an archived unit is found
  by neither lexical, vector nor window recall; an archived topic is not greeted); a restore brings
  each back; `test_a_confirmed_restatement_unarchives_the_fact` (D-9).
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS; every existing store test
  unchanged.
- [ ] **Step 5:** commit `feat: archive a memory without losing it (plan 0086)`.

## Task 2: The diary outlives its record

- [ ] **Step 1: Write the failing tests:** an expired record with a written episode keeps its row,
  episode and episode unit and loses its turns, turn units, candidates and topics; one without an
  episode goes whole; the cap deletes turns oldest first and stops with no closed record holding a
  turn; recall finds the episode unit after the expiry; withdrawing the consent deletes the episode;
  the pins of case 1 (D-2): no occurred interval for «mañana voy a jugar a la pelota», the
  `HAPPENED` answer quotes it with the told day, a later «se suspendió el partido» is found with it.
- [ ] **Step 2:** FAIL. **Step 3:** implement D-11. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: keep the diary after the raw record expires (plan 0086)`.

## Task 3: The deletion register and protocol

**Interfaces:** `class DeletionKind(StrEnum)` (D-12's eight kinds);
`@dataclass(frozen=True) class Deletion: kind: DeletionKind; row_id: int`;
`async def delete_for_good(deletions: Sequence[Deletion], apply: Callable[[aiosqlite.Connection],
Awaitable[None]], *, now: datetime) -> bool` (the protocol; returns whether the checkpoint
completed); `async def replay_register() -> int` (lines applied); `async def
checkpoint_wal_until_done(attempts: int = 5, pause_s: float = 0.2) -> bool` in `db.py`.

- [ ] **Step 1: Write the failing tests:** each kind deleted through the protocol leaves no row and
  one register line with no value; `test_a_restore_never_resurrects` (a database copied before a
  deletion, put back, opened: nothing found, marker moved);
  `test_a_reissued_id_survives_a_second_start` (Review focus 2);
  `test_a_cut_after_the_append_deletes_at_the_next_start` and a half-written last line ignored
  (Review focus 3); an unreadable middle line refuses the start with a count; `synchronous` is
  `FULL` during the deletion and `NORMAL` after; `conversations delete` and `consent-revoke` write
  their lines; the byte-level test of Plan 0085 extended to a fact, a turn and an episode deleted
  through the protocol, checkpoint reported done.
- [ ] **Step 2:** FAIL. **Step 3:** implement; replay wired in `main.py`'s lifespan and in
  `iroko-admin` after `open_db`. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: a deletion register a restore re-applies (plan 0086)`.

## Task 4: `iroko-admin` forget, archive list and restore

- [ ] **Step 1: Write the failing tests:** each command of D-13 under a correct and a wrong PIN, with
  the server answering (refused) and with `--dry-run`; `forget turn` deletes the whole episode, names
  and keeps the confirmed facts (ADR 0038 row 10); `forget person --name Canaria` deletes the
  turns, episodes, units and topics that name the canary and nothing else; `forget person <id>`
  deletes the care contact before the entity and refuses the owner and an enrolled person; one
  `admin_audit` row per command with no value; `archive list` groups by instant and `archive
  restore` clears one group.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: forget for good and restore with the PIN (plan 0086)`.

## Task 5: The change grammar

**Interfaces:** `@dataclass(frozen=True) class MemoryChange: kind: Literal["correct", "archive"];
predicate: str | None; target: str; replacement: str | None; replacement_predicate: str | None`;
`def parse_memory_change(message: str) -> MemoryChange | None`.

- [ ] **Step 1: Write the failing tests:** each form of D-4 parses («Ya no me gusta el té.»,
  «Ya no me gusta el té, ahora prefiero el café.», «Me equivoqué, ya no me gustan los porotos.»,
  «No quiero saber nunca más de Canaria.», «Mi mejor amiga Canaria me traicionó; no quiero saber
  nunca más de ella.»); questions, conditionals, a third person, two names with a pronoun and
  «olvídalo» do not; case 3 (D-3): «Fuimos al restaurante La Ola y me gustó más.» matches neither
  this grammar nor the gate; the gate's refusal of «ya no me gusta» is unchanged.
- [ ] **Step 2:** FAIL. **Step 3:** implement; `InformationNeed.MEMORY_CHANGE`. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: a closed grammar for changing a memory (plan 0086)`.

## Task 6: The change dialogue: correct a taste

- [ ] **Step 1: Write the failing tests:** the owner's face says case 2, hears the read-back of D-5,
  answers «sí, autorizo.» with the face only: the old fact `superseded` (or `revoked`), the new one
  active, the card shows only the new one, the audit has the `correct_personal_memory` decision
  before the write; «no autorizo.» changes nothing; after 60 s the answer is ordinary conversation;
  a stranger, a token, a second face and an unknown voice-only actor get ordinary conversation and
  nothing pending (Review focus 4); no offer is spoken while a change is pending; a pending change
  wins over an open offer; a restart loses it; case 3's second taste never supersedes the first.
- [ ] **Step 2:** FAIL. **Step 3:** implement; the new capability with its pinned-actions test
  updated. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: correct a taste by voice (plan 0086)`.

## Task 7: The change dialogue: archive by voice

- [ ] **Step 1: Write the failing tests:** case 4 with a diary-only canary: the read-back counts the
  units that name her, «sí, autorizo.» archives them and her topics, «¿qué te conté de Canaria?»
  answers «No me acuerdo de eso.», the short-term session is cleared, `archive restore` brings them
  back; with an alta entity: its relations and facts archived too; a care contact, an enrolled
  person or a `private` relation hears the iroko-admin phrase and nothing changes; a name found
  nowhere hears «No tengo nada guardado de {x}.»; a common-word name shows its true count (Review
  focus 5).
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: set aside a person by voice (plan 0086)`.

## Task 8: Verification and review

- [ ] **Step 1:** the CI selection, `uv run pyright`, `uv run mypy server/src robot/src`,
  `uv run ruff check .`, `uv run ruff format --check .`, `uv run ruff check scripts/*.py`,
  `uv run python scripts/check_reserved_terms.py`, `just gate`.
- [ ] **Step 2:** the `simplify` skill, then `database-architect`, `security-auditor`,
  `pr-review-toolkit:code-reviewer`, `pr-review-toolkit:silent-failure-hunter` and
  `pr-review-toolkit:pr-test-analyzer` on `git diff main...HEAD` (`sonnet`, `.claude/` first,
  read-only); each accepted finding fixed with its RED test; Step 1 again. Push, PR, CI green.

## Task 9: Hardware acceptance, the real migration and close

**Setup.** With the server stopped, the agent backs up to `data/backups/pre-0086-<fecha>/` and
proves it opens; merge; Pipec starts the server (migration 021 runs) and the robot, streaming
route, memory, record, recall and pending topics on. Recall units come only from turns with the
owner's verified voice: say each story in one long sentence (about 3 s or more). The agent runs
every `iroko-admin` step and reads `logs/server.log`; Pipec speaks and types the PIN.

| # | Who | Step | Expected |
|---|---|---|---|
| 1 | Tú | «Me gusta el té.» … «Sí, autorizo.» | «Listo, lo guardé.» (skip if already stored) |
| 2 | Tú | «Ya no me gusta el té.» | «Tenía guardado que te gusta el té. ¿Lo cambio? Dime: sí, autorizo.» |
| 3 | Tú | «Sí, autorizo.» | «Listo, lo cambié.» |
| 4 | Tú | «¿Qué sabes de mí?» | The tea is not among the tastes |
| 5 | Tú | «Ya no me gusta el café, ahora prefiero el mate.» … «Sí, autorizo.» (with «me gusta el café» stored first) | The new read-back, then «Listo, lo cambié.» |
| 6 | Yo | `iroko-admin list`, then a count of the owner's taste rows by lifecycle (counts only) | Tea and coffee gone from the list, mate in it; one `revoked` and one `superseded` row more than before |
| 7 | Tú | «Me gusta la comida china del restaurante El Faro.» … «Sí, autorizo.» | Saved |
| 8 | Tú | «Fuimos al restaurante La Ola y me gustó más.» | An ordinary reply; no offer, no read-back |
| 9 | Tú | «¿Qué sabes de mí?» | The Chinese food is still there |
| 10 | Tú | «Mañana voy a jugar a la pelota con mis amigos del barrio.» | An ordinary reply |
| 11 | Tú | «Al final se suspendió el partido de mañana porque va a llover.» | An ordinary reply |
| 12 | Tú | «¿Cuándo jugué a la pelota?» | «No tengo registrado cuándo fue.», then the plan quoted as told today; never «jugaste» |
| 13 | Tú | «El sábado fui al cine con mi amiga Canaria y vimos una película de terror.» and «Ayer almorcé con Canaria en el centro y hablamos mucho rato.» | Ordinary replies |
| 14 | Tú | «Mi mejor amiga Canaria me traicionó; no quiero saber nunca más de ella.» | «Encontré 2 recuerdos de Canaria. Los dejo de lado …» (the count may differ: the agent reads it in the log) |
| 15 | Tú | «Sí, autorizo.» | «Listo, lo dejé de lado.» |
| 16 | Tú | «¿Qué te conté de Canaria?» and «¿Con quién fui al cine?» | «No me acuerdo de eso.» / no mention of her |
| 17 | Yo | Stop the server; `iroko-admin archive list`, then `archive restore <instante>` (PIN) | One group; restored |
| 18 | Tú | Start; «¿Qué te conté de Canaria?» | The memories again |
| 19 | Yo | Stop; back up to `data/rehearsal-0086/` (database and `deletions.jsonl`); `iroko-admin forget person --name Canaria` (PIN, `SI`) | The counts, then deleted |
| 20 | Tú | Start; «¿Qué te conté de Canaria?» | «No me acuerdo de eso.» (survives the restart) |
| 21 | Yo | Stop; open the rehearsal copy (`BRAIN_DB_PATH` to it, the current register beside it) with `iroko-admin health` | The replay applies the lines, health 0, nothing of the canary left (counts) |
| 22 | Yo | `iroko-admin health` on the real database; the `post-0086` backup made and proven; the rehearsal copy deleted | Health 0 |

Cases 1 to 6 are case 2, 7 to 9 case 3, 10 to 12 case 1 (its greeting days are covered by Task 2's
tests, as in Plan 0084), 13 to 21 case 4. A step that fails is fixed with its RED test and repeated.

- [x] **Step 1:** the script above; the record `docs/evals/0086-c2-acceptance.md` (outcomes and
  counts only).
- [x] **Step 2:** when Pipec accepts, the `pre-0086` backup deleted and recorded; the documents of
  the permitted list updated (ADR 0032 and 0039 `Accepted`, the notes on ADR 0019, 0026, 0027 and
  0038); the plan moved to `completed/`; commit `docs: close plan 0086, correct archive and delete`,
  push, PR, squash-merge, delete the branch.

---

## Completion criteria

1. The four cases pass on hardware (Task 9), with the record written.
2. Migration 021 on the real database, `iroko-admin health` exits 0, a proven `post-0086` backup.
3. No archived row reaches any reader; a restore, a restart and a cut during a deletion resurrect
   nothing; the byte-level test covers a fact, a turn and an episode.
4. The CI selection, `just gate`, the type checkers, `ruff` and the reserved-terms guard pass.
5. The documents of Task 9 updated; the plan in `completed/`; `pre-0086` deleted after acceptance.

## Non-goals

Everything in *Deferred, with their triggers*; the export (Plan 0087); backups, restore procedure
and encryption (ADR 0033); correcting anything but a taste by voice; learning third parties from
conversation (after CM-7); any wire, robot, setting or dependency change.

## Self-review (2026-11-17)

- **Scope rule.** Every piece names its reason: the correction and the archive are the behaviours
  of cases 2 and 4; the readers' filter is what «never said» means; the register, the protocol and
  the replay are the defect «a restore brings a deleted conversation back» and the ledger's
  postponed checkpoint; the diary rule is ADR 0032 decision 5 confirmed by Pipec. Cases 1 and 3 add
  no code, only tests. Four pieces ADR 0038 deferred here are not built: ADR 0039 shows the guarantee
  each was for already holds, or holds more cheaply, and keeps its trigger.
- **Cheapest form.** One `ADD COLUMN` migration; no table rebuild (the audit kinds are reused); no
  persisted dialogue state; no new setting.
- **Type consistency.** `MemoryChange`, `parse_memory_change`, `ArchiveCounts`, `archive_rows`,
  `restore_archived`, `DeletionKind`, `Deletion`, `delete_for_good`, `replay_register`,
  `checkpoint_wal_until_done` are each defined once and named the same in later tasks.

## Pipec's decisions (confirmed 2026-11-17, all eleven as written)

1. **ADR 0039 decision 1:** the register keyed on the integer id with a replay marker, instead of a
   `uid` on every row.
2. **ADR 0039 decision 2:** the diary outlives its record by keeping the record row, instead of
   rebuilding `recall_units` with new keys.
3. **ADR 0039 decision 3:** no fact-to-turn column (the candidate already links them).
4. **ADR 0039 decision 4:** a sixth capability, `archive_personal_memory` (`basic`).
5. **ADR 0039 decision 5:** a deleted story's turn is deleted, not redacted to a marker.
6. **D-5:** the change is confirmed with the existing «sí, autorizo», the face only, no voice.
7. **D-6:** «ya no me gusta el té» alone leaves the tea as history (`revoked`), and does not store
   «no le gusta el té».
8. **D-4 and D-7:** the archive phrases, the pronoun rule («… de ella») and what an archive covers;
   a care contact or an enrolled person only in `iroko-admin`.
9. **D-9:** a taste restated and confirmed brings its archived fact back.
10. **D-13:** no «borra todo» command (`consent-revoke` and `reset-db` cover it); the audit kinds
    reused.
11. **The hardware script** of Task 9 in one sitting, with the greeting days of case 1 covered by
    tests.

## Execution record (2026-11-18)

Executed in the session that wrote it, at Pipec's request («Haz esta tarea aquí»), on
`feat/0086-c2-correct-archive-delete`; the ledger is
`.superpowers/sdd/0086-c2-correct-archive-delete/progress.md`.

- **Tasks 0 to 7** as planned, with these deviations, each recorded in the ledger: Tasks 3 and 4,
  and 6 and 7, landed as one commit each (they share their modules); `memory/forget_scope.py`,
  `memory/admin_forget.py` and `memory/candidates.facts_confirmed_from_turn` were added beside the
  permitted list; `forget` dispatches each kind to its owner module instead of taking an `apply`
  callback, and `conversation_record.delete_record` and the deleting part of
  `revoke_conversation_consent` were retired so no unregistered deletion path remains;
  `PERSON_WORDS` and `GREETING_WORDS` moved to `text_keys.py` (the cognitive core may import no
  memory module); the data dictionary was updated in Task 1 (its guard requires it). In Tasks 3,
  4, 6 and 7 the code came before its tests; RED was proven by mutation instead (each mutation
  caught).
- **Task 8:** three read-only reviews on `sonnet` (database, security, code and tests, instead of
  five) plus the automated security review. One critical finding (a deletion a `RESTRICT` key
  refused left its register line and stopped every start: now probed in a rolled-back savepoint
  before the append; a replayed line a key refuses waits, is retried at every start and is
  announced) and the important ones (a record whose episode was deleted stayed for ever; a
  `medical` topic could be archived by voice; `iroko-admin` showed counts before the PIN and left
  refusals unaudited; a voice change's new value skipped the preference gate; a secret could be
  read as a change), each fixed with its test.
- **Task 9:** the four cases pass ([record](../../evals/0086-c2-acceptance.md)); the sitting found
  and fixed three defects (PR #286 to #288).

## Open points (Pipec, 2026-11-18)

Pipec's rule for the MVP: a wide margin of error; these are kept here for the review of all the
plans' open points, not fixed now («hasta los mismos Siri o Alexa se equivocan»).

| Open point | What it would take | Seen |
|---|---|---|
| Speech-to-text variants of a name beyond one final «s» («Canadia»), and other speakers | Real audio of several people, then a measured tolerance | Hardware 2026-11-18 |
| Recall precision for a named person: with no unit holding the name, an unrelated story found by meaning alone | A rule such as «a question that names someone answers only from units that hold the name» (recall, ADR 0028) | Hardware 2026-11-18 (distance 0.368 and 0.372 under the 0.43 gate) |
| A memory offer's short answer asks to repeat when the voice does not verify | Known since Plan 0068; a correction or an archive needs the face only | Hardware 2026-11-18 |
| «No tengo nada guardado de …» when only `private` rows name the person | By design (no oracle at `basic`); `iroko-admin` reaches them | Hardware 2026-11-18 |
| The owner's day with an always-on robot (how long an identification lasts) | Its own decision, roadmap | Pipec, 2026-11-17 |
