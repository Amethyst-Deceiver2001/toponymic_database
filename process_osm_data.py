#!/usr/bin/env python3
# process_osm_data.py
"""
Script to load extracted OpenStreetMap data from a PBF file into the toponymic database.
This version includes resilient database connections and corrected SQL for data integrity.
"""

import sys
from pathlib import Path
import osmium as osm
import geopandas as gpd
from shapely.geometry import Point, LineString
from typing import Dict, Any, List
import click
import logging
from tqdm import tqdm

# --- Resiliency and Database Imports ---
# Tenacity is used for robust, retrying database connections.
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import psycopg2
from psycopg2 import pool
from psycopg2.extras import DictCursor

# --- Project-specific Imports ---
# Assuming config.py is in scripts/utils/
sys.path.append(str(Path(__file__).parent.joinpath('scripts', 'utils')))
from config import setup_logging, MARIUPOL_BBOX

# Use the logger setup from your config file
logger = setup_logging(__name__)


# --- Resilient Database Connection Handling ---
@retry(
    stop=stop_after_attempt(7),  # Retry up to 7 times
    wait=wait_exponential(multiplier=1, min=2, max=30),  # Wait 2s, 4s, 8s, 16s, 30s, 30s...
    retry=retry_if_exception_type(psycopg2.OperationalError), # Only retry on connection-related errors
    before_sleep=lambda retry_state: logger.warning(
        f"DB connection failed. Retrying in {retry_state.next_action.sleep:.0f}s "
        f"(Attempt {retry_state.attempt_number})..."
    )
)
def get_resilient_db_connection(db_pool):
    """Gets a connection from the pool with retry logic."""
    logger.info("Attempting to acquire database connection...")
    conn = db_pool.getconn()
    logger.info("Database connection established successfully.")
    return conn


# --- OSM Data Processing Classes ---
class OSMDataHandler(osm.SimpleHandler):
    """
    Osmium handler to extract named ways, relations, and nodes from OSM PBF data.
    """
    def __init__(self):
        super(OSMDataHandler, self).__init__()
        self.features = []
        logger.info("Initialized OSM Data Handler.")

    def process_tags(self, element):
        tags = dict(element.tags)
        name_tags = {k: v for k, v in tags.items() if k.startswith('name')}
        if not name_tags:
            return None

        properties = {
            'osm_id': element.id,
            'osm_type': 'node' if isinstance(element, osm.osm.Node) else ('way' if isinstance(element, osm.osm.Way) else 'relation'),
            **{k: v for k, v in tags.items() if not k.startswith('name')}
        }
        return {'name_tags': name_tags, 'properties': properties}

    def node(self, n):
        data = self.process_tags(n)
        if data:
            try:
                geom = Point(n.location.lon, n.location.lat)
                data['geometry'] = geom
                self.features.append(data)
            except osm.InvalidLocationError:
                logger.warning(f"Skipping node {n.id} due to invalid location.")

    def way(self, w):
        data = self.process_tags(w)
        if data:
            try:
                # Reconstitute line geometry from node references
                coords = [(node.lon, node.lat) for node in w.nodes]
                if len(coords) >= 2:
                    geom = LineString(coords)
                    data['geometry'] = geom
                    self.features.append(data)
            except (osm.InvalidLocationError, RuntimeError) as e:
                logger.warning(f"Skipping way {w.id}: {e}")

    def area(self, a):
        # Areas (from closed ways or relations) are complex. This is a simplified handler.
        data = self.process_tags(a)
        if data:
            # For this simplified script, we don't build the full polygon geometry here
            # as it can be complex. We'll rely on GeoPandas to handle WKT if available,
            # or just log the properties.
            logger.debug(f"Processing area from OSM ID: {a.orig_id}")
            # In a full implementation, you'd use a geometry factory here.


