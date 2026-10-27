# 0073 — Step 0, fourth plan: the local administration, a command-line CRUD (the amendment path)

> **Status:** `Ready`/`NOW` — detailed on 2026-10-27 from the 2026-10-23 outline and **promoted by
> Pipec on 2026-10-27** (D-1 to D-9 and C-1 to C-3 confirmed), who chose inline same-session execution
> on the branch `docs/0073-detail-plan` (which carries this plan and its implementation).
> [Plan 0072](../completed/0072-commissioning-session.md) closed on
> 2026-10-27 (PR #216, `c5a5dc9`, and the docs PR #217), so queue rule 4 was applied: this plan was
> re-audited against the merged code of [Plan 0070](../completed/0070-seed-load-data-pool-storage.md),
> [Plan 0071](../completed/0071-seed-load-file-importer.md) and Plan 0072 and rewritten in their
> format before any code. It implements the **local half** of
> [ADR 0025](../../adr/0025-remote-administration-backup-updates-and-telemetry.md) (decisions 2 level A,
> 4, 10 and 11) and is the **amendment path** that [ADR 0024](../../adr/0024-seed-load-senses-secrets-and-channels.md)
> decision 8 names as the write path missing after the commissioning closes. Written for an executor
> who has not seen this repository: what it needs is here, in the ADRs or in
> [`seed-data-pool.md`](../../architecture/seed-data-pool.md), not in the chat that produced them.

> **For agentic workers:** if the status above does not say `Ready`, stop. REQUIRED SUB-SKILLS:
> `superpowers:executing-plans`, `superpowers:test-driven-development`,
> `superpowers:verification-before-completion`, `superpowers:finishing-a-development-branch`.
> **Pipec's rules win over the skills:** one plain branch from `main` (`docs/0073-detail-plan` holds
> this plan; the implementation runs on its own `feat/0073-local-admin-crud` branch), never a git
> worktree, subagents only if Pipec asks, this plan lives under `docs/plans/`. One commit per task;
> every code test observed RED for the stated reason first (the tasks that are text or manual say so).
> If evidence contradicts the plan, stop and report instead of redesigning. The Bash tool of this
> environment loses backslashes and non-ASCII characters in heredocs: use the Write and Edit tools.
> Run the suite with `MEMORY_ENABLED=false` (CI does). Pin the clock in any test with a date. Never run
> `uv sync --all-packages --all-groups` (it removes the optional `cuda` extra: use `--extra cuda`);
> commit `uv.lock` before `just gate` if it changed. **The processes (server) are started by Pipec**,
> never by the agent; the command runs with the server stopped.

**Goal.** After the alta closes, the importer refuses to run and the voice stores only tastes, so a
phone, a medication, an address or a contact can no longer change. This plan gives the machine's
operator a command, `iroko-admin`, run on the server's machine over SSH with the server stopped, to
**see** the loaded pool, the contacts and each section's status, to **add**, **change** and **revoke**
a datum through the same canonical writers the importer uses (channel `admin_local`), and to **see the
audit** of those changes. Every write is a supersede or a revoke-to-inactive, never a hard delete
(that is CM-6); a change to sensitive data (medical, location, security) or to a contact needs the
owner's PIN verified on the spot; every operation that mutates writes **one audit row that holds no
value**. Nothing new is reachable from the network, no route changes and the robot is untouched.

**Architecture.** (1) One migration (012) and one repository, `admin_audit.py`, the only module with
SQL on the `admin_audit` table (an architecture guard), append-only, holding no household value.
(2) A new write channel `admin_local` in `write_types.py`, outside `IMPORT_CHANNELS`, so the existing
writers classify and fence an admin write exactly as they do a voice or import write, and the
import-channel guard does not capture it. (3) An offline owner-PIN check that reuses the single
cryptographic verifier (`cognition/pin_credentials.verify_pin` over `get_active_owner_pin_credential`),
so a sensitive edit can require the PIN with the server stopped. (4) Read functions in the owning
repositories (`relational_v4`, `care_contacts`, `commissioning`) that return the rows for display,
and a read-only recompute of the readiness report; the command holds no SQL. (5) A revoke-to-inactive
in the owning repositories (`relational_v4`, `care_contacts`): a change is history, never a deletion.
(6) An orchestrator, `admin_ops.py`, that applies one change through a writer or a revoke and writes
its audit row in one transaction. (7) A status-free command, `admin_cli.py`, built like `seed_cli`:
`argparse`, a synchronous `/health` probe before `asyncio.run`, injected `read_text`/`write_text`, a
dry run by default and a confirmation before any write.

**Tech Stack.** Python 3.12, aiosqlite, pydantic, httpx (already a dependency; used synchronously in
the command for the health probe, like `seed_cli`), pytest. **No new dependency. One migration (012).
No new route, status code, response field or setting.** One new console script and one `just` recipe.

