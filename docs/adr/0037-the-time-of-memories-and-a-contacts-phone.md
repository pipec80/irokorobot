# 0037 — The time of memories and the alta by voice: when it happened, what is pending, and every loaded datum reachable

- **Status:** Proposed (2026-11-11). Written from the research of the memory engine (kept in the
  ignored `project-history/`), the code read that day and Pipec's four decisions of 2026-11-11 (see
  *Pipec's decisions and where they land*). It becomes `Accepted` when the plan that implements it
  closes (plan 0082 or the plans it is split into). Decisions 1 and 5 implemented by Plan 0082 and
  accepted on real hardware on 2026-11-12, 9 of 9 cases (*Implemented in Plan 0082* below).
- **Date:** 2026-11-11
- **Builds on:** [ADR 0024](0024-seed-load-senses-secrets-and-channels.md) (the contacts table),
  [ADR 0027](0027-conversation-record-and-the-diary.md) (the record and the diary),
  [ADR 0028](0028-recall-what-the-owner-told.md) (recall),
  [ADR 0029](0029-it-knows-who-is-listening.md) (reads by level and the camera check),
  [ADR 0031](0031-the-memory-engine-boundary.md) (the engine's contract, decision 5: the four
  meanings of time).
- **Amends:** [ADR 0024](0024-seed-load-senses-secrets-and-channels.md) decision 5 («nothing reads
  the table by voice»: the owner may now hear a contact's phone, decision 1);
  [ADR 0029](0029-it-knows-who-is-listening.md) decision 1 (the contacts and the rest of the profile join the closed
  map of levels, decision 5);
  [ADR 0031](0031-the-memory-engine-boundary.md) decision 5 (the occurred time is now stored when
  the owner says it, decision 3).
- **Delivers:** row 7 of the
  [path to the finish line](../roadmap/cognitive-roadmap.md#closing-path-of-conversational-memory),
  «the memory the MVP still lacks».

## Context

1. **A contact's phone is loaded and never read.** The alta stores each contact in `care_contacts`
   (ADR 0024 decision 5): a closed role, a relationship label («hija», «vecina»), one or two phones,
   classified `personal`/`private` (`location` when the contact holds a key). ADR 0024 left the
   reader to «a future care ADR». The owner's own question, «¿tienes el teléfono de mi hijo?», has
   no answer today.
2. **What is said about the future is kept and never used.** «Mañana te cuento», «el jueves voy al
   médico» enter the record and, when the owner's face and voice are verified on the turn, the
   diary (ADR 0027). Nothing marks them as pending, so the robot never asks about them. The
   research names this *prospective memory*, and Pipec asked for a greeting that picks one up
   («¿cómo te fue ayer en el cine?», 2026-11-10).
3. **The occurred time is not stored.** ADR 0031 decision 5 fixed four meanings of time (said,
   recorded, occurred, valid) and stored the occurred time only «when a use case needs it». Plan 0080
   decided the minimum: «¿cuándo fui a la playa?» answers the day it was **told**, with «No tengo
   registrado cuándo fue». The research marks it as an open gap (LRN-08).
4. **Two of the three need the same reader.** `cognition/spoken_dates.py` resolves past windows
   («ayer», «el sábado», «la semana pasada») against the household day. The occurred time needs it
   for told past events; pending topics need its future mirror («mañana», «el jueves», «la próxima
   semana»). One reader for both directions is one module, one corpus and one set of tests.
5. **The generic prompt reads no household store** (Plan 0077, guardrails): a turn routed to the
   model by mistake can invent and cannot reveal. Anything here that speaks a stored value goes
   through the controller and its fixed templates, never through the generic prompt.

6. **More of the alta is stored and never read.** The seed data pool marks «the rest of the profile»
   (partner, devices, mobility, hearing, vision, dwelling, access note, lives alone, health coverage)
   as planned with no plan. Pipec (2026-11-11): what the alta loads must stay available to his
   questions, the way «¿qué sabes de mí?» is, never disconnected.

## Decision

### 1. A contact's phone is read by voice at the sensitive level, to the owner only

- The owner's own question about **their own** contacts («¿tienes el teléfono de mi hijo?», «¿cuál
  es el número de mi doctor?», «dame el teléfono de mi vecina») is a closed controller branch, like
  the sensitive read of ADR 0029. It matches the contact by relationship label, by role («mi
  contacto de emergencia», «mi doctor»), by call order («mi contacto 1», «mi primer contacto») and
  by name when the owner says one; «¿quién tiene llave de mi casa?» reads the key holders.
- «Llama a mi contacto 1» is answered honestly: the robot cannot call yet (no telephony, ADR 0024)
  and says so with the fixed sentence, followed by the contact's name and phone at the same level,
  so the owner can call. The call itself is a later capability (an alert, a telephony line).
- **Level: sensitive** (*Pipec, 2026-11-11*): the owner's face (`basic`) and no other face in
  view, the camera check of ADR 0029 decision 3 unchanged: two faces hear «Te lo digo cuando
  estemos solos.»; anyone else, or no face, the generic denial. The datum joins the closed map of
  ADR 0029 decision 1 (the map stays explicit, never derived from the stored sensitivity).
- The answer is a fixed template that says the relationship and the number grouped so the voice
  reads it digit by digit; two contacts that match are both said; none says «No tengo ese teléfono
  guardado.». The exact wording is the plan's.
- The record keeps a marker instead of the number, as ADR 0029 does for a sensitive answer.
- Nothing calls a phone and no alert is built: reading is not dialling (ADR 0024, «capture now,
  build later»). Who else may read the table (a carer, an alert) stays with the future care ADR.

### 2. Pending topics: kept from the owner's own verified words, picked up once by a fixed sentence

- **Source.** Only the turns that already feed the diary (ADR 0027: the owner's face and a verified
  voice on that turn, the record's consent). A visitor's «mañana vuelvo» is never a pending topic.
- **Detection.** A deterministic grammar finds a future announcement in the owner's words (a future
  marker resolved by the shared reader, decision 4, plus a first-person verb or «te cuento»). The
  local model only **names the topic** in two or three words («el médico», «el cine»), with the
  extractor's rules (it sees the owner's words only, its output is short data, never a sentence to
  speak); a topic it cannot name is not kept.
