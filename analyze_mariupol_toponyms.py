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
import osmium
from tqdm import tqdm
import logging

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'mariupol_toponyms',
    'user': 'mariupol_user',
    'password': 'secure_password'
}

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
        self.batch_size = 1000
        
        # Batch storage
        self.node_batch = []
        self.way_batch = []
        self.relation_batch = []
        
        # Statistics
        self.stats = {
            'nodes_processed': 0,
            'ways_processed': 0,
            'relations_processed': 0,
            'nodes_inserted': 0,
            'ways_inserted': 0,
            'relations_inserted': 0,
            'toponyms_found': 0
        }
        
        # Toponymic keywords for detection
        self.toponymic_tags = {
            'name', 'name:uk', 'name:ru', 'name:en', 
            'place', 'addr:street', 'addr:city',
            'official_name', 'old_name', 'alt_name'
        }
        
    def _has_toponymic_data(self, tags):
        """Check if OSM object has toponymic information."""
        if not tags:
            return False
        return any(tag in self.toponymic_tags for tag in tags.keys())
    
    def _extract_location(self, obj):
        """Extract location as WKT for PostGIS."""
        if hasattr(obj, 'location') and obj.location.valid():
            lon, lat = obj.location.lon, obj.location.lat
            return f'POINT({lon} {lat})'
        return None
    
    def _prepare_tags_json(self, tags):
        """Convert OSM tags to JSON for database storage."""
        if not tags:
            return None
        return json.dumps(dict(tags))
    
    def node(self, n):
        """Process OSM nodes."""
        self.stats['nodes_processed'] += 1
        
        # Extract data
        location_wkt = self._extract_location(n)
        tags_json = self._prepare_tags_json(n.tags)
        
        # Add to batch
        self.node_batch.append({
            'id': n.id,
            'version': n.version,
            'timestamp': n.timestamp.to_datetime(),
            'changeset_id': n.changeset,
            'user_id': n.uid,
            'username': n.user,
            'location': location_wkt,
            'tags': tags_json
        })
        
        # Check for toponymic data
        if self._has_toponymic_data(n.tags):
            self.stats['toponyms_found'] += 1
        
        # Process batch if full
        if len(self.node_batch) >= self.batch_size:
            self._insert_node_batch()
    
    def way(self, w):
        """Process OSM ways."""
        self.stats['ways_processed'] += 1
        
        # Extract data
        tags_json = self._prepare_tags_json(w.tags)
        node_refs = list(w.nodes) if w.nodes else []
        
        # Add to batch
        self.way_batch.append({
            'id': w.id,
            'version': w.version,
            'timestamp': w.timestamp.to_datetime(),
            'changeset_id': w.changeset,
            'user_id': w.uid,
            'username': w.user,
            'node_refs': node_refs,
            'tags': tags_json,
            'geometry': None  # Will be calculated later if needed
        })
        
        # Check for toponymic data
        if self._has_toponymic_data(w.tags):
            self.stats['toponyms_found'] += 1
        
        # Process batch if full
        if len(self.way_batch) >= self.batch_size:
            self._insert_way_batch()
    
    def relation(self, r):
        """Process OSM relations."""
        self.stats['relations_processed'] += 1
        
        # Extract data
        tags_json = self._prepare_tags_json(r.tags)
        
        # Extract members
        members = []
        for member in r.members:
            members.append({
                'type': member.type,
                'ref': member.ref,
                'role': member.role
            })
        
        # Add to batch
        self.relation_batch.append({
            'id': r.id,
            'version': r.version,
            'timestamp': r.timestamp.to_datetime(),
            'changeset_id': r.changeset,
            'user_id': r.uid,
            'username': r.user,
            'members': json.dumps(members),
            'tags': tags_json
        })
        
        # Check for toponymic data
        if self._has_toponymic_data(r.tags):
            self.stats['toponyms_found'] += 1
        
        # Process batch if full
        if len(self.relation_batch) >= self.batch_size:
            self._insert_relation_batch()
    
    def _insert_node_batch(self):
        """Insert batch of nodes into database."""
        if not self.node_batch:
            return
        
        try:
            with self.conn.cursor() as cur:
                # Prepare INSERT statement
                insert_sql = """
                INSERT INTO osm_data.nodes 
                (id, version, timestamp, changeset_id, user_id, username, location, tags)
                VALUES (%(id)s, %(version)s, %(timestamp)s, %(changeset_id)s, 
                       %(user_id)s, %(username)s, 
                       CASE WHEN %(location)s IS NOT NULL THEN ST_GeomFromText(%(location)s, 4326) ELSE NULL END,
                       %(tags)s::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    version = EXCLUDED.version,
                    timestamp = EXCLUDED.timestamp,
                    changeset_id = EXCLUDED.changeset_id,
                    user_id = EXCLUDED.user_id,
                    username = EXCLUDED.username,
                    location = EXCLUDED.location,
                    tags = EXCLUDED.tags
                """
                
                cur.executemany(insert_sql, self.node_batch)
                self.conn.commit()
                
                self.stats['nodes_inserted'] += len(self.node_batch)
                logger.debug(f"Inserted {len(self.node_batch)} nodes")
                
        except Exception as e:
            logger.error(f"Error inserting node batch: {e}")
            self.conn.rollback()
        
        finally:
            self.node_batch = []
    
    def _insert_way_batch(self):
        """Insert batch of ways into database."""
        if not self.way_batch:
            return
        
        try:
            with self.conn.cursor() as cur:
                insert_sql = """
                INSERT INTO osm_data.ways 
                (id, version, timestamp, changeset_id, user_id, username, node_refs, tags, geometry)
                VALUES (%(id)s, %(version)s, %(timestamp)s, %(changeset_id)s, 
                       %(user_id)s, %(username)s, %(node_refs)s, %(tags)s::jsonb, %(geometry)s)
                ON CONFLICT (id) DO UPDATE SET
                    version = EXCLUDED.version,
                    timestamp = EXCLUDED.timestamp,
                    changeset_id = EXCLUDED.changeset_id,
                    user_id = EXCLUDED.user_id,
                    username = EXCLUDED.username,
                    node_refs = EXCLUDED.node_refs,
                    tags = EXCLUDED.tags,
                    geometry = EXCLUDED.geometry
                """
                
                cur.executemany(insert_sql, self.way_batch)
                self.conn.commit()
                
                self.stats['ways_inserted'] += len(self.way_batch)
                logger.debug(f"Inserted {len(self.way_batch)} ways")
                
        except Exception as e:
            logger.error(f"Error inserting way batch: {e}")
            self.conn.rollback()
        
        finally:
            self.way_batch = []
    
    def _insert_relation_batch(self):
        """Insert batch of relations into database."""
        if not self.relation_batch:
            return
        
        try:
            with self.conn.cursor() as cur:
                insert_sql = """
                INSERT INTO osm_data.relations 
                (id, version, timestamp, changeset_id, user_id, username, members, tags)
                VALUES (%(id)s, %(version)s, %(timestamp)s, %(changeset_id)s, 
                       %(user_id)s, %(username)s, %(members)s::jsonb, %(tags)s::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    version = EXCLUDED.version,
                    timestamp = EXCLUDED.timestamp,
                    changeset_id = EXCLUDED.changeset_id,
                    user_id = EXCLUDED.user_id,
                    username = EXCLUDED.username,
                    members = EXCLUDED.members,
                    tags = EXCLUDED.tags
                """
                
                cur.executemany(insert_sql, self.relation_batch)
                self.conn.commit()
                
                self.stats['relations_inserted'] += len(self.relation_batch)
                logger.debug(f"Inserted {len(self.relation_batch)} relations")
                
        except Exception as e:
            logger.error(f"Error inserting relation batch: {e}")
            self.conn.rollback()
        
        finally:
            self.relation_batch = []
    
    def finalize(self):
        """Process any remaining batches."""
        self._insert_node_batch()
        self._insert_way_batch()
        self._insert_relation_batch()


