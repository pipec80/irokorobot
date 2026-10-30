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
[0049 audit](0049-server-objective-conformance-audit.md): standalone imports
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

[Plan 0061](0061-cm2-generic-turn-continuity.md) closed on 2026-10-13 (merged as PR #179, `ec8178b`; CM-2, short-term continuity): the face (or an observed `/chat` token) names the speaker of a generic turn, with no voice embedding and no grant spent, and the identified person gets one in-process session slot (3000 characters, 180 s of silence, replaced by another identified person, suspended by an unknown or ambiguous turn) in place of `memory/working.py`. `just gate` 2597 tests (baseline 2515); a measured prompt sentence (`history` fallback 0.00 % in two runs); accepted on real hardware by Pipec, with an iPad face standing in for the second person; the face check costs a median of about 0.9 s on a generic turn. [Record](../../evals/0061-generic-turn-continuity-acceptance.md); [ADR 0020](../../adr/0020-authorized-actor-in-the-conversation.md) `Accepted`.

[Plan 0062](0062-cm3a-memory-candidates-and-writer.md) closed on 2026-10-15 (merged as PR #183; CM-3a, first cut): a face-identified generic voice turn schedules a background candidate proposal that also needs the voice of the same person on the turn's own clip, behind the default-off `MEMORY_CANDIDATES_ENABLED`; candidates live in their own table (migration 009) and `memory_writer.promote` is the only place one becomes a V4 literal fact, with no route caller yet. `consolidate_turn`, `PROPOSE_MEMORY` and `COMMIT_MEMORY` are retired. No spoken dialogue and no hardware: the offer, the answer and the hardware acceptance were [Plan 0063](0063-cm3a-memory-dialogue.md). `just gate` 2972 tests (CI selection 2955; baseline 2597 / 2580). [Local smoke record](../../evals/0062-memory-candidates-local-smoke.md).

[Plan 0063](0063-cm3a-memory-dialogue.md) closed on 2026-10-16 (CM-3a, second cut; closes CM-3a): the offer, spoken after the reply of a later generic turn (one WAV on the classic route, one more `audio` event on the stream, neither in the history or in `llm_ms`), and the explicit answer, a closed grammar that needs a closed verb **and** the value (`InformationNeed.MEMORY_ANSWER`), which promotes the candidate through `memory_writer.promote` or rejects it and erases the value. Every offer, answer and promotion needs the face and the voice of the same person on that turn's own clip; anything else is the ordinary turn. No wire change, robot untouched, no migration, no new setting; `MEMORY_CANDIDATES_ENABLED` stays `false` by default. `just gate` 3217 tests (baseline 2972); four independent read-only reviewers, everything found fixed or pinned. Hardware acceptance by Pipec alone on the shared laptop: cases 1, 2, 3, 4, 6 and 7 passed, 5 partial, 8 measured (no homelab), 9 (replay) not run. [Record](../../evals/0063-memory-dialogue-acceptance.md); [ADR 0021](../../adr/0021-memory-candidates-and-the-canonical-writer.md) `Accepted`.

[Plan 0064](0064-speech-and-dialogue-quality.md) closed on 2026-10-19 (PR #193): what Iroko says is one voice and is truthful about memory. Every persona, prompt template, fixed controller string, perception template and fallback phrase uses neutral Spanish with tuteo (`tests/unit/test_no_voseo_in_spoken_strings.py` fails on voseo outside the recognition lexicons and the internal extraction prompts); one rule closes the master prompt and the streaming contract asks for Spanish; the explicit answer also accepts the third person (`autoriza`, `aprueba`), the openers `ya`, `dale`, `po`, a trailing `po` and a leading `mi`/`mis` (ADR 0021 decision 9, amended); a pure `claim_guard` replaces a model sentence that claims to have saved, registered or noted something with «Eso no lo he guardado.» on the classic reply and on the stream; and the server logs one warning at start-up when Ollama does not answer `/api/tags`. `just gate` 3327 tests (baseline 3217). Not in Spanish on `qwen2.5:3b`: 1 of 97 before, 0 of 98 and 0 of 97 after; on real hardware (Pipec, 2026-10-19) 0 of about 24 turns in another language and 1 of 2 explicit answers understood. Two independent reviews found nothing Critical; the probe moved into `llm_transport` because of the Plan 0050 seam guard. Letting a closed verb alone resolve the open offer (Pipec's decision of 2026-10-19) is a new plan.

[Plan 0065](0065-cm3b-a-channel-neutral-writer-core.md) closed on 2026-10-22 (CM-3b, tranche A): one writer stores the owner's household facts whatever the channel (`voice_classic`, `voice_stream`, `import_file`), assigns the classification itself (the owner's facts `personal`, a child's or a pet's `household`, the partner or an outsider refused), records who asserted a fact and through which channel (migration 010) and joins a transaction the caller owns. Relations carry visibility, sensitivity, confirmer and validity; the household capability pair is policy only; dataset v3 of the benchmark moved the two-person provenance scenario to the family stage. [ADR 0022](../../adr/0022-household-rules-and-third-party-memory.md) `Accepted`; `just gate` 4179.

[Plan 0066](0066-verb-only-answer.md) closed on 2026-10-19 (PR #196): a closed verb alone («sí, autorizo.») resolves the one open memory offer of the verified speaker, and the offer ends «Dime: sí, autorizo.». [Plan 0067](0067-reply-listening-mode.md) closed the same day (PR #199): after a spoken offer the robot listens once in a dedicated reply mode, the server biases Whisper with the reply words, and «acepto» and «guárdala» are accepted. [Plan 0068](0068-short-clip-speaker-measurement.md) closed on 2026-10-21: when only the voice failed and the owner's face is recognized, one fixed sentence asks for a longer answer and the robot listens once more (code PR #201); its hardware counts were 7 offers, 1 promoted, 1 rejected, 1 retry and no wrong promotion, and its Tasks 7 and 8 (short-clip captures and report) were deferred by Pipec.

[Plan 0069](0069-stt-owner-voice-audit.md) closed on 2026-10-21 (PR #202): the transcript was measured with the owner's own voice for the first time; `medium` on the GPU takes the test-half word error rate from 15.4 % to 6.8 %, the retry temperature is fixed at 0 and the private corpus was deleted. [ADR 0023](../../adr/0023-speech-to-text-model-and-decoding.md) `Accepted`; [record](../../evals/0069-stt-owner-voice.md).

The four plans of **Step 0** (the seed load, the "alta" of the robot) closed between 2026-10-23 and 2026-10-28 under [ADR 0024](../../adr/0024-seed-load-senses-secrets-and-channels.md) (`Accepted` 2026-10-27) and [ADR 0025](../../adr/0025-remote-administration-backup-updates-and-telemetry.md) (`Accepted` 2026-10-28, local half):

- [Plan 0070](0070-seed-load-data-pool-storage.md) (PR #208, `just gate` 4511): the storage of the data pool and the provenance of an assisted interview. Migration 011 (`care_contacts`, `commissioning_records`, `commissioning_sections`), the 25 pool predicates, a secret stored by reference (never its value), the adult child and the owner's relatives fenced in the writer, the refuse-on-conflict policy.
- [Plan 0071](0071-seed-load-file-importer.md) (PR #214, `just gate` 4720): `just seed-import`, a dry run by default, the owner's review and `SI`, one transaction with the commissioning record, `--replace` only while commissioning; `just reset-db` honours `BRAIN_DB_PATH`. [Record](../../evals/0071-seed-import-acceptance.md).
- [Plan 0072](0072-commissioning-session.md) (PR #216, `just gate` 4814): `just commission`, a state machine that enrols the face (five frames) and the voice (three references), records the biometric notice, the consents, the backups and the readiness of the capabilities that exist, writes the acta with no household value and closes the window. Rehearsed on real hardware, then Pipec's real alta. [Record](../../evals/0072-commissioning-acceptance.md).
- [Plan 0073](0073-local-admin-crud.md) (PR #218, CI-selection suite 4846): `iroko-admin`, the amendment path after the closing. Migration 012 (the admin audit, which holds no household value), the `admin_local` channel, the owner's PIN read offline for sensitive writes, add, change and revoke through the canonical writers (a revoke is history, not a hard delete) and a read-only recompute of the readiness. [Record](../../evals/0073-admin-acceptance.md).

The measurement before CM-4 closed on 2026-10-29:

- [Plan 0075](0075-cm4-pre-measurement.md) (PR #226, CI-selection suite 4983): three offline instruments (`cm4-corpus`, `cm4-voice-rate`, `cm4-embed`) and an invented Spanish fixture, with nothing under `server/src` or `robot/src`. The owner's voice verified on 35.5 % of 62 real turns, driven by duration; the eligibility rule for CM-4 is **per turn** (confirmed by Pipec); `nomic-embed-text` separates Spanish at ROC-AUC 0.98. [Record](../../evals/0075-cm4-pre-measurement.md).

CM-4 closed on 2026-10-30:

- [Plan 0076](0076-cm4-conversation-record-and-diary.md) (`just gate` 5442): the legacy memory path retired (the prompts kept their golden digests), migration 013, the segmented conversation record behind the owner's `conversation_storage` consent and two switches, the per-turn face + voice verdict, the diary job (only the owner's verified part) and `iroko-admin conversations` under the PIN. Accepted on real hardware, 8 of 8 cases; a fixed reply now keeps its speaker (found on hardware). ADR 0027 `Accepted`. [Record](../../evals/0076-conversation-record-acceptance.md).
