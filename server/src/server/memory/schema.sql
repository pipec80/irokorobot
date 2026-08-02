-- =====================================================================
-- OMNiBot brain schema v1
-- Apply by reading PRAGMA user_version; if < 1, execute and set to 1.
-- =====================================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

-- ---------------------------------------------------------------------
-- ENTITIES: personas, lugares, objetos, preferencias con JSON attributes
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entities (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL CHECK (type IN (
        'person', 'place', 'object', 'event',
        'preference', 'schedule', 'concept', 'other'
    )),
    attributes  TEXT NOT NULL DEFAULT '{}',   -- JSON
    aliases     TEXT NOT NULL DEFAULT '[]',   -- JSON array
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (name, type)
);

CREATE INDEX IF NOT EXISTS entities_name_idx ON entities (name);
CREATE INDEX IF NOT EXISTS entities_type_idx ON entities (type);

-- ---------------------------------------------------------------------
-- FACTS: triples (entity, predicate, object) con versionado
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS facts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id       INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    predicate       TEXT NOT NULL,
    object_value    TEXT NOT NULL,
    confidence      REAL NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    source_memory_id INTEGER REFERENCES memories(id) ON DELETE SET NULL,
    asserted_at     TEXT NOT NULL DEFAULT (datetime('now')),
    superseded_at   TEXT,
    superseded_by   INTEGER REFERENCES facts(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS facts_active_idx
    ON facts (entity_id, predicate)
    WHERE superseded_at IS NULL;

-- ---------------------------------------------------------------------
-- MEMORIES: episodios y reflexiones con embedding asociado en vec_memories
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memories (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    kind              TEXT NOT NULL CHECK (kind IN ('episodic', 'semantic', 'reflection')),
    content           TEXT NOT NULL,
    summary           TEXT,
    metadata          TEXT NOT NULL DEFAULT '{}',  -- JSON
    importance        REAL NOT NULL DEFAULT 0.5 CHECK (importance BETWEEN 0 AND 1),
    related_entities  TEXT NOT NULL DEFAULT '[]', -- JSON array of entity IDs
    last_accessed_at  TEXT,
    access_count      INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    archived_at       TEXT
);

CREATE INDEX IF NOT EXISTS memories_kind_idx ON memories (kind) WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS memories_importance_idx
    ON memories (importance DESC) WHERE archived_at IS NULL;

-- ---------------------------------------------------------------------
-- VEC_MEMORIES: tabla virtual de sqlite-vec
-- rowid == memories.id   (mapping 1:1)
-- ---------------------------------------------------------------------
CREATE VIRTUAL TABLE IF NOT EXISTS vec_memories USING vec0(
    embedding float[768]
);

-- ---------------------------------------------------------------------
-- SENSOR_CURRENT: 1 fila por sensor, siempre la última lectura
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sensor_current (
    sensor_id   TEXT PRIMARY KEY,
    sensor_type TEXT NOT NULL,      -- 'temperature', 'gas', 'battery', etc.
    value       REAL NOT NULL,
    unit        TEXT NOT NULL,      -- 'celsius', 'ppm', 'percent', etc.
    location    TEXT,               -- 'kitchen', 'living_room', ''
    metadata    TEXT NOT NULL DEFAULT '{}',
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------
-- SENSOR_READINGS: crudo, retención corta
-- Insertado solo cuando el sensor hub considera la lectura "significativa"
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sensor_readings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_id   TEXT NOT NULL,
    sensor_type TEXT NOT NULL,
    value       REAL NOT NULL,
    unit        TEXT NOT NULL,
    location    TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS readings_sensor_time_idx
    ON sensor_readings (sensor_id, created_at DESC);

-- ---------------------------------------------------------------------
-- SENSOR_AGGREGATES_HOURLY: rollup automático
-- Poblado por un job (ver módulo sensors/aggregator.py)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sensor_aggregates_hourly (
    sensor_id    TEXT NOT NULL,
    hour_bucket  TEXT NOT NULL,  -- 'YYYY-MM-DD HH:00:00'
    avg_value    REAL NOT NULL,
    min_value    REAL NOT NULL,
    max_value    REAL NOT NULL,
    count        INTEGER NOT NULL,
    PRIMARY KEY (sensor_id, hour_bucket)
);

-- ---------------------------------------------------------------------
-- EVENTS: hechos estructurados detectados (umbrales cruzados, alertas)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type   TEXT NOT NULL,   -- 'gas_alert', 'low_battery', 'temp_spike'
    severity     TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    sensor_id    TEXT,
    value        REAL,
    payload      TEXT NOT NULL DEFAULT '{}',  -- JSON con detalles
    memory_id    INTEGER REFERENCES memories(id) ON DELETE SET NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS events_type_time_idx ON events (event_type, created_at DESC);

-- ---------------------------------------------------------------------
-- EMBEDDINGS_CACHE: hash(text) -> vector blob
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS embeddings_cache (
    text_hash   TEXT PRIMARY KEY,   -- sha256[:16]
    model       TEXT NOT NULL,
    vector      BLOB NOT NULL,      -- float32 packed
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------
-- OUTBOX: cola de cambios para sync futuro (hoy nadie la lee)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS outbox (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    aggregate_type  TEXT NOT NULL,   -- 'entity', 'fact', 'memory', 'event'
    aggregate_id    INTEGER NOT NULL,
    op              TEXT NOT NULL CHECK (op IN ('insert', 'update', 'delete')),
    payload         TEXT NOT NULL,   -- JSON snapshot
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    synced_at       TEXT,
    attempts        INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS outbox_pending_idx ON outbox (created_at)
    WHERE synced_at IS NULL;
