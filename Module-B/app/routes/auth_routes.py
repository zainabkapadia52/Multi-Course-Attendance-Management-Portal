from flask import Blueprint, request, jsonify, make_response
from ..auth import login, logout, verify_session, AuthError
from ..logger import audit_log

bp = Blueprint("auth", __name__)

@bp.post("/login")
def do_login():
    data     = request.get_json(silent=True) or {}
    username = data.get("user") or data.get("username", "")
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "Missing parameters"}), 401
    try:
        sess = login(username, password)
    except AuthError as e:
        audit_log("LOGIN_FAIL", "/login", None, f"username={username}")
        return jsonify({"error": str(e)}), 401
    audit_log("LOGIN_OK", "/login", sess["user_id"], f"username={username}")
    return jsonify({
        "message":       "Login successful",
        "session_token": sess["session_id"],
        "mac":           sess["mac"],
        "user_id":       sess["user_id"],
        "role":          sess["role"],
        "username":      sess["username"]
    }), 200

@bp.get("/isAuth")
def is_auth():
    data = request.get_json(silent=True) or {}
    sid  = (request.headers.get("X-Session-Id")
            or data.get("session_token")
            or request.cookies.get("session_id"))
    mac  = (request.headers.get("X-Session-Mac")
            or data.get("mac")
            or request.cookies.get("session_mac"))
    try:
        user = verify_session(sid, mac)
        return jsonify({
            "message":  "User is authenticated",
            "username": user["username"],
            "role":     user["role"],
            "expiry":   user["expires_at"]
        }), 200
    except AuthError as e:
        return jsonify({"error": str(e)}), 401

@bp.post("/logout")
def do_logout():
    sid = (request.headers.get("X-Session-Id")
           or request.cookies.get("session_id"))
    if sid:
        logout(sid)
        audit_log("LOGOUT", "/logout", None)
    resp = make_response(jsonify({"message": "Logged out"}))
    resp.delete_cookie("session_id",  path="/")
    resp.delete_cookie("session_mac", path="/")
    return resp