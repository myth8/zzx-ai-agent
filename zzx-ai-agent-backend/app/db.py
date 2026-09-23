"""Pooled MySQL access and explicit transaction boundaries."""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager

from flask import current_app
import pymysql
from sqlalchemy import create_engine
from sqlalchemy.engine import URL


logger = logging.getLogger(__name__)
_ENGINE_EXTENSION_KEY = "mysql_engine"


def init_db_engine(app):
    """Create one process-local SQLAlchemy pool for raw PyMySQL connections."""
    url = URL.create(
        "mysql+pymysql",
        username=app.config["MYSQL_USER"],
        password=app.config["MYSQL_PASSWORD"],
        host=app.config["MYSQL_HOST"],
        port=app.config["MYSQL_PORT"],
        database=app.config["MYSQL_DB"],
        query={"charset": "utf8mb4"},
    )
    engine = create_engine(
        url,
        pool_size=app.config["MYSQL_POOL_SIZE"],
        max_overflow=app.config["MYSQL_MAX_OVERFLOW"],
        pool_timeout=app.config["MYSQL_POOL_TIMEOUT"],
        pool_recycle=app.config["MYSQL_POOL_RECYCLE"],
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": app.config["MYSQL_CONNECT_TIMEOUT"],
            "read_timeout": app.config["MYSQL_READ_TIMEOUT"],
            "write_timeout": app.config["MYSQL_WRITE_TIMEOUT"],
        },
    )
    app.extensions[_ENGINE_EXTENSION_KEY] = engine
    return engine


def get_engine():
    engine = current_app.extensions.get(_ENGINE_EXTENSION_KEY)
    if engine is None:
        engine = init_db_engine(current_app)
    return engine


def get_db_connection():
    """Checkout a pooled DBAPI connection; close() returns it to the pool."""
    raw = get_engine().raw_connection()
    threshold = current_app.config["MYSQL_SLOW_QUERY_MS"] / 1000
    return _PooledDictConnection(raw, threshold)


class _TimedDictCursor:
    def __init__(self, cursor, slow_seconds):
        self._cursor = cursor
        self._slow_seconds = slow_seconds

    def _run(self, method, statement, *args, **kwargs):
        started = time.monotonic()
        try:
            return method(statement, *args, **kwargs)
        finally:
            elapsed = time.monotonic() - started
            if elapsed >= self._slow_seconds:
                operation = statement.lstrip().split(None, 1)[0].upper() if statement else "SQL"
                logger.warning(
                    "Slow database query operation=%s elapsed_ms=%.1f",
                    operation,
                    elapsed * 1000,
                )

    def execute(self, statement, *args, **kwargs):
        return self._run(self._cursor.execute, statement, *args, **kwargs)

    def executemany(self, statement, *args, **kwargs):
        return self._run(self._cursor.executemany, statement, *args, **kwargs)

    def __enter__(self):
        self._cursor.__enter__()
        return self

    def __exit__(self, *args):
        return self._cursor.__exit__(*args)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _PooledDictConnection:
    """Expose legacy DictCursor semantics while SQLAlchemy owns the pool."""
    def __init__(self, raw_connection, slow_seconds):
        self._raw_connection = raw_connection
        self._slow_seconds = slow_seconds

    def cursor(self, *args, **kwargs):
        if not args and "cursor" not in kwargs:
            args = (pymysql.cursors.DictCursor,)
        cursor = self._raw_connection.cursor(*args, **kwargs)
        return _TimedDictCursor(cursor, self._slow_seconds)

    def __getattr__(self, name):
        return getattr(self._raw_connection, name)


@contextmanager
def connection():
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction():
    """Commit on success and always roll back on an exception."""
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
