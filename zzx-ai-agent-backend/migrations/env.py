from logging.config import fileConfig
import os
from pathlib import Path

from alembic import context
from dotenv import dotenv_values
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import URL


config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)


def database_url():
    values = {}
    for candidate in (Path(__file__).resolve().parents[1] / ".env", Path.cwd().parent / ".env"):
        if candidate.exists():
            values.update({k: v for k, v in dotenv_values(candidate).items() if v is not None})
    values.update(os.environ)
    return URL.create(
        "mysql+pymysql",
        username=values.get("MYSQL_USER"),
        password=values.get("MYSQL_PASSWORD"),
        host=values.get("MYSQL_HOST", "127.0.0.1"),
        port=int(values.get("MYSQL_PORT", "3306")),
        database=values.get("MYSQL_DB", "zzx_agent_db"),
        query={"charset": "utf8mb4"},
    )


def run_migrations_offline():
    context.configure(
        url=database_url(), literal_binds=True, dialect_opts={"paramstyle": "named"}
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = database_url().render_as_string(hide_password=False)
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_offline() if context.is_offline_mode() else run_migrations_online()
