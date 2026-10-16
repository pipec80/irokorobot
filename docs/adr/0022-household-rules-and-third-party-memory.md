# 0022 — Household rules: whose data a third party's fact is, and one writer for every channel

- **Status:** Proposed (2026-10-16), **revised the same day after an independent review** (see
  *Review record*). Written from the audit of CM-3b (nine pieces, of which only the channel-neutral
  writer is needed before Step 0) and from the Plan 0063 hardware acceptance. Every decision below
  carries the recommendation of that audit; **Pipec confirms each when he accepts this ADR** (they
  are his to make): decisions 0 to 14 of the audit table were confirmed by him on 2026-10-16
  («estan correctas todas»), with the changes of that day (decision 0, the stated age of decision 6);
  the three decisions the review added (marked *Confirmed by Pipec* below) he **confirmed the same day
  by taking the recommendations** (migration 010 for the asserter and channel; the personal
  provenance scenario; no homonymous third parties until Step 0). Accepted when
  [Plan 0065](../plans/open/0065-cm3b-a-channel-neutral-writer-core.md) closes; that plan may start
  while this ADR is `Proposed`, now that those three are confirmed.
- **Date:** 2026-10-16
- **Builds on:** [ADR 0006](0006-personal-and-family-companion-profiles.md),
  [ADR 0009](0009-locked-posture-and-scoped-capabilities.md),
  [ADR 0016](0016-face-and-voice-identity-fusion.md),
  [ADR 0019](0019-personal-memory-capabilities.md),
  [ADR 0020](0020-authorized-actor-in-the-conversation.md),
  [ADR 0021](0021-memory-candidates-and-the-canonical-writer.md)
- **Amends:** [ADR 0019](0019-personal-memory-capabilities.md) §2, which limits every personal-memory
  capability to the actor's own data and to the `personal` visibility: this ADR adds a household
  pair of capabilities (decision 3). [ADR 0021](0021-memory-candidates-and-the-canonical-writer.md)
  decision 5 on who assigns a stored fact's visibility (decision 2 below), its decision 4 on what
  the gate may extract (decisions 1, 9 and 10 say what stays out) and its decision 13 and
  `docs/architecture/memory-and-world-state.md`'s derived-age row (decision 6: a stated age with
  its as-of date **is** stored; today's age never is).
- **Implemented by:** [Plan 0065](../plans/open/0065-cm3b-a-channel-neutral-writer-core.md) (the
  writer core, tranche A of CM-3b). Tranche B (spoken capture of third parties, reported facts, the
  behaviour of the disclosure rule, perceptual candidates) is planned after Step 0.

## Context

CM-3a stores the owner's own tastes, as `personal` literal facts, through one writer
(`memory_writer.promote`) reached by one channel (the spoken dialogue). The roadmap's CM-3b and
Step 0 ask for more: the household itself (children, a partner, pets), places with validity,
facts reported by someone else, a disclosure rule, the first SECURITY datum, and an initial load
that must go through *the same writer* as the conversation (Plan 0050, non-goals, rule 1).

What the audit and the review verified in code (`feat/0063-cm3a-memory-dialogue`, 2026-10-16):

1. `assert_entity_relation` cannot take a visibility, a sensitivity, a confirmer or a validity
   range; the `confirmed_by_entity_id`, `confirmed_at`, `valid_from` and `valid_to` columns exist on
   `entity_relations_v4` (`migration_004_relational_v4.sql`) and nobody writes the first two.
   `assert_literal_fact` can. **Neither V4 table has a column for who asserted a fact or through
   which channel**; only `memory_candidates` does.
2. `memory_candidates` holds literals only: no relation target, no validity, no origin other than
   voice (`migration_009`); `promote` writes `personal`/`normal` literals and only opposes
   `likes`/`dislikes`.
3. All five personal-memory capabilities accept only the `personal` visibility and
   `target_person_id == actor.person_id` (`cognition/authorization.py`); `forget` also accepts
   `private` and `temporary`. A child, a partner or a pet as subject is **denied by design**, and so
   is a `household`-visibility fact (the default of `child_of`, `birth_date` and `likes`). The
   policy is pure and its request carries only `target_person_id`: it cannot know that a subject is
   the owner's child.
4. The household reader returns only rows whose stored classification equals the registry default
   (`memory/policy_gated_v4_reader.py`); a writer that stored `personal` would be invisible to it.
