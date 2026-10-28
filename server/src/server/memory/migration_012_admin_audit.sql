-- Migration 12 — the admin audit (Plan 0073 Task 1, ADR 0025 decision 4).
-- One row per mutating admin operation (add, change, revoke) run through `iroko-admin`: actor,
-- role, channel, operation, the field or section id and the affected entity, outcome and time.
-- It holds **no household value** (no value, name or phone column): a change is traceable without
-- exposing what changed. New and unread by any older code, so there is no down-step: the rollback
-- is to leave it. Atomic like 011. Timestamps follow migration 004 (UTC text; the caller states
-- when it happened). The CHECKs are closed on purpose: the Python repository validates first.
BEGIN;

CREATE TABLE admin_audit (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at         TEXT NOT NULL,
    actor_label         TEXT NOT NULL CHECK (length(actor_label) BETWEEN 1 AND 80),
    actor_role          TEXT NOT NULL CHECK (actor_role IN ('owner', 'builder')),
    channel             TEXT NOT NULL CHECK (channel = 'admin_local'),
    operation           TEXT NOT NULL CHECK (operation IN ('add', 'change', 'revoke')),
    target_kind         TEXT NOT NULL CHECK (
        target_kind IN ('pool_literal', 'pool_relation', 'care_contact')
    ),
    field_id            TEXT,
    target_entity_id    INTEGER REFERENCES entities(id) ON DELETE SET NULL,
    outcome             TEXT NOT NULL CHECK (outcome IN ('applied', 'refused')),
    reason              TEXT
);

-- The `audit` sub-command lists the most recent operations first.
CREATE INDEX admin_audit_recorded_at_idx ON admin_audit (recorded_at DESC, id DESC);

PRAGMA user_version = 12;
COMMIT;
