# 0082 — The whole alta by voice: every loaded datum reachable, and a contact's phone

> **Status:** `Draft` (2026-11-11). Written for Pipec's review from
> [ADR 0037](../../adr/0037-the-time-of-memories-and-a-contacts-phone.md) (`Proposed`), decisions
> 1 and 5 only, and the code of the branch `docs/memory-engine-adrs` at `65ea877`. It becomes
> `Ready` and `NOW` when Pipec approves it and confirms D-1 to D-12 (D-13 decided 2026-11-11); ADR 0037 stays `Proposed`
> until plans 0083 and 0084 close too (or Pipec accepts it in parts). Queue rule 4 applies at
> execution: Task 0 re-verifies every claim below against the merged code before any code, and
> **stops and reports** if one is false. Written for an executor who has not seen this repository.

> **For agentic workers:** if the status above does not say `Ready`, stop. REQUIRED SUB-SKILL:
> `superpowers:executing-plans` or `superpowers:subagent-driven-development` (Pipec chooses at
> promotion), with `superpowers:test-driven-development`,
> `superpowers:verification-before-completion` and `superpowers:finishing-a-development-branch`.
> Every subagent runs on the `sonnet` model and reads `.claude/` (CLAUDE.md and `.claude/rules/`)
> in full before touching code. **Pipec's rules win over the skills:** one plain branch from `main`
> (`feat/0082-alta-by-voice`), never a git worktree, this plan lives under `docs/plans/`. One commit
> per task; every test seen RED for the stated reason first. If evidence contradicts the plan, stop
> and report instead of redesigning. The Bash tool loses backslashes and non-ASCII characters in
> heredocs and arguments: use the Write and Edit tools, and put Spanish test phrases in YAML
> fixtures. Commit titles: Conventional Commits, at most 72 characters, check `git log` after each
> commit (the hook rejects silently); never pipe `git commit`; `git add` with explicit paths. Run the
> suite with `MEMORY_ENABLED=false` as CI does; each test that needs memory sets
> `settings.memory_enabled` itself. Never run `uv sync --all-packages --all-groups` (it removes the
> `cuda` extra). Do not run `just gate` in the background while Pipec rehearses (about 3.5 GB of
> RAM). The server and the robot are started by Pipec, never by the agent. Before pushing, run
> `pyright`, `ruff` and `mypy` over the **whole** project, lint `scripts/` with explicit paths and
> `uv run ruff format --check .` (CI also checks python blocks in `docs/*.md`).

## Decisions

Pipec's decisions are ADR 0037 decisions 1 and 5 and its table *Pipec's decisions* rows 1 and 5.
The plan's own calls below fill in what the ADR leaves to the builder; they are confirmed when Pipec
promotes the plan.

- **D-1 One reader, extended.** Everything new joins the sensitive read of Plan 0079: new members of
  `SensitiveTopic`, the same fixed order of `sensitive_reply` (two faces → `NOT_ALONE`; not the
  face-identified owner → `DENIED`; a security topic below `strong` → `RETRY_VOICE` or `DENIED`;
  consent, policy and audit row **before** the read), the same `InformationNeed.SENSITIVE_READ`,
  the same record marker `[dato sensible leído]` and the same `sensitive.read` log line. No second
  audience check, no second marker, no new need.
- **D-2 The switch.** `ALTA_READ_ENABLED` (`alta_read_enabled: bool = False`). It works only with
  `MEMORY_ENABLED` **and** `SENSITIVE_READ_ENABLED` (it extends that reader; without it there is no
  reader to extend). Off, the new phrases match nothing: every route, prompt, reply and log line is
  byte-identical to today with `SENSITIVE_READ_ENABLED` on or off.
- **D-3 The new topics, their predicates, levels and stored labels** (one closed map each, as
  today; the labels as the canonical writer stores them, checked in Task 0):

  | Topic | Predicate | Level | Label (visibility, sensitivity) |
  |---|---|---|---|
  | `IMPLANTED_DEVICE` | `implanted_device` | sensitive | `personal`, `medical` |
  | `MOBILITY` | `mobility` | sensitive | `personal`, `medical` |
  | `HEARING` | `hearing` | sensitive | `personal`, `medical` |
  | `VISION` | `vision` | sensitive | `personal`, `medical` |
  | `HEALTH_COVERAGE` | `health_coverage` | sensitive | `personal`, `private` |
  | `DWELLING_TYPE` | `dwelling_type` | sensitive | `personal`, `location` |
  | `FLOOR` | `floor` | sensitive | `personal`, `location` |
  | `LIFT` | `has_lift` | sensitive | `personal`, `location` |
  | `HOME_ACCESS` | `home_access_note` | sensitive | `personal`, `location` |
  | `LIVES_ALONE` | `lives_alone` | **security** | `personal`, `location` |
  | `CONTACT_PHONE` | — (`care_contacts`) | sensitive | `personal`, `location` (D-8) |
  | `CONTACT_CALL` | — (`care_contacts`) | sensitive | `personal`, `location` (D-8) |
  | `KEY_HOLDERS` | — (`care_contacts`) | sensitive | `personal`, `location` (D-8) |

  `TOPIC_PREDICATE` stays a map of the topics read from V4 literals; the three contact topics are
  `CONTACT_TOPICS: frozenset[SensitiveTopic]` and have no predicate. `TOPIC_LEVEL` and
  `TOPIC_LABEL` cover every topic.
