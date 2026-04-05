from functools import wraps
from flask import request, jsonify, g, current_app
from .auth import verify_session, AuthError
from .logger import audit_log

def _read_session():
    session_id = (request.headers.get("X-Session-Id")
                  or request.cookies.get("session_id"))
    mac        = (request.headers.get("X-Session-Mac")
                  or request.cookies.get("session_mac"))
    return session_id, mac

def thread_safe_db(f):
    """Decorator to wrap route handlers with thread-safe database locking"""
    @wraps(f)
    def decorated(*args, **kwargs):
        db_lock = current_app.config["THREAD_LOCKS"]["database"]
        with db_lock:
            return f(*args, **kwargs)
    return decorated

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        sid, mac = _read_session()
        try:
            g.user = verify_session(sid, mac)
        except AuthError as e:
            audit_log("UNAUTHORIZED", request.path, None)
            return jsonify({"error": str(e)}), 401
        return f(*args, **kwargs)
    return decorated

def require_role(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            sid, mac = _read_session()
            try:
                g.user = verify_session(sid, mac)
            except AuthError as e:
                audit_log("UNAUTHORIZED", request.path, None)
                return jsonify({"error": str(e)}), 401
            if g.user["role"] not in allowed_roles:
                audit_log("FORBIDDEN", request.path, g.user["user_id"])
                return jsonify({"error": "Forbidden: insufficient role"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator