````markdown
# A Roadmap for Local Development with Postgres.app and Python

This document provides a complete roadmap for setting up a robust, professional-grade development environment on macOS using Postgres.app for native database performance. It codifies a set of best practices for configuration management, database schema versioning, resilient application code, and task automation.

---

## 1. Initial Setup: Core Tools

This setup prioritizes native performance and is ideal for resource-constrained machines like a MacBook Air.

### **1.1. Install Postgres.app**
- **Download:** Go to [Postgresapp.com](https://postgresapp.com/) and download the latest version.
- **Install:** Drag the downloaded `Postgres.app` to your `Applications` folder.
- **Launch:** Open the app. It will appear in your macOS menu bar. Click "Initialize" to create a new server. The server will be running on the default port `5432`.
- **Configure Path (Crucial Step):** To use the `psql` command-line tool from your terminal, follow the on-screen instructions in the Postgres.app window for adding it to your `$PATH`. It will typically be a command like this:
  ```bash
  sudo mkdir -p /etc/paths.d && echo /Applications/Postgres.app/Contents/Versions/latest/bin | sudo tee /etc/paths.d/postgresapp
````

After running this, **quit and restart your terminal** for the changes to take effect.

### **1.2. Set Up Python Environment**

  - **Create a Virtual Environment:** In your project's root directory, create a Python virtual environment.
    ```bash
    python3 -m venv venv
    ```
  - **Activate the Environment:**
    ```bash
    source venv/bin/activate
    ```
  - **Create `requirements.txt`:** Create a file named `requirements.txt` with the necessary Python libraries.

-----

## 2\. The Project Directory Structure

A logical directory structure is key to a maintainable project. Create the following layout in your project's root directory.

```
.
├── .env
├── .env.example
├── Makefile
├── requirements.txt
├── scripts/
│   ├── utils/
│   │   ├── __init__.py
│   │   └── config.py
│   └── process_data.py
└── sql/
    ├── 10_setup/
    │   ├── 01_extensions.sql
    │   ├── 02_schemas.sql
    │   └── 03_tables.sql
    ├── 20_functions/
    │   └── 01_name_normalization.sql
    └── 30_constraints/
        └── 01_names_exclusion.sql
```

-----

## 3\. Core File Contents

Here are the complete contents for each core file in the structure.

### **3.1. `requirements.txt`**

```
psycopg2-binary==2.9.9
python-dotenv==1.0.1
tenacity==8.2.3
click==8.1.7
osmium==3.6.0
geopandas==0.14.3
shapely==2.0.4
tqdm==4.66.4
```

*(Install with `pip install -r requirements.txt`)*

### **3.2. `.env.example`**

(Copy this to a file named `.env` and fill in your password. The `.env` file should be added to `.gitignore` and never committed to version control.)

```ini
# PostgreSQL Database Configuration for Local Postgres.app
DB_HOST=localhost
DB_PORT=5432
DB_DATABASE=mariupol_toponyms
DB_USER=mariupol_researcher
DB_PASSWORD=your_secret_password_here
```

### **3.3. `Makefile`**

(This file automates your common tasks.)

```makefile
.PHONY: help clean_db init_db connect_db run_import

# Default command
help:
	@echo "Available commands:"
	@echo "  make clean_db    - Drops and recreates the database and user."
	@echo "  make init_db     - Runs all SQL scripts to set up the database schema."
	@echo "  make connect_db  - Connects to the database using psql."
	@echo "  make run_import  - Runs the main Python data import script."

# Load environment variables from .env file
include .env
export

# PostgreSQL connection string for psql
PSQL_CONN_ADMIN := "postgresql://postgres@$(DB_HOST):$(DB_PORT)/postgres"
PSQL_CONN_APP   := "postgresql://$(DB_USER):$(DB_PASSWORD)@$(DB_HOST):$(DB_PORT)/$(DB_DATABASE)"

clean_db:
	@echo "WARNING: This will delete all data for user $(DB_USER) and database $(DB_DATABASE)!"
	@read -p "Press Enter to continue, or Ctrl+C to cancel."
	@psql $(PSQL_CONN_ADMIN) -c "DROP DATABASE IF EXISTS $(DB_DATABASE);"
	@psql $(PSQL_CONN_ADMIN) -c "DROP ROLE IF EXISTS $(DB_USER);"
	@echo "Database and role dropped."

init_db:
	@echo "Creating database and user..."
	@psql $(PSQL_CONN_ADMIN) -c "CREATE DATABASE $(DB_DATABASE);"
	@psql $(PSQL_CONN_ADMIN) -c "CREATE ROLE $(DB_USER) WITH LOGIN PASSWORD '$(DB_PASSWORD)';"
	@psql $(PSQL_CONN_ADMIN) -c "GRANT ALL PRIVILEGES ON DATABASE $(DB_DATABASE) TO $(DB_USER);"
	@echo "Running setup scripts..."
	@for f in $(shell find sql/10_setup -name '*.sql' | sort); do \
		echo "Executing $$f..."; \
		psql $(PSQL_CONN_APP) -f $$f; \
	done
	@echo "Running function scripts..."
	@for f in $(shell find sql/20_functions -name '*.sql' | sort); do \
		echo "Executing $$f..."; \
		psql $(PSQL_CONN_APP) -f $$f; \
	done
	@echo "Running constraint scripts..."
	@for f in $(shell find sql/30_constraints -name '*.sql' | sort); do \
		echo "Executing $$f..."; \
		psql $(PSQL_CONN_APP) -f $$f; \
	done
	@echo "Database initialization complete."

connect_db:
	@psql $(PSQL_CONN_APP)

run_import:
	@echo "Running data import..."
	@python3 scripts/process_data.py --pbf-file path/to/your/data.osm.pbf

```

-----

## 4\. SQL Directory Files

These files define your entire database structure in a version-controllable and repeatable way.

### **4.1. `sql/10_setup/01_extensions.sql`**

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS btree_gist;
```

### **4.2. `sql/10_setup/02_schemas.sql`**

```sql
CREATE SCHEMA IF NOT EXISTS toponyms;
CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS staging;

-- Set the default search path for the user to prioritize our custom schema
ALTER ROLE mariupol_researcher SET search_path TO toponyms, public;
```

### **4.3. `sql/10_setup/03_tables.sql`**

```sql
CREATE TABLE IF NOT EXISTS toponyms.entity_types (
    type_code VARCHAR(50) PRIMARY KEY,
    description TEXT
);

CREATE TABLE IF NOT EXISTS toponyms.entities (
    entity_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type VARCHAR(50) NOT NULL REFERENCES toponyms.entity_types(type_code),
    geometry GEOMETRY(GEOMETRY, 4326) NOT NULL,
    source_authority TEXT,
    valid_start TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS entities_geom_idx ON toponyms.entities USING GIST (geometry);

CREATE TABLE IF NOT EXISTS toponyms.names (
    name_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id UUID NOT NULL REFERENCES toponyms.entities(entity_id) ON DELETE CASCADE,
    name_text TEXT NOT NULL,
    normalized_name TEXT,
    language_code VARCHAR(10),
    name_type VARCHAR(50) DEFAULT 'official',
    valid_start TIMESTAMPTZ NOT NULL,
    valid_end TIMESTAMPTZ,
    source_type TEXT,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS names_entity_id_idx ON toponyms.names (entity_id);

-- Pre-populate types
INSERT INTO toponyms.entity_types (type_code, description) VALUES
('street', 'Street, avenue, or road'),
('district', 'Administrative district'),
('park', 'Park or green space')
ON CONFLICT (type_code) DO NOTHING;
```

### **4.4. `sql/20_functions/01_name_normalization.sql`**

```sql
CREATE OR REPLACE FUNCTION toponyms.normalize_name(input_text TEXT)
RETURNS TEXT AS $$
DECLARE
    normalized_text TEXT;
BEGIN
    IF input_text IS NULL THEN RETURN NULL; END IF;
    normalized_text := lower(input_text);
    normalized_text := regexp_replace(normalized_text, '[.,''"`-]', '', 'g');
    normalized_text := regexp_replace(normalized_text, '[[:space:]]+', ' ', 'g');
    normalized_text := trim(normalized_text);
    RETURN normalized_text;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

