# 0075 — The measurement before CM-4: how often the owner's voice verifies, and whether the embedding model separates Spanish

> **Closed 2026-10-29.** Executed in one session (native, TDD). The instruments (`cm4-corpus`,
> `cm4-voice-rate`, `cm4-embed`) and the Spanish fixture are merged; Pipec recorded two real
> conversations (62 clips) and ran the measurement. Results and the accepted decisions are in
> [the record](../../evals/0075-cm4-pre-measurement.md): owner-voice verified 35.5 % per turn
> (duration-driven; short answers 7 %, questions 0 %), the 1.5 s floor closed (0/12 no-floor matches),
> `nomic-embed-text` separates Spanish at ROC-AUC 0.98 with two 768-d multilingual drop-ins at 1.00
> (follow-up tracked in the roadmap). Pipec accepted the measurement and confirmed the **per-turn**
> eligibility rule. The private corpus was deleted and verified. ADR 0027 stays `Proposed`; the CM-4
> implementation is the next plan.
>
> **For agentic workers (historical):** the plan was `Draft` when written and was executed after Pipec
> authorized it. If you ever reuse it, REQUIRED SUB-SKILLS:
> `superpowers:executing-plans`, `superpowers:test-driven-development`,
> `superpowers:verification-before-completion`, `superpowers:finishing-a-development-branch`. Pipec's
> rules win over any skill: one plain branch from `main`, never a git worktree; subagents only with
> model `sonnet`, after reading `.claude/` in full, on disjoint files and without committing. **An
> agent never opens the microphone, never records, imitates or plays back a voice, and never reads the
> private corpus aloud or into a tracked file; Pipec runs every capture and every live run, and
> Pipec starts the server — the agent never does.** Synthetic audio is allowed. Create and edit files
> with Write and Edit (the Bash of this environment drops backslashes and writes LF into CRLF files).
> Run the suite with `MEMORY_ENABLED=false`. Never run `uv sync --all-packages --all-groups` (it drops
> the optional `cuda` extra). Every finding met while executing is fixed (Pipec's standing policy).

**Status:** `Closed` (2026-10-29; was `Draft`). Written with `superpowers:writing-plans`. It is **measurement only**:
it adds instruments under `scripts/` and a tracked fixture, and changes **nothing** under `server/src`
or `robot/src`, no migration, no new runtime dependency, no new setting. It does **not** change the
status of [ADR 0027](../../adr/0027-conversation-record-and-the-diary.md), which stays `Proposed`; the
plan that implements CM-4 (the record, the jobs, migration 013) flips it to `Accepted` when it closes.
Pipec's seven design decisions of 2026-10-29 are folded in as D-1 to D-7.

**Goal:** Measure, with Pipec's own real conversations, two numbers ADR 0027 said must be known before
CM-4 is built: (1) the fraction of real conversation turns whose clip verifies as the owner's voice,
broken down by clip duration and by phrase type; (2) whether the current embedding model
(`nomic-embed-text`) separates Spanish paraphrases from unrelated Spanish phrases, with a few
multilingual models measured beside it as a reference. Produce a deterministic, reusable instrument
whose output is counts and percentages — never text — and the procedure for Pipec to record the corpus
with the server stopped. From the numbers, propose the eligibility rule of ADR 0027 and leave it as
Pipec's decision; adopting a different embedding model or changing the voice floor are later plans.

**Why:** CM-4 keeps the whole conversation but lets **only the owner's verified turns** feed memory
(ADR 0027 decisions 2 and 3), and it indexes episodes with an embedding model it assumes suits Spanish
(decision 11). Both assumptions rest on one hardware data point each: a 1.9 s clip came back `unknown`
and a 1.6 s clip `verified` (2026-10-28), and the embedding model has never been checked on Spanish.
Building CM-4 on a per-turn rule that in practice passes one turn in three, or indexing episodes with a
model that cannot tell a paraphrase from an unrelated sentence, would be deciding blind. ADR 0027's own
follow-up names this measurement as CM-4's first task.

**Architecture:** Three offline instruments under `scripts/`, each deterministic and each testable with
synthetic inputs, plus one tracked Spanish fixture of invented phrases. (1) A **conversation corpus
tool** records one continuous raw take with the robot's exact capture parameters and cuts it offline,
with the robot's own adopted segmentation (`VAD_SILENCE_MS=1200`, `VAD_UPLOAD_TAIL_MS=300`,
`VAD_PREROLL_MS=400`), into the exact clips the robot would upload; Pipec annotates a coarse phrase type
per clip. (2) A **verified-voice-rate harness** replays each clip through the production voice functions
exactly as the candidate path does (`has_voiced_energy` → `meets_verification_duration` → `embed_wav` →
`centroid_match` → `evaluate_speaker_verification`), against the owner's **real enrolled voiceprint read
from a read-only copy** of the database, and reports the rate by duration bucket and phrase type, per
turn and per conversation. (3) An **embedding-separation instrument** embeds the invented Spanish phrases
through `llm_transport.ollama_embed` (dimension-agnostic on purpose) and reports within-group versus
across-group cosine similarity for each model, with the model's footprint. Nothing reaches the runtime:
the server stays a generic audio API (ADR-0002), and no instrument changes a setting, a threshold or an
enrolment.

