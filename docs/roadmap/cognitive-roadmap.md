# Cognitive roadmap

> **Status:** Canonical implementation order
>
> **Starting point:** [Current cognitive implementation](../architecture/current-state.md)
>
> **Personal-companion traceability:** [Delivery map](personal-companion-delivery-map.md)
>
> **Longitudinal-memory traceability:** [Delivery map](conversational-memory-delivery-map.md)
>
> **Rule:** Finish and verify one bounded plan before preparing or implementing
> the next. Priority does not authorize all work in a phase at once.

## Goal

Turn the existing conversational prototype into a trustworthy household brain
before coupling it to new electronics. The roadmap preserves what already
works—audio, text, memory, personality, vision, and the server/robot boundary—
while adding identity, policy, typed orchestration, reliable family knowledge,
and explicit uncertainty.

The ordering optimizes for false-positive avoidance and privacy, not feature
count. A capable model without identity and authorization is less useful in a
home than a smaller system that knows when it does not know.

Iroko uses two independent product axes per
[ADR 0014](../adr/0014-orthogonal-social-and-responsibility-profiles.md): the
social profile (`personal` or `family`) and the responsibility
(`companion`, `care`, or `education`). The current target is
`personal + companion`; `care` and `education` remain unimplemented future
responsibilities with no product claim.

## Phases at a glance

- **P0 — trustworthy cognitive foundation:** closed.
- **P1 — personal companion:** identity closed (PC-1…PC-4); integrated acceptance
  (PC-5 / P1.3) open.
