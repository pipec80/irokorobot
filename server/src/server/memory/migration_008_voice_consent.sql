-- Migration 8 — consented speaker evidence (Plan 0053, PC-3B).
-- Mirrors migration 003 (face profiles) and 007 (face consent).
-- voice_consent_grants records an explicit, revocable consent to use a
-- person's voice as identity evidence. Only ONE active (unrevoked) grant may
-- exist per person, and revoking it must purge every voice_profiles row for
-- that person — see server/src/server/memory/voice_consent.py.
-- A voiceprint is a 192-d float32 ECAPA embedding, L2-normalized, stored as a
-- BLOB: verification compares against the CENTROID of the references, which is
-- what Plan 0047 measured, not a nearest-neighbour search. No audio is ever
-- stored. model_id pins the frozen model@revision that produced the vector;
-- vectors from any other model are ignored, never silently compared.

CREATE TABLE IF NOT EXISTS voice_consent_grants (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    person_entity_id    INTEGER NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
    purpose             TEXT NOT NULL CHECK (purpose = 'speaker_evidence'),
    granted_at          TEXT NOT NULL DEFAULT (datetime('now')),
    revoked_at          TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS voice_consent_grants_active_idx
ON voice_consent_grants (person_entity_id)
WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS voice_profiles (
    id          INTEGER PRIMARY KEY,
    entity_id   INTEGER NOT NULL REFERENCES entities(id),
    label       TEXT NOT NULL,
    embedding   BLOB NOT NULL,
    model_id    TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_voice_profiles_entity ON voice_profiles(entity_id);
