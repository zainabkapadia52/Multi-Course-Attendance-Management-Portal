"""
Update existing shard table schemas to add AUTO_INCREMENT and indexes.
Run this after create_shards.py to fix the table schemas.
"""

import mysql.connector
import sys

SHARD_CONFIGS = [
    {
        "shard_id": 0,
        "host": "10.0.116.184",
        "port": 3307,
        "database": "Scalix",
        "user": "Scalix",
        "password": "password@123",
        "min_id": 12,
        "max_id": 30,
    },
    {
        "shard_id": 1,
        "host": "10.0.116.184",
        "port": 3308,
        "database": "Scalix",
        "user": "Scalix",
        "password": "password@123",
        "min_id": 31,
        "max_id": 50,
    },
    {
        "shard_id": 2,
        "host": "10.0.116.184",
        "port": 3309,
        "database": "Scalix",
        "user": "Scalix",
        "password": "password@123",
        "min_id": 51,
        "max_id": 71,
    },
]

def update_shard_schema(config):
    """
    Update shard table schema:
    1. Add AUTO_INCREMENT to record_id
    2. Add indexes on key columns
    3. Preserve existing data
    """
    shard_id = config["shard_id"]
    table_name = f"shard_{shard_id}_attendance_records"
    
    try:
        print(f"\n  ⧖ Updating Shard {shard_id} schema...")
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
        if not cursor.fetchone():
            print(f"    ✗ Table {table_name} does not exist")
            cursor.close()
            conn.close()
            return False
        
        # Drop existing indexes (except PRIMARY KEY)
        cursor.execute(f"SHOW INDEX FROM {table_name} WHERE Key_name != 'PRIMARY'")
        indexes = cursor.fetchall()
        for index_row in indexes:
            index_name = index_row[2]
            try:
                cursor.execute(f"ALTER TABLE {table_name} DROP INDEX {index_name}")
                print(f"    - Dropped index: {index_name}")
            except Exception as e:
                print(f"    - Index {index_name} already dropped or error: {str(e)}")
        
        # Modify record_id to add AUTO_INCREMENT
        try:
            cursor.execute(
                f"ALTER TABLE {table_name} MODIFY record_id INT AUTO_INCREMENT PRIMARY KEY"
            )
            print(f"    + Modified record_id to AUTO_INCREMENT PRIMARY KEY")
        except Exception as e:
            print(f"    - AUTO_INCREMENT modification failed (may already exist): {str(e)}")
        
        # Add new indexes for performance
        indexes_to_create = [
            (f"idx_{shard_id}_att_session", f"(att_session_id)"),
            (f"idx_{shard_id}_student_id", f"(student_id)"),
            (f"idx_{shard_id}_session_student", f"(att_session_id, student_id)"),
        ]
        
        for index_name, columns in indexes_to_create:
            try:
                cursor.execute(f"ALTER TABLE {table_name} ADD INDEX {index_name} {columns}")
                print(f"    + Created index: {index_name} {columns}")
            except Exception as e:
                if "Duplicate" in str(e):
                    print(f"    - Index {index_name} already exists")
                else:
                    print(f"    - Error creating index {index_name}: {str(e)}")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"    ✓ Shard {shard_id} schema updated successfully")
        return True
        
    except mysql.connector.Error as e:
        print(f"    ✗ MySQL Error for Shard {shard_id}: {str(e)}")
        return False
    except Exception as e:
        print(f"    ✗ Unexpected error for Shard {shard_id}: {str(e)}")
        return False

def main():
    print("=" * 60)
    print("  UPDATING SHARD TABLE SCHEMAS")
    print("=" * 60)
    print("\n  This script updates existing shard tables to:")
    print("    • Add AUTO_INCREMENT to record_id")
    print("    • Add performance indexes")
    print("    • Preserve all existing data")
    print()
    
    success_count = 0
    for config in SHARD_CONFIGS:
        if update_shard_schema(config):
            success_count += 1
    
    print()
    print("=" * 60)
    print(f"  ✓ Updated {success_count}/{len(SHARD_CONFIGS)} shards")
    print("=" * 60)

if __name__ == "__main__":
    main()
