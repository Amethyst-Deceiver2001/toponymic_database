-- 01_name_normalization.sql
-- Function to normalize names for searching (removes accents, converts to lowercase)

CREATE OR REPLACE FUNCTION toponyms.normalize_name(input_text TEXT)
RETURNS TEXT AS $$
DECLARE
    normalized_text TEXT;
BEGIN
    -- Convert to lowercase
    normalized_text := lower(input_text);
    
    -- Remove all punctuation characters (Unicode-aware)
    -- \p{P} matches any Unicode punctuation character.
    -- Use E'' for standard backslash interpretation.
    normalized_text := regexp_replace(normalized_text, E'\\p{P}+', '', 'g'); 

    -- Normalize multiple spaces to a single space, then trim
    normalized_text := regexp_replace(normalized_text, E'\\s+', E' ', 'g');
    normalized_text := trim(normalized_text);
    
    -- Handle Ukrainian-specific normalizations
    normalized_text := replace(normalized_text, 'і', 'и');
    normalized_text := replace(normalized_text, 'ї', 'и');
    normalized_text := replace(normalized_text, 'є', 'е');
    
    RETURN normalized_text;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMENT ON FUNCTION toponyms.normalize_name IS 'Normalizes names for fuzzy searching across languages';