- **Storage.** One row per topic, owned by the owner: the topic, the due day (the household day the
  marker resolves to), the day it was said, the source record, a state (`open`, `asked`, `expired`)
  and a classification assigned by the writer. It is deleted in cascade with its record and expires
  two days after its due day whether asked or not (it is a reminder of a conversation, not a diary).
- **The follow-up** (*Pipec, 2026-11-11*): on the first face-identified turn of a new session
  (empty continuity), at most one open topic due from two days ago to today is picked up by a
  **fixed sentence of the controller**, spoken after the model's own reply, the way the memory offer
  is (ADR 0021 decision 9): «¿Cómo te fue {día} con {tema}?». It is never put in the generic
  prompt. An open memory offer on the same turn wins and the topic waits. A topic is asked once,
  then `asked`; what the owner answers is ordinary conversation.
- **Health** (*Pipec, 2026-11-11*): a topic whose words fall in the sensitive lexicon of ADR 0029
  (a doctor, an exam, a medicine) is classified sensitive and picked up **only when the owner's face
  is alone in view**; with anyone else in view it is not mentioned and stays open.

### 3. The occurred time is stored when the owner says it, and the answer says which time it is

- When a turn that feeds the diary tells a past event with a time the shared reader resolves («el
  sábado fui a la playa», «en 2015 viví en Santiago», «el verano pasado»), its recall unit gets an
  **occurred interval** (a start and an end day: a day, a week, a month, a season or a year) next to
  `said_at`. It is never inferred from anything the owner did not say (ADR 0031 decision 5).
- «¿Cuándo fui a la playa?» answers with the occurred interval when the found unit has one
  («Fuiste el sábado 8 de noviembre.», «Fue en 2015.»), and with today's told-day answer when it does
  not. An answer always names which time it reports.
- A recall window («¿qué hice el sábado?») matches a unit by its occurred interval when it has one,
  and by `said_at` otherwise. The plan measures that a told-yesterday story about last year is no
  longer returned for «¿qué hice ayer?».

