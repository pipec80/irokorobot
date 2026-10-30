# 0026 — Read the owner's profile back: a small card in every identified turn, and nothing sensitive in it

- **Status:** Accepted (2026-10-28, when Plan 0074 closed). Written from the audit of `docs/` and the research of the same
  day (kept in the ignored `project-history/`), after Pipec approved the seven decisions of the
  closing plan of conversational memory on 2026-10-28 (see *Pipec's decisions and where they
  land*). It became `Accepted` when Plan 0074, the first plan that implements it, closed. Every
  decision below is the author's recommendation unless it says *Confirmed by Pipec*.
- **Date:** 2026-10-28
- **Builds on:** [ADR 0016](0016-face-and-voice-identity-fusion.md),
  [ADR 0019](0019-personal-memory-capabilities.md),
  [ADR 0020](0020-authorized-actor-in-the-conversation.md),
  [ADR 0021](0021-memory-candidates-and-the-canonical-writer.md),
  [ADR 0022](0022-household-rules-and-third-party-memory.md),
  [ADR 0024](0024-seed-load-senses-secrets-and-channels.md)
- **Amends:** [ADR 0020](0020-authorized-actor-in-the-conversation.md) §7 (the prompt may carry
  two datums of the speaker, decision 7); the order of the roadmap (CM-5 is split, decision 1);
  [ADR 0021](0021-memory-candidates-and-the-canonical-writer.md) decision 13 and
  [ADR 0024](0024-seed-load-senses-secrets-and-channels.md) decision 7 on whether reads of
  ordinary private data move from `basic` to `strong` (decision 4: for `normal` data they do not).
- **Implemented by:** [Plan 0074](../plans/completed/0074-cm5a-profile-card.md) (closed 2026-10-28,
  accepted by Pipec on real hardware: [record](../evals/0074-profile-card-acceptance.md)).

## Context

Iroko can write: a taste the owner says is offered back and, after a spoken «sí, autorizo»,
becomes a V4 fact (CM-3a), and the whole commissioning pool is loaded by file (Step 0). It cannot
**read any of it back**. Pipec's goal is the opposite of a toy: «te conté que me gusta un equipo
de fútbol, ¿te acuerdas?» must work, with the language model used as little as possible and the
robot's own memory doing the work.

What holds today (verified in code on `main` at `eed9cfd`, 2026-10-28):

1. `PolicyGatedV4Reader` serves **household** data only; a row stored under another label is
   withheld. The owner's `personal` rows (tastes, `preferred_name`, `address_form`, the pool) have
   no reader. Only the children's list and count are wired to the controller; every other
   authorized household question answers «todavía no está conectada».
2. The legacy path, `build_context`, is reachable only with `MANUAL` evidence, which no production
   route emits, and `_format_memory_block` writes the entity's **name** into the system prompt,
   which ADR 0020 §7 forbids.
3. The policy already has `read_personal_conversation_memory`: owner only, own data only,
   `personal` visibility, minimum assurance `basic`; `biometric`, `medical` and `location` data
   need `strong` (ADR 0019 §3). One caller exists: the spoken offer (`candidate_dialogue`).
4. A generic turn identifies its speaker by the face at `basic`, with no voice and no grant spent
   (ADR 0020 §1); `prepare_text_turn` already opens the continuity session for that person. An
   unknown or ambiguous speaker suspends it and reads nothing.
5. The prompt tells the model that the authorized memory block and what was said in this
   conversation are its **only** sources and that it must admit not remembering (`_MEMORY_DISCIPLINE`).
6. The roadmap puts CM-4 (episodes) before CM-5 as a hard dependency, but reading structured V4
   facts needs no episodes; ADR 0021 says CM-5 «may open earlier» and ADR 0024 calls the profile
   read «the first slice of CM-5».
7. What the research found (sources in the ignored research note): the memory that works in
   practice keeps a **short card always in context** and a **searchable archive consulted only on a
   cue**; letting a language model decide every write costs more and recalls less; a small model
   does not say «no me acuerdo» by itself, so the answer to an empty search must be fixed text.

## Decision

### 1. CM-5 is split in two, and the first half does not wait for episodes

**CM-5a** reads the structured V4 facts that already exist (this ADR, Plan 0074). **CM-5b** reads
episodes and the semantic archive and depends on CM-4. The roadmap's CM-5 row, the memory map and
the plan index are amended in the same change. CM-5a depends on CM-2, CM-3a and Step 0, not on
CM-4. *Confirmed by Pipec (decision 1).*

### 2. The card: a closed list, small, and nothing else

