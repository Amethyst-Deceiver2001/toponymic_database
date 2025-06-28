#!/usr/bin/env python3
# process_osm_data.py
"""
Script to load extracted OpenStreetMap data from a PBF file into the toponymic database.
"""

import sys
from pathlib import Path
import osmium as osm
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon, MultiLineString, MultiPolygon
from datetime import datetime, timezone
from typing import Dict, Any, List
import click
import logging
from tqdm import tqdm

# --- CHANGED IMPORTS FOR PSYCOPG2 ---
import psycopg2 # Use the psycopg2 driver
from psycopg2.extras import DictRow # For dictionary-like rows
from psycopg2 import OperationalError, errors # For error handling
# --- END CHANGED IMPORTS ---

# Import the database connection utility
# Assumes scripts/utils/database.py exists and is updated for psycopg2
from scripts.utils.database import db
from scripts.utils.config import setup_logging, MARIUPOL_BBOX

logger = setup_logging(__name__)

class OSMDataLoader(osm.SimpleHandler):
    """
    Osmium handler to extract named ways, relations, and nodes from OSM PBF data
    within a target bounding box, and prepare them for GeoDataFrame creation.
    """
    def __init__(self, target_bbox: List[float]):
        super(OSMDataLoader, self).__init__()
        self.features = []
        self.target_bbox = target_bbox # [min_lat, min_lon, max_lat, max_lon]
        self.nodes = {} # Store nodes to build ways
        self.processed_objects_count = 0
        self.extracted_objects_count = 0
        logger.info(f"Initialized OSM Data Loader for BBOX: {self.target_bbox}")

    def node(self, n):
        self.processed_objects_count += 1
        if self._is_within_bbox(n.location.lat, n.location.lon):
            self.nodes[n.id] = (n.location.lon, n.location.lat) # Store (lon, lat)

        tags = dict(n.tags)
        if any(tag.startswith('name') for tag in tags) and 'place' in tags and tags['place'] in ["city", "town", "village", "hamlet", "suburb", "borough", "district", "neighbourhood"]:
            if self._is_within_bbox(n.location.lat, n.location.lon):
                self._add_feature(n.id, "node", Point(n.location.lon, n.location.lat), tags)
                self.extracted_objects_count += 1

    def way(self, w):
        self.processed_objects_count += 1
        tags = dict(w.tags)
        if any(tag.startswith('name') for tag in tags): # Only interested in named ways
            try:
                coords = []
                for node_ref in w.nodes:
                    if node_ref.ref in self.nodes:
                        coords.append(self.nodes[node_ref.ref])
                    else:
                        # Node not found in loaded nodes. This happens if node is outside bbox
                        # or if processing a large PBF where all nodes can't be held in memory.
                        # For filtered PBFs, this should be rare for named ways.
                        pass 
                
                if len(coords) > 1:
                    geom = LineString(coords)
                    if self._is_within_bbox(geom.centroid.y, geom.centroid.x): # Check if way centroid is in bbox
                        self._add_feature(w.id, "way", geom, tags)
                        self.extracted_objects_count += 1
                else:
                    logger.debug(f"Skipping way {w.id} with insufficient coordinates ({len(coords)}).")

            except Exception as e:
                logger.warning(f"Error processing way {w.id}: {e}")

    def relation(self, r):
        self.processed_objects_count += 1
        tags = dict(r.tags)
        if any(tag.startswith('name') for tag in tags) and ('boundary' in tags or 'type' in tags and tags['type'] == 'multipolygon'):
            logger.debug(f"Processing relation {r.id} without direct full geometry from PBF for now. Tags: {tags}")
            try:
                if r.nodes or r.ways or r.relations: # Check if it has any members
                    # Attempt to get a centroid if possible from a member node, or default to bbox center
                    center_lat = (self.target_bbox[0] + self.target_bbox[2]) / 2
                    center_lon = (self.target_bbox[1] + self.target_bbox[3]) / 2
                    geom = Point(center_lon, center_lat) # Fallback placeholder
                    
                    self._add_feature(r.id, "relation", geom, tags)
                    self.extracted_objects_count += 1
            except Exception as e:
                 logger.warning(f"Could not add placeholder geometry for relation {r.id}: {e}")

    def _add_feature(self, osm_id, osm_type, geometry, tags):
        name_tags = {k: v for k, v in tags.items() if k.startswith('name:') or k == 'name'}
        if not name_tags: # Ensure it has at least one name tag
            return

        properties = {k: v for k, v in tags.items() if not k.startswith('name')}
        properties['osm_type'] = osm_type
        properties['osm_id'] = osm_id
        
        self.features.append({
            'osm_id': osm_id,
            'osm_type': osm_type,
            'name_tags': name_tags,
            'geometry': geometry,
            'properties': properties
        })

    def _is_within_bbox(self, lat, lon):
        min_lat, min_lon, max_lat, max_lon = self.target_bbox
        return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


