-- 01_names_exclusion.sql
-- Applies advanced exclusion constraint to toponyms.names table.

ALTER TABLE toponyms.entities
ADD CONSTRAINT entity_temporal_uniqueness
EXCLUDE USING gist (
    entity_id WITH =,
    tstzrange(valid_start, valid_end) WITH &&
) WHERE (txn_end IS NULL);

ALTER TABLE toponyms.names
ADD CONSTRAINT name_temporal_uniqueness
EXCLUDE USING gist (
    entity_id WITH =,
    language_code WITH =,
    name_type WITH =,
    tstzrange(valid_start, valid_end) WITH &&
) WHERE (txn_end IS NULL);
