import os


class Config:
    """Central configuration."""
    DEEPSEEK_API_KEY = "sk-826badae5f6a49ce88f0bea5aec73f4c"
    DEEPSEEK_API_BASE = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL = "deepseek-chat"         # deepseek-v4-flash
    LLM_MODE = os.getenv("LLM_MODE", "chain")  # "chain" | "agent"