- **D-4 The grammar** (folded, whole phrases, the phrase opens the sentence body after the fillers
  and openers of Plan 0079; a closed topic allows only the trailing fillers):
  `IMPLANTED_DEVICE` `que dispositivos tengo`, `que implantes tengo`, `cuales son mis dispositivos`,
  `cuales son mis implantes`, `tengo algun dispositivo`, `tengo algun implante`;
  `MOBILITY` `cual es mi movilidad`, `como es mi movilidad`, `como me desplazo`, `como me muevo`;
  `HEARING` `cual es mi audicion`, `como es mi audicion`, `como escucho`, `uso audifonos`;
  `VISION` `cual es mi vision`, `como es mi vision`, `como veo`, `uso lentes`;
  `HEALTH_COVERAGE` `cual es mi prevision`, `cual es mi prevision de salud`, `que prevision tengo`,
  `cual es mi seguro de salud`, `que seguro de salud tengo`;
  `DWELLING_TYPE` `vivo en casa o departamento`, `vivo en casa o en departamento`,
  `en que tipo de vivienda vivo`, `que tipo de vivienda tengo`;
  `FLOOR` `en que piso vivo`, `en que piso esta mi departamento`, `cual es mi piso`;
  `LIFT` `tengo ascensor`, `mi edificio tiene ascensor`;
  `HOME_ACCESS` `como se entra a mi casa`, `como se entra a mi departamento`,
  `como entran a mi casa`, `como entra la ambulancia`;
  `LIVES_ALONE` `vivo solo`, `vivo sola`;
  `KEY_HOLDERS` `quien tiene llave`, `quien tiene llaves`, `quien tiene la llave`,
  `quien tiene las llaves`, each optionally followed by `de mi casa`, `de la casa` or
  `de mi departamento` (written out as whole phrases);
  `CONTACT_PHONE` (open) `tienes el telefono de`, `tienes el numero de`, `tienes el celular de`,
  `cual es el telefono de`, `cual es el numero de`, `cual es el celular de`, `dame el telefono de`,
  `dame el numero de`, `me das el telefono de`, `me das el numero de`;
  `CONTACT_CALL` (open) `llama a`, `llamale a`, `puedes llamar a`, `podrias llamar a`,
  `quiero llamar a`, `necesito llamar a`.
  The phrases that open with a statement form need a question mark, like `ANTICOAGULANT` today:
  one set `_NEEDS_QUESTION_MARK = {ANTICOAGULANT, IMPLANTED_DEVICE «tengo algun…», HEARING «uso
  audifonos», VISION «uso lentes», LIFT, LIVES_ALONE}` held per phrase, not per topic (so «¿cómo
  escucho?» needs none). `SECRET_HOLDER`'s «quien tiene la» + a non-secret word («llave») already
  falls through, so «¿quién tiene la llave de mi casa?» is `KEY_HOLDERS` and «¿quién tiene la clave
  de la alarma?» stays `SECRET_HOLDER`.
- **D-5 A contact question's words.** For the two open contact topics the query carries the folded
  tail **as is** (no length filter, no stopwords: «1», «mi» and «tio» matter), so
  `SensitiveQuery.keywords` holds those words for these topics only. `cognition/contact_questions.py`
  parses them into a `ContactSelector`: `own` (the tail has «mi» or «mis», or names a call order);
  `order` (`contacto 1`, `contacto uno`, `contacto numero 1`, `primer`/`primero`, `segundo`,
  `tercer`/`tercero`, `cuarto`, `quinto` + `contacto`; digits `1` to `9` and words `uno` to
  `nueve`); `roles` (`emergencia` → `emergency`; `cuidador`, `cuidadora` → `caregiver`; `doctor`,
  `doctora`, `medico`, `medica` → `doctor`; `vecino`, `vecina` → `neighbor`; `confianza` →
  `trusted`); `words` (what is left once the function words `mi`, `mis`, `de`, `del`, `el`, `la`,
  `los`, `las`, `a`, `al`, `numero`, `contacto`, `contactos`, `telefono`, `telefonos`,
  `celular`, `y`, `por`, `favor`, `porfa`, `po`, `iroko`, `oye` and the order and role words are
  removed).
- **D-6 Own contacts only, never a name alone.** A contact question with `own` false
  («¿cuál es el teléfono de los bomberos?», «llama a Canary») is `NOT_HOUSEHOLD`: ordinary
  conversation, decided before any check and with nothing read, as Plan 0079 does for
  «¿cuándo nació Mozart?». A name alone is not accepted because deciding it would read the contacts
  before the audit row and a refusal would confirm the name (Plan 0077). A name **with** «mi»
  («el teléfono de mi doctora Canary») narrows the selection after the audit.
- **D-7 Which contacts a question selects** (after the checks, from `list_active_contacts`, in its
  call order): a row is selected when its `call_order` equals `order`, or its role is in `roles`,
  or a word of `words` equals a whole word of its folded relationship or its folded contact name,
  also with a final «s» removed from the word («mis hijas» selects «hija»). A selector with no
  order, role or word («¿tienes los teléfonos de mis contactos?») selects every row. One sentence
  per distinct person and phone pair; at most `MAX_SPOKEN_CONTACTS = 3` people, the first by call
  order (a robot turn is capped at 28 s). `KEY_HOLDERS` selects the rows with `has_key`.