5. The registry has no `species`, no stated age and no disclosure or SECURITY predicate;
   `entities` is `UNIQUE(name, type)` and `upsert_entity` merges by folded name, so two third
   parties with one name collide; there is no column for a disambiguating key.
6. Two other writers touch V4 directly: `personal_setup` (owner and children by name) and the legacy
   migration (`legacy_v4_migration`), which resolves predicates through the registry.
7. The longitudinal benchmark's `provenance_attribution` scenario is marked `personal` but needs
   two identified people, and it is the **only** scenario with `expected_provenance`, which feeds a
   gate of the personal stage.

## Decision

### 0. The frame that governs the rest (Pipec, 2026-10-16)

In the `personal` profile, **when the firewall attributes the turn to the owner** (face and voice
of the same person on that clip, no second face, no token, ADR 0021 decision 3) or when a channel
authorized by Step 0 (the import) carries it, **everything said is said by the owner about the
owner's world**: the data belongs to the owner. Anything else is ordinary conversation and stores
nothing. Every first-person possessive («mi novia», «mi hija», «mi perro», «mi casa») is anchored
to the owner. A fact about a household member is stored as `household` data with the owner as
asserter and confirmer; the owner's own facts stay `personal`. Examples: «te presento a mi novia»
is the owner's partner; «mi hija tiene 7 años» means the owner has a daughter and her age, as
stated, is 7.

A reference by relationship resolves **only on what V4 stores**: `child_of`, `partner_of`, `pet_of`;
the daughter/son distinction is not stored, so «mi hija» does not by itself identify a child. It
resolves to the owner's household entity of that relationship when exactly one exists; when none
exists the capture proposes creating it and asks for the name if it was not given; when several
exist (or the gender is not stored) it asks which; in doubt it discards. **The confirmation always
names the resolved entity** («¿Guardo que {nombre} tiene 7 años?»), so a wrong resolution cannot be
saved silently. That resolution belongs to the spoken capture (tranche B); this ADR and Plan 0065
provide the rules and the writer it will call. Decisions 1 to 11 are the consequences, not
exceptions.

### 1. Who the owner may write about (profile `personal`)

A closed set: the owner's **children, partner and pets**. Anyone else named (friends, a boss,
neighbours) is outside the gate ("when in doubt, discard"); widening needs an ADR in the `family`
profile.

### 2. One writer for the conversation and the import

There is one canonical writer: `(subject, predicate, object-or-literal, asserter, channel,
confirmer)`. `promote` (the spoken confirmation, CM-3a) and the Step 0 import are two callers of
it; a future perceptual source would be a third. **The speaker never assigns the classification**:
the writer does, from the predicate and the subject (Plan 0050 rule 1, ADR 0021 decision 5).

*Confirmed by Pipec, 2026-10-16 — where the asserter and the channel live.* V4 has no column for them
(Context 1). Recommendation: **migration 010, additive** (`ALTER TABLE … ADD COLUMN
asserted_by_entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL` and `ADD COLUMN channel
TEXT` on both V4 tables; SQLite needs no table rebuild for that). It gives the provenance the
benchmark's `provenance_accuracy` gate measures. The alternative, "check the asserter at write time
and log the channel, store neither", keeps the schema but makes the gate unmeasurable.

Two writers remain outside it — `personal_setup` and the legacy migration — as documented
exceptions that the Step 0 ADR decides; a guard fixes who may call the repository's `assert_*`.

### 3. A household capability pair

New capabilities `propose_household_memory` and `confirm_household_memory`: the owner only, the
`household` visibility, `strong` assurance (face and voice of the same person on the turn, never a
token). They are separate from the five personal ones, whose rule (own data only) is unchanged.
Because the policy is pure, the request gains a closed `subject_relation` (`owner`, `child`,
`partner`, `pet`), **classified by the caller before any read** (ADR 0019 §6.2); the pair allows
only `child` and `pet` for literals and `child`, `partner` and `pet` for relations. Reading stays
through the existing policy-gated reader, which already serves `household` facts. The data of a
child or a pet belongs to the owner **as guardian**: the minor neither speaks for nor confirms their
own data in the `personal` profile.

### 4. Other adults

