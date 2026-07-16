from flask import Flask
from flask import jsonify


def create_app():
    """Flask application factory."""
    app = Flask(__name__)
    app.config.from_object("app.config.Config")

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
    app.register_blueprint(manus_bp)
    app.register_blueprint(love_bp)

    # Health check
    @app.route("/api/health")
    def health():
        from app.config import Config
        return jsonify({"status": "ok", "mode": Config.LLM_MODE})

    return app
