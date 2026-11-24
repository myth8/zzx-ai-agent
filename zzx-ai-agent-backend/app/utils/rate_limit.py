"""差异化限流策略及稳定的匿名、账号和登录用户键。"""
import hashlib
import unicodedata

from flask import current_app, request
from flask_limiter.util import get_remote_address

from app.extensions import limiter


def _configured(name, fallback):
    return lambda: current_app.config.get(name, fallback)


def remote_ip_key():
    return f"ip:{get_remote_address()}"


def login_account_key():
    """账号键使用摘要，避免用户名以明文形式进入 Redis key。"""
    data = request.get_json(silent=True) or {}
    username = unicodedata.normalize(
        "NFKC", str(data.get("username") or "").strip().lower()
    )
    digest = hashlib.sha256(username.encode("utf-8")).hexdigest()[:24]
    return f"login-account:{digest}"


def current_user_key():
    user = getattr(request, "current_user", None) or {}
    user_id = user.get("user_id")
    return f"user:{user_id}" if user_id is not None else remote_ip_key()


register_rate_limit = limiter.shared_limit(
    _configured("REGISTER_RATE_LIMIT", "5 per hour"),
    scope="auth-register",
    key_func=remote_ip_key,
)
login_ip_rate_limit = limiter.shared_limit(
    _configured("LOGIN_IP_RATE_LIMIT", "20 per minute"),
    scope="auth-login-ip",
    key_func=remote_ip_key,
)
login_account_rate_limit = limiter.shared_limit(
    _configured("LOGIN_ACCOUNT_RATE_LIMIT", "5 per minute"),
    scope="auth-login-account",
    key_func=login_account_key,
)
chat_rate_limit = limiter.shared_limit(
    _configured("CHAT_RATE_LIMIT", "12 per minute"),
    scope="chat-stream",
    key_func=current_user_key,
)
admin_read_rate_limit = limiter.shared_limit(
    _configured("ADMIN_READ_RATE_LIMIT", "120 per minute"),
    scope="rag-admin-read",
    key_func=current_user_key,
)
admin_write_rate_limit = limiter.shared_limit(
    _configured("ADMIN_WRITE_RATE_LIMIT", "6 per minute"),
    scope="admin-write",
    key_func=current_user_key,
)
