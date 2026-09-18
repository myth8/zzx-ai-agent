import os
import sys
import logging
from flask import Flask
from flask import jsonify
from werkzeug.middleware.proxy_fix import ProxyFix


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
    trusted_proxy_hops = app.config.get("TRUST_PROXY_HOPS", 0)
    if trusted_proxy_hops:
        # 只信任显式配置数量的反向代理，避免客户端伪造 X-Forwarded-For
        # 绕过基于来源 IP 的登录与注册限流。
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=trusted_proxy_hops,
            x_proto=trusted_proxy_hops,
            x_host=trusted_proxy_hops,
        )

    from app.utils.request_context import init_request_context
    init_request_context(app)

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
            "Authorization, Content-Type, X-CSRF-TOKEN, X-Request-ID"
        )
        response.headers["Access-Control-Expose-Headers"] = "X-Request-ID"
        # API 默认不应被浏览器解释为可执行页面。前端静态页面的 CSP 由 Nginx
        # 单独设置，因为只给 API 增加 CSP 无法保护 Vue 页面。
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
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

    from app.utils.responses import api_error

    @app.errorhandler(400)
    def bad_request(_error):
        return api_error("BAD_REQUEST", "请求格式不正确", 400)

    @app.errorhandler(404)
    def not_found(_error):
        return api_error("NOT_FOUND", "请求的资源不存在", 404)

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return api_error("METHOD_NOT_ALLOWED", "请求方法不允许", 405)

    @app.errorhandler(413)
    def request_too_large(_error):
        return api_error("REQUEST_TOO_LARGE", "请求内容超过允许的大小", 413)

    @app.errorhandler(429)
    def rate_limit_exceeded(_error):
        return api_error(
            "RATE_LIMIT_EXCEEDED",
            "请求过于频繁，请稍后重试",
            429,
        )

    @app.errorhandler(Exception)
    def unhandled_error(error):
        logging.getLogger(__name__).error(
            "Unhandled request error",
            exc_info=(type(error), error, error.__traceback__),
        )
        return api_error("INTERNAL_ERROR", "服务暂时不可用，请稍后重试", 500)

    return app