**Spec:** [ADR 0025](../../adr/0025-remote-administration-backup-updates-and-telemetry.md) decisions 2
(level A), 3 (the owner-verification rule only), 4 and 11; [ADR 0024](../../adr/0024-seed-load-senses-secrets-and-channels.md)
decision 8 (the amendment path) and decisions 5, 6, 7 (the contacts, the channel level, the writers' bypass);
[`seed-data-pool.md`](../../architecture/seed-data-pool.md) (the catalogue and *Capabilities and what they need*);
[Plan 0070](../completed/0070-seed-load-data-pool-storage.md), [Plan 0071](../completed/0071-seed-load-file-importer.md)
and [Plan 0072](../completed/0072-commissioning-session.md) (the interfaces they produced).

## Decisions

Pipec confirmed D-1 to D-9 (and C-1 to C-3 below) on 2026-10-27, which lets the plan be written; it
stays `Draft` until he promotes it.

1. **D-1 — The surface is a command-line tool only** (ADR 0025 decision 2, level A): `iroko-admin`,
   run on the server's machine over SSH, with the server stopped. No web page, no LAN/VPN exposure,
   no TLS, no passkeys, and no new network service. A loopback web page (level B) is a later, separate
   plan. *Cost: a non-technical person cannot edit yet; that is level B.*
2. **D-2 — Every write goes through the canonical writers with a new channel `admin_local`** (ADR 0025
   decision 4). The command never writes SQL on a V4 or contacts table: `add` and `change` call
   `write_literal`/`write_relation`/`write_contact` with `on_conflict=SUPERSEDE`, `revoke` calls a new
   revoke-to-inactive in the owning repository. The classification stays the writer's. *Cost: `revoke`
   needs new repository functions; see D-5.*
3. **D-3 — A sensitive write needs the owner's PIN, verified offline.** A write to `medical`,
   `location` or `security` data, or to a contact, or about anyone but the owner, prompts for the
   owner's PIN and verifies it through the single cryptographic verifier (`verify_pin` over the active
   credential); a write to the owner's own `normal`/`private` data, and every read, does not (ADR 0025
   decision 4, resolved with C-1 below). Multi-adult and `representative` actors are **refused** until
   the support session exists (ADR 0025 decision 3). *Cost: a small offline PIN helper and a lockout;
   it reuses the one hash-check so nothing about the PIN is re-implemented.*
4. **D-4 — One audit row per mutating operation** (ADR 0025 decision 4): `add`, `change`, `revoke`
   each write one row to `admin_audit` (actor label and role, channel, operation, target kind, the
   field or section id, the affected entity id, outcome and time) — **never a value, a name or a
   phone**. A read is not audited. Retention: **append-only, no automatic purge** (the table is tiny
   and holds no value; purging is a later CM-6 concern). *Cost: one migration and one repository.*
5. **D-5 — `revoke` is a supersede-to-inactive, never a hard delete** (ADR 0025 decision 4; a hard
   delete is CM-6). A fact or relation gets a `revoked_at`/`valid_to`; a contact gets its `revoked_at`.
   New functions live in the owning repositories (`relational_v4`, `care_contacts`), which keep the
   SQL. *Cost: one revoke function per repository, each guarded as the repository already is.*
6. **D-6 — The sub-commands.** `iroko-admin list|status|add|change|revoke|audit`, with `argparse` like
   `seed-import`. A field is named by its catalogue id (`medication`, `home_address`, a contact's
   `role`); a **value is read from standard input, never from an argument**, so a medication or a
   phone never lands in the shell history; every write asks for confirmation and honours `--dry-run`.
   **`candidates` and `export` are out of this plan** (see *Not here*). *Cost: author's call; low.*
7. **D-7 — The command installs as a console script** `iroko-admin = "server.admin_cli:main"` in
   `server/pyproject.toml`, with a `just admin` recipe, mirroring `seed-import`. It touches no camera
   or microphone, so the 0072 rule (hardware CLIs live in `scripts/`) does not apply. *Cost: trivial.*
8. **D-8 — `status` recomputes the readiness report read-only and never edits the frozen acta**
   (resolved with C-2 below). It reads the frozen section statuses (`list_section_statuses`) and the
   closed readiness, recomputes which sections hold active rows now, and reports the divergence; it
   calls none of the commissioning writers, which refuse a closed record by design. *Cost: one small
   read-only derivation; it reuses `commissioning_readiness.evaluate_readiness`.*
9. **D-9 — The authority is access to the machine, plus the PIN for sensitive writes** (ADR 0025
   decision 11, like the importer). The command refuses to run if the server answers `/health` or the
   database is locked, never creates a database or a schema, needs an existing one at the latest
   version, and prints the database it uses. It never creates the owner. *Cost: none beyond `seed_cli`'s
   pattern, reused.*

### Contradictions resolved before this plan (reported to Pipec, confirmed 2026-10-27)

- **C-1 — the authority (ADR 0024 decision 11 vs ADR 0025 decision 4).** ADR 0024 decision 11 says
  access to the machine is enough (no PIN), as for the importer; ADR 0025 decision 4 says a sensitive
  or other-person change needs the owner's verification. **Resolved:** ADR 0025 decision 4 governs the
  CRUD, because a targeted sensitive edit is riskier than a reviewed bulk load; the offline PIN of D-3
  is the verification. This plan edits ADR 0024's follow-up pointer to say so (Task 7).
- **C-2 — editing a section status after the closing (the outline vs the freeze).** The outline asked
  to edit a section's status after the closing, but `set_section_status` and every acta writer refuse
  a closed record (`_read_open` raises `CommissioningClosedError`; the freeze of ADR 0024 decision 8).
  **Resolved:** `status` **recomputes** the readiness read-only and never edits the acta (D-8). A data
  change is recorded only in `admin_audit`.
- **C-3 — ADR 0025's status at close.** ADR 0025 says it becomes `Accepted` when the first plan that
  implements it closes, and this plan implements its local half. **Resolved:** closing Plan 0073 moves
  ADR 0025 to `Accepted` (Task 7); its *Follow-up* records that the remote half (decisions 5 to 8) has
  no plan yet.

## Review Focus

The failure modes the tasks' main tests would miss; each line has its test in the task named.

1. **The audit row holds no value:** a canary medication, phone, address or contact name written or
   revoked through the command is absent from every `admin_audit` row, from `read_text`/`write_text`
   output that a log could capture, and from the record's `repr` (Tasks 1, 4, 5).
