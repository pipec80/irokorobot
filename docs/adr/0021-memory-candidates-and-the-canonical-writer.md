# 0021 — Keep what the owner says as a candidate, and let one deterministic writer promote it

- **Status:** Accepted (2026-10-16). Proposed 2026-10-14: scope and design chosen by Pipec in a
  brainstorming session of that day; revised the same day after two independent read-only audits
  against the code and after Pipec stated the firewall rule of decision 3. Amended on 2026-10-15,
  before Plan 0063 was written, with Pipec's decisions for the dialogue: neutral Spanish with tuteo
  (not voseo), the answer's closed verbs, filler phrases before a taste, one open offer per person
  (decisions 4 and 9). Accepted when Plan 0063 closed with its hardware cases run (cases 1, 2, 3,
  4, 6 and 7 passed, 5 partial, 8 measured on the shared laptop, 9 not run; see
  [the acceptance note](../evals/0063-memory-dialogue-acceptance.md)). Amended on 2026-10-16 by
  [Plan 0064](../plans/completed/0064-speech-and-dialogue-quality.md): decision 9's answer grammar
  admits how the speech-to-text writes the verbs, and a model sentence that claims a save is
  replaced.
- **Date:** 2026-10-14
- **Builds on:** [ADR 0006](0006-personal-and-family-companion-profiles.md),
  [ADR 0009](0009-locked-posture-and-scoped-capabilities.md),
  [ADR 0016](0016-face-and-voice-identity-fusion.md),
  [ADR 0019](0019-personal-memory-capabilities.md),
  [ADR 0020](0020-authorized-actor-in-the-conversation.md)
- **Refines:** [ADR 0019](0019-personal-memory-capabilities.md) §6 (its seven wiring obligations are
  addressed in decision 12; two stay unwired) and its §1 sentence that the plan introducing the writer decides whether to
  retire `PROPOSE_MEMORY` and `COMMIT_MEMORY` (decision 11). The policy of ADR 0019 is unchanged:
  CM-3a's callers demand more than the policy minimum, which ADR 0019 §3 permits.
- **Amends:** [ADR 0020](0020-authorized-actor-in-the-conversation.md) §1 and §2. §1 says the voice
  is never consulted on a generic turn: it is now consulted in the background for a turn that
  matches the gate, and concurrently with generation when a candidate waits to be offered
  (decisions 3 and 9). §2 says persistent context, retrieval and consolidation keep their `MANUAL`
  gate and that turns are "never extracted, consolidated or promoted": an identified generic turn
  may now be **extracted for candidates** (decision 4). Consolidation, episodes, persistent context
  and retrieval stay closed.
- **Implemented by:** [Plan 0062](../plans/completed/0062-cm3a-memory-candidates-and-writer.md)
  (candidates and the writer, no hardware; closed 2026-10-15, PR #183; decisions 1 to 8, 10, 11 and
  12) and [Plan 0063](../plans/completed/0063-cm3a-memory-dialogue.md) (decision 9: the spoken offer
  and answer, and the hardware acceptance; closed 2026-10-16). "CM-3" without a
  letter names both CM-3a (this ADR) and CM-3b (decision 13).

## Context

CM-3 is the first slice that writes durable personal memory. The
[memory map](../roadmap/conversational-memory-delivery-map.md) states its goal: *extraction creates
candidates; one writer assigns the classification and promotes to canonical V4 facts.* ADR 0019
decided who may propose, confirm, correct and forget; ADR 0020 decided who the speaker is and what
short-term memory they have. Missing: the store between "the person said it" and "it is the
person's memory", the writer, and the dialogue.

### What holds today (verified in code at `f58d84f`, 2026-10-14)

1. **Nothing durable is written.** `consolidate_turn` returns unless the turn carries `MANUAL`
   evidence ([consolidation.py:150-192](../../server/src/server/memory/consolidation.py)); its only
   producer, `select_person`, has no production caller. If it ran it would write the legacy
   `entities`, `facts` and `memories` tables, store the whole turn as an episode, and extract with a
   13-predicate prompt that also receives the assistant's reply.
2. **V4 has no place for a candidate.** `literal_facts_v4` accepts lifecycle `active`, `superseded`,
   `disputed`, `revoked` and `expired` only (a `CHECK`, which SQLite cannot alter without rebuilding
   the table). `confirmed_by_entity_id` and `confirmed_at` exist and **no Python reads or writes
   them**.
3. **The registry is also the read contract.** `assert_literal_fact` stamps the registry's default
   visibility (`household` for `likes`, `dislikes`, `prefers`), and `PolicyGatedV4Reader` and the
   household tools build their policy requests from the same fields; those predicates also admit
   pet subjects.
4. **The policy exists and nothing consumes it.** `propose_personal_memory` needs `basic`,
   `confirm_personal_memory` needs `strong`, both for the owner's own data only. Any `local_unlock`
   item in the actor's evidence is checked against the capability's scope and, for these actions,
   **turns the decision into `grant-scope`**; a token-bearing actor is nevertheless `strong`
   (`_assurance_for`), so assurance alone does not say how it was reached.
5. **`strong` needs the face first and then a voice, and the voice is not enrolled here.** Face
   authentication enabled, an enrolled face and a frame; then speaker authentication enabled, enough
   voiceprints for the current model, an active consent, the owner role, and a clip of at least
   `SPEAKER_MIN_VERIFICATION_S`, **measured over all samples, silence included**. The local database
   holds 0 voice profiles. A generic turn is identified by the face alone and never touches the
   voice (ADR 0020).
