# migrate_to_shards.py
import sqlite3
import os

MAIN_DB = "module_b.db"
NUM_SHARDS = 3

SHARD_SCHEMA = """
CREATE TABLE IF NOT EXISTS attendance_records (
    record_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    att_session_id INTEGER NOT NULL,
    student_id     INTEGER NOT NULL,
    status         TEXT    CHECK(status IN ('present','absent')) NOT NULL DEFAULT 'absent'
);
CREATE INDEX IF NOT EXISTS idx_ar_student ON attendance_records(student_id);
CREATE INDEX IF NOT EXISTS idx_ar_session ON attendance_records(att_session_id);
"""


def get_shard_id(student_id: int) -> int:
    """Return shard index for a student_id using modulo 3 partitioning."""
    return student_id % 3


def get_shard_path(shard_id: int) -> str:
    return f"shard_{shard_id}.db"


def migrate():
    # Connect to main DB
    main_conn = sqlite3.connect(MAIN_DB)
    main_conn.row_factory = sqlite3.Row

    rows = main_conn.execute(
        "SELECT record_id, att_session_id, student_id, status FROM attendance_records ORDER BY student_id"
    ).fetchall()

    print(f"Total records in main.db: {len(rows)}")
    print()

    # Delete old shard files if they exist
    for shard_id in range(NUM_SHARDS):
        path = get_shard_path(shard_id)
        if os.path.exists(path):
            os.remove(path)
            print(f"Deleted old {path}")

    # Create fresh shard DBs with schema
    shard_conns = {}
    for shard_id in range(NUM_SHARDS):
        path = get_shard_path(shard_id)
        conn = sqlite3.connect(path)
        conn.executescript(SHARD_SCHEMA)
        conn.commit()
        shard_conns[shard_id] = conn
        print(f"Initialised {path}  (student_id % 3 == {shard_id})")

    print()

    # Distribute records into shards
    counts = {i: 0 for i in range(NUM_SHARDS)}

    for row in rows:
        shard_id = get_shard_id(row["student_id"])
        shard_conns[shard_id].execute(
            """INSERT INTO attendance_records
               (record_id, att_session_id, student_id, status)
               VALUES (?, ?, ?, ?)""",
            (row["record_id"], row["att_session_id"], row["student_id"], row["status"])
        )
        counts[shard_id] += 1

    # Commit and close all shards
    for shard_id, conn in shard_conns.items():
        conn.commit()
        conn.close()

    main_conn.close()

    # Report
    print("\n--- Migration Results ---")
    total_migrated = 0
    for shard_id in range(NUM_SHARDS):
        lo, hi = SHARD_RANGES[shard_id]
        print(f"  shard_{shard_id}.db  (student_id {lo:>2}–{hi:>2})  →  {counts[shard_id]} records")
        total_migrated += counts[shard_id]

    print(f"\n  Total migrated : {total_migrated}")
    print(f"  Total in main  : {len(rows)}")

    if skipped:
        print(f"\n  Skipped (non-student user_ids): {sorted(set(skipped))}  ({len(skipped)} records)")

    # Skew analysis
    print("\n--- Skew Analysis ---")
    avg = total_migrated / NUM_SHARDS
    print(f"  Expected per shard (avg) : {avg:.1f}")
    for shard_id in range(NUM_SHARDS):
        delta = counts[shard_id] - avg
        pct = (delta / avg) * 100
        bar = "▓" * int(counts[shard_id] / 20)
        print(f"  shard_{shard_id}  {counts[shard_id]:>5} records  {pct:+.1f}%  {bar}")

    max_diff = max(counts.values()) - min(counts.values())
    print(f"\n  Max imbalance  : {max_diff} records between most and least loaded shard")

    if max_diff > avg * 0.2:
        print("  ⚠  Skew detected — range-based sharding is uneven for this dataset")
    else:
        print("  ✓  Distribution is acceptably balanced")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    migrate()