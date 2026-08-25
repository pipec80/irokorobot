-- Migration 7 — biometric consent for local face evidence (Plan 0029, PC-2).
-- face_consent_grants records an explicit, revocable consent to use a
-- person's face as owner-authentication evidence. Only ONE active
-- (unrevoked) grant may exist per person at a time; revoking it must also
-- purge every stored face_profiles/vec_faces row for that person — see
-- server/src/server/memory/biometric_consent.py.

CREATE TABLE IF NOT EXISTS face_consent_grants (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    person_entity_id    INTEGER NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
    purpose             TEXT NOT NULL CHECK (purpose = 'owner_authentication'),
    granted_at          TEXT NOT NULL DEFAULT (datetime('now')),
    revoked_at          TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS face_consent_grants_active_idx
ON face_consent_grants (person_entity_id)
WHERE revoked_at IS NULL;
