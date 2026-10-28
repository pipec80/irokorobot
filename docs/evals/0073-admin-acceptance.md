# Plan 0073 — local admin CRUD, acceptance (outcomes only)

> Run by Pipec on 2026-10-28 on a database kept apart (`BRAIN_DB_PATH` set to a scratch file,
> created with `just setup-personal`), the server stopped. Outcomes only, never a value: the
> scratch database held invented local data and was destroyed after the run.

## What ran

| Step | Result |
|---|---|
| `just setup-personal` on the scratch path | owner and PIN created; `status` showed `schema_version=12`, owner ready |
| `iroko-admin list` | printed the pool (empty at first) and the two `child_of` relations; no contacts |
| `iroko-admin status` | printed every section (acta vs. rows now) and the six capabilities' recomputed verdict; did not crash on a record with no readiness |
| `iroko-admin add likes` | value typed at the prompt, confirmed `SI`, **no PIN asked**, applied |
| `iroko-admin add medication` | value typed, `SI`, **PIN asked** and accepted, applied |
| `iroko-admin revoke literal <id>` | `SI`, PIN asked and accepted, applied; a follow-up `list` no longer showed that fact (history, not deleted) |
| `iroko-admin audit` | listed the operations with **no value, phone or name** (only the field id such as `medication`) |
| `iroko-admin list` with the server running | refused: «El servidor está encendido…» |
| `iroko-admin list` against the **real** database (env var lost, fell back to `data/omnibot.db`) | refused: «La base de datos no está en la última versión» — the tool never created or migrated it, so the real database was untouched (migration 012 is not on `main`) |

## Not exercised live (covered by automated tests)

- The wrong-PIN refusal (`verify_owner_pin` → `AdminPinError`): the PIN mechanism was proven live
  (prompted and accepted on the sensitive operations); the explicit three-wrong-tries refusal is
  covered by `tests/integration/test_admin_pin.py` and `test_admin_cli.py`.
- The contact path (`change-contact`, `revoke contact`): no contact was loaded on the scratch
  database (the `seed-import` step was skipped), so these were not run live; they are covered by
  `tests/integration/test_admin_revoke.py` and the CLI test. The CLI verb to **create** a new
  contact entity is deferred (a named follow-up); `apply_contact_edit` is complete and tested.

## Verdict

**PASS.** The local amendment path works: an operator on the machine lists, adds, changes and
revokes the loaded data through the canonical writers, the PIN gates the sensitive writes, the audit
holds no household value, and the command refuses a running server and a database behind the schema.
No behaviour reaches the voice, so there is no hardware case.
