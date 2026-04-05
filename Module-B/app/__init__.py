from flask import Flask
from .db import init_app
from concurrent.futures import ThreadPoolExecutor
import threading

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"]    = "cs432-iitgn-secret-change-in-prod"
    app.config["DB_PATH"]       = "module_b.db"
    app.config["SESSION_HOURS"] = 2
    
    # ═══════════════════════════════════════════════════════════════════════════
    # THREADING CONFIGURATION — Handle concurrent requests in parallel
    # ═══════════════════════════════════════════════════════════════════════════
    # ThreadPoolExecutor: manages a pool of worker threads for concurrent operations
    # max_workers=10: up to 10 concurrent threads (can be increased if needed)
    app.config["THREAD_POOL"] = ThreadPoolExecutor(max_workers=10)
    app.config["THREAD_LOCKS"] = {  # Thread-safe locks for critical sections
        "database": threading.RLock(),      # Recursive lock for DB operations
        "session": threading.RLock(),       # Lock for session management
        "auth": threading.RLock(),          # Lock for authentication
    }
    
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