**Tech Stack:** Python 3.12, NumPy, `soxr` (already a `server` dependency), SpeechBrain ECAPA on CPU
(the frozen Plan 0047 adapter, already cached under `HF_HUB_OFFLINE=1`), Ollama for embeddings,
faster-whisper is **not** needed (the voice rate is acoustic, not textual), pytest. No new runtime
dependency; the only models pulled are embedding models Pipec chooses with `ollama pull` (D-5).

**Spec:** [ADR 0027](../../adr/0027-conversation-record-and-the-diary.md) decisions 2, 3, 6 and 11 (the
rule for whose turns feed memory, how a turn becomes the owner's, the two retention clocks that depend
on eligibility, and the embedding question), with
[ADR 0016](../../adr/0016-face-and-voice-identity-fusion.md) (voice raises assurance; a verified voice
alone never identifies) and [ADR 0020](../../adr/0020-authorized-actor-in-the-conversation.md) (the
background voice check on a generic turn's own clip). Pipec's seven decisions of 2026-10-29 are D-1 to
D-7 below. The molde for a private-corpus measurement plan is
[Plan 0069](0069-stt-owner-voice-audit.md).

## Evidence base (checked in code on `main`, 2026-10-29)

Nothing here depends on local notes; every fact was read in the source.

- The voice check that CM-4's per-turn rule reuses is `verify_face_and_voice`
  (`server/src/server/cognition/strong_actor.py`): for a face-identified actor it builds
  `build_default_speaker_resolver(wav_bytes, owner_person_id)` and runs
  `SpeakerRequestResolver.resolve_actor`, whose pipeline is, in order,
  `count_voiceprints` → `has_voiced_energy` → `meets_verification_duration` → `embed_wav` →
  `centroid_match` → `evaluate_speaker_verification`
  (`server/src/server/cognition/speaker_authentication.py`). The clip is held only in memory. This is
  exactly the check ADR 0027 decision 3 names.
- `evaluate_speaker_verification` returns `VERIFIED` only with `reference_count >=
  settings.speaker_min_reference_count` (**3**), a cosine distance `<=
  settings.speaker_authentication_match_threshold` (**0.4834**, in-sample from Plan 0047), active
  consent, and the `OWNER` role; every other case is `UNKNOWN`, and a backend failure is `UNAVAILABLE`.
- **A clip shorter than `settings.speaker_min_verification_s` (1.5 s) is rejected by
  `meets_verification_duration` before it is ever embedded** (`server/src/server/voice/speaker_embedding.py`).
  So the `< 1.5 s` bucket is `UNKNOWN` by construction, not by acoustics; the measurement's job there is
  to count how many real turns fall below the floor (lost to memory whatever else is true) and, as a
  diagnostic only (D-1), what the distance would have been if the floor did not exist.
- `has_voiced_energy` rejects a clip whose mean absolute amplitude is at or below the silence floor
  before embedding.
- The embedding model is `settings.embedding_model = "nomic-embed-text"`, 768-d
  (`server/src/server/memory/embeddings.py`, `EMBEDDING_DIM = 768`); `vec_memories` hard-codes
  `float[768]`, and `memory.embeddings.embed` **raises** on any vector that is not 768-d. The lower-level
  `server.llm_transport.ollama_embed(client, text, model=..., timeout=...)` returns whatever dimension
  the model gives, so the instrument calls it directly and computes cosine itself (dimension-agnostic).
- Pipec's runtime (`.env`, 2026-10-29): `SPEAKER_AUTHENTICATION_ENABLED=true`,
  `MEMORY_CANDIDATES_ENABLED=true`, the owner is enrolled (real alta 2026-10-27), robot segmentation is
  `VAD_SILENCE_MS=1200 / VAD_UPLOAD_TAIL_MS=300 / VAD_PREROLL_MS=400`, Whisper is GPU `medium`,
  `EMBEDDING_MODEL=nomic-embed-text`, `HF_HUB_OFFLINE=1`, `BRAIN_DB_PATH=data/omnibot.db`.
- Reusable instrument code already in the tree: `robot/src/robot/audio_capture.py`
  (`segment_utterance`, `SegmentationPolicy.from_settings`, `CHUNK_FRAMES`, `ChunkSource`, Plan 0069);
  `scripts/stt_corpus.py` (`segment_take(raw, policy) -> list[bytes]`, cuts a raw take into the robot's
  clips offline); `scripts/speaker_calibration_corpus.py` (`write_new_file_atomic`,
  `resolve_corpus_path`, `sha256_of_file`). Reuse, do not copy.

## Global Constraints

- **Measurement only.** No file under `server/src` or `robot/src` changes; no migration; no new runtime
  dependency or setting; ADR 0027 stays `Proposed`. The instruments import production functions but
  never mutate the runtime, a threshold, an enrolment or the production database.
- **Private corpus.** Every WAV, manifest and per-clip result lives under
  `project-history/calibration/cm4/` (gitignored, D-6), is never committed, never pasted into a chat,
  never played by an agent, and is deleted at the end after Pipec types `delete`, with the deletion
  verified. Every instrument refuses a corpus root outside that directory.
- **Tracked records carry only aggregates** — counts, rates, distributions, the model footprints — never
  a transcript, a phrase, a phrase-type annotation value tied to text, a name, a distance per clip, or
  any household datum. The embedding fixture is invented canaries and passes
  `scripts/check_reserved_terms.py`.
- **Read the owner voiceprint from a copy.** The voice-rate harness runs with `BRAIN_DB_PATH` pointed at
  a copy of the database opened read-only (`immutable=1`, no `-wal`/`-shm` sidecar on the original); it
  reads counts and the centroid math, never a stored value, and never the live production file.
- **Audio contract** at every boundary: WAV, 16 000 Hz, mono, int16; every function that touches audio
  says so in its docstring. A capture at another rate is converted with `soxr` before it becomes a WAV.
  Offline segmentation uses the robot's real adopted policy (1200 / 300 / 400), so a scored clip is
  byte-identical to what the robot uploads today.
- **The agent never starts the server or the robot and never records.** Pipec prepares the laptop, stops
  the server for the voice-rate run, keeps Ollama up for the embedding run, and runs every capture.
- **Fixed threshold and baseline model.** The harness scores at the fixed 0.4834 and the baseline
  `nomic-embed-text`; it changes no setting. Adopting a different voice floor or embedding model is a
  later plan.
- **Lint and commits.** `uv run ruff check` and `uv run ruff format --check` over explicit paths that
  include `scripts/` (the repository config skips `scripts/` but the pre-commit hook does not) and the
  Python blocks of this document; `uv run mypy server/src robot/src` clean; `uv run python
  scripts/check_reserved_terms.py` clean; `just gate` green before any PR; commit titles at most 72
  characters (count them, then check `git log -1`); `git add` with explicit paths; never pipe
  `git commit`.

## Review Focus

1. The voice-rate harness reads the owner centroid from a **copy** opened `immutable=1`; it never opens
   the live `data/omnibot.db` and leaves no `-wal`/`-shm` sidecar beside the original (Task 3).
2. Every tracked output is counts and rates only: a sentinel phrase typed during `annotate` and a
   sentinel distance never appear in the report, the JSON results or any log (assert the sentinels are
   absent) (Tasks 1, 3 and 5).
3. The corpus tool refuses any root outside `project-history/calibration/cm4/` **before** it records or
   writes, `cleanup` deletes only after the typed answer is exactly `delete`, and `git status` never
   lists a file under `project-history/` (Tasks 2 and 6).
4. The embedding instrument embeds through `ollama_embed` directly, so a non-768-d model is **measured**
   (its dimension recorded) and never rejected; a model that is not pulled is skipped with a clear line,
   never a crash (Task 4).
5. A clip below 1.5 s is reported as `UNKNOWN` with gate `duration`, and the no-floor diagnostic distance
   sits in a separate column labelled "if the floor did not exist — not a proposal"; a silent clip is
   gate `energy`; neither is ever counted as a verified owner turn (Tasks 1 and 3).

## Decisions (Pipec, 2026-10-29)

1. **D-1 — The sub-1.5 s diagnostic (point 1 = B).** For clips shorter than `speaker_min_verification_s`,
   the harness also embeds the clip and computes its owner distance, bypassing the duration gate, and
   reports whether it would have matched — in a separate column clearly labelled a diagnostic, never a
   proposal. This tells a later plan whether lowering the floor would recover turns; it changes nothing.
2. **D-2 — Both rates, the rule is Pipec's (point 2).** The report gives both the **per-turn** rate (a
   turn is the owner's when its own clip verifies) and the **per-conversation** aggregate (how many clips
   per conversation verify, and the share of conversations with at least one verified turn). The plan
   then proposes the eligibility rule of ADR 0027 decision 2/3 — per turn, or per conversation if the
   per-turn rate is too low — with the numbers; **Pipec decides**, the plan builds nothing.
