# 0029 — It knows who is listening: read the owner's sensitive data by voice, by levels, and never keep a spoken secret

- **Status:** Proposed (2026-11-04), amended 2026-11-05. Every decision below was confirmed by
  Pipec in the design session of 2026-11-04 (decisions 1 to 7 of *Pipec's decisions*); the
  pre-plan audit of 2026-11-05 found five gaps against the code on `main` (`443bbaf`) and Pipec
  closed them (decisions 8 to 12, written into decisions 1, 4, 5 and 7 and marked *Amended
  2026-11-05*). In the same day's review of the plan Pipec simplified the audience check and the
  secret rule to cut friction, and settled the remaining details (decisions 13 to 21): decision 3
  is rewritten, and decisions 4, 5 and 6 carry notes marked *Amended 2026-11-05 (review)*. It
  becomes `Accepted` when the plan that implements it closes with its hardware acceptance.
- **Date:** 2026-11-04
- **Builds on:** [ADR 0016](0016-face-and-voice-identity-fusion.md),
  [ADR 0019](0019-personal-memory-capabilities.md),
  [ADR 0020](0020-authorized-actor-in-the-conversation.md),
  [ADR 0024](0024-seed-load-senses-secrets-and-channels.md),
  [ADR 0026](0026-owner-profile-card-and-the-read-side-of-memory.md),
  [ADR 0027](0027-conversation-record-and-the-diary.md),
  [ADR 0028](0028-recall-what-the-owner-told.md)
- **Amends:** [ADR 0019](0019-personal-memory-capabilities.md) §3 (the owner's own `medical` and
  `location` data are read at `basic` when no other face is in view, decisions 1 and 3);
  [ADR 0026](0026-owner-profile-card-and-the-read-side-of-memory.md) decisions 6 and 9 (the replay
  choice is made, decision 2; CM-3b tranche B is emptied and the CM-7 scenarios move, decision 6);
  [ADR 0027](0027-conversation-record-and-the-diary.md) decision 1 (a turn that carries a secret is
  kept as a marker, not as text, decision 5; a sensitive answer is kept as a marker, decision 4).
- **Delivers:** step 3 of the
  [closing path of conversational memory](../roadmap/cognitive-roadmap.md#closing-path-of-conversational-memory),
  **block B, «it knows who is listening»**, in one plan (the next free number, 0079).

## Context

Block B was written as one concept, the audience, with four pieces: the first sensitive read by
voice, the replay decision, «¿estás con alguien?», and CM-3b tranche B (`lives_in` and «no menciones
X» by voice). What holds today (verified in code on `main` at `53abcce`, 2026-11-04):

1. **The data are already there.** The alta (Phase 0, Plans 0070 to 0073) loads the owner's health
   (conditions, medications, rescue medication, allergies, blood type, anticoagulant, devices), home
   (address, preferred emergency facility, dwelling), the birth dates of the owner and the children,
   the relatives, the people to keep out (`withhold_from`), the topics not to touch (`private_topic`)
   and who knows a secret (`secret_holder`, never the value: ADR 0024 decision 4). Nothing of it is
   read by voice except the children, the profile card and, since Plan 0078, the `normal` relatives.
2. **The policy is already there and asks too much for a question.** ADR 0019 §3 raises every
   personal-memory read of `medical`, `location` and `biometric` data to `strong` (the owner's face
   **and** a verified voice on that turn's clip); `security` is `strong` for every action (ADR 0016
   §3). The owner's voice almost never verifies on a question: 0 of 7 questions in Plan 0075, and
   every recall question of 1.6–2.6 s stayed `unknown` in Plan 0078's acceptance. With the rule as it
   stands the robot would refuse the owner almost every sensitive answer.
3. **What the voice adds.** Against a prepared attack it adds little: a photograph plus a recording
   of the exact question passed 6 of 8 replay probes (ADR 0016 §9). In the home it covers one real
   case: the owner's face is in view and **someone else, off camera, asks**. The face says who is
   there; the voice says who is asking. A second face in view already suspends the session
   (ADR 0020 §4); a second voice with no face is not detected.
4. **A secret said in conversation is kept on disk.** ADR 0024 decision 4 says the value of a secret
   is never stored, and the alta honours it. But the conversation record keeps every verified turn's
   text for up to 365 days (ADR 0027), the recall index keeps it as a unit marked `security`
   (unreadable by voice, ADR 0028) and the diary summary may repeat it. «Mi clave del banco es 1234»
   is therefore readable by anyone with the disk, and with the owner's PIN through `iroko-admin
   conversations export`.
5. **Phase 0 already covers what block B was going to learn by voice.** The address is loaded at the
   alta and corrected with `iroko-admin` (a move is rare). `private_topic` and `withhold_from` are
   loaded at the alta too, and nothing in the personal stage discloses the owner's data to a visitor:
   the generic prompt reads no household store (Plan 0077), every personal read answers only the
   face-identified owner, and a second face suspends the session. «No menciones X» matters when
   several people share the robot, which is the family stage.
6. **The core CM-7 scenario is about «no menciones X».** `sensitive_preference_lifecycle` (27 of the
   benchmark's 90 steps: propose, restart, recall, correct, restart, forget, a guest asks) feeds four
   of the five categories CM-7 requires. `domicile_temporal_validity` asks for `lives_in` by voice.

## Decision

### 1. Reads by level: the face for the owner's own sensitive data, face and voice for security

| Level | Data (the owner's own, loaded at the alta) | Needs |
|---|---|---|
| **Sensitive** | Health: `health_condition`, `medication`, `rescue_medication`, `allergic_to`, `blood_type`, `takes_anticoagulant`. Home: `home_address`, `preferred_emergency_facility`. Birthdays: `birth_date` of the owner and of the children (the alta keeps the other relatives as name and relationship only, so it holds no birth date for them) | The owner's face (`basic`) **and** no other face in view (decision 3) |
| **Security** | `secret_holder` (who knows a code), `document_location` (where a document is) | Face **and** a verified voice on that turn (`strong`, unchanged) **and** no other face in view |

This amends ADR 0019 §3 for one capability and one subject: **reading** the owner's **own**
`medical` and `location` facts. `propose`, `confirm`, `correct` and `forget` keep their
assurance; `biometric` stays at `strong`; reading anyone else's sensitive data is not opened.
`child_data` (the children's birth dates) stays at the face, as ADR 0016 §1 already accepts.

*Amended 2026-11-05.* The level of a datum is the table above, kept as an explicit closed map from
predicate to level in one place; it is never derived from the stored sensitivity. The two do not
line up: `birth_date` has the registry default `child_data`, while the canonical writer stores the
owner's own birthday as `personal`/`private` (a child's stays `household`/`child_data`), and
`implanted_device`, `mobility`, `hearing` and `vision` are `medical` without being in the closed
list (decision 5 of *Pipec's decisions*). *(Corrected in the plan review of 2026-11-05: the first
version said the owner's birthday carries `child_data`; the request uses the stored labels.)*

*Amended 2026-11-05 (consent).* Reading personal memory has `consent_applies` (ADR 0019 §3): a
`medical` or `location` datum is read only with the consent `granted`, and today no read passes
one. For the owner's **own** data of this table, the consent is the alta: when the owner's
commissioning record is closed (ADR 0024; the owner reviewed the load and answered `SI`), the read
carries `granted`; with no closed alta it carries `missing` and the policy denies it. No new
consent, no migration, and the consent rule of the policy does not change (the assurance rule
does, above).

When the voice fails on a security question and the owner's face is recognized, the robot says one
fixed retry sentence asking for the question again in a full sentence (the pattern of ADR 0021
decision 9, amended by Plan 0068) and evaluates the next turn. *(Review: no state is kept for the retry, as decision 3 keeps none. Every
security question whose voice fails, with the owner's face alone in view, hears the retry sentence;
the next turn is evaluated afresh, and no count of failures exists.)*

### 2. Replay: accepted for the home, and a second factor later only for security

The residual risk of ADR 0016 §9 (a photograph plus a recording) is **accepted for the personal
stage in the home** and stated here: it can draw the owner's sensitive data, never a secret's value
(none is stored, decision 5). No liveness challenge is built. A fingerprint reader, or another
electronic factor, joins later as a second verifier **for the security level only**, through the
existing seam: it issues the same scoped `LOCAL_UNLOCK` grant the PIN issues (ADR 0020 decision 6),
so scopes, single use, expiry and the policy do not change. Its sensor needs its own ADR.

### 3. Who is listening: the camera, checked in silence on every answer

*Rewritten 2026-11-05 (review, decision 13).* The robot asks nothing. Before a sensitive or a
security answer it reads the face evidence of **that turn**, which the identity resolver already
produces (ADR 0016, ADR 0020):

| What the camera sees on that turn | The robot answers |
|---|---|
| Only the owner's face | The answer (the security level still needs the verified voice, decision 1) |
| Two or more faces (`veto_multiple_faces`) | «Te lo digo cuando estemos solos.» |
| Another enrolled person, an unknown face, or no face at all (the camera covered, facing a wall, too dark) | The existing generic denial |

Nothing is kept between turns: no audience flag, no pending question, no short-reply listening
mode. A camera that cannot see fails safe: without the owner's face the robot does not know it is
the owner, so it does not need to know whether the owner is alone. With two faces the resolver does
not match anyone (ADR 0016 vetoes before matching), so «Te lo digo cuando estemos solos.» is said
whoever is in view and whatever is stored; it reveals nothing.

The questions are a first-person grammar («¿qué remedios **tomo**?», «¿cuál es **mi**
dirección?»), so someone off camera who asks about the owner in the third person («¿qué remedios
toma?») does not match it and is not answered by this decision.

What the first version of this decision did, and why it changed: it asked a fixed «Es algo
privado. ¿Estás solo?» before the first sensitive answer of a conversation and held the question
for 60 s. Pipec found it a friction on the owner's own questions, the kind Plan 0077 removed from
ordinary conversation, for a case the camera already mostly covers. The residual risk it covered
is accepted (see *Consequences*). Answering **in company**, after a long spoken authorization that
verifies the owner's voice, needs the two-face veto changed and goes to ADR 0030 (decision 6).

### 4. The answers are fixed templates, and a recalled memory stays `normal`

Every answer of decision 1 is a fixed template of the controller, never the model, like the
relatives of ADR 0028 decision 9: «Tus medicamentos son …», «Tu grupo sanguíneo es …», «Tu
dirección es …», «El cumpleaños de Zeta es el 3 de marzo.», «Quien conoce la clave es …». Nothing
loaded answers «No tengo registrado eso.». The questions are a closed grammar in
`intent_resolution`, written with Pipec's real phrases and the speech-to-text slips of the corpus.
Anyone who is not the face-identified owner hears the existing generic denial, the same phrase
whatever is stored. The opt-in text log shows a fixed marker instead of the answer.

*Amended 2026-11-05.* The conversation record keeps the robot's reply as text (ADR 0027), so an
answer of this decision would copy the value into the record for up to 365 days and into
`iroko-admin conversations export`. The record keeps the owner's question as said and, in place
of the robot's answer, the fixed marker «[dato sensible leído]»; the diary therefore knows the
owner asked, never the value. The same holds for the security level. «Te lo digo cuando estemos
solos.» carries no value and is kept as said.

*Amended 2026-11-05 (review, decisions 16 to 19).*

- **Which reference is read.** `secret_holder` and `document_location` are free texts the owner
  wrote at the alta, several per owner. When the question names a word that one or more entries
  contain («¿quién conoce la clave del **banco**?»), only those entries are read; when none
  matches, all of them are read. An entry is read as written.
- **A child with no birth date.** The alta may hold a stated age instead of a date. A birthday
  question about that child answers «No tengo registrada su fecha.»; the age is not offered.
- **Values said aloud.** The template says a stored value the way a person says it, never its
  storage form: the blood type `O+` is «O positivo» (every value of the closed list has its
  spoken form), `takes_anticoagulant` is «Sí, tomas anticoagulante.», «No tomas anticoagulante.»
  or «No tengo claro si tomas anticoagulante.», a date is said with the spoken dates of
  Plan 0078.
- **The debug text log.** `LOG_CONVERSATION_TEXT` stays what it is: a debugging aid, off by
  default, console only, never written to a file; it shows what the speech-to-text heard, a secret
  included, because that is what it is for (Pipec found Whisper's errors with it). It is never on
  in production, and the operator manual says so. The spoken side keeps its marker, as above.

Recall (ADR 0028) keeps reading only `normal` units: a conversation unit marked `medical`,
`location` or `security` is never read back by voice. The security level is the alta's reference
(`secret_holder`, `document_location`), never a recalled sentence, which could hold the number.

### 5. A secret said in conversation is never kept

A turn whose words carry a **secret word** — `clave`, `contraseña`, `código`, `pin` (folded, whole
words) — is a closed branch of the controller:

- the model never receives it, and the robot answers a fixed «Las claves y los códigos no los
  guardo ni los repito.»;
- the conversation record keeps the turn with a fixed marker in place of its words
  («[dato de seguridad omitido]») and the robot's fixed reply, so the conversation keeps its shape;
- no recall unit, no candidate and no continuity entry is made from it, and the diary summarizes
  the marker, never the words.

The secret words are narrower than the security words of the recall classifier (Plan 0078 D-5),
which also lists `alarma`, `llave`, `llaves` and `portón`: those mark a sentence as `security` so
recall never reads it, but «dejé las llaves en la mesa» is no secret and keeps its ordinary turn.
A secret said without any secret word («el número del banco es…») is not caught; the classifier's
wider list still keeps it unreadable by voice. Units already stored with a secret word are found
by the same rule and deleted by the plan, with the owner's OK.

*Amended 2026-11-05 (order).* A question of the security grammar of decision 4 («¿quién conoce la
clave?», «¿quién sabe el código de la alarma?») carries a secret word and is a read, not a secret:
the closed grammar of decision 4 is evaluated **first**, and only a turn it does not match goes to
the secret branch. With `SENSITIVE_READ_ENABLED=false` that grammar does not exist, so the same
question is a secret turn and hears the fixed phrase. *(Review, decision 14: with the switch off
the question states no value and asks for none, so it is an ordinary turn, as today.)*

*Amended 2026-11-05 (one list).* The secret words are defined once, in a module that both the
cognitive core and the memory package may import (`cognition/` cannot import `server.memory`, an
architecture guard). The security words of the recall classifier are that set plus `alarma`,
`llave`, `llaves` and `portón`, derived from it rather than written twice. Known false positives,
accepted and pinned in the trap corpus: «código postal», «eso es clave» (Chilean for «important»),
«el pin de la chaqueta»; they hear the fixed phrase and leave a marker. *(Narrowed by the review
amendment below: only «código postal» with its number is still caught.)*

*Amended 2026-11-05 (review, decision 14): a value, not a mention.* As first written the rule
fired on any secret word, which is the mistake Plan 0077 removed from the household protection:
«hoy cambié la clave del wifi», «eso es clave», «el código del colegio cambió» would have cut the
conversation without holding any secret. The branch fires only when a turn **states** a secret's
value or **asks** for one:

- **States a value:** a secret word followed, in the same sentence, by a digit, a spoken number
  («uno dos tres cuatro») or a copula with a word after it («es», «son», «era»: «la contraseña es
  perro123»). The robot answers «Las claves y los códigos no los guardo ni los repito.» and the
  rest of this decision applies (no model, a marker, nothing kept).
- **Asks for a value:** a closed grammar of questions for the secret itself («¿cuál es mi clave
  …?», «dime la contraseña …», «¿me recuerdas el pin …?»). Same fixed answer: the robot holds no
  value, and the model must not invent one. «¿Quién conoce la clave?» is not this grammar: it is the
  security read of decision 4, evaluated first.
- **Anything else is an ordinary turn.** It reaches the model and is kept like any turn; it holds
  no value, and the recall classifier still marks it `security`, so it is never read back by voice.

Accepted false positive: a secret word followed by a copula that does not state a secret («la clave
es que llegues temprano»), and «mi código postal es …»; pinned in the trap corpus. *(Plan review,
2026-11-05, an author's call: the copula form applies to `clave` and `contraseña` only; `código` and
`pin` state a value only with a digit or a spoken number, so a developer's «el código es un
desastre» stays ordinary; and the asking form with «la»/«el» needs a named account — «¿cuál es la
clave del banco?» — so «¿cuál es la clave del éxito?» stays ordinary. The plan's D-2 holds the closed
lists.)* The same rule,
and nothing wider, decides what the cleanup below finds.

*Amended 2026-11-05 (what was kept before).* The record's text and the diary summaries can hold a
secret said before this rule existed, not only the recall units. One cleanup, run once with the
owner's PIN through `iroko-admin` (server stopped, ADR 0025): every stored turn whose words carry a
secret word has its words replaced by the fixed marker «[dato de seguridad omitido]», its recall
unit is deleted, and every diary summary of an affected conversation is deleted and its record set
back to pending, so the diary job writes it again from the redacted turns. It prints counts only (turns,
units, summaries), never a text, and writes one audit row with no household value. A dry run shows
the counts first; it applies only on the owner's `SI`.

*Amended 2026-11-05 (review, decision 20).* The cleanup serves only a database that recorded turns
before this rule; a new robot has none. Before it is built, the plan counts, on a read-only copy of
the owner's database and with the rule above, how many stored turns state a secret's value (counts
only, never a text). With none, the cleanup is not built and this paragraph lapses; with some, it is
built as written.

*Counted 2026-11-05, before the plan:* 57 stored turns, none states or asks for a secret's value
(no mention either), no recall unit and no diary summary holds one. **The cleanup is not built**;
the paragraph above lapses. The rule protects every turn from now on.

### 6. What leaves block B

| Piece | Where it goes | Why |
|---|---|---|
| `lives_in` by voice | **Only the alta and `iroko-admin`** | The address is loaded at the alta; a move is rare and is corrected with the owner's PIN; learning a location by voice opens a sensitive write path |
| «No menciones X» by voice, and its audience rule | **The family stage (P3)** | The alta loads `private_topic` and `withhold_from`; nothing in the personal stage discloses the owner's data to a visitor (*Context*, item 5) |
| Keeping a **household** secret (the wifi) after the robot offers it and the owner answers with a long authorization that verifies the voice; a **money** secret (bank, card, PIN) never | **ADR 0030, after Plan 0079** (review, decision 15) | It replaces ADR 0024 decision 4, an accepted decision, so it needs its own ADR; the offer and the long answer reuse the memory dialogue of ADR 0021. Reading a kept household secret would be the security level |
| Answering **in company** after the owner's long spoken authorization («sí, te autorizo a darme esta información») with the voice verified | **ADR 0030, after Plan 0079** (review, decision 15) | With two faces the resolver identifies nobody (ADR 0016, ADR 0020); a verified voice among several faces changes that veto |
| Recalling the owner's `medical` conversation units («hoy fui al doctor por la presión») | **A roadmap row, after Plan 0079** (review, decision 21) | The day-to-day health of an older owner is what a companion should remember; it would use decision 1's sensitive level and decision 3's check, but it widens the read and is not needed for CM-7 |

CM-3b tranche B is therefore empty. The benchmark changes with dataset v4, in the plan that
prepares CM-7 (ADR 0026 decision 9 already opened that bump):

- `sensitive_preference_lifecycle` keeps its steps and its five categories, with a **taste** as its
  subject instead of a topic not to mention: «me gusta X» → restart → «¿qué te dije que me gusta?» →
  «ya no me gusta, corrígelo» → restart → forget → a guest asks and learns nothing. Tastes are
  written by voice today (CM-3a) and corrected and forgotten by CM-6. The test proves the same
  thing: learn, recall after a restart, correct, forget and not disclose.
- `domicile_temporal_validity` moves to the staged pending scope, reported like the family stage and
  never excluded.
- `personal_access_code_pending` already moves to `secret_holder` (ADR 0026 decision 9); its read
  is decision 1's security level.

### 7. Switch

Everything above is behind one setting, `SENSITIVE_READ_ENABLED`, default `false` in code (like
`RECALL_ENABLED`); with it off every turn is byte for byte today's, except decision 5.

*Amended 2026-11-05.* The secret rule does **not** follow `CONVERSATION_RECORD_ENABLED`, as first
written: with the record off the model would still receive «mi clave es 1234», and the in-process
session would hold it for minutes. The secret branch runs whenever `MEMORY_ENABLED` is on, whatever
the other switches say. It is the one documented exception to «byte for byte today's with the
switch off»: a turn that carries a secret word changes even with every new switch off.

## Pipec's decisions and where they land

Confirmed on 2026-11-04:

| # | Decision | Where it is written |
|---|---|---|
| 1 | One ADR; after the write half emptied, one plan | *Delivers*, decision 6 |
| 2 | Reads by levels (option C): the face for health, home and birthdays, face and voice for security; a fingerprint later for security only | Decisions 1 and 2 |
| 3 | A spoken secret is not kept (option A) | Decision 5 |
| 4 | «¿Estás con alguien?» once per conversation, the camera as a veto (option C); replaced by decision 13 | Decision 3 |
| 5 | The closed list of data read by voice (option A) | Decision 1 |
| 6 | `lives_in` only through the alta and `iroko-admin` (option A) | Decision 6 |
| 7 | «No menciones X» to the family stage, and the core CM-7 scenario rewritten with a taste (option 1) | Decision 6 |

Confirmed on 2026-11-05, after the pre-plan audit:

| # | Decision | Where it is written |
|---|---|---|
| 8 | The security grammar is evaluated before the secret branch | Decision 5, *order* |
| 9 | The record keeps the question and «[dato sensible leído]» in place of the answer | Decision 4, amendment |
| 10 | A closed alta is the consent for the owner's own sensitive reads | Decision 1, *consent* |
| 11 | One cleanup redacts old secret turns, deletes their units and rewrites their diary | Decision 5, *what was kept before* |
| 12 | The secret branch runs whenever `MEMORY_ENABLED` is on, record on or off | Decision 7, amendment |

Confirmed on 2026-11-05, in the review before the plan (to cut friction):

| # | Decision | Where it is written |
|---|---|---|
| 13 | The camera is checked in silence on every answer; «¿Estás solo?» is dropped | Decision 3, rewritten |
| 14 | The secret branch fires on a stated or an asked value, never on a mention | Decision 5, *a value, not a mention* |
| 15 | Keeping a household secret with authorization (a money secret never) and answering in company go to ADR 0030, after Plan 0079 | Decision 6 |
| 16 | A reference question reads the matching entries, or all when none matches | Decision 4, *review* |
| 17 | A child with no birth date: «No tengo registrada su fecha.» | Decision 4, *review* |
| 18 | Stored values are said the way a person says them | Decision 4, *review* |
| 19 | The debug text log stays as is and is never on in production | Decision 4, *review* |
| 20 | The cleanup is built only if a read-only count finds old secret values | Decision 5, *review* |
| 21 | Recalling medical conversation units goes to the roadmap | Decision 6 |

The author's calls, for Pipec's review of this ADR: the secret words are narrower than the recall
classifier's security words (decision 5); the secret branch answers a fixed phrase so the model
never holds the number; the setting name and its default; the explicit level map (decision 1,
amendment); one module for the secret words (decision 5, *one list*).

The author's calls from the independent builder check of 2026-11-05 (answers the plan builds on):

- **Where `basic` lives.** The policy changes, not the request: the read capability of ADR 0019
  §3 gains one exemption, reading the actor's **own** `medical` or `location` data needs the
  capability's own minimum (`basic`) instead of `strong`. The request keeps its true sensitivity,
  so the audit row says `medical` or `location`. `biometric` and every other action stay `strong`.
- **How the controller sees two faces.** The fusion reason of the turn (`veto_multiple_faces`)
  reaches the controller as a typed field beside the actor, from the frame the turn already
  captures with its clip; nothing is probed again.
- **The in-process session.** A sensitive or security answer, like the recall answer of Plan 0078,
  is never written to the continuity session, so a later generic turn cannot repeat it.
- **Who the secret branch serves, and its order.** It serves every speaker (a stranger's «mi clave es
  1234» is not kept either). Order in the controller: a **stated** value first, then the sensitive
  and security grammar, then an **asked** value, then every other branch, the memory-offer answer
  included («sí, mi clave es …» is a secret, not an answer). A stated value goes first so that a
  message that says one and also asks something («mi clave es 1234, ¿cuál es mi dirección?») is
  never kept as said; the security question of decision 8 states no value, so it is still read.
- **The consent source.** One read of whether a closed commissioning record exists, made only when
  a question matches the grammar; no cache. A closed alta never reopens (its acta is frozen).
- **Birthdays.** With the switch on, a birthday question about the owner or a child is answered by
  this decision's template instead of today's protected birth answer; a relative the alta holds by
  name only («¿cuándo cumple mi mamá?») answers «No tengo registrada su fecha.».

## What Phase 0 already covers

Pipec asked to check which planned work the alta already does. Recorded here so later plans do not
rebuild it:

| Planned work | Covered by Phase 0 | What is left |
|---|---|---|
| Third parties captured by voice (CM-3b) | The alta loads children, partner, parents, siblings, grandparents, grandchildren and pets | Nothing in the personal stage (ADR 0026 decision 9) |
| `lives_in` by voice | Address, dwelling and facility at the alta; `iroko-admin` corrects | Nothing (decision 6) |
| «No menciones X» | `private_topic` and `withhold_from` at the alta | The audience rule, in the family stage |
| The sensitive profile by voice | All of it is loaded | Reading it: this ADR |
| Tastes | The first ones at the alta; new ones by voice (CM-3a) | Correcting them («ya no me gusta») is CM-6 |
| Family onboarding (P3.1) | The family's names and relations are entities already | Enrolling each member's face and voice, their roles and their own consent: P3.1 extends the alta rather than building a new system |
| Voice calibration of the person | **Not covered.** Plan 0069 left the tools (an 85-phrase script, the bench); Plan 0072 left per-person voice settings out on purpose | The roadmap row «Voice calibration when a user is enrolled» stays open; it is what would help short questions verify |

## Not decided here

| Subject | Why not now | Owner |
|---|---|---|
| Reading another person's sensitive data (a child's health) | The personal stage reads only the owner's own | The family stage |
| The audience rule with `withhold_from` and `private_topic` | Family stage (decision 6) | P3 |
| The fingerprint sensor | A new sense on the robot | Its own ADR, with the electronics |
| Recalling `medical` or `location` conversation units | Not needed for CM-7; widens the read | A roadmap row (decision 21) |
| Keeping a household secret, answering in company | Reverses accepted decisions of ADR 0024 and ADR 0016 | ADR 0030 (decision 15) |
| Correcting and forgetting by voice | The cascade exists; the commands are CM-6 | Block C |
| Calibrating the person's voice at enrolment | Its own measurement and plan | The roadmap row above |

## Alternatives considered

- **Face and voice for every sensitive read (ADR 0019 §3 as it stood).** Rejected: questions are
  short and the voice fails on almost all of them; the robot would refuse the owner daily.
- **The face alone for everything, security included.** Rejected: CM-7 requires a security read
  that `basic` cannot reach, and a secret's holder is the most delicate reference the robot keeps.
- **Ask «¿estás solo?» before every answer.** Rejected: friction on every question for what the
  camera and the session already cover.
- **Ask «¿estás solo?» once per conversation** (the first version of decision 3). Replaced on
  2026-11-05: still a friction on the owner's own questions, a pending slot and a short-reply mode
  to build, for a residual case the camera mostly covers.
- **Trust the camera alone.** First rejected (a speaker off camera is the one case the face cannot
  see); **chosen** on 2026-11-05 (decision 13), with that case stated as an accepted risk and the
  first-person grammar as a partial filter.
- **The secret rule on every secret word** (the first version of decision 5). Replaced on
  2026-11-05 (decision 14): it cut ordinary conversation («cambié la clave del wifi») without
  protecting any value.
- **Keep a spoken secret without its digits.** Rejected: a number said in words passes.
- **Keep spoken secrets as today, readable only with the PIN.** Rejected: the value would sit on
  disk, against ADR 0024 decision 4.
- **`lives_in` and «no menciones X» by voice now.** Rejected: the alta already holds both, and the
  personal stage has no visitor to protect from that the existing rules miss.

## Consequences

### Positive

The owner hears their medications, address and birthdays with a question and a face, with nothing
asked back, and the voice is asked only for the rare security reference. Talking about a password
(«cambié la clave del wifi») is ordinary conversation. A secret said by mistake leaves no trace but
a marker. Block B shrinks to one plan, and CM-7 keeps every category it needs.

### Negative

A photograph plus a recording can draw the owner's sensitive data (never a secret's value). Someone
off camera hears an answer the owner asks for in their presence, and someone off camera who asks in
the first person while the owner is in view is answered (decision 13). A secret said without a
secret word, or without a value the rule recognizes, is kept as an ordinary turn, unreadable by
voice. «No menciones X» waits for the family stage. Two CM-7 scenarios change or move with dataset
v4. A turn that states or asks for a secret's value changes even with every new switch off, and its
false positives («la clave es que llegues temprano», «mi código postal es …») never reach the
model. The owner cannot have an answer in company until ADR 0030.

## Test consequences

Offline and deterministic, with invented canaries. *(Rewritten 2026-11-05 after the review.)*

- **Grammar.** The closed grammar of the sensitive and security questions against a corpus with
  Pipec's real phrases, their speech-to-text slips and the traps (a story that mentions a
  medication, «¿cuál es la dirección del colegio?», a third-person question «¿qué remedios toma?»);
  it is evaluated before the household protection of Plan 0077, which would otherwise take «¿cuál es
  mi dirección?».
- **Levels against actors.** Each level against the owner face-only, the owner with face and voice,
  another enrolled person, an unknown face, two faces and no face; the level map against every
  predicate of the table (the owner's `birth_date` included); a read with no closed alta is denied,
  with a closed one granted; the security retry, stateless.
- **Templates.** Every template with nothing loaded; the matching reference entries and the
  fallback to all; a child with a stated age only; the spoken forms of every blood type and of
  `takes_anticoagulant`; the record keeps the question and «[dato sensible leído]», never the value.
- **The secret rule.** Stated values (digits, spoken numbers, a copula and a word) and asked values
  hear the fixed phrase on the classic, the streaming and the `/chat` route: no model call, the
  marker in the record, no unit, no candidate, no continuity entry, nothing in the diary; mentions
  stay ordinary turns («cambié la clave del wifi», «eso es clave», «dejé las llaves en la mesa»);
  «¿quién conoce la clave?» is a read with the switch on and an ordinary turn with it off; the rule
  runs with the record off; the secret words defined once and the recall classifier's list derived
  from them.
- **Switch.** With `SENSITIVE_READ_ENABLED=false` every read route is byte for byte today's.

Hardware acceptance by Pipec, outcomes only: a medication and an address asked with only the face in
view (no question back); a birthday; the security reference with face and voice, and its retry; a
second face (a photo on a phone) → «Te lo digo cuando estemos solos.»; the camera covered → the
denial; a stranger → the denial; a stated secret → the fixed reply and nothing stored; a mention
(«cambié la clave del wifi») → an ordinary reply.

## Docs to update

With `Proposed`: the ADR index, the roadmap (step 3 of the closing path, row 7b emptied, the
cross-cutting rows for liveness and the audience rule, the P3.1 row), the memory map. With
`Accepted`: `current-state.md` and its diagram, the operator manual (the setting, the phrases, the
markers, the debug log never on in production), ADR 0019 §3, ADR 0026 and ADR 0027 (amendment notes), the seed data pool (the
capabilities table).

## Review

Revisit when a photograph-and-recording attempt is seen, when the fingerprint arrives, when the
voice verifies short questions on the real body, when the family stage opens, or when a secret is
found kept without a secret word.

## Follow-up

- The implementing plan is the next free plan number, 0079.
- The next free ADR number is 0030; it is reserved for decision 15 (a household secret kept with
  authorization, answering in company), written after Plan 0079 closes.
