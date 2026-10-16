# 0022 — Household rules: whose data a third party's fact is, and one writer for every channel

- **Status:** Proposed (2026-10-16). Written from the audit of CM-3b made on 2026-10-16 (nine
  pieces, of which only the channel-neutral writer is needed before Step 0) and from the Plan 0063
  hardware acceptance. Every decision below carries the recommendation of that audit; **Pipec
  confirms each when he accepts this ADR** (they are his to make). Accepted when he confirms them
  and [Plan 0065](../plans/open/0065-cm3b-a-channel-neutral-writer-core.md) closes.
- **Date:** 2026-10-16
- **Builds on:** [ADR 0006](0006-personal-and-family-companion-profiles.md),
  [ADR 0009](0009-locked-posture-and-scoped-capabilities.md),
  [ADR 0016](0016-face-and-voice-identity-fusion.md),
  [ADR 0019](0019-personal-memory-capabilities.md),
  [ADR 0020](0020-authorized-actor-in-the-conversation.md),
  [ADR 0021](0021-memory-candidates-and-the-canonical-writer.md)
- **Amends:** [ADR 0019](0019-personal-memory-capabilities.md) §2, which limits every personal-memory
  capability to the actor's own data and to the `personal` visibility: this ADR adds a household
  pair of capabilities (decision 3). It also amends [ADR 0021](0021-memory-candidates-and-the-canonical-writer.md)
  decision 5 on who assigns a stored fact's visibility (decision 6) and its decision 4 on what the
  gate may extract (decisions 1, 9 and 10 below say what stays out).
- **Implemented by:** [Plan 0065](../plans/open/0065-cm3b-a-channel-neutral-writer-core.md) (the
  writer core, tranche A of CM-3b). Tranche B (spoken capture of third parties, reported facts, the
  behaviour of the disclosure rule, perceptual candidates) is planned after Step 0.

## Context

CM-3a stores the owner's own tastes, as `personal` literal facts, through one writer
(`memory_writer.promote`) reached by one channel (the spoken dialogue). The roadmap's CM-3b and
Step 0 ask for more: the household itself (children, a partner, pets), places with validity,
facts reported by someone else, a disclosure rule, the first SECURITY datum, and an initial load
that must go through *the same writer* as the conversation (Plan 0050, non-goals, rule 1).

What the audit verified in code (`feat/0063-cm3a-memory-dialogue`, 2026-10-16):

1. `assert_entity_relation` cannot take a visibility, a sensitivity, a confirmer or a validity
   range; the `confirmed_by_entity_id` column exists and nobody writes it
   (`memory/relational_v4.py`). `assert_literal_fact` can.
2. `memory_candidates` holds literals only: no relation target, no validity, no origin other than
   voice (`migration_009`); `promote` writes `personal`/`normal` literals and only opposes
   `likes`/`dislikes`.
3. All five personal-memory capabilities accept only the `personal` visibility and
   `target_person_id == actor.person_id` (`cognition/authorization.py`): a child, a partner or a
   pet as subject is **denied by design**, and so is a `household`-visibility fact (the default of
   `child_of`, `birth_date` and `likes`).
4. The household reader returns only rows whose stored classification equals the authorized one;
   a writer that stored `personal` would be invisible to it
   (`memory/policy_gated_v4_reader.py`).
5. The registry has no `species` and no disclosure or SECURITY predicate; `entities` is
   `UNIQUE(name, type)`, so two third parties with one name collide.
6. The longitudinal benchmark's `provenance_attribution` scenario is marked `personal` but needs
   two identified people, and its vocabulary (`fact|tomas|nacimiento|2016`) is not V4's.

## Decision

### 0. The frame that governs the rest (Pipec, 2026-10-16)

In the `personal` profile the speaker is always the identified owner, and **everything said is said
by the owner about the owner's world**: the data belongs to the owner. Every first-person
possessive («mi novia», «mi hija», «mi perro», «mi casa») is anchored to the owner; every fact is
stored as household data of the owner, with the owner as asserter and as confirmer. Examples:
«te presento a mi novia» is the owner's partner; «mi hija tiene 8 años» means the owner has a
daughter (the existing one when exactly one is known, say the one named in the household) and her
age, as stated, is 8. A reference by relationship resolves to the owner's household entity of that
relationship when exactly one exists; when none exists the capture proposes creating it (and asks
for the name if it was not given); when several exist it asks which; in doubt it discards. That
resolution belongs to the spoken capture (tranche B); this ADR and Plan 0065 provide the rules and
the writer it will call. Decisions 1 to 11 below are the consequences, not exceptions.

### 1. Who the owner may write about (profile `personal`)

A closed set: the owner's **children, partner and pets**. Anyone else named (friends, a boss,
neighbours) is outside the gate ("when in doubt, discard"); widening needs an ADR in the `family`
profile.

### 2. One writer, every channel

There is one canonical writer: `(subject, predicate, object-or-literal, classification, asserter,
channel, confirmer)`. `promote` (the spoken confirmation, CM-3a) and the Step 0 import are two
callers of it; a future perceptual source is a third. The channel is recorded; each channel
declares in the Step 0 ADR the assurance it needs. **The speaker never assigns the
classification**: the writer does, from the predicate and the subject (Plan 0050 rule 1, ADR 0021
decision 5).

### 3. A household capability pair

New capabilities `propose_household_memory` and `confirm_household_memory`: the owner only, the
`household` visibility, `strong` assurance (face and voice of the same person on the turn, never a
token). They are separate from the five personal ones, whose rule (own data only) is unchanged.
Reading stays through the existing policy-gated reader, which already serves `household` facts.
The data of a child or a pet belongs to the owner **as guardian**: the minor neither speaks for
nor confirms their own data in the `personal` profile.

