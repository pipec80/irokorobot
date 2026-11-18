-- Migration 21 — archiving a memory without losing it (Plan 0086 D-10, ADR 0032 decision 3).
-- By voice a memory is set aside, never destroyed: `archived_at` marks a fact, a relation, a recall
-- unit or a pending topic that no reader may say, offer or search; clearing it brings the row back
-- (`iroko-admin archive restore`). The rows keep their lifecycle: an archived fact is still
-- `active`, so the writers' own duplicate checks keep seeing it. The columns are added with ALTER
-- TABLE ... ADD COLUMN, so no table is rebuilt; each carries the exact instant check of the data
-- dictionary or NULL. No index: the four tables are small and every reader already filters by
-- another indexed column. No transaction statements: the runner wraps this file.

ALTER TABLE literal_facts_v4 ADD COLUMN archived_at TEXT DEFAULT NULL CHECK (
    archived_at IS NULL OR (
        length(archived_at) = 32
        AND archived_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
        AND strftime('%Y-%m-%dT%H:%M:%S', substr(archived_at, 1, 19)) IS substr(archived_at, 1, 19)
    )
);
ALTER TABLE entity_relations_v4 ADD COLUMN archived_at TEXT DEFAULT NULL CHECK (
    archived_at IS NULL OR (
        length(archived_at) = 32
        AND archived_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
        AND strftime('%Y-%m-%dT%H:%M:%S', substr(archived_at, 1, 19)) IS substr(archived_at, 1, 19)
    )
);
ALTER TABLE recall_units ADD COLUMN archived_at TEXT DEFAULT NULL CHECK (
    archived_at IS NULL OR (
        length(archived_at) = 32
        AND archived_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
        AND strftime('%Y-%m-%dT%H:%M:%S', substr(archived_at, 1, 19)) IS substr(archived_at, 1, 19)
    )
);
ALTER TABLE pending_topics ADD COLUMN archived_at TEXT DEFAULT NULL CHECK (
    archived_at IS NULL OR (
        length(archived_at) = 32
        AND archived_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
        AND strftime('%Y-%m-%dT%H:%M:%S', substr(archived_at, 1, 19)) IS substr(archived_at, 1, 19)
    )
);
