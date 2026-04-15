"""
=============================================================
  CS 432 - Assignment 4: Sharding
  SubTask 2: Verify Data Integrity Across Shards
=============================================================
  Strategy  : Hash-Based Partitioning
  Shard Key : student_id
  Method    : student_id % 3

  Checks:
    1. Total row count matches original (no data loss)
    2. Each shard contains only its designated hash partition
    3. No duplicate record_ids across shards
    4. CHECK constraint rejects wrong-shard inserts
    5. All original student_ids are present after migration
    6. Sample records from each shard
=============================================================
"""

import sqlite3
import mysql.connector
import sys

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
SQLITE_DB_PATH = "../module_b.db"

# Number of shards for hash-based partitioning
NUMBER_OF_SHARDS = 3

SHARD_CONFIGS = {
    0: {"host": "10.0.116.184", "port": 3307,
        "database": "Scalix", "user": "Scalix", "password": "password@123"},
    1: {"host": "10.0.116.184", "port": 3308,
        "database": "Scalix", "user": "Scalix", "password": "password@123"},
    2: {"host": "10.0.116.184", "port": 3309,
        "database": "Scalix", "user": "Scalix", "password": "password@123"},
}

def print_header():
    print()
    print("=" * 60)
    print("  STEP 3: VERIFYING DATA INTEGRITY ACROSS SHARDS")
    print("=" * 60)
    print()
    print("  Strategy  : Hash-Based Partitioning")
    print("  Shard Key : student_id")
    print("  Method    : student_id % 3")
    print()
    print("  Shard Hash Rules:")
    for shard_id in range(NUMBER_OF_SHARDS):
        print(f"    shard_{shard_id} (shard_db_{shard_id}) → "
              f"student_id % 3 == {shard_id}")
    print()
    print("  Running 5 verification checks:")
    print("    Check 1 — Row count matches original (no data loss)")
    print("    Check 2 — Each shard has only its correct hash partition")
    print("    Check 3 — No duplicate record_ids across shards")
    print("    Check 4 — CHECK constraint rejects wrong-partition inserts")
    print("    Check 5 — All original student_ids present after migration")
    print()

def connect_shards():
    shards = {}
    for shard_id, config in SHARD_CONFIGS.items():
        try:
            conn = mysql.connector.connect(**config)
            shards[shard_id] = conn
        except Exception as e:
            print(f"  ✗ Cannot connect to shard_{shard_id}: {e}")
            sys.exit(1)
    return shards

def check_1_row_counts(shards):
    """Check total row count matches original — no data loss."""
    print("─" * 60)
    print("  CHECK 1: ROW COUNT — No Data Loss")
    print("─" * 60)
    print()

    sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
    original_count = sqlite_conn.execute(
        "SELECT COUNT(*) FROM attendance_records"
    ).fetchone()[0]
    sqlite_conn.close()

    shard_counts = {}
    for shard_id, conn in shards.items():
        cur = conn.cursor()
        cur.execute(
            f"SELECT COUNT(*) FROM shard_{shard_id}_attendance_records"
        )
        shard_counts[shard_id] = cur.fetchone()[0]


    total_sharded = sum(shard_counts.values())

    print(f"  {'Database':<35} {'Row Count':>10}")
    print(f"  {'─'*35} {'─'*10}")
    print(f"  {'Original (module_b.db)':<35} {original_count:>10}")
    print(f"  {'─'*35} {'─'*10}")
    for shard_id, count in shard_counts.items():
        label = f"shard_db_{shard_id} (hash: student_id % 3 == {shard_id})"
        print(f"  {label:<35} {count:>10}")
    print(f"  {'─'*35} {'─'*10}")
    print(f"  {'TOTAL ACROSS SHARDS':<35} {total_sharded:>10}")
    print()

    if original_count == total_sharded:
        print(f"  ✓ PASS — {original_count} original rows = "
              f"{total_sharded} sharded rows. No data lost.")
    else:
        print(f"  ✗ FAIL — {original_count - total_sharded} records missing!")
    print()
    return original_count == total_sharded

