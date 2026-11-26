"""Store the original question and final answer for the admin view.

Revision ID: 20261124_0004
Revises: 20261124_0003
"""
from alembic import op
import sqlalchemy as sa


revision = "20261124_0004"
down_revision = "20261124_0003"
branch_labels = None
depends_on = None


def _columns():
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns("agent_telemetry_runs")}


def upgrade():
    columns = _columns()
    if "input_text" not in columns:
        op.add_column("agent_telemetry_runs", sa.Column("input_text", sa.Text()))
    if "output_text" not in columns:
        op.add_column("agent_telemetry_runs", sa.Column("output_text", sa.Text()))


def downgrade():
    columns = _columns()
    if "output_text" in columns:
        op.drop_column("agent_telemetry_runs", "output_text")
    if "input_text" in columns:
        op.drop_column("agent_telemetry_runs", "input_text")