def verify_system():
    """Verify database connection and system readiness."""
    logger.info("🔍 Verifying system readiness...")
    
    try:
        # Test database connection
        conn = psycopg.connect(**DB_CONFIG)
        logger.info("✅ Database connection successful")
        
        # Test PostGIS
        with conn.cursor() as cur:
            cur.execute('SELECT PostGIS_Version();')
            version = cur.fetchone()[0]
            logger.info(f"✅ PostGIS version: {version}")
            
            # Check schema exists
            cur.execute("""
                SELECT schema_name FROM information_schema.schemata 
                WHERE schema_name IN ('osm_data', 'analysis', 'evidence')
                ORDER BY schema_name
            """)
            schemas = [row[0] for row in cur.fetchall()]
            logger.info(f"✅ Database schemas: {', '.join(schemas)}")
            
            # Check tables exist
            cur.execute("""
                SELECT table_schema, table_name FROM information_schema.tables 
                WHERE table_schema IN ('osm_data', 'analysis', 'evidence')
                ORDER BY table_schema, table_name
            """)
            tables = cur.fetchall()
            logger.info(f"✅ Database tables: {len(tables)} tables ready")
            
        conn.close()
        
        # Check input files
        input_dir = Path('data/analysis/osm')
        if input_dir.exists():
            osm_files = list(input_dir.glob('*.osm.pbf'))
            logger.info(f"✅ OSM files available: {len(osm_files)}")
            for file in osm_files:
                size_mb = file.stat().st_size / 1024 / 1024
                logger.info(f"   - {file.name}: {size_mb:.1f} MB")
        else:
            logger.warning("⚠️  No OSM analysis directory found")
        
        logger.info("🎯 System verification complete - ready for processing")
        return True
        
    except Exception as e:
        logger.error(f"❌ System verification failed: {e}")
        return False


