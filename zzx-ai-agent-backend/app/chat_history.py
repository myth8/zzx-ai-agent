"""
聊天历史管理
============
管理会话、消息和对话摘要，存储在 MySQL 中。
提供多轮对话的上下文构建功能。
"""
import uuid

from app.auth import get_db

# 上下文包含的最近消息数量
RECENT_LIMIT = 50

# 摘要更新策略：每 N 轮对话触发一次，或累计 token 超过阈值时触发
SUMMARY_INTERVAL = 5  # 每隔多少轮对话更新一次摘要
SUMMARY_TOKEN_THRESHOLD = 4000  # 累计消息超过此 token 估计值时强制触发摘要

# ── 表初始化 ──────────────────────────────────────────────────────────

def init_tables():
    """创建会话 / 聊天消息 / 聊天摘要表。"""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id         INT AUTO_INCREMENT PRIMARY KEY,
                    user_id    INT NOT NULL,
                    session_id VARCHAR(100) NOT NULL UNIQUE,
                    chat_type  VARCHAR(20) NOT NULL COMMENT 'chain or agent',
                    title      VARCHAR(200) DEFAULT '新对话',
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
                    id             INT AUTO_INCREMENT PRIMARY KEY,
                    session_id     VARCHAR(100) NOT NULL UNIQUE,
                    summary        TEXT,
                    updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_session_id (session_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        conn.commit()
    finally:
        conn.close()


# ── 会话 CRUD ──────────────────────────────────────────────────

def create_session(user_id, chat_type, title=None):
    """创建新会话，返回 session_id。"""
    session_id = str(uuid.uuid4())[:8]
    if title is None:
        title = "新对话"
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
    """获取用户的所有会话，按 updated_at 降序排列。"""
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
    """删除会话及其所有消息和摘要。"""
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


# ── 消息 CRUD ──────────────────────────────────────────────────

def save_message(session_id, role, content):
    """保存消息到数据库，自动分配 msg_order。"""
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
    """获取会话的所有消息，按 msg_order 排序。"""
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
    """加载最近的 N 条消息，用于构建上下文。"""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role, content FROM chat_messages "
                "WHERE session_id=%s ORDER BY msg_order DESC LIMIT %s",
                (session_id, limit),
            )
            rows = cur.fetchall()
            rows = list(reversed(rows))  # 按时间顺序
            return rows
    finally:
        conn.close()


def get_message_count(session_id):
    """获取会话的消息总数。"""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM chat_messages WHERE session_id=%s",
                (session_id,),
            )
            return cur.fetchone()["cnt"]
    finally:
        conn.close()


def get_total_chars(session_id):
    """获取会话所有消息的字符总数，用于粗略估算 token 量。"""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(LENGTH(content)), 0) AS total FROM chat_messages WHERE session_id=%s",
                (session_id,),
            )
            return cur.fetchone()["total"]
    finally:
        conn.close()


# ── 摘要管理 ────────────────────────────────────────────────────────────

def load_summary(session_id):
    """加载会话的摘要文本。"""
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
    """插入或更新会话的摘要。"""
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
    msg_count = get_message_count(session_id)

    # 条件1：按固定轮次触发（每轮 = user + assistant 两条消息）
    rounds = msg_count // 2
    if rounds % SUMMARY_INTERVAL != 0:
        # 条件2：按 token 阈值触发（粗略估计，中文字符约 2 字符/token）
        total_chars = get_total_chars(session_id)
        estimated_tokens = total_chars / 2
        if estimated_tokens < SUMMARY_TOKEN_THRESHOLD:
            return  # 两个条件都不满足，跳过摘要生成

    recent = load_recent_messages(session_id, 20)
    if len(recent) < 2:
        return

    existing = load_summary(session_id)

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
        save_summary(session_id, new_summary)

def build_context(session_id):
    """构建包含摘要和最近消息的上下文字符串。"""
    summary = load_summary(session_id)
    recent = load_recent_messages(session_id, RECENT_LIMIT)

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