GRANT EXECUTE ON FUNCTION toponyms.normalize_name(TEXT) TO mariupol_researcher;
```

### **4.5. `sql/30_constraints/01_names_exclusion.sql`**

```sql
ALTER TABLE toponyms.names
ADD CONSTRAINT names_entity_text_lang_type_timespan_excl
EXCLUDE USING gist (
    entity_id WITH =,
    name_text WITH =,
    language_code WITH =,
    name_type WITH =,
    tstzrange(valid_start, valid_end, '[]') WITH &&
);
```

-----

## 5\. Application Code (`scripts/` directory)

This code is structured for resilience and clear configuration.

### **5.1. `scripts/utils/config.py`**

```python
import os
from dotenv import load_dotenv
import logging

# Load environment variables from a .env file in the project root
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

# --- Database Configuration ---
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "database": os.getenv("DB_DATABASE"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD")
}

if not DB_CONFIG["password"]:
    raise ValueError("DB_PASSWORD environment variable not set. Please check your .env file.")

# --- Logging Setup ---
def setup_logging(name):
    logger = logging.getLogger(name)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    if not logger.handlers:
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
```

### **5.2. `scripts/process_data.py`** (Template)

```python
import click
import logging
import psycopg2
from psycopg2 import pool
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Import our custom config
from utils.config import DB_CONFIG, setup_logging

