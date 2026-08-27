# Real-Camera Face Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement Tasks 1-2 (the calibration
> harness) task-by-task. Tasks 3-8 are operator-run acceptance work in the
> style of `superpowers:executing-plans` checkpoint-by-checkpoint — do not
> dispatch coding workers for them; the operator (Pipec) captures the real
> frames and runs the real processes. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Status:** Open. Not started. This plan is the real-camera acceptance study
that [Plan 0029](0029-consented-local-face-evidence.md) and
[`docs/plans/README.md`](../README.md) both name as the remaining gate before
P1.2's exit criteria can be evaluated. `docs/plans/README.md` states this
explicitly: *"No further plan is authorized until a real-camera acceptance
plan is written and approved."* Writing and approving this document satisfies
that condition; executing it is separate work in its own session.

**Goal:** Measure, with the real webcam and in the real conditions of the
household, the cosine distance at which Pipec's own face falls and the
distance at which faces that are not Pipec's fall; choose
`face_authentication_match_threshold` and the enrolled-profile-count policy
from that data instead of the unvalidated guess Plan 0029 shipped; and confirm
the chosen value through the real `just run-server` + `just run-robot` path.

**Product framing:** Plan 0029 proved the face-evidence contract works
end-to-end. It did not prove the number gating it is right. Today
`face_authentication_match_threshold = 0.25` (`server/src/server/settings.py:99`)
is a value chosen by hand while writing Plan 0029 — no real cosine distance
ever informed it. This plan replaces that guess with a measured one, or
confirms it if the data agrees, and reports honestly if no threshold clears
both false-accept and false-reject at once.

**Architecture — two layers:**

**Numeric layer (offline, reproducible).** A new script captures a frame,
extracts its embedding through the existing `server.vision.faces.detect_faces`
pipeline, discards the frame immediately, and appends `(embedding, subject,
condition)` to an untracked corpus file. The same script reads Pipec's already
enrolled reference embeddings from `vec_faces`/`face_profiles` (read-only —
see Task 2) and copies them into the same untracked corpus once, so every
later sweep runs entirely offline against stored embeddings, with no further
webcam or database access. This is what lets the study compare a
one-enrolled-profile policy against a three-enrolled-profile policy, and
re-run the threshold sweep freely, without a second capture session.

**Product layer (live, non-reproducible).** Once the numeric layer picks a
threshold, a handful of real turns through `just run-server` + `just
run-robot` confirm it end-to-end: accepted for Pipec, denied for an impostor.
These live turns are not where the threshold comes from — they are the same
kind of confirmation Plan 0028 already established is necessary and
insufficient: *"Automated tests are prerequisite evidence, not product
acceptance"* (`docs/plans/completed/0028-owner-authenticated-memory-runtime-acceptance.md:58`,
applied here to the calibration numbers instead of pytest).

**The metric, exactly:** `match_face()`
(`server/src/server/vision/faces.py:245-246`) computes
`cosine_distance = L2² / 2` over the L2-normalized embeddings InsightFace
already produces, which is algebraically identical to `1 - dot(a, b)`. The
calibration script computes `1 - np.dot(a, b)` in numpy, so every distance it
reports is the exact number sqlite-vec's KNN would have produced in
production — not an approximation. A multi-profile match is the minimum
distance over the enrolled profiles for that person, mirroring `k = 1` in the
real KNN query; comparing a one-profile policy to a three-profile policy is
therefore just comparing the minimum over different subsets of the same
stored embeddings.

**Constraint discovered in Plan 0029's own code, binding here:**
`match_face()` (`faces.py:246`) pre-filters on `settings.face_match_threshold`
(the generic conversational bound, default `0.4` in code, `0.65` in
`.env.example:144`) *before* `_strict_match()`
(`server/src/server/cognition/face_authentication.py:283`) applies the
stricter `face_authentication_match_threshold`. **The authentication threshold
only has any effect while it stays at or below the generic one.** If this
study's data calls for raising it above `face_match_threshold`, that would be
silently capped by the pre-filter today. This plan does not resolve that
tension by touching `faces.py` — if the data pushes the threshold that high,
Task 5 stops, reports the conflict, and defers the fix to a follow-up plan
instead of quietly reordering the two thresholds.

