-- Migration 18 — the turns as rows (Plan 0085 D-7, ADR 0038 decision 6).
-- A conversation record kept its exchanges as one JSON array, so deleting or redacting one turn
-- meant rewriting the whole record. Each exchange becomes a row of `conversation_turns`: the
-- correlation id (unique, it joins a turn to its candidates and audit rows), the exact instant,
-- the verdict, and the two texts. The copy keeps the order (record, then position in the array);
-- a read orders by instant, then id, so two equal instants keep their append order. The record's
-- `turns`, `turn_count` and `byte_count` go: the count and the size are now computed from the
-- rows, in bytes: a turn weighs its generated `bytes` column, the UTF-8 length of both texts
-- (`length` of a BLOB counts bytes on every supported SQLite; `octet_length` needs 3.43).
-- Nothing is dropped silently: a turn that breaks a rule of the new table (an instant that is not
-- the exact 32-character form, a repeated correlation id) fails the copy, the runner rolls
-- everything back and leaves version 17, and the count guard below fails if any turn was left
-- behind. The numbers 2000 and 4000 repeat HEARD_MAX_CHARS and SAID_MAX_CHARS of
-- conversation_types.py. No transaction statements: the
-- runner wraps this file.

CREATE TABLE conversation_turns (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id         INTEGER NOT NULL REFERENCES conversation_records(id) ON DELETE CASCADE,
    correlation_id    TEXT NOT NULL UNIQUE,
    -- The exact instant (ADR 0038 decision 5): 32 characters, every digit position explicit
    -- (six fraction digits), the literal +00:00 suffix, and a real calendar instant.
    said_at           TEXT NOT NULL CHECK (
        length(said_at) = 32
        AND said_at GLOB
            '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
        AND strftime('%Y-%m-%dT%H:%M:%S', substr(said_at, 1, 19)) IS substr(said_at, 1, 19)
    ),
    verdict           TEXT NOT NULL CHECK (verdict IN ('verified', 'not_verified', 'not_owner', 'not_checked')),
    heard             TEXT NOT NULL CHECK (length(heard) <= 2000),
    said              TEXT NOT NULL CHECK (length(said) <= 4000),
    -- What the turn weighs for the segment limit and the space cap. The one definition: the append
    -- in conversation_record.py weighs the new turn in Python and a test pins both to be equal.
    bytes             INTEGER GENERATED ALWAYS AS (length(CAST(heard AS BLOB)) + length(CAST(said AS BLOB))) STORED
) STRICT;

-- The read order, the cascade of a record's delete, and the lookup of a record's rows for its
-- count and byte sum (at most CONVERSATION_SEGMENT_MAX_TURNS rows). SQLite reads a stored
-- generated column from the table, never from an index, so no index can cover that sum.
CREATE INDEX conversation_turns_record_idx ON conversation_turns (record_id, said_at, id);

INSERT INTO conversation_turns (record_id, correlation_id, said_at, verdict, heard, said)
SELECT
    r.id,
    json_extract(j.value, '$.cid'),
    json_extract(j.value, '$.at'),
    json_extract(j.value, '$.voice'),
    json_extract(j.value, '$.heard'),
    json_extract(j.value, '$.said')
FROM conversation_records r, json_each(r.turns) j
ORDER BY r.id, j.key;

-- Every turn of every record landed: the number of JSON turns equals the number of rows.
CREATE TEMP TABLE _turns_left_behind (n INTEGER CHECK (n = 0));
INSERT INTO _turns_left_behind SELECT
    (SELECT COALESCE(SUM(json_array_length(turns)), 0) FROM conversation_records)
    - (SELECT count(*) FROM conversation_turns);
DROP TABLE _turns_left_behind;

ALTER TABLE conversation_records DROP COLUMN turns;
ALTER TABLE conversation_records DROP COLUMN turn_count;
ALTER TABLE conversation_records DROP COLUMN byte_count;
