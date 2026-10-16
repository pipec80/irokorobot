# 0064 — Speech and dialogue quality: Spanish, tuteo, no false «guardé», a forgiving answer

> **Status:** `Draft` — written 2026-10-16 from the audit of the three items before Step 0
> (streaming repair, CM-1 remainder, CM-3b) and from the findings of the Plan 0063 hardware
> acceptance. Pipec decided D-1, D-2 and D-3 on 2026-10-16; D-4 to D-8 are the plan's and wait for
> his confirmation when he promotes it. **Not rehearsed** in a scratch copy: the code below is the
> specification of each task, not a rehearsed diff. It is not executable until Pipec marks it
> `Ready` and `NOW`; to be executed in a **new session**.

> **For agentic workers:** if the status above does not say `Ready`, stop: Pipec has not promoted
> this plan. REQUIRED SUB-SKILLS: `superpowers:executing-plans`,
> `superpowers:test-driven-development`, `superpowers:verification-before-completion`,
> `superpowers:finishing-a-development-branch`. **Pipec's rules win over the skills:** one plain
> branch from `main` (`git checkout -b`), never a git worktree, subagents only if Pipec asks, and
> this plan lives under `docs/plans/`. Implement exactly the tasks below, in order, one commit per
> task, each test observed RED for the stated reason first. If evidence contradicts the plan,
> stop and report the conflict instead of redesigning. Pipec runs every local process (server,
> robot, Ollama, anything that uses the camera or the microphone); record outcomes only, never a
> sentence, a value or a name. The Bash tool of this environment loses backslashes and non-ASCII
> characters in heredocs: create and edit files with the Write and Edit tools. Run the suite with
> `MEMORY_ENABLED=false` (CI does). **Dates:** a test that builds data at a fixed date must also
> pin the clock (`clock=lambda: ...`); Plan 0063 shipped a test that broke the next day.

**Goal:** What Iroko says sounds like one voice and tells the truth about memory. Every spoken
string and every persona prompt uses neutral Spanish with **tuteo** (Pipec lives in Santiago de
Chile; idioms may come later); the streaming contract asks for Spanish like the classic contract
does; a model reply never claims to have saved, registered or noted anything (nothing is stored
by the model: the only save is the deterministic one of Plan 0063); the explicit answer to a
memory offer survives the way Whisper `small` actually writes it («autoriza a guardar mi café»,
«sí po, autorizo…»); and the stale prose and the missing start-up signal found by the audit are
fixed. No wire change, no migration, no new route.

**Architecture:** Five small, independent changes behind one plan.
(1) One sentence in `_STREAMING_OUTPUT_CONTRACT`. (2) A tuteo pass over the two personas, the
fixed controller strings, the perception templates and the fallback/look phrases, plus a guard
test that no fixed string uses voseo (the *recognition* lexicons keep accepting voseo input).
(3) A pure module `cognition/claim_guard.py` with `neutralize_memory_claims(text)`, applied to
model-generated text only: the classic reply in `text_turn` and each model sentence in the
stream's `_consume_body` and tail; the deterministic phrases never pass through it. One extra line
in `_MEMORY_DISCIPLINE`. (4) The answer grammar in `intent_resolution` accepts the third-person
form of the verbs, the Chilean openers and a trailing «po», and a leading «mi» in the value.
(5) A start-up probe that only warns when Ollama is unreachable, and the removal of stale prose.

**Tech Stack:** Python 3.12, FastAPI, pytest. No new dependency.