def load_osm_file(file_path):
    """Load OSM file into database."""
    file_path = Path(file_path)
    
    if not file_path.exists():
        logger.error(f"❌ File not found: {file_path}")
        return False
    
    logger.info(f"📊 Loading OSM data from {file_path}")
    logger.info(f"   File size: {file_path.stat().st_size / 1024 / 1024:.1f} MB")
    
    try:
        # Connect to database
        conn = psycopg.connect(**DB_CONFIG)
        logger.info("✅ Connected to database")
        
        # Create loader
        loader = OSMDatabaseLoader(conn)
        
        # Process file
        logger.info("🔄 Processing OSM data...")
        start_time = datetime.now()
        
        loader.apply_file(str(file_path), locations=True)
        loader.finalize()
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Log statistics
        stats = loader.stats
        logger.info("✅ OSM data processing complete!")
        logger.info(f"   Duration: {duration:.1f} seconds")
        logger.info(f"   Nodes: {stats['nodes_processed']:,} processed, {stats['nodes_inserted']:,} inserted")
        logger.info(f"   Ways: {stats['ways_processed']:,} processed, {stats['ways_inserted']:,} inserted")
        logger.info(f"   Relations: {stats['relations_processed']:,} processed, {stats['relations_inserted']:,} inserted")
        logger.info(f"   Toponyms found: {stats['toponyms_found']:,}")
        
        # Update database statistics
        with conn.cursor() as cur:
            cur.execute("ANALYZE;")
            conn.commit()
            logger.info("✅ Database statistics updated")
        
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ Error loading OSM file: {e}")
        return False


