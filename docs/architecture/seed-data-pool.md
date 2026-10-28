# The seed data pool: what Step 0 captures, and where each datum lives

> **Status:** Canonical (2026-10-27, when [ADR 0024](../adr/0024-seed-load-senses-secrets-and-channels.md)
> became `Accepted`; proposed 2026-10-23). Every field of the catalogue below is implemented by the
> plan named in its *Plan* column (Plans 0070 to 0072, and Plan 0073 for amending it); the
> capabilities table at the end is the part that is still intent
> ([`current-state.md`](current-state.md) says what runs).
>
> **Plan 0070 (the storage) closed on 2026-10-23.** Every field the *Plan* column marks `0070` is now
> registered, validated and writable: through the canonical writer for a V4 fact, through the contacts
> writer for a contact and through the commissioning module for the acta.
>
> **Plan 0071 (the importer) closed on 2026-10-26** (accepted by Pipec on a database kept apart): every field
> of the catalogue below except the commissioning's consents and backups is loaded from
> the seed file by `just seed-import`; the file's keys, its template and questionnaire are in
> [`docs/examples/seed-household.example.toml`](../examples/seed-household.example.toml) and its
> schema in [`seed-household.schema.json`](../examples/seed-household.schema.json). **Nothing reads
> them by voice (CM-5)**, except the children's list and count.
>
> **Plan 0072 (the session) closed on 2026-10-27** (rehearsed end to end by Pipec on real hardware): the
> consents and the backups of the commissioning are recorded by `just commission` in the acta, together
> with the notice version, the modalities enrolled (derived from the database) and the readiness report
> of the capabilities that exist today; this document is now canonical (ADR 0024 is `Accepted`).
>
> **Plan 0073 (the local admin CRUD) closed on 2026-10-28.** After the alta closes, `iroko-admin`
> (run on the machine over SSH, server stopped) is the **amendment path**: it lists, adds, changes and
> revokes the loaded pool and contacts through the same canonical writers (channel `admin_local`), with
> the owner's PIN for sensitive data and an audit that holds no value. A datum now changes without a
> re-interview ([ADR 0025](../adr/0025-remote-administration-backup-updates-and-telemetry.md) `Accepted`,
> local half; `revoke` is history, a hard delete is CM-6).

## Why this list exists

Step 0 is the commissioning of the robot: an interview with the owner, before the robot goes into
service, whose result is the database everything afterwards starts from. A capability added later
(a fall alert that calls the caregiver, a medication reminder, the sheet read to a paramedic,
evacuation advice) must find its data already there; collecting it then means interviewing the owner
again. So the rule of the phase is **capture now, build later**:

- **Capturing a datum is not building a capability.** A stored phone number calls nobody; a stored
  medication reminds nobody. Each capability keeps its own gate (a policy, a test, a hardware
  check) and is planned on its own.
- **Nothing in this pool can be read back by voice** before CM-5, except the list and the count of
  the children, which the household reader already serves.
- **A field earns its place by a purpose.** If nobody can say what it is for, it is not asked
  (Law 21.719 asks for purpose and proportionality; the legal reading is pending advice). Fields
  with no purpose today are listed under *Not stored*.
- **Absence is data too.** For every section where silence is ambiguous the interviewer records
  one status: `provided`, `none` (the owner says there is none), `unknown` (asked, nobody knows),
  `declined` (the owner does not want to say) or `not_asked` (the interview did not reach it; the
  default). «No allergies» and «not asked» must never look alike. A status is not a fact: it lives in
  the commissioning record, never in the memory. A section is `provided` when any of its fields has a
  value. The eleven sections are: `conditions`, `allergies`, `medications`, `devices`, `contacts`,
  `withhold`, `secrets`, `documents`, `household` (children, partner, pets), `home` and `function`.
- **Adding a field later is cheap, re-interviewing is not.** A field is one registry entry; the
  pool version is recorded in the commissioning record so a later interview knows what was asked.

## Where things live

| Kind | Home | Why |
|---|---|---|
| A fact about the owner, a child, a pet | V4 literal fact through the canonical writer | One writer, one classification, provenance, a forgetting path in CM-6 |
| A relationship of the owner (parents, siblings, grandchildren, the people to keep out) | V4 relation, the other person a third party created apart, **name and relationship only** | ADR 0022 §4, ADR 0024 decision 10 |
| A contact with a phone (caregiver, doctor, key holder, neighbour) | The `care_contacts` table, written by the contacts writer | A phone, an order, a role and what the contact may be told are operational data, not a sentence; ADR 0024 decision 5 |
| Who interviewed, how the owner confirmed, what was asked, each section's status, the backup and the consents | The `commissioning_records` and `commissioning_sections` tables | The acta of the commissioning, with no household value |
| A secret, an identity document | **Never the value**: who knows it or where it is, as a reference | ADR 0024 decision 4 |

