-- Migration 23 — the owner's documents and their sections (Plan 0088 D-8, ADR 0034 decision 4).
-- document_sources: one loaded file (or one kept camera reading) of one owner; the same file twice
-- is refused by its hash. document_sections: its text cut under the embedding window, each with
-- its heading path; a body never changes (a trigger refuses it). document_sections_fts is the word
-- index (external content, no accents, `secure-delete` on) and document_sections_vec the 768-d
-- cosine vectors, partitioned by owner with the level and the source as metadata columns filtered
-- inside the KNN. Triggers keep both indexes in step, so deleting a source (CASCADE) removes every
-- trace. `vector_refused_by` names the model that refused a section as too long: it stays
-- searchable by its words and is not offered to that model again (D-10). `admin_audit` has closed
-- checks, so it is rebuilt as migration 022 did, adding the operation `list` and the target kind
-- `document`; every row, id and index is kept. No transaction statements: the runner wraps this
-- file.

CREATE TABLE admin_audit_new (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at         TEXT NOT NULL,
    actor_label         TEXT NOT NULL CHECK (length(actor_label) BETWEEN 1 AND 80),
    actor_role          TEXT NOT NULL CHECK (actor_role IN ('owner', 'builder')),
    channel             TEXT NOT NULL CHECK (channel = 'admin_local'),
    operation           TEXT NOT NULL CHECK (
        operation IN ('add', 'change', 'revoke', 'grant', 'export', 'delete', 'list')
    ),
    target_kind         TEXT NOT NULL CHECK (
        target_kind IN (
            'pool_literal', 'pool_relation', 'care_contact',
            'conversation_consent', 'conversation_record', 'household_data', 'document'
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

CREATE TABLE document_sources (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_entity_id       INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    title                 TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 120),
    file_sha256           TEXT NOT NULL CHECK (length(file_sha256) = 64),
    format                TEXT NOT NULL CHECK (format IN ('md', 'txt', 'pdf', 'camera')),
    level                 TEXT NOT NULL CHECK (level IN ('normal', 'sensitive')),
    channel               TEXT NOT NULL
                          CHECK (channel IN ('admin_local', 'import_file', 'voice_camera')),
    loaded_at             TEXT NOT NULL CHECK (
        length(loaded_at) = 32
        AND loaded_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
        AND strftime('%Y-%m-%dT%H:%M:%S', substr(loaded_at, 1, 19)) IS substr(loaded_at, 1, 19)
    ),
    loaded_by_entity_id   INTEGER REFERENCES entities(id) ON DELETE SET NULL,
    sections              INTEGER NOT NULL CHECK (sections >= 0),
    characters            INTEGER NOT NULL CHECK (characters >= 0),
    UNIQUE (owner_entity_id, file_sha256)
) STRICT;

CREATE INDEX document_sources_loaded_by_idx ON document_sources (loaded_by_entity_id);

CREATE TABLE document_sections (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id          INTEGER NOT NULL REFERENCES document_sources(id) ON DELETE CASCADE,
    position           INTEGER NOT NULL CHECK (position >= 0),
    heading            TEXT NOT NULL CHECK (length(heading) <= 400),
    body               TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 1200),
    body_sha256        TEXT NOT NULL CHECK (length(body_sha256) = 64),
    embedding_model    TEXT,
    vector_refused_by  TEXT,
    UNIQUE (source_id, position)
) STRICT;

CREATE INDEX document_sections_unembedded_idx ON document_sections (id)
    WHERE embedding_model IS NULL;
CREATE INDEX document_sections_model_idx ON document_sections (embedding_model)
    WHERE embedding_model IS NOT NULL;

CREATE VIRTUAL TABLE document_sections_fts USING fts5(
    heading, body, content='document_sections', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);
INSERT INTO document_sections_fts (document_sections_fts, rank) VALUES ('secure-delete', 1);

CREATE VIRTUAL TABLE document_sections_vec USING vec0(
    owner_entity_id integer partition key, level text, source_id integer,
    embedding float[768] distance_metric=cosine
);

CREATE TRIGGER document_sections_ai AFTER INSERT ON document_sections BEGIN
    INSERT INTO document_sections_fts (rowid, heading, body)
    VALUES (new.id, new.heading, new.body);
END;

CREATE TRIGGER document_sections_ad AFTER DELETE ON document_sections BEGIN
    INSERT INTO document_sections_fts (document_sections_fts, rowid, heading, body)
    VALUES ('delete', old.id, old.heading, old.body);
    DELETE FROM document_sections_vec WHERE rowid = old.id;
END;

CREATE TRIGGER document_sections_text_locked
BEFORE UPDATE OF body, heading ON document_sections BEGIN
    SELECT RAISE(ABORT, 'document section text is immutable');
END;
