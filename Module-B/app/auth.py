import uuid
import hmac
import hashlib
from datetime import datetime, timedelta
from flask import current_app
from werkzeug.security import check_password_hash
from .db import get_db

class AuthError(Exception):
    pass

def _make_mac(session_id: str, secret: str) -> str:
    return hmac.new(
        secret.encode(),
        session_id.encode(),
        hashlib.sha256
    ).hexdigest()

def login(username: str, password: str) -> dict:
    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()

    if not user or not check_password_hash(user["pwd_hash"], password):
        raise AuthError("Invalid credentials")

    # Invalidate old sessions for this user
    db.execute("DELETE FROM sessions WHERE user_id = ?", (user["user_id"],))

    session_id = str(uuid.uuid4())
    secret     = current_app.config["SECRET_KEY"]
    mac        = _make_mac(session_id, secret)
    hours      = current_app.config["SESSION_HOURS"]
    expires_at = (datetime.utcnow() + timedelta(hours=hours)).isoformat()

    db.execute(
        "INSERT INTO sessions (session_id, user_id, mac, expires_at) VALUES (?,?,?,?)",
        (session_id, user["user_id"], mac, expires_at)
    )
    db.execute(
        "UPDATE users SET last_login = ? WHERE user_id = ?",
        (datetime.utcnow().isoformat(), user["user_id"])
    )
    db.commit()

    return {
        "session_id": session_id,
        "mac": mac,
        "user_id": user["user_id"],
        "username": user["username"],
        "role": user["role"],
        "expires_at": expires_at
    }

def verify_session(session_id: str, mac: str) -> dict:
    if not session_id or not mac:
        raise AuthError("No session found")

    db = get_db()
    row = db.execute(
        """SELECT s.*, u.username, u.role, u.user_id AS uid
           FROM sessions s JOIN users u ON s.user_id = u.user_id
           WHERE s.session_id = ?""",
        (session_id,)
    ).fetchone()

    if not row:
        raise AuthError("No session found")

    if datetime.utcnow() > datetime.fromisoformat(row["expires_at"]):
        db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        db.commit()
        raise AuthError("Session expired")

    secret   = current_app.config["SECRET_KEY"]
    expected = _make_mac(session_id, secret)
    if not hmac.compare_digest(expected, mac):
        raise AuthError("Invalid session token")

    return {
        "user_id":    row["uid"],
        "username":   row["username"],
        "role":       row["role"],
        "expires_at": row["expires_at"],
        "session_id": session_id
    }

def logout(session_id: str):
    db = get_db()
    db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    db.commit()