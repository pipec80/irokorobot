# 0025 — Administering a local-first robot: the surfaces, support sessions, backup, updates and telemetry

- **Status:** Accepted (2026-10-28, when [Plan 0073](../plans/completed/0073-local-admin-crud.md),
  the first plan that implements it, closed — the local half, decisions 2 level A, 4, 10 and 11;
  the remote half, decisions 5 to 8, has no plan yet). Proposed 2026-10-23. Written from Pipec's brief of the same day and his answers to four
  questions (the robot as the only source of truth; a support session opened by the owner; a periodic
  job that only proposes; the local CRUD closing Phase 0 and the remote part apart) and to three more
  the same day (**no SaaS for now**; a remote chat test in public mode; the installation id and the
  consents captured at the alta) and to three more later the same day (the amendment path is a **command-line
  tool over SSH first**, with the web page as a later option; the operator may fill Excel or CSV and a
  converter produces the TOML; the security of the audio port is **not** registered for now) and to three
  more afterwards (the SaaS holds **only encrypted backups**, never a readable copy; the contacts carry a
  `may_view_activity` flag; the command-line tool gets an `export`). Every
  decision below is the author's recommendation; those answers are Pipec's. It becomes `Accepted` when
  the first plan that implements it closes.
- **Date:** 2026-10-23
- **Builds on:** [ADR 0004](0004-local-first-cognitive-policy.md),
  [ADR 0006](0006-personal-and-family-companion-profiles.md),
  [ADR 0009](0009-locked-posture-and-scoped-capabilities.md),
  [ADR 0013](0013-local-http-network-posture.md),
  [ADR 0015](0015-owner-grant-scope-and-speaker-binding.md),
  [ADR 0021](0021-memory-candidates-and-the-canonical-writer.md),
  [ADR 0022](0022-household-rules-and-third-party-memory.md),
  [ADR 0024](0024-seed-load-senses-secrets-and-channels.md)
- **Amends:** [ADR 0013](0013-local-http-network-posture.md): remote access exists, only through a
  private VPN, and only for the admin router (decision 2); the voice and chat routes keep their
  loopback default.
- **Implemented by:** [Plan 0073](../plans/completed/0073-local-admin-crud.md) (closed 2026-10-28:
  the local CRUD `iroko-admin` that closes Phase 0 — migration 012 and the admin audit, the
  `admin_local` channel, the offline owner PIN, add/change/revoke through the canonical writers, and
  the read-only readiness recompute). The remote part (decisions 3 and 5 to 8) has no plan yet.

## Context

The data of the robot cannot be written in stone. After the alta (ADR 0024) a phone changes, a
medication is added, a taste is removed. Pipec also wants to administer the robot from afar, to see
what the robot knows and let the owner load data in a web page, to back the data up outside the
robot, to send controlled updates, and to see the robot's health, while keeping what has defined the
project from the start: **everything runs locally, with open-source parts, and the robot works with no
Internet.** Facts that shape the design (verified in the code, 2026-10-23):

1. There is no administration surface, no telemetry, no backup and no update mechanism. The only web
   page is the static chat (`chat_ui.py`). ADR 0013 keeps the server on loopback and asks for an explicit
   decision before any LAN or remote exposure.
2. The robot does not keep conversations: continuity lives in memory and is dropped after 180 s of
   silence; the optional text log goes to the console only (Plan 0052). A periodic job over the
   conversations would need them stored, which no decision allows today.
3. ADR 0021 fixes that extraction only **proposes** and that a deterministic writer saves **after the
   owner confirms**; `/chat` cannot confirm because it has no voice.
4. ADR 0006 says a technical administrator does not inherit another adult's private data.
5. The canonical writer (ADR 0022, ADR 0024) is the one place that stores a fact, with a closed list of
   channels; the contacts have their own writer (ADR 0024 decision 5).

## Decision

### 1. The robot is the only source of truth

Every datum lives in the robot's SQLite file. The cloud, the homelab or any other place holds **only
encrypted backups** and never a readable copy or a second writable one. Remote operations are
conveniences: when there is no connection the robot works and is administered on the spot. There is no
synchronization and therefore no conflict between an administrator's edit and what the robot learned
meanwhile. Every component is open source and replaceable.

### 2. The administration surfaces, from the smallest exposure up

*Terminology.* In this ADR «the robot» is the **machine that runs the server and holds the database**
(today Pipec's computer, later a homelab server or the Pi). The electronics (ESP32, microphone, speaker,
sensors) are clients of it. The server is also the generic audio API of ADR 0002; administration is part
of the server and does not move that boundary.

