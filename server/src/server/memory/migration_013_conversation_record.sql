-- Migration 13 — the conversation record and the diary (Plan 0076, ADR 0027).
-- conversation_consent_grants: the owner's revocable consent to store conversation text, with the
-- version of the notice that was read (one active grant per person, like migrations 007 and 008).
-- conversation_records: the archive. One row per segment of a conversation, its exchanges as JSON
-- text (never audio or frames, ADR 0024 decision 3); at most one segment is open at a time (one
-- microphone). conversation_episodes: the diary, one summary per eligible record, deleted with it.
-- admin_audit is rebuilt (its CHECKs are closed) to accept the conversation operations of
-- `iroko-admin`; every row and id is kept. The legacy `memories` / `vec_memories` store is retired
-- (ADR 0027 decision 9): nothing has written to it since Plan 0062 and the database was counted
-- empty before this plan. Atomic like 011 and 012; there is no down-step.
BEGIN;

CREATE TABLE conversation_consent_grants (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    person_entity_id  INTEGER NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
    purpose           TEXT NOT NULL CHECK (purpose = 'conversation_storage'),
    notice_version    TEXT NOT NULL CHECK (length(notice_version) BETWEEN 1 AND 20),
    granted_at        TEXT NOT NULL,
    revoked_at        TEXT
);

CREATE UNIQUE INDEX conversation_consent_active_idx
    ON conversation_consent_grants (person_entity_id) WHERE revoked_at IS NULL;

CREATE TABLE conversation_records (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    previous_id       INTEGER REFERENCES conversation_records(id) ON DELETE SET NULL,
    owner_entity_id   INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    started_at        TEXT NOT NULL,
    last_turn_at      TEXT NOT NULL,
    closed_at         TEXT,
    turns             TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(turns)),
    turn_count        INTEGER NOT NULL DEFAULT 0 CHECK (turn_count >= 0),
    byte_count        INTEGER NOT NULL DEFAULT 0 CHECK (byte_count >= 0),
    eligible          INTEGER NOT NULL DEFAULT 0 CHECK (eligible IN (0, 1)),
    expires_at        TEXT,
    episode_status    TEXT NOT NULL DEFAULT 'pending'
                      CHECK (episode_status IN ('pending', 'done', 'skipped', 'failed')),
    episode_attempts  INTEGER NOT NULL DEFAULT 0 CHECK (episode_attempts >= 0),
    CHECK ((closed_at IS NULL) = (expires_at IS NULL))
);

-- At most one open segment: one microphone, one conversation.
CREATE UNIQUE INDEX conversation_records_one_open_idx
    ON conversation_records ((closed_at IS NULL)) WHERE closed_at IS NULL;
CREATE INDEX conversation_records_expiry_idx ON conversation_records (expires_at);
CREATE INDEX conversation_records_pending_idx
    ON conversation_records (episode_status, closed_at) WHERE closed_at IS NOT NULL;

CREATE TABLE conversation_episodes (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source_record_id  INTEGER NOT NULL UNIQUE
                      REFERENCES conversation_records(id) ON DELETE CASCADE,
    owner_entity_id   INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    visibility        TEXT NOT NULL CHECK (visibility = 'personal'),
    sensitivity       TEXT NOT NULL
                      CHECK (sensitivity IN ('normal', 'private', 'medical', 'location', 'security')),
    summary           TEXT NOT NULL CHECK (length(summary) BETWEEN 1 AND 1000),
    model             TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    expires_at        TEXT NOT NULL
);

CREATE TABLE admin_audit_new (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at         TEXT NOT NULL,
    actor_label         TEXT NOT NULL CHECK (length(actor_label) BETWEEN 1 AND 80),
    actor_role          TEXT NOT NULL CHECK (actor_role IN ('owner', 'builder')),
    channel             TEXT NOT NULL CHECK (channel = 'admin_local'),
    operation           TEXT NOT NULL CHECK (
        operation IN ('add', 'change', 'revoke', 'grant', 'export', 'delete')
    ),
    target_kind         TEXT NOT NULL CHECK (
        target_kind IN (
            'pool_literal', 'pool_relation', 'care_contact',
            'conversation_consent', 'conversation_record'
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

-- The legacy store is retired. Its vector index goes; the `memories` table itself stays, empty,
-- because four tables (facts, events, literal_facts_v4, entity_relations_v4) still name it as
-- the parent of a nullable foreign key, and SQLite cannot drop a parent that a foreign key
-- names without rebuilding every child. A trigger refuses any new row.
DROP TABLE vec_memories;
CREATE TRIGGER memories_retired BEFORE INSERT ON memories
BEGIN
    SELECT RAISE(ABORT, 'memories is retired (ADR 0027 decision 9)');
END;

PRAGMA user_version = 13;
COMMIT;
