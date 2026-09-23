"""Runtime database schema checks; schema mutation belongs to Alembic."""
from app.db import connection


class DatabaseMigrationRequired(RuntimeError):
    pass


def verify_database_schema():
    try:
        with connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT version_num FROM alembic_version LIMIT 1")
            row = cur.fetchone()
    except Exception as exc:
        raise DatabaseMigrationRequired(
            "数据库尚未完成迁移，请先在后端目录执行 alembic upgrade head"
        ) from exc
    if not row:
        raise DatabaseMigrationRequired("数据库迁移版本为空，请执行 alembic upgrade head")
