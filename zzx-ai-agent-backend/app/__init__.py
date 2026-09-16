import os
import sys
from flask import Flask
from flask import jsonify


def create_app(config_object=None, initialize_database=True):
    """Flask application factory."""
    # Add local lib path for pymysql (installed via --target)
    _lib = os.path.join(os.path.dirname(__file__), "..", "pylib")
    if os.path.isdir(_lib) and _lib not in sys.path:
        sys.path.insert(0, _lib)

    from app.config import Config
    from app.utils.logging_config import configure_logging

    selected_config = config_object or Config
    selected_config.validate()
    configure_logging(selected_config.LOG_LEVEL)

    app = Flask(__name__)
    app.config.from_object(selected_config)

    from app.extensions import init_extensions
    init_extensions(app)

    # Initialise database tables on startup
    if initialize_database:
        with app.app_context():
            from app.auth import init_db
            from app.chat_history import init_tables as init_chat_tables
            from app.rag_documents import init_rag_tables
            init_db()
            init_chat_tables()
            init_rag_tables()

    # Credential-aware CORS for the configured frontend origins.
    @app.after_request
    def add_cors(response):
        from flask import request

        origin = request.headers.get("Origin")
        if origin and origin in app.config["CORS_ORIGINS"]:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers.add("Vary", "Origin")
        response.headers["Access-Control-Allow-Methods"] = (
            "GET, POST, PUT, DELETE, OPTIONS"
        )
        response.headers["Access-Control-Allow-Headers"] = (
            "Authorization, Content-Type, X-CSRF-TOKEN"
        )
        return response

    # Register route blueprints
    from app.routes.manus import manus_bp
    from app.routes.love_app import love_bp
    from app.auth import auth_bp
    from app.routes.session import session_bp
    from app.routes.rag_admin import rag_admin_bp
    app.register_blueprint(manus_bp)
    app.register_blueprint(love_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(session_bp)
    app.register_blueprint(rag_admin_bp)

    # Health check
    @app.route("/api/health")
    def health():
        from app.auth_store import redis_is_ready
        redis_ready = redis_is_ready()
        return jsonify({
            "status": "ok" if redis_ready else "degraded",
            "mode": app.config["SYSTEM_NAME"],
            "environment": app.config["APP_ENV"],
            "redis": "ok" if redis_ready else "unavailable",
        })

    @app.errorhandler(413)
    def request_too_large(_error):
        return jsonify({
            "code": 413,
            "msg": "请求内容超过允许的大小",
            "error_code": "REQUEST_TOO_LARGE",
        }), 413

    return app