## The catalogue

*Plan* is the plan that implements the destination (0070 storage, **shipped**; every field marked `0070` or `exists` is loaded by the 0071 importer); *Phase 0* says
whether the field is captured in this phase; *Section* is the section whose status covers it (a
blank means the field has no status). «Sensitivity» is the `DataSensitivity` value the writer stores.

| Field | Destination | Sensitivity | Section | Feeds (later) | Plan | Phase 0 |
|---|---|---|---|---|---|---|
| Full name | the owner's entity (`just setup-personal`) | normal | | every utterance, a rescuer's read-out | exists | yes |
| Name to be called by | `preferred_name` (new) | normal | | greeting, rescuer | 0070 | yes |
| Form of address (tú or usted) | `address_form` (new, choice) | normal | | every reply | 0070 | yes |
| Birth date | `birth_date` | private (the owner's) | | the sheet, age | exists | yes |
| Health coverage | `health_coverage` (new) | private | | which facility | 0070 | optional |
| Chronic conditions | `health_condition` (new, several) | medical | conditions | the sheet, fall and illness advice | 0070 | yes |
| Allergies and their reaction | `allergic_to` | medical | allergies | the sheet | exists | yes |
| Medications, dose, times, with or without food | `medication` (new, several; one sentence each) | medical | medications | the sheet now, reminders later (a structured schedule is a later model; the sentence keeps nothing lost) | 0070 | yes |
| Takes an anticoagulant (yes, no, don't know) | `takes_anticoagulant` (new, choice) | medical | medications | head injury, fall alert | 0070 | yes |
| Rescue medication and where it is | `rescue_medication` (new, several) | medical | medications | the sheet | 0070 | yes |
| Devices and implants | `implanted_device` (new, several) | medical | devices | the sheet | 0070 | yes |
| Blood type | `blood_type` (new, choice) | medical | | the sheet | 0070 | optional |
| Mobility: alone, cane, walker, wheelchair | `mobility` (new, choice) | medical | function | fall risk, evacuation | 0070 | yes |
| Hearing: normal, hearing aid, difficulty | `hearing` (new, choice) | medical | function | volume and pace of speech, alerts | 0070 | yes |
| Vision: normal, glasses, difficulty | `vision` (new, choice) | medical | function | scene description, alerts | 0070 | yes |
| Advance directive, will, identity card: that it exists and where | `document_location` (new, a reference) | security | documents | the sheet | 0070 | yes |
| Preferred emergency facility | `preferred_emergency_facility` (new) | location | home | the sheet, an ambulance | 0070 | yes |
| Address | `home_address` (new) | location | home | ambulance, evacuation | 0070 | yes |
| Dwelling type (house or flat), floor and lift | `dwelling_type` (choice), `floor` (integer), `has_lift` (choice) (new) | location | home | access, evacuation | 0070 | yes |
| How to get in (gate, concierge; never a code) | `home_access_note` (new, a reference) | location | home | an ambulance | 0070 | yes |
| Lives alone | `lives_alone` (new, choice) | location | home | initiative, inactivity (with the address it is a burglar's map, so it is read at `strong`) | 0070 | yes |
| Emergency contacts, caregiver, doctor, key holder, neighbour, trusted person: name, relationship, a phone and an optional second one, call order, key, whether they may be told health information, whether they may later see the owner's activity events | `care_contacts` | private (`location` when the contact holds a key) | contacts | fall alert, the sheet, evacuation, the audience rule | 0070 | yes |
| Children (minor or adult), partner | `child_of`, `partner_of` | child_data, normal | household | contacts, family | exists | yes |
| Pets and their species | `pet_of`, `species` | normal | household | rescuers | exists | yes |
| Parents, grandparents, siblings, grandchildren | `has_parent`, `has_grandparent`, `has_sibling`, `has_grandchild` (new) | normal | | family conversation | 0070 | yes |
| People who must not receive information | `withhold_from` (new relation) | private | withhold | the audience rule of CM-5 | 0070 | yes |
| Who knows an alarm code, a safe, a bank card | `secret_holder` (new, a reference) | security | secrets | CM-5, CM-7 | 0070 | yes |
| Tastes (likes, dislikes, prefers) | `likes`, `dislikes`, `prefers` | normal | | conversation | exists | yes |
| Topics not to touch | `private_topic` | normal (its content may be health or grief: revisit its default with CM-5) | | CM-5 | exists | yes |
| Who interviewed, the owner's confirmation, the file, the counts, the backup, the consents (biometric, telemetry, remote support, backup and its destination label), a random installation id | `commissioning_records` | n/a | | provenance, audits, the operations plane of ADR 0025 | 0070 (the table, shipped), 0072 (the values, shipped) | yes |
| Each section's status | `commissioning_sections` | n/a | | knowing what was never asked | 0070 | yes |

A phone is written in international format (`+56912345678`); the writer rejects anything else so a
later alert never has to guess a country code. A contact with no call order is **never called by
an alert**; the order belongs to the person, and both of their phones are tried in the order the
alert decides.

## Capabilities and what they need

The alta ends with a **readiness report** (ADR 0024 decision 14): for each row, whether its data is
present (derived from the statuses and the rows) and whether its hardware and software are
*supported, configured and verified* (checked by a person). A capability is ready only when both are;
filling in the form never turns one on. *State* is today's: `exists`, `planned` (in the roadmap) or
`idea` (named by Pipec, not planned).

| Capability | State | Data it needs from the pool | Hardware and software it needs |
|---|---|---|---|
| Speak a reply | exists | none | a speaker, the voice model |
| Understand speech | exists | the seeded names, as hotwords (optional) | a microphone, the speech model |
| Recognize the owner by face | exists, flag off | the face session, consent | a camera |
| Recognize the owner by voice | exists, flag off | the voice session (three or more references), consent | a microphone |
| Remember a taste the owner states | exists, switch off | both biometrics enrolled | none beyond the above |
| Describe a scene | exists | `function` (vision) | a camera, the vision model |
| Answer the profile by voice (name, birth date, partner, parents, tastes) | planned (CM-5) | the profile sections | the structured reader of CM-5 |
| The audience rule («don't say X in front of visitors») | planned (CM-5) | `withhold_from`, `private_topic`, `may_receive_health_info`, `household` | presence detection (a second face), the reader |
| Address the owner as they like | planned | `preferred_name`, `address_form`, `hearing` | the prompt |
| Call a contact, raise an alert | idea | `contacts` with a phone, an order and a role | **telephony or a VoIP/GSM line**, an audio path, a tested call |
| Detect a fall and warn | idea | `contacts`, `takes_anticoagulant`, `function`, `lives_alone`, `conditions` | a detector that has been measured (camera or sensor), the alert above |
| The sheet read to a paramedic | idea | `conditions`, `allergies`, `medications`, `devices`, `documents`, blood type, `home`, `contacts` | the care policy, a way to identify the paramedic |
| Evacuation and rescue advice | idea | `home` (address, dwelling, floor, lift), `function` | connectivity for official information, a tested procedure |
| Locate a person inside the home | idea | places (pending) | presence sensors (P2.1) |
| Remind a medication | idea | `medications` (a structured schedule later) | a scheduler, the speaker |
| A fingerprint, iris or chip as a way in | idea | the modalities inventory | a reader and its adapter (an ADR sets its assurance) |
| Send the health of the machine to an operator | idea (no SaaS yet) | the `telemetry` consent, the installation id | an agent that opens the connection itself, a closed list of commands (ADR 0025 decision 9) |
| A remote support session | idea | the `remote_support` consent | a VPN or tunnel, opened by the owner at the robot |
| An encrypted backup off the robot | idea | the `backup` consent and its destination label | a backup tool and a destination (ADR 0025 decision 6) |
| The operator's test chat in public mode | idea | none (it sees no household data) | the support tunnel, the existing public chat |
| Show a family member the owner's activity events from a web page | idea | `contacts` (`may_view_activity`), a consent per person and purpose | the SaaS, an event projection published by the agent, the care profile and legal advice (ADR 0025 decision 12) |

## Not stored in Phase 0, and why

| Datum | Why | Revisit |
|---|---|---|
| National identity or passport number | No purpose that a card in the owner's pocket does not serve better | A clinic integration, with an ADR |
| Any secret's value (alarm, safe, bank PIN, card number) | A voice or a face can be replayed (ADR 0016 §9) | Never as a value |
| Spoken language | The product speaks Spanish always (a standing product rule) | Never in the file |
| Religion and beliefs | The law treats them as sensitive and `private` does not say so | Legal advice, then an ADR |
| Mental health, substances | Clinical and legal advice first | The `care` ADR |
| Sleep and meals routine, memory and orientation, daily activities | Their consumers (inactivity, patience) are far; asked in the next interview level | A later interview plan |
| Where gas, water and electricity are cut off | No consumer before the sensors | P2.1 |
| Photographs and audio in the import file | Face and voice have their own consented flows | Never in the file |
| Medication schedule as a structured model | Its consumer is a reminder service, not planned | When reminders are planned |

## Adding a field

A new field needs: a sentence saying what it is for and which capability it feeds, a destination
from the table at the top, its sensitivity, a decision on whether it carries a status (and which
section), and a bump of the pool version. Without the purpose sentence it is not added.
