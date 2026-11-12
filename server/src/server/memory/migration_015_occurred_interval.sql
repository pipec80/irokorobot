-- Migration 15 — when a told event happened, on the recall units (Plan 0083 D-8, ADR 0037 d. 3).
-- occurred_start / occurred_end: the inclusive LOCAL household calendar days a turn unit's words
-- say the event happened («el sábado fui a la playa»), as ISO dates (2025-11-08), never UTC
-- instants: a told day is a day, and a later change of HOUSEHOLD_TIMEZONE does not move it. Both
-- NULL when the words say no time, for every episode unit and for every unit written before this
-- migration (no backfill). The CHECK uses IS, so an invalid date is refused instead of passing as
-- NULL. FTS5, vec0 and their triggers are untouched. Atomic like 011 to 014; no down-step.
BEGIN;

ALTER TABLE recall_units ADD COLUMN occurred_start TEXT;
ALTER TABLE recall_units ADD COLUMN occurred_end TEXT
    CHECK ((occurred_start IS NULL) = (occurred_end IS NULL)
           AND (occurred_end IS NULL
                OR (date(occurred_start) IS occurred_start
                    AND date(occurred_end) IS occurred_end
                    AND occurred_start <= occurred_end)));

CREATE INDEX recall_units_owner_occurred_idx ON recall_units (owner_entity_id, occurred_start);

PRAGMA user_version = 15;
COMMIT;
