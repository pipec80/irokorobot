# Completed plan archive

> **Status:** Historical execution evidence. Nothing in this directory is an
> active instruction or authorization.

These plans preserve decisions, tests, commits, migrations, and acceptance
evidence from completed or superseded slices. A few entries (0014, 0020,
0024, 0031) are umbrella/design documents that never had their own
executable code or gates — they moved here because every slice they
governed already closed elsewhere, not because they were themselves
executed. Current work must use the
[canonical architecture](../../architecture/README.md),
[current state](../../architecture/current-state.md),
[roadmap](../../roadmap/cognitive-roadmap.md), and
[open-plan index](../open/README.md).

[Plan 0043](0043-dependency-refresh.md) refreshed the workspace lock to the
latest stable resolution on 2026-09-02 and recorded the framework capabilities
measured against the installed packages. It is transversal rather than part of
any milestone.

[Plan 0032](0032-server-privacy-and-request-observability.md) is the first
executed child of the server-production capsule: it stopped fourteen log sites
from writing household content and introduced request correlation.

[Plan 0048](0048-fastapi-baseline-final-hardening.md) is a bounded follow-up
to a second independent audit of the server (2026-09-07), not a 0031 child:
it closed four small edges (semantic `max_length`, the streaming
one-terminal-event guarantee, the NDJSON 200 OpenAPI contract, `/health`
wording + injectable `create_app`) and left only Uvicorn concurrency
calibration open, as its own `perf(...)` plan.

[Plan 0057](0057-stream-protocol-diagnosis.md) closed on 2026-10-06 and merged as PR #166 (`a78e05a`, 2026-10-07): a diagnosis of why the streaming protocol drops to the fallback phrase,
with nothing under `server/src` changed. `just diagnose-stream` ran on `qwen2.5:3b` for 820 streams over two seeds: the
dominant failure shape is a tag that shares its line with the text, removing the memory block lowers the rate (exploratory,
confirmed by a second seed that also tripped the order-effect rule), a schema-constrained reply arrives spread over time, and the fragmentation defect is pinned by a
test and was not seen on live output. [Record](../../evals/0057-stream-protocol-diagnosis.md); the repair became Plans 0058 and 0059.

[Plan 0058](0058-stream-protocol-repair.md) closed on 2026-10-07 **without meeting its gate** and was replaced by Plan 0059: a tolerant `EMOTION:` grammar plus the rescue of untagged replies, implemented on the unmerged branch `feat/0058-stream-protocol-repair`, still left 35.00 % of context turns falling back in seed 57 (gate 5 %). Evidence: `docs/evals/0058-stream-protocol-repair.md` (docs-only PR, unmerged).

