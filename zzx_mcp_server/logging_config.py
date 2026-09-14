"""Logging setup for MCP with credential redaction."""
import logging
import re


_SECRET_PATTERN = re.compile(
    r"(?i)((?:api[_-]?key|authorization|cookie|password|secret|token|key)"
    r"\s*[:=]\s*)[^\s,;]+"
)
_BEARER_PATTERN = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+")


class RedactingFilter(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        message = _BEARER_PATTERN.sub(r"\1[REDACTED]", message)
        record.msg = _SECRET_PATTERN.sub(r"\1[REDACTED]", message)
        record.args = ()
        return True


def configure_logging(level):
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
    secret_filter = RedactingFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(secret_filter)
