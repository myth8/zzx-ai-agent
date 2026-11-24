"""Shared tool catalogue for both agent engines.

The LangChain ReAct route and the new MultiStepAgent engines must see exactly
the same tool set, otherwise a tool-calling benchmark would compare different
problems. Keeping the catalogue here avoids two lists drifting apart.
"""
import os

from app.llm.agent import calc, get_now_weather, get_time
from app.llm.rag import rag_search
from app.llm.skill_middleware import SkillsMiddleware


_SKILL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "skills",
)

skill_middleware = SkillsMiddleware(sources=[_SKILL_DIR])

# Base tools are LangChain @tool objects. The MultiStepAgent adapter converts
# them to ToolSpec objects, so both engines execute the same callables.
BASE_TOOLS = [get_time, calc, get_now_weather, rag_search]


def build_agent_tools():
    """Return base tools plus the progressive-disclosure skill tools."""
    return list(BASE_TOOLS) + skill_middleware.get_tools()


def build_skill_tools():
    return skill_middleware.get_tools()