logger = setup_logging(__name__)

# --- Resilient Database Connection ---
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(psycopg2.OperationalError),
    before_sleep=lambda rs: logger.warning(f"DB connection failed. Retrying... (Attempt {rs.attempt_number})")
)
def get_resilient_connection(db_pool):
    return db_pool.getconn()

# --- Main Application ---
@click.command()
@click.option('--pbf-file', required=True, type=click.Path(exists=True))
def main(pbf_file):
    """
    Main entry point for processing data.
    """
    logger.info(f"Starting data processing for {pbf_file}")
    db_pool = None
    conn = None
    try:
        db_pool = psycopg2.pool.SimpleConnectionPool(1, 5, **DB_CONFIG)
        conn = get_resilient_connection(db_pool)
        
        with conn.cursor() as cur:
            # --- YOUR DATA PROCESSING LOGIC GOES HERE ---
            # Example:
            cur.execute("SELECT COUNT(*) FROM toponyms.entities;")
            count = cur.fetchone()[0]
            logger.info(f"Successfully connected. Found {count} entities in the database.")
            # Your script would continue to parse the PBF and insert data...
            
        conn.commit()

    except Exception as e:
        logger.error(f"A critical error occurred: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn and db_pool:
            db_pool.putconn(conn)
        if db_pool:
            db_pool.closeall()
        logger.info("Process finished.")

if __name__ == "__main__":
    main()
```

-----

## 6\. Implementation Workflow

1.  **Create Directories:** Set up the `sql/{10_setup,20_functions,30_constraints}` and `scripts/utils` directories.
2.  **Populate Files:** Create all the files listed above and paste the corresponding code into them.
3.  **Configure Environment:** Copy `.env.example` to `.env` and enter your chosen password.
4.  **Install Dependencies:** Run `pip install -r requirements.txt`.
5.  **Initialize Database:** Open a **new terminal window** (to ensure the `$PATH` is updated for `psql`). Run `make clean_db` followed by `make init_db`. This will set up your entire database schema.
6.  **Test Connection:** Run `make connect_db`. You should be logged into your new database. Type `\q` to exit.
7.  **Run Your Code:** Run `make run_import` (after updating the PBF file path in the `Makefile`) to execute your main Python script.

<!-- end list -->

```
```