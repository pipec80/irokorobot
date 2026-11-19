-- Migration 22 — the audit kind of an export of the household data (Plan 0087 D-7, ADR 0032
-- decision 8). `admin_audit` has closed CHECKs, so it is rebuilt as migration 013 did, adding the
-- target kind `household_data`: one row per `iroko-admin export` attempt, never a value, a name or
-- a path. Every row and id is kept (the AUTOINCREMENT counter follows the copied ids) and both
-- indexes are created again. The table is a child only (its foreign key names `entities`), so the
-- rebuild runs with foreign keys off as every rebuild does; the runner's foreign-key guard proves
-- nothing dangles. No transaction statements: the runner wraps this file.

CREATE TABLE admin_audit_new (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at         TEXT NOT NULL,
    actor_label         TEXT NOT NULL CHECK (length(actor_label) BETWEEN 1 AND 80),
    actor_role          TEXT NOT NULL CHECK (actor_role IN ('owner', 'builder')),
    channel             TEXT NOT NULL CHECK (channel = 'admin_local'),
    operation           TEXT NOT NULL CHECK (
        operation IN ('add', 'change', 'revoke', 'grant', 'export', 'delete')
    ),
    target_kind         TEXT NOT NULL CHECK (
        target_kind IN (
            'pool_literal', 'pool_relation', 'care_contact',
            'conversation_consent', 'conversation_record', 'household_data'
        )
    ),
    field_id            TEXT,
    target_entity_id    INTEGER REFERENCES entities(id) ON DELETE SET NULL,
    outcome             TEXT NOT NULL CHECK (outcome IN ('applied', 'refused')),
    reason              TEXT
);

INSERT INTO admin_audit_new (
    id, recorded_at, actor_label, actor_role, channel, operation, target_kind, field_id,
    target_entity_id, outcome, reason
)
SELECT
    id, recorded_at, actor_label, actor_role, channel, operation, target_kind, field_id,
    target_entity_id, outcome, reason
FROM admin_audit;

DROP TABLE admin_audit;
ALTER TABLE admin_audit_new RENAME TO admin_audit;
CREATE INDEX admin_audit_recorded_at_idx ON admin_audit (recorded_at DESC, id DESC);
CREATE INDEX admin_audit_target_entity_id_idx ON admin_audit (target_entity_id);
