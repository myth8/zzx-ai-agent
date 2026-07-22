import os


class Config:
    """Central configuration."""
    # LLM
    DEEPSEEK_API_KEY = "sk-826badae5f6a49ce88f0bea5aec73f4c"
    DEEPSEEK_API_BASE = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL = "deepseek-chat"         # deepseek-v4-flash
    SYSTEM_NAME = "ZZX-AI-AGENT"

    # MySQL
    MYSQL_HOST = "127.0.0.1"
    MYSQL_PORT = 3306
    MYSQL_USER = "root"
    MYSQL_PASSWORD = "underdog"
    MYSQL_DB = "zzx_agent_db"

    # JWT
    JWT_SECRET = "zzx-ai-jwt-secret-2024"
