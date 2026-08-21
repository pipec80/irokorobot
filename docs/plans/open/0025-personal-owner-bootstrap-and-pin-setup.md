# Personal Owner Bootstrap and PIN Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Status:** Minimal north-star scope approved by Pipec on 2026-08-20.
Implemented on `feat/personal-owner-bootstrap` on 2026-08-20 — Tasks 1-5 done,
one commit per task. All focused and repository gates pass (677 tests, up
from the 641 baseline; `just lint`, `just typecheck`, `just audit`, `just
check` all green). Setup/credential persistence is complete and locally
usable via `just setup-personal`. Not yet implemented by this plan: token
issue, router identity propagation, robot propagation, the protected
child-answer runtime, and microphone/TTS acceptance — those belong to Plans
0026, 0027, and 0028 respectively. Pending independent review and merge
before Plan 0026 may start.

**Goal:** Provide one restart-safe, local CLI wizard that establishes Pipec as
the sole owner, stores Máximo and Dominga as confirmed v4 child relationships,
and persists a securely hashed PIN credential.

**Architecture:** A local application service composes the existing v4 entity,
relation, and owner-role repositories using their current transaction
boundaries. A dedicated credential repository stores only a salted scrypt
verifier in a new additive migration. The setup is confirm-before-write,
restart-safe, and idempotently resumable; it is not falsely described as one
cross-repository atomic transaction. The CLI is a thin `getpass`/input adapter;
it never becomes an HTTP or general family administration API.

**Tech Stack:** Python 3.12 standard library (`getpass`, `hashlib.scrypt`,
`secrets`), SQLite/aiosqlite, existing v4 repositories, pytest, `just`.

**Spec:** [Plan 0024 — owner-authenticated personal-memory MVP
design](0024-owner-authenticated-memory-mvp-design.md)

## Global Constraints

- Read `AGENTS.md`, ADR 0006, ADR 0007, ADR 0008, Plan 0024,
  `architecture/identity-and-access.md`, and
  `architecture/memory-and-world-state.md` completely before editing.
- This plan owns setup and persistent credential configuration only. It does
  not issue authentication tokens, modify public routers, or answer a query.
- Run the wizard only with `just run-server` and `just run-robot` stopped; the
  project currently uses one process-global SQLite connection.
- Preserve existing entity integer IDs, v4 predicate semantics, authorization
  audit, API contracts, and the server↔robot boundary.
- No PIN, plaintext derivative, verifier, salt, token, protected child value,
  or full credential object may be logged.
- Never store a plaintext PIN or reversible PIN encryption.
- PIN input is exactly 6–12 ASCII digits and must be confirmed twice.
- Use `hashlib.scrypt` with a unique 16-byte salt, `n=2**15`, `r=8`, `p=3`,
  `dklen=32`, and `maxmem=64 * 1024 * 1024`. Store algorithm and parameters
  with the verifier so a later ADR can migrate them.
- Do not add a dependency. Python exposes scrypt as a password-based key
  derivation function; OWASP lists scrypt as the fallback when Argon2id is not
  available and requires a per-secret salt and tunable work factor.
- The setup summary must be confirmed explicitly before any durable write.
- Do not set `meta.onboarding_complete`: the existing eight-slot onboarding
  reads legacy v3 facts while this setup writes authoritative v4 relationships.
  Extended profile fields and v3/v4 onboarding convergence are later work.
- Do not add a `personal_mvp_ready` flag. Readiness for Plans 0026–0028 is
  derived by verifying exactly one active owner, the confirmed active child
  relationships, and one active PIN credential.
- Re-running the same confirmed setup must not create duplicate entities,
  relations, role assignments, or active credentials. A same-PIN rerun reuses
  the active credential; a different confirmed PIN rotates it and may retain
  revoked history while keeping exactly one active row.
- Existing repositories own their transactions and commits. Do not wrap
  `upsert_entity`, `bootstrap_initial_owner`, v4 relation writes, outbox writes,
  and credential persistence in a second outer SQLite transaction.
