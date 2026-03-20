from functools import wraps
from flask import request, jsonify, g
from .auth import verify_session, AuthError
from .logger import audit_log

def _read_session():
    session_id = (request.headers.get("X-Session-Id")
                  or request.cookies.get("session_id"))
    mac        = (request.headers.get("X-Session-Mac")
                  or request.cookies.get("session_mac"))
    return session_id, mac

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