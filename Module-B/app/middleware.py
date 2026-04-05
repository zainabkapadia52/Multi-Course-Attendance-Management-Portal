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

def thread_safe_db(*resources):
    """
    Decorator to wrap route handlers with per-resource thread-safe locking.
    Supports multiple resources - locks are acquired in order.
    
    Usage:
        @bp.get("/students")
        @require_role("admin")
        @thread_safe_db("users", "enrollments")  # Lock users and enrollments
        def list_students():
            # ...
    
    Args:
        *resources: Resource names to lock (e.g., "auth", "courses", "attendance", etc.)
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            locks = []
            for resource in resources:
                if resource in current_app.config["THREAD_LOCKS"]:
                    lock = current_app.config["THREAD_LOCKS"][resource]
                    if lock is not None:
                        locks.append(lock)
            
            # Acquire all locks in order (prevents deadlock with consistent ordering)
            for lock in locks:
                lock.acquire()
            
            try:
                return f(*args, **kwargs)
            finally:
                # Release in reverse order
                for lock in reversed(locks):
                    lock.release()
        
        return decorated
    
    # Handle case where decorator is used without arguments (backward compatibility)
    if len(resources) == 1 and callable(resources[0]):
        f = resources[0]
        @wraps(f)
        def decorated(*args, **kwargs):
            # Use "auth" as default if no resource specified
            lock = current_app.config["THREAD_LOCKS"].get("auth")
            if lock:
                lock.acquire()
            try:
                return f(*args, **kwargs)
            finally:
                if lock:
                    lock.release()
        return decorated
    
    return decorator

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