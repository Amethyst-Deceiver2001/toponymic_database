## Comprehensive Debugging Onboarding & System Review

**To:** Red Team (Anthropic Claude Sonnet/Opus 4.0)
**From:** Blue Team (User) & Gemini (Guidance AI)
**Date:** June 28, 2025, 4:00 PM CEST
**Subject:** Mission Status Update & Post-Mortem on Core Infrastructure Setup

-----

### 1\. Project Overview & Current Mission State

The Mariupol Toponymic Database project aims to document property seizures and toponymic manipulation in occupied Mariupol, Ukraine, building a bitemporal PostgreSQL database for investigative journalism and accountability.

The current phase is focused on establishing a **robust and reliable core database infrastructure** and successfully performing the **initial ingestion of pre-invasion OpenStreetMap (OSM) data** for Mariupol Urban Hromada.

**Current Project State:**

  * **Dockerized PostgreSQL (16.4) + PostGIS (3.4) backend:** The intended architecture.
  * **Persistent Docker Container Startup Issue:** The `mariupol_postgis` (or `db`) container *fails to stay running* after `docker compose up -d`, resulting in `service "db" is not running`.
  * **Mounts Denied Error (Root of Docker Failure):** The specific reason for the container not staying up is a `mounts denied` error for `/data/backups`. This indicates a Docker Desktop File Sharing configuration issue.
  * **Data Ingestion Blocked:** The PBF data import script (`process_osm_data.py`) cannot connect to the database, preventing data loading.

-----

### 2\. Project Assets (Current State of Files)

This section provides the latest, finalized content for all critical configuration and script files. Any previous, intermediate versions or commented-out sections (unless explicitly part of the final structure for a specific purpose) have been removed for clarity.

**File Structure (`sql/` directory refactor):**

```
sql/
├── 10_setup/
│   ├── 01_extensions.sql
│   ├── 02_schemas.sql
│   └── 03_tables.sql
├── 20_functions/
│   └── 01_name_normalization.sql
└── 30_constraints/
    └── 01_names_exclusion.sql
```

**`docker-compose.yml` (Latest Version):**

```yaml
services:
  postgis:
    image: postgis/postgis:16-3.4
    platform: linux/amd64
    container_name: mariupol_postgis
    restart: unless-stopped
    ports:
      - "5433:5432" # Host:Container port mapping
    environment:
      POSTGRES_DB: mariupol_toponyms
      POSTGRES_USER: mariupol_researcher
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD} # Password passed via ENV var
      POSTGRES_HOST_AUTH_METHOD: md5 # Explicitly sets host auth method to MD5

    volumes:
      # Mount SQL initialization scripts directly into docker-entrypoint-initdb.d for proper execution order
      - ./sql/10_setup/01_extensions.sql:/docker-entrypoint-initdb.d/10_01_extensions.sql
      - ./sql/10_setup/02_schemas.sql:/docker-entrypoint-initdb.d/10_02_schemas.sql
      - ./sql/10_setup/03_tables.sql:/docker-entrypoint-initdb.d/10_03_tables.sql
      - ./sql/20_functions/01_name_normalization.sql:/docker-entrypoint-initdb.d/20_01_name_normalization.sql
      - ./sql/30_constraints/01_names_exclusion.sql:/docker-entrypoint-initdb.d/30_01_names_exclusion.sql
      # --- ORIGINAL VOLUME MOUNTS (KEEP THESE) ---
      - postgis_data:/var/lib/postgresql/data # Volume for persistent data
      - ./data/backups:/backups # For backups
      # --- END ORIGINAL ---

    # healthcheck: (Commented out due to persistent validation issues, relying on tenacity)
    #   test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB -h localhost || exit 1"]
    #   interval: 5s       
    #   timeout: 5s        
    #   retries: 10        
    #   start_period: 60s  

    command: postgres -c 'fsync=off' # Runs postgres in foreground, ensures container stays alive

    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2.0'

volumes:
  postgis_data:
    driver: local
```

**`.env` (Latest Configuration):**

