from flask import Blueprint, render_template, redirect

bp = Blueprint("pages", __name__)

@bp.get("/")
def index():
    return redirect("/login")

@bp.get("/login")
def login_page():
    return render_template("login.html")

@bp.get("/admin")
def admin_page():
    return render_template("admin/dashboard.html")

@bp.get("/instructor")
def instructor_page():
    return render_template("instructor/dashboard.html")

@bp.get("/student")
def student_page():
    return render_template("student/dashboard.html")

@bp.get("/dean")
def dean_page():
    return render_template("dean/dashboard.html")

@bp.get("/ta")
def ta_page():
    return render_template("ta/dashboard.html")