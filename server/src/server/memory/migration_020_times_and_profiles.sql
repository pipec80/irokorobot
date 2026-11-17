-- Migration 20 — one time format in the data, and fixed profile keys (Plan 0085 D-9, ADR 0038
-- decisions 5 and 7). Part A made every writer store the exact 32-character instant
-- (YYYY-MM-DDTHH:MM:SS.ffffff+00:00); here the rows written before it are brought to the same form.
-- One UPDATE per `*_at` column converts a 19-character value (YYYY-MM-DD HH:MM:SS, SQLite's
-- datetime('now')) with replace(x, ' ', 'T') || '.000000+00:00' and a 25-character UTC one
-- (YYYY-MM-DDTHH:MM:SS+00:00) with substr(x, 1, 19) || '.000000+00:00'. Each rule is guarded by the
-- exact shape (GLOB), so a value in another offset is never read as UTC. The guard that follows
-- aborts the migration on any non-NULL value that is still not an exact, real instant: the runner
-- rolls everything back and leaves version 19. The columns are every TEXT column named `*_at` of a
-- live ordinary table of a v19 database (derived, not listed by hand); none holds a day. The two
-- instant validity bounds of facts and relations (`valid_from`, `valid_to`) become their UTC day;
-- a day (YYYY-MM-DD) or a month (YYYY-MM) stays; any other shape aborts.
-- `face_profiles` and `voice_profiles` are then rebuilt (SQLite's 12-step procedure, runner-wrapped
-- with foreign keys off): STRICT, AUTOINCREMENT (a deleted top id is never handed out again), the
-- person's foreign key written ON DELETE RESTRICT (the consent revocation deletes the biometrics
-- and `vec_faces` first, so a person cannot be deleted with a face or a voiceprint left behind),
-- and the instant a CHECK with no SQL default: the writer supplies it. Every id is kept, so
-- `vec_faces` (keyed by rowid = face_profiles.id) is untouched. Neither table had a
-- sqlite_sequence row; the counter becomes the old top id, captured before the DROP.
-- No transaction statements: the runner wraps this file.

UPDATE admin_audit SET recorded_at = CASE
    WHEN recorded_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(recorded_at, ' ', 'T') || '.000000+00:00'
    WHEN recorded_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(recorded_at, 1, 19) || '.000000+00:00'
    ELSE recorded_at
END WHERE length(recorded_at) IN (19, 25);

UPDATE authorization_audit_events SET evaluated_at = CASE
    WHEN evaluated_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(evaluated_at, ' ', 'T') || '.000000+00:00'
    WHEN evaluated_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(evaluated_at, 1, 19) || '.000000+00:00'
    ELSE evaluated_at
END WHERE length(evaluated_at) IN (19, 25);

UPDATE authorization_audit_events SET expires_at = CASE
    WHEN expires_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(expires_at, ' ', 'T') || '.000000+00:00'
    WHEN expires_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(expires_at, 1, 19) || '.000000+00:00'
    ELSE expires_at
END WHERE length(expires_at) IN (19, 25);

UPDATE care_contacts SET confirmed_at = CASE
    WHEN confirmed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(confirmed_at, ' ', 'T') || '.000000+00:00'
    WHEN confirmed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(confirmed_at, 1, 19) || '.000000+00:00'
    ELSE confirmed_at
END WHERE length(confirmed_at) IN (19, 25);

UPDATE care_contacts SET created_at = CASE
    WHEN created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(created_at, ' ', 'T') || '.000000+00:00'
    WHEN created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(created_at, 1, 19) || '.000000+00:00'
    ELSE created_at
END WHERE length(created_at) IN (19, 25);

UPDATE care_contacts SET revoked_at = CASE
    WHEN revoked_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(revoked_at, ' ', 'T') || '.000000+00:00'
    WHEN revoked_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(revoked_at, 1, 19) || '.000000+00:00'
    ELSE revoked_at