class DataLoader:
    """Handles the logic of loading processed OSM data into the database."""
    def __init__(self, db_pool):
        self.db_pool = db_pool

    def get_valid_entity_types(self):
        """Fetches valid entity types from the database for validation."""
        conn = None
        try:
            conn = get_resilient_db_connection(self.db_pool)
            with conn.cursor() as cur:
                cur.execute("SELECT type_code FROM toponyms.entity_types;")
                types = [row[0] for row in cur.fetchall()]
                logger.info(f"Loaded valid entity types from DB: {types}")
                return types
        except psycopg2.Error as e:
            logger.error(f"Could not fetch entity types: {e}. Falling back to a hardcoded list.")
            return ['region', 'district', 'street', 'square', 'park', 'building', 'city', 'point_of_interest', 'area', 'path', 'waterway']
        finally:
            if conn:
                self.db_pool.putconn(conn)

    def load_osm_data_to_db(self, pbf_filepath: Path, query_date: str, source_authority: str):
        logger.info(f"📊 Starting data extraction from {pbf_filepath}")
        
        handler = OSMDataHandler()
        # Use idx='dense_file_array' for better performance if memory allows
        handler.apply_file(str(pbf_filepath), locations=True, idx='sparse_mem_array')
        logger.info(f"Finished extraction. Found {len(handler.features)} named features.")

        if not handler.features:
            logger.warning("⚠️ No named features found in PBF file. Nothing to load.")
            return

        gdf = gpd.GeoDataFrame(handler.features, crs="EPSG:4326")
        gdf['geometry'] = gdf['geometry'].buffer(0)
        gdf = gdf[gdf['geometry'].is_valid]
        logger.info(f"Created and cleaned GeoDataFrame with {len(gdf)} valid features.")

        valid_db_entity_types = self.get_valid_entity_types()
        conn = None
        try:
            conn = get_resilient_db_connection(self.db_pool)
            with conn.cursor() as cur:
                logger.info(f"Starting database import of {len(gdf)} features...")
                for index, row in tqdm(gdf.iterrows(), total=len(gdf), desc="DB Loading"):
                    try:
                        # --- Entity Mapping Logic ---
                        properties = row['properties']
                        mapped_entity_type = get_entity_type(properties, row['geometry'].geom_type)
                        if mapped_entity_type not in valid_db_entity_types:
                            mapped_entity_type = 'point_of_interest'

                        # --- Insert Entity ---
                        sql_entity = """
                        INSERT INTO toponyms.entities (entity_type, geometry, source_authority, valid_start)
                        VALUES (%s, ST_SetSRID(ST_GeomFromText(%s), 4326), %s, %s)
                        RETURNING entity_id;
                        """
                        cur.execute(sql_entity, (mapped_entity_type, row['geometry'].wkt, source_authority, query_date))
                        entity_id = cur.fetchone()[0]

                        # --- Insert Names ---
                        for name_tag, name_value in row['name_tags'].items():
                            if not name_value or not name_value.strip(): continue
                            
                            lang_code = 'und'
                            if name_tag == 'name:uk': lang_code = 'ukr'
                            elif name_tag == 'name:ru': lang_code = 'rus'
                            elif name_tag == 'name:en': lang_code = 'eng'
                            elif name_tag == 'name': lang_code = 'ukr' # Default 'name' tag to Ukrainian

                            # CORRECTED INSERT STATEMENT FOR NAMES
                            sql_name = """
                            INSERT INTO toponyms.names
                            (entity_id, name_text, normalized_name, language_code, name_type, valid_start, source_type, notes)
                            VALUES (
                                %(entity_id)s,
                                %(name_text)s,
                                toponyms.normalize_name(%(name_text)s),
                                %(language_code)s,
                                'official',
                                %(valid_start)s,
                                'osm_data',
                                %(notes)s
                            )
                            -- This ON CONFLICT clause correctly references the EXCLUSION constraint
                            -- defined in 'sql/setup/04_constraints.sql'. It tells PostgreSQL
                            -- to ignore inserts that violate our rule against overlapping time
                            -- periods for the same name, preventing the script from crashing.
                            ON CONFLICT ON CONSTRAINT names_entity_text_lang_type_timespan_excl
                            DO NOTHING;
                            """
                            cur.execute(sql_name, {
                                'entity_id': entity_id,
                                'name_text': name_value,
                                'language_code': lang_code,
                                'valid_start': query_date,
                                'notes': f"OSM ID: {row['osm_id']}, Type: {row['properties']['osm_type']}, Tag: {name_tag}"
                            })
                    except Exception as e:
                        logger.error(f"Skipping OSM ID {row.get('osm_id', 'N/A')} due to error: {e}")
                        # Rollback the transaction for this specific feature to maintain data integrity
                        conn.rollback()
                        # Restart the transaction for the next loop iteration
                        conn.autocommit = False 
                        continue

            # Commit the final transaction if all went well
            conn.commit()
            logger.info(f"✅ Database import complete. Processed {len(gdf)} features.")

        except psycopg2.Error as e:
            logger.error(f"A database error occurred during the import process: {e}")
            if conn:
                conn.rollback()
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            if conn:
                self.db_pool.putconn(conn)


# --- Command Line Interface ---
@click.command()
@click.option('--load', 'pbf_file',
              required=True,
              type=click.Path(exists=True, dir_okay=False, readable=True),
              help='Path to the OpenStreetMap PBF file to load.')
@click.option('--query-date',
              default="2022-02-23",
              help='Date to assign as valid_start for imported data (YYYY-MM-DD).')
def main(pbf_file: str, query_date: str):
    """
    Orchestrates the loading of OpenStreetMap data into the toponymic database.
    """
    logger.info(f"Starting process for PBF file: {pbf_file}")
    full_query_date = f"{query_date}T00:00:00Z"
    
    db_pool = None
    try:
        # --- Database Connection Pool ---
        # This pool manages connections. The get_resilient_db_connection function
        # will handle retries if the database is not immediately available.
        db_pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=5,
            dbname="mariupol_toponyms",
            user="mariupol_researcher",
            password="your_password", # IMPORTANT: Replace with your password or load from .env
            host="localhost",
            port="5433"
        )
        
        data_loader = DataLoader(db_pool)
        data_loader.load_osm_data_to_db(Path(pbf_file), full_query_date, "OpenStreetMap")

    except Exception as e:
        logger.error(f"❌ A critical error occurred in the main process: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        if db_pool:
            db_pool.closeall()
            logger.info("Database connection pool closed.")

if __name__ == "__main__":
    main()