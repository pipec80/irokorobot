# 0010 — Standardize the FastAPI/ASGI runtime baseline

- **Status:** Proposed
- **Date:** 2026-08-31

## Context

Iroko already uses FastAPI, Starlette, Pydantic, Uvicorn, HTTPX, and asyncio,
but its HTTP conventions grew feature by feature. The server now handles
audio, images, identity grants, streaming, local models, and domestic data.
The project needs one explicit runtime philosophy without adopting unused
enterprise infrastructure.

## Decision

Keep FastAPI as the HTTP composition boundary and Uvicorn as the ASGI server.
Use FastAPI/Pydantic for typed contracts, validation, dependencies, response
filtering, exception translation, and OpenAPI; use Starlette for justified
ASGI middleware; keep domain code independent of FastAPI.

Run one Uvicorn worker while grants, models, SQLite state, and background jobs
are process-local. Lifespan owns long-lived resources and guarantees cleanup.
Loopback, disabled proxy trust, and no CORS remain defaults. Features are added
only for demonstrated requirements.

## Alternatives considered

- **Change framework:** rejected because the verified gaps are lifecycle,
  boundary, and operational issues rather than FastAPI limitations.
- **Adopt a DI container/hexagonal rewrite:** rejected as disproportionate to
  the small server and likely to obscure existing domain boundaries.
- **Use every FastAPI feature proactively:** rejected because unused OAuth2,
  CORS, WebSockets, SSE, and middleware increase attack and maintenance cost.
- **Leave conventions implicit:** rejected because future endpoints would
  repeatedly rediscover validation, lifecycle, logging, and testing policy.

## Consequences

### Positive

- New endpoints inherit one predictable HTTP pattern.
- Generated OpenAPI can represent the actual runtime contract.
- Resource ownership and shutdown become testable.
- The cognitive core remains portable and framework-independent.

### Negative

- Existing globals require incremental migration.
- One worker constrains horizontal process scaling.
- Some improvements require coordinated server/robot contract tests.

## Review

Review after a real need for independently deployed clients, multiple workers,
a new transport, or a different process topology. Acceptance requires Pipec's
explicit review; implementation plans do not accept this ADR implicitly.