END WHERE length(revoked_at) IN (19, 25);

UPDATE commissioning_records SET started_at = CASE
    WHEN started_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(started_at, ' ', 'T') || '.000000+00:00'
    WHEN started_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(started_at, 1, 19) || '.000000+00:00'
    ELSE started_at
END WHERE length(started_at) IN (19, 25);

UPDATE commissioning_records SET closed_at = CASE
    WHEN closed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(closed_at, ' ', 'T') || '.000000+00:00'
    WHEN closed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(closed_at, 1, 19) || '.000000+00:00'
    ELSE closed_at
END WHERE length(closed_at) IN (19, 25);

UPDATE commissioning_sections SET recorded_at = CASE
    WHEN recorded_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(recorded_at, ' ', 'T') || '.000000+00:00'
    WHEN recorded_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(recorded_at, 1, 19) || '.000000+00:00'
    ELSE recorded_at
END WHERE length(recorded_at) IN (19, 25);

UPDATE conversation_consent_grants SET granted_at = CASE
    WHEN granted_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(granted_at, ' ', 'T') || '.000000+00:00'
    WHEN granted_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(granted_at, 1, 19) || '.000000+00:00'
    ELSE granted_at
END WHERE length(granted_at) IN (19, 25);

UPDATE conversation_consent_grants SET revoked_at = CASE
    WHEN revoked_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(revoked_at, ' ', 'T') || '.000000+00:00'
    WHEN revoked_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(revoked_at, 1, 19) || '.000000+00:00'
    ELSE revoked_at
END WHERE length(revoked_at) IN (19, 25);

UPDATE conversation_episodes SET created_at = CASE
    WHEN created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(created_at, ' ', 'T') || '.000000+00:00'
    WHEN created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(created_at, 1, 19) || '.000000+00:00'
    ELSE created_at
END WHERE length(created_at) IN (19, 25);

UPDATE conversation_episodes SET expires_at = CASE
    WHEN expires_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(expires_at, ' ', 'T') || '.000000+00:00'
    WHEN expires_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(expires_at, 1, 19) || '.000000+00:00'
    ELSE expires_at
END WHERE length(expires_at) IN (19, 25);

UPDATE conversation_records SET started_at = CASE
    WHEN started_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(started_at, ' ', 'T') || '.000000+00:00'
    WHEN started_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(started_at, 1, 19) || '.000000+00:00'
    ELSE started_at
END WHERE length(started_at) IN (19, 25);

UPDATE conversation_records SET last_turn_at = CASE
    WHEN last_turn_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(last_turn_at, ' ', 'T') || '.000000+00:00'
    WHEN last_turn_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(last_turn_at, 1, 19) || '.000000+00:00'
    ELSE last_turn_at
END WHERE length(last_turn_at) IN (19, 25);

UPDATE conversation_records SET closed_at = CASE
    WHEN closed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(closed_at, ' ', 'T') || '.000000+00:00'
    WHEN closed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(closed_at, 1, 19) || '.000000+00:00'
    ELSE closed_at
END WHERE length(closed_at) IN (19, 25);

UPDATE conversation_records SET expires_at = CASE
    WHEN expires_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(expires_at, ' ', 'T') || '.000000+00:00'
    WHEN expires_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(expires_at, 1, 19) || '.000000+00:00'
    ELSE expires_at
END WHERE length(expires_at) IN (19, 25);

UPDATE conversation_turns SET said_at = CASE
    WHEN said_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(said_at, ' ', 'T') || '.000000+00:00'
    WHEN said_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(said_at, 1, 19) || '.000000+00:00'
    ELSE said_at
END WHERE length(said_at) IN (19, 25);

UPDATE entities SET created_at = CASE
    WHEN created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(created_at, ' ', 'T') || '.000000+00:00'
    WHEN created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(created_at, 1, 19) || '.000000+00:00'
    ELSE created_at
END WHERE length(created_at) IN (19, 25);

