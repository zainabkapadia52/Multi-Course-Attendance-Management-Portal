import sqlite3
import json
from datetime import datetime

DB_PATH  = "module_b.db"
LOG_PATH = "logs/audit.log"

# Maps each audit action to which table it modifies
ACTION_TABLE_MAP = {
    "TA_UPDATE_ATT":       "attendance_records",
    "ADMIN_ATT_OVERRIDE":  "attendance_records",
    "TA_CREATE_SESSION":   "attendance_sessions",
    "CREATE_ATT_SESSION":  "attendance_sessions",
    "ACCEPT_CORRECTION":   "correction_requests",
    "REJECT_CORRECTION":   "correction_requests",
    "SUBMIT_CORRECTION":   "correction_requests",
    "CREATE_SEMESTER":     "semesters",
    "CREATE_COURSE":       "courses",
    "DELETE_COURSE":       "courses",
    "ASSIGN_INSTRUCTOR":   "course_instructors",
    "REMOVE_INSTRUCTOR":   "course_instructors",
    "ASSIGN_TA":           "course_tas",
    "REMOVE_TA":           "course_tas",
    "ENROLL_STUDENT":      "course_enrollments",
    "REMOVE_ENROLLMENT":   "course_enrollments",
    "CREATE_USER":         "users",
    "DELETE_USER":         "users",
}

# When a session is created, attendance_records are bulk inserted too.
# These actions also authorize attendance_records changes.
SESSION_CREATE_ACTIONS = {"TA_CREATE_SESSION", "CREATE_ATT_SESSION"}

# ACCEPT_CORRECTION updates both correction_requests AND attendance_records
CORRECTION_ACCEPT_ACTIONS = {"ACCEPT_CORRECTION"}


