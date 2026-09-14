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

    # Initialise database tables on startup
    if initialize_database:
        with app.app_context():
            from app.auth import init_db
            from app.chat_history import init_tables as init_chat_tables
            init_db()
            init_chat_tables()

    # Minimal CORS via after_request
    @app.after_request
    def add_cors(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
        return response

    # Register route blueprints
    from app.routes.manus import manus_bp
    from app.routes.love_app import love_bp
    from app.auth import auth_bp
    from app.routes.session import session_bp
    app.register_blueprint(manus_bp)
    app.register_blueprint(love_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(session_bp)

    # Health check
    @app.route("/api/health")
    def health():
        return jsonify({
            "status": "ok",
            "mode": app.config["SYSTEM_NAME"],
            "environment": app.config["APP_ENV"],
        })

    return app
