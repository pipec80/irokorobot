-- Migration 9 — memory candidates (Plan 0062, CM-3a, ADR 0021).
-- A candidate is a claim the identified owner made about their own taste, kept until the
-- owner confirms it or it lapses. It is NOT canonical memory: the one writer promotes it into
-- literal_facts_v4 (whose lifecycle CHECK has no `proposed` state and cannot be altered
-- without rebuilding the table), and every row of V4 stays canonical.
--
-- The value exists only while the candidate is live. The CHECK makes the scrub a schema rule:
-- value_text and value_key are non-null exactly in `proposed` and `offered`, so a resolution
-- that forgets to erase the value is refused by the database itself. Timestamps are written
-- by the caller from one clock as UTC ISO 8601 (never datetime('now')), so expiry and the
-- audit compare like with like.
-- No raw utterance, no source_memory_id (episodes are CM-4) and no assurance column: in
-- CM-3a a candidate always needs face and voice of the same person (decision 3).

CREATE TABLE IF NOT EXISTS memory_candidates (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_person_id           INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    asserted_by_person_id       INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    predicate                   TEXT NOT NULL,
    value_text                  TEXT,
    value_key                   TEXT,
    status                      TEXT NOT NULL CHECK (
        status IN ('proposed', 'offered', 'confirmed', 'rejected', 'expired')
    ),
    channel                     TEXT NOT NULL CHECK (channel IN ('voice_classic', 'voice_stream')),
    source_correlation_id       TEXT NOT NULL,
    offer_correlation_id        TEXT,
    resolution_correlation_id   TEXT,
    proposed_at                 TEXT NOT NULL,
    offered_at                  TEXT,
    resolved_at                 TEXT,
    expires_at                  TEXT NOT NULL,
    offer_count                 INTEGER NOT NULL DEFAULT 0 CHECK (offer_count >= 0),
    promoted_fact_id            INTEGER REFERENCES literal_facts_v4(id) ON DELETE SET NULL,
    CHECK (
        (status IN ('proposed', 'offered') AND value_text IS NOT NULL AND value_key IS NOT NULL)
        OR
        (status NOT IN ('proposed', 'offered') AND value_text IS NULL AND value_key IS NULL)
    )
);

-- One live candidate per (person, predicate, comparison key): a repeated statement is a
-- no-op insert, never a second offer.
CREATE UNIQUE INDEX IF NOT EXISTS memory_candidates_live_value_idx
    ON memory_candidates (subject_person_id, predicate, value_key)
    WHERE status IN ('proposed', 'offered');

CREATE INDEX IF NOT EXISTS memory_candidates_subject_status_idx
    ON memory_candidates (subject_person_id, status);

-- The retention job and every store entry look up what has lapsed.
CREATE INDEX IF NOT EXISTS memory_candidates_live_expiry_idx
    ON memory_candidates (expires_at)
    WHERE status IN ('proposed', 'offered');