- All public functions have complete type hints and Google docstrings.
- Use `apply_patch`; do not commit directly to `main`.

---

## File map

| File | Responsibility |
|---|---|
| `server/src/server/memory/migration_006_owner_credentials.sql` | Add one-owner PIN credential storage. |
| `server/src/server/db.py` | Register migration 006 only. |
| `server/src/server/cognition/pin_credentials.py` | Validate, hash, encode, and verify PINs without persistence. |
| `server/src/server/memory/owner_credentials.py` | Store/read/revoke the active owner PIN verifier. |
| `server/src/server/personal_setup.py` | Local wizard and application orchestration. |
| `server/pyproject.toml` | Add `personal-setup` console entrypoint. |
| `justfile` | Add `just setup-personal`. |
| `tests/integration/test_owner_credentials_schema.py` | Migration and repository proof. |
| `tests/unit/test_pin_credentials.py` | Pure PIN/security tests. |
| `tests/integration/test_personal_setup.py` | Empty/rerun/rollback-boundary setup scenarios. |

No other production file is in scope. In particular, do not modify routers,
the controller, robot code, face code, voice code, RAG, or semantic memory.

## Preflight evidence — 2026-08-20

- Code inspection confirmed migrations stop at 005 and the PIN/setup artifacts
  named by this plan are absent.
- The original draft was not executable as written: legacy onboarding reads v3
  while the setup writes v4, current repositories own separate commits, and
  PIN rerun/rotation semantics conflicted. This revision removes those
  contradictions and narrows the product input to owner, children, and PIN.
- Python's `hashlib.scrypt` supports the stored parameter contract. OWASP lists
  `N=2**15`, `r=8`, `p=3` as one accepted scrypt trade-off. A local probe on
  this Windows Python/OpenSSL produced a 32-byte verifier in 1100.9 ms with the
  plan's 64 MiB `maxmem` setting.
- Full baseline command with local streaming configuration neutralized:

  ```powershell
  try { $env:ROBOT_STREAMING='false'; just test } finally { Remove-Item Env:ROBOT_STREAMING -ErrorAction SilentlyContinue }
  ```

  Result: `641 passed in 29.81s`.
- No Plan 0025 production implementation has started. The remaining preflight
  gate is a recoverable/versioned checkpoint of the documentation worktree.

---

### Task 1: Add the bounded owner credential migration

**Files:**

- Create: `server/src/server/memory/migration_006_owner_credentials.sql`
- Modify: `server/src/server/db.py`
- Create: `tests/integration/test_owner_credentials_schema.py`

**Interfaces:**

- Consumes: existing `entities(id)` and migration runner.
- Produces: one active `owner_pin_credentials` row per owner; migration version
  6.

- [ ] **Step 1: Write the failing migration tests**

Add tests that open a disposable database, run migrations, and assert:

```python
cursor = await db.get_conn().execute("PRAGMA user_version")
assert (await cursor.fetchone())[0] == 6

columns = await _table_columns("owner_pin_credentials")
assert columns == {
    "id",
    "person_entity_id",
    "algorithm",
    "parameters_json",
    "salt",
    "verifier",
    "created_at",
    "updated_at",
    "revoked_at",
}
```

Also prove foreign keys are enabled, two active credentials for the same owner
are rejected, and a credential cannot reference a missing entity.

- [ ] **Step 2: Run the focused test and observe RED**

Run:

```powershell
uv run pytest -n0 tests/integration/test_owner_credentials_schema.py -q
```

Expected: FAIL because migration 006/table does not exist.

- [ ] **Step 3: Create the additive schema**

The migration must create this shape without changing previous tables:

```sql
CREATE TABLE IF NOT EXISTS owner_pin_credentials (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    person_entity_id    INTEGER NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
    algorithm           TEXT NOT NULL CHECK (algorithm = 'scrypt'),
    parameters_json     TEXT NOT NULL,
    salt                BLOB NOT NULL,
    verifier            BLOB NOT NULL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    revoked_at          TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS owner_pin_credentials_active_owner_idx
ON owner_pin_credentials (person_entity_id)
WHERE revoked_at IS NULL;
```