**Tech stack:** Python 3.12, existing `server.vision.faces` module (InsightFace
`buffalo_l`, ONNX/CPU), existing `robot.camera_capture.capture_frame`, numpy,
pytest, the existing `just face-auth-demo` enrollment flow.

**Spec:** [Plan 0029 — consented local face evidence](0029-consented-local-face-evidence.md),
[Plan 0015 — personal companion design](0015-personal-companion-design.md) (PC-2
exit gate), [`docs/roadmap/cognitive-roadmap.md`](../../roadmap/cognitive-roadmap.md)
(P1.2 section).

## Global Constraints

- Read `AGENTS.md`, this plan, Plan 0029 in full, `server/src/server/vision/faces.py`,
  `server/src/server/cognition/face_authentication.py`, and
  `scripts/face_auth_demo.py` completely before writing any code.
- **No frame is ever persisted anywhere — not Pipec's, not an impostor's.**
  The untracked corpus stores only `(embedding: list[float], subject: str,
  condition: str, source: Literal["webcam", "photo"])` tuples, never image
  bytes. This is the same invariant `server/src/server/vision/faces.py:7-9`
  already states for the production path; the calibration harness must not
  weaken it.
- The untracked corpus lives under `project-history/calibration/` (already
  gitignored — `.gitignore:71` ignores `project-history/`). It must never be
  added to git, referenced from a tracked file, or attached to a PR.
