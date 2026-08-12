CREATE TABLE IF NOT EXISTS household_role_assignments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    person_entity_id    INTEGER NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
    role                TEXT NOT NULL CHECK (role IN ('owner', 'adult', 'child', 'guest')),
    grantor_entity_id   INTEGER REFERENCES entities(id) ON DELETE SET NULL,
    reason              TEXT NOT NULL,
    granted_at          TEXT NOT NULL DEFAULT (datetime('now')),
    revoked_at          TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS household_role_assignments_active_person_idx
    ON household_role_assignments (person_entity_id)
    WHERE revoked_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS household_role_assignments_single_active_owner_idx
    ON household_role_assignments (role)
    WHERE role = 'owner' AND revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS authorization_audit_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_entity_id     INTEGER REFERENCES entities(id) ON DELETE SET NULL,
    target_entity_id    INTEGER REFERENCES entities(id) ON DELETE SET NULL,
    action              TEXT NOT NULL,
    data_categories     TEXT NOT NULL,
    decision            TEXT NOT NULL CHECK (decision IN ('allowed', 'denied', 'requires_confirmation')),
    policy_id           TEXT NOT NULL,
    reason              TEXT NOT NULL,
    correlation_id      TEXT NOT NULL,
    evaluated_at        TEXT NOT NULL,
    expires_at          TEXT
);

CREATE INDEX IF NOT EXISTS authorization_audit_events_correlation_idx
    ON authorization_audit_events (correlation_id, evaluated_at);
