"""Shared Flask extensions."""
from flask import current_app
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from redis import Redis


jwt = JWTManager()
limiter = Limiter(key_func=get_remote_address, default_limits=[])


def init_extensions(app):
    """Bind extensions to an application instance."""
    jwt.init_app(app)
    # Test and small standalone Flask apps may only provide REDIS_URL. Always
    # use Redis storage so limits stay consistent across threads and workers.
    app.config.setdefault("RATELIMIT_STORAGE_URI", app.config["REDIS_URL"])
    app.config.setdefault("RATELIMIT_KEY_PREFIX", "zzx:ratelimit")
    app.config.setdefault("RATELIMIT_HEADERS_ENABLED", True)
    app.config.setdefault("RATELIMIT_SWALLOW_ERRORS", False)
    limiter.init_app(app)
    app.extensions["redis_client"] = Redis.from_url(
        app.config["REDIS_URL"],
        decode_responses=True,
        socket_connect_timeout=app.config["REDIS_CONNECT_TIMEOUT"],
        socket_timeout=app.config["REDIS_SOCKET_TIMEOUT"],
        health_check_interval=30,
    )


def get_redis():
    """Return the Redis client for the active Flask application."""
    return current_app.extensions["redis_client"]
