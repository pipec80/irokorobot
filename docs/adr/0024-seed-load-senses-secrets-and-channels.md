# 0024 — The seed load: the data pool, secrets at rest, contacts, the confirmation of an assisted interview, identity modalities and the order of the commissioning

- **Status:** Accepted (2026-10-27, when Plan 0072 closed; proposed 2026-10-22 and **revised
  2026-10-23** after two rounds of independent review and
  Pipec's second and third briefs; see *Review record*). Every decision below is the author's
  recommendation. Pipec has confirmed, on 2026-10-22 and 2026-10-23: the importer by file as the
  first tool; a secret stored by reference only; the adult child declared in the file; access to the
  machine as the authority of the import; the owner's relatives (decision 10) and the predicate
  names; the contacts in their own table; two plans for the storage and the importer; the assisted
  channel with a commissioning record; a replacement window while the robot is being commissioned;
  resetting the database and loading everything through Step 0; and the purpose of the phase as
  stated in decision 1. It became `Accepted` when the plans that implement it closed (Plans 0070,
  0071 and 0072). Pipec's own real alta ran on 2026-10-27, after the plans closed.
- **Date:** 2026-10-22 (revised 2026-10-23)
- **Builds on:** [ADR 0004](0004-local-first-cognitive-policy.md),
  [ADR 0006](0006-personal-and-family-companion-profiles.md),
  [ADR 0008](0008-progressive-owner-authentication.md),
  [ADR 0009](0009-locked-posture-and-scoped-capabilities.md),
  [ADR 0016](0016-face-and-voice-identity-fusion.md),
  [ADR 0019](0019-personal-memory-capabilities.md),
  [ADR 0020](0020-authorized-actor-in-the-conversation.md),
  [ADR 0021](0021-memory-candidates-and-the-canonical-writer.md),
  [ADR 0022](0022-household-rules-and-third-party-memory.md),
  [ADR 0023](0023-speech-to-text-model-and-decoding.md)
- **Amends:** [ADR 0022](0022-household-rules-and-third-party-memory.md) decision 1 (the people the
  owner may write about gain relatives and the people to keep out, name and relationship only;
  contacts have their own table, decision 5), decision 2 (the confirmer is the owner only when the
  owner or the builder who is the owner confirmed; decision 6 here), decision 9 (the repository
  refuses a value by its predicate) and its open obligations 1 and 2. The roadmap's *Privacy contract
  of the senses* row is satisfied by decision 3.
- **Implemented by:** [Plan 0070](../plans/completed/0070-seed-load-data-pool-storage.md) (closed
  2026-10-23: the storage and the provenance), [Plan 0071](../plans/completed/0071-seed-load-file-importer.md) (closed 2026-10-26: the
  importer), [Plan 0072](../plans/completed/0072-commissioning-session.md) (closed 2026-10-27: the
  session itself, with the notice and the consents, the face and voice sessions, the readiness report,
  the closing and the acta, as `just commission`) and
  [Plan 0073](../plans/completed/0073-local-admin-crud.md) (closed 2026-10-28: the local administration
  that is the amendment path of decision 8; its remote half is [ADR 0025](0025-remote-administration-backup-updates-and-telemetry.md)).
- **Companion document:** [`seed-data-pool.md`](../architecture/seed-data-pool.md), the catalogue of
  what is captured, where it lives and which capability needs it.

## Context

The roadmap's row «Seed load» describes Step 0 as a load from a local file as the second input
channel of the canonical writer. Pipec's briefs of 2026-10-23 say what it is for: **the robot
needs information loaded before it can work at all; without it it is a toy.** Whatever tool is
defined now or later (a call to a phone, a geolocation, a spoken warning) needs its data and its
hardware to exist: a tool that calls a phone is useless with no phone stored, one that locates a
person is useless with no location stored, one that speaks is useless with no speaker. The data
cannot be remembered when the tool is built, because by then the interview is over. The interviewer
may not be the owner (a relative, a technician, or Pipec himself when he is the first owner) and the
owner may be an older, non-technical person; the interviewer also enrols face and voice in the same
session. Pipec also wants the earlier onboarding work recovered into one flow (the wizard, the face
and voice scripts, the voice research of Plan 0069), with room for biometric inputs that do not exist
yet (a fingerprint, an iris, a chip), because a chip a user carries could one day replace voice,
image and PIN.

What the audit and two rounds of independent review verified in code (`main` at `5f90e6e`):

1. `relational_v4.refuse_security_value` refuses by sensitivity and runs before any query, write or
   log. The only `security` predicate is `access_code`, with no Spanish alias. A caller can state a
   sensitivity that differs from the predicate's default (the stamp is `sensitivity or default`).
2. `canonical_writer._is_member_of_owner` treats every active `child_of` or `pet_of` row as a
   member, and `_may_become_a_member` reuses it for the symmetric partner relation. A relation
   `child_of` with a relative as its source would be accepted, and every fact about that relative
   with it.
3. `personal_setup.apply_personal_setup` creates the owner, the children and the PIN from the server's
   machine and replaces the PIN without asking for the previous one. `check_db_available` only runs
   `BEGIN IMMEDIATE`; an idle server holds no write lock, so it does not prove the server is stopped.
4. `scripts/reset_db.ps1` hard-codes `data/omnibot.db` (it ignores `BRAIN_DB_PATH`), voids live
   candidates, copies only the main database file (not the `-wal`), embeddings included, to
   `data/backups` and deletes it. Nothing ever deletes that copy. The face and voice profiles
   (`face_profiles`, `voice_profiles`), the consent grants and the authorization audit rows live in
   the same file, so a reset deletes them all. `db.py` opens SQLite with `secure_delete = ON`; `data/`
   is ignored by git.
5. Enrolling is manual and split: `just onboard` first runs the identity wizard (server stopped), then
   the face phase (server running, one frame); `just speaker-auth-demo --enroll` enrols one voiceprint
   per call (server running, `SPEAKER_AUTHENTICATION_ENABLED=true`, a PIN each, three references
   needed). Plan 0069 left a reading script, a corpus recorder and a calibration bench; nothing runs
   them at enrolment.
6. Nothing in `server/src` models a contact or a phone number. The household reader serves the list
   and the count of the children and nothing else; the policy-gated reader does not look at
   `confirmed_by`/`confirmed_at`, so a row stored without a confirmation would be read as if it had one.
7. The canonical writer has no policy of its own: the policy sits in its callers. An import calls
   none, writes no authorization audit row and does not consult `memory_enabled`.

The research Pipec brought (a questionnaire of 107 questions, eight data blocks and an audience axis)
is context, not authority. This ADR and the companion document take from it what Step 0 needs and
list the rest, with an owner, under *Not decided here*.

## Decision

### 1. What Step 0 is: the alta of the robot

The **alta** (the commissioning) of the robot: a conversation, before it goes into service, in which
an **interviewer** (a relative, a technician or the builder, who may be the owner) and the **owner**
fill in a form that loads what the robot needs to work, and in which the interviewer enrols the
owner's face and voice. The owner reviews the result before anything is written. The robot
interviews nobody. What it loads is there to support the tools already defined and those still to be
defined; what the robot later learns by voice (a taste it offers to remember) refines the loaded data
and never replaces it. The tool that loads from the form is a text file in this phase: no
photograph and no audio in it; face and voice go through their own consented flows, because a
photograph used to recognize a person is that person's biometric data.

### 2. The data pool

The pool is the catalogue in [`seed-data-pool.md`](../architecture/seed-data-pool.md). Its rules,
which are decisions of this ADR:

- **Capture now, build later.** A stored phone calls nobody; each capability keeps its own gate.
- **A field needs a purpose**, a destination, a sensitivity and a decision on its status; without a
  purpose sentence it is not added. The catalogue says, for each capability, which fields it needs.
- **Absence is data.** Each section where silence is ambiguous carries one status in the
  commissioning record: `provided`, `none`, `unknown`, `declined` or `not_asked` (the default). A
  status is not a fact and is never written to the memory (ADR 0022 decision 10 still holds: a
  negation is not persisted).
- **Sensitive classification is the writer's**, from the predicate: health is `medical`, an address
  `location`, a reference to a document `security`.
- The pool has a version, recorded in the commissioning record.

### 3. The privacy of the senses

| Kept | Never leaves the device |
|---|---|
| Confirmed text facts, with their asserter and channel | Raw audio and camera frames (not retained after the turn) |
| Face and voice embeddings: local, consented, revocable, purged on revoke | The embeddings themselves, any transcript, any prompt or reply text |
| Authorization audit rows and the commissioning record (decisions and counts, never a household value) | Any value in a log, in `llm_response`, in the history or in the acta |

Nothing in the runtime path reaches a cloud provider (ADR 0004). Today's capture is per turn. **Any
new continuous capture** (an always-on microphone or camera, a recording beyond one turn) is not
allowed until this ADR is amended, and the amendment must include a physical switch and an indicator
once there is hardware. Porting the per-turn capture to the Raspberry Pi needs neither.

### 4. Secrets at rest: the value is never stored

The value of a secret (an alarm code, a safe combination, a bank PIN) is **not stored in any form**,
plain or encrypted. The robot cannot say what it does not hold.

- `access_code` stays registered and is refused **permanently**: a new registry field, `storable`,
  is `False` for it. The repository refuses a value by that field, and also refuses any mismatch
  between the sensitivity a caller states and the one a `security` predicate defaults to (both
  directions: nobody labels another predicate `security`, nobody relabels `secret_holder`). The
  refusal runs first, before any query, write or log, and the error and every log carry no part of
  the value.
- What is stored is **who knows it** (`secret_holder`, several values, the owner's own, `personal`
  visibility, `security` sensitivity) and **where a document is** (`document_location`). Reading
  them demands `strong` assurance (ADR 0016). They are free text written by the owner and may name
  a person outside the closed set; that is accepted because it is the owner's own sentence and not
  an entity.
- Defence in depth, not a guarantee: the three *reference* fields (`secret_holder`,
  `document_location`, `home_access_note`) refuse a value with four or more digits anywhere. That
  also refuses «depto 1204»: the number of the flat belongs in `home_address`, which takes digits,
  and the importer's message says so. A code spelled in words is not caught; the example file's
  comments tell the interviewer so.
- The floor for every other sensitive datum is the operating system's disk encryption (BitLocker,
  LUKS). The system neither verifies nor promises it: the commissioning record stores the
  interviewer's declaration (`declared_yes`, `declared_no`, `unknown`).