Register exactly:

```python
((6, "migration_006_owner_credentials.sql"),)
```

after migration 005 in `server/src/server/db.py`.

- [ ] **Step 4: Run migration regression tests**

Run:

```powershell
uv run pytest -n0 tests/integration/test_owner_credentials_schema.py tests/integration/test_memory_v4_schema.py tests/integration/test_household_authorization_schema.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the independently reviewable migration**

```powershell
git add server/src/server/memory/migration_006_owner_credentials.sql server/src/server/db.py tests/integration/test_owner_credentials_schema.py
git commit -m "feat(auth): add owner PIN credential schema"
```

---

### Task 2: Implement pure PIN hashing and verification

**Files:**

- Create: `server/src/server/cognition/pin_credentials.py`
- Create: `tests/unit/test_pin_credentials.py`

**Interfaces:**

- Consumes: a candidate PIN string and secure random salt.
- Produces:

```python
class EncodedPinCredential(BaseModel):
    algorithm: Literal["scrypt"]
    parameters_json: str
    salt: bytes
    verifier: bytes


def hash_pin(pin: str, *, salt: bytes | None = None) -> EncodedPinCredential: ...
def verify_pin(pin: str, credential: EncodedPinCredential) -> bool: ...
```

- [ ] **Step 1: Write pure RED tests**

Cover exact behavior:

```python
@pytest.mark.parametrize("pin", ["", "12345", "1234567890123", "１２３４５６", "123 456", "abcdef"])
def test_hash_pin_rejects_non_six_to_twelve_ascii_digits(pin: str) -> None:
    with pytest.raises(ValueError, match="6 to 12 ASCII digits"):
        hash_pin(pin)


def test_hash_pin_uses_unique_salt_and_never_contains_plaintext() -> None:
    first = hash_pin("482173")
    second = hash_pin("482173")
    assert len(first.salt) == 16
    assert first.salt != second.salt
    assert first.verifier != second.verifier
    assert b"482173" not in first.salt + first.verifier


def test_verify_pin_accepts_only_the_matching_pin() -> None:
    credential = hash_pin("482173", salt=b"0" * 16)
    assert verify_pin("482173", credential) is True
    assert verify_pin("482174", credential) is False
```

Also assert exact algorithm/parameters and reject malformed salt, verifier, or
parameters without leaking the candidate PIN in exception text.

- [ ] **Step 2: Observe RED**

```powershell
uv run pytest -n0 tests/unit/test_pin_credentials.py -q
```

Expected: collection/import failure because the module is absent.

- [ ] **Step 3: Implement the minimal pure module**

Use constants and a single private derivation function:

```python
_PIN_PATTERN = re.compile(r"^[0-9]{6,12}$")
_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 3
_SCRYPT_DKLEN = 32
_SCRYPT_MAXMEM = 64 * 1024 * 1024