UPDATE entities SET updated_at = CASE
    WHEN updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(updated_at, ' ', 'T') || '.000000+00:00'
    WHEN updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(updated_at, 1, 19) || '.000000+00:00'
    ELSE updated_at
END WHERE length(updated_at) IN (19, 25);

UPDATE entity_relations_v4 SET asserted_at = CASE
    WHEN asserted_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(asserted_at, ' ', 'T') || '.000000+00:00'
    WHEN asserted_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(asserted_at, 1, 19) || '.000000+00:00'
    ELSE asserted_at
END WHERE length(asserted_at) IN (19, 25);

UPDATE entity_relations_v4 SET confirmed_at = CASE
    WHEN confirmed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(confirmed_at, ' ', 'T') || '.000000+00:00'
    WHEN confirmed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(confirmed_at, 1, 19) || '.000000+00:00'
    ELSE confirmed_at
END WHERE length(confirmed_at) IN (19, 25);

UPDATE entity_relations_v4 SET superseded_at = CASE
    WHEN superseded_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(superseded_at, ' ', 'T') || '.000000+00:00'
    WHEN superseded_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(superseded_at, 1, 19) || '.000000+00:00'
    ELSE superseded_at
END WHERE length(superseded_at) IN (19, 25);

UPDATE face_consent_grants SET granted_at = CASE
    WHEN granted_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(granted_at, ' ', 'T') || '.000000+00:00'
    WHEN granted_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(granted_at, 1, 19) || '.000000+00:00'
    ELSE granted_at
END WHERE length(granted_at) IN (19, 25);

UPDATE face_consent_grants SET revoked_at = CASE
    WHEN revoked_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(revoked_at, ' ', 'T') || '.000000+00:00'
    WHEN revoked_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(revoked_at, 1, 19) || '.000000+00:00'
    ELSE revoked_at
END WHERE length(revoked_at) IN (19, 25);

UPDATE face_profiles SET created_at = CASE
    WHEN created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(created_at, ' ', 'T') || '.000000+00:00'
    WHEN created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(created_at, 1, 19) || '.000000+00:00'
    ELSE created_at
END WHERE length(created_at) IN (19, 25);

UPDATE household_role_assignments SET granted_at = CASE
    WHEN granted_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(granted_at, ' ', 'T') || '.000000+00:00'
    WHEN granted_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(granted_at, 1, 19) || '.000000+00:00'
    ELSE granted_at
END WHERE length(granted_at) IN (19, 25);

UPDATE household_role_assignments SET revoked_at = CASE
    WHEN revoked_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(revoked_at, ' ', 'T') || '.000000+00:00'
    WHEN revoked_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(revoked_at, 1, 19) || '.000000+00:00'
    ELSE revoked_at
END WHERE length(revoked_at) IN (19, 25);

UPDATE literal_facts_v4 SET asserted_at = CASE
    WHEN asserted_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(asserted_at, ' ', 'T') || '.000000+00:00'
    WHEN asserted_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(asserted_at, 1, 19) || '.000000+00:00'
    ELSE asserted_at
END WHERE length(asserted_at) IN (19, 25);

UPDATE literal_facts_v4 SET confirmed_at = CASE
    WHEN confirmed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(confirmed_at, ' ', 'T') || '.000000+00:00'
    WHEN confirmed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(confirmed_at, 1, 19) || '.000000+00:00'
    ELSE confirmed_at
END WHERE length(confirmed_at) IN (19, 25);

UPDATE literal_facts_v4 SET superseded_at = CASE
    WHEN superseded_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(superseded_at, ' ', 'T') || '.000000+00:00'
    WHEN superseded_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(superseded_at, 1, 19) || '.000000+00:00'
    ELSE superseded_at
END WHERE length(superseded_at) IN (19, 25);

