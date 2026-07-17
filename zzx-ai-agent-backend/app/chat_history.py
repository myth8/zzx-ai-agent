"""
Chat History Management
=======================
Manages sessions, messages, and conversation summaries in MySQL.
Provides context building for multi-turn conversations.
"""
import uuid
import time
from datetime import datetime
from flask import current_app
import pymysql
from app.auth import get_db, login_required
from app.config import Config

# Number of recent messages to include in context
# Number of recent messages to include in context
RECENT_LIMIT = 50

# ── Table Initialisation ──────────────────────────────────────────

def init_tables():
    """Create sessions / chat_messages / chat_summaries tables."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id         INT AUTO_INCREMENT PRIMARY KEY,
                    user_id    INT NOT NULL,
                    session_id VARCHAR(100) NOT NULL UNIQUE,
                    chat_type  VARCHAR(20) NOT NULL COMMENT 'chain or agent',
                    title      VARCHAR(200) DEFAULT '\u65b0\u5bf9\u8bdd',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_user_id (user_id),
                    INDEX idx_user_chat_type (user_id, chat_type)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id         INT AUTO_INCREMENT PRIMARY KEY,
                    session_id VARCHAR(100) NOT NULL,
                    role       VARCHAR(20) NOT NULL COMMENT 'user or assistant',
                    content    TEXT NOT NULL,
                    msg_order  INT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_session_id (session_id),
                    INDEX idx_session_order (session_id, msg_order)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_summaries (
                    id         INT AUTO_INCREMENT PRIMARY KEY,
                    session_id VARCHAR(100) NOT NULL UNIQUE,
                    summary    TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_session_id (session_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        conn.commit()
    finally:
        conn.close()


# ── Session CRUD ──────────────────────────────────────────────────

def create_session(user_id, chat_type, title=None):
    """Create a new session, return session_id."""
    session_id = str(uuid.uuid4())[:8]
    if title is None:
        title = "\u65b0\u5bf9\u8bdd"
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (user_id, session_id, chat_type, title) VALUES (%s, %s, %s, %s)",
                (user_id, session_id, chat_type, title),
            )
        conn.commit()
    finally:
        conn.close()
    return session_id


def get_user_sessions(user_id, chat_type):
    """List sessions for a user, ordered by updated_at desc."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT session_id, title, chat_type, created_at, updated_at "
                "FROM sessions WHERE user_id=%s AND chat_type=%s ORDER BY updated_at DESC",
                (user_id, chat_type),
            )
            return cur.fetchall()
    finally:
        conn.close()


def rename_session(session_id, title):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE sessions SET title=%s WHERE session_id=%s", (title, session_id))
        conn.commit()
    finally:
        conn.close()


def delete_session(session_id):
    """Delete a session and all its messages and summary."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chat_messages WHERE session_id=%s", (session_id,))
            cur.execute("DELETE FROM chat_summaries WHERE session_id=%s", (session_id,))
            cur.execute("DELETE FROM sessions WHERE session_id=%s", (session_id,))
        conn.commit()
    finally:
        conn.close()


def get_session_title(session_id):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT title, chat_type FROM sessions WHERE session_id=%s", (session_id,))
            return cur.fetchone()
    finally:
        conn.close()


# ── Message CRUD ──────────────────────────────────────────────────

def save_message(session_id, role, content):
    """Save a message to the DB, auto-assign msg_order."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(msg_order), 0) + 1 AS next_order FROM chat_messages WHERE session_id=%s",
                (session_id,),
            )
            next_order = cur.fetchone()["next_order"]
            cur.execute(
                "INSERT INTO chat_messages (session_id, role, content, msg_order) VALUES (%s, %s, %s, %s)",
                (session_id, role, content, next_order),
            )
        conn.commit()
    finally:
        conn.close()


