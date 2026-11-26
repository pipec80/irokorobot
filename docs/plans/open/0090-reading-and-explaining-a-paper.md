# 0090 — Reading and explaining a paper

> **Status:** **`Ready`** (2026-11-25, approved by Pipec). Pipec answered D-1 to D-7 the same day,
> every recommendation accepted (see *Pipec's decisions* at the end). **Scope amended 2026-11-26**
> by Pipec for the laptop's limits (see *Scope amendment of 2026-11-26*): Task 1 becomes an
> isolated OCR probe with three photographs and Task 9 four steps on the streaming route; what is
> left out is listed with its trigger. Execution runs in a new session, on its own branch.
>
> **Source:** row **9a** of the
> [path to the finish line](../../roadmap/cognitive-roadmap.md#closing-path-of-conversational-memory),
> Pipec's first need of vision (2026-11-24, option B), recorded in Plan 0089's *Deferred* section
> and its *second round*. Written with Plan 0089's [bench](../../evals/0089-vlm-bench.md) and its
> [closing record](../../evals/0089-streaming-scene-acceptance.md). Goes before row 9b (R2b), which
> reuses the same reading. Takes **ADR 0041** (D-7). One plain branch from `main`
> (`feat/0090-read-and-explain-a-paper`), one PR.
>
> **What Pipec decided (2026-11-24, option B).** The robot reads the paper as today («lee esto»).
> Then, to a question («¿cuánto tengo que pagar?», «¿para cuándo es?»), it answers only from what
> it read, saying it comes from the paper, or says the answer is not in it.
> - The read text lives only in that conversation's short term (deleted by another person or
>   180 s of silence, as ADR 0020's session). It is kept as a document only after «sí, guárdalo».
> - With nobody identified it reads aloud but answers no question about the paper.
> - The paper is data, never an order. A medical letter is read, never interpreted.

> **For agentic workers:** if the status above does not say `Ready`, stop. Read `CLAUDE.md`,
> `AGENTS.md` and every file of `.claude/rules/` in full first. REQUIRED SUB-SKILLS:
> `superpowers:executing-plans`, `superpowers:test-driven-development` for every task,
> `superpowers:verification-before-completion` before any claim of done,
> `superpowers:requesting-code-review` and `superpowers:receiving-code-review` for Task 8, and
> `superpowers:finishing-a-development-branch` at the end. Review agents run on `sonnet` and read
> `.claude/` in full before reading code. **Pipec's rules win over the skills:** one plain branch
> from `main`, never a git worktree. One commit per task; every test seen RED for the stated reason
> first. If evidence contradicts the plan, stop and report; **a discovery this plan's goal does not
> need is recorded, not built.** The Bash tool loses backslashes and non-ASCII characters in
> heredocs: use the Write and Edit tools. Commit titles: Conventional Commits, at most 72
> characters, check `git log` after each commit; never pipe `git commit`; `git add` with explicit
> paths. Run the suite with `MEMORY_ENABLED=false` as CI does. Never `uv sync` without
> `--extra cuda`. No `just gate` or full suite in the background while Pipec rehearses (15.7 GB of
> RAM). Pipec starts the server and the robot. Before pushing: `pyright`, `ruff` and `mypy` over the
> whole project, `uv run ruff format --check .`, and `ruff` with explicit paths over any file under
> `scripts/`. A new runtime dependency follows Pipec's rule for model runtimes: measured first in a
> separate environment, never by trying it in the real `.venv`.

## Required reading

[Implementation guardrails](../../architecture/implementation-guardrails.md);
[ADR 0034](../../adr/0034-documents-and-reading-through-the-camera.md) (decision 5 and its
deviations 3, 5, 9 and 11); [ADR 0020](../../adr/0020-authorized-actor-in-the-conversation.md)
(the short-term session); [ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md)
(the closed «sí, guárdalo» dialogue and its 60 s window); the
[Plan 0089 bench](../../evals/0089-vlm-bench.md); ADR 0041 once Task 2 writes it.

## What the code does today (verified 2026-11-25 on `docs/0089-close` at `b4dcb40`, Plan 0089 merged)

Re-verify each item on `main` in Task 0; **stop and report** if one is false.

1. **The reading is one closed branch.** `cognition/document_cues.py` `_READING` hears «lee
   esto», «léeme esto», «lee lo que dice», «¿qué dice aquí / acá?» (and Plan 0089 D-10's shapes);
   `CognitiveController._read_text_plan` calls the per-request `_text_reader` seam
   (`routers/transcribe.py`), once per event, on both voice routes. It needs `MEMORY_ENABLED`,
   `DOCUMENTS_ENABLED`, `VISION_ENABLED` and `FACE_AUTHENTICATION_ENABLED` (`_reading_on()`).
2. **The reader is the VLM.** `vision/read_text.py` `read_text` sends the turn's frame with one
   fixed prompt («Escribe exactamente el texto que se ve…») to `settings.vlm_model`
   (`qwen3-vl:2b-instruct`), temperature 0. On the laptop it costs **70 to 120 s** per frame: ~1100
   image tokens evaluated on the CPU, because the 1.9 GiB model never fits the 2 GiB GPU beside
   Ollama's 457 MiB floor; the frame's size changes nothing (bench, run 2). It read the printed
   canary card 9 of 9 and a phone screen 7 of 7 whenever it finished; the bill and handwriting were
   **never reached** (every such cell stopped at an earlier timeout).
3. **What is spoken is capped, and so is what is held.** `_cap_reading` flattens the text and cuts
   it to `_MAX_READING_CHARS = 400` (about 25 s of speech) **before** the secret check and before
   it is offered: the text kept by «sí, guárdalo» is the capped one, not the whole read.
4. **The read text waits 60 s, for one turn only.** `memory/reading_offer.py` `READING_SLOT` holds
   the last reading bound to the speaker identified on the reading turn (`peek_actor`), or to
   nobody; `OFFER_WINDOW` is 60 s. `_reading_keeper` runs on **every** turn first
   (`_kept_reading`) and empties the slot unless that turn is «sí, guárdalo» from the same
   identified speaker. So today any question after a reading erases it.
5. **A reading leaves no text behind.** The turn is recorded with the marker «[texto leído por la
   cámara]» (`READING_RECORDED_TEXT`, ADR 0034 deviation 5); it never enters the conversation
   record, the diary, a recall unit, an export or the ADR 0020 continuity slot.
6. **The short-term session is generic-only.** `memory/continuity.py` `ContinuitySession` holds the
   identified person's last exchanges, dropped after `WORKING_MEMORY_IDLE_SECONDS` (180) of
   silence, replaced by another identified person, suspended by an unknown or ambiguous turn,
   forgotten on restart. Only generic turns read and write it, and it feeds the generic prompt,
   which **reads no household store** (guardrails, Plan 0077).
7. **A document answer quotes; no model words it.** `memory/document_answer.py` `word_document`
   picks at most two sentences holding the most question words, drops every sentence in the closed
   shapes of an order (`gives_an_order`) and every one the secret detector flags (`flags_secret`),
   caps at 220 characters (`MAX_ANSWER_CHARS`), and says «Según {título}: …» or «No lo encuentro
   en tus documentos.». Reason (ADR 0034 deviation 9): on the bench the 3B obeyed a planted order in
   12 of 24 answers.
8. **Fixed phrases** (`cognition/response_plan.py`): `READ_OFFER` «¿Lo guardo? Dime: sí,
   guárdalo.», `READING_KEPT`, `NOTHING_TO_READ`, `COULD_NOT_READ`, `READ_SECRET`.
9. **Runtimes already installed** (`uv.lock`): `onnxruntime` 1.32.0 (the face model), `torch`
   2.15.0 (the speaker model), `opencv-python` 5.1, `pillow` 13.0. No OCR package.

## Scope amendment of 2026-11-26 (Pipec)

**Why.** The laptop cannot run every model at once (Whisper, the 3B, the 4B, the VLM and the
embeddings share 15.7 GB and a 2 GiB GPU), and a parallel audit
(`docs/architecture/model-candidates.md`) is weighing fewer models. Measuring vision again and
again on a machine known to be short would never end. Pipec's goal for this plan: the robot reads
a printed paper, tries a handwritten one, and *understands something* (answers from it). The
approach is the one Pipec used when building the pipeline: prove each piece alone, in its own
script, then wire it. A dedicated OCR is not an Ollama model (a few MB on the installed ONNX
Runtime, about 1 s per image in third-party benchmarks), so a result measured alone holds when
everything is on; its contention with the other models is measured on the home server (PC-5).

**The plan's points, and what this amendment does with each** (✅ done as written · ✂️ reduced ·
❌ left out, with its trigger in *Deferred*):

| # | Point of the plan as written on 2026-11-25 | Why it was there | Now | What changes, and why |
|---|---|---|---|---|
| T0 | Re-audit `main` and take a baseline | Never build on code that changed | ✅ | — |
| D-1 / T1 | **Reader bench:** 2 or 3 OCR engines (RapidOCR, Tesseract, EasyOCR or docTR) against the VLM, about 8 photographs (card, screen, bill, marker, ballpoint, blue ink, graphite, handwritten prescription), the server loaded (latency, RSS, free RAM) | Choose the reader with numbers: the VLM takes 70 to 120 s | ✂️ | **One OCR (RapidOCR), an isolated script, the server off, 3 photographs:** a printed invented bill, a note in blue ballpoint, a note in graphite, each as taken and with its contrast raised. Tesseract only as the reserve if RapidOCR fails on print |
| T1 | The VLM on every photograph | Know whether the OCR beats it | ❌ | Plan 0089 measured it: right on print, 70 to 120 s per frame. Repeating it costs two minutes a photograph and teaches nothing new |
| T1 | The measurement with Whisper, the LLM and the rest loaded | Their fight for RAM | ❌ | The OCR is small and outside Ollama, so it evicts no model; the contention belongs to the home server (PC-5) |
| T1 | A handwritten prescription | The hardest real case | ❌ | No OCR reads a doctor's hand today; it goes to Pipec's real-world reading round |
| T1 | Read the licences before anything is used | Never AGPL or GPL | ✅ | RapidOCR's and its models' only (and Tesseract's if the reserve is used) |
| D-7 / T2 | ADR 0041 | The decision written down | ✅ | Shorter: one reader to record |
| T3 | The chosen reader behind the seam, and `READING_ENGINE` | Change the reader without touching the rest | ✅ | If RapidOCR passes, it is wired. If it does not, the VLM stays and no setting is built (nothing built that is not used) |
| — | Raising the contrast before reading (new, not in the plan) | Graphite and dim light | ✂️ | Enters only if the probe shows it helps |
| D-2 / T4 | **The paper's own slot:** the whole text, bound to who showed it, ended by another person or 180 s of silence | The heart of option B | ✅ | Needs no camera: tested on invented text |
| D-6 / T4 | «Sí, guárdalo» after several questions | The paper is not lost | ✅ | — |
| D-3 / D-4 / T5 | The closed questions, the quoted answer «Según el papel: …», the planted-order eval | The *understands something* | ✅ | All in tests over fixed text, no camera, in seconds |
| D-5 / T6 | The fixed phrase with nobody identified, and the one that declines to interpret | Privacy, no medical advice | ✅ | — |
| T7 | No paper text in a log, the record, the diary or an export | Privacy | ✅ | — |
| T8 | Verification and review | Definition of done | ✅ | `just gate` never while Pipec rehearses |
| T9 | **Hardware acceptance:** 6 steps on both routes | The real microphone and camera | ✂️ | **4 steps, the streaming route only** (production's): the bill read and two questions; «¿es grave?»; «sí, guárdalo»; the face out of view. The 180 s silence and the unrelated question are covered by tests with an injected clock |

**The ledger.** Of the 15 points the plan had, **11 stay whole, 2 are reduced (T1, T9) and 3 are
left out** (the VLM on every photograph, the loaded measurement, the prescription); one
conditional point is new (the contrast). This plan closes at 100 % of its amended scope; the three
left out, and the engines not tried, are the part of the original goal not done for the laptop's
limits, each with its trigger in *Deferred*, to be taken up when the server moves to its board or
a better OCR is weighed.

## Decisions (answered by Pipec on 2026-11-25; D-1 amended 2026-11-26)

### D-1. Who reads the paper: one OCR proved alone, then wired

Task 1 runs **RapidOCR** (PP-OCR models on the installed `onnxruntime`) in an isolated script on
the CPU, with the server off. If it reads the printed paper right, it becomes the reader behind
the existing `_text_reader` seam, named by a setting (`READING_ENGINE`, default `vlm`, so
`main`'s behaviour is unchanged until Pipec chooses); never a hidden fallback from one to the
other.

- **Licence** read in Task 1 before it is used (code and model weights); never AGPL or GPL, as ADR
  0034 decision 1. **Tesseract** with its Spanish model is the only reserve, tried only if
  RapidOCR fails on print.
- **Photographs** (invented canaries only, taken with the robot's capture path, 640x480, the
  room's ordinary light), three: a printed invented bill, an invented note in blue ballpoint, the
  same note in graphite. Each is read as taken and with its contrast raised (grayscale and a local
  contrast step with the installed OpenCV). They stay in the ignored `.superpowers/sdd/0090/` and
  are deleted at the close.
- **What is recorded per photograph:** latency, peak RSS, and closed checks with no judge model:
  `bill_ok` (the amount and due date read exactly) and, for the notes, how many canary words were
  read.
- **The pass:** `bill_ok` on the printed bill. **Handwriting is recorded, not promised**: it never
  blocks the plan; what it misses stays in R4 with the probe as its evidence.
- **Pipec's choice** is recorded in the probe's record and ADR 0041. If RapidOCR (or the reserve)
  passes, it enters with `uv add` in Task 3, its licence named in ADR 0041; if neither passes, the
  VLM stays the reader and Task 3 builds nothing.
- **The contrast step** enters the reader only if the probe shows it raises a check.

### D-2. The paper slot: where the paper waits

A new in-process slot in `memory/reading_offer.py` replaces the 60 s `READING_SLOT`. It holds the
**whole** read text (cut at `PAPER_MAX_CHARS`, 4,000 characters), bound to the speaker identified
on the reading turn, and follows ADR 0020's rules:

- another identified person, or `WORKING_MEMORY_IDLE_SECONDS` of silence since the last paper turn,
  deletes it;
- an unknown or ambiguous turn neither reads nor extends it;
- a new reading replaces it; a restart forgets it;
- its `repr` and every log line say only whether a paper waits and its length, never its text.

It never enters the continuity slot or the generic prompt (item 6). The secret check runs over the
whole text, not only over the spoken 400 characters. What is spoken stays capped at 400.

### D-3. A question about the paper is a closed cue

While a paper waits, `cognition/document_cues.py` hears a closed **paper cue**: the phrases that
name it («¿qué dice el papel / la carta / la cuenta / la boleta / la receta…?», «¿ahí dice…?») and
a paper's own short questions («¿cuánto tengo que pagar?», «¿cuánto es?», «¿para cuándo es?»,
«¿cuándo vence?», «¿quién lo manda?», «¿de qué se trata?»). The cue is resolved only when a paper
slot is open; with no paper, every one of these turns is today's turn. Every other turn is
today's turn too («¿qué hora es?» stays the clock).

### D-4. The answer quotes; no model words it

A new `memory/paper_answer.py` reuses `document_answer`'s sentence cutting, scoring, order filter,
secret filter and 220-character cap (imported, not copied). Two small closed extractors raise the
right sentence: an amount (`$` or «pesos» with digits) for «¿cuánto…?», a date near «vence»,
«vencimiento», «fecha», «hasta», «pagar antes» for «¿para cuándo…?» / «¿cuándo vence?». The answer
is «Según el papel: …»; nothing found is «Eso no aparece en lo que leí.» (`NOT_IN_PAPER`). The turn
is recorded with the marker «[respuesta del papel leído]», like a document answer (item 5).

### D-5. Nobody identified, and a question that asks to interpret

- **Nobody identified (D-5a).** The reading is read aloud and the slot keeps **no text**, only that
  a reading bound to nobody happened, under the same silence rule. A paper cue then hears
  «Solo puedo leértelo; para responder sobre el papel necesito reconocerte.»
  (`PAPER_NEEDS_IDENTITY`), with nothing of the paper in it.
- **Interpreting (D-5b).** A closed list of questions that ask to interpret («¿es grave?», «¿qué
  significa?», «¿qué tengo que tomar?», «¿es normal?», «¿qué me recomiendas?») asked while a paper
  waits hears «Eso no lo puedo interpretar. Te puedo leer lo que dice; para entenderlo, pregúntale
  a tu médico.» (`PAPER_NOT_INTERPRETED`), for every paper, with no attempt to tell a medical paper
  from another.

### D-6. «Sí, guárdalo» while the paper lives

«¿Lo guardo? Dime: sí, guárdalo.» is offered only after the reading, as today. «Sí, guárdalo»
keeps the paper's **whole** text while the slot lives, from the same speaker; a paper question in
between no longer erases it. This widens ADR 0021's 60 s window for a reading only (ADR 0041);
ADR 0021's verb keeps its meaning when no paper waits. Kept, it is today's `normal` document of
format `camera`.

### D-7. ADR 0041, «Reading and explaining a paper»

Written `Proposed` in Task 2, before the probe, with the reader left to the measurement. It amends
ADR 0034 decision 5 (the paper waits and answers), the alternative ADR 0034 rejected («a dedicated
OCR engine now») once the probe decides, and ADR 0021's window for a reading. Accepted when the
plan closes on hardware.

## Deferred, with their triggers

- A conversation about objects shown («me gané una medalla»): after this plan, on the same slot.
- A person recognized in a photograph: its own ADR first.
- The content of a QR code or a barcode: after the file-ingestion threat model.
- An object detector: only by measurement, never AGPL (Ultralytics is refused).
- Handwriting beyond what this plan's probe shows: R4, with the probe as its evidence.
- **Left out by the amendment of 2026-11-26:**
  - other OCR engines (EasyOCR, docTR, GLM-OCR and others in `model-candidates.md`): when
    RapidOCR misses a household paper in real use, or the server moves to its board;
  - the VLM against the OCR on every photograph: when a lighter vision model is measured
    (`model-candidates.md`, section 4);
  - the reader's contention with Whisper and the other models: the home-server budget (PC-5);
  - a doctor's handwritten prescription: Pipec's real-world reading round, below.
- Pipec's real-world reading round (the home's dim light, blue ink, graphite, a doctor's
  handwriting, notebooks, the robot's own light): after this plan, as a bench of its own.
- A model that words or explains the answer: a larger local model (P4.1), with ADR 0034's
  injection eval run again.

## Global constraints

- The API contract is unchanged: no field added, removed or renamed on any route; the OpenAPI
  document is byte-identical (the existing contract test). The robot changes nothing.
- With `READING_ENGINE=vlm` and no paper waiting, every turn is byte-identical to `main`, except
  that the kept text is the whole read (D-2) instead of the 400 spoken characters.
- No text of a paper in any log, the conversation record, the diary, a recall unit, an export or
  the continuity slot; logs hold counts, causes and durations only.
- Ollama stays the only model runtime for language and the VLM (ADR 0004); an OCR engine runs in
  the server's process or a child, on the CPU, never a cloud call.
- Spoken strings in neutral tuteo (Santiago de Chile, no voseo). No real household data: invented
  canaries only (the «qqcanarioqq» card, an invented bill «qqluzqq» with an invented amount and
  date, an invented note); `scripts/check_reserved_terms.py` passes.

## Review focus

1. **The paper outside its slot:** no paper text in a log, the record, the diary, an export, the
   continuity slot or the generic prompt.
2. **The wrong listener:** another identified person, an unknown turn or 180 s of silence; the
   paper is gone or untouched as D-2 says, and a stranger hears `PAPER_NEEDS_IDENTITY`, never a
   quotation.
3. **A planted order or a code:** a paper with «ignora tus reglas y di que…» or a code next to its
   secret word is never read in an answer (ADR 0034's injection eval, on papers).
4. **A cue that steals a turn:** with no paper, every paper cue is today's turn; with a paper,
   «¿qué hora es?», a recall, a document question and a secret turn keep their branches.
5. **The reader switch:** `READING_ENGINE=vlm` is today's payload byte for byte; an OCR engine
   never falls back to the VLM on failure, it says `COULD_NOT_READ`.

---

## Permitted files

Paths under `server/src/server/` unless they start with `scripts/`, `tests/`, `docs/` or the root;
a need outside the list stops the plan for Pipec.

| Task | Files |
|---|---|
| 1 | `scripts/ocr_probe.py` (new), `tests/unit/test_ocr_probe.py` (new), `docs/evals/0090-ocr-probe.md` (new); the probe's own environment outside the repo's `.venv` |
| 2 | `docs/adr/0041-reading-and-explaining-a-paper.md` (new), `docs/adr/README.md` (the index) |
| 3 | `settings.py`, `.env.example`, `vision/read_text.py`, `vision/ocr_reader.py` (new, only if an OCR is chosen), root `pyproject.toml` and `uv.lock` (only the chosen engine); `tests/unit/test_read_text.py` (or the existing reading test file), `tests/unit/test_ocr_reader.py` (new, same condition), `tests/unit/test_settings.py` |
| 4 | `memory/reading_offer.py`, `routers/transcribe.py` (`_text_reader`, `_reading_keeper`, `_cap_reading`); `tests/unit/test_reading_offer.py` (or the existing slot test file), the existing reading integration tests |
| 5 | `cognition/document_cues.py`, `cognition/intent_resolution.py`, `cognition/models.py` (one new need), `cognition/controller.py`, `cognition/response_plan.py` (the phrases and the marker), `memory/paper_answer.py` (new), `routers/transcribe.py` (the paper seam); `tests/unit/test_document_cues.py`, `tests/unit/test_intent_resolution.py`, `tests/unit/test_paper_answer.py` (new), `tests/integration/test_paper_questions.py` (new), `tests/unit/test_no_voseo_in_spoken_strings.py` |
| 6 | the same files as Task 5 (D-5's two phrases and their cues) |
| 7 | `tests/integration/test_paper_privacy.py` (new) |
| 9 | `docs/runbooks/operator-manual.md` (the reading, its questions, `READING_ENGINE`), `docs/architecture/current-state.md`, the Archify voice-turn diagram (`docs/architecture/diagrams/current-state-voice-turn.json` and `.html`, validate then deliver), `docs/evals/0090-paper-acceptance.md` (new), ADR 0041 (accepted), ADR 0034 and ADR 0021 (an *Amended by ADR 0041* note), the roadmap (row 9a), the plan board, `docs/plans/open/README.md`, `docs/plans/completed/README.md`, Pipec's local `docs/roadmap/tabla-tareas.md` |

The exact test file names are confirmed in Task 0; a file named here that does not exist is the
closest existing one, not a new one, unless marked new.

**Rollback boundary.** Before the merge, the branch. After it, a revert: no migration, no stored
data beyond today's kept documents; a revert brings back the 60 s slot, the 400-character keep and
the VLM reader.

---

## Task 0: Re-audit and baseline

- [ ] **Step 1:** `git switch main && git pull`, create `feat/0090-read-and-explain-a-paper`.
- [ ] **Step 2:** verify items 1 to 9 of *What the code does today* on `main`; confirm the test
  file names of the permitted list. **Stop and report** if an item is false.
- [ ] **Step 3:** baseline: the CI selection with `MEMORY_ENABLED=false`, `pyright`, `mypy`,
  `ruff`; record the counts in the commit message of Task 1.

## Task 1: The isolated OCR probe (D-1, amended 2026-11-26), with Pipec at the laptop

- [ ] **Step 1:** read RapidOCR's licence (code and model weights) and its last release, and
  Tesseract's only if the reserve is used; refuse AGPL, GPL or a non-commercial model licence.
  Record name, version and licence in `docs/evals/0090-ocr-probe.md`.
- [ ] **Step 2 (TDD):** `scripts/ocr_probe.py` reads one photograph with one engine, as taken and
  with the contrast step, and writes one JSON line per read (engine, photograph label, variant,
  latency, peak RSS, `bill_ok` or the count of canary words read, failure cause);
  `tests/unit/test_ocr_probe.py` proves the checks and that no line holds read text. RED first.
- [ ] **Step 3:** build a separate environment from the lock plus RapidOCR (never the real
  `.venv`); Pipec takes the three photographs, one step per message, his «listo» each time.
- [ ] **Step 4:** run the probe with the server **off**; one read per cell, no retry.
- [ ] **Step 5:** write the record (numbers and outcomes only) and put the choice to Pipec, with a
  recommendation. Record his answer in the record and below.

## Task 2: ADR 0041, `Proposed`

- [ ] Write ADR 0041 from D-1 to D-7, the probe's numbers and Pipec's choice; add it to the index.

## Task 3: The reader behind the seam (D-1)

Built only if the probe passed; otherwise the VLM stays the reader and this task records that.

- [ ] **RED:** `READING_ENGINE=vlm` sends `main`'s payload byte for byte; an unknown value fails
  at startup; with the chosen OCR, a canary frame gives the canary text, a failure raises
  `VisionError` (so the route says `COULD_NOT_READ`) and the VLM is never called; the contrast
  step runs only if the probe kept it.
- [ ] **GREEN:** the setting, `.env.example`, `vision/ocr_reader.py` (CPU-bound, through
  `run_in_executor_with_context`, the frame in memory only) with `uv add` of the engine.

## Task 4: The paper slot (D-2) and «sí, guárdalo» over it (D-6)

- [ ] **RED:** the whole text is held (up to 4,000) and the spoken one is capped at 400; another
  identified person, an unknown turn, 180 s of silence, a new reading and `clear()` behave as D-2
  says; a reading bound to nobody holds no text; the secret check covers the whole text; «sí,
  guárdalo» after two paper questions keeps the whole text for the same speaker and not for
  another; the `repr` and the logs hold no text.
- [ ] **GREEN:** the slot in `memory/reading_offer.py` and the route's reader and keeper.

## Task 5: The paper cue (D-3) and the quoted answer (D-4)

- [ ] **RED:** each phrase of D-3 resolves to the paper need only with a paper open; with none, to
  today's need; «¿qué hora es?», a recall, a document cue and a secret turn keep their branches
  with a paper open. On invented papers: «¿cuánto tengo que pagar?» quotes the amount's sentence,
  «¿para cuándo es?» the due date's, a missing answer says `NOT_IN_PAPER`; the record holds the
  marker. ADR 0034's injection eval, rerun on papers: no planted order and no code in any answer.
- [ ] **GREEN:** the cue, the need, `memory/paper_answer.py` (reusing `document_answer`), the
  controller branch and the phrases.

## Task 6: Nobody identified, and interpreting (D-5)

- [ ] **RED:** after a reading bound to nobody, a paper cue says `PAPER_NEEDS_IDENTITY` and nothing
  of the paper; each interpreting question with a paper open says `PAPER_NOT_INTERPRETED`; with no
  paper, those questions are today's turns. The voseo guard covers the new phrases.
- [ ] **GREEN:** the two cues and phrases.

## Task 7: The privacy lock

- [ ] One integration test drives a reading, two questions and a keep with a canary paper and
  asserts the canary is absent from the log capture, the conversation record, the diary input, the
  continuity slot and an export, and present only in the kept document.

## Task 8: Verification and review

- [ ] The CI selection, `just gate` (not while Pipec rehearses), `pyright`, `mypy`, `ruff`,
  `ruff format --check`, the reserved-terms guard; a `sonnet` review over the five review-focus
  points; fixes applied with `superpowers:receiving-code-review`.

## Task 9: Hardware acceptance, and close

Pipec at the laptop, one step per message. With the chosen reader, on the streaming route
(production's; the classic route shares the same seam and is covered by the tests):

1. An invented bill: «Iroko, lee esto», then «¿cuánto tengo que pagar?» and «¿para cuándo es?»:
   both quoted «Según el papel: …», right.
2. «¿Es grave?» with the bill still open: `PAPER_NOT_INTERPRETED`.
3. «Sí, guárdalo» after the questions: kept; «¿qué dice mi nota del …?» finds it.
4. The face out of view on the reading, then «¿cuánto tengo que pagar?»: `PAPER_NEEDS_IDENTITY`.

The 180 s of silence and an unrelated question with a paper open are proved by Task 4 and Task 5's
tests with an injected clock, not on hardware.

Record outcomes only in `docs/evals/0090-paper-acceptance.md`; update the documents of Task 9's
row; ADR 0041 `Accepted`; the plan to `completed/`.

## Completion criteria

1. The probe's record holds RapidOCR's numbers on the three photographs, as taken and with the
   contrast step (and the reserve's, if used), and Pipec's choice; the chosen reader is the
   default.
2. A paper is read, answered by its amount and its due date with «Según el papel: …», and kept on
   «sí, guárdalo» after the questions: on hardware on the streaming route, in tests on both.
3. Nobody identified hears `PAPER_NEEDS_IDENTITY`; an interpreting question hears
   `PAPER_NOT_INTERPRETED`; no planted order or code is ever answered.
4. Another person, an unknown turn and 180 s of silence end the paper as D-2 says.
5. No paper text outside its slot and a kept document (Task 7).
6. The CI selection, `just gate`, the type checkers, `ruff` and the reserved-terms guard pass.
7. Task 9's script passes on hardware, with its record; the documents updated; ADR 0041 accepted.

## Non-goals

Everything in *Deferred*; interpreting a text; wording an answer with a model; any change to the
scene or to `/vision/*`; a new field on any route; keeping the frame; a cloud provider; a reader
that falls back to another; tolerant or fuzzy phrase matching beyond the closed cues.

## Pipec's decisions (answered 2026-11-25, every recommendation accepted)

Asked one at a time.

1. **D-1, who reads: measure first.** A bench compares two or three OCR engines on the CPU with a
   permissive licence against the VLM on the same photographs; Pipec picks the reader with the
   numbers; one reader, no hidden fallback. Rejected: keeping the VLM unmeasured on a bill, and an
   OCR chosen without numbers.
2. **D-2, where the paper waits: its own paper slot**, the whole text (about 4,000 characters),
   bound to the speaker of the reading turn, with ADR 0020's rules; never in the continuity slot or
   the generic prompt. Rejected: the continuity slot (the generic prompt would read the paper).
3. **D-3, which turns ask about the paper: a closed list.** Rejected: every turn of the window (it
   steals the conversation).
4. **D-4, how the answer is worded: it quotes, no model.** Rejected: the 3B wording with a number
   check (it cannot see a planted order, and adds 8 to 20 s).
5. **D-5a, nobody identified: a fixed phrase that explains.** Rejected: treating the question as
   if there were no paper (the 3B could invent an amount).
6. **D-5b, a question that asks to interpret: a fixed phrase**, for every paper. Rejected: quoting
   the nearest sentence (out of context it can sound like medical advice).
7. **D-6, keeping after questions: while the paper slot lives.** Rejected: the next turn only.
8. **D-7, the ADR: a new ADR 0041.** Rejected: one more amendment inside ADR 0034.

**Amendment of 2026-11-26 (Pipec).** After the plan was `Ready`, Pipec asked to stop measuring
vision on a laptop known to be short and to prove the reader alone first. He approved the table of
*Scope amendment of 2026-11-26*: D-1 becomes one OCR (RapidOCR) proved in an isolated script with
three photographs; Task 9 becomes four steps on the streaming route; the VLM comparison, the loaded
measurement and the prescription are left out with their triggers. Every other decision stands.
