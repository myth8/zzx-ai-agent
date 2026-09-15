"""Shared Flask extensions."""
from flask import current_app
from flask_jwt_extended import JWTManager
from redis import Redis


jwt = JWTManager()


def init_extensions(app):
    """Bind extensions to an application instance."""
    jwt.init_app(app)
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
