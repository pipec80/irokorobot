# Speaker-Evidence Calibration Study Implementation Plan

> **For future agentic workers:** REQUIRED SUB-SKILL after this plan is
> promoted to `Ready`: use `superpowers:using-git-worktrees`, then
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans`. Use `superpowers:test-driven-development` for
> each behavior, `superpowers:systematic-debugging` for failures,
> `superpowers:verification-before-completion` before claims, and
> `superpowers:requesting-code-review` for independent review. Pipec—not an
> agent—owns every real microphone, impostor and replay capture checkpoint.

**Status:** Queued — reviewed 2026-09-07, not executable. Plan 0046 (CM-0)
closed 2026-09-08, clearing the sequencing blocker; the readiness blockers
below must still be resolved in a reviewed amendment, and Pipec must explicitly
approve promotion to `Ready`, before any code, dependency download or
real-voice capture begins.

**Goal:** Evaluate whether a local CPU speaker-embedding backend can separate
Pipec's live voice from consenting live impostors under household conditions;
measure false accepts, false rejects, replay behavior and latency; and either
select an evidence-based candidate for a later PC-3B runtime plan or close the
study honestly as FAIL. This plan does not enroll a production voiceprint and
does not make `VOICE` trusted identity evidence.

**Architecture — three isolated layers:**

1. **Pure numeric harness:** strict sample metadata, L2 normalization,
   reference centroid, cosine distance, threshold sweep, FAR/FRR and latency
   percentiles. Unit tests use synthetic vectors and never load a model.
2. **Replaceable evaluation backend:** one protocol accepts validated WAV bytes
   and returns one finite, fixed-dimension embedding. The concrete model,
   version, revision, license, preprocessing and installation command are
   frozen by the readiness amendment before this plan can become `Ready`.
3. **Operator-owned temporary corpus:** real WAV files and derived embeddings
   stay under a gitignored calibration directory, use pseudonyms, and are
   deleted after an aggregate privacy-reviewed report is accepted. The harness
   and schema are reproducible; household voices are deliberately not.

**Tech stack after readiness:** Python 3.12, numpy, current WAV validation and
microphone capture, a locally cached CPU speaker-embedding backend selected by
the readiness gate, pytest, Ruff, mypy and `just`. No cloud inference is
allowed.

**Spec:** [Plan 0015 PC-3](0015-personal-companion-design.md),
[identity and access](../../architecture/identity-and-access.md),
[current state](../../architecture/current-state.md),
[ADR 0006](../../adr/0006-personal-and-family-companion-profiles.md).

## Why this plan is queued

The repository currently has no speaker-recognition code, voiceprint schema,
speaker enrollment, diarization or selected dependency. `IdentityEvidenceSource.VOICE`
exists, but the trusted-source set excludes it and tests require voice-only
input to remain `UNKNOWN`. STT and VAD identify speech activity/content, not a
speaker.

One concrete study candidate exists: SpeechBrain `1.1.1`. Its official
[`SpeakerRecognition` source at tag v1.1.1](https://github.com/speechbrain/speechbrain/blob/v1.1.1/speechbrain/inference/speaker.py)
exposes speaker embedding/verification, and the Apache-2.0 ECAPA-TDNN model is
frozen to revision
[`0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb/commit/0f99f2d0ebe89ac095bcc5903c4dd8f72b367286).
The [SpeechBrain 1.1.1 package record](https://pypi.org/project/speechbrain/1.1.1/)
declares Python `>=3.8.1` and Apache-2.0, but that is only research evidence:
the package/model have not been installed or validated on this repository's
Windows, Python 3.12 and CPU environment. Its generic score threshold is not a
household authorization threshold.

The candidate may fail technically during the authorized study. Before
promotion, a documentation-only amendment must freeze the exact v1.1.1 call,
tensor/array shape, cache path and preprocessing from pinned primary sources.
No implementer may choose another backend while executing this plan.

## Readiness blockers and promotion gate

No task in this file may execute while it is `Queued`. Promotion work is
documentation-only and must complete all items below without installing a
package, downloading a model or capturing audio:

- [x] Plan 0046 is closed (2026-09-08). Refresh live branch/SHA/status once its
  PR (#122) merges to `main` before promotion.
- [ ] A read-only researcher refreshes the three pinned primary sources above
  and records any version/license/API/security drift. A material change keeps
  the plan queued for redesign.
- [ ] Amend the plan with the exact `SpeakerRecognition` construction and
  embedding calls, input tensor shape/dtype, output shape, conversion from
  validated PCM int16 to float waveform, CPU device selection, immutable model
  revision argument and offline cache behavior. There may be no free adapter
  choice afterward.
- [ ] Freeze the root development dependency command, expected root
  `pyproject.toml`/`uv.lock` scope and rollback. Development groups belong at
  the workspace root; no subproject receives this study dependency.
- [ ] Freeze the three literal neutral Spanish phrases and a numeric p95 CPU
  feasibility budget chosen by Pipec before measurement. The result must be
  compared with that precommitted budget, not one selected after seeing data.
- [ ] Freeze the latency protocol: one already-loaded backend; one generated
  three-second WAV at 16 kHz mono int16; file I/O and WAV validation outside
  timing; three warm-up embeddings; then 30 sequential embeddings timed with
  `perf_counter`; nearest-rank p50/p95; no concurrent load or model download.
  Task 6 additionally reports per-real-sample embedding latency but does not
  retroactively change this technical feasibility gate.
- [ ] Freeze exact model-contract, capture, validate, analyze and cleanup
  commands using the stable CLI contract below.
- [ ] Pipec explicitly approves testing SpeechBrain `1.1.1` plus the pinned
  model, including package/model downloads and the possibility of a technical
  FAIL before any household capture.
- [ ] Run an independent plan review. Only then change `Status` to `Ready`, put
  0047 in `NOW`, and obtain explicit implementation authorization.

If Pipec declines the candidate, the plan remains queued or is cancelled by an
explicit roadmap decision; that is not measured FAIL. After promotion, a real
compatibility/backend failure is an evidence-complete technical FAIL and may
close the study without collecting household voices.

## Required reading after promotion

Before editing, read completely:

1. `AGENTS.md`, every `.claude/rules/` file, `docs/plans/README.md`, and the
   promoted version of this plan;
2. every document under **Spec**;
3. `server/src/server/audio_contract.py`,
   `robot/src/robot/audio_capture.py`, and `scripts/mic_test.py`;
4. `server/src/server/cognition/identity.py` and
   `tests/unit/test_active_person_identity.py`;
5. `scripts/face_calibration.py`,
   `tests/unit/test_face_calibration.py`, and `justfile` as current code reuse,
   not as normative dependence on its completed plan;
6. `server/pyproject.toml`, `robot/pyproject.toml`, root `pyproject.toml`, and
   the selected backend's frozen primary documentation.

The implementer must follow the root `pyproject.toml` marker definitions when
they conflict with stale prose elsewhere: pure vector/math tests are `unit`,
real backend tests are `slow`, microphone capture is `hardware`, and quality
measurement is `eval`.

## Global constraints

- This is PC-3A evaluation only. PC-3 remains open for a separately reviewed
  PC-3B enrollment/runtime plan even if this study passes.
- Do not modify `server/src/`, `robot/src/`, identity trusted sources,
  authorization, tokens, routes, settings, migrations, databases, prompts or
  the server/robot boundary.
- Do not produce `IdentityEvidence`, persist a voiceprint, create enrollment or
  revocation APIs, or grant any capability from a score.
- Every function that accepts, reads, records or validates audio states in its
  docstring: WAV, 16,000 Hz, mono, signed int16. Reject mismatches; do not
  silently reinterpret bytes.
- Use the existing real microphone capture implementation after promotion.
  Scripts may import the robot adapter as existing calibration tools do, but
  runtime packages may not import each other.
- All real participants give explicit consent. Use pseudonyms such as
  `owner`, `impostor_a`, never names. No child or non-consenting person is used.
- Agents never record, imitate, synthesize, transform or replay a person's
  voice. Pipec performs and confirms each physical operation.
- Raw WAV, manifests containing local paths, embeddings and per-sample scores
  live only under `project-history/calibration/speaker/`, which is gitignored.
  They are never staged, pasted into chat, attached to a PR or cited by a
  tracked path.
- The tracked closure section in this plan contains only aggregate counts/rates,
  condition labels, selected threshold, model metadata, latency summaries and
  limitations. It
  contains no names, transcripts, hashes linkable to retained samples,
  embeddings or absolute local paths.
- Reference and probe sessions are distinct. Phrase/session leakage is
  reported and prevented by the corpus validator.
- Live impostor acceptance is the safety gate. Any threshold with a measured
  false accept is ineligible. If genuine and live-impostor distances overlap so
  no zero-observed-FAR threshold exists, result is FAIL; never trade safety for
  convenience.
- Replay is a separate measured attack result, not silently mixed into FAR.
  An accepted replay is documented and forbids treating voice as standalone
  high-assurance evidence; replay/liveness policy remains PC-4.
- A zero-observed-FAR result on this small corpus is provisional evidence, not
  proof of population-level security. Report counts and confidence limitation.
- Do not choose a latency ceiling after seeing the study result. Pipec freezes
  the feasibility budget in the readiness amendment before promotion.
- Missing backend, malformed audio, zero/NaN embedding, inconsistent dimension
  or model error returns nonzero and writes no partial accepted report.
- Code/comments/docstrings are English; public APIs are typed with Google
  docstrings; data containers are frozen; use `pathlib.Path`, logging and
  exception chaining; no `print()`, bare `except`, unjustified `Any`, hardcoded
  path/model or handwritten `uv.lock` change.
- Tests never load a real model in the ordinary `unit` suite. No real voices or
  network calls enter CI.
- Preserve unrelated work and do not broaden this study after discovering an
  adjacent identity, spoofing or memory issue.

## Stable file map

These are the only files permitted after readiness, plus the exact dependency
files named by the approved amendment:

| File | Action and responsibility |
|---|---|
| `scripts/speaker_calibration.py` | Create model-independent sample schema, numeric calibration, safe corpus CLI and the amended concrete evaluation backend. |
| `scripts/speaker_calibration_models.py` | Conditional create if needed to keep the main script near 200 lines; contains only the frozen dataclasses/protocol, no I/O or backend behavior. Record the split before creating it. |
| `tests/unit/test_speaker_calibration.py` | Create pure synthetic tests for math, schema, paths, reports and backend boundary fakes. |
| `tests/slow/test_speaker_calibration_backend.py` | Create opt-in frozen-model smoke/contract tests; never part of ordinary unit execution. |
| `pyproject.toml`, `uv.lock` | Add the exact approved package to the root development group and record the generated resolution; no subproject dependency edit. |
| `justfile` | Add `speaker-calibration *ARGS` after dependencies are locked. |
| `docs/plans/open/0047-speaker-evidence-calibration-study.md` | Persistent checkpoints and final measured evidence. |
| `docs/architecture/current-state.md`, `docs/architecture/identity-and-access.md` | Record study result while keeping `VOICE` untrusted. |
| `docs/roadmap/personal-companion-delivery-map.md`, `docs/roadmap/cognitive-roadmap.md` | Record PC-3A result and PC-3B/PC-4 remaining work. |
| `docs/plans/README.md`, `docs/plans/open/README.md` | Operational status and eventual move to `completed/`. |

`server/src/`, `robot/src/`, `.env.example`, runtime DB/schema and API docs are
explicitly forbidden. The only dependency files permitted are root
`pyproject.toml` and generated `uv.lock`; no subproject dependency file becomes
permitted implicitly.

## Stable interface contract

The model-independent layer must expose exactly these contracts:

```python
SampleClass = Literal["reference", "genuine", "impostor", "replay"]


@dataclass(frozen=True)
class SpeakerSample:
    sample_id: str
    subject_id: str
    sample_class: SampleClass
    session_id: str
    phrase_id: str
    condition: str
    wav_path: Path
    sha256: str


@dataclass(frozen=True)
class EmbeddedSample:
    sample: SpeakerSample
    embedding: np.ndarray
    latency_ms: float


@dataclass(frozen=True)
class SpeakerThresholdResult:
    threshold: float
    false_accepts: int
    false_rejects: int
    total_genuine: int
    total_impostor: int


@dataclass(frozen=True)
class SpeakerManifest:
    schema_version: Literal[1]
    samples: tuple[SpeakerSample, ...]


@dataclass(frozen=True)
class ConditionSummary:
    sample_class: SampleClass
    condition: str
    total: int
    accepted: int
    rejected: int
    distance_min: float
    distance_max: float
    distance_mean: float


@dataclass(frozen=True)
class AggregateSpeakerReport:
    model_id: str
    package_version: str
    sample_counts: dict[SampleClass, int]
    selected_threshold: float | None
    live_false_accepts: int | None
    live_far: float | None
    genuine_false_rejects: int | None
    genuine_frr: float | None
    replay_accepts: int | None
    replay_accept_rate: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    by_condition: dict[str, ConditionSummary]
    outcome: Literal[
        "provisional_pass",
        "fail_distance_overlap",
        "fail_backend_latency",
        "invalid_procedure",
    ]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class SpeakerCliOptions:
    action: Literal["capture", "validate", "embed", "analyze", "cleanup"]
    corpus_root: Path
    manifest_path: Path
    output_path: Path | None
    sample_class: SampleClass | None
    subject_id: str | None
    session_id: str | None
    phrase_id: str | None
    condition: str | None


class SpeakerEmbeddingBackend(Protocol):
    @property
    def model_id(self) -> str:
        """Return the frozen model identifier and revision."""

    def embed_wav(self, wav_bytes: bytes) -> np.ndarray:
        """Embed WAV audio at 16 kHz, mono, signed int16."""


def l2_normalize(vector: np.ndarray) -> np.ndarray:
    """Return a finite unit vector or reject invalid input."""


def reference_centroid(references: Sequence[np.ndarray]) -> np.ndarray:
    """Return the normalized mean of normalized reference embeddings."""


def cosine_distance(probe: np.ndarray, reference: np.ndarray) -> float:
    """Return one-minus-cosine for equal finite nonzero vectors."""


def sweep_speaker_thresholds(
    genuine_distances: Sequence[float],
    impostor_distances: Sequence[float],
    candidates: Sequence[float],
) -> list[SpeakerThresholdResult]:
    """Evaluate FAR and FRR at each deterministic candidate threshold."""


def zero_far_speaker_threshold(
    genuine_distances: Sequence[float],
    impostor_distances: Sequence[float],
) -> tuple[float, float] | None:
    """Return threshold and FRR for the best zero-observed-FAR candidate."""


def percentile(values: Sequence[float], quantile: Literal[0.5, 0.95]) -> float:
    """Return a deterministic nearest-rank latency percentile."""


def validate_wav_bytes(wav_bytes: bytes) -> None:
    """Validate WAV audio at 16 kHz, mono, signed int16."""


def load_manifest(path: Path, corpus_root: Path) -> SpeakerManifest:
    """Load a strict manifest and prove every WAV remains in the corpus."""


def append_sample_atomic(
    manifest_path: Path,
    corpus_root: Path,
    sample: SpeakerSample,
) -> None:
    """Append one validated sample without exposing a partial manifest."""


def validate_corpus(manifest: SpeakerManifest) -> None:
    """Enforce subject, class, session, phrase and minimum-matrix rules."""


def render_aggregate_report(report: AggregateSpeakerReport) -> str:
    """Render a local aggregate report without biometric or path data."""


def parse_cli_args(argv: Sequence[str] | None = None) -> SpeakerCliOptions:
    """Parse one explicit speaker-calibration action."""


def run_cli(options: SpeakerCliOptions) -> int:
    """Execute one safe action and return zero only for complete success."""
```

Matching uses distance `<= threshold`. References are individually
L2-normalized, averaged, then normalized again. Selection minimizes FRR among
thresholds with zero observed live-impostor accepts; ties choose the lower
threshold. Empty sets, mismatched dimensions, zero vectors and non-finite data
are errors. Replay distances never participate in threshold selection.

The manifest is schema version `1`. Every record includes the exact fields in
`SpeakerSample`; `subject_id` must be `owner` for reference/genuine/replay and
an `impostor_[a-z]+` pseudonym for impostors. `sha256` detects accidental file
change but is removed from tracked reports. Corpus resolution must prove every
WAV is below the resolved corpus root and is not a symlink escaping it.

The default corpus root is
`project-history/calibration/speaker/`; the manifest is `manifest.json`; raw
embeddings are `embeddings.npz`; and the detailed local aggregate output is
`aggregate-report.md`, all below that ignored root. `render_aggregate_report`
must omit sample IDs, subjects, hashes, transcripts and absolute paths. The
privacy-reviewed safe aggregate values are copied into this plan's closure
section; no separate biometric report is committed.

Report invariants depend on `outcome`. `fail_backend_latency` permits no corpus:
all FAR/FRR/replay fields and the selected threshold are `None`, sample counts
and `by_condition` are empty, and available latency may be present. The two
measurement outcomes require the full corpus, every metric and every condition
summary; `provisional_pass` additionally requires zero live false accepts and a
selected threshold, while `fail_distance_overlap` requires no selected
threshold. `invalid_procedure` renders only measurements actually observed and
must state why they are non-gating. Model/package identity and limitations are
always mandatory. Model validators reject any inconsistent combination rather
than filling missing values with zero.

After the readiness amendment freezes the literal phrases and exact backend,
the CLI shape is fixed:

```powershell
just speaker-calibration capture --class reference --subject owner --session reference-01 --phrase phrase-01 --condition quiet-near
just speaker-calibration validate
just speaker-calibration embed
just speaker-calibration analyze --output project-history/calibration/speaker/aggregate-report.md
just speaker-calibration cleanup
```

Capture requires every metadata flag. Other actions reject capture-only flags.
`embed` requires a complete valid capture manifest and writes embeddings
atomically. `analyze` never opens the microphone or network, requires cached
model assets and complete embeddings, and refuses to overwrite its output.
`cleanup` first lists/resolves each exact artifact, refuses paths outside the
corpus, requires Pipec confirmation, and deletes individual files rather than
a recursive directory target.

## Corpus and condition matrix

The minimum accepted corpus is:

| Class | Minimum | Separation and conditions |
|---|---:|---|
| Reference | 6 | Owner, one dedicated enrollment session, three neutral fixed phrases × two repetitions, quiet/near. |
| Genuine | 24 | Owner, at least two later sessions, three phrases, near/far and quiet/ordinary-background conditions; no reference file reused. |
| Live impostor | 18 | At least three consenting adults, each three phrases × two repetitions, captured live rather than played from a device. |
| Replay | 6 | Pipec replays at least three owner probe recordings through a household speaker at two distances; source IDs recorded locally. |

Phrases contain no personal facts, secrets, wake words or names. The readiness
amendment freezes the literal Spanish phrases so repeats are comparable. A
participant may stop and withdraw at any point; withdrawal deletes their WAVs,
embeddings and manifest rows before analysis and adjusts the corpus gate
honestly. Do not pressure, replace or fabricate a participant to satisfy a
count.

## Agent execution protocol after promotion

One fresh implementer owns each coding task. No concurrent implementers edit
the shared worktree. Each receives the full task text, permitted files, exact
amended backend contract and a warning not to revert others' work. Each task
must show intended RED, minimal GREEN, self-review, a fresh spec-compliance
review, then a fresh code-quality/security review. The same implementer fixes
findings; five unsuccessful review rounds stop for Pipec.

The model-selection gate uses a read-only research agent and a separate
privacy/license reviewer. Physical tasks use no worker: Pipec runs commands and
confirms consent/capture. Final closure gets an independent whole-branch and
privacy review. Keep checkbox evidence in this file so a later session can
resume without relying on chat memory.

## Task 0: Freeze an isolated execution base after promotion

**Owner:** orchestrator; no coding or capture agent.

- [ ] Confirm every readiness blocker is checked, the reviewed plan status is
  `Ready`, it is the sole `NOW`, and Pipec explicitly authorized execution.
- [ ] Record branch, SHA, `git status`, frozen backend/package/model revision,
  approved download scope, literal phrase IDs/text and precommitted p95 budget.
- [ ] Use `superpowers:using-git-worktrees` to create a clean feature worktree
  from the approved merged SHA. Preserve all other worktrees and user changes.
- [ ] Re-read all required sources in that worktree. Any material API, license,
  package or lock drift stops for a documentation amendment; do not adapt while
  coding.

**Hard stop:** no code, dependency/model download or voice capture occurs
unless all four checks pass. No commit.

## Task 1: Build the pure numeric calibration layer with TDD

**Files:** create `scripts/speaker_calibration.py` and
`tests/unit/test_speaker_calibration.py`.

- [ ] Write tests for unit/orthogonal/opposite vectors, normalization,
  centroid order independence, equal dimensions and invalid zero/NaN/infinite
  values.
- [ ] Write tests for inclusive threshold comparison, FAR/FRR counts, tie
  breaking, no-zero-FAR overlap returning `None`, replay exclusion and p50/p95.
- [ ] Run RED:

  ```powershell
  uv run pytest tests/unit/test_speaker_calibration.py -k "normalize or centroid or distance or threshold or latency" -n0 -v
  ```

  Expected: missing symbols/behavior only; no audio/model import.
- [ ] Implement the minimum pure functions from the stable interface.
- [ ] Re-run focused and full unit file; observe GREEN.
- [ ] Complete spec and quality reviews.
- [ ] Commit: `feat(eval): add speaker calibration math`

## Task 2: Build the private corpus manifest and safe CLI with TDD

**Files:** modify the script/unit test and add `speaker-calibration` to
`justfile`.

- [ ] Write failing tests for manifest version/extra fields/duplicate IDs,
  class-subject rules, session separation, minimum matrix, WAV contract,
  SHA-256 mismatch, traversal/symlink escape and non-corpus paths.
- [ ] Test that `--analyze` never opens a microphone and capture cannot write
  outside `project-history/calibration/speaker/`.
- [ ] Test backend/capture exception: nonzero exit, no partial manifest row and
  no accepted report.
- [ ] Test aggregate-report invariants for technical FAIL without corpus,
  measurement overlap, provisional PASS and invalid procedure; test
  per-condition ranges/counts and omission of private fields.
- [ ] Run RED:

  ```powershell
  uv run pytest tests/unit/test_speaker_calibration.py -k "manifest or wav or path or cli" -n0 -v
  ```

- [ ] Implement atomic manifest append, strict WAV validation and safe path
  resolution. Every audio-touching function carries the exact audio-contract
  docstring.
- [ ] Add the exact recipe only after the readiness amendment has locked all
  imports:

  ```just
  speaker-calibration *ARGS:
      uv run --env-file .env python scripts/speaker_calibration.py {{ARGS}}
  ```

- [ ] Re-run tests and `just lint`/`just typecheck`; observe GREEN.
- [ ] Complete spec, quality and privacy reviews.
- [ ] Commit: `feat(eval): add private speaker corpus workflow`

## Task 3: Add the frozen backend adapter with TDD

**Files:** only the script/tests and exact dependency files authorized by the
readiness amendment.

- [ ] From workspace root run the approved command
  `uv add --group dev "speechbrain==1.1.1"`; never `uv pip install`, never edit
  a subproject dependency file and never hand-edit the lockfile.
- [ ] Write unit tests with a typed backend fake for byte/input conversion,
  normalization, fixed dimension, model metadata and errors.
- [ ] Write an opt-in `slow` contract test against a generated non-biometric WAV
  fixture and the exact frozen model. Assert finite repeatable shape and
  offline-after-cache behavior; do not assert speaker quality on synthetic
  tone.
- [ ] Execute the frozen latency protocol exactly: generated three-second WAV,
  one loaded backend, three warm-ups, 30 sequential timed embeddings with I/O
  and validation excluded, nearest-rank p50/p95. Compare to the precommitted
  budget and preserve sanitized measurements.
- [ ] Observe RED with the focused unit command and opt-in slow command frozen
  by the readiness amendment.
- [ ] Implement only the approved adapter. No identity/runtime import.
- [ ] Observe GREEN; inspect lock diff and run a frozen environment sync check.
- [ ] Complete spec, quality, dependency/license and privacy reviews.
- [ ] Commit: `feat(eval): add frozen speaker embedding backend`

If package resolution, model load, frozen revision, CPU execution,
offline-after-cache behavior, finite fixed-dimension output or the precommitted
p95 budget fails, record `FAIL — backend/latency`, remove any incomplete corpus
(none should yet exist), keep only reviewed non-biometric diagnostic evidence,
and proceed directly to Task 7. Do not collect household voices or swap models.

## Task 4: Capture owner reference and genuine samples

**Owner:** Pipec. Agents may display the next command and validate metadata
afterward; they may not activate the microphone themselves.

- [ ] Confirm corpus root resolves under
  `project-history/calibration/speaker/`, is ignored by Git, and contains no
  prior participant data unless Pipec explicitly elects to reuse it.
- [ ] Show the consent notice and confirm Pipec agrees to temporary local WAV
  and embedding storage plus deletion after analysis.
- [ ] Capture six references in the dedicated reference session using the
  frozen phrases.
- [ ] On at least two later sessions, capture at least 24 genuine probes across
  the frozen near/far and quiet/ordinary-background matrix.
- [ ] After each batch, run manifest validation and inspect counts/conditions;
  recapture only invalid technical samples and record exclusions.
- [ ] Confirm `git status --short` never lists WAV, manifest or embedding data.

**Checkpoint:** report aggregate counts only and wait for Pipec before inviting
other participants. No Git commit.

## Task 5: Capture consenting live-impostor and replay samples

**Owner:** Pipec and consenting adults.

- [ ] Obtain explicit consent independently from at least three adults and
  assign only local pseudonyms.
- [ ] Capture at least 18 live impostor probes. They must be spoken live during
  capture and distributed across the frozen phrases.
- [ ] Allow immediate withdrawal and execute targeted deletion/manifest repair
  before proceeding if requested.
- [ ] Pipec creates at least six replay probes using the frozen procedure. Keep
  replay labels separate from live impostors.
- [ ] Validate corpus counts, class labels, distinct files, session/phrase
  separation and hashes. Do not inspect or publish transcripts.
- [ ] Confirm again that private artifacts are ignored and absent from staged
  changes.

**Checkpoint:** if consented minimums cannot be reached, pause. Do not lower the
matrix silently or substitute internet/synthetic voices.

## Task 6: Analyze, choose or reject the candidate

**Owner:** orchestrator executes only after Pipec confirms capture complete.

- [ ] Run the frozen analyze command from the readiness amendment. Analysis
  must not access microphone/network and must use the already cached exact
  model revision.
- [ ] Produce per-condition aggregate distance ranges/counts, live-impostor
  FAR, genuine FRR, replay accept rate, exclusion reasons and p50/p95 CPU
  embedding latency.
- [ ] Apply the fixed rule: choose the lowest-risk zero-observed-FAR threshold
  with minimum FRR; a tie chooses the lower threshold. If none exists, result
  is FAIL and no compromise threshold is selected.
- [ ] Compare measured p95 with the readiness-amended feasibility bound.
- [ ] Independently inspect the aggregate report against local raw results
  without copying raw samples into tracked files.
- [ ] Record one conclusion: `PROVISIONAL PASS`, `FAIL — distance overlap`,
  `FAIL — backend/latency`, or `INVALID — corpus/procedure`. Only the first can
  inform PC-3B; none changes runtime here.
- [ ] Report replay acceptance separately and state explicitly that PC-4 owns
  anti-spoofing. A replay accepted at any rate forbids standalone high-assurance
  claims.

## Task 7: Privacy cleanup and documentation closure

- [ ] After Pipec accepts the aggregate report, resolve and list each exact
  private artifact path under the corpus root, verify all stay within that
  root, and delete individual files without recursive broad-target commands.
- [ ] Confirm WAVs, embeddings, manifests, per-sample scores and temporary
  caches containing samples are gone. Model package/cache may remain only if it
  contains no captured audio and Pipec chooses to retain it.
- [ ] Run the current canonical gate, then documentation hook/diff checks:

  ```powershell
  just gate
  just check
  git diff --check
  ```

- [ ] Run a privacy search over tracked diff for names, `.wav`, embeddings,
  absolute paths, manifest hashes and transcript content; explain benign code
  literals.
- [ ] Inspect all changes produced by the auto-fixing `just gate` before final
  review; do not assume the pre-gate diff is the final diff.
- [ ] Obtain whole-branch spec, code-quality, dependency/license and privacy
  reviews. Resolve all high/medium findings and rerun affected gates.
- [ ] Update canonical docs without changing `VOICE` trust or claiming PC-3
  complete. If provisional PASS, state that PC-3B enrollment/runtime and PC-4
  fusion/replay remain open. If FAIL, record the exact blocked outcome.
- [ ] Move this plan to `completed/` only with measured evidence and verified
  deletion. Use `superpowers:finishing-a-development-branch`; Pipec chooses
  merge/PR/keep and any worktree deletion.
- [ ] Commit: `docs(plan): record speaker calibration study`

## Rollback and incident boundary

The harness is outside runtime and its commits can be reverted independently.
No production identity or database rollback is expected because touching them
is forbidden. Private corpus deletion is intentionally irreversible after the
aggregate report is approved. Before deletion, Pipec may choose to invalidate
the study instead of preserving voices. If private media is staged, uploaded,
logged outside the corpus or written to production data, stop immediately,
preserve only minimal incident metadata, remove exposure through an explicitly
approved safe procedure, and do not call ordinary Git revert a privacy repair.

## Non-goals

- production speaker enrollment, recognition, revocation or profile storage;
- making `VOICE` a trusted source or changing `resolve_active_person`;
- authorization, identity fusion, face changes or PIN recovery changes;
- replay/liveness detection, diarization, speech-to-text or VAD improvement;
- identifying visitors or creating family accounts;
- retaining a reusable household voice dataset;
- cloud APIs, remote inference, model training/fine-tuning or online learning;
- changing the audio/API contract, server/robot runtime or PC-5 acceptance.

## Completion criteria

Plan 0047 closes only after it was promoted through the readiness gate and one
of these evidence-complete outcomes exists:

**Provisional PASS** requires a frozen local backend; all deterministic and
backend contract tests GREEN; the minimum consented corpus; zero observed live
impostor accepts at the selected threshold; honest global/per-condition FRR;
latency within the pre-frozen bound; replay reported separately; complete
private-artifact deletion; full repository gates and reviews GREEN. It closes
PC-3A only.

**Honest FAIL** has two valid forms. A technical FAIL occurs in Task 3 when the
frozen backend cannot resolve/load/run offline, return valid embeddings or meet
the precommitted p95 bound; it requires no household corpus and prohibits
capture. A measurement FAIL completes the consented minimum corpus but finds no
zero-observed-FAR separation. Both retain reviewed non-biometric diagnostics,
select no substitute/compromise and do not authorize PC-3B.

An incomplete corpus after capture, missing consent, leaked artifact, model
drift outside the approved revision or unverifiable deletion is `INVALID`, not
PASS or FAIL, and the plan stays open or is explicitly blocked by Pipec.
