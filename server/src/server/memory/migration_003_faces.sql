-- Migration 3 — face recognition (V1, docs/audit/05 §3).
-- face_profiles links each face embedding to the SAME memory entity the
-- conversation already knows ("Valentina" the face IS "Valentina" the
-- daughter). One entity may hold several profiles — re-enrolling on a
-- different day adds robustness. vec_faces rowid == face_profiles.id.

CREATE TABLE IF NOT EXISTS face_profiles (
    id          INTEGER PRIMARY KEY,
    entity_id   INTEGER NOT NULL REFERENCES entities(id),
    label       TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_face_profiles_entity ON face_profiles(entity_id);

CREATE VIRTUAL TABLE IF NOT EXISTS vec_faces USING vec0(embedding float[512]);
