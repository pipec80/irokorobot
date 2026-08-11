# Plan 0002a — Local-first provider quarantine

**Status:** Complete

**Prerequisite:** Plan 0002 (Active person context) is complete.

**Unblocks:** revalidation of Plan 0003. No later plan is automatically Ready.

## Outcome

The running server uses Ollama as its only LLM and consolidation provider.  No
direct Anthropic client, SDK dependency, configuration path, or provider
fallback remains reachable from application code.

This is deliberately a quarantine, not a cloud escalation feature.  A future
P2 `CognitiveEscalationGateway` may introduce a separately reviewed and
privacy-filtered cloud route.  It must not restore a generic provider switch.

## Why this comes first

The current default provider is Anthropic, while requests can contain private
conversation content and, for identified users, retrieved household memory.
P0.2 correctly prevents unknown people from reading that memory, but it does
not make the default generation path local.  Deterministic P0 tools should be
introduced only after this boundary is mechanically enforced.

## Scope

- Make Ollama the sole accepted runtime LLM provider.
- Route response generation and memory consolidation through Ollama only.
- Remove the Anthropic package and application client wrapper.
- Replace cloud-oriented example configuration with local provider guidance.
- Preserve the public `/chat`, `/transcribe`, and streaming response contracts.
- Prove the absence of direct Anthropic runtime references with tests and a
  repository search.

## Non-goals

- No cloud fallback, opt-in environment escape hatch, or escalation gateway.
- No change to identity, authorization, memory schema, prompt content, STT,
  TTS, vision, or robot code.
- No model download, model selection benchmark, or Ollama service deployment.
- No semantic change to the existing streaming NDJSON protocol.

## Files and ownership

| File | Change |
|---|---|
| `server/pyproject.toml` | Remove the direct `anthropic` dependency. |
| `uv.lock` | Regenerate lock data after dependency removal. |
| `server/src/server/settings.py` | Model an Ollama-only provider configuration and default. |
| `server/src/server/llm.py` | Remove cloud dispatch and direct Anthropic generation. |
| `server/src/server/memory/consolidation.py` | Use the existing local extractor only. |
| `server/src/server/streaming.py` | Retain only the supported local streaming path, if its current dispatcher still contains provider branching. |
| `server/src/server/llm_clients.py` | Delete after every import is removed. |
| `.env.example` | Document local Ollama defaults; remove cloud keys and stale provider examples. |
| `tests/unit/test_settings.py` | Replace Anthropic-default expectations. |
| `tests/unit/test_llm_generate.py` | Exercise the Ollama-only generation contract. |
| `tests/unit/test_consolidation_extract.py` | Exercise local-only extraction and failure behavior. |
| `tests/integration/test_transcribe_stream.py` | Preserve the public streaming contract. |

The exact streaming edit is conditional on a code reread immediately before
implementation; do not edit it merely because it is listed here.

## Execution sequence

1. Re-audit Git status, provider imports, configuration, and existing provider
   tests.  Stop if unrelated local changes overlap these files.
2. Add or update focused tests first.  Observe them fail while Anthropic remains
   the default or reachable provider.
3. Change settings so an unsupported provider value is rejected at validation
   time and the default is `ollama`.
4. Simplify generation and consolidation to their local implementations; retain
   existing timeout and error translation behavior.
5. Remove `llm_clients.py` only after `rg` confirms no callers.
6. Use `uv remove anthropic` from the relevant workspace package context to
   update the manifest and lockfile; never edit generated lock data by hand.
7. Update `.env.example` without placing a live server URL, secret, or model
   download instruction in source code.
8. Run the checks below.  Record the exact result before changing this plan to
   Complete.

## Acceptance criteria

- With no LLM environment variables, `Settings().llm_provider` is `ollama`.
- `LLM_PROVIDER=anthropic` fails configuration validation instead of silently
  selecting a cloud route.
- Normal generation and consolidation issue requests only to the configured
  local Ollama URL.
- The server package and lockfile no longer contain the Anthropic dependency.
- `rg -n -i "anthropic|claude" server/src server/pyproject.toml .env.example`
  returns no runtime/provider reference (historical documentation may be
  excluded explicitly and reviewed separately).
- `/chat`, `/transcribe`, and streaming shapes remain backward compatible.
- Existing local provider error handling remains typed and does not fall back to
  a remote service.

## Required tests

| Test | Proof |
|---|---|
| Settings default test | The default is local. |
| Settings invalid-provider test | Cloud cannot be selected by configuration. |
| LLM generation tests | Only the Ollama request adapter is invoked. |
| Consolidation tests | Extraction cannot select a remote implementation. |
| Streaming integration test | Client protocol remains unchanged. |
| Import/search check | No direct cloud runtime path survives. |

Use mocks for Ollama HTTP boundaries; no live model is needed for unit tests.

## Validation gates

Run from the repository root, adapting only where the current `justfile`
requires it:

```powershell
uv lock --check
just lint
just typecheck
just test
just audit
```

Also run the focused test files before the full suite and review `git diff
--check`.  Do not claim `just test` passes unless its command completes.  A
separate local preflight may verify that an already-installed Ollama instance
is reachable, but it is not a test prerequisite and must not download models.

## Demonstration

After the PR, start the server with an Ollama URL pointing to a test/local
instance, submit a normal `/chat` or `/transcribe` turn, and verify the same
public response envelope is returned.  Set `LLM_PROVIDER=anthropic` in a
separate process and verify startup/configuration rejects it.  This gives a
visible, falsifiable local-first milestone before P0.3 adds new cognition.

## Completion record

Completed on `feat/local-first-provider-quarantine` on 2026-08-11.

### TDD evidence

- `tests/unit/test_settings.py` first failed because the default remained
  `anthropic` and invalid `LLM_PROVIDER=anthropic` was accepted; then passed
  `7` tests after `Settings` became Ollama-only.
- Generation and consolidation each first failed when an invalid runtime
  provider mutation selected their removed cloud branch; their local-only tests
  then passed.
- Streaming first failed because a local `httpx.ConnectError` left the NDJSON
  response unclosed. `llm_streaming` now translates local transport and invalid
  NDJSON errors to `LLMError`; the pipeline emits its documented fallback and
  `done` event. The focused integration test passed.

### Final verification

- `just lint`: passed; 173 files unchanged after format.
- `just typecheck`: mypy passed for 64 source files; Pyright reported 0 errors,
  warnings, and information diagnostics.
- `just test`: **496 passed** in 46.31 s.
- `just audit`: passed; `pip-audit --local` found no known vulnerabilities.
- `uv lock --check`, `uv run --directory server deptry .`, `uv run ruff check
  .`, `uv run ruff format --check .`, and `git diff --check`: passed.
- `rg -n -i "anthropic|claude" server/src server/pyproject.toml .env.example`
  and the equivalent `uv.lock` check produced no runtime/provider match.

An independent review initially found the streaming fallback defect above; its
follow-up review reported no blockers after the fix. The local Ollama preflight
was attempted but `localhost:11434` refused the connection, so a live-model
demo is **not verified** in this workspace. No model was downloaded or service
configuration changed.
