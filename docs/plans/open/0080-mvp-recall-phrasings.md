# 0080 — The memory MVP: the owner's own phrasings, the sides of the family (mother and father, daughter and son), and the delivery filters

> **Status:** `Ready` and `NOW` — **promoted by Pipec on 2026-11-09** («pásalo, está todo ok»),
> decisions D-1 to D-11 confirmed as written, including the four builder's calls (the fallback
> wording, `label-parent` / `label-child`, the verb list of the «cuándo» cue and the one-hit,
> no-model answer) and the daughter and the son added at his request; executed in a new session.
> Written as `Draft` the same day against `main` at `f9b610e` and the code read that day (queue
> rule 4: Task 0 re-verifies every claim below against the merged code before any change, and
> **stops and reports** if one is false). Written for an executor who has not seen this
> repository. Step 1 of the
> [path to the MVP](../../roadmap/cognitive-roadmap.md#closing-path-of-conversational-memory).

> **For agentic workers:** if the status above does not say `Ready`, stop. REQUIRED SUB-SKILL:
> `superpowers:subagent-driven-development` or `superpowers:executing-plans` (Pipec chooses), with
> `superpowers:test-driven-development` and `superpowers:verification-before-completion`.
> **Pipec's rules win over the skills:** one plain branch from `main` (`feat/0080-mvp-recall`),
> never a git worktree. One commit per task; every new test seen RED for the stated reason first
> (paste the RED output in the PR). The Bash tool of this environment loses backslashes and
> non-ASCII characters in heredocs and arguments: use Write/Edit, put Spanish phrases in files,
> and keep commit titles ASCII, 72 characters at most; check `git log` after each commit (the hook
> rejects silently); do not pipe `git commit`; `git add` with explicit paths. Run the suite with
> `MEMORY_ENABLED=false` as CI does. Never run `uv sync --all-packages --all-groups` (it removes
> the optional `cuda` extra). **Do not run `just gate` while Pipec rehearses** (about 3.5 GB of
> RAM). **Pipec starts the server and the robot**, never the agent; every hardware case is
> confirmed in `logs/server.log`, not by anyone's word. Before pushing run `pyright`, `ruff` and
> `mypy` over the **whole** project and lint `scripts/` with explicit paths.

## What the MVP needs, and where `main` stands

The test (Pipec, 2026-11-05) is a conversation on the laptop body in which the robot answers,
coherently and without inventing, the six questions below. Resolved on 2026-11-09 against the intent
rules of `main` with `recall=True` by a throwaway script and no database (`resolve_information_need`,
`classify_recall_cue`, `relation_of`):

| Question | Resolves today to | Gap |
|---|---|---|
| «¿Quiénes son mis hijos?» | `own_children_list` | none |
| «¿Cómo se llama mi hija?» / «mi hijo?» | `own_children_list` (recall on, Plan 0078 amendment A3): the whole list, because nothing stores which child is a daughter | the side of a child is stored nowhere |
| «¿Cuál es el nombre de mi papá?» / «… de mi mamá?» | `protected_household` («todavía no está conectada») | shape missing from `_RELATIVE_SHAPES` |
| «¿Cómo se llama mi papá?» / «mi mamá?» | `relatives_names`, `has_parent`: both parents | the mother is not told from the father |
| «¿Qué hice ayer?» / «la semana pasada?» | `recall.strong`, a window and no words: that window's episodes | none (Task 0 may prove otherwise) |
| «¿Cuándo fui a la playa?», «¿cuándo estuve en…?», «¿cuándo hablamos de…?» | `generic_conversation`: the model, which holds no memory and can invent | no recall cue |
| «¿Te acuerdas cuándo fui a la playa?», «¿cuándo te conté de la playa?» | `recall.weak`, `recall.strong`, answered by the model's wording of the found text | no date answer |

Also read in code: `recall_search.search_recall` filters ids, awaits the embedding call, then reads
the text with `recall_store.units_by_id`, which re-applies **nothing** (no owner, class or expiry).
[ADR 0031](../../adr/0031-the-memory-engine-boundary.md) *Context* item 8; decision 2 asks that the
read that hands the text over re-apply them.

## Decisions

Fill in what the ADRs leave to the builder; confirmed when Pipec promotes the plan.

- **D-1 No migration.** Verified: `predicate` is free `TEXT` in `literal_facts_v4` and
  `entity_relations_v4` (migration 004, no `CHECK` on it), so two new relation predicates are
  registry entries only; the admin audit reuses `operation = 'change'` and
  `target_kind = 'pool_relation'` (migration 012 allows both). The four new predicates of D-4 are
  registry entries only. Task 0 re-verifies this. **If any
  task finds it needs a migration of V4 or of the audit, stop and tell Pipec before writing it.**
- **D-2 Off is byte-identical.** Every new shape, cue and branch sits behind `recall=True` /
  `RECALL_ENABLED`; with it off every route, phrase and log line of today is unchanged
  (`tests/fixtures/recall_routes.yaml` keeps its `today` column).
- **D-3 «El nombre de mi X».** `_RELATIVE_SHAPES` gains `cual es el nombre de mi`,
  `cuales son los nombres de mis`, `dime el nombre de mi`, `dime los nombres de mis`. The recall-only
  child rule gains the same shapes for `hijo` and `hija`: «¿cuál es el nombre de mi hija?», «dime el
  nombre de mi hijo». The **plural** («mis hijos») keeps answering the whole list
  (`own_children_list`); the **singular** «mi hijo» / «mi hija» (today also the list) now asks for
  one side (D-4). They are requests, not
  mentions: the message must **open** with the shape after the leading fillers (Plan 0077's lesson;
  `opens_with`), so a story never matches. Task 0 may add shapes; each is one corpus row.
- **D-4 The side of a relative is a relation, never an attribute (one concept for parents and
  children).** The canonical writer lets a fact be stored only about the owner, a minor child or a
  pet; about a parent, a partner or an **adult child** it keeps «name and relationship only» (ADR
  0022 decision 4, ADR 0024 decisions 9 and 10). A `sex` literal would therefore be refused for
  every parent and for an adult child, so a side is stored as a **relationship**:
  - Parents: new pool relations `has_mother` and `has_father` (alias `tiene_madre`, `tiene_padre`;
    `personal`, `normal`, like `has_parent`), from the owner to the parent. `has_parent` stays and
    now means **a parent whose side is not recorded** (everything loaded before this plan).
  - Children: new membership relations `daughter_of` and `son_of` (alias `hija_de`, `hijo_de`),
    from the child to the owner, like `child_of`, `household` with the registry's sensitivity. They
    are a **marker added to** the one `child_of` row, never a replacement: every reader of
    `child_of` (the list, the count, the birthdays, the adult fence) is untouched. The writer's
    `_MEMBERSHIP_PREDICATES` gains both; the same fences apply (the owner at the owning end, a
    relative cannot become a child, an adult child may carry the marker because it is a
    relationship). A child may hold at most one of the two.
  - Words: `relation_of` returns `has_mother` for `mama`/`madre`, `has_father` for `papa`/`padre`,
    `has_parent` for `papas`/`padres` and when one message names both a mother word and a father
    word; for the singular child words it returns `daughter_of` (`hija`) or `son_of` (`hijo`) from a
    **separate** table, so `RELATIVE_WORDS` stays the same set (Plan 0079 reads it). Every other
    relation keeps its predicate.
  - One type and one sentence builder serve both: `Side` (`FEMALE`, `MALE`), `SidedNames(status,
    female, male, unlabelled)`, and `sided_sentence(group, asked, names)` with `SideGroup.PARENTS`
    or `SideGroup.CHILDREN`. The siblings and the grandparents (`hermana`, `abuela`…) keep today's
    one-name-says-both templates; the same pattern extends to them later, by need, not now.
- **D-5 What the robot says** (tuteo, no voseo; in `cognition/relatives_answers.py`, `{}` joined with
  `spanish_join`):

  | Group | Asked | Answer |
  |---|---|---|
  | Parents | mother | «Tu mamá se llama {}.» / «Tus mamás se llaman {}.» |
  | Parents | father | «Tu papá se llama {}.» / «Tus papás se llaman {}.» |
  | Parents | all (a plural question) | «Tus papás se llaman {}.» (one name: today's «Tu papá o tu mamá se llama {}.») |
  | Children | daughter | «Tu hija se llama {}.» / «Tus hijas se llaman {}.» |
  | Children | son | «Tu hijo se llama {}.» / «Tus hijos varones se llaman {}.» |

  Asked for one side that has no row **and** some member of the group has no side: «No tengo claro
  cuál de ellos es tu mamá. Tus papás se llaman {}.» (`tu papá`; for the children «… es tu hija.
  Tus hijos son {}.», `tu hijo`), naming every member. No member at all, or the asked side absent
  while every member has the other side: the existing «No tengo registrado eso.». The whole list of
  children («¿quiénes son mis hijos?») is untouched. A stranger, a refused speaker and two faces hear
  the same refusal as every relatives question, whatever is stored.
- **D-6 The seed file.** Parents: two optional single-person tables beside `partner`, `mother` and
  `father` (`SeedPerson`), written as `has_mother` / `has_father` with roles `SeedRole.MOTHER` /
  `SeedRole.FATHER`; `parents` stays (a person whose side is not known). Children: an optional
  `side = "daughter" | "son"` key on each `[[children]]` entry (allowed for a minor and for an
  adult child), written as `daughter_of` / `son_of` next to the `child_of` row. **No new
  validator:** the two tables join `_people()`, the one walk of the circle that `_name_problems`
  already uses, so the existing closed `duplicate_name` refusal (`field.path: reason`, no value)
  covers every pair — the owner, the partner, a child, a parent, a grandparent, a sibling, a
  grandchild, and `mother` against `father` — and a pet named like either. A contact may be the same
  person as the mother or the father (the importer already merges one folded name into one entity).
  Like `parents`, the two tables belong to **no** section of `sections_with_items` (the household
  section is partner, children and pets): a file holding only `[mother]` leaves that section's
  status as the file says, and `status.household = "provided"` with nothing else is still refused
  `status_without_items`. This is deliberate and pinned by a test.
- **D-7 `iroko-admin label-parent` and `label-child`.** The household that is already loaded
  (Pipec's alta holds unlabelled `has_parent` rows and children with no marker) needs a way to say
  which is which. `label-parent <relation_id> mother|father` takes an **active `has_parent` row of
  the owner** by id (from `list`), writes the `has_mother` / `has_father` relation to the same
  person and revokes the `has_parent` row in one transaction. `label-child <relation_id>
  daughter|son` takes an **active `child_of` row of the owner** and writes the `daughter_of` /
  `son_of` marker for the same child (nothing is revoked; a child that already holds the other
  marker is refused, the operator revokes it first). Both ask the owner's PIN (a third party),
  audit `change` / `pool_relation` with the new predicate as `field_id` and no value, and refuse a
  row that is not what the verb says. `list` prints the other person's display name beside every
  relation (the relative, or the child), this terminal only, like the facts' values, so the
  operator can tell the ids apart. Adding a new relative after the alta stays the roadmap row
  *Local admin follow-ups*.
- **D-8 The «cuándo» cue.** A recall question whose body **opens with «cuando»**, directly or after
  one weak cue phrase («¿te acuerdas cuándo…?»), carries `RecallCue.when`, one of two closed values
  (`WhenKind.TOLD`, `WhenKind.HAPPENED`; `None` for every other question). It is `TOLD` when the
  message holds one of the strong phrases already in the grammar («cuándo te conté…», «te dije»,
  «te comenté»…) or the verb `hablamos` (the robot is part of «nosotros»); otherwise `HAPPENED`. A
  bare «cuándo» question is a cue only when it carries a first-person past verb of the closed list
  `fui fuimos estuve estuvimos hable hablamos hice hicimos vi vimos visite visitamos viaje viajamos
  sali salimos comi comimos compre compramos jugue jugamos conoci conocimos` (it is then
  **strong**: nobody asks general knowledge with «fui»), or one of the strong phrases. The verbs
  join `_STOP_WORDS`, so they never count as a shared
  content word of the lexical gate (they would match every story), but they stay in the text that
  is embedded. «¿Cuándo fue el mundial de 2010?» has no such verb: not a cue, ordinary
  conversation. «Cuando fui a la playa me quemé» is not a question: ordinary conversation. Task 0
  extends the list from Pipec's real phrases.
- **D-9 What a «cuándo» answer reports** (the minimum ADR 0031 decision 5 leaves to this plan):
  **the day it was told, and it says so; never a date of the event**. There is no `occurred`
  column and no migration: the unit stores only `said_at`, and the robot never invents an occurred
  date. The two questions are different, so the two answers are (review of 2026-11-09):
  «¿cuándo **te conté** que fui…?» (`TOLD`) is answered by the told day itself, and
  «¿cuándo **fui** a la playa?» (`HAPPENED`) says first that the date is not recorded. The answer is
  deterministic (no model call, so the 3B model cannot turn «me lo contaste» into «fuiste») and
  uses the first hit, with `{día}` the lowercase `date_label` of `said_at` («ayer», «el martes», «el
  3 de marzo»):

  | Kind | `turn` unit | `episode` unit |
  |---|---|---|
  | `TOLD` | «{Día} me contaste esto: {words}» | «{Día} hablamos de eso.» |
  | `HAPPENED` | «No tengo registrado cuándo fue. Sí recuerdo que {día} me contaste esto: {words}» | «No tengo registrado cuándo fue. Sí recuerdo que {día} hablamos de eso.» |

  `{words}` are the owner's own words, which keep whatever they said about when it happened («el
  sábado fui a la playa»). Nothing found keeps today's rule: a strong cue says «No me acuerdo de
  eso.», a weak one converses.
- **D-10 The delivery filters.** `units_by_id(ids, *, owner_entity_id, now)` re-applies the
  readable filters of every other read (owner, `personal`, `normal`, record not expired) in the
  same statement that returns the text. A unit raised to `medical` or expired between the search
  and the read is dropped. Accepted residual, stated in the docs: text already read is not recalled
  while the model words the answer (seconds); the decision-2 requirement is that the read that
  returns the text applies the filters.
- **D-11 Task 0 is a real-speech session, outcomes only.** About 20 phrases (below), said by Pipec to
  the real server. Each failure is sorted into **STT** (what was heard differs from what was said in
  a word the grammar needs), **intention** (heard right, the route is not the expected need),
  **retrieval** (a recall route, a story was told, nothing or the wrong thing found) or
  **generation** (found, answered wrong, in the owner's first person, invented). A small script
  prints one line of closed values per turn from `logs/server.log`; Pipec writes the heard text and
  the sorting in a local, untracked sheet (`project-history/`). Tracked: counts per stage and the
  failing **shapes**, rewritten with invented canaries (`Zeta`, `Omega`), never a name, date or
  place of the household. A failure of the STT stage that a tolerance would only catch by also
  catching a story is recorded and left (Plan 0069 owns STT tuning).

## Global constraints

- English code, comments and docstrings (Google style); Spanish only in user-facing strings;
  **no voseo** (`tests/unit/test_no_voseo_in_spoken_strings.py`).
- No `Any`, no `print` (the `scripts/` entry point writes through a passed callable like
  `admin_cli`), no `os.path`, no bare `except`; logging with `%`; settings only through `settings`.
- **No text in any log line** and no stored value in a log, an audit row or an exception message;
  the recall log line gains one closed value (`when`: `told`, `happened` or none) and nothing else.
- The generic prompt reads no household store (`test_the_generic_prompt_reads_no_household_store`);
  the recall prompt receives only the found units.
- A relatives or recall answer never enters continuity (ADR 0028 decision 8) and the record keeps
  the existing markers.
- Nothing is invented: a date the robot says is the day a unit was **said**, labelled «me
  contaste».
- No real household data anywhere in a tracked file: canaries only (`Zeta`, `Omega`, `Canary`).
- `LOG_CONVERSATION_TEXT=true` (Plan 0052: a deliberate, local, debug-only exception that prints
  what was heard and spoken on the console and never in the JSON log) is used only in a consented
  sitting of Pipec's, goes back to `false` when the sitting ends (checked in `.env`), and no
  console capture is shared or pasted anywhere; the PR and the records hold closed values only.

## Review focus

Inputs the ADRs imply and no task title names; each has its test in the task that owns it.

1. A unit reclassified `medical`, or whose record expires, between the search and the read is not
   delivered, in the lexical and in the vector path (Task 1).
2. «¿Cuál es el nombre de mi mamá?» in a household whose parents were loaded without a side: the
   honest fallback of D-5, never a labelled name that was not recorded (Task 3).
3. «¿Cuándo fue el mundial de 2010?» and «Cuando fui a la playa me quemé» stay ordinary
   conversation, and «¿cuándo fui a Zeta?» with nothing told says «No me acuerdo de eso.» instead
   of asking the model; and «¿cuándo fui a la playa?» never answers as if the told day were the
   day of the trip (Task 7).
4. `label-parent` and `label-child` on the wrong row (a sibling, the other verb's row, a revoked
   row, another owner's, an unknown id), twice on the same row, or without the PIN: refused or a
   no-op, never a second active label (Task 6).
5. A visitor, an unknown face or two faces asking «¿cuál es el nombre de mi papá?» or «de mi
   hija»: the standard refusal, never the name and never «No tengo registrado eso.» (Tasks 3 and 4).
6. An **adult** child with a side: stored (a marker is a relationship) while every other fact about
   an adult child is still refused (Tasks 4 and 5).

## File structure

| File | Responsibility | Task |
|---|---|---|
| `scripts/mvp_session_report.py` (new), `tests/unit/test_mvp_session_report.py` (new) | One line of closed values per turn from the server log | 0 |
| `memory/recall_store.py`, `memory/recall_search.py`, `tests/integration/test_recall_search.py` | The delivery filters | 1 |
| `cognition/recall_cues.py`, `cognition/intent_resolution.py`, `tests/fixtures/recall_routes.yaml`, `tests/unit/test_recall_cues.py` | «El nombre de mi X» shapes | 2 |
| `memory/predicate_registry.py`, `memory/canonical_writer.py`, `cognition/household_tools.py`, `cognition/relatives_answers.py` (new), `cognition/controller.py`, `cognition/recall_cues.py` | The mother and the father: registry, reader, shared side types, answers, routing | 3 |
| the same files, plus `cognition/intent_resolution.py`, `tests/fixtures/recall_routes.yaml` | The daughter and the son: markers, reader, routing | 4 |
| `memory/seed_file.py`, `memory/seed_members.py`, `memory/seed_plan.py`, `docs/examples/*` | The seed fields (parents and children) | 5 |
| `admin_cli.py`, `memory/admin_ops.py` | `label-parent`, `label-child`, names in `list` | 6 |
| `cognition/recall_cues.py`, `memory/recall_answer.py`, `memory/recall_access.py` | The «cuándo» cue and answer | 7 |
| `docs/…`, `tests/unit/test_architecture_guards.py` | Guards, truth, acceptance, close | 8 |

---

### Task 0: Re-audit, baseline and the real-speech session

**Files:** Create `scripts/mvp_session_report.py`, `tests/unit/test_mvp_session_report.py`,
`docs/evals/0080-mvp-recall-session.md`.

- [ ] **Step 1:** `git checkout main && git pull`, then `git checkout -b feat/0080-mvp-recall`.
  Verify against the code and **stop and report** if any is false: D-1 (no `CHECK` on `predicate`
  in migration 004; migration 012 allows `change` and `pool_relation`); `units_by_id` has no
  filters and is called only by `recall_search`; `relation_of`, `_RELATIVE_SHAPES`,
  `_OWN_CHILD_NAME_PATTERNS` and `classify_recall_cue` are as quoted above; `controller._relatives_plan`
  reads through `HouseholdKnowledgeTools.get_relatives`; `tests/fixtures/recall_routes.yaml` is read
  by `tests/unit/test_recall_cues.py`; **for D-4:** `_membership_refusal` stores `daughter_of` from an
  adult child to the owner without widening what is stored about adults (try it in a throwaway
  test: if it refuses, **stop and report**, Task 4 needs Pipec's decision), `_child_ids` and the
  children list's consent are the ones Task 4 reuses, and no code reads `child_of` in a way a second
  row to the same pair would break. Re-run the throwaway resolution of the table above (script in
  the scratchpad, phrases in a file) and attach the output to the PR.
- [ ] **Step 2:** Baseline: `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and not eval" -q -n auto`;
  write the count in the PR.
- [ ] **Step 3: Write the failing test** `tests/unit/test_mvp_session_report.py` with invented JSON
  log lines (the shape of `logs/server.log`: `ts`, `level`, `logger`, `msg`, `event`, `request_id`
  and the event's own fields): `test_a_turn_is_one_row_of_closed_values` (events `stt.transcribed`
  `chars=21`, `turn.decision` `need=relatives_names status=known source=deterministic llm_ms=0`,
  `recall.read` `outcome=found route=strong hits=2 best_distance=0.395` → one `TurnRow` with those
  values), `test_a_turn_without_a_plan_is_generic` (`turn.decision` with
  `outcome="no-plan-channel-generates"` → `need="generic_conversation"`),
  `test_lines_before_since_and_other_requests_are_ignored`, and
  `test_a_row_never_carries_a_message_text` (a line whose `msg` holds a canary sentence: the
  canary is absent from `repr(row)` and from the printed output).
- [ ] **Step 4:** Run → FAIL (module missing).
- [ ] **Step 5: Implement** `scripts/mvp_session_report.py`:
  `@dataclass(frozen=True) class TurnRow(ts: str, request_id: str, stt_chars: int | None,
  need: str, status: str | None, source: str | None, recall_outcome: str | None,
  recall_hits: int | None, best_distance: float | None)`;
  `def summarize_turns(lines: Iterable[str], *, since: str) -> list[TurnRow]` (groups by
  `request_id`, keeps closed fields only, drops lines that are not JSON);
  `def main(argv: Sequence[str] | None = None) -> int` with `--log` (default `logs/server.log`) and
  `--since` (ISO time), printing one aligned line per row through a `write_text` callable.
- [ ] **Step 6:** Run → PASS; `uv run ruff check scripts/mvp_session_report.py`,
  `uv run ruff format --check scripts/mvp_session_report.py`, `uv run pyright`.
- [ ] **Step 7: The session (Pipec runs it; the agent starts nothing).** `.env`: memory, record,
  diary, `RECALL_ENABLED=true`, face and speaker on, `LOG_CONVERSATION_TEXT=true`. Part A: Pipec
  tells **three stories of at least 4 seconds each** (the owner's voice verifies on 58 % of turns
  over 3 s and on 7 % of short ones, Plan 0075; one story is about a beach trip) and checks in the
  log that each turn was captured. Part B: the 20 phrases, one request each, on today's `main`:
  children ×4 («¿quiénes son mis hijos?», «¿cómo se llaman mis hijos?», «¿cómo se llama mi hija?»,
  «¿cuál es el nombre de mi hijo?»); parents ×5 («¿cuál es el nombre de mi papá?», «… de mi mamá?», «¿cómo se llama mi
  papá?», «¿cómo se llaman mis papás?», «dime el nombre de mi mamá»); days ×3 («¿qué hice
  ayer?», «¿qué hice la semana pasada?», «¿qué hice el sábado?»); when ×5 («¿cuándo fui a la
  playa?», «¿cuándo estuve en la playa?», «¿cuándo hablamos de la playa?», «¿cuándo te conté de la
  playa?», «¿te acuerdas cuándo fui a la playa?»); traps ×4 («cuando fui a la playa me quemé»,
  «¿cuándo fue el mundial de 2010?», «¿cuándo nació mi hijo?», «¿qué sabes de mí?»). Then
  `uv run python scripts/mvp_session_report.py --since <start>`; Pipec fills his local sheet with
  the heard text and the failing stage of each turn (D-11). **When the sitting ends,
  `LOG_CONVERSATION_TEXT` goes back to `false`** (the global constraint above); nothing from the
  console is shared.
- [ ] **Step 8:** Write `docs/evals/0080-mvp-recall-session.md` (outcomes only: setup, the table of
  counts per stage, the failing **shapes** with canaries, what each later task takes from it; no
  transcript, name, date or place). Add every new shape the session found as a
  failing corpus row in the task that owns it (Tasks 2, 3, 4, 7), and extend D-3 / D-8's lists there.
  It also lists, for each question of the session, the phrase that worked and the one that failed:
  a first table of **canonical phrases**, the seed of the spoken-command decision recorded in the
  roadmap (Task 8), not a commitment of this plan.
  `uv run python scripts/check_reserved_terms.py`.
- [ ] **Step 9:** commit the script and its test:
  `test: tabulate one line per turn from the server log (plan 0080)`; then commit the record:
  `docs: record the MVP phrase session, outcomes only (plan 0080)`.

---

### Task 1: The delivery filters (the race, RED first)

**Files:** Modify `memory/recall_store.py:358-370`, `memory/recall_search.py:207`; Test
`tests/integration/test_recall_search.py`.

**Interfaces:** Produces `units_by_id(ids: Sequence[int], *, owner_entity_id: int, now: str) ->
list[RecallUnit]` (the units still readable, in the order given). Consumes `_READABLE` and the
`now_iso` already built in `search_recall`.

- [ ] **Step 1: Write the failing tests** next to `test_a_record_deleted_mid_search_drops_its_units`
  (same fixtures `owners`, `embed`, `_record`, `_unit`, `_search`, `_cue`):
  `test_a_unit_reclassified_mid_search_is_not_delivered` (two units of one record with words
  matching the cue; wrap `recall_search.ollama_embed` with an async double that, while "embedding",
  runs `UPDATE recall_units SET sensitivity = 'medical' WHERE id = :first` in `db.transaction()`
  and returns `_axis(0)`; assert `_ids(found) == [second]`);
  `test_a_unit_whose_record_expired_mid_search_is_not_delivered` (same wrapper, but
  `UPDATE conversation_records SET expires_at = '2026-11-01T00:00:00.000000+00:00' WHERE id = :record`;
  `_NOW` is 2026-11-04; assert the expired record's unit is absent); and
  `test_the_same_holds_when_only_the_words_found_it` (the embedding double raises
  `httpx.ConnectError`, so the search is lexical only, and the wrapper of `lexical_hits` reclassifies
  after the ids were read; assert absent); and
  `test_another_owners_unit_ids_are_never_returned` (call `recall_store.units_by_id` directly with
  the ids of a unit of each owner mixed, for each owner in turn: only that owner's unit comes back;
  RED today, because the read has no owner filter: it is the owner filter's own test).
- [ ] **Step 2:** `MEMORY_ENABLED=false uv run pytest tests/integration/test_recall_search.py -q` →
  the three new tests FAIL because the reclassified or expired unit is returned (copy the output
  into the PR as the reproduction).
- [ ] **Step 3: Implement** `units_by_id` with the new keywords: one statement joining
  `conversation_records r` and filtering by `_READABLE` (with `:since` and `:until` bound to
  `NULL`), `u.id IN (…)`; keep the order of *ids*. Pass `owner_entity_id` and `now_iso` from
  `search_recall`. Update the docstring (what is re-applied, and the D-10 residual).
- [ ] **Step 4:** Run the whole file and `tests/integration/test_recall_store.py`,
  `tests/integration/test_recall_index.py`, `tests/integration/test_recall_routes.py` → PASS.
- [ ] **Step 5:** commit `fix: re-read owner, class and expiry when a recalled unit is read (0080)`.

---

### Task 2: «El nombre de mi X»

**Files:** Modify `cognition/recall_cues.py:72-83`, `cognition/intent_resolution.py:231-238`,
`tests/fixtures/recall_routes.yaml`, `tests/unit/test_recall_cues.py`.

**Interfaces:** Produces the new shapes of D-3 inside `relation_of` and `_own_child_name_rule`.
No signature changes. Until Task 4 the singular child shapes still answer the children list, as
today.

- [ ] **Step 1: Write the failing corpus rows** (`need` with recall on, `today` with it off):
  «¿Cuál es el nombre de mi papá?» → `relatives_names` / `protected_household`; «¿Cuál es el nombre
  de mi mamá?»; «Dime el nombre de mi mamá» (same); «¿Cuáles son los nombres de mis hermanos?»;
  «¿Cuál es el nombre de mi perro?» → `relatives_names`; «¿Cuál es el nombre de mi hijo?», «Dime
  el nombre de mi hija», «¿Cuáles son los nombres de mis hijos?» → `own_children_list` /
  `protected_household`; the traps «Mi mamá se llama Zeta y cocina rico», «No sé cuál es el nombre
  de mi tía», «¿Cuál es el nombre de la calle de mi hijo?» → `generic_conversation` /
  `protected_household` as the corpus runner reports for each (record the observed `today`, it is
  main's route); plus every shape Task 0 found for this family. In `test_recall_cues.py` add
  `relation_of` rows for the four new shapes (`mama` → today's predicate, replaced in Task 3).
- [ ] **Step 2:** Run `tests/unit/test_recall_cues.py` → FAIL on the new rows.
- [ ] **Step 3: Implement** the shapes (`_RELATIVE_SHAPES`, `_OWN_CHILD_NAME_PATTERNS`); the child
  patterns stay in the recall-only rule so flag-off is untouched. Keep the «opens the sentence»
  rule of D-3 (`opens_with` over the shape for every new one).
- [ ] **Step 4:** Run `tests/unit/test_recall_cues.py tests/unit/test_relatives_plan.py
  tests/integration/test_recall_routes.py` → PASS (the `today` column proves D-2).
- [ ] **Step 5:** commit `feat: answer 'the name of my X' as a relatives question (plan 0080)`.

---

### Task 3: The mother and the father in the answer

**Files:** Create `cognition/relatives_answers.py`; Modify `memory/predicate_registry.py:174-177`,
`memory/canonical_writer.py:98`, `cognition/household_tools.py`, `cognition/controller.py:540-570,857-870`,
`cognition/recall_cues.py:84-105,192-208`; Test `tests/unit/test_predicate_registry.py`,
`tests/unit/test_recall_cues.py`, `tests/unit/test_relatives_answers.py` (new),
`tests/unit/test_relatives_plan.py`, `tests/integration/test_relatives_reader.py`,
`tests/integration/test_canonical_writer_fence.py`.

**Interfaces:**

- Produces `has_mother`, `has_father` in `POOL_PREDICATE_IDS`; `relation_of(message) -> str | None`
  returning `has_mother | has_father | has_parent | has_sibling | has_grandparent | has_grandchild |
  partner_of | pet_of` (the child sides come in Task 4).
- Produces the shared types of D-4: `class Side(StrEnum): FEMALE = "female"; MALE = "male"`,
  `class SideGroup(StrEnum): PARENTS = "parents"; CHILDREN = "children"` and
  `@dataclass(frozen=True) class SidedNames(status: KnowledgeStatus, female: tuple[str, ...], male:
  tuple[str, ...], unlabelled: tuple[str, ...])` (names hidden from `repr`) in
  `cognition/household_tools.py`.
- Produces `async HouseholdKnowledgeTools.get_parents(*, owner_entity_id: int, actor:
  ActivePersonContext, consent: ConsentStatus, correlation_id: UUID, requested_at: datetime) ->
  SidedNames`: `UNAUTHORIZED` on any denial, `UNKNOWN` with no parent of any kind, else `KNOWN`;
  it authorizes and audits as `get_relatives` does for `has_parent`, then reads the three
  predicates (`has_mother` → `female`, `has_father` → `male`, `has_parent` → `unlabelled`).
- Produces in `cognition/relatives_answers.py`: `relatives_sentence(predicate: str, names:
  tuple[str, ...]) -> str` (moved from `controller.py`, same templates) and
  `sided_sentence(group: SideGroup, asked: Side | None, names: SidedNames) -> str | None`
  implementing the table of D-5 (`asked=None` is the plural question; `None` is returned when the
  controller must say «No tengo registrado eso.»).

- [ ] **Step 1: Write the failing tests.**
  `test_predicate_registry.py`: the pool set equals today's plus `{"has_mother", "has_father"}`; both
  resolve by alias; neither is symmetric. `test_canonical_writer_fence.py`: a `has_mother` row to an
  entity that is a child or the partner is refused `ROLE_CONFLICT` like `has_parent`.
  `test_recall_cues.py`: `relation_of` rows — «¿cómo se llama mi mamá?» and «¿cuál es el nombre de
  mi madre?» → `has_mother`; «mi papá», «mi padre» → `has_father`; «¿cómo se llaman mis papás?»,
  «¿quiénes son mis padres?» → `has_parent`; a message naming both words («¿cuáles son los nombres
  de mi mamá y de mi papá?» is only pinned if Task 0 found it) → `has_parent`.
  `test_relatives_answers.py` (the PARENTS rows of D-5, one assertion each):
  `sided_sentence(SideGroup.PARENTS, Side.FEMALE, SidedNames(KNOWN, female=("Zeta",),
  male=("Omega",), unlabelled=()))` is «Tu mamá se llama Zeta.»; `Side.MALE` → «Tu papá se llama
  Omega.»; `asked=None` with both → «Tus papás se llaman Omega y Zeta.» (sorted, `spanish_join`);
  `asked=None` with one unlabelled name → «Tu papá o tu mamá se llama Zeta.»; `Side.FEMALE` with
  `unlabelled=("Omega", "Zeta")` → «No tengo claro cuál de ellos es tu mamá. Tus papás se llaman
  Omega y Zeta.»; `Side.MALE` with `female=("Zeta",)` and nothing else → `None`; no parent of any
  kind → `None`. `test_relatives_plan.py`: with the household tools double returning `SidedNames`, a
  mother question speaks the mother; a stranger and two faces get
  `_PROFILE_SUMMARY_UNKNOWN_RESPONSE` and the double is **not** called.
  `test_relatives_reader.py` (real SQLite, canaries): `get_parents` over a household with one
  `has_mother`, one `has_father` and one `has_parent` returns each in its group and writes the same
  authorization audit rows `get_relatives` writes; an owner with no parent → `UNKNOWN`; a denied
  actor → `UNAUTHORIZED`.
- [ ] **Step 2:** Run those files → FAIL for the missing predicates, types, function and module.
- [ ] **Step 3: Implement.** Registry: two `_pool_relation` entries; writer: both ids in
  `_RELATIVE_PREDICATES`; `relation_of` per D-4 (singular and plural words split; both gendered
  words → `has_parent`); `household_tools`: the three types and `get_parents` reusing
  `_authorize_tool`, `_required_predicate` and the label reader of `get_relatives`; the new module
  with the moved templates and `sided_sentence` (the strings of D-5 as module constants);
  `controller._relatives_plan`: after the actor and the consent are resolved, a predicate in
  `{has_mother, has_father, has_parent}` goes through `get_parents` and `sided_sentence`
  (`None` → `NOT_REGISTERED`), every other predicate through `get_relatives` as today.
- [ ] **Step 4:** Run the six files above, then
  `uv run pytest tests/unit/test_no_voseo_in_spoken_strings.py tests/unit/test_architecture_guards.py
  tests/integration/test_recall_routes.py -q` → PASS.
- [ ] **Step 5:** commit `feat: tell the mother from the father in parent answers (plan 0080)`.

---

### Task 4: The daughter and the son in the answer

**Files:** Modify `memory/predicate_registry.py`, `memory/canonical_writer.py:96`,
`cognition/household_tools.py`, `cognition/recall_cues.py`, `cognition/intent_resolution.py:364-376`,
`cognition/relatives_answers.py`, `cognition/controller.py:540-570`,
`tests/fixtures/recall_routes.yaml`; Test `tests/unit/test_predicate_registry.py`,
`tests/unit/test_recall_cues.py`, `tests/unit/test_relatives_answers.py`,
`tests/unit/test_relatives_plan.py`, `tests/integration/test_relatives_reader.py`,
`tests/integration/test_canonical_writer_fence.py`.

**Interfaces:**

- Produces `daughter_of`, `son_of` in the registry: the **same definition as `child_of`** (subject
  and target `person`, `household`, the same default sensitivity, a relation, not symmetric) with
  aliases `hija_de` and `hijo_de`; both ids join `_MEMBERSHIP_PREDICATES`.
- Produces `async HouseholdKnowledgeTools.get_children_by_side(*, parent_entity_id: int, actor:
  ActivePersonContext, consent: ConsentStatus, correlation_id: UUID, requested_at: datetime) ->
  SidedNames`, composed like `get_children_birthdays` (the `child_of` read of `get_children`, then
  the marker read per child through the same authorized reader), so no new policy path exists:
  `daughter_of` → `female`, `son_of` → `male`, a child with neither marker, or with both,
  → `unlabelled`.
- `relation_of` returns `daughter_of` for the singular `hija` and `son_of` for `hijo` after the same
  shapes (D-3), from a table separate from `_RELATION_WORDS` (so `RELATIVE_WORDS` does not change).
  `_own_child_name_rule` resolves them to `InformationNeed.RELATIVES_NAMES` (rule id
  `own_children.name.v1` kept); the plural keeps `own_children_list`.
- `sided_sentence(SideGroup.CHILDREN, …)` implements the CHILDREN rows of D-5.

- [ ] **Step 1: Write the failing tests.** Registry: the two predicates resolve by alias, share
  `child_of`'s visibility and sensitivity, are not symmetric. `test_canonical_writer_fence.py`:
  `daughter_of` from a minor child and from an **adult** child to the owner is stored (the marker is a
  relationship); from the partner, from a relative and from an entity that is no child of the owner
  it is refused as `child_of` is; an exact repeat is a no-op. `test_recall_cues.py`: «¿cómo se llama
  mi hija?», «¿quién es mi hijo?», «¿cuál es el nombre de mi hija?», «dime el nombre de mi hijo» →
  `daughter_of` / `son_of`; «¿cómo se llaman mis hijos?» is **not** a `relation_of` question.
  Corpus: those singular rows change from `own_children_list` to `relatives_names` (`today` column
  unchanged: the flag-off route of `main`), the plural rows stay `own_children_list`, and the traps
  «Mi hija se llama Zeta y baila» and «¿Dónde baila mi hija?» stay as they are.
  `test_relatives_answers.py` (the CHILDREN rows): `Side.FEMALE` with `female=("Zeta",)` → «Tu hija se
  llama Zeta.»; `Side.MALE` with `male=("Omega",)` → «Tu hijo se llama Omega.»; two daughters → «Tus
  hijas se llaman Omega y Zeta.»; two sons → «Tus hijos varones se llaman …»; `Side.FEMALE` with
  `unlabelled=("Omega", "Zeta")` → «No tengo claro cuál de ellos es tu hija. Tus hijos son Omega y
  Zeta.»; `Side.FEMALE` with only `male` set → `None`. `test_relatives_plan.py`: a daughter question
  speaks the daughter; a stranger and two faces get the refusal and the double is not called.
  `test_relatives_reader.py` (real SQLite, canaries): `get_children_by_side` over two children, one
  with `daughter_of`, one with `son_of`, plus a third with no marker and a fourth with both markers
  (→ `unlabelled`); the same audit rows as `get_children`; a denied actor → `UNAUTHORIZED`; no
  children → `UNKNOWN`.
- [ ] **Step 2:** Run those files → FAIL.
- [ ] **Step 3: Implement** the registry entries (copying `child_of`'s definition), the writer set,
  `get_children_by_side`, the child words table and the rule, the CHILDREN rows of `sided_sentence`,
  and the controller branch: a predicate in `{daughter_of, son_of}` goes through
  `get_children_by_side` with **the consent the children list already uses** (`controller.py`, the
  `OWN_CHILDREN_LIST` branch) and `sided_sentence(SideGroup.CHILDREN, …)`. Update the docstring of
  `_own_child_name_rule` (Plan 0078 amendment A3 is superseded for the singular).
- [ ] **Step 4:** Run the files above and `tests/integration/test_recall_routes.py
  tests/unit/test_cognitive_controller.py` → PASS (the `today` column proves D-2).
- [ ] **Step 5:** commit `feat: tell the daughter from the son in child answers (plan 0080)`.

---

### Task 5: The seed file carries the sides

**Files:** Modify `memory/seed_file.py:78-92`, `memory/seed_members.py:161-182`,
`memory/seed_plan.py:60-80,200-260`; Regenerate `docs/examples/seed-household.schema.json`
(`json_schema_text()`); Modify `docs/examples/seed-household.example.toml`; Test
`tests/unit/test_seed_file.py`, `tests/unit/test_seed_plan.py`, `tests/integration/test_seed_import.py`.

**Interfaces:** Consumes `SeedPerson`, `SeedChild`. Produces `SeedFile.mother: SeedPerson | None`,
`SeedFile.father: SeedPerson | None`, `SeedChild.side: Literal["daughter", "son"] | None`,
`SeedRole.MOTHER`, `SeedRole.FATHER`; `_people()` yields `mother.name` and `father.name`;
`build_plan` emits one `has_mother` / `has_father` relation from the owner for each (and creates
the person with that role), and one `daughter_of` / `son_of` relation from the child to the owner
after the `child_of` row. `sections_with_items` is unchanged on purpose (D-6).

- [ ] **Step 1: Write the failing tests.** `test_seed_file.py`: a file with `[mother] name = "Zeta"`
  and `[father] name = "Omega"` loads; a table-driven test refuses with `duplicate_name` (path
  `mother.name` or `father.name`, **no name** in the message, repr or cause) the same folded name
  — case and accent folded — as the owner, the partner, a child, `parents`, `grandparents`,
  `siblings`, `grandchildren`, and `mother` against `father`; a pet named like the mother is refused
  at `pets.0.name`; a contact with the mother's name loads (one person, one entity); a file with
  only `parents` still loads (no regression); a file with only `[mother]` loads and
  `sections_with_items` does not list `household`; `status.household = "provided"` with only
  `[mother]` is refused `status.household: status_without_items`; a child with `side = "daughter"`
  loads, one with `side = "niece"` is refused with a closed reason and no value, and an **adult**
  child with a side loads (name, guardianship and the side are allowed; any other fact is still
  `adult_child_facts`). `test_seed_plan.py`: the plan holds `create_entity` ×2 with roles
  `mother`/`father`, `write_relation` `has_mother` and `has_father` from the owner, **no**
  `has_parent`, and for a child with a side a `child_of` row followed by `daughter_of` (or `son_of`)
  from the same child to the owner. `test_seed_import.py` (real SQLite): importing the file stores
  the relations through the writer with the `import_file` channel (`personal`/`normal` for the
  parents, `household` for the markers), and the import key `…mother:zeta` makes a re-import a
  no-op. The committed schema file equals `json_schema_text()` (the existing test pins it).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement** the two optional tables and the child key, `_people()` (no new
  validator), the roles and the plan operations next to `partner` and `children`; regenerate the
  schema and add `[mother]`, `[father]` and a `side` example with canary names.
- [ ] **Step 4:** Run the three files and `tests/integration/test_seed_file_loading.py` (it pins the
  committed schema) → PASS.
- [ ] **Step 5:** commit `feat: load the sides of the family from the seed file (plan 0080)`.

---

### Task 6: `iroko-admin label-parent` and `label-child`

**Files:** Modify `memory/admin_ops.py`, `admin_cli.py:157-173,568-601`; Test
`tests/integration/test_admin_ops_write.py`, `tests/integration/test_admin_cli.py`,
`tests/integration/test_admin_reads.py`.

**Interfaces:** Consumes `write_relation`, `revoke_entity_relation`, `get_entity_relation`,
`get_person_label`. Produces `async apply_side_label(*, actor: AdminActor, owner_entity_id: int,
relation_id: int, side: Literal["mother", "father", "daughter", "son"], now: str,
owner_verified: bool, manage_transaction: bool = True) -> AdminOutcome` (a parent side needs an
active `has_parent` row, a child side an active `child_of` row; any other pairing is refused) and
the CLI verbs `label-parent <row_id> {mother,father}` and `label-child <row_id> {daughter,son}`
with `--dry-run` and `--actor` like `change-contact`.

- [ ] **Step 1: Write the failing tests** (real SQLite, canaries). `label-parent`: on an active
  `has_parent` row of the owner `APPLIED`, the row is revoked and an active `has_mother` to the same
  person exists; with `father`, `has_father`. `label-child`: on an active `child_of` row `APPLIED`,
  the `child_of` row stays active and an active `daughter_of` from the same child to the owner
  exists; `son` likewise; a child that already holds the **other** marker is refused
  (`already_labelled`), the same marker again is a no-op refusal. Refusals (`REFUSED`, a closed
  reason, an audit row, **no** write) for both: `owner_not_verified` without the PIN; the id of a
  `has_sibling` row; a `child_of` id given to `label-parent` and a `has_parent` id given to
  `label-child`; an already revoked row; a row of another owner; an unknown id. Running a verb twice
  on the same id leaves exactly one active label. A failure of the write rolls everything back. The
  audit row holds `change`, `pool_relation`, the new predicate as `field_id`, the person's entity id
  and no name. CLI: `list` prints the other person's display name beside every relation; each verb
  asks `CONFIRMAR` and the PIN, `--dry-run` writes nothing.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement** in one `db.transaction()` (or the caller's): read and validate the row,
  write the new relation through `write_relation` with `WriteChannel.ADMIN_LOCAL`, revoke the old
  `has_parent` (parents only), audit; map a closed refusal to `REFUSED` as `apply_literal_edit` does.
  Wire the verbs and the names in `list`; update the parser help text.
- [ ] **Step 4:** Run the three files plus `tests/integration/test_admin_audit.py` → PASS.
- [ ] **Step 5:** commit `feat: label parents and children with iroko-admin (plan 0080)`.

---

### Task 7: «¿Cuándo fui…?»

**Files:** Modify `cognition/recall_cues.py`, `memory/recall_answer.py`, `memory/recall_access.py`;
Test `tests/fixtures/recall_routes.yaml`, `tests/unit/test_recall_cues.py`,
`tests/unit/test_recall_answer.py`, `tests/unit/test_recall_access.py`,
`tests/integration/test_recall_routes.py`.

**Interfaces:** Produces `class WhenKind(StrEnum): TOLD = "told"; HAPPENED = "happened"` and
`RecallCue.when: WhenKind | None = None` in `recall_cues.py` (existing constructors keep working);
`word_when(hits: Sequence[RecallHit], kind: WhenKind, *, today: date, tz: ZoneInfo) -> str` in
`recall_answer.py` (pure, no model); `recall.read` gains `"when": "told" | "happened" | None`.

- [ ] **Step 1: Write the failing tests.** Corpus (`need` / `today`): «¿Cuándo fui a la playa?»,
  «¿Cuándo estuve en la playa?», «¿Cuándo hablamos de la playa?», «¿Cuándo te conté de la playa?»,
  «¿Te acuerdas cuándo fui a la playa?», «¿Y cuándo fuimos al cerro con Zeta?» → `recall` /
  `generic_conversation`; the traps «¿Cuándo fue el mundial de 2010?», «Cuando fui a la playa me
  quemé» and «¿Cuándo fui?» (nothing after the verb) → `generic_conversation` /
  `generic_conversation`; «¿Qué te conté cuando fui a la playa?» (a «what» question) → `recall` /
  `generic_conversation` with `when` none; every shape of Task 0. `test_recall_cues.py`: `when` is
  `HAPPENED` for «¿cuándo fui a la playa?», «¿cuándo estuve…?», «¿te acuerdas cuándo fui…?» and
  «¿y cuándo fuimos al cerro?»; `TOLD` for «¿cuándo te conté de la playa?», «¿cuándo te dije…?» and
  «¿cuándo hablamos de la playa?»; none for the «what» trap; the query of «¿cuándo fui a la
  playa?» still contains «fui» (it is embedded) while `content_words(query) == ("playa",)`.
  `test_recall_answer.py` (the table of D-9, one assertion per cell): `TOLD` with a `turn` hit said
  yesterday → «Ayer me contaste esto: {words}»; `HAPPENED` with the same hit → «No tengo registrado
  cuándo fue. Sí recuerdo que ayer me contaste esto: {words}»; both kinds with an `episode` hit on a
  weekday → «El martes hablamos de eso.» and «No tengo registrado cuándo fue. Sí recuerdo que el
  martes hablamos de eso.»; a hit from the current year → «el 3 de marzo»; only the first of several
  hits; no answer of either kind contains «fuiste» or «fue el», and the `HAPPENED` answer never
  states a date as the day of the event. `test_recall_access.py`: with `cue.when` set the
  answerer double (`word_recall`) is **not** called and the reply is `word_when`'s; nothing found
  with a strong cue stays `RecallReply(text=None)` and the controller still says «No me acuerdo de
  eso.». `test_recall_routes.py` (both routes, real store, embedding and model doubles): the beach
  story told yesterday, «¿cuándo fui a la playa?» → the `HAPPENED` answer and «¿cuándo te conté de
  la playa?» → the `TOLD` answer, and the generation double was not called; the same question with
  an empty store → «No me acuerdo de eso.».
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement** per D-8 and D-9: the verb list, `WhenKind` and `when` in `recall_cues`
  (strong upgrade when a bare «cuándo» carries a listed verb; the verbs into `_STOP_WORDS` only for
  the lexical gate), `word_when` reusing `_template`'s label logic, and the branch in
  `recall_access._search_and_word`.
- [ ] **Step 4:** Run the five files and `tests/unit/test_recall_*.py
  tests/integration/test_recall_*.py` → PASS; with `RECALL_ENABLED` false the corpus `today`
  column is unchanged.
- [ ] **Step 5:** commit `feat: answer 'when did I...' with the day it was told (plan 0080)`.

---

### Task 8: Guards, truth, acceptance and close

**Files:** `tests/unit/test_architecture_guards.py`; `docs/architecture/current-state.md` and its
Archify diagram (validate → deliver); `docs/runbooks/operator-manual.md`;
`docs/architecture/seed-data-pool.md` (the parents row: `has_mother`, `has_father`, `has_parent`);
ADR 0024 decision 10 and ADR 0028 (*Implemented in Plan 0080* notes: the phrasings, the mother and
the father, the told-not-happened rule); ADR 0031 (*Context* item 8 first bullet stays latent for
C1, second bullet **fixed**; decision 5's minimum decided; *Not decided here* row closed);
`docs/roadmap/cognitive-roadmap.md` (the rows *MVP recall phrasings* and *Telling the mother from
the father* closed, the second renamed *the sides of the family*; step 1 of the path done and its
size corrected to medium; the voice calibration is next; a **new row, unplanned, *Spoken command
vocabulary*** (Pipec, 2026-11-09): a bounded set of canonical phrases per data question of the
alta, tolerant variants, a confirmation of near-misses and a marker such as «Iroko,», built from
the canonical-phrase table of Task 0 and the real failures, and decided by its own ADR; intonation
is not a signal, since the speech-to-text gives none and the question mark already misses 3 of 10
questions (ADR 0023));
ADR 0028 (amendment A3 superseded for the singular child question); `docs/plans/README.md`
(board and closed row), `docs/plans/open/README.md`;
`docs/evals/0080-mvp-recall-acceptance.md` (new, outcomes only); the local
`docs/roadmap/tabla-tareas.md` (git-excluded).

- [ ] **Step 1: Write the failing guards:** `test_the_relative_words_are_defined_once` (no module
  besides `recall_cues` spells the mother/father/parent word sets); `test_the_relatives_templates_live_in_one_module`
  (`controller.py` no longer defines `_RELATIVES_TEMPLATES`); `test_recall_units_are_read_only_through_the_filtered_store`
  (an allow-list of the modules that call `units_by_id`: only `recall_search`).
- [ ] **Step 2:** Run → FAIL where new; implement; run → PASS. Then the whole-project checks:
  `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and not eval" -q -n auto`,
  `uv run pyright`, `uv run mypy server/src robot/src`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run ruff check scripts/*.py`,
  `uv run python scripts/check_reserved_terms.py`; `just gate` only when Pipec is not rehearsing.
  Write the test count in the PR. Commit `test: guard the MVP recall phrasings (plan 0080)`.
- [ ] **Step 3: Hardware acceptance by Pipec** (streaming; outcomes only; **a copy of the database
  is taken first**). Phrases are only ones the grammar accepts, each tried first with a throwaway
  script. **Day 1:** (1) «¿quiénes son mis hijos?»; (2) «¿cuál es el nombre de mi mamá?» and «¿cómo
  se llama mi hija?» **before** labelling, which must give the honest fallbacks of D-5 while his
  alta holds unlabelled parents and unmarked children; then `iroko-admin label-parent` for each
  parent and `label-child` for each child (server stopped); (3) «¿cuál es el nombre de mi mamá?»,
  (4) «¿… de mi papá?», (4b) «¿cómo se llama mi hija?» and «¿… mi hijo?» (one name each),
  (5) «¿cómo se llaman mis papás?» and «¿quiénes son mis hijos?» (the whole lists, unchanged);
  (6) a long story (4 s or more)
  about the beach and, in the same sitting, «¿cuándo fui a la playa?» → «No tengo registrado
  cuándo fue. Sí recuerdo que hoy me contaste esto: …» and «¿cuándo te conté de la playa?» → «Hoy me
  contaste esto: …»; **then Pipec stops and starts the server** (the continuity slot dies with the
  process; the story must survive in the database) and asks both questions again plus «¿qué te
  conté de la playa?», which the model words from the found text; the same three answers, confirmed
  in the log as `found` recalls of the new process (the full cycle of correcting and forgetting is
  CM-6 and CM-7, not here); (7) «¿cuándo fui a la luna?» with nothing told → «No me acuerdo de eso.»; (8)
  «¿cuándo fue el mundial de 2010?» → ordinary conversation; (9) with the camera covered (or a
  second face), «¿cuál es el nombre de mi papá?» → the standard refusal; (10) «¿qué hice hoy?».
  **Day 2:** (11) «¿qué hice ayer?»; (12) «¿qué hice la semana pasada?» (if the diary holds that
  window; otherwise the expected answer is the fixed «No me acuerdo de eso.» and the retrieval half
  is proved by 10 and 11). Each case is confirmed in `logs/server.log` with
  `scripts/mvp_session_report.py` (route, `recall.read` outcome, hits). A real phrasing that missed
  the grammar becomes a corpus row and a fix commit, recorded as a count.
- [ ] **Step 4:** Update the documents above; regenerate the architecture diagram; move this plan to
  `docs/plans/completed/` with its closing status line.
- [ ] **Step 5:** commit `docs: close plan 0080, the memory MVP phrasings accepted`, push, open the
  PR, squash-merge with green CI (GitHub is delegated, Pipec 2026-11-04), delete the branch and
  return to `main`.

---

## Non-goals

The voice calibration (step 3 of the path), the prompt, block C and its forgetting, the deployment,
R2 and the embedding-model guard (C1); the `occurred` time of a story (a column, a parser of «el
verano pasado», a migration); telling a stepfather or a godmother; adding a new relative after the
alta (the *Local admin follow-ups* row); the sensitive recall of health conversations; any change to
the generic prompt, the wire, the robot, the continuity rules or the thresholds (`RECALL_MAX_DISTANCE`
stays 0.43); STT tuning (Plan 0069); the household time zone of `_recall_rule`'s `date.today()` (the
machine's day is enough to decide whether a window remains).

## Self-review (2026-11-09)

- **Scope coverage.** Task 0 session → Task 0; «nombre de mi X» and «¿cuándo fui…?» → Tasks 2 and 7;
  the mother apart from the father and the daughter apart from the son, in the answer, the alta and
  `iroko-admin` → Tasks 3 to 6 (no migration, D-1); what «cuándo» reports → D-9 and Task 7; the
  delivery race, RED first → Task 1. The excluded items are in *Non-goals*.
- **Type consistency.** `Side`, `SideGroup`, `SidedNames`, `get_parents`, `get_children_by_side`,
  `sided_sentence`, `relatives_sentence`, `apply_side_label`, `RecallCue.when`, `WhenKind`,
  `word_when` and `units_by_id(ids, *, owner_entity_id, now)` are each defined once, in the task
  that produces them, and named the same afterwards.
- **Size.** Nine working tasks after Task 0, one commit each plus one extra in Task 0 (under
  Plan 0078's twelve); no migration, no new setting, no wire or robot change. It touches the cues,
  the readers, the seed, `iroko-admin` and the answers, so it is **medium**, not small: Task 8
  changes the roadmap's size for step 1 accordingly. Tasks 1, 2 and 7 are independent of Tasks 3 to
  6, so a review may take them as two deliveries.
- **Independent review (2026-11-09).** An outside review (Pipec's) found five things; applied:
  «cuándo fui» no longer answers as if the told day were the trip (D-8, D-9, Task 7); the seed
  fields now join the one walk of the circle and the closed `duplicate_name` rule instead of a
  bespoke validator (D-6, Task 5); the size note above; the debug-log rule (global constraints,
  Task 0); the restart case and the owner-filter test (Tasks 8 and 1). Pipec then added the
  daughter and the son (Tasks 4 to 6), and the fence on adult children turned the storage of a
  side into a relationship marker instead of a `sex` literal (D-4).
- **Open for Pipec at promotion:** D-5's fallback wording, D-7's verb names (`label-parent`,
  `label-child`), D-8's verb list and D-9's one-hit, no-model answer; they are the builder's
  calls, not the ADRs'. One check can still stop the plan: if Task 0 finds that the writer cannot
  store `daughter_of` / `son_of` for an adult child without widening what is stored about adults,
  Task 4 stops and Pipec decides (an amendment of ADR 0024 decision 9).
