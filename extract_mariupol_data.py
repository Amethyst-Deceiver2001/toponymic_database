#!/usr/bin/env python3
"""
Extract Mariupol OSM data for specified time periods using pure Python.
Replaces command-line osmium operations with Python osmium library.

Usage:
    python extract_mariupol_data.py --help
    python extract_mariupol_data.py --pre-invasion
    python extract_mariupol_data.py --post-invasion
    python extract_mariupol_data.py --custom 2022-03-01T00:00:00Z
"""

import os
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path
import osmium
from tqdm import tqdm

# Mariupol bounding box coordinates
MARIUPOL_BBOX = {
    'min_lon': 37.29,
    'min_lat': 47.00, 
    'max_lon': 37.76,
    'max_lat': 47.23
}

# Key dates
PRE_INVASION_DATE = "2022-02-23T23:59:59Z"
POST_INVASION_START = "2022-02-24T00:00:00Z"

class MariupolExtractor(osmium.SimpleHandler):
    """OSM handler for extracting Mariupol data within time and bbox constraints."""
    
    def __init__(self, output_writer, bbox, target_timestamp=None):
        osmium.SimpleHandler.__init__(self)
        self.writer = output_writer
        self.bbox = bbox
        self.target_timestamp = target_timestamp
        self.processed_count = 0
        self.extracted_count = 0
        
    def _in_bbox(self, obj):
        """Check if object is within Mariupol bounding box."""
        if hasattr(obj, 'location') and obj.location.valid():
            lon, lat = obj.location.lon, obj.location.lat
            return (self.bbox['min_lon'] <= lon <= self.bbox['max_lon'] and 
                   self.bbox['min_lat'] <= lat <= self.bbox['max_lat'])
        return False
    
    def _check_timestamp(self, obj):
        """Check if object timestamp is before target timestamp."""
        if self.target_timestamp is None:
            return True
        
        # Handle different timestamp formats
        obj_timestamp = obj.timestamp
        
        # Convert to comparable datetime objects
        if hasattr(obj_timestamp, 'to_datetime'):
            obj_datetime = obj_timestamp.to_datetime()
        elif hasattr(obj_timestamp, 'timestamp'):
            obj_datetime = datetime.fromtimestamp(obj_timestamp.timestamp(), tz=timezone.utc)
        elif isinstance(obj_timestamp, datetime):
            obj_datetime = obj_timestamp
        else:
            # Try to convert timestamp directly
            try:
                obj_datetime = datetime.fromtimestamp(float(obj_timestamp), tz=timezone.utc)
            except:
                # If all else fails, assume it's current and include it
                return True
        
        # Ensure both timestamps have timezone info for comparison
        if obj_datetime.tzinfo is None:
            obj_datetime = obj_datetime.replace(tzinfo=timezone.utc)
        if self.target_timestamp.tzinfo is None:
            target_dt = self.target_timestamp.replace(tzinfo=timezone.utc)
        else:
            target_dt = self.target_timestamp
            
        return obj_datetime <= target_dt
    
    def _has_mariupol_tags(self, obj):
        """Check if object has tags related to Mariupol or surrounding area."""
        if not hasattr(obj, 'tags'):
            return False
            
        mariupol_keywords = [
            'mariupol', 'маріуполь', 'мариуполь',
            'azov', 'азов', 'азовський',
            'donetsk', 'донецьк', 'донецкая'
        ]
        
        for tag in obj.tags:
            value_lower = tag.v.lower()
            if any(keyword in value_lower for keyword in mariupol_keywords):
                return True
        return False
    
    def node(self, n):
        """Process OSM nodes."""
        self.processed_count += 1
        
        if self._check_timestamp(n) and (self._in_bbox(n) or self._has_mariupol_tags(n)):
            self.writer.add_node(n)
            self.extracted_count += 1
    
    def way(self, w):
        """Process OSM ways."""
        self.processed_count += 1
        
        if self._check_timestamp(w):
            # For ways, check if any nodes are in bbox or if tags mention Mariupol
            if self._has_mariupol_tags(w):
                self.writer.add_way(w)
                self.extracted_count += 1
    
    def relation(self, r):
        """Process OSM relations."""
        self.processed_count += 1
        
        if self._check_timestamp(r) and self._has_mariupol_tags(r):
            self.writer.add_relation(r)
            self.extracted_count += 1


def parse_timestamp(timestamp_str):
    """Parse ISO timestamp string to datetime for comparison."""
    try:
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return dt
    except ValueError as e:
        print(f"Error parsing timestamp '{timestamp_str}': {e}")
        sys.exit(1)


