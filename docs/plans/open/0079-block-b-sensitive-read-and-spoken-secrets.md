# 0079 — Block B: read the owner's sensitive data by voice, and never keep a spoken secret's value

> **Status:** `Ready` and `NOW` — **promoted by Pipec on 2026-11-05** («el plan refleja lo que yo
> quiero»), D-1 to D-12 confirmed as written; executed in a new session. Written as `Draft` the
> same day as the review amendments of its design,
> [ADR 0029](../../adr/0029-it-knows-who-is-listening.md) (`Proposed`, decisions 1 to 21 and the
> author's calls, all confirmed by Pipec on 2026-11-05). It becomes `Ready` and `NOW` when Pipec
> approves this plan; ADR 0029 moves to `Accepted` when it closes. Detailed against `main` at
> `482de44` plus the ADR amendments of the same branch (`46178a4` and after); queue rule 4 applies at execution: Task 0 re-verifies every claim below against the
> merged code before any code, and **stops and reports** if one is false. Written for an executor
> who has not seen this repository.

> **For agentic workers:** if the status above does not say `Ready`, stop. REQUIRED SUB-SKILL:
> `superpowers:subagent-driven-development` (Pipec's choice, 2026-11-05), with
> `superpowers:test-driven-development`, `superpowers:verification-before-completion` and
> `superpowers:finishing-a-development-branch`. Every subagent runs on the `sonnet` model and reads
> `.claude/` (CLAUDE.md and `.claude/rules/`) in full before touching code. **Pipec's rules win over
> the skills:** one plain branch from `main` (`feat/0079-sensitive-read`), never a git worktree,
> this plan lives under `docs/plans/`. One commit per task; every test seen RED for the stated
> reason first. If evidence contradicts the plan, stop and report instead of redesigning. The Bash
> tool of this environment loses backslashes and non-ASCII characters in heredocs and command
> arguments: use the Write and Edit tools, and put Spanish test phrases in files. Commit messages:
> Conventional Commits, title at most 72 characters, check `git log` after each commit (the hook
> rejects silently); do not pipe `git commit`; `git add` with explicit paths. Run the suite with
> `MEMORY_ENABLED=false` as CI does, and have each test that needs memory set
> `settings.memory_enabled` itself. Never run `uv sync --all-packages --all-groups` (it removes the
> optional `cuda` extra). **Do not run `just gate` in the background while Pipec rehearses** (about
> 3.5 GB of RAM). **The server and the robot are started by Pipec**, never by the agent. Before
> pushing, run `pyright`, `ruff` and `mypy` over the **whole** project and lint `scripts/` with
> explicit paths (`ruff check .` skips it, the pre-commit hook does not).

## Decisions

Pipec's decisions are ADR 0029's tables (1 to 21) and its *author's calls*. The plan's own calls
below fill in what the ADR leaves to the builder; they are confirmed when Pipec promotes the plan.

- **D-1 Order of the rules.** `intent_resolution` builds its rule tuple from three flags:
  `sensitive` (the sensitive reader is wired), `secrets` (the secret guard is on) and `recall`
  (Plan 0078). The new rules go **first**, in this order: `_stated_secret_rule` (if `secrets`),
  `_sensitive_question_rule` (if `sensitive`), `_asked_secret_rule` (if `secrets`); then the tuple
  of today for the `recall` flag, unchanged. With all three off the tuple is `_RULES` itself. The
  controller passes each flag **only when it is set**: the calls `resolver(message)` and
  `resolver(message, recall=True)` of today stay exactly as they are (`test_cognitive_controller.py`
  pins the bare call).
- **D-2 The secret words and the value rule** (`server/secret_values.py`, folded with
  `normalize_spanish`, whole words). `SECRET_WORDS = {clave, claves, contrasena, contrasenas,
  codigo, codigos, pin}`. `NUMBER_WORDS` = `cero` to `veinte`, `veintiuno` to `veintinueve`,
  `treinta`, `cuarenta`, `cincuenta`, `sesenta`, `setenta`, `ochenta`, `noventa`, `cien`, `ciento`,
  `doscientos` to `novecientos`, `mil`. A message **states** a value when, within the six words after
  a secret word, there is a token with a digit or a number word; or, for `clave`, `claves`,
  `contrasena` and `contrasenas` only, a copula (`es`, `son`, `era`) followed by one more word. So
  «el código es un desastre» and «mi código es en python» are ordinary turns (the owner is a
  developer), and «la clave es que llegues temprano» is an accepted false positive. A message
  **asks** for a value when it contains `cual es mi {w}`, `cual era mi {w}`, `dime mi {w}`,
  `me dices mi {w}`, `me recuerdas mi {w}`, `recuerdame mi {w}` or `que {w} tengo` for any secret
  word, or the same openers with `la`/`el` instead of `mi` **only** when the secret word is followed
  by `del` or `de la` and one of `banco`, `tarjeta`, `cuenta`, `cajero`, `wifi`, `alarma`, `correo`,
  `celular`, `telefono`, `computador`, `casa`, `porton` («¿cuál es la clave del banco?»); so «¿cuál
  es la clave del éxito?» and «¿cuál es el código de barras?» stay ordinary. The ask grammar is
  closed on purpose. `recall_sensitivity`'s security set becomes
  `SECRET_WORDS | {alarma, llave, llaves, porton}` (it gains the three plurals: more protective,
  never less).
- **D-3 The sensitive grammar** (`cognition/sensitive_questions.py`, folded, whole phrases, first
  person only). Topics and their phrases:
  `MEDICATION` `que remedios tomo`, `que medicamentos tomo`, `que pastillas tomo`,
  `cuales son mis remedios`, `cuales son mis medicamentos`, `que remedio tomo`;
  `RESCUE_MEDICATION` `cual es mi remedio de rescate`, `cual es mi medicamento de rescate`;
  `HEALTH_CONDITION` `que enfermedades tengo`, `cuales son mis enfermedades`,
  `cuales son mis condiciones de salud`, `que condiciones de salud tengo`;
  `ALLERGY` `a que soy alergico`, `a que soy alergica`, `que alergias tengo`, `cuales son mis alergias`;
  `BLOOD_TYPE` `cual es mi grupo sanguineo`, `que sangre tengo`, `cual es mi tipo de sangre`;
  `ANTICOAGULANT` `tomo anticoagulante`, `tomo anticoagulantes`;
  `ADDRESS` `cual es mi direccion`, `donde vivo`;
  `EMERGENCY_FACILITY` `cual es mi urgencia`, `a que urgencia voy`, `a que clinica me llevan`;
  `OWN_BIRTHDAY` `cuando es mi cumpleanos`, `cuando naci`, `cuando cumplo anos`,
  `cual es mi fecha de nacimiento`;
  `CHILD_BIRTHDAY` `cuando es el cumpleanos de`, `cuando cumple`, `cuando cumplen`, `cuando nacio`,
  `cuando nacieron`;
  `SECRET_HOLDER` `quien conoce la`, `quien sabe la`, `quien tiene la`, `quien conoce el`,
  `quien sabe el`, `quien tiene el`, each followed by a secret word;
  `DOCUMENT_LOCATION` `donde esta mi`, `donde estan mis`, `donde guardo`, `donde dejo`, each
  followed within three words by a document word (`documento`, `documentos`, `pasaporte`, `carnet`,
  `cedula`, `escritura`, `escrituras`, `testamento`, `papeles`, `poder`).
  **Where a phrase may sit** (Plan 0077's lesson, requests and not mentions): the phrase must
  **open** the sentence body, after the leading fillers of `household_request` («oye Iroko,»).
  After the phrase, a **closed** topic (every topic but the three below) allows only trailing
  fillers (`po`, `oye`, `iroko`, `porfa`, `por favor`, `cachai`, `ahora`, `hoy`), so «¿cuál es mi
  dirección de correo?», «donde vivo hace frío» and «cuando cumplo años me regalan libros» match
  nothing; `CHILD_BIRTHDAY`, `SECRET_HOLDER` and `DOCUMENT_LOCATION` allow the words that name what
  is asked (D-5). `ANTICOAGULANT` needs «?» («tomo anticoagulante desde hace años» is a statement);
  every other phrase already opens with its question word. `household_request` gains a public
  `sentence_body(message: str) -> tuple[str, ...]` over its own `_body` and `_LEADING_FILLERS`, so
  the fillers are defined once. A third-person form («¿qué remedios toma?») and «¿dónde dejé las
  llaves?» match nothing.
- **D-4 Levels, predicates and stored labels** (one closed map: `TOPIC_PREDICATE`, `TOPIC_LEVEL`
  and `TOPIC_LABEL`, the visibility and sensitivity **as the canonical writer stores them**, checked
  in Task 0): `MEDICATION` `medication`, `RESCUE_MEDICATION` `rescue_medication`,
  `HEALTH_CONDITION` `health_condition`, `ALLERGY` `allergic_to`, `BLOOD_TYPE` `blood_type`,
  `ANTICOAGULANT` `takes_anticoagulant` → `personal`/`medical`; `ADDRESS` `home_address`,
  `EMERGENCY_FACILITY` `preferred_emergency_facility` → `personal`/`location`; `OWN_BIRTHDAY`
  `birth_date` → `personal`/`private` (`canonical_writer._OWNER_PRIVATE_LITERALS`: the owner's own
  birthday is `private`, not the registry's `child_data`; `private` is no sensitive category, so it
  needs no consent and passes at `basic` today); `CHILD_BIRTHDAY` `birth_date` →
  `household`/`child_data` (the registry default); all `SENSITIVE`. `SECRET_HOLDER`
  `secret_holder` and `DOCUMENT_LOCATION` `document_location` → `personal`/`security`, `SECURITY`.
- **D-5 Keywords of a question.** A `SensitiveQuery` carries the folded words of the message that
  are not in its matched phrase, have at least four letters and are not in `_STOPWORDS`
  (`para`, `como`, `donde`, `cuando`, `quien`, `esta`, `estan`, `tengo`, `tiene`, `sabe`,
  `conoce`). For a reference topic, an entry is selected when one of these words is a whole word of
  the folded entry; none selected → all entries. For `CHILD_BIRTHDAY` the household is decided
  **first, before any audience or policy check**: a keyword `hijo`, `hija`, `hijos`, `hijas` or a
  relative word of Plan 0078 D-9 (`mama`, `papa`, `hermano` …) makes it a household question; a
  keyword equal to a stored household name (`read_household_names`) makes it one **only for the
  face-identified owner** (otherwise a refusal would confirm the name, Plan 0077); anything else
  («¿cuándo nació Mozart?», or a stored name asked by a visitor or with two faces) is
  `NOT_HOUSEHOLD` and stays ordinary conversation, as today. Then a child's folded label selects
  that child, `hijo`/`hija`/`hijos`/`hijas` select all children, and a relative word or a stored
  name that is no child answers `NO_BIRTH_DATE`.
- **D-6 The fixed phrases** (tuteo, no voseo; in `cognition/response_plan.py`):
  `NOT_ALONE = "Te lo digo cuando estemos solos."`;
  `SECURITY_VOICE_RETRY = "No reconocí bien tu voz. Pregúntamelo de nuevo con una frase completa."`;
  `SECRET_REFUSAL = "Las claves y los códigos no los guardo ni los repito."`;
  `NO_BIRTH_DATE = "No tengo registrada su fecha."`; the existing `NOT_REGISTERED` for nothing
  stored; a stranger or a refusal hears the existing `_PROFILE_SUMMARY_UNKNOWN_RESPONSE` and an
  audit or read failure the existing `_PROFILE_SUMMARY_UNAVAILABLE_RESPONSE` (`controller.py`).
- **D-7 The templates** (`cognition/sensitive_answers.py`; `{v}` joined with `spanish_join`):
  medication «Tu medicamento es {v}.» / «Tus medicamentos son {v}.»; rescue «Tu medicamento de
  rescate es {v}.» / «Tus medicamentos de rescate son {v}.»; condition «Tu condición de salud
  registrada es {v}.» / «Tus condiciones de salud registradas son {v}.»; allergy «Tienes alergia a
  {v}.»; blood «Tu grupo sanguíneo es {v}.»; anticoagulant `si` «Sí, tomas anticoagulante.», `no`
  «No tomas anticoagulante.», `no_se` «No tengo claro si tomas anticoagulante.»; address «Tu
  dirección es {v}.»; facility «Tu urgencia preferida es {v}.»; own birthday «Tu cumpleaños es
  {d}.»; one child «El cumpleaños de {name} es {d}.», several «{name} cumple {d}» joined with
  `spanish_join` and closed with «.», a child without a date in a list «de {name} no tengo la
  fecha»; secret holder «Sobre las claves tengo anotado: {v}.»; documents «Sobre tus documentos
  tengo anotado: {v}.» (several entries joined with «; »). `{d}` is `day_month_label`: «el 3 de
  marzo». Blood types: `A+` «A positivo», `A-` «A negativo», and the same for `B`, `AB`, `O`.
  `_spanish_join` moves from `controller.py` to `cognition/sensitive_answers.py` as `spanish_join`
  and the controller imports it (one definition).
- **D-8 Markers.** `SENSITIVE_RECORDED_TEXT = "[dato sensible leído]"` replaces the robot's answer
  in the conversation record and in the opt-in spoken log for a `KNOWN` `SENSITIVE_READ` plan;
  `SECRET_RECORDED_TEXT = "[dato de seguridad omitido]"` replaces the heard words in the record for
  a `SECRET_VALUE` plan. The debug heard-log (`conversation_log.log_heard`) is **not** changed
  (ADR 0029 decision 19). A secret turn resolves no actor, so its record verdict is `not_checked`
  and it never becomes a recall unit nor reaches the diary (`conversation_capture.turn_verdict`).
- **D-9 Consent.** For `medical`, `location` and `security` the read carries `GRANTED` only when
  the route's consent resolver grants it (the face identified the owner) **and** a closed
  commissioning record exists; otherwise `MISSING`. One `SELECT` per matched question, no cache.
  `private` (the owner's birthday) and `child_data` need no consent today and keep that rule.
- **D-10 Who authorizes what.** The owner's own data: `READ_PERSONAL_CONVERSATION_MEMORY`,
  `target_person_id` = the owner, visibility and sensitivity from D-4, the audit row before the
  read; the read keeps only rows stored with exactly those labels. The children's birth dates:
  `HouseholdKnowledgeTools.get_children_birthdays`, which composes the existing paths: the
  `child_of` relation read that `get_children` makes (for the child ids) and the existing
  `get_person_birth_date(person_entity_id=…)` per child, so no new policy path exists.
- **D-11 The retry needs the voice to exist.** A security question from the owner hears the retry
  phrase only when the fusion reason is `FACE_ONLY` **and** `SPEAKER_AUTHENTICATION_ENABLED` is on;
  with the setting off, or the reason `BACKEND_UNAVAILABLE` or `ERROR`, it hears the denial, never an
  endless retry.
- **D-12 Logging.** One line per sensitive read: `event="sensitive.read"`, `topic`, `level`,
  `outcome` (`answered`, `not_alone`, `retry_voice`, `denied`, `not_registered`, `unavailable`,
  `not_household`), `entries` (a count); one per secret turn: `event="secret.turn"`, `kind`
  (`stated`, `asked`). Never a text. Every new value-carrying field is `repr=False`
  (`SensitiveReply.text`, `ChildBirthdays.children`).

**Goal.** The face-identified owner, alone in view, hears their own medications, conditions,
allergies, blood type, address, emergency facility and birthdays with one question; the security
references need the voice too; a second face hears «Te lo digo cuando estemos solos.», anyone else
the denial; a stated or asked secret value never reaches the model and never stays on disk; with
`SENSITIVE_READ_ENABLED=false` every read route is byte for byte today's, and with
`MEMORY_ENABLED=false` everything is.

**Architecture.** Two pure cognitive modules decide the question (`sensitive_questions`) and word
the answer (`sensitive_answers`); one top-level pure module decides a secret value
(`secret_values`), shared by the controller and the recall classifier. `memory/sensitive_store`
reads, `memory/sensitive_access` checks the audience, the level, the consent and the policy, audits
and answers; the controller gets `InformationNeed.SENSITIVE_READ` and `InformationNeed.SECRET_VALUE`,
one optional collaborator and one flag, wired by the voice routes (the flag also by `/chat` and
`/vision/respond`). The record's markers are applied in one place, `_record_plan`.

**Tech stack.** Python 3.12, FastAPI, aiosqlite, pytest. No new dependency, no migration, no wire
change, no robot change, no prompt change.

**Spec.** [ADR 0029](../../adr/0029-it-knows-who-is-listening.md) (all decisions and the author's
calls), ADR 0019 §3, ADR 0016 (the veto and `strong`), ADR 0020, ADR 0024 decision 4, ADR 0027
decision 1, ADR 0028 decisions 3 and 9, [guardrails](../../architecture/implementation-guardrails.md).

## Global constraints

- English code, comments and docstrings (Google style); Spanish only in user-facing strings;
  **no voseo** (`tests/unit/test_no_voseo_in_spoken_strings.py`).
- No `Any`, no `print`, no `os.path`, no bare `except`; logging with `%`; settings only through
  `settings`; every public API typed and documented.
- **No text in any log line** and no stored value in a log, an audit row or an exception message.
- The model never receives a stored sensitive value nor a stated secret; the generic prompt reads no
  household store (Plan 0077 guard).
- A sensitive answer and a secret turn never enter the continuity session.
- With `SENSITIVE_READ_ENABLED=false` every prompt, response, wire field and log line of a read
  question is byte-identical to `main`; with `MEMORY_ENABLED=false` every turn is.
- No real household data anywhere: invented canaries only (`Canary`, `Zeta`, `Omega`, «Remedio A»,
  «Calle Falsa 123»).

## Review focus

Failure modes the ADR implies and no task title names; each has its test in the task that owns it.

1. Whisper's shapes of a stated value: «mi clave es 12 34», «la clave: 1234», «la clave del banco
   cuatro cinco seis», «CLAVE es perro123», a value said before the word («1234 es mi clave»):
   all `stated` except the last, which is pinned as an accepted miss (Task 1).
2. A stored value that looks like something else: an address with digits and «#», a medication
   with a dose («Remedio A 50 mg»), a reference entry that itself contains «clave»: read as written,
   never refused as a secret, never in a log (Tasks 4 and 7).
3. A voice turn with no frame (face authentication off, or the frame invalid): the denial, never a
   crash and never `NOT_ALONE` (Task 6).
4. The voice backend off or failing on a security question: the denial, not an endless retry
   (Task 6, D-11).
5. A message that states a value **and** asks a sensitive question: the secret branch, and the
   record keeps the marker, never the words (Tasks 5 and 8).

---

## File structure

| File | Responsibility | Task |
|---|---|---|
| `server/secret_values.py` (new), `memory/recall_sensitivity.py` | Secret words, stated and asked values; the recall security set derived | 1 |
| `cognition/authorization.py`, `memory/commissioning.py`, `tests/unit/test_personal_memory_policy.py` | Own `medical`/`location` read at `basic`; whether an alta is closed | 2 |
| `cognition/sensitive_questions.py` (new), `cognition/household_request.py` | Topics, grammar, keywords, levels, stored labels; `sentence_body` | 3 |
| `cognition/sensitive_answers.py` (new), `cognition/spoken_dates.py`, `cognition/controller.py` | Templates, spoken values, `spanish_join`, `day_month_label` | 4 |
| `cognition/intent_resolution.py`, `cognition/response_plan.py`, `memory/recall_store.py` | The two needs, the rule order, `tells_something` | 5 |
| `memory/sensitive_store.py` (new), `memory/sensitive_access.py` (new), `cognition/household_tools.py` | Reads; audience, level, consent, policy, audit, answer | 6 |
| `cognition/controller.py`, `cognition/response_plan.py` | The two branches, phrases, markers | 7 |
| `settings.py`, `.env.example`, `routers/transcribe.py`, `routers/chat.py`, `routers/vision.py` | The switch, the wiring, the record markers | 8 |
| `tests/unit/test_architecture_guards.py` | Guards, whole-project checks | 9 |
| `docs/…` | Truth, acceptance, close | 10 |

---

### Task 0: Re-audit and baseline

**Files:** none changed.

- [ ] **Step 1:** `git checkout main && git pull`, then create `feat/0079-sensitive-read`.
- [ ] **Step 2:** Verify, and **stop and report** if any is false:
  - `intent_resolution.resolve_information_need(message, *, recall=False)` walks `_RULES` or
    `_RECALL_RULES`, and today «¿cuál es mi dirección?» and «¿cuándo cumple Zeta?» (with `Zeta` a
    stored child) do not resolve to a read of the stored value (check with a throwaway script in the
    scratchpad: the shell mangles accents).
  - `CognitiveController.__init__` takes `recall_answerer`, `household_tools`,
    `observed_person_resolver` and `consent_resolver`; `_resolved_need` passes `recall=True` only
    with a recall answerer; continuity is written only by `text_turn` (`continuity.record_pair`).
  - `FusedIdentityResolver.last_reason` is `FusionReason.VETO_MULTIPLE_FACES` after a two-face
    frame, `FACE_ONLY` for a face-identified owner whose voice did not verify (or with no speaker
    factory) and `FACE_AND_VOICE` at `strong`; `peek_actor` judges face and voice without spending a
    grant; `_RequestIdentity.fused` is reachable where the voice controller is built.
  - `authorization._lacks_assurance` raises the need to `strong` for any
    `PERSONAL_MEMORY_STRONG_CATEGORIES` datum, and `READ_PERSONAL_CONVERSATION_MEMORY` has
    `consent_applies=True`.
  - A throwaway policy check: `EXECUTE_HOUSEHOLD_TOOL` for `child_of` and `READ_HOUSEHOLD_DATA` for
    a child's `birth_date` (`household` / `child_data`) **allow** the face-identified owner at
    `basic` with the consent the face path returns. If not, stop: the children's birthdays need a
    policy change the ADR did not decide.
  - The canonical writer stores the owner's pool literals (`medication` … `secret_holder`) with
    visibility `personal` and the registry's default sensitivity, and the owner's own
    `birth_date` as `personal`/`private` (`canonical_writer._OWNER_PRIVATE_LITERALS`); a child's
    `birth_date` as `household`/`child_data` (D-4).
  - `HouseholdKnowledgeTools.get_person_birth_date(*, person_entity_id, actor, consent,
    correlation_id, requested_at)` exists, and `get_children` reads the `child_of` relations
    whose ids D-10 reuses.
  - The personal-memory policy pins live in `tests/unit/test_personal_memory_policy.py`
    (`_BASIC_ACTIONS`, the D-10 matrix oracle, the strong-categories test); list the exact
    tests that pin «read + medical/location at basic is denied» in the PR.
  - `routers/transcribe._record_plan` is the only place a deterministic voice reply is recorded, and
    `recall_store.tells_something` decides whether a heard text becomes a recall unit.
  - `commissioning.importer_window_open()` counts the closed records.
  - No existing test phrase in `tests/` states or asks a secret value as D-2 defines it (a list of
    hits, if any, goes in the PR; they will change with `MEMORY_ENABLED` on).
- [ ] **Step 3:** Run the baseline and write the count in the PR:
  `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and not eval" -q -n auto`.

---

### Task 1: The secret words and the value rule

**Files:** Create `server/secret_values.py`, `tests/unit/test_secret_values.py`,
`tests/fixtures/secret_phrases.yaml`; modify `memory/recall_sensitivity.py`,
`tests/unit/test_recall_sensitivity.py`.

**Interfaces:**
- Produces: `SECRET_WORDS: Final[frozenset[str]]`;
  `class SecretKind(StrEnum): STATED = "stated"; ASKED = "asked"`;
  `def secret_kind(message: str) -> SecretKind | None` (pure; `STATED` wins over `ASKED`).
- `recall_sensitivity`'s security terms are `SECRET_WORDS | {"alarma", "llave", "llaves", "porton"}`.

- [ ] **Step 1: Write the failing tests** over the YAML fixture (three lists, Spanish phrases):
  `stated` («mi clave es 1234», «la contraseña es perro123», «el pin es uno dos tres cuatro», «mi
  clave es 12 34», «la clave: 1234», «la clave del banco cuatro cinco seis», «CLAVE es perro123»,
  «la clave treinta y cinco cuarenta», «la clave es que llegues temprano» and «mi código postal
  es 8320000» as accepted false positives); `asked` («¿cuál es mi clave del banco?», «dime la
  contraseña del wifi», «¿me recuerdas mi pin?», «¿qué clave tengo?»); `none` («hoy cambié la
  clave del wifi», «eso es clave para mí», «el código del colegio cambió», «el código es un
  desastre», «mi código es en python», «¿cuál es la clave del éxito?», «¿cuál es el código de
  barras?», «¿quién conoce la clave del banco?», «dejé las llaves en la mesa», and «1234 es mi
  clave» as an accepted miss).
  `test_each_fixture_phrase_has_its_kind`; `test_stated_wins_when_a_message_also_asks`;
  `test_the_recall_security_set_is_derived_from_the_secret_words` (an identity check against
  `SECRET_WORDS`, and `codigos` classifies `security`).
- [ ] **Step 2:** Run `uv run pytest tests/unit/test_secret_values.py tests/unit/test_recall_sensitivity.py -q`
  → FAIL (module missing).
- [ ] **Step 3:** Implement `secret_kind` with `normalize_spanish` and the D-2 lists; make
  `recall_sensitivity` import `SECRET_WORDS`.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** commit `feat: tell a stated or asked secret value apart (plan 0079)`.

---

### Task 2: The policy reads the owner's own health and home at `basic`

**Files:** Modify `cognition/authorization.py`, `memory/commissioning.py`; tests in
`tests/unit/test_personal_memory_policy.py` (the pinned rows and the matrix oracle listed in
Task 0) and the commissioning repository test.

**Interfaces:**
- Produces: `OWN_READ_BASIC_CATEGORIES: Final = frozenset({DataSensitivity.MEDICAL, DataSensitivity.LOCATION})`;
  `_lacks_assurance` requires `strong` only for the categories in
  `PERSONAL_MEMORY_STRONG_CATEGORIES - OWN_READ_BASIC_CATEGORIES` when the action is
  `READ_PERSONAL_CONVERSATION_MEMORY` and the data is the actor's own; `async def
  has_closed_commissioning() -> bool` in `commissioning.py`, and `importer_window_open()` returns
  `not await has_closed_commissioning()`.

- [ ] **Step 1: Write the failing tests:** `test_the_owner_reads_own_medical_data_with_the_face`
  (basic, consent `GRANTED` → `ALLOWED`); `..._own_location_data_with_the_face`;
  `test_own_medical_read_without_consent_is_denied`; `test_own_biometric_read_still_needs_strong`;
  `test_proposing_medical_data_still_needs_strong`; `test_another_persons_medical_read_is_denied`;
  `test_a_security_read_with_the_face_alone_is_denied`;
  `test_has_closed_commissioning_tells_open_from_closed`. The pinned rows that said «read +
  medical/location at basic is denied» change **for the own read only**, and the matrix oracle
  gains that single exemption (`read_personal_conversation_memory` with `medical` or
  `location`, own data); every other row, `biometric` included, keeps its result.
- [ ] **Step 2:** Run the two test files → FAIL on the new tests only.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS; `uv run pytest tests/unit -q -k "authoriz or policy or commissioning"`.
- [ ] **Step 5:** commit `feat: read the owner's own health and home at basic (plan 0079)`.

---

### Task 3: The sensitive question grammar

**Files:** Create `cognition/sensitive_questions.py`, `tests/unit/test_sensitive_questions.py`,
`tests/fixtures/sensitive_questions.yaml`; modify `cognition/household_request.py` (+ its test).

**Interfaces:**
- Produces: `class SensitiveTopic(StrEnum)` with the twelve members of D-3 (values the lower-case
  names); `class SensitiveLevel(StrEnum): SENSITIVE = "sensitive"; SECURITY = "security"`;
  `TOPIC_PREDICATE: Mapping[SensitiveTopic, str]`; `TOPIC_LEVEL: Mapping[SensitiveTopic,
  SensitiveLevel]`; `TOPIC_LABEL: Mapping[SensitiveTopic, tuple[str, str]]` (visibility,
  sensitivity, D-4) (all `MappingProxyType`); `sentence_body(message: str) -> tuple[str, ...]` in
  `household_request`; `@dataclass(frozen=True) class SensitiveQuery: topic: SensitiveTopic;
  keywords: tuple[str, ...]`; `def classify_sensitive_question(message: str) -> SensitiveQuery | None`.

- [ ] **Step 1: Write the failing tests** over the fixture: every D-3 phrase in a full question,
  with «oye», «Iroko», «po» and «¿», and two speech-to-text slips each (no accents, «sanguinio»,
  «cumpleaño»); the traps resolve to `None` («¿qué remedios toma?», «ayer hablé de mis remedios con
  el doctor», «¿cuál es la dirección del colegio?», «¿dónde dejé las llaves?», «¿quién conoce a
  Zeta?», «te cuento que cambié mi dirección de correo», «¿cuál es mi dirección de correo?»,
  «donde vivo hace frío», «cuando cumplo años me regalan libros», «tomo anticoagulante desde
  hace años», «¿me mandas esto a mi dirección?»). `test_sentence_body_drops_the_fillers` (in
  `household_request`, the fillers defined once); `test_every_topic_has_its_predicate_level_and_label`
  (the D-4 map, exact, the owner's birthday `personal`/`private`);
  `test_keywords_drop_the_phrase_and_the_stopwords` («¿quién conoce la clave del banco?» →
  `("banco",)`; «¿cuándo cumple Zeta?» → `("zeta",)`).
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** commit `feat: recognize the owner's sensitive questions (plan 0079)`.

---

### Task 4: The answer templates and the values said aloud

**Files:** Create `cognition/sensitive_answers.py`, `tests/unit/test_sensitive_answers.py`; modify
`cognition/spoken_dates.py` (+ its test), `cognition/controller.py` (import `spanish_join`).

**Interfaces:**
- Consumes: `SensitiveTopic` (Task 3).
- Produces: `def spanish_join(values: tuple[str, ...]) -> str` (moved, behaviour unchanged);
  `def spoken_blood_type(value: str) -> str`; `def word_own_answer(topic: SensitiveTopic,
  values: tuple[str, ...]) -> str` (`values` non-empty, as stored; ISO dates for `OWN_BIRTHDAY`);
  `def word_children_birthdays(children: tuple[tuple[str, date | None], ...]) -> str`;
  `def day_month_label(day: date) -> str` in `spoken_dates.py` («el 3 de marzo», the existing
  month tuple).

- [ ] **Step 1: Write the failing tests:** one per D-7 template, singular and plural, with the
  canaries; `test_every_blood_type_has_a_spoken_form` (all eight); the three anticoagulant answers;
  `test_a_reference_is_read_as_written` (an entry with «clave» and digits); an address with «#» and
  digits; `test_one_child_without_a_date_in_a_list`; `test_spanish_join_is_unchanged` (one, two,
  three labels, the controller's existing children answer still «Tus hijos son Zeta y Omega.»).
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS, the controller suite
  included.
- [ ] **Step 5:** commit `feat: word the owner's sensitive answers (plan 0079)`.

---

### Task 5: The two needs and the rule order

**Files:** Modify `cognition/intent_resolution.py`, `cognition/response_plan.py`,
`memory/recall_store.py`, `tests/unit/test_intent_resolution.py`, the recall-store test.

**Interfaces:**
- Consumes: `secret_kind` (Task 1), `classify_sensitive_question` (Task 3).
- Produces: `InformationNeed.SENSITIVE_READ = "sensitive_read"`,
  `InformationNeed.SECRET_VALUE = "secret_value"`; `resolve_information_need(message, *,
  recall: bool = False, sensitive: bool = False, secrets: bool = False) -> IntentResolution` with the
  rule ids `sensitive.{topic}.v1`, `secret.stated.v1`, `secret.asked.v1`; the tuple per flag set is
  built once (`functools.cache` over the three booleans), D-1's order.
- `tells_something(text)` resolves with `recall=True`, `sensitive=settings.sensitive_read_enabled`
  and `secrets=settings.memory_enabled`, so with the switch off an ordinary «¿cuál es mi
  dirección?» still becomes a unit exactly as today, and with it on a sensitive question does not.

- [ ] **Step 1: Write the failing tests:** `test_with_every_flag_off_the_rules_are_unchanged` (the
  whole existing route corpus, byte-identical resolutions); `test_a_sensitive_question_needs_the_flag`;
  `test_a_secret_needs_the_flag`; `test_a_stated_secret_wins_over_a_sensitive_question`
  («mi clave es 1234, ¿cuál es mi dirección?»); `test_the_security_question_is_a_read_not_a_secret`;
  `test_the_sensitive_rule_comes_before_the_household_protection` («¿cuál es mi dirección?» with
  recall off and on); `test_a_secret_wins_over_a_memory_answer` («sí, mi clave es 1234»);
  `test_tells_something_follows_the_switches` (a sensitive question tells nothing only with the
  switch on; a stated secret tells nothing with memory on); `test_the_security_question_is_ordinary_with_the_switch_off`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS;
  `uv run pytest tests/unit -q -k "intent or recall"`.
- [ ] **Step 5:** commit `feat: route sensitive questions and secret values (plan 0079)`.

---

### Task 6: The sensitive store and access

**Files:** Create `memory/sensitive_store.py`, `memory/sensitive_access.py`,
`tests/unit/test_sensitive_access.py`, `tests/integration/test_sensitive_store.py`; modify
`cognition/household_tools.py` (+ its test), `cognition/response_plan.py`.

**Interfaces:**
- Consumes: Tasks 2 to 4.
- Produces, in `response_plan.py` (the core, so the controller imports no `server.memory`):
  `class SensitiveOutcome(StrEnum)` with D-12's seven outcomes;
  `@dataclass(frozen=True) class SensitiveReply: outcome: SensitiveOutcome; text: str | None =
  field(default=None, repr=False)`; `type SensitiveReader = Callable[[ActivePersonContext,
  SensitiveQuery, CognitiveEvent[TextTurnPayload]], Awaitable[SensitiveReply]]`.
- `async def read_own_values(owner_entity_id: int, predicate: str, sensitivity: str) ->
  tuple[str, ...]` (active literals of the owner, visibility `personal` and that sensitivity,
  ordered by id) in `sensitive_store.py`.
- `HouseholdKnowledgeTools.get_children_birthdays(*, parent_entity_id: int, actor, consent,
  correlation_id, requested_at) -> ChildBirthdays` with `@dataclass(frozen=True) class
  ChildBirthdays: status: KnowledgeStatus; children: tuple[tuple[str, str | None], ...] =
  field(default=(), repr=False)` (label, ISO date or `None`), sorted by label; it composes the
  `child_of` read of `get_children` and `get_person_birth_date` per child (D-10).
- `async def sensitive_reply(actor: ActivePersonContext, query: SensitiveQuery, *,
  faces: FusionReason | None, face_consent: ConsentStatus, voice_check: bool, correlation_id: UUID,
  now: datetime, household_tools: HouseholdKnowledgeTools, policy: PolicyEvaluator =
  evaluate_authorization, audit: AuditWriter = record_authorization_decision,
  alta_closed: Callable[[], Awaitable[bool]] = has_closed_commissioning, names: Callable[[],
  Awaitable[frozenset[str]]] = read_household_names) -> SensitiveReply`, in this
  fixed order: for `CHILD_BIRTHDAY` only, the household decision of D-5 (`NOT_HOUSEHOLD`, nothing
  read, nothing audited); `faces is VETO_MULTIPLE_FACES` → `NOT_ALONE` (nothing read, nothing
  audited); not `may_read_own_memory(actor)` → `DENIED`; level `SECURITY` and assurance below
  `strong` → `RETRY_VOICE` if `voice_check` and `faces is FACE_ONLY`, else `DENIED` (D-11); consent (D-9); policy request (D-10) and the audit
  row (a failing audit → `UNAVAILABLE`, no read); not allowed → `DENIED`; read; nothing →
  `NOT_REGISTERED` (`CHILD_BIRTHDAY`: a relative word or a stored name that is no child →
  `NOT_REGISTERED` with `NO_BIRTH_DATE`; no family word and no stored name → `NOT_HOUSEHOLD`, decided
  before any policy call); else `ANSWERED` with the D-7 text, selecting entries or children by D-5. It never
  raises; a store error is `UNAVAILABLE` and one class-only warning.

- [ ] **Step 1: Write the failing tests** (doubles for policy, audit and store; invented canaries):
  `test_two_faces_hear_not_alone_and_nothing_is_read_or_audited`; `test_a_stranger_is_denied`;
  `test_no_frame_is_denied_never_not_alone` (Review focus 3);
  `test_security_with_the_face_alone_asks_to_retry`; `test_security_without_a_voice_backend_is_denied`
  (the setting off, and `BACKEND_UNAVAILABLE` or `ERROR` with it on; Review focus 4); `test_security_with_face_and_voice_answers`; `test_no_closed_alta_is_denied`;
  `test_the_audit_row_precedes_the_read`; `test_a_failing_audit_reads_nothing`;
  `test_nothing_stored_is_not_registered`; `test_the_matching_reference_entries_are_read`;
  `test_no_matching_entry_reads_them_all`; `test_a_named_child_is_read`; `test_all_children_are_read`;
  `test_a_name_that_is_no_child_has_no_birth_date`; `test_a_stranger_name_is_not_a_household_question`
  («¿cuándo nació Mozart?» → `NOT_HOUSEHOLD`, nothing audited, also with two faces);
  `test_a_stored_name_asked_by_a_visitor_is_not_a_household_question` (no oracle, Plan 0077);
  `test_the_owners_birthday_is_read_as_private_without_consent`; `test_no_value_reaches_a_log_line` (caplog over
  every outcome). Integration (a real migrated database, the canonical writer): rows of another
  visibility or sensitivity are not read; revoked rows are not read;
  `get_children_birthdays` returns a child without a date as `None`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** commit `feat: read the owner's sensitive data after the checks (plan 0079)`.

---

### Task 7: The controller branches

**Files:** Modify `cognition/controller.py`, `cognition/response_plan.py`; create
`tests/unit/test_controller_sensitive.py`.

**Interfaces:**
- Consumes: Tasks 5 and 6.
- Produces: `CognitiveController(..., sensitive_reader: SensitiveReader | None = None,
  secret_guard: bool = False)`; `_resolved_need` passes `sensitive=self._sensitive_reader is not
  None` and `secrets=self._secret_guard`; `SECRET_VALUE` → a `DETERMINISTIC` `UNKNOWN` plan with
  `SECRET_REFUSAL`, resolving **no** actor; `SENSITIVE_READ` → the observed actor (never spends a
  grant), `classify_sensitive_question`, the reader, cached per `event_id` like `_recalls`, and the
  outcome mapped: `ANSWERED` → `KNOWN` with the text, `NOT_ALONE` → `NOT_ALONE`, `RETRY_VOICE` →
  `SECURITY_VOICE_RETRY`, `DENIED` → `_PROFILE_SUMMARY_UNKNOWN_RESPONSE`, `NOT_REGISTERED` → the
  reply's text or `NOT_REGISTERED`, `UNAVAILABLE` → `_PROFILE_SUMMARY_UNAVAILABLE_RESPONSE`,
  `NOT_HOUSEHOLD` → `None` (ordinary conversation).
- `response_plan.py`: the D-6 and D-8 constants; `spoken_log_text` returns
  `SENSITIVE_RECORDED_TEXT` for a `KNOWN` `SENSITIVE_READ` plan; `def recorded_exchange(plan:
  ResponsePlan, heard: str) -> tuple[str, str]` returns `(SECRET_RECORDED_TEXT, plan.response)` for
  `SECRET_VALUE`, `(heard, SENSITIVE_RECORDED_TEXT)` for a `KNOWN` `SENSITIVE_READ`, else
  `(heard, plan.response)`.

- [ ] **Step 1: Write the failing tests:** one per outcome mapping; `test_a_secret_turn_calls_no_model_and_no_resolver`;
  `test_a_sensitive_answer_never_spends_a_grant`; `test_a_sensitive_answer_is_not_written_to_continuity`;
  `test_without_the_reader_a_sensitive_question_resolves_as_today`;
  `test_without_the_guard_a_secret_is_ordinary_conversation`; `test_recorded_exchange_markers`;
  `test_the_spoken_log_shows_the_marker`; the no-voseo guard passes over the new phrases.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS, the whole controller
  suite included.
- [ ] **Step 5:** commit `feat: answer sensitive questions and refuse secrets (plan 0079)`.

---

### Task 8: The switch and the wiring

**Files:** Modify `settings.py`, `.env.example`, `routers/transcribe.py`, `routers/chat.py`,
`routers/vision.py`; tests in `tests/api/` (the voice-route byte-identity tests), the chat and
vision route tests.

**Interfaces:**
- `sensitive_read_enabled: bool = False` (`SENSITIVE_READ_ENABLED`, documented in `.env.example`).
- `routers/transcribe._sensitive_reader(request_identity, household_tools) -> SensitiveReader | None`:
  `None` unless `settings.memory_enabled and settings.sensitive_read_enabled`; the closure reads
  `request_identity.fused.last_reason` and `await request_identity.resolve_consent(event, actor)` at
  call time and passes `voice_check=settings.speaker_authentication_enabled`. Both voice routes pass
  it and `secret_guard=settings.memory_enabled`; `/chat` and `/vision/respond` pass only
  `secret_guard=settings.memory_enabled`.
- `_record_plan` records `recorded_exchange(plan, heard)` instead of `(heard, plan.response)`.

- [ ] **Step 1: Write the failing tests:** `test_with_the_switch_off_every_read_route_is_byte_identical`
  (classic and streaming, a sensitive question and a generic one, against `main`'s behaviour);
  `test_with_memory_off_a_secret_is_byte_identical`; `test_a_stated_secret_on_each_route`
  (classic, streaming, `/chat`, `/vision/respond`: the fixed phrase, no model call; on the voice
  routes the record gets `SECRET_RECORDED_TEXT`, no unit and no candidate);
  `test_the_secret_guard_runs_with_the_record_off` (`CONVERSATION_RECORD_ENABLED=false`: the
  fixed phrase, no model call); `test_with_memory_on_existing_route_tests_still_pass` (the
  hits listed in Task 0, if any, updated in this commit with their reason);
  `test_a_sensitive_answer_is_recorded_with_the_marker`; `test_a_two_face_frame_hears_not_alone`
  (classic and streaming, the `done` event carries no new field); `test_the_reader_is_built_only_with_both_switches`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** implement. **Step 4:** Run → PASS; the whole unit, API
  and integration suites with `MEMORY_ENABLED=false`.
- [ ] **Step 5:** commit `feat: wire the sensitive read and the secret guard (plan 0079)`.

---

### Task 9: Guards and whole-project checks

**Files:** Modify `tests/unit/test_architecture_guards.py`.

- [ ] **Step 1: Write the failing guards:** `test_the_generic_prompt_still_reads_no_household_store`
  (extended: no `sensitive_*` or `secret_values` import in `characters/`, `llm*.py`,
  `streaming*.py`, `text_turn.py`); `test_the_secret_words_are_defined_once` (no other module
  spells the frozenset of D-2); `test_the_pool_literals_are_read_only_where_allowed` (an explicit
  allow-list of the modules that call `get_active_literal_facts` today, Task 0 lists them, plus
  `memory/sensitive_store.py`; any other caller fails).
- [ ] **Step 2:** Run → FAIL where new. **Step 3:** implement. **Step 4:** Run →
  `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and not eval" -q -n auto`,
  `uv run pyright`, `uv run mypy server/src robot/src`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run ruff check scripts/*.py`, `just gate` — all pass. Write
  the test count in the PR.
- [ ] **Step 5:** commit `test: guard the sensitive read and the secret rule (plan 0079)`.

---

### Task 10: Truth, acceptance and close

**Files:** `docs/architecture/current-state.md` and its Archify diagram (validate → deliver), the
operator manual (`docs/runbooks/operator-manual.md`: `SENSITIVE_READ_ENABLED`, the questions, the
phrases, the markers, the debug log never on in production, the security level needs
`SPEAKER_AUTHENTICATION_ENABLED`), `docs/evals/0079-sensitive-read-acceptance.md` (new, outcomes
only), ADR 0029 (`Accepted`), ADR 0019 §3, ADR 0026 and ADR 0027 (amendment notes),
`docs/architecture/seed-data-pool.md` (the capabilities table), the plan board, the roadmap step 3,
the memory map.

- [ ] **Step 1: Hardware acceptance by Pipec** (streaming, and classic if he chooses), outcomes
  only: (1) a medication and (2) the address asked with only his face in view, no question back;
  (3) his birthday and a child's; (4) the security reference with face and voice; (5) the same
  with a short question → the retry phrase; (6) a second face (a photo on a phone) → «Te lo digo
  cuando estemos solos.»; (7) the camera covered → the denial; (8) a stated secret → the fixed reply,
  and `iroko-admin conversations` shows the marker; (9) «hoy cambié la clave del wifi» → an
  ordinary reply. Pipec's real phrasings that missed the grammar are added to the Task 3 fixture
  and the grammar in a fix commit, and recorded as counts only.
- [ ] **Step 2:** Update the documents above; ADR 0029 → `Accepted`; move the plan to
  `completed/`.
- [ ] **Step 3:** commit `docs: close plan 0079, sensitive read accepted`, push, open the PR,
  squash-merge with green CI (GitHub is delegated), delete the branch, return to `main`.

---

## Non-goals

Keeping any secret value, answering in company, the two-face veto (ADR 0030); recalling `medical`
or `location` conversation units (a roadmap row); reading anyone else's sensitive data; `lives_in`
and «no menciones X» by voice; the cleanup of old secrets (the count found none, ADR 0029 decision
20); dataset v4 of the benchmark (the CM-7 preparation); the debug heard-log; any change to the
generic prompt, the wire, the robot, a migration, the 0077 household rule or `lexicon.SENSITIVE_WORDS`
(a different list: the taste gate).

## Self-review (2026-11-05)

- **Spec coverage.** ADR 0029 decision 1 (levels, consent, retry) → Tasks 2, 3, 6; 2 (replay) →
  nothing to build, stated in Task 10's documents; 3 (silent camera check) → Tasks 6 and 8; 4
  (templates, record marker, references, birthdays, spoken values, debug log) → Tasks 4, 7, 8; 5
  (value rule, order, one list, stated before asked, cleanup lapsed) → Tasks 1, 5, 7, 8; 6 and 21 →
  Non-goals; 7 (switch, secret guard with memory) → Task 8; the author's calls → D-9 to D-11 and
  Tasks 6 to 8; *Test consequences* → Tasks 1 to 10.
- **Type consistency.** `SecretKind`, `SensitiveTopic`, `SensitiveLevel`, `SensitiveQuery`,
  `SensitiveOutcome`, `SensitiveReply`, `SensitiveReader`, `ChildBirthdays` are each defined once
  and named the same in every later task.
- **Size.** Ten working tasks after Task 0, under Plan 0078's twelve; no migration.
- **Independent review (2026-11-05).** A fresh reviewer read the plan against the ADR and the
  code: 1 Critical (the owner's birthday is stored `private`), 8 Important (the policy pins live in
  `test_personal_memory_policy.py`; a general-knowledge birth question; the grammar matched
  mentions; the secret rule fired on a developer's «el código es…»; `tells_something` broke byte
  identity; the bare resolver call; the guard allow-list; reuse `get_person_birth_date`) and 6
  Minor. All are applied above, in D-1 to D-12 and Tasks 0 to 9.