2. **A sensitive write with no PIN, or a wrong PIN, writes nothing and is not audited as applied:** a
   `change` of a `medication`, a `home_address` or a contact without the owner's PIN is refused before
   any write, and a wrong PIN (after the lockout) refuses likewise; a `revoke` of the same is refused
   (Tasks 3, 4, 5).
3. **`admin_local` is a write channel but not an import channel:** it is in `WriteChannel`, outside
   `IMPORT_CHANNELS` and `VOICE_CHANNELS`, and the import-channel architecture guard does not flag the
   admin modules for naming it (Tasks 2, 6).
4. **A revoke is history, not a deletion:** after `revoke` the row still exists with `revoked_at`/
   `valid_to` set and the readers no longer serve it; a second revoke of the same id is a no-op, not an
   error (Task 5).
5. **The command refuses the wrong server state and a closed-record edit path:** an `iroko-admin` run
   while the server answers `/health` is refused with the next step named; `status` never calls a
   commissioning writer and so never raises `CommissioningClosedError` on a closed robot (Tasks 6, 8).

## Global Constraints

- **The plan of operations is the one contract for entering and changing data** (ADR 0025 decision 11):
  the admin CRUD produces changes applied through the same canonical writers as the importer; no front
  end writes SQL or calls a writer by itself. The writer assigns the classification; no caller passes
  one.
- **No real household data anywhere:** invented canaries (`scripts/check_reserved_terms.py`), invented
  phones such as `+56900000001`. The `admin_audit` table and every log carry **no** household value;
  the actor's label is the only free text and never reaches a log or a `repr` (as the interviewer label
  does today). A value appears only on the terminal of the person who runs the command.
- The constraints of [Plan 0070](../completed/0070-seed-load-data-pool-storage.md) and
  [Plan 0071](../completed/0071-seed-load-file-importer.md) apply unchanged (`.claude/rules/`: English
  identifiers, Google docstrings, type hints, no `print()` outside a CLI adapter, logging with `%` and
  never a value, specific exceptions chained, `pathlib`, `match` for dispatch, functions about 30 lines,
  files about 200, `Any` only with its reason; the writer assigns the classification; commit titles at
  most 72 characters; `ruff` over explicit paths including `scripts/`; `mypy server/src robot/src` and
  `pyright` clean).
- **The command performs the health probe synchronously before `asyncio.run`** (the pattern of
  `seed_cli.main`), with the port from the settings; it must not construct an `httpx.AsyncClient`
  (the architecture guard allows it only in the lifespan) and must not block the event loop.
- `db.transaction()` is not reentrant: a repository joined to a caller's transaction passes
  `manage_transaction=False`. Each admin operation (the write and its audit row) is one transaction or
  nothing.
- No new route, status code, response field or setting. `robot/src`, `/chat`, `/transcribe`, the policy
  (`cognition/authorization.py`), the spoken dialogue, the seed importer (`memory/seed_*`) and
  `personal_setup.py` are **not** edited.

## Required reading

- `AGENTS.md`, `docs/architecture/implementation-guardrails.md`, `.claude/rules/` (including
  `scripts-powershell.md` and `fastapi.md`).
- [ADR 0025](../../adr/0025-remote-administration-backup-updates-and-telemetry.md) (decisions 1 to 4,
  9 to 13), [ADR 0024](../../adr/0024-seed-load-senses-secrets-and-channels.md) (decisions 4 to 8),
  [`seed-data-pool.md`](../../architecture/seed-data-pool.md),
  [`identity-and-access.md`](../../architecture/identity-and-access.md) (the channels, the scopes, the
  support session), [`memory-and-world-state.md`](../../architecture/memory-and-world-state.md) (the
  writer, the contacts, the revoked status), Plans 0070, 0071 and 0072 (the interfaces and the
  execution records).
- `server/src/server/memory/{canonical_writer,write_types,care_contacts,commissioning,relational_v4,predicate_registry,declarative,seed_import,seed_run}.py`,
  `server/src/server/memory/commissioning_readiness.py` (`evaluate_readiness`, `Capability`,
  `CATALOGUE`, `HardwareStatus`, `Verdict`, `readiness_to_json`),
  `server/src/server/memory/owner_credentials.py` (`get_active_owner_pin_credential`, `get_ready_owner`),
  `server/src/server/cognition/{pin_credentials,owner_authentication}.py` (`verify_pin`; how `unlock`
  verifies today), `server/src/server/memory/entity_labels.py` (`get_person_label`),
  `server/src/server/seed_cli.py` (the command shape, the health probe, injected adapters, the
  server-stopped refusals), `server/src/server/{db,exceptions,settings}.py`, `scripts/reset_db.ps1`,
  `justfile`, `server/pyproject.toml`.
- `server/src/server/memory/migration_011_contacts_and_commissioning.sql` (the migration convention),
  `server/src/server/memory/migration_010_asserter_and_channel.sql`.
- `tests/unit/test_architecture_guards.py` (the import-channel, care-contacts, commissioning and
  command-dependency guards and their detection tests),
  `tests/integration/test_seed_cli.py`, `tests/integration/test_care_contacts.py`,
  `tests/integration/test_commissioning.py`, `tests/integration/test_memory_v4_schema.py`.

## Permitted files

