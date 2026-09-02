# Owner Unlock HTTP Hardening Implementation Plan

> **Status:** Completed 2026-09-02. Historical evidence only — this document
> is not an instruction and authorizes nothing.

**Goal:** Make the local owner-PIN boundary deterministic, private, and safe
under concurrent requests.

**Architecture:** Pydantic validates HTTP shape; the domain service serializes
one complete verification attempt; the router maps domain outcomes to existing
HTTP semantics.

**Tech Stack:** FastAPI, Pydantic V2, asyncio, stdlib `ipaddress`, pytest.

**Spec:**
[`server-production-baseline.md`](../../architecture/server-production-baseline.md)

## Permitted files

- `server/src/server/schemas_auth.py`
- `server/src/server/cognition/owner_authentication.py`
- `server/src/server/routers/auth.py`
- `server/src/server/main.py` — validation-error handler, see execution notes
- `tests/unit/test_owner_authentication.py`
- `tests/integration/test_owner_unlock_endpoint.py`

No identity-token semantics, credential hashing parameters, database schema,
face authentication, or non-loopback unlock path may change.

## Interfaces

`OwnerUnlockRequest.pin` remains `SecretStr` and accepts only the ASCII pattern
`^[0-9]{6,12}$`. `OwnerUnlockService` owns `_attempt_lock: asyncio.Lock`.

## Task 1: Lock the HTTP contract with RED tests

- [ ] Add endpoint cases:
  - malformed PIN (`abcdef`, Unicode digits, 5 digits, 13 digits) -> `422`;
  - valid-shaped wrong PIN -> `401`;
  - non-loopback -> `403` before verification;
  - threshold reached -> `429` with `Retry-After`;
  - success -> `200` with `Cache-Control: no-store`.
- [ ] Use unique malformed PIN/token sentinels and assert they are absent from
  response JSON and `caplog.text`.
- [ ] Observe RED:

  ```powershell
  uv run pytest -n0 tests/integration/test_owner_unlock_endpoint.py -q
  ```

## Task 2: Prove and close the concurrency race

- [ ] Add an async unit test that gates six simultaneous valid-shaped wrong
  attempts at the verifier, releases them together, and asserts the limiter
  threshold cannot be passed by all six.
- [ ] Observe the test fail against the pre-lock check/await/update sequence.
- [ ] Add one `asyncio.Lock` and keep prune/check, credential read, role read,
  expensive verify, and success/failure mutation inside the lock.
- [ ] Do not use `threading.Lock`; do not hold a database transaction across
  scrypt verification.

## Task 3: Harden the router boundary

- [ ] Add Pydantic pattern validation while retaining `SecretStr`.
- [ ] Parse `request.client.host` with `ipaddress.ip_address()` and require
  `.is_loopback`; a missing/unparseable client is forbidden.
- [ ] Add cache and retry headers without changing success body fields.
- [ ] Rerun focused tests, then `just lint`, `just typecheck`, `just test`, and
  `just audit`.

## Rollback

Revert the PR. No data migration is involved; existing tokens remain
process-local and unchanged.

## Completion criteria

- All five status classes are deterministic and documented by tests.
- Concurrent attempts cannot bypass the limiter.
- No secret appears in error bodies or logs.
- Existing one-use-token and authenticated-turn tests remain green.

## Execution notes

Executed 2026-09-02 on branch `feat/0033-owner-unlock-http-hardening`,
test-first: every one of the 14 new tests was watched failing against real code
before any production line changed.

### The race was real

The concurrency test failed with `assert 6 <= 5`: six simultaneous wrong PINs
all reached the verifier although the limiter blocks at five. `unlock` checked
the limiter, then awaited the credential read, the role read and scrypt before
recording a failure — three scheduling points during which no attempt had yet
invalidated the check that all of them passed. scrypt is deliberately slow
(`N=2**15`), which widens that window rather than narrowing it.

Closed with one `asyncio.Lock` covering a complete attempt: limiter check,
credential and role reads, verification, and the failure/success mutation.
Writes are intentionally serialized; a local PIN unlock is not a throughput
path.

### Moving validation to Pydantic introduced a leak, and it had to be fixed

A malformed PIN used to reach `verify_pin`, which raised `ValueError` that
nothing caught — a `500`, with the expensive scrypt path entered for input that
could never match. Adding an `AfterValidator` to `OwnerUnlockRequest.pin` fixed
the status code and produced a new problem: FastAPI's default `422` body
includes an `input` field carrying the rejected value verbatim, so the response
handed the candidate PIN straight back to the caller.

`Field(pattern=...)` cannot be applied to `SecretStr` — Pydantic raises
`Unable to apply constraint 'pattern' ... for schema of type 'lax-or-strict'` —
so the shape is checked by a validator that reads the secret and reports only
the rule, never the value.

The leak is closed by a `RequestValidationError` handler that keeps `type`,
`loc` and `msg` and drops `input` and `ctx`. That required `main.py`, which the
original permitted files did not list; it was added because "no secret appears
in error bodies" is a completion criterion of this plan and the leak was
introduced by this plan's own change. Plan 0040 owns centralizing exception
handlers and should absorb it.

### Loopback by IP semantics

`client.host in {"127.0.0.1", "::1"}` rejected `127.0.0.2` and
`::ffff:127.0.0.1`, both of which are loopback. Now parsed with
`ipaddress.ip_address()`, unwrapping `ipv4_mapped` first; an absent or
unparseable address is not local.

### Headers

A successful grant answers `Cache-Control: no-store`. A `429` answers
`Retry-After` with the seconds remaining, which required
`OwnerUnlockRateLimitedError` to carry `retry_after_seconds` — a signature
change that also updated one existing test.

### Verification

- `just test` — **968 passed** (954 before, 14 added)
- `just lint` — clean
- `just typecheck` — mypy (90 files) and pyright, 0 errors
- `just audit` — Ruff S and pip-audit, no known vulnerabilities
- Real acceptance: **PASS**, 2026-09-02. Two parts.

  Voice regression via `just run-server` + `just run-robot`: a face-
  authenticated turn resolved `status=identified role=owner`, triggered the
  deterministic `get_children` tool, and a second unauthenticated turn
  completed normally — the identity and streaming paths this plan sits beside
  are unaffected.

  The three behaviors this plan actually changes were verified by direct HTTP
  calls to the live server (`POST /auth/owner/unlock`), not exercised by the
  voice path:

  ```text
  malformed PIN {"pin":"abc"}  -> 422, body has no trace of "abc"
  5x wrong 6-digit PIN         -> 401, 401, 401, 401, 401
  6th attempt                  -> 429, Retry-After: 59
  7th attempt (still blocked)  -> 429, Retry-After: 51
  ```

  The countdown between the 6th and 7th call confirms `retry_after_seconds` is
  computed from the real remaining block time, not a fixed value.

## Closure

Merged as PR #97 (`a944c7e`). Real HTTP acceptance and the voice regression
both recorded above. The capsule's next child is Plan 0034. Closing this plan
does not authorize it.
