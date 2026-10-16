# 0064 — Speech and dialogue quality: Spanish, tuteo, no false «guardé», a forgiving answer

> **Status:** `Draft` — written 2026-10-16 from the audit of the three items before Step 0
> (streaming repair, CM-1 remainder, CM-3b) and from the findings of the Plan 0063 hardware
> acceptance; **revised the same day after an independent review** (two read-only reviewers; their
> findings are folded in, see *Review record*). Pipec decided D-1, D-2 and D-3 on 2026-10-16; D-4 to
> D-8 are the plan's and wait for his confirmation when he promotes it. **Not rehearsed** in a
> scratch copy: the code below is the specification of each task, not a rehearsed diff. It is not
> executable until Pipec marks it `Ready` and `NOW`; to be executed in a **new session**.

> **For agentic workers:** if the status above does not say `Ready`, stop: Pipec has not promoted
> this plan. REQUIRED SUB-SKILLS: `superpowers:executing-plans`,
> `superpowers:test-driven-development`, `superpowers:verification-before-completion`,
> `superpowers:finishing-a-development-branch`. **Pipec's rules win over the skills:** one plain
> branch from `main` (`git checkout -b`), never a git worktree, subagents only if Pipec asks, and
> this plan lives under `docs/plans/`. Implement exactly the tasks below, in order, one commit per
> task, each code test observed RED for the stated reason first (the text-only Tasks 5 and 8 have
> no RED). If evidence contradicts the plan, stop and report the conflict instead of redesigning.
> Pipec runs every local process (server, robot, Ollama, anything that uses the camera or the
> microphone); record outcomes only, never a sentence, a value or a name. The Bash tool of this
> environment loses backslashes and non-ASCII characters in heredocs: create and edit files with
> the Write and Edit tools. Run the suite with `MEMORY_ENABLED=false` (CI does). **Dates:** a test
> that builds data at a fixed date must also pin the clock (`clock=lambda: ...`); Plan 0063 shipped
> a test that broke the next day.

**Goal:** What Iroko says sounds like one voice and tells the truth about memory. Every spoken
string and every persona prompt uses neutral Spanish with **tuteo** (Pipec lives in Santiago de
Chile; idioms may come later); the master prompt and the streaming contract ask for Spanish like the
classic contract does; a model reply never claims to have saved, registered or noted anything
(nothing is stored by the model: the only save is the deterministic one of Plan 0063); the explicit
answer to a memory offer survives the way Whisper `small` actually writes it («autoriza a guardar
mi café», «sí po, autorizo…»); and the stale prose and the missing start-up signal found by the
audit are fixed. No wire change, no migration, no new route.

**Architecture:** Five small, independent changes behind one plan, in this order.
(1) A tuteo pass over the personas, the prompt templates, the fixed controller strings, the
perception templates and the fallback/look phrases, plus a guard test that no fixed spoken string
or prompt uses voseo (the *recognition* lexicons and the internal extraction prompts are an
allowlist). (2) One language rule as the **last** block of the master prompt
(`build_system_prompt`) and one sentence in `_STREAMING_OUTPUT_CONTRACT`. (3) The answer grammar in
`intent_resolution` accepts the third-person form of the verbs, the Chilean openers, a trailing
«po» and a leading «mi»/«mis» in the value. (4) A pure module `server/claim_guard.py` whose closed
lexicon recognizes a model sentence that claims a memory action; applied to **model-generated text
only**: the classic reply in `text_turn._generate` and, in the stream, through one new function
`synthesize_model_sentence` used where the model's sentences are spoken; one extra line in
`_MEMORY_DISCIPLINE`. (5) Removal of stale prose and a start-up probe that only warns when Ollama
is unreachable.

**Tech Stack:** Python 3.12, FastAPI, pytest. No new dependency.

