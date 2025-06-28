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
