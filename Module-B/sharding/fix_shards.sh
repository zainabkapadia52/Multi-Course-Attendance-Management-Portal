#!/bin/bash

# ============================================================================
# Fix Shard Table Schemas - Run this from Module-B directory
# ============================================================================

echo "================================"
echo "  Fixing Shard Table Schemas"
echo "================================"

# Configuration
HOST="10.0.116.184"
USER="Scalix"
PASSWORD="password@123"

SHARDS=(
    "3307:shard_0"
    "3308:shard_1"
    "3309:shard_2"
)

for SHARD_INFO in "${SHARDS[@]}"; do
    PORT="${SHARD_INFO%%:*}"
    SHARD_NAME="${SHARD_INFO##*:}"
    
    echo ""
    echo "⧖ Fixing $SHARD_NAME (port $PORT)..."
    
    # Create temporary SQL script for this shard
    SQL_FILE="/tmp/fix_${PORT}.sql"
    cat > "$SQL_FILE" << EOSQL
USE Scalix;

DROP TABLE IF EXISTS shard_${PORT}_attendance_records;

CREATE TABLE shard_${PORT}_attendance_records (
    record_id       INT          PRIMARY KEY AUTO_INCREMENT,
    att_session_id  INT          NOT NULL,
    student_id      INT          NOT NULL,
    status          VARCHAR(10)  NOT NULL,
    INDEX idx_att_session (att_session_id),
    INDEX idx_student_id (student_id),
    INDEX idx_session_student (att_session_id, student_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

EOSQL
    
    # Note: This would require mysql CLI to be installed and accessible
    # For now, we'll show the user what to run
    echo "  To fix this shard, run:"
    echo "    mysql -h $HOST -P $PORT -u $USER -p$PASSWORD < $SQL_FILE"
    echo ""
done

echo "✓ SQL scripts prepared in /tmp/"
echo ""
echo "Next steps:"
echo "1. Delete the local database:   rm module_b.db"
echo "2. Re-run init_db:              python init_db.py" 
echo "3. Test course deletion again"