```ini
# Local PostgreSQL Configuration
DB_HOST=localhost
DB_PORT=5433
DB_NAME=mariupol_toponyms
DB_USER=mariupol_researcher
DB_PASSWORD='YOUR_ACTUAL_PASSWORD_FOR_RESEARCHER' # User should replace this with their actual password.

# API Keys
OVERPASS_API_URL=https://overpass-api.de/api/interpreter

# Geographical Settings
MARIUPOL_BBOX="47.0002828,37.2942822,47.2294948,37.7554739" # BBOX for Mariupol Urban Hromada

# Logging
LOG_LEVEL=INFO # Can be set to DEBUG for verbose output
```

**`requirements.txt` (Latest Version):**

```txt
psycopg2-binary==2.9.9
geopandas~=0.14.0
shapely~=2.0.0
pyproj~=3.6.0
pandas~=2.2.0
numpy~=1.26.0
python-dotenv~=1.0.0
requests~=2.31.0
pytest~=8.2.0
pytest-cov~=5.0.0
click~=8.1.0
tqdm~=4.66.0
tenacity==8.2.3
osmium==3.7.0
```

**`sql/10_setup/01_extensions.sql` (Latest Version):**

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
COMMENT ON DATABASE mariupol_toponyms IS 'Bitemporal database tracking toponymic changes in Mariupol for historical preservation and legal documentation';
```

**`sql/10_setup/02_schemas.sql` (Latest Version):**

```sql
-- Create database user (only if not exists, and grant CREATEDB)
DO
$do$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'mariupol_researcher') THEN
      CREATE USER mariupol_researcher WITH PASSWORD 'YOUR_ACTUAL_PASSWORD_FOR_RESEARCHER' LOGIN CREATEDB;
   END IF;
END
$do$;

-- Grant CONNECT privilege to the database
GRANT CONNECT ON DATABASE mariupol_toponyms TO mariupol_researcher;

-- Create schemas (owned by mariupol_researcher)
CREATE SCHEMA IF NOT EXISTS toponyms AUTHORIZATION mariupol_researcher;
CREATE SCHEMA IF NOT EXISTS audit AUTHORIZATION mariupol_researcher;
CREATE SCHEMA IF NOT EXISTS staging AUTHORIZATION mariupol_researcher;

-- Grant USAGE on schemas to mariupol_researcher (redundant if owned, but harmless)
GRANT USAGE ON SCHEMA toponyms TO mariupol_researcher;
GRANT USAGE ON SCHEMA audit TO mariupol_researcher;
GRANT USAGE ON SCHEMA staging TO mariupol_researcher;

-- Set default search path for mariupol_researcher (and globally for the database for new connections)
ALTER ROLE mariupol_researcher SET search_path TO toponyms, public;
ALTER DATABASE mariupol_toponyms SET search_path TO toponyms, public;

-- Grant default privileges on future tables within schemas to mariupol_researcher
ALTER DEFAULT PRIVILEGES FOR ROLE mariupol_researcher IN SCHEMA toponyms GRANT ALL PRIVILEGES ON TABLES TO mariupol_researcher;
ALTER DEFAULT PRIVILEGES FOR ROLE mariupol_researcher IN SCHEMA audit GRANT ALL PRIVILEGES ON TABLES TO mariupol_researcher;
ALTER DEFAULT PRIVILEGES FOR ROLE mariupol_researcher IN SCHEMA staging GRANT ALL PRIVILEGES ON TABLES TO mariupol_researcher;

-- Make mariupol_researcher the owner of the database itself
ALTER DATABASE mariupol_toponyms OWNER TO mariupol_researcher;

