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
  CM-1…CM-7) is next; perception (P2.1), adaptation (P2.3) and outcomes (P2.4)
  follow.
- **P3 — family:** after the personal companion is accepted.
- **P4 — cloud escalation (optional) and physical body:** after the 19 slices.

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
owner and keeps every private fact closed to anyone else. Documentary retrieval
(R2, R3) adds documents afterwards; its other stages are already CM or P2.1 work
(see [RAG §25](../architecture/rag-and-memory-retrieval.md#25-secuencia-de-evolución)).

Numbered rows are the 19 required product slices. Rows marked `—` are hardening
or data-loading work that belongs to the queue without being a slice, so the
count stays 19. A row is neither a reserved plan number nor authorization: only
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
| — | Speech-to-text on the owner's real voice | **Closed in code 2026-10-21** ([Plan 0069](../plans/completed/0069-stt-owner-voice-audit.md), [ADR 0023](../adr/0023-speech-to-text-model-and-decoding.md), [the record](../evals/0069-stt-owner-voice.md)). The transcript was measured with Pipec's own voice through the robot's capture chain: the model was the only link that moved the result, `medium` on the GPU (optional `cuda` extra) takes the test-half WER from 15.4 % to 6.8 % (a second look at that half) and the short answers from 25.7 % to 2.9 % (1 of 35 words against 9) at a median 3.0 s per clip with Ollama busy (8.7 s on the CPU); the retry temperature is fixed at 0; the robot closes a turn after 1200 ms and uploads a 300 ms tail; a per-clip `stt.confidence` is logged and the «No te entendí» reply is built and off by default (the owner runs `-0.9`); the `amara.org` credit Whisper writes on noise is discarded. The taste gate keeps refusing «?» (0 of 17 statements were punctuated that way). One speaker, one microphone in a quiet room: measure again on the Raspberry Pi's microphone. The private corpus was deleted at the close. | — | **Closed** 2026-10-21 (PR #202) | Plan 0069; ADR 0023 |
| 5 | CM-1 — scoped memory capabilities | First every grant is bound to one named operation ([ADR-0015](../adr/0015-owner-grant-scope-and-speaker-binding.md) decision 1, implemented by **Plan 0051**, the first plan of this slice, which also covered the voice enrolment and revocation endpoints Plan 0053 added after the ADR, the household-looking stub answer that used to spend a grant, and the optional PIN hardware case left unrun by Plan 0054); then policy distinguishes `read`, `propose`, `confirm`, `correct` and `forget` for personal memory, and `SECURITY` data declare their `strong` requirement, without turning identity into authorization. | PC-4 | Plan 0051 **closed 2026-10-06** (grants bound to one operation; accepted on real hardware, [record](../evals/0051-scoped-grant-acceptance.md)); [Plan 0060](../plans/completed/0060-cm1-personal-memory-capabilities.md) **closed 2026-10-09** (the five memory capabilities as pure policy, a minimum assurance per capability with `confirm` and `forget` at `strong`, `biometric`, `medical` and `location` data at `strong`, and two one-use grant scopes carried in the identity evidence; [ADR 0019](../adr/0019-personal-memory-capabilities.md) `Accepted`; [record](../evals/0060-personal-memory-capabilities-acceptance.md)). Nothing was wired when it closed; CM-3a (Plans 0062 and 0063, 2026-10-16) now consumes `propose`, `read` and `confirm` for the owner's own preferences | [Memory map](conversational-memory-delivery-map.md#delivery-sequence) |
| — | Streaming-protocol fallback repair | Streamed replies stop dropping to the fallback phrase at a measurable rate: Plan 0056 measured **29.17 %** (35 of 120; 56.67 % on turns with memory context, 1.67 % on context-free turns), above the 5 % rule. The figure is a synthetic evaluation of the generator, not a production rate, and the context split mixed four factors. [Plan 0057](../plans/completed/0057-stream-protocol-diagnosis.md) (diagnosis only, executed 2026-10-06, [record](../evals/0057-stream-protocol-diagnosis.md)) measured them on `qwen2.5:3b` (820 streams over two seeds, generator only): the baseline falls back in about 43 to 52 % of context turns and 1.7 to 3.3 % of public turns; the dominant shape is a tag that shares its line with the text (`tag_same_line`, 85 to 97 % of context fallbacks); removing the memory block lowered the rate by 35 and 27 points on the same 12 turns (confirmed by a second seed that also tripped the order-effect rule; exploratory, not a cause); and a schema-constrained reply reached the client spread over time, which is evidence against the `llm_streaming.py` claim that Ollama withholds it. The fragmentation defect was not seen on live output (none of the 820 replies was judged differently under any split). Moving the output contract to the start of the prompt made the model drop the tag in all 120 runs (one seed), which argues against that option; the repair plan also owns correcting the stale `llm_streaming.py` header that claims Ollama withholds structured output. Pipec chose the repair on 2026-10-07 from those readings: a tolerant tag grammar **plus** rescuing a reply with no tag as plain text with the emotion `neutral`, with the prompt untouched ([ADR 0017](../adr/0017-streaming-reply-protocol.md), `Proposed`); the gate is a baseline fallback rate at or below 5 % in context and public turns in two seeds. It is written as [Plan 0058](../plans/completed/0058-stream-protocol-repair.md), whose first code task is the fragmentation defect: production validates the body start once, so a split `EMOTION:` or code fence is spoken. **Outcome (2026-10-07/08):** Plan 0058 implemented that grammar and measured 35.00 % of context turns still falling back in seed 57 (21 of 60, gate 5 %; 20 of 21 a same-line tag whose next word is not an emotion), so it closed without its gate and was replaced by [Plan 0059](../plans/completed/0059-user-emotion-apart.md): the model answers in plain text and the `emotion` event is decided from the user's words by a pure, precision-first function ([ADR 0018](../adr/0018-user-emotion-decided-apart.md), `Accepted`). Gate met on the final code: 0 of 60 context and 0 of 60 public fallbacks in seeds 57 and 59 ([record](../evals/0059-user-emotion-apart.md)). | Plan 0056; ordered after CM-1 (Pipec, 2026-10-05) | **Closed 2026-10-08** — diagnosis Plan 0057 (2026-10-06); Plan 0058 closed without its gate (2026-10-07); [Plan 0059](../plans/completed/0059-user-emotion-apart.md) closed it (gate met). CM-2's hard gate is met. Hardware acceptance by Pipec done 2026-10-08 (memory case not exercisable before CM-2). Open: the language of the reply (one French answer seen), the robot's facial *expression*, a model-based classifier, the end-to-end rate | [Measurements](../evals/0056-voice-pipeline-measurements.md#1-streaming-protocol-fallback-0049-o-04); [0049 O-04](../plans/completed/0049-server-objective-conformance-audit.md) |
| 6 | CM-2 — authorized actor propagation | The actor and grants resolved by face, voice or PIN reach the generic conversation, with no name interpolated into the prompt and no widened grant. Until Plan 0061 identity was resolved only on protected turns ([ADR-0016 §5](../adr/0016-face-and-voice-identity-fusion.md#5-turn-order)), so CM-2 needed a new ADR that supersedes that section: when a generic turn is identified, how an authorized session is kept, and when its history is discarded. [ADR 0020](../adr/0020-authorized-actor-in-the-conversation.md) (`Accepted` 2026-10-13) decides it and Plan 0061 implemented it: every generic turn is identified by the face (or an observed `/chat` token) with no voice embedding and no grant spent. `just chat-test` is adapted, because it expects continuity between unauthenticated public requests. Its first visible result is short-term continuity: the identified actor's last turns (in-process working memory, never persisted) reach the next turn, another identified person or 180 s of silence deletes them, and an `unknown` or `ambiguous` turn suspends them without exposing them; only generic turns take part, so a protected answer never enters the history — with its own acceptance test and a measured fallback rate and language on history-bearing streamed turns. Connecting the actor is not enabling durable memory: legacy retrieval and consolidation stay blocked, and each read or write opens only in the slice that implements its guarantees (writes CM-3, episodes CM-4, retrieval CM-5). | CM-1; streaming-protocol repair (the first turn that carries memory or history in the prompt is where the measured fallback rate matters) | **Complete 2026-10-13** — accepted on real hardware (continuity, a second face beside the owner, no evidence, 180 s of silence); 2597 tests; `history` fallback 0.00 % in two runs; the face check costs a median of about 0.9 s on a generic turn (maximum 1.6 s) | [Plan 0061](../plans/completed/0061-cm2-generic-turn-continuity.md); [acceptance record](../evals/0061-generic-turn-continuity-acceptance.md); [Memory map](conversational-memory-delivery-map.md#current-fracture) |
| 7 | CM-3a — candidates and the canonical V4 writer ("CM-3" without a letter names both CM-3a and CM-3b) | Extraction only proposes; one deterministic writer assigns the classification (never the speaker) and promotes with provenance, deduplication and contradictions. First cut: the owner's own `likes`, `dislikes` and `prefers`, by classic and streaming voice only, where every candidate, spoken value, answer and promotion requires the face and the voice of the same person verified on that turn (nothing is stored until both are enrolled), with an audited policy decision; `/chat` is out. It closes none of the benchmark's personal-scope write steps (they are CM-3b). A spoken "lo recordaré" from the LLM is never evidence of a write. Designed by [ADR 0021](../adr/0021-memory-candidates-and-the-canonical-writer.md) (`Accepted` 2026-10-16) and delivered in two plans: **0062** (candidate store, writer, extraction, no hardware) and **0063** (the spoken offer, the explicit answer and their hardware acceptance, with the owner's voice re-enrolled). Corte 1: a face-identified generic voice turn schedules a background candidate proposal (default-off `MEMORY_CANDIDATES_ENABLED`), `consolidate_turn`, `PROPOSE_MEMORY` and `COMMIT_MEMORY` are retired, and `memory_writer.promote` is the only place a candidate becomes a V4 literal fact. Corte 2: the classic and streaming voice routes speak the offer on a later generic turn (one WAV on the classic route, one more `audio` event on the stream; no wire change, robot untouched) and only an explicit spoken answer (a closed verb alone since Plan 0066; the value is optional and must match when present) promotes it or rejects it and erases the value, each step needing the face and the voice of the same person on that turn's own clip; anything else is the ordinary turn, byte for byte. The switch stays off by default (Pipec's decision). Nothing can be read back until CM-5. | CM-2; audit repairs | ADR 0021 `Accepted` (2026-10-16). **Complete 2026-10-16**: corte 1 [Plan 0062](../plans/completed/0062-cm3a-memory-candidates-and-writer.md) (closed 2026-10-15, PR #183; no spoken dialogue, no hardware; `just gate` 2972, CI selection 2955, baseline 2597/2580) and corte 2 [Plan 0063](../plans/completed/0063-cm3a-memory-dialogue.md) (`just gate` 3217; accepted by Pipec on the shared laptop: cases 1, 2, 3, 4, 6 and 7 passed, 5 partial, 8 measured, 9 not run; [record](../evals/0063-memory-dialogue-acceptance.md)). Open findings are in the cross-cutting table | [Memory map](conversational-memory-delivery-map.md#lifecycle) |
| 7b | CM-3b — the rest of the personal-scope write steps | What CM-7 needs that the first cut leaves out, each tied to the benchmark step that demands it: relations and literals about third parties (`extraction_family_and_pet`), `lives_in` and `works_at` with validity dates (`domicile_temporal_validity`), facts reported by another person (`provenance_attribution`), a disclosure rule such as "no menciones X delante de visitas" (`sensitive_preference_lifecycle`; Pipec decides between a new predicate and a dataset version bump), perceptual candidates that stay proposed (`perceptual_evidence_stays_proposed`, with P2.1), `nombre`/`edad`/`especie`, the first `SECURITY` datum, and a `confirm` operation in the benchmark dataset (a version bump). Third-party memory needs household rules decided in an ADR first. **Required before CM-7**, and before CM-6's correct and forget steps of `sensitive_preference_lifecycle`. | CM-3a (closed 2026-10-16) | **Tranche A closed 2026-10-22** ([ADR 0022](../adr/0022-household-rules-and-third-party-memory.md) `Accepted`, [Plan 0065](../plans/completed/0065-cm3b-a-channel-neutral-writer-core.md): one channel-neutral writer, relation validity, `species`, the stated age, the disclosure and `security` predicates (the repository refuses a `security` value until Step 0), the household capability pair as policy only, and dataset v3); **tranche B** (spoken capture of third parties, reported facts, the behaviour of the disclosure rule, perceptual candidates) is **after Step 0** and not yet planned | [ADR 0021 decision 13](../adr/0021-memory-candidates-and-the-canonical-writer.md#13-everything-this-adr-leaves-out-has-an-owner) **Order proposed 2026-10-16 (Pipec asked to continue it):** split into tranche A, before Step 0 ([ADR 0022](../adr/0022-household-rules-and-third-party-memory.md) and [Plan 0065](../plans/completed/0065-cm3b-a-channel-neutral-writer-core.md): the channel-neutral writer, the household capabilities, `species`, validity, the disclosure and SECURITY predicates, dataset v3), and tranche B, after Step 0 (spoken capture of third parties, reported facts, the behaviour of the disclosure rule, perceptual candidates). [Plan 0064](../plans/completed/0064-speech-and-dialogue-quality.md) (speech and dialogue quality) goes first. |
| — | Seed load ("step 0") | Owner, household, photos and classifications load in person from a local file or form as a second input channel of the CM-3 writer; seeded sensitive facts change only with owner verification; the owner → stranger matrix passes once per channel. Until then `just setup-personal` and `just onboard` remain the setup. Phase 0 also owns the security rules found while building CM-3a ([ADR 0021](../adr/0021-memory-candidates-and-the-canonical-writer.md) decision 13): enrolling face **and** voice as the first step of setup (today the voice is a separate script and no profile exists), who may pass and at which level, "you are with someone, still want it?" before speaking private data, and whether reads of private normal data move from `basic` to `strong` (ADR 0019 §3). | CM-3a for the owner's own data; CM-3b for household members | **Designed 2026-10-22 and revised 2026-10-23, not executed:** [ADR 0024](../adr/0024-seed-load-senses-secrets-and-channels.md) `Proposed` (the data pool of the commissioning, a secret stored by reference, contacts with phones, the confirmation of an assisted interview, the order of the commissioning; the field catalogue is [`seed-data-pool.md`](../architecture/seed-data-pool.md)), [Plan 0070](../plans/open/0070-seed-load-data-pool-storage.md) `Draft` (storage and provenance) [Plan 0071](../plans/open/0071-seed-load-file-importer.md) `Draft` (the file importer) and [Plan 0072](../plans/open/0072-commissioning-session.md) `Draft`, an outline (the commissioning session: face and voice in one flow, the voice session that is the «voice calibration when a user is enrolled» row, the readiness report, closing the window, the acta). [Plan 0073](../plans/open/0073-local-admin-crud.md) `Draft`, an outline (the local administration, a command-line CRUD over SSH through the canonical writers, with no new network service: it closes Phase 0 and is the amendment path after the closing); its remote half (a VPN, a support session opened by the owner, encrypted backup, signed controlled updates, telemetry with no household value, and a periodic job that only proposes candidates) is [ADR 0025](../adr/0025-remote-administration-backup-updates-and-telemetry.md) `Proposed`, with no plan yet. Still unwritten: the structured read of the profile by voice (a first slice of CM-5) and the «are you with someone?» question (CM-5). | Rules in [0050 *Non-goals*](../plans/completed/0050-server-audit-repairs.md#non-goals) |
| 8 | CM-4 — protected episodes | Episodes declare owner, subjects, visibility, sensitivity, consent, validity and retention. | CM-3a | Unplanned | [Memory map](conversational-memory-delivery-map.md#delivery-sequence) |
| 9 | CM-5 — authorized relevant retrieval | Person, visibility, sensitivity and validity filter vector and structured candidates before the prompt; a relevance threshold permits zero results and keeps provenance (RAG stage R1). Structured household reads beyond the children list and count (today every other authorized family question answers "todavía no está conectada") go through the same authorized seam. The first reserved (`SECURITY`) category becomes real here: written with that classification by the CM-3 writer, read only at assurance `strong`, while `basic` (face alone) and strangers get the generic denial. CM-3a (closed 2026-10-16) writes no `strong`-only category: which datum it is is decided when CM-3b is planned ([ADR 0021](../adr/0021-memory-candidates-and-the-canonical-writer.md) decision 13). | CM-4 | Unplanned | [Memory map](conversational-memory-delivery-map.md#retrieval) |
| 10 | CM-6 — correction and forgetting | Correction and deletion reach facts, relations, episodes, embeddings, summaries, caches and the live rows of `memory_candidates`; "ya no me gusta X", which CM-3a closes without writing, is made here as a correction. | CM-3a through CM-5, and CM-3b for the dataset's write steps | Unplanned | [Memory map](conversational-memory-delivery-map.md#forgetting) |
| 11 | CM-7 — real longitudinal scenario | The real server/robot path proves `learn -> restart -> recall -> correct -> restart -> recall current truth -> forget -> do not disclose`, including turn-to-turn continuity, one `SECURITY` datum (`strong` reads it, `basic` and strangers do not) and the benchmark's **personal acceptance** verdict PASS without relaxed thresholds. Family acceptance stays `pending` for P3.2 (`recipient_only_message`, `two_adult_private_facts`) and the full suite keeps failing until then; no scenario is excluded. | CM-0 through CM-6, including CM-3b | Unplanned | [Evaluation](../architecture/longitudinal-conversational-memory-evaluation.md#pc-5-longitudinal-gate) |
| 12 | PC-5 / P1.3 — integrated personal acceptance | Pipec completes voice, biometric, protected-memory, visual, correction, forgetting, denial, degradation and audible-output scenarios with literal transcripts; it decides whether scene description must work in streaming mode (today the robot refuses to start with streaming and server vision together, so scenes are classic-only); the CPU/RAM/latency budget and the Uvicorn concurrency (`UVICORN_LIMIT_CONCURRENCY`) are measured on the homelab server. | CM-7 | Unplanned | [Plan 0015](../plans/open/0015-personal-companion-design.md#pc-5--integrated-personal-companion-acceptance--unstarted) |
| 13 | P2.1 — structured perception and `WorldState` | Typed observations for people, objects, sensor state and location carry source, time, confidence and expiry; simulated sensors can later be replaced by firmware. | P1 controller and policy | Unplanned | [Memory and world state](../architecture/memory-and-world-state.md#world-state-is-not-long-term-memory) |
| 14 | R2 — minimum documentary source | One local Markdown or text source is versioned, classified, chunked and retrieved with owner, visibility, provenance and deletion. | CM-5, CM-6 | Unplanned | [RAG §25](../architecture/rag-and-memory-retrieval.md#25-secuencia-de-evolución) |
| 15 | R3 — lexical and hybrid retrieval | Lexical and vector retrieval over authorized candidates; RRF, deduplication, zero results and measured quality. | R2 | Unplanned | [RAG §15](../architecture/rag-and-memory-retrieval.md#15-recuperación-híbrida) |
| 16 | P2.3 — bounded adaptation and initiative | Personality stays coherent and private; initiative is explainable, sparse, rate-limited and disableable. | P2.1, CM-7 | Unplanned | [P2.3](#p23--personality-adaptation-and-bounded-initiative) |
| 17 | P2.4 — outcomes and feedback | Decisions link to observed outcomes and authorized feedback without claiming unobserved learning. | P2.1, CM-7 | Unplanned | [P2.4](#p24--outcomes-and-feedback-contracts) |
| 18 | P3.1 / PC-6A — family onboarding and consent | One idempotent service, the seed-load writer extended to more members, creates members, roles, relationships, visibility and revocable consent. | PC-5 | Unplanned | [P3.1](#p31--family-onboarding-ui-and-consent) |
| 19 | P3.2 / PC-6B — family interaction acceptance | Adults, children, guests, pets, identity conflict, personal/shared/`recipient_only` isolation and biometric-failure recovery; the family-scope CM benchmark scenarios left pending by CM-7 turn GREEN. | P3.1, P2.1 | Unplanned | [P3.2](#p32--family-companion-interaction) |

After all 19 slices close with their own evidence, P4.2 may open its first
physical-architecture plan: the Raspberry Pi versus microcontroller boundary,
typed action proposals, capability checks, electrical and motion safety,
simulation, emergency stop and human acceptance before motion. P4.1 cloud
escalation is optional and does not block P4.2.

### Cross-cutting gates and conditional work

These items do not add slices. Required evidence belongs to the plan that creates
the load or the behavior; conditional work opens only after a measured need.

| Item | Classification | Required disposition | Owned by |
|---|---|---|---|
| CPU, RAM, token and latency budget | Cross-cutting required evidence | Measure bounded contention among STT, LLM, VLM, embeddings and candidate extraction, plus the Uvicorn concurrency limit, on the homelab server; no unbounded parallel workload or separate scheduler by default. | CM plans that add load; PC-5 acceptance |
| Liveness and replay defense | Conditional per [ADR-0016 §9](../adr/0016-face-and-voice-identity-fusion.md#9-replay-and-spoofing-measured-not-closed) | Replay is measured, not defended: a photograph plus a recording of the exact question can still reach `strong`. A liveness plan opens only if the measurement justifies it; making it a mandatory gate needs a new ADR that supersedes that section. Case 9 of Plan 0063's acceptance (the owner's photograph plus an earlier recording against the spoken offer and answer) was not run for lack of a second person or device. | CM-5, which introduces the first reserved read, re-measures and decides |
| Voice calibration when a user is enrolled | Unplanned (open, after the step 0 seed load) | Plan 0069 left the building blocks: a reading script of 85 invented phrases (24 form the short block), a corpus recorder that cuts the robot's clip offline, a deterministic bench and the threshold calibration. Not built: the robot running a short script at enrolment, a per-user profile and its settings (the «unclear» threshold, hotwords, a level and distance check). Not covered by the plan either: the Raspberry Pi's microphone, noise with speech in it, Whisper's accuracy under noise, the Chilean markers («po», «cachai»), sentences with pauses, full phonetic coverage, intonation and other voices; the script is not validated by an expert. | A plan that reuses `scripts/stt_*` |
| Language-model latency beside the memory extraction | Cross-cutting evidence | Measured in Plan 0069's live runs: in turns that used the language model, a median 19 s and up to 57 s (Ollama on the CPU with the candidate extraction in the background); the speech-to-text is no longer the bottleneck (median 2.6 s). | PC-5 acceptance (the budget row above) |
| Remaining biometric measurements | Required before relying on voice beyond the laptop | Runtime impostors, genuine utterances of 1.5–3 s and a second acoustic condition were never measured (PC-3B). [Plan 0068](../plans/completed/0068-short-clip-speaker-measurement.md)'s Tasks 7 and 8 (the short-clip capture sessions and report: trimmed against raw clips, short against long references; they need at least three consenting adults) were deferred on 2026-10-21 and belong here. | The recalibration of electronics track 1, or PC-5 if the laptop stays the body |
| Privacy contract of the senses | Required before any new continuous capture | What is kept, what never leaves the device, and a physical switch and indicator once there is hardware. Needs an ADR. It gates new capture (an always-on microphone or camera, recording beyond one turn), not the purchase: porting today's per-turn capture to the Pi does not need it. | An ADR written with the seed load |
| Diarization / simultaneous speakers | Required decision, conditional implementation | Before P3.2 becomes `Ready`, choose an explicit turn-taking constraint or local diarization. Speaker verification is not diarization. | P3.2 readiness design |
| Barge-in (interrupting the robot while it speaks) | Product gap, required decision, not scheduled | Pipec asked for it on 2026-10-07: streaming with STT already feels fluid on the laptop, and talking over the robot is the natural next step. Today the loop is half-duplex by design (`robot/app.py`, [ADR-0002](../adr/0002-server-robot-separation.md)): the microphone is closed while the robot speaks, so it never transcribes its own voice, and a turn is recorded only when the stream ends whole. Supporting it needs acoustic echo cancellation (the speaker and the microphone share the laptop today), voice detection while `SPEAKING`, a cut of the playback and of the stream (the server tolerates a client that leaves, but it is not proven that Ollama stops generating), and recording only the sentences already spoken (`StreamState.response_parts` is a base). It does not block or change [Plan 0058](../plans/completed/0058-stream-protocol-repair.md). | Unplanned; decide with the hardware (the recalibration of electronics track 1, where echo cancellation depends on the real microphone and speaker) or in PC-5 if the laptop stays the body |
| Ollama-down signal | Partly addressed by Plan 0064, closed (a start-up warning; `/health` still does not report Ollama) | Pipec forgets to start Ollama and the first symptom is the fallback phrase ("mi cerebro todavía se está despertando"): `GET /health` passes while Ollama is unreachable, so neither the robot's start-up check nor the operator sees it (seen 2026-10-09 while accepting Plan 0060: two greetings spoke the fallback phrase with `reason=llm_error`, then answered normally once Ollama ran). Candidate: report Ollama reachability in `/health` and log one clear warning at server start and when the first stream fails, without making the server refuse to start (the deterministic branches do not need the model). The robot stays a generic audio client: it only reads the health answer. Sketch only; it needs a plan and a decision on whether `/health` may report degraded. | A small plan chosen by Pipec; PC-5 acceptance would also surface it |
| Face-check latency on a generic turn | Measured, not judged ([ADR 0020](../adr/0020-authorized-actor-in-the-conversation.md) *Review* trigger) | Plan 0061's acceptance measured 6 generic identifications on the development laptop (shared with Docker, no GPU): median about 0.9 s, maximum 1.6 s, on turns that take 7 to 13 s in total. Decide whether that is acceptable once the homelab server is the runtime; options already named by the ADR: an earlier face check in the router, or warming the face model per request. Nothing to do until a measurement on the server says it matters | Homelab measurement; pre-purchase gate |
| Language of the reply and confabulation with an empty session | Language: addressed by Plan 0064 (a rule closes the master prompt and the streaming contract; `eval-chat --mode stream` on `qwen2.5:3b`: 1 of 97 before, 0 of 98 and 0 of 97 after; 0 of about 24 hardware turns on 2026-10-19). Confabulation: open finding, small, not scheduled | The word-list heuristic judged 1 of 53 (second run) and 0 of 50 (first run) `history` replies not Spanish, and 2 of 60 `public` ones; the report keeps counts only, so the reply was not located and was accepted as the heuristic's limit (Pipec, 2026-10-13). With an empty session the small local model invented a value (answered "7") instead of admitting it does not remember: the same confabulation Plan 0059 left open, not a continuity defect. Both belong to a prompt or model slice; also the STT echo of its own prompt ("Conversación con un robot doméstico llamado Iroko") reached the controller once and was harmlessly suspended. Plan 0063's hardware acceptance (2026-10-16, the shared laptop) saw the language problem again, on real turns: about 2 of 12 generic or fall-through turns answered partly or wholly in French | A prompt/model-quality plan, with the language of the reply in `scripts/reply_language.py` as its instrument |
| The model says it saved something that was not written | Addressed by [Plan 0064](../plans/completed/0064-speech-and-dialogue-quality.md) (closed 2026-10-19, PR #193) | `claim_guard` replaces a model sentence that claims a save with «Eso no lo he guardado.» on the classic reply and the stream, and the memory-discipline block tells the model it stores nothing. The lexicon is closed: wordings outside it (present and future without an object, «lo dejé guardado») and the persona verbs «Conservas»/«Registrar» can still invite a claim. | Pipec's voice acceptance; a wider lexicon only if it is seen |
| The explicit answer against the speech-to-text | **Closed in code by Plan 0066** (2026-10-19, PR #196); its first hardware session promoted 1 of 2 short answers, the other failed the speaker check on a short clip. **[Plan 0067](../plans/completed/0067-reply-listening-mode.md) closed in code the listening and words part** (2026-10-19: a reply listening mode, hotwords for the recognizer, «acepto» and «guárdala» as answers); its hardware counts were taken with Task 6 of Plan 0068. The speaker check on short clips is [Plan 0068](../plans/completed/0068-short-clip-speaker-measurement.md), closed 2026-10-21: **Part A is in code** (2026-10-19: when only the voice failed and the owner's face is recognized, one fixed retry sentence asks for a longer answer and the robot listens once more; «que lo guardes» now parses; the `Speaker verdict` log carries the clip seconds, the distance and the failed gate; ADR 0021 decision 9, amended) and its hardware counts were taken on 2026-10-21 with the adopted speech-to-text profile ([Plan 0069](../plans/completed/0069-stt-owner-voice-audit.md), ADR 0023): 7 offers, 1 promoted, 1 rejected, 1 retry, no wrong promotion; a «sí, autorizo a guardarlo» that Pipec said in that session was read as a value and is fixed (PR #203); **Part B, the measurement of trimmed against raw short clips and of short against long references (Tasks 7 and 8), is deferred by Pipec** (the calibration tool and its report are in code; no threshold, enrollment or embedding changes before the report; the item is under «Remaining biometric measurements») | The grammar accepts `autoriza`/`aprueba`, `ya`/`dale`/`po` and a leading `mi`/`mis` (ADR 0021 decision 9, amended). On hardware 1 of 2 answers was understood (baseline 2 of 4): the failure was an extra word inserted by Whisper inside a long phrase. Pipec found repeating the value cumbersome and decided that a closed verb alone («autorizo», «sí, autorizo», «apruebo», «sí, guarda») resolves the single open offer, a bare «sí» still not; face and voice verified on that turn stay mandatory. This amended decision 9 (option A of 2026-10-15) and is [Plan 0066](../plans/completed/0066-verb-only-answer.md), which also amended ADR 0021 (the spoken offer now ends «Dime: sí, autorizo.»; the cost, that a recording of «autorizo» inside the 60 s window of an open offer can promote it without knowing its value, is stated in decision 9). Counted on hardware on 2026-10-21 (Plan 0068 Task 6, two sessions, events only): the plan's bar of 4 of 5 promoted was **not** reached (1 promoted). Open follow-ups from the causes: an answer said together with another sentence («no acepto» and then a clause) goes to the model because the words after a closed verb are read as a value (Pipec decides whether a closed verb that opens a longer utterance may count), and the 60 s window against a model turn of 20 to 40 s (the language-model latency row). The speech-to-text hotwords that Plan 0066 named as the next candidate are now Plan 0067 (`SHORT_REPLY_HOTWORDS`, sent only when the robot flags a reply), with the longer end-of-speech pause and the words «acepto» and «sí, guárdala». Re-measure on the homelab. | The two follow-ups above; the homelab measurement; Plan 0068's Tasks 7 and 8 (deferred) |
| Short turns cannot carry an offer | Documented limit of Plan 0063, to be re-measured | The offer needs the voice of that turn: three clips of about 1.5 s gave `Speaker verdict: unknown` and nothing was offered, while of the owner's turns of about 3 s or more all but two were `verified`. By design (the firewall needs the voice of the same turn); the operator manual asks for a full sentence. Re-measure with a homelab and a second acoustic condition | The recalibration of electronics track 1; PC-5 acceptance |
| Cold-start Ollama and the model-down phrase | Operational observation of Plan 0063's acceptance, small, not scheduled | The first chat turn after Ollama started failed with a 500 twice while the laptop had about 460 MB of free memory (the model was loading) and the stream spoke the fallback phrase; the next turn worked, and time to first audio ran from 7 s to 90 s with the machine's load. Warming the model first avoids it; the Ollama-down signal above would make it visible. The fallback phrase and the controller phrases are in tuteo since Plan 0064; the start-up probe now logs one warning when Ollama is down but cannot see this cold-start failure | A small plan chosen by Pipec; the homelab as runtime |
| Local unlock on a robot without a keyboard | Product gap, Pipec's decision, not scheduled | The PIN is still needed for set-up, for enrolling and revoking face and voice (`biometric_admin`) and for `forget` (a spent `personal_memory_forget` grant, ADR 0019), because face and voice are replayable (ADR-0016 §9) and the PIN is not. Today it is typed at the robot's terminal (`ROBOT_OWNER_UNLOCK_PROMPT`, off by default) or in the scripts, which does not fit a robot with no keyboard or screen (raised by Pipec on 2026-10-13). The PIN is checked in one place (`unlock()` in `cognition/owner_authentication.py`) and everything downstream sees only a scoped `LOCAL_UNLOCK` grant, so a fingerprint reader would be a second verifier that issues the same grant: scopes, single use, expiry and policy stay as they are, and [ADR 0020](../adr/0020-authorized-actor-in-the-conversation.md) decision 6 already covers it. The sensor needs its own ADR (a new sense on the robot, which would send only a match result, and the privacy contract of the senses). | An ADR with the electronics track; Pipec chooses when |
| Wiring of the personal-memory capabilities | Follow-up of [Plan 0060](../plans/completed/0060-cm1-personal-memory-capabilities.md), scheduled through CM-2 to CM-6 | The policy exists. CM-3a now consumes `propose`, `read` and `confirm` for the owner's own preferences (Plans 0062 and 0063, audited before the effect); `correct` and `forget` are still consumed by nothing. Left for the wiring plans: `confirm` is reachable only with face and a verified voice (it has no PIN route; a `personal_memory_confirm` scope would add one); `forget` cannot be exercised when the owner's face identifies the turn because the PIN is then not consulted (decided by [ADR 0020](../adr/0020-authorized-actor-in-the-conversation.md) decision 6: a grant of the operation's own scope is consulted after a face match; it is built by the plan that wires `forget`); single use protects a request, not an erasure, so a second `forget` target needs a fresh grant ([ADR 0019](../adr/0019-personal-memory-capabilities.md) §6). | CM-2 ADR; CM-3 to CM-6 |
| Leftovers of CM-3a | Follow-up of [ADR 0021](../adr/0021-memory-candidates-and-the-canonical-writer.md), scheduled | A candidate that contradicts an active fact is closed without writing ("ya no me gusta el mate"); that is a correction and CM-6 owns it, and CM-6's forgetting also reaches the live values of `memory_candidates`. `/chat` cannot create or confirm a candidate (no audio, so no `strong`); a `personal_memory_confirm` scope would change that and is Pipec's decision, unscheduled. [Plan 0063](../plans/completed/0063-cm3a-memory-dialogue.md)'s acceptance (2026-10-16, [record](../evals/0063-memory-dialogue-acceptance.md)) measured on the shared laptop only: voice check to stored row 30 s and 60 s on the two clean runs, the explicit answer parsed 2 of 4 times (see its row above) and short turns cannot carry an offer (see its row above). **Not run:** case 9 (a photograph plus an earlier recording; replay stays measured, not defended, see the liveness row), any homelab measurement (extraction contention, the cost of the third face-and-voice resolution per turn there) and a second person for the "another voice" and "another face" cases, which were substituted by a translator app, a Windows text-to-speech voice and a photo on a phone. The switch `MEMORY_CANDIDATES_ENABLED` stays off by default; turning it on for daily use is Pipec's decision. The benchmark has no `confirm` operation and no restart seam: a dataset version bump (CM-3b or CM-7 preparation) and a driver seam (CM-7 preparation). | CM-6; a homelab session with a second person; CM-3b; CM-7 preparation |
| R4 PDF, OCR, advanced chunking and reranking | Conditional | Only when real documents or R3 metrics prove Markdown/text plus hybrid retrieval insufficient. | [RAG evolution](../architecture/rag-and-memory-retrieval.md) |
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
| 1. The same senses on the Pi | Raspberry Pi 5 with a microphone, a speaker and a camera replacing the laptop's | None in the cognitive queue | It is a port of the robot client; the server does not change. Required work: repeat the face ([Plan 0030](../plans/completed/0030-real-camera-face-acceptance.md)) and speaker ([Plan 0047](../plans/completed/0047-speaker-evidence-calibration-study.md)) calibrations on the new devices, because the thresholds `0.5815` and `0.4834` were measured on the laptop and are device-specific. |
| 2. New kinds of sensors | Temperature, distance, presence and similar | The P2.1 contract is designed (row 13) | A sensor is an adapter behind a typed observation; choosing sensors before the contract can force rework. |
| 3. Anything that moves | Motors and actuators | P4.2, after the 19 slices | Typed action proposals, a safety layer, an emergency stop and human acceptance come first. |

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
electronic biometric (future adapter for the identity seam, no ADR yet), cloud
escalation (P4.1, optional), R4 PDF/OCR, alternative TTS, and the care and
education responsibilities. Independent of the queue: the second GT-P3110 tablet
(a hobby task).

**Who decides.** Closing a row is evidence-based (each plan's own gates). The
decision to spend money is Pipec's and is not made by this document; it only
states what is ready.

### How Chat and Codex advance the portfolio

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

Rows 1–4, the PC-4 follow-ups, Plan 0050, Plan 0056, Plan 0051 (CM-1's first plan) and Plan 0057 (the streaming-protocol diagnosis), Plan 0058 (closed without its gate) and Plan 0059 (the streaming repair, gate met), Plan 0060 (CM-1's memory capabilities, policy only), Plan 0061 (CM-2), Plan 0062 (CM-3a's first cut) and Plan 0063 (CM-3a's second cut, closed 2026-10-16) and Plan 0064 (speech and dialogue quality), Plan 0066 (the verb-only answer) and Plan 0067 (the reply listening mode) are closed (all 2026-10-19); Plan 0069 (speech-to-text on the owner's real voice) closed 2026-10-21; Plan 0068 (the voice retry and the short-clip study) closed 2026-10-21 with its Tasks 7 and 8 deferred; CM-3b tranche A (ADR 0022 and Plan 0065) is `NOW` since 2026-10-22. What each row still needs before
it can become `NOW` (checked 2026-10-02):

| Work | What is really missing |
|---|---|
| CM-1 | [Plan 0051](../plans/completed/0051-scoped-owner-grants.md) closed 2026-10-06 (every grant bound to one named operation); CM-1 stays open for the memory permissions (`read`, `propose`, `confirm`, `correct`, `forget`), closed as [Plan 0060](../plans/completed/0060-cm1-personal-memory-capabilities.md) (2026-10-09; pure policy, nothing wired: `confirm` and `forget` still need a wiring plan) |
| Streaming-protocol fallback repair | Closed 2026-10-08 by [Plan 0059](../plans/completed/0059-user-emotion-apart.md) (Plan 0058's tolerant grammar had not met the gate). What remains, none of it blocking CM-2: the language of the reply (Pipec's hardware acceptance of 2026-10-08 saw one answer in French; no streaming contract tells the model to answer in Spanish, and the instrument does not measure it); the robot's facial *expression*, a different signal from the user's emotion, for which [ADR 0018](../adr/0018-user-emotion-decided-apart.md) reserves the name `expression`; a model-based classifier behind `classify_user_emotion` when a larger model exists (today most turns are `neutral`); the end-to-end rate of a spoken turn, which the generator-only instrument does not measure; the known limits of the tag guard and a JSON or code fence in the middle of a reply |
| CM-2 | Closed 2026-10-13: [ADR 0020](../adr/0020-authorized-actor-in-the-conversation.md) `Accepted` (it supersedes part of ADR-0016 §5 and amends §8) and implemented by [Plan 0061](../plans/completed/0061-cm2-generic-turn-continuity.md), accepted on real hardware. The identified person has short-term continuity; durable memory stays blocked (writes CM-3, episodes CM-4, retrieval CM-5). Open follow-ups are in the cross-cutting table |
| CM-3a → CM-3b → seed load → CM-7 | Separate plans; the first `SECURITY` datum and its gates are specified before it is enabled. CM-3a is closed: corte 1 on 2026-10-15 as [Plan 0062](../plans/completed/0062-cm3a-memory-candidates-and-writer.md) (candidate store, canonical writer, background proposal behind the default-off `MEMORY_CANDIDATES_ENABLED`) and corte 2 on 2026-10-16 as [Plan 0063](../plans/completed/0063-cm3a-memory-dialogue.md) (offer, answer, hardware acceptance; [ADR 0021](../adr/0021-memory-candidates-and-the-canonical-writer.md) `Accepted`). CM-3b tranche A closed on 2026-10-22 as [Plan 0065](../plans/completed/0065-cm3b-a-channel-neutral-writer-core.md) (the channel-neutral writer; its household rules are [ADR 0022](../adr/0022-household-rules-and-third-party-memory.md), `Accepted`); tranche B (spoken capture of third parties, reported facts, the behaviour of the disclosure rule) comes after the seed load, still unwritten, and is required before CM-7 |
| PC-5 | The streaming-with-vision scope is decided when its plan is written; measurement on the homelab happens during acceptance |

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

Real-hardware acceptances are historical: they cover only the recorded
scenarios, devices and configuration and are not a new run on the current tree.
Limits carried forward from these phases, each owned by a queue row or a
cross-cutting item above: no liveness (a photograph identifies at `basic`) and
replay measured but not defended; on hardware Plan 0054 proved the two-faces
veto, while the veto of a single other enrolled person was proven only against
test doubles until Plan 0055 (Task 4) pinned it against real role rows in automated tests; the calibrations are provisional (one owner,
few impostors, laptop devices); the grant proves the PIN, not the speaker (bound to
an operation since Plan 0051; the memory capabilities are CM-1's remaining plan);
the generic conversation has short-term continuity for the identified person (CM-2, closed 2026-10-13) but no durable memory (CM-3…CM-5): CM-3a (Plans 0062 and 0063, closed 2026-10-16) can hold a candidate, offer it by voice and promote it to one canonical fact only after an explicit spoken answer, behind a default-off switch, but nothing reads a fact back until CM-5.

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
audit outcome. P1.3 executes only after P2.2's longitudinal gate, even though
the roadmap groups it under P1.

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
retrieval and complete forgetting. Then add documentary and hybrid retrieval
in the staged order defined by [RAG, memory, and hybrid
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

## P4 — Cloud escalation and physical body

### P4.1 — Controlled cloud escalation

Cloud is an optional escalator, not the primary brain. Create a separate ADR
and plan for an explicit gateway only after local result validation exists.

Escalation requires all of:

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

**Exit gate:** policy and redaction tests run without network; provider adapters
are replaceable; every attempt is auditable without logging protected payloads;
budgets and timeouts are enforced; cloud output is validated as untrusted.

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

## How to hand work to Codex

Use one instruction of this form:

```text
Implement docs/plans/open/NNNN-name.md exactly as written.
Read docs/architecture/implementation-guardrails.md,
docs/architecture/README.md, and only the required files named by the plan.
Respect the permitted file list. If code or current behavior
contradicts the plan, stop and report the exact conflict; do not redesign or
expand scope. Run the listed verification. Do not commit unless asked.
```
