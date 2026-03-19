from flask import Blueprint, request, jsonify, make_response, redirect
from ..auth import login, logout, verify_session, AuthError
from ..logger import audit_log

bp = Blueprint("auth", __name__)

@bp.post("/login")
def do_login():
    data = request.get_json(silent=True) or {}
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

    resp = make_response(jsonify({
        "message": "Login successful",
        "session_token": sess["session_id"],
        "mac": sess["mac"],
        "role": sess["role"],
        "username": sess["username"]
    }))
    resp.set_cookie("session_id",  sess["session_id"], httponly=True, samesite="Lax")
    resp.set_cookie("session_mac", sess["mac"],        httponly=True, samesite="Lax")
    return resp, 200

@bp.get("/isAuth")
def is_auth():
    # Support both cookies and headers for session tokens
    session_id = request.cookies.get("session_id") or request.headers.get("X-Session-Id") or request.json.get("session_token") if request.is_json else None
    mac        = request.cookies.get("session_mac") or request.headers.get("X-Session-Mac") or request.json.get("mac") if request.is_json else None
    
    try:
        user = verify_session(session_id, mac)
        return jsonify({
            "message": "User is authenticated",
            "username": user["username"],
            "role": user["role"],
            "expiry": user["expires_at"]
        }), 200
    except AuthError as e:
        return jsonify({"error": str(e)}), 401

@bp.post("/logout")
def do_logout():
    session_id = request.cookies.get("session_id")
    if session_id:
        logout(session_id)   # deletes from DB
        audit_log("LOGOUT", "/logout", None)

    resp = make_response(redirect("/login"))
    # Delete both cookies — set expires to epoch so browser removes them immediately
    resp.delete_cookie("session_id",  path="/")
    resp.delete_cookie("session_mac", path="/")
    # Belt-and-suspenders: also set no-cache so the redirect itself isn't cached
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp