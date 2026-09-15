"""
Agent Implementation
====================
ReAct Agent with tool-calling capability.
Use: make_agent(system_prompt) -> stream_agent(executor, message)
Tools available:
  - get_time(): Current date/time
  - calc(expr): Math expression evaluation
Data flow:
  Prompt (system + tools + scratchpad) -> ChatOpenAI -> ReAct output parser
  -> tool_execute -> observe -> loop until Final Answer
"""
import logging
from datetime import datetime
from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.prompts import PromptTemplate
from langchain.tools import tool
from app.llm import llm
import re

logger = logging.getLogger(__name__)

@tool
def get_time():
    """Get current date and time. Use when user asks about time."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@tool
def calc(expr: str):
    """
    Calculate a math expression.
    Input: expression string like "2 + 3 * 4" or "sqrt(16)".
    """
    try:
        result = eval(expr, {"__builtins__": {}}, {})
        return str(result)
    except Exception as e:
        return f"Error: {e}"

@tool
def get_now_weather(location: str) -> dict:
    """
    Query real-time weather information for a specified location.

    Args:
        location: The location to query, supports city name (e.g., "Shanghai"),
                  city pinyin (e.g., "shanghai"), or coordinates (e.g., "31.23:121.47").

    Returns:
        A string containing the real-time weather information, e.g.:
        "Shanghai, China: Sunny, Temperature: 25°C, Last update: 2026-07-21 12:00"
        If the query fails, returns an error message string (e.g., "未获取到天气数据").
    """
    import asyncio
    from app.llm.mcp_tools import get_mcp_tools
    mcp_tools = get_mcp_tools()
    weather_tool = next((t for t in mcp_tools if t.name == "get_weather"), None)
    try:
        result = asyncio.run(weather_tool.ainvoke({"location": location}))
        return str(result)
    except Exception as e:
        return "未获取到天气数据";


# ==============================
# ReAct Prompt Template
# ==============================
# Required variables: {tools}, {tool_names}, {input}, {agent_scratchpad}
# {system_prompt} is pre-filled via .partial() at factory time.
AGENT_TEMPLATE = """{system_prompt}
You have access to a set of advanced "Skills" – these are specialized, multi-step workflows for handling specific domain tasks (e.g., romantic confession generation, conflict resolution, trust repair).

Your available skill-related tools are:
- `list_skills` – lists all available skills and their brief descriptions.
- `read_skill` – retrieves the full instruction body of a specific skill by its name.

CRITICAL ROUTING RULE – HOW TO USE SKILLS AUTOMATICALLY:
When a user's request falls into any of the following categories, DO NOT respond with a generic answer or force the user to type an explicit trigger command. Instead, you MUST proactively consider using a skill:
1. The request is vague, complex, or creative in nature, and the user does not specify a concrete tool or format.

Your decision flow:
Step A – Identify the domain. If it matches the above, call `list_skills` to check if a relevant skill exists.
Step B – If a matching skill is found (e.g., "romantic_confession_generator"), call `read_skill` with its exact name to load its full instructions.
Step C – Execute the skill's body step by step. This may include calling other base tools (like `get_time`) as required by the skill.
Step D – Produce the final output strictly according to the skill's format and length requirements.