- **D-8 The contacts' policy request.** One request per question, before the read:
  `READ_PERSONAL_CONVERSATION_MEMORY`, target the owner, visibility `{personal}`, sensitivity
  `{private, location}` (the two the table can hold), consent by Plan 0079 D-9 (location needs the
  face's grant and a closed alta). One audit row; a failing audit reads nothing.
- **D-9 The spoken phone.** `spoken_phone(phone)`: «más», then the digits in groups of four from the
  right (the leftmost group keeps the rest), each digit as its word (`cero` … `nueve`), groups
  joined with «, »: `+56900000001` → «más cinco seis nueve, cero cero cero cero, cero cero cero
  uno». Words, not numerals, so the voice never reads «5 6 9» as a number.
- **D-10 The contact templates** (tuteo, in `cognition/contact_answers.py`; values read as stored):
  the descriptor is the relationship label when present, else the role's words (`emergency`
  «contacto de emergencia», `caregiver` «contacto de cuidado», `doctor` «contacto médico»,
  `key_holder` «contacto con llave», `neighbor` «contacto vecino», `trusted` «contacto de
  confianza», `other` «contacto»); one person «El teléfono de {name}, tu {descriptor}, es
  {phone}.», without a stored name «El teléfono de tu {descriptor} es {phone}.», with a second
  phone « También tiene el {alt}.» appended; several people are their sentences joined with a
  space. `NO_PHONE = "No tengo ese teléfono guardado."`. Key holders: one «{name} tiene llave de tu
  casa.», several «Tienen llave de tu casa: {names}.» (`spanish_join`), a nameless row says «tu
  {descriptor}»; none `NO_KEY_HOLDER = "No tengo registrado que alguien tenga llave de tu casa."`.
  `CANNOT_CALL = "Todavía no puedo hacer llamadas."` opens every `CONTACT_CALL` reply that passed
  the checks (answered: `CANNOT_CALL` + « » + the phone sentences; nothing selected: `CANNOT_CALL` +
  « » + `NO_PHONE`). A refusal (`NOT_ALONE`, `DENIED`, `RETRY_VOICE`, `UNAVAILABLE`) is today's
  phrase, never `CANNOT_CALL`.
- **D-11 The other templates** (`cognition/sensitive_answers.py`): devices «Tu dispositivo
  registrado es {v}.» / «Tus dispositivos registrados son {v}.»; mobility `solo` «Te desplazas sin
  ayuda.», `baston` «Te desplazas con bastón.», `andador` «Te desplazas con andador.»,
  `silla_de_ruedas` «Te desplazas en silla de ruedas.»; hearing `normal` «Tienes registrada una
  audición normal.», `audifonos` «Usas audífonos.», `dificultad` «Tienes dificultad para
  escuchar.»; vision `normal` «Tienes registrada una visión normal.», `lentes` «Usas lentes.»,
  `dificultad` «Tienes dificultad para ver.»; coverage «Tu previsión de salud es {v}.»; dwelling
  `casa` «Vives en una casa.», `departamento` «Vives en un departamento.»; floor «Vives en el piso
  {v}.»; lift `si` «Sí, tu edificio tiene ascensor.», `no` «Tu edificio no tiene ascensor.»;
  access «Sobre cómo entrar a tu casa tengo anotado: {v}.»; lives alone `si` «Tengo registrado que
  vives sin nadie más en casa.», `no` «Tengo registrado que vives con alguien más.». A stored choice
  outside these maps raises `ValueError` (no value in the message) → `UNAVAILABLE`, as today.
- **D-12 The reach map and its test.** `server/memory/alta_reach.py` holds one closed map from each
  field the alta can load to how it is reached: `Reach.CARD`, `Reach.RELATIVES`,
  `Reach.SENSITIVE`, `Reach.CONTACTS`, or a reason it is not said aloud (`Reach.RULE`: a rule the
  robot obeys, `withhold_from`, `private_topic`, `may_receive_health_info`, `may_view_activity`;
  `Reach.BOOKKEEPING`: ids, labels, channel and dates of a row; `Reach.FAMILY_STAGE`, D-13). The
  fields come from the importer itself: `seed_plan.ALTA_FIELDS` (new, derived from
  `OWNER_PREDICATES`, `_CHILD_KEYS`, `_PET_KEYS`, the membership relations, the child sides,
  `_RELATIVES` and `withhold_from`) and the fields of `CareContact`. The test fails when a field has
  no entry, and checks each claim against the reader that makes it: `CARD` ⊆ `CARD_PREDICATES`,
  `SENSITIVE` ⊆ the predicates of `TOPIC_PREDICATE`, `RELATIVES` ⊆ what `relation_of` and the
  children routes answer, `CONTACTS` ⊆ the `CareContact` fields `contact_access` reads.
