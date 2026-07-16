"""Skills Middleware
Progressive disclosure: loads .md knowledge documents from skills/ directory.
Provides list_skills + read_skill tools for agents.

Usage:
    middleware = SkillsMiddleware(sources=["./skills/"])
    executor = create_agent(SYSTEM_PROMPT, middleware=[middleware], extra_tools=[get_time, calc])
"""
import os as _os
from langchain.tools import tool


class SkillsMiddleware:
    """Scans a directory for .md files and exposes them as progressive-disclosure skills."""

    def __init__(self, sources):
        self.sources = sources
        self._skills = {}  # name -> {"description": ..., "body": ...}
        self._discover()

    def _discover(self):
        for src in self.sources:
            skill_dir = _os.path.abspath(src)
            if not _os.path.isdir(skill_dir):
                continue
            for fname in sorted(_os.listdir(skill_dir)):
                if fname.endswith(".md"):
                    self._load(fname, skill_dir)

    def _load(self, fname, skill_dir):
        filepath = _os.path.join(skill_dir, fname)
        with open(filepath, "r", encoding="utf-8") as f:
            raw = f.read()
        name = fname[:-3]  # strip .md
        description = ""
        body = raw
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                fm = parts[1].strip()
                body = parts[2].strip()
                for line in fm.split("\n"):
                    if line.startswith("name:"):
                        name = line.split(":", 1)[1].strip()
                    elif line.startswith("description:"):
                        description = line.split(":", 1)[1].strip()
        self._skills[name] = {"description": description, "body": body}

    def get_tools(self):
        """Return [list_skills, read_skill] tools for LangChain agents."""

        skills_ref = self._skills

        @tool
        def list_skills():
            """列出所有可用的技能模块名称和简介。"""
            if not skills_ref:
                return "当前没有可用的技能模块。"
            result = ["可用的技能模块："]
            for name, info in skills_ref.items():
                desc = info.get("description", "暂无描述")
                result.append(f"  - {name}: {desc}")
            return "\n".join(result)

        @tool
        def read_skill(skill_name: str):
            """读取指定技能的完整内容，输入技能名称。"""
            if skill_name in skills_ref:
                return skills_ref[skill_name]["body"]
            available = ", ".join(skills_ref.keys())
            return f"技能\"{skill_name}\"不存在。可用的技能: {available}"

        return [list_skills, read_skill]


def create_agent(system_prompt, middleware=None, extra_tools=None):
    """创建一个带中间件的 Agent。
    Args:
        system_prompt: 系统提示词
        middleware: SkillsMiddleware 实例列表
        extra_tools: 额外的工具列表（如 [get_time, calc]）
    Returns:
        AgentExecutor 可用 .stream() / .invoke()
    """
    from langchain.agents import create_react_agent as _create_react, AgentExecutor
    from langchain_core.prompts import PromptTemplate
    from app.llm import llm
    from app.llm.agent import AGENT_TEMPLATE

    tools = list(extra_tools or [])
    if middleware:
        for m in middleware:
            if hasattr(m, "get_tools"):
                tools.extend(m.get_tools())

    prompt = PromptTemplate.from_template(AGENT_TEMPLATE).partial(system_prompt=system_prompt)
    agent = _create_react(llm, tools, prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=False,
        handle_parsing_errors=True,
        max_iterations=15,
        early_stopping_method="generate",
        max_execution_time=90,
    )