IMPORTANT – You DO NOT need the user to repeat any special command like "[时刻浪漫表白]". Once the skill is loaded, act as if it is already activated, and follow its internal workflow precisely. This makes the experience seamless for the user.
You have access to the following tools:
{tools}
STRICT FORMAT RULES - YOU MUST FOLLOW THESE EXACTLY:
You must output EXACTLY ONE of the following two patterns in each response:
=== Pattern 1 - Call a tool ===
Thought: (your reasoning)
Action: (tool name, exactly one of [{tool_names}])
Action Input: (input for the tool)
Then the system will give you an Observation. After the observation, repeat with
Thought / Action / Action Input or go to Pattern 2.
=== Pattern 2 - Give the final answer ===
Thought: (your reasoning)
Final Answer: (your complete answer to the user)
CRITICAL RULES:
- "Final Answer:" MUST appear at the very end, on its own line.
- Never output explanatory text before or after the patterns above.
- Never output Chinese text outside of "Final Answer:".
- The "Action:" line must include only the tool name.
- The "Action Input:" line must include only the tool input.
- After "Final Answer:", do NOT add any more text.
=== Example ===
Question: What time is it?
Thought: I need to check the current time.
Action: get_time
Action Input: (none)
Observation: 2026-07-16 10:00:00
Thought: I have the time now.
Final Answer: Current time is 2026-07-16 10:00.
Begin!
Question: {input}
Thought:{agent_scratchpad}"""
# ==============================
# Factory & Streaming
# ==============================
def make_agent(system_prompt, context=""):
    """
    Build a ReAct AgentExecutor.
    Args:
        system_prompt: Role instruction for the AI.
        context:       Conversation history (optional).
    Returns:
        AgentExecutor (Runnable) usable with .stream() / .invoke()
    """
    full_prompt = system_prompt
    if context:
        full_prompt = system_prompt + "\n\n【对话历史】\n" + context
    tools = [get_time, calc]
    prompt = PromptTemplate.from_template(AGENT_TEMPLATE).partial(system_prompt=full_prompt)
    agent = create_react_agent(llm, tools, prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=False, # 是否打印详细日志:False（不打印，由 stream_agent 自行打印）
        handle_parsing_errors=True,# 是否处理解析错误（如格式不正确）：True，遇到解析错误会尝试重试或返回友好信息
        max_iterations=15,# 最大推理循环次数:15，防止死循环
        early_stopping_method="generate",# 提前停止策略:"generate"，当 Agent 输出不完整时，强制让其生成最终答案
        max_execution_time=90,# 最大执行时间（秒）:90，超时则强制停止
    )

def extract_thought(log_text: str) -> str:
    """从 LLM 输出日志中提取 Thought 内容"""
    match = re.search(r"Thought:\s*(.*?)(?=\nAction:|\nFinal Answer:|$)", log_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return log_text.strip()  # 保底


def stream_agent(executor, message, user_id=None, session_id="", llm_ref=None):
    """
    Synchronous agent streaming with real-time thinking log.

    Yields intermediate thinking events and the final answer via SSE,
    and prints each step to stdout for server-side debugging.

    Args:
        executor: AgentExecutor returned by make_agent()
        message: User input string.
        session_id: For saving messages after stream (optional).
        llm_ref: LLM instance for summary generation (optional).

    Yields:
        str: Event strings for SSE - either "[THINK] <msg>"
             or the final answer text.
    """
    logger.info(
        "Agent started session=%s input_chars=%s",
        session_id or "-",
        len(message),
    )
    final_answer = ""

    for step in executor.stream({"input": message}):
        actions = step.get("actions", [])
        steps = step.get("steps", [])
        for action in actions:
            if getattr(action, "tool", None):
                # 提取 Thought 内容
                thought_text = extract_thought(action.log) if hasattr(action, 'log') else ""
                if thought_text:
                    yield f"[THINK] 思考:{thought_text}"
                logger.info(
                    "Agent tool started session=%s tool=%s",
                    session_id or "-",
                    action.tool,
                )
        for s in steps:
            obs = s.observation.strip() if s.observation else ""
            if obs and "Invalid Format" not in obs and "Could not parse" not in obs:
                tool_name = getattr(s.action, 'tool', '?') if hasattr(s, 'action') and s.action else '?'
                tool_in = getattr(s.action, 'tool_input', '') if hasattr(s, 'action') and s.action else ''
                yield f"[STEP] 工具: {tool_name} 输入: {tool_in} 结果: {obs[:300]}"
        if "output" in step:
            answer = step["output"]
            final_answer = answer
            yield f"[FINAL] {answer}"

    logger.info(
        "Agent completed session=%s output_chars=%s",
        session_id or "-",
        len(final_answer),
    )

    # Save messages and trigger summary if we have a session_id
    if session_id and final_answer:
        try:
            from app.chat_history import save_message, update_summary
            save_message(user_id, session_id, "assistant", final_answer)
            if llm_ref:
                update_summary(user_id, session_id)
        except Exception:
            logger.exception("Agent result persistence failed session=%s", session_id)