- **No impostor face — living or photographed — is ever enrolled into
  `omnibot.db`.** The calibration script only *reads* `face_profiles` /
  `vec_faces` (Pipec's own already-enrolled reference profiles); it never
  calls `enroll_face()` or `INSERT`s into either table. Enrolling the three
  reference profiles Task 3 needs is done through the existing, unmodified
  `just face-auth-demo --enroll` flow — this plan does not write a second
  enroller.
- Photos of unrelated people used as file-based impostors stay in
  `settings.images_dir` (gitignored) and are never committed or attached to a
  PR.
- Do not modify `server/src/server/vision/faces.py`,
  `server/src/server/cognition/face_authentication.py`,
  `server/src/server/cognition/controller.py`,
  `server/src/server/cognition/authorization.py`,
  `server/src/server/routers/auth.py`, or `server/src/server/routers/transcribe.py`.
  If the calibration data appears to require a change to any of these
  (including the pre-filter/authentication-threshold ordering above), stop at
  Task 5 and report — do not implement the fix inside this plan.
- The only production values this plan may change are
  `face_authentication_match_threshold` (settings default + `.env.example`)
  and, only if Task 5's data supports it, the number of enrolled profiles
  Pipec is asked to keep (documentation guidance, not a new settings key).
- A false accept anywhere in the measured corpus is disqualifying for the
  threshold that allowed it — see the decision rule in Task 5. This plan does
  not trade false accepts for a lower false-reject rate.
- The calibration script must never load the InsightFace model in CI; its
  unit tests run entirely against synthetic embeddings (the same
  `_unit_vector()`-style pattern as `tests/integration/test_faces.py`).
- All public functions have complete type hints and Google docstrings.
- Use `apply_patch`; do not commit directly to `main`.
- Out of scope: liveness/anti-spoofing (PC-4's territory — a photo of Pipec
  held to the camera is a known, already-documented limitation, not something
  this plan tries to close), speaker evidence (PC-3), fusion (PC-4),
  third-party enrollment (PC-6), and any change to `/chat` or
  `/vision/respond`.

---

## File map

| File | Responsibility |
|---|---|
| `scripts/face_calibration.py` | New. Capture a probe frame or load a photo → embedding (discard frame) → append to the untracked corpus; read Pipec's enrolled reference embeddings once; sweep candidate thresholds and report FAR/FRR. Read-only against `omnibot.db`. |
| `justfile` | New recipe `face-calibration *ARGS`, same shape as `face-auth-demo` (`justfile:138`). |
| `tests/unit/test_face_calibration.py` | New. RED/GREEN on the distance formula (must match `faces.py`'s formula exactly), the multi-profile minimum, the threshold sweep, and a synthetic proof that the script never writes to `omnibot.db`. |
| `server/src/server/settings.py`, `.env.example` | `face_authentication_match_threshold` default only, and only if Task 5's data justifies changing it. |
| `docs/architecture/current-state.md`, `docs/roadmap/cognitive-roadmap.md`, `docs/roadmap/personal-companion-delivery-map.md`, `docs/plans/README.md`, `docs/plans/open/README.md` | Close this plan's own gates; do not touch PC-3/PC-4/PC-5/PC-6 status beyond recording that they remain open. |
| `docs/plans/open/0029-consented-local-face-evidence.md` → `docs/plans/completed/0029-consented-local-face-evidence.md` | Its only remaining debt was this acceptance. |

No other production file is in scope.

## Rollback boundary

Tasks 1-2 (the calibration harness) are ordinary code behind no feature flag
and touch no runtime path — reverting them is a plain `git revert` of that
PR with zero product impact, since `scripts/` is never imported by
`server` or `robot` at runtime. Tasks 3-6 (capture and threshold selection)
produce only untracked, gitignored evidence — nothing to roll back in git.
Task 7 (applying the chosen threshold) is the only step with runtime effect;
if the live confirmation in Task 8 fails, revert that one settings/`.env.example`
commit and leave `face_authentication_match_threshold` at Plan 0029's original
`0.25` while the discrepancy is investigated — do not leave a
partially-applied threshold in place.

---

## Reuse — do not rebuild

- `robot.camera_capture.capture_frame` for webcam capture, already used by
  `scripts/face_auth_demo.py:71`.
- `server.vision.faces.detect_faces` → `DetectedFace(embedding, score, width)`
  for embedding extraction; it already carries the detector score and face
  width needed to flag a low-quality capture.
- `settings.images_dir` and the `_resolve_photo()` pattern
  (`scripts/face_auth_demo.py:40-61`) for loading impostor photo files.
- `just face-auth-demo --enroll` / `--revoke` to create and remove the three
  reference enrollment profiles Task 3 needs. This plan does not write a new
  enrollment path.
- The `nargs="+"` argparse convention for any free-text CLI argument
  (`.claude/rules/scripts-powershell.md`), and `_read_pin`/`_unlock`'s pattern
  if the script ever needs to unlock (it does not — it only reads already
  -enrolled embeddings, which needs no owner unlock).

---

### Task 1: Write RED tests for the calibration math

**Files:**

- Create: `tests/unit/test_face_calibration.py`

**Interfaces:**

```python
def cosine_distance(a: np.ndarray, b: np.ndarray) -> float: ...

def closest_profile_distance(probe: np.ndarray, profiles: list[np.ndarray]) -> float: ...

@dataclass(frozen=True)
class ThresholdResult:
    threshold: float
    false_accepts: int
    false_rejects: int
    total_genuine: int
    total_impostor: int

def sweep_thresholds(
    genuine_distances: list[float],
    impostor_distances: list[float],
    candidates: list[float],
) -> list[ThresholdResult]: ...

def zero_far_threshold(
    genuine_distances: list[float], impostor_distances: list[float]
) -> tuple[float, float] | None:
    """Return (threshold, margin) at zero false accepts, or None if genuine
    and impostor distances overlap and no such threshold exists."""
```

- [ ] **Step 1: Write RED tests**

Against synthetic unit vectors (mirror `test_faces.py`'s `_unit_vector()`
pattern — no InsightFace, no DB): `cosine_distance` matches `1 - dot(a, b)`
and reproduces the same value `faces.py:245`'s `L2² / 2` formula would for
identical inputs; `closest_profile_distance` returns the minimum over 1 vs 3
synthetic profiles; `sweep_thresholds` reports the correct FAR/FRR counts for
a hand-constructed set of genuine/impostor distances; `zero_far_threshold`
returns `None` when a synthetic impostor distance is smaller than a synthetic
genuine distance (overlapping case — no threshold can separate them), and
returns the correct threshold and margin otherwise.

- [ ] **Step 2: Observe RED**

```powershell
uv run pytest -n0 tests/unit/test_face_calibration.py -q
```

- [ ] **Step 3: Implement the pure math**

No I/O in any of these four functions — same discipline as
`evaluate_face_authentication` in `face_authentication.py:76-113`.

- [ ] **Step 4: Run focused tests**

```powershell
uv run pytest -n0 tests/unit/test_face_calibration.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add tests/unit/test_face_calibration.py scripts/face_calibration.py
git commit -m "feat(scripts): add pure FAR/FRR calibration math"
```

---

### Task 2: Capture/corpus CLI, read-only against `omnibot.db`

**Files:**

- Modify: `scripts/face_calibration.py`
- Modify: `justfile`
- Modify: `tests/unit/test_face_calibration.py`

**Interfaces:**

```text
just face-calibration --capture --subject owner --condition light=day,distance=near,glasses=off
just face-calibration --capture --subject impostor:emma --condition light=warm --live
just face-calibration --capture --subject impostor:stranger1 --image foto.jpg
just face-calibration --load-reference-profiles
just face-calibration --analyze --profiles 1
just face-calibration --analyze --profiles 3
```

- [ ] **Step 1: Write RED tests**

Prove: `--capture` extracts exactly one embedding via `detect_faces` and never
retains the decoded frame past that call; a frame with zero or 2+ faces is
rejected with a clear message and nothing is appended to the corpus;
`--load-reference-profiles` issues only `SELECT` statements against
`face_profiles`/`vec_faces` (assert via a fake connection that raises on any
non-`SELECT` statement) and appends the read embeddings to the corpus tagged
`subject="owner-reference"`; `--analyze` never opens the webcam or touches the
DB, reading only the corpus file.

- [ ] **Step 2: Observe RED**

```powershell
uv run pytest -n0 tests/unit/test_face_calibration.py -q
```

- [ ] **Step 3: Implement**

`--capture` reuses `capture_frame()` (webcam) or `_resolve_photo()`-style
loading (photo file), calls `detect_faces()`, discards the frame, and appends
one JSON line `{embedding, subject, condition, source}` to
`project-history/calibration/<date>-face-corpus.jsonl` (created on first use;
directory not tracked). `--load-reference-profiles` opens the real
`db.get_conn()` exactly like `faces.py` does, runs a read-only `SELECT
embedding FROM vec_faces JOIN face_profiles ...` for Pipec's `entity_id`, and
appends each as `subject="owner-reference"` with a `profile_index` so Task 5
can select "just the frontal one" (index 0) vs "all three" (all indices).
`--analyze` loads the whole corpus, computes genuine distances (each
`owner`-tagged probe against the reference profiles) and impostor distances
(each `impostor:*`-tagged probe against the same references), and prints the
`sweep_thresholds`/`zero_far_threshold` results as a table.

- [ ] **Step 4: Run focused tests**

```powershell
uv run pytest -n0 tests/unit/test_face_calibration.py -q
just lint
just typecheck
```

- [ ] **Step 5: Commit**

```powershell
git add scripts/face_calibration.py justfile tests/unit/test_face_calibration.py
git commit -m "feat(scripts): capture and analyze face-calibration corpus"
```

---

### Task 3: Enroll reference profiles and capture Pipec's genuine samples

**Files:** Untracked corpus only (`project-history/calibration/`).

- [ ] **Step 1: Enroll three reference profiles**

Using the existing, unmodified flow:

```powershell
just run-server
just face-auth-demo --enroll   # frontal, well lit
just face-auth-demo --enroll   # dim light
just face-auth-demo --enroll   # wearing glasses
```

- [ ] **Step 2: Pull the reference embeddings into the corpus**

```powershell
just face-calibration --load-reference-profiles
```

- [ ] **Step 3: Capture 36 genuine samples**

3 lighting conditions (daylight / warm lamp / dim screen-light) × 2 distances
(~50 cm / ~150 cm) × 2 glasses states (on/off) × 3 repetitions. If Pipec does
not wear glasses, drop that axis and capture 6 repetitions per
lighting-×-distance cell instead, to keep the sample count comparable.

```powershell
just face-calibration --capture --subject owner --condition light=day,distance=near,glasses=off
:: ...repeat with each condition combination
```

- [ ] **Step 4: Record capture notes**

Log each session's date, time, and any deviation from the matrix (a skipped
cell, an extra retry) in
`project-history/acceptance/YYYY-MM-DD-real-camera-face-acceptance.md`
(untracked) — not in any tracked file.

---

### Task 4: Capture impostor samples

**Files:** Untracked corpus only.

- [ ] **Step 1: Capture live household impostors**

Two household members, 3 lighting conditions, 2 repetitions each (~12
samples). Get each person's spoken consent before capturing — the embeddings
are ephemeral (untracked corpus, deleted at Task 8) and never enrolled, but
consent is still required before pointing a camera at someone for this
purpose.

```powershell
just face-calibration --capture --subject impostor:person1 --condition light=day --live
```

- [ ] **Step 2: Capture file-based stranger impostors**

Drop ~10 photos of unrelated people into `settings.images_dir` and run:

```powershell
just face-calibration --capture --subject impostor:stranger1 --image foto1.jpg
```

- [ ] **Step 3: Record capture notes**

Same untracked evidence file as Task 3, Step 4.

---

### Task 5: Sweep thresholds and choose

**Files:** Untracked evidence only; no code changes.

- [ ] **Step 1: Run the sweep for both profile policies**

```powershell
just face-calibration --analyze --profiles 1
just face-calibration --analyze --profiles 3
```

- [ ] **Step 2: Apply the decision rule**

A false accept anywhere in the corpus disqualifies that threshold —
tighten until `false_accepts = 0` across every captured impostor sample
(live and photo). With that constraint fixed, report the resulting false
-reject rate honestly, broken down by lighting/distance/glasses condition —
if dim light rejects Pipec 3 times out of 6, that number is recorded, not
averaged away. Choose whichever profile-count policy (1 vs 3) yields the
lower false-reject rate at zero false accepts.

- [ ] **Step 3: Check the margin**

Report `zero_far_threshold`'s margin (largest genuine distance vs smallest
impostor distance). If `zero_far_threshold` returns `None` — genuine and
impostor distances overlap — this is a **FAIL**: stop, do not pick a
compromise threshold, and open a bounded remediation follow-up instead of
closing this plan.

