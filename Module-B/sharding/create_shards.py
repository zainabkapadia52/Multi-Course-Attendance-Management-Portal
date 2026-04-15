"""
=============================================================
  CS 432 - Assignment 4: Sharding
  SubTask 2: Create Shard Tables in Docker Containers
=============================================================
  Strategy  : Hash-Based Partitioning
  Shard Key : student_id
  Method    : student_id % 3
              Shard 0 → student_id % 3 == 0
              Shard 1 → student_id % 3 == 1
              Shard 2 → student_id % 3 == 2
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
        "host": "10.0.116.184",
        "port": 3307,
        "database": "Scalix",
        "user": "Scalix",
        "password": "password@123",
        "container": "shard_0",
    },
    {
        "shard_id": 1,
        "host": "10.0.116.184",
        "port": 3308,
        "database": "Scalix",
        "user": "Scalix",
        "password": "password@123",
        "container": "shard_1",
    },
    {
        "shard_id": 2,
        "host": "10.0.116.184",
        "port": 3309,
        "database": "Scalix",
        "user": "Scalix",
        "password": "password@123",
        "container": "shard_2",
    },
]

def print_header():
    print()
    print("=" * 60)
    print("  STEP 1: CREATING SHARD TABLES IN REMOTE MYSQL SHARDS")
    print("=" * 60)
    print()
    print("  Sharding Strategy : Hash-Based Partitioning")
    print("  Shard Key         : student_id")
    print("  Method            : student_id % 3")
    print()
    print("  Shard Layout:")
    print("  ┌──────────┬────────────┬──────────┬─────────────────────┐")
    print("  │  Shard   │  Database  │   Port   │    Partition Rule   │")
    print("  ├──────────┼────────────┼──────────┼─────────────────────┤")
    print("  │ shard_0  │ Scalix     │   3307   │   student_id % 3 == 0│")
    print("  │ shard_1  │ Scalix     │   3308   │   student_id % 3 == 1│")
    print("  │ shard_2  │ Scalix     │   3309   │   student_id % 3 == 2│")
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
    """Create shard table with hash-based CHECK constraint."""
    shard_id = config["shard_id"]

    create_sql = f"""
        CREATE TABLE IF NOT EXISTS shard_{shard_id}_attendance_records (
            record_id       INT          PRIMARY KEY AUTO_INCREMENT,
            att_session_id  INT          NOT NULL,
            student_id      INT          NOT NULL,
            status          VARCHAR(10)  NOT NULL,
            CONSTRAINT chk_shard_{shard_id}
                CHECK (MOD(student_id, 3) = {shard_id}),
            INDEX idx_att_session (att_session_id),
            INDEX idx_student_id (student_id),
            INDEX idx_session_student (att_session_id, student_id)
    
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
    print("  Connecting to remote MySQL shards...")
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
            print(f"  ✓ shard_{shard_id} | Database : {config['database']} "
                  f"| Port : {config['port']}")
            print(f"    Table     : shard_{shard_id}_attendance_records")
            print(f"    CHECK     : MOD(student_id, 3) = {shard_id}")
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