[Plan 0059](0059-user-emotion-apart.md) closed on 2026-10-08 (merged as PR #171, `29cfbc0`): the streamed reply is plain text, the `emotion` event is decided from the user's words by a pure function, and the gate was met (0 of 60 context and 0 of 60 public fallbacks in seeds 57 and 59; [record](../../evals/0059-user-emotion-apart.md)). Pipec accepted it on real hardware on 2026-10-08 (the memory case cannot be exercised before CM-2); the language of the reply (one French answer seen), the robot's facial expression and a model-based classifier remain open.

[Plan 0060](0060-cm1-personal-memory-capabilities.md) closed on 2026-10-09 (CM-1, memory capabilities): the five personal-memory actions exist as pure authorization policy and **nothing consumes them**. Owner only and own data only; a minimum assurance per capability by rank (`confirm` and `forget` `strong`; `biometric`, `medical` and `location` data `strong` in all five); `forget` needs a PIN grant spent for the new scope `personal_memory_forget` and ignores consent; `personal_memory_read` is the other new one-use scope; `grant_scope` and `grant_spent` travel in the identity evidence, so a peeked grant authorizes nothing. The eleven older actions are pinned by a 138,006-case characterization and did not move; architecture guards fail if a server module references the new surface. `just gate` 2515 tests (baseline 2315); one whole-branch review (0 Critical, 0 Important, four Minor fixed). [Record](../../evals/0060-personal-memory-capabilities-acceptance.md); [ADR 0019](../../adr/0019-personal-memory-capabilities.md) `Accepted`.

[Plan 0051](0051-scoped-owner-grants.md) closed on 2026-10-06 (merged as PR #164, `1ecd63c`; CM-1, first plan): every owner grant is
bound to one named operation (`personal_protected_read` or `biometric_admin`), a grant presented to the
wrong operation is refused without being spent, and "who am I" and the "not connected yet" answer no
longer spend it; accepted on real hardware, with the bearer limit still pinned.

[Plan 0050](0050-server-audit-repairs.md) closed on 2026-10-01 (merged as PR #154, `a496c1f`) the repairs of the
[0049 audit](../open/0049-server-objective-conformance-audit.md): standalone imports
and a pure cognitive core, one transport seam to Ollama, header-first image bounds,
a V4 reader that honours stored classification, owner-scoped setup readiness, dead
settings removed, no names in logs, static architecture guards and the owner →
stranger matrix, with two grant limits pinned for Plan 0051. `just gate` 1695 tests;
accepted on real hardware except the two-face veto, which was not run.

[Plan 0055](0055-pc4-identity-fusion-followups.md) closed the PC-4 follow-ups on
2026-10-01 (merged as PR #152, `1c0a914`): a store error while the face is resolved degrades to `unknown`, the face and
speaker models warm at startup behind their flags, `identity_source` and the clock have one
definition each, and the other-person veto is pinned against real role rows and survives a
failing consent read. It changes no identity rule and no OpenAPI; one hardware sample shows the first protected turn at 3.58 s (was 8 to 13 s). A static independent review reported one blocker, fixed before closing.

[Plan 0054](0054-face-default-identity-fusion.md) closed PC-4 on 2026-09-30: the
owner's face alone identifies at assurance `basic`, a verified voice of the same person
raises it to `strong`, reserved data (`SECURITY`) will require `strong`, and another
enrolled person or two faces veto. Accepted on real hardware by Pipec and independently
reviewed; replay is not defended and no reserved capability exists yet.

[Plan 0053](0053-consented-speaker-runtime-evidence.md) closed PC-3B on
2026-09-29: consented voice enrolment and revocation plus **untrusted** `VOICE`
evidence behind `SPEAKER_AUTHENTICATION_ENABLED` (default off), accepted on real
hardware and independently reviewed. It grants nothing; replay is not defended and
fusion is PC-4.

[Plan 0046](0046-reproducible-longitudinal-memory-baseline.md) closed CM-0 on
2026-09-08: it delivered a longitudinal-memory **benchmark and a measured RED
baseline**, not longitudinal memory. It repaired the two stale eval entrypoints,
added an 8-module out-of-runtime observation instrument
(`scripts/eval_longitudinal_memory.py` + `longitudinal_eval_*`), the synthetic
9-scenario suite `tests/evals/golden_longitudinal_memory.yaml`, and
`just eval-longitudinal`. `just gate` is GREEN; `just eval-longitudinal --runs 3`
recorded [`docs/evals/0046-longitudinal-memory-baseline.md`](../../evals/0046-longitudinal-memory-baseline.md)
at `ac43c58` with exit `1` — extraction (the only live seam) scored p/r `0.25`
(`FAIL`, no CM-0 gate), every other operation is honestly `unsupported`, all four
frozen gates `FAIL`, and the production DB hash was unchanged. The plan's file
map, smoke scenario id, and one scoring-denominator leak were adjusted during
execution (rulings recorded in the plan's closure banner). No runtime memory,
authorization, prompt, model, or API change.

[Plan 0047](0047-speaker-evidence-calibration-study.md) closed PC-3A on
2026-09-25 with a **provisional PASS**: a local, offline calibration study —
not speaker recognition. It added an out-of-runtime harness
(`scripts/speaker_calibration*.py`, `just speaker-calibration`) around a frozen
SpeechBrain ECAPA backend, and measured 62 private samples (deleted afterwards):
0/24 live-impostor false accepts at a 0.4834 cosine-distance threshold, 0/24
genuine false rejects (in-sample), 6/8 replay probes accepted and a frozen-protocol
p95 of 231 ms. `VOICE` stays untrusted; PC-3B (enrollment/runtime) and PC-4
(fusion, replay/liveness) remain open. No runtime, API or database change.

Do not modify a completed plan to create a new decision. Record architecture
changes in a new ADR and create a new open plan.
