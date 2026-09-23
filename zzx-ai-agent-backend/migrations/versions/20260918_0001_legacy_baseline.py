"""Create the legacy baseline on an empty database.

Revision ID: 20260918_0001
Revises: None
"""
from alembic import op
import sqlalchemy as sa


revision = "20260918_0001"
down_revision = None
branch_labels = None
depends_on = None


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade():
    tables = _tables()
    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("username", sa.String(50), nullable=False),
            sa.Column("nickname", sa.String(50), nullable=False),
            sa.Column("password", sa.String(255), nullable=False),
            sa.Column("role", sa.String(32), nullable=False, server_default="user"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("username", name="uq_users_username"),
            mysql_charset="utf8mb4",
        )
        op.create_index("idx_users_role", "users", ["role"])
    tables = _tables()
    if "sessions" not in tables:
        op.create_table(
            "sessions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("session_id", sa.String(100), nullable=False),
            sa.Column("chat_type", sa.String(20), nullable=False),
            sa.Column("title", sa.String(200), server_default="新对话"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("session_id", name="uq_sessions_session_id"),
            mysql_charset="utf8mb4",
        )
        op.create_index("idx_user_id", "sessions", ["user_id"])
        op.create_index("idx_user_chat_type", "sessions", ["user_id", "chat_type"])
    tables = _tables()
    if "chat_messages" not in tables:
        op.create_table(
            "chat_messages",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("session_id", sa.String(100), nullable=False),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("msg_order", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            mysql_charset="utf8mb4",
        )
        op.create_index("idx_session_id", "chat_messages", ["session_id"])
        op.create_index("idx_session_order", "chat_messages", ["session_id", "msg_order"])
    tables = _tables()
    if "chat_summaries" not in tables:
        op.create_table(
            "chat_summaries",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("session_id", sa.String(100), nullable=False),
            sa.Column("summary", sa.Text()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("session_id", name="uq_chat_summaries_session_id"),
            mysql_charset="utf8mb4",
        )
    tables = _tables()
    if "rag_documents" not in tables:
        op.create_table(
            "rag_documents",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("filename", sa.String(255), nullable=False, unique=True),
            sa.Column("display_name", sa.String(255), nullable=False),
            sa.Column("file_size", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("sha256", sa.String(64), nullable=False),
            sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("document_metadata", sa.JSON()),
            sa.Column("status", sa.String(20), nullable=False, server_default="ready"),
            sa.Column("last_error", sa.String(500)),
            sa.Column("uploaded_by", sa.Integer()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")),
            mysql_charset="utf8mb4",
        )
        op.create_index("idx_rag_documents_status", "rag_documents", ["status"])
        op.create_index("idx_rag_documents_uploader", "rag_documents", ["uploaded_by"])
    tables = _tables()
    if "rag_document_chunks" not in tables:
        op.create_table(
            "rag_document_chunks",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("document_id", sa.Integer(), nullable=False),
            sa.Column("chunk_id", sa.String(24), nullable=False, unique=True),
            sa.Column("chunk_index", sa.Integer(), nullable=False),
            sa.Column("content", sa.Text().with_variant(sa.Text(length=2**32-1), "mysql"), nullable=False),
            sa.Column("content_sha256", sa.String(64), nullable=False),
            sa.Column("char_count", sa.Integer(), nullable=False),
            sa.Column("section_title", sa.String(500)),
            sa.Column("metadata", sa.JSON()),
            sa.Column("vector_id", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["document_id"], ["rag_documents.id"], name="fk_rag_chunks_document", ondelete="CASCADE"),
            sa.UniqueConstraint("document_id", "chunk_index", name="uk_rag_chunks_document_index"),
            mysql_charset="utf8mb4",
        )
        op.create_index("idx_rag_chunks_document", "rag_document_chunks", ["document_id"])
        op.create_index("idx_rag_chunks_content_sha256", "rag_document_chunks", ["content_sha256"])


def downgrade():
    # The baseline may have adopted pre-existing production tables. Never drop
    # those tables automatically from the baseline revision.
    pass
