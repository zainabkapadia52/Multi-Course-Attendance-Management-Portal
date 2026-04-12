import sqlite3
import mysql.connector

# Connect to original SQLite database
sqlite_conn = sqlite3.connect("../module_b.db")
sqlite_conn.row_factory = sqlite3.Row  # lets us access columns by name
cursor = sqlite_conn.cursor()

# Fetch all rows from original attendance_records
cursor.execute("SELECT record_id, att_session_id, student_id, status FROM attendance_records")
all_rows = cursor.fetchall()
print(f"Total rows in original: {len(all_rows)}")

# Connect to each MySQL shard
shards = {
    0: mysql.connector.connect(
        host="localhost", port=3307, database="shard_db_0",
        user="root", password="shardpass"
    ),
    1: mysql.connector.connect(
        host="localhost", port=3308, database="shard_db_1",
        user="root", password="shardpass"
    ),
    2: mysql.connector.connect(
        host="localhost", port=3309, database="shard_db_2",
        user="root", password="shardpass"
    ),
}

shard_cursors = {i: shards[i].cursor() for i in shards}
counts = {0: 0, 1: 0, 2: 0}

insert_sql = """
    INSERT INTO attendance_records 
        (record_id, att_session_id, student_id, status)
    VALUES (%s, %s, %s, %s)
"""

# Route each row to correct shard
for row in all_rows:
    student_id = row["student_id"]
    shard_id = student_id % 3
    shard_cursors[shard_id].execute(insert_sql, (
        row["record_id"],
        row["att_session_id"],
        row["student_id"],
        row["status"]
    ))
    counts[shard_id] += 1

# Commit all shards
for i in shards:
    shards[i].commit()
    shard_cursors[i].close()
    shards[i].close()

sqlite_conn.close()

print(f"\nMigration complete:")
print(f"  shard_0 (student_id % 3 = 0): {counts[0]} rows")
print(f"  shard_1 (student_id % 3 = 1): {counts[1]} rows")
print(f"  shard_2 (student_id % 3 = 2): {counts[2]} rows")
print(f"  Total migrated: {sum(counts.values())}")