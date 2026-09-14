"""Environment configuration for the standalone MCP server."""
import os
from pathlib import Path

from dotenv import load_dotenv


_SERVICE_DIR = Path(__file__).resolve().parent
_REPOSITORY_DIR = _SERVICE_DIR.parent
load_dotenv(_SERVICE_DIR / ".env")
load_dotenv(_REPOSITORY_DIR / ".env")


def _env(name, default=""):
    return os.getenv(name, default).strip()


APP_ENV = _env("APP_ENV", "development").lower()
if APP_ENV in {"dev"}:
    APP_ENV = "development"
elif APP_ENV in {"prod"}:
    APP_ENV = "production"
elif APP_ENV in {"testing"}:
    APP_ENV = "test"

if APP_ENV not in {"development", "test", "production"}:
    raise RuntimeError("APP_ENV must be one of: development, test, production")

SENIVERSE_API_KEY = _env("SENIVERSE_API_KEY")
MCP_HOST = _env("MCP_HOST", "127.0.0.1")
MCP_PORT = int(_env("MCP_PORT", "8000"))
MCP_PATH = _env("MCP_PATH", "/mcp")
LOG_LEVEL = _env("LOG_LEVEL", "INFO").upper()

if APP_ENV == "test" and not SENIVERSE_API_KEY:
    SENIVERSE_API_KEY = "test-only-weather-key"


def validate_mcp_config():
    """Reject missing credentials and unsafe production placeholders."""
    if not SENIVERSE_API_KEY:
        raise RuntimeError("Missing required environment variable: SENIVERSE_API_KEY")
    if not MCP_PATH.startswith("/"):
        raise RuntimeError("MCP_PATH must start with '/'")
    if APP_ENV == "production":
        value = SENIVERSE_API_KEY.lower()
        if any(marker in value for marker in ("change-me", "replace-with", "example", "test-only")):
            raise RuntimeError(
                "SENIVERSE_API_KEY contains an unsafe production placeholder"
            )
