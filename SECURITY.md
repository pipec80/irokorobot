# Security Policy

## Supported versions

This project is in early development (`0.x`). Only the latest release on `main`
receives security fixes.

| Version | Supported |
|---------|-----------|
| 0.x     | ✅        |

## Reporting a vulnerability

Please **do not** open a public issue for security vulnerabilities.

Instead, report privately using GitHub's
[private vulnerability reporting](https://github.com/pipec80/irokorobot/security/advisories/new),
or email **pipec800@gmail.com** with:

- A description of the vulnerability and its impact.
- Steps to reproduce (a proof of concept if possible).
- The affected version or commit.

You can expect an initial response within a reasonable timeframe. This is a
personal project maintained on a best-effort basis.

## Scope

Iroko is designed as a **local-first, home** system. It is not intended to be
exposed directly to the public internet. Deployments that expose the API
publicly do so at their own risk.

## Network posture (ADR-0013)

- **Loopback by default.** `SERVER_HOST=127.0.0.1` out of the box. LAN
  binding (`0.0.0.0` or a LAN address) is an explicit deployment decision,
  never assumed.
- **Proxy headers are not trusted by default** (`UVICORN_PROXY_HEADERS=false`).
  A non-loopback deployment behind a reverse proxy must configure allowed
  hosts and trust forwarded headers only from a named proxy address.
- **No CORS.** No cross-origin browser access is currently supported or
  configured.
- **Owner unlock is never exposed through a public proxy.** Request IDs,
  forwarded addresses, and any face/voice/text identity evidence are
  context only — none of them grants authorization by themselves.
- **One Uvicorn worker, always** (`UVICORN_WORKERS` is fixed to `1`) —
  owner-unlock grants, SQLite state, and background jobs are process-local
  (ADR-0010); a second worker would silently split them across processes.

## Upload limits (Plan 0034)

Every upload is bounded twice: a raw ASGI body-size ceiling
(`MAX_REQUEST_BODY_BYTES`, Starlette's native
`RequestBodyLimitMiddleware`), checked before any parsing, and per-file
semantic budgets (`MAX_AUDIO_UPLOAD_BYTES`, `MAX_IMAGE_UPLOAD_BYTES`,
`MAX_IMAGE_PIXELS`, `MAX_AUDIO_DURATION_S`) checked per part. An oversized
request is rejected with `413` before it reaches STT/vision processing, and
an upload's own `filename` is never trusted for any filesystem or logging
decision.

## Logging rules

Server and robot logs never contain raw transcript text, LLM response
content, scene descriptions, PINs, tokens, or household values — only
lengths (`"%d chars"`), bounded outcome codes, and timing. This is verified
mechanically as part of every server baseline closure
(`docs/architecture/server-production-baseline.md`).
