# Owner Unlock HTTP Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:test-driven-development` and
> `superpowers:verification-before-completion`.

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
