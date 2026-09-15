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


class ProductionConfig(BaseConfig):
    APP_ENV = "production"
    DEBUG = False


CONFIG_BY_ENV = {
    "development": DevelopmentConfig,
    "test": TestConfig,
    "production": ProductionConfig,
}

Config = CONFIG_BY_ENV[BaseConfig.APP_ENV]
