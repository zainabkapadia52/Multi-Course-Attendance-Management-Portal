"""
=============================================================
  CS 432 - Assignment 4: Sharding
  SubTask 2: Migrate Data from SQLite to MySQL Shards
=============================================================
  Strategy  : Hash-Based Partitioning
  Shard Key : student_id
  Method    : student_id % 3
  Source    : module_b.db (SQLite)
  Targets   : shard_db_0, shard_db_1, shard_db_2 (MySQL)

  Routing Logic:
    student_id % 3 == 0  →  shard_db_0  (port 3307)
    student_id % 3 == 1  →  shard_db_1  (port 3308)
    student_id % 3 == 2  →  shard_db_2  (port 3309)
=============================================================
"""

import sqlite3
import mysql.connector
import sys
import os
import argparse
import time

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
SQLITE_DB_PATH = "../module_b.db"

# Number of shards
NUMBER_OF_SHARDS = 3

SHARD_CONFIGS = {
    0: {"host": "10.0.116.184", "port": 3307,
        "database": "Scalix", "user": "Scalix", "password": "password@123"},
    1: {"host": "10.0.116.184", "port": 3308,
        "database": "Scalix", "user": "Scalix", "password": "password@123"},
    2: {"host": "10.0.116.184", "port": 3309,
        "database": "Scalix", "user": "Scalix", "password": "password@123"},
}

# Default to small test runs so connectivity and routing can be validated quickly.
# Set to 0 (or pass --max-per-shard 0) for no per-shard cap.
DEFAULT_MAX_PER_SHARD = 100000
MYSQL_CONNECT_TIMEOUT_SECONDS = 5

def print_header():
    print()
    print("=" * 60)
    print("  STEP 2: MIGRATING DATA FROM SQLITE TO MYSQL SHARDS")
    print("=" * 60)
    print()
    print(f"  Source    : {SQLITE_DB_PATH} (SQLite)")
    print(f"  Targets   : 10.0.116.184:3307 -> Scalix")
    print(f"              10.0.116.184:3308 -> Scalix")
    print(f"              10.0.116.184:3309 -> Scalix")
    print()
    print("  Routing Logic (Hash-Based):")
    print("    student_id % 3 == 0  →  shard_db_0")
    print("    student_id % 3 == 1  →  shard_db_1")
    print("    student_id % 3 == 2  →  shard_db_2")
    print()

def get_shard_id(student_id):
    """
    Route a student_id to the correct shard based on hash partitioning.
    Shard ID = student_id % 3
    """
    return student_id % NUMBER_OF_SHARDS

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
            start = time.perf_counter()
            conn = mysql.connector.connect(
                **config,
                connection_timeout=MYSQL_CONNECT_TIMEOUT_SECONDS,
            )
            connections[shard_id] = conn
            cursors[shard_id] = conn.cursor()
            elapsed = (time.perf_counter() - start) * 1000
            print(f"  ✓ Connected to shard_{shard_id} "
                  f"({config['host']}:{config['port']}, db={config['database']}, {elapsed:.0f} ms)")
        except Exception as e:
            print(f"  ✗ Failed to connect to shard_{shard_id}: {e}")
            sys.exit(1)
    return connections, cursors

def clear_shard_tables(connections):
    """Clear all existing data from shard tables before migration."""
    print()
    print("─" * 60)
    print("  Clearing existing data from shard tables...")
    print("─" * 60)
    for shard_id, conn in connections.items():
        cursor = conn.cursor()
        table_name = f"shard_{shard_id}_attendance_records"
        try:
            cursor.execute(f"DELETE FROM {table_name}")
            conn.commit()
            print(f"  ✓ Cleared {table_name}")
        except Exception as e:
            print(f"  ⚠ Could not clear {table_name}: {e}")
        cursor.close()
    print()

