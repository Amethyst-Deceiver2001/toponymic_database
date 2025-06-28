-- This script creates all necessary tables for the toponyms schema.

-- Table for defining the types of geographic entities
CREATE TABLE IF NOT EXISTS toponyms.entity_types (
    type_code VARCHAR(20) PRIMARY KEY,
    type_name_uk VARCHAR(100) NOT NULL,
    type_name_en VARCHAR(100) NOT NULL,
    hierarchy_level INTEGER NOT NULL DEFAULT 99,
    description TEXT
);

-- Pre-populate the entity types
INSERT INTO toponyms.entity_types (type_code, type_name_uk, type_name_en, hierarchy_level, description) VALUES
('region', 'область', 'region', 1, 'Administrative region'),
('district', 'район', 'district', 2, 'Administrative district'),
('city', 'місто', 'city', 2, 'Main city settlement'),
('street', 'вулиця', 'street', 3, 'Street, avenue, or road'),
('square', 'площа', 'square', 3, 'Public square or plaza'),
('park', 'парк', 'парк', 3, 'Park or green space'),
('building', 'будівля', 'building', 4, 'Individual building or structure'),
('point_of_interest', 'місце інтересу', 'point of interest', 5, 'Monument, landmark, or other point of interest'),
('area', 'територія', 'area', 4, 'General named area or neighborhood'),
('path', 'шлях', 'path', 4, 'Footpath or trail'),
('waterway', 'водний шлях', 'waterway', 3, 'River, stream, or canal')
ON CONFLICT (type_code) DO NOTHING;


-- Table for the core geographic entities themselves
CREATE TABLE IF NOT EXISTS toponyms.entities (
    entity_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type VARCHAR(20) NOT NULL REFERENCES toponyms.entity_types(type_code),
    geometry GEOMETRY(GEOMETRY, 4326),
    centroid GEOMETRY(POINT, 4326),
    source_authority VARCHAR(255),
    valid_start TIMESTAMPTZ NOT NULL,
    valid_end TIMESTAMPTZ,
    txn_start TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    txn_end TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(100) DEFAULT CURRENT_USER,
    verification_status VARCHAR(50) DEFAULT 'pending',
    verification_notes TEXT
);
CREATE INDEX IF NOT EXISTS entities_geom_idx ON toponyms.entities USING GIST (geometry);
CREATE INDEX IF NOT EXISTS entities_type_idx ON toponyms.entities (entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_temporal ON toponyms.entities(valid_start, valid_end);
CREATE INDEX IF NOT EXISTS idx_entities_centroid ON toponyms.entities USING GIST(centroid);


-- Table for the various names associated with each entity
CREATE TABLE IF NOT EXISTS toponyms.names (
    name_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id UUID NOT NULL REFERENCES toponyms.entities(entity_id) ON DELETE CASCADE,
    name_text TEXT NOT NULL,
    normalized_name TEXT,
    language_code VARCHAR(3) NOT NULL,
    script_code VARCHAR(4) DEFAULT 'Cyrl',
    transliteration_scheme VARCHAR(50),
    name_type VARCHAR(20) NOT NULL CHECK (name_type IN (
        'official', 'historical', 'traditional', 'colloquial', 'memorial', 'occupational', 'former', 'variant'
    )),
    name_status VARCHAR(50) DEFAULT 'active',
    valid_start TIMESTAMPTZ NOT NULL,
    valid_end TIMESTAMPTZ,
    source_type VARCHAR(50),
    source_reliability VARCHAR(50),
    notes TEXT,
    txn_start TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    txn_end TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS names_entity_id_idx ON toponyms.names (entity_id);
CREATE INDEX IF NOT EXISTS names_normalized_name_idx ON toponyms.names (normalized_name);
CREATE INDEX IF NOT EXISTS idx_names_temporal ON toponyms.names(valid_start, valid_end);
CREATE INDEX IF NOT EXISTS idx_names_language ON toponyms.names(language_code);
CREATE INDEX IF NOT EXISTS idx_names_fulltext ON toponyms.names USING gin(to_tsvector('simple', name_text));