| Level | Surface | Exposed port | State |
|---|---|---|---|
| **A** | A command-line tool, `iroko-admin`, run on the machine over **SSH** (key only) | SSH only | **Chosen by Pipec (2026-10-23) for the amendment path** |
| **B** | A web page bound to **loopback**, reached with an SSH tunnel (`ssh -L`) | SSH only; the web port is not reachable from the network | Later, when a person who is not technical must edit |
| **C** | A web page reachable on the network, with TLS, accounts and rate limits | A web port | Not recommended; needs its own decision |

- **Reaching the machine** is SSH with keys only (ed25519, password login off, a firewall that limits who
  can reach it) or a WireGuard tunnel, which does not answer a packet from someone without the key. On the
  Pi it is a standard Linux setup; on the Windows development machine it is the optional OpenSSH Server.
  The robot is **never** exposed to the Internet and the owner unlock is never exposed through a proxy
  (ADR 0013). Nothing in this ADR opens a port other than SSH or the VPN.
- **If a web surface is built (level B)** it is a separate FastAPI router (`/admin`), **off by default**,
  server-rendered with Jinja2 and HTMX (no JavaScript build), on the same process and the same canonical
  writers, bound to loopback. FastAPI and not Django: the writers, the PIN and its scoped grants, and the
  tests are already here, and Django would bring a second user system and an ORM that competes with the
  one writer of the project.
- The voice and chat routes keep their loopback default. **The port the electronics will use** when they
  are separate devices is a different problem (it has to listen on the network and needs a credential per
  device); it is not decided here.

### 3. Who may do what, and the support session

| Role | May | Authentication |
|---|---|---|
| `owner` | See and change their own data; approve or reject proposals | The PIN (a passkey later), as a scoped, expiring grant |
| `superadmin` (the builder) | Version, health, schema, backups (opaque), updates, the audit view; **no household data** outside a support session | An SSH key on the machine (or the VPN); the PIN for anything that touches someone else's data |
| `interviewer` | During the commissioning only, through the importer (ADR 0024) | The machine's access |
| `family`, `caregiver` | Not now: the `family` profile and the care ADR | — |

An administrator's access to sensitive data of someone else (health, contacts, locations, references)
requires a **support session**: the owner opens it **at the robot** with their PIN, for a stated scope
(the sections) and a limited time (a default of one hour, a ceiling of eight), the robot says it is
active, it ends by itself or when the owner revokes it, and it is recorded in the audit. When the owner
is the builder the session adds nothing. An admin grant is scoped like every grant of ADR 0015: one
purpose, expiring, never a master session.

### 4. A CRUD is a set of operations on the canonical writers

- The router never touches SQL: create, change and revoke call the canonical writers (ADR 0022, ADR 0024)
  with two new channels, `admin_local` and `admin_remote`. A change is a supersede (the old row stays as
  history, protected like the data itself); a hard delete is CM-6.
- Changing the data of someone else, or any `medical`, `location`, `security` or contact datum, needs the
  owner's verification at that moment (a grant spent), unless the actor is the owner.
- Every operation writes **one audit event**: actor, role, channel, operation, section or field id,
  outcome and time; **never a value**. An architecture guard keeps the router away from the tables.
- Undo is a new operation that restores the previous row. The readiness report of ADR 0024 decision 14
  can be recomputed from the admin at any time.

### 5. The periodic job proposes; it never writes

A job that runs on the robot when it is idle (never inside a turn) may analyse **locally stored**
conversation text and create **candidates** (ADR 0021), never facts. The owner approves them by voice or
in the admin with their PIN (a second confirmation channel for ADR 0021). Storing conversation text is a
decision of its own, taken with the protected episodes (CM-4): local only, never leaves the device,
consent given at the alta, a short retention window, deletable, covered by the disk encryption floor. No
code before CM-4. *Answered by [ADR 0027](0027-conversation-record-and-the-diary.md) and implemented by
[Plan 0076](../plans/completed/0076-cm4-conversation-record-and-diary.md) (2026-10-30): the record is local text behind the `conversation_storage`
consent, 365 / 30 days, deletable under the PIN; the diary job writes episodes only, and candidates
still come from the live path.*

### 6. Backup

