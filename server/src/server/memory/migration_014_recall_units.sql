-- Migration 14 — the recall units and their two indexes (Plan 0078, ADR 0028 decision 1).
-- recall_units: one row per thing the owner can ask to recall — the owner's words of one VERIFIED
-- turn ('turn') or the diary summary of a conversation ('episode'). Each unit is deleted with its
-- record (and an episode unit with its episode); the record stays the source of truth.
-- recall_units_fts: external-content FTS5 without accents. recall_units_vec: 768-d cosine vectors,
-- partitioned by owner, with the sensitivity as a metadata column filtered inside the KNN query.
-- Triggers keep both indexes in step with the table. The missing indexes on the conversation
-- tables are added here. Atomic like 011 to 013; there is no down-step.
BEGIN;

CREATE TABLE recall_units (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_entity_id   INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    source_record_id  INTEGER NOT NULL REFERENCES conversation_records(id) ON DELETE CASCADE,
    episode_id        INTEGER REFERENCES conversation_episodes(id) ON DELETE CASCADE,
    kind              TEXT NOT NULL CHECK (kind IN ('turn', 'episode')),
    body              TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 2000),
    said_at           TEXT NOT NULL,
    visibility        TEXT NOT NULL CHECK (visibility = 'personal'),
    sensitivity       TEXT NOT NULL
                      CHECK (sensitivity IN ('normal', 'private', 'medical', 'location', 'security')),
    correlation_id    TEXT,
    embedding_model   TEXT,
    CHECK ((kind = 'episode') = (episode_id IS NOT NULL)),
    CHECK ((kind = 'turn') = (correlation_id IS NOT NULL))
);

CREATE INDEX recall_units_owner_time_idx ON recall_units (owner_entity_id, said_at);
CREATE INDEX recall_units_record_idx ON recall_units (source_record_id);
CREATE INDEX recall_units_episode_idx ON recall_units (episode_id);
CREATE INDEX recall_units_unembedded_idx ON recall_units (id) WHERE embedding_model IS NULL;

CREATE VIRTUAL TABLE recall_units_fts USING fts5(
    body, content='recall_units', content_rowid='id', tokenize='unicode61 remove_diacritics 2'
);
-- A deleted unit's words leave the index's storage at once, not at the next merge, like the
-- database's own `secure_delete` (ADR 0021 decision 6). A persistent option of this table.
INSERT INTO recall_units_fts (recall_units_fts, rank) VALUES ('secure-delete', 1);

CREATE VIRTUAL TABLE recall_units_vec USING vec0(
    owner_entity_id integer partition key, sensitivity text,
    embedding float[768] distance_metric=cosine
);

CREATE TRIGGER recall_units_ai AFTER INSERT ON recall_units BEGIN
    INSERT INTO recall_units_fts (rowid, body) VALUES (new.id, new.body);
END;

CREATE TRIGGER recall_units_ad AFTER DELETE ON recall_units BEGIN
    INSERT INTO recall_units_fts (recall_units_fts, rowid, body) VALUES ('delete', old.id, old.body);
    DELETE FROM recall_units_vec WHERE rowid = old.id;
END;

CREATE TRIGGER recall_units_au_sensitivity AFTER UPDATE OF sensitivity ON recall_units BEGIN
    UPDATE recall_units_vec SET sensitivity = new.sensitivity WHERE rowid = new.id;
END;

CREATE INDEX conversation_records_owner_idx ON conversation_records (owner_entity_id);
CREATE INDEX conversation_records_previous_idx ON conversation_records (previous_id);
CREATE INDEX conversation_episodes_owner_idx ON conversation_episodes (owner_entity_id);

PRAGMA user_version = 14;
COMMIT;
