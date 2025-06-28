#!/usr/bin/env python3
# scripts/test_setup.py
"""
Test script to verify our database setup
Run this after starting Docker to ensure everything works
"""

import sys
from pathlib import Path

# Add project root to Python path
sys.path.append(str(Path(__file__).parent.parent))

from scripts.utils.database import db
from scripts.utils.config import setup_logging, SQL_DIR

logger = setup_logging(__name__)

def main():
    """Run all setup tests"""
    print("🔍 Testing Mariupol Toponyms Database Setup\n")
    
    # Test 1: Database connection
    print("1. Testing database connection...")
    if not db.test_connection():
        print("❌ Database connection failed!")
        print("   Make sure Docker is running: make up")
        return False
    print("✅ Database connected successfully!\n")
    
    # Test 2: Create extensions
    print("2. Setting up PostgreSQL extensions...")
    try:
        db.execute_sql_file(SQL_DIR / 'setup' / '01_extensions.sql')
        print("✅ Extensions created!\n")
    except Exception as e:
        print(f"❌ Extension setup failed: {e}\n")
        return False
    
    # Test 3: Create schemas
    print("3. Creating database schemas...")
    try:
        db.execute_sql_file(SQL_DIR / 'setup' / '02_schemas.sql')
        print("✅ Schemas created!\n")
    except Exception as e:
        print(f"❌ Schema creation failed: {e}\n")
        return False
    
    # Test 4: Create tables
    print("4. Creating database tables...")
    table_files = [
        '01_entity_types.sql',
        '02_toponymic_entities.sql',
        '03_toponymic_names.sql'
    ]
    
    for table_file in table_files:
        try:
            filepath = SQL_DIR / 'tables' / table_file
            if filepath.exists():
                db.execute_sql_file(filepath)
                print(f"   ✅ Created tables from {table_file}")
            else:
                print(f"   ⚠️  File not found: {table_file}")
        except Exception as e:
            print(f"   ❌ Failed on {table_file}: {e}")
            return False
    
    print("\n🎉 All tests passed! Your database is ready to use.")
    print("\nNext steps:")
    print("1. You can connect to the database with: make psql")
    print("2. Start adding toponymic data!")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)