- **D-13 Not in ADR 0037's table (*Pipec, 2026-11-11: listed with a reason*).** The alta also
  loads a child's `stated_age` and tastes, and a pet's `species`, `stated_age` and tastes; the ADR's
  table names neither, and no reader serves them today (Task 0 confirms). They are listed as
  `Reach.FAMILY_STAGE` («a household member's own data, read in the family stage, P3»), not read
  by this plan, and ADR 0037's table gains that row at the close.

**Goal.** With `ALTA_READ_ENABLED` on, the face-identified owner alone in view hears every datum the
alta loaded that ADR 0037 decision 5 marks readable: devices, mobility, hearing, vision, coverage,
dwelling, floor, lift and how to get in at the sensitive level, «vive solo» at the security level,
and their contacts' phones by relationship, role, call order or name with «mi», the key holders, and
«llama a mi contacto 1» answered with «Todavía no puedo hacer llamadas.» plus the name and the
phone; a test fails whenever a loaded field has neither a read nor a listed reason.

**Architecture.** Read only and fixed templates: the grammar of `sensitive_questions` grows behind
an `alta` flag; a pure `contact_questions` parses a contact question's words into a selector and a
pure `contact_answers` words the phones; `memory/contact_access` reads `care_contacts` through the
existing `list_active_contacts` and `get_person_label`, after the checks of `sensitive_reply`, which
delegates the three contact topics to it. The controller and the voice routes pass one more flag.
`memory/alta_reach` is the map the coverage test walks.

**Tech stack.** Python 3.12, FastAPI, aiosqlite, pytest. No new dependency, no migration, no write,
no wire change, no robot change, no prompt change.

**Spec.** [ADR 0037](../../adr/0037-the-time-of-memories-and-a-contacts-phone.md) decisions 1, 5
and 6; [ADR 0029](../../adr/0029-it-knows-who-is-listening.md) decisions 1 to 4 (levels, the camera
check, templates, the marker); [ADR 0024](../../adr/0024-seed-load-senses-secrets-and-channels.md)
decision 5 (the contacts table); the
[seed data pool](../../architecture/seed-data-pool.md);
[guardrails](../../architecture/implementation-guardrails.md).

## Global constraints

- English code, comments and docstrings (Google style); Spanish only in user-facing strings;
  **no voseo** (`tests/unit/test_no_voseo_in_spoken_strings.py` covers the new phrases).
- No `Any`, no `print`, no `os.path`, no bare `except`; logging with `%`; settings only through
  `settings`; every public API typed and documented.
- **Nothing is written:** no migration, no writer import in the new modules (a guard says so).
- No phone, name, relationship or stored value in a log line, an audit row, an exception message or
  a `repr`; logs carry the topic, the level, the outcome and a count.
- The generic prompt reads no household store (Plan 0077 guard); a stored value is said only by a
  fixed template; a sensitive answer never enters the continuity session.
- With `ALTA_READ_ENABLED=false` every route is byte-identical to `main`; with
  `MEMORY_ENABLED=false` every turn is.
- No real household data: invented canaries only (`Canary Daughter`, `Canary Doctor`, `Zeta`,
  `+56900000001`, «Calle Falsa 123», «Remedio A»); `scripts/check_reserved_terms.py` passes.

## Review focus

Failure modes the ADR implies and no task title names; each has its test in the task that owns it.

1. «Contacto uno», «contacto 1.», «el primer contacto», «contacto número uno» as Whisper writes them:
   all order 1; «mis contactos» with no order selects all, capped at three (Task 2).
2. One person who is two contacts (a daughter who is `caregiver` and `key_holder`): one sentence,
   not two, in a phone question; listed once among the key holders (Task 5).
3. «¿Quién tiene la llave de mi casa?» against «¿quién tiene la clave de la alarma?»: the first
   `KEY_HOLDERS` (sensitive), the second `SECRET_HOLDER` (security), never swapped (Task 3).
4. A contact question that names no own contact («¿cuál es el teléfono de los bomberos?», «llama a
   Canary»): ordinary conversation, nothing read and nothing audited, also with two faces (Task 5).
5. A stored phone of 8 to 15 digits, a landline and a second phone: grouped and said in words,
   never a digit in a log line (Tasks 1 and 5).

---

## File structure

| File | Responsibility | Task |
|---|---|---|
| `cognition/contact_answers.py` (new) | The spoken phone, the descriptors, the contact and key-holder sentences, the fixed phrases | 1 |
| `cognition/contact_questions.py` (new) | `ContactSelector` from a contact question's words | 2 |
| `cognition/sensitive_questions.py` | The new topics, the maps, the phrases, the `alta` flag | 3 |
| `cognition/sensitive_answers.py` | The templates of D-11 | 4 |
| `memory/contact_access.py` (new), `memory/sensitive_access.py` | The contact read after the checks; delegation | 5 |
| `cognition/intent_resolution.py`, `cognition/controller.py`, `memory/recall_store.py` | The `alta` flag through the need and the controller | 6 |
| `settings.py`, `.env.example`, `routers/transcribe.py` | The switch and the wiring | 7 |
| `memory/alta_reach.py` (new), `memory/seed_plan.py`, `tests/unit/test_architecture_guards.py` | The reach map, its test, the guards | 8 |
| `docs/…` | Truth, acceptance, close | 9 |

---

### Task 0: Re-audit and baseline

**Files:** none changed.

- [ ] **Step 1:** `git checkout main && git pull`, then create `feat/0082-alta-by-voice`.
- [ ] **Step 2:** Verify, and **stop and report** if any is false:
  - `classify_sensitive_question(message)` has the twelve topics of Plan 0079, `_OPEN_TOPICS`,
    `_PATTERNS` built from `_PHRASES`, and the `ANTICOAGULANT` question-mark rule; «¿quién tiene la
    llave de mi casa?» matches nothing today (a throwaway script under `.superpowers/sdd/0082/`:
    the shell mangles accents).
  - `sensitive_reply` runs the order of D-1 and is the only caller of `read_own_values`;
    `_read_own` builds one `AuthorizationRequest` with `READ_PERSONAL_CONVERSATION_MEMORY`.
  - A throwaway policy check: the face-identified owner at `basic`, own data, visibility
    `{personal}` and sensitivity `{private, location}` with consent `GRANTED` is `ALLOWED`, and with
    `MISSING` is denied (D-8). If not, stop: the contacts need a policy change the ADR did not decide.
  - The canonical writer stores each D-3 predicate with visibility `personal` and the registry's
    default sensitivity (`health_coverage` `private`; `implanted_device`, `mobility`, `hearing`,
    `vision` `medical`; the dwelling fields and `lives_alone` `location`), and the choices are
    exactly those of D-11 (`predicate_registry._POOL_PREDICATES`).
  - `care_contacts.list_active_contacts(owner_entity_id)` orders by call order (none last), then id;
    `entity_labels.get_person_label(entity_id=…)` returns an `EntityLabel` with `display_name`;
    `care_contacts` is the only module with SQL on the table (the guard).
  - The partner is read today: «¿cómo se llama mi pareja?» → `InformationNeed.RELATIVES_NAMES` with
    `RECALL_ENABLED` on and «Tu pareja se llama {}.» (`relatives_answers`), so it needs no task.
  - The fields the importer can load (`seed_members.OWNER_PREDICATES`, `seed_plan._CHILD_KEYS`,
    `_PET_KEYS`, `_CHILD_SIDES`, `_RELATIVES`, the membership and `withhold_from` relations) and no
    reader of a child's `stated_age` or tastes, nor of a pet's `species`, `stated_age` or tastes
    (D-13). `access_code` cannot be loaded by the seed file. List them in the PR.
  - `intent_resolution.resolve_information_need(message, *, recall, sensitive, secrets)` builds its
    tuple with `functools.cache` (`_rules_for`); the controller passes each flag only when set and
    calls `classify_sensitive_question` in `_sensitive_plan`; `recall_store.tells_something`
    passes `sensitive=settings.sensitive_read_enabled`.
  - `routers/transcribe._sensitive_reader` builds the closure for both voice routes; `/chat` and
    `/vision/respond` build no sensitive reader.
- [ ] **Step 3:** Run the baseline and write the count in the PR:
  `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and not eval" -q -n auto`.

---

### Task 1: The contact answers and the spoken phone

**Files:** Create `server/src/server/cognition/contact_answers.py`,
`tests/unit/test_contact_answers.py`.

**Interfaces:**
- Consumes: `ContactRole` (`memory/care_contacts.py`, a `StrEnum`, imported for its values only
  under `TYPE_CHECKING`, so the cognitive core imports no SQLite), `spanish_join`
  (`cognition/sensitive_answers.py`).
- Produces: `CANNOT_CALL`, `NO_PHONE`, `NO_KEY_HOLDER: Final[str]` (D-10);
  `MAX_SPOKEN_CONTACTS: Final = 3`; `@dataclass(frozen=True) class SpokenContact: name: str | None;
  descriptor: str; phone: str; phone_alt: str | None` (every field `repr=False`);
  `def spoken_phone(phone: str) -> str`; `def role_descriptor(role: str) -> str`;
  `def word_contacts(contacts: tuple[SpokenContact, ...]) -> str`;
  `def word_key_holders(contacts: tuple[SpokenContact, ...]) -> str` (empty → `NO_KEY_HOLDER`).

- [ ] **Step 1: Write the failing tests:** `test_spoken_phone_groups_from_the_right`
  (`+56900000001` → the D-9 sentence; `+5622000000` and a 15-digit number);
  `test_spoken_phone_rejects_a_non_phone` (`ValueError`, the message holds no digit);
  `test_every_role_has_a_descriptor` (all seven `ContactRole` values);
  `test_one_contact_with_and_without_a_name`; `test_a_second_phone_is_appended`;
  `test_several_contacts_are_joined`; `test_key_holders_one_several_and_none`;
  `test_values_are_read_as_written` (a relationship «Hija mayor»).
- [ ] **Step 2:** Run `uv run pytest tests/unit/test_contact_answers.py -q` → FAIL (module missing).
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS; the no-voseo test passes.
- [ ] **Step 5:** commit `feat: word a contact's phone with fixed phrases (plan 0082)`.

---

### Task 2: The contact selector

**Files:** Create `server/src/server/cognition/contact_questions.py`,
`tests/unit/test_contact_questions.py`, `tests/fixtures/contact_selectors.yaml`.

**Interfaces:**
- Produces: `@dataclass(frozen=True) class ContactSelector: own: bool; order: int | None;
  roles: frozenset[str]; words: frozenset[str]` (`words` `repr=False`), with `is_empty` true when
  `order`, `roles` and `words` are all empty; `def contact_selector(tail: tuple[str, ...]) ->
  ContactSelector` (pure, D-5); `def selects(selector: ContactSelector, *, call_order: int | None,
  role: str, relationship: str | None, name: str | None) -> bool` (D-7, the plural rule).

- [ ] **Step 1: Write the failing tests** over the fixture (folded tails and their selectors):
  «mi hija» → own, words `{hija}`; «mi contacto 1», «mi contacto uno», «mi primer contacto», «mi
  contacto numero uno» → order 1 (Review focus 1); «mi contacto de emergencia» → roles
  `{emergency}`; «mi doctora canary» → roles `{doctor}`, words `{canary}`; «mis contactos» → own,
  empty; «los bomberos» → not own; «canary» → not own. `test_selects_by_order_role_word_and_plural`
  («hijas» selects a row «hija»; a name word selects; nothing else does).
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** commit `feat: tell which own contact a question names (plan 0082)`.

---

### Task 3: The grammar of the rest of the alta

**Files:** Modify `server/src/server/cognition/sensitive_questions.py`,
`tests/unit/test_sensitive_questions.py`, `tests/fixtures/sensitive_questions.yaml`.

**Interfaces:**
- Produces: the thirteen new `SensitiveTopic` members of D-3 (values the lower-case names);
  `CONTACT_TOPICS: Final[frozenset[SensitiveTopic]]`; `ALTA_TOPICS: Final[frozenset[SensitiveTopic]]`
  (the thirteen); `TOPIC_PREDICATE` gains the ten predicate topics, `TOPIC_LEVEL` and `TOPIC_LABEL`
  all thirteen; `def classify_sensitive_question(message: str, *, alta: bool = False) ->
  SensitiveQuery | None`: a topic in `ALTA_TOPICS` matches only with `alta`; the contact topics are
  open and keep the raw folded tail as `keywords` (D-5); the question-mark rule is per phrase (D-4).

- [ ] **Step 1: Write the failing tests:** every D-4 phrase in a full question with «oye», «Iroko»,
  «po» and «¿», matched only with `alta=True` and `None` with `alta=False`
  (`test_the_new_topics_need_the_flag`); `test_plan_0079_phrases_are_unchanged` (the whole existing
  fixture, both flag values, byte-identical); the traps resolve to `None`: «uso lentes desde chico»,
  «vivo solo desde 2010», «tengo ascensor en la pega», «¿cómo veo esta foto?», «¿cómo se entra a la
  página?», «¿quién tiene la razón?»; `test_the_key_and_the_alarm_code_are_told_apart` (Review
  focus 3); `test_a_contact_question_keeps_its_tail` («¿tienes el teléfono de mi tío?» →
  `("mi", "tio")`); `test_every_topic_has_its_level_and_label` (D-3, exact) and
  `test_contact_topics_have_no_predicate`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** commit `feat: recognize the rest of the alta's questions (plan 0082)`.

---

### Task 4: The templates of the rest of the profile

**Files:** Modify `server/src/server/cognition/sensitive_answers.py`,
`tests/unit/test_sensitive_answers.py`.

**Interfaces:**
- Consumes: the topics of Task 3.
- Produces: `word_own_answer(topic, values)` words the ten predicate topics of D-3 by D-11;
  unchanged signature; a contact topic raises `ValueError` (they are worded by Task 1).

- [ ] **Step 1: Write the failing tests:** one per D-11 template, singular and plural for devices,
  every choice of mobility, hearing, vision, dwelling, lift and lives alone;
  `test_an_unknown_choice_raises_without_the_value`; `test_a_contact_topic_is_not_worded_here`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** commit `feat: word the rest of the owner's profile (plan 0082)`.

---

### Task 5: The contact read after the checks

**Files:** Create `server/src/server/memory/contact_access.py`,
`tests/unit/test_contact_access.py`, `tests/integration/test_contact_access_store.py`; modify
`server/src/server/memory/sensitive_access.py`, `tests/unit/test_sensitive_access.py`.

**Interfaces:**
- Consumes: Tasks 1 to 3; `list_active_contacts`, `get_person_label`.
- Produces: `async def contact_reply(actor: ActivePersonContext, query: SensitiveQuery, *,
  consent: ConsentStatus, correlation_id: UUID, now: datetime, policy: PolicyEvaluator, audit:
  AuditWriter, contacts: ContactsReader = list_active_contacts, labels: LabelReader =
  get_person_label) -> tuple[SensitiveReply, int]` (the reply and a count), run after the common
  checks: the D-8 request and its audit row, then the read, the D-7 selection and the D-10 wording.
  `def is_own_contact_question(query: SensitiveQuery) -> bool` (D-6; `KEY_HOLDERS` is always own).
  `sensitive_reply` gains `contacts` and `labels` seams with those defaults; in `_decide`, a contact
  topic that is not own is `NOT_HOUSEHOLD` **first**, before the faces (D-6), and an own one goes
  through the same `NOT_ALONE`, `DENIED` and level steps, then to `contact_reply` with the D-9
  consent of Plan 0079 for `location`.

- [ ] **Step 1: Write the failing tests** (doubles for policy, audit, contacts and labels):
  `test_two_faces_hear_not_alone_and_nothing_is_read`; `test_a_stranger_is_denied`;
  `test_a_question_with_no_own_contact_is_ordinary` (also with two faces; nothing audited, nothing
  read; Review focus 4); `test_the_audit_row_precedes_the_read`; `test_a_failing_audit_reads_nothing`;
  `test_no_closed_alta_is_denied`; `test_by_relationship_role_order_and_name`;
  `test_none_selected_says_no_phone`; `test_call_opens_with_cannot_call` (answered and nothing
  selected); `test_a_refused_call_hears_the_refusal_not_cannot_call`;
  `test_one_person_with_two_roles_is_said_once` (Review focus 2); `test_at_most_three_people`;
  `test_key_holders`; `test_lives_alone_needs_strong` (retry with `FACE_ONLY` and the voice on,
  denial without); `test_the_new_profile_topics_read_their_predicate`;
  `test_no_value_reaches_a_log_line` (caplog over every outcome: no digit of a phone, no name).
  Integration (a migrated database, the contacts writer, canaries): a revoked contact is not read;
  another owner's contact is not read; the order comes from the table.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS, the whole
  `test_sensitive_access.py` included.
- [ ] **Step 5:** commit `feat: read the owner's contacts after the checks (plan 0082)`.

---

### Task 6: The flag through the need and the controller

**Files:** Modify `server/src/server/cognition/intent_resolution.py`,
`server/src/server/cognition/controller.py`, `server/src/server/memory/recall_store.py`;
tests `tests/unit/test_intent_resolution.py`, `tests/unit/test_controller_sensitive.py`, the
recall-store test.

**Interfaces:**
- Produces: `resolve_information_need(message, *, recall=False, sensitive=False, secrets=False,
  alta=False)`; `_rules_for` caches over the four booleans and passes `alta` to the sensitive rule;
  `alta` without `sensitive` changes nothing. `CognitiveController(..., alta_read: bool = False)`
  passes `alta=True` to the resolver and to `classify_sensitive_question` only when set (the bare
  calls of today stay). `tells_something` passes
  `alta=settings.sensitive_read_enabled and settings.alta_read_enabled`.

- [ ] **Step 1: Write the failing tests:** `test_with_the_alta_flag_off_resolutions_are_unchanged`
  (the whole existing corpus, byte-identical); `test_an_alta_question_needs_both_flags`;
  `test_a_call_request_is_a_sensitive_read` («llama a mi contacto 1» → `sensitive.contact_call.v1`);
  `test_the_controller_passes_the_flag_only_when_set`; `test_a_contact_answer_is_not_written_to_continuity`;
  `test_tells_something_follows_the_alta_switch`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS;
  `uv run pytest tests/unit -q -k "intent or controller or recall"`.
- [ ] **Step 5:** commit `feat: route the alta's questions behind a flag (plan 0082)`.

---

### Task 7: The switch and the wiring

**Files:** Modify `server/src/server/settings.py`, `.env.example`,
`server/src/server/routers/transcribe.py`; tests in `tests/api/` (the voice-route byte-identity
tests and the sensitive-read route tests).

**Interfaces:**
- `alta_read_enabled: bool = False` (`ALTA_READ_ENABLED`, documented in `.env.example` with its two
  prerequisites, D-2).
- Both voice routes pass `alta_read=settings.alta_read_enabled` to the controller only when the
  sensitive reader is built; `/chat` and `/vision/respond` are unchanged.

- [ ] **Step 1: Write the failing tests:** `test_with_the_switch_off_every_route_is_byte_identical`
  (classic and streaming; an alta question and a generic one; `SENSITIVE_READ_ENABLED` on and off);
  `test_the_switch_needs_the_sensitive_read` (alta on, sensitive off: today's behaviour);
  `test_a_contact_phone_on_each_voice_route` (the template, no model call, the record keeps
  `[dato sensible leído]`, no recall unit, the `done` event has no new field);
  `test_a_two_face_frame_hears_not_alone_for_a_contact`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS; the unit, API and
  integration suites with `MEMORY_ENABLED=false`.
- [ ] **Step 5:** commit `feat: wire the alta read switch (plan 0082)`.

---

### Task 8: The reach map, its test and the guards

**Files:** Create `server/src/server/memory/alta_reach.py`, `tests/unit/test_alta_reach.py`; modify
`server/src/server/memory/seed_plan.py` (+ its test), `tests/unit/test_architecture_guards.py`.

**Interfaces:**
- Produces: `ALTA_FIELDS: Final[frozenset[tuple[str, str]]]` in `seed_plan.py` (the subject role,
  `owner`, `child`, `pet` or `relation`, and the predicate; derived from the importer's own
  constants, D-12); in `alta_reach.py`, `class Reach(StrEnum)` with the members of D-12,
  `@dataclass(frozen=True) class ReachEntry: reach: Reach; reason: str | None = None` (a reason is
  required for `RULE`, `BOOKKEEPING` and `FAMILY_STAGE` and forbidden for a read),
  `ALTA_REACH: Final[Mapping[tuple[str, str], ReachEntry]]`,
  `CONTACT_FIELD_REACH: Final[Mapping[str, ReachEntry]]`.

- [ ] **Step 1: Write the failing tests:** `test_every_alta_field_has_a_reach` (`ALTA_FIELDS` equals
  the keys of `ALTA_REACH`; a field added to the importer without an entry fails);
  `test_every_contact_field_has_a_reach` (`dataclasses.fields(CareContact)` equals the keys of
  `CONTACT_FIELD_REACH`); `test_each_read_is_real` (the D-12 cross-checks);
  `test_a_reason_goes_with_every_unread_field`; `test_the_pool_is_inside_the_alta`
  (`POOL_PREDICATE_IDS` ⊆ the predicates of `ALTA_FIELDS`). Guards:
  `test_the_alta_read_writes_nothing` (`contact_access`, `contact_answers`, `contact_questions` and
  `alta_reach` import no `write_contact`, `revoke_contact`, `canonical_writer` or `memory_writer`);
  `test_the_generic_prompt_still_reads_no_household_store` extended with the three new modules;
  `test_the_cognitive_core_imports_no_sqlite` covers `contact_*`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run →
  `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and not eval" -q -n auto`,
  `uv run pyright`, `uv run mypy server/src robot/src`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run ruff check scripts/*.py`,
  `uv run python scripts/check_reserved_terms.py`, `just gate` — all pass. Write the count in the PR.
- [ ] **Step 5:** commit `test: no alta field stays unreachable by voice (plan 0082)`.

---

### Task 9: Truth, acceptance and close

**Files:** `docs/architecture/current-state.md` and its Archify diagram (validate → deliver),
`docs/architecture/seed-data-pool.md` (the capabilities table and the «nothing reads them by voice»
notes), `docs/runbooks/operator-manual.md` (`ALTA_READ_ENABLED`, the questions, the phrases),
`docs/evals/0082-alta-by-voice-acceptance.md` (new, outcomes only), ADR 0037 (an *Implemented in
Plan 0082* note for decisions 1 and 5, and the D-13 row in its table), ADR 0024 decision 5 (an
*Amended by ADR 0037* note), the plan board, the roadmap row 7.

- [ ] **Step 1: Hardware acceptance by Pipec** (streaming, and classic if he chooses), outcomes only,
  on his real alta: (1) «¿tienes el teléfono de mi …?» with only his face in view; (2) «¿cuál es el
  número de mi contacto 1?»; (3) «llama a mi contacto 1» → «Todavía no puedo hacer llamadas.» and
  the name and phone; (4) «¿quién tiene llave de mi casa?»; (5) two of devices, mobility, hearing,
  vision, coverage, dwelling, floor, lift, access; (6) «¿vivo solo?» with face and voice, and with a
  short question → the retry phrase; (7) a second face (a photo on a phone) → «Te lo digo cuando
  estemos solos.»; (8) «¿cuál es el teléfono de los bomberos?» → an ordinary reply; (9)
  `iroko-admin conversations` shows the marker. Phrasings that missed the grammar go into the Task 3
  fixture and the grammar in a fix commit, recorded as counts only.
- [ ] **Step 2:** Update the documents above; move the plan to `completed/`.
- [ ] **Step 3:** commit `docs: close plan 0082, the alta read by voice`, push, open the PR,
  squash-merge with green CI (GitHub is delegated), delete the branch, return to `main`.

---

## Non-goals

The spoken-time reader, the occurred time and «¿cuándo ocurrió?» (Plan 0083); pending topics and the
greeting that picks one up (Plan 0084); calling a phone, an alert or telephony; anyone but the
owner reading the contacts (the future care ADR); a name-only contact question (D-6); reading a
child's or a pet's own literals (D-13); `withhold_from`,
`private_topic` and the contact's permissions as answers (rules, the family stage); correcting or
forgetting by voice (ADR 0032); any migration, write, wire, robot or prompt change.

## Self-review (2026-11-11)

- **Spec coverage.** ADR 0037 decision 1 (match by relationship, role, order and name; key holders;
  «llama a» honest; sensitive level and the camera check; the template digit by digit; the marker;
  nothing dialled) → D-4 to D-10 and Tasks 1, 2, 3, 5, 7; decision 5 (every field read or listed;
  partner, devices, mobility, hearing, vision, coverage, dwelling, access at sensitive; lives alone
  at security; the test) → D-3, D-11 to D-13 and Tasks 3, 4, 5, 8 (the partner already read, Task
  0); decision 6 (its own default-off switch, byte-identical) → D-2 and Tasks 6, 7; *Test
  consequences* for the phone → Tasks 5 and 7.
- **Type consistency.** `SensitiveTopic`, `CONTACT_TOPICS`, `ALTA_TOPICS`, `ContactSelector`,
  `SpokenContact`, `Reach`, `ReachEntry`, `ALTA_FIELDS`, `ALTA_REACH` and `CONTACT_FIELD_REACH` are
  each defined once and named the same in every later task; `classify_sensitive_question(…, alta=)`,
  `resolve_information_need(…, alta=)` and `CognitiveController(…, alta_read=)` are the only new
  parameters.
- **Open for Pipec.** D-13 is decided (listed with a reason, 2026-11-11). Still to confirm at
  promotion: the switch's two prerequisites (D-2); the three-person cap (D-7); the phone said in
  words (D-9).