- The import file holds real data, and so does every source it is made from (an Excel sheet, a CSV).
  The interviewer may fill an Excel or CSV sheet on their own machine and a **converter that runs there,
  never on the server**, produces the TOML (Pipec's choice, 2026-10-23; the importer reads only TOML).
  Either way the file reaches the server **only over SSH** (`scp`), never by USB, mail or a synced
  folder, and lands under `data/`, which git ignores. The importer does not delete it and says so;
  deleting it, the sheet and the converter's output (the recycle bin and editor swap files included) on
  every machine is a step of the closing checklist. No value reaches a log. The report is printed on the
  terminal of the person who runs the command and stays in its scrollback; the interviewer is told to
  clear the screen after applying.
- **A backup is a copy of everything.** The pre-reset copy in `data/backups` holds biometric and
  health data and is never deleted by the system. The commissioning record stores its path and the
  date it must be destroyed; so does the baseline backup of decision 13.

### 5. Contacts: the `care_contacts` table

A caregiver's phone is a fact about a third party, which ADR 0022 closes. Instead of opening an
exception in the V4 writer, contacts are **operational data in a table of their own** (migration 011),
written only by one function of the canonical writing family:

- a row: the owner, the contact (an existing person entity or a third party created apart; an adult
  child, the partner or a relative may be a contact), a closed `role` (`emergency`, `caregiver`,
  `doctor`, `key_holder`, `neighbor`, `trusted`, `other`), a short `relationship` label («hija»,
  «vecina»), a phone and an optional second one (a mobile and a landline) in international format,
  an optional call order unique among the active contacts and belonging to the person (**no order
  means an alert never calls them**), one active row per owner, contact and role, `has_key`, `may_receive_health_info` (the allow-list counterpart of `withhold_from`; its
  consumer is the audience rule of CM-5), `may_view_activity` (whether the contact may later see the
  owner's activity events from a web page; nothing shows them before the care profile and the SaaS
  exist, and a consent per person is not implied by the flag), the asserter, the channel, the confirmer and `revoked_at`;
- the classification is stored in the row and assigned by the writer, never by the caller: visibility
  `personal`, sensitivity `private`, or `location` when the contact holds a key;
- being a contact **does not make a person a household member**: it opens no V4 fact about them, and a
  person who holds a contact row cannot be declared a child, a pet or the partner to unlock facts;
- nothing reads the table by voice and no alert is built: a future care ADR decides who reads it (a
  system purpose is not an authorized actor) and how a contact may ask to be removed;
- forgetting (CM-6) covers the table; until then a row is revoked, never edited.

Alternative considered: V4 facts `phone_number` and `call_order` on a contact entity. It reuses the
writer but needs an exception to ADR 0022 for facts about adults, and a phone, an order and a role
are one thing. The legal reading of keeping third parties' phones for the owner's own care is pending
advice.

### 6. The confirmation of an assisted interview

The writer so far stamped the owner as asserter and confirmer whoever typed the confirmation. With an
interviewer who is not the owner that stamp would say something that did not happen. So:

- A new channel, `import_assisted`, beside `import_file`. The importer always uses `import_assisted`;
  `import_file` stays in the list for a load made by the owner alone.
- A **commissioning record** (migration 011) is opened for the session: the interviewer's label (free
  text, a person's name), the interviewer's role (`builder`, `family`, `technician`, `other`), the
  confirmation mode (`owner_in_person`, `representative`, `builder_is_owner`), the declaration about
  disk encryption, the pool version and a random **installation id** (generated at the opening, derived
  from nothing about the house or the hardware); then at each import the hash of the file and the counts;
  and at the closing the consents given (face, voice, and, for [ADR 0025](0025-remote-administration-backup-updates-and-telemetry.md),
  telemetry, remote support and backup with a label for its destination), the biometric notice's version,
  the modalities enrolled and the backup's path and destruction date. A consent recorded builds and
  enables nothing. `builder_is_owner` requires the role `builder`.
- The importer applies **nothing** unless the interviewer answers the review question with `SI`: for
  the modes `owner_in_person` and `builder_is_owner` «¿la persona titular revisó este resumen y lo
  aprueba?», for `representative` «¿la persona que representa a la titular revisó este resumen y lo
  aprueba?». If not, the run is a dry run. There is no state «declared but not confirmed» in the
  data, because the readers cannot tell it apart.
- **The asserter is the owner's entity; the confirmer is the owner's entity only in the modes
  `owner_in_person` and `builder_is_owner`.** In `representative` mode `confirmed_by` stays `NULL`
  and `confirmed_at` is kept: the readers ignore the column, so the record is honest at no cost.
  Representatives (a legal figure for an owner who cannot decide) are **not modelled**; the mode only
  records that one acted, and whether it is valid needs legal advice.
- The interviewer is a label in the record, not an entity.

### 7. The level of each channel

| Channel | Who authorizes | How it writes |
|---|---|---|
| `voice_classic`, `voice_stream` | The face **and** the voice of the same person on that turn's own clip, never a token (ADR 0021) | A spoken offer and an explicit spoken answer |
| `import_assisted`, `import_file` | Local administration: the person who runs the command on the server's machine, with the server stopped | A dry run, the owner's review, the typed word `SI` |

The classification and the reads are the same whatever the channel, and the channel is only recorded.
Reads do not change (`basic` for ordinary private data, `strong` for `biometric`, `medical`,
`location` and `security`, ADR 0019 §3). The canonical writer has **no policy**, and the import
**bypasses the policy, the audit-before-effect rule and the `memory_enabled` switch** on purpose: it
is an administration act, not a conversation. What replaces them is the commissioning record (who,
when, which file by hash, how many rows) and a log line with counts only. Whether ordinary private
data should also move to `strong`, and the question «are you with someone?», need the audience of the
turn and a reader, so they are CM-5.

### 8. Replacement while commissioning, none after

- **While the robot is being commissioned** (no commissioning record is closed), loading again with
  the replacement flag **retracts what an earlier import wrote** (the rows whose channel is an import
  channel, the contacts and the statuses, and the third parties nobody refers to) and **then writes
  the file with the refuse-on-conflict policy**. It is refused if the robot already learned anything
  by voice (a stored row with a voice channel or a live memory candidate): corrections of what was said aloud are
  CM-6, and an old file must never resurrect what the owner asked to forget. This is how a typo found
  at the verification is fixed without a reset, which would delete the face, the voice, the consents
  and the audit.
- **Without the flag, even inside the window**, a load never overwrites: a value that differs from the
  stored one, a different partner, a different phone for the same contact and role, or a changed
  `guardianship` stops the whole load as a conflict and writes nothing.
- **After the commissioning is closed** the importer does not run at all. The marker exists in this
  phase (`closed_at`); the command that sets it belongs to the commissioning plan, so until that plan
  the window stays open.
- **A gap, stated:** after the closing, contacts, medications and conditions have **no write path**:
  the voice writes only tastes. A caregiver's phone changes within months. Before the robot is trusted
  with any capability that depends on them (an alert, a reminder) there must be an **amendment** path.
  It is [Plan 0073](../plans/completed/0073-local-admin-crud.md), the local CRUD `iroko-admin` that
  closed Phase 0 on 2026-10-28 (every edit through the canonical writers, with an audit that holds no
  value; the machine's access plus the owner's PIN for sensitive data authorize it); administering
  from afar is [ADR 0025](0025-remote-administration-backup-updates-and-telemetry.md). The amendment
  path now exists, so the care capabilities are no longer blocked on it.
- Loading the same file twice changes nothing in either case.

### 9. The adult child

The file declares `guardianship: minor | adult` for every child, and it is required. The marker is
stored in the child's entity attributes and **the writer reads it**, so the rule holds on every
channel: a child marked `adult` is treated like the partner, **name and relationship only**, and any
fact about them is refused as `not_household_member`. They remain eligible as a contact (decision 5),
which is the usual case of the adult child who is the caregiver. A child created by `personal-setup`
has no marker and keeps being treated as a child the owner is guardian of (fail-open, accepted
because the owner named them in that wizard); the importer never adopts an existing entity, so the
recommended flow is `setup-personal` with no children and the children in the file. When a minor
turns 18 the change is a correction (CM-6).

### 10. The owner's relatives and the people to keep out

*Confirmed by Pipec.* Parents, grandparents, siblings and grandchildren are outside the closed set of
ADR 0022 §1. They get **the partner's rule (§4): the name and the relationship, and nothing else.**
Relation predicates `has_parent`, `has_grandparent`, `has_sibling` (symmetric) and `has_grandchild`,
the **owner at the source end** (a symmetric row read from the other end is refused), the relative a
third party created apart (`create_third_party`, which never merges homonyms), stored `personal`.
`withhold_from` records the people who must not receive information (stored `personal`/`private`; its
consumer is the audience rule of CM-5); its target may be any person, a household member or a contact
included, because keeping a relative out is the commonest case. A relative can never become a member,
and a member can never become a relative: the fence looks at the four relative relations and at the
contacts, **not** at `withhold_from`, and it never refuses an exact repeat of a relation that is
already active (a load run twice changes nothing).

### 11. Who may import

Access to the machine is enough (Pipec's decision, 2026-10-22). The cost, stated: whoever can run
commands on the server can write as the owner; already true today (context 3). What the tool adds
against mistakes, none of it authentication: it refuses to run if the server answers `/health`
(probed once, synchronously, before the event loop starts, with the port from the settings) or the
database is locked; it never creates a database or a schema (it needs an existing one at the current
version, and says which command makes it); it never creates the owner (the owner and the PIN must
exist, and the owner's name in the file must equal the stored one); it prints the database it is about
to use; the default is a dry run that writes nothing; applying needs the owner's review answer; and
everything is written in one transaction or nothing is. Alternatives set aside for now: the owner's
PIN, and the PIN plus the face. **Revisit** when a second adult is enrolled, when the server is shared,
or if the importer becomes a service.

### 12. One comparison for duplicates

One neutral module (a top-level module of `server`, so both `cognition` and `memory` may import it)
holds `fold_name`, `comparison_key` (folded, without a leading article) and `normalize_spanish`, which
moves there from `cognition/intent_resolution.py`. It replaces the three copies of `_fold_name`, and the
canonical writer compares `text` values with it, so a spoken «El Café» and an imported «café» are one
row. Known limit, pinned by a test: the key drops punctuation, so «C++» and «C#» collide; a key that
comes out empty falls back to an exact comparison.

### 13. The order of the commissioning and what «freeze» means

An operating procedure; the commissioning plan turns it into a runbook with a command.

| Step | Server | Action |
|---|---|---|
| 0 | off | Declare the disk encryption; set the `.env` flags `FACE_AUTHENTICATION_ENABLED` and `SPEAKER_AUTHENTICATION_ENABLED` (**not** `MEMORY_CANDIDATES_ENABLED`: a candidate learned by voice would end the replacement window). Tag `main` as `pre-step0` |
| 1 | off | `just reset-db` (the reset script honours `BRAIN_DB_PATH` and copies the `-wal` too). Record the backup's path and the date it is destroyed |
| 2 | off | `just setup-personal`: the owner and a PIN the owner chooses, no children |
| 3 | on | Read the biometric notice, record the consents (biometric, and telemetry, remote support and backup), enrol the face (the face phase of `just onboard`, several frames) and the voice session of decision 15 |
| 4 | off | Dry run, the owner's review, apply (the commissioning record is opened here) |
| 5 | on | Verify what can be verified (the children's list and count; a turn by face and voice) |
| 6 | off | A second dry run must show no change |
| 7 | — | The readiness report of decision 14; a baseline backup of the commissioned database, offline, with its path and destruction date; close the commissioning (the marker); write the acta; destroy the import file and the paper form; only now `MEMORY_CANDIDATES_ENABLED`, if Pipec wants it |

**Freeze** means: after step 7 the import channels no longer replace anything; the pool version, the
file's hash and the counts are fixed in the acta; later changes come only by voice and through CM-6
(and, for contacts and medications, the amendment path of decision 8 when it exists). It does not make
the database read-only. The **acta** holds no household value: the date, the interviewer's label and
role, the confirmation mode, the installation id, the consents given, the modalities enrolled, each section's status, the
file's hash, the counts, the backup paths and destruction dates, the disk declaration and the
readiness report.

### 14. A capability is ready only when its data **and** its hardware are

The commissioning closes with a **readiness report**: for every capability in the catalogue's table
(*Capabilities and what they need*) it says whether its data is present (derived from the sections'
statuses and the rows, never typed by hand) and whether its hardware and software are supported,
configured and verified (checked by a person, one by one). A stored phone does not enable a call, a
stored address does not enable a rescue instruction, a permission never installs a capability, and
approving the form never turns anything on. A capability with data and no hardware (a call with no
telephony, a location with no sensor) is reported as **blocked by hardware**, a capability with
hardware and no data as **blocked by data**; both are visible on the day of the alta instead of the
day of the emergency.

### 15. Identity modalities and the voice session

- **Identity modalities are adapters.** A way of recognizing the owner (the PIN, the face, the voice
  and, later, a fingerprint, an iris scan or a chip the user carries) is an adapter that produces
  typed, expiring identity evidence or a scoped grant, and nothing else; the fusion and the policy
  (ADR 0008, 0016, 0020 decision 6) decide what the evidence is worth. The commissioning record keeps a
  closed inventory of the modalities enrolled with their consent; the list names the reserved ones
  (`fingerprint`, `iris`, `token`) so a future modality is a new adapter, its own enrolment and consent
  and an ADR that sets its assurance, never a change of the pool. A token that replaces voice, image
  and PIN is possible only if such an ADR says what assurance it gives.
- **The voice session** is part of the alta. It reads the owner a short script (the building blocks
  are Plan 0069's reading script and corpus recorder), and from it takes the voice references the
  speaker check needs (three or more), a level and distance check of the microphone, and, as
  measurements and not as interview answers, the per-person settings the speech-to-text benefits from
  (the threshold below which a transcript is «unclear», hotwords). The seeded names (children, pets,
  relatives, contacts) are the natural hotwords for the recognizer. How a person pronounces their own
  and their family's names is worth capturing; whether a pronunciation field joins the pool is for the
  commissioning plan. Audio is embedded and discarded, never stored in the file or the repository.
- **The face session** takes several frames (distance, glasses, lighting, as Plan 0030 measured), not
  one.

## Not decided here

| Subject | Why not now | Owner |
|---|---|---|
| The interview's interface and the 107-question catalogue | The first tool loads from a file; the pool document is its field list | A later Step 0 plan |
| The Excel and CSV converter to the TOML | Pipec's choice for filling the form; it runs on the interviewer's machine, so it needs a spreadsheet library (`openpyxl`) in an optional group that the server never installs, and its own plan | A later Step 0 plan |
| Where the voice's per-person settings and pronunciations are stored | Measured data, not interview answers | The commissioning plan |
| A fingerprint, iris or chip adapter | No hardware; an ADR with the adapter | The electronics track |
| The amendment path for contacts and medications after the closing | See decision 8 | Plan 0073 (local, done 2026-10-28), ADR 0025 (remote, no plan yet) |
| The structured read of the profile and contacts by voice | Reading is CM-5; nothing reads them yet | The first slice of CM-5 |
| The eight disclosure blocks and the audience axis («who is listening») | They need the reader and the audience of the turn | CM-5 |
| The emergency sheet and break-glass access, durable consent records and grants, the alert and the call | The `care` responsibility profile and legal and clinical advice (Law 21.719) | A future ADR of that profile |
| Who may read a contact's phone, and a contact's right to be removed | A system purpose is not an authorized actor | The care ADR |
| A structured medication schedule | Its consumer is a reminder service | When reminders are planned |
| A `beliefs` sensitivity for religion | Legal advice first | An ADR after the advice |
| Places with validity | Pipec left it pending | A later plan |
| Two third parties with the same name | Needs a migration that rebuilds `entities` | Unplanned |
| The benchmark's pending SECURITY scenario (it names `access_code`, now never stored) | A dataset version bump | CM-7 preparation |

## Alternatives considered

- **Encrypt the secret with a key derived from the PIN.** Key management, recovery and backups, a new
  dependency, and a secret a replayed voice could be tricked into asking for. Rejected.
- **Keep refusing every `security` value.** Leaves CM-7 without a `SECURITY` datum. Rejected.
- **The adult child from the birth date.** Fails without a complete date and changes by itself. Rejected.
- **The owner's PIN, or the PIN plus the face, to import.** Chosen against by Pipec for now.
- **Contacts as V4 facts, or deferred.** Decision 5.
- **A row «declared, not confirmed».** The readers cannot tell it apart. Decision 6.
- **Never replacing.** A typo would need a reset that deletes the biometrics. Decision 8.
- **Replacing with the supersede policy.** It would overwrite a fact said by voice. Decision 8.

## Consequences

### Positive

The data a later alert, sheet, reminder or evacuation needs has a place and a classification now, and
the alta says which capabilities can work and which are blocked and why; a contact, a secret reference
and an adult child are handled without breaking ADR 0022; the confirmation says who confirmed; a load
is reviewable, repeatable, correctable while commissioning and all-or-nothing; the senses have a
written contract before the hardware arrives; a new biometric input does not change the pool.

### Negative

The machine is the root of trust of the import; the references are free text with a weak digit check;
a file with real data sits on disk until the end of the commissioning; nothing can be read by voice
until CM-5, so «¿cómo se llaman mis padres?» is not answerable yet; a reset deletes face, voice,
consents and audit and must be followed by a new enrolment; a contact's phone is a third party's data
whose legal footing is pending; contacts and medications cannot be changed after the closing until an
amendment path exists; there are three plans before the first commissioning.

## Test consequences

A secret is refused whatever its label and leaves no trace in a row, a log, a message or a repr; a
reference with four digits is refused; a contact needs an international phone and an unambiguous
order; a person holding a contact, a relative or an `adult` marker receives no fact on any channel and
cannot be relabeled a member, while an exact repeat of an existing relation is accepted; the same fact
by voice and by import has one classification; the same file twice changes nothing; a conflict stops
the load and a replacement while commissioning retracts only import rows, refuses when the robot already
learned by voice, and after the closing the importer refuses to run; a failure half-way leaves nothing;
nothing is applied without the owner's review; the commissioning record carries no household value;
the import channels are named only by the importer (an architecture guard); `confirmed_by` is `NULL`
in `representative` mode.

## Docs to update

With **Accepted**: ADR 0022 (pointers from decisions 1, 2 and 9 and from its open obligations), ADR 0021
(decision 13, where it says the first `SECURITY` datum waits for Step 0), `identity-and-access.md` (the
channels, the modalities), `memory-and-world-state.md` (the writer, the adult child, the relatives,
`secret_holder`, the contacts), `longitudinal-conversational-memory-evaluation.md` and
`docs/evals/longitudinal-memory-v3.md` (the pending SECURITY scenario), `current-state.md` and its
diagram, the cognitive roadmap (the Step 0 row, the privacy row and the voice-calibration row), the plan
index and the ADR index.

## Review

Revisit when a second adult is enrolled, when the server is shared, when the robot gains a continuous
sense or a new biometric input, when the care profile is decided, when a `beliefs` classification is
decided, or when CM-5 can read what was loaded.

## Review record

**Independent reviews, 2026-10-23** (two read-only reviewers that had not written the first version, run
twice: on the first version and on the rewrite). First round, folded in: the first version left out the
data the phase exists for (contacts with phones, address, health, the people to keep out) and put the
adult child caregiver out of reach; the typed `SI` recorded a confirmation that may not have happened; a
typo could only be fixed by a reset that deletes the biometrics; there was no acta and the order mixed
stopped and running server; the import was said to keep the policy and the audit when it bypasses them;
the rewritten refusal lost the guard against relabeling `secret_holder`; a relative could be relabeled a
child and an adult child a partner; a changed `guardianship` passed in silence; `check_db_available`
does not prove the server is stopped and the dry run created the database; `reset_db.ps1` ignores
`BRAIN_DB_PATH`. Second round, folded in: the contact fence broke the idempotency of the caregiver child;
`--replace` could overwrite a fact said by voice and resurrect a forgotten one; the health probe could not
use the lifespan's HTTP client; the entity cleanup needed SQL outside its repository; the review answer
and the commissioning data were one parameter; a unique index on a nullable column enforced nothing;
mobility, hearing, vision, floor and lift, a relationship label, a second phone and the allow-list were
missing from the pool; `not_asked` was missing from the statuses and `household`, `home` and `function` from
the sections; `confirmed_by` stamped the owner in `representative` mode; the acta lacked its columns, the
baseline backup and the readiness report; contacts have no write path after the closing (stated as a gap).

## Follow-up

- [Plan 0070](../plans/completed/0070-seed-load-data-pool-storage.md) — the storage and the provenance (closed 2026-10-23).
- [Plan 0071](../plans/completed/0071-seed-load-file-importer.md) — the importer (closed 2026-10-26).
- [Plan 0072](../plans/completed/0072-commissioning-session.md) — the commissioning session (closed 2026-10-27).
- The next free ADR number is 0026 (0025 is [the administration ADR](0025-remote-administration-backup-updates-and-telemetry.md)).
