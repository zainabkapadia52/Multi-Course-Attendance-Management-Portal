#!/usr/bin/env python3
"""
Create indexes on shard tables for query optimization.
Indexes on att_session_id and student_id dramatically speed up cascading deletes and lookups.

Run this once after shards are created: python create_shard_indexes.py
"""

import mysql.connector
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

SHARD_CONFIGS = {
    0: {"host": "10.0.116.184", "port": 3307,
        "database": "Scalix", "user": "Scalix", "password": "password@123"},
    1: {"host": "10.0.116.184", "port": 3308,
        "database": "Scalix", "user": "Scalix", "password": "password@123"},
    2: {"host": "10.0.116.184", "port": 3309,
        "database": "Scalix", "user": "Scalix", "password": "password@123"},
}

def create_indexes_for_shard(shard_id: int):
    """Create indexes on a shard's attendance_records table."""
    config = SHARD_CONFIGS[shard_id]
    table_name = f"shard_{shard_id}_attendance_records"
    
    try:
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor()
        
        # Index 1: att_session_id (used for session-based lookups and cascading deletes)
        try:
            cursor.execute(f"CREATE INDEX idx_att_session_id ON {table_name}(att_session_id)")
            logger.info(f"✓ Shard {shard_id}: Created index on att_session_id")
        except mysql.connector.Error as e:
            if "Duplicate key name" in str(e):
                logger.info(f"  Shard {shard_id}: Index idx_att_session_id already exists")
            else:
                logger.error(f"✗ Shard {shard_id}: Failed to create idx_att_session_id: {e}")
        
        # Index 2: student_id (used for student-based lookups and cascading deletes)
        try:
            cursor.execute(f"CREATE INDEX idx_student_id ON {table_name}(student_id)")
            logger.info(f"✓ Shard {shard_id}: Created index on student_id")
        except mysql.connector.Error as e:
            if "Duplicate key name" in str(e):
                logger.info(f"  Shard {shard_id}: Index idx_student_id already exists")
            else:
                logger.error(f"✗ Shard {shard_id}: Failed to create idx_student_id: {e}")
        
        # Index 3: Composite (student_id, att_session_id) for UPDATE queries
        try:
            cursor.execute(f"CREATE INDEX idx_student_session ON {table_name}(student_id, att_session_id)")
            logger.info(f"✓ Shard {shard_id}: Created composite index on (student_id, att_session_id)")
        except mysql.connector.Error as e:
            if "Duplicate key name" in str(e):
                logger.info(f"  Shard {shard_id}: Index idx_student_session already exists")
            else:
                logger.error(f"✗ Shard {shard_id}: Failed to create idx_student_session: {e}")
        
        # Index 4: record_id (if not primary key, speeds up UPDATE by record_id)
        try:
            cursor.execute(f"SHOW INDEX FROM {table_name} WHERE Column_name='record_id'")
            indexes = cursor.fetchall()
            if not indexes or indexes[0][2] != 'PRIMARY':
                cursor.execute(f"CREATE INDEX idx_record_id ON {table_name}(record_id)")
                logger.info(f"✓ Shard {shard_id}: Created index on record_id")
            else:
                logger.info(f"  Shard {shard_id}: record_id is already indexed (PRIMARY KEY)")
        except mysql.connector.Error as e:
            logger.error(f"✗ Shard {shard_id}: Failed to create idx_record_id: {e}")
        
        conn.commit()
        cursor.close()
        conn.close()
        
    except mysql.connector.Error as e:
        logger.error(f"✗ Connection error for shard {shard_id}: {e}")
    except Exception as e:
        logger.error(f"✗ Unexpected error for shard {shard_id}: {e}")

def verify_indexes():
    """Verify that indexes were created successfully."""
    logger.info("\n📊 Verifying indexes on all shards:")
    for shard_id in SHARD_CONFIGS:
        config = SHARD_CONFIGS[shard_id]
        table_name = f"shard_{shard_id}_attendance_records"
        try:
            conn = mysql.connector.connect(**config)
            cursor = conn.cursor()
            cursor.execute(f"SHOW INDEX FROM {table_name}")
            indexes = cursor.fetchall()
            
            logger.info(f"\n  Shard {shard_id} ({table_name}):")
            index_names = set()
            for idx in indexes:
                index_name = idx[2]
                if index_name not in index_names:
                    index_names.add(index_name)
                    columns = [i[4] for i in indexes if i[2] == index_name]
                    logger.info(f"    - {index_name}: {columns}")
            
            cursor.close()
            conn.close()
        except Exception as e:
            logger.error(f"  ✗ Shard {shard_id}: Could not verify indexes: {e}")

if __name__ == "__main__":
    logger.info("🔧 Creating indexes on shard tables for performance optimization...\n")
    
    for shard_id in SHARD_CONFIGS:
        logger.info(f"Processing Shard {shard_id}...")
        create_indexes_for_shard(shard_id)
    
    verify_indexes()
    
    logger.info("\n✅ Index creation complete!")
    logger.info("Expected performance improvements:")
    logger.info("  - Cascading deletes: 60+ sequential queries → 3 parallel batch queries")
    logger.info("  - Session lookups: Full table scans → Index seeks")
    logger.info("  - Student lookups: Full table scans → Index seeks")