**Spec:** [ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md) decision 9 (the
answer grammar, amended by this plan with Pipec's decision D-3 of 2026-10-16),
[ADR 0018](../../adr/0018-user-emotion-decided-apart.md) (the streaming contract is plain text and
names no tag), the acceptance note
[`0063-memory-dialogue-acceptance.md`](../../evals/0063-memory-dialogue-acceptance.md) (the
findings this plan closes) and
[`.claude/rules/python-style.md`](../../../.claude/rules/python-style.md).

## Global Constraints

- No real household data in any tracked file, test, prompt, doc or commit message: invented
  canaries only (`scripts/check_reserved_terms.py` guards it).
- Every new spoken phrase is neutral Spanish with tuteo (D-1). A *recognition* lexicon (what the
  robot accepts as input: `intent_resolution`, `memory/lexicon`) keeps voseo forms on purpose.
- The guard of Task 4 touches **model-generated** text only. The deterministic results of
  Plan 0063 («Listo, lo guardé.», «Está bien, no lo guardo.», the offer, the failure phrase) must
  reach the wire byte for byte (a test pins it).
- A fall-through (the ordinary turn, ADR 0021 decision 9) stays indistinguishable from any other
  ordinary turn except that a model sentence which claims a memory action is replaced.
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
   2026-10-16, his acceptance of the recommendation).** The prompt line is support (a small model
   may ignore it); the guard is what the tests pin.
3. **D-3 — The explicit answer admits the speech-to-text's usual writings (Pipec, 2026-10-16).**
   The value stays mandatory and the short verbs keep their article rule. Accepted: `autoriza`,
   `aprueba` (alone, or followed by `guardar`, `a guardar` or `que guardes`) and their `no`
   forms; the openers `ya`, `dale`, `po`; a trailing `po`; one leading `mi` before the value.
4. **D-4 — The language gate (plan default, Pipec ratifies).** What "fixed" means is a number
   agreed before measuring: in two runs of `just eval-chat --provider ollama --mode stream` the
   column *Not in Spanish* is at most 2 % of the replies, and in Pipec's first 20 hardware turns
   after the change none is in another language. It is reported, not enforced by a CI test (it
   needs a real model); a miss is a finding, not a redesign.
5. **D-5 — The replacement sentence** for a model sentence that claims a memory action is
   «Todavía no he guardado nada.» (true on that turn: only a promotion stores a fact).
6. **D-6 — The Ollama probe only warns.** One short `GET /api/tags` at start-up; on failure a
   warning with the class, never an exception, never a delay beyond its timeout. No `/health`
   field (that is a separate, additive decision).
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
- `server/src/server/{llm_streaming,llm,text_turn,streaming,streaming_render,settings,main}.py`,
  `server/src/server/cognition/{controller,intent_resolution}.py`,
  `server/src/server/characters/{__init__,iroko,nova}.py` and `profiles/ejemplo_vendedor.md`,
  `server/src/server/vision/perception.py`, `scripts/{reply_language,stream_diagnosis_report}.py`.
- The tests named in each task.

## Permitted files

- Production: `server/src/server/{llm_streaming,text_turn,streaming_render,settings,main}.py`,
  `server/src/server/cognition/{controller,intent_resolution}.py`, new
  `server/src/server/cognition/claim_guard.py`, `server/src/server/characters/{__init__,iroko,nova}.py`,
  `server/src/server/characters/profiles/ejemplo_vendedor.md`,
  `server/src/server/vision/perception.py`.
- Other: `.env.example`, `justfile` (one comment), `scripts/stream_diagnosis_report.py`.
- Tests: those named in each task and their new files.
- Docs (Task 8): ADR 0021 (amendment), `docs/runbooks/operator-manual.md`,
  `docs/architecture/current-state.md`, the plan index files and this plan.

No new URL, field, migration, setting or dependency. The robot (`robot/src`) is not edited.

---

## Task 0: Revalidate the baseline

- [ ] **Step 0: Status.** This plan says `Ready`; otherwise stop.
- [ ] **Step 1: Branch.** `git checkout main && git pull`, clean tree, then
  `git checkout -b feat/0064-speech-and-dialogue-quality`; record the base SHA.
- [ ] **Step 2: Baseline.** `just gate`; record the outcome and test count (3217 at the close of
  Plan 0063, on `main` after its merge). A pre-existing failure is reported, not hidden.
