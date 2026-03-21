import logging
import json
from datetime import datetime
from flask import session, request

audit_logger = logging.getLogger("audit")
audit_logger.setLevel(logging.INFO)
_logger.propagate = False  

handler = logging.FileHandler("audit.log")
handler.setFormatter(logging.Formatter('%(message)s'))
audit_logger.addHandler(handler)


def log_audit(action, table_name, record_id, old_value, new_value, status="success"):
    entry = {
        "timestamp":     datetime.utcnow().isoformat(),
        "user_id":       session.get("user_id"),
        "username":      session.get("username"),
        "role":          session.get("role"),
        "endpoint":      request.path,
        "method":        request.method,
        "action":        action,          # MARK, UPDATE, DELETE
        "table_name":    table_name,
        "record_id":     record_id,
        "old_value":     old_value,
        "new_value":     new_value,
        "ip_address":    request.remote_addr,
        "session_token": session.get("session_id"),
        "status":        status
    }
    audit_logger.info(json.dumps(entry))