### 4. Other adults

For a partner (or any other adult) the owner may write **only the name and the relationship**.
Their birth date, tastes, health or anything private waits for the `family` profile, where that
person is enrolled and decides (ADR 0006: an owner does not inherit another adult's private data).

### 5. Facts reported by another person

A fact asserted by someone other than its subject is **not written** in the `personal` profile.
The benchmark scenario `provenance_attribution` needs two identified people and moves to the
`family` scope in dataset v3, which is declared in the evaluation report (the full suite stays red
until P3.2). The writer keeps one invariant, with a test: nobody but the subject writes into the
subject's `personal` memory.

### 6. Validity and dates

`lives_in` and `works_at` take `valid_from` = the spoken date when there is one, else the date of
the assertion; the previous row is closed **at that `valid_from`** (not at `now`); "I used to live
in X" without a date is a historical row with no `valid_from`. A date of birth is stored only as a
**full ISO date** (a year alone is not stored; the robot asks for the full date). **A stated age
is stored** (Pipec, 2026-10-16: «mi hija tiene 8 años» is kept) as the predicate `stated_age`,
a single current value **with its as-of date** (the assertion date): «8, as of 2026-10-16». The
current age is derived from it (the stated age plus the whole years elapsed) and a `birth_date`,
when known, supersedes it. The age is never persisted as "today's age".

### 7. Entities

Never merge a third party by name alone. A name that already exists is asked about; if in doubt it
is discarded. The import requires an explicit key. A pet's species is the literal predicate
`species` (single, current).

### 8. The disclosure rule

A new predicate in the registry (name decided in Plan 0065) states «do not mention X in front of
visitors»: the audience is fixed as "any other person present". This ADR and Plan 0065 add the
**predicate and its classification only**; the behaviour needs CM-5 (retrieval filtering) and the
"are you with someone?" escalation of Step 0, so nothing consumes it yet. The benchmark scenario
`sensitive_preference_lifecycle` keeps its meaning (a new predicate, not a moved goalpost).

### 9. The first SECURITY datum

The first datum is an **alarm or gate code**. Tests and the hardware acceptance use an invented
value and record outcomes only. The predicate and its `security` sensitivity (already `strong`
in the policy) are registered, but **the writer refuses to store a `security` value until the
Step 0 ADR decides storage at rest** (plain SQLite, per-value encryption or reference only;
backups, `secure_delete`, `reset-db`). Reading it is CM-5.

### 10. Negations and the spoken capture of third parties

A negation («no tenemos gato») is never persisted. The spoken capture of a third party (names by
Whisper, grouped offers, a date parser for spoken dates, a migration of `memory_candidates` for
relation targets) is tranche B, after Step 0: names are fragile in the speech-to-text and each
candidate costs 30 to 60 s of extraction on the shared laptop.

### 11. What does not change

The firewall (face **and** voice of the same person on that turn's clip, never a token), the
no-oracle rule, the closed answer that repeats the value, the audit-before-effect rule, and the
fact that a value never reaches a log, `llm_response` or the history.

## Alternatives considered

- **Third parties as `personal` facts of the owner.** Rewrites the household reader (finding 4) and
  loses the "household" meaning; rejected.
- **Any named person.** Opens the memory to friends and neighbours without their consent; rejected
  for the `personal` profile.
- **Store the partner's facts as «according to the owner».** A private fact of another adult would
  live in the database without that adult seeing or confirming it; rejected until `family`.
- **Move the disclosure scenario into `likes`/`prefers`.** Moves the benchmark's goalposts: that
  scenario is the only one that tests derived copies (fact, episode, embedding, summary, cache).
- **Spoken capture before Step 0.** Costly and fragile (names, extraction time); the import by file
  resolves names without Whisper.

## Consequences

### Positive

The initial load and the conversation share one writer and one classification rule; the policy
change is explicit instead of a patch; the minors and the other adults are protected by default;
the benchmark's contradictions are surfaced.

### Negative

A second pair of capabilities and a larger policy matrix; the owner cannot yet tell the robot about
a friend; `provenance_attribution` leaves the personal acceptance; the SECURITY datum cannot be
stored until the Step 0 ADR.

## Test consequences

Matrix tests for the household pair (owner `strong` allowed; owner without voice, token, visitor,
other adult, minor denied; the five personal capabilities unchanged); the writer from two channels
produces the same classification; a third party with a repeated name is never merged; `species`
and the validity rules; the writer refuses a `security` value; the invariant of decision 5;
dataset v3 loads and the driver reports honestly what it does not support.

## Docs to update

With **Accepted**: ADR 0019 §2 and ADR 0021 decisions 4 and 5 (cross-references), the memory map
and the roadmap rows for CM-3b (tranches A and B), `identity-and-access.md` (the household pair),
`memory-and-world-state.md` (the writer, validity, the disclosure and SECURITY predicates),
`current-state.md` and the plan index.

## Review

Revisit when Step 0 decides the levels per channel and the storage at rest, when the `family`
profile enrolls a second adult, when CM-5 filters retrieval, or if a measured cost on the homelab
changes the economics of the spoken capture.

## Follow-up

- [Plan 0065](../plans/open/0065-cm3b-a-channel-neutral-writer-core.md) — tranche A, the writer core.
- Tranche B of CM-3b — after Step 0 (spoken capture, reported facts, disclosure behaviour,
  perceptual candidates, benchmark restart seam).
- The next free ADR number is 0023.