### 4. One reader of spoken time, past and future

`cognition/spoken_dates.py` gains the future words («mañana», «pasado mañana», «el jueves», «la
próxima semana», «el próximo mes») and the year and season forms, resolved against the household
day and time zone (`HOUSEHOLD_TIMEZONE`). Every consumer (recall windows, the occurred interval,
pending topics) uses it; no second date parser is written. It stays pure and closed: a phrase it
does not know is no time, never a guess.

### 5. Nothing loaded at the alta is unreachable by voice (*Pipec, 2026-11-11*)

Pipec's rule: a datum loaded at the alta must be available to the owner's questions, never stored
and disconnected. Each field of the [seed data pool](../architecture/seed-data-pool.md) gets a
voice read by a fixed template at its level, or is listed with the reason it is not read:

| Fields | Read by | Level |
|---|---|---|
| Name, form, tastes | The card and «¿qué sabes de mí?» (exists, ADR 0026) | Face |
| Relatives, children with their side, pets | The relatives templates (exists, ADR 0028, Plan 0080) | Face |
| Health, address, emergency facility, birthdays; who knows a code, where a document is | The sensitive read (exists, ADR 0029) | Sensitive; security |
| Contacts: phone, role, call order, key holders | Decision 1 | Sensitive (`location` for a key) |
| Partner | The relatives templates, extended | Face |
| Devices and implants, mobility, hearing, vision, health coverage | The sensitive read, extended | Sensitive |
| Dwelling, floor, lift, how to get in | The sensitive read, extended | Sensitive |
| Lives alone | The sensitive read, extended | Security (with the address it is a burglar's map, ADR 0024) |
| `withhold_from`, `private_topic`, a contact's `may_receive_health_info` and `may_view_activity` | Not read aloud: they are rules the robot obeys, not answers (the family stage, ADR 0029 decision 6) | — |
| The commissioning record and section statuses | Not read by voice: `iroko-admin status` | PIN |
| A child's `stated_age` and tastes; a pet's `species`, `stated_age` and tastes | Not read yet: a household member's own data, read in the family stage (P3) (*Pipec, 2026-11-12, Plan 0082 D-13*) | — |

A test walks the registry of pool predicates and fails when a field has neither a read nor a
listed reason, so a field added later cannot be stored disconnected.

### 6. Switches and order

Each part sits behind its own default-off switch that needs `MEMORY_ENABLED` (the names are the
plan's); off, every route, prompt and reply is byte-identical. The parts are independent and may be
delivered by separate plans in this order: the alta's data reachable (decisions 1 and 5: read-only,
templates), the shared reader and the occurred time (it changes recall), the pending topics (a new
table and the greeting).

## Pipec's decisions and where they land

| # | Decision | Date | Where |
|---|---|---|---|
| 1 | A contact's phone at the sensitive level: the face and no other face in view | 2026-11-11 | Decision 1 |
| 2 | A pending topic is picked up by a fixed sentence plus a topic the local model names at capture | 2026-11-11 | Decision 2 |
| 3 | A health topic is kept as sensitive and picked up only when the owner is alone in view | 2026-11-11 | Decision 2 |
| 4 | The occurred time enters this ADR, with the same reader as the future | 2026-11-11 | Decisions 3 and 4 |
| 5 | Nothing loaded at the alta stays disconnected: every datum is reachable by voice or listed with a reason; «mi contacto 1» works | 2026-11-11 | Decisions 1 and 5 |

The author's calls, for Pipec's review: one follow-up per new session, an open offer winning over
it; two days of grace after the due day; the topic deleted with its record; the occurred time as a
day interval; the order of decision 5.

## Not decided here

| Subject | Owner |
|---|---|
| Who besides the owner reads the contacts (a carer, an alert) and calling a phone | The future care ADR (ADR 0024) |
| Correcting or forgetting a pending topic or an occurred time by voice | ADR 0032 (block C) |
| Pending topics told by someone other than the owner | The family stage (P3) |
| A reminder at a time of day, or one not tied to a greeting | Not planned (P2.3, bounded initiative) |
| The exact templates, the grammar's word lists and the switch names | The implementing plan |

## Alternatives considered

- **The phone at the normal level (face only).** Rejected by Pipec: a phone number of a family
  member is as private as the owner's address, which is sensitive.
- **The phone at the security level (face and voice).** Rejected: the voice verifies on about one
  turn in three on the laptop (Plan 0075), so the owner would rarely hear it.
- **The topic in the generic prompt, phrased by the model.** Rejected by Pipec: it puts household
  data in the prompt that reads none (Plan 0077) and the 3B model's wording is unpredictable.
- **Quoting the owner's own sentence back.** Rejected: long and odd to hear («Me contaste que el
  jueves ibas al médico…»); a two-word topic in a fixed sentence reads naturally.