def analyze_toponyms():
    """Extract and analyze toponymic data from loaded OSM data."""
    logger.info("🔍 Analyzing toponymic data...")
    
    try:
        conn = psycopg.connect(**DB_CONFIG)
        
        with conn.cursor() as cur:
            # Extract toponyms from OSM data
            logger.info("📊 Extracting toponyms from OSM data...")
            
            extract_sql = """
            INSERT INTO analysis.toponyms 
            (osm_type, osm_id, osm_version, name_current, name_variants, location, 
             place_type, first_seen, last_modified, status)
            
            -- Extract from nodes
            SELECT 'node' as osm_type, 
                   id as osm_id,
                   version as osm_version,
                   COALESCE(tags->>'name', tags->>'name:en', tags->>'name:uk') as name_current,
                   jsonb_build_object(
                       'name', tags->>'name',
                       'name:uk', tags->>'name:uk', 
                       'name:ru', tags->>'name:ru',
                       'name:en', tags->>'name:en',
                       'official_name', tags->>'official_name',
                       'old_name', tags->>'old_name'
                   ) as name_variants,
                   location,
                   COALESCE(tags->>'place', tags->>'amenity', 'unknown') as place_type,
                   timestamp as first_seen,
                   timestamp as last_modified,
                   'active' as status
            FROM osm_data.nodes 
            WHERE tags IS NOT NULL 
              AND (tags ? 'name' OR tags ? 'name:uk' OR tags ? 'name:ru' OR tags ? 'name:en' OR tags ? 'place')
              AND location IS NOT NULL
            
            UNION ALL
            
            -- Extract from ways  
            SELECT 'way' as osm_type,
                   id as osm_id, 
                   version as osm_version,
                   COALESCE(tags->>'name', tags->>'name:en', tags->>'name:uk') as name_current,
                   jsonb_build_object(
                       'name', tags->>'name',
                       'name:uk', tags->>'name:uk',
                       'name:ru', tags->>'name:ru', 
                       'name:en', tags->>'name:en',
                       'official_name', tags->>'official_name',
                       'old_name', tags->>'old_name'
                   ) as name_variants,
                   ST_Centroid(geometry) as location,
                   COALESCE(tags->>'highway', tags->>'place', tags->>'landuse', 'unknown') as place_type,
                   timestamp as first_seen,
                   timestamp as last_modified,
                   'active' as status
            FROM osm_data.ways
            WHERE tags IS NOT NULL
              AND (tags ? 'name' OR tags ? 'name:uk' OR tags ? 'name:ru' OR tags ? 'name:en')
            
            UNION ALL
            
            -- Extract from relations
            SELECT 'relation' as osm_type,
                   id as osm_id,
                   version as osm_version, 
                   COALESCE(tags->>'name', tags->>'name:en', tags->>'name:uk') as name_current,
                   jsonb_build_object(
                       'name', tags->>'name',
                       'name:uk', tags->>'name:uk',
                       'name:ru', tags->>'name:ru',
                       'name:en', tags->>'name:en', 
                       'official_name', tags->>'official_name',
                       'old_name', tags->>'old_name'
                   ) as name_variants,
                   NULL as location, -- Relations don't have simple locations
                   COALESCE(tags->>'type', tags->>'boundary', 'unknown') as place_type,
                   timestamp as first_seen,
                   timestamp as last_modified,
                   'active' as status
            FROM osm_data.relations
            WHERE tags IS NOT NULL
              AND (tags ? 'name' OR tags ? 'name:uk' OR tags ? 'name:ru' OR tags ? 'name:en')
            
            ON CONFLICT (osm_type, osm_id, osm_version) DO NOTHING
            """
            
            cur.execute(extract_sql)
            toponyms_count = cur.rowcount
            conn.commit()
            
            logger.info(f"✅ Extracted {toponyms_count:,} toponyms")
            
            # Generate summary statistics
            cur.execute("""
                SELECT 
                    COUNT(*) as total_toponyms,
                    COUNT(*) FILTER (WHERE name_current IS NOT NULL) as named_toponyms,
                    COUNT(*) FILTER (WHERE place_type = 'city') as cities,
                    COUNT(*) FILTER (WHERE place_type = 'town') as towns,
                    COUNT(*) FILTER (WHERE place_type = 'village') as villages,
                    COUNT(*) FILTER (WHERE osm_type = 'node') as node_toponyms,
                    COUNT(*) FILTER (WHERE osm_type = 'way') as way_toponyms,
                    COUNT(*) FILTER (WHERE osm_type = 'relation') as relation_toponyms
                FROM analysis.toponyms
            """)
            
            stats = cur.fetchone()
            logger.info("📊 Toponymic Analysis Summary:")
            logger.info(f"   Total toponyms: {stats[0]:,}")
            logger.info(f"   Named toponyms: {stats[1]:,}")
            logger.info(f"   Cities: {stats[2]:,}")
            logger.info(f"   Towns: {stats[3]:,}")
            logger.info(f"   Villages: {stats[4]:,}")
            logger.info(f"   Distribution: {stats[5]:,} nodes, {stats[6]:,} ways, {stats[7]:,} relations")
        
        conn.close()
        logger.info("🎯 Toponymic analysis complete")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error in toponymic analysis: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Process OSM data for Mariupol toponymic analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Verify system readiness
    python process_osm_data.py --verify-system
    
    # Load extracted OSM data  
    python process_osm_data.py --load data/analysis/osm/mariupol-pre-invasion.osm.pbf
    
    # Analyze toponymic data
    python process_osm_data.py --analyze-toponyms
    
    # Full pipeline
    python process_osm_data.py --verify-system
    python process_osm_data.py --load data/analysis/osm/mariupol-pre-invasion.osm.pbf
    python process_osm_data.py --analyze-toponyms
        """
    )
    
    # Mutually exclusive action group
    action_group = parser.add_mutually_exclusive_group(required=True)
    
    action_group.add_argument(
        '--verify-system',
        action='store_true',
        help='Verify database connection and system readiness'
    )
    
    action_group.add_argument(
        '--load',
        type=Path,
        metavar='OSM_FILE',
        help='Load OSM file into database'
    )
    
    action_group.add_argument(
        '--analyze-toponyms',
        action='store_true',
        help='Extract and analyze toponymic data from loaded OSM data'
    )
    
    args = parser.parse_args()
    
    # Execute requested action
    if args.verify_system:
        success = verify_system()
    elif args.load:
        success = load_osm_file(args.load)
    elif args.analyze_toponyms:
        success = analyze_toponyms()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())