- Production: new `server/src/server/memory/migration_012_admin_audit.sql`;
  new `server/src/server/memory/admin_audit.py`; new `server/src/server/memory/admin_ops.py`;
  new `server/src/server/admin_cli.py`; `server/src/server/memory/write_types.py` (the new channel);
  `server/src/server/memory/{relational_v4,care_contacts}.py` (the revoke and admin-read functions);
  `server/src/server/cognition/owner_authentication.py` **or** a small new
  `server/src/server/memory/admin_pin.py` (the offline PIN check — Task 0 decides which, see Task 3);
  `server/src/server/{db,exceptions}.py`; `server/pyproject.toml` (one script); `justfile` (one recipe).
- Tests: the files named in each task and their new files.
- Docs (Task 7): the list there.

No new route, status code, response field or setting. `robot/src`, the policy, the spoken dialogue,
the seed importer and `personal_setup.py` are not edited.

---

## Task 0: Revalidate the baseline

- [ ] **Step 0:** this plan says `Ready` and Pipec confirmed D-1 to D-9 and C-1 to C-3 in writing.
  Otherwise stop.
- [ ] **Step 1:** `git checkout main && git pull`, a clean tree, `git checkout -b feat/0073-local-admin-crud`.
- [ ] **Step 2:** `just gate` with `MEMORY_ENABLED=false`; record the count (4814 at `c5a5dc9`,
  otherwise the count of `main` now).
- [ ] **Step 3: Re-audit** (each must find what the plan names, or a difference is reported before any
  code): the writers take `on_conflict` and `channel` and the three channels exist
  (`rg -n "on_conflict|class WriteChannel|IMPORT_CHANNELS|VOICE_CHANNELS" server/src/server/memory/write_types.py server/src/server/memory/canonical_writer.py`);
  `migration_011` is the last migration and `latest_schema_version()` returns 11
  (`rg -n "_MIGRATIONS|latest_schema_version" server/src/server/db.py`); the contacts and
  commissioning readers exist as Plan 0070/0072 produced them
  (`rg -n "def list_active_contacts|def list_section_statuses|def read_session_details|def evaluate_readiness" server/src`);
  the V4 repository's active-fact readers and how a fact is deactivated today
  (`rg -n "revoked_at|valid_to|def get_active_literal_facts|def get_active_entity_relations" server/src/server/memory/relational_v4.py`);
  the offline PIN primitives (`rg -n "def verify_pin|def get_active_owner_pin_credential|def unlock\b" server/src`);
  whether `cognition/owner_authentication.unlock` is callable with the server stopped (no app state, no
  HTTP) — if it is, Task 3 reuses it; if it is coupled to the token registry, Task 3 adds a thin
  offline helper over `verify_pin`; **report which, with the evidence**; the architecture guards and
  their homes (`rg -n "admin_audit|_IMPORT_CHANNEL|_CARE_CONTACT_SQL|_commissioning_queriers|command" tests/unit/test_architecture_guards.py`);
  the health-probe and injected-adapter pattern of `seed_cli.main`. A difference is reported before code.

## Task 1: Migration 012 and the audit repository

**Files:** new `server/src/server/memory/migration_012_admin_audit.sql`, `server/src/server/db.py`;
new `server/src/server/memory/admin_audit.py`; `tests/unit/test_architecture_guards.py`; tests new
`tests/integration/test_admin_audit.py`, and the schema tests that pin the version
(`rg -n "migration_011|user_version|latest_schema_version|Schema up-to-date" tests server/src`).

The script is atomic like 011 (`BEGIN`, the statements, `PRAGMA user_version = 12`, `COMMIT`);
timestamps follow migration 004's convention. The table, in prose and key constraints (the executor
writes the full DDL):

- `admin_audit`: `id`; `recorded_at` `NOT NULL`; `actor_label` `NOT NULL`, 1 to 80 characters
  (a control-character check is in the repository, as for the interviewer label); `actor_role` `CHECK`
  in `owner builder`; `channel` `NOT NULL CHECK = 'admin_local'`; `operation` `CHECK` in
  `add change revoke`; `target_kind` `CHECK` in `pool_literal pool_relation care_contact`;
  `field_id` nullable (a catalogue id such as `medication`, or a contact role); `target_entity_id`
  nullable `REFERENCES entities(id) ON DELETE SET NULL` (who the change was about, never a value);
  `outcome` `CHECK` in `applied refused`; `reason` nullable (a closed word). **No value column of any
  kind.** An index on `(recorded_at)` for the `audit` listing.

**Interfaces — Produces** in `admin_audit.py` (every write joinable with `manage_transaction=False`):
`AdminActorRole(StrEnum)` (`OWNER`, `BUILDER`); `AdminOperationKind(StrEnum)` (`ADD`, `CHANGE`,
`REVOKE`); `TargetKind(StrEnum)` (`POOL_LITERAL`, `POOL_RELATION`, `CARE_CONTACT`);
`AdminOutcomeStatus(StrEnum)` (`APPLIED`, `REFUSED`); frozen `AdminAuditEntry` (the row's fields; its
`repr` is safe because it holds no value); `async record_admin_operation(*, actor_label: str,
actor_role: AdminActorRole, operation: AdminOperationKind, target_kind: TargetKind, field_id: str |
None, target_entity_id: int | None, outcome: AdminOutcomeStatus, reason: str | None, recorded_at: str,
manage_transaction: bool = True) -> AdminAuditEntry` (refuses a label outside 1 to 80 printable
characters); `async list_admin_operations(limit: int = 50) -> tuple[AdminAuditEntry, ...]` (most
recent first). This module is the **only** place with SQL on `admin_audit` (an architecture guard).

