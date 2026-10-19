# 0068 — Short clips and the speaker check: measure silence trimming and short references

> **Status:** `Draft` — written 2026-10-19 after Pipec's hardware session with Plan 0066. Third item of
> the order Pipec chose (after [Plan 0067](0067-reply-listening-mode.md)): *measure* whether trimming the
> silence and adding short voice references let the speaker check recognize the owner on a short
> answer. It is a **measurement plan: it changes no runtime behavior, no threshold and no enrollment**
> (the one runtime edit is a diagnostic log). The face-only fallback is **not** planned (Pipec).
> Waits for Plan 0067 to close and for Pipec to mark it `Ready` and `NOW`; to be executed in a **new
> session**. **Not rehearsed**; Tasks 2 and 3 name behavior and tests, and the executor re-reads
> `scripts/speaker_calibration*.py` before touching them.

> **For agentic workers:** if the status above does not say `Ready`, stop. REQUIRED SUB-SKILLS:
> `superpowers:executing-plans`, `superpowers:test-driven-development`,
> `superpowers:verification-before-completion`, `superpowers:finishing-a-development-branch`. Pipec's
> rules win: one plain branch from `main`, never a git worktree, subagents only if Pipec asks. An
> agent never records, imitates or replays a voice and never reads the private corpus aloud; Pipec
> runs every capture and deletes the corpus when he accepts the report. Record counts and distances
> only, never a sentence. Create and edit files with the Write and Edit tools.

**Goal:** An evidence-backed answer to: «on a 1–2.5 s answer, does the owner pass the speaker check
more often if (a) the silence around the speech is trimmed before the embedding, (b) the stored
references include short confirmations, or both — with no impostor accepted at the current
threshold?» The answer becomes a recommendation for a later plan; this plan ships no behavior change.

**Why (facts from the code, 2026-10-19):** the whole uploaded clip is embedded, including the 0.4 s
pre-roll and about 0.8 s of trailing silence the robot adds (`robot/audio_capture.py`), so a 1 s
«sí» reaches the speaker model as about 2.2 s, half of it silence; the owner's three references are
5 s fixed recordings in one condition; `SPEAKER_MIN_VERIFICATION_S=1.5` and the 1.5–3 s range were
never measured (Plan 0047 captured 3–5 s phrases and its tool rejects live takes under 2.5 s); the
`Speaker verdict` log carries only the verdict, so the distance is unobservable. The session log
shows `verified` for clips of 2.6 s, 3.1 s and 5.8 s and `unknown` for 1.7 s, 2.1 s and 2.2 s.

## Task overview

| # | Task | Closes |
|---:|---|---|
| 0 | Revalidate the baseline | — |
| 1 | The verdict log says why | clip seconds, distance, which gate |
| 2 | The corpus tool accepts short classes | capture of short answers |
| 3 | The analysis compares the variants | trimmed vs raw, long vs long+short references |
| 4 | Capture sessions (Pipec) | the private corpus |
| 5 | Analysis, report, recommendation, cleanup | the answer |

## Global Constraints

- Private corpus only: never committed, never read aloud, deleted after Pipec accepts the report
  (typed `delete`), the model cache kept, as in Plan 0047. No real household names in anything tracked.
- No runtime change except Task 1's log fields. No threshold, enrollment or settings change. The
  threshold stays 0.4834; any variant is judged **at that threshold**.
- A variant is only *recommended* if it keeps impostor accepts at 0 observed on the short impostor
  class; the report states the upper bound (rule of three) with the sample size, and that the
  genuine rate is in-sample.
- The audio contract (WAV, 16 000 Hz, mono, int16); `ruff` clean over explicit paths including
  `scripts/`; `mypy server/src robot/src` clean; commit titles at most 72 characters.

## Decisions

1. **D-1 — The corpus (all private).** `reference-short` 6 (the owner's «sí», «acepto», «sí,
   autorizo», in one quiet session), `genuine-short` 24 (the same words, 1–2.5 s, at least 2 later
   sessions, the four conditions of Plan 0047), `impostor-short` 18 (at least 3 consenting adults,
   live), `replay-short` 6 (Pipec plays; an agent never does). The Plan 0047 classes for long phrases
   are recaptured or reused only if Pipec says the old ones are still valid (they were deleted
   2026-09-25, so assume recapture of 6 long references and 6 long genuines as the control).