- **Inferring the occurred time from context.** Rejected: ADR 0031 decision 5 forbids an occurred
  time nobody said.

## Consequences

### Positive

- The three gaps of row 7 close with one shared reader of time and no new model call in the turn.
- Nothing household reaches the generic prompt; every stored value is spoken by a fixed template.
- The answer to «¿cuándo fui…?» finally reports when it happened, when the owner said it.

### Negative

- A new table for pending topics and a migration for the occurred interval on recall units.
- A topic is named by the local model at capture, in the background: a wrong topic is possible and
  is spoken once («¿cómo te fue con el cine?» after a theatre); it is never treated as a fact.
- Only the turns that feed the diary yield topics and occurred times, so the voice coverage limit
  (about one turn in three on the laptop) limits them too, until the body is recalibrated.

## Test consequences

- The shared reader: a corpus of past and future phrases with their resolved days, across a year
  change and the household time zone; an unknown phrase yields nothing.
- The phone: the owner alone hears it; two faces hear the fixed sentence; a stranger or no face
  hears the generic denial; the record keeps a marker; a non-owner's contact is never read.
- Pending topics: a visitor's future sentence is not kept; a topic is asked once on a new session
  and never in the generic prompt; a health topic is not mentioned with a second face; a topic
  expires two days after its due day and is deleted with its record.
- The occurred time: «¿cuándo fui…?» says the occurred interval when it exists and the told day
  otherwise; «¿qué hice ayer?» no longer returns a story about last year told yesterday.

## Implemented in Plan 0082 (decisions 1 and 5)

Implemented on 2026-11-12 behind the default-off `ALTA_READ_ENABLED` (needs `MEMORY_ENABLED` and
`SENSITIVE_READ_ENABLED`); accepted on real hardware the same day, 9 of 9 cases
([record](../evals/0082-alta-by-voice-acceptance.md)); the ADR stays `Proposed` until decisions 2 to
4 close (Plans 0083 and 0084). The builder's calls, recorded in
[Plan 0082](../plans/completed/0082-the-whole-alta-by-voice.md):

- **One reader.** The contacts and the rest of the profile join the sensitive read of ADR 0029: same
  order, same camera check, same marker; one own-read authorization (`_authorized`) serves the
  predicates and the contacts (sensitivity `private` and `location`, the two the table holds).
- **Own contacts only.** A contact question is the owner's when the words after the phrase open
  with «mi» or «mis» or name a call order; a name alone («llama a Canary») and someone else's
  phone («los bomberos») stay ordinary conversation, decided before any check and with nothing
  read (a refusal would confirm the name, Plan 0077).
- **Selection.** By call order («contacto 1», «contacto uno», «primer contacto»), role words,
  relationship label or name; the best match wins (people who share a surname are not all
  selected); «mis contactos» reads them all; at most three people, one sentence each.
- **The phone** is said in digit words, grouped by four from the right, after «más»; «llama a…»
  opens with «Todavía no puedo hacer llamadas.».
- **Reach.** `memory/alta_reach.py` and `tests/unit/test_alta_reach.py` implement the last paragraph
  of decision 5 over the fields the importer can load and the fields of a contact row.

## Docs to update

The ADR index; the roadmap (row 7); `current-state.md` and the architecture diagrams when the plan
closes; ADR 0024 decision 5, ADR 0029 decision 1 and ADR 0031 decision 5 (an *Amended by ADR 0037*
note each, when this ADR is accepted).
