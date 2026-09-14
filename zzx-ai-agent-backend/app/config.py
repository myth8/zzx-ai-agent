"""Environment-aware application configuration.

Local values are loaded from zzx-ai-agent-backend/.env and then the repository
root .env. Existing process environment values always have highest priority.
"""
import os
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

    @classmethod
    def validate(cls):
        """Fail fast when required runtime configuration is unsafe or missing."""
        required = (
            "DEEPSEEK_API_KEY",
            "MYSQL_USER",
            "MYSQL_PASSWORD",
            "MYSQL_DB",
            "JWT_SECRET",
        )
        missing = [name for name in required if not getattr(cls, name, "")]
        if missing:
            raise RuntimeError(
                "Missing required environment variables: " + ", ".join(missing)
            )

        if cls.APP_ENV == "production":
            unsafe_markers = ("change-me", "replace-with", "example", "test-only")
            unsafe = []
            for name in ("DEEPSEEK_API_KEY", "MYSQL_PASSWORD", "JWT_SECRET"):
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


class ProductionConfig(BaseConfig):
    APP_ENV = "production"
    DEBUG = False


CONFIG_BY_ENV = {
    "development": DevelopmentConfig,
    "test": TestConfig,
    "production": ProductionConfig,
}

Config = CONFIG_BY_ENV[BaseConfig.APP_ENV]