For a partner (or any other adult) the owner may write **only the name and the relationship**.
Their birth date, tastes, health or anything private waits for the `family` profile, where that
person is enrolled and decides (ADR 0006: an owner does not inherit another adult's private data).
The writer refuses a literal whose subject is the partner (`not_household_member`).

### 5. Facts reported by another person

A fact reported by a person other than the owner (a visitor, or «X me dijo…») is **not written**
in the `personal` profile. The benchmark scenario `provenance_attribution` needs two identified
people and **stays in the `family` scope**; so that the personal stage keeps a provenance
denominator, dataset v3 **adds one personal-scope provenance scenario** (the owner states a fact; a
later recall must name `subject=owner, assertor=owner, source=conversation`). No gate moves.
*Confirmed by Pipec, 2026-10-16.* The writer keeps one invariant, with a test: nobody but the subject writes into
the subject's `personal` memory.

### 6. Validity and dates

`lives_in` and `works_at` (the `temporal` predicates) take `valid_from` = the spoken date when
there is one, else the date of the assertion; the previous row is closed **at that `valid_from`**
(not at `now`). A row given an explicit `valid_to` is stored as history (lifecycle `expired`),
never closes the current row, and may have no `valid_from`. Dates are ISO `YYYY-MM-DD`
(`YYYY-MM` when only the month was spoken).

A date of birth is stored only as a **full ISO date** (a year alone is not stored; the robot asks
for the full date). **A stated age is stored** (Pipec, 2026-10-16: «mi hija tiene 7 años» is
kept) as the predicate `stated_age`, a single current value **with its as-of date** (the assertion
date, in UTC): «7, as of 2026-10-16». The age shown later is derived from it (the stated age plus
the whole years elapsed) and is **approximate by up to a year** (the birthday is unknown); a
`birth_date`, when known, **always** supersedes a `stated_age`, whatever their order. Today's age is
never persisted. The helper that derives it has no consumer before CM-5 and is not written now.

### 7. Entities

Never merge a third party by name alone. In tranche A a third party whose folded `(name, type)`
already exists is **not created** (`AmbiguousEntityError`); the import key is stored in the
entity's `attributes["import_key"]` so a re-run is idempotent. Two third parties with one name
would need a migration that rebuilds `entities` without `UNIQUE(name, type)` (eight tables
reference it): that is decided in the Step 0 ADR, not here. A pet's species is the literal
predicate `species` (single, current).

### 8. The disclosure rule

A new predicate in the registry (`private_topic`) states «do not mention X in front of visitors»:
the audience is fixed as "any other person present". This ADR and Plan 0065 add the **predicate and
its classification only**; the behaviour needs CM-5 (retrieval filtering) and the "are you with
someone?" escalation of Step 0, so nothing consumes it yet. Open question for CM-5: a topic the
owner marks private may be medical or financial, and `personal`/`normal` does not say so. The
benchmark scenario `sensitive_preference_lifecycle` keeps its meaning (a new predicate, not a
moved goalpost).

### 9. The first SECURITY datum

The first datum is an **alarm or gate code** (`access_code`, no Spanish alias, so the legacy
migration cannot route a legacy fact into it). Tests and the hardware acceptance use an invented
value and record outcomes only. The predicate and its `security` sensitivity (already `strong` in
the policy) are registered, but **the repository refuses to store a value whose predicate defaults
to `security`** (the refusal is in `assert_literal_fact` and `assert_entity_relation`, so no writer
can bypass it) until the Step 0 ADR decides storage at rest (plain SQLite, per-value encryption or
reference only; backups, `secure_delete`, `reset-db`). Reading it is CM-5.

### 10. Negations and the spoken capture of third parties

A negation («no tenemos gato») is never persisted. The spoken capture of a third party (names by
Whisper, grouped offers, a date parser for spoken dates, relation-target resolution above, a
migration of `memory_candidates`) is tranche B, after Step 0: names are fragile in the
speech-to-text and each candidate costs 30 to 60 s of extraction on the shared laptop.

### 11. What does not change

The firewall (face **and** voice of the same person on that turn's clip, never a token), the
no-oracle rule, the closed answer that repeats the value, the audit-before-effect rule, and the
fact that a value never reaches a log, `llm_response` or the history. **Two consequences are
accepted and written down** rather than hidden: a household read of `medical` or `location` data
must require `strong` before any reader serves it (CM-5), because the household read today asks
`basic` plus a consent the face alone gives; and a child's tastes stored as `household`/`normal`
are readable by any adult once the `family` profile exists.

## Alternatives considered

- **Third parties as `personal` facts of the owner.** Rewrites the household reader (Context 4) and
  loses the "household" meaning; rejected.
- **Any named person.** Opens the memory to friends and neighbours without their consent; rejected
  for the `personal` profile.
- **Store the partner's facts as «according to the owner».** A private fact of another adult would
  live in the database without that adult seeing or confirming it; rejected until `family`.
- **Do not store a stated age; store a birth-date range derived from it.** Keeps "age is derived"
  but invents a date nobody said and still goes stale; rejected in favour of the stated value with
  its as-of date.
- **Move the disclosure scenario into `likes`/`prefers`.** Moves the benchmark's goalposts: that
  scenario is the only one that tests derived copies (fact, episode, embedding, summary, cache).
- **Move `provenance_attribution` to `family` without a personal replacement.** Leaves the personal
  stage with no provenance denominator and CM-7 unreachable (a frozen gate cannot be relaxed).
- **Spoken capture before Step 0.** Costly and fragile (names, extraction time); the import by file
  resolves names without Whisper.

## Consequences

### Positive

The initial load and the conversation share one writer and one classification rule; the policy
change is explicit instead of a patch; the minors and the other adults are protected by default;
the benchmark's contradictions are surfaced and solved without relaxing a gate.

### Negative

A second pair of capabilities and a larger policy matrix; a migration (010) if Pipec accepts the
provenance columns; the owner cannot yet tell the robot about a friend; two homonymous third
parties are impossible until Step 0; the SECURITY datum cannot be stored until the Step 0 ADR.
Known gaps, not solved here: introducing a person with them in frame is vetoed by the two-face rule
(ADR 0016), so the introduction cannot be captured in their presence; `partner_of` is not temporal,
so a second partner accumulates and a break-up is a CM-6 matter; a child's data held by the
guardian becomes another adult's data when the child turns 18.

## Test consequences

Matrix tests for the household pair (owner `strong` allowed for `child`/`pet` literals and
`child`/`partner`/`pet` relations; owner without voice, token, visitor, other adult, minor,
`partner` literals, `owner` subject denied; the five personal capabilities unchanged); the writer
from two channels produces the same classification; a third party with a repeated folded name is
never created; `species`, `stated_age` and the validity rules; the repository refuses a `security`
value; the invariant of decision 5; dataset v3 loads and the driver reports honestly what it does
not support.

## Docs to update

With **Accepted**: ADR 0019 §2 and ADR 0021 decisions 4, 5 and 13 (cross-references), the memory
map and the roadmap rows for CM-3b (tranches A and B), `identity-and-access.md` (the household
pair), `memory-and-world-state.md` (the writer, validity, the derived-age row, the disclosure and
SECURITY predicates), `current-state.md` and the plan index.

## Review

Revisit when Step 0 decides the levels per channel and the storage at rest, when the `family`
profile enrolls a second adult, when CM-5 filters retrieval, or if a measured cost on the homelab
changes the economics of the spoken capture.

## Review record

**Independent review, 2026-10-16** (a read-only reviewer that had not written this ADR, against the
code and ADRs 0006, 0009, 0016, 0019, 0020 and 0021). Findings folded in: the frame of decision 0
presumed the speaker was always the owner (now conditional on the firewall); resolving «mi hija»
against the household could attribute a child's data to the wrong child (now only on stored
relations, always named in the confirmation); internal contradictions between decisions 0, 2 and 5;
storing a stated age amended undeclared rules (now declared, with the birth-date precedence and the
±1-year caveat); V4 has no column for the asserter and the channel (now a decision for Pipec); the
"one writer" is not exclusive (documented exceptions and a guard) and a Spanish alias could route a
legacy fact into the SECURITY predicate (no alias, refusal in the repository); homonymous third
parties are impossible without a migration (decision 7); moving `provenance_attribution` alone
would have made the personal stage unpassable (decision 5); the policy cannot know a subject is the
owner's child (decision 3's `subject_relation`); missing consequences are now stated.

## Follow-up

- [Plan 0065](../plans/open/0065-cm3b-a-channel-neutral-writer-core.md) — tranche A, the writer core.
- Tranche B of CM-3b — after Step 0 (spoken capture, reported facts, disclosure behaviour,
  perceptual candidates, benchmark restart seam).
- The next free ADR number is 0023.