6. **Writes are serialised by a non-reentrant lock.** `db.transaction()` hangs when re-entered;
   `assert_literal_fact` opens its own by default, and a duplicate active literal raises
   `sqlite3.IntegrityError` (a test pins it). The V4 unique index is on the exact `value_text`.
7. **The controller is built per route and is shared.** `CognitiveController.decide()` runs on
   `/chat`, `/vision/respond`, `/transcribe` and `/transcribe/stream`; the classic route calls it
   twice on a generic turn, and the streaming route never calls `handle()`.
8. **Extraction is slow and thinly measured.** About 41 s per call on the shared laptop in the CM-0
   baseline (one case, three runs, precision and recall 0.25, probably a comparison artifact).
9. **Values leave through more doors than the tables.** `SQLite` runs with `secure_delete = 0` and
   the code never sets it, so a scrubbed value survives in free pages and the WAL; `just reset-db`
   copies the live database to `data/backups` (14 copies today); `conversation_log.log_spoken`
   prints every spoken sentence when `LOG_CONVERSATION_TEXT` is on, while its docstring promises
   that household values from the memory layer stay unlogged.
10. **The local database is a clean slate.** No legacy facts or memories; two `child_of` relations
    from `setup-personal`.

### What CM-7 asks for, and why CM-3 is two slices

The personal-scope scenarios of the longitudinal benchmark are the CM-7 exit evidence, and **CM-3a
closes none of their write steps** ([evaluation spec](../architecture/longitudinal-conversational-memory-evaluation.md)):

| Personal-scope scenario | What its write step needs | CM-3a |
|---|---|---|
| `sensitive_preference_lifecycle` | A disclosure rule ("do not mention my move in front of visitors"): not a taste, and sensitive | No; the gate must refuse it |
| `extraction_family_and_pet` | A child, a birth date, a pet and a negation: third parties | No |
| `provenance_attribution` | "Aria told me…": the asserter is not the subject | No (schema ready) |
| `domicile_temporal_validity` | `lives_in` with validity dates; location is `strong` | No |
| `perceptual_evidence_stays_proposed` | A low-confidence camera claim that stays proposed | No |
| `abstention_unknown_fact`, `false_memory_resistance_claim` | Recall only | CM-5 |

## Decision

### 1. Scope of CM-3a

- **Predicates:** `likes`, `dislikes` and `prefers` (multi-value literals), `normal` sensitivity.
- **Subject:** the identified owner and only themself; a pet is never a subject.
- **Channels:** classic voice and streaming voice. `/chat`, `/vision/respond` and any turn without an
  identified speaker never create a candidate, offer or answer.
- **Result:** after the owner's explicit confirmation, one V4 literal fact, visibility `personal`,
  sensitivity `normal`, with who confirmed it and when.
- **Out:** reading it back (CM-5), correcting or forgetting (CM-6), episodes (CM-4), third parties,
  sensitive categories, perception, the seed load (decision 13).

### 2. Units, each with one reason to change

| Unit | Responsibility |
|---|---|
| **Preference gate** | Pure: does the text declare a first-person taste, under which predicates? |
| **Candidate extractor** | One Ollama call that structures a matched turn into `(predicate, object)` pairs |
| **Candidate classifier** | Pure `classify`: accepts or drops a pair and fixes its classification |
| **Candidate store** | Persists candidates with compare-and-set transitions; scrubs on resolution |
| **Policy check** | Builds the `AuthorizationRequest`, evaluates ADR 0019's policy, audits before any effect |
| **Memory writer** | The only place that inserts a V4 fact from a candidate (`promote`, one transaction) |
| **Offer and answer** (Plan 0063) | Composes the offer in the text-turn seam; reads the explicit answer |

Modules: `memory/preference_gate.py`, `candidate_extraction.py`, `candidate_classifier.py`,
`candidates.py`, `memory_writer.py`. Plan 0062 added the vocabulary (`candidate_types.py`), the
policy check (`candidate_policy.py`), the limiter (`candidate_limits.py`), the background
orchestrator (`candidate_proposal.py`), the composite enrolment reader (`enrollment.py`) and the
face-and-voice actor (`cognition/strong_actor.py`). The repo already holds several accent and case folding copies (`declarative`,
`legacy_v4_migration`, `personal_setup`, `stt`, `intent_resolution`, `user_emotion`); the plan reuses
one, adds whitespace and punctuation collapse, and adds no further copy.

### 3. The firewall rule (Pipec, 2026-10-14)

The robot is a firewall for the owner's private information: nothing private is written, spoken or
accepted on the strength of a face alone. In CM-3a **every candidate, every spoken value, every
answer and every promotion requires the face and the voice of the same person, verified on that
turn's own clip, and no second face in frame.** Otherwise the robot behaves exactly as it would for
a stranger: it says nothing about it, and the reply is the ordinary one.

- **Voice on the turn's own audio.** The turn's WAV bytes (16 kHz, mono, `int16`, a few hundred
  kilobytes at most) are handed in memory to the background task, and the voice half of the fused
  resolution runs there, for the person the face named. It costs no visible latency. No clip, a clip
  below the floor, or a failed verification means **no candidate**.