- **P2 — situated cognition and memory quality:** conversational memory (P2.2,
  CM-1…CM-7): rows 1 to 5 of the [path to the finish line](#closing-path-of-conversational-memory)
  are done (the household protection, block A «it remembers», block B «it knows who is listening»,
  the memory MVP of Plan 0080, ADR 0031), and so are rows 6 and 7: what the robot says (Plan 0081)
  and the memory the MVP lacked (Plans 0082 to 0084: a contact's phone, the rest of the alta, when
  a told event happened and the pending topics, whose greeting is under hardware acceptance until
  2026-11-19); block C (correct and forget), documents and reading through the camera
  (R2), the home server and
  block D (CM-7 + PC-5) remain before the line «ready for the electronics»; perception (P2.1),
  adaptation (P2.3) and outcomes (P2.4) follow.
- **P3 — family:** after the personal companion is accepted.
- **P4 — model-provider evaluation (optional) and physical body:** after the 16 slices.

The order of the remaining work is the portfolio below; what is already closed
is summarized in [Closed foundations](#closed-foundations--history).

## Canonical pre-electronics delivery portfolio

This is the **only** delivery queue. The specialized maps (personal companion,
conversational memory, RAG) explain one track in depth and the plan router holds
the single `NOW` item; neither defines order. If another document shows a
different order, this table governs and the other document is stale.

Iroko has one product axis: the personal companion, `STT -> memory -> LLM ->
TTS`, where memory is the brain. Identity (PC-1…PC-4) answers *who is speaking*
and is closed. Conversational memory (CM-1…CM-7) is the next chapter of the same
companion, not a separate program: it makes "¿te acuerdas de…?" work for the
owner and keeps every private fact closed to anyone else. Hybrid search (R3) arrives
with CM-5b and documents (R2) are conditional; the other retrieval stages are already
CM or P2.1 work
(see [RAG §25](../architecture/rag-and-memory-retrieval.md#25-secuencia-de-evolución)).

Numbered rows are the 16 required product slices (19 until the
[closing path](#closing-path-of-conversational-memory) of 2026-10-30 merged or moved three; numbers
12, 14 and 15 are gone or shared on purpose). Rows marked `—` are hardening
or data-loading work that belongs to the queue without being a slice, so the
count stays 16. A row is neither a reserved plan number nor authorization: only
the `NOW` item in [`docs/plans/README.md`](../plans/README.md) may be executed,
after Pipec authorizes its `Ready` plan, and each row is re-audited against the
merged code before its plan is written (queue rule 4). `Depends on` lists hard
gates only.

| Order | Slice | Verifiable outcome / exit evidence | Depends on | State | Detail |
|---:|---|---|---|---|---|
| 1 | CM-0 — longitudinal benchmark | A versioned synthetic suite runs reproducibly; the harness is GREEN and the measured product honestly RED. | — | **Complete 2026-09-08** — Extraction scored precision 0.25 and recall 0.25. The full longitudinal run recorded 75 steps: 3 failed and 72 unsupported. The report's `source_commit` is `38fa89c`; `ac43c58` is the commit that added the report. It is a historical measurement, and memory code changed afterwards (PR #131, Plan 0053). | [Plan 0046](../plans/completed/0046-reproducible-longitudinal-memory-baseline.md); [baseline](../evals/0046-longitudinal-memory-baseline.md) |
| 2 | PC-3A — speaker calibration | FAR/FRR, replay, quality and CPU latency measured offline on a frozen backend. | CM-0 | **Complete 2026-09-25** — provisional: threshold 0.4834, 0/24 false accepts, 6/8 replay accepted, p95 231 ms | [Plan 0047](../plans/completed/0047-speaker-evidence-calibration-study.md) |
| 3 | PC-3B — consented speaker evidence | Local enrolment, revocation and typed `VOICE` evidence; weak or failed evidence is `unknown`. | PC-3A | **Complete 2026-09-29** | [Plan 0053](../plans/completed/0053-consented-speaker-runtime-evidence.md) |
| 4 | PC-4 — identity fusion | The owner's face identifies at `basic`, face plus verified voice at `strong`; another enrolled person or two faces veto; the PIN is optional. | PC-3B | **Complete 2026-09-30** — accepted on real hardware; replay not defended; no reserved capability yet | [Plan 0054](../plans/completed/0054-face-default-identity-fusion.md); [ADR-0016](../adr/0016-face-and-voice-identity-fusion.md) |
| — | PC-4 follow-ups | A store error during face recognition degrades to `unknown`; face and speaker models warm at startup; one `identity_source` and one clock; two coverage holes closed. | PC-4 | **Complete 2026-10-01** (PR #152, `1c0a914`) — automated gates green; one hardware sample: first protected turn 3.58 s (was 8 to 13 s); static independent review blocker fixed | [Plan 0055](../plans/completed/0055-pc4-identity-fusion-followups.md) |
| — | Audit repairs | The 12 repairs of the 0049 audit: import cycles, one seam to Ollama, fail-closed parsing of Ollama transport responses (not the classic `response`/`emotion` parser), image bounds, stored classification honoured, owner-scoped readiness, setup contract, dead settings, no names in logs, architecture guards, the owner → stranger matrix, docs truth. | — | **Complete 2026-10-01** — `just gate` 1695 tests (baseline 1607), CI-command coverage 91.69 %; hardware acceptance by Pipec: all cases passed except the two-face veto, not run (no second person) and still covered by Plan 0054/0055 tests and the PC-4 acceptance; merged as PR #154 (`a496c1f`) | [Plan 0050](../plans/completed/0050-server-audit-repairs.md) |
| — | Voice-pipeline reliability and truthful diagnostics | Whisper no longer returns its own initial prompt from a noise clip (seen four times) and the first utterance after a restart is transcribed correctly; the classic parser rejects a non-text `response` (for example `{"response": []}`) while the raw-text fallback stays a separate, explicit decision; `just test-pipeline` runs again (its `llm.generate_response` call lacks the client) and is described as an STT → LLM → TTS smoke test, not the cognitive path; `just eval-chat` measures the streaming `EMOTION:` protocol (0049 O-04), not only the classic generator; the longitudinal evaluator reports the three staged verdicts (personal, family, full suite) defined in the [evaluation spec](../architecture/longitudinal-conversational-memory-evaluation.md#cm-0-measured-baseline). | Audit repairs | **Complete 2026-10-02** (PR #159, `4d62f26`) — accepted by Pipec on real hardware (classic mode not run; the echo guard was not exercised on real audio); `just test` 1807, CI-command coverage 91.83 %; measured streaming fallback 29.17 % (a repair row is opened below), noise and first-turn rules closed | [Plan 0056](../plans/completed/0056-voice-pipeline-reliability-and-diagnostics.md); [0049 O-04](../plans/completed/0049-server-objective-conformance-audit.md) |
| — | Voice-pipeline follow-ups not triggered | A hallucination filter for non-echo Whisper output on noise and a Whisper warm-up inference at start-up stay closed: 0 % of 100 synthetic-noise clips returned non-echo text (rule: more than 5 %) and the first-call error was 0.000 above later calls (rule: more than 0.15). A real-room recording or the real first-utterance acceptance can reopen either with new evidence. | Plan 0056 | Closed by measurement | [Measurements](../evals/0056-voice-pipeline-measurements.md#decisions) |
| — | Speech-to-text on the owner's real voice | **Closed in code 2026-10-21** ([Plan 0069](../plans/completed/0069-stt-owner-voice-audit.md), [ADR 0023](../adr/0023-speech-to-text-model-and-decoding.md), [the record](../evals/0069-stt-owner-voice.md)). The transcript was measured with Pipec's own voice through the robot's capture chain: the model was the only link that moved the result, `medium` on the GPU (optional `cuda` extra) takes the test-half WER from 15.4 % to 6.8 % (a second look at that half) and the short answers from 25.7 % to 2.9 % (1 of 35 words against 9) at a median 3.0 s per clip with Ollama busy (8.7 s on the CPU); the retry temperature is fixed at 0; the robot closes a turn after 1200 ms and uploads a 300 ms tail; a per-clip `stt.confidence` is logged and the «No te entendí» reply is built and off by default (the owner runs `-0.9`); the `amara.org` credit Whisper writes on noise is discarded. The taste gate keeps refusing «?» (0 of 17 statements were punctuated that way). One speaker, one microphone in a quiet room: measure again on the body's microphone. The private corpus was deleted at the close. | — | **Closed** 2026-10-21 (PR #202) | Plan 0069; ADR 0023 |
| 5 | CM-1 — scoped memory capabilities | First every grant is bound to one named operation ([ADR-0015](../adr/0015-owner-grant-scope-and-speaker-binding.md) decision 1, implemented by **Plan 0051**, the first plan of this slice, which also covered the voice enrolment and revocation endpoints Plan 0053 added after the ADR, the household-looking stub answer that used to spend a grant, and the optional PIN hardware case left unrun by Plan 0054); then policy distinguishes `read`, `propose`, `confirm`, `correct` and `forget` for personal memory, and `SECURITY` data declare their `strong` requirement, without turning identity into authorization. | PC-4 | Plan 0051 **closed 2026-10-06** (grants bound to one operation; accepted on real hardware, [record](../evals/0051-scoped-grant-acceptance.md)); [Plan 0060](../plans/completed/0060-cm1-personal-memory-capabilities.md) **closed 2026-10-09** (the five memory capabilities as pure policy, a minimum assurance per capability with `confirm` and `forget` at `strong`, `biometric`, `medical` and `location` data at `strong`, and two one-use grant scopes carried in the identity evidence; [ADR 0019](../adr/0019-personal-memory-capabilities.md) `Accepted`; [record](../evals/0060-personal-memory-capabilities-acceptance.md)). Nothing was wired when it closed; CM-3a (Plans 0062 and 0063, 2026-10-16) now consumes `propose`, `read` and `confirm` for the owner's own preferences | [Memory map](conversational-memory-delivery-map.md#delivery-sequence) |
| — | Streaming-protocol fallback repair | Streamed replies stop dropping to the fallback phrase at a measurable rate: Plan 0056 measured **29.17 %** (35 of 120; 56.67 % on turns with memory context, 1.67 % on context-free turns), above the 5 % rule. The figure is a synthetic evaluation of the generator, not a production rate, and the context split mixed four factors. [Plan 0057](../plans/completed/0057-stream-protocol-diagnosis.md) (diagnosis only, executed 2026-10-06, [record](../evals/0057-stream-protocol-diagnosis.md)) measured them on `qwen2.5:3b` (820 streams over two seeds, generator only): the baseline falls back in about 43 to 52 % of context turns and 1.7 to 3.3 % of public turns; the dominant shape is a tag that shares its line with the text (`tag_same_line`, 85 to 97 % of context fallbacks); removing the memory block lowered the rate by 35 and 27 points on the same 12 turns (confirmed by a second seed that also tripped the order-effect rule; exploratory, not a cause); and a schema-constrained reply reached the client spread over time, which is evidence against the `llm_streaming.py` claim that Ollama withholds it. The fragmentation defect was not seen on live output (none of the 820 replies was judged differently under any split). Moving the output contract to the start of the prompt made the model drop the tag in all 120 runs (one seed), which argues against that option; the repair plan also owns correcting the stale `llm_streaming.py` header that claims Ollama withholds structured output. Pipec chose the repair on 2026-10-07 from those readings: a tolerant tag grammar **plus** rescuing a reply with no tag as plain text with the emotion `neutral`, with the prompt untouched ([ADR 0017](../adr/0017-streaming-reply-protocol.md), `Proposed`); the gate is a baseline fallback rate at or below 5 % in context and public turns in two seeds. It is written as [Plan 0058](../plans/completed/0058-stream-protocol-repair.md), whose first code task is the fragmentation defect: production validates the body start once, so a split `EMOTION:` or code fence is spoken. **Outcome (2026-10-07/08):** Plan 0058 implemented that grammar and measured 35.00 % of context turns still falling back in seed 57 (21 of 60, gate 5 %; 20 of 21 a same-line tag whose next word is not an emotion), so it closed without its gate and was replaced by [Plan 0059](../plans/completed/0059-user-emotion-apart.md): the model answers in plain text and the `emotion` event is decided from the user's words by a pure, precision-first function ([ADR 0018](../adr/0018-user-emotion-decided-apart.md), `Accepted`). Gate met on the final code: 0 of 60 context and 0 of 60 public fallbacks in seeds 57 and 59 ([record](../evals/0059-user-emotion-apart.md)). | Plan 0056; ordered after CM-1 (Pipec, 2026-10-05) | **Closed 2026-10-08** — diagnosis Plan 0057 (2026-10-06); Plan 0058 closed without its gate (2026-10-07); [Plan 0059](../plans/completed/0059-user-emotion-apart.md) closed it (gate met). CM-2's hard gate is met. Hardware acceptance by Pipec done 2026-10-08 (memory case not exercisable before CM-2). Open: the language of the reply (one French answer seen), the robot's facial *expression*, a model-based classifier, the end-to-end rate | [Measurements](../evals/0056-voice-pipeline-measurements.md#1-streaming-protocol-fallback-0049-o-04); [0049 O-04](../plans/completed/0049-server-objective-conformance-audit.md) |
| 6 | CM-2 — authorized actor propagation | The actor and grants resolved by face, voice or PIN reach the generic conversation, with no name interpolated into the prompt and no widened grant. Until Plan 0061 identity was resolved only on protected turns ([ADR-0016 §5](../adr/0016-face-and-voice-identity-fusion.md#5-turn-order)), so CM-2 needed a new ADR that supersedes that section: when a generic turn is identified, how an authorized session is kept, and when its history is discarded. [ADR 0020](../adr/0020-authorized-actor-in-the-conversation.md) (`Accepted` 2026-10-13) decides it and Plan 0061 implemented it: every generic turn is identified by the face (or an observed `/chat` token) with no voice embedding and no grant spent. `just chat-test` is adapted, because it expects continuity between unauthenticated public requests. Its first visible result is short-term continuity: the identified actor's last turns (in-process working memory, never persisted) reach the next turn, another identified person or 180 s of silence deletes them, and an `unknown` or `ambiguous` turn suspends them without exposing them; only generic turns take part, so a protected answer never enters the history — with its own acceptance test and a measured fallback rate and language on history-bearing streamed turns. Connecting the actor is not enabling durable memory: legacy retrieval and consolidation stay blocked, and each read or write opens only in the slice that implements its guarantees (writes CM-3, episodes CM-4, retrieval CM-5). | CM-1; streaming-protocol repair (the first turn that carries memory or history in the prompt is where the measured fallback rate matters) | **Complete 2026-10-13** — accepted on real hardware (continuity, a second face beside the owner, no evidence, 180 s of silence); 2597 tests; `history` fallback 0.00 % in two runs; the face check costs a median of about 0.9 s on a generic turn (maximum 1.6 s) | [Plan 0061](../plans/completed/0061-cm2-generic-turn-continuity.md); [acceptance record](../evals/0061-generic-turn-continuity-acceptance.md); [Memory map](conversational-memory-delivery-map.md#how-the-fracture-closed-history) |
| 7 | CM-3a — candidates and the canonical V4 writer ("CM-3" without a letter names both CM-3a and CM-3b) | Extraction only proposes; one deterministic writer assigns the classification (never the speaker) and promotes with provenance, deduplication and contradictions. First cut: the owner's own `likes`, `dislikes` and `prefers`, by classic and streaming voice only, where every candidate, spoken value, answer and promotion requires the face and the voice of the same person verified on that turn (nothing is stored until both are enrolled), with an audited policy decision; `/chat` is out. It closes none of the benchmark's personal-scope write steps (they are CM-3b). A spoken "lo recordaré" from the LLM is never evidence of a write. Designed by [ADR 0021](../adr/0021-memory-candidates-and-the-canonical-writer.md) (`Accepted` 2026-10-16) and delivered in two plans: **0062** (candidate store, writer, extraction, no hardware) and **0063** (the spoken offer, the explicit answer and their hardware acceptance, with the owner's voice re-enrolled). Corte 1: a face-identified generic voice turn schedules a background candidate proposal (default-off `MEMORY_CANDIDATES_ENABLED`), `consolidate_turn`, `PROPOSE_MEMORY` and `COMMIT_MEMORY` are retired, and `memory_writer.promote` is the only place a candidate becomes a V4 literal fact. Corte 2: the classic and streaming voice routes speak the offer on a later generic turn (one WAV on the classic route, one more `audio` event on the stream; no wire change, robot untouched) and only an explicit spoken answer (a closed verb alone since Plan 0066; the value is optional and must match when present) promotes it or rejects it and erases the value, each step needing the face and the voice of the same person on that turn's own clip; anything else is the ordinary turn, byte for byte. The switch stays off by default (Pipec's decision). Nothing can be read back until CM-5. | CM-2; audit repairs | ADR 0021 `Accepted` (2026-10-16). **Complete 2026-10-16**: corte 1 [Plan 0062](../plans/completed/0062-cm3a-memory-candidates-and-writer.md) (closed 2026-10-15, PR #183; no spoken dialogue, no hardware; `just gate` 2972, CI selection 2955, baseline 2597/2580) and corte 2 [Plan 0063](../plans/completed/0063-cm3a-memory-dialogue.md) (`just gate` 3217; accepted by Pipec on the shared laptop: cases 1, 2, 3, 4, 6 and 7 passed, 5 partial, 8 measured, 9 not run; [record](../evals/0063-memory-dialogue-acceptance.md)). Open findings are in the cross-cutting table | [Memory map](conversational-memory-delivery-map.md#lifecycle) |
| 7b | CM-3b — the rest of the personal-scope write steps | What CM-7 needs that the first cut leaves out, each tied to the benchmark step that demands it: relations and literals about third parties (`extraction_family_and_pet`), `lives_in` and `works_at` with validity dates (`domicile_temporal_validity`), facts reported by another person (`provenance_attribution`), a disclosure rule such as "no menciones X delante de visitas" (`sensitive_preference_lifecycle`; Pipec decides between a new predicate and a dataset version bump), perceptual candidates that stay proposed (`perceptual_evidence_stays_proposed`, with P2.1), `nombre`/`edad`/`especie`, the first `SECURITY` datum, and a `confirm` operation in the benchmark dataset (a version bump). Third-party memory needs household rules decided in an ADR first. **Required before CM-7**, and before CM-6's correct and forget steps of `sensitive_preference_lifecycle`. *Narrowed by [ADR 0026](../adr/0026-owner-profile-card-and-the-read-side-of-memory.md) decision 9 (`Accepted`): tranche B keeps `lives_in` and the disclosure rule by voice, the owner's own data; the spoken capture of third parties, perceptual candidates and facts reported by another person move after CM-7.* | CM-3a (closed 2026-10-16); tranche B after CM-5b ([closing path](#closing-path-of-conversational-memory)) | **Tranche A closed 2026-10-22** ([ADR 0022](../adr/0022-household-rules-and-third-party-memory.md) `Accepted`, [Plan 0065](../plans/completed/0065-cm3b-a-channel-neutral-writer-core.md): one channel-neutral writer, relation validity, `species`, the stated age, the disclosure and `security` predicates (the repository refuses a `security` value until Step 0), the household capability pair as policy only, and dataset v3); **tranche B is emptied** by [ADR 0029](../adr/0029-it-knows-who-is-listening.md) decision 6 (2026-11-04, Pipec): `lives_in` is loaded only by the alta and `iroko-admin`, and «no menciones X» by voice with its audience rule moves to the family stage; dataset v4 rewrites `sensitive_preference_lifecycle` with a taste and moves `domicile_temporal_validity` to the staged pending scope | [ADR 0021 decision 13](../adr/0021-memory-candidates-and-the-canonical-writer.md#13-everything-this-adr-leaves-out-has-an-owner) **Order proposed 2026-10-16 (Pipec asked to continue it):** split into tranche A, before Step 0 ([ADR 0022](../adr/0022-household-rules-and-third-party-memory.md) and [Plan 0065](../plans/completed/0065-cm3b-a-channel-neutral-writer-core.md): the channel-neutral writer, the household capabilities, `species`, validity, the disclosure and SECURITY predicates, dataset v3), and tranche B, after Step 0 (spoken capture of third parties, reported facts, the behaviour of the disclosure rule, perceptual candidates). [Plan 0064](../plans/completed/0064-speech-and-dialogue-quality.md) (speech and dialogue quality) goes first. |
| — | Seed load ("step 0") | Owner, household, photos and classifications load in person from a local file or form as a second input channel of the CM-3 writer; seeded sensitive facts change only with owner verification; the owner → stranger matrix passes once per channel. Until then `just setup-personal` and `just onboard` remain the setup. Phase 0 also owns the security rules found while building CM-3a ([ADR 0021](../adr/0021-memory-candidates-and-the-canonical-writer.md) decision 13): enrolling face **and** voice as the first step of setup (today the voice is a separate script and no profile exists), who may pass and at which level, "you are with someone, still want it?" before speaking private data, and whether reads of private normal data move from `basic` to `strong` (ADR 0019 §3). | CM-3a for the owner's own data; CM-3b for household members | **Designed 2026-10-22 and revised 2026-10-23; executed in four plans: the storage (2026-10-23, Plan 0070, `just gate` 4511), the importer (2026-10-26, Plan 0071, accepted by Pipec), the session (2026-10-27, Plan 0072, `just gate` 4814, rehearsed end to end by Pipec on real hardware) and the amendment path (2026-10-28, Plan 0073, CI-selection suite 4846, accepted by Pipec on a database kept apart); Phase 0 is complete:** [ADR 0024](../adr/0024-seed-load-senses-secrets-and-channels.md) `Accepted` 2026-10-27 (the data pool of the commissioning, a secret stored by reference, contacts with phones, the confirmation of an assisted interview, the order of the commissioning; the field catalogue is [`seed-data-pool.md`](../architecture/seed-data-pool.md)), [Plan 0070](../plans/completed/0070-seed-load-data-pool-storage.md) closed 2026-10-23 (storage and provenance: migration 011, the pool predicates, a secret by reference, the adult child and the relatives, contacts, the commissioning record; nothing loads or reads them yet), [Plan 0071](../plans/completed/0071-seed-load-file-importer.md) closed 2026-10-26 (the file importer: `just seed-import`, a dry run by default, the owner's review, one transaction, `--replace` while commissioning; accepted by Pipec) and [Plan 0072](../plans/completed/0072-commissioning-session.md) closed 2026-10-27 (the commissioning session, `just commission`: face and voice in one flow with the PIN asked before each frame and reference, the biometric notice and the consents, the backups, the readiness report of the capabilities that exist today, closing the window and the acta with no household value; per-person voice settings and pronunciations stayed out of it by decision D-2, so the «voice calibration when a user is enrolled» row stays open; Pipec's own real alta followed on 2026-10-27). [Plan 0073](../plans/completed/0073-local-admin-crud.md) closed 2026-10-28 (the local administration, `iroko-admin`, a command-line CRUD over SSH through the canonical writers with the `admin_local` channel and no new network service: list/add/change/revoke the loaded pool and contacts, the owner's PIN for sensitive data read offline, one audit row per operation with no household value — migration 012 — and a read-only readiness recompute; accepted by Pipec on a database kept apart, [record](../evals/0073-admin-acceptance.md)); it **closes Phase 0** and is the amendment path after the closing. Its remote half (a VPN, a support session opened by the owner, encrypted backup, signed controlled updates, telemetry with no household value, and a periodic job that only proposes candidates) is [ADR 0025](../adr/0025-remote-administration-backup-updates-and-telemetry.md) `Accepted` (the local half shipped), with no plan yet. The structured read of the profile by voice shipped as CM-5a (Plan 0074) and the relatives of the alta as part of CM-5b (Plan 0078); the «are you with someone?» question belongs to block B. | Rules in [0050 *Non-goals*](../plans/completed/0050-server-audit-repairs.md#non-goals) |
| 8 | CM-4 — the conversation record and the diary, decided by [ADR 0027](../adr/0027-conversation-record-and-the-diary.md) (`Accepted` 2026-10-30): every conversation is kept as text, and only the owner's verified part feeds memory (episodes that declare owner, visibility, sensitivity, consent, validity and retention, and candidates for facts) | Episodes declare owner, subjects, visibility, sensitivity, consent, validity and retention. | CM-3a | ADR written; the pre-measurement is done ([Plan 0075](../plans/completed/0075-cm4-pre-measurement.md), 2026-10-29: the owner's voice verifies on 35.5 % of real turns, so the eligibility rule is **per turn**, confirmed by Pipec); **closed 2026-10-30** by [Plan 0076](../plans/completed/0076-cm4-conversation-record-and-diary.md), accepted on hardware ([record](../evals/0076-conversation-record-acceptance.md)); the diary has been read back by recall since CM-5b ([Plan 0078](../plans/completed/0078-cm5b-recall-what-the-owner-told.md), closed 2026-11-04) | [Memory map](conversational-memory-delivery-map.md#delivery-sequence) |
| — | The household protection answers requests, not mentions | Telling the robot that one's children or pet will do something reaches the model as an ordinary turn; asking for household data keeps the protected route and its denial. Found on hardware during [Plan 0076](../plans/completed/0076-cm4-conversation-record-and-diary.md). | — | **Closed 2026-11-02** by [Plan 0077](../plans/completed/0077-household-requests-not-mentions.md) (accepted on hardware in two rounds); step 1 of the [closing path](#closing-path-of-conversational-memory). Open and outside it, as rows of the cross-cutting table below: how the 3B model answers when a request slips through, and the Chilean-idiom coverage | The intent grammar and its corpus |
| 9 | CM-5 — authorized relevant retrieval, **split by [ADR 0026](../adr/0026-owner-profile-card-and-the-read-side-of-memory.md)** (`Accepted` 2026-10-28, when Plan 0074 closed) into **CM-5a** (the structured read: a small profile card in every identified turn and the explicit «what do you know about me», [Plan 0074](../plans/completed/0074-cm5a-profile-card.md), **closed 2026-10-28 behind the default-off `PROFILE_CARD_ENABLED`, accepted by Pipec on hardware**) and **CM-5b** (episodes and the semantic archive), **delivered together with R3** as «recall what I told you» ([closing path](#closing-path-of-conversational-memory)); the text that follows describes CM-5 as a whole | Person, visibility, sensitivity and validity filter vector and structured candidates before the prompt; a relevance threshold permits zero results and keeps provenance (RAG stage R1). Structured household reads beyond the children list and count go through the same authorized seam (since Plan 0078 the `normal` relatives of the alta are answered too; every other authorized family question still answers "todavía no está conectada"). The first reserved (`SECURITY`) category becomes real here: written with that classification by the CM-3 writer, read only at assurance `strong`, while `basic` (face alone) and strangers get the generic denial. CM-3a (closed 2026-10-16) writes no `strong`-only category: which datum it is is decided when CM-3b is planned ([ADR 0021](../adr/0021-memory-candidates-and-the-canonical-writer.md) decision 13). CM-5b carries R3's outcome: lexical (FTS5) and vector retrieval over authorized candidates in the diary, RRF, deduplication, zero results and measured quality, plus date questions and a fixed «no me acuerdo» when nothing qualifies. Its plan decides the embedding model and needs the ADR that [RAG §26](../architecture/rag-and-memory-retrieval.md#26-decisiones-que-requieren-adr-futuro) asks for. | CM-4 for CM-5b; CM-2, CM-3a and Step 0 for CM-5a (ADR 0026 decision 1) | CM-5a: closed 2026-10-28 (Plan 0074); CM-5b + R3: **closed 2026-11-04** by [Plan 0078](../plans/completed/0078-cm5b-recall-what-the-owner-told.md) behind the default-off `RECALL_ENABLED`, calibrated (`RECALL_MAX_DISTANCE` 0.43) and accepted by Pipec on hardware, 9 of 9 ([record](../evals/0078-recall-acceptance.md)); [ADR 0028](../adr/0028-recall-what-the-owner-told.md) `Accepted` with five amendments (recall units over the owner's verified words of ordinary turns and the diary, FTS5 + `vec0` + RRF with an absolute gate, strong and weak recall cues, spoken dates, «No me acuerdo de eso.» only when nothing qualified, the `normal` relatives of the alta read by a template, `granite-embedding:278m`), block A of the [closing path](#closing-path-of-conversational-memory). The sensitive read was block B: closed 2026-11-06 by [Plan 0079](../plans/completed/0079-block-b-sensitive-read-and-spoken-secrets.md) (see the closing path) | [Memory map](conversational-memory-delivery-map.md#retrieval) |
| 10 | CM-6 — correction and forgetting | Correction and deletion reach facts, relations, episodes, embeddings, summaries, caches and the live rows of `memory_candidates`; "ya no me gusta X", which CM-3a closes without writing, is made here as a correction. | CM-3a through CM-5, and CM-3b for the dataset's write steps | Unplanned | [Memory map](conversational-memory-delivery-map.md#forgetting) |
| 11–12 | CM-7 + PC-5 / P1.3 — the final acceptance, one delivery in two parts, memory first ([closing path](#closing-path-of-conversational-memory)) | **Memory (CM-7).** The real server/robot path proves `learn -> restart -> recall -> correct -> restart -> recall current truth -> forget -> do not disclose`, including turn-to-turn continuity, one `SECURITY` datum (`strong` reads it, `basic` and strangers do not) and the benchmark's **personal acceptance** verdict PASS without relaxed thresholds. Family acceptance stays `pending` for P3.2 (`recipient_only_message`, `two_adult_private_facts`) and the full suite keeps failing until then; no scenario is excluded. *Amended by [ADR 0026](../adr/0026-owner-profile-card-and-the-read-side-of-memory.md) decision 9 (`Accepted`, 2026-10-28): the scenarios that need third parties captured by voice and perceptual candidates move to a staged pending scope after CM-7 (dataset v4), reported like the family stage and never excluded; personal acceptance keeps the four frozen gates with no relaxed threshold.* **Integrated (PC-5).** Pipec completes voice, biometric, protected-memory, visual, correction, forgetting, denial, degradation and audible-output scenarios with literal transcripts; it decides whether scene description must work in streaming mode (today the robot refuses to start with streaming and server vision together, so scenes are classic-only); the CPU/RAM/latency budget and the Uvicorn concurrency (`UVICORN_LIMIT_CONCURRENCY`) are measured on the home server, which needs the explicit LAN deployment decision of [ADR 0013](../adr/0013-local-http-network-posture.md). | CM-0 through CM-6, including CM-3b | Unplanned; step 5 of the closing path | [Evaluation](../architecture/longitudinal-conversational-memory-evaluation.md#pc-5-longitudinal-gate); [Plan 0015](../plans/open/0015-personal-companion-design.md#pc-5--integrated-personal-companion-acceptance--unstarted) |
| 13 | P2.1 — structured perception and `WorldState` | Typed observations for people, objects, sensor state and location carry source, time, confidence and expiry; simulated sensors can later be replaced by firmware. | P1 controller and policy | Unplanned | [Memory and world state](../architecture/memory-and-world-state.md#world-state-is-not-long-term-memory) |
| 16 | P2.3 — bounded adaptation and initiative | Personality stays coherent and private; initiative is explainable, sparse, rate-limited and disableable. | P2.1, CM-7 | Unplanned | [P2.3](#p23--personality-adaptation-and-bounded-initiative) |
| 17 | P2.4 — outcomes and feedback | Decisions link to observed outcomes and authorized feedback without claiming unobserved learning. | P2.1, CM-7 | Unplanned | [P2.4](#p24--outcomes-and-feedback-contracts) |
| 18 | P3.1 / PC-6A — family onboarding and consent | One idempotent service, the seed-load writer extended to more members, creates members, roles, relationships, visibility and revocable consent. Phase 0 already loads the family's names and relations as entities ([ADR 0029](../adr/0029-it-knows-who-is-listening.md) *What Phase 0 already covers*); what is left is enrolling each member's face and voice, their roles and their own consent, as an extension of the alta. | PC-5 | Unplanned | [P3.1](#p31--family-onboarding-ui-and-consent) |
| 19 | P3.2 / PC-6B — family interaction acceptance | Adults, children, guests, pets, identity conflict, personal/shared/`recipient_only` isolation and biometric-failure recovery; the family-scope CM benchmark scenarios left pending by CM-7 turn GREEN. | P3.1, P2.1 | Unplanned | [P3.2](#p32--family-companion-interaction) |

After all 16 slices close with their own evidence, P4.2 may open its first
physical-architecture plan: the ESP32 body's boundary with the server (the body is
an ESP32 board, [ADR 0035](../adr/0035-deployment-worlds.md)), typed action proposals, capability checks, electrical and motion safety,
simulation, emergency stop and human acceptance before motion. P4.1 model-provider
evaluation ([ADR 0036](../adr/0036-model-providers-local-first.md), Proposed) is
optional and does not block P4.2.

### Closing path of conversational memory

**The core and the finish line (Pipec, 2026-11-11).** Every assistant answers when spoken to; what
makes Iroko a companion is the **memory engine**: it recalls what the owner did yesterday or last
week, what the owner told about someone, the names and data loaded in the alta, and it reads the tense of
the question (past, present, future) to find them, while the firewall decides who may hear each
datum. The rest of the pipeline is a set of modules already studied and replaceable behind their
ports: speech-to-text is measured and tuned on the owner's voice
([ADR 0023](../adr/0023-speech-to-text-model-and-decoding.md)); the language model and the voice are
limited by the machine, not by the design ([ADR 0004](../adr/0004-local-first-cognitive-policy.md),
[ADR 0036](../adr/0036-model-providers-local-first.md) `Proposed`). The work before the electronics
therefore closes the memory engine, not the modules.

The **finish line** is *ready for the electronics*: the laptop runs only the server, in a container
(ADR 0033, reserved), and the body is a client of the API
contract — the `robot/` Python client today, the ESP32 board of
[ADR 0035](../adr/0035-deployment-worlds.md) when it is connected. What depends on the real
microphone, camera and speaker (voice calibration, thresholds, barge-in) is tuned after the line,
on the body. This table is the one order to the line; it replaces the closing path of 2026-10-30
and the path to the MVP of 2026-11-06 and 2026-11-09, both kept in
[history](../history/roadmaps/closing-path-tables-2026-11-10.md). The *Older step* column keeps the
step numbers older documents cite. Queue rule 6 applies: rows are combined, and no outcome is removed.

| # | Delivery | Older step | Size | ADR | State |
|---:|---|---|---|---|---|
| 1 | The household protection answers requests, not mentions | Step 1 | Small | — | **Closed 2026-11-02** ([Plan 0077](../plans/completed/0077-household-requests-not-mentions.md)) |
| 2 | **Block A, «it remembers»:** recall what the owner told (search over the diary, dates, a fixed «no me acuerdo») and the `normal` relatives of the alta by voice (row 9, CM-5b + R3) | Step 2 | Medium | [0028](../adr/0028-recall-what-the-owner-told.md) | **Closed 2026-11-04** ([Plan 0078](../plans/completed/0078-cm5b-recall-what-the-owner-told.md)) |
| 3 | **Block B, «it knows who is listening»:** the sensitive read by voice (health, address, birthdays, the `SECURITY` datum) by levels, a silent camera check of who is listening, never keeping a spoken secret's value (row 7b emptied) | Step 3 | Medium | [0029](../adr/0029-it-knows-who-is-listening.md) | **Closed 2026-11-06** ([Plan 0079](../plans/completed/0079-block-b-sensitive-read-and-spoken-secrets.md), 10 of 10 on hardware, [record](../evals/0079-sensitive-read-acceptance.md)) |
| 4 | **The memory MVP:** «¿cuál es el nombre de mi papá/mamá?», «¿cuándo fui …?», the mother told from the father in the alta, the recall delivery filter | — | Medium | Notes in 0028, 0024 | **Closed 2026-11-10** ([Plan 0080](../plans/completed/0080-mvp-recall-phrasings.md), two rounds on hardware, [record](../evals/0080-mvp-recall-acceptance.md)) |
| 5 | The memory engine boundary (documentation only) | — | Small | [0031](../adr/0031-the-memory-engine-boundary.md) | **Accepted 2026-11-09** |
| 6 | **What the robot says:** the owner's tastes only on taste talk, never in a greeting and said to be the person's; no «tuteo» in the reply; the language rule follows the `usted` form; nothing claimed about the person without a source | — | Small | Note in 0026 | **Closed 2026-11-11** ([Plan 0081](../plans/completed/0081-what-the-robot-says.md), [record](../evals/0081-what-the-robot-says-acceptance.md); `usted` coherent but not obeyed by the 3B model, a model limit) |
| 7 | **The memory the MVP still lacks:** (a) a contact's phone by voice («¿tienes el teléfono de mi hijo?»: the alta stores it, no voice read returns it; its level and audience in the firewall), and (b) pending topics, the future tense («mañana te cuento», «el jueves voy al médico»): kept with their day, so that a greeting of the next one or two days may pick one up («¿cómo te fue ayer en el cine?»), a medical one under the sensitive level; (c) when a told event happened, when the owner says it; (d) **nothing loaded at the alta stays disconnected** (Pipec, 2026-11-11): «mi contacto 1», the partner, devices, mobility, hearing, vision, dwelling, access, lives alone and coverage get a voice read at their level, or a listed reason | — | Medium | [0037](../adr/0037-the-time-of-memories-and-a-contacts-phone.md) (Proposed) | **Part (a) and (d) closed 2026-11-12** ([Plan 0082](../plans/completed/0082-the-whole-alta-by-voice.md), the contacts and the rest of the alta by voice, 9 of 9 on hardware, [record](../evals/0082-alta-by-voice-acceptance.md)); **part (c) closed 2026-11-12** ([Plan 0083](../plans/completed/0083-spoken-time-and-when-it-happened.md), when a told event happened and the one reader of spoken time, 13 of 13 on hardware, [record](../evals/0083-when-it-happened-acceptance.md)); (b) the pending topics: [Plan 0084](../plans/open/0084-pending-topics-and-the-greeting.md) implemented and merged 2026-11-13, day 1 on hardware passed, the greeting days 2026-11-16 to 2026-11-19 ([record](../evals/0084-pending-topics-acceptance.md)) |
| 8 | **Block C, «it corrects and forgets»** (ADR 0032 amended by Pipec on 2026-11-13): C1 the database with good practices (one ISO 8601 time format in UTC, a key on every table, a declared foreign key with its rule for every relation, an index on every key and frequent filter, constraints, normalization, naming, no dead tables, a data dictionary, a health check and the engine's guards, the embedding-model guard among them); C2 correct and archive by voice (the owner's face and a closed verb; an archived memory is set aside, never destroyed) and delete for good only with the PIN in `iroko-admin`, with a deletion register a restore re-applies (row 10, CM-6); then the export of the owner's data, all or one person, readable by a person and as JSON, for a legal audit. It supersedes ADR 0026 decision 4 and the forget part of ADR 0019 explicitly, and decides the retention of memories for years; a web administration comes after the line | Step 4 | Medium to large | [0032](../adr/0032-block-c-hygiene-correct-forget-and-years.md) (Proposed) | Plan 0085 (C1) next, then 0086 (C2) and 0087 (export) |
| 9 | **Documents and reading through the camera (R2, Pipec 2026-11-11):** local documents (Markdown, plain text and PDF with a text layer) as one more source of the memory engine, versioned, classified, chunked and retrieved with owner, visibility, provenance and deletion on the search of block A, kept apart from what a person told; and «Iroko, lee esto»: a camera frame read by the local vision model (`qwen3-vl:2b`), kept as a document only after the owner confirms. An instruction inside a document is data, never an order. Recalibrated on the body after the line (its camera reads worse than the laptop's) | — | Medium | [0034](../adr/0034-documents-and-reading-through-the-camera.md) (Proposed) | Unplanned |
| 10 | **The home server:** an offline run with the internet off first (a cross-cutting row), then the server in a container on the laptop, the robot as a separate client, `/health` reporting Ollama, an orderly shutdown, backups. It amends ADR 0013 (LAN) and lifts Docker from the project's «future» list | — | Medium | [0033](../adr/0033-the-home-server-in-a-container.md) (Proposed) | Unplanned |
| 11 | **Block D, the final acceptance:** dataset v4 with LongMemEval's dimensions and an injected clock, a scale test, then CM-7 (memory) and PC-5 (integrated) measured in the container (row 11–12); the memory switches become default-on when it closes | Step 5 | Medium | — | Unplanned |
| 🏁 | **Finish line: ready for the electronics.** The laptop is only the home server; the body is a client of the API | | | | |

**After the line,** in this order unless a measurement says otherwise: the ESP32 body's client
(firmware or a thin gateway, [ADR 0035](../adr/0035-deployment-worlds.md)) and the recalibration on
the body — face, voice and speech-to-text thresholds, the **voice calibration at enrolment**
(moved after the line by Pipec on 2026-11-11: it depends on the real microphone; on the laptop the
35.5 % rate of verified owner turns of Plan 0075 is the accepted provisional limit), barge-in, the
privacy contract of the senses; the remote dashboard (the remote half of
[ADR 0025](../adr/0025-remote-administration-backup-updates-and-telemetry.md)); extracting the memory
engine (ADR 0031 decision 11); ADR 0030 (a household secret kept with
authorization, answering in company); **learning from conversation what the alta did not take**
(relatives, third parties and facts told by another person, kept after CM-7 by
[ADR 0026](../adr/0026-owner-profile-card-and-the-read-side-of-memory.md) decision 9, confirmed by
Pipec on 2026-11-11; until then the alta and `iroko-admin` load them); R4 (scanned PDF with a
dedicated OCR, tables, a reranker) only by measurement; then P2.1 (and R6 after it), P2.3, P2.4,
P3 and P4.2.

- **CM-5b + R3.** Both search the same thing: without documents, R3's lexical and hybrid search is
  how the diary is searched, so it no longer waits for R2.
- **CM-7 + PC-5.** One acceptance with two parts in a fixed order. PC-5 builds no memory: it proves
  on the real path what the earlier rows built.
- **R2 returns to the path (Pipec, 2026-11-11).** Pipec wants the RAG closed before the
  electronics: documents and reading through the camera are row 9, on the search of block A and
  before the home server, so the container ships with them. R4 stays conditional, by measurement;
  R6 waits for P2.1.
- **The generic prompt reads no household store** ([guardrails](../architecture/implementation-guardrails.md),
  Plan 0077 D-21). Row 1 rests on it: a turn routed to the model by mistake can invent and cannot
  reveal a stored value. A later row that adds household data to that prompt (row 7's greeting is
  one) first makes the household rule broad again.

ADR 0030 stays reserved for ADR 0029 decision 15, written after CM-7 + PC-5.

### Cross-cutting gates and conditional work

These items do not add slices. Required evidence belongs to the plan that creates
the load or the behavior; conditional work opens only after a measured need.

| Item | Classification | Required disposition | Owned by |
|---|---|---|---|
| CPU, RAM, token and latency budget | Cross-cutting required evidence | Measure bounded contention among STT, LLM, VLM, embeddings and candidate extraction, plus the Uvicorn concurrency limit, on the home server; no unbounded parallel workload or separate scheduler by default. | CM plans that add load; PC-5 acceptance |
| Liveness and replay defense | Conditional per [ADR-0016 §9](../adr/0016-face-and-voice-identity-fusion.md#9-replay-and-spoofing-measured-not-closed) | Replay is measured, not defended: a photograph plus a recording of the exact question can still reach `strong`. A liveness plan opens only if the measurement justifies it; making it a mandatory gate needs a new ADR that supersedes that section. Case 9 of Plan 0063's acceptance (the owner's photograph plus an earlier recording against the spoken offer and answer) was not run for lack of a second person or device. Decided by [ADR 0029](../adr/0029-it-knows-who-is-listening.md) decision 2 (`Accepted` 2026-11-06, Plan 0079; the hardware run did not attempt a replay): the residual risk is accepted for the home; a fingerprint or another factor joins later as a second verifier for the security level only |
| Voice calibration, short turns and the remaining biometric measurements (recalibration on a new device) | Unplanned (open; the step 0 seed load closed 2026-10-28, so it is unblocked); required before relying on voice beyond the laptop; the limit on short turns is a documented limit of Plan 0063, to be re-measured | **Calibration at enrolment.** Plan 0069 left the building blocks: a reading script of 85 invented phrases (24 form the short block), a corpus recorder that cuts the robot's clip offline, a deterministic bench and the threshold calibration. Not built: the robot running a short script at enrolment, a per-user profile and its settings (the «unclear» threshold, hotwords, a level and distance check). Not covered by the plan either: the body's microphone, noise with speech in it, Whisper's accuracy under noise, the Chilean markers («po», «cachai»), sentences with pauses, full phonetic coverage, intonation and other voices; the script is not validated by an expert. **Pipec, 2026-11-06:** after Plan 0080, as a tool (the script at enrolment, the level and distance check), with no new threshold: thresholds are device-specific and are measured again on new devices. **Remaining measurements.** Runtime impostors, genuine utterances of 1.5–3 s and a second acoustic condition were never measured (PC-3B). [Plan 0068](../plans/completed/0068-short-clip-speaker-measurement.md)'s Tasks 7 and 8 (the short-clip capture sessions and report: trimmed against raw clips, short against long references; they need at least three consenting adults) were deferred on 2026-10-21 and belong here. **Short turns.** The offer needs the voice of that turn: three clips of about 1.5 s gave `Speaker verdict: unknown` and nothing was offered, while of the owner's turns of about 3 s or more all but two were `verified`. By design (the firewall needs the voice of the same turn); the operator manual asks for a full sentence. Re-measure on the server board and in a second acoustic condition **From the closed explicit-answer item (Plans 0066 to 0068):** an answer said together with another sentence («no acepto» and then a clause) goes to the model because the words after a closed verb are read as a value; Pipec decides whether a closed verb that opens a longer utterance may count. **From the closed embedding-model item:** the embedding model (`granite-embedding:278m`, ADR 0028) is re-measured on the real body too. **Short questions and pauses (Pipec, 2026-11-12, Plan 0082 hardware):** a short security-level question («¿vivo solo?») hears the retry phrase because a clip under about 1.5 s rarely verifies the voice; a longer sentence passed. Two related open questions to study together: a pause longer than `VAD_SILENCE_MS` (1200 ms) splits one idea into two turns, and noise can cut a phrase (Silero VAD); and whether a voice verified moments before, in the same session, may count for a short security question (a security decision: it needs an ADR). | A plan that reuses `scripts/stt_*`, **after the [finish line](#closing-path-of-conversational-memory)** (Pipec, 2026-11-11: it depends on the real microphone, so it is done on the body); the recalibration of electronics track 1, or PC-5 if the laptop stays the body; PC-5 acceptance |
| Recalling the owner's health conversation units | Unplanned; after Plan 0079 ([ADR 0029](../adr/0029-it-knows-who-is-listening.md) decision 21, Pipec 2026-11-05) | The diary and the recall index keep what the owner tells about their day, but a unit the recall classifier marks `medical` («hoy fui al doctor por la presión») is never read back by voice (ADR 0028). For an older owner that day-to-day health is what a companion should remember. Reading it would reuse ADR 0029's sensitive level (the owner's face) and its silent camera check; it widens the read and is not needed for CM-7. | A small plan chosen by Pipec, after Plan 0079 |
| Database hygiene (review of 2026-11-03) | Unplanned; small; **before CM-6** (block C, its first task) | SQLite is configured well (WAL, `synchronous=NORMAL`, foreign keys, `secure_delete=ON`, `busy_timeout`) and needs no new extension. Found: two timestamp formats (11 columns default to `YYYY-MM-DD HH:MM:SS`, 16 are written as ISO 8601 with an offset; both live in `literal_facts_v4`), so comparing or ordering across them is wrong, and unifying needs table rebuilds; foreign keys without an index in V4 (`superseded_by`, `asserted_by_entity_id`, `confirmed_by_entity_id`, `source_memory_id`) and in the audit tables, so a cascade scans; dead or future tables (`facts`, `events`, `memories` retired with four tables naming it, `legacy_fact_migration_v4`, `outbox`, `sensor_*`); no data dictionary in one place; the per-connection pragmas live in code rather than in settings. The indexes of `conversation_*` and `PRAGMA optimize` shipped with Plan 0078 (migration 014). Since [ADR 0031](../adr/0031-the-memory-engine-boundary.md) (2026-11-09) the same plan (C1) also writes the engine's architecture guard, its integrity and staleness checks (counts only), the embedding-model guard (today a model change would compare vectors of two spaces and never re-embed the old units; ADR 0031 *Context* item 8) and the measured tuning in ADR 0031 decision 12's order (an FTS5 `trigram` comparison on a real Spanish corpus; `int8` vectors and durability pragmas only if the scale test asks). | Block C (C1) |
| Local admin follow-ups (`iroko-admin`) | Small, unscheduled; follow-up of [Plan 0073](../plans/completed/0073-local-admin-crud.md) | After the alta closes there is **no way to add a new contact, child or pet**: the importer refuses to run, and `iroko-admin` only changes the phone of an existing contact or revokes one, and its `add` and `change` edit the owner's own pool fields (not a child's or a pet's). `apply_contact_edit` is complete and tested, so a CLI verb to create a contact (a person who is not yet an entity) is the missing piece. Smaller: `revoke` always asks the PIN, even for a plain taste of the owner; a revoke of a pool fact audits no predicate id; the readiness `status` is a coarse present/absent derivation (it cannot tell `none` from `declined`). | A small plan chosen by Pipec; before the care capabilities rely on a contact |
| Loading and exporting the pool | Unplanned; named by [ADR 0024](../adr/0024-seed-load-senses-secrets-and-channels.md) and [ADR 0025](../adr/0025-remote-administration-backup-updates-and-telemetry.md) decision 11 | Three tools around the one plan of operations, none built: the Excel/CSV-to-TOML converter that runs on the interviewer's machine (a spreadsheet library in an optional group the server never installs); the `export` from the database to the importer's own TOML without secrets, so a load can be compared with the original sheet and the round trip tested; and the interview's interface with the 107-question catalogue. The importer reads only TOML and refuses once an alta is closed, so they matter for the next robot or household. | Later Step 0 plans |
| Remote administration (the remote half of ADR 0025) | Unplanned; [ADR 0025](../adr/0025-remote-administration-backup-updates-and-telemetry.md) is `Accepted` for its local half only | The private VPN and the admin web surface (levels B and C), the support session the owner opens at the robot, encrypted backups, signed and reversible updates, telemetry with no household value, the agent that opens the connection itself, and the periodic job that only proposes candidates (it needs CM-4). The installation id and the three consents are already recorded in the acta of the alta. | The first remote plan, chosen by Pipec |
| A closed acta cannot be corrected | Observation, no plan | The acta is frozen by design: every writer refuses a closed record, so a wrong declaration stays. The real alta declared the disk encryption `no` while BitLocker was active ([Plan 0072](../plans/completed/0072-commissioning-session.md) record). A correction path (an amendment record beside the acta) is not designed. | Decide only if it starts to matter |
| Latency on the target host: the language model, the recall turns and the face check | Cross-cutting evidence; belongs to the move to the home server; the face check is measured, not judged ([ADR 0020](../adr/0020-authorized-actor-in-the-conversation.md) *Review* trigger) | **Language model.** Measured in Plan 0069's live runs: in turns that used the language model, a median 19 s and up to 57 s (Ollama on the CPU with the candidate extraction in the background); the speech-to-text is no longer the bottleneck (median 2.6 s). The 60 s window of a spoken offer is eaten by turns of 20 to 40 s (seen in Plan 0068's counts). **Recall turns on the shared laptop GPU (Plan 0078's acceptance).** Two recall turns waited 24 s and 60 s: the diary job had started a summary between conversations and cannot be interrupted, or the chat model, candidate extraction and the embeddings swapped in 2 GB of GPU. Whisper's known-hallucination filter also discarded a 21.6 s story (`422`, «No speech understood»), a Plan 0069 follow-up **Face check on a generic turn.** Plan 0061's acceptance measured 6 generic identifications on the development laptop (shared with Docker, no GPU): median about 0.9 s, maximum 1.6 s, on turns that take 7 to 13 s in total. Decide whether that is acceptable once the home server is the runtime; options already named by the ADR: an earlier face check in the router, or warming the face model per request. Nothing to do until a measurement on the server says it matters | PC-5 acceptance (the budget row above); the homelab move; the STT follow-up (the hallucination filter); a homelab measurement of the face check |
| Spoken commands: fixed phrases, a short manual, a real-speech corpus and the command vocabulary | Unplanned (idea of 2026-10-28; vocabulary: Pipec, 2026-11-09, decided by its own ADR) | Like a smart speaker, the robot understands a small set of fixed phrases the person learns (a short manual: «oye robot, haz X», «oye, borra esto»), and accepts natural variants only where that is safe. Today the intents are closed patterns over normalized text (`cognition/intent_resolution.py`), so a speech-to-text variant breaks them (Whisper wrote «sabe» for «sabes»; fixed for that phrase only). Research, not desk work: record the real users (the product targets older adults: stutters, pauses, fillers), measure with the speech-to-text bench, normalize fillers, tolerate one letter in keywords but never in sensitive data, ask a closed yes/no when a phrase looks like a command, and pick phonetically distinct commands. Ideas gathered while testing: an encrypted backup (already ADR 0025 decision 6), a per-person habitual phrase as a signal, and a daily conversation summary (the CM-4 diary of [ADR 0027](../adr/0027-conversation-record-and-the-diary.md): the full text is kept and one summary per conversation is written from the owner's verified turns). Also from the Plan 0074 run: `is_prompt_echo` missed a Whisper echo that carries the hotwords before the initial prompt (**fixed 2026-10-29**: it now also checks «hotwords prompt», with the hotwords of the same call). **Vocabulary (Pipec, 2026-11-09).** A bounded set of canonical phrases per data question of the alta, tolerant variants of each, a confirmation of near-misses («¿Me preguntas por…?») and a marker such as «Iroko,» that says a question is for the robot. It is built from the canonical-phrase table of the Task 0 session of [Plan 0080](../plans/completed/0080-mvp-recall-phrasings.md) and from the real failures, not from a guess. Intonation is not a signal: speech-to-text gives none, and the question mark already misses about 3 of 10 questions ([ADR 0023](../adr/0023-speech-to-text-model-and-decoding.md)). Today each shape is added to the closed patterns one at a time (as Plan 0080 did); this row is the systematic answer. Still open from the closed «MVP recall phrasings» item: other phrasings that a real-speech session finds, and the speech-to-text slips (the day questions failed twice on speech-to-text, not on the grammar). | A plan with a real-speech corpus, after its ADR (unblocked: CM-5b closed 2026-11-04) |
| Chilean Spanish coverage: idioms, diminutives and fillers (Pipec, 2026-11-02) | Unplanned; **measure first**. Pipec wants it kept visible | Pipec asked that the robot understand how people really speak in Chile and raised the published Chilean dictionaries of idioms. Do not load a dictionary into the closed lists: every extra word of a list can cut a conversation again, and almost no idiom decides whether a sentence asks for household data. Run first one short real-speech case (about ten sentences with idioms, said by Pipec, outcomes only) that tells **where it fails**: Whisper writing the word, or the model understanding it. If Whisper fails, it belongs with *Spoken commands* below (a real-speech corpus). If the model fails, weigh with evidence a short glossary in the prompt, or retrieval after CM-5b; a published dictionary needs its licence read before it ships inside the product. The idioms hardware already showed went into the lists of `cognition/household_request.py` ([Plan 0077](../plans/completed/0077-household-requests-not-mentions.md), D-11 and D-22). | The plan that adds the real-speech corpus, or a hardware session (unblocked: CM-5b closed 2026-11-04) |
| The model's own answers (the 3B model) | Open, unplanned; small. What the prompt and the card could fix closed with [Plan 0081](../plans/completed/0081-what-the-robot-says.md) (row 6 of the [path to the finish line](#closing-path-of-conversational-memory)); the pending topics of the greeting are row 7, ADR 0037 | **What is left is the model, not the code** (Pipec, 2026-11-11: fix our code and prompt, measure the model). On `qwen2.5:3b`: general facts stated wrongly (a birth month, a footballer's brother, the time of day: the prompt holds no clock); «Kachai» once taken for a name; when a household request slips past the lists it invents the answer (it holds no stored value; a listener hears a lie); it mirrors what the owner just said as its own taste (Plan 0081 case 3: the source is the session, not the card); it ignores the `usted` form although the language rule now asks for it (0 of 3, coherent 3 of 3); without a card it reads «¿qué me gusta…?» as a question about itself. Each is measured again with the next model before any code is written for it. | P4.1 (the second local model); before an older-adult user; PC-5 acceptance |
| The local suite downloads Whisper | Small, unplanned (found on 2026-11-04) | `just test` runs the `slow` tests, and `tests/slow/test_stt_transcription.py` calls `stt.preload()`, which downloads Whisper medium (about 1.5 GB) when the cache is empty, although the `slow` marker promises a skip when the model is absent; only the Piper tests have a skip guard. | A small test fix |
| Privacy contract of the senses | Required before any new continuous capture | What is kept, what never leaves the device, and a physical switch and indicator once there is hardware. The contract is written as [ADR 0024](../adr/0024-seed-load-senses-secrets-and-channels.md) decision 3 (`Accepted` 2026-10-27). It gates new capture (an always-on microphone or camera, recording beyond one turn), not the purchase: porting today's per-turn capture to the Pi does not need it. | An amendment to ADR 0024 decision 3, written with the first new continuous sense |
| Diarization / simultaneous speakers | Required decision, conditional implementation | Before P3.2 becomes `Ready`, choose an explicit turn-taking constraint or local diarization. Speaker verification is not diarization. | P3.2 readiness design |
| Barge-in (interrupting the robot while it speaks) | Product gap, required decision, not scheduled | Pipec asked for it on 2026-10-07: streaming with STT already feels fluid on the laptop, and talking over the robot is the natural next step. Today the loop is half-duplex by design (`robot/app.py`, [ADR-0002](../adr/0002-server-robot-separation.md)): the microphone is closed while the robot speaks, so it never transcribes its own voice, and a turn is recorded only when the stream ends whole. Supporting it needs acoustic echo cancellation (the speaker and the microphone share the laptop today), voice detection while `SPEAKING`, a cut of the playback and of the stream (the server tolerates a client that leaves, but it is not proven that Ollama stops generating), and recording only the sentences already spoken (`StreamState.response_parts` is a base). It does not block or change [Plan 0058](../plans/completed/0058-stream-protocol-repair.md). | Unplanned; decide with the hardware (the recalibration of electronics track 1, where echo cancellation depends on the real microphone and speaker) or in PC-5 if the laptop stays the body |
| Ollama down or cold: the health signal and the warm-up phrase | Partly addressed by Plan 0064, closed (a start-up warning; `/health` still does not report Ollama); the cold-start failure is an operational observation of Plan 0063's acceptance, small, not scheduled | **Ollama-down signal.** Pipec forgets to start Ollama and the first symptom is the fallback phrase ("mi cerebro todavía se está despertando"): `GET /health` passes while Ollama is unreachable, so neither the robot's start-up check nor the operator sees it (seen 2026-10-09 while accepting Plan 0060: two greetings spoke the fallback phrase with `reason=llm_error`, then answered normally once Ollama ran). Candidate: report Ollama reachability in `/health` and log one clear warning at server start and when the first stream fails, without making the server refuse to start (the deterministic branches do not need the model). The robot stays a generic audio client: it only reads the health answer. Sketch only; it needs a plan and a decision on whether `/health` may report degraded. Seen again on 2026-11-04 (Plan 0078's acceptance): a round started with Ollama stopped, `/health` passed and the robot spoke the warm-up phrase. **Cold start and the model-down phrase.** The first chat turn after Ollama started failed with a 500 twice while the laptop had about 460 MB of free memory (the model was loading) and the stream spoke the fallback phrase; the next turn worked, and time to first audio ran from 7 s to 90 s with the machine's load. Warming the model first avoids it; the Ollama-down signal above (same row) would make it visible. The fallback phrase and the controller phrases are in tuteo since Plan 0064; the start-up probe now logs one warning when Ollama is down but cannot see this cold-start failure | The home-server deployment plan (ADR 0033, Pipec 2026-11-06): a container's health check needs it; a small plan chosen by Pipec; the homelab as runtime |
| Language of the reply and confabulation with an empty session | Language: addressed by Plan 0064 (a rule closes the master prompt and the streaming contract; `eval-chat --mode stream` on `qwen2.5:3b`: 1 of 97 before, 0 of 98 and 0 of 97 after; 0 of about 24 hardware turns on 2026-10-19). Confabulation: open finding, small, not scheduled | The word-list heuristic judged 1 of 53 (second run) and 0 of 50 (first run) `history` replies not Spanish, and 2 of 60 `public` ones; the report keeps counts only, so the reply was not located and was accepted as the heuristic's limit (Pipec, 2026-10-13). With an empty session the small local model invented a value (answered "7") instead of admitting it does not remember: the same confabulation Plan 0059 left open, not a continuity defect. Both belong to a prompt or model slice; also the STT echo of its own prompt ("Conversación con un robot doméstico llamado Iroko") reached the controller once and was harmlessly suspended. Plan 0063's hardware acceptance (2026-10-16, the shared laptop) saw the language problem again, on real turns: about 2 of 12 generic or fall-through turns answered partly or wholly in French | A prompt/model-quality plan, with the language of the reply in `scripts/reply_language.py` as its instrument |
| Local unlock on a robot without a keyboard | Product gap, Pipec's decision, not scheduled | The PIN is still needed for set-up, for enrolling and revoking face and voice (`biometric_admin`) and for `forget` (a spent `personal_memory_forget` grant, ADR 0019), because face and voice are replayable (ADR-0016 §9) and the PIN is not. Today it is typed at the robot's terminal (`ROBOT_OWNER_UNLOCK_PROMPT`, off by default) or in the scripts, which does not fit a robot with no keyboard or screen (raised by Pipec on 2026-10-13). The PIN is checked in one place (`unlock()` in `cognition/owner_authentication.py`) and everything downstream sees only a scoped `LOCAL_UNLOCK` grant, so a fingerprint reader would be a second verifier that issues the same grant: scopes, single use, expiry and policy stay as they are, and [ADR 0020](../adr/0020-authorized-actor-in-the-conversation.md) decision 6 already covers it. The sensor needs its own ADR (a new sense on the robot, which would send only a match result, and the privacy contract of the senses). | An ADR with the electronics track; Pipec chooses when |
| Wiring of the personal-memory capabilities and the leftovers of CM-3a | Follow-up of [Plan 0060](../plans/completed/0060-cm1-personal-memory-capabilities.md) and of [ADR 0021](../adr/0021-memory-candidates-and-the-canonical-writer.md), scheduled through CM-2 to CM-6 | **Wiring.** The policy exists. CM-3a now consumes `propose`, `read` and `confirm` for the owner's own preferences (Plans 0062 and 0063, audited before the effect); `correct` and `forget` are still consumed by nothing. Left for the wiring plans: `confirm` is reachable only with face and a verified voice (it has no PIN route; a `personal_memory_confirm` scope would add one); `forget` cannot be exercised when the owner's face identifies the turn because the PIN is then not consulted (decided by [ADR 0020](../adr/0020-authorized-actor-in-the-conversation.md) decision 6: a grant of the operation's own scope is consulted after a face match; it is built by the plan that wires `forget`); single use protects a request, not an erasure, so a second `forget` target needs a fresh grant ([ADR 0019](../adr/0019-personal-memory-capabilities.md) §6). **Leftovers of CM-3a.** A candidate that contradicts an active fact is closed without writing ("ya no me gusta el mate"); that is a correction and CM-6 owns it, and CM-6's forgetting also reaches the live values of `memory_candidates`. `/chat` cannot create or confirm a candidate (no audio, so no `strong`); a `personal_memory_confirm` scope would change that and is Pipec's decision, unscheduled. [Plan 0063](../plans/completed/0063-cm3a-memory-dialogue.md)'s acceptance (2026-10-16, [record](../evals/0063-memory-dialogue-acceptance.md)) measured on the shared laptop only: voice check to stored row 30 s and 60 s on the two clean runs, the explicit answer parsed 2 of 4 times (see *Closed foundations*) and short turns cannot carry an offer (see the voice-calibration row). **Not run:** case 9 (a photograph plus an earlier recording; replay stays measured, not defended, see the liveness row), any measurement on the home server (extraction contention, the cost of the third face-and-voice resolution per turn there) and a second person for the "another voice" and "another face" cases, which were substituted by a translator app, a Windows text-to-speech voice and a photo on a phone. The switch `MEMORY_CANDIDATES_ENABLED` stays off by default; turning it on for daily use is Pipec's decision. The benchmark has no `confirm` operation and no restart seam: a dataset version bump (CM-3b or CM-7 preparation) and a driver seam (CM-7 preparation). | CM-2 ADR; CM-3 to CM-6; CM-6; a homelab session with a second person; CM-3b; CM-7 preparation |
| R2 minimum documentary source | **On the path** (Pipec, 2026-11-11): row 9 of the [path to the finish line](#closing-path-of-conversational-memory), with reading through the camera; it was after CM-7 + PC-5 since 2026-11-06. Scope changed the same day: R2 was Markdown or text only (2026-10-30), with PDF in R4 | Local documents are versioned, classified, chunked and retrieved with owner, visibility, provenance and deletion, on the search of CM-5b, as one more source of the memory engine ([ADR 0031](../adr/0031-the-memory-engine-boundary.md) decision 13), kept apart from what a person told; an instruction inside a document is data. The first source is Markdown, plain text **and PDF with a text layer** (a Spanish extraction bench; the library and its licence are read before it ships). | ADR 0034, then its plan; [RAG §25](../architecture/rag-and-memory-retrieval.md#25-secuencia-de-evolución) |
| R4 OCR, advanced chunking and reranking | Conditional | After R2, only when real documents or the metrics of the search prove R2 insufficient: scanned PDF and OCR, tables, better chunking, a reranker. OCR competes with Whisper and Ollama for RAM and GPU. | [RAG evolution](../architecture/rag-and-memory-retrieval.md) |
| Extracting the memory engine | Unplanned; **after CM-7 + PC-5** (Pipec, 2026-11-06) | Move the firewall and product modules out of `memory/` and put the four kinds of coupling behind ports, with the two policies and their isolation tests; no public package. | A plan after the final acceptance |
| The home-server deployment | Unplanned; **before block D** (Pipec, 2026-11-06) | The laptop becomes the home server, without VS Code: the server in a Docker container, the robot a separate client (later the ESP32 body; the server later moves to a Raspberry Pi or Jetson class board, [ADR 0035](../adr/0035-deployment-worlds.md)). Needs an ADR that amends [ADR 0013](../adr/0013-local-http-network-posture.md) (LAN binding), lifts Docker from the project's «future» list and the non-goal of `server-production-baseline.md`, and decides how the loopback-only owner unlock and biometric enrolment work when the client is not on the same host, where `commission` and `iroko-admin` run, the data volume, backups, encryption at rest, GPU access under WSL2 and an orderly shutdown (the last turn is written after the reply). Testable without electronics: the robot client on the same laptop against the container. Docker Desktop's own VM uses RAM; the saving comes from closing the development tools and moving capture to the board. | ADR 0033, then its plan |
| Offline run: the whole pipeline with the internet off | Unplanned; small (Pipec, 2026-11-10); verification of local-first, before the model-provider evaluation of P4.1 | Switch the network off and run the real turn end to end (speech to text, identity, memory engine, controller, language model, speech synthesis, audio out), plus the start-up and one enrolment check. Nothing may reach out at runtime: every failure is a hidden network dependency to remove or to list. The Hugging Face cache must be present offline: the pinned speaker model (`just speaker-calibration model-contract` downloads it once) and Whisper are read from `~/.cache/huggingface`, and an empty cache breaks them at start-up; set `HF_HUB_OFFLINE=1` to prove it. Ollama must have its models pulled beforehand. Record the outcome in a short evaluation record. | A small plan or a manual acceptance, before the deployment of ADR 0033 is declared done; PC-5 acceptance |
| Memories for years | Decision, before CM-7 | The eligible record lives 365 days (30 for the rest, 200 MB in total) and its episodes and recall units go with it, so «¿qué hice hace dos años?» cannot work. Options: keep it; give episodes their own retention; or consolidate the essential into confirmed facts. A product and consent decision, not an efficiency one. | ADR 0032 |
| Third-party speech and Chile's Law 21.719 | Open; legal advice pending since [ADR 0027](../adr/0027-conversation-record-and-the-diary.md) | Text of people other than the owner is kept unused (30 days, 365 inside an owner conversation). The law's entry into force and whether it applies to domestic use are not verified here. The retention is configurable, so it can be shortened without code. | Pipec |
| Open Memory Protocol Initiative | Watch only | A protocol to move agent memory between systems, pre-1.0, no reference implementation (checked 2026-11-09). Read it when it publishes a specification, before an export format is designed. | ADR 0031 *Review* |
| Alternative TTS | Conditional, non-blocking | Piper and the WAV contract remain the baseline. | Future plan outside the critical path |
| Care and education | Future responsibilities, non-blocking | Separate ADRs, policies, outcomes/feedback and acceptance after the companion core. | Future responsibility profiles |

### Pre-purchase readiness gate — "plug it in and it works"

Revised 2026-09-30 on Pipec's decision; it replaces the 2026-09-25 rule "buy the
electronics when CM-7 closes" and its blocks A–D. The server is a generic audio
API and the robot a generic audio client
([ADR 0002](../adr/0002-server-robot-separation.md)), and `robot/` already owns
capture, playback and the camera. Buying electronics therefore splits into three
independent tracks, and only the last two wait on software:

| Track | What | Gate | Why |
|---|---|---|---|
| 1. The ESP32 body | An ESP32 board with a microphone, a speaker and a camera replacing the laptop's ([ADR 0035](../adr/0035-deployment-worlds.md)) | None in the cognitive queue | The server does not change. Required work: **an ESP32 client** (firmware that speaks the API contract, or a thin gateway), because the Python `robot/` client cannot run on an ESP32 and no plan lists this item; and repeat the face ([Plan 0030](../plans/completed/0030-real-camera-face-acceptance.md)) and speaker ([Plan 0047](../plans/completed/0047-speaker-evidence-calibration-study.md)) calibrations on the new devices, because the thresholds `0.5815` and `0.4834` were measured on the laptop and are device-specific. |
| 2. New kinds of sensors | Temperature, distance, presence and similar | The P2.1 contract is designed (row 13) | A sensor is an adapter behind a typed observation; choosing sensors before the contract can force rework. |
| 3. Anything that moves | Motors and actuators | P4.2, after the 16 slices | Typed action proposals, a safety layer, an emergency stop and human acceptance come first. |

**What "it works when plugged in" means for any new device.** A device is an
adapter behind an existing software contract, never a reason to change one:

1. It produces a typed observation or typed identity evidence with source, time,
   confidence and expiry (P0.1 vocabulary; P2.1 for sensors; PC-4 for identity).
2. Missing, weak or failed evidence is `unknown` and grants nothing by itself;
   authorization stays in the policy layer, so a new sensor cannot widen access.
3. It is proven first as a simulator or replay against the same contract tests;
   replacing the simulator by the real device must not change a test.
4. The server does not learn the device exists (server = generic API, robot =
   generic client); only the adapter in the robot side knows the hardware.
5. Physical *actuation* is a different, later gate: P4.2 (typed action
   proposals, safety layer, emergency stop, human acceptance). An LLM never
   commands a motor directly.

**Not required before buying, on purpose:** a fingerprint reader or any other
electronic biometric (future adapter for the identity seam, no ADR yet), a cloud
provider (P4.1, optional, ADR 0036), R4 OCR, alternative TTS, and the care and
education responsibilities. Independent of the queue: the second GT-P3110 tablet
(a hobby task).

**Who decides.** Closing a row is evidence-based (each plan's own gates). The
decision to spend money is Pipec's and is not made by this document; it only
states what is ready.

**Pipec's decision (2026-11-04): no electronics purchase is planned.** The laptop
stays the robot's provisional body (the target body is an ESP32 board, ADR 0035), and every plan is written and accepted on it until Pipec
decides otherwise. Track 1 remains ungated, but nothing waits for it: the work that
needs the new devices (repeating the face and speaker calibrations, the remaining
biometric measurements on a second acoustic condition, echo cancellation for
barge-in) is postponed to that purchase, while the voice work that helps on the
laptop (a short calibration at enrolment, short-clip verification) may be planned
on its own.

### How an agent advances the portfolio

1. Read this table to identify the first row whose dependencies are closed.
2. Confirm the operational cursor in [`docs/plans/README.md`](../plans/README.md#operational-board).
3. Execute only the single explicitly authorized `Ready` plan in `NOW`.
4. Close it with observed RED/GREEN evidence, review, required gates and real
   acceptance where applicable.
5. Update this row, the specialized delivery map, current state and the plan
   router in the same closure documentation change. Closure narratives live in
   the completed plan, not in this table.
6. Re-audit the next row before assigning a plan number or writing its detailed
   plan. New evidence may split or combine implementation plans, but it must not
   silently remove the row's product outcome.

*A table of "what is really missing" per row, checked on 2026-10-02, was removed on 2026-11-10: its rows
(CM-1, the streaming repair, CM-2, CM-3, PC-5) were closed or are carried by the portfolio and the
cross-cutting table above, and it described them as pending.*

## Closed foundations — history

Closed work is summarized here in one line per phase; its evidence (commands,
counts, commits, real-hardware runs) lives in each completed plan, not in this
file.

| Phase | Outcome | Closed by |
|---|---|---|
| C0 | Canonical tracked documentation; `project-history/` is reference-only | Documentation pass |
| P0.1–P0.2 | Typed domain models; active-person context with `identified`, `probable`, `unknown` and `ambiguous`; working history isolated by identity | [0001](../plans/completed/0001-cognitive-domain-models.md), [0002](../plans/completed/0002-active-person-context.md) |
| P0-S | Public biometric enrollment quarantined; least-exposed desktop defaults; cloud providers quarantined | [0002a](../plans/completed/0002a-local-first-provider-quarantine.md), [0002b](../plans/completed/0002b-biometric-enrollment-quarantine.md), [0002c](../plans/completed/0002c-desktop-security-and-drift.md) |
| P0.3 | Small typed controller; deterministic date and age; no ToolRegistry until several real tools share a need | [0003](../plans/completed/0003-typed-controller-and-deterministic-tools.md) |
| P0.4 | Relational memory V4: entity-ID relations, cardinality, lifecycle and a dry-run-first migration; v3 stays the runtime compatibility path | [0004](../plans/completed/0004-relational-memory-v4-design-and-migration.md), [0005](../plans/completed/0005-relational-memory-v4-implementation.md) |
| P0.5 | Deterministic fail-closed household authorization; policy-gated V4 reader and family tools | [0007](../plans/completed/0007-household-authorization-foundation.md)–[0010](../plans/completed/0010-policy-gated-v4-family-tools.md) |
| P0-C | Every public route obeys the controller/policy boundary; combined operator acceptance on 2026-08-25 | [0011](../plans/completed/0011-p0-closure-and-acceptance.md)–[0023](../plans/completed/0023-p0-grounded-visual-dialogue.md) |
| P1.1 / PC-1 | A freshly authenticated owner hears the children's names through the real server/robot path; without authentication nothing is revealed | [0024](../plans/completed/0024-owner-authenticated-memory-mvp-design.md)–[0028](../plans/completed/0028-owner-authenticated-memory-runtime-acceptance.md) |
| X1 | Server production baseline: privacy, uploads, PIN hardening, SQLite transactions, CI, Uvicorn, lifecycle, OpenAPI and streaming | [0031](../plans/completed/0031-server-production-baseline-design.md)–[0045](../plans/completed/0045-async-test-client-resources-parity.md), [0048](../plans/completed/0048-fastapi-baseline-final-hardening.md) |
| CM-0 | Longitudinal benchmark and its RED baseline | [0046](../plans/completed/0046-reproducible-longitudinal-memory-baseline.md) |
| P1.2 / PC-2…PC-4 | Consented face evidence (threshold 0.5815), consented speaker evidence (0.4834) and fusion: face `basic`, face plus voice `strong`, another person vetoes | [0029](../plans/completed/0029-consented-local-face-evidence.md), [0030](../plans/completed/0030-real-camera-face-acceptance.md), [0047](../plans/completed/0047-speaker-evidence-calibration-study.md), [0053](../plans/completed/0053-consented-speaker-runtime-evidence.md), [0054](../plans/completed/0054-face-default-identity-fusion.md) |

Closed items moved out of the cross-cutting table on 2026-11-10 (each keeps its evidence in the plan or ADR named):

- **Embedding model for the memory index (Spanish):** closed 2026-11-04, `granite-embedding:278m` by
  [ADR 0028](../adr/0028-recall-what-the-owner-told.md) decision 10, shipped by
  [Plan 0078](../plans/completed/0078-cm5b-recall-what-the-owner-told.md) (warmed at start-up; 0.25 to 0.30 s
  warm, 6 to 10 s cold on the laptop; chosen on the invented set of
  [Plan 0075](../plans/completed/0075-cm4-pre-measurement.md), ROC-AUC 1.00 against 0.98 for
  `nomic-embed-text`). Left: the re-measurement on the real body (the voice-calibration row) and the
  cross-model guard (block C, C1).
- **MVP recall phrasings and the sides of the family:** closed 2026-11-10 by
  [Plan 0080](../plans/completed/0080-mvp-recall-phrasings.md), accepted on real hardware
  ([record](../evals/0080-mvp-recall-acceptance.md)). Left: the relatives are stored lowercase in the seed
  data (not the importer), so the template says them lowercase and `iroko-admin` can correct them; other
  phrasings and speech-to-text slips are in the spoken-commands row.
- **A turn is capped at 28 s on the robot:** closed by Plan 0080 (`MAX_UTTERANCE_S`, the robot's `.env`).
- **The model says it saved something that was not written:** addressed by
  [Plan 0064](../plans/completed/0064-speech-and-dialogue-quality.md) (`claim_guard`); the lexicon is
  closed, so a wider one only if a miss is seen.
- **The explicit answer against the speech-to-text:** closed in code by Plans 0066 to 0068 (a closed verb
  alone is enough, a reply listening mode and hotwords, a retry when only the voice failed, ADR 0021
  decision 9 amended; the bar of 4 of 5 promoted was not reached on 2026-10-21, 1 promoted). Its open
  follow-ups moved to the voice-calibration row and the latency row.
- **Memory engine contract:** [ADR 0031](../adr/0031-the-memory-engine-boundary.md) `Accepted` 2026-11-09: one
  core behind a policy port checked at every boundary; verified that 20 of the 77 modules of `memory/` import
  `server.cognition`, which block C1's guard test and the extraction plan address.

Real-hardware acceptances are historical: they cover only the recorded
scenarios, devices and configuration and are not a new run on the current tree.
Limits carried forward from these phases, each owned by a queue row or a
cross-cutting item above: no liveness (a photograph identifies at `basic`) and
replay measured but not defended; on hardware Plan 0054 proved the two-faces
veto, while the veto of a single other enrolled person was proven only against
test doubles until Plan 0055 (Task 4) pinned it against real role rows in automated tests; the calibrations are provisional (one owner,
few impostors, laptop devices); the grant proves the PIN, not the speaker (bound to
an operation since Plan 0051; the memory capabilities are CM-1's remaining plan);
the generic conversation has short-term continuity for the identified person (CM-2, closed 2026-10-13); CM-3a (Plans 0062 and 0063, closed 2026-10-16) can hold a candidate, offer it by voice and promote it to one canonical fact only after an explicit spoken answer, behind a default-off switch; the owner's tastes and two name datums are read back (Plan 0074, `PROFILE_CARD_ENABLED`), what the owner told is recalled (Plan 0078, `RECALL_ENABLED`) and the sensitive data are read by voice (Plan 0079, `SENSITIVE_READ_ENABLED`); nothing is corrected or forgotten until CM-6.

## P1.3 — Personal companion acceptance (PC-5)

Demonstrate the full companion flow with `just run-server` and
`just run-robot`: voice, face/voice evidence, authorized personal data,
longitudinal memory, on-demand scene description, deterministic claims, and
Piper output. A raw
frame never enters the text LLM; the controller receives only typed,
policy-approved evidence and scene results.

**Exit gate:** Pipec can complete approved personal scenarios, including
`aprendo -> reinicio -> recuerdo -> corrijo -> olvido`; an unknown speaker
cannot read protected data; a model outage degrades safely; and every
acceptance transcript records literal STT, route, response, audible output, and
audit outcome. P1.3 is the second part of the final acceptance: it runs only
after P2.2's longitudinal gate passes (CM-7, the first part), even though the
roadmap groups it under P1.

## P2 — Situated cognition and memory quality

### P2.1 — Current world state and structured perception

Introduce typed, expiring observations and `WorldState` for people, objects,
sensor state, and location. Keep it separate from durable memory and raw
telemetry. Convert on-demand vision first; provider clients stay inside
adapters.

**Exit gate:** stale data expires; contradictions remain explicit; visual scene
description is distinct from face identity; every observation carries source,
timestamps, confidence, and expiry; frames are not retained by default.

### P2.2 — Memory lifecycle and retrieval

Bring the longitudinal runtime slice forward after PC-4 and before P1.3. CM-0
ran intentionally earlier: Plan 0046 measured the current RED baseline
(`ac43c58`, 2026-09-08) without changing runtime. Follow CM-1 through CM-7 after
PC-4 in the
[conversational-memory delivery map](conversational-memory-delivery-map.md):
start with a reproducible RED benchmark; add candidate confirmation,
deduplication, contradictions, supersession, scoped authorization, V4 canonical
writes, protected episodes, relevance thresholds, authorized semantic
retrieval and complete forgetting. Hybrid retrieval arrives with CM-5b and
documentary retrieval stays conditional, as staged in [RAG, memory, and hybrid
retrieval](../architecture/rag-and-memory-retrieval.md). Derived indexes must be
rebuildable and deletions must propagate. This does not reopen the completed
P1.1 structured “Joaquín y Martina” proof.

**Exit gate:** the versioned evaluation defined in
[longitudinal-conversational-memory-evaluation.md](../architecture/longitudinal-conversational-memory-evaluation.md)
passes; low-relevance queries return no memory; protected memories never enter
model context; corrections expose only the current truth; forgetting reaches
facts, episodes, summaries, embeddings and caches; and the real server/robot
path proves persistence, correction, abstention and cross-person privacy.

### P2.3 — Personality adaptation and bounded initiative

Move stable identity, relationship style, dynamic state, and situational
expression into bounded structured composition. Add proactive behavior only
from fresh authorized events with cooldowns, quiet hours, cancellation, and
rate limits.

**Exit gate:** one coherent personality survives across roles; no private
cross-person prompt leakage occurs; transient interactions do not become
permanent traits; proactive prompts are explainable, sparse, and disableable.

### P2.4 — Outcomes and feedback contracts

After the longitudinal memory core is accepted, define typed outcomes for
observable results and typed feedback for authorized evaluation of those
results. Keep both distinct from events, telemetry and autobiographical memory;
link them through stable provenance instead of copying them into a generic
prompt. This phase does not authorize online model training or autonomous
policy changes.

**Exit gate:** a decision or action can be linked to an observed outcome and
authorized feedback; missing outcomes remain unknown; private feedback is
access-controlled; corrections and deletion propagate according to policy; and
no system claims to have learned from a result that was never observed.

## P3 — Family companion and UI

The family profile is intentionally later than the validated personal
companion. It reuses the same local entities, relationships, policy evaluator,
and identity evidence; it must not create a separate family brain or relax
sensitive-data policy.

### P3.1 — Family onboarding UI and consent

Build one reviewable local onboarding application service, exposed later through
the UI and controlled import paths. It creates the household profile, adults,
children, pets, relationships, visibility defaults, consent grants, and
biometric consent. The initial owner/admin configures the household but does
not automatically obtain another adult's personal data.

**Exit gate:** onboarding is idempotent; consent is explicit and revocable;
relationships and provenance remain structured; no UI or voice channel writes
truth by raw SQL or independent rules.

### P3.2 — Family companion interaction

Extend Iroko's social interaction to consented, identified household members.
It may greet members, use permitted household context, and adapt its style, but
must return unknown, ambiguous, or unauthorized rather than disclose another
person's private data.

**Exit gate:** multi-member acceptance covers adults, children, guests, pets,
identity conflicts, data isolation, and recovery after biometric failure.

## Future responsibility profiles — not scheduled

`care` and `education` are orthogonal to the `personal`/`family` social axis;
they are not later maturity labels for the same permissions. They reuse the
accepted companion core only after outcomes and feedback have explicit
contracts.

A future `care` capability must distinguish beneficiary, family member,
caregiver, health professional, technical administrator and emergency contact.
A future `education` capability must distinguish student, tutor and educator.
No role inherits another person's private data or unrestricted action authority.

Before either responsibility is scheduled it needs a separate accepted ADR,
bounded capability policy, risk classification, deterministic failure posture,
outcome/feedback contract and real acceptance criteria. Until then, Iroko is a
companion; the roadmap makes no nurse, clinical-monitoring or autonomous-teacher
claim.

## P4 — Model providers and physical body

### P4.1 — Model-provider evaluation (second local model, optional cloud), ADR 0036

The default and the first goal are local self-hosting (Ollama). The laptop cannot run
large models or a good speech synthesis, so Pipec wants to compare, on the project's
own cases, (a) the current local model, (b) a second local model and (c) a cloud
option, measuring answer quality, latency and the load on the laptop. The cloud is
neither excluded nor assumed: it enters the runtime path only through
[ADR 0036](../adr/0036-model-providers-local-first.md) (Proposed, with open
questions for Pipec), as an explicit opt-in chosen at composition for a named
capability. Create the plan only after local result validation exists and ADR 0036
is decided.

If a cloud provider is accepted, its use requires all of:

```text
local result is uncertain or insufficient
+ the task is eligible
+ the active person is authorized
+ the data categories may leave the home
+ a minimized/redacted request has real expected benefit
+ timeout, cost, audit, and local fallback policies are available
```

Biometrics, children's raw images/audio, full household profiles, medical
records, complete conversations, location history, credentials, and home maps
do not leave by default. A cloud failure returns the best safe local outcome,
including `unknown`; it never blocks basic operation.

**Exit gate:** the comparison of the three options is recorded with numbers; if a
cloud provider is accepted, policy and redaction tests run without network, provider
adapters are replaceable, every attempt is auditable without logging protected
payloads, budgets and timeouts are enforced and cloud output is validated as
untrusted.

### P4.2 — Physical body and ROS2 decision

Only after cognitive, identity, policy, and current-state contracts are stable
should the project choose physical action architecture. ROS2 is appropriate if
real requirements demand distributed nodes, navigation, device discovery, or
its ecosystem; it is not a prerequisite for the cognitive foundation.

Physical work starts with typed action proposals and a separate safety layer:

```text
cognitive intent
-> authorization
-> capability check
-> physical safety/interlocks
-> actuator adapter
-> outcome observation
```

**Exit gate before motion:** simulation and emergency-stop behavior, limits,
timeouts, collision/failure handling, cancellation, audit, and human acceptance
tests exist. An LLM never commands a motor directly.

## Global constraints for every plan

- Local-first and open-source-compatible operation is the default.
- Optimize for CPU operation; optional acceleration must have a safe fallback.
- Use the existing Python 3.12 workspace, SQLite, and `sqlite-vec` unless a
  measured requirement and ADR justify a change.
- Preserve the server/robot and public audio contracts in
  [`implementation-guardrails.md`](../architecture/implementation-guardrails.md).
- Use one small typed orchestrator; do not introduce a multi-agent runtime,
  giant framework, general autonomous loop, or plugin ecosystem.
- Unknown, ambiguous, contradictory, and unauthorized are successful domain
  outcomes when they accurately represent the evidence.
- Identity and authorization precede private retrieval and generation.
- New electronics are adapters after software contracts, not the starting point.
- Every plan states exact files, tests, rollback/migration concerns, and non-goals.
- No plan may require ignored `project-history/local-docs/` content or unstated chat history.
- No commit, push, PR, dependency install, or unrelated cleanup is implicit in
  an implementation request.

## How to hand work to an implementing agent

Use one instruction of this form:

```text
Implement docs/plans/open/NNNN-name.md exactly as written.
Read docs/architecture/implementation-guardrails.md,
docs/architecture/README.md, and only the required files named by the plan.
Respect the permitted file list. If code or current behavior
contradicts the plan, stop and report the exact conflict; do not redesign or
expand scope. Run the listed verification. Do not commit unless asked.
```