- [ ] **Step 4: Check the pre-filter constraint**

If the chosen threshold exceeds `settings.face_match_threshold`
(`0.4`/`0.65` today), stop per the Global Constraints — this is also a
**FAIL** for this plan's scope, reported and deferred rather than fixed here.

---

### Task 6: Apply the chosen defaults

**Files:**

- Modify: `server/src/server/settings.py`, `.env.example`
- Modify: `tests/unit/test_settings.py` (if a default-value test exists;
  otherwise no test change needed — this is a constant, not new behavior)

- [ ] **Step 1: Apply, only if Task 5 passed**

Update `face_authentication_match_threshold`'s default in both files to the
chosen value, with a comment citing this plan and the measured margin.

- [ ] **Step 2: Run the existing face-authentication regression**

```powershell
uv run pytest -n0 tests/unit/test_face_authentication.py tests/unit/test_active_person_identity.py tests/integration/test_face_authenticated_turn.py -q
```

- [ ] **Step 3: Commit**

```powershell
git add server/src/server/settings.py .env.example
git commit -m "fix(vision): set face-authentication threshold from measured FAR/FRR"
```

---

### Task 7: Live confirmation

**Files:** Untracked evidence only.

- [ ] **Step 1: Restart with the applied threshold**

```powershell
just services
just run-server
just run-robot
```