3. **D-3 — Five coarse phrase types (point 3).** Each clip is annotated by Pipec with exactly one of:
   `short_answer` (sí/no/autorizo…), `taste_statement`, `question`, `command`, `other`. The annotation
   stays in the private corpus; the tracked report carries only counts per type × verdict.
4. **D-4 — Invented canary fixture (point 4).** The embedding phrases are invented Chilean-neutral
   Spanish, tracked as `tests/evals/cm4_embedding_phrases.yaml`, reviewed and editable by Pipec before
   the run, and they pass `check_reserved_terms`. No real household data, ever.
5. **D-5 — Embedding models: pull what fits, measure what is present, record the footprint (point 5).**
   The baseline `nomic-embed-text` (768-d) is required. Beside it, the instrument measures whichever of a
   shortlist Pipec has pulled, each run isolated with the server stopped so runtime RAM is not the
   binding constraint during measurement. The shortlist, from the 2026-10-29 research below, prefers
   **768-d drop-in** candidates (no `vec_memories` migration): `embeddinggemma:300m`,
   `granite-embedding:278m`, `paraphrase-multilingual:278m`; and names two **1024-d reference ceilings**
   (a migration would be needed to adopt, so reference only): `qwen3-embedding:0.6b`, `bge-m3`. The
   report records, per model, its output dimension, the size Ollama reports and the resident memory while
   embedding, beside its separation score, so a later adoption plan has the RAM number in hand. Nothing
   is adopted here. The instrument measures whatever models are present and skips the rest with a clear
   line.