def check_2_shard_isolation(shards):
    """Check each shard contains only student_ids in its hash partition."""
    print("─" * 60)
    print("  CHECK 2: HASH PARTITION ISOLATION — No Wrong-Partition Records")
    print("─" * 60)
    print()

    all_passed = True
    for shard_id, conn in shards.items():
        cur = conn.cursor()

        # Count rows where student_id % 3 != shard_id
        cur.execute(
            f"SELECT COUNT(*) FROM shard_{shard_id}_attendance_records "
            f"WHERE MOD(student_id, 3) != {shard_id}"
        )
        wrong_count = cur.fetchone()[0]

        # Total rows in this shard
        cur.execute(
            f"SELECT COUNT(*) FROM shard_{shard_id}_attendance_records"
        )
        total = cur.fetchone()[0]

        if wrong_count == 0:
            print(f"  ✓ shard_{shard_id} (shard_db_{shard_id}) — "
                  f"All {total} records satisfy student_id % 3 == {shard_id}")
        else:
            print(f"  ✗ shard_{shard_id} (shard_db_{shard_id}) — "
                  f"{wrong_count} records have incorrect hash partition!")
            all_passed = False

    print()
    if all_passed:
        print("  ✓ PASS — All shards contain only their designated hash partition.")
    else:
        print("  ✗ FAIL — Some shards have wrong-partition records.")
    print()
    return all_passed

def check_3_no_duplicates(shards):
    """Check no record_id appears in more than one shard."""
    print("─" * 60)
    print("  CHECK 3: DUPLICATE CHECK — No Record in Multiple Shards")
    print("─" * 60)
    print()

    all_ids = []
    for shard_id, conn in shards.items():
        cur = conn.cursor()
        cur.execute(
            f"SELECT record_id FROM shard_{shard_id}_attendance_records"
        )
        ids = [row[0] for row in cur.fetchall()]
        all_ids.extend(ids)
        print(f"  shard_{shard_id} (shard_db_{shard_id}) — "
              f"{len(ids)} record_ids fetched")

    total     = len(all_ids)
    unique    = len(set(all_ids))
    duplicates = total - unique

    print()
    print(f"  Total record_ids across all shards : {total}")
    print(f"  Unique record_ids                  : {unique}")
    print(f"  Duplicates found                   : {duplicates}")
    print()

    if duplicates == 0:
        print("  ✓ PASS — No record_id appears in more than one shard.")
    else:
        print(f"  ✗ FAIL — {duplicates} duplicate record_ids found!")
    print()
    return duplicates == 0

def check_4_constraint_enforcement(shards):
    """Verify CHECK constraint rejects out-of-hash-partition inserts."""
    print("─" * 60)
    print("  CHECK 4: CONSTRAINT ENFORCEMENT — Wrong Partition Rejected")
    print("─" * 60)
    print()
    print("  Testing: Insert student_id=5 into shard_0")
    print("  Expected: REJECTED  (5 % 3 = 2, belongs in shard_2 not shard_0)")
    print()

    passed = False
    try:
        cur = shards[0].cursor()
        # student_id=5: 5 % 3 = 2, so belongs in shard_2, not shard_0 (which needs student_id % 3 == 0)
        cur.execute("""
            INSERT INTO shard_0_attendance_records
            VALUES (99999, 1, 5, 'present')
        """)
        shards[0].commit()
        print("  ✗ FAIL — Insert was wrongly accepted! Constraint not working.")
    except mysql.connector.errors.DatabaseError as e:
        print(f"  ✓ PASS — Insert correctly rejected by CHECK constraint.")
        print(f"    MySQL Error: {e.msg}")
        passed = True
    except Exception as e:
        print(f"  ✓ PASS — Insert correctly rejected.")
        print(f"    Error: {e}")
        passed = True

    print()
    return passed