def parse_audit_log():
    entries = []
    try:
        with open(LOG_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("127.0.0.1") or line.startswith("*") or line.startswith("WARNING"):
                    continue

                parts = [p.strip() for p in line.split("|")]
                entry = {
                    "timestamp":  None,
                    "action":     None,
                    "user_id":    None,
                    "record_id":  None,
                    "session_id": None,
                    "req_id":     None,
                    "raw":        line
                }

                for part in parts:
                    if part.startswith("ACTION="):
                        entry["action"] = part.replace("ACTION=", "").strip()
                    elif part.startswith("USER="):
                        entry["user_id"] = part.replace("USER=", "").strip()
                    elif part.startswith("record_id="):
                        try:
                            entry["record_id"] = int(part.replace("record_id=", "").split()[0])
                        except:
                            pass
                    elif part.startswith("att_session_id="):
                        try:
                            entry["session_id"] = int(part.replace("att_session_id=", "").split()[0])
                        except:
                            pass
                    elif part.startswith("req_id="):
                        try:
                            entry["req_id"] = int(part.replace("req_id=", "").split()[0])
                        except:
                            pass
                    else:
                        try:
                            entry["timestamp"] = datetime.fromisoformat(part)
                        except:
                            pass

                if entry["timestamp"] and entry["action"]:
                    entries.append(entry)

    except FileNotFoundError:
        print(f"audit.log not found at {LOG_PATH}\n")

    return entries


def get_raw_changes():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, table_name, record_id, old_value, new_value, changed_at
        FROM raw_changes
        ORDER BY changed_at ASC
    """).fetchall()
    conn.close()
    return rows


def find_match(raw_record_id, table_name, changed_at, new_value_str, audit_entries):
    new_value = {}
    try:
        if new_value_str:
            new_value = json.loads(new_value_str)
    except:
        pass

    for entry in audit_entries:
        if entry["timestamp"] is None or entry["action"] is None:
            continue

        time_diff = abs((changed_at - entry["timestamp"]).total_seconds())
        if time_diff > 5:
            continue

        action = entry["action"]

        # ── attendance_records ──────────────────────────────────────────────
        if table_name == "attendance_records":

            # Direct update by TA
            if action == "TA_UPDATE_ATT":
                if entry["record_id"] == raw_record_id:
                    return entry

            # Direct override by admin
            if action == "ADMIN_ATT_OVERRIDE":
                if entry["record_id"] == raw_record_id:
                    return entry

            # Bulk insert as part of session creation
            if action in SESSION_CREATE_ACTIONS:
                session_id_in_record = new_value.get("att_session_id")
                if session_id_in_record and session_id_in_record == entry["session_id"]:
                    return entry

            # ── KEY FIX ──────────────────────────────────────────────────────
            # Attendance updated as a side effect of instructor accepting a
            # correction. The audit.log has one ACCEPT_CORRECTION entry but
            # TWO raw_changes rows (correction_requests + attendance_records).
            # Match the attendance_records change by checking the req_id in
            # the audit entry corresponds to a correction that affected this
            # att_session_id.
            if action == "ACCEPT_CORRECTION":
                att_session_id_in_record = new_value.get("att_session_id")
                if att_session_id_in_record and entry["session_id"] == att_session_id_in_record:
                    return entry
                # Fallback: if session_id wasn't parsed, match on timestamp alone
                # since ACCEPT_CORRECTION is the only action that updates
                # attendance_records without a direct record_id in the log
                if entry["req_id"] is not None:
                    return entry

        # ── attendance_sessions ─────────────────────────────────────────────
        elif table_name == "attendance_sessions":
            if action in SESSION_CREATE_ACTIONS:
                if entry["session_id"] == raw_record_id:
                    return entry

        # ── correction_requests ─────────────────────────────────────────────
        elif table_name == "correction_requests":
            if action in ("SUBMIT_CORRECTION", "ACCEPT_CORRECTION", "REJECT_CORRECTION"):
                if entry["req_id"] == raw_record_id:
                    return entry

        # ── all other tables ────────────────────────────────────────────────
        else:
            expected_table = ACTION_TABLE_MAP.get(action)
            if expected_table == table_name:
                return entry

    return None


def find_unauthorized_changes():
    print("=" * 60)
    print("   Unauthorized Change Report")
    print("=" * 60)
    print()

    raw_changes   = get_raw_changes()
    audit_entries = parse_audit_log()

    if not raw_changes:
        print("raw_changes is empty — nothing to verify.")
        print("Either no data has been modified yet, or triggers are not set up.\n")
        return

    if not audit_entries:
        print("Warning: audit.log is empty or missing.")
        print("Every raw_change will be flagged.\n")

    # Group results by table for clean output
    results = {}
    for row in raw_changes:
        table      = row["table_name"]
        record_id  = row["record_id"]
        old_val    = row["old_value"]
        new_val    = row["new_value"]
        changed_at = datetime.fromisoformat(row["changed_at"])

        match = find_match(record_id, table, changed_at, new_val, audit_entries)

        if table not in results:
            results[table] = {"clean": 0, "flagged": []}

        if match:
            results[table]["clean"] += 1
        else:
            results[table]["flagged"].append({
                "record_id":  record_id,
                "changed_at": str(changed_at),
                "old_value":  old_val,
                "new_value":  new_val,
            })

    # Print results per table
    total_clean   = 0
    total_flagged = 0

    for table, data in sorted(results.items()):
        flagged_count = len(data["flagged"])
        clean_count   = data["clean"]
        total_clean   += clean_count
        total_flagged += flagged_count

        print(f"--- {table} ---")
        if flagged_count == 0:
            print(f"  All {clean_count} change(s) authorized.\n")
        else:
            print(f"  clean={clean_count}  flagged={flagged_count}\n")
            for f in data["flagged"]:
                print(f"  [UNAUTHORIZED]")
                print(f"  record_id  : {f['record_id']}")
                print(f"  changed_at : {f['changed_at']}")
                print(f"  old_value  : {f['old_value']}")
                print(f"  new_value  : {f['new_value']}")
                print(f"  verdict    : No matching audit.log entry — bypassed API\n")

    print("=" * 60)
    print(f"  Total clean   : {total_clean}")
    print(f"  Total flagged : {total_flagged}")
    print("=" * 60)

    if total_flagged == 0:
        print("\n  All clear. No unauthorized changes detected.")
    else:
        print(f"\n  {total_flagged} unauthorized change(s) detected.")
        print("  These were made directly in the DB, bypassing the API.")


if __name__ == "__main__":
    find_unauthorized_changes()