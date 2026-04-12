import sqlite3
import mysql.connector

# Original count from SQLite
sqlite_conn = sqlite3.connect("../module_b.db")
original_count = sqlite_conn.execute(
    "SELECT COUNT(*) FROM attendance_records"
).fetchone()[0]
sqlite_conn.close()

# Shard connections
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

print("=" * 50)
print("VERIFICATION REPORT")
print("=" * 50)

# 1. Row counts
print(f"\n1. ORIGINAL ROW COUNT: {original_count}")
total_sharded = 0
for i, conn in shards.items():
    count = conn.cursor()
    count.execute("SELECT COUNT(*) FROM attendance_records")
    n = count.fetchone()[0]
    total_sharded += n
    print(f"   shard_{i}: {n} rows")

print(f"   TOTAL SHARDED: {total_sharded}")
if original_count == total_sharded:
    print("   ✓ No data loss — counts match")
else:
    print("   ✗ DATA LOSS DETECTED")

# 2. Check no wrong students in each shard
print("\n2. SHARD ISOLATION CHECK:")
for i, conn in shards.items():
    cur = conn.cursor()
    cur.execute(
        f"SELECT COUNT(*) FROM attendance_records WHERE student_id % 3 != {i}"
    )
    wrong = cur.fetchone()[0]
    if wrong == 0:
        print(f"   ✓ shard_{i} contains only correct students")
    else:
        print(f"   ✗ shard_{i} has {wrong} rows that don't belong")

# 3. Check no duplicates across shards
print("\n3. DUPLICATE CHECK:")
all_ids = []
for i, conn in shards.items():
    cur = conn.cursor()
    cur.execute("SELECT record_id FROM attendance_records")
    all_ids.extend([row[0] for row in cur.fetchall()])

duplicates = len(all_ids) - len(set(all_ids))
if duplicates == 0:
    print("   ✓ No duplicate record_ids across shards")
else:
    print(f"   ✗ {duplicates} duplicate record_ids found")

# 4. Test CHECK constraint — insert wrong student into shard_0
print("\n4. CONSTRAINT ENFORCEMENT CHECK:")
try:
    cur = shards[0].cursor()
    # student_id=1 belongs to shard_1 (1%3=1), not shard_0
    cur.execute("""
        INSERT INTO attendance_records VALUES (99999, 1, 1, 'present')
    """)
    shards[0].commit()
    print("   ✗ Wrong insert succeeded — constraint not working")
except Exception as e:
    print(f"   ✓ Wrong shard correctly rejected the insert")

for conn in shards.values():
    conn.close()

print("\n" + "=" * 50)