2. **D-2 — Variants, per clip, offline.** `raw` (as the robot sends it), `trimmed` (leading and
   trailing silence removed by a fixed energy rule defined and tested in Task 3, with the same RMS
   floor family the robot's VAD uses). References: `long-only` vs `long+short`. Four cells, plus the
   control with long phrases.
3. **D-3 — Output.** For each cell: genuine distance range and rate under the threshold, impostor
   distance range and accepts, replay accepts, clip-length buckets (1–1.5, 1.5–2, 2–2.5 s). Also the
   share of silence in the raw clips. No threshold is retuned.
4. **D-4 — The recommendation names the next plan, it does not make it.** If trimming helps and is
   safe: a runtime plan for a trimmed embedding. If short references help: an enrollment plan. If
   neither: the alternatives of the 2026-10-19 discussion (a longer spoken answer, a non-voice
   confirmation).

## Required reading

- `docs/plans/completed/0047-speaker-evidence-calibration-study.md` (procedure, frozen commands,
  report format) and `docs/runbooks/operator-manual.md` (speaker section).
- `server/src/server/voice/speaker_embedding.py`, `server/src/server/cognition/speaker_authentication.py`,
  `scripts/speaker_calibration*.py`, `robot/src/robot/audio_capture.py`.

## Task 0: Revalidate the baseline

- [ ] Status `Ready` and Plan 0067 closed; branch `feat/0068-short-clip-speaker-measurement` from
  `main`; `just gate`; record the count; re-audit the symbols named above.

## Task 1: The verdict log says why

**Files:** modify `server/src/server/cognition/speaker_authentication.py`; test modified
`tests/unit/test_speaker_authentication.py`.

- [ ] **Step 1: Failing tests:** the `speaker.verdict` log record carries `clip_s` (rounded to 0.1 s),
  `distance` (rounded to 0.001, absent when none was computed) and `gate` (one of `ok`, `energy`,
  `duration`, `references`, `distance`, `consent`, `role`, `unavailable`); no field carries audio,
  a name or a value. Expected RED: the extra fields are absent.
- [ ] **Step 2: Implement** the fields in the existing log call and its `extra`; the verdict logic
  and the order of checks do not change (the existing table tests stay green).
- [ ] **Step 3:** run the two speaker test files; lint and types. **Step 4: Commit** `feat(server): log why the speaker check said unknown (plan 0068)`.

## Task 2: The corpus tool accepts short classes

**Files:** modify `scripts/speaker_calibration.py` (and the corpus/models modules it uses); tests
modified `tests/unit/test_speaker_calibration.py`.

- [ ] The four classes of D-1 exist in the manifest and the validation matrix with their minimums;
  `capture` takes a per-class lower bound (default 2.5 s unchanged; the short classes accept 1.0 s) and
  still rejects clipped takes and silence; a short class never satisfies a long-class minimum.
  Tests first (RED on the unknown class), then implementation; `uv run ruff check scripts/...` over
  explicit paths. Commit `feat(scripts): capture short answers for the speaker study (plan 0068)`.

## Task 3: The analysis compares the variants

**Files:** modify `scripts/speaker_calibration_analysis.py` (and its helpers); tests modified
`tests/unit/test_speaker_calibration_analysis.py`.

- [ ] A pure `trim_silence(samples, sample_rate) -> samples` with a fixed, documented energy rule and
  its tests (a clip of pure silence stays empty and is reported, speech inside is never cut, the
  result is never longer than the input); the analysis embeds each clip as `raw` and `trimmed`, builds
  the `long-only` and `long+short` centroids, and writes the cells and buckets of D-3 into the
  aggregate report. Tests use synthetic tones and a fake encoder (no private data). Commit
  `feat(scripts): compare trimmed and raw short clips in the speaker study (plan 0068)`.

## Task 4: Capture sessions (Pipec runs everything)

- [ ] Pipec captures the classes of D-1 with `just speaker-calibration capture ...` in at least two
  sessions and the four conditions, consenting impostors live, replay by Pipec. Record only counts per
  class and condition in the execution record.

## Task 5: Analysis, report, recommendation, cleanup

- [ ] `just speaker-calibration validate`, `embed`, `analyze`; Pipec reads the report. The execution
  record states the cells of D-3, the sample sizes and bounds, and the D-4 recommendation. After
  Pipec's acceptance, `discard`/`cleanup` with his typed `delete`. `just gate` green; docs touched
  (operator manual: what the new log fields mean; the plan indexes); commit `docs: close plan 0068`;
  PR; merge with Pipec's go-ahead.

## Completion criteria

1. The `Speaker verdict` log carries the clip seconds, the distance and the gate.
2. The report answers the goal with numbers, bounds and the D-4 recommendation; no threshold changed.
3. The private corpus is deleted after Pipec's acceptance; `just gate` green.

## Not here, and why

- Any runtime change to embedding, enrollment or thresholds: the recommendation of Task 5 decides the
  next plan.
- A face-only fallback (removed by Pipec) and a bare «sí» (Plan 0066 decision).

## Execution record

*(Filled in when the plan is executed.)*
