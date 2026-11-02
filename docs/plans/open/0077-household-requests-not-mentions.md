# 0077 — The household protection answers requests, not mentions

> **Status:** `Ready` and `NOW`, promoted by Pipec on 2026-11-02, who confirmed D-1 to D-21 (D-17
> accepted as recommended); written 2026-10-30 against `main` at `d7ef78a`. Pipec chose to execute it in
> the same session. The Chilean-idiom dictionary he raised is decided at the close (see *Not here*). Step 1 of the
> [closing path of conversational memory](../../roadmap/cognitive-roadmap.md#closing-path-of-conversational-memory).
> **Rehearsed** in a scratch copy of that commit and **reviewed** by three independent read-only
> reviewers; the numbers are in *Rehearsal* and the findings in *Reviews*. The tasks are specifications
> (files, signatures, closed values, tests to write first), not diffs. Queue rule 4 applies: Task 0
> re-verifies the claims below against the merged code and **stops and reports** if one is false.

> **For agentic workers:** if the status above does not say `Ready`, stop: Pipec has not promoted this
> plan. REQUIRED SUB-SKILLS: `superpowers:executing-plans`, `superpowers:test-driven-development`,
> `superpowers:verification-before-completion`, `superpowers:finishing-a-development-branch`.
> **Pipec's rules win over the skills:** one plain branch from `main` (`feat/0077-household-requests`),
> never a git worktree, subagents only if Pipec asks, this plan lives under `docs/plans/`. One commit per
> task; every code test seen RED for the stated reason first. If evidence contradicts the plan, stop and
> report instead of redesigning. The Bash tool of this environment loses backslashes and non-ASCII
> characters in heredocs: use the Write and Edit tools. Commit messages: Conventional Commits, title at
> most 72 characters, check `git log` after each commit (the hook rejects silently); do not pipe
> `git commit`; `git add` with explicit paths. Run the suite with `MEMORY_ENABLED=false` as CI does. Never
> run `uv sync --all-packages --all-groups` (it removes the optional `cuda` extra). **Do not run
> `just gate` in the background while Pipec rehearses** (about 3.5 GB of RAM). **The server and the robot
> are started by Pipec**, never by the agent; record outcomes only, never a sentence, a value or a name.
> Before pushing, run `pyright`, `ruff` and `mypy` over the **whole** project and `ruff format --check .`
> (CI also formats the Python blocks of the `.md` files).

**Goal.** The robot stops cutting a conversation short when the person only tells it something about
their family or pet. «Hoy voy a salir con mis hijos.», «Me gusta el sushi y a mis hijos también.» and
«¿Qué le regalo a mi hija?» reach the model; «¿Cuándo nació mi mamá?» keeps the protected route;
«¿Cuándo nació Mozart?» is an ordinary question. No wire change, no migration, no new setting, no
prompt change, no robot change.

**Why.** Today `_protected_household_rule` fires on a household word anywhere, on «le gusta» alone and
on a birth word alone, with no request in the sentence. Found by Pipec on hardware during
[Plan 0076](../completed/0076-cm4-conversation-record-and-diary.md) and again in later tests. The rule
guesses privacy from loose words, while what protects the stored data is elsewhere: the prompt of a
generic turn carries the character, the profile card and the session, and **no value read from a
household store**, so a turn routed to the model by mistake can invent and cannot reveal a stored
value. Task 4 pins that with an architecture guard, because this plan now rests on it. The word rule
therefore has one honest job: keep the model from inventing an answer about the family when someone
asks for a datum.

**What does change in what is kept.** A mention used to get a fixed reply and stop there. It now takes
the path of any generic turn: it enters the short session (3000 characters, 180 s) of the identified
speaker, its real reply enters the conversation record, and it passes through the taste gate. See D-17.

**Architecture.** One new pure module, `cognition/household_request.py`, judges each sentence and calls
it a household request when **three things hold together**: it names the household (a first-person
possessive before a relative or a pet), it asks for a datum, and it has the form of a request.
`intent_resolution` uses it and hands one utterance to each rule. A question about someone it does not
name as family resolves to ordinary conversation in the pure resolver; the controller then compares it
with the household's stored names, and only an owner's or an adult's question about a stored name takes
the protected path. Two neighbouring rules with the same defect («años», «relación») stop firing on a
loose word.

**Tech stack.** Python 3.12, pytest. No new dependency.

**Spec.** The Decisions below; [ADR 0023](../../adr/0023-speech-to-text-model-and-decoding.md)
decision 7 (the mark is missing on 3 of 10 questions); [ADR 0022](../../adr/0022-household-rules-and-third-party-memory.md)
(a pet's data is `household`); [ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md)
decision 9 (the answer grammar); [ADR 0020](../../adr/0020-authorized-actor-in-the-conversation.md) (the
session); [ADR 0005](../../adr/0005-small-typed-cognitive-controller.md) (the controller owns policy); the
roadmap row «The household protection answers questions, not mentions». No ADR changes: authorization,
the fixed replies and the audit of a protected branch are untouched. This plan replaces item 6 of
[Plan 0050](../completed/0050-server-audit-repairs.md) («"Mi papá es ingeniero" must still be protected»)
on Pipec's decision; Plan 0050 stays as written.

## Required reading

- `AGENTS.md`, `docs/architecture/implementation-guardrails.md`, `.claude/rules/`.
- [ADR 0023](../../adr/0023-speech-to-text-model-and-decoding.md) decision 7,
  [ADR 0022](../../adr/0022-household-rules-and-third-party-memory.md) decision 10,
  [ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md) decision 9,
  [ADR 0020](../../adr/0020-authorized-actor-in-the-conversation.md) decision 1.
- `server/src/server/cognition/{intent_resolution,controller,authorization}.py`,
  `server/src/server/memory/entity_labels.py`, `server/src/server/routers/{transcribe,chat}.py`.
- The tests named in each task.

## Permitted files

Those of *File structure* and of Task 6. No new URL, field, migration, setting or dependency.
`server/src/server/routers/vision.py`, the characters, the prompts and the robot are not edited.

## Decisions

Confirmed by Pipec on 2026-10-30, before the plan was written:

- **D-1 Three conditions together.** A household request names the household **and** asks for a datum
  **and** has the form of a request. A story and a piece of advice are conversation. This replaces the
  roadmap's «questions, not mentions»: «¿Qué le regalo a mi hija?» is a question that asks for no datum.
- **D-2 The neighbouring rules are fixed here.** `_explicit_age_rule` and `_relationship_rule` fire on
  «años» and «relación» alone («Hace dos años fui a Valparaíso.» answers «No puedo calcular la edad sin
  una fecha de nacimiento ISO válida.»). Same defect, and «Mi hijo cumple diez años» would keep failing.
- **D-3 Someone else is conversation.** «¿Cuándo nació Mozart?» and «¿Cuándo nació el papá de Mozart?»
  reach the model. A stored name counts as naming the household for an identified person; a visitor's
  question about a stored name stays conversation (D-16 narrows «identified»).
- **D-4 A question with no mark and no interrogative goes to the model.** «mi hijo tiene alergias» is
  the same text as a statement when Whisper drops the mark. It is measured in Task 7.
- **D-5 Pets are household.** With a possessive only: «¿Cómo se llama mi perro?» is protected,
  «¿Qué comen los perros?» is conversation, «Quiero salir con mi mascota.» is conversation.
- **D-6 The refusal of the pet sentence is measured, not assumed.** «Quiero salir con mi mascota.»
  already resolves to `generic_conversation` on `main`, so the refusal Pipec heard did not come from
  this rule. Task 7 measures where it comes from. If the model says it, this plan does not fix it.
- **D-7 The reviewed fall-through.** «Conoce a mi hija.» and «Aprende la cara de mi hijo.» get the fixed
  enrolment reply; «Mira lo que hizo mi hija.» opens the camera.
- **D-8 The answer grammar keeps its barrier.** A message with the shape of a memory answer keeps the
  broad test, so «sí, autorizo guardar a mi hijo» never reaches the grammar.

The author's calls, confirmed by Pipec on promotion (2026-11-02):

- **D-9 Names first, then the actor.** The stored names are compared first and the actor is observed
  only when a name appears. «¿Quién es…?» is an everyday turn, and judging the face and the voice costs
  3 to 4 s on the shared laptop against one `SELECT`. The cost is a weak timing channel, listed in
  *Known limits*. The answer path (ADR 0021 decision 9) resolves first because a reply there does
  depend on the store; here the reply to a visitor is the model's either way.
- **D-10 «Conoce a» only opens a message.** «Mi mamá conoce a todos.» was protected and would otherwise
  fall to the enrolment reply. The call to the robot may come first («Iroko, conoce a…»).
- **D-11 The lists speak Chilean.** Relatives, pets, fillers, data words and request phrases include how
  people here say them, older adults first: «mi señora», «mi vieja», «mi guagua», «mi quiltro», «me puede
  decir», «no me acuerdo», «cachai». An adversarial run found these to be the main gap (*Reviews*). All
  count only with a first-person possessive.
- **D-12 One word of reach.** One word may sit between the possessive and the relative («mis dos
  perros», «mi querida madre»), not more.
- **D-13 A store failure is conversation.** When the names cannot be read the turn stays generic, with
  one class-only warning. It fails towards conversation, unlike `list_known_names`, because the model
  holds no stored household value and the fixed reply is not worth a broken turn.
- **D-14 The relationship rule becomes closed phrases.** «¿Cuál es la relación entre la luna y las
  mareas?» is conversation; `«relación»` with a relative is already a household request.
- **D-15 `rule_id` values do not change.** No new `InformationNeed`.
- **D-16 Only the roles the policy could let read take the name path.** A child's or a guest's enrolled
  face would otherwise hear a refusal for a stored name and the model for any other, which confirms the
  name exists. `OWNER` and `ADULT` only; the rest stay conversation, like a visitor.
- **D-17 Family talk enters the short session. Accepted by Pipec.** It is the behaviour he asked for and the
  limit ADR 0020 already accepted for ordinary talk: a generic turn identifies by the face alone, so
  someone speaking off camera beside the owner continues the owner's session and could hear it back
  within 180 s. **Recommended: accept it**, and Task 7 case 12 proves the session stops with no face. The
  alternative is not writing a family mention to the session (`mentions_the_household`), at the price of
  the robot forgetting what was just said.
- **D-18 Only a first-person possessive names the household.** «¿Cómo se llama tu perro?» asks the robot
  and «¿Cuándo nació su hijo?» asks about someone else. The broad test of D-8 keeps every possessive.
- **D-19 One sentence at a time, and a closing tag is no question.** «¿Sabes dónde queda la farmacia? Mi
  mamá necesita remedios.» does not add up across sentences; «Mi hijo vive en Temuco, ¿cachai?» is a
  story. An interrogative with no mark must end on the person, so «Cuando nació mi hija llovía mucho.» is
  a story and «cuando nació mi hijo» is not.
- **D-20 The names are read only with memory on.** With `MEMORY_ENABLED=false` the database is closed
  and a read per turn would log one warning per turn. The routes pass no reader.
- **D-21 The prompt rule is written down.** Task 4 adds an architecture guard and Task 6 a line in the
  guardrails: no household store in the generic prompt; a plan that adds one first makes this rule broad
  again. CM-3b, CM-5b and CM-7 are the ones that will meet it.

## Known limits, stated on purpose

- **A stored name that is also a common word or a famous person.** With a pet called Luna, an owner's
  «¿Qué sabes de la luna?» gets the fixed reply, and a stored «Andrés» matches «¿Cuándo nació Andrés
  Bello?». Task 4 pins it.
- **A story with a real question tag.** «Mi hijo nació en marzo, ¿de verdad?» stays protected. Task 1
  pins it.
- **A datum loose inside advice.** «¿Qué le regalo a mi nieto para su cumpleaños?» and «¿Cómo se llama el
  remedio que toma mi papá?» get the fixed reply. A proximity rule was tried and broke real requests.
- **A family word without a first-person possessive.** «¿Cómo se llaman los niños?» reaches the model.
- **A name with no kinship.** «¿Cuántos años tiene la Martina?» takes the protected path only for an
  owner or adult whose question names a stored name; for anyone else the model holds nothing and may
  invent.
- **An unknown datum or a cut word.** «¿Qué hace mi hijo?» and «como se llam mi hijo» reach the model. The
  closed lists grow from what hardware shows, not from guessing.
- **Formal questions with no mark inside a sentence.** «mi hija me dice que…» is a story, so «me dice» is
  no request phrase.
- **A weak timing channel (D-9).** A visitor's question with a stored name takes 3 to 4 s longer inside
  a model turn of 17 to 33 s. The reply holds nothing.
- **An invented reply can reach the diary.** When a request falls outside the lists, the model's reply
  is stored as `said` on a verified turn. The summary prompt treats the robot's words as context; Task 7
  counts it, and CM-5b must cite only the person's lines.
- **Rules not audited here.** The date, identity, scene and own-children rules can also fire inside a
  story («Cuántos hijos tengo no importa», «¿Quién soy yo para juzgar?»). They did not show up on
  hardware; they stay as they are. «Mi hijo me preguntó cuántos años tengo.» reaches the age rule.

## Global constraints

- English code, comments and docstrings (Google style); Spanish only in the closed word lists and the
  corpus. No voseo in spoken strings.
- No `Any`, no `print`, no `os.path`, no bare `except`; logging with `%`; every public API typed and
  documented. `cognition/` imports no `aiosqlite`, no FastAPI, no `httpx` and no `memory`
  (`tests/unit/test_architecture_guards.py`): the name reader is injected.
- `household_request.py` and every rule stay pure: no LLM, no embedding, no database, no fuzzy match.
- **No message text, name or alias in any log line**: exception classes only.
- No real household data anywhere: invented canaries only (`Joaquín`, `Martina`, `Valentina`, `Zeta`).
- The fixed replies, the authorization policy, the prompts (their golden digests) and the wire are
  byte-identical. A generic turn with no name seam behaves as on `main`.
- A mention no longer writes a `READ_HOUSEHOLD_DATA` audit row: it reads nothing, and no requirement asks
  for one. Every protected branch still audits before any effect.
- `requests_household_data` and the rules never read a stored name; only the controller does.

## Review focus

The inputs no task title names; each has its test in the task that owns it.

1. A stored name that is a common word, with an owner (Task 4): the fixed reply, no crash.
2. A story with a real question tag, «Mi hijo nació en marzo, ¿de verdad?» (Task 1): protected, a stated
   limit. A closing «¿cachai?» is not one (Task 1).
3. An empty message, or only fillers: `""`, «oye», «Iroko, por favor» (Task 1): `False`, no `IndexError`.
4. A stored name with an accent, a hyphen or several words, and an empty stored name (Task 1): compared
   after folding, whole words only; «Joaquina» never matches «Joaquín»; an empty name matches nothing.
5. Upper case and spacing from the speech-to-text, «¿CUÁNDO NACIÓ MI HIJO?» (Task 2 corpus): protected.

---

## File structure

| File | Responsibility | Task |
|---|---|---|
| `server/src/server/cognition/household_request.py` (new) | The three conditions, pure | 1 |
| `tests/unit/test_household_request.py` (new) | What the corpus cannot say | 1 |
| `server/src/server/cognition/intent_resolution.py` | `_Utterance`; the household, age, relationship and enrolment rules | 2, 3 |
| `tests/fixtures/intent_resolution_es.json`, `tests/unit/test_intent_resolution.py`, `tests/unit/test_memory_answer_grammar.py`, `tests/unit/test_cognitive_controller.py`, `tests/integration/test_conversation_record_routes.py`, `tests/evals/stt_reading_script.yaml` | The reviewed corpus and its pins | 2, 3 |
| `server/src/server/cognition/controller.py` | The stored-name seam | 4 |
| `server/src/server/memory/entity_labels.py` | `read_household_names`, the reader that never raises | 4 |
| `server/src/server/routers/transcribe.py`, `server/src/server/routers/chat.py` | Hand the reader to the controller, with memory on | 4 |
| `tests/unit/test_cognitive_controller.py`, `tests/integration/test_household_names.py` (new), `tests/unit/test_architecture_guards.py` | The seam, the wiring and the prompt guard | 4 |
| `docs/evals/0077-household-requests-acceptance.md` (new) and the documents of Task 6 | Truth and the record | 6, 7 |

---

### Task 0: Re-audit and baseline

**Files:** none changed.

- [ ] **Step 1:** This plan says `Ready`; otherwise stop. `git checkout main && git pull`, clean tree (the
  untracked `docs/evals/longitudinal-memory-v3.md` is Pipec's and stays untouched), then
  `git checkout -b feat/0077-household-requests`; record the base SHA.
- [ ] **Step 2:** Verify, and **stop and report** if any is false:
  - `_RULES` in `intent_resolution.py` is the tuple of 13 rules ending in `_memory_answer_rule`, with
    `_protected_household_rule` third.
  - `build_system_prompt` receives no household store data: `profile_card` is the only person data
    (`characters/__init__.py`), and the card renders name, form of address and tastes.
  - `decide()` is the entry of the classic, streaming, chat and vision routes, and the classic route
    calls it twice on a turn that falls through (the comment over `_answers`).
  - `FusedIdentityResolver.peek_actor` spends no grant and caches its result.
  - `entity_labels.list_known_names()` exists and raises `BrainMemoryError` when the database is closed.
  - `«Quiero salir con mi mascota.»` resolves to `generic_conversation`.
  - Comparing the need of every string literal of `tests/` on `main` and on this plan's rule finds one
    test that depends on the old behaviour, `test_a_deterministic_turn_keeps_the_speaker_the_controller_resolved`
    (Task 2 changes it). Search `tests/integration` for «mis hijos» and «mi hijo» again; a new one is
    reported.
- [ ] **Step 3:** Run the baseline and write the count in the PR:
  `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and not eval" -q -n auto`.

---

### Task 1: The shape of a household request

**Files:**

- Create: `server/src/server/cognition/household_request.py`
- Test: `tests/unit/test_household_request.py`

**Interfaces.** Produces, all pure. `normalized` is text folded by `normalize_spanish`; `message` and
`sentence` are raw.

```python
BIRTH_WORDS: frozenset[str]


def has_question_mark(message: str) -> bool: ...
def mentions_the_household(normalized: str) -> bool: ...
def opens_with(normalized: str, phrase: str) -> bool: ...
def states_a_request(normalized: str, *, marked: bool) -> bool: ...
def requests_household_data(message: str) -> bool: ...
def requests_data_of_a_name(message: str) -> bool: ...
def names_someone_known(message: str, names: frozenset[str]) -> bool: ...
```

**Closed values.** **Copy** `_POSSESSIVES`, `_HOUSEHOLD_WORDS`, `_HOUSEHOLD_WORDS_NEEDING_POSSESSIVE`,
`_HOUSEHOLD_PHRASES` and the birth words here unchanged from `intent_resolution.py`; Task 2 removes the
originals. Add, folded:

| Constant | Values |
|---|---|
| `_OWN_POSSESSIVES` | mi mis nuestro nuestra nuestros nuestras |
| `_MORE_RELATIVES` | nieto nieta nietos nietas bisnieto bisnieta bisnietos sobrino sobrina sobrinos sobrinas suegro suegra suegros yerno nuera cunado cunada cunados novio novia pololo polola senora senoras viejo vieja viejos viejas hijito hijita hijitos hijitas mamita papito guagua guaguas regalon regalona compadre comadre ahijado ahijada hijastro hijastra bisabuelo bisabuela nene nena bebe chiquillo chiquilla cabro cabra pequeno pequena |
| `_PET_WORDS` | perro perra perros perras perrito perrita quiltro cachorro cachorra gato gata gatos gatas gatito gatita michi mascota mascotas conejo coneja conejos conejito pajaro pajaros pajarito loro lorito canario cotorra tortuga tortuguita hamster cuy cobayo pez peces pececito caballo pollito chanchito |
| `_DATA_WORDS` | anos nacimiento nacimientos nacio cumpleanos cumple cumples cumplio cumplen nombre nombres llama llaman llamaba llamaban apellido apellidos apellida gustos preferencia preferencias favorito favorita favoritos favoritas alergia alergias alergico alergica vive viven trabaja trabajan estudia estudian telefono celular numero correo direccion relacion |
| `_DATA_PHRASES` | «le gusta», «les gusta», «le gustan», «les gustan», «quien es», «quien fue», «quienes son», «edad tiene», «edad tenia», «edad tendra», «edad cumple», «edad de», «edad del», «edades de» |
| `_SOFT_DATA_WORDS` / `_SOFT_DATA_LINKS` | sabes sabe recuerdas acuerdas acuerda / de del sobre a |
| `_INTERROGATIVES` | que cual cuales quien quienes cuando cuanto cuanta cuantos cuantas como donde |
| `_SUBORDINATING_OPENERS` | que cuando como donde |
| `_REQUEST_PHRASES` | «dime», «digame», «me dices», «cuentame», «sabes», «recuerdas», «te acuerdas», «quiero saber», «necesito saber», «me gustaria saber», «quiero que me digas», «quiero que me diga», «me puedes decir», «puedes decirme», «me puede decir», «puede decirme», «me podria decir», «podria decirme», «me podrias decir», «podrias decirme», «usted sabe», «no me acuerdo», «no recuerdo», «se me olvido», «me olvide», «calcula» |
| `_LEADING_FILLERS` | iroko oye oiga hola bueno y a ya disculpa disculpe perdon perdone por favor cachai mira mire entonces pues po eh ah ok ver |
| `_TRAILING_FILLERS` | po pues cachai porfa por favor ya |
| `_VERBLESS_DATA_NOUNS` | fecha ano mes dia edad cumpleanos nombre nombres telefono celular numero correo direccion gustos |
| `_VERBLESS_LINKS` | de del nacimiento cumpleanos en que nacio |
| `_COUNT_WORDS` / `_FIRST_PERSON_HAVE` | cuantos cuantas / tengo tenemos |
| `_TAGS` | cachai no cierto verdad sabes sabe sabias ya ves eh si entiendes, «te conte», «o no», «me entiendes» |

Why the phrases: `gusta` is third-person because «¿Te gusta mi perro?» asks the robot; `edad` needs its
neighbour because «¿A qué edad debería mi hijo empezar el colegio?» asks for advice.

**Rules the signatures leave open:**

- *Sentences:* the raw text split with `re.compile(r"(?<=[.!?])\s+")`. Never split on «¿»: «A mi hijo, ¿qué
  le gusta?» is one sentence. `requests_household_data` and `requests_data_of_a_name` are `any` over them.
- `has_question_mark`: if `re.compile(r"(?:,\s*¿?|\s¿)\s*([^,¿?]+)\?\s*$")` matches and its folded group is
  in `_TAGS`, drop the match; then look for `?` or `¿`. So «¿Mi hijo vive en Temuco, no?» stays marked.
- *Names the household:* a word of `_OWN_POSSESSIVES` with a relative or pet word (the union of the four
  sets) among the next **two** words (D-12).
- *Body:* the words after dropping leading `_LEADING_FILLERS`; all fillers leave the words as they are.
  *Closing fillers:* trailing `_TRAILING_FILLERS` words dropped.
- *A datum:* a `_DATA_WORDS` word; a `_DATA_PHRASES` phrase; `_COUNT_WORDS` right before a relative or pet;
  or a soft word that points at someone: after it, an optional `_SOFT_DATA_LINKS` word and an optional
  article, then a `_OWN_POSSESSIVES` word. On the name path a soft word also counts with a link alone
  («¿Qué sabes de Zeta?»), so `_asks_for_a_datum` takes `possessive_only: bool`.
- *Opening interrogative:* the body opens with `_INTERROGATIVES`, unless that word is in
  `_SUBORDINATING_OPENERS` and the next one is in `_POSSESSIVES` («cuando mi hijo llega…» is a story).
- *Opening request:* the body starts with a `_REQUEST_PHRASES` phrase, as whole words. Only at the opening:
  «mi hijo vive en Temuco, sabes» is a story.
- `states_a_request(normalized, *, marked)`: `marked`, an opening request, or an opening interrogative.
- *Household form:* `marked`, or an opening request, or an opening interrogative **and** one of the last two
  words (closing fillers aside) is a relative or pet.
- *Verbless request:* the body with closing fillers dropped, without one leading article (`el la los las`),
  starts with a `_VERBLESS_DATA_NOUNS` word, ends in a `_OWN_POSSESSIVES` word plus a relative or pet, and
  every word between is in `_VERBLESS_LINKS`. Nothing may follow the person.
- *What one has:* with a mark or an opening interrogative, `tengo|tenemos` with a relative or pet within two
  words on either side and no first-person possessive there («¿Tengo hijos?», «¿Cuántas mascotas tengo?»).
- *One sentence requests:* what one has; or names the household and (verbless, or a datum and the household
  form). The *name* variant: does **not** name the household, a datum with `possessive_only=False`, and
  `states_a_request`.
- `mentions_the_household` is the broad test: a `_HOUSEHOLD_WORDS` or birth word alone, a
  `_HOUSEHOLD_WORDS_NEEDING_POSSESSIVE` word right after a `_POSSESSIVES` word, names the household, or a
  `_HOUSEHOLD_PHRASES` phrase.
- `names_someone_known`: folds each name with `normalize_spanish` and matches it as whole words; an empty
  key matches nothing.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_household_request.py`, marked `unit`:

```python
def _request(message: str) -> bool:
    return requests_household_data(message)


@pytest.mark.parametrize(
    "message",
    [
        "Cuando mi hijo nació lloré.",
        "Como mi hija vive lejos, la llamo.",
        "Que mi hijo sabe nadar.",
    ],
)
def test_a_subordinate_opening_is_a_story_not_a_question(message: str) -> None:
    assert _request(message) is False


def test_a_question_mark_is_one_signal_and_not_the_only_one() -> None:
    assert states_a_request("que edad tiene mi hija", marked=False) is True
    assert states_a_request("mi hijo tiene alergias", marked=False) is False
    assert states_a_request("mi hijo tiene alergias", marked=True) is True


@pytest.mark.parametrize(
    "tag", ["¿cachai?", "¿no?", "¿cierto?", "¿verdad?", "¿sabes?", "¿te conté?"]
)
def test_a_closing_tag_is_not_a_question(tag: str) -> None:
    assert has_question_mark(f"Mi hijo vive en Temuco, {tag}") is False
    assert _request(f"Mi hijo vive en Temuco, {tag}") is False


def test_a_question_that_merely_ends_in_no_keeps_its_mark() -> None:
    assert has_question_mark("¿Mi hijo vive en Temuco, no?") is True


def test_each_sentence_is_judged_alone() -> None:
    assert _request("¿Sabes dónde queda la farmacia? Mi mamá necesita remedios.") is False
    assert _request("Hola Iroko. ¿Qué edad tiene mi hija?") is True
    assert _request("A mi hijo, ¿qué le gusta?") is True


@pytest.mark.parametrize("message", ["¿Cómo se llama tu perro?", "¿Cuándo nació su hijo?"])
def test_only_a_first_person_possessive_names_the_household(message: str) -> None:
    assert _request(message) is False


def test_an_unmarked_question_must_close_on_the_person() -> None:
    assert _request("Cuando nació mi hija llovía mucho.") is False
    assert _request("Cuántos años tiene mi mamá en el cielo, pobrecita.") is False
    assert _request("cuando nacio mi hijo") is True
    assert _request("como se llama mi perro po") is True


@pytest.mark.parametrize(
    "message",
    [
        "El cumpleaños de mi hijo fue genial.",
        "La fecha de nacimiento de mi hija es en marzo.",
        "El nombre de mi perro me gusta.",
    ],
)
def test_a_datum_followed_by_a_verb_is_a_story(message: str) -> None:
    assert _request(message) is False


@pytest.mark.parametrize(
    "message", ["fecha de nacimiento de mi hija", "la edad de mi mamá", "el teléfono de mi hermana"]
)
def test_a_bare_datum_of_a_relative_is_a_request(message: str) -> None:
    assert _request(message) is True


def test_the_possessive_reaches_one_word_and_no_further() -> None:
    assert _request("¿Cómo se llaman mis dos perros?") is True
    assert _request("¿Cómo se llama mi nuevo vecino del perro?") is False


def test_a_story_with_a_question_tag_stays_protected() -> None:
    """A stated limit: the mark and the datum are there, and only meaning tells it apart."""
    assert _request("Mi hijo nació en marzo, ¿de verdad?") is True


@pytest.mark.parametrize("message", ["", "oye", "Iroko, por favor"])
def test_an_empty_or_filler_message_is_no_request(message: str) -> None:
    assert _request(message) is False
    assert requests_data_of_a_name(message) is False


def test_requests_data_of_a_name_needs_a_datum_and_a_request() -> None:
    assert requests_data_of_a_name("¿Cuándo nació Mozart?") is True
    assert requests_data_of_a_name("cuando nacio mozart") is True
    assert requests_data_of_a_name("¿Qué sabes de Zeta?") is True
    assert requests_data_of_a_name("Mozart nació en 1756.") is False
    assert requests_data_of_a_name("¿Qué hora es?") is False
    assert requests_data_of_a_name("¿Cuándo nació mi hijo?") is False


def test_a_stored_name_matches_as_whole_folded_words() -> None:
    names = frozenset({"Joaquín", "Ana María", "Eva-Luna", ""})

    assert names_someone_known("¿Cuándo nació joaquin?", names) is True
    assert names_someone_known("¿Qué le gusta a ANA MARÍA?", names) is True
    assert names_someone_known("¿Qué edad tiene Eva Luna?", names) is True
    assert names_someone_known("¿Qué edad tiene Joaquina?", names) is False
    assert names_someone_known("¿Cuándo nació Ana?", names) is False
    assert names_someone_known("¿Cuándo nació Mozart?", frozenset()) is False
    assert names_someone_known("", names) is False


def test_the_broad_mention_test_keeps_every_family_value_out_of_an_answer() -> None:
    assert mentions_the_household("si autorizo guardar a mi hijo") is True
    assert mentions_the_household("guarda lo que le gusta") is True
    assert mentions_the_household("guarda la fecha de nacimiento") is True
    assert mentions_the_household("guarda mi perro") is True
    assert mentions_the_household("guarda mi papa") is True
    assert mentions_the_household("guarda las papas fritas") is False


def test_opens_with_skips_the_call_to_the_robot() -> None:
    assert opens_with("iroko conoce a esta persona", "conoce a") is True
    assert opens_with("mi mama conoce a todos", "conoce a") is False
```

- [ ] **Step 2: Run them.** `uv run pytest tests/unit/test_household_request.py -q`. Expected: collection
  error, the module does not exist.
- [ ] **Step 3: Implement** `household_request.py`, with a module docstring stating D-1 and why a miss can
  invent and cannot reveal a stored value. Named constants, no magic numbers (`PLR2004`); `ruff` writes the
  word lists as explicit literals (`SIM905`).
- [ ] **Step 4: Run them.** Expected: all pass.
- [ ] **Step 5: Commit** `feat(server): the shape of a household request`.

---

### Task 2: The household rule protects requests

**Files:**

- Modify: `server/src/server/cognition/intent_resolution.py`
- Modify: `tests/fixtures/intent_resolution_es.json`, `tests/unit/test_intent_resolution.py`,
  `tests/unit/test_memory_answer_grammar.py`, `tests/unit/test_cognitive_controller.py`,
  `tests/integration/test_conversation_record_routes.py`, `tests/evals/stt_reading_script.yaml`

**Interfaces.** Consumes Task 1. Produces, private to the module but read by the grammar test:

```python
@dataclass(frozen=True)
class _Utterance:
    message: str
    normalized: str
```

Every rule of `_RULES` takes one `_Utterance`. `resolve_information_need(message)` keeps its signature.

- [ ] **Step 1: Write the failing corpus.** In `intent_resolution_es.json`:
  - **Change these rows.** `«¿Cuándo nació Joaquín?»`, `«Mi papá es ingeniero.»`, `«Mis niños duermen.»` and
    `«Mi mujer cocina.»` become `generic_conversation` / `none` / `null`. `«¿Qué sabes de mi perro?»` and
    `«¿Qué sabe de mi perro?»` become `protected_household` / `exact` / `household.protected.v1`.
  - **Add the rows of group A** (table below).
  - In `test_intent_resolution.py`, the rule-id test uses `«¿Cuándo nació mi hijo Joaquín?»`.
  - In `test_cognitive_controller.py`, `«¿Cuándo nació Joaquín?»` in the extended-denial parameters becomes
    `«¿Cuándo nació mi hijo?»`.
  - In `test_conversation_record_routes.py`, `test_a_deterministic_turn_keeps_the_speaker_the_controller_resolved`
    hears `«¿Cómo se llama mi esposa?»`. With the old sentence it would still pass and exercise nothing.
  - In `stt_reading_script.yaml`, the `expect.need` of H13 («Mi tío tenía una idea increíble.») becomes
    `generic_conversation`.

  | Group A | `need` / `rule_id` |
  |---|---|
  | Hoy voy a salir con mis hijos. · Quiero salir con mi mascota. · Me gusta el sushi y a mis hijos también. · Mis hijos van mañana al colegio. · A Martina le gusta el fútbol. · A mi hijo le gusta el fútbol. · Mi hijo nació en marzo. · Cuando mi hijo llega del colegio le doy once. · Como mi hija tiene clases, salgo tarde. · mi hijo tiene alergias · Mi hijo vive en Temuco, ¿cachai? · Mi hija trabaja en un banco, ¿no? · Mi perro es muy bueno, ¿sabes? · Cuando nació mi hija llovía mucho. · Sabes qué, mi vieja hacía sopaipillas. | `generic_conversation` / `null` |
  | ¿Qué le regalo a mi hija? · ¿Qué película veo con mis hijos? · ¿Cómo ayudo a mi hijo con las tareas? · Mi hijo está enfermo, ¿qué le doy? · ¿Te gusta mi perro? · ¿Qué comen los perros? · ¿Qué le gusta comer a los perros? · ¿Sabes dónde queda la farmacia? Mi mamá necesita remedios. · ¿Te acuerdas de esa canción que cantaba mi mamá? | `generic_conversation` / `null` |
  | ¿Cuándo nació Mozart? · ¿Cuándo nació el papá de Mozart? · ¿Quién es el hermano de Messi? · Mozart nació en 1756. · ¿Cómo se llama tu perro? · ¿Cuándo nació su hijo? | `generic_conversation` / `null` |
  | ¿Cuándo nació mi mamá? · cuándo nació mi papá · cuando nacio mi hijo · ¿CUÁNDO NACIÓ MI HIJO? · el año en que nació mi hijo | `protected_household` / `birth.protected.v1` |
  | el cumpleaños de mi hijo · que edad tiene mi hija · cuantos años tiene mi hijo · ¿Mi hijo tiene alergias? · dime el nombre de mi hijo · cómo se llama mi esposa · qué le gusta a mi hijo · cómo se llama mi perro · ¿Cuántas mascotas tengo? · ¿Dónde vive mi nieto? · ¿Cómo se llaman mis dos perros? · Iroko, ¿sabes cuándo es el cumpleaños de mi mamá? · oye dime cuantos años tiene mi hermana | `protected_household` / `household.protected.v1` |
  | ¿Qué edad tiene mi vieja? · ¿Cuántos años tiene mi señora? · ¿Cómo se llama mi guagua? · ¿Cuándo es el cumpleaños de mi mamita? · ¿Cómo se llama mi quiltro? · me puede decir cuantos anos tiene mi hijo · Quiero que me digas cómo se llama mi hijo. · No me acuerdo cuántos años tiene mi hijo. · Se me olvidó cómo se llama mi nieto. · oye cachai cuantos años tiene mi hija · la edad de mi nieto po · ¿Cuándo cumple mi hijo? · ¿Cómo se llamaba mi papá? · ¿Cuál es el apellido de mi nuera? · ¿Cuál es la comida favorita de mi hijo? · ¿Tengo hijos? · ¿Cuántos hijos tiene mi hermano? · Ya, a ver, dime cómo se llama mi hijo. | `protected_household` / `household.protected.v1` |
  | Conoce a mi hija. · Aprende la cara de mi hijo. | `biometric_enrollment` / `enrollment.biometric.v1` |
  | Mira lo que hizo mi hija. | `scene_description` / `scene.description.v1` |

- [ ] **Step 2: Run them.** `uv run pytest tests/unit/test_intent_resolution.py -q`. Expected: the flipped
  rows and the story rows fail with `protected_household`.
- [ ] **Step 3: Implement.** Remove the copied lists, `_names_a_relative` and the `pairwise` import it alone
  used; add `_Utterance`; change every rule to take it (each opens with `normalized = utterance.normalized`);
  keep `_protected_rule_id`, reading `BIRTH_WORDS`. The household rule:

```python
def _protected_household_rule(utterance: _Utterance) -> IntentResolution | None:
    """Recognize a request for household data, or a family value shaped as a memory answer.

    An answer-shaped message keeps the broad test on purpose: «sí, autorizo guardar a mi hijo»
    never reaches the answer grammar, whatever its form (ADR 0021 decision 9).
    """
    normalized = utterance.normalized
    protected = (
        mentions_the_household(normalized)
        if parse_memory_answer(normalized) is not None
        else requests_household_data(utterance.message)
    )
    if not protected:
        return None
    return _resolution(
        InformationNeed.PROTECTED_HOUSEHOLD,
        IntentMatch.EXACT,
        _protected_rule_id(normalized.split()),
    )
```

  In `test_memory_answer_grammar.py`, `test_every_rule_before_the_answer_rule_has_a_case_that_it_wins`
  calls `rule(_Utterance(text, text))`. It is the only caller of a rule from outside.
- [ ] **Step 4: Run them.** `uv run pytest tests/unit/test_intent_resolution.py
  tests/unit/test_memory_answer_grammar.py tests/unit/test_cognitive_controller.py
  tests/integration/test_conversation_record_routes.py -q`. Expected: all pass, with every
  `_PREEMPTING_BODIES` case unchanged.
- [ ] **Step 5: Commit** `feat(server): protect household requests, not mentions`.

---

### Task 3: The neighbouring rules

**Files:**

- Modify: `server/src/server/cognition/intent_resolution.py`, `tests/fixtures/intent_resolution_es.json`

**Interfaces.** Consumes `opens_with`, `states_a_request` and `has_question_mark` from Task 1.

**Closed values:**

```python
_OWN_AGE_PATTERNS = ("que edad tengo", "cuantos anos tengo", "edad que tengo")
_OWN_AGE_REQUEST = "mi edad"
_RELATIONSHIP_PATTERNS = (
    "que relacion existe",
    "que relacion hay",
    "que relacion tengo",
    "que relacion tenemos",
    "cual es mi relacion",
    "cual es nuestra relacion",
)
_BIOMETRIC_OPENING_PATTERN = "conoce a"
```

- [ ] **Step 1: Write the failing corpus: group B.**

  | Group B | `need` / `rule_id` |
  |---|---|
  | Mi hijo cumple diez años. · Mi hija tiene ocho años. · Mi hermano tiene una relación nueva. · Mi mamá conoce a todos en el barrio. · ¿Cuántos años tiene Joaquín? · Hace dos años fui a Valparaíso. · Llevamos diez años en esta casa. · Tengo una buena relación con el trabajo. · ¿Cuál es la relación entre la luna y las mareas? · A mi edad ya no corro. · ¿Qué edad tienes? · ¿A qué edad debería mi hijo empezar el colegio? | `generic_conversation` / `null` |
  | ¿Cuántos años tengo? · ¿Cuál es mi edad? | `explicit_birth_date_age` / `age.explicit.v1` |
  | ¿Qué relación tenemos? | `relationship_or_profile` / `relationship.profile.v1` |

- [ ] **Step 2: Run them.** Expected: the `generic_conversation` rows of group B fail with the age, the
  relationship or the enrolment need.
- [ ] **Step 3: Implement.**
  - `_explicit_age_rule` fires when an `_AGE_WORDS` word is present **and** one of: an `_OWN_AGE_PATTERNS`
    phrase; a strict date, matched on the folded text with `re.compile(r"\b\d{4} \d{2} \d{2}\b")` (folding
    turns the hyphens into spaces, and «Calcula mi edad desde 1980-08-17» keeps working); `_OWN_AGE_REQUEST`
    with `states_a_request(normalized, marked=has_question_mark(utterance.message))`; or the shape of a
    memory answer.
  - `_relationship_rule` fires when an `_RELATIONSHIP_WORDS` word is present **and** either a
    `_RELATIONSHIP_PATTERNS` phrase or the shape of a memory answer.
  - `_biometric_enrollment_rule` removes `"conoce a"` from `_BIOMETRIC_ENROLLMENT_PATTERNS` and accepts
    `opens_with(normalized, _BIOMETRIC_OPENING_PATTERN)`.
- [ ] **Step 4: Run them.** `uv run pytest tests/unit/test_intent_resolution.py
  tests/unit/test_memory_answer_grammar.py -q`. Expected: all pass, `_PREEMPTING_BODIES` included: the
  answer shape keeps «guarda la relacion» and «guarda la edad que tengo» away from the grammar.
- [ ] **Step 5: Commit** `fix(server): age and relationship rules need a request`.

---

### Task 4: The stored names and the prompt guard

**Files:**

- Modify: `server/src/server/memory/entity_labels.py`, `server/src/server/cognition/controller.py`,
  `server/src/server/routers/transcribe.py`, `server/src/server/routers/chat.py`
- Test: `tests/unit/test_cognitive_controller.py`, `tests/integration/test_household_names.py` (new),
  `tests/unit/test_architecture_guards.py`

**Interfaces.** Consumes `requests_data_of_a_name` and `names_someone_known`. Produces:

```python
# memory/entity_labels.py
async def read_household_names() -> frozenset[str]: ...


# cognition/controller.py
type HouseholdNameReader = Callable[[], Awaitable[frozenset[str]]]
# CognitiveController.__init__(..., household_names: HouseholdNameReader | None = None)
```

- [ ] **Step 1: Write the failing tests.** In `test_cognitive_controller.py`, with `_NAMED_QUESTION =
  "¿Cuándo nació Zeta?"` and a helper building a controller with spies on `legacy_turn`, the observing
  resolver, the spending resolver and the reader (returning `frozenset({"Zeta"})` by default):

  | Test | Asserts |
  |---|---|
  | `test_an_identified_person_asking_about_a_stored_name_takes_the_protected_path` | owner: `plan.need is PROTECTED_HOUSEHOLD`; legacy not awaited; **the spending resolver not awaited** |
  | `test_a_name_the_household_does_not_know_stays_conversation` | «¿Cuándo nació Mozart?», owner: `GENERIC_CONVERSATION`, legacy awaited |
  | `test_a_visitor_asking_about_a_stored_name_stays_conversation` | unknown actor: `GENERIC_CONVERSATION`, legacy awaited |
  | `test_an_identified_person_the_policy_refuses_cannot_confirm_a_stored_name` | parametrized on `CHILD` and `UNKNOWN` roles with a person id: `GENERIC_CONVERSATION`, legacy awaited |
  | `test_a_question_without_a_stored_name_never_judges_the_face_or_the_voice` | «¿Quién es el presidente de Chile?»: reader awaited once, observer **not** awaited |
  | `test_a_story_with_a_name_reads_nothing` | «Zeta llegó tarde.»: neither awaited |
  | `test_the_classic_route_reads_the_names_once_per_event` | names `{"Otro"}`: `decide` then `handle` on one event, the reader awaited once |
  | `test_without_the_seam_a_named_question_is_conversation_and_observes_nobody` | no `household_names`: generic, observer not awaited |
  | `test_an_empty_store_answer_leaves_the_turn_as_conversation` | names empty: generic, legacy awaited |
  | `test_a_stored_common_word_gives_the_fixed_reply_to_an_identified_person` | names `{"Luna"}`, «¿Qué sabes de la luna?», owner: `PROTECTED_HOUSEHOLD` (the stated limit) |

  In `tests/integration/test_household_names.py`, with a `household` fixture over a temporary migrated
  database (as in `test_candidate_proposal.py`):

  | Test | Asserts |
  |---|---|
  | `test_the_reader_returns_the_names_and_aliases` | a person and a pet with aliases are all returned |
  | `test_malformed_aliases_mean_no_names_and_never_log_the_value` | aliases set to `{zumo`: empty set; the class name in `caplog`, `zumo` not |
  | `test_a_closed_store_means_no_names` | `db._conn = None`: empty set |
  | `test_the_voice_route_hands_the_reader_to_the_controller` | `Mock(wraps=CognitiveController)`, `settings.memory_enabled` true: `household_names` is `read_household_names` |
  | `test_with_memory_off_the_voice_route_reads_no_names` | `settings.memory_enabled` false: `household_names` is `None` |
  | `test_a_voice_route_without_identity_reads_no_names` | the key is absent without `request_identity` |
  | `test_the_chat_route_imports_the_same_reader` | `chat.read_household_names is read_household_names` |
  | `test_a_visitor_on_chat_reaches_the_model_with_a_stored_name` | memory on, `/chat`, no token, «¿Cuándo nació Zeta?», names `{"Zeta"}`: the response is the legacy one |

  In `test_architecture_guards.py`, following `_record_readers`:

```python
_NO_HOUSEHOLD_READS = ("characters/", "llm", "streaming", "text_turn.py")
_HOUSEHOLD_READER_MODULES = frozenset(
    {
        "server.cognition.household_tools",
        "server.memory.declarative",
        "server.memory.entity_labels",
        "server.memory.policy_gated_v4_reader",
    }
)
```

  `test_the_generic_prompt_reads_no_household_store` asserts `_household_readers(_sources()) == []`, and
  `test_the_household_prompt_guard_detects_a_violation` flags a synthetic `text_turn.py` and spares a
  synthetic `routers/chat.py`.

- [ ] **Step 2: Run them.** Expected: `TypeError` on `household_names`, an import error on
  `read_household_names`, and a `NameError` on the guard helper.
- [ ] **Step 3: Implement.**
  - `read_household_names` wraps `list_known_names`, catches `(BrainMemoryError, aiosqlite.Error)`, logs
    `"Household names unavailable: %s"` with `type(exc).__name__` and
    `extra={"event": "entity_labels.names_unavailable"}`, and returns `frozenset()`.
  - In the controller, `decide` starts with `need = await self._resolved_need(event)` (a helper, or the
    method exceeds `PLR0912`). `_resolved_need` returns `PROTECTED_HOUSEHOLD` when the resolver says
    `GENERIC_CONVERSATION` and `_asks_about_known_name(event)` is true. A dict keyed by `event.event_id`,
    next to `_answers`, keeps the classic route to one read per event. `_HOUSEHOLD_READERS =
    frozenset({HouseholdRole.OWNER, HouseholdRole.ADULT})`, the roles `_evaluate_public_read` allows:

```python
async def _asks_about_known_name(self, event: CognitiveEvent[TextTurnPayload]) -> bool:
    """Tell whether an owner or an adult asks for a datum of someone the household knows.

    The names are compared first: one read of the store, while judging the face and the voice
    costs seconds, and «¿quién es…?» is an everyday question. A visitor never reaches the
    protected path: their question stays conversation, where the model holds no stored value,
    so the reply cannot tell a stored name from any other. Neither does a child or a guest, or
    the refusal would confirm the name. It never spends a grant.
    """
    message = event.payload.message
    if self._household_names is None or not requests_data_of_a_name(message):
        return False
    if event.event_id not in self._named_requests:
        names = await self._household_names()
        self._named_requests[event.event_id] = names_someone_known(
            message, names
        ) and _may_read_the_household(await self._observed_person_resolver(event))
    return self._named_requests[event.event_id]
```

  - `_may_read_the_household(actor)` is `actor.status is ActivePersonStatus.IDENTIFIED and actor.role in
    _HOUSEHOLD_READERS`.
  - `_voice_controller` passes `household_names=read_household_names if settings.memory_enabled else None`
    only on its branch with `request_identity`; `chat.py` passes the same. `vision.py` is not touched: its
    actor is always the public unknown.
- [ ] **Step 4: Run them.** Expected: all pass.
- [ ] **Step 5: Commit** `feat(server): a stored name makes a question a household request`.

---

### Task 5: Whole-project checks

**Files:** only what a check finds.

- [ ] **Step 1:** `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy server/src robot/src`,
  `uv run pyright`, `uv run python scripts/check_reserved_terms.py`. Expected: clean, with pyright no worse
  than the baseline of Task 0.
- [ ] **Step 2:** `just gate`. Expected: the baseline plus the new tests, no failure. The `slow` and
  `hardware` tests do not depend on this plan.
- [ ] **Step 3:** A read of the whole diff against *Global constraints*, then an independent review of the
  branch if Pipec asks for one. Findings are verified against the code before any change.

---

### Task 6: Documentation truth (text only, no RED)

**Files:** the documents below and this plan.

- [ ] `docs/architecture/implementation-guardrails.md`, *Cognitive constraints*: one line, D-21 («The prompt
  of a generic turn reads no household store; a plan that adds one first makes the household rule broad
  again»).
- [ ] `docs/architecture/current-state.md`: the *Typed intent resolution* row (the three conditions, the
  stored names, the neighbouring rules) and the flow diagram line «protected household, no identified
  owner -> unauthorized». Regenerate the Archify diagram (`docs/architecture/diagrams/current-state.json`
  and its `.html`) with validate, then deliver.
- [ ] `docs/runbooks/operator-manual.md`: the troubleshooting line that blames an unrecognized phrasing,
  with the known limits of this plan and how to widen the closed lists.
- [ ] `docs/roadmap/cognitive-roadmap.md`: close the `—` row and step 1 of the closing path; its text says
  **requests**, not questions. In the rows of CM-3b, CM-5b and CM-7, one clause: D-21 applies. The plan index
  files, and the local `docs/roadmap/tabla-tareas.md` (never committed). Move this plan to `completed/` with
  its execution record.
- [ ] `uv run ruff format --check .`, `uv run python scripts/check_reserved_terms.py`, and a check that every
  relative link of the touched `.md` files resolves. Commit `docs: close plan 0077`.

---

### Task 7: Hardware acceptance (Pipec runs everything)

Outcomes only, never a sentence or a value, in `docs/evals/0077-household-requests-acceptance.md`. The
agent starts nothing. With face and voice enrolled and `LOG_CONVERSATION_TEXT=true` on the console, on the
streaming route (the robot's default), and then one case of 1, 5 and 7 on the classic route:

| # | Who | Says | Expected |
|---|---|---|---|
| 1 | Owner | A story about the children (three different ones) | The model answers, no fixed phrase |
| 2 | Owner | «Quiero salir con mi mascota» and two more about a pet | The model answers. **Record who refused if anyone did** (D-6): a fixed phrase is a rule, anything else is the model |
| 3 | Owner | The sushi sentence (a taste plus the children) | The model answers; with candidates on, the offer names only the owner's taste |
| 4 | Owner | Three pieces of advice about a relative | The model answers |
| 5 | Owner | Two facts about a famous person, as questions | The model answers |
| 6 | Owner | Two stories with «años», one with «relación», and one ending in «¿cachai?» | The model answers, no fixed phrase |
| 7 | Owner | Three requests for a relative's or a pet's datum, in your own words | The fixed «La información familiar autorizada…» |
| 8 | Owner | A request by a stored first name | The same fixed reply |
| 9 | No face in view | A request as in 7, and one as in 8 | 7: the fixed refusal. 8: the model, with nothing true about the household |
| 10 | Owner | Five requests of case 7's kind, spoken normally | Count how many Whisper wrote with a mark, and how many reached the fixed reply |
| 11 | Owner | Two questions the model cannot know («¿Qué hace mi hijo?») | Count invented answers against «no lo sé», and later how many reached the day's summary |
| 12 | Owner, then no face | A story about the family, then, with no face in view, «¿qué te conté de mi familia?» | The second reply knows nothing of the story: the session stops with no face (D-17) |

Stop and report, without changing the rule on the spot, if: a case 7 request reaches the model **and** the
model states a household value as true; or case 2 is still refused by the model (the follow-up is the
prompt, which is not this plan and needs its golden digests changed); or fewer than 4 of 5 in case 10 reach
the fixed reply; or case 12 repeats the story.

## Completion criteria

1. Tasks 0 to 7 done, one commit per task, every code test RED before GREEN.
2. `just gate` green with the baseline plus the new tests; the corpus holds every row of groups A and B.
3. A story, a piece of advice and a question about someone else reach the model; a request for a
   relative's or a pet's datum keeps the protected route; an owner's or adult's question about a stored
   name takes it too; a message shaped as a memory answer never carries a family value.
4. The fixed replies, the policy, the prompts and the wire are unchanged, and the architecture guard
   proves the generic prompt reads no household store.
5. The hardware record exists, with the origin of the pet refusal stated (D-6).

## Rollback boundary

Each task is one commit. Task 4 may be reverted alone: named questions become plain conversation. Task 3
may be reverted alone. Tasks 1 and 2 are reverted together. No setting, migration or wire field is added,
so a revert leaves nothing behind but the mentions already kept in the record, as any other turn.

## Not here, and why

- **Spoken commands and a keyword («Iroko, busca…»):** the roadmap row *Spoken commands*, a plan after
  CM-5b with a real-speech corpus. They suit actions, not conversation.
- **Internet search:** no outbound path exists, and ADR 0004 requires an explicit policy first.
- **An LLM or an embedding as classifier:** 17 to 33 s of model time per turn on this laptop, not
  deterministic, and the architecture gives the model no authorization role.
- **Answering the protected data:** the fixed «todavía no está conectada» stays; reading a relative's
  profile is a later plan (`strong` assurance).
- **The prompt line that names «family, pets»:** if case 2 points at it, it is a follow-up.
- **Wider lists without evidence:** they grow from hardware, not from guessing.
- **A dictionary of Chilean idioms:** Pipec raised it on 2026-10-31 and decides at the close. The
  author's recommendation, which he will take if it is included: not inside these lists (every extra word
  can cut a conversation again), but a short measurement case in Task 7 and a roadmap row, so that a real
  failure tells whether the gap is the speech-to-text or the model before any glossary or RAG is built.
- **The date, identity, scene and own-children rules:** see *Known limits*.

## Rehearsal

Rehearsed on 2026-10-30 in a scratch copy of `d7ef78a`, with the repository's virtual environment.
Results, not promises for the execution:

- **CI selection:** 5563 passed in the full run (`MEMORY_ENABLED=false`, `-m "not slow and not hardware
  and not eval"`). The `slow`, `hardware` and `eval` markers were not run.
- **Corpus:** 157 rows, every one as written here (84 new, 6 changed).
- **Task order:** with Task 2 applied and the three rules of Task 3 restored, exactly the 12
  `generic_conversation` rows of group B fail and no other row does.
- **Adversarial sentences:** a reviewer wrote 485 sentences outside the corpus, in Chilean Spanish, built to
  break the first version: 68 % right. The final version gets 539 of 569 right (95 %), counting those and
  the corpus; 15 of 224 requests miss and 15 of 345 stories are cut. **This is no real-use rate:** the
  sentences were written to fail, and the lists were then widened from them. What remains is in *Known
  limits*.
- **Static:** `ruff check` and `ruff format` clean on the touched files, `mypy server/src robot/src` clean.
  `pyright` could not be judged in the copy (it does not resolve the virtual environment there); on the
  repository `entity_labels.py` is clean. Task 5 runs it for real.
- **Not rehearsed:** hardware, the real model, real speech, and the streaming route end to end. Task 7 is
  that evidence.

## Reviews

Three independent read-only reviewers on 2026-10-30, each finding verified against the code before use.

- **Plan against the repository:** no critical finding. Applied: the reader ignored `MEMORY_ENABLED` (D-20);
  `test_a_deterministic_turn_keeps_the_speaker_the_controller_resolved` would have kept passing and tested
  nothing (Task 2; a scan of 3750 test literals confirms it is the only one); the prompt property had no
  guard (D-21, Task 4); `tu` and `su` pointed at the robot or at third parties (D-18); `pairwise` left
  unused; «copy», not «move», in Task 1; the *Required reading* and *Permitted files* headings. Not applied:
  a guard for the seam itself, because `cognition/` already cannot import `memory`.
- **Adversarial sentences:** D-11 and D-19, the `edad` and soft-word changes, and the list of limits.
  Not applied: a proximity rule (it broke real requests), and any change to the rules outside this plan.
- **Privacy and authorization:** the central claim holds: a generic turn carries no stored household value,
  and the session is suspended or replaced for anyone else. Applied: the session change is now stated
  (D-17, case 12); a child or guest could confirm a stored name (D-16); pets and the new relatives in the
  broad test of D-8; an invented reply reaching the diary (*Known limits*, case 11); the audit statement in
  *Global constraints*.

## Self-review (2026-10-30)

Spec coverage: D-1 Tasks 1 and 2; D-2 Task 3; D-3 Tasks 2 and 4; D-4 Task 2 (`mi hijo tiene alergias`) and
Task 7 case 10; D-5 Tasks 1 and 2; D-6 Task 7 case 2; D-7 Task 2; D-8 Task 2; D-9, D-13, D-16, D-20 and D-21
Task 4; D-10 and D-14 Task 3; D-11, D-12, D-18 and D-19 Task 1; D-15 Tasks 2 and 3; D-17 Task 7 case 12. The
five Review focus items each have a named test. Names are consistent across Tasks 1 to 4.

## Execution record

Not executed.
