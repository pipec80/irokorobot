# Conversational-memory delivery map

**Status:** canonical design; CM-0 closed (Plan 0046, 2026-09-08); CM-1's grant scoping closed
(Plan 0051, 2026-10-06) and its memory capabilities closed as policy only (Plan 0060, 2026-10-09);
CM-2 closed (Plan 0061, 2026-10-13: short-term continuity for the identified person); CM-3 designed
in [ADR 0021](../adr/0021-memory-candidates-and-the-canonical-writer.md) (`Accepted`, 2026-10-16) and split into CM-3a and CM-3b;
CM-3a closed (corte 1 [Plan 0062](../plans/completed/0062-cm3a-memory-candidates-and-writer.md), 2026-10-15: candidate store,
canonical writer, background proposal; corte 2 [Plan 0063](../plans/completed/0063-cm3a-memory-dialogue.md), 2026-10-16: spoken
offer, explicit answer, hardware acceptance); CM-3b tranche A closed ([Plan 0065](../plans/completed/0065-cm3b-a-channel-neutral-writer-core.md), 2026-10-22: the channel-neutral writer, [ADR 0022](../adr/0022-household-rules-and-third-party-memory.md) `Accepted`); Step 0 closed (Plans 0070 to 0073, 2026-10-23 to 2026-10-28: the data pool, the importer, the commissioning session and the local administration); CM-4 closed ([Plan 0076](../plans/completed/0076-cm4-conversation-record-and-diary.md), 2026-10-30: the conversation record and the diary); CM-5a closed ([Plan 0074](../plans/completed/0074-cm5a-profile-card.md), 2026-10-28); the household protection answers requests, not mentions ([Plan 0077](../plans/completed/0077-household-requests-not-mentions.md), 2026-11-02); CM-5b + R3 closed ([Plan 0078](../plans/completed/0078-cm5b-recall-what-the-owner-told.md), 2026-11-04: recall over the diary); block B closed ([Plan 0079](../plans/completed/0079-block-b-sensitive-read-and-spoken-secrets.md), 2026-11-06: the owner's sensitive data by voice and spoken secrets); the MVP recall phrasings and the sides of the family closed ([Plan 0080](../plans/completed/0080-mvp-recall-phrasings.md), 2026-11-10). **Open:** block C (database hygiene, then CM-6 correct and forget, ADR 0032, written against [ADR 0031](../adr/0031-the-memory-engine-boundary.md)), the home-server deployment (ADR 0033), and block D (CM-7 + PC-5, the final acceptance). CM-3b tranche B was emptied by ADR 0029 and its remaining items (third-party spoken capture, reported facts, perceptual candidates) are required before CM-7 or move to the family stage.
**Last reviewed:** 2026-11-10 (`main` at `3954405`, Plan 0080 closed)

## Objective

Connect the vision of longitudinal autobiographical memory with the code, the
tests, and the observed gaps, without opening a second memory system or
confusing documentation with implementation.

This map expands P2.2 of the
[cognitive roadmap](cognitive-roadmap.md) and is a dependency of PC-5 in
[Plan 0015](../plans/open/0015-personal-companion-design.md). It is not an
executable plan: each increment needs its own `Ready` plan and runs one at a
time.

## Desired outcome

```text
conversation or perception
          ↓
memory candidate
          ↓
attribution, classification, and policy
     ┌────┼─────────┐
  accept  confirm  reject
     ↓
canonical V4 memory
     ↓
authorized retrieval
     ↓
response with evidence
     ↓
correction, history, or complete forgetting
```

Remembering more text is not the goal. Every durable memory must be able to
explain whose it is, who asserted it, what its source was, when it was valid,
what its truth state is, who may see it, whether it is sensitive, what it
corrects, and what must be removed when it is forgotten.

## How the fracture closed (history)

Until Plan 0061 the protected household queries and the generic conversation travelled different
paths: a protected query went identity -> authorization -> V4 memory -> a deterministic response,
while generic conversation went through a legacy text turn with legacy and semantic memory, and
the controller did not carry the resolved actor into it. That legacy memory path (`build_context`,
`memory/semantic.py`, the `MANUAL` gate, the consolidation writer) was retired in steps, and no
runtime path reads or writes it now:

- Plan 0061 (CM-2, 2026-10-13) carried the identified actor into the generic turn for short-term
  continuity: the person's last exchanges reach the next turn for 180 s of silence and 3000
  characters, in process only.
- Plan 0062 (CM-3a corte 1, 2026-10-15) retired `consolidate_turn`, `PROPOSE_MEMORY` and
  `COMMIT_MEMORY`; a face-identified voice turn can leave a stored memory candidate behind the
  default-off `MEMORY_CANDIDATES_ENABLED`, and `memory_writer.promote` is the one place a candidate
  becomes a V4 literal fact. Plan 0063 (2026-10-16) added the spoken offer and the explicit spoken
  answer on the two voice routes; `/chat` has no audio and cannot create or confirm a candidate.
- Plan 0074 (CM-5a, 2026-10-28) reads the owner's tastes and two name datums back through the
  profile card.
- Plan 0076 (CM-4, 2026-10-30) retired the legacy memory path completely (the `MANUAL` gate, the
  prompt's memory block, `vec_memories`) and records every spoken exchange of the two voice routes;
  no prompt reads the record.
- Plans 0078 to 0080 (2026-11-04 to 2026-11-10) read back what the owner told (recall), the
  relatives of the alta with their sides, and the owner's sensitive data by voice, from the
  controller, authorized and audited, before any model runs.

What still cannot be done: no controller branch corrects or forgets a memory (CM-6), every other
authorized household question answers that the information "todavía no está conectada", and the
family stage is not built. The pre-Plan-0061 evidence (for example, that production routes never
emitted `MANUAL` evidence) is kept in git history and in the plans, not here.

## Reusable capabilities

What already exists must not be rebuilt:

- identity separated from authorization;
- unknown as a valid state;
- policy and audit evaluator;
- V4 facts and relations with state and validity;
- authorized household reads;
- short-term continuity of the identified person (`memory/continuity.py`, Plan 0061):
  one in-process session slot bounded by characters and silence, suspended for an
  unknown or ambiguous speaker;
- local extraction through Ollama;
- the candidate store (`memory_candidates`, migration 009), the canonical writer
  (`memory_writer.promote`, Plan 0062) and the spoken offer and explicit answer that
  call it (`memory/candidate_dialogue.py`, Plan 0063);
- the conversation record, the diary and the recall index with its hybrid search
  (`recall_units_fts`, `recall_units_vec`), over SQLite and sqlite-vec;
- the profile card, the recall and relatives answers, and the sensitive read, all behind
  default-off switches and decided before the model runs.

## Delivery sequence

This table governs only the CM-0…CM-7 subprogram. Its position among
biometrics, personal acceptance, perception, RAG, family, and P4.2 is defined
once in the
[canonical pre-electronics delivery portfolio](cognitive-roadmap.md#canonical-pre-electronics-delivery-portfolio).

| Stage | Verifiable outcome | Dependencies | Executable plan |
|---|---|---|---|
| CM-0 | Versioned longitudinal benchmark and one reproducible RED run | evaluation specification | [Plan 0046](../plans/completed/0046-reproducible-longitudinal-memory-baseline.md) — **closed 2026-09-08**: benchmark GREEN, measured baseline RED (`ac43c58`, exit 1) |
| CM-1 | Every grant bound to one named operation (ADR-0015 decision 1, Plan 0051), then explicit `read`, `propose`, `confirm`, `correct`, and `forget` capabilities for personal memory | current policy and identity; PC-4 (closed) | [Plan 0051](../plans/completed/0051-scoped-owner-grants.md) **closed 2026-10-06**; the memory capabilities are [Plan 0060](../plans/completed/0060-cm1-personal-memory-capabilities.md) (closed 2026-10-09; policy only, nothing wired; [ADR 0019](../adr/0019-personal-memory-capabilities.md) `Accepted`) |
| CM-2 | The authorized actor and its grants reach the conversational flow without interpolating names or expanding permissions implicitly; short-term continuity (in-process working memory for the identified actor, deleted by another identified person or 180 s of silence, suspended on an `unknown` or `ambiguous` turn, per [ADR 0020](../adr/0020-authorized-actor-in-the-conversation.md) `Accepted`) has its own acceptance test; durable legacy paths stay blocked. Identifying generic turns supersedes part of ADR-0016 §5 | CM-1 | [ADR 0020](../adr/0020-authorized-actor-in-the-conversation.md) `Accepted`; [Plan 0061](../plans/completed/0061-cm2-generic-turn-continuity.md) — **closed 2026-10-13**, accepted on real hardware ([record](../evals/0061-generic-turn-continuity-acceptance.md)) |
| CM-3a | Extraction creates candidates; one writer assigns the classification and promotes to canonical V4 facts. First cut: the owner's own `likes`, `dislikes` and `prefers`, by voice, where every candidate, spoken value and promotion requires face and voice of the same person on that turn; it closes none of the benchmark's write steps ("CM-3" without a letter names CM-3a and CM-3b). The seed load ("step 0") follows as its second input channel | CM-0, CM-1, CM-2; Plan 0050 | [ADR 0021](../adr/0021-memory-candidates-and-the-canonical-writer.md) `Accepted` (2026-10-16); corte 1 [Plan 0062](../plans/completed/0062-cm3a-memory-candidates-and-writer.md) — **closed 2026-10-15** (PR #183; no spoken dialogue, no hardware; gate 2972); corte 2 [Plan 0063](../plans/completed/0063-cm3a-memory-dialogue.md) (the offer, the answer and the hardware acceptance) — **closed 2026-10-16** (gate 3217; hardware cases 1, 2, 3, 4, 6 and 7 passed, 5 partial, 8 measured on the laptop, 9 not run; [record](../evals/0063-memory-dialogue-acceptance.md)). **CM-3a is closed** |
| CM-3b | The rest of the personal-scope write steps CM-7 needs: third-party relations, `lives_in` with validity, facts reported by another person, a disclosure rule, perceptual candidates, the first `SECURITY` datum and a benchmark `confirm` step (each tied to its owner in ADR 0021 decision 13; [ADR 0026](../adr/0026-owner-profile-card-and-the-read-side-of-memory.md) decision 9 leaves tranche B with `lives_in` and the disclosure rule by voice) | CM-3a (closed 2026-10-16) | **tranche A closed 2026-10-22** (Plan 0065); tranche B not written, after CM-5b; **required before CM-7** **Order proposed 2026-10-16 (Pipec asked to continue it):** split into tranche A, before Step 0 ([ADR 0022](../adr/0022-household-rules-and-third-party-memory.md) and [Plan 0065](../plans/completed/0065-cm3b-a-channel-neutral-writer-core.md): the channel-neutral writer, the household capabilities, `species`, validity, the disclosure and SECURITY predicates, dataset v3), and tranche B, after Step 0 (spoken capture of third parties, reported facts, the behaviour of the disclosure rule, perceptual candidates). [Plan 0064](../plans/completed/0064-speech-and-dialogue-quality.md) (speech and dialogue quality) went first and closed on 2026-10-19. |
| CM-4 | Episodes declare owner, visibility, sensitivity, consent, and retention. Designed by [ADR 0027](../adr/0027-conversation-record-and-the-diary.md) (`Accepted`, 2026-10-30): the whole conversation is kept as a record, memory is derived from the owner's verified part | CM-3a | ADR 0027 written; pre-measurement done ([Plan 0075](../plans/completed/0075-cm4-pre-measurement.md), 2026-10-29: owner voice verified on 35.5 % of real turns, rule **per turn** confirmed by Pipec); implementation: [Plan 0076](../plans/completed/0076-cm4-conversation-record-and-diary.md), closed 2026-10-30, accepted on hardware; ADR 0027 `Accepted` |
| CM-5 | Retrieval filters authorization and validity before the prompt and applies a relevance threshold. **Split by [ADR 0026](../adr/0026-owner-profile-card-and-the-read-side-of-memory.md) (`Accepted`, 2026-10-28):** **CM-5a** reads the structured V4 facts that exist (a small card in every identified turn and the explicit «what do you know about me», nothing sensitive); **CM-5b** reads episodes and the semantic archive, delivered together with R3 (lexical and hybrid search over the diary) | CM-4 for CM-5b; CM-2, CM-3a and Step 0 for CM-5a | CM-5a: closed 2026-10-28, [Plan 0074](../plans/completed/0074-cm5a-profile-card.md) (behind the default-off `PROFILE_CARD_ENABLED`, accepted on hardware); CM-5b + R3: closed 2026-11-04, [Plan 0078](../plans/completed/0078-cm5b-recall-what-the-owner-told.md) (behind the default-off `RECALL_ENABLED`, calibrated and accepted on hardware, [record](../evals/0078-recall-acceptance.md)); [ADR 0028](../adr/0028-recall-what-the-owner-told.md) `Accepted`. The sensitive read is block B: closed 2026-11-06, [Plan 0079](../plans/completed/0079-block-b-sensitive-read-and-spoken-secrets.md) (behind the default-off `SENSITIVE_READ_ENABLED`, accepted on hardware 10 of 10, [record](../evals/0079-sensitive-read-acceptance.md)); [ADR 0029](../adr/0029-it-knows-who-is-listening.md) `Accepted`. Recall was then extended by the MVP phrasings ([Plan 0080](../plans/completed/0080-mvp-recall-phrasings.md), 2026-11-10), the alta's contacts and profile by voice ([Plan 0082](../plans/completed/0082-the-whole-alta-by-voice.md)) and when a told event happened, with one reader of spoken time ([Plan 0083](../plans/completed/0083-spoken-time-and-when-it-happened.md), behind `OCCURRED_TIME_ENABLED`; both 2026-11-12, [ADR 0037](../adr/0037-the-time-of-memories-and-a-contacts-phone.md) `Proposed` until Plan 0084's greeting is accepted; Plan 0084, the pending topics, merged 2026-11-13) |
| CM-6 | Correction and forgetting reach facts, relations, episodes, embeddings, summaries, and derived caches | CM-3a through CM-5, and CM-3b for the dataset's write steps | not written; block C of the closing path, after its database hygiene (C1). ADR 0032 decides who may correct and forget (Pipec, 2026-11-06: one ordinary memory with the owner's face and a closed spoken verb; a sensitive or security one, or «olvida todo», with the PIN in `iroko-admin`, superseding ADR 0026 decision 4 and the forget part of ADR 0019) and the retention of memories for years; it is designed against [ADR 0031](../adr/0031-the-memory-engine-boundary.md) |
| CM-7 | A real scenario learns, restarts, recalls, corrects, forgets, and does not disclose; the benchmark is GREEN on its personal-scope scenarios, and the family-scope ones (`recipient_only_message`, `two_adult_private_facts`) stay reported as pending for P3.2 | CM-0 through CM-6 (including CM-3b), PC-3, PC-4 | not written; one delivery with PC-5, memory first |

The single cross-track order, including the hardening rows (Plans 0055 and
0050) and the seed load, lives only in the
[canonical portfolio](cognitive-roadmap.md#canonical-pre-electronics-delivery-portfolio).
CM is not a separate program: it is the memory half of the personal companion,
and PC-5 is delivered with CM-7, as the second part of one final acceptance. The order
of the remaining memory work is the
[closing path](cognitive-roadmap.md#closing-path-of-conversational-memory) of
2026-10-30. Its only biometric dependency, PC-4, closed
on 2026-09-30, and its hardening follow-up, Plan 0055, merged on 2026-10-01
(PR #152); Plan 0050 (audit repairs) closed on 2026-10-01, ahead of CM-1.

The documentary-retrieval stages of
[RAG §25](../architecture/rag-and-memory-retrieval.md#25-secuencia-de-evolución)
overlap this map: R1 is CM-5, R3 (hybrid search) is delivered with CM-5b and R5 is
CM-3, CM-4 and CM-6. R2 (documents) left the memory path and is conditional.
The CM-1…CM-7 plan numbers are not reserved (Plan 0051, the first plan of CM-1, is
closed); each stage is written only after its predecessor closes and is
re-audited.

## Contracts that must become explicit

### Lifecycle

`proposed -> confirmed|rejected -> corrected|revoked|expired`, with history and
provenance. Automatic extraction never on its own equals confirmed personal
truth.

### Authorization

The minimum capabilities are:

- `read_personal_conversation_memory`;
- `propose_personal_memory`;
- `confirm_personal_memory`;
- `correct_personal_memory`;
- `forget_personal_memory`.

Face, voice, PIN, or manual resolution provides evidence; policy decides each
capability and its scope.

### Retrieval

Person, visibility, sensitivity, consent, state, and validity are filtered
before any evidence reaches the LLM. Semantic similarity only ranks candidates
that are already authorized and sufficiently relevant.

### Forgetting

Forgetting must reach the canonical record and all its projections: embeddings,
summaries, caches, and retrieval material. Security logs that must be retained
will keep only the minimum permitted evidence and not the forgotten content.

## Out of scope

- own neural training, JAX, or online weight learning;
- DuckDB, microservices, or agent frameworks;
- automatically expanding current tokens or permissions;
- copying whole conversations as durable truth;
- implementing `care` or `education`;
- using a cloud provider in the runtime path ([ADR 0036](../adr/0036-model-providers-local-first.md), Proposed).

## Criteria for opening plans

Plan 0046 for CM-0 is closed: it observed a reproducible failure (`ac43c58`,
exit 1) without changing the runtime. Every later plan must have small scope,
RED/GREEN tests, verification commands, non-goals, and independent review. PC-5
stays open until CM-7 and its complete physical acceptance are passed.