- [ ] **Step 2: Run 3 accepted turns**

Pipec asks a protected question 3 times (fresh turns). Each must return the
exact confirmed child names with no PIN and no token, matching Plan 0029's
already-proven behavior.

- [ ] **Step 3: Run 3 denied turns**

An impostor (consenting household member or a held-up unrelated photo) in
frame for the same protected question, 3 times. Each must deny without
disclosing that protected data exists — no names, no count, no confirmation.

- [ ] **Step 4: Record evidence**

Same untracked acceptance file as Tasks 3-4. Do not paste PINs, tokens, or
database contents.

---

### Task 8: Close documentation

**Files:**

- Modify: `docs/architecture/current-state.md`
- Modify: `docs/roadmap/cognitive-roadmap.md`
- Modify: `docs/roadmap/personal-companion-delivery-map.md`
- Modify: `docs/plans/README.md`
- Modify: `docs/plans/open/README.md`
- Move: `docs/plans/open/0029-consented-local-face-evidence.md` →
  `docs/plans/completed/0029-consented-local-face-evidence.md`

- [ ] **Step 1: Run full repository gates**

```powershell
just lint
just typecheck
just test
just audit
just check
git diff --check
```

- [ ] **Step 2: Update documentation honestly**

Record the measured threshold, its margin, the chosen profile-count policy,
and the false-reject breakdown by condition — including a PASS or an explicit
FAIL if Task 5 could not clear both constraints. State plainly that closing
this plan closes only PC-2's real-camera acceptance. **It does not close
P1.2** — speaker evidence (PC-3) and fusion (PC-4) remain unstarted — and it
does not close the [Plan 0015](0015-personal-companion-design.md) umbrella,
which also still needs PC-5 (visual companion acceptance, P1.3) and PC-6
(family profile expansion, P3.2).

