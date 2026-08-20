CREATE TABLE IF NOT EXISTS owner_pin_credentials (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    person_entity_id    INTEGER NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
    algorithm           TEXT NOT NULL CHECK (algorithm = 'scrypt'),
    parameters_json     TEXT NOT NULL,
    salt                BLOB NOT NULL,
    verifier            BLOB NOT NULL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    revoked_at          TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS owner_pin_credentials_active_owner_idx
ON owner_pin_credentials (person_entity_id)
WHERE revoked_at IS NULL;
