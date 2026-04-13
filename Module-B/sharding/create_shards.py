"""
=============================================================
  CS 432 - Assignment 4: Sharding
  SubTask 2: Create Shard Tables in Docker Containers
=============================================================
  Strategy  : Range-Based Partitioning
  Shard Key : student_id
  Ranges    : Shard 0 → 12 to 31
              Shard 1 → 32 to 51
              Shard 2 → 52 to 71
=============================================================
"""

import mysql.connector
import time
import sys

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
SHARD_CONFIGS = [
    {
        "shard_id": 0,
        "host": "localhost",
        "port": 3307,
        "database": "shard_db_0",
        "user": "root",
        "password": "shardpass",
        "container": "shard_0",
        "min_id": 12,
        "max_id": 31,
        "condition": "student_id BETWEEN 12 AND 31",
    },
    {
        "shard_id": 1,
        "host": "localhost",
        "port": 3308,
        "database": "shard_db_1",
        "user": "root",
        "password": "shardpass",
        "container": "shard_1",
        "min_id": 32,
        "max_id": 51,
        "condition": "student_id BETWEEN 32 AND 51",
    },
    {
        "shard_id": 2,
        "host": "localhost",
        "port": 3309,
        "database": "shard_db_2",
        "user": "root",
        "password": "shardpass",
        "container": "shard_2",
        "min_id": 52,
        "max_id": 71,
        "condition": "student_id BETWEEN 52 AND 71",
    },
]

def print_header():
    print()
    print("=" * 60)
    print("  STEP 1: CREATING SHARD TABLES IN DOCKER CONTAINERS")
    print("=" * 60)
    print()
    print("  Sharding Strategy : Range-Based Partitioning")
    print("  Shard Key         : student_id")
    print("  Total Students    : 60 (student_id 12 to 71)")
    print()
    print("  Shard Layout:")
    print("  ┌──────────┬────────────┬──────────┬─────────────────────┐")
    print("  │  Shard   │  Database  │   Port   │   student_id Range  │")
    print("  ├──────────┼────────────┼──────────┼─────────────────────┤")
    print("  │ shard_0  │ shard_db_0 │   3307   │   12  to  31        │")
    print("  │ shard_1  │ shard_db_1 │   3308   │   32  to  51        │")
    print("  │ shard_2  │ shard_db_2 │   3309   │   52  to  71        │")
    print("  └──────────┴────────────┴──────────┴─────────────────────┘")
    print()

def wait_for_mysql(config, retries=10, delay=5):
    """Wait for MySQL container to be ready."""
    print(f"  Waiting for shard_{config['shard_id']} "
          f"(port {config['port']}) to be ready...", end="", flush=True)
    for attempt in range(retries):
        try:
            conn = mysql.connector.connect(
                host=config["host"],
                port=config["port"],
                user=config["user"],
                password=config["password"],
                database=config["database"],
                connection_timeout=3
            )
            conn.close()
            print(f" Ready ✓")
            return True
        except Exception:
            print(".", end="", flush=True)
            time.sleep(delay)
    print(f" FAILED ✗")
    return False

def create_table(config):
    """Create shard table with range-based CHECK constraint."""
    shard_id = config["shard_id"]
    min_id   = config["min_id"]
    max_id   = config["max_id"]

    create_sql = f"""
        CREATE TABLE IF NOT EXISTS shard_{shard_id}_attendance_records (
            record_id       INT          PRIMARY KEY,
            att_session_id  INT          NOT NULL,
            student_id      INT          NOT NULL,
            status          VARCHAR(10)  NOT NULL,
            CONSTRAINT chk_shard_{shard_id}
                CHECK (student_id BETWEEN {min_id} AND {max_id})
        )
    """

    conn = mysql.connector.connect(
        host=config["host"],
        port=config["port"],
        database=config["database"],
        user=config["user"],
        password=config["password"]
    )
    cursor = conn.cursor()
    cursor.execute(create_sql)
    conn.commit()
    cursor.close()
    conn.close()

def main():
    print_header()

    print("─" * 60)
    print("  Connecting to Docker containers...")
    print("─" * 60)

    # Wait for all containers to be ready
    all_ready = True
    for config in SHARD_CONFIGS:
        ready = wait_for_mysql(config)
        if not ready:
            all_ready = False

    if not all_ready:
        print("\n  ✗ One or more containers not ready.")
        print("  Make sure Docker containers are running:")
        print("    docker ps")
        sys.exit(1)

    print()
    print("─" * 60)
    print("  Creating shard tables in each container...")
    print("─" * 60)
    print()

    success_count = 0
    for config in SHARD_CONFIGS:
        shard_id = config["shard_id"]
        try:
            create_table(config)
            print(f"  ✓ shard_{shard_id} | Database : shard_db_{shard_id} "
                  f"| Port : {config['port']}")
            print(f"    Table     : shard_{shard_id}_attendance_records")
            print(f"    CHECK     : student_id BETWEEN "
                  f"{config['min_id']} AND {config['max_id']}")
            print()
            success_count += 1
        except Exception as e:
            print(f"  ✗ shard_{shard_id} FAILED: {e}")
            print()

    print("─" * 60)
    if success_count == 3:
        print(f"  ✓ All 3 shard tables created successfully.")
        print()
        print("  Next step: Run migrate.py to move data into shards.")
    else:
        print(f"  ✗ Only {success_count}/3 shards created. Check errors above.")
    print("─" * 60)
    print()

if __name__ == "__main__":
    main()