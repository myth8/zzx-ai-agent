"""
聊天历史管理
============
管理会话、消息和对话摘要，存储在 MySQL 中。
提供多轮对话的上下文构建功能。
"""
import uuid

from app.auth import get_db
from app.db import connection, transaction

# 上下文包含的最近消息数量
RECENT_LIMIT = 50

# 摘要更新策略：每 N 轮对话触发一次，或累计 token 超过阈值时触发
SUMMARY_INTERVAL = 5  # 每隔多少轮对话更新一次摘要
SUMMARY_TOKEN_THRESHOLD = 4000  # 累计消息超过此 token 估计值时强制触发摘要

# ── 表初始化 ──────────────────────────────────────────────────────────

def init_tables():
    """Deprecated compatibility hook; schema changes are Alembic migrations."""
    from app.db_schema import verify_database_schema
    verify_database_schema()


# ── 会话 CRUD ──────────────────────────────────────────────────

def create_session(user_id, chat_type, title=None):
    """创建新会话，返回 session_id。"""
    session_id = str(uuid.uuid4())
    if title is None:
        title = "新对话"
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (user_id, session_id, chat_type, title) VALUES (%s, %s, %s, %s)",
                (user_id, session_id, chat_type, title),
            )
    return session_id


def get_user_sessions(user_id, chat_type):
    """获取用户的所有会话，按 updated_at 降序排列。"""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT session_id, title, chat_type, created_at, updated_at "
                "FROM sessions WHERE user_id=%s AND chat_type=%s "
                "ORDER BY updated_at DESC, id DESC",
                (user_id, chat_type),
            )
            return cur.fetchall()


