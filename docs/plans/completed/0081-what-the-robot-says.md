# 0081 — What the robot says: the owner's tastes only when they apply, no prompt words in the reply, `usted` with the 3B model, nothing invented on an empty session

> **Status:** **Closed** (2026-11-11). Accepted by Pipec on real hardware, streaming route, in two
> sittings ([acceptance record](../../evals/0081-what-the-robot-says-acceptance.md)); CI selection
> 7005 passed (baseline 6957). The builder's rulings that go beyond the text below win over it
> where they differ:
>
> - The card footer opens «Es memoria autorizada.» before D-5's text, so the card stays the
>   discipline's «authorized memory block» (ADR 0026; `test_desktop_hardening`).
> - An allowed but empty card read gives `PromptCard("tu", None)` and logs `tastes=none`.
> - The golden fixture keeps its one-space indent; its canary card is built by the renderer.
>
> Hardware: cases 1, 2b, 4a, 4c, 5 and 7 pass; 4b partial; case 3 fails and case 6 misses its gate
> (D-8): limits of `qwen2.5:3b` (it mirrors the owner's just-said tastes, it ignores `usted`),
> recorded for P4.1, not patched. Next free numbers: plan **0082**, ADR **0038**.
>
> **Status at promotion:** `Ready` and `NOW` — **promoted by Pipec on 2026-11-11** («Sí, promuévelo»), decisions
> D-1 to D-8 confirmed as written, after he removed the reply guard (the plan fixes our code and
> prompt, not the 3B model's output). To be executed in a new session. GitHub is on stand-by that
> day (the CI cannot install its apt packages; PR #256 and #255 are open): the branch is local,
> `feat/0081-what-the-robot-says` from the local `docs/finish-line-path` (which holds this plan;
> its code is identical to `main` at `dd793b9`), and the merge with `main` waits for GitHub.
> Written as `Draft` the same day against `docs/finish-line-path` at `6629b77` and the code read
> that day. Queue rule 4: Task 0 re-verifies every claim below against the merged code before any
> change, and **stops and reports** if one is false. Written for an executor who has not seen this
> repository. Row 6 of the
> [path to the finish line](../../roadmap/cognitive-roadmap.md#closing-path-of-conversational-memory)
> and the cross-cutting row *The prompt, the card and the model's own answers* of the roadmap.
> **It moves the golden prompt digests** (`tests/fixtures/prompt_golden.json`) on purpose and needs a
> hardware acceptance by Pipec.

> **For agentic workers:** if the status above does not say `Ready`, stop. REQUIRED SUB-SKILL:
> `superpowers:subagent-driven-development` or `superpowers:executing-plans` (Pipec chooses), with
> `superpowers:test-driven-development` and `superpowers:verification-before-completion`.
> **Pipec's rules win over the skills:** one plain branch, `feat/0081-what-the-robot-says` (local,
> see the status above), never a git worktree; no push while GitHub is on stand-by. One commit per task; every new test
> seen RED for the stated reason first (paste the RED output in the PR). The Bash tool of this
> environment loses backslashes and non-ASCII characters in heredocs and arguments: use Write/Edit,
> put Spanish phrases in files, keep commit titles ASCII and **72 characters at most**; check
> `git log` after each commit (the hook rejects silently); do not pipe `git commit`; `git add` with
> explicit paths. Run the suite with `MEMORY_ENABLED=false` as CI does. Never run
> `uv sync --all-packages --all-groups` (it removes the optional `cuda` extra). **Do not run
> `just gate` while Pipec rehearses** (about 3.5 GB of RAM). **Pipec starts the server and the
> robot**, never the agent; on hardware only phrases first tried with the Task 0 script, and every
> case confirmed in `logs/server.log`, not by anyone's word. Before pushing run `pyright`, `ruff`
> and `mypy` over the **whole** project and lint `scripts/` with explicit paths.

## What was seen, and where `main` stands

On `qwen2.5:3b`, in the acceptances of Plans 0074, 0078 and 0080 (records under `docs/evals/`,
outcomes only):

| # | Seen | Source in the code |
|---|---|---|
| 1 | A generic reply voiced a taste of the owner's card as the robot's own; a cold «hola» brought a taste in («¿aún te gusta …?») and claimed to have observed it | The card enters **every** face-identified voice turn with its tastes (`text_turn.prepare_text_turn` → `profile_card_access.prompt_card_text` → `profile_card.render_prompt_card`); its lines read `- Le gusta: "…".`, which does not say whose taste it is; the footer «apóyate en ella solo si viene al caso» is the only brake |
| 2 | The word «Tuteo» spoken (once on a turn **without** face evidence, so without a card), and a reply that opened «Tuteo, tu nombre es "…"» | `characters._LANGUAGE_RULE` says «con tuteo (tú)»; the card renders `Nombre: "…".` with quotes (anti-injection, ADR 0026 decision 2) |
| 3 | With `address_form = usted` the replies were incoherent (2 of 2) | The card says «Trato: usted.» while the language rule of the same prompt demands tuteo (ADR 0026, implementation notes) |
| 4 | With no history the model said it had seen or noticed something about the person, and once invented a relative | `_MEMORY_DISCIPLINE` forbids inventing names, not claiming an observation; with an empty session the card is the model's only context |

Every voice and chat prompt is pinned by SHA-256 in `tests/fixtures/prompt_golden.json`
(`tests/unit/test_prompt_golden.py`, a matrix of character × card × position × emotion × perception
× actor). The recall prompt has its own fixture (`recall_prompt_golden.json`) and does not use the
language rule: it does not move.

**Model or code? (Pipec, 2026-11-11).** `qwen2.5:3b` is the model this laptop can run, not the
final one (ADR 0036, P4.1). So the plan fixes only what is a defect of our code or our prompt and
would reach any model: two contradictory orders in one prompt (row 3), a word of our own rule
(row 2), the owner's data put in every prompt and left for the model to filter (row 1), a taste
line that does not say whose taste it is (row 1). What is only a weakness of the 3B model gets the
least effort: one line of the memory discipline (row 4) and no more. A guard that would clean the
model's replies (strip «Tuteo» and the card's quotes) was considered and **left out**: once the word
leaves the prompt the audible case has no source, and the quotes are not spoken. A later model is
checked by re-running the hardware cases of Task 5, not by new code.

## Decisions

Confirmed by Pipec as written when he promoted the plan (2026-11-11).

- **D-1 One change for every turn, no new switch.** The language rule and the memory discipline
  change for every route (with `PROFILE_CARD_ENABLED` off too), so every golden digest moves. No
  setting is added; the rollback is reverting the branch. The wire, the robot, the recall prompt,
  the fixed controller strings and the fallback phrase do not change.
- **D-2 The language rule names no register word and follows the form.** `_LANGUAGE_RULE` becomes
  `language_rule(address_form)`, still the **last** block of every prompt (Plan 0064, Task 2):
  - `tu`: «\nIDIOMA — Responde siempre en español neutro y háblale de tú a la persona. No uses otro
    idioma ni mezcles palabras de otro idioma, aunque la persona lo haga.»
  - `usted`: «\nIDIOMA — Responde siempre en español neutro y trata de usted a la persona. No uses
    otro idioma ni mezcles palabras de otro idioma, aunque la persona lo haga.»

  The word «tuteo» is gone from the prompt. Every **fixed controller string** stays in tuteo
  (Plan 0064 D-1 and its guard `test_no_voseo_in_spoken_strings.py`); only the model's own
  sentences follow `usted`. A mixed register on a formal owner's fixed replies is a known limit.
- **D-3 The form reaches the prompt as a value, not as a card line.** The card no longer renders
  «Trato: usted.» (it fought the language rule); the form travels as `address_form` beside the card
  text, from the card read to `build_system_prompt`. A speaker with no card read (unknown, refused,
  a failed read, `/chat`, `/vision/respond`) is `tu`. This amends ADR 0026 decisions 2 and 7 (Task 5
  writes the amendment).
- **D-4 Tastes enter the prompt only when the message is about tastes.** A deterministic, pure gate
  decides it; the model is not trusted to judge relevance (it ignored the footer on hardware). The
  tastes are included when the folded message (`text_keys.normalize_spanish`) holds
  - a word of `TASTE_CUE_WORDS`: `gusta`, `gustan`, `gustaba`, `gustaria`, `gusto`, `gustos`,
    `encanta`, `encantan`, `prefiero`, `prefieres`, `prefiere`, `favorito`, `favorita`,
    `favoritos`, `favoritas`, `recomiendas`, `recomienda`, `recomiendes`, `sugieres`, `comer`,
    `comemos`, `comida`, `cenar`, `cena`, `almorzar`, `almuerzo`, `desayunar`, `desayuno`, `beber`,
    `musica`, `cancion`, `canciones`, `escuchar`, `pelicula`, `peliculas`, `serie`, `series`,
    `libro`, `libros`, `leer`, `regalo`, `regalar`, `panorama`, `plan`; or
  - a content word of one of the card's tastes: the taste folded, without `ARTICLES` and
    `lexicon.STOPWORDS_ES`, words of **4 letters or more** (so «el té» never matches «¿te
    acuerdas?»; a short taste is reached only through a cue word).

  Otherwise the card keeps only the name line (and the form travels apart, D-3). **A greeting never
  carries a taste**: «hola», «hola Iroko, ¿cómo estás?», «buenos días», «oye hola» hold no cue and
  no taste word; a test pins them. Pipec may add or remove cue words at promotion; each is one row
  of the test table.
- **D-5 The card says whose tastes they are.** Labels `Le gusta` / `No le gusta` / `Prefiere`
  become `A la persona le gusta` / `A la persona no le gusta` / `La persona prefiere`. The footer
  becomes: «Son gustos de la persona, no tuyos: nunca digas que a ti te gustan. La persona te los
  contó: no digas que los viste ni que los notaste. Úsalos solo si viene al caso y no inventes nada
  que no esté aquí.» The header and the `Nombre: "…".` line stay; values stay quoted (ADR 0026
  decision 2's anti-injection). The 600-character cap and the 12 tastes do not change.
- **D-6 Nothing about the person without a source.** `_MEMORY_DISCIPLINE` gains one bullet, last:
  «- If neither the memory block nor this conversation holds it, you know nothing about this
  person: never say you saw, noticed or remember anything about them.» It is the same block on
  every turn (no conditional variant).
- **D-7 Closed log values for the acceptance.** On an allowed card read, one INFO line
  `event="card.prompt"` with `tastes` ∈ {`none`, `included`, `withheld`} and `address_form` ∈
  {`tu`, `usted`}. Never a value, a message or a reply text.
- **D-8 Stop rule for `usted`, a check of the model, not a target.** If on hardware `usted` is
  still incoherent in 2 or more of 5 turns, the `tu` half closes, `usted` stays a documented limit
  of the 3B model (ADR 0026 note kept) and nothing more is built for it; Pipec decides whether the
  plan closes that way.

## Global constraints

- English code, comments and docstrings (Google style); Spanish only in user-facing strings and
  prompt copy; **no voseo** (`tests/unit/test_no_voseo_in_spoken_strings.py`).
- No `Any`, no `print`, no `os.path`, no bare `except`; logging with `%`; settings only through
  `settings`. No new setting, dependency, migration, route or wire field.
- The generic prompt reads no household store (`test_the_generic_prompt_reads_no_household_store`);
  the card stays the only durable datum of the person in the prompt, read with its audit row first
  (ADR 0026 decision 3).
- **No text in any log line** (D-7).
- Model replies are not post-processed by this plan: `claim_guard` stays the only guard on model
  text.
- No real household data in any tracked file: canaries only (`Canary`, `Zeta`, `Omega`, «el
  mate», «la lluvia»).
- `LOG_CONVERSATION_TEXT=true` only in a consented sitting of Pipec's, back to `false` in `.env`
  when it ends; no console capture is shared; the records hold counts only.

## Review focus

Inputs no task title names; each has its test in the task that owns it.

1. A greeting with a filler or the robot's name («oye hola», «hola Iroko, ¿cómo estás?», «buenas»)
   carries no taste, and «¿te acuerdas de mí?» does not match a taste «el té» (Task 2).
2. A formal owner with no name and no tastes: no card block in the prompt, and the language rule
   still says «de usted» (Task 3).
3. A card read that is denied, unavailable or raises: no card and the `tu` rule, the turn answered
   (Task 3).
4. A turn with no card read at all (unknown speaker, `MEMORY_ENABLED` or `PROFILE_CARD_ENABLED`
   off, `/chat`): the `tu` rule and no «tuteo» anywhere in the prompt (Tasks 1 and 3).
5. A message that names a taste of 4 letters or more inside a longer sentence («ayer tomé mate con
   pan») includes the tastes; one that only shares a stopword or an article with a taste does not
   (Task 2).

## File structure

| File | Responsibility | Task |
|---|---|---|
| `characters/__init__.py`, `llm.py`, `llm_streaming.py`, `text_turn.py`, `streaming.py` | `language_rule(form)`, `address_form` through the prompt builders | 1 |
| `memory/card_relevance.py` (new) | The taste gate (D-4) | 2 |
| `memory/profile_card.py`, `memory/profile_card_access.py`, `routers/transcribe.py`, `text_turn.py` | `PromptCard`, labels and footer, no «Trato» line, the message reaches the provider, `card.prompt` log | 3 |
| `characters/__init__.py` | The memory-discipline bullet (D-6) | 4 |
| `tests/fixtures/prompt_golden.json`, `tests/unit/test_prompt_golden.py` | The matrix gains the form; regenerated in Tasks 1, 3 and 4 | 1, 3, 4 |
| `docs/…` | ADR 0026 amendment, truth, acceptance, close | 5 |

Paths under `server/src/server/` unless they start with `tests/` or `docs/`.

**Regenerating the golden fixture.** Task 1 adds a `__main__` block to
`tests/unit/test_prompt_golden.py` that writes `golden_prompts(...)` (inside
`pytest.MonkeyPatch.context()`) to the fixture, sorted, indented 2. Every task that moves the
prompt runs `uv run python tests/unit/test_prompt_golden.py` **after** its own RED/GREEN tests pass
and writes in the PR how many keys changed and why. A digest that changes in a task whose decision
does not touch that prompt is a bug: stop and find it.

---

### Task 0: Re-audit, baseline and the phrase script

- [ ] **Step 1:** Verify against the code, **stop and report** if any is false:
  `_LANGUAGE_RULE` and `_MEMORY_DISCIPLINE` are as quoted (`characters/__init__.py:79-95`) and
  `build_system_prompt` appends the rule last; `render_prompt_card` renders `Le gusta`, «Trato:
  usted.» and the footer quoted above; `ProfileCardProvider` is
  `Callable[[ActivePersonContext], Awaitable[str | None]]` with one production binding
  (`routers/transcribe.py:_profile_card_provider`); the recall prompt does not use
  `_LANGUAGE_RULE`; `server/characters` may import `server.memory.profile_card` under
  `TYPE_CHECKING` without an architecture guard failing; `iroko-admin change address_form` changes
  the owner's form (the hardware case 6 depends on it).
- [ ] **Step 2:** Baseline:
  `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and not eval" -q -n auto`; write
  the count in the PR.
- [ ] **Step 3: The phrase script** (scratchpad, not committed; phrases in a UTF-8 file). For each
  hardware phrase of Task 5 it prints `resolve_information_need`'s need with recall, sensitive read
  and the card on (it must be generic conversation, except «¿qué sabes de mí?») and, once Task 2
  exists, `tastes_are_relevant` against the canary tastes «el mate», «la lluvia», «comida china».
  Attach its output to the PR before the hardware sitting; a phrase that resolves elsewhere is
  replaced, never used.

### Task 1: The language rule follows the form

**Files:** Modify `characters/__init__.py`, `llm.py`, `llm_streaming.py`, `text_turn.py`,
`streaming.py`, `tests/unit/test_prompt_golden.py`, `tests/fixtures/prompt_golden.json`; Test
`tests/unit/test_prompt_language.py`.

**Interfaces:** Produces `type AddressForm = Literal["tu", "usted"]` in `memory/profile_card.py`
(and `ProfileCard.address_form: AddressForm | None`); `language_rule(address_form: AddressForm) ->
str` in `characters`; keyword `address_form: AddressForm = "tu"` on `build_system_prompt`,
`llm._build_classic_base_prompt`, `llm.generate_response`,
`llm_streaming._build_streaming_base_prompt`, `llm_streaming.generate_response_stream`; field
`PreparedTextTurn.address_form: AddressForm = "tu"`, passed by `text_turn._generate` and
`streaming._text_deltas`.

- [ ] **Step 1: Write the failing tests** in `test_prompt_language.py`:
  `test_the_rule_names_no_register_word` (`"tuteo" not in language_rule(f).casefold()` for both
  forms); `test_the_tu_rule_asks_for_tu` (`"háblale de tú" in language_rule("tu")`);
  `test_the_usted_rule_asks_for_usted` (`"trata de usted" in language_rule("usted")`,
  `"de tú" not in` it); `test_the_prompt_ends_with_the_rule_of_its_form` (parametrized over both
  forms and the existing perception/emotion/card cases: `prompt.endswith(language_rule(form))`,
  counted once); the classic and stream base prompts with `address_form="usted"` end with the
  `usted` rule; `test_a_prompt_without_a_card_names_no_register_word` (every character, no card,
  no actor: `"tuteo" not in prompt.casefold()` and it ends with the `tu` rule). Replace
  `test_the_rule_asks_for_spanish_with_tuteo` and keep the `español` check.
- [ ] **Step 2:** Run → FAIL (`language_rule` missing).
- [ ] **Step 3: Implement** D-2's two strings and the keyword through the builders above.
- [ ] **Step 4:** Run → PASS. Extend the golden matrix with the form (`("tu", "usted")`, the key
  gains `|{form}`), add the `__main__` writer, regenerate: every key changes (the `tu` rule text
  moved). `uv run pytest tests/unit/test_prompt_golden.py tests/unit/test_prompt_language.py -q`.
- [ ] **Step 5: Commit** `feat(server): language rule follows the address form (plan 0081)`.

### Task 2: The taste gate

**Files:** Create `memory/card_relevance.py`; Test `tests/unit/test_card_relevance.py`.

**Interfaces:** Produces `TASTE_CUE_WORDS: Final[frozenset[str]]` (D-4's list, folded) and
`tastes_are_relevant(message: str, tastes: Sequence[CardTaste]) -> bool`.

- [ ] **Step 1: Write the failing tests** (tastes «el mate», «la lluvia», «comida china»):
  `test_a_greeting_carries_no_taste` (parametrized: «hola», «Hola.», «hola Iroko, ¿cómo estás?»,
  «buenos días», «buenas», «oye hola», «¿cómo te va?» → `False`);
  `test_a_cue_word_carries_the_tastes` («¿qué me recomiendas comer?», «¿qué música te gusta?»,
  «pon una canción», «¿qué película vemos?» → `True`); `test_a_taste_word_carries_the_tastes`
  («hoy tomé mate» → `True`, «¿va a haber lluvia?» → `True`, «quiero algo chino» → `False`: the
  folded words must be equal, and «chino» is not «china»; «ayer tomé mate con pan» → `True`);
  `test_a_shared_article_or_stopword_is_not_a_match` («la casa está fría» against «la lluvia» →
  `False`); `test_a_short_taste_matches_only_by_cue`
  (taste «el té»: «¿te acuerdas de mí?» → `False`, «¿qué me gusta tomar?» → `True`);
  `test_no_tastes_is_never_relevant_by_word` (empty tastes, «hola» → `False`); `test_the_cues_are_folded`
  (every word of `TASTE_CUE_WORDS` equals `normalize_spanish(word)`).
- [ ] **Step 2:** Run → FAIL (module missing).
- [ ] **Step 3: Implement** with `normalize_spanish`, `ARTICLES` and `lexicon.STOPWORDS_ES`; words
  of 4 letters or more.
- [ ] **Step 4:** Run → PASS. The prompt does not move here.
- [ ] **Step 5: Commit** `feat(server): include card tastes only on taste talk (plan 0081)`.

### Task 3: The card says whose tastes they are, and carries the form

**Files:** Modify `memory/profile_card.py`, `memory/profile_card_access.py`,
`routers/transcribe.py`, `text_turn.py`, the golden test and fixture; Test
`tests/unit/test_profile_card.py`, `tests/unit/test_profile_card_access.py`,
`tests/unit/test_text_turn.py`, `tests/integration/test_profile_card_routes.py`.

**Interfaces:** Consumes `AddressForm`, `tastes_are_relevant`. Produces
`@dataclass(frozen=True) class PromptCard(address_form: AddressForm, text: str | None =
field(default=None, repr=False))`; `render_prompt_card(card: ProfileCard, *, include_tastes:
bool) -> str | None`; `prompt_card_for_turn(actor: ActivePersonContext, message: str, *,
correlation_id: UUID, now: datetime) -> PromptCard | None` (replaces `prompt_card_text`);
`ProfileCardProvider = Callable[[ActivePersonContext, str], Awaitable[PromptCard | None]]`;
`prepare_text_turn` passes the message and fills `profile_card` (the text) and `address_form`.

- [ ] **Step 1: Write the failing tests:** `test_the_lines_say_the_taste_is_the_persons` (`- A la
  persona le gusta: "el mate".`, `- A la persona no le gusta: …`, `- La persona prefiere: …`);
  `test_the_footer_says_the_tastes_are_not_the_robots` (D-5's footer exact);
  `test_the_card_never_renders_the_form` (`"Trato"` absent for `tu` and `usted`; replaces the two
  «Trato: usted.» rows); `test_withheld_tastes_leave_the_name_only` (`include_tastes=False` →
  header, `- Nombre: "Canary".`, footer; no taste label); `test_a_formal_card_with_nothing_else_has_no_text`;
  in access: `test_the_prompt_card_withholds_tastes_on_a_greeting` («hola» → `PromptCard("tu",
  text without "le gusta")`), `test_the_prompt_card_carries_usted`, `test_a_denied_read_has_no_prompt_card`
  (`None`) and `test_the_prompt_card_logs_closed_values` (`caplog`: one `card.prompt` record with
  `tastes="withheld"` and `address_form="tu"`, and no canary in any record); in `test_text_turn`:
  `test_the_provider_receives_the_message` and `test_the_form_reaches_the_prepared_turn` (a provider
  returning `PromptCard("usted", None)` → `prepared.address_form == "usted"`,
  `prepared.profile_card is None`); a provider that raises → `profile_card is None`,
  `address_form == "tu"`; the routes test asserts the classic and stream prompts end with the
  `usted` rule for a formal canary owner.
- [ ] **Step 2:** Run → FAIL for the stated reasons.
- [ ] **Step 3: Implement** D-3, D-5 and D-7's `card.prompt` line (logged in
  `prompt_card_for_turn`, only on an allowed read); `_says_something_to_the_model` counts the name
  and the **included** tastes only.
- [ ] **Step 4:** Run → PASS; regenerate the golden fixture (only the card keys move: the canary
  card `_CARD` of the matrix becomes the new rendering of «el mate»). Run the touched tests.
- [ ] **Step 5: Commit** `feat(server): card names whose tastes, form as a value (plan 0081)`.

### Task 4: Nothing about the person without a source

**Files:** Modify `characters/__init__.py`, the golden fixture; Test
`tests/unit/test_memory_discipline.py`.

- [ ] **Step 1: Write the failing test** `test_the_discipline_forbids_claiming_an_observation`
  (D-6's bullet is the last line of `_MEMORY_DISCIPLINE`; the block still names no person).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement** D-6.
- [ ] **Step 4:** Run → PASS; regenerate the golden fixture (every key moves).
- [ ] **Step 5: Commit** `feat(server): no claimed observation without a source (plan 0081)`.

### Task 5: Truth, acceptance and close

**Files:** ADR 0026 (an *Amended by Plan 0081* note on decisions 2 and 7, and its implementation
notes on `usted` and the «Trato» line updated); `docs/architecture/current-state.md` and its Archify
diagram if the card's description changes (validate → deliver);
`docs/architecture/personality-and-interaction.md` where it says tuteo or describes the card;
`docs/roadmap/cognitive-roadmap.md` (row 6 closed; the cross-cutting row keeps only what this plan
did not touch: wrong general facts, «Kachai» taken for a name, a larger model on the home server);
`docs/plans/README.md` (board) and `docs/plans/open/README.md`;
`docs/evals/0081-what-the-robot-says-acceptance.md` (new, outcomes only); the local
`docs/roadmap/tabla-tareas.md` (git-excluded).

- [ ] **Step 1: Whole-project checks:**
  `MEMORY_ENABLED=false uv run pytest -m "not slow and not hardware and not eval" -q -n auto`,
  `uv run pyright`, `uv run mypy server/src robot/src`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run ruff check scripts/*.py`,
  `uv run python scripts/check_reserved_terms.py`; `just gate` only when Pipec is not rehearsing.
  Write the test count in the PR.
- [ ] **Step 2: Hardware acceptance by Pipec** (streaming route; a copy of the database first;
  `.env`: memory, card, record, recall and sensitive read on, face and speaker on,
  `LOG_CONVERSATION_TEXT=true` for the sitting only). Only phrases that passed the Task 0 script.
  The agent confirms each case in `logs/server.log` (`card.prompt` and the turn's need) and
  writes the outcome; Pipec judges what he hears.
  1. **Greetings, a new session** (server just started, or 180 s of silence): «hola», «hola Iroko,
     ¿cómo estás?», «buenos días» with the face in view → no taste in the reply; log
     `tastes=withheld` 3 of 3.
  2. **Taste talk:** «¿qué me recomiendas comer hoy?», «¿qué música me gusta?» → a taste may be
     used, always as the owner's («como te gusta…»); log `tastes=included`.
  3. **The robot's own taste:** «¿y a ti qué música te gusta?» → the robot does not claim the
     owner's taste as its own (gate: 0 replies that do).
  4. **No face** (camera covered): «hola» and «¿qué me gusta comer?» → no card read (no
     `card.prompt` line), and the reply says it does not know; nothing seen or remembered is
     claimed (gate: 0 invented tastes).
  5. **The prompt's words:** across every turn of the sitting, «tuteo» heard 0 times (the word is no
     longer in the prompt). A reply that still echoes the prompt is counted in the record and left
     to the model evaluation of P4.1, not patched here.
  6. **`usted`:** `iroko-admin change address_form` to `usted` (server stopped), five ordinary
     turns («¿cómo estás?», «cuéntame un chiste», «¿qué hora es?», «¿qué me recomiendas comer?»,
     «gracias») → coherent and in `usted` in at least 4 of 5, log `address_form=usted`; then back to
     `tu` and one turn to confirm. D-8 applies.
  7. **«¿qué sabes de mí?»** → the fixed summary, unchanged.

  `LOG_CONVERSATION_TEXT` back to `false` when the sitting ends. A real phrasing that fails becomes
  a test row and a fix commit, recorded as a count.
- [ ] **Step 3:** Update the documents above; move this plan to `docs/plans/completed/` with its
  closing status line.
- [ ] **Step 4:** commit `docs: close plan 0081, what the robot says accepted`, push, open the PR,
  squash-merge with green CI (GitHub is delegated, Pipec 2026-11-04), delete the branch and return
  to `main`.

---

## Non-goals

The pending topics of the greeting and a contact's phone by voice (row 7, ADR 0037); a greeting
that picks up anything at all; the recall prompt and its fixture; the fixed controller strings and
their tuteo; Chilean modismos; a model-based relevance judge or a second model call; the model's
wrong general facts and a larger model (ADR 0036, P4.1); the card's predicates, cap and audit
(ADR 0026 decisions 2 and 3 otherwise unchanged); STT; the wire, the robot, `/chat` and
`/vision/respond`; **any guard that rewrites the model's replies** (stripping «Tuteo» or quotes):
a weakness of the 3B model, left out by Pipec on 2026-11-11.

## Self-review (2026-11-11)

- **Scope coverage.** Item 1 (tastes only when relevant, never in a greeting, never as the robot's
  own) → D-4, D-5, Tasks 2 and 3, hardware cases 1 to 3. Item 2 («Tuteo» and the card's quotes) →
  D-2 and Task 1 remove the word from the prompt, case 5 checks it; the quotes stay (anti-injection,
  not spoken) and no reply guard is built (*Non-goals*). Item 3 (`usted` with the 3B model) → D-2,
  D-3, D-8, Tasks 1 and 3, case 6. Item 4 (nothing invented with an empty session) → D-4 (no taste on a cold greeting),
  D-6, Task 4, cases 1 and 4. Row 7 is out (*Non-goals*). The golden digests move in Tasks 1, 3 and
  4, each regenerated and counted in the PR.
- **Type consistency.** `AddressForm`, `language_rule`, `TASTE_CUE_WORDS`, `tastes_are_relevant`,
  `PromptCard`, `render_prompt_card(…, include_tastes=…)`, `prompt_card_for_turn`,
  `ProfileCardProvider` and `PreparedTextTurn.address_form` are each defined once, in the task that
  produces them, and named the same afterwards.
- **Size.** Small: four working tasks, one new pure module, no migration, setting, route or wire
  change. Task 2 is independent of the others; Tasks 1, 3 and 4 touch the same prompt and the same
  fixture and go in order.
- **Model or code.** Every task changes our code or our prompt, not the model's output; nothing is
  tied to `qwen2.5:3b`, and a later model is measured by re-running Task 5's hardware cases.
- **Open for Pipec at promotion:** D-2's two sentences, D-4's cue list and its 4-letter floor,
  D-5's labels and footer, D-6's bullet and D-8's stop rule. The design choice to confirm is D-4:
  a deterministic gate instead of trusting the prompt alone.
