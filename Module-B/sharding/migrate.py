"""
=============================================================
  CS 432 - Assignment 4: Sharding
  SubTask 2: Migrate Data from SQLite to MySQL Shards
=============================================================
  Strategy  : Range-Based Partitioning
  Shard Key : student_id
  Source    : module_b.db (SQLite)
  Targets   : shard_db_0, shard_db_1, shard_db_2 (MySQL)

  Routing Logic:
    student_id 12 – 31  →  shard_db_0  (port 3307)
    student_id 32 – 51  →  shard_db_1  (port 3308)
    student_id 52 – 71  →  shard_db_2  (port 3309)
=============================================================
"""

import sqlite3
import mysql.connector
import sys
import os

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
SQLITE_DB_PATH = "../module_b.db"

# Range boundaries for each shard
SHARD_RANGES = {
    0: (12, 31),
    1: (32, 51),
    2: (52, 71),
}

SHARD_CONFIGS = {
    0: {"host": "localhost", "port": 3307,
        "database": "shard_db_0", "user": "root", "password": "shardpass"},
    1: {"host": "localhost", "port": 3308,
        "database": "shard_db_1", "user": "root", "password": "shardpass"},
    2: {"host": "localhost", "port": 3309,
        "database": "shard_db_2", "user": "root", "password": "shardpass"},
}

def print_header():
    print()
    print("=" * 60)
    print("  STEP 2: MIGRATING DATA FROM SQLITE TO MYSQL SHARDS")
    print("=" * 60)
    print()
    print(f"  Source    : {SQLITE_DB_PATH} (SQLite)")
    print(f"  Targets   : shard_db_0 (port 3307)")
    print(f"              shard_db_1 (port 3308)")
    print(f"              shard_db_2 (port 3309)")
    print()
    print("  Routing Logic (Range-Based):")
    print("    student_id  12 – 31  →  shard_db_0")
    print("    student_id  32 – 51  →  shard_db_1")
    print("    student_id  52 – 71  →  shard_db_2")
    print()

def get_shard_id(student_id):
    """
    Route a student_id to the correct shard based on range boundaries.
    Raises ValueError if student_id falls outside all defined ranges.
    """
    for shard_id, (min_id, max_id) in SHARD_RANGES.items():
        if min_id <= student_id <= max_id:
            return shard_id
    raise ValueError(
        f"student_id {student_id} is outside all defined shard ranges! "
        f"Ranges are: {SHARD_RANGES}"
    )

def read_from_sqlite():
    """Read all attendance_records from original SQLite database."""
    if not os.path.exists(SQLITE_DB_PATH):
        print(f"  ✗ SQLite database not found at: {SQLITE_DB_PATH}")
        print(f"    Make sure you are running this from the sharding/ folder.")
        sys.exit(1)

    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT record_id, att_session_id, student_id, status "
        "FROM attendance_records"
    )
    rows = cursor.fetchall()
    conn.close()
    return rows

def connect_to_shards():
    """Open connections to all 3 MySQL shards."""
    connections = {}
    cursors = {}
    for shard_id, config in SHARD_CONFIGS.items():
        try:
            conn = mysql.connector.connect(**config)
            connections[shard_id] = conn
            cursors[shard_id] = conn.cursor()
            print(f"  ✓ Connected to shard_{shard_id} "
                  f"(shard_db_{shard_id}, port {config['port']})")
        except Exception as e:
            print(f"  ✗ Failed to connect to shard_{shard_id}: {e}")
            sys.exit(1)
    return connections, cursors