- [ ] **Step 3: Delete the untracked corpus**

Once evidence is recorded in the untracked acceptance file, delete
`project-history/calibration/` — the raw embeddings (including household
members' impostor embeddings) have no further purpose once the threshold is
chosen and confirmed.

- [ ] **Step 4: Request independent review**

Review: the distance formula matches `faces.py` exactly, no frame or impostor
embedding was ever persisted or committed, no impostor was enrolled into
`omnibot.db`, the zero-false-accept rule was actually applied (not relaxed),
and the pre-filter constraint was respected or the plan correctly stopped
instead of silently reordering the two thresholds.

## Completion criteria

Plan 0030 is complete only when:

- the calibration script's distance math is proven identical to
  `faces.py`'s production formula by a passing unit test;
- the full capture matrix (Tasks 3-4) is executed and its untracked evidence
  recorded, including any deviation from the planned matrix;
- either a threshold clears zero false accepts across every captured
  impostor sample with a reported margin and an honest false-reject
  breakdown by condition, **or** the plan stops and reports FAIL because no
  such threshold exists — both are valid closures, a forced compromise
  threshold is not;
- the chosen threshold does not exceed `settings.face_match_threshold`,
  or the plan stops and defers that conflict rather than reordering the two
  thresholds itself;
- the live confirmation (Task 7) passes 3 accepted and 3 denied turns through
  the real `just run-server` + `just run-robot` path;
- no frame, no impostor embedding, and no impostor enrollment ever reaches
  `omnibot.db` or a tracked file;
- the untracked calibration corpus is deleted after evidence is recorded;
- full repository gates pass;
- documentation records this plan's own scope only — it explicitly leaves
  PC-3, PC-4, PC-5, and PC-6 open, and does not claim P1.2 or the Plan 0015
  umbrella is closed;
- independent review is complete and its findings resolved.
