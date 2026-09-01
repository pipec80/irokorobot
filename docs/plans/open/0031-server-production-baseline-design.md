# Iroko Server Production Baseline Design

> **Status:** Reference-only umbrella. Never execute this document as one
> implementation batch.

**Goal:** Establish a durable, secure, idiomatic FastAPI/Starlette/Uvicorn
baseline after Plan 0030 closes, without changing framework or adding unused
infrastructure.

**Source of truth:**
[`server-production-baseline.md`](../../architecture/server-production-baseline.md)
and proposed ADRs [0010](../../adr/0010-fastapi-asgi-runtime-baseline.md),
[0011](../../adr/0011-sqlite-transaction-ownership.md),
[0012](../../adr/0012-line-delimited-stream-terminal-events.md), and
[0013](../../adr/0013-local-http-network-posture.md).

## Why this is an umbrella

The audited findings span independent security, persistence, CI, runtime,
lifecycle, HTTP-contract, and streaming concerns. Combining them would make
regressions hard to attribute and rollback unsafe. Each child plan below
produces a separately testable improvement and requires independent review.

## Locked order

| Order | Plan | Outcome | Depends on |
|---:|---|---|---|
| 1 | [0032](0032-server-privacy-and-request-observability.md) | No sensitive household content in normal logs; request correlation | Plan 0030 closed |
| 2 | [0033](0033-owner-unlock-http-hardening.md) | Deterministic PIN validation and race-safe limiter | 0032 |
| 3 | [0034](0034-upload-and-multipart-security.md) | Raw and semantic upload limits | 0033 |
| 4 | [0035](0035-sqlite-transaction-owner.md) | One transaction owner and concurrency primitive | 0034 |
| 5 | [0036](0036-sqlite-write-migration-and-outbox-removal.md) | All runtime writes migrated; unused outbox removed | 0035 |
| 6 | [0037](0037-deterministic-ci-baseline.md) | Deterministic API/local integration PR gate | 0036 |
| 7 | [0038](0038-uvicorn-runtime-baseline.md) | Explicit safe ASGI runtime configuration | 0037 |
| 8 | [0039](0039-application-lifecycle-and-http-resources.md) | Owned lifespan and outbound HTTP resources | 0038 |
| 9 | [0040](0040-fastapi-contract-and-openapi-baseline.md) | Typed HTTP composition, docs, and readiness | 0039 |
| 10 | [0041](0041-streaming-terminal-contract.md) | Coordinated terminal `error` event | 0040 |
| 11 | [0042](0042-server-baseline-closure.md) | Runtime acceptance and canonical closure | 0041 |

Only one child may be `NOW`. A child plan's presence is not implementation or
commit authorization.

## Global constraints

- Preserve the immutable `/transcribe` and WAV contracts.
- Preserve server/robot separation.
- Keep one Uvicorn worker and loopback default.
- Use TDD with observed RED and GREEN for each behavior change.
- Do not log transcripts, model output, TTS sentences, PINs, tokens, raw
  visual descriptions, biometrics, or household values.
- Do not add SQLAlchemy, Redis, Celery, Docker, Kubernetes, OAuth2, wildcard
  CORS, an external DI container, or a manual OpenAPI file.
- Use `just` commands when a task exists; commands are PowerShell-compatible.
- Stage only explicitly named files; never use `git add -A`.
- A plan never authorizes a commit or merge by itself.

## Promotion rule

After Plan 0030 closes, revalidate Plan 0032's named log sites and tests against
merged code. If they still match, update the operational board to make 0032
the only `NOW` item. Repeat this narrow audit at each child boundary.