def migrate(rows, connections, cursors, max_per_shard=DEFAULT_MAX_PER_SHARD):
    """Route and insert each row into the correct shard by hash function."""
    counts      = {0: 0, 1: 0, 2: 0}
    skipped     = []
    throttled   = 0
    buffered_rows = {0: [], 1: [], 2: []}

    max_per_shard = int(max_per_shard)
    if max_per_shard < 0:
        raise ValueError("max_per_shard cannot be negative")

    for row in rows:
        student_id = row["student_id"]
        shard_id = get_shard_id(student_id)

        if max_per_shard and counts[shard_id] >= max_per_shard:
            throttled += 1
            continue

        buffered_rows[shard_id].append(
            (row["record_id"], row["att_session_id"], row["student_id"], row["status"])
        )
        counts[shard_id] += 1

        if sum(counts.values()) % 10 == 0:
            print(f"  ... migrated {sum(counts.values())} rows so far")

    for shard_id in (0, 1, 2):
        table = f"shard_{shard_id}_attendance_records"
        if buffered_rows[shard_id]:
            cursors[shard_id].executemany(
                f"INSERT INTO {table} "
                f"(record_id, att_session_id, student_id, status) "
                f"VALUES (%s, %s, %s, %s)",
                buffered_rows[shard_id],
            )

    # Commit all shards
    for shard_id, conn in connections.items():
        conn.commit()

    return counts, skipped, throttled

def print_summary(original_count, counts, skipped, throttled, max_per_shard):
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
    print(f"  {'Shard':<35} {'Inserted':>8}  {'Hash Rule'}")
    print(f"  {'─'*35} {'─'*8}  {'─'*16}")
    for shard_id, count in counts.items():
        pct = (count / original_count * 100) if original_count > 0 else 0
        print(f"  {'shard_db_' + str(shard_id) + ' (port ' + str(SHARD_CONFIGS[shard_id]['port']) + ')':<35} "
              f"{count:>8}  student_id % 3 == {shard_id}  ({pct:.1f}%)")
    print(f"  {'─'*35} {'─'*8}")
    print(f"  {'TOTAL MIGRATED':<35} {total_migrated:>8}")
    print()

    if max_per_shard:
        print(f"  Test mode limit              : {max_per_shard} rows per shard")
        print(f"  Rows intentionally not migrated due to limit: {throttled}")
        print()

    if skipped:
        print(f"  ⚠ {len(skipped)} rows skipped:")
        for record_id, student_id, reason in skipped:
            print(f"    record_id={record_id}, student_id={student_id}")
        print()

    if max_per_shard:
        print("  ✓ Test run completed with intentional row cap.")
    elif original_count == total_migrated:
        print("  ✓ All records migrated successfully. No data loss.")
    else:
        diff = original_count - total_migrated
        print(f"  ⚠ {diff} records not migrated.")

    print()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Migrate attendance records from SQLite to range-sharded MySQL instances."
    )
    parser.add_argument(
        "--max-per-shard",
        type=int,
        default=DEFAULT_MAX_PER_SHARD,
        help=(
            "Maximum records to insert per shard for test runs. "
            "Use 0 for no cap. Default: 5"
        ),
    )
    return parser.parse_args()

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
    args = parse_args()
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

    # Step 2b: Clear existing data
    clear_shard_tables(connections)

    # Step 3: Migrate
    print("─" * 60)
    print(f"  Migrating {original_count} records using hash-based routing...")
    if args.max_per_shard:
        print(f"  Test run mode enabled: max {args.max_per_shard} rows per shard")
    else:
        print("  Full migration mode enabled: no per-shard cap")
    print("─" * 60)
    counts, skipped, throttled = migrate(
        rows,
        connections,
        cursors,
        max_per_shard=args.max_per_shard,
    )
    print(f"  ✓ Migration complete.")

    # Close connections
    for conn in connections.values():
        conn.close()

    # Summary
    print_summary(
        original_count,
        counts,
        skipped,
        throttled,
        args.max_per_shard,
    )

    print("─" * 60)
    print("  Next step: Run verify.py to confirm data integrity.")
    print("─" * 60)
    print()

if __name__ == "__main__":
    main()