Consistent snapshots with SQLite's online backup (never a copy of the open file), encrypted on the robot
with a key that the owner and the superadmin hold, sent to the homelab first and to a cloud object
store later. Candidate tools, to be chosen in the plan: restic or borg for versioned snapshots, Litestream
for continuous replication. A backup is a copy of everything (ADR 0024 decision 4): its retention and its
destruction date are recorded, a restore is tested before it is trusted, and the face and voice
embeddings are **excluded by default** (the owner may include them; after a restore the owner is enrolled
again).

### 7. Updates are controlled, pulled and reversible

The robot **checks** a release source (the homelab or the repository) only inside a maintenance window the
administrator opens, verifies an open-source **signature** (minisign or sigstore), takes a backup,
installs the new version beside the old one, runs the forward-only migrations (the schema is already
versioned), runs a health probe and **rolls back** if it fails. It never updates during a conversation, a
version is pinned, a changelog is shown, and being offline only means no update. Changing data is not an
update: it is decision 4. The operating system of the Raspberry Pi (RAUC, Mender or a plain image) is a
separate layer decided with the hardware.

### 8. Telemetry carries no household value

Health, version, uptime, latencies, error counts, disk and temperature, the age of the last backup: no
name, transcript or value (the rule of the logs). It is exposed as a text endpoint for a collector on the
homelab (Prometheus, optionally Grafana) over the VPN, or pushed; the robot never waits for it.

### 9. Three planes and a ladder of connection

What the robot holds is split in three planes, and each has its own reach.

| Plane | Holds | Leaves the robot? |
|---|---|---|
| **Data** | The household's data (contacts, medications, tastes, conversations) | **Never readable.** Only encrypted backups |
| **Operations** | Health of the machine (CPU, memory, disk, temperature, service state), version, errors, latencies, the activity of the sensors without personal values | Yes, **only if the owner consented at the alta** |
| **Support** | Seeing or editing data, the test chat, a console | Only inside a support session the owner opens (decision 3) |

The ladder: **level 0** no connection, everything works; **level 1** outbound telemetry and a closed list
of commands, optional; **level 2** a support session opened by the owner; **level 3, never**: anyone
reaching the robot from the Internet without the robot starting the connection.

**No SaaS for now (Pipec, 2026-10-23).** Pipec has a SaaS project whose first client could be Iroko. The
direction, when it is decided, is an **agent**: a small separate process on the robot that **opens the
connection itself** (so the house needs no open port and it works behind any router), sends the operations
plane with a local queue for when there is no Internet, and receives only commands from a **closed list**
(restart a service, collect a diagnostic, open a support window, fetch a signed update), each audited, never
a free shell. The contract (telemetry schema and command list) belongs to Iroko and is independent of the
SaaS's framework. The agent reads the machine with a library such as `psutil` plus the board's temperature
and the state of the services; the sensor nodes (an ESP32 is a microcontroller with no disk, which can report
free memory, uptime, signal strength and, by variant, temperature) report **to the Pi**, which includes them,
instead of reaching the SaaS directly (the Pi against microcontroller boundary is P4.2). Until then the only
surface is the command-line tool (and, later, the loopback web page) of decision 2.

**The remote chat test.** An operator may talk to the robot's chat **in public mode** (as a stranger, with
no household data) to diagnose it; seeing more needs a support session. Speaking to the owner through the
robot (a message the robot says aloud) is a different capability with its own consent and is not decided here.

### 10. The alta records the installation and the consents

The commissioning record (ADR 0024) holds a random **installation id** (generated at the alta, derived from
nothing about the house or the hardware) and the owner's consents for the operations plane: telemetry,
remote support and backup (with a label for its destination). This is captured now so the owner is never
interviewed again when the agent is built; recording a consent builds nothing and enables nothing.
Plan 0072 (closed 2026-10-27) records the three consents and the destination label in the acta
(`just commission`), and they stay fixed once the commissioning closes.

### 11. One contract, many doors

Every way of entering or changing the household's data (a spreadsheet converted to TOML, a future form, the
command-line tool, a future inbox of changes from a SaaS) must produce the **same versioned change set**: the
`SeedOperation`s of Plan 0071, described by a committed JSON Schema. One validator and one applier write it
through the canonical writers; no front end writes SQL, calls a writer by itself or re-implements the rules.
The same shape is the **export** (SQLite to TOML, without secrets), so a load can be verified by comparing it
with the original sheet and the round trip is tested. Adding a front end is adding a door to this contract,
never a second way of writing.

### 12. What a SaaS may hold