- [ ] **Step 3: Re-audit.** Each of these must find what this plan names:
  `rg -n "_STREAMING_OUTPUT_CONTRACT" server/src`, `rg -n "Hablás siempre" server/src`,
  `rg -n "def parse_memory_answer" server/src`, `rg -n "_MEMORY_DISCIPLINE" server/src`,
  `rg -n "llm_fallback_phrase" server/src .env.example`. A difference is reported before code.

## Task 1: The streaming contract asks for Spanish

**Files:** modify `server/src/server/llm_streaming.py`; test modified
`tests/unit/test_llm_streaming.py`.

- [ ] **Step 1: Failing test.** In `tests/unit/test_llm_streaming.py` (it already checks that the
  contract says «texto plano» and names no tag), add a test that the system prompt built by
  `_streaming_system_prompt("...")` contains the sentence `Responde siempre en español.` and still
  names no tag. Expected RED: `AssertionError` (the sentence is absent).
- [ ] **Step 2: Implement.** Extend `_STREAMING_OUTPUT_CONTRACT` to
  `"\n\nResponde únicamente en texto plano, siempre en español: sin JSON, sin etiquetas, sin listas ni formato. Escribe solo lo que dirías en voz alta."`
  and make the test match the exact phrase (`siempre en español`). Keep the comment that the
  contract names no tag (ADR 0018).
- [ ] **Step 3:** run `tests/unit/test_llm_streaming.py tests/unit/test_stream_diagnosis_variants.py`
  (the second one uses the contract as text); lint and types over the files.
- [ ] **Step 4: Commit** `feat(server): ask the streaming reply for Spanish (plan 0064)`.

## Task 2: One dialect, tuteo, everywhere the robot speaks

**Files:** modify `server/src/server/characters/{iroko,nova}.py`,
`server/src/server/characters/profiles/ejemplo_vendedor.md`,
`server/src/server/cognition/controller.py`, `server/src/server/vision/perception.py`,
`server/src/server/settings.py`, `.env.example`; tests modified (see Step 3) and new
`tests/unit/test_no_voseo_in_spoken_strings.py`.

**The mapping** (tuteo, neutral): `Sos` → `Eres`; `Tenés` → `Tienes`; `preguntás` → `preguntas`;
`sos` → `eres`; `volvé a hablarme` → `vuelve a hablarme`; `dejame mirar` → `déjame mirar`;
`Hablás siempre de "vos" (nunca "tú")` → `Hablas siempre de "tú" (nunca "vos")`; the persona
verbs in voseo (`conocés`, `Conservás`, `tenés permitido`, `soltás`, `ejecutás`, `actuás`,
`suplantás`, `explicalo`, `redirigí`, `Presentate`, `cubrilo`, `compartís`, `tratás`, `podés`,
`revelás`, `Reconocés`, `saludá`, `Pedile`, `Confirmáselo`, `Acabás`) to their `tú` forms; the
pronoun `vos` → `ti`/`tú` as the sentence needs.

- [ ] **Step 1: The guard test first.** New `tests/unit/test_no_voseo_in_spoken_strings.py`:
  walk `server/src/server/**/*.py` and the persona `.md` profiles, and fail on a word of the
  closed list `{sos, tenés, querés, podés, sabés, preguntás, volvé, dejame, decime, mirá, vení,
  hablás, vos, contame, acordás, pensás, necesitás, ayudá, ayudame, escuchá, esperá, fijate,
  avisame, conocés, conservás, soltás, ejecutás, actuás, suplantás, explicalo, redirigí,
  presentate, cubrilo, compartís, tratás, revelás, reconocés, saludá, pedile, confirmáselo,
  acabás}` (case-insensitive, whole word, accents as written) **outside** an allowlist of the
  *recognition* lexicons: `cognition/intent_resolution.py` and `memory/lexicon.py` (they accept
  voseo input on purpose). Add a second test that the allowlist files still contain at least one
  such word (so the allowlist cannot silently go stale). Expected RED: the first test fails
  listing the files and words found today (the personas, `controller.py`, `perception.py`,
  `settings.py`).
