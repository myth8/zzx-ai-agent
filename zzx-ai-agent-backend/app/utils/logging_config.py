"""Central logging setup with conservative secret redaction."""
import logging
import re

from flask import g, has_request_context


_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(
        r"(?i)((?:api[_-]?key|authorization|cookie|jwt[_-]?secret|"
        r"password|token)\s*[:=]\s*)[^\s,;]+"
    ),
)


def redact(value):
    """Remove common credential forms from a log message."""
    text = str(value)
    text = _PATTERNS[0].sub(r"\1[REDACTED]", text)
    text = _PATTERNS[1].sub(r"\1[REDACTED]", text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record):
        record.msg = redact(record.getMessage())
        record.args = ()
        record.request_id = (
            getattr(g, "request_id", "-") if has_request_context() else "-"
        )
        return True


class RedactingFormatter(logging.Formatter):
    """连同异常堆栈一起脱敏；Filter 单独处理 record.msg 并不覆盖 traceback。"""

    def format(self, record):
        return redact(super().format(record))


def configure_logging(level="INFO"):
    """Configure root logging and attach redaction to every root handler."""
    resolved_level = getattr(logging, str(level).upper(), logging.INFO)
    logging.basicConfig(
        level=resolved_level,
        format=(
            "%(asctime)s %(levelname)s %(name)s "
            "request_id=%(request_id)s %(message)s"
        ),
        force=True,
    )
    redacting_filter = RedactingFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(redacting_filter)
        handler.setFormatter(RedactingFormatter(
            "%(asctime)s %(levelname)s %(name)s "
            "request_id=%(request_id)s %(message)s"
        ))