- [ ] **Step 1: Failing tests** (temporary SQLite, canaries). After `run_migrations` the database is
  at version 12 and has `admin_audit`; a database at version 11 with rows upgrades in place without
  losing any; running the migrations twice changes nothing. `record_admin_operation` stores a row and
  `list_admin_operations` returns it most-recent-first; each `CHECK` rejects a value outside its list
  (an `operation` `edit`, a `channel` `voice_classic`, a `target_kind` `secret`, an `outcome` `maybe`);
  a label with a control character or of 81 characters is refused; **a canary medication name, phone
  and owner name passed nowhere into the call leave no household value in a log** (`caplog` at DEBUG)
  and the row's `repr` holds none. Deleting the referenced entity sets `target_entity_id` to `NULL`
  (`SET NULL`) and keeps the row. The architecture guard fails when any other module puts SQL on
  `admin_audit`. **Expected RED:** `no such table`; the module does not exist.
- [ ] **Step 2: Implement** the script, register it in `db._MIGRATIONS`, add the
  `admin_audit`-SQL guard beside the care-contacts and commissioning guards in
  `tests/unit/test_architecture_guards.py` (and its detection test), and update the tests that pin
  version 11.
- [ ] **Step 3:** run `test_admin_audit.py`, the schema/migration tests and the architecture guards;
  lint and types.
- [ ] **Step 4: Commit** `feat(server): add migration 012 and the admin audit (plan 0073)`.

## Task 2: The admin channel and the read functions

**Files:** `server/src/server/memory/write_types.py`; `server/src/server/memory/relational_v4.py`
(admin reads); `tests/unit/test_architecture_guards.py` (the import-channel guard, run as a guard);
tests new `tests/unit/test_write_channels.py`, `tests/integration/test_admin_reads.py`.

