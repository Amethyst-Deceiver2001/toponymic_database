#!/usr/bin/env python3
"""
OSM Data Processor for Mariupol Toponymic Analysis
Loads extracted OSM data into PostgreSQL database with PostGIS.

Usage:
    python process_osm_data.py --help
    python process_osm_data.py --verify-system
    python process_osm_data.py --load data/analysis/osm/mariupol-pre-invasion.osm.pbf
    python process_osm_data.py --analyze-toponyms
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone
import json
import psycopg
import psycopg2  # Keep for backward compatibility
import osmium
from tqdm import tqdm
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Database configuration
DB_CONFIG = {
    # Connection parameters for psycopg3
    # Note: Use dbname, not database
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', '5432')),
    'dbname': os.getenv('DB_NAME', 'mariupol_toponyms'),
    'user': os.getenv('DB_USER', 'alexeykovalev'),
    'password': os.getenv('DB_PASSWORD', 'REDACTED')
}

# For backward compatibility with code that might use 'database' key

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('osm_processing.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class OSMDatabaseLoader(osmium.SimpleHandler):
    """Load OSM data into PostgreSQL database."""
    
    def __init__(self, connection):
        osmium.SimpleHandler.__init__(self)
        self.conn = connection

def verify_system():
    """Verify database connection and system readiness."""
    try:
        logger.info("🔍 Verifying system readiness...")
        
        # Test database connection
        conn = psycopg.connect(
    host=DB_CONFIG["host"],
    port=DB_CONFIG["port"],
    dbname=DB_CONFIG["dbname"],
    user=DB_CONFIG["user"],
    password=DB_CONFIG["password"]
)
        logger.info("✅ Database connection successful")
        
        # Test PostGIS
        with conn.cursor() as cur:
            cur.execute('SELECT PostGIS_Version();')
            version = cur.fetchone()[0]
            logger.info(f"✅ PostGIS version: {version}")
            
            # Check schema exists
            cur.execute("""
                SELECT schema_name 
                FROM information_schema.schemata 
                WHERE schema_name = 'public'
            """)
            if not cur.fetchone():
                logger.warning("⚠️  Public schema not found")
            else:
                logger.info("✅ Public schema exists")
        
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ System verification failed: {str(e)}")
        return False

def load_osm_file(file_path):
    """Load OSM file into database."""
    if not os.path.exists(file_path):
        logger.error(f"❌ OSM file not found: {file_path}")
        return False
        
    try:
        conn = psycopg.connect(
    host=DB_CONFIG["host"],
    port=DB_CONFIG["port"],
    dbname=DB_CONFIG["dbname"],
    user=DB_CONFIG["user"],
    password=DB_CONFIG["password"]
)
        logger.info("✅ Connected to database")
        
        # Create loader
        loader = OSMDatabaseLoader(conn)
        
        # Process file
        logger.info("🔄 Processing OSM data...")
        start_time = datetime.now()
        
        loader.apply_file(str(file_path), locations=True)
        
        # Commit changes
        conn.commit()
        conn.close()
        
        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"✅ Successfully loaded OSM data in {duration:.2f} seconds")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error loading OSM data: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False

def analyze_toponyms():
    """Extract and analyze toponymic data from loaded OSM data."""
    try:
        conn = psycopg.connect(
    host=DB_CONFIG["host"],
    port=DB_CONFIG["port"],
    dbname=DB_CONFIG["dbname"],
    user=DB_CONFIG["user"],
    password=DB_CONFIG["password"]
)
        
        with conn.cursor() as cur:
            # Extract toponyms from OSM data
            logger.info("📊 Extracting toponyms from OSM data...")
            
            extract_sql = """
            INSERT INTO analysis.toponyms 
            (osm_type, osm_id, osm_version, name_current, name_variants, location, 
             place_type, first_seen, last_modified, status)
            SELECT 
                'node' as osm_type,
                n.id as osm_id,
                n.version as osm_version,
                n.tags->'name' as name_current,
                ARRAY[n.tags->'name:ru', n.tags->'name:uk', n.tags->'old_name'] as name_variants,
                ST_SetSRID(ST_MakePoint(n.lon, n.lat), 4326) as location,
                n.tags->'place' as place_type,
                NOW() as first_seen,
                NOW() as last_modified,
                'active' as status
            FROM nodes n
            WHERE n.tags->'name' IS NOT NULL
            AND n.tags->'place' IS NOT NULL
            
            UNION ALL
            
            SELECT 
                'way' as osm_type,
                w.id as osm_id,
                w.version as osm_version,
                w.tags->'name' as name_current,
                ARRAY[w.tags->'name:ru', w.tags->'name:uk', w.tags->'old_name'] as name_variants,
                ST_Centroid(w.linestring) as location,
                w.tags->'place' as place_type,
                NOW() as first_seen,
                NOW() as last_modified,
                'active' as status
            FROM ways w
            WHERE w.tags->'name' IS NOT NULL
            AND w.tags->'place' IS NOT NULL
            AND w.linestring IS NOT NULL;
            """
            
            cur.execute(extract_sql)
            conn.commit()
            
            # Count toponyms
            cur.execute("SELECT COUNT(*) FROM analysis.toponyms")
            count = cur.fetchone()[0]
            logger.info(f"✅ Extracted {count} toponyms")
            
            # Analyze naming patterns
            logger.info("🔍 Analyzing naming patterns...")
            analysis_sql = """
            -- Your analysis queries here
            """
            cur.execute(analysis_sql)
            
            logger.info("✅ Toponym analysis complete")
            
        return True
        
    except Exception as e:
        logger.error(f"❌ Error analyzing toponyms: {str(e)}")
        conn.rollback()
        return False
        
    finally:
        if 'conn' in locals():
            conn.close()

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Process OSM data for Mariupol toponym analysis')
    parser.add_argument('--verify-system', action='store_true', help='Verify system requirements')
    parser.add_argument('--load', type=str, help='Load OSM file into database')
    parser.add_argument('--analyze-toponyms', action='store_true', help='Analyze toponym data')
    
    args = parser.parse_args()
    
    if args.verify_system:
        if not verify_system():
            sys.exit(1)
    
    elif args.load:
        if not load_osm_file(args.load):
            sys.exit(1)
    
    elif args.analyze_toponyms:
        if not analyze_toponyms():
            sys.exit(1)
    
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
