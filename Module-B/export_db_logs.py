import sqlite3
from datetime import datetime

DB_PATH  = "module_b.db"
LOG_PATH = "logs/database_logs.log"


def export():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT id, table_name, record_id, old_value, new_value, changed_at
        FROM raw_changes
        ORDER BY changed_at ASC
    """).fetchall()
    conn.close()

    with open(LOG_PATH, "w") as f:
        f.write(f"=== Database Log Export — {datetime.utcnow().isoformat()} ===\n\n")

        for row in rows:
            line = (
                f"{row['changed_at']} | "
                f"TABLE={row['table_name']} | "
                f"ROWID={row['record_id']} | "
                f"OLD={row['old_value']} | "
                f"NEW={row['new_value']}"
            )
            f.write(line + "\n")

    print(f"Exported {len(rows)} entries → {LOG_PATH}")


if __name__ == "__main__":
    export()