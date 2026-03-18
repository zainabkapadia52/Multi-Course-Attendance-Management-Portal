from flask import Blueprint, render_template, redirect, request, make_response
from ..auth import verify_session, AuthError

bp = Blueprint("pages", __name__)

def _get_user():
    try:
        return verify_session(
            request.cookies.get("session_id"),
            request.cookies.get("session_mac")
        )
    except AuthError:
        return None

def _no_cache(response):
    """Prevent browser from caching any protected page."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"]        = "no-cache"
    response.headers["Expires"]       = "0"
    return response

ROLE_REDIRECT = {
    "admin":      "/admin",
    "instructor": "/instructor",
    "student":    "/student",
    "dean":       "/dean",
    "ta":         "/ta",
}

@bp.get("/")
def index():
    user = _get_user()
    if not user:
        return redirect("/login")
    return redirect(ROLE_REDIRECT.get(user["role"], "/login"))

@bp.get("/login")
def login_page():
    # If already logged in, go straight to dashboard — don't show login again
    user = _get_user()
    if user:
        return redirect(ROLE_REDIRECT.get(user["role"], "/"))
    resp = make_response(render_template("login.html"))
    # No-cache on login page too so back-button can't return to it after logout
    return _no_cache(resp)

@bp.get("/admin")
def admin_page():
    user = _get_user()
    if not user or user["role"] != "admin":
        return redirect("/login")
    return _no_cache(make_response(render_template("admin/dashboard.html", user=user)))

@bp.get("/instructor")
def instructor_page():
    user = _get_user()
    if not user or user["role"] != "instructor":
        return redirect("/login")
    return _no_cache(make_response(render_template("instructor/dashboard.html", user=user)))

@bp.get("/student")
def student_page():
    user = _get_user()
    if not user or user["role"] != "student":
        return redirect("/login")
    return _no_cache(make_response(render_template("student/dashboard.html", user=user)))

@bp.get("/dean")
def dean_page():
    user = _get_user()
    if not user or user["role"] != "dean":
        return redirect("/login")
    return _no_cache(make_response(render_template("dean/dashboard.html", user=user)))

@bp.get("/ta")
def ta_page():
    user = _get_user()
    if not user or user["role"] != "ta":
        return redirect("/login")
    return _no_cache(make_response(render_template("ta/dashboard.html", user=user)))