- [ ] **Step 2: Implement** the mapping in the files above. Keep every sentence's meaning and the
  persona's character; only the dialect changes. `settings.llm_fallback_phrase` becomes
  `"Uy, mi cerebro todavía se está despertando. Dame unos segundos y vuelve a hablarme."` and the
  same line in `.env.example`; `vision_look_phrase` becomes `"A ver, déjame mirar..."`. Check
  whether Pipec's own `.env` redefines either phrase and say so in the execution record (do not
  edit `.env`).
- [ ] **Step 3: Update the tests that pin the old strings** (found by
  `rg -n "Sos |Tenés|preguntás|volvé|dejame|quién sos" tests`): `test_chat_endpoint.py:343`,
  `test_cognitive_controller.py:219,338,575,589,607`, `test_owner_authenticated_turn.py:336`,
  `test_owner_authenticated_stream.py:287`, `test_owner_stranger_matrix.py:324`,
  `test_transcribe_pipeline.py:126,132,182`, `test_transcribe_stream.py:381,530`,
  `test_vision_dialog.py:292` to the new strings («Todavía no puedo confirmar quién eres.»,
  «Eres Ada.», «Tienes 2 hijos.», «No entendí si preguntas por la fecha actual o por información
  personal. …»). Fixtures that only use «Sos …» as sample text
  (`test_character_registry.py`, `test_character_parser.py`, `test_llm_streaming.py:79`) are not
  spoken strings: leave them.
- [ ] **Step 4:** run the whole touched set, then `uv run pytest tests/unit tests/integration -q
  -p no:cacheprovider -n auto` once; lint and types.
- [ ] **Step 5: Commit** `feat(server): speak in neutral tuteo everywhere (plan 0064)`.

## Task 3: The explicit answer survives the speech-to-text

**Files:** modify `server/src/server/cognition/intent_resolution.py`; tests modified
`tests/unit/test_memory_answer_grammar.py`.

- [ ] **Step 1: Failing tests** (parametrized; each case is `message → (accept, phrase)` or
  `None`). Accepted, after this task:
  `«Sí, autoriza a guardar mi café»` → `(True, "cafe")`;
  `«Autoriza guardar el mate»` → `(True, "el mate")`;
  `«Ya, autorizo guardar el mate»` → `(True, "el mate")`;
  `«Sí po, autorizo guardar el mate»` → `(True, "el mate")`;
  `«Dale, autorizo guardar el mate»` → `(True, "el mate")`;
  `«Autorizo guardar el mate po»` → `(True, "el mate")`;
  `«Aprueba guardar las empanadas»` → `(True, "las empanadas")`;
  `«No autoriza guardar el jazz»` → `(False, "el jazz")`;
  `«No, no autoriza a guardar mi jazz»` → `(False, "jazz")`;
  `«Guarda mi café»` → `(True, "cafe")` (the short verb is satisfied by «mi»).
  Still refused (must stay `None`): `«Autoriza»`, `«Sí po»`, `«Ya»`, `«Dale»`,
  `«Guarda silencio»`, `«Guarda mi»`, `«Ya, guarda silencio»`, `«Autorizo guardar»`,
  `«Autoriza guardar el mate de la abuela de mi vecino de al lado»` (a value of more than six words).
  Folding (accents, case) is done by `normalize_spanish`; write the expected phrases as the
  grammar returns them today (folded, article kept when present).
  Expected RED: the accepted cases fail with `assert None == MemoryAnswer(...)`.
- [ ] **Step 2: Implement** in `intent_resolution.py`: add `"ya"`, `"dale"`, `"po"` to
  `_ANSWER_OPENERS`; add `"po"` to `_ANSWER_TRAILERS` (the trailing-word loop already strips it
  repeatedly); add the third-person prefixes after the first-person ones **in each tuple, longest
  first** («autoriza que guardes», «aprueba que guardes», «autoriza a guardar», «aprueba a
  guardar», «autoriza guardar», «aprueba guardar», «autoriza», «aprueba») and the `no` forms
  («no autoriza …», «no aprueba …»); in `_answer`, drop **one** leading `mi` from the value and
  treat it as the article for the short verbs. Keep every other rule (article for the short verbs,
  at most six words, no value starting with «guardar» or «que»). Update the module comment and the
  `parse_memory_answer` docstring; the openers are only skipped, so an opener alone still matches
  nothing.
- [ ] **Step 3: The round trip still holds.** `tests/integration/test_candidate_dialogue.py`
  already asserts that the words the offer asks for resolve the offer; run it. Add one test that a
  value stored without a determiner resolves from «autoriza a guardar mi {x}».
- [ ] **Step 4:** run `tests/unit/test_memory_answer_grammar.py tests/unit/test_intent_resolution.py
  tests/integration/test_candidate_dialogue.py tests/integration/test_memory_dialogue_routes.py`;
  lint and types.
- [ ] **Step 5: Commit** `feat(server): accept how Whisper writes the memory answer (plan 0064)`.

## Task 4: A model reply never claims to have saved