UPDATE memories SET last_accessed_at = CASE
    WHEN last_accessed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(last_accessed_at, ' ', 'T') || '.000000+00:00'
    WHEN last_accessed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(last_accessed_at, 1, 19) || '.000000+00:00'
    ELSE last_accessed_at
END WHERE length(last_accessed_at) IN (19, 25);

UPDATE memories SET created_at = CASE
    WHEN created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(created_at, ' ', 'T') || '.000000+00:00'
    WHEN created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(created_at, 1, 19) || '.000000+00:00'
    ELSE created_at
END WHERE length(created_at) IN (19, 25);

UPDATE memories SET archived_at = CASE
    WHEN archived_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(archived_at, ' ', 'T') || '.000000+00:00'
    WHEN archived_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(archived_at, 1, 19) || '.000000+00:00'
    ELSE archived_at
END WHERE length(archived_at) IN (19, 25);

UPDATE memory_candidates SET proposed_at = CASE
    WHEN proposed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(proposed_at, ' ', 'T') || '.000000+00:00'
    WHEN proposed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(proposed_at, 1, 19) || '.000000+00:00'
    ELSE proposed_at
END WHERE length(proposed_at) IN (19, 25);

UPDATE memory_candidates SET offered_at = CASE
    WHEN offered_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(offered_at, ' ', 'T') || '.000000+00:00'
    WHEN offered_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(offered_at, 1, 19) || '.000000+00:00'
    ELSE offered_at
END WHERE length(offered_at) IN (19, 25);

UPDATE memory_candidates SET resolved_at = CASE
    WHEN resolved_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(resolved_at, ' ', 'T') || '.000000+00:00'
    WHEN resolved_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(resolved_at, 1, 19) || '.000000+00:00'
    ELSE resolved_at
END WHERE length(resolved_at) IN (19, 25);

UPDATE memory_candidates SET expires_at = CASE
    WHEN expires_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(expires_at, ' ', 'T') || '.000000+00:00'
    WHEN expires_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(expires_at, 1, 19) || '.000000+00:00'
    ELSE expires_at
END WHERE length(expires_at) IN (19, 25);

UPDATE meta SET updated_at = CASE
    WHEN updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(updated_at, ' ', 'T') || '.000000+00:00'
    WHEN updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(updated_at, 1, 19) || '.000000+00:00'
    ELSE updated_at
END WHERE length(updated_at) IN (19, 25);

UPDATE owner_pin_credentials SET created_at = CASE
    WHEN created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(created_at, ' ', 'T') || '.000000+00:00'
    WHEN created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(created_at, 1, 19) || '.000000+00:00'
    ELSE created_at
END WHERE length(created_at) IN (19, 25);

UPDATE owner_pin_credentials SET updated_at = CASE
    WHEN updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(updated_at, ' ', 'T') || '.000000+00:00'
    WHEN updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(updated_at, 1, 19) || '.000000+00:00'
    ELSE updated_at
END WHERE length(updated_at) IN (19, 25);

UPDATE owner_pin_credentials SET revoked_at = CASE
    WHEN revoked_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(revoked_at, ' ', 'T') || '.000000+00:00'
    WHEN revoked_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(revoked_at, 1, 19) || '.000000+00:00'
    ELSE revoked_at
END WHERE length(revoked_at) IN (19, 25);

UPDATE pending_topics SET created_at = CASE
    WHEN created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(created_at, ' ', 'T') || '.000000+00:00'
    WHEN created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(created_at, 1, 19) || '.000000+00:00'
    ELSE created_at
END WHERE length(created_at) IN (19, 25);

UPDATE pending_topics SET asked_at = CASE
    WHEN asked_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(asked_at, ' ', 'T') || '.000000+00:00'
    WHEN asked_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(asked_at, 1, 19) || '.000000+00:00'
    ELSE asked_at
END WHERE length(asked_at) IN (19, 25);

UPDATE recall_units SET said_at = CASE
    WHEN said_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(said_at, ' ', 'T') || '.000000+00:00'
    WHEN said_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(said_at, 1, 19) || '.000000+00:00'
    ELSE said_at
