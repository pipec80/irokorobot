# Evaluation reports

> **Status:** Canonical. Rules for safe, attributable evaluation reports written
> by the offline eval runners (`scripts/eval_*.py`). These runners exercise real
> Ollama and a real (temporary) database; they are **not** part of `just test`.

Reports land in this directory (`docs/evals/`) and nowhere else. Each report is
a point-in-time record: it is never overwritten, and it carries enough metadata
(git commit, dataset hash, model names, sanitized command) to reproduce the run.

## Longitudinal-memory baseline — `just eval-longitudinal`

`scripts/eval_longitudinal_memory.py` (Plan 0046, milestone CM-0) probes whether
the current runtime supports longitudinal memory: durable multi-session recall,
correction, authorized cross-person privacy, complete deletion, provenance and
false-memory resistance. It runs the deterministic synthetic suite in
`tests/evals/golden_longitudinal_memory.yaml` against real Ollama and a
throwaway database.

```powershell
just services            # Ollama must be up with the consolidation model pulled
just eval-longitudinal   # full gating baseline needs --runs 3 and no --only
```

### Preflight

Before touching the database the runner issues a cheap `GET {OLLAMA_URL}/api/version`.
If Ollama does not answer, the runner writes **no report**, closes every
resource, and exits `2`. Provider or network failure is always a harness error —
never a cognitive result, and never a reason to fall back to a cloud provider.

### Exit codes (automation contract)

| Code | Meaning |
|---|---|
| `0` | Valid full suite **and** every frozen cognitive gate passed: `forbidden_disclosure_rate == 0.0`, `complete_deletion_rate == 1.0`, `truth_current_accuracy == 1.0`, `provenance_accuracy == 1.0` (each with a non-empty denominator). |
| `1` | Valid full suite, no harness/provider error, but at least one cognitive case **failed or is unsupported** — the expected CM-0 (RED) outcome. |
| `2` | Invalid dataset/configuration, unsafe output path, unavailable provider, malformed response, incomplete run, or an internal harness error. No baseline report is written. |

A `--only` run is smoke/debug: it is marked **non-gating**, so it can never
report `0` on the strength of the gates. A full gating baseline requires every
version-1 scenario and `--runs 3`.

### Expected RED baseline (CM-0)

The current runtime supports only single-turn extraction. Every other
longitudinal operation (`propose`, `restart`, `recall`, `correct`, `forget`,
`inspect_derivatives`) has no safe public seam yet, so the runner records it as
`unsupported` with the exact missing capability — it is never simulated with an
injected context or a database reconnect. The expected result today is exit
`1`: extraction PASSes, everything else is honestly `unsupported`.

### Safe output paths and non-overwrite

- The report path must resolve **inside `docs/evals/`**. Anything else exits `2`.
- If the target file already exists, the runner exits `2` and writes nothing.
  Pick a new name (e.g. add a date) rather than deleting the old report.
- The runner never accepts a `--database` option and never opens the configured
  production database.

### Temporary database

The run creates a `TemporaryDirectory` (`iroko-cm0-…`), migrates a fresh
`brain.db` inside it, points `settings.brain_db_path` at it **for the process
only** (never `.env`), and on exit always closes the connection and restores the
original setting. The temporary directory then removes the `.db`, `-wal` and
`-shm` files. A pre-existing open connection, a path-proof failure, a migration
error or a cleanup error each exit `2`.

### What a report may and may not contain

- **May** contain synthetic model output — every identity, place and fact in the
  suite is invented.
- **Must not** contain secrets, credentials, local absolute paths, real
  household names or reserved terms. The Ollama URL is stored stripped of user
  info and query string; each `--reserved-term` value is replaced with
  `<redacted>` and only its count is kept.