6. **D-6 — Corpus root (point 6).** `project-history/calibration/cm4/`, a new directory beside
   `calibration/stt/` and `calibration/speaker/`, with `takes/`, `clips/`, `references/` (option A of
   D-7 only), `manifest.jsonl`, `results/` and `report.md`.
7. **D-7 — Centroid from the real enrolled voiceprint (point 7 = B).** The harness scores against the
   owner's real enrolled voiceprint, read from a **read-only copy** of `data/omnibot.db` (`immutable=1`),
   reusing `count_voiceprints` and `centroid_match`, so the verdict is the exact production verdict. As a
   fallback only, option A captures reference clips in the same session and builds a centroid from them;
   the report states which source was used. Pipec makes the copy; the agent never touches the live DB.
8. **D-8 — Statistics.** Rates are pooled (the sum of verified clips over the sum of clips, never a mean
   of per-conversation rates). Each rate carries a 95 % interval; a zero cell gets the rule-of-three
   bound; every table states its n. Conversations are the resampling unit for the per-conversation
   interval (turns within one conversation are correlated). Cosine similarity within versus across groups
   is reported as a distribution with the separation (mean within − mean across) and the overlap
   (ROC-AUC of within-group against across-group pairs).
9. **D-9 — What Pipec decides, and the next plan.** From the record Pipec decides (a) the eligibility
   rule (per turn or per conversation, with the measured numbers); (b) whether the sub-1.5 s floor is
   worth a later plan; (c) whether an embedding model swap is worth a later plan, and which, with its
   footprint. The **next plan** is the CM-4 implementation (the conversation record, the episode and
   candidate jobs, migration 013), which is out of scope here and flips ADR 0027 to `Accepted` when it
   closes.

## Embedding-model research (2026-10-29, recorded so a later plan does not repeat it)

The question is only decision 11's: does `nomic-embed-text` separate Spanish paraphrases from unrelated
Spanish? Spanish-specific embedding models are **few**, and the best-documented ones
(`jina-embeddings-v2-base-es`, `bilingual-embedding-large`, `jina-embeddings-v3`) are distributed on
Hugging Face, not as simple Ollama pulls; with `HF_HUB_OFFLINE=1` they are out of reach for this
measurement, and `jina-embeddings-v3` carries a non-commercial licence. The practical path is a strong
multilingual model that does Spanish well, pulled through Ollama. From 2025–2026 MTEB-multilingual
roundups and a 2026 robustness study of the Spanish retrieval task:

- `qwen3-embedding:0.6b` — among the strongest small models for Spanish per the robustness study;
  **1024-d**, so adopting it needs a `vec_memories` migration. Reference ceiling here.
- `bge-m3` — a solid, widely used multilingual baseline; **1024-d**, migration needed. Reference ceiling.
- `embeddinggemma:300m` — Google, 2025; **768-d** (Matryoshka), multilingual; a drop-in by dimension.
- `granite-embedding:278m` — IBM; **768-d**, multilingual; drop-in by dimension.
- `paraphrase-multilingual:278m` — sentence-transformers paraphrase model; **768-d**, specialised for
  paraphrase similarity; drop-in by dimension.
- `nomic-embed-text` — the current baseline; **768-d**, English-centric but functional on Spanish.

Pipec's observation holds: the most-used models (nomic, bge-m3) are the best maintained, but for a
drop-in without migration the dimension (768) decides. The averages above are across many languages, so
they only rank candidates; this plan's own measurement on invented Spanish phrases is what decides
whether the question is open. Exact Ollama tags and sizes must be confirmed at `ollama pull` time, since
the library changes; a broader survey of newer Spanish-capable models is itself follow-up work, not part
of this plan.