END WHERE length(said_at) IN (19, 25);

UPDATE voice_consent_grants SET granted_at = CASE
    WHEN granted_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(granted_at, ' ', 'T') || '.000000+00:00'
    WHEN granted_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(granted_at, 1, 19) || '.000000+00:00'
    ELSE granted_at
END WHERE length(granted_at) IN (19, 25);

UPDATE voice_consent_grants SET revoked_at = CASE
    WHEN revoked_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(revoked_at, ' ', 'T') || '.000000+00:00'
    WHEN revoked_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(revoked_at, 1, 19) || '.000000+00:00'
    ELSE revoked_at
END WHERE length(revoked_at) IN (19, 25);

UPDATE voice_profiles SET created_at = CASE
    WHEN created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' THEN replace(created_at, ' ', 'T') || '.000000+00:00'
    WHEN created_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' THEN substr(created_at, 1, 19) || '.000000+00:00'
    ELSE created_at
END WHERE length(created_at) IN (19, 25);

-- Every non-NULL time value is now an exact instant, or the migration stops here.
CREATE TEMP VIEW _all_times (tbl, col, value) AS
    SELECT 'admin_audit', 'recorded_at', recorded_at FROM admin_audit
UNION ALL
    SELECT 'authorization_audit_events', 'evaluated_at', evaluated_at FROM authorization_audit_events
UNION ALL
    SELECT 'authorization_audit_events', 'expires_at', expires_at FROM authorization_audit_events
UNION ALL
    SELECT 'care_contacts', 'confirmed_at', confirmed_at FROM care_contacts
UNION ALL
    SELECT 'care_contacts', 'created_at', created_at FROM care_contacts
UNION ALL
    SELECT 'care_contacts', 'revoked_at', revoked_at FROM care_contacts
UNION ALL
    SELECT 'commissioning_records', 'started_at', started_at FROM commissioning_records
UNION ALL
    SELECT 'commissioning_records', 'closed_at', closed_at FROM commissioning_records
UNION ALL
    SELECT 'commissioning_sections', 'recorded_at', recorded_at FROM commissioning_sections
UNION ALL
    SELECT 'conversation_consent_grants', 'granted_at', granted_at FROM conversation_consent_grants
UNION ALL
    SELECT 'conversation_consent_grants', 'revoked_at', revoked_at FROM conversation_consent_grants
UNION ALL
    SELECT 'conversation_episodes', 'created_at', created_at FROM conversation_episodes
UNION ALL
    SELECT 'conversation_episodes', 'expires_at', expires_at FROM conversation_episodes
UNION ALL
    SELECT 'conversation_records', 'started_at', started_at FROM conversation_records
UNION ALL
    SELECT 'conversation_records', 'last_turn_at', last_turn_at FROM conversation_records
UNION ALL
    SELECT 'conversation_records', 'closed_at', closed_at FROM conversation_records
UNION ALL
    SELECT 'conversation_records', 'expires_at', expires_at FROM conversation_records
UNION ALL
    SELECT 'conversation_turns', 'said_at', said_at FROM conversation_turns
UNION ALL
    SELECT 'entities', 'created_at', created_at FROM entities
UNION ALL
    SELECT 'entities', 'updated_at', updated_at FROM entities
UNION ALL
    SELECT 'entity_relations_v4', 'asserted_at', asserted_at FROM entity_relations_v4
UNION ALL
    SELECT 'entity_relations_v4', 'confirmed_at', confirmed_at FROM entity_relations_v4
UNION ALL
    SELECT 'entity_relations_v4', 'superseded_at', superseded_at FROM entity_relations_v4
UNION ALL
    SELECT 'face_consent_grants', 'granted_at', granted_at FROM face_consent_grants
UNION ALL
    SELECT 'face_consent_grants', 'revoked_at', revoked_at FROM face_consent_grants
