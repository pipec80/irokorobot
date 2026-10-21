# 0068 — Short answers and the speaker check: a retry when only the voice failed, and a measurement

> **Back in `NOW` since 2026-10-21:** it was paused on 2026-10-20 while
> [Plan 0069](../completed/0069-stt-owner-voice-audit.md) measured the speech-to-text itself, and that plan
> is closed ([ADR 0023](../../adr/0023-speech-to-text-model-and-decoding.md)). Tasks 0 to 5 are merged
> (PR #201, `917deec`); Tasks 6 to 8 are Pipec's. Take their counts with the adopted profile in the
> runtime `.env` (`medium` on the GPU, a 1200 ms closing silence, a 300 ms upload tail), and say so in
> the report.

> **Status:** `Ready` and `NOW` — promoted by Pipec on 2026-10-19 and executed in the same session
> (Pipec's choice: «a final estamos en lo mismo, así vamos sumando mejoras»), after Plan 0067 merged
> (PR #199). Written 2026-10-19 as a measurement-only draft; **rewritten the same day** after the
> first hardware session of Plan 0067, when Pipec added the retry of Part A. Part A changes runtime
> behavior (one fixed phrase); Part B is a measurement that changes no threshold and no enrollment.
> The face-only fallback is **not** planned (Pipec). Task 6 also records the hardware counts that Plans
> 0066 and 0067 left open. **Not rehearsed**; Tasks 3 and 4 name behavior and tests, and the executor
> re-reads `scripts/speaker_calibration*.py` before touching them.

> **For agentic workers:** if the status above does not say `Ready`, stop. REQUIRED SUB-SKILLS:
> `superpowers:executing-plans`, `superpowers:test-driven-development`,
> `superpowers:verification-before-completion`, `superpowers:finishing-a-development-branch`. Pipec's
> rules win: one plain branch from `main`, never a git worktree, subagents only if Pipec asks. An
> agent never records, imitates or replays a voice and never reads the private corpus aloud; Pipec
> runs every capture and deletes the corpus once the report is accepted. Record counts and distances
> only, never a sentence. Create and edit files with the Write and Edit tools. Run the suite with
> `MEMORY_ENABLED=false`. Every finding met while executing is fixed (Pipec's standing policy).

**Goal:** (A) When the owner's face is in front of the robot, an offer of theirs is open, and they
answer it but **only the voice check failed**, the robot says one fixed sentence that asks for a
longer answer and listens again in reply mode, instead of handing the bare «sí, autorizo» to the
language model (which, not knowing the question, invents one). (B) An evidence-backed answer to: «on
a 1–2.5 s answer, does the owner pass the speaker check more often if the silence around the speech
is trimmed before the embedding, or if the stored references include short confirmations — with no
impostor accepted at the current threshold?»

**Why:** In the first hardware session of Plan 0067 (2026-10-19), three offers were answered «Sí,
autorizo.»: the reply mode worked every time (one turn, `hotwords=7`) and Whisper heard the words,
but the speaker check said `verified` once and `unknown` twice on the same 2.5 s clip (2.1 s after
the recognizer's VAD). The two failures fell through to ordinary generation, and the model replied
«Entendido, estaré listo para tu cita a las 20 horas»: the spoken offer is not in its history, so it
guessed. Facts from the code: the whole uploaded clip is embedded, including the 0.4 s pre-roll and
the ~0.8 s silent tail the robot keeps; the owner's three references are 5 s fixed recordings in one
condition; `SPEAKER_MIN_VERIFICATION_S=1.5` and the 1.5–3 s range were never measured (Plan 0047
captured 3–5 s phrases); the `Speaker verdict` log carries only the verdict.

**Architecture (Part A):** `answer_offer` already reads the actor and the open offer. When the actor
is the owner identified **by face only** (no token, voice not verified), the parsed answer names an
offer of that same person that is open (by value, or the one open offer for a verb alone), it
returns a typed reply: the fixed retry phrase and «expects a short reply». It writes nothing, audits
nothing and does not move the offer; the answer window keeps running from the offer. The controller
turns the typed reply into a deterministic `ResponsePlan` that carries `expects_short_reply`, and the
stream's `done` says so, so the robot's reply mode of Plan 0067 listens once more. Every other case is
unchanged: a token, a weaker actor, another person's face, no open offer, a different value — fall
through byte-identical, as today.

**Tech Stack:** Python 3.12, FastAPI, SQLite, SpeechBrain ECAPA, pytest. No new dependency.

**Spec:** [ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md) decisions 3 and 9
(this plan amends the «falls through byte-identical» clause for one case), the Plan 0067 record
([Plan 0067](../completed/0067-reply-listening-mode.md)),
[Plan 0047](../completed/0047-speaker-evidence-calibration-study.md) (the calibration procedure), and
`.claude/rules/` (not tracked; read them from the working copy).

## Task overview

| # | Task | Closes |
|---:|---|---|
| 0 | Revalidate the baseline | — |
| 1 | The verdict log says why | clip seconds, distance, which gate |
| 2 | A retry when only the voice failed | Part A, Pipec's point 3 |
| 3 | The corpus tool accepts short classes | capture of short answers |
| 4 | The analysis compares the variants | trimmed vs raw, long vs long+short references |
| 5 | Documentation truth | ADR 0021 amendment, manual, current state |
| 6 | Hardware counts (Pipec) | Plan 0066 and 0067 leftovers, the retry |
| 7 | Capture sessions (Pipec) | the private corpus |
| 8 | Analysis, report, recommendation, cleanup | Part B's answer |

## Global Constraints

- Private corpus only: never committed, never read aloud, deleted after Pipec accepts the report
  (typed `delete`), the model cache kept, as in Plan 0047. No real household names in anything tracked.
- No threshold, enrollment or speaker setting changes. Part B judges every variant **at** 0.4834.
- The firewall of ADR 0021 decisions 3 and 9 is untouched for **writes**: only the face-and-voice
  composite of the same person answers; a token never answers; the actor is resolved first for every
  answer-shaped message. The retry is the only new observable outcome, and only for the owner's own
  face with that person's own open offer.
- A variant is only *recommended* if it keeps impostor accepts at 0 observed on the short impostor
  class; the report states the rule-of-three bound with the sample size and that genuine rates are
  in-sample.
- Audio contract (WAV, 16 000 Hz, mono, int16); `ruff` clean over explicit paths including `scripts/`;
  `mypy server/src robot/src` clean; commit titles at most 72 characters (count them).

## Decisions

1. **D-1 — The retry (Pipec, 2026-10-19).** Phrase: `ANSWER_RETRY_PHRASE = "No reconocí bien tu voz.
   Dímelo un poco más largo: sí, autorizo que lo guardes."` (tuteo neutro). **Finding while writing
   this plan:** «sí, autorizo que lo guardes» does **not** parse today (only «que guardes» is a verb
   form), although it was suggested to Pipec as a longer answer; Task 2 adds «que lo guardes» and «que
   la guardes» after every long verb (and their «no» forms) so the retry asks for an answer that
   works. Conditions, all required: answer switch on,
   the actor is identified by face with no token (`is_face_actor`) and is **not** the face-and-voice
   composite, and `find_offered` finds that person's open offer for the parsed answer (key, or `None`
   for a verb alone). No write, no audit row, no offer change, no extension of the answer window.
2. **D-2 — The cost, stated.** A person who is not the owner but stands where the owner's face is
   recognized (the owner in frame, another person speaking) gets the retry phrase instead of ordinary
   conversation. It reveals that an offer is open, which was already spoken aloud in the room; it
   writes nothing. A different face, a token, or no open offer still get ordinary conversation. The
   ADR 0021 amendment says so.
3. **D-3 — The reply hint follows the retry.** `ResponsePlan.expects_short_reply: bool = False`; the
   deterministic stream path copies it into `done.expects_short_reply`. The classic route ignores it
   (its robot path has no reply mode).
4. **D-4 — The typed reply lives in the cognitive core.** `MemoryAnswerReply(phrase: str,
   expects_short_reply: bool = False)` (frozen) in `server/src/server/cognition/response_plan.py`;
   `MemoryAnswerer` returns `MemoryAnswerReply | None`; `answer_offer` returns the same. The core
   still imports nothing from `server.memory`.
5. **D-5 — Part B's corpus (all private).** `reference-short` 6 (the owner's «sí», «acepto», «sí,
   autorizo», one quiet session), `genuine-short` 24 (the same words, 1–2.5 s, at least 2 later
   sessions, the four conditions of Plan 0047), `impostor-short` 18 (at least 3 consenting adults,
   live), `replay-short` 6 (Pipec plays). Plus a long control: 6 long references and 6 long genuines
   recaptured (the Plan 0047 corpus was deleted on 2026-09-25).
6. **D-6 — Variants, per clip, offline.** `raw` (as the robot sends it) and `trimmed` (leading and
   trailing silence removed by a fixed energy rule defined and tested in Task 4); references
   `long-only` and `long+short`. Output per cell: genuine distances and rate under the threshold,
   impostor distances and accepts, replay accepts, clip-length buckets (1–1.5, 1.5–2, 2–2.5 s), and the
   share of silence in raw clips.
7. **D-7 — The recommendation names the next plan, it does not make it.** Trimming helps and is
   safe → a runtime plan for a trimmed embedding; short references help → an enrollment plan;
   neither → a longer spoken answer stays the rule, or a non-voice confirmation later.

## Required reading

- `AGENTS.md`, `docs/architecture/implementation-guardrails.md`, `.claude/rules/`.
- ADR 0021 decisions 3 and 9 with their amendments; Plan 0047 (procedure, frozen commands, report
  format); `docs/runbooks/operator-manual.md` (speaker and memory sections).
- `server/src/server/memory/{candidate_dialogue,lexicon}.py`, `server/src/server/cognition/{controller,response_plan,strong_actor,speaker_authentication}.py`,
  `server/src/server/streaming.py`, `server/src/server/routers/transcribe.py`,
  `server/src/server/voice/speaker_embedding.py`, `scripts/speaker_calibration*.py`,
  `robot/src/robot/audio_capture.py`.

## Review Focus

1. Another person's face (or two faces) with the owner's offer open: ordinary conversation, never the
   retry (Task 2).
2. A token-identified owner, or no face at all, answering: ordinary conversation (Task 2).
3. The owner's face, voice unverified, but **no** open offer or a different value: ordinary
   conversation, byte-identical (Task 2).
4. The retry followed by a verified «sí, autorizo que lo guardes» inside the window: promoted; after
   the window: ordinary conversation (Task 2).
5. The verdict log never carries audio, a value or a name, and a missing distance is absent, not zero
   (Task 1).

---

## Task 0: Revalidate the baseline

- [ ] Status `Ready`; branch `feat/0068-retry-and-speaker-study` from `main`; `just gate`; record the
  count (3490 at the close of Plan 0067); `rg -n "def answer_offer|type MemoryAnswerer|class ResponsePlan|Speaker verdict" server/src` finds what this plan names.

## Task 1: The verdict log says why

**Files:** `server/src/server/cognition/speaker_authentication.py`; test
`tests/unit/test_speaker_authentication.py`.

- [ ] **Failing tests:** the `speaker.verdict` record carries `clip_s` (0.1 s), `distance` (0.001;
  absent when none was computed) and `gate` (`ok`, `energy`, `duration`, `references`, `distance`,
  `consent`, `role`, `unavailable`); nothing carries audio, a name or a value. RED: the fields are
  absent.
- [ ] **Implement** in the existing log call; the verdict logic and the order of checks do not change.
- [ ] Run the speaker test files; lint and types. **Commit** `feat(server): log why the speaker check said unknown`.

## Task 2: A retry when only the voice failed

**Files:** `server/src/server/cognition/{response_plan,controller,intent_resolution}.py`,
`server/src/server/memory/{candidate_dialogue,lexicon}.py`, `server/src/server/streaming.py`,
`server/src/server/routers/transcribe.py` (the answerer binding); tests
`tests/integration/test_candidate_dialogue.py`, `tests/unit/test_cognitive_controller.py`,
`tests/integration/test_memory_dialogue_routes.py`, `tests/unit/test_architecture_guards.py` (run).

**Interfaces.** Produces `MemoryAnswerReply` (D-4), `ResponsePlan.expects_short_reply`,
`ANSWER_RETRY_PHRASE` (D-1). `answer_offer(...) -> MemoryAnswerReply | None`; every existing result
phrase becomes `MemoryAnswerReply(phrase)`.

- [ ] **Failing tests:** grammar (`tests/unit/test_memory_answer_grammar.py`): «Sí, autorizo que lo
  guardes», «Acepto que la guardes», «Apruebo que lo guardes» → `(True, "")`; «No autorizo que lo
  guardes» → `(False, "")`; «Autorizo que lo guardes el mate» → `(True, "el mate")`; the round trip:
  the words the retry phrase dictates parse to `(True, "")`. Dialogue: a face-only owner (no voice evidence) with their open offer answers
  «sí, autorizo» and with the value → retry phrase, `expects_short_reply` true, the offer still
  `offered`, no fact, no audit; the same with no open offer, a different value, a token, another
  person's face, the switch off → `None`; after a retry, the face-and-voice owner answers inside the
  window → promoted. Controller: the typed reply becomes a deterministic plan carrying the flag; the
  actor is still resolved before the answerer. Routes: on the stream, the owner's face with another
  voice answering an open offer gets the retry phrase and `done.expects_short_reply` true, and the
  offer stays open; on `/chat` nothing changes. The Plan 0066/0067 tests that assert «another voice
  with the owner's face falls through» are updated to the retry, each with a comment naming D-2.
  RED: `answer_offer` returns `None` for the face-only owner.
- [ ] **Implement** the «que lo/la guardes» prefixes (longest first), the type, the field, the phrase, the branch in `_find_open_offer`/`answer_offer`
  (before the face-and-voice check returns `None`), the controller mapping and the stream copy into
  `done`.
- [ ] Run the four test files plus `tests/integration/test_stream_offer.py` and
  `tests/integration/test_import_graph.py`; lint and types. **Commit** `feat(server): ask again when only the voice failed on an answer`.

## Task 3: The corpus tool accepts short classes

**Files:** `scripts/speaker_calibration.py` (and the corpus/models modules it uses); test
`tests/unit/test_speaker_calibration.py`.

- [ ] The classes of D-5 exist in the manifest and the validation matrix with their minimums;
  `capture` takes a per-class lower bound (default 2.5 s unchanged; the short classes accept 1.0 s)
  and still rejects clipped takes and silence; a short class never satisfies a long-class minimum.
  Tests first (RED on the unknown class). **Commit** `feat(scripts): capture short answers for the speaker study`.

## Task 4: The analysis compares the variants

**Files:** `scripts/speaker_calibration_analysis.py` (and helpers); test
`tests/unit/test_speaker_calibration_analysis.py`.

- [ ] A pure `trim_silence(samples, sample_rate) -> samples` with a fixed, documented energy rule
  (pure silence stays empty and is reported; speech inside is never cut; never longer than the
  input); the analysis embeds each clip `raw` and `trimmed`, builds both centroids and writes the
  cells of D-6 into the aggregate report. Synthetic tones and a fake encoder in tests (no private
  data). **Commit** `feat(scripts): compare trimmed and raw short clips`.

## Task 5: Documentation truth (text only)

- [ ] ADR 0021 decision 9: the retry (D-1) and its cost (D-2), dated. Operator manual: the retry, the
  new log fields and how to read them, the short-class capture commands. `current-state.md`, the
  roadmap row, the plan indexes; refresh the architecture diagram only if it shows the answer path.
  `ruff format --check .`, `check_reserved_terms`, links; **commit** `docs: record plan 0068 code`.
  Open the PR; merge with Pipec's go-ahead.

## Task 6: Hardware counts (Pipec runs everything)

With `MEMORY_CANDIDATES_ENABLED=true`, counts only:

- [ ] Plan 0067 leftovers: two «no acepto», two «sí, guárdala», three offers left unanswered for
  15 s (back to normal listening?), one unrelated question as the reply (answered normally?).
- [ ] Plan 0066 leftovers: two answers with the old full phrase; three casual «autorizo» or «sí,
  guarda» with no open offer (nothing saved, ordinary reply).
- [ ] The retry: how many short answers got the retry phrase; after it, how many longer answers
  promoted.

## Task 7: Capture sessions (Pipec runs everything)

- [ ] The classes of D-5 with `just speaker-calibration capture ...`, at least two sessions and the
  four conditions; consenting impostors live; replay by Pipec. Counts per class and condition only.

## Task 8: Analysis, report, recommendation, cleanup

- [ ] `validate`, `embed`, `analyze`; Pipec reads the report. The execution record states the cells
  of D-6, sample sizes, bounds and the D-7 recommendation. After Pipec's acceptance, `discard` and
  `cleanup` with Pipec's typed `delete`. `just gate`; docs; commit `docs: close plan 0068`; PR.

## Completion criteria

1. A face-only owner whose short answer failed only by voice hears the retry and the robot listens
   again in reply mode; nothing else in the firewall changed.
2. The verdict log carries the clip seconds, the distance and the gate.
3. The hardware counts of Task 6 are recorded.
4. The report answers Part B with numbers and the D-7 recommendation; no threshold changed; the
   private corpus is deleted after acceptance; `just gate` green.

## Not here, and why

- Any runtime change to the embedding, the enrollment or the thresholds: Task 8 recommends the next plan.
- A face-only fallback that *writes* (removed by Pipec) and a bare «sí» (Plan 0066 decision).
- Putting the spoken offer into the model's history: the retry removes the case that needed it; if a
  fall-through after an offer still confuses the model, it is a follow-up.

## Execution record

Executed 2026-10-19 on `feat/0068-retry-and-speaker-study` (base `983d46f`), tasks 0 to 5, in the
same session that closed Plans 0066 and 0067 (Pipec's choice). **Tasks 6 to 8 are Pipec's**: the
hardware counts, the capture sessions (with at least three consenting adults) and the report; the
plan stays `NOW` until they are recorded here.

- **Baseline:** not re-run locally; `main` was Plan 0067's gate (3490 passed) plus documentation
  (PR #200, CI green).
- **Gate:** `just gate` green, 3654 passed after the review fixes.
- **Rulings.** (1) The retry also requires active voice consent: without it the voice can never
  verify, so asking again would only loop; the answer falls through as before (test-first). (2) An
  undecodable clip logs `clip_s=0.0`. (3) Tasks 3 and 4 are one commit: both changed the same four
  calibration modules. (4) The short study has its own phrases (`short-01` «Sí», `short-02` «Acepto»,
  `short-03` «Sí, autorizo») and, when a corpus holds any short sample, writes the short report
  instead of the long aggregate (that corpus has no long impostor or replay classes to score).
  (5) Finding while writing the plan: «sí, autorizo que lo guardes», suggested to Pipec as a longer
  answer, did not parse; Task 2 added «que lo/la guardes» after every long verb.
- **Review** (independent, read-only, code and tooling): no Critical and no Important finding. Fixed,
  test-first: a refusal is asked again as a refusal (`ANSWER_RETRY_REJECT_PHRASE` dictates «no
  autorizo que lo guardes»), never as an acceptance; no retry with the speaker check switched off or
  when the consent lookup fails; the `done` field comment names the retry; the study report states
  the rule-of-three bound only for a variant with no accepts, warns that a click or steady noise
  defeats the trim and that production refuses clips under 1.5 s; one speech floor shared by the
  trim and the capture guard, and a drift guard on the threshold. Written into the ADR: the same
  person can confirm a guessed value through the retry, a value already spoken aloud in the offer.
