# 0013 — Keep the HTTP server local-first by default

- **Status:** Proposed
- **Date:** 2026-08-31

## Context

Iroko processes domestic audio, images, identity evidence, and memory. The
current server binds to loopback and the owner unlock path relies on the direct
client address. Future LAN or reverse-proxy deployment changes the trust
boundary for host headers, forwarded addresses, TLS, and browser origins.

## Decision

Keep loopback binding, disabled proxy headers, and no CORS as defaults. Treat
LAN binding as an explicit deployment decision. Trust forwarded headers only
from a named proxy address, configure allowed hosts for any non-loopback
deployment, and terminate TLS at a documented trusted proxy when TLS becomes
required.

Never expose owner unlock directly through a public proxy. Request IDs,
forwarded addresses, face, voice, text, and names are context/evidence only;
they do not grant authorization.

## Alternatives considered

- **Bind to all interfaces by default:** rejected because convenience does not
  justify widening access to household data.
- **Trust all forwarded headers:** rejected because a direct client could spoof
  loopback/source information.
- **Enable wildcard CORS:** rejected because no current cross-origin browser
  requirement exists.
- **Add HTTPS redirect now:** rejected until the TLS termination topology is
  real and testable.

## Consequences

### Positive

- Safe local development and operation remain the default.
- LAN/proxy exposure requires visible, reviewable configuration.
- Owner unlock cannot silently inherit proxy trust.

### Negative

- Remote access needs explicit deployment work.
- Proxy configuration and direct-address semantics require coordinated tests.

## Review

Review before LAN exposure, remote access, a browser on another origin, or a
reverse proxy becomes part of the supported runtime.