UNION ALL
    SELECT 'face_profiles', 'created_at', created_at FROM face_profiles
UNION ALL
    SELECT 'household_role_assignments', 'granted_at', granted_at FROM household_role_assignments
UNION ALL
    SELECT 'household_role_assignments', 'revoked_at', revoked_at FROM household_role_assignments
UNION ALL
    SELECT 'literal_facts_v4', 'asserted_at', asserted_at FROM literal_facts_v4
UNION ALL
    SELECT 'literal_facts_v4', 'confirmed_at', confirmed_at FROM literal_facts_v4
UNION ALL
    SELECT 'literal_facts_v4', 'superseded_at', superseded_at FROM literal_facts_v4
UNION ALL
    SELECT 'memories', 'last_accessed_at', last_accessed_at FROM memories
UNION ALL
    SELECT 'memories', 'created_at', created_at FROM memories
UNION ALL
    SELECT 'memories', 'archived_at', archived_at FROM memories
UNION ALL
    SELECT 'memory_candidates', 'proposed_at', proposed_at FROM memory_candidates
UNION ALL
    SELECT 'memory_candidates', 'offered_at', offered_at FROM memory_candidates
UNION ALL
    SELECT 'memory_candidates', 'resolved_at', resolved_at FROM memory_candidates
UNION ALL
    SELECT 'memory_candidates', 'expires_at', expires_at FROM memory_candidates
UNION ALL
    SELECT 'meta', 'updated_at', updated_at FROM meta
UNION ALL
    SELECT 'owner_pin_credentials', 'created_at', created_at FROM owner_pin_credentials
UNION ALL
    SELECT 'owner_pin_credentials', 'updated_at', updated_at FROM owner_pin_credentials
UNION ALL
    SELECT 'owner_pin_credentials', 'revoked_at', revoked_at FROM owner_pin_credentials
UNION ALL
    SELECT 'pending_topics', 'created_at', created_at FROM pending_topics
UNION ALL
    SELECT 'pending_topics', 'asked_at', asked_at FROM pending_topics
UNION ALL
    SELECT 'recall_units', 'said_at', said_at FROM recall_units
UNION ALL
    SELECT 'voice_consent_grants', 'granted_at', granted_at FROM voice_consent_grants
UNION ALL
    SELECT 'voice_consent_grants', 'revoked_at', revoked_at FROM voice_consent_grants
UNION ALL
    SELECT 'voice_profiles', 'created_at', created_at FROM voice_profiles;

CREATE TEMP TABLE _bad_times (
    n INTEGER,
    CONSTRAINT a_time_column_holds_a_value_that_is_not_an_exact_instant CHECK (n = 0)
);
INSERT INTO _bad_times SELECT count(*) FROM _all_times
WHERE value IS NOT NULL AND NOT (length(value) = 32 AND value GLOB
            '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
        AND strftime('%Y-%m-%dT%H:%M:%S', substr(value, 1, 19)) IS substr(value, 1, 19));
DROP TABLE _bad_times;
DROP VIEW _all_times;

-- The validity bounds: an instant becomes its UTC day; a day or a month stays.

UPDATE literal_facts_v4 SET valid_from = substr(valid_from, 1, 10)
WHERE valid_from GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' OR valid_from GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' OR valid_from GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00';

UPDATE literal_facts_v4 SET valid_to = substr(valid_to, 1, 10)
WHERE valid_to GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' OR valid_to GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' OR valid_to GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00';

UPDATE entity_relations_v4 SET valid_from = substr(valid_from, 1, 10)
WHERE valid_from GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' OR valid_from GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' OR valid_from GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00';

UPDATE entity_relations_v4 SET valid_to = substr(valid_to, 1, 10)
WHERE valid_to GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][ T][0-9][0-9]:[0-9][0-9]:[0-9][0-9]' OR valid_to GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00' OR valid_to GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00';

