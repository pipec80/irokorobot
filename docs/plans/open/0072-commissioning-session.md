# 0072 — Step 0, third plan: the commissioning session (the alta of the robot)

> **Status:** `Draft`, **an outline** (written 2026-10-23). It is not executable and not `Ready`: its tasks
> are named but not detailed, because they depend on what [Plan 0070](0070-seed-load-data-pool-storage.md) and
> [Plan 0071](0071-seed-load-file-importer.md) leave in the code, on hardware sessions and on decisions Pipec has
> not made (below). Queue rule 4 applies: when Plan 0071 closes, this plan is re-audited against the merged code and
> rewritten in the format of Plan 0070 before Pipec can promote it. It implements the rest of
> [ADR 0024](../../adr/0024-seed-load-senses-secrets-and-channels.md) (decisions 13, 14 and 15), and when it closes the
> ADR becomes `Accepted`.

**Why it exists.** Pipec's definition of Phase 0 is the **alta** of the robot: a conversation in which an interviewer
and the owner fill in a form that loads what the robot needs to work, and in which the interviewer enrols face and
voice, so that the tools defined now and later find their data and their hardware ready. Plans 0070 and 0071 give the
database the places and the tool that loads the form. This plan gives the session: the earlier onboarding work
(`just setup-personal`, `just onboard`, `just speaker-auth-demo`, the face and voice scripts, the reading script and
corpus recorder of Plan 0069) recovered into **one guided flow**, with room for biometric inputs that do not exist yet.

**Goal (to be confirmed at the re-audit).** One command, `just commission`, driven by the state of the database (as
`scripts/onboard.py` is), that tells the interviewer the exact next step and never asks for the server to be both on and
off: it walks the checklist of ADR 0024 decision 13, records everything that is not a household value in the commissioning
record, produces the readiness report of decision 14 and the acta, and closes the window.

## What the session contains

| Step | Content | Built from |
|---|---|---|
| Preflight | The `.env` flags, the declaration about disk encryption, the tag `pre-step0`, the backup of the old database with its path and destruction date | `reset_db.ps1` (Plan 0071), the commissioning record (Plan 0070) |
| Owner | The owner and the PIN the owner chooses | `personal_setup` |
| Notice and consent | The biometric notice read to the owner and the consents recorded, with the notice's version; also the consents for the operations plane of [ADR 0025](../../adr/0025-remote-administration-backup-updates-and-telemetry.md): telemetry, remote support and backup (with a label for its destination). A consent builds and enables nothing | `face_consent_grants`, `voice_consent_grants`, the record's `consents_json` and `installation_id` |
| Face session | Several frames, not one: distance, glasses, lighting (the matrix of Plan 0030) | `scripts/onboard.py`, the face endpoints |
| Voice session | The reading script; three or more voice references; a level and distance check of the microphone; the per-person settings the speech-to-text benefits from, measured and not asked; the seeded names as hotwords; optionally how the owner pronounces their own and their family's names | Plan 0069's script, corpus recorder and bench; the speaker endpoints |
| The load | The dry run, the owner's review, the apply, the second dry run | Plan 0071 |
| Verification | A turn by face and voice; the children's list and count | existing routes |
| Readiness report | For each capability of the catalogue: data present (derived) and hardware supported, configured, verified (typed by a person) | the catalogue's capability table |
| Closing | The baseline backup (path, destruction date), the modalities enrolled, the marker `closed_at`, the acta without household values, the import file destroyed | Plan 0070's `close_commissioning` |

## Decisions Pipec must make before this plan is detailed

1. **One command or a runbook.** A `just commission` state machine (recommended: it cannot skip a step) or a document that lists
   the existing commands in order.
2. **Where the voice's per-person settings and the pronunciations live.** They are measurements, not interview answers: a table
   of their own (a later migration) or the per-person section of the settings. And whether a pronunciation field joins the pool.
3. **The biometric notice.** Its text and its version, and whether Pipec wants it reviewed legally before the first real use.
4. **The readiness report's hardware list.** Which items a person ticks for each capability, and what «verified» means for each (a test
   call, a measured detector, a speaker check).
5. **The acta.** Its format (a Markdown file under `data/`, ignored by git) and who keeps it.
6. **How many face frames and voice references** (Plan 0030 and Plan 0047 measured on one microphone and one camera; the Raspberry
   Pi will need them again).
7. **When the real database is reset.** Not before this plan can enrol face and voice again, so the owner is never left without them.
8. **The amendment path** for contacts and medications after the closing (ADR 0024 decision 8): it can be part of this plan or a
   later one, but a capability that depends on them (an alert, a reminder) must not be enabled before it exists.

## Tasks (outline)

| # | Task | Notes |
|---:|---|---|
| 0 | Re-audit against the merged Plans 0070 and 0071; detail this plan; Pipec confirms the decisions | |
| 1 | The record's session details: `record_session_details` (consents, notice version, modalities, backups), the readiness report column, the acta | uses Plan 0070's columns |
| 2 | The capability table as data and the pure data-readiness evaluator | reads statuses and rows, never typed by hand |
| 3 | The hardware checklist: the typed `supported`, `configured`, `verified`, `enabled` per capability | human-entered |
| 4 | The face session: several frames | reuses the face endpoints |
| 5 | The voice session: script, references, level check, per-person settings | reuses Plan 0069's tools |
| 6 | The orchestrating command and its status-driven state machine | like `scripts/onboard.py` |
| 7 | The acta writer, the baseline backup record and the closing command | |
| 8 | Documentation truth, ADR 0024 `Accepted`, and Pipec's real commissioning as the acceptance (real data stays local; the record holds outcomes only) | a hardware session |

## Not here

- A fingerprint, iris or chip adapter (the inventory names them; an adapter, its enrolment and an ADR come with the hardware).
- The structured read of the profile by voice, the alert, the call, the paramedic's sheet: CM-5 and the care ADR.
- The interview's interface and the 107-question catalogue: a later Step 0 plan.
