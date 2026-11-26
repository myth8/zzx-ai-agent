"""Persist redacted Agent run telemetry for the admin observability page.

Revision ID: 20261124_0003
Revises: 20260918_0002
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "20261124_0003"
down_revision = "20260918_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_telemetry_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_id", sa.String(64)),
        sa.Column("session_id", sa.String(100)),
        sa.Column("user_id", sa.Integer()),
        sa.Column("engine", sa.String(32), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("started_at", mysql.DATETIME(fsp=6), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP(6)")),
        sa.Column("finished_at", mysql.DATETIME(fsp=6)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("steps", sa.Integer(), server_default="0"),
        sa.Column("tool_calls", sa.Integer(), server_default="0"),
        sa.Column("tool_errors", sa.Integer(), server_default="0"),
        sa.Column("prompt_tokens", sa.Integer(), server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), server_default="0"),
        sa.Column("total_tokens", sa.Integer(), server_default="0"),
        sa.Column("context", mysql.JSON()),
        sa.Column("output_chars", sa.Integer(), server_default="0"),
        sa.Column("error_type", sa.String(100)),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP(6)")),
        sa.CheckConstraint(
            "status IN ('running','succeeded','failed','cancelled')",
            name="ck_agent_telemetry_runs_status",
        ),
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_agent_telemetry_started", "agent_telemetry_runs", ["started_at"])
    op.create_index("idx_agent_telemetry_engine_time", "agent_telemetry_runs", ["engine", "started_at"])
    op.create_index("idx_agent_telemetry_session", "agent_telemetry_runs", ["session_id"])

    op.create_table(
        "agent_telemetry_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("payload", mysql.JSON(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP(6)")),
        sa.ForeignKeyConstraint(
            ["run_id"], ["agent_telemetry_runs.id"],
            name="fk_agent_telemetry_events_run", ondelete="CASCADE",
        ),
        sa.UniqueConstraint("run_id", "seq", name="uq_agent_telemetry_event_seq"),
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_agent_telemetry_events_run", "agent_telemetry_events", ["run_id", "seq"])
    op.create_index("idx_agent_telemetry_events_type", "agent_telemetry_events", ["event_type", "created_at"])


def downgrade():
    op.drop_table("agent_telemetry_events")
    op.drop_table("agent_telemetry_runs")
