-- Migration 16 — the owner's pending topics (Plan 0084 D-14, ADR 0037 decision 2).
-- pending_topics: what the owner said they would do on one day («mañana voy al banco»), kept
-- until the greeting of a later day asks about it once. A row starts 'unnamed' with the turn's
-- words in `heard`; the conversation job names it (`topic`, `heard` cleared, state 'open') or
-- deletes it; the follow-up moves it to 'asked'. said_day and due_day are LOCAL household days as
-- ISO dates, never UTC instants. A row is deleted with its owner and with the record of the turn
-- that said it, and by the job two days after its due day: there is no 'expired' state. One row
-- per turn at most (its correlation id). `heard` is bounded like the record's turn (2000). Atomic
-- like 011 to 015; no down-step. secure_delete is already on (db.open_db).
BEGIN;

CREATE TABLE pending_topics (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_entity_id   INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    source_record_id  INTEGER NOT NULL REFERENCES conversation_records(id) ON DELETE CASCADE,
    correlation_id    TEXT NOT NULL UNIQUE,
    said_day          TEXT NOT NULL CHECK (date(said_day) IS said_day),
    due_day           TEXT NOT NULL CHECK (date(due_day) IS due_day AND due_day >= said_day),
    topic             TEXT CHECK (topic IS NULL OR length(topic) BETWEEN 1 AND 40),
    heard             TEXT CHECK (heard IS NULL OR length(heard) BETWEEN 1 AND 2000),
    state             TEXT NOT NULL CHECK (state IN ('unnamed', 'open', 'asked')),
    sensitivity       TEXT NOT NULL CHECK (sensitivity IN ('normal', 'medical')),
    created_at        TEXT NOT NULL,
    asked_at          TEXT,
    CHECK ((state = 'unnamed') = (topic IS NULL)),
    CHECK ((topic IS NULL) = (heard IS NOT NULL)),
    CHECK ((state = 'asked') = (asked_at IS NOT NULL))
);

CREATE INDEX pending_topics_owner_state_due_idx ON pending_topics (owner_entity_id, state, due_day);
CREATE INDEX pending_topics_record_idx ON pending_topics (source_record_id);

PRAGMA user_version = 16;
COMMIT;