def _derive(pin: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        pin.encode("ascii"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        maxmem=_SCRYPT_MAXMEM,
        dklen=_SCRYPT_DKLEN,
    )
```

Generate salts using `secrets.token_bytes(16)` and compare derived bytes with
`hmac.compare_digest`. Never add custom encryption, fast SHA hashing, or
password logging.

- [ ] **Step 4: Run focused tests and security lint**

```powershell
uv run pytest -n0 tests/unit/test_pin_credentials.py -q
uv run ruff check --select S server/src/server/cognition/pin_credentials.py
```

Expected: PASS with no security warning.

- [ ] **Step 5: Commit**

```powershell
git add server/src/server/cognition/pin_credentials.py tests/unit/test_pin_credentials.py
git commit -m "feat(auth): hash owner PIN with scrypt"
```

---

### Task 3: Add the credential repository

**Files:**

- Create: `server/src/server/memory/owner_credentials.py`
- Modify: `tests/integration/test_owner_credentials_schema.py`

**Interfaces:**

- Consumes: `EncodedPinCredential` and an existing owner entity ID.
- Produces:

```python
class OwnerPinCredential(BaseModel):
    id: int
    person_entity_id: int
    encoded: EncodedPinCredential


async def save_owner_pin_credential(
    *, person_entity_id: int, credential: EncodedPinCredential
) -> OwnerPinCredential: ...


async def get_active_owner_pin_credential() -> OwnerPinCredential | None: ...
async def revoke_owner_pin_credential(*, person_entity_id: int) -> None: ...
```

- [ ] **Step 1: Add RED repository tests**

Prove:

- only an existing `person` with active `owner` role is accepted;
- save then read preserves bytes and parameters;
- saving the same verified PIN for the same owner returns the existing active
  credential without inserting a row;
- saving a different confirmed PIN rotates atomically and leaves exactly one
  active credential, while revoked history may remain;
- revoke returns no active credential;
- no repository log contains PIN, salt, or verifier.

- [ ] **Step 2: Observe RED**

```powershell
uv run pytest -n0 tests/integration/test_owner_credentials_schema.py -q
```

Expected: FAIL because repository functions are absent.

- [ ] **Step 3: Implement parameterized repository operations**

Validate owner status using the existing role table before writing. Read the
active credential first and use `verify_pin()` to reuse it when the candidate
PIN already matches. A genuine rotation must use `BEGIN IMMEDIATE`, revoke the
previous active row, insert the new row, and commit once. On any exception,
roll back and re-raise.

Do not use `meta` for the verifier and do not write an outbox record containing
credential material.

- [ ] **Step 4: Run focused tests**

```powershell
uv run pytest -n0 tests/integration/test_owner_credentials_schema.py tests/unit/test_pin_credentials.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add server/src/server/memory/owner_credentials.py tests/integration/test_owner_credentials_schema.py
git commit -m "feat(auth): persist owner PIN verifier"
```

---

### Task 4: Build the confirmed minimal personal setup service

**Files:**

- Create: `server/src/server/personal_setup.py`
- Create: `tests/integration/test_personal_setup.py`

**Interfaces:**

- Consumes one immutable confirmed input:

```python
class PersonalSetupInput(BaseModel):
    owner_name: str
    child_names: tuple[str, ...]
    pin: SecretStr


class PersonalSetupResult(BaseModel):
    owner_entity_id: int
    child_entity_ids: tuple[int, ...]
    personal_security_ready: bool


async def apply_personal_setup(data: PersonalSetupInput) -> PersonalSetupResult: ...
```

- Produces one owner, two confirmed v4 child relations, one active PIN
  credential, and a derived `personal_security_ready` result. It writes no
  completion shortcut and does not mutate legacy onboarding facts.

- [ ] **Step 1: Write the empty-database RED acceptance test**

Use the real disposable SQLite migration path and call:

```python
result = await apply_personal_setup(
    PersonalSetupInput(
        owner_name="Pipec",
        child_names=("Máximo", "Dominga"),
        pin=SecretStr("482173"),
    )
)
```

Assert:

- exactly one Pipec owner role exists;
- exactly two active `child_of` relations point to Pipec;
- labels are exactly `Máximo` and `Dominga`;
- active PIN credential exists but plaintext does not appear anywhere in the
  DB file's logical rows;
- `personal_security_ready is True` is derived only after rereading owner,
  child relations, labels, and active credential;
- `meta.onboarding_complete` remains absent or unchanged.

- [ ] **Step 2: Write failure and rerun RED tests**

Cover:

```python
async def test_setup_rejects_children_before_owner_confirmation(...): ...
async def test_setup_rejects_duplicate_child_names_after_accent_folding(...): ...
async def test_setup_rejects_a_second_active_owner(...): ...
async def test_same_pin_rerun_is_idempotent(...): ...
async def test_different_confirmed_pin_rotates_one_active_credential(...): ...
async def test_partial_failure_is_safely_resumable(...): ...
async def test_setup_never_marks_extended_onboarding_complete(...): ...
```

The same-PIN rerun must keep one owner, one active credential row, and two
active relations. A different-PIN rerun may add one revoked history row but
must still expose exactly one active credential.

- [ ] **Step 3: Observe RED**

```powershell
uv run pytest -n0 tests/integration/test_personal_setup.py -q
```

Expected: FAIL because the service does not exist.

- [ ] **Step 4: Implement structured writes in the required order**

The service must:

1. validate the complete immutable input and exact non-empty, accent-folded
   unique child names without writing;
2. `upsert_entity(name=owner_name, type="person")`;
3. call `bootstrap_initial_owner()` only if no active owner exists; otherwise
   require the existing owner to be the same entity;
4. create each child as `type="person"`;
5. write each child through `assert_entity_relation()` as
   `source child -> child_of -> target owner`;
6. reuse or rotate the active credential according to Task 3;
7. reread owner role, active child relations/labels, and active credential;
8. return `personal_security_ready=True` only when that derived verification
   succeeds.

Use `resolve_predicate("child_of")` and fail if the closed predicate is absent.
Each existing repository keeps its own transaction. A failure can leave a
safe partial bootstrap, but no readiness flag or false completion claim; the
confirmed rerun must converge without duplicates. Do not write relationship
sentences into prompts, semantic memory, legacy v3 facts, or vectors.

- [ ] **Step 5: Run setup and existing family acceptance tests**

```powershell
uv run pytest -n0 tests/integration/test_personal_setup.py tests/integration/test_p05b2_household_acceptance.py tests/integration/test_onboarding_checklist.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add server/src/server/personal_setup.py tests/integration/test_personal_setup.py
git commit -m "feat(onboarding): bootstrap personal owner profile"
```

---

### Task 5: Add the local conversational CLI wizard

**Files:**

- Modify: `server/src/server/personal_setup.py`
- Modify: `server/pyproject.toml`
- Modify: `justfile`
- Modify: `tests/integration/test_personal_setup.py`

**Interfaces:**

- Consumes: terminal input/getpass while the server is stopped.
- Produces: `personal-setup = "server.personal_setup:main"` and
  `just setup-personal`.

- [ ] **Step 1: Write RED adapter tests with injected input/output**

Do not test the real terminal. Expose:

```python
type ReadText = Callable[[str], str]
type ReadSecret = Callable[[str], str]
type WriteText = Callable[[str], None]


async def run_personal_setup_wizard(
    *, read_text: ReadText, read_secret: ReadSecret, write_text: WriteText
) -> PersonalSetupResult | None: ...
```

Test exact behavior:

- prompts follow owner → children → PIN → redacted summary → literal `SI`
  confirmation;
- PIN mismatch writes nothing;
- any confirmation other than `SI` writes nothing;
- summary includes only owner and child names and displays PIN as `******`;
- successful setup prints IDs/status, never the PIN/verifier/token;
- `status` prints only schema version, owner count, active child-relation count,
  derived personal-security readiness, active credential count, and the
  separate extended-onboarding state;
- completed setup exits safely without overwriting.

- [ ] **Step 2: Observe RED**

```powershell
uv run pytest -n0 tests/integration/test_personal_setup.py -q
```

- [ ] **Step 3: Implement the thin adapter**

`main()` must call `asyncio.run()`, open/run migrations/close DB in
`try/finally`, and use `getpass.getpass` for PIN entries. Before setup writes,
perform a bounded lock-availability preflight with `BEGIN IMMEDIATE` followed
immediately by `ROLLBACK`; lock failure exits non-zero. Do not hold that
transaction while calling repositories that own their commits. Add a `status`
subcommand that performs only the non-secret aggregate/status reads named
above.

Register:

```toml
[project.scripts]
serve = "server.main:main"
personal-setup = "server.personal_setup:main"
```

Add:

```just
setup-personal *ARGS:
    uv run --env-file .env --package server personal-setup {{ARGS}}
```

- [ ] **Step 4: Run focused tests and inspect CLI help/start cancellation**

```powershell
uv run pytest -n0 tests/integration/test_personal_setup.py -q
just --list
just setup-personal status
```

Manually start `just setup-personal`, answer the first prompt with an empty
value, and verify it exits without writes. Do not use Pipec's real PIN in an
automated transcript.

- [ ] **Step 5: Commit**

```powershell
git add server/src/server/personal_setup.py server/pyproject.toml justfile tests/integration/test_personal_setup.py
git commit -m "feat(onboarding): add local personal setup wizard"
```

---

### Task 6: Close Plan 0025 gates

**Files:**

- Modify: `docs/architecture/current-state.md`
- Modify: `docs/plans/README.md`
- Modify: `docs/plans/open/0025-personal-owner-bootstrap-and-pin-setup.md`

- [ ] **Step 1: Run focused regression**

```powershell
uv run pytest -n0 tests/unit/test_pin_credentials.py tests/integration/test_owner_credentials_schema.py tests/integration/test_personal_setup.py tests/integration/test_p05b2_household_acceptance.py tests/integration/test_onboarding_checklist.py -q
```

- [ ] **Step 2: Run repository gates**

```powershell
just lint
just typecheck
just test
just audit
just check
git diff --check
```

Expected: every command exits 0. Record observed counts and duration; do not
copy anticipated numbers into evidence.

- [ ] **Step 3: Perform security review**

Search tracked code/test output for the synthetic PIN and forbidden logging:

```powershell
rg -n "482173|pin=.*|verifier=.*|salt=.*" server/src robot/src tests logs
```

Expected: synthetic test fixtures only; no runtime log or production literal.
Review that every SQL write is parameterized and credential bytes never enter
authorization audit/outbox.

- [ ] **Step 4: Update documentation evidence**

Mark only setup/credential persistence complete. Explicitly state token issue,
router identity, robot propagation, child-answer runtime, and microphone/TTS
acceptance remain unimplemented in Plans 0026–0028.

- [ ] **Step 5: Request independent review before merge**

Review migration safety, PIN handling, idempotency, owner-before-household
ordering, and scope. Resolve findings, rerun affected gates, then create the
PR. Do not begin Plan 0026 before this plan is merged or its reviewed interface
is frozen.

## Completion criteria

Plan 0025 is complete only when:

- a fresh DB can be configured through `just setup-personal`;
- Pipec is the sole owner and Máximo/Dominga are exact v4 child relations;
- readiness is derived from one owner, the exact active child relations, and
  one active credential; no shortcut flag is persisted;
- `meta.onboarding_complete` is not changed by this minimal setup;
- the PIN is stored only as a salted, parameterized scrypt verifier;
- cancellation, invalid input, rerun, and second-owner attempts fail safely;
- all focused and repository gates pass;
- no auth token, router, robot, face, voice, RAG, or runtime-answer code was
  introduced.

**Evidence (2026-08-20):** Every criterion above is met on
`feat/personal-owner-bootstrap`. `just setup-personal` and
`just setup-personal status` run against a fresh DB; the wizard's blank-owner
cancellation and its no-write behavior were verified manually with a
synthetic (non-real) PIN. Idempotent rerun, PIN rotation, and second-owner
rejection are covered by `tests/integration/test_personal_setup.py`. No file
outside this plan's file map was modified except two pre-existing migration
version assertions (`tests/integration/test_memory_v4_schema.py`,
`tests/integration/test_household_authorization_schema.py`) that pin the
schema to its latest applied migration and had to advance from 5 to 6 —
consistent with how they were already bumped for migration 5.

## Security references

- [Python `hashlib` key derivation documentation](https://docs.python.org/3/library/hashlib.html#key-derivation)
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
