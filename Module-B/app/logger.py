import logging
import os
from datetime import datetime

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    filename="logs/audit.log",
    level=logging.INFO,
    format="%(message)s"
)
_logger = logging.getLogger("audit")

def audit_log(action: str, endpoint: str, user_id, details: str = "", old_value=None, new_value=None):
    entry = (
        f"{datetime.utcnow().isoformat()} | "
        f"ACTION={action} | "
        f"USER={user_id} | "
        f"ENDPOINT={endpoint} | "
        f"{details}"
    )
    if old_value is not None or new_value is not None:
        entry += f" | OLD={old_value} | NEW={new_value}"

    _logger.info(entry)