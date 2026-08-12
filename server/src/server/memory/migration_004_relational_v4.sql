CREATE TABLE IF NOT EXISTS literal_facts_v4 (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_entity_id       INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    predicate               TEXT NOT NULL,
    value_text              TEXT NOT NULL,
    confidence              REAL NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    source_memory_id        INTEGER REFERENCES memories(id) ON DELETE SET NULL,
    confirmed_by_entity_id  INTEGER REFERENCES entities(id) ON DELETE SET NULL,
    asserted_at             TEXT NOT NULL DEFAULT (datetime('now')),
    confirmed_at            TEXT,
    valid_from              TEXT,
    valid_to                TEXT,
    lifecycle               TEXT NOT NULL DEFAULT 'active' CHECK (
        lifecycle IN ('active', 'superseded', 'disputed', 'revoked', 'expired')
    ),
    visibility              TEXT NOT NULL DEFAULT 'household' CHECK (
        visibility IN ('public', 'household', 'adults', 'personal', 'private', 'temporary')
    ),
    sensitivity             TEXT NOT NULL DEFAULT 'normal' CHECK (
        sensitivity IN ('normal', 'private', 'biometric', 'medical', 'location', 'child_data', 'security')
    ),
    superseded_at           TEXT,
    superseded_by           INTEGER REFERENCES literal_facts_v4(id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS literal_facts_v4_active_value_idx
    ON literal_facts_v4 (subject_entity_id, predicate, value_text)
    WHERE lifecycle = 'active';

CREATE INDEX IF NOT EXISTS literal_facts_v4_active_subject_predicate_idx
    ON literal_facts_v4 (subject_entity_id, predicate)
    WHERE lifecycle = 'active';

CREATE TABLE IF NOT EXISTS entity_relations_v4 (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    source_entity_id        INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    predicate               TEXT NOT NULL,
    target_entity_id        INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    confidence              REAL NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    source_memory_id        INTEGER REFERENCES memories(id) ON DELETE SET NULL,
    confirmed_by_entity_id  INTEGER REFERENCES entities(id) ON DELETE SET NULL,
    asserted_at             TEXT NOT NULL DEFAULT (datetime('now')),
    confirmed_at            TEXT,
    valid_from              TEXT,
    valid_to                TEXT,
    lifecycle               TEXT NOT NULL DEFAULT 'active' CHECK (
        lifecycle IN ('active', 'superseded', 'disputed', 'revoked', 'expired')
    ),
    visibility              TEXT NOT NULL DEFAULT 'household' CHECK (
        visibility IN ('public', 'household', 'adults', 'personal', 'private', 'temporary')
    ),
    sensitivity             TEXT NOT NULL DEFAULT 'normal' CHECK (
        sensitivity IN ('normal', 'private', 'biometric', 'medical', 'location', 'child_data', 'security')
    ),
    superseded_at           TEXT,
    superseded_by           INTEGER REFERENCES entity_relations_v4(id) ON DELETE SET NULL,
    CHECK (source_entity_id != target_entity_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS entity_relations_v4_active_triple_idx
    ON entity_relations_v4 (source_entity_id, predicate, target_entity_id)
    WHERE lifecycle = 'active';

CREATE INDEX IF NOT EXISTS entity_relations_v4_active_source_predicate_idx
    ON entity_relations_v4 (source_entity_id, predicate)
    WHERE lifecycle = 'active';

CREATE INDEX IF NOT EXISTS entity_relations_v4_active_target_predicate_idx
    ON entity_relations_v4 (target_entity_id, predicate)
    WHERE lifecycle = 'active';

CREATE TABLE IF NOT EXISTS legacy_fact_migration_v4 (
    legacy_fact_id          INTEGER PRIMARY KEY REFERENCES facts(id) ON DELETE RESTRICT,
    outcome                 TEXT NOT NULL CHECK (outcome IN ('migrated', 'deferred', 'rejected')),
    literal_fact_v4_id      INTEGER REFERENCES literal_facts_v4(id) ON DELETE RESTRICT,
    entity_relation_v4_id   INTEGER REFERENCES entity_relations_v4(id) ON DELETE RESTRICT,
    reason                  TEXT NOT NULL,
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (
        (outcome = 'migrated' AND (
            (literal_fact_v4_id IS NOT NULL AND entity_relation_v4_id IS NULL) OR
            (literal_fact_v4_id IS NULL AND entity_relation_v4_id IS NOT NULL)
        )) OR
        (outcome IN ('deferred', 'rejected') AND literal_fact_v4_id IS NULL AND entity_relation_v4_id IS NULL)
    )
);