Sources: [bentoml 2026 open-source embeddings](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models),
[MTEB multilingual robustness study](https://arxiv.org/html/2605.31142v1),
[Granite Embedding report](https://arxiv.org/pdf/2502.20204),
[Jina Spanish-English embeddings](https://jina.ai/news/aqui-se-habla-espanol-top-quality-spanish-english-embeddings-and-8k-context),
[premai best embedding models for RAG 2026](https://www.premai.io/blog/best-embedding-models-for-rag-2026-ranked-by-mteb-score-cost-and-self-hosting/).

## Required reading

- `CLAUDE.md` and `.claude/rules/` (all; not tracked — read them from the working copy),
  `docs/architecture/implementation-guardrails.md`.
- [ADR 0027](../../adr/0027-conversation-record-and-the-diary.md) (decisions 2, 3, 6, 11 and the
  follow-up), [ADR 0016](../../adr/0016-face-and-voice-identity-fusion.md),
  [ADR 0020](../../adr/0020-authorized-actor-in-the-conversation.md).
- [Plan 0069](0069-stt-owner-voice-audit.md) (the private-corpus molde) and the operator
  manual's speaker-calibration and STT-bench sections (`docs/runbooks/operator-manual.md`).
- `server/src/server/cognition/strong_actor.py`,
  `server/src/server/cognition/speaker_authentication.py`,
  `server/src/server/voice/speaker_embedding.py`, `server/src/server/voice/voiceprints.py`,
  `server/src/server/memory/candidate_proposal.py`, `server/src/server/memory/embeddings.py`,
  `server/src/server/llm_transport.py` (`ollama_embed`), `server/src/server/settings.py`,
  `robot/src/robot/audio_capture.py`, `scripts/stt_corpus.py`,
  `scripts/speaker_calibration_corpus.py`, `justfile`.

## Task overview

| # | Task | Owner | RED? |
|---:|---|---|:---:|
| 0 | Revalidate the baseline | agent | — |
| 1 | The verified-voice verdict harness (pure replay of the production pipeline) | agent | yes |
| 2 | The conversation corpus tool (capture, offline segment, annotate, validate, cleanup) | agent | yes |
| 3 | The voice-rate report (buckets, phrase types, per-conversation, intervals) | agent | yes |
| 4 | The embedding-separation instrument and the invented Spanish fixture | agent | yes |
| 5 | Capture, runs and the evaluation record | Pipec + agent writes record | — |
| 6 | Documentation and cleanup | agent + Pipec | — |

---

## Task 0: Revalidate the baseline

- [ ] **Step 1:** branch `docs/0075-cm4-measurement-plan` already holds this plan; for execution, a plan
  branch `feat/0075-cm4-pre-measurement` from `main`. Run `just gate` and record the count.
- [ ] **Step 2:** confirm the named seams exist and the values match this plan:
  `rg -n "def evaluate_speaker_verification|def meets_verification_duration|def has_voiced_energy|def clip_duration_s|def embed_wav|def centroid_match|def count_voiceprints|def verify_face_and_voice|def ollama_embed|def segment_utterance|def segment_take" server/src robot/src scripts`;
  and `rg -n "speaker_min_verification_s|speaker_authentication_match_threshold|speaker_min_reference_count|embedding_model|EMBEDDING_DIM" server/src/server`.
  Expected: `speaker_min_verification_s = 1.5`, `speaker_authentication_match_threshold = 0.4834`,
  `speaker_min_reference_count = 3`, `embedding_model = "nomic-embed-text"`, `EMBEDDING_DIM = 768`.
- [ ] **Step 3:** if anything differs, **stop and report the exact evidence** instead of adjusting the
  plan. A mismatch between ADR 0027 and the code is a conflict to raise, not to redesign around.

## Task 1: The verified-voice verdict harness

**Files:** `scripts/cm4_voice_rate.py` (new), `scripts/cm4_models.py` (new, the dataclasses); test
`tests/unit/test_cm4_voice_rate.py` (new).

The harness replays one clip through the **production** pipeline, in the same order as
`SpeakerRequestResolver._resolve`, reusing the production functions — it does not re-implement the
decision. It classifies the clip into a duration bucket and records the gate that stopped it and the
production verdict. For a sub-1.5 s clip it also computes the no-floor diagnostic distance (D-1).

**Interfaces — Produces** in `cm4_models.py`:
- `type DurationBucket = Literal["lt_1_5", "1_5_to_3", "gt_3"]`.
- `@dataclass(frozen=True) class ClipVerdict(duration_s: float, bucket: DurationBucket, gate: str,
  verdict: str, phrase_type: str, no_floor_distance: float | None, no_floor_would_match: bool | None)` —
  `gate` is the first failed gate name from `speaker_authentication._first_failed_gate`'s vocabulary
  (`unavailable`, `references`, `energy`, `duration`, `distance`, `consent`, `role`, `ok`); `verdict` is
  a `SpeakerVerdict` value; the two `no_floor_*` fields are set only for the `lt_1_5` bucket.

**Interfaces — Produces** in `cm4_voice_rate.py`:
- `def duration_bucket(duration_s: float) -> DurationBucket` — `< 1.5`, `[1.5, 3]`, `> 3`.
- `async def score_clip(wav_bytes: bytes, phrase_type: str, *, owner_person_id: int, model_id: str,
  embed: Embedder, match: CentroidMatcher, count_refs: ReferenceCounter) -> ClipVerdict` — mirrors the
  production order; `embed`, `match`, `count_refs` are the production functions in composition and test
  doubles in the unit test; it forces `consent_active=True` and `role=OWNER` (the corpus is the enrolled
  owner's own voice, read from the owner's own DB copy) so the verdict isolates the acoustic question.
- `def aggregate(verdicts: Sequence[ClipVerdict]) -> CountTable` — pure counts, no text.

- [ ] **Step 1 — failing tests.** `duration_bucket(1.49) == "lt_1_5"`, `duration_bucket(1.5) ==
  "1_5_to_3"`, `duration_bucket(3.0) == "1_5_to_3"`, `duration_bucket(3.01) == "gt_3"`. With synthetic
  WAVs and fake `embed`/`match`/`count_refs`: a loud 0.8 s clip → `bucket "lt_1_5"`, `gate "duration"`,
  `verdict "unknown"`, and `no_floor_distance` is the fake distance with `no_floor_would_match` from
  `distance <= 0.4834`; a silent 2 s clip → `gate "energy"`, `verdict "unknown"`, `no_floor_* is None`; a
  2 s clip with distance 0.30 → `gate "ok"`, `verdict "verified"`; a 2 s clip with distance 0.60 → `gate
  "distance"`, `verdict "unknown"`; fewer than 3 references → `gate "references"`. `aggregate` over a
  fixed list returns the expected per-bucket and per-type counts and never a float distance. RED:
  `score_clip` does not exist.
- [ ] **Step 2 — run:** `uv run pytest tests/unit/test_cm4_voice_rate.py -v`. Expected: FAIL (module
  missing).
- [ ] **Step 3 — implement** `score_clip` by calling `has_voiced_energy`, `meets_verification_duration`,
  `clip_duration_s`, `embed_wav`/`centroid_match` and `evaluate_speaker_verification` from the server
  package; the no-floor branch embeds and matches a sub-1.5 s clip that passed the energy gate. Document
  the audio contract in every docstring.
- [ ] **Step 4 — run** the test file: PASS. `uv run ruff check scripts/cm4_voice_rate.py
  scripts/cm4_models.py tests/unit/test_cm4_voice_rate.py`; `uv run ruff format --check` on the same;
  `uv run mypy server/src robot/src`.
- [ ] **Step 5 — commit** `feat(scripts): cm4 verified-voice verdict harness`.

## Task 2: The conversation corpus tool

**Files:** `scripts/cm4_corpus.py` (new), `justfile` (`cm4-corpus`); test `tests/unit/test_cm4_corpus.py`
(new). Reuse, do not copy: `segment_utterance`, `SegmentationPolicy.from_settings`, `CHUNK_FRAMES`,
`ChunkSource` from `robot.audio_capture`; `segment_take` from `scripts/stt_corpus.py`;
`write_new_file_atomic`, `resolve_corpus_path`, `sha256_of_file` from
`scripts/speaker_calibration_corpus.py`.

**Interfaces — Produces:** `DEFAULT_CM4_CORPUS_ROOT = Path("project-history/calibration/cm4")`;
`@dataclass(frozen=True) class ClipRecord(clip_id: str, session: str, duration_s: float, phrase_type:
str, sha256: str)` (no text field ever); `def append_clip(manifest: Path, root: Path, record:
ClipRecord) -> None`; `def load_clips(manifest: Path, root: Path) -> list[ClipRecord]`; a CLI with the
subcommands below. Every path is resolved through `resolve_corpus_path` against
`DEFAULT_CM4_CORPUS_ROOT`, which refuses any root outside it.

CLI (through `just cm4-corpus <subcommand>`, all free-text arguments `nargs="+"`):
- `capture-conversation --session S --minutes N` — opens the default input with the robot's exact
  parameters (16 kHz, mono, int16, `blocksize=CHUNK_FRAMES`, no `device=`), settles the stream and
  discards the first 0.5 s before anything is shown, a **visual-only** cue, records one continuous raw
  take to `takes/`.
- `capture-reference --session S` (option A fallback of D-7 only) — the same capture for a short
  reference phrase, saved under `references/`.
- `segment --session S` — cuts each raw take offline with `segment_take(raw,
  SegmentationPolicy.from_settings())` (the robot's adopted 1200 / 300 / 400), writes each clip to
  `clips/`, appends one manifest line per clip with no phrase type yet.
- `annotate --session S` — plays each clip to Pipec, who types exactly one of the five phrase types
  (D-3); writes the type into the manifest; the typed text of what was said is **never** stored.
- `validate` — checks files, hashes, that every clip has a phrase type from the closed set, and the
  counts per session; `check_reserved_terms` passes on every tracked file the tool writes.
- `cleanup` — deletes every private artifact only after the typed answer is exactly `delete`.

- [ ] **Step 1 — failing tests** (fake recorder and fake VAD, no microphone): `segment` on a raw take
  with two speech bursts 2.0 s apart gives two clips, and 0.5 s apart gives one clip (the pause is below
  the 1200 ms closing silence); a silent take gives `[]`; a burst that reaches the end of the take still
  yields one clip. A clip round-trips through the manifest with its hash; `resolve_corpus_path` refuses a
  root outside `project-history/calibration/cm4/` before any write; `annotate` rejects a phrase type
  outside the closed set; `cleanup` deletes nothing unless the typed answer is exactly `delete`; the
  capture path with a fake recorder saves the raw take and appends no text. RED: nothing exists.
- [ ] **Step 2 — run:** `uv run pytest tests/unit/test_cm4_corpus.py -v`. Expected: FAIL.
- [ ] **Step 3 — implement** the CLI and the `just cm4-corpus` recipe (ASCII-only `@echo`, no quotes in
  usage examples, per `.claude/rules/scripts-powershell.md`). Logging, not `print`, except a final
  summary table (`# noqa: T201` with the reason).
- [ ] **Step 4 — run** the test; `uv run ruff check`/`format --check` on explicit paths; `uv run python
  scripts/check_reserved_terms.py`.
- [ ] **Step 5 — commit** `feat(scripts): cm4 private conversation corpus tool`.

## Task 3: The voice-rate report

**Files:** `scripts/cm4_voice_rate.py` (extend), `scripts/cm4_stats.py` (new, pure statistics); test
`tests/unit/test_cm4_voice_rate_report.py` (new), `tests/unit/test_cm4_stats.py` (new).

**Interfaces — Produces** in `cm4_stats.py`: `def wilson_interval(successes: int, n: int) -> tuple[float,
float]`; `def rule_of_three(n: int) -> float`; `def pooled_rate(successes: int, n: int) -> float`; `def
bootstrap_by_conversation(per_conversation: Sequence[tuple[int, int]], *, resamples: int = 2000, seed:
int = 75) -> tuple[float, float]`. In `cm4_voice_rate.py`: `report` subcommand that reads the manifest
(Task 2), opens the owner voiceprint from the read-only DB copy (D-7), scores every clip (Task 1), and
writes `results/voice_rate.json` and a human table — both **aggregates only**.

The report contains: per duration bucket × verdict counts and pooled rate with its interval; per phrase
type × verdict; the sub-1.5 s no-floor diagnostic column (how many sub-1.5 s clips would have matched if
the floor did not exist), clearly labelled not a proposal; the **per-turn** verified rate and the
**per-conversation** aggregate (verified clips per conversation, and the share of conversations with at
least one verified turn), with the by-conversation bootstrap interval; the centroid source used (real
voiceprint, or in-session references); and every table's n. No distance, no text.

- [ ] **Step 1 — failing tests.** `pooled_rate(3, 12) == 0.25`; `rule_of_three(18)` ≈ `0.1667`;
  `wilson_interval` matches a hand-computed value on a small case; `bootstrap_by_conversation` is
  deterministic under the fixed seed and returns a low ≤ high pair. `report` over a **synthetic** manifest
  of `ClipVerdict`s (no audio) writes a JSON whose buckets, phrase types, per-turn and per-conversation
  figures match hand counts, and whose text contains neither a sentinel phrase nor any float distance
  (assert both sentinels absent). RED: `report` and the stats module do not exist.
- [ ] **Step 2 — run:** `uv run pytest tests/unit/test_cm4_voice_rate_report.py tests/unit/test_cm4_stats.py -v`.
  Expected: FAIL.
- [ ] **Step 3 — implement** the stats functions and the `report` subcommand; open the DB copy with
  `immutable=1` and reuse `count_voiceprints`/`centroid_match`; refuse to run against a path equal to the
  live `BRAIN_DB_PATH`.
- [ ] **Step 4 — run** the tests; lint and types over explicit paths.
- [ ] **Step 5 — commit** `feat(scripts): cm4 voice-rate report and statistics`.

## Task 4: The embedding-separation instrument and the Spanish fixture

**Files:** `tests/evals/cm4_embedding_phrases.yaml` (new, invented canaries, D-4),
`scripts/cm4_embed_separation.py` (new), `justfile` (`cm4-embed`); test
`tests/unit/test_cm4_embed_separation.py` (new).

The fixture holds several **groups**; each group has an `id`, an `anchor` and at least two `paraphrases`
(near), all invented Chilean-neutral Spanish about tastes, home and the time — never real household data.
Phrases of different groups are the unrelated (far) pairs. The instrument embeds every phrase through
`llm_transport.ollama_embed` for each `--model` given (dimension-agnostic), computes cosine similarity,
and reports within-group versus across-group distributions, the separation and the overlap (D-8), plus
each model's output dimension, the size Ollama reports and the resident memory while embedding (D-5).

**Interfaces — Produces:** `def load_phrases(path: Path) -> tuple[PhraseGroup, ...]` (validates unique
ids, ≥ 2 paraphrases per group, ≥ 6 groups); `def cosine(a: Sequence[float], b: Sequence[float]) ->
float`; `def separation(within: Sequence[float], across: Sequence[float]) -> SeparationReport` with the
means, the difference and the ROC-AUC of within against across; `async def embed_fixture(client:
httpx.AsyncClient, groups: Sequence[PhraseGroup], *, model: str) -> dict[str, list[float]]`.

- [ ] **Step 1 — failing tests.** `load_phrases` on the real YAML: structure valid and
  `check_reserved_terms` passes on the file. `cosine` of two known vectors matches a hand value.
  `separation` on a constructed case where within-group pairs are near 0.9 and across near 0.2 reports a
  positive difference and an ROC-AUC of 1.0; on fully overlapping inputs, 0.5. With a fake embedder
  (deterministic vectors per phrase), the end-to-end report groups and scores correctly and records the
  dimension. RED: the module does not exist.
- [ ] **Step 2 — run:** `uv run pytest tests/unit/test_cm4_embed_separation.py -v`. Expected: FAIL.
- [ ] **Step 3 — implement** the instrument and `just cm4-embed --model M [--model M2 ...]` (it skips a
  model that is not pulled with a clear line, never a crash); it calls `ollama_embed` directly, not
  `memory.embeddings.embed` (which rejects non-768-d). Write the invented fixture; Pipec reviews it in
  Task 5.
- [ ] **Step 4 — run** the test; `uv run ruff check`/`format --check` on explicit paths; `uv run python
  scripts/check_reserved_terms.py`.
- [ ] **Step 5 — commit** `feat(scripts): cm4 Spanish embedding separation instrument`.

## Task 5: Capture, runs and the evaluation record (Pipec runs; the agent writes the record)

**Files:** `docs/evals/0075-cm4-pre-measurement.md` (new, aggregates only).

- [ ] **Step 1 (Pipec):** make a **read-only copy** of `data/omnibot.db` under
  `project-history/calibration/cm4/` (or point `BRAIN_DB_PATH` at a copy). Record one or more
  spontaneous conversation sessions with `just cm4-corpus capture-conversation` (server stopped), then
  `segment` and `annotate`. Review and edit `tests/evals/cm4_embedding_phrases.yaml`. Pull the embedding
  models the machine tolerates (`ollama pull nomic-embed-text` is already present; then any of
  `embeddinggemma:300m`, `granite-embedding:278m`, `paraphrase-multilingual:278m`,
  `qwen3-embedding:0.6b`, `bge-m3`).
- [ ] **Step 2 (Pipec):** run `just cm4-voice-rate report` (server stopped, against the DB copy) and
  `just cm4-embed --model ...` (Ollama up) for each pulled model; paste the aggregate output.
- [ ] **Step 3 (agent):** write `docs/evals/0075-cm4-pre-measurement.md` with the machine conditions, the
  voice-rate tables (per bucket, per phrase type, per turn, per conversation, the no-floor diagnostic,
  with intervals and n), and the embedding tables (separation and footprint per model). Aggregates only —
  no transcript, phrase, distance or household datum.
- [ ] **Step 4 (agent):** add to the record a section **"What Pipec decides"** that states the proposed
  eligibility rule with the measured per-turn and per-conversation numbers (D-2), and the open questions
  of D-9 (the sub-1.5 s floor, an embedding model swap), each with its number.

## Task 6: Documentation and cleanup

**Files:** `docs/runbooks/operator-manual.md`, `docs/plans/README.md`, `docs/plans/open/README.md`, and
(Pipec) the corpus deletion.

- [ ] **Step 1 (agent):** add an operator-manual subsection for `just cm4-corpus`, `just cm4-voice-rate`
  and `just cm4-embed` — their privacy rules (corpus root, counts only, the agent never records), the DB
  copy, and that the server is stopped for the voice-rate run. State explicitly that CM-4's
  implementation (the record, the jobs, migration 013) is the **next** plan and out of scope here, and
  that ADR 0027 stays `Proposed` until it closes.
- [ ] **Step 2 (agent):** move this plan to `completed/` and update the plan indexes only when the record
  is accepted (queue rule 3).
- [ ] **Step 3 (Pipec):** `just cm4-corpus cleanup` and type `delete`; delete the DB copy; confirm `git
  status` lists no file under `project-history/`.
- [ ] **Step 4 (agent):** `just gate` green; the PR carries only `scripts/`, `tests/`, `docs/` and
  `justfile` changes, and nothing under `server/src` or `robot/src`.

## Non-goals

- The conversation record, the episode and candidate jobs, and migration 013 — that is the CM-4
  implementation plan, which this measurement precedes.
- Changing `speaker_min_verification_s`, the 0.4834 threshold, the enrolment, or any embedding model in
  the runtime. The sub-1.5 s diagnostic and the embedding separation only measure.
- Speaker separation, several enrolled speakers, intonation, a face-only fallback (later stages).
- A broader survey of newer Spanish embedding models beyond the shortlist (its own follow-up).

## Verification commands

```powershell
uv run pytest tests/unit/test_cm4_voice_rate.py tests/unit/test_cm4_corpus.py tests/unit/test_cm4_voice_rate_report.py tests/unit/test_cm4_stats.py tests/unit/test_cm4_embed_separation.py -v
uv run ruff check scripts tests
uv run ruff format --check scripts tests
uv run mypy server/src robot/src
uv run python scripts/check_reserved_terms.py
just gate
```

## Exit criteria

1. Tasks 1–4 land with each test RED before GREEN; `just gate` is green and no file under `server/src`
   or `robot/src`, no migration, no new runtime dependency or setting changed.
2. The three instruments run, with output that is counts and percentages only; the corpus tool refuses a
   root outside `project-history/calibration/cm4/` and `cleanup` needs the typed `delete`.
3. `docs/evals/0075-cm4-pre-measurement.md` records the voice-rate numbers (by bucket, phrase type, per
   turn, per conversation, the no-floor diagnostic, with intervals) and the embedding separation and
   footprint per measured model — aggregates only.
4. The record proposes the eligibility rule with the numbers and leaves it, the sub-1.5 s floor and the
   embedding swap as Pipec's decisions, and names the CM-4 implementation as the next plan.
5. The private corpus and the DB copy are deleted and the deletion verified; `git status` lists nothing
   under `project-history/`.
