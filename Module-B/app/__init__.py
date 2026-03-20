from flask import Flask
from .db import init_app

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"]    = "cs432-iitgn-secret-change-in-prod"
    app.config["DB_PATH"]       = "module_b.db"
    app.config["SESSION_HOURS"] = 2

    init_app(app)

    from .routes.auth_routes  import bp as auth_bp
    from .routes.admin        import bp as admin_bp
    from .routes.instructor   import bp as instructor_bp
    from .routes.student      import bp as student_bp
    from .routes.dean         import bp as dean_bp
    from .routes.ta           import bp as ta_bp
    from .routes.page_routes  import bp as page_bp
    from .routes.stream       import bp as stream_bp   # ← new

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp,      url_prefix="/api/admin")
    app.register_blueprint(instructor_bp, url_prefix="/api/instructor")
    app.register_blueprint(student_bp,    url_prefix="/api/student")
    app.register_blueprint(dean_bp,       url_prefix="/api/dean")
    app.register_blueprint(ta_bp,         url_prefix="/api/ta")
    app.register_blueprint(stream_bp)     # ← new (no prefix, /stream is the url)
    app.register_blueprint(page_bp)

    return app