The **card** is what the robot always has at hand about the person it is talking to. Its content is
a closed allow-list of predicates, owner's own data, visibility `personal`, sensitivity `normal`,
lifecycle active:

| Predicate | Why it is in |
|---|---|
| `preferred_name` | How to address the person |
| `address_form` (`tu` or `usted`) | The register of the reply |
| `likes`, `dislikes`, `prefers` | The tastes the person said and confirmed, or loaded at the alta |

- **Nothing else enters, whatever its sensitivity.** The reader filters by the allow-list **and**
  by visibility and sensitivity, so a predicate added later to the registry is not read by
  accident. A new predicate enters only by amending this decision.
- **Left out on purpose:** `private_topic` (its content may be health or grief), the names of
  relatives, partner, children and pets (answered on an explicit question, decision 5),
  `birth_date`, `stated_age`, and everything `private`, `medical`, `location`, `child_data` or
  `security`, including `secret_holder` and `document_location`.
- **Size and recency:** at most 600 characters and 12 tastes. Order: `preferred_name`,
  `address_form`, then tastes **newest first**, grouped by predicate in one line each. No model
  processes them: the writer already deduplicates by key. What does not fit stays stored and is
  dropped from the card without a message; the log carries the count, never a value. Older tastes
  are reachable when the archive search exists (CM-5b). *Confirmed by Pipec, 2026-10-28
  («procesarla y recuperar lo más reciente»).*
- **Rendering:** a new renderer, not `_format_memory_block`. It carries no entity name, id or role,
  one datum per line, values as quoted data. The values passed the preference grammar or the
  import validator, so they are short noun phrases, not free text.

### 3. When the card is read, and what audits it

- On every generic turn whose speaker the continuity session already accepts (an identified person
  at `basic` or more): classic `/transcribe` and `/transcribe/stream`. **`/chat` and
  `/vision/respond` read no card.** `/chat` is the operator's diagnostic tool, controlled and not
  public (ADR 0025 decision 9: public mode, no household data), rarely used by the owner; it keeps
  its behaviour. *Confirmed by Pipec, 2026-10-28.* A suspended session (unknown, ambiguous,
  vetoed) gets **no card**. The voice is not consulted, so the card costs one local read and no
  latency.
- Each read evaluates `read_personal_conversation_memory` for the person's own `personal`/`normal`
  data and writes **one audit row before the effect**; a failing audit or a denial means no card
  (ADR 0019 §6.3). The volume is one small row per identified turn; revisit if it grows.
- A kill-switch, `PROFILE_CARD_ENABLED`, off by default in the code like
  `MEMORY_CANDIDATES_ENABLED`; it needs `MEMORY_ENABLED`. **A delivered robot has it on.** Iroko is
  made to order: Pipec interviews the client, loads the pool and sets the unit up (the alta), and the
  client only uses it at home; so the commissioning turns the card on and checks it with a test
  turn, as a capability of the readiness report (ADR 0024 decision 14), not the client.

### 4. The level of a read: `basic` for ordinary data, `strong` for anything above

This closes the question ADR 0021 decision 13 and ADR 0024 decision 7 left open for **`normal`**
data: reads stay at `basic` (ADR 0019 §3). The card holds only tastes and two ways of addressing
the person, so what a photograph of the owner or a second voice beside them could obtain is low
and stated here as an accepted risk (ADR 0016 §9). A second face in frame already suspends the
session (ADR 0020 §4); a second **voice** with no face is not detected. Anything above `normal`
needs `strong` (ADR 0019 §3), is never in the card and is read only on an explicit question,
which this ADR does not open (decision 6).

### 5. Explicit questions are answered by the controller, not by the model

A new `InformationNeed` for «¿qué sabes de mí?» and «¿qué te he contado?» (a pure rule in
`intent_resolution`) makes the controller answer from the same reader with a **fixed template**
that lists the card's items. An empty card answers a fixed «todavía no me has contado cosas que
pueda recordar». A speaker who is not identified gets the existing generic denial of ADR 0016 §8,
so no oracle appears. The list also tells the person what the robot holds, which the studies with
older adults ask for (control and transparency). Structured questions about the pool («¿cómo se
llaman mis padres?», health, address) are the **next** plan, not this one; they need `strong` for
sensitive data and are where decision 6 applies.

### 6. Replay and liveness: not defended in CM-5a, with an owner

