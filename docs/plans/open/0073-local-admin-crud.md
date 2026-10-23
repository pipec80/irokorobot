# 0073 — Step 0, fourth plan: the local administration, a command-line CRUD (the amendment path)

> **Status:** `Draft`, **an outline** (written and rewritten 2026-10-23). Not executable and not
> `Ready`: queue rule 4 applies, so when Plan 0072 closes this plan is re-audited against the merged code and
> rewritten in the format of [Plan 0070](../completed/0070-seed-load-data-pool-storage.md) before Pipec can promote it. It
> implements the local half of [ADR 0025](../../adr/0025-remote-administration-backup-updates-and-telemetry.md)
> (decisions 2 and 4) and is the **amendment path** that [ADR 0024](../../adr/0024-seed-load-senses-secrets-and-channels.md)
> decision 8 says is missing after the closing.

**Why it exists.** After the alta the importer refuses to run and the voice only stores tastes, so a phone, a
medication or a contact could not change. A CRUD makes the loaded data editable without a re-interview, and every
edit goes through the same canonical writers, with provenance and an audit that holds no value.

**What changed from the first outline.** It was a web page. Pipec's concern (2026-10-23) is that a web service is a
new port to attack and a framework to build, and today he is the only operator. So the first form is a **command-line
tool run on the machine over SSH**, with no new network service. A web page (bound to loopback and reached with an
SSH tunnel) is a later, separate plan for the day a person who is not technical must edit; it is not part of this one.

**Goal (to be confirmed at the re-audit).** On the machine that runs the server, an administrator who reached it by SSH
(key only) runs `iroko-admin` to list, add, change and revoke the data of the pool (the catalogue's sections, the contacts,
the statuses), to approve or reject pending candidates, and to see the audit of the changes. Nothing new is reachable from
the network.

## Scope

| In | Out (ADR 0025, later plans) |
|---|---|
| One console script, `iroko-admin`, with sub-commands (`list`, `add`, `change`, `revoke`, `status`, `candidates`, `audit`), written with `argparse` like `personal-setup` | A web page, LAN or VPN exposure, TLS, passkeys |
| The machine's access (SSH) as the authority, as for the importer (ADR 0024 decision 11); the PIN for anything that touches the data of someone who is not the administrator | The remote superadmin and the support session |
| Every change through the canonical writers and `write_contact`, with a new channel `admin_local` | Hard delete and forgetting (CM-6) |
| A section's status edited after the closing, with the amendment recorded | The periodic job and storing conversations (CM-4) |
| An audit of each operation, with no value | Backup, updates, telemetry |
| Pending candidates listed, approved or rejected | Reading the profile by voice (CM-5) |
| `export` to the importer's own TOML (the round trip) | A readable copy of the data outside the machine (ADR 0025 decision 12) |

## Decisions Pipec must make before this plan is detailed

1. **Where the audit lives.** A new table (a migration) of operations with no value, and how long it is kept.
2. **What needs the owner's PIN** when the administrator is the builder and the owner is someone else (ADR 0025 decision 4); this
   plan can assume the builder is the owner and refuse otherwise until the support session exists.
3. **What an amendment is.** A record per edit session, or a row per operation only.
4. **The interface of the sub-commands.** A field is named by its catalogue id (`medication`, `care_contacts`), a value is read
   from the command line or from standard input (so a medication never lands in the shell history), and every sub-command
   asks for confirmation before writing and has a dry-run flag.
5. **The name** of the console script and where it is installed (`server/pyproject.toml`).

## Tasks (outline)

| # | Task | Notes |
|---:|---|---|
| 0 | Re-audit against the merged Plans 0070 to 0072; detail this plan; Pipec confirms the decisions | |
| 1 | The audit table and the operation log, with no value | a migration |
| 2 | `iroko-admin list` and `status`: the pool and the sections' statuses, read through the existing readers | no value printed to a log |
| 3 | `add`, `change`, `revoke` for the pool fields and the contacts, through the writers, with the owner's PIN for sensitive data of someone else | one writer, new channel `admin_local`; an architecture guard against SQL in the tool |
| 4 | The statuses after the closing and the readiness report recomputed | reuses Plan 0072's evaluator |
| 5 | `candidates`: list, approve, reject | a second confirmation channel for ADR 0021 |
| 6 | `audit`: show the operations with no value | |
| 6b | `export`: write what is loaded to the **same TOML** as the importer reads (no secrets; it holds real data, so it warns and writes under `data/`), so the interviewer can compare it with the original sheet; a test loads the export into a fresh database and gets identical rows | the round trip of ADR 0025 decision 11; needs an administrator's read of the raw tables, so it is the tool's one read module |
| 7 | Documentation truth; ADR 0025 stays `Proposed` (the remote half is unwritten); acceptance by Pipec on his machine, outcomes only | |

## Not here

- A web page of any level, and everything remote: the VPN, the support session, the backup, the updates, the telemetry and the
  periodic job (ADR 0025).
- Reading the profile by voice (CM-5), forgetting (CM-6), conversation storage (CM-4).
