"""Shared LLM instance - reused by both Chain and Agent."""
from langchain_openai import ChatOpenAI
from app.config import Config

llm = ChatOpenAI(
    model=Config.DEEPSEEK_MODEL,
    api_key=Config.DEEPSEEK_API_KEY,
    base_url=Config.DEEPSEEK_API_BASE,
    temperature=0.7,
)