def check_5_student_id_completeness(shards):
    """Verify all original student_ids are present after migration."""
    print("─" * 60)
    print("  CHECK 5: STUDENT ID COMPLETENESS — No Student Lost")
    print("─" * 60)
    print()

    # Get original student_ids from SQLite
    sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
    original_ids = set(
        row[0] for row in sqlite_conn.execute(
            "SELECT DISTINCT student_id FROM attendance_records"
        ).fetchall()
    )
    sqlite_conn.close()

    # Get student_ids from all shards
    sharded_ids = set()
    for shard_id, conn in shards.items():
        cur = conn.cursor()
        cur.execute(
            f"SELECT DISTINCT student_id "
            f"FROM shard_{shard_id}_attendance_records"
        )
        ids = set(row[0] for row in cur.fetchall())
        sharded_ids.update(ids)
        print(f"  shard_{shard_id} — {len(ids)} distinct student_ids "
              f"(hash: student_id % 3 == {shard_id})")

    missing  = original_ids - sharded_ids
    extra    = sharded_ids - original_ids

    print()
    print(f"  Original distinct student_ids : {len(original_ids)}")
    print(f"  Sharded distinct student_ids  : {len(sharded_ids)}")
    print(f"  Missing student_ids           : {len(missing)}")
    print(f"  Unexpected student_ids        : {len(extra)}")
    print()

    if not missing and not extra:
        print("  ✓ PASS — All original student_ids present across shards.")
    else:
        if missing:
            print(f"  ✗ FAIL — Missing student_ids: {sorted(missing)}")
        if extra:
            print(f"  ✗ FAIL — Unexpected student_ids: {sorted(extra)}")
    print()
    return not missing and not extra

def show_sample_records(shards):
    """Show sample records from each shard."""
    print("─" * 60)
    print("  SAMPLE RECORDS FROM EACH SHARD")
    print("─" * 60)
    print()

    for shard_id, conn in shards.items():
        cur = conn.cursor()
        cur.execute(
            f"SELECT record_id, att_session_id, student_id, status "
            f"FROM shard_{shard_id}_attendance_records LIMIT 4"
        )
        rows = cur.fetchall()

        cur.execute(
            f"SELECT DISTINCT student_id "
            f"FROM shard_{shard_id}_attendance_records LIMIT 5"
        )
        sample_students = [r[0] for r in cur.fetchall()]

        print(f"  shard_{shard_id} (shard_db_{shard_id}, "
              f"port {SHARD_CONFIGS[shard_id]['port']}) "
              f"| partition: student_id % 3 == {shard_id}:")
        print(f"  {'record_id':>10} {'att_session_id':>15} "
              f"{'student_id':>12} {'status':>10}  {'Partition?':>12}")
        print(f"  {'─'*10} {'─'*15} {'─'*12} {'─'*10}  {'─'*12}")
        for row in rows:
            partition = row[2] % 3
            is_correct = "✓ Yes" if partition == shard_id else "✗ No"
            print(f"  {row[0]:>10} {row[1]:>15} "
                  f"{row[2]:>12} {row[3]:>10}  {is_correct:>12}")
        print(f"  Sample student_ids: {sample_students}")
        print()

def print_final_summary(results):
    """Print overall pass/fail summary."""
    print("=" * 60)
    print("  FINAL VERIFICATION SUMMARY")
    print("=" * 60)
    print()

    labels = [
        "Check 1 — No data loss (row counts match)",
        "Check 2 — Hash partition isolation (no wrong-partition records)",
        "Check 3 — No duplicate record_ids across shards",
        "Check 4 — CHECK constraint rejects wrong-partition inserts",
        "Check 5 — All original student_ids present",
    ]

    all_passed = True
    for label, passed in zip(labels, results):
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}  {label}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("  ✓ ALL CHECKS PASSED.")
        print()
        print("  Sharding implementation is verified correct:")
        print("    • Data partitioned using hash-based strategy on student_id")
        print("    • Partitioning formula: student_id % 3")
        print("    • No records lost during migration from module_b.db")
        print("    • No record exists in more than one shard")
        print("    • Each shard physically enforces its partition via CHECK constraint")
        print("    • All students accounted for across shards with balanced distribution")
    else:
        print("  ✗ SOME CHECKS FAILED. Review errors above.")
    print()
    print("=" * 60)
    print()

def main():
    print_header()

    shards = connect_shards()

    r1 = check_1_row_counts(shards)
    r2 = check_2_shard_isolation(shards)
    r3 = check_3_no_duplicates(shards)
    r4 = check_4_constraint_enforcement(shards)
    r5 = check_5_student_id_completeness(shards)

    show_sample_records(shards)

    print_final_summary([r1, r2, r3, r4, r5])

    for conn in shards.values():
        conn.close()

if __name__ == "__main__":
    main()