def migrate(rows, connections, cursors):
    """Route and insert each row into the correct shard by range."""
    counts      = {0: 0, 1: 0, 2: 0}
    skipped     = []

    for row in rows:
        student_id = row["student_id"]
        try:
            shard_id = get_shard_id(student_id)
        except ValueError as e:
            skipped.append((row["record_id"], student_id, str(e)))
            continue

        table = f"shard_{shard_id}_attendance_records"
        cursors[shard_id].execute(
            f"INSERT INTO {table} "
            f"(record_id, att_session_id, student_id, status) "
            f"VALUES (%s, %s, %s, %s)",
            (row["record_id"], row["att_session_id"],
             row["student_id"], row["status"])
        )
        counts[shard_id] += 1

    # Commit all shards
    for shard_id, conn in connections.items():
        conn.commit()

    return counts, skipped

def print_summary(original_count, counts, skipped):
    """Print migration summary."""
    total_migrated = sum(counts.values())

    print()
    print("─" * 60)
    print("  MIGRATION SUMMARY")
    print("─" * 60)
    print()
    print(f"  {'Source':<35} {'Rows':>8}")
    print(f"  {'─'*35} {'─'*8}")
    print(f"  {'Original (module_b.db)':<35} {original_count:>8}")
    print()
    print(f"  {'Shard':<35} {'Inserted':>8}  {'Range'}")
    print(f"  {'─'*35} {'─'*8}  {'─'*16}")
    for shard_id, count in counts.items():
        min_id, max_id = SHARD_RANGES[shard_id]
        pct = (count / original_count * 100) if original_count > 0 else 0
        print(f"  {'shard_db_' + str(shard_id) + ' (port ' + str(SHARD_CONFIGS[shard_id]['port']) + ')':<35} "
              f"{count:>8}  student_id {min_id}–{max_id}  ({pct:.1f}%)")
    print(f"  {'─'*35} {'─'*8}")
    print(f"  {'TOTAL MIGRATED':<35} {total_migrated:>8}")
    print()

    if skipped:
        print(f"  ⚠ {len(skipped)} rows skipped (student_id out of range):")
        for record_id, student_id, reason in skipped:
            print(f"    record_id={record_id}, student_id={student_id}")
        print()

    if original_count == total_migrated:
        print("  ✓ All records migrated successfully. No data loss.")
    else:
        diff = original_count - total_migrated
        print(f"  ⚠ {diff} records not migrated "
              f"({'skipped due to out-of-range student_id' if skipped else 'data loss'}).")

    print()

    # Distribution analysis
    if total_migrated > 0:
        max_count = max(counts.values())
        min_count = min(counts.values())
        skew = max_count - min_count
        print(f"  Distribution Analysis:")
        print(f"    Max shard size : {max_count} rows")
        print(f"    Min shard size : {min_count} rows")
        print(f"    Skew (max-min) : {skew} rows")
        if skew <= total_migrated * 0.1:
            print(f"    Assessment     : Even distribution ✓")
        else:
            print(f"    Assessment     : Uneven distribution ⚠ "
                  f"(expected with range-based sharding if IDs are not uniform)")
    print()

def main():
    print_header()

    # Step 1: Read from SQLite
    print("─" * 60)
    print("  Reading from source database (module_b.db)...")
    print("─" * 60)
    rows = read_from_sqlite()
    original_count = len(rows)

    # Show student_id range found in source
    student_ids = [row["student_id"] for row in rows]
    print(f"  ✓ {original_count} records read from attendance_records")
    print(f"    student_id range in source: "
          f"{min(student_ids)} to {max(student_ids)}")
    print()

    # Step 2: Connect to shards
    print("─" * 60)
    print("  Connecting to MySQL shard containers...")
    print("─" * 60)
    connections, cursors = connect_to_shards()
    print()

    # Step 3: Migrate
    print("─" * 60)
    print(f"  Migrating {original_count} records using range-based routing...")
    print("─" * 60)
    counts, skipped = migrate(rows, connections, cursors)
    print(f"  ✓ Migration complete.")

    # Close connections
    for conn in connections.values():
        conn.close()

    # Summary
    print_summary(original_count, counts, skipped)

    print("─" * 60)
    print("  Next step: Run verify.py to confirm data integrity.")
    print("─" * 60)
    print()

if __name__ == "__main__":
    main()