**Spec:** [ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md) decision 9 (the
answer grammar, amended by this plan with Pipec's decision D-3 of 2026-10-16),
[ADR 0018](../../adr/0018-user-emotion-decided-apart.md) (the streaming contract is plain text and
names no tag), the acceptance note
[`0063-memory-dialogue-acceptance.md`](../../evals/0063-memory-dialogue-acceptance.md) (the
findings this plan closes) and the repository rule `.claude/rules/python-style.md` (not tracked;
read it from the working copy).

## Task overview

| # | Task | Closes |
|---:|---|---|
| 0 | Revalidate the baseline; measure the language baseline | — |
| 1 | One dialect, tuteo, everywhere the robot speaks | D-1, voseo in persona/controller/fallback |
| 2 | The master prompt and the streaming contract ask for Spanish | French replies (to be measured) |
| 3 | The explicit answer survives the speech-to-text | D-3, 2 of 4 answers parsed |
| 4a | `claim_guard`: the pure lexicon | D-2, D-5 |
| 4b | The guard on the classic reply | "dije que guardé" (classic) |
| 4c | The guard on the stream | "dije que guardé" (stream) |
| 4d | One prompt line against claiming to save | support for the guard |
| 5 | Stale prose | audit finding |
| 6 | Say so when Ollama is unreachable at start-up | audit finding |
| 7 | Measure the language | D-4 |
| 8 | Documentation truth | the docs this plan makes stale |

## Global Constraints

- No real household data in any tracked file, test, prompt, doc or commit message: invented
  canaries only (`scripts/check_reserved_terms.py` guards it).
- Every new spoken phrase is neutral Spanish with tuteo (D-1). A *recognition* lexicon (what the
  robot accepts as input: `cognition/intent_resolution.py`, `memory/lexicon.py`) keeps voseo forms
  on purpose; the internal extraction prompts (`memory/candidate_extraction.py`,
  `memory/consolidation.py`) are never spoken and keep theirs (their wording is the measured
  behaviour of CM-0), so they are allowlisted with that reason.
- The guard of Task 4 touches **model-generated** text only. The deterministic results of
  Plan 0063 («Listo, lo guardé.», «Está bien, no lo guardo.», the offer, the failure phrase) and
  the fallback phrases must reach the wire byte for byte (a test pins it).
- The audio contract is untouched (WAV, 16 000 Hz, mono, int16); no `print()`; Google docstrings;
  type hints; `ruff` clean over the explicit paths of every file touched (including `scripts/`);
  `mypy server/src robot/src` clean.
- A commit title is at most 72 characters; check `git log -1` after every commit.
- `MEMORY_CANDIDATES_ENABLED` stays `false` by default.

## Decisions

1. **D-1 — Tuteo everywhere (Pipec, 2026-10-16).** Neutral Spanish, Santiago de Chile; modismos are
   a later, separate addition. Persona prompts included, because the model imitates the dialect of
   its prompt.
2. **D-2 — «Dije que guardé» is answered by a deterministic guard plus one prompt line (Pipec,
   2026-10-16).** The prompt line is support (a small model may ignore it); the guard is what the
   tests pin.
3. **D-3 — The explicit answer admits the speech-to-text's usual writings (Pipec, 2026-10-16).**
   The value stays mandatory and the short verbs keep their article rule. Accepted: `autoriza`,
   `aprueba` (alone, or followed by `guardar`, `a guardar` or `que guardes`) and their `no`
   forms; the openers `ya`, `dale`, `po`; a trailing `po`; one leading `mi` or `mis` before the value.
   Cost to know: a message with the shape of an answer makes the controller verify face and voice
   first (3 to 4 s, ADR 0021 decision 9), so the wider grammar makes that check fire on a few more
   ordinary phrases («guarda mi …»); it still writes nothing without an open offer.
4. **D-4 — The language gate (plan default, Pipec ratifies).** The 0061 runs already had 1 of 147
   and 3 of 164 replies judged not Spanish, so a threshold of 2 % would pass without any change.
   The gate is therefore: (a) **no worse than the baseline** measured in Task 0 on the same
   command, and (b) **none of Pipec's first 20 hardware turns** after the change in another
   language. It is reported, not enforced by a CI test (it needs a real model); a miss is a
   finding, not a redesign.
5. **D-5 — The replacement sentence** for a model sentence that claims a memory action is
   «Eso no lo he guardado.» (true on that turn: only a promotion stores a fact, and a promotion is
   never spoken by the model).
6. **D-6 — The Ollama probe only warns.** One `GET /api/tags` at start-up with a short timeout; on
   failure a warning with the exception class, never an exception, never a delay beyond its
   timeout. It does **not** detect the cold-start 500 seen in the acceptance (the model answers
   `/api/tags` while it is still loading): the operator manual says so and advises warming the
   model. No `/health` field (a separate, additive decision).
7. **D-7 — The English prompt blocks are not translated now.** `_MEMORY_DISCIPLINE`, the
   behaviour directives and the emotion adaptation stay in English inside a Spanish prompt: the
   audit suspects them of the drift to French, but that is unmeasured. Task 7 measures first; a
   translation would be its own change with its own measurement.
8. **D-8 — The old `undue_accept`/`contract_first` variants and the tag-filter limits stay as they
   are** (closed plans' evidence; documented limits).

## Required reading

- `AGENTS.md`, `docs/architecture/implementation-guardrails.md`, `.claude/rules/`.
- [ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md) decision 9 and
  *Acceptance*; [the 0063 acceptance note](../../evals/0063-memory-dialogue-acceptance.md).
- `server/src/server/{llm_streaming,llm,text_turn,streaming,streaming_render,sentences,settings,main}.py`,
  `server/src/server/cognition/{controller,intent_resolution}.py`,
  `server/src/server/characters/{__init__,iroko,nova}.py` and `characters/profiles/ejemplo_vendedor.md`,
  `server/src/server/vision/perception.py`, `scripts/{reply_language,stream_diagnosis_report}.py`.
- The tests named in each task.

## Permitted files

- Production: `server/src/server/{llm_streaming,llm,text_turn,streaming,streaming_render,settings,main}.py`,
  new `server/src/server/{claim_guard,ollama_probe}.py`,
  `server/src/server/cognition/{controller,intent_resolution}.py`,
  `server/src/server/characters/{__init__,iroko,nova}.py`,
  `server/src/server/characters/profiles/ejemplo_vendedor.md`,
  `server/src/server/vision/perception.py`.
- Other: `.env.example` (including `VISION_LOOK_PHRASE`), `justfile` (one comment),
  `scripts/stream_diagnosis_report.py`.
- Tests: those named in each task and their new files.
- Docs (Task 8): ADR 0021 (amendment) and the quoted phrase in ADR 0007, `docs/runbooks/operator-manual.md`,
  `docs/architecture/current-state.md` and its Archify diagram if its text changes,
  `docs/roadmap/cognitive-roadmap.md`, the plan index files and this plan.

No new URL, field, migration, setting or dependency. The robot (`robot/src`) is not edited.

---

## Task 0: Revalidate the baseline

- [ ] **Step 0: Status.** This plan says `Ready`; otherwise stop.
- [ ] **Step 0b: The code is in `main`.** The Plan 0063 PR (branch `feat/0063-cm3a-memory-dialogue`)
  and the PR that carries this plan are merged: `git fetch && git merge-base --is-ancestor
  <the 0063 squash commit> origin/main` must succeed and `rg -n "def parse_memory_answer" server/src`
  must find the function. If not, stop.
- [ ] **Step 1: Branch.** `git checkout main && git pull`, clean tree, then
  `git checkout -b feat/0064-speech-and-dialogue-quality`; record the base SHA.
- [ ] **Step 2: Baseline.** `just gate`; record the outcome and test count (3217 at the close of
  Plan 0063). A pre-existing failure is reported, not hidden.
- [ ] **Step 3: Re-audit.** Each of these must find what this plan names:
  `rg -n "_STREAMING_OUTPUT_CONTRACT" server/src`, `rg -n "Hablás siempre" server/src`,
  `rg -n "_MEMORY_DISCIPLINE" server/src`, `rg -n -i "llm_fallback_phrase" server/src .env.example`,
  `rg -n "def synthesize_sentence" server/src`. A difference is reported before code.
- [ ] **Step 4: The language baseline.** With Pipec's Ollama running, `just eval-chat --provider
  ollama --mode stream` once, **before any change**; record the *Not in Spanish* count and the
  number of replies it could judge (the denominator). Counts only.

## Task 1: One dialect, tuteo, everywhere the robot speaks

**Files:** modify `server/src/server/characters/{__init__,iroko,nova}.py`,
`server/src/server/characters/profiles/ejemplo_vendedor.md`, `server/src/server/llm.py`,
`server/src/server/cognition/controller.py`, `server/src/server/vision/perception.py`,
`server/src/server/settings.py`, `.env.example`; tests modified (Step 3) and new
`tests/unit/test_no_voseo_in_spoken_strings.py`.

**The mapping** (tuteo, neutral). Strings: `Sos` → `Eres`; `Tenés` → `Tienes`; `preguntás` →
`preguntas`; `quién sos` → `quién eres`; `volvé a hablarme` → `vuelve a hablarme`;
`dejame mirar` → `déjame mirar`. Persona line `Hablás siempre de "vos" (nunca "tú")` →
`- Tuteas siempre a la persona.` (the line must not contain the word `vos`, which the guard
forbids). Pronoun: `con vos` → `contigo`, `para vos` → `para ti`, `frente a vos` → `frente a ti`.
Every other voseo verb or imperative in the persona, prompt templates and perception templates to
its `tú` form: `conocés, Conservás, tenés permitido, soltás, ejecutás, actuás, suplantás,
explicalo, redirigí, Presentate, cubrilo, compartís, tratás, podés, revelás, Reconocés, saludá,
Pedile, Confirmáselo, Acabás, convivís, escuchás, explicás, engañás, encontrás, alterás, Saludalo,
Ofrecele, preguntale, repetilo, Respondé, reaccioná, respondé SIEMPRE con JSON (llm.py)`.

- [ ] **Step 1: The guard test first.** New `tests/unit/test_no_voseo_in_spoken_strings.py`:
  walk `server/src/server/**/*.py` and the persona `.md` profiles and fail on a whole word (case-
  insensitive, accents as written) of this closed list: `sos, tenés, querés, podés, sabés,
  preguntás, volvé, dejame, decime, mirá, vení, hablás, vos, contame, acordás, pensás, necesitás,
  ayudá, ayudame, escuchá, escuchás, esperá, fijate, avisame, conocés, conservás, soltás, ejecutás,
  actuás, suplantás, explicalo, explicás, redirigí, presentate, cubrilo, compartís, tratás,
  revelás, reconocés, saludá, saludalo, pedile, ofrecele, preguntale, repetilo, respondé,
  reaccioná, confirmáselo, acabás, convivís, engañás, encontrás, alterás`, **outside** an
  allowlist with one reason each: `cognition/intent_resolution.py` and `memory/lexicon.py`
  (recognition lexicons: they accept voseo input), `memory/candidate_extraction.py` and
  `memory/consolidation.py` (internal prompts, never spoken). A second test asserts that the two
  recognition files still contain at least one listed word (so the allowlist cannot silently go
  stale). Expected RED: the first test fails listing the files and words found today (the
  personas, `characters/__init__.py`, `llm.py`, `controller.py`, `perception.py`, `settings.py`,
  `ejemplo_vendedor.md`).
- [ ] **Step 2: Implement** the mapping. Keep every sentence's meaning and the persona's
  character; only the dialect changes. `settings.llm_fallback_phrase` becomes
  `"Uy, mi cerebro todavía se está despertando. Dame unos segundos y vuelve a hablarme."`
  (also in `.env.example`), `vision_look_phrase` becomes `"A ver, déjame mirar..."` (also the
  commented `VISION_LOOK_PHRASE` line of `.env.example`). **Ask Pipec** whether his own `.env`
  redefines either phrase (do not read or edit `.env`) and record the answer.
- [ ] **Step 3: Update the tests that pin the old strings** (found by `rg -n "Sos |Tenés|preguntás|
  volvé|dejame|quién sos|reconocés" tests`): `test_chat_endpoint.py:343`,
  `test_cognitive_controller.py:219,338,575,589,607`, `test_owner_authenticated_turn.py:336`,
  `test_owner_authenticated_stream.py:287`, `test_owner_stranger_matrix.py:324`,
  `test_transcribe_pipeline.py:126,132,182`, `test_transcribe_stream.py:381,530`,
  `test_vision_dialog.py:292` and `tests/unit/test_perception.py:57` (`NO reconocés` →
  `NO reconoces`), to the new strings («Todavía no puedo confirmar quién eres.», «Eres Ada.»,
  «Tienes 2 hijos.», «No entendí si preguntas por la fecha actual o por información personal. …»).
  Fixtures that only use «Sos …» as sample text (`test_character_registry.py`,
  `test_character_parser.py`, `test_llm_streaming.py:79`) are not spoken strings: leave them.
- [ ] **Step 4:** run `uv run pytest tests/unit tests/integration -q -p no:cacheprovider -n auto`
  once (expected: all green); lint and types over the files.
- [ ] **Step 5: Commit** `feat(server): speak in neutral tuteo everywhere (plan 0064)`.

## Task 2: The master prompt and the streaming contract ask for Spanish

Pipec's idea (2026-10-16): one rule in the master prompt, «siempre responde en español», may fix
most of the drift. It goes in **both** places: the master prompt (`build_system_prompt`, which every
route uses: classic, stream, onboarding, vision) and the streaming contract (the last thing the
stream's model reads).

**Files:** modify `server/src/server/characters/__init__.py`, `server/src/server/llm_streaming.py`;
tests new `tests/unit/test_prompt_language.py` (it builds the prompt through `build_system_prompt`,
like `tests/unit/test_memory_discipline.py` and `tests/unit/test_system_prompt_date.py`) and
modified `tests/unit/test_llm_streaming.py`.

- [ ] **Step 1: Failing tests.** (a) `build_system_prompt(...)` for the default profile, with and
  without memory, perception, onboarding and an emotion, **ends with** `_LANGUAGE_RULE`, and the
  rule contains `español` and `tuteo`; it is the last part, after the memory and perception
  blocks (a small model weighs the end of the prompt). (b) The prompt from
  `_streaming_system_prompt("...")` contains `siempre en español` and still names no tag
  (ADR 0018). Expected RED: `AssertionError` (both absent).
- [ ] **Step 2: Implement.**

```python
# server/src/server/characters/__init__.py
_LANGUAGE_RULE = (
    "\nIDIOMA — Responde siempre en español neutro, con tuteo (tú). "
    "No uses otro idioma ni mezcles palabras de otro idioma, aunque la persona lo haga."
)
# ... appended as the LAST element of `parts` in build_system_prompt

# server/src/server/llm_streaming.py
_STREAMING_OUTPUT_CONTRACT = (
    "\n\nResponde únicamente en texto plano, siempre en español: sin JSON, sin etiquetas, "
    "sin listas ni formato. Escribe solo lo que dirías en voz alta."
)
```

  Keep the comment that the contract names no tag.
- [ ] **Step 3:** run the two test files, `tests/unit/test_stream_diagnosis_variants.py` (it uses
  the contract as text) and every test that pins a whole system prompt
  (`rg -n "base_prompt|system_prompt" tests`); update those that compare the entire prompt. Lint
  and types over the files.
- [ ] **Step 4: Commit** `feat(server): ask every reply for Spanish in the master prompt (plan 0064)`.

## Task 3: The explicit answer survives the speech-to-text

**Files:** modify `server/src/server/cognition/intent_resolution.py`; tests modified
`tests/unit/test_memory_answer_grammar.py` and `tests/unit/test_intent_resolution.py` (run only).

- [ ] **Step 1: Failing tests** (parametrized; each case is `message → (accept, phrase)` or
  `None`; `phrase` is what the grammar returns, folded). Accepted, after this task:
  `«Sí, autoriza a guardar mi café»` → `(True, "cafe")`;
  `«Autoriza guardar el mate»` → `(True, "el mate")`;
  `«Ya, autorizo guardar el mate»` → `(True, "el mate")`;
  `«Sí po, autorizo guardar el mate»` → `(True, "el mate")`;
  `«Dale, autorizo guardar el mate»` → `(True, "el mate")`;
  `«Autorizo guardar el mate po»` → `(True, "el mate")`;
  `«Aprueba guardar las empanadas»` → `(True, "las empanadas")`;
  `«Autoriza guardar mis empanadas»` → `(True, "empanadas")`;
  `«No autoriza guardar el jazz»` → `(False, "el jazz")`;
  `«No, no autoriza a guardar mi jazz»` → `(False, "jazz")`;
  `«Guarda mi café»` → `(True, "cafe")` (the short verb is satisfied by «mi»).
  Still refused (must stay `None`): `«Autoriza»`, `«Sí po»`, `«Ya»`, `«Dale»`,
  `«Guarda silencio»`, `«Guarda mi»`, `«Ya, guarda silencio»`, `«Autorizo guardar»`,
  `«Autoriza guardar el mate de la abuela de mi vecino de al lado»` (more than six words).
  Expected RED: the accepted cases fail with `assert None == MemoryAnswer(...)`, except
  `«Autorizo guardar el mate po»`, which fails with a phrase that still ends in «po»
  (`MemoryAnswer(accept=True, phrase="el mate po")`).
  Run first: `uv run pytest tests/unit/test_memory_answer_grammar.py -q -p no:cacheprovider`.
- [ ] **Step 2: Implement** in `intent_resolution.py`: add `"ya"`, `"dale"`, `"po"` to
  `_ANSWER_OPENERS`; add `"po"` to `_ANSWER_TRAILERS` (the trailing-word loop already strips it
  repeatedly); add the third-person prefixes after the first-person ones **in each tuple, longest
  first** («autoriza que guardes», «aprueba que guardes», «autoriza a guardar», «aprueba a
  guardar», «autoriza guardar», «aprueba guardar», «autoriza», «aprueba») and the `no` forms
  («no autoriza …», «no aprueba …»); in `_answer`, drop **one** leading `mi` or `mis` from the value
  and treat it as the article for the short verbs. Keep every other rule (article for the short
  verbs, at most six words, no value starting with «guardar» or «que»). Update the module comment
  and the `parse_memory_answer` docstring; the openers are only skipped, so an opener alone still
  matches nothing.
- [ ] **Step 3: The round trip still holds.** `tests/integration/test_candidate_dialogue.py`
  already asserts that the words the offer asks for resolve the offer; run it unchanged. Add one
  test that a value stored without a determiner resolves from «autoriza a guardar mi {x}».
  Pin the clock in any new test that builds a candidate (`clock=lambda: _NOW`).
- [ ] **Step 4:** run `tests/unit/test_memory_answer_grammar.py tests/unit/test_intent_resolution.py
  tests/integration/test_candidate_dialogue.py tests/integration/test_memory_dialogue_routes.py`
  (expected: all green; the 64 fixtures of `intent_resolution_es.json` unchanged); lint and types.
- [ ] **Step 5: Commit** `feat(server): accept how Whisper writes the memory answer (plan 0064)`.

## Task 4a: `claim_guard`, the pure lexicon

**Files:** new `server/src/server/claim_guard.py`; test new `tests/unit/test_claim_guard.py`.
The module imports only `re` and `server.sentences` (so the cognitive core's import-graph guard is
not involved: nothing under `cognition/` imports it).

**Interface.** `REPLACEMENT = "Eso no lo he guardado."`;
`claims_memory_action(sentence: str) -> bool`; `replace_if_claim(sentence: str) -> str` (the
sentence itself, or `REPLACEMENT`); `neutralize_memory_claims(text: str) -> str`.

**The lexicon is closed and exact.** It is matched on `sentence.casefold()` **without removing
accents** (so `guardé` ≠ `guarde`), one sentence at a time, and a sentence is a claim when any of
these patterns match:

1. object + the speaker's preterite, present, future or perfect, written in the module as explicit
   alternations of exactly these forms: `\b(lo|la|los|las|eso|esto|todo)\s+(guardé|guardaré|guardo|
   registré|registraré|registro|almacené|almacenaré|almaceno|memoricé|memorizaré|memorizo|anoté|
   anotaré|anoto|apunté|apuntaré|apunto|he guardado|he registrado|he almacenado|he memorizado|
   he anotado|he apuntado)\b`;
2. the state of the thing said: `\b(queda|quedó|quedará|está|estará|ya\s+está|ha\s+sido|fue|será|
   siempre\s+será)\s+(guardad|registrad|almacenad|memorizad|anotad|apuntad)[oa]s?\b` and
   `\blo\s+tengo\s+(guardado|anotado|registrado)\b`;
3. future recall: `\b(lo|la|eso|esto)\s+recordaré\b` and `\bme\s+acordaré\b`.

A **bare participle** («Anotado.», «Guardado.») is **not** a claim (the continuity of ADR 0020
keeps what was said, and `tests/integration/test_generic_turn_continuity.py` simulates a model
that answers «Anotado.»: it must stay green unchanged). It is never a claim when the **raw**
sentence contains `?` or `¿`. It is never a claim when a negation stands in the three words before
the match: `\b(no|nunca|jamás|aún no|todavía no|ya no)\s+(\w+\s+){0,2}$` on the text before the
match («No lo he guardado» and «todavía no lo guardo» are not claims; «No te preocupes, ya lo
guardé» is one). Infinitives and imperatives («puedo guardar silencio», «guarda tus llaves») never
match by construction.

`neutralize_memory_claims(text)`: if no sentence claims, return `text` **unchanged**; otherwise
split with `server.sentences.split_first_sentence` (an unterminated tail counts as the last
sentence), replace each claiming sentence by `REPLACEMENT`, collapse consecutive replacements into
one and join with a single space.

- [ ] **Step 1: Failing tests** `tests/unit/test_claim_guard.py`: ≥ 14 claiming sentences →
  `True` (include, as invented equivalents of the acceptance findings: «El café siempre será
  guardado.», «El café está registrado.», «Lo guardé.», «No te preocupes, ya lo guardé.», «Lo anoto
  en mi memoria.», «Lo recordaré siempre.», «Ya lo tengo guardado.»), ≥ 14 non-claims → `False`
  (include «Anotado.», «¿Quieres que lo guarde?», «No lo he guardado.», «Todavía no lo guardo.»,
  «Puedo guardar silencio.», «Guarda tus llaves.», «Recuerdo que me dijiste que hace calor.»,
  «Eso no lo he guardado.»), `neutralize_memory_claims` on a three-sentence reply with one claim (the
  two others byte for byte), on all-claims (one `REPLACEMENT`), on claim-free and empty text
  (returned unchanged), and `replace_if_claim` of `REPLACEMENT` itself is `REPLACEMENT`. Expected
  RED: `ModuleNotFoundError: No module named 'server.claim_guard'`.
- [ ] **Step 2: Implement** (pure, no I/O, no logging of the text). **Step 3:** run the file; lint
  and types. **Step 4: Commit** `feat(server): add a pure guard for memory claims (plan 0064)`.

## Task 4b: The guard on the classic reply

**Files:** modify `server/src/server/text_turn.py`; test modified `tests/unit/test_text_turn.py`.

- [ ] **Step 1: Failing tests:** with `llm.generate_response` returning «Perfecto, lo guardé.» the
  `TextTurnResult.response` is `REPLACEMENT`; a plain reply is unchanged; the fallback phrase is
  unchanged; the same guard covers `/chat` and `/vision/respond` because they use `_generate`.
  Expected RED: `AssertionError` (the claim reaches the response).
- [ ] **Step 2: Implement** in `_generate`'s success path, right after the model returns and
  before the reply is logged or recorded: `response = neutralize_memory_claims(response)`.
- [ ] **Step 3:** run `tests/unit/test_text_turn.py tests/integration/test_generic_turn_continuity.py
  tests/integration/test_transcribe_pipeline.py` (expected: green, the continuity tests unchanged);
  lint and types. **Step 4: Commit** `feat(server): keep a false "guardé" out of the classic reply (plan 0064)`.

## Task 4c: The guard on the stream

**Files:** modify `server/src/server/streaming_render.py` (a new `StreamState.last_sentence_replaced:
bool = False`, a new `synthesize_model_sentence`) and `server/src/server/streaming.py`; test
modified `tests/integration/test_transcribe_stream.py` (read its fixtures first).

**Design.** `synthesize_model_sentence(sentence, state) -> str | None` calls `replace_if_claim`;
if the result is `REPLACEMENT` and `state.last_sentence_replaced` is true it returns `None` (the
collapse that `neutralize_memory_claims` does for the classic reply, here across deltas); otherwise
it sets `last_sentence_replaced` and calls `synthesize_sentence`. It is used in exactly the two
places where the model's own sentences are spoken: the loop of `streaming._consume_llm_stream` and
the tail of `streaming_render._finalize_model_output`. `_consume_body`, `emit_fallback`, the offer
and every deterministic plan keep calling what they call today, so `scripts/eval_stream_protocol.py`
(which uses `_consume_body`) measures the same thing as before.

- [ ] **Step 1: Failing tests:** a model stream whose second sentence claims a save speaks
  `REPLACEMENT` in its place (one `audio` event with that text), the others are unchanged, `done`
  still ends the stream, and the spoken-text log and the recorded history carry the replaced text;
  two claiming sentences in different deltas produce **one** `REPLACEMENT`; a claim in the unterminated
  tail is replaced; the fallback phrase and the Plan 0063 offer/answer events are byte for byte
  (the existing tests stay green unchanged). Expected RED: the claim reaches the event.
- [ ] **Step 2: Implement.** **Step 3:** run `tests/integration/test_transcribe_stream.py
  tests/integration/test_stream_offer.py` and the tests of `scripts/eval_stream_protocol.py`; lint
  and types.
- [ ] **Step 4: Commit** `feat(server): keep a false "guardé" out of the stream (plan 0064)`.

## Task 4d: One prompt line against claiming to save

**Files:** modify `server/src/server/characters/__init__.py`; test modified
`tests/unit/test_memory_discipline.py`.

- [ ] **Step 1: Failing test:** the prompt built by `build_system_prompt` contains the sentence
  `You do NOT store anything yourself`. Expected RED: `AssertionError`.
- [ ] **Step 2: Implement:** add to `_MEMORY_DISCIPLINE` (English, like the block): «You do NOT store
  anything yourself: never say you saved, registered or noted something. Only the robot's own
  spoken offer saves, and only after the person agrees.» (It is support; the guard is the
  guarantee.) **Step 3:** run the prompt tests; lint and types. **Step 4: Commit**
  `feat(server): tell the model it stores nothing itself (plan 0064)`.

## Task 5: Stale prose (text only, no RED)

**Files:** `scripts/stream_diagnosis_report.py`, `justfile` (one comment).

- [ ] **Step 1:** `justfile:125` says `eval-chat` measures, with `--mode stream`, «el protocolo
  EMOTION: del streaming»: the stream is plain text since Plan 0059. Rewrite the comment (Spanish,
  ASCII-safe like its neighbours) to say it measures the stream's plain-text contract and the
  reply language.
- [ ] **Step 2:** `scripts/stream_diagnosis_report.py` (about lines 291 to 317 and 353 to 354)
  still argues about «the `llm_streaming.py` claim that Ollama withholds» a schema-constrained
  reply. Read `llm_streaming.py`'s header; if the claim is gone from the code, rewrite those
  sentences as a statement of what the probe measures. Do **not** change any computed value or
  verdict. `tests/unit/test_stream_diagnosis_report.py` pins phrases («stays unproven» at about
  lines 526 and 551): update them in the same commit. Run that test and lint
  `scripts/stream_diagnosis_report.py` with explicit paths (`scripts/` is excluded from
  `ruff check .`).
- [ ] **Step 3: Commit** `docs(scripts): drop the stale streaming-protocol prose (plan 0064)`.

## Task 6: Say so when Ollama is unreachable at start-up

**Files:** new `server/src/server/ollama_probe.py`; modify `server/src/server/main.py`; tests new
`tests/unit/test_ollama_probe.py` and modified `tests/unit/test_app_lifecycle.py`,
`tests/unit/test_main_lifespan.py`, `tests/integration/test_candidates_startup.py` (find the exact
files with `rg -n "lifespan|_quiet_startup" tests`).

- [ ] **Step 1: Failing tests.** `probe_ollama(client, base_url) -> bool` does one `GET {base_url}/api/tags`
  with a 3 s timeout and `response.raise_for_status()`; on any `httpx.HTTPError` it returns `False`
  after logging **one** warning that contains only `type(exc).__name__`. With `httpx.MockTransport`:
  200 → `True` and no warning; a connection error and a 500 → `False` and exactly one warning
  naming the class. A lifespan test that the probe is called once with `cfg.ollama_url` and that a
  `False` result neither stops the start nor changes `/health`. Expected RED: `ModuleNotFoundError`.
- [ ] **Step 2: Implement** and call it once in the lifespan after the models load, with the
  settings the lifespan already reads (`cfg`, not the global). There is no provider guard
  (`llm_provider` is `Literal["ollama"]`; a guard makes mypy report an unreachable statement).
- [ ] **Step 3: No test may reach the network.** Add an autouse stub (an `AsyncMock` returning
  `True` patched onto `server.main.probe_ollama`) to `_quiet_startup` and to every other fixture
  that enters the lifespan; the guardrails require offline, deterministic tests.
- [ ] **Step 4:** run the lifespan tests; lint and types. **Step 5: Commit**
  `feat(server): warn at start-up when Ollama is unreachable (plan 0064)`.

## Task 7: Measure the language (a measurement, not a test)

- [ ] **Step 1:** with Pipec's Ollama running, `just eval-chat --provider ollama --mode stream`
  twice (the command has no seed argument); record, for each run, the *Not in Spanish* count and the
  number of replies it could judge. No sentence is recorded.
- [ ] **Step 2:** ask Pipec to hold a short conversation of at least 20 turns by voice and report
  how many replies were not Spanish (a count, nothing else). Ask him also to say «autorizo guardar
  el …» to a fresh offer a few times and report only how many were understood (the 2-of-4 baseline).
- [ ] **Step 3:** compare with D-4 and write the numbers in the execution record. If the gate is
  missed, **stop and report**: the next candidate is the translation of the English prompt blocks
  (D-7), which is a new plan.

## Task 8: Documentation truth (text only, no RED)

- [ ] ADR 0021 decision 9: amend the answer-grammar bullet (the verbs of D-3, the openers, the
  trailing «po», the leading «mi»/«mis»), the «byte-identical» sentence of the fall-through (the
  ordinary turn is generated by the model and a claim of saving is replaced by the guard), and add
  a dated line to its status; ADR 0007's quoted phrase («Todavía no puedo confirmar quién sos.»).
- [ ] `docs/runbooks/operator-manual.md`: the answer forms, that the robot never claims to have
  saved (and what it says instead), tuteo, the Ollama start-up warning (it does not catch the
  cold-start 500; warm the model with one ordinary sentence after the start) and the stale prose of
  Task 5 if it lives there.
- [ ] `docs/architecture/current-state.md` (the memory row and the voice-path notes) and its
  Archify diagram **only if** the diagram text mentions what changed (validate, then deliver);
  `docs/roadmap/cognitive-roadmap.md` (the transversal follow-ups the plan closes).
- [ ] `docs/plans/README.md`, `docs/plans/open/README.md`, `docs/plans/completed/README.md`, the
  local table (never committed); move this plan to `completed/` with its execution record.
- [ ] `uv run ruff format --check .`, `uv run python scripts/check_reserved_terms.py`, and a check
  that every relative link of the touched `.md` files resolves; commit `docs: close plan 0064`;
  open the PR; merge only with Pipec's go-ahead.

## Review record

**Independent review, 2026-10-16.** Two read-only reviewers that had not written the plan checked
every citation against the code and simulated the Task 3 table on the real module (10 of 10
accepted, 9 of 9 refused, 0 of 64 fixtures changed). Their findings, all folded in above:
the language test and the rule disagreed on «tuteo» (Task 2); the persona mapping produced the
word `vos` that the guard forbids (Task 1); the claim lexicon was under-specified and would have
broken `test_generic_turn_continuity.py` (Task 4a); the voseo inventory was incomplete
(`characters/__init__.py`, `llm.py`, more verbs) and one test was missing (`test_perception.py:57`);
the stream guard needed one place and a collapse across deltas (Task 4c); the replacement phrase
could be false (D-5); the language gate did not discriminate (D-4); the start-up probe would have
reached the network from the lifespan tests (Task 6); the code of Plan 0063 is not in `main`
until its PR merges (Task 0, Step 0b); Tasks 1 and 2 had to be swapped so the prompt never
contradicts itself; Task 4 was split into four commits.

## Completion criteria

1. Tasks 0 to 8 done, one commit per task, every code test RED before GREEN.
2. `just gate` green with the baseline plus the new tests.
3. No fixed spoken string, persona prompt or fallback phrase uses voseo (the guard test), and the
   master prompt and the streaming contract ask for Spanish.
4. A model reply cannot claim to have saved (unit, classic and stream tests), the deterministic
   results of Plan 0063 are unchanged on the wire, and `test_generic_turn_continuity.py` is
   untouched and green.
5. The answer forms of D-3 parse and the refusals stay refused (the table of Task 3).
6. The language measurement of Task 7 is recorded against D-4.

## Rollback boundary

Each task is one commit. Task 2 (the language rule) and Task 1 (tuteo) should be reverted
together or Task 2 alone: reverting Task 1 alone would leave the persona asking for «vos» next to
a rule that asks for «tú». The other tasks are independent. Nothing is stored differently, no
setting or migration is added.

## Not here, and why

- **Translating the English prompt blocks** (D-7), **an Ollama field in `/health`**, and
  **warming the model at start-up** (the memory pressure that caused the cold-start failure is a
  hardware budget question, PC-5).
- **Conversational face enrolment** (`perception.enroll_from_frame`, not wired today): when it is
  reconnected (P1.2) its truthful «ya aprendí tu cara» must be exempted from the guard.
- **Idioms** (modismos) in the persona: a later, separate addition (D-1).
- **Widening the answer further** (more openers, other verbs): measured on hardware first.
- **The model-based emotion classifier, the robot's facial `expression`, and the end-to-end rate**
  of the stream: conditional on the larger model, the physical face and PC-5.
- **Case 9 (replay) and the homelab runs**: they need a second person or the homelab.

## Execution record

*(Filled in when the plan is executed.)*