- **Never from a token.** An actor carrying a `LOCAL_UNLOCK` item is refused before any extraction.
  The face-and-voice actor is the turn's token-free face actor fused with the voice verdict of that
  clip by `fuse_face_and_voice` (the fusion rule extracted from `FusedIdentityResolver`, so it
  exists once); the face is not computed a second time.
- **Fail closed and enrolment first.** Until the owner's face and voice are enrolled, CM-3a produces
  nothing, by design. The kill-switch `MEMORY_CANDIDATES_ENABLED` (default off) covers every path:
  proposal, offer, answer and promotion.
- **Not proof.** `strong` is a strong filter, not a wall: ADR 0016 §9 measured replay of a face and a
  recording, which is why `forget` also demands a PIN. CM-3a limits what a replay can do: it can
  only confirm text the replayer cannot choose (decision 9).
- **Who else may pass, levels, and "you are with someone, still want it?"** belong to Phase 0
  (decision 13), not to this ADR.

### 4. The preference gate and the extractor

- **Gate.** A closed list of first-person Spanish patterns, matched after case and accent folding,
  returning the set of predicates the text may carry: `me gusta(n)`, `me encanta(n)`, `amo`,
  `adoro` (likes); `no me gusta(n)`, `odio`, `detesto`, `no soporto` (dislikes); `prefiero`, `mi
  favorito/a es` (prefers). The plan fixes the table. A short closed list of fillers may sit right
  before the trigger — the phrases «la verdad es que» and «es que», and «oye» (Pipec, 2026-10-15) —
  as whole phrases, never free words, so a habit or a condition («siempre que me gusta…») still
  refuses. It refuses, with a closed reason: a question or
  conditional; a third person as experiencer; **a clause rather than a thing** (`prefiero que no
  menciones…`, `me gusta que…`: an instruction to the robot, which is CM-3b's disclosure rule);
  any negated form other than `no me gusta(n)` and `no soporto`; a **contrast inside one taste**
  (`todo menos X`, `excepto`, `salvo`, and after `prefiero` an `al`, `en vez de` or `en lugar de`:
  the model never picks which side is the taste); a taste that follows an attribution after a soft
  break (`mi hija dice: me gusta el helado`); and a **sensitive topic** from a closed deny-list
  (health, address, money, credentials, disclosure vocabulary), which also covers the plural and
  the diminutive of each entry.
- **A positive grammar and a closed topic set for the object.** The object is accepted only as a
  noun phrase of at most five words or an infinitive from a short allow-list, letters and spaces
  only, no Unicode format or control characters, no digits or URL, **and only when the extractor
  places it in a closed topic set** (food, drink, music, colour, pastime, sport, animal, weather,
  media; the plan fixes the set). An object that names a person, a kinship or a role
  (`lexicon.RELATION_TRIGGERS` plus jefe, amigo, vecino, …), a place, or a body or health word, or
  that falls outside the set, is dropped (`sensitive_topic`). **On doubt, drop**; the deny-list is
  only a second layer, because a miss there is unsafe. "Me gusta vivir en la costa", "odio mi
  medicación", "amo a mi hijo" and "no hablar de mi divorcio" never become a candidate.
- **Extractor.** The model receives **only the user's text**. Its output is at most three
  `{predicate, object, topic}` triples with `predicate` in `{likes, dislikes, prefers}` and `topic`
  in the closed set, no free-form field;
  a predicate outside the set the gate returned is dropped. It uses `consolidation_model` and the
  existing `ollama_chat` helper **without a retry** (a missed candidate is restated; a retry doubles
  a 41 s worst case) and logs the exception class only (`candidate.extraction_failed`).
- **Bounded cost.** Extraction runs only after the voice check of decision 3 passes. At most one
  extraction is in flight (a matching turn that finds one running is dropped: `busy`, before the
  voice check), and there is a per-hour budget (setting), whose slot is taken only after the voice
  check so a bystander cannot spend the owner's hour. The cap of decision 6 never evicts the
  owner's candidates to admit a new one.

### 5. The classifier assigns the classification; nobody else does

`classify` is pure: `(actor, predicate, object, user_text, known_person_names) → candidate | reason`.

- the predicate resolves through `resolve_predicate`; the subject is `actor.person_id` and the
  model's subject is ignored;
- the object is **grounded** (after folding, a substring of the user's text), 2 to 80 characters,
  not the name of a known person (names are an argument, so the function stays pure), in the closed
  topic set and free of kinship, role and place words;
- `value_text` keeps the spoken phrase including its article; the comparison key strips a leading
  article and folds case and accents;
- visibility `personal` and sensitivity `normal` are passed **explicitly to the V4 writer**. The
  registry defaults do not change (Context fact 3: they are the read contract of the household
  reader). CM-5 decides how the reader asks for personal rows.

### 6. The candidate store

A new table, `memory_candidates`, migration 009. It is not named `_v4`: it holds claims, not
canonical memory, and a `proposed` lifecycle inside V4 is rejected (Alternatives). Statuses:
`proposed`, `offered`, `confirmed`, `rejected` and `expired`.

| Column | Meaning |
|---|---|
| `id` | Primary key |
| `subject_person_id` | Whose memory it would become; entity id, `ON DELETE CASCADE` |
| `asserted_by_person_id` | Who said it; equal to the subject in CM-3a, separate because the memory contract asks "who asserted it" and CM-3b's reported facts need it |
| `predicate` | Canonical registry id |
| `value_text`, `value_key` | The phrase and its comparison key; **both null once resolved** |
| `status` | One of the five |
| `channel` | `voice_classic` or `voice_stream` |
| `source_correlation_id`, `offer_correlation_id`, `resolution_correlation_id` | The turns that proposed, offered and resolved it, so audit rows join to the candidate and the fact |
| `proposed_at`, `offered_at`, `resolved_at`, `expires_at` | Timestamps |
| `offer_count` | Times it was offered |
| `promoted_fact_id` | The V4 literal it became; `ON DELETE SET NULL` |

- **No raw utterance, no `source_memory_id`** (episodes are CM-4), **no assurance column** (always
  `strong`, decision 3).
- **One clock.** Every timestamp is supplied by the caller from an injectable clock as UTC ISO 8601
  with offset. The store never uses SQLite's `datetime('now')`, so expiry and the audit compare like
  with like and tests can fake time.
- **The schema enforces the scrub:** a `CHECK` says `value_text` and `value_key` are non-null
  exactly in `proposed` and `offered`. The scrub is **physical**: the connection sets
  `secure_delete`, a scrub is followed by a WAL checkpoint, and `just reset-db` voids live
  candidates before it copies the database to `data/backups`.
- **Idempotent and bounded:** a unique partial index on `(subject_person_id, predicate,
  value_key)` over `proposed` and `offered` backs the rule; at most five live candidates per
  person. The duplicate check, the cap check and the insert run in **one** transaction, so a
  repeated taste is a no-op and **at the cap a new candidate is refused**, never an old one
  evicted. A read-only `precheck_insert` asks the same question before the audit row is written,
  so a repeated taste or a capped person leaves no `allowed` audit row; the transaction stays the
  authority.
- **Reclamation:** the existing `retention` job (start-up and hourly) also expires rows past
  `expires_at` (24 h from proposal) or out of offers, whatever the kill-switch says, in its own
  transaction apart from the other purges and logging the exception class only; every write entry
  of the store (insert, offer, resolve and the writer's `promote`) runs the same housekeeping
  first, inside its own transaction. Start-up resets `offered` rows to `proposed` and expires what
  lapsed, or, when the kill-switch is off, voids every live row, and then **always** truncates the
  write-ahead log: a checkpoint a previous process still owed is not forgotten across a restart.
  `checkpoint_wal` never raises for a busy log or a closed connection; an owed checkpoint is
  retried at the next write entry and at every hourly run.
- **Transitions are compare-and-set** (`UPDATE … WHERE status = ?` and a row count). An `offered`
  candidate unanswered within `MEMORY_CANDIDATE_ANSWER_SECONDS` (proposed 60) returns to `proposed`
  on the next write entry; it is offered at most `MEMORY_CANDIDATE_MAX_OFFERS` times (proposed 2),
  the oldest first, and then expires. State changes only on a turn resolved to the subject at
  `strong`, or on the clock.
- **No canonical oracle.** Duplicate and contradiction are decided **at promotion only**, so whether
  an offer appears never depends on what is stored. A *contradiction* is the same value key under
  the opposite polarity among the active canonical facts; the candidate is then closed `rejected`
  (reason `contradiction`), nothing is written and its value is scrubbed. "Ya no me gusta el mate"
  is a correction and waits for CM-6.

### 7. The policy check

| Step | Action | `target_person_id` |
|---|---|---|
| Accept a candidate | `propose_personal_memory` | the candidate's subject |
| Speak an offer | `read_personal_conversation_memory` | the candidate's subject |
| Accept or reject an answer | `confirm_personal_memory` | the candidate's subject |

- **Request:** visibility `{personal}`, sensitivity `{normal}`, consent `not_required`. Targeting the
  subject (not the actor) lets `own-data-only` fire at promotion.
- **Actor:** face and voice from decision 3, never a token. One resolution serves the whole request,
  including the classic route's second `decide()`.
- **Order:** classify, evaluate, **write the audit row, then** the effect. If the audit write fails,
  nothing is stored or spoken (ADR 0019 §6.3). A rejection is audited like an acceptance. The
  model call takes tens of seconds, so both consents are re-read before the audit row and again
  right before the insert: a consent revoked meanwhile stores nothing, and the first re-read keeps
  an `allowed` row from being written for it (the second closes the short window in which the
  audit write waits for the write lock).
- **Same person:** candidates are always selected by `subject_person_id = actor.person_id`, never
  by an id the request carries, and a promotion requires the same equality.

### 8. Promotion

One function, **one `db.transaction()`**, never relying on an `IntegrityError`:

1. compare-and-set the candidate: it must be `offered` and not expired;
2. contradiction against active canonical facts → close it `rejected` (`contradiction`), write
   nothing;
3. select the active rows of that subject and predicate and compare folded keys; a match is the
   result (idempotent);
4. otherwise insert through `assert_literal_fact(..., manage_transaction=False)` (its docstring is
   amended: no longer reserved for the legacy migration) with keyword-only `visibility`,
   `sensitivity`, `confirmed_by_entity_id` (the actor) and `confirmed_at` (now); `LiteralFactV4`
   gains the two fields. `asserted_at` is the candidate's `proposed_at`, `confidence` 1.0,
   `source_memory_id` null;
5. mark `confirmed`, set `promoted_fact_id`, scrub the value.

### 9. Offer and answer (Plan 0063)

- **The offer is spoken only on a turn that is `strong` itself.** Whenever a `proposed` candidate
  exists, a generic voice turn starts the voice check concurrently with generation, so latency does
  not reveal it; if it fails, nothing is said. That is a third face-and-voice resolution per
  request, about 0.5 s of voice plus the face pass, paid only while a candidate waits. Measured in
  Plan 0063 on the shared laptop: the offer's check is hidden behind the model's own time, and an
  answer turn costs about 3 to 4 s over the speech-to-text with no model call. The check needs a
  clip of about 3 s or more: three turns of about 1.5 s failed it and nothing was offered, which is
  the intended silence. Every proposal, offer and answer re-checks consent through that resolution, so a
  revoked consent stops all three.
- **Placement.** The offer is composed in the shared text-turn seam and carried as an optional
  `offer` of `TextTurnResult` and `ResponsePlan`: `decide()` runs twice on a classic turn and never
  reaches streaming generation. Classic appends it to the text sent to the synthesiser, so one
  `audio_base64` carries reply and offer, and **the wire's `llm_response` does not contain it**.
  Streaming sends it as one more `audio` event before `done` with empty text. Neither goes through
  `log_spoken`, neither enters the continuity history or the `llm_ms` accounting, and there is
  never an offer on a fallback reply. The candidate becomes `offered` once the response has been
  built; no claim is made that it was heard.
- **Phrases** (fixed templates in `memory/lexicon.py`, neutral Spanish with **tuteo** — Pipec
  lives in Santiago de Chile, amended 2026-10-15 — filled with the stored value, which already
  passed decision 4): «Antes me dijiste que te gusta {x}. ¿Quieres que lo guarde? Dime: sí,
  autorizo guardar {x}.», with «te gustan» before a plural article, and the dislike («… que no te
  gusta {x}.») and prefer («… que prefieres {x}.») forms. The offer does not promise recall; that
  is CM-5.
- **The answer repeats the value** (Pipec's option A, 2026-10-15). A closed
  `InformationNeed.MEMORY_ANSWER`, recognised by a pure grammar in `intent_resolution`, matches a
  message that carries a closed verb (yes: `autorizo`, `apruebo` and, since Plan 0064, their
  third-person writings `autoriza`, `aprueba` — alone or followed by `guardar`, `a guardar` or
  `que guardes` — `guarda`, `guárdalo`; no: the same with `no`, `no lo guardes`, `no guardes`,
  `olvídalo`, `bórralo`) and the value. A bare «sí» or any phrase an attacker can know in advance
  never promotes. After the short verbs the value starts with an article, because ordinary speech
  uses them too («guarda silencio»).
  **Amended 2026-10-16 (Plan 0064, Pipec's decision D-3):** the answer survives how Whisper
  `small` writes it. The openers `ya`, `dale` and `po` are skipped like «sí»; a trailing `po` is a
  courtesy word like «gracias»; one leading `mi` or `mis` is dropped from the value and counts as
  the article of a short verb («guarda mi café»). The value stays mandatory, an opener or a verb
  alone still matches nothing, and the cost is known: more ordinary phrases («guarda mi …») have
  the shape of an answer and make the controller verify face and voice first (3 to 4 s); nothing
  is written without an open offer.
- **One open offer per person.** While an offer waits for its answer, nothing else of that person
  is offered, so an answer always names the offer it resolves.
- **No oracle.** The controller branch for that need resolves the actor (face and voice) **first**,
  for every message of that shape and whether or not an offer exists, and only then reads the
  actor's own candidates. The collaborator is injected **only by the voice routes**; on `/chat` and
  `/vision/respond` it is absent and the need falls through. Anything that is not a `strong` answer
  by the subject, carrying the value of an `offered` candidate, **falls through to ordinary
  generation**: no new phrase, no state change, no attempt counted (the ordinary turn is written
  by the model, and since Plan 0064 a model sentence that claims to have saved, registered or
  noted something is replaced by «Eso no lo he guardado.», because only a promotion stores a
  fact). Only after the
  verified owner's own open offer was found (so nothing is revealed to anyone else) can a refused
  or failed answer say a fixed phrase instead, so the model never improvises «listo» for something
  that was not saved.
- **Results:** «Listo, lo guardé.» or «Está bien, no lo guardo.» only after the transaction
  commits; after a contradiction, «No lo guardé: ya tengo guardado algo distinto.»; if the open
  offer was found and the step was refused or failed, «No pude guardarlo ahora. Dímelo de nuevo en
  un rato.» (Plan 0063 review).
- **Replay is not defended** (ADR 0016 §9). A recording of the owner saying the offered answer, with
  a photograph, could confirm it; it cannot choose the value, which the owner said earlier, and a
  liveness defence belongs to Phase 0.

### 10. Where it runs

Proposals run in the background task that follows a successful generic voice turn. The `MANUAL`
gate at the call site in `record_text_turn` is replaced by "identified by face with no token,
kill-switch on" (identity only; it is not an authorization decision). The voice check of decision 3,
the composite enrolment, the policy and its audit row all happen inside the background task, before
anything is extracted or stored. The scheduler callback is `(message, actor)`: it never receives the
assistant's reply, and the voice route closes over the turn's event (its correlation id), clip and
channel, which `text_turn` does not know. A turn whose generation failed proposes nothing. The
settings are fixed, each documented in `.env.example`; the phrase tables, the deny-list and the
grammar live in `memory/lexicon.py`: `MEMORY_CANDIDATES_ENABLED=false`,
`MEMORY_CANDIDATE_TTL_SECONDS=86400`, `MEMORY_CANDIDATE_MAX_LIVE=5`,
`MEMORY_CANDIDATE_VALUE_MAX_CHARS=80`, `MEMORY_CANDIDATE_MAX_OFFERS=2`,
`MEMORY_CANDIDATE_ANSWER_SECONDS=60`, `MEMORY_CANDIDATE_EXTRACTIONS_PER_HOUR=12`.

### 11. What leaves

- `consolidate_turn`, with its `MANUAL` gate and legacy writes, leaves the runtime. It never ran in
  production; episodes return in CM-4. `store_memory` and `assert_fact` lose their last production
  caller, so the plan handles the dead-code hook.
- The extraction seam the CM-0 benchmark and `just eval-memory` use **stays where it is**, typed
  and linted, and behaviourally unchanged, so `just eval-longitudinal` stays comparable until CM-3b
  replaces it; its extraction scenario is about family and pets, which are CM-3b. Its logging stops
  embedding the model's output. Only `consolidate_turn` goes.
- `PROPOSE_MEMORY` and `COMMIT_MEMORY` leave `AuthorizationAction` and the legacy evaluation: no
  production code consumes them, and nothing parses a stored `action` back into the enum.

### 12. Logging and audit; ADR 0019's seven obligations

Events carry ids, the canonical predicate, status, channel, a closed reason and counts, **never a
value and never an exception's message**. A failure the closed reasons cannot name logs the
exception class (and, for the proposal's catch-all, the innermost frame: file, line and function),
never the message. These are memory-layer reasons, separate from ADR 0016
§8's identity reasons. Closed reasons: `gate_no_match`, `not_a_taste`,
`negation_unsupported`, `sensitive_topic`, `gate_mismatch`, `strong_unreachable`, `not_grounded`,
`busy`, `budget`, `capacity`, `contradiction`, `duplicate`, `expired`, `denied`. Structured events:
`candidate.insert`, `candidate.proposal` and `candidate.promotion` (each carries the turn's
`correlation_id`, which also stamps the audit row), `candidate.policy`,
`candidate.extraction_failed`, `candidate.enrolment_check_failed` and
`candidate.proposal_error`. Every evaluated proposal, offer and answer is a row of
`authorization_audit_events` (action, categories, policy id); a proposal the store would refuse
(a repeated taste, a capped person) is pre-checked read-only and leaves no row.

| ADR 0019 §6 obligation | How CM-3a meets it |
|---|---|
| 1. Consuming resolver with the capability's scope | These actions declare no PIN scope: a no-token resolver, nothing spent |
| 2. Classify before retrieval | The classifier assigns before any read |
| 3. Audit before the effect, deny on failure | Decision 7 |
| 4. One generic spoken denial | CM-3a says nothing: ordinary generation, byte-identical (decision 9) |
| 5. `correct` supersedes | Not wired; a contradiction never overwrites |
| 6. `forget` after the confirmation step | Not wired (CM-6) |
| 7. The dialogue belongs to CM-3 | Decision 9 |

### 13. Everything this ADR leaves out has an owner

| Item | Why it is not in CM-3a | Owner | Closes when |
|---|---|---|---|
| Enrolling face and voice as the first setup step; who may pass and at which level; "you are with someone, still want it?"; reads of private normal data at `strong` (ADR 0019 §3 puts `read` at `basic`); the privacy of the senses | The firewall policy was built in the order face, then voice, and should have started from enrolment; it is Pipec's decision and spans every slice | **Phase 0 ("Paso 0")**, with the seed load; its ADR also gates new continuous capture | One setup flow enrols and verifies all biometrics and the access rules are written and tested |
| Relations and literals about third parties (children, partner, pets, birth dates, "no tenemos gato") | ADR 0019 §2 covers the owner's own data; household rules need an ADR | **CM-3b** | `extraction_family_and_pet` supported and passing |
| `lives_in` and `works_at` with validity dates | Location is `strong` already to propose; needs temporal supersede | **CM-3b** | `domicile_temporal_validity` write step |
| Facts reported by another person | Needs an attribution policy; the schema is ready | **CM-3b** | `provenance_attribution` propose step |
| A disclosure rule ("no menciones X delante de visitas") | No predicate fits and CM-3a refuses it. **Pipec decides:** a new predicate or a dataset version bump | **CM-3b** | `sensitive_preference_lifecycle` propose step |
| Perceptual candidates | The vision path does not call the store; source `perception` needs a policy | **CM-3b**, with P2.1 | `perceptual_evidence_stays_proposed` |
| `nombre`, `edad`, `especie` | No V4 predicate: the name is the entity, the age is derived, species belongs to pets | **CM-3b** | decided with the relation predicates |
| The first `SECURITY` datum | No `strong`-only category is written by CM-3a | **CM-3b**, read by CM-5 | one datum chosen and its gates specified |
| A `confirm` step in the benchmark; a process-restart seam | The dataset expects a same-turn acknowledgement and has no confirm operation or restart | **CM-3b** / **CM-7** preparation (dataset version bump, driver seam) | the benchmark can exercise decision 9 |
| Resolving a contradiction; removing live candidates | A contradiction is a correction; candidate rows hold values while live | **CM-6** (its reach includes `memory_candidates`) | roadmap row updated |
| Reading what was stored | Recall is a different slice | **CM-5** | row 9 |
| Episodes and `source_memory_id` of a candidate | Episodes declare owner and retention first | **CM-4** | row 8 |
| `/chat` as a channel | No audio, so no `strong` | Pipec's decision, unscheduled | the cross-cutting "wiring" row |
| CPU contention of extraction on the homelab; offer cadence; a short explicit answer failing verification | Judged only with a real person and clip | **Plan 0063** acceptance | measured and recorded |
| Seed load as a second input channel | It follows the writer; household members are third parties | After CM-3a (own data) and CM-3b (members) | its own row |

**Ordering.** CM-3b is **required before CM-7**, unplanned, written when CM-3a closes. CM-6's correct
and forget steps of `sensitive_preference_lifecycle` need its write step; CM-5 may open earlier but
its acceptance of scenarios without a write step waits.

## Alternatives considered

- **A `proposed` lifecycle inside V4.** Rejected: it rebuilds both V4 tables and makes "every row of
  V4 is canonical" false for every reader.
- **Candidates only in process memory.** Rejected: an offer can come after hours or a restart, the
  audit must say what was proposed, and CM-3b's perceptual candidates must outlive a session.
- **Propose and offer at `basic`, with `strong` only to confirm.** Rejected by the firewall rule: a
  face in frame, or a photograph of it, would let a third party write into the owner's memory and
  hear their stored values.
- **A bare "sí" or a fixed phrase as the answer.** Rejected: a public, replayable credential bound to
  nothing, and a one-syllable clip is the worst case for verification.
- **A fixed "could not verify you" phrase for a failed answer.** Rejected: it appears only when an
  offer exists, so it is an existence oracle.
- **Evict the oldest candidate at the cap.** Rejected: a third party could push the owner's out.
- **The model extracts every identified turn.** Rejected: tens of seconds of inference after each
  turn on a shared laptop.
- **Rules only, no model.** Rejected: spoken Spanish needs the object isolated.
- **Promote automatically at `basic` for low-risk predicates.** Rejected: it reverses the reason ADR
  0019 made `confirm` `strong`.
- **Offer and answer in `decide()`.** Rejected: it runs twice on a classic turn and never reaches
  streaming generation.
- **Change the registry default visibility.** Rejected: it is the household reader's read contract
  and pets share the predicates.
- **A `personal_memory_confirm` PIN scope now.** Rejected: the robot has no keyboard.
- **Give the extractor the assistant's reply, or keep the legacy write path.** Rejected: the reply is
  the model's own words; the legacy path is dead code that bypasses the policy.
- **One plan.** Rejected: the store and writer are fully testable; the dialogue needs hardware.

## Consequences

### Positive

- The first durable memory has provenance, a policy decision and an audit row per step, and no
  non-owner voice can write into it, hear it, confirm it, reject it or probe whether it exists.
- Everything left out is named, owned and tied to the benchmark step that demands it.
- The CM-0 benchmark, the V4 reader and the registry keep working unchanged.

### Negative

- **Nothing is stored until the owner's face and voice are enrolled** (`just face-auth-demo`,
  `just speaker-auth-demo --enroll`). That is the intent, and Phase 0 makes enrolment the first step.
- **Nothing can be read back until CM-5**; Plan 0063's acceptance inspects the database and the audit
  through a local, read-only report that prints states, predicates and counts, never values.
- **A genuine owner can fail verification** (a short or noisy clip, near the floor): the answer is
  then ordinary conversation and the candidate waits. Plan 0063 measures the false-rejection rate.
- **A contradiction writes nothing** ("ya no me gusta el mate" is closed with a spoken "ya tengo
  algo distinto guardado" and waits for CM-6's correction).
- **Replay is not closed** (ADR 0016 §9): a recording of the owner repeating the offered value could
  confirm it. It cannot choose the value, which comes from the owner's own earlier words.
- **A live value sits at rest** from proposal until it is resolved or expires (at most 24 h, and
  the hourly retention job reclaims it), on a database that is not encrypted.
- Tests that pin the legacy consolidation, the old actions and the memory guards change.

## Test consequences

Detail (file lists, tables, values) belongs to Plan 0062 and 0063. The behaviours the plans must
turn into RED tests, each from an audit finding or a decision above:

- no candidate without a verified voice on that clip, with a face-only, a token-bearing, a
  below-floor and a no-clip actor; no candidate with a second face; none from `/chat` or
  `/vision/respond` with zero credentials;
- the benchmark's own sentence "Prefiero que no menciones mi mudanza reciente delante de visitas…"
  and "prefiero no hablar de mi divorcio" are refused;
- a non-answer, a bare "sí", a replay of a public phrase, a wrong value and a non-strong answer all
  produce the same ordinary reply, wire fields and timing class, and change no row;
- an owner's candidate cannot be evicted by the cap, rejected or lapsed by another person;
- duplicates and contradictions decide only at promotion, with no `IntegrityError` and no
  observable difference in whether an offer appears;
- compare-and-set races (two proposals, offer against answer), expiry at store entry and at start-up
  (including a restart resetting `offered` and the kill-switch voiding live rows), migration 009
  (`user_version` 9, `SET NULL`, `CASCADE`, the scrub `CHECK`);
- the scrub is physical: after a resolution the old value is not found in the file or the WAL;
- no value or exception message in any log, including the conversation log for an offer;
- the policy matrix of ADR 0019 for propose, read and confirm with the face matched and unmatched
  and a token present; audit failure denies and stores nothing;
- classic and streaming parity of the offer, with the continuity history untouched and its synthesis
  failure swallowed; an owner → stranger matrix extension;
- a revoked voice or face consent between turns stops proposals, offers and answers; the answer
  collaborator is absent on `/chat` and `/vision/respond`; the scheduler callback no longer
  receives the reply and carries the clip and the correlation id; the test fixture that forces
  `memory_enabled=False` pins the new flag too;
- the legacy tests of `consolidate_turn`, the old actions, the four schema tests that assert
  `user_version` 8 and the architecture guards that list the V4 readers and tables are
  rewritten.

## Acceptance (Plan 0063, real hardware, outcomes only)

Enrol the face and the voice first. Each case is recorded as pass or fail, never with its content.
Pipec runs the acceptance alone (2026-10-15): "another voice" is a recording or a different
synthetic voice played near the microphone, and "another face" a photo on a phone; they are
recorded as substitutes:

1. State a preference; on a later turn the offer is spoken; saying «sí, autorizo guardar {x}» in the
   owner's voice creates one `personal` fact with `confirmed_by`; the audit shows `allowed` for read and
   confirm.
2. The same with the rejection: `rejected`, value gone, no fact.
3. The same words in another person's voice while the owner's face (or a photograph) is in frame:
   no promotion, an ordinary reply, nothing changes.
4. An unknown speaker, or the owner with a second person's face in frame, states a preference: no
   candidate. The same with the owner's face but a recording of another voice.
5. Restart between offer and answer: the candidate returns to `proposed`, is offered again, and the
   answer promotes.
6. «Sí, autorizo guardar {y}» with no offer outstanding, or with a different value: an ordinary
   turn, no write.
7. The benchmark's sentence about the move is refused: no candidate.
8. Extraction contention on the shared laptop (and the homelab when available), the cost of
   the third face-and-voice resolution per turn, and the false-rejection rate of the explicit
   answer are measured.
9. A photograph plus an earlier recording of the owner is **measured, not defended**: the
   outcome is recorded (ADR 0016 §9) and feeds Phase 0's liveness decision.

**Result (2026-10-16, Pipec alone, on the shared laptop; no homelab):** cases 1, 2, 3, 4 (a, b, c),
6 (a, b) and 7 passed; case 5 is partial (the offer survived the restart and was offered again; the
answer was mis-heard by the speech-to-text, and promotion after an offer is proven by case 1);
case 8 is measured (the explicit answer parsed 2 of 4 times, the failures being Whisper `small`
writing «autoriza a guardar …»; widening the closed verbs is left to the owner); case 9 and the
homelab were **not run** and need a second person or device. Details, counts and the findings
left open are in [the acceptance note](../evals/0063-memory-dialogue-acceptance.md).

## Docs to update

With this ADR as **Proposed**: the ADR index; the CM-3 row of the roadmap and the memory map (CM-3a
and CM-3b, dependency columns); the cross-cutting row on what CM-3a leaves; the roadmap's seed-load
row and the local task table, which receive the Phase 0 items of decision 13.

With **Accepted** (Plan 0063, done 2026-10-16): ADR 0020's status and its *Review* trigger (the §1 and §2
amendments), the vocabulary and the *Lifecycle* contract of `memory-and-world-state.md` and the
memory map, the CM-5 row ("decided when CM-3 is planned"), `current-state.md` and its Archify
diagram, `architecture/README.md`, `identity-and-access.md` where it names `confirm` as unwired,
ADR 0019's status line, the plan index and the operator manual's new settings.

## Review

Revisit when CM-3b opens, when Phase 0 defines enrolment and access levels (this ADR's `strong`
requirement may then be expressed as a level), when CM-5 reads personal memory, if the explicit
answer proves too costly day to day, or when measured extraction cost on the homelab changes the
gate's economics.

## Follow-up

- [Plan 0062](../plans/completed/0062-cm3a-memory-candidates-and-writer.md) — candidates, the writer
  and the extraction (written 2026-10-14; closed 2026-10-15, PR #183; no hardware, no spoken
  dialogue; `promote` has no caller in a route yet).
- [Plan 0063](../plans/completed/0063-cm3a-memory-dialogue.md) — the spoken offer and answer
  (decision 9) and the hardware acceptance; closed 2026-10-16, it moved this ADR to `Accepted`. The
  next free ADR number is 0022.
- Left open by the acceptance, none of them a regression of this ADR: the model sometimes says it
  saved something on a message that only has the shape of an answer (nothing is written);
  occasional replies in French; whether the closed answer should admit the speech-to-text's common
  mis-hearings; short turns cannot carry an offer; case 9 (replay) and a homelab measurement.
- Phase 0 — enrolment first, access levels, escalation with company (decision 13).
- CM-3b, CM-4, CM-5, CM-6.