class DataLoader:
    def __init__(self, db_connection):
        self.db = db_connection
        self.valid_db_entity_types = self.db.get_valid_entity_types() 
        
    def load_osm_data_to_db(self, pbf_filepath: Path, query_date: str, source_authority: str):
        logger.info(f"📊 Loading OSM data from {pbf_filepath}")
        logger.info(f"   File size: {pbf_filepath.stat().st_size / (1024*1024):.1f} MB")
        
        bbox_parts = MARIUPOL_BBOX.split(',')
        target_bbox = [float(p) for p in bbox_parts] # [min_lat, min_lon, max_lat, max_lon]

        handler = OSMDataLoader(target_bbox)
        try:
            logger.info(f"Applying OSM handler to PBF file {pbf_filepath}...")
            handler.apply_file(str(pbf_filepath), locations=True, idx='sparse_mem_array')
            logger.info(f"Finished applying handler. Extracted {len(handler.features)} features.")
        except Exception as e:
            logger.error(f"❌ Error applying Osmium handler to PBF: {e}")
            return

        if not handler.features:
            logger.warning("⚠️ No features extracted from PBF data within the specified bounding box.")
            return

        gdf = gpd.GeoDataFrame(handler.features, crs="EPSG:4326")
        
        # Ensure geometries are valid for PostGIS
        gdf['geometry'] = gdf['geometry'].buffer(0)
        gdf = gdf[gdf['geometry'].is_valid] # Filter out any remaining invalid geometries
        
        logger.info(f"Processed {len(gdf)} valid geospatial features from PBF after cleaning for DB load.")

        inserted_count = 0
        logger.info(f"Starting import of {len(gdf)} features into the database...")
        for index, row in tqdm(gdf.iterrows(), total=len(gdf), desc="DB Loading"): # Add progress bar
            try:
                mapped_entity_type = 'unknown' 

                # Map OSM tags to your database entity types
                if row['osm_type'] == 'way':
                    if 'highway' in row['properties']: mapped_entity_type = 'street'
                    elif 'waterway' in row['properties']: mapped_entity_type = 'waterway'
                    elif 'footway' in row['properties'] or 'path' in row['properties']: mapped_entity_type = 'path'
                elif row['osm_type'] == 'relation':
                    if 'admin_level' in row['properties'] and row['properties']['admin_level'] in ['8', '9', '10']: mapped_entity_type = 'district'
                    elif 'boundary' in row['properties'] and row['properties']['boundary'] == 'administrative': mapped_entity_type = 'region'
                    elif row['properties'].get('type') == 'multipolygon':
                        if 'landuse' in row['properties'] and row['properties']['landuse'] == 'park': mapped_entity_type = 'park'
                        elif 'building' in row['properties'] or 'amenity' in row['properties']: mapped_entity_type = 'building'
                        else: mapped_entity_type = 'area'
                elif row['osm_type'] == 'node':
                    if 'place' in row['properties'] and row['properties']['place'] == 'city': mapped_entity_type = 'city'
                    elif 'building' in row['properties']: mapped_entity_type = 'building'
                    elif 'amenity' in row['properties'] or 'shop' in row['properties'] or 'leisure' in row['properties']: mapped_entity_type = 'point_of_interest'
                    elif 'place' in row['properties'] and row['properties']['place'] in ['town', 'village', 'hamlet', 'suburb', 'borough', 'neighbourhood']: mapped_entity_type = 'district'

                if mapped_entity_type == 'unknown':
                    if row['geometry'].geom_type == 'Point':
                        mapped_entity_type = 'point_of_interest'
                    elif row['geometry'].geom_type == 'LineString' or row['geometry'].geom_type == 'MultiLineString':
                        mapped_entity_type = 'path'
                    elif row['geometry'].geom_type == 'Polygon' or row['geometry'].geom_type == 'MultiPolygon':
                        mapped_entity_type = 'area'

                if mapped_entity_type not in self.valid_db_entity_types:
                    logger.warning(f"Calculated entity type '{mapped_entity_type}' for OSM ID {row['osm_id']} is not in current `entity_types` table. Defaulting to 'point_of_interest'. Please extend `entity_types` if this is a common type.")
                    mapped_entity_type = 'point_of_interest'

                entity_id = self.db.insert_entity(
                    entity_type=mapped_entity_type,
                    geometry_wkt=row['geometry'].wkt,
                    source_authority=source_authority,
                    valid_start=query_date 
                )

                for name_tag, name_value in row['name_tags'].items():
                    if not name_value or not name_value.strip(): continue

                    language_code = 'und'
                    script_code = 'Latn'

                    if name_tag == 'name':
                        if any(c in name_value for c in 'іїєґІЇЄҐ'): language_code = 'ukr'
                        elif any(c in name_value for c in 'ыЭЫ'): language_code = 'rus'
                        else: language_code = 'ukr'
                        script_code = 'Cyrl'
                    elif name_tag == 'name:uk': language_code = 'ukr'; script_code = 'Cyrl'
                    elif name_tag == 'name:ru': language_code = 'rus'; script_code = 'Cyrl'
                    elif name_tag == 'name:en': language_code = 'eng'; script_code = 'Latn'

                    sql_name = """
                    INSERT INTO toponyms.names 
                    (entity_id, name_text, normalized_name, language_code, script_code, name_type, valid_start,
                     decree_authority, source_type, source_reliability, notes)
                    VALUES (
                        %(entity_id)s, %(name_text)s, toponyms.normalize_name(%(name_text)s),
                        %(language_code)s, %(script_code)s, %(name_type)s, %(valid_start)s::timestamptz,
                        %(decree_authority)s, %(source_type)s, %(source_reliability)s, %(notes)s
                    )
                    ON CONFLICT (entity_id, language_code, name_type, tstzrange(valid_start, valid_end)) WHERE txn_end IS NULL DO NOTHING;
                    """

                    with self.db.get_connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute(sql_name, {
                                'entity_id': entity_id,
                                'name_text': name_value,
                                'language_code': language_code,
                                'script_code': script_code,
                                'name_type': 'official',
                                'valid_start': query_date,
                                'decree_authority': source_authority,
                                'source_type': 'osm_data',
                                'source_reliability': 'high',
                                'notes': f"Imported from OpenStreetMap (OSM ID: {row['osm_id']}, Type: {row['osm_type']}, Name Tag: {name_tag})"
                            })
                    inserted_count += 1

            except Exception as e:
                import traceback
                logger.error(f"❌ Error importing OSM ID {row.get('osm_id', 'N/A')} (Name: {row['name_tags'].get('name', 'N/A')}, Type: {row.get('osm_type', 'N/A')}): {e}\n{traceback.format_exc()}")
            
        logger.info(f"✅ Completed import. Successfully inserted {inserted_count} records.")


@click.command()
@click.option('--load', 
              type=click.Path(exists=True, dir_okay=False, readable=True),
              help='Path to the OpenStreetMap PBF file to load into the database (e.g., data/analysis/osm/mariupol-pre-invasion.osm.pbf).')
@click.option('--query-date', 
              default="2022-02-23", # Default to pre-invasion date for valid_start
              help='Date to assign as valid_start for imported data (YYYY-MM-DD).')
def main(load: str, query_date: str):
    """
    Orchestrates the loading of extracted OpenStreetMap data into the database.
    """
    full_query_date = f"{query_date}T00:00:00Z"

    if load:
        data_loader = DataLoader(db)
        try:
            data_loader.load_osm_data_to_db(Path(load), full_query_date, "OpenStreetMap - Geofabrik Pre-Invasion Extract")
            logger.info("Database loading process completed.")
        except Exception as e:
            logger.error(f"❌ Error loading OSM data into database: {e}")
            import traceback
            logger.error(f"{traceback.format_exc()}")
    else:
        logger.error("❌ No load path provided. Use --load to specify a PBF file for database loading.")

if __name__ == "__main__":
    main()