CREATE TEMP VIEW _all_bounds (tbl, col, value) AS
    SELECT 'literal_facts_v4', 'valid_from', valid_from FROM literal_facts_v4
UNION ALL
    SELECT 'literal_facts_v4', 'valid_to', valid_to FROM literal_facts_v4
UNION ALL
    SELECT 'entity_relations_v4', 'valid_from', valid_from FROM entity_relations_v4
UNION ALL
    SELECT 'entity_relations_v4', 'valid_to', valid_to FROM entity_relations_v4;
CREATE TEMP TABLE _bad_bounds (
    n INTEGER,
    CONSTRAINT a_validity_bound_is_not_a_day_or_a_month CHECK (n = 0)
);
INSERT INTO _bad_bounds SELECT count(*) FROM _all_bounds WHERE value IS NOT NULL AND NOT (
    (value GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' AND strftime('%Y-%m-%d', value) IS value)
    OR (value GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]' AND strftime('%Y-%m-%d', value || '-01') IS value || '-01')
);
DROP TABLE _bad_bounds;
DROP VIEW _all_bounds;

-- The two biometric tables. The counters are captured before the DROP: the larger of the
-- table's own counter (none today) and its top id.
CREATE TEMP TABLE _profile_counters (name TEXT PRIMARY KEY, seq INTEGER NOT NULL);
INSERT INTO _profile_counters
SELECT 'face_profiles', max(
    coalesce((SELECT seq FROM sqlite_sequence WHERE name = 'face_profiles'), 0),
    coalesce((SELECT max(id) FROM face_profiles), 0));
INSERT INTO _profile_counters
SELECT 'voice_profiles', max(
    coalesce((SELECT seq FROM sqlite_sequence WHERE name = 'voice_profiles'), 0),
    coalesce((SELECT max(id) FROM voice_profiles), 0));


CREATE TABLE face_profiles_new (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id   INTEGER NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
    label       TEXT NOT NULL,
    created_at  TEXT NOT NULL CHECK (
        length(created_at) = 32 AND created_at GLOB
            '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
        AND strftime('%Y-%m-%dT%H:%M:%S', substr(created_at, 1, 19)) IS substr(created_at, 1, 19)
    )
) STRICT;
INSERT INTO face_profiles_new (id, entity_id, label, created_at)
SELECT id, entity_id, label, created_at FROM face_profiles ORDER BY id;
DROP TABLE face_profiles;
ALTER TABLE face_profiles_new RENAME TO face_profiles;
CREATE INDEX idx_face_profiles_entity ON face_profiles(entity_id);
DELETE FROM sqlite_sequence WHERE name = 'face_profiles';
INSERT INTO sqlite_sequence (name, seq) SELECT name, seq FROM _profile_counters WHERE name = 'face_profiles';


CREATE TABLE voice_profiles_new (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id   INTEGER NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
    label       TEXT NOT NULL,
    embedding   BLOB NOT NULL,
    model_id    TEXT NOT NULL,
    created_at  TEXT NOT NULL CHECK (
        length(created_at) = 32 AND created_at GLOB
            '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
        AND strftime('%Y-%m-%dT%H:%M:%S', substr(created_at, 1, 19)) IS substr(created_at, 1, 19)
    )
) STRICT;
INSERT INTO voice_profiles_new (id, entity_id, label, embedding, model_id, created_at)
SELECT id, entity_id, label, embedding, model_id, created_at FROM voice_profiles ORDER BY id;
DROP TABLE voice_profiles;
ALTER TABLE voice_profiles_new RENAME TO voice_profiles;
CREATE INDEX idx_voice_profiles_entity ON voice_profiles(entity_id);
DELETE FROM sqlite_sequence WHERE name = 'voice_profiles';
INSERT INTO sqlite_sequence (name, seq) SELECT name, seq FROM _profile_counters WHERE name = 'voice_profiles';


DROP TABLE _profile_counters;