The card holds nothing for which a replay of a face and a recording would be harmful, so CM-5a
adds no liveness defense. The decision the roadmap gave to CM-5 is made like this: **CM-5a opens no
sensitive read**; the plan that does must choose, with Pipec, between `strong` alone (accepting
that 6 of 8 replay probes passed, ADR 0016 §9) and a PIN grant (the robot has no keyboard until the
electronics decide it). The question «¿estás con alguien?» belongs to that same plan. Until then,
sensitive pool data stays unreadable by voice, as today.

### 7. The prompt may carry two datums of the speaker

ADR 0020 §7 forbids the speaker's name, id or role in the prompt. This ADR allows exactly
**`preferred_name` and `address_form`**, as lines of the card, and nothing else about the person.
The memory-discipline text is adjusted to name the card as a source. The language rule keeps
tuteo for every fixed controller string (Plan 0064's guard); `address_form = usted` reaches only
the model's own sentences, a known limit written in the plan.

### 8. The legacy path stays closed and untouched

`build_context`, the `memories` table and the `MANUAL` gate are not changed by CM-5a. CM-4's ADR
decides whether they are retired or replaced; nothing reads them in production today. *Decided by
[ADR 0027](0027-conversation-record-and-the-diary.md) decision 9 and done by [Plan 0076](../plans/completed/0076-cm4-conversation-record-and-diary.md):
the path is retired; `memories` stays empty and refuses rows (foreign keys still name it).*

### 9. What CM-7 requires (Pipec's decision 2)

The personal acceptance of the benchmark keeps its four frozen gates, with no relaxed threshold. It
stops requiring what Pipec moved out of the path:

| Scenario need | Where it goes | Why |
|---|---|---|
| Third parties captured **by voice** (`extraction_family_and_pet`) | A staged scope reported as pending, after CM-7 | Third parties already enter by the import and by `iroko-admin` (ADR 0024, 0025) |
| Perceptual candidates (`perceptual_evidence_stays_proposed`) | The same pending scope, with P2.1 | CM-7 would otherwise depend on P2.1, which comes after it |
| Facts reported by another person (`provenance_attribution`) | Already `family` (ADR 0022 decision 5, dataset v3) | Family work (P3) |

Nothing is excluded: the staged verdicts already work this way for the family stage (pending
scenarios stay visible and the full suite keeps failing until they are built). It needs dataset
v4 and a small change of the staged-verdict code, in the plan that prepares CM-7. The access-code
scenario moves to `secret_holder` in the same bump (ADR 0024 decision 4). CM-3b tranche B shrinks
to what stays: `lives_in` and the disclosure rule `private_topic` by voice, the owner's own data.

## Pipec's decisions and where they land

Approved by Pipec on 2026-10-28 («todo estoy de acuerdo»):

| # | Decision | Where it is written |
|---|---|---|
| 1 | CM-5a before CM-4 | Decision 1 of this ADR |
| 2 | What CM-7 requires | Decision 9 of this ADR |
| 3 | The diary: summaries only, 90 days, only turns whose voice was verified | The ADR of CM-4 |
| 4 | Forgetting by voice: face, voice and a spoken confirmation for one thing; the PIN only for «olvida todo» | The ADR of CM-6, which amends ADR 0019 |
| 5 | `preferred_name` and `address_form` in the prompt | Decision 7 of this ADR |
| 6 | Multilingual embeddings | Measured first, in the plan of CM-4 |
| 7 | Order the first electronics in November; the network ADR in December | Outside memory; the roadmap's electronics gate |

## Not decided here

| Subject | Why not now | Owner |
|---|---|---|
| The diary, the archive search, the recall cues, spoken dates and the fixed «no me acuerdo» | CM-4 and CM-5b | Their own ADRs |
| Structured and sensitive reads of the pool, «¿estás con alguien?» | Needs decision 6 | The plan after 0074 |
| Correcting and forgetting by voice | CM-6 | Its ADR |
| Whether `build_context` and `memories` are retired | CM-4 | ADR 0027: retired (Plan 0076) |
| Greeting first and reminders | The `care` profile and P2.3 | A future ADR |

## Alternatives considered

- **The card at `strong` (a voice check on every generic turn).** Rejected: about 0.5 s on every
  turn and the voice model for all chat (ADR 0020 rejected it), for data that is only tastes.
- **Let the model search its memory with a tool (Letta, MemGPT style).** Rejected: a small local
  model under-uses retrieval, and it moves a permission decision into the model.
- **Put the whole profile in the prompt.** Rejected: health and location would reach the model on
  a photograph, and the prompt of a 3B model gets slower and less faithful.
- **Reuse `build_context`.** Rejected: it prints the entity's name and sits behind a gate no route
  opens; patching it would reopen the legacy path.
- **A framework for memory (Mem0, Zep, Letta).** Rejected: the writer, the policy and the
  confirmation already exist and are stricter than what they offer.
- **A card that includes the names of the relatives.** Rejected for now: it is the commonest
  question after tastes, but a name of a family member is not harmless in front of a visitor; the
  explicit question of decision 5 covers it.

## Consequences

### Positive

The robot can say what it knows about the person, for the first time, with no language-model
decision and no latency; nothing sensitive reaches the prompt; the order of CM stops waiting for
episodes where it need not; the CM-7 gate stops depending on work Pipec moved later.

### Negative

A photograph of the owner can make the robot address them by name and show their tastes; the
card is small, so a taste stored but over the cap is not recalled until the explicit question
exists for it; `usted` does not reach fixed strings; one audit row per identified turn; the
benchmark still reports most steps unsupported until each plan connects its seam.

## Test consequences

The allow-list is closed (a predicate outside it, any sensitivity above `normal` or a visibility
other than `personal` never reaches the card); no entity name, id or role in any prompt (a
property test over the renderer); an unknown, ambiguous or vetoed speaker gets no card and the
generic denial on the explicit question; the audit row is written before the card and a failing
audit gives no card; the cap and the order; the switch off means the prompt is byte-identical to
today's; classic and stream parity; the owner → stranger matrix gains the card.

## Docs to update

With `Proposed`: the ADR index, the roadmap (the CM-5 row split, the CM-7 row, tranche B of CM-3b),
the memory map, the plan index and the open-plan index. With `Accepted` (when Plan 0074 closes):
ADR 0020 §7, ADR 0021 decision 13, ADR 0024 decision 7, `identity-and-access.md`,
`current-state.md` and its diagram, the operator manual (the new setting).

## Review

Revisit when CM-4 or CM-5b land, when the first sensitive read is planned (decision 6), when the
card proves too small or too noisy in daily use, when `address_form = usted` is used for real, or
when the electronics change what identifies a person.

## Implementation notes (Plan 0074, 2026-10-28)

What the code does where it differs from, or settles, the text above:

- **Decision 7, the memory-discipline text, is not edited.** Changing `_MEMORY_DISCIPLINE` would make
  every prompt differ from `main` with the switch off. The card carries its own authorizing sentence
  («Es memoria autorizada: apóyate en ella solo si viene al caso y no inventes nada que no esté
  aquí.»), so the byte-identity of the switch-off prompt, response and wire holds.
- **Decision 3, «a test turn in the alta», becomes: the person who commissions the robot turns
  `PROFILE_CARD_ENABLED` on and verifies it by asking «¿qué sabes de mí?».** There is no automated
  test turn (YAGNI). The readiness report gets its own capability row, `answer_profile` (decision 14
  of ADR 0024), checked by that person.
- **Decision 3, where the card sits.** `PROFILE_CARD_POSITION` (`with_memory`, the default, or
  `before_language`) is configurable because the acceptance measures which one the model follows
  better; the language rule stays the last block either way.
- **Decision 5, no oracle.** A speaker who is not identified and an identified person the policy
  refused hear the same phrase; a failing audit or read has its own phrase because it is not a
  refusal. The spoken summary is kept out of the opt-in spoken-text log (a marker is logged instead).
- **Decision 2, the `tu` form is not rendered.** On the first hardware run the 3B model opened replies with «Tú, bien.» because of the line «Trato: tú.». The prompt block says nothing for `tu` (the language rule already demands tuteo) and «Trato: usted.» only for `usted`; the spoken summary still says the form.
- **Decision 7, `usted` is a known limit with the 3B model.** With `usted` the card says «Trato: usted.» while the language rule of the same prompt demands tuteo, and the replies became incoherent on hardware (2 of 2 turns; coherent again with `tu`). `address_form = usted` is not to be used with `qwen2.5:3b` until the language rule follows the form (a separate plan, with an amendment to the dialect decision of Plan 0064 and a hardware measurement).
- **Decision 3, the position.** Measured on hardware, `with_memory` (0 of 6 replies opened with «Tú, …», the name used every time) beat `before_language` (5 of 5 opened with «Tú, muy bien.», no name); `with_memory` stays the default. The extra time to the first audio was about 0.2 s.
- **Access.** A speaker who is not face-identified at `basic` (a token speaker included) never
  reaches the policy, so no denial row is written per turn; an identified non-owner is audited as
  denied. One audit row per read (decision 3's volume note stands).

## Follow-up

- [Plan 0074](../plans/completed/0074-cm5a-profile-card.md) — the card and the explicit summary
  (closed 2026-10-28).
- The next free ADR number is 0027.