def get_session_messages(session_id):
    """Get all messages for a session, ordered by msg_order."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role, content, msg_order, created_at FROM chat_messages "
                "WHERE session_id=%s ORDER BY msg_order ASC",
                (session_id,),
            )
            return cur.fetchall()
    finally:
        conn.close()


def load_recent_messages(session_id, limit=RECENT_LIMIT):
    """Load the most recent N messages for context."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role, content FROM chat_messages "
                "WHERE session_id=%s ORDER BY msg_order DESC LIMIT %s",
                (session_id, limit),
            )
            rows = cur.fetchall()
            rows = list(reversed(rows))  # chronological order
            return rows
    finally:
        conn.close()


# ── Summary Management ────────────────────────────────────────────

def load_summary(session_id):
    """Load the summary text for a session."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT summary FROM chat_summaries WHERE session_id=%s",
                (session_id,),
            )
            row = cur.fetchone()
            return row["summary"] if row and row["summary"] else ""
    finally:
        conn.close()


def save_summary(session_id, summary_text):
    """Insert or update the summary for a session."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_summaries (session_id, summary) VALUES (%s, %s) "
                "ON DUPLICATE KEY UPDATE summary=%s",
                (session_id, summary_text, summary_text),
            )
        conn.commit()
    finally:
        conn.close()


def update_summary(session_id):
    """Auto-generate summary via LLM if there are enough new messages."""
    from app.llm import llm
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser

    recent = load_recent_messages(session_id, 20)
    if len(recent) < 2:
        return

    existing = load_summary(session_id)

    # Build new lines
    new_lines = ""
    for msg in recent:
        prefix = "\u7528\u6237" if msg["role"] == "user" else "AI"
        new_lines += f"{prefix}: {msg['content']}\n"

    prompt = ChatPromptTemplate.from_messages([
        ("human", (
            "\u8bf7\u5c06\u4ee5\u4e0b\u5bf9\u8bdd\u538b\u7f29\u4e3a\u4e2d\u6587\u6458\u8981\uff0c\u53ea\u4fdd\u7559\u4ee5\u4e0b\u4fe1\u606f\uff1a\n"
            "1. \u7528\u6237\u7684\u8eab\u4efd\u3001\u5174\u8da3\u3001\u76ee\u6807\n"
            "2. \u7528\u6237\u63d0\u51fa\u7684\u4e3b\u8981\u95ee\u9898\u6216\u8bf7\u6c42\n"
            "3. AI\u7ed9\u51fa\u7684\u5173\u952e\u56de\u7b54\u6216\u5efa\u8bae\n"
            "\u4e0d\u8981\u91cd\u590d\u5bf9\u8bdd\u7ec6\u8282\uff0c\u53ea\u505a\u6982\u62ec\u3002\n\n"
            "\u5f53\u524d\u6458\u8981\uff1a\n{summary}\n\n"
            "\u65b0\u7684\u5bf9\u8bdd\u884c\uff1a\n{new_lines}\n\n"
            "\u65b0\u7684\u6458\u8981\uff08\u4e0d\u8d85\u8fc7200\u5b57\uff09\uff1a"
        )),
    ])

    chain = prompt | llm | StrOutputParser()
    new_summary = chain.invoke({"summary": existing, "new_lines": new_lines}).strip()

    if new_summary:
        save_summary(session_id, new_summary)


# ── Context Building ──────────────────────────────────────────────

def build_context(session_id):
    """Build a context string containing summary + recent messages."""
    summary = load_summary(session_id)
    recent = load_recent_messages(session_id, RECENT_LIMIT)

    parts = []
    if summary:
        parts.append(f"\u3010\u5bf9\u8bdd\u6458\u8981\u3011\n{summary}")

    if recent:
        lines = ["\u3010\u6700\u8fd1\u5bf9\u8bdd\u3011"]
        for msg in recent:
            prefix = "\u7528\u6237" if msg["role"] == "user" else "AI"
            lines.append(f"{prefix}: {msg['content']}")
        parts.append("\n".join(lines))

    return "\n\n".join(parts)