def get_user_session(user_id, session_id):
    """Return a session only when it belongs to the requested user."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT session_id, user_id, title, chat_type, created_at, updated_at "
                "FROM sessions WHERE user_id=%s AND session_id=%s",
                (user_id, session_id),
            )
            return cur.fetchone()


def rename_session(user_id, session_id, title):
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sessions SET title=%s "
                "WHERE user_id=%s AND session_id=%s",
                (title, user_id, session_id),
            )
            updated = cur.rowcount
        return updated > 0


def delete_session(user_id, session_id):
    """Delete a session; child messages, summaries and runs cascade in MySQL."""
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM sessions WHERE user_id=%s AND session_id=%s",
                (user_id, session_id),
            )
            return cur.rowcount > 0


def get_session_title(user_id, session_id):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT title, chat_type FROM sessions "
                "WHERE user_id=%s AND session_id=%s",
                (user_id, session_id),
            )
            return cur.fetchone()
    finally:
        conn.close()


# ── 消息 CRUD ──────────────────────────────────────────────────

def _save_message_in_transaction(
    conn, user_id, session_id, role, content, *, message_id=None,
    client_message_id=None
):
    message_id = message_id or str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            "SELECT next_message_order FROM sessions "
            "WHERE user_id=%s AND session_id=%s FOR UPDATE",
            (user_id, session_id),
        )
        session = cur.fetchone()
        if session is None:
            return None
        next_order = session["next_message_order"]
        cur.execute(
            "INSERT INTO chat_messages "
            "(message_id, session_id, client_message_id, role, content, msg_order) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                message_id, session_id, client_message_id, role, content,
                next_order,
            ),
        )
        cur.execute(
            "UPDATE sessions SET next_message_order=%s, updated_at=UTC_TIMESTAMP(6) "
            "WHERE user_id=%s AND session_id=%s",
            (next_order + 1, user_id, session_id),
        )
    return {"message_id": message_id, "msg_order": next_order}


def save_message(
    user_id, session_id, role, content, *, message_id=None,
    client_message_id=None, conn=None
):
    """Atomically allocate an order, insert a message and touch the session."""
    if conn is not None:
        return _save_message_in_transaction(
            conn, user_id, session_id, role, content,
            message_id=message_id, client_message_id=client_message_id,
        )
    with transaction() as owned_conn:
        return _save_message_in_transaction(
            owned_conn, user_id, session_id, role, content,
            message_id=message_id, client_message_id=client_message_id,
        )


def get_session_messages(user_id, session_id):
    """获取会话的所有消息，按 msg_order 排序。"""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT m.message_id, m.client_message_id, m.role, m.content, "
                "m.msg_order, m.created_at "
                "FROM chat_messages m "
                "JOIN sessions s ON s.session_id=m.session_id "
                "WHERE s.user_id=%s AND m.session_id=%s "
                "ORDER BY m.msg_order ASC",
                (user_id, session_id),
            )
            return cur.fetchall()
    finally:
        conn.close()


def load_recent_messages(user_id, session_id, limit=RECENT_LIMIT):
    """加载最近的 N 条消息，用于构建上下文。"""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT m.role, m.content FROM chat_messages m "
                "JOIN sessions s ON s.session_id=m.session_id "
                "WHERE s.user_id=%s AND m.session_id=%s "
                "ORDER BY m.msg_order DESC LIMIT %s",
                (user_id, session_id, limit),
            )
            rows = cur.fetchall()
            rows = list(reversed(rows))  # 按时间顺序
            return rows
    finally:
        conn.close()


def get_message_count(user_id, session_id):
    """获取会话的消息总数。"""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM chat_messages m "
                "JOIN sessions s ON s.session_id=m.session_id "
                "WHERE s.user_id=%s AND m.session_id=%s",
                (user_id, session_id),
            )
            return cur.fetchone()["cnt"]
    finally:
        conn.close()


def get_total_chars(user_id, session_id):
    """获取会话所有消息的字符总数，用于粗略估算 token 量。"""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(LENGTH(m.content)), 0) AS total "
                "FROM chat_messages m "
                "JOIN sessions s ON s.session_id=m.session_id "
                "WHERE s.user_id=%s AND m.session_id=%s",
                (user_id, session_id),
            )
            return cur.fetchone()["total"]
    finally:
        conn.close()


# ── 摘要管理 ────────────────────────────────────────────────────────────

def load_summary(user_id, session_id):
    """加载会话的摘要文本。"""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT cs.summary FROM chat_summaries cs "
                "JOIN sessions s ON s.session_id=cs.session_id "
                "WHERE s.user_id=%s AND cs.session_id=%s",
                (user_id, session_id),
            )
            row = cur.fetchone()
            return row["summary"] if row and row["summary"] else ""
    finally:
        conn.close()


def save_summary(user_id, session_id, summary_text):
    """插入或更新会话的摘要。"""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT session_id FROM sessions "
                "WHERE user_id=%s AND session_id=%s FOR UPDATE",
                (user_id, session_id),
            )
            if cur.fetchone() is None:
                return False
            cur.execute(
                "INSERT INTO chat_summaries (session_id, summary) VALUES (%s, %s) "
                "ON DUPLICATE KEY UPDATE summary=%s",
                (session_id, summary_text, summary_text),
            )
        conn.commit()
        return True
    finally:
        conn.close()


def update_summary(user_id, session_id):
    """
    按策略自动生成/更新对话摘要。

    触发条件（满足任一即可）：
      1. 消息总轮数达到 SUMMARY_INTERVAL 的整数倍
      2. 累计消息字符数估算的 token 量超过 SUMMARY_TOKEN_THRESHOLD

    两个条件都不满足时直接跳过，不调用 LLM。
    """
    from app.llm import llm
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser

    # ── 判断是否应该触发摘要更新 ──
    msg_count = get_message_count(user_id, session_id)

    # 条件1：按固定轮次触发（每轮 = user + assistant 两条消息）
    rounds = msg_count // 2
    if rounds % SUMMARY_INTERVAL != 0:
        # 条件2：按 token 阈值触发（粗略估计，中文字符约 2 字符/token）
        total_chars = get_total_chars(user_id, session_id)
        estimated_tokens = total_chars / 2
        if estimated_tokens < SUMMARY_TOKEN_THRESHOLD:
            return  # 两个条件都不满足，跳过摘要生成

    recent = load_recent_messages(user_id, session_id, 20)
    if len(recent) < 2:
        return

    existing = load_summary(user_id, session_id)

    # 构建新消息行
    new_lines = ""
    for msg in recent:
        prefix = "用户" if msg["role"] == "user" else "AI"
        new_lines += f"{prefix}: {msg['content']}\n"

    prompt = ChatPromptTemplate.from_messages([
        ("human", (
            "请将以下对话压缩为中文摘要，只保留以下信息：\n"
            "1. 用户的身份、兴趣、目标\n"
            "2. 用户提出的主要问题或请求\n"
            "3. AI给出的关键回答或建议\n"
            "不要重复对话细节，只做概括。\n\n"
            "当前摘要：\n{summary}\n\n"
            "新的对话行：\n{new_lines}\n\n"
            "新的摘要（不超过500字）："
        )),
    ])

    chain = prompt | llm | StrOutputParser()
    new_summary = chain.invoke({"summary": existing, "new_lines": new_lines}).strip()

    if new_summary:
        save_summary(user_id, session_id, new_summary)

def build_context(user_id, session_id):
    """构建包含摘要和最近消息的上下文字符串。"""
    summary = load_summary(user_id, session_id)
    recent = load_recent_messages(user_id, session_id, RECENT_LIMIT)

    parts = []
    if summary:
        parts.append(f"【对话摘要】\n{summary}")

    if recent:
        lines = ["【最近对话】"]
        for msg in recent:
            prefix = "用户" if msg["role"] == "user" else "AI"
            lines.append(f"{prefix}: {msg['content']}")
        parts.append("\n".join(lines))

    return "\n\n".join(parts)