**Files:** new `server/src/server/cognition/claim_guard.py`; modify
`server/src/server/text_turn.py`, `server/src/server/streaming_render.py` (and the one
call site in `server/src/server/streaming.py` only if the tail goes through it),
`server/src/server/characters/__init__.py`; tests new `tests/unit/test_claim_guard.py`, modified
`tests/unit/test_text_turn.py`, `tests/integration/test_transcribe_stream.py` (or
`test_stream_offer.py`'s fixtures) and `tests/integration/test_memory_dialogue_routes.py`.

**Interface.** `claim_guard.REPLACEMENT = "Todavía no he guardado nada."`;
`claims_memory_action(sentence: str) -> bool` (pure); `neutralize_memory_claims(text: str) ->
str`, which splits the text into sentences with `server.sentences.split_first_sentence`, replaces
each claiming sentence by `REPLACEMENT` and collapses consecutive replacements into one.

**What counts as a claim** (the closed lexicon, matched on `normalize_spanish` text, one
sentence at a time, first person or a passive/participle about the thing said): the forms of
`guardar`, `registrar`, `anotar`, `apuntar`, `memorizar`, `almacenar` in the preterite or present
of the speaker («lo guardé», «guardo eso», «lo registré», «anoté tu gusto», «lo anoto»), the
future («lo recordaré», «lo guardaré», «me acordaré»), and the participle as a state («queda
guardado», «está registrado», «ya está anotado», «ha sido guardado», «lo tengo guardado»).
**Not** a claim: a negation in the same sentence («no lo guardo», «no he guardado nada»), a
question («¿quieres que lo guarde?»), the infinitive or an unrelated use («puedo guardar
silencio», «guarda tus llaves», «guardar las apariencias»), and any sentence without the lexicon.

- [ ] **Step 1: Failing tests** `tests/unit/test_claim_guard.py`: a table of ≥ 12 claiming
  sentences (including the real ones from the 0063 acceptance, written as invented equivalents:
  «El café siempre será guardado.», «El café está registrado.», «¡Perfecto! Lo guardé.») → `True`,
  a table of ≥ 12 non-claims → `False`, and `neutralize_memory_claims` on a three-sentence reply
  with one claim (keeps the other two byte for byte, replaces the claim once), on a reply that is
  all claims (one `REPLACEMENT`), and on an empty or claim-free reply (returned unchanged).
  Expected RED: `ModuleNotFoundError: server.cognition.claim_guard`.
- [ ] **Step 2: Implement** the module (pure, no I/O, no logging of the text). It imports only
  `server.sentences` and `server.cognition.intent_resolution.normalize_spanish`.
- [ ] **Step 3: Failing wiring tests.** (a) `test_text_turn.py`: with `llm.generate_response`
  returning «Perfecto, lo guardé.» the `TextTurnResult.response` is `REPLACEMENT`; with a plain
  reply it is unchanged; with the fallback phrase it is unchanged. (b) the stream: a model
  stream whose second sentence claims a save speaks `REPLACEMENT` in its place (one `audio`
  event with that text), the other sentences are unchanged, `done` still ends the stream, and the
  spoken-text log and the history carry the replaced text. (c) the deterministic results of
  Plan 0063 are byte for byte: the existing answer and offer tests must stay green unchanged.
  Expected RED: the claim reaches the response/the event.
- [ ] **Step 4: Wire.** Classic: in `text_turn._generate` (or just after it, before the reply is
  recorded in the session) apply `neutralize_memory_claims` when the reply is a model answer
  (`llm_failed` false). Stream: in `streaming_render._consume_body` replace a claiming sentence
  before it is appended (after `reject_embedded_tag`), and apply the same to the final tail in
  `_finalize_model_output`. Do not touch `emit_fallback`, the offer, or any deterministic plan.
- [ ] **Step 5: The prompt line.** Add to `_MEMORY_DISCIPLINE` (English, like the block): «You do
  NOT store anything yourself: never say you saved, registered or noted something. Only the
  robot's own spoken offer saves, and only after the person agrees.» A test pins that the line is
  in the prompt built by `build_system_prompt`. (It is support; the guard is the guarantee.)
- [ ] **Step 6:** run the touched tests, then the full suite once; lint and types.
- [ ] **Step 7: Commit** `feat(server): never let the model claim it saved (plan 0064)`.

## Task 5: Stale prose

**Files:** `scripts/stream_diagnosis_report.py`, `justfile` (one comment),
`docs/runbooks/operator-manual.md` (Task 8 edits the same file; do this one there).

- [ ] **Step 1:** `justfile:125` says `eval-chat` measures, with `--mode stream`, «el protocolo
  EMOTION: del streaming»: the stream is plain text since Plan 0059. Rewrite the comment (Spanish,
  ASCII-safe like its neighbours) to say it measures the stream's plain-text contract and the
  reply language.
- [ ] **Step 2:** `scripts/stream_diagnosis_report.py` (about lines 291 to 317 and 353 to 354)
  still argues about «the `llm_streaming.py` claim that Ollama withholds» a schema-constrained
  reply. Read `llm_streaming.py`'s header; if the claim is gone from the code, rewrite those
  sentences as a statement of what the probe measures, without referring to a claim that no longer
  exists. Do **not** change any computed value or verdict. Run
  `tests/unit/test_stream_diagnosis_report.py` (it may pin phrases: update them in the same
  commit) and lint `scripts/stream_diagnosis_report.py` with explicit paths (`scripts/` is
  excluded from `ruff check .`).
- [ ] **Step 3: Commit** `docs(scripts): drop the stale streaming-protocol prose (plan 0064)`.

## Task 6: Say so when Ollama is down at start-up

**Files:** modify `server/src/server/main.py`; test new `tests/unit/test_ollama_probe.py` (or
the existing lifespan test file).

- [ ] **Step 1: Failing test.** A function `probe_ollama(client)` (in `llm_transport.py` or next
  to the lifespan) that does one `GET {ollama_url}/api/tags` with a 3 s timeout and returns
  `True`/`False`; on `False` it logs a warning with the exception class only (no URL path
  beyond the host, no response body). Tests with `httpx.MockTransport`: 200 → `True` and no
  warning; connection error and 500 → `False` and exactly one warning that names the class.
  Expected RED: `ImportError`.
- [ ] **Step 2: Implement** and call it once in the lifespan after the models load; the result
  never stops the start and never changes `/health`. Do not call it when `settings.llm_provider`
  is not `ollama` (it always is today). One sentence in the operator manual (Task 8): warm the
  model with one ordinary sentence after the start.
- [ ] **Step 3:** lifespan tests still green; lint and types. **Step 4: Commit**
  `feat(server): warn at start-up when Ollama is unreachable (plan 0064)`.

## Task 7: Measure the language (a measurement, not a test)

- [ ] **Step 1:** with Pipec's Ollama running, `just eval-chat --provider ollama --mode stream`
  twice (the command has no seed argument); record, for each run, the *Not in Spanish* count
  and its share of the replies. No sentence is recorded.
- [ ] **Step 2:** ask Pipec to hold a short conversation of at least 20 turns by voice and report
  how many replies were not Spanish (a count, nothing else).
- [ ] **Step 3:** compare with D-4 and write both numbers in the execution record. If the gate is
  missed, **stop and report**: the next candidate is the translation of the English prompt blocks
  (D-7), which is a new plan.

## Task 8: Documentation truth

- [ ] ADR 0021 decision 9: amend the answer-grammar bullet (the verbs of D-3, the openers, the
  trailing «po», the leading «mi») and add a dated line to its status («amended 2026-10-xx by
  Plan 0064»); the *Acceptance* case 6 wording is unchanged.
- [ ] `docs/runbooks/operator-manual.md`: the answer forms, that the robot never claims to have
  saved (and what it says instead), tuteo, the Ollama start-up warning and the warm-up advice,
  and the stale prose of Task 5 if it lives there.
- [ ] `docs/architecture/current-state.md` (the memory row and the voice-path notes) and its
  Archify diagram **only if** the diagram text mentions what changed (validate, then deliver).
- [ ] `docs/plans/README.md`, `docs/plans/open/README.md`, `docs/plans/completed/README.md`,
  `docs/roadmap/cognitive-roadmap.md` (the transversal follow-ups the plan closes), the local
  table (never committed); move this plan to `completed/` with its execution record.
- [ ] `uv run ruff format --check .`, `uv run python scripts/check_reserved_terms.py`, and a check
  that every relative link of the touched `.md` files resolves; commit `docs: close plan 0064`;
  open the PR; merge only with Pipec's go-ahead.

## Completion criteria

1. Tasks 0 to 8 done, one commit per task, every test RED before GREEN.
2. `just gate` green with the baseline plus the new tests.
3. No fixed spoken string, persona prompt or fallback phrase uses voseo (the guard test), and the
   streaming contract asks for Spanish.
4. A model reply cannot claim to have saved (unit, classic and stream tests), and the
   deterministic results of Plan 0063 are unchanged on the wire.
5. The answer forms of D-3 parse and the refusals stay refused (the table of Task 3).
6. The language measurement of Task 7 is recorded against D-4.

## Rollback boundary

Each task is one commit and independent: reverting one restores the previous behaviour. Nothing
is stored differently, no setting or migration is added. The persona rewrite (Task 2) changes how
the model speaks; if Pipec dislikes a persona, only those two files revert.

## Not here, and why

- **Translating the English prompt blocks** (D-7), **an Ollama field in `/health`**, and
  **warming the model at start-up** (the memory pressure that caused the cold-start failure is a
  hardware budget question, PC-5).
- **Idioms** (modismos) in the persona: a later, separate addition (D-1).
- **Widening the answer further** (more openers, other verbs): measured on hardware first.
- **The model-based emotion classifier, the robot's facial `expression`, and the end-to-end rate**
  of the stream: conditional on the larger model, the physical face and PC-5.
- **Case 9 (replay) and the homelab runs**: they need a second person or the homelab.

## Execution record

*(Filled in when the plan is executed.)*