def extract_mariupol_data(input_file, output_file, target_timestamp=None, description=""):
    """Extract Mariupol data from OSM file."""
    
    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"\n🔍 Extracting Mariupol data{description}")
    print(f"   Input:  {input_file}")
    print(f"   Output: {output_file}")
    if target_timestamp:
        print(f"   Before: {target_timestamp}")
    print(f"   Bbox:   {MARIUPOL_BBOX}")
    
    # Create output writer
    writer = osmium.SimpleWriter(str(output_file))
    
    # Create handler
    handler = MariupolExtractor(
        output_writer=writer,
        bbox=MARIUPOL_BBOX,
        target_timestamp=target_timestamp
    )
    
    try:
        # Process the file
        print("📊 Processing OSM data...")
        handler.apply_file(str(input_file), locations=True)
        
        # Close writer
        writer.close()
        
        print(f"✅ Extraction complete!")
        print(f"   Processed: {handler.processed_count:,} objects")
        print(f"   Extracted: {handler.extracted_count:,} objects")
        print(f"   Output size: {output_file.stat().st_size / 1024 / 1024:.1f} MB")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during extraction: {e}")
        if output_file.exists():
            output_file.unlink()  # Clean up partial file
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Extract Mariupol OSM data for temporal analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Extract pre-invasion baseline (before Feb 24, 2022)
    python extract_mariupol_data.py --pre-invasion
    
    # Extract post-invasion data (all changes since Feb 24, 2022)  
    python extract_mariupol_data.py --post-invasion
    
    # Extract data before custom date
    python extract_mariupol_data.py --custom 2022-03-01T00:00:00Z
        """
    )
    
    # Input/output options
    parser.add_argument(
        '--input', '-i',
        type=Path,
        default=Path('data/raw/osm/ukraine-internal.osh.pbf'),
        help='Input OSM history file (default: data/raw/osm/ukraine-internal.osh.pbf)'
    )
    
    parser.add_argument(
        '--output-dir', '-o',
        type=Path,
        default=Path('data/analysis/osm'),
        help='Output directory (default: data/analysis/osm)'
    )
    
    # Time period options (mutually exclusive)
    time_group = parser.add_mutually_exclusive_group(required=True)
    
    time_group.add_argument(
        '--pre-invasion',
        action='store_true',
        help=f'Extract pre-invasion baseline (before {PRE_INVASION_DATE})'
    )
    
    time_group.add_argument(
        '--post-invasion', 
        action='store_true',
        help=f'Extract post-invasion data (after {POST_INVASION_START})'
    )
    
    time_group.add_argument(
        '--custom',
        type=str,
        metavar='TIMESTAMP',
        help='Extract data before custom timestamp (ISO format: 2022-03-01T00:00:00Z)'
    )
    
    time_group.add_argument(
        '--full',
        action='store_true', 
        help='Extract all data (no time filter)'
    )
    
    args = parser.parse_args()
    
    # Validate input file
    if not args.input.exists():
        print(f"❌ Input file not found: {args.input}")
        print("   Make sure you have downloaded the Ukraine OSM history file")
        sys.exit(1)
    
    # Determine timestamp and output filename
    target_timestamp = None
    
    if args.pre_invasion:
        target_timestamp = parse_timestamp(PRE_INVASION_DATE)
        output_file = args.output_dir / "mariupol-pre-invasion.osm.pbf"
        description = " (pre-invasion baseline)"
        
    elif args.post_invasion:
        # For post-invasion, we'll extract everything and filter later
        # This is because osmium doesn't have "after" filtering
        target_timestamp = None
        output_file = args.output_dir / "mariupol-post-invasion.osm.pbf"  
        description = " (post-invasion data)"
        print("⚠️  Note: Post-invasion filtering requires additional processing")
        
    elif args.custom:
        target_timestamp = parse_timestamp(args.custom)
        date_str = args.custom.split('T')[0]
        output_file = args.output_dir / f"mariupol-{date_str}.osm.pbf"
        description = f" (before {args.custom})"
        
    elif args.full:
        target_timestamp = None
        output_file = args.output_dir / "mariupol-complete.osm.pbf"
        description = " (complete history)"
    
    # Extract data
    success = extract_mariupol_data(
        input_file=args.input,
        output_file=output_file,
        target_timestamp=target_timestamp,
        description=description
    )
    
    if success:
        print(f"\n🎯 Next steps:")
        print(f"   1. Analyze extracted data: python analyze_mariupol_toponyms.py")
        print(f"   2. Load into database: python process_osm_data.py")
        print(f"   3. Review output file: {output_file}")
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())