**Interfaces — Produces:** `WriteChannel.ADMIN_LOCAL = "admin_local"` (a fourth member), **not** added
to `IMPORT_CHANNELS` or `VOICE_CHANNELS`. In `relational_v4.py`:
`async list_active_facts(subject_entity_id: int) -> tuple[LiteralFactV4, ...]` (every active literal
of a subject, across predicates, for display) and `async list_active_relations(owner_entity_id: int)
-> tuple[EntityRelationV4, ...]` (the owner's active relations); the SQL stays in `relational_v4.py`,
so neither the raw-reader guard nor the V4-table guard is touched. The contacts reader
(`care_contacts.list_active_contacts`) and the acta readers (`commissioning.list_section_statuses`,
`read_session_details`) already exist and are reused.

- [ ] **Step 1: Failing tests** (temporary SQLite, canaries). `WriteChannel.ADMIN_LOCAL` resolves to
  `"admin_local"`, is not in `IMPORT_CHANNELS` and not in `VOICE_CHANNELS`; the import-channel
  architecture guard still passes (the vocabulary module may name the member; the admin modules do not
  name an *import* channel). A write made through `write_literal(..., channel=WriteChannel.ADMIN_LOCAL)`
  is classified exactly as the same fact written through a voice or import channel (one case, to pin
  that the channel does not change the classification). `list_active_facts` returns the owner's active
  literals and hides a revoked one; `list_active_relations` returns the membership and relative
  relations; neither returns a value in a log. **Expected RED:** `ADMIN_LOCAL` does not exist; the read
  functions do not exist.
- [ ] **Step 2: Implement** the enum member and the two read functions (small `SELECT`s in
  `relational_v4.py`; no clock).
- [ ] **Step 3:** run the new files, `test_canonical_writer_*`, the architecture guards; lint and types.
- [ ] **Step 4: Commit** `feat(server): add the admin_local channel and admin reads (plan 0073)`.

## Task 3: The offline owner-PIN check

**Files:** `server/src/server/cognition/owner_authentication.py` **or** new
`server/src/server/memory/admin_pin.py` (Task 0 decides which; the plan assumes a new `admin_pin.py`
unless `unlock` is reusable offline), `server/src/server/exceptions.py`; tests new
`tests/integration/test_admin_pin.py`.

**Interfaces — Produces:** `exceptions.AdminPinError(ValueError)` (closed message, no value);
`async verify_owner_pin(pin: str) -> None` — reads the active owner credential
(`get_active_owner_pin_credential`) and checks `pin` with the single verifier `verify_pin`; raises
`AdminPinError` when there is no active credential or the PIN does not match. A simple attempt counter
(the command refuses after the same few tries `owner_authentication` uses) lives in the command, not
here; this function is a pure yes/no against the stored credential. It reuses the one cryptographic
check, so nothing about the PIN is re-implemented (the "PIN checked in one place" invariant holds
through `verify_pin`).

- [ ] **Step 1: Failing tests** (temporary SQLite; an owner set up as `personal-setup` does, with a
  canary PIN). `verify_owner_pin` with the right PIN returns `None`; with a wrong PIN raises
  `AdminPinError`; with no active credential raises `AdminPinError`; the error message and every log
  record hold no part of the PIN (`caplog` at DEBUG). **Expected RED:** the function does not exist.
- [ ] **Step 2: Implement** over `get_active_owner_pin_credential` and `verify_pin`; if Task 0 found
  `unlock` reusable offline, call its verifying core instead and note the ruling.
- [ ] **Step 3:** run the file; lint and types.
- [ ] **Step 4: Commit** `feat(server): verify the owner PIN offline for the admin (plan 0073)`.

## Task 4: `add` and `change` through the writers, with the audit

**Files:** new `server/src/server/memory/admin_ops.py`; `tests/unit/test_architecture_guards.py`
(the no-SQL-in-admin_ops-beyond-its-reads expectation is covered by the existing V4/contacts guards);
tests new `tests/integration/test_admin_ops_write.py`.

**Interfaces — Consumes:** the three writers with `on_conflict`/`channel`/`confirmed_at`
(Plan 0070), `create_third_party` (Plan 0070), `resolve_predicate` and the registry's sensitivity
(Plan 0070), `record_admin_operation` (Task 1), `WriteChannel.ADMIN_LOCAL` (Task 2). **Produces:**
frozen `AdminActor(label: str, role: AdminActorRole)`; frozen `AdminOutcome(operation:
AdminOperationKind, status: AdminOutcomeStatus, reason: str | None)`;
`requires_owner_verification(*, target_kind: TargetKind, predicate: str | None, subject_is_owner: bool)
-> bool` — `True` when `target_kind` is `CARE_CONTACT`, when `subject_is_owner` is `False`, or when the
predicate's registry sensitivity is `medical`, `location` or `security` (the classification stays the
registry's, never re-implemented);
`async apply_literal_edit(*, actor: AdminActor, owner_entity_id: int, subject_entity_id: int, predicate:
str, value: str, kind: AdminOperationKind, now: str, owner_verified: bool, manage_transaction: bool =
True) -> AdminOutcome`;
`async apply_contact_edit(*, actor: AdminActor, owner_entity_id: int, contact_entity_id: int, role:
ContactRole, terms: ContactTerms, kind: AdminOperationKind, now: str, owner_verified: bool,
manage_transaction: bool = True) -> AdminOutcome` (a small frozen `ContactTerms` carries the phone,
the optional second phone, the relationship, the order and the flags). Each `apply_*`: refuses with
`reason="owner_not_verified"` (status `REFUSED`, nothing written, **one audit row with that outcome**)
when `requires_owner_verification` is true and `owner_verified` is false; refuses with
`reason="actor_not_owner"` when `actor.role` is not `OWNER`/`BUILDER`; otherwise writes through the
matching writer with `channel=ADMIN_LOCAL` and `on_conflict=SUPERSEDE`, then writes **one** audit row
(outcome `APPLIED`, or `REFUSED` with the writer's closed reason if the writer refused), all in one
transaction.

- [ ] **Step 1: Failing tests** (temporary SQLite, canaries). `requires_owner_verification` is true for
  a contact, for a non-owner subject and for a `medical`/`location`/`security` predicate, and false for
  the owner's `likes` or `preferred_name`. `apply_literal_edit(kind=ADD)` writes a new multi-value
  literal of the owner through `admin_local` and records one `applied` audit row; `kind=CHANGE` of a
  single-value predicate supersedes the stored value; a sensitive predicate with `owner_verified=False`
  writes nothing and records one `refused` row (`owner_not_verified`); a writer refusal
  (`classification_conflict`, `not_household_member`) is reported as `REFUSED` with the writer's reason
  and audited once; **no audit row, outcome or log holds the value, the phone or a name**.
  `apply_contact_edit(kind=ADD)` with `owner_verified=True` writes a contact and audits it; with
  `owner_verified=False` refuses and audits `owner_not_verified`. A failure mid-operation rolls back
  both the write and its audit row. **Expected RED:** the module does not exist.
- [ ] **Step 2: Implement.** `match` on `kind` and `target_kind`; the audit row's `field_id` is the
  predicate id or the contact role, `target_entity_id` the subject or contact; the writer's
  classification is never recomputed here.
- [ ] **Step 3:** run the new file, `test_canonical_writer_*`, `test_care_contacts.py`,
  `test_admin_audit.py`, the architecture guards; lint and types.
- [ ] **Step 4: Commit** `feat(server): apply admin add and change with the audit (plan 0073)`.

## Task 5: `revoke` — supersede to inactive

**Files:** `server/src/server/memory/relational_v4.py`, `server/src/server/memory/care_contacts.py`
(one revoke function each); `server/src/server/memory/admin_ops.py` (the revoke orchestrator);
tests new `tests/integration/test_admin_revoke.py`.

**Interfaces — Produces:** in `relational_v4.py`: `async revoke_literal_fact(fact_id: int, *,
revoked_at: str, manage_transaction: bool = False) -> bool` and `async revoke_entity_relation(relation_id:
int, *, revoked_at: str, manage_transaction: bool = False) -> bool` (set the fact/relation inactive —
`revoked_at` or `valid_to` as the schema uses today, confirmed in Task 0 — and return whether a row
changed; a second call returns `False`). In `care_contacts.py`: `async revoke_contact(contact_id: int,
*, revoked_at: str, manage_transaction: bool = False) -> bool` (sets `revoked_at`; a second call is a
no-op). In `admin_ops.py`: `async apply_revoke(*, actor: AdminActor, target_kind: TargetKind,
target_id: int, subject_is_owner: bool, predicate: str | None, now: str, owner_verified: bool,
manage_transaction: bool = True) -> AdminOutcome` — refuses without the PIN exactly as the writes do,
otherwise calls the matching revoke and audits one `revoke` row.

- [ ] **Step 1: Failing tests** (temporary SQLite, canaries). `revoke_literal_fact` of an active fact
  returns `True`, the fact is no longer served by `list_active_facts`/`get_active_literal_facts`, the
  row still exists with its inactive marker set, and a second call returns `False`; the same for
  `revoke_entity_relation` and `revoke_contact` (gone from `list_active_contacts`, row kept). A revoke
  is **never a hard delete** (a count of all rows, active and inactive, is unchanged). `apply_revoke`
  of a contact or a sensitive fact without `owner_verified` refuses and audits `owner_not_verified`
  and nothing is revoked; with the PIN it revokes and audits one `revoke` row holding no value.
  **Expected RED:** the revoke functions do not exist.
- [ ] **Step 2: Implement** the three revoke functions (SQL stays in the owning repositories) and the
  orchestrator.
- [ ] **Step 3:** run the new file, `test_memory_v4_*`, `test_care_contacts.py`, `test_admin_audit.py`,
  the architecture guards; lint and types.
- [ ] **Step 4: Commit** `feat(server): revoke a datum to inactive, with the audit (plan 0073)`.

## Task 6: The `iroko-admin` command

**Files:** new `server/src/server/admin_cli.py`; `server/pyproject.toml`
(`iroko-admin = "server.admin_cli:main"`); `justfile` (recipe `admin *ARGS`, ASCII-only echo, Spanish
comment); `tests/unit/test_architecture_guards.py` (run as a guard); tests new
`tests/integration/test_admin_cli.py`.

**Interfaces — Consumes:** Tasks 1 to 5, `resolve_ready_owner` (Plan 0071, reused to find and name the
owner), `get_person_label`, `list_active_facts`, `list_active_relations`, `list_active_contacts`,
`list_section_statuses`, `read_session_details`, `verify_owner_pin`, `check_db_available`,
`db.latest_schema_version`. **Produces:** `async run_admin_command(*, argv-derived inputs, read_text:
ReadText, write_text: WriteText, now: str) -> int` (the exit code; adapters injected like
`run_seed_command`); `main() -> None`, which does the **synchronous** health probe (`httpx.get` on
`/health`, the port from the settings, a 2 s timeout) **before** `asyncio.run` and refuses a server
that answers. Sub-commands (D-6): `list` (the pool and contacts, values on this terminal only),
`status` (Task 8), `add`/`change`/`revoke` (the value read from **stdin**, a confirmation, `--dry-run`),
`audit` (the audit rows, no value). A sensitive operation prompts for the PIN and calls
`verify_owner_pin`, refusing after the same few wrong tries `owner_authentication` uses.

- [ ] **Step 1: Failing tests** (database state and server state stubbed; the step adapters stubbed).
  *Refusals (each prints a closed message, exits 1, writes nothing):* the server answers `/health`; the
  database file does not exist; the schema is not the latest (names `just setup-personal status`); the
  database is locked. *Reads:* `list` prints the pool and contacts (values included, in Spanish) and
  `audit` prints the rows with no value, both exit 0. *Writes:* `add`/`change`/`revoke` read the value
  from stdin, print the intended change, ask for confirmation, write only on the confirmation word and
  print «operación cancelada» otherwise; `--dry-run` writes nothing and says so; a sensitive operation
  asks for the PIN and, on a wrong PIN past the lockout, refuses and writes nothing. The database about
  to be used is printed first. The probe refusal is tested through `main()` with the probe stubbed. The
  command names no *import* channel (the import-channel guard is unaffected). **Expected RED:** the
  module does not exist.
- [ ] **Step 2: Implement.** `argparse` with any free-text argument as `nargs="+"` joined with spaces
  (the `just` rule on Windows); the command opens the database without creating it and never runs
  migrations; `now` is UTC ISO 8601 with microseconds like the other writers; the values are printed on
  this terminal only, with a reminder to clear the screen (as `seed_cli` does).
- [ ] **Step 3:** run the new tests and `ruff` over `server/src scripts tests`; types.
- [ ] **Step 4: Commit** `feat(server): add the iroko-admin command (plan 0073)`.

## Task 7: `status` — recompute the readiness read-only

**Files:** `server/src/server/memory/admin_ops.py` (a read-only recompute) **or** new
`server/src/server/memory/admin_readiness.py`; `server/src/server/admin_cli.py` (the `status`
sub-command calls it); tests new `tests/integration/test_admin_status.py`.

**Interfaces — Consumes:** `list_section_statuses`, `read_session_details`,
`commissioning_readiness.{evaluate_readiness, CATALOGUE, HardwareStatus, Verdict, readiness_to_json}`,
`get_open_commissioning`/the closed record, `list_active_facts`, `list_active_contacts`. **Produces:**
`async recompute_readiness(owner_entity_id: int) -> tuple[CapabilityReadiness, ...]` — derives which
sections hold active rows **now** (a small `derive_section_presence(owner_entity_id) -> Mapping[Section,
bool]`), feeds `evaluate_readiness` with those as the data side and the **frozen** hardware attestation
read from the closed acta's readiness (never re-attested here), and returns the report; it calls **no**
commissioning writer, so it never raises `CommissioningClosedError`. `status` prints the frozen section
statuses of the acta beside the recomputed presence, flagging any divergence (a section the acta calls
`provided` with no active row now, or the reverse).

- [ ] **Step 1: Failing tests** (temporary SQLite, canaries, a closed record). On a closed robot,
  `recompute_readiness` returns a report and **raises nothing** (it touches no writer); a section the
  acta froze as `provided` whose rows were all revoked is flagged as diverged; the hardware side equals
  the frozen attestation (it is not re-attested); `derive_section_presence` is true for a section with
  an active row and false for one with none. **Expected RED:** the function does not exist.
- [ ] **Step 2: Implement** the pure-ish derivation and the recompute; reuse `evaluate_readiness`.
- [ ] **Step 3:** run the new file, `test_commissioning*`, the architecture guards; lint and types.
- [ ] **Step 4: Commit** `feat(server): recompute the readiness read-only for the admin (plan 0073)`.

## Task 8: Documentation truth, ADR 0025 `Accepted`, and acceptance (text and manual, no RED)

- [ ] [ADR 0025](../../adr/0025-remote-administration-backup-updates-and-telemetry.md) →
  **`Accepted`** (its first implementing plan closed; C-3), its *Implemented by* and *Follow-up*
  updated (the remote half, decisions 5 to 8, has no plan yet);
  [ADR 0024](../../adr/0024-seed-load-senses-secrets-and-channels.md) decision 8 pointer (the amendment
  path shipped; the authority is the machine plus the PIN for sensitive writes, C-1);
  [`seed-data-pool.md`](../../architecture/seed-data-pool.md) (the amendment path now exists; a datum
  changes without a re-interview);
  [`memory-and-world-state.md`](../../architecture/memory-and-world-state.md) (the `admin_local`
  channel, revoke-to-inactive, the admin audit);
  [`identity-and-access.md`](../../architecture/identity-and-access.md) (the admin surface, the offline
  PIN for sensitive writes, the audit with no value);
  [`current-state.md`](../../architecture/current-state.md) and its Archify diagram (validate, then
  deliver); the roadmap's Step 0 row and the cross-cutting rows it touches; the plan index
  (`docs/plans/README.md`), the open-plan index (`docs/plans/open/README.md`), the completed index and
  the ADR index; `server/README.md` (one paragraph on `iroko-admin`); the local tracking table
  (never committed). Move this plan to `completed/` with its execution record.
- [ ] `uv run ruff format --check .`, `uv run ruff check .`, `uv run python scripts/check_reserved_terms.py`,
  every relative link resolves, `just gate` with `MEMORY_ENABLED=false`.
- [ ] **Acceptance by Pipec on a database kept apart** (`BRAIN_DB_PATH` set to a scratch file with a
  commissioning already closed; outcomes only, never a value, in `docs/evals/0073-admin-acceptance.md`):
  `iroko-admin list` shows the pool and contacts; `status` shows the frozen acta beside the recomputed
  readiness; `add`/`change` a `likes` (no PIN) and a `medication`/a contact (PIN prompted); `revoke`
  one of each (PIN prompted); `audit` shows the operations with no value; a wrong PIN refuses; a run
  with the server up is refused. No behaviour reaches the voice, so there is no hardware case; say so.
- [ ] Commit `docs: close plan 0073`; PR; merge only with Pipec's go-ahead.

## ADR coverage

| ADR | Decision | Where |
|---|---|---|
| ADR 0025 | 2 (level A, the CLI surface) | Task 6 |
| ADR 0025 | 3 (owner-verification rule; multi-adult refused) | Tasks 3, 4, 5 |
| ADR 0025 | 4 (writers, the two channels — local only — supersede/revoke, one audit event, no value, guard) | Tasks 1, 2, 4, 5 |
| ADR 0025 | 10 (the installation id and consents already recorded; nothing added) | — (read only) |
| ADR 0025 | 11 (the machine as authority, the refusals) | Tasks 3, 6 |
| ADR 0024 | 8 (the amendment path) | Tasks 4, 5, 6 |
| ADR 0024 | 5, 6, 7 (contacts, the assisted/admin channel level, the writers' bypass) | Tasks 2, 4 |
| ADR 0025 | 5 to 8 (the remote half) | Not here |

## Completion criteria

1. Tasks 0 to 8 done, one commit per task, every code test RED before GREEN (Task 8 is text and a
   manual acceptance, declared).
2. `just gate` green with `MEMORY_ENABLED=false`; the Plan 0070, 0071 and 0072 tests unchanged; one
   migration (012), no new route or setting.
3. Every write goes through the canonical writers with `admin_local`; a sensitive or other-person
   write needs the owner's PIN; a revoke is history, never a hard delete; every mutating operation
   writes one audit row that holds no value; no module but `admin_audit.py` puts SQL on `admin_audit`,
   and the command holds no SQL.
4. The migration upgrades a version-11 database in place; `status` recomputes the readiness read-only
   and never edits the frozen acta; the command refuses a server that answers `/health`.
5. ADR 0025 is `Accepted`; the acceptance record exists with outcomes only.

## Rollback boundary

Each task is one commit. Task 1 adds migration 012: there is no down-step, the table is new and unused
by older code, so the rollback is to leave it. Tasks 4 and 5 need Tasks 1, 2 and 3; Task 6 needs Tasks
1 to 5; Task 7 needs Task 6. The command and the recipe are additive.

## Not here, and why

- **A web page of any level (B or C), and everything remote:** the VPN, the support session opened by
  the owner at the robot, the `admin_remote` channel, the encrypted backup, the signed controlled
  updates, the telemetry and the periodic job (ADR 0025 decisions 2 level B/C, 3 the support session,
  5 to 8). Only the command-line tool and `admin_local` are here.
- **`candidates` (approve/reject):** the periodic job that would create admin-approvable candidates
  has no code before CM-4 (ADR 0025 decision 5), candidates are created only by voice today, and
  approving one from the admin would be a third caller of `promote`/`resolve_candidate`, which an
  architecture guard forbids and ADR 0021's firewall (face and voice of the turn) governs. YAGNI until
  CM-4.
- **`export` (the round trip to TOML):** ADR 0025 decision 11's export is the inverse of the importer
  (undo the folding, the predicate map, read the raw tables) and, with the window closed, serves only
  comparison. It is a later, separate plan so this one stays one reviewable slice.
- **Hard delete and forgetting (CM-6):** a revoke is history; erasing a row, its embeddings and its
  audit is CM-6.
- **Reading the pool by voice (CM-5), the audience rule, the alert, the call:** CM-5 and the care ADR.
- **A second adult or a `representative` actor:** refused until the support session and the `family`
  profile exist (ADR 0025 decision 3, ADR 0006).
