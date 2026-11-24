"""Stage 1.1-1.5 constraints, UUIDs, runs and idempotency.

Revision ID: 20260918_0002
Revises: 20260918_0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "20260918_0002"
down_revision = "20260918_0001"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _columns(table):
    return {item["name"] for item in _inspector().get_columns(table)}


def _indexes(table):
    return {item["name"] for item in _inspector().get_indexes(table)}


def _foreign_keys(table):
    return {item["name"] for item in _inspector().get_foreign_keys(table)}


def _archive_orphans():
    op.execute("""
        CREATE TABLE IF NOT EXISTS migration_orphan_records (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            source_table VARCHAR(64) NOT NULL,
            source_key VARCHAR(191) NOT NULL,
            payload JSON NOT NULL,
            reason VARCHAR(255) NOT NULL,
            archived_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            INDEX idx_migration_orphan_source (source_table, source_key)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    op.execute("""
        INSERT INTO migration_orphan_records (source_table, source_key, payload, reason)
        SELECT 'chat_messages', CAST(m.id AS CHAR),
               JSON_OBJECT('id',m.id,'session_id',m.session_id,'role',m.role,
                           'content',m.content,'msg_order',m.msg_order,'created_at',m.created_at),
               'session owner missing before user foreign key migration'
        FROM chat_messages m JOIN sessions s ON s.session_id=m.session_id
        LEFT JOIN users u ON u.id=s.user_id WHERE u.id IS NULL
    """)
    op.execute("""
        INSERT INTO migration_orphan_records (source_table, source_key, payload, reason)
        SELECT 'chat_summaries', CAST(cs.id AS CHAR),
               JSON_OBJECT('id',cs.id,'session_id',cs.session_id,'summary',cs.summary,
                           'updated_at',cs.updated_at),
               'session owner missing before user foreign key migration'
        FROM chat_summaries cs JOIN sessions s ON s.session_id=cs.session_id
        LEFT JOIN users u ON u.id=s.user_id WHERE u.id IS NULL
    """)
    op.execute("""
        INSERT INTO migration_orphan_records (source_table, source_key, payload, reason)
        SELECT 'sessions', CAST(s.id AS CHAR),
               JSON_OBJECT('id',s.id,'user_id',s.user_id,'session_id',s.session_id,
                           'chat_type',s.chat_type,'title',s.title,
                           'created_at',s.created_at,'updated_at',s.updated_at),
               'user row missing before foreign key migration'
        FROM sessions s LEFT JOIN users u ON u.id=s.user_id WHERE u.id IS NULL
    """)
    op.execute("DELETE m FROM chat_messages m JOIN sessions s ON s.session_id=m.session_id LEFT JOIN users u ON u.id=s.user_id WHERE u.id IS NULL")
    op.execute("DELETE cs FROM chat_summaries cs JOIN sessions s ON s.session_id=cs.session_id LEFT JOIN users u ON u.id=s.user_id WHERE u.id IS NULL")
    op.execute("DELETE s FROM sessions s LEFT JOIN users u ON u.id=s.user_id WHERE u.id IS NULL")


def upgrade():
    _archive_orphans()
    if "next_message_order" not in _columns("sessions"):
        op.add_column("sessions", sa.Column("next_message_order", sa.Integer(), nullable=False, server_default="1"))
    if "version" not in _columns("sessions"):
        op.add_column("sessions", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.execute("""
        UPDATE sessions s LEFT JOIN (
            SELECT session_id, COALESCE(MAX(msg_order),0)+1 AS next_order
            FROM chat_messages GROUP BY session_id
        ) m ON m.session_id=s.session_id
        SET s.next_message_order=COALESCE(m.next_order,1),
            s.updated_at=GREATEST(s.updated_at, COALESCE((SELECT MAX(cm.created_at) FROM chat_messages cm WHERE cm.session_id=s.session_id), s.updated_at))
    """)
    if "message_id" not in _columns("chat_messages"):
        op.add_column("chat_messages", sa.Column("message_id", sa.String(36), nullable=True))
        op.execute("UPDATE chat_messages SET message_id=UUID() WHERE message_id IS NULL")
        op.alter_column("chat_messages", "message_id", existing_type=sa.String(36), nullable=False)
    if "client_message_id" not in _columns("chat_messages"):
        op.add_column("chat_messages", sa.Column("client_message_id", sa.String(36), nullable=True))
    indexes = _indexes("sessions")
    if "idx_sessions_user_updated" not in indexes:
        op.create_index("idx_sessions_user_updated", "sessions", ["user_id", "updated_at", "id"])
    indexes = _indexes("chat_messages")
    if "uq_chat_messages_message_id" not in indexes:
        op.create_index("uq_chat_messages_message_id", "chat_messages", ["message_id"], unique=True)
    if "uq_chat_messages_session_order" not in indexes:
        op.create_index("uq_chat_messages_session_order", "chat_messages", ["session_id", "msg_order"], unique=True)
    if "uq_chat_messages_client_id" not in indexes:
        op.create_index("uq_chat_messages_client_id", "chat_messages", ["session_id", "client_message_id"], unique=True)
    fks = _foreign_keys("sessions")
    if "fk_sessions_user" not in fks:
        op.create_foreign_key("fk_sessions_user", "sessions", "users", ["user_id"], ["id"], ondelete="CASCADE")
    fks = _foreign_keys("chat_messages")
    if "fk_chat_messages_session" not in fks:
        op.create_foreign_key("fk_chat_messages_session", "chat_messages", "sessions", ["session_id"], ["session_id"], ondelete="CASCADE")
    fks = _foreign_keys("chat_summaries")
    if "fk_chat_summaries_session" not in fks:
        op.create_foreign_key("fk_chat_summaries_session", "chat_summaries", "sessions", ["session_id"], ["session_id"], ondelete="CASCADE")

    op.create_table(
        "chat_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(100), nullable=False),
        sa.Column("user_message_id", sa.String(36), nullable=False),
        sa.Column("assistant_message_id", sa.String(36)),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("model", sa.String(100)),
        sa.Column("agent_type", sa.String(32), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.String(500)),
        sa.Column("prompt_tokens", sa.Integer()),
        sa.Column("completion_tokens", sa.Integer()),
        sa.Column("total_tokens", sa.Integer()),
        sa.Column("estimated_cost", sa.Numeric(18, 8)),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
        sa.Column("started_at", mysql.DATETIME(fsp=6)),
        sa.Column("finished_at", mysql.DATETIME(fsp=6)),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)")),
        sa.CheckConstraint("status IN ('queued','running','succeeded','failed','cancelled','timed_out')", name="ck_chat_runs_status"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_chat_runs_user", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.session_id"], name="fk_chat_runs_session", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_message_id"], ["chat_messages.message_id"], name="fk_chat_runs_user_message", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assistant_message_id"], ["chat_messages.message_id"], name="fk_chat_runs_assistant_message", ondelete="SET NULL"),
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_chat_runs_lookup", "chat_runs", ["user_id", "session_id", "status", "created_at"])
    op.create_index("idx_chat_runs_session_created", "chat_runs", ["session_id", "created_at"])

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.String(191), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(32)),
        sa.Column("resource_id", sa.String(100)),
        sa.Column("response_status", sa.SmallInteger()),
        sa.Column("response_body", mysql.JSON()),
        sa.Column("status", sa.String(20), nullable=False, server_default="processing"),
        sa.Column("locked_until", mysql.DATETIME(fsp=6)),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)")),
        sa.CheckConstraint("status IN ('processing','completed','failed')", name="ck_idempotency_status"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_idempotency_user", ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "endpoint", "idempotency_key", name="uq_idempotency_scope_key"),
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_idempotency_expiry", "idempotency_records", ["expires_at"])
    op.create_index("idx_idempotency_resource", "idempotency_records", ["resource_type", "resource_id"])


def downgrade():
    op.drop_table("idempotency_records")
    op.drop_table("chat_runs")
    for table, constraint in (
        ("chat_summaries", "fk_chat_summaries_session"),
        ("chat_messages", "fk_chat_messages_session"),
        ("sessions", "fk_sessions_user"),
    ):
        if constraint in _foreign_keys(table):
            op.drop_constraint(constraint, table, type_="foreignkey")
    for name in ("uq_chat_messages_client_id", "uq_chat_messages_session_order", "uq_chat_messages_message_id"):
        if name in _indexes("chat_messages"):
            op.drop_index(name, table_name="chat_messages")
    if "idx_sessions_user_updated" in _indexes("sessions"):
        op.drop_index("idx_sessions_user_updated", table_name="sessions")
    for column in ("client_message_id", "message_id"):
        if column in _columns("chat_messages"):
            op.drop_column("chat_messages", column)
    for column in ("version", "next_message_order"):
        if column in _columns("sessions"):
            op.drop_column("sessions", column)