| Held by the SaaS | Privacy cost | Verdict |
|---|---|---|
| The machine's health | None | Allowed, with the `telemetry` consent |
| **Events the owner agreed to share** with a named person (for example «no answer», «fall detected», «low battery»), published by the agent as a projection and shown to that person | They are personal data of an adult: a consent per person and purpose, legal advice, the `care` profile | Later; the alta only records `may_view_activity` per contact |
| **Changes** that a family member or operator sends, waiting in an inbox until the robot pulls them and applies them (with approval by sensitivity) | The SaaS holds changes in transit, not the database | Later |
| **Encrypted backups** that only the owner's key restores | Opaque to the SaaS | Allowed, with the `backup` consent |
| A readable copy of the household's data | A fault in the SaaS would expose the health data and contacts of every home | **Rejected** (Pipec, 2026-10-23); it would need its own ADR and legal advice |

### 13. The board never writes the database

Three kinds of data live apart: the household and its memory (the database of ADR 0022 and 0024), the world
state and the sensor series (observations with a source, a time, a confidence and an expiry, kept with a
retention window; ADR 0005 and P2.1), and the machine's health (metrics). The electronics (an ESP32, a
sensor, the Pi's microphone) send **observations to the server**; the server decides what to store. No
firmware, agent or SaaS has a path to the household tables other than decision 11.

## Not decided here

| Subject | Why not now | Owner |
|---|---|---|
| The SaaS contract (telemetry schema, command list, the device's identity and keys) | There is no SaaS yet | The agent plan |
| Messages to the owner through the robot | Another capability, another consent | A later ADR |
| TLS topology, passkeys (WebAuthn) | Needs the real deployment | The first remote plan |
| `family` and `caregiver` roles in the admin | The `family` profile and the care ADR | P3 |
| Which backup tool and which destination | Needs the homelab and the cloud choice | The backup plan |
| Which signature scheme and release source | Needs the hardware and the repository policy | The update plan |
| Operating-system updates of the Pi | Needs the board | The electronics track |
| Storing conversation text, its retention | Protected episodes | CM-4 |
| Several robots | One robot | Never, unless asked |

## Alternatives considered

- **A cloud portal with a change queue.** Edits without reaching the robot, but it needs synchronization,
  conflict resolution and a readable copy outside the robot. Rejected by Pipec.
- **Permanent administrator access to all data.** Contradicts ADR 0006 when the owner is another adult.
  Rejected by Pipec.
- **A job that writes inferred tastes.** Breaks ADR 0021. Rejected.
- **Editing the SQLite file with a generic tool.** No audit, no classification, no provenance. Rejected.
- **A readable copy of the data in the SaaS** so the interface can show and edit it. Simpler, but it turns
  the SaaS into the most valuable target for every home. Rejected for now (decision 12).
- **A different front end, a different way of writing, for each door.** Work done twice and rules that
  drift. Rejected (decision 11).

## Consequences

### Positive

Data can change after the alta without a re-interview; the robot never depends on the network; a remote
administrator is bounded by the owner's consent; every change is traceable without exposing a value;
updates and backups are reversible.

### Negative

An admin surface is a new attack surface on a device that holds household data; without a connection the
administrator must be on the spot; the support session needs the owner's presence once; the periodic job
waits for the decision to store conversations; several plans of hardware-dependent work follow.

## Test consequences

The command-line tool refuses to run without the machine's access and without the owner's verification for
sensitive data of someone else; if a web router exists it is off by default, bound to loopback and never
mounted on the voice routes; a sensitive change without the owner's verification is refused; an operation writes an
audit event with no value; the router has no SQL (an architecture guard); a support session expires and is
audited; a backup restores to an identical database; an update that fails its health probe rolls back.

## Docs to update

With **Accepted**: ADR 0013 (the amendment), `identity-and-access.md` (the roles and the support session),
`server-production-baseline.md` (the admin surface), the roadmap (a cross-cutting row), `current-state.md`,
and ADR 0024 and the data-pool document (the installation id and the consents, already recorded there).
**Done for the local half with Plan 0073 (2026-10-28):** the ADR 0013 pointer, `identity-and-access.md`,
`server-production-baseline.md`, the roadmap, `current-state.md`, ADR 0024 and the data-pool document.
The roles table and the support session of decision 3 are not built, so they are not documented as code.

## Review

Revisit when the Raspberry Pi is bought, when a second adult is enrolled, when the care profile is decided,
when conversations are stored, or when a connection to the Internet becomes part of a feature.

## Follow-up

- [Plan 0073](../plans/completed/0073-local-admin-crud.md) — the local admin (closed 2026-10-28).
- The backup, update, telemetry, remote-access and support-session plans: not written.
- The next free ADR number is 0026.
