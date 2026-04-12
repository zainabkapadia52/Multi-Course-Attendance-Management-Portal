import mysql.connector
import time

# Give MySQL containers time to be ready
time.sleep(5)

shard_configs = [
    {"host": "localhost", "port": 3307, "database": "shard_db_0", 
     "user": "root", "password": "shardpass", "shard_id": 0},
    {"host": "localhost", "port": 3308, "database": "shard_db_1", 
     "user": "root", "password": "shardpass", "shard_id": 1},
    {"host": "localhost", "port": 3309, "database": "shard_db_2", 
     "user": "root", "password": "shardpass", "shard_id": 2},
]

create_table_sql = """
CREATE TABLE IF NOT EXISTS attendance_records (
    record_id      INT PRIMARY KEY,
    att_session_id INT NOT NULL,
    student_id     INT NOT NULL,
    status         VARCHAR(10) NOT NULL,
    CONSTRAINT chk_shard_{shard_id} 
        CHECK (student_id % 3 = {shard_id})
)
"""

for config in shard_configs:
    shard_id = config.pop("shard_id")
    try:
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor()
        cursor.execute(
            create_table_sql.format(shard_id=shard_id)
        )
        conn.commit()
        print(f"✓ shard_{shard_id} table created in shard_db_{shard_id}")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"✗ shard_{shard_id} failed: {e}")