"""Environment-aware application configuration.

Local values are loaded from zzx-ai-agent-backend/.env and then the repository
root .env. Existing process environment values always have highest priority.

.env 决定具体配置值。
APP_ENV 决定使用哪一套配置规则。
config.py 将二者组合、校验后交给 Flask。
"""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv


_BACKEND_DIR = Path(__file__).resolve().parents[1]
_REPOSITORY_DIR = _BACKEND_DIR.parent
load_dotenv(_BACKEND_DIR / ".env")
load_dotenv(_REPOSITORY_DIR / ".env")


def _env(name, default=""):
    return os.getenv(name, default).strip()


def _env_int(name, default):
    value = _env(name, str(default))
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def _env_path(name, default):
    value = Path(_env(name, str(default))).expanduser()
    if not value.is_absolute():
        value = _BACKEND_DIR / value
    return str(value.resolve())


def _environment():
    value = _env("APP_ENV", "development").lower()
    aliases = {"dev": "development", "prod": "production", "testing": "test"}
    value = aliases.get(value, value)
    if value not in {"development", "test", "production"}:
        raise RuntimeError(
            "APP_ENV must be one of: development, test, production"
        )
    return value


class BaseConfig:
    """Shared configuration for every environment."""

    APP_ENV = _environment()
    SYSTEM_NAME = _env("SYSTEM_NAME", "ZZX-AI-AGENT")
    DEBUG = False
    TESTING = False
    LOG_LEVEL = _env("LOG_LEVEL", "INFO").upper()

    # LLM
    DEEPSEEK_API_KEY = _env("DEEPSEEK_API_KEY")
    DEEPSEEK_API_BASE = _env(
        "DEEPSEEK_API_BASE", "https://api.deepseek.com/v1"
    )
    DEEPSEEK_MODEL = _env("DEEPSEEK_MODEL", "deepseek-chat")

    # MySQL
    MYSQL_HOST = _env("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT = _env_int("MYSQL_PORT", 3306)
    MYSQL_USER = _env("MYSQL_USER")
    MYSQL_PASSWORD = _env("MYSQL_PASSWORD")
    MYSQL_DB = _env("MYSQL_DB", "zzx_agent_db")
    MYSQL_POOL_SIZE = _env_int("MYSQL_POOL_SIZE", 8)
    MYSQL_MAX_OVERFLOW = _env_int("MYSQL_MAX_OVERFLOW", 4)
    MYSQL_POOL_TIMEOUT = _env_int("MYSQL_POOL_TIMEOUT", 10)
    MYSQL_POOL_RECYCLE = _env_int("MYSQL_POOL_RECYCLE", 1800)
    MYSQL_CONNECT_TIMEOUT = _env_int("MYSQL_CONNECT_TIMEOUT", 5)
    MYSQL_READ_TIMEOUT = _env_int("MYSQL_READ_TIMEOUT", 30)
    MYSQL_WRITE_TIMEOUT = _env_int("MYSQL_WRITE_TIMEOUT", 30)
    MYSQL_SLOW_QUERY_MS = _env_int("MYSQL_SLOW_QUERY_MS", 500)

    # JWT
    JWT_SECRET = _env("JWT_SECRET")
    JWT_SECRET_KEY = JWT_SECRET
    JWT_ALGORITHM = "HS256"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=_env_int("JWT_ACCESS_TOKEN_MINUTES", 30)
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        days=_env_int("JWT_REFRESH_TOKEN_DAYS", 14)
    )
    JWT_ENCODE_ISSUER = _env("JWT_ISSUER", "zzx-ai-agent")
    JWT_DECODE_ISSUER = JWT_ENCODE_ISSUER
    JWT_ENCODE_AUDIENCE = _env("JWT_AUDIENCE", "zzx-ai-agent-web")
    JWT_DECODE_AUDIENCE = JWT_ENCODE_AUDIENCE
    JWT_TOKEN_LOCATION = ["headers", "cookies"]
    JWT_REFRESH_COOKIE_PATH = "/api/auth"
    JWT_REFRESH_CSRF_COOKIE_PATH = "/"
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_CSRF_IN_COOKIES = True
    JWT_SESSION_COOKIE = False
    JWT_COOKIE_SECURE = APP_ENV == "production"
    JWT_COOKIE_SAMESITE = "Lax"

    # Reusable bootstrap code for creating/promoting administrators.
    ADMIN_INVITE_CODE = _env("ADMIN_INVITE_CODE")

    # Redis-backed auth state
    REDIS_URL = _env("REDIS_URL", "redis://127.0.0.1:6379/0")
    REDIS_AUTH_PREFIX = _env("REDIS_AUTH_PREFIX", "zzx:auth")
    REDIS_CONNECT_TIMEOUT = _env_int("REDIS_CONNECT_TIMEOUT", 2)
    REDIS_SOCKET_TIMEOUT = _env_int("REDIS_SOCKET_TIMEOUT", 2)

    # Redis-backed, cross-process API rate limits. Limit strings use the
    # Flask-Limiter syntax and can be tuned per deployment without code edits.
    RATELIMIT_STORAGE_URI = REDIS_URL
    RATELIMIT_KEY_PREFIX = _env("RATELIMIT_KEY_PREFIX", "zzx:ratelimit")
    RATELIMIT_STRATEGY = "fixed-window"
    RATELIMIT_HEADERS_ENABLED = True
    RATELIMIT_SWALLOW_ERRORS = False
    REGISTER_RATE_LIMIT = _env("REGISTER_RATE_LIMIT", "5 per hour")
    LOGIN_IP_RATE_LIMIT = _env("LOGIN_IP_RATE_LIMIT", "20 per minute")
    LOGIN_ACCOUNT_RATE_LIMIT = _env("LOGIN_ACCOUNT_RATE_LIMIT", "5 per minute")
    CHAT_RATE_LIMIT = _env("CHAT_RATE_LIMIT", "12 per minute")
    ADMIN_READ_RATE_LIMIT = _env("ADMIN_READ_RATE_LIMIT", "120 per minute")
    ADMIN_WRITE_RATE_LIMIT = _env("ADMIN_WRITE_RATE_LIMIT", "6 per minute")

    # Only enable this when Flask is behind exactly this many trusted proxies.
    TRUST_PROXY_HOPS = _env_int("TRUST_PROXY_HOPS", 0)

    # RAG document and vector index storage
    RAG_DOCUMENTS_DIR = _env_path("RAG_DOCUMENTS_DIR", "documents")
    RAG_CHROMA_DIR = _env_path("RAG_CHROMA_DIR", "chroma_db")
    RAG_MAX_FILE_SIZE_BYTES = _env_int("RAG_MAX_FILE_SIZE_MB", 5) * 1024 * 1024
    MAX_CONTENT_LENGTH = _env_int("MAX_REQUEST_SIZE_MB", 8) * 1024 * 1024

    # Browser origins allowed to send credentialed requests.
    CORS_ORIGINS = tuple(
        origin.strip()
        for origin in _env(
            "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",")
        if origin.strip()
    )

    @classmethod
    def validate(cls):
        """Fail fast when required runtime configuration is unsafe or missing."""
        required = (
            "DEEPSEEK_API_KEY",
            "MYSQL_USER",
            "MYSQL_PASSWORD",
            "MYSQL_DB",
            "JWT_SECRET",
            "ADMIN_INVITE_CODE",
            "REDIS_URL",
        )
        missing = [name for name in required if not getattr(cls, name, "")]
        if missing:
            raise RuntimeError(
                "Missing required environment variables: " + ", ".join(missing)
            )

        if cls.RAG_MAX_FILE_SIZE_BYTES <= 0:
            raise RuntimeError("RAG_MAX_FILE_SIZE_MB must be greater than zero")
        if cls.MAX_CONTENT_LENGTH < cls.RAG_MAX_FILE_SIZE_BYTES:
            raise RuntimeError(
                "MAX_REQUEST_SIZE_MB must not be smaller than RAG_MAX_FILE_SIZE_MB"
            )
        if cls.TRUST_PROXY_HOPS < 0:
            raise RuntimeError("TRUST_PROXY_HOPS must not be negative")
        positive_database_settings = (
            "MYSQL_POOL_SIZE",
            "MYSQL_POOL_TIMEOUT",
            "MYSQL_POOL_RECYCLE",
            "MYSQL_CONNECT_TIMEOUT",
            "MYSQL_READ_TIMEOUT",
            "MYSQL_WRITE_TIMEOUT",
            "MYSQL_SLOW_QUERY_MS",
        )
        invalid_database_settings = [
            name for name in positive_database_settings
            if getattr(cls, name) <= 0
        ]
        if cls.MYSQL_MAX_OVERFLOW < 0:
            invalid_database_settings.append("MYSQL_MAX_OVERFLOW")
        if invalid_database_settings:
            raise RuntimeError(
                "Database pool/timeouts must be positive: "
                + ", ".join(invalid_database_settings)
            )

        if cls.APP_ENV == "production":
            unsafe_markers = ("change-me", "replace-with", "example", "test-only")
            unsafe = []
            for name in (
                "DEEPSEEK_API_KEY",
                "MYSQL_PASSWORD",
                "JWT_SECRET",
                "ADMIN_INVITE_CODE",
            ):
                value = str(getattr(cls, name, "")).lower()
                if any(marker in value for marker in unsafe_markers):
                    unsafe.append(name)
            if unsafe:
                raise RuntimeError(
                    "Production secrets still contain placeholder values: "
                    + ", ".join(unsafe)
                )


class DevelopmentConfig(BaseConfig):
    APP_ENV = "development"
    DEBUG = True


class TestConfig(BaseConfig):
    APP_ENV = "test"
    TESTING = True
    DEBUG = False
    DEEPSEEK_API_KEY = _env("DEEPSEEK_API_KEY", "test-only-deepseek-key")
    MYSQL_USER = _env("MYSQL_USER", "test")
    MYSQL_PASSWORD = _env("MYSQL_PASSWORD", "test-only-database-password")
    MYSQL_DB = _env("MYSQL_DB", "zzx_agent_test")
    JWT_SECRET = _env("JWT_SECRET", "test-only-jwt-secret")
    JWT_SECRET_KEY = JWT_SECRET
    ADMIN_INVITE_CODE = _env("ADMIN_INVITE_CODE", "test-only-admin-invite")
    REDIS_URL = _env("REDIS_URL", "redis://127.0.0.1:6379/15")
    RATELIMIT_STORAGE_URI = REDIS_URL


class ProductionConfig(BaseConfig):
    APP_ENV = "production"
    DEBUG = False


CONFIG_BY_ENV = {
    "development": DevelopmentConfig,
    "test": TestConfig,
    "production": ProductionConfig,
}

Config = CONFIG_BY_ENV[BaseConfig.APP_ENV]