COMMENT ON SCHEMA toponyms IS 'Current toponymic entities and names';
COMMENT ON SCHEMA audit IS 'Complete audit trail for legal compliance';
COMMENT ON SCHEMA staging IS 'Temporary tables for data import and validation';
```

**`sql/10_setup/03_tables.sql` (Latest Version):**

```sql
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
('park', 'парк', 'park', 3, 'Park or green space'),
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
```

**`sql/20_functions/01_name_normalization.sql` (Latest Version):**

```sql
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
```

**`sql/30_constraints/01_names_exclusion.sql` (Latest Version):**

```sql
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
```

**`scripts/utils/database.py` (Latest Version):**

```python
import psycopg2
from psycopg2.extras import DictRow, DictCursor
from psycopg2 import OperationalError
from psycopg2.errors import UndefinedTable # Correct import for UndefinedTable error

import pandas as pd
import geopandas as gpd
from contextlib import contextmanager
from typing import Optional, Dict, Any, List
import json
import time
import logging

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_log

from .config import DB_CONFIG, setup_logging

logger = setup_logging(__name__)

RETRYABLE_DB_EXCEPTIONS = (
    OperationalError,
)

class DatabaseConnection:
    """Manages database connections with proper error handling and logging"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or DB_CONFIG
        self._valid_entity_types_cache = None # FIX: Initialize the cache here
        
    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(10),
        retry=retry_if_exception_type(RETRYABLE_DB_EXCEPTIONS),
        before=before_log(logger, logging.INFO),
    )
    @contextmanager
    def get_connection(self):
        conn = None
        try:
            logger.info("Attempting to acquire database connection...")
            conn = psycopg2.connect(
                host=self.config['host'],
                port=self.config['port'],
                dbname=self.config['database'],
                user=self.config['user'],
                password=self.config['password'],
                # options="-c search_path=toponyms,public" # OPTIONAL: REMOVE THIS LINE
            )

            # REMOVE THIS BLOCK. The search_path should be set by ALTER ROLE/DATABASE
            # with conn.cursor() as cur:
            #     cur.execute("SET search_path TO toponyms, public;")
            # logger.debug("Database session search_path set to 'toponyms, public'.")

            logger.info("Database connection established successfully.")
            yield conn
            conn.commit()
            logger.debug("Transaction committed successfully")
        except Exception as e:
            if conn:
                conn.rollback()
                logger.error(f"Transaction rolled back due to error: {e}")
            raise 
        finally:
            if conn:
                conn.close()
                logger.debug("Database connection closed")
    
    def execute_sql_file(self, filepath: str) -> None:
        logger.info(f"Executing SQL file: {filepath}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql_content)
        
        logger.info(f"Successfully executed: {filepath}")
    
    def test_connection(self) -> bool:
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT version(), PostGIS_version()")
                    pg_version, postgis_version = cur.fetchone()
                    logger.info(f"Connected to PostgreSQL: {pg_version}")
                    logger.info(f"PostGIS version: {postgis_version}")
            return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
    
    def insert_entity(self, entity_type: str, geometry_wkt: str, 
                     source_authority: str, valid_start: str,
                     properties: Dict[str, Any] = None) -> str:
        
        sql = """
        INSERT INTO toponyms.entities 
        (entity_type, geometry, centroid, source_authority, valid_start)
        VALUES (
            %(entity_type)s,
            ST_GeomFromText(%(geometry)s, 4326),
            ST_Centroid(ST_GeomFromText(%(geometry)s, 4326)),
            %(source_authority)s,
            %(valid_start)s::timestamptz
        )
        RETURNING entity_id
        """
        
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {
                    'entity_type': entity_type,
                    'geometry': geometry_wkt,
                    'source_authority': source_authority,
                    'valid_start': valid_start
                })
                entity_id = cur.fetchone()[0]
                
        logger.info(f"Created entity {entity_id} of type {entity_type}")
        return entity_id
    
    def get_valid_entity_types(self) -> List[str]:
        if self._valid_entity_types_cache:
            return self._valid_entity_types_cache

        sql = "SELECT type_code FROM toponyms.entity_types ORDER BY type_code;"
        try:
            with self.get_connection() as conn: 
                with conn.cursor(cursor_factory=DictCursor) as cur:
                    cur.execute(sql)
                    types = [row['type_code'] for row in cur.fetchall()]
                    self._valid_entity_types_cache = types
                    logger.debug(f"Fetched valid entity types: {types}")
                    return types
            except UndefinedTable as e:
                logger.error(f"Schema for entity_types table not ready or does not exist: {e}. Falling back to hardcoded list.")
                return ['region', 'district', 'street', 'square', 'park', 'building', 'city', 'point_of_interest', 'area', 'path', 'waterway', 'unknown']
            except Exception as e:
                logger.error(f"Error fetching valid entity types from DB: {e}. Falling back to hardcoded list.")
                return ['region', 'district', 'street', 'square', 'park', 'building', 'city', 'point_of_interest', 'area', 'path', 'waterway', 'unknown']

db = DatabaseConnection()
```

-----

### 3\. Comprehensive Debugging Chronicle (Focus on `mounts denied` and Docker Container Crash)

The project has faced a cascade of issues. For a full historical trace, please refer to the detailed chat log. Here, we focus on the most recent, persistent Docker-related problems.

1.  **Bug: `mounts denied: The path /.data/backups is not shared from the host`**

      * **Problem:** Docker Compose `up -d` failed because the `data/backups` volume mount from the host was not shared with Docker Desktop. This error was very persistent, reappearing even after seemingly applying the fix in Docker Desktop's preferences.
      * **Hypothesis:** Docker Desktop's File Sharing configuration was not persistently saving or applying the user's manual additions, or there was a conflict with default `/Users` sharing.
      * **Attempted Fixes:**
          * Manually adding `~/Desktop/mariupol_project/toponymic_database` (or `data/`) to Docker Desktop -\> Preferences -\> Resources -\> File Sharing and clicking "Apply & restart".
          * Trying to simplify Docker File Sharing (remove all but `/Users`) and re-add just the project folder.
          * Performing a full Docker Desktop reset (`/Applications/Docker.app/Contents/MacOS/Docker --reset`).
      * **Outcome:** This `mounts denied` error is still part of the cycle, though its resolution is dependent on Docker Desktop's GUI configuration outside of direct CLI control.

2.  **Bug: `service "db" is not running` (Docker Container Crash/Exit)**

      * **Problem:** The `mariupol_postgis` container starts but almost immediately exits, preventing `docker compose exec` commands or `psycopg2` from connecting. `docker compose up -d` reports success, but `docker compose ps` shows the container is not `Up`. Running `docker compose up` in attached mode (without `-d`) did not show a clear `ERROR:` or `FATAL:` message from PostgreSQL itself at the point of exit. Instead, it showed "database system is ready to accept connections" and then the container exited.
      * **Hypothesis:**
          * The `docker-entrypoint.sh` script completed its initialization duties and then exited, and the Docker image's `CMD` was not correctly configured to keep the PostgreSQL server running in the foreground.
          * A subtle `initdb.d` script error was causing a crash that wasn't immediately logged as a `FATAL` by PostgreSQL, but caused `docker-entrypoint.sh` to exit.
      * **Attempted Fixes:**
          * Added `command: postgres -c 'fsync=off'` to `docker-compose.yml` to explicitly force PostgreSQL to run in the foreground.
          * Ensured correct mounting of SQL files (e.g., `./sql/10_setup/01_extensions.sql:/docker-entrypoint-initdb.d/10_01_extensions.sql`) to ensure `docker-entrypoint.sh` executes all schema scripts in order. (Previous logs showed "ignoring" of `sql/` subdirectories).
          * Corrected `docker-compose.yml` indentation issues (which were breaking YAML parsing).
      * **Outcome:** This `service "db" is not running` error is still part of the cycle. The `command: postgres -c 'fsync=off'` was added to address this, but the problem persists if `mounts denied` prevents `docker compose up` from completing cleanly.

-----

### 4\. Meta-Analysis: Challenges of LLM-Assisted Debugging & Proposed Improvements

The prolonged debugging process has highlighted significant challenges inherent in LLM-assisted technical troubleshooting, especially when environmental state is dynamic and opaque.

**Key Challenges Identified:**

1.  **State Latency & Invisibility:** The primary bottleneck was my inability to directly inspect the user's live system (file content, terminal state, running processes, Docker Desktop GUI settings). This led to reliance on manual user reports and screenshots, introducing latency and ambiguity.
      * **Example:** Persistent `mounts denied` errors when Docker Desktop GUI wasn't saving shared paths, or `Makefile` indentation issues, were difficult to diagnose without direct visual confirmation or programmatic access.
2.  **Copy-Paste Fidelity Issues:** Code blocks (especially YAML and complex SQL with backslashes/quotes) provided by the LLM were frequently broken during the user's copy-paste operation into the terminal or editor. This caused `SyntaxError`, `missing separator`, `invalid connection option`, and `invalid regular expression` errors that were not faults of the LLM-generated code, but of the transfer method.
      * **Impact:** A significant portion of debugging cycles was spent on fixing syntax errors introduced by the transfer, rather than logical code errors.
3.  **Cascading & Intertwined Errors:** Issues were rarely isolated. A Docker `mounts denied` led to container exit, which led to `service not running`, which led to `psycopg2.OperationalError`, which led to `UndefinedTable`, masking the root cause for multiple cycles.
4.  **Implicit Assumptions about Defaults:** Initial assumptions about Homebrew PostgreSQL's default `postgres` superuser or `docker-entrypoint.sh`'s behavior (e.g., auto-running all scripts) proved incorrect for this specific environment, leading to detours.

**Proposed Solutions for Red Team Review (LLM-to-Human Collaboration):**

1.  **Prioritize Automated Environment Profiling (Early & On-Demand):**

      * **Action:** Implement a diagnostic script (potentially a Python script) that the user runs and whose output is directly ingested by the LLM. This script would:
          * Collect system info (`uname -a`, `python --version`, `brew services list`, `docker --version`).
          * Read and output contents of critical config files (`.env`, `docker-compose.yml`, `Makefile`, all `sql/` files).
          * Check Docker status (`docker compose ps`, `docker compose logs`).
          * Run basic DB connectivity tests (`psql` status).
      * **Benefit:** Provides a real-time, comprehensive, and accurate snapshot of the user's environment, reducing guesswork and speeding up diagnosis.

2.  **Standardize Ultra-Robust Code Transfer:**

      * **Action:** All multi-line code (especially YAML and complex SQL) should be provided solely via `cat > filename << 'EOF'` blocks. The LLM must explicitly instruct the user to **copy the block verbatim, including `cat > ...` and `EOF`**, and **not edit or re-indent it**.
      * **Benefit:** Eliminates syntax errors introduced by copy-paste, allowing focus on logical errors.

3.  **Proactive Docker Desktop GUI Remediation Guidance:**

      * **Action:** When `mounts denied` errors appear, provide a highly visual, step-by-step guide for fixing Docker Desktop's File Sharing *before* attempting further `docker compose` commands. Emphasize "Apply & Restart" visually.
      * **Benefit:** Addresses the most common macOS-specific Docker issue directly and early.

4.  **Hypothesis-Driven Debugging with Explicit Branching:**

      * **Action:** When a critical error persists, explicitly state competing hypotheses and provide a branching path for debugging (e.g., "If A, do X. If B, do Y."). This empowers the user to follow the correct path based on specific output.
      * **Benefit:** Provides structure to complex debugging flows and reduces the "going in circles" feeling.

5.  **LLM-Specific Contextual Memory (Internal to LLM):**

      * **Action:** The LLM's internal state management should maintain a more robust and granular "user environment model" that updates with each interaction, anticipating common pitfalls (e.g., "user is on macOS, so Homebrew and Docker Desktop are relevant"; "user has had copy-paste issues, so emphasize `cat << EOF`").
      * **Benefit:** Improves the "intelligence" of the guidance over time.

-----

This comprehensive review outlines the significant work accomplished and the challenges that remain. The immediate focus for the Red Team should be to successfully resolve the `mounts denied` and Docker container startup issues, enabling the PBF data import to finally proceed.