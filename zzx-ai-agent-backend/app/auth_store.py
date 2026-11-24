"""Redis-backed login sessions and JWT revocation state."""
import logging
import time

from flask import current_app
from redis.exceptions import RedisError, WatchError

from app.extensions import get_redis


logger = logging.getLogger(__name__)


class AuthStoreUnavailable(RuntimeError):
    """Raised when security state cannot be read from Redis."""


def _prefix():
    return current_app.config["REDIS_AUTH_PREFIX"]


def _session_key(session_id):
    return f"{_prefix()}:session:{session_id}"


def _user_sessions_key(user_id):
    return f"{_prefix()}:user_sessions:{user_id}"


def _revoked_key(jti):
    return f"{_prefix()}:revoked:{jti}"


def _ttl(expires_at):
    return max(1, int(expires_at) - int(time.time()))


def create_login_session(user_id, session_id, refresh_jti, expires_at):
    """Persist a refresh-token family and its current token identifier."""
    try:
        client = get_redis()
        session_key = _session_key(session_id)
        user_sessions_key = _user_sessions_key(user_id)
        ttl = _ttl(expires_at)
        with client.pipeline(transaction=True) as pipe:
            pipe.hset(
                session_key,
                mapping={
                    "user_id": str(user_id),
                    "refresh_jti": refresh_jti,
                    "status": "active",
                },
            )
            pipe.expire(session_key, ttl)
            pipe.sadd(user_sessions_key, session_id)
            pipe.expire(user_sessions_key, ttl)
            pipe.execute()
    except RedisError as exc:
        logger.exception("Unable to create Redis login session")
        raise AuthStoreUnavailable("认证服务暂时不可用") from exc


def rotate_refresh_token(session_id, old_jti, new_jti, expires_at):
    """Atomically replace the current refresh token for one login session."""
    client = get_redis()
    key = _session_key(session_id)
    try:
        for _ in range(3):
            try:
                with client.pipeline() as pipe:
                    pipe.watch(key)
                    current = pipe.hgetall(key)
                    if (
                        not current
                        or current.get("status") != "active"
                        or current.get("refresh_jti") != old_jti
                    ):
                        pipe.unwatch()
                        return False
                    pipe.multi()
                    pipe.hset(key, "refresh_jti", new_jti)
                    ttl = _ttl(expires_at)
                    pipe.expire(key, ttl)
                    pipe.expire(
                        _user_sessions_key(current["user_id"]), ttl
                    )
                    pipe.execute()
                    return True
            except WatchError:
                continue
        return False
    except RedisError as exc:
        logger.exception("Unable to rotate Redis refresh token")
        raise AuthStoreUnavailable("认证服务暂时不可用") from exc


def revoke_token(jti, expires_at):
    """Block a JWT until its natural expiration time."""
    if not jti:
        return
    try:
        get_redis().set(_revoked_key(jti), "1", ex=_ttl(expires_at))
    except RedisError as exc:
        logger.exception("Unable to revoke JWT")
        raise AuthStoreUnavailable("认证服务暂时不可用") from exc


def revoke_login_session(user_id, session_id):
    """Revoke one device/login session."""
    if not session_id:
        return
    try:
        client = get_redis()
        with client.pipeline(transaction=True) as pipe:
            pipe.delete(_session_key(session_id))
            pipe.srem(_user_sessions_key(user_id), session_id)
            pipe.execute()
    except RedisError as exc:
        logger.exception("Unable to revoke Redis login session")
        raise AuthStoreUnavailable("认证服务暂时不可用") from exc


def revoke_all_login_sessions(user_id):
    """Revoke every tracked login session for a user."""
    try:
        client = get_redis()
        user_key = _user_sessions_key(user_id)
        session_ids = client.smembers(user_key)
        with client.pipeline(transaction=True) as pipe:
            for session_id in session_ids:
                pipe.delete(_session_key(session_id))
            pipe.delete(user_key)
            pipe.execute()
        return len(session_ids)
    except RedisError as exc:
        logger.exception("Unable to revoke all Redis login sessions")
        raise AuthStoreUnavailable("认证服务暂时不可用") from exc


def is_token_revoked(jwt_payload):
    """Fail closed when a token is revoked, untracked, or Redis is unavailable."""
    try:
        client = get_redis()
        jti = jwt_payload.get("jti", "")
        if not jti or client.exists(_revoked_key(jti)):
            return True

        session_id = jwt_payload.get("sid", "")
        if not session_id:
            return True

        login_session = client.hgetall(_session_key(session_id))
        if not login_session or login_session.get("status") != "active":
            return True
        if login_session.get("user_id") != str(jwt_payload.get("sub", "")):
            return True
        if (
            jwt_payload.get("type") == "refresh"
            and login_session.get("refresh_jti") != jti
        ):
            return True
        return False
    except RedisError:
        logger.exception("Unable to verify Redis JWT state; denying request")
        return True


def redis_is_ready():
    """Check Redis connectivity without exposing connection details."""
    try:
        return bool(get_redis().ping())
    except RedisError:
        return False
