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
import json
import logging
import time
from datetime import datetime
from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.prompts import PromptTemplate
from langchain.tools import tool
from app.llm import llm
from app.llm.agent_metrics import AgentMetricsCallback
from app.telemetry import TelemetryRecorder
from app.utils.responses import get_request_id
from app.utils.safe_math import SafeMathError, evaluate_math_expression

logger = logging.getLogger(__name__)


def _format_weather_result(value):
    """Convert the MCP weather payload into a compact human-readable result.

    The MCP client may return a dict or a JSON string. ToolCalling/CodeAgent
    otherwise tend to paste the raw payload into final answers, which makes the
    UI noisy and wastes completion tokens. ReAct benefits from the same concise
    observation.
    """
    payload = value
    if isinstance(value, str):
        try:
            payload = json.loads(value)
        except (TypeError, ValueError):
            return value
    if isinstance(payload, dict) and payload.get("location"):
        location = payload.get("location")
        weather = payload.get("weather", "未知")
        temperature = payload.get("temperature", "未知")
        updated = payload.get("last_update", "未知")
        return f"{location}：{weather}，气温 {temperature}℃，更新时间 {updated}"
    return str(value)


@tool
def get_time():
    """Get current date and time. Use when user asks about time."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@tool
def calc(expr: str):
    """
    Calculate a math expression.
    Input: expression string like "2 + 3 * 4" or "(10 - 2) / 4".
    """
    try:
        return str(evaluate_math_expression(expr))
    except SafeMathError:
        return "计算表达式无效，仅支持数字、括号和批准的基础运算符。"

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

    # 整个调用链都必须在 try 内：MCP 服务不可达时 get_mcp_tools() 会抛出
    # anyio 的 ExceptionGroup，若放在 try 外会一路冒泡打断整轮对话。
    try:
        mcp_tools = get_mcp_tools()
        weather_tool = next((t for t in mcp_tools if t.name == "get_weather"), None)
        if weather_tool is None:
            logger.warning("Weather tool unavailable: get_weather not exposed by MCP server")
            return "未获取到天气数据"
        result = asyncio.run(weather_tool.ainvoke({"location": location}))
        return _format_weather_result(result)
    except Exception as exc:
        logger.warning(
            "Weather tool failed location_chars=%s error=%s: %s",
            len(location),
            type(exc).__name__,
            exc,
        )
        return "未获取到天气数据"


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
    started = time.time()
    recorder = TelemetryRecorder(
        "react",
        session_id=session_id,
        request_id=get_request_id(),
        user_id=user_id,
        input_text=message,
    )
    recorder.start()
    trace = recorder.trace()
    trace.run_start(task_chars=len(message or ""), engine="react")
    metrics = AgentMetricsCallback(trace=trace)
    event_index = 0

    try:
        for step in executor.stream(
            {"input": message},
            config={"callbacks": [metrics]},
        ):
            event_index += 1
            event_started = time.time()
            actions = step.get("actions", [])
            steps = step.get("steps", [])
            for action in actions:
                if getattr(action, "tool", None):
                    # 不向浏览器暴露模型原始 Thought，只输出产品可控的阶段状态。
                    yield "[THINK] 正在分析问题并选择合适的工具。"
                    logger.info(
                        "Agent tool started session=%s tool=%s",
                        session_id or "-",
                        action.tool,
                    )
            for s in steps:
                obs = s.observation.strip() if s.observation else ""
                if obs and "Invalid Format" not in obs and "Could not parse" not in obs:
                    tool_name = getattr(s.action, 'tool', '?') if hasattr(s, 'action') and s.action else '?'
                    # 工具输入和原始结果可能包含用户隐私或第三方响应，不直接下发。
                    yield f"[STEP] 工具 {tool_name} 执行完成。"
            if "output" in step:
                answer = step["output"]
                final_answer = answer
                yield f"[FINAL] {answer}"
            if trace:
                trace.event(
                    "stream_step",
                    step=event_index,
                    actions=[getattr(a, "tool", "?") for a in actions],
                    observations=len(steps),
                    has_output="output" in step,
                    output_chars=len(str(step.get("output") or "")),
                    elapsed_ms=int((time.time() - event_started) * 1000),
                    cumulative_prompt_tokens=metrics.prompt_tokens,
                    cumulative_completion_tokens=metrics.completion_tokens,
                )
    except Exception as exc:  # noqa: BLE001
        trace.event(
            "run_error",
            error_type=type(exc).__name__,
            elapsed_ms=int((time.time() - started) * 1000),
        )
        raise

    duration_ms = int((time.time() - started) * 1000)
    meta = {
        "engine": "react",
        "engine_label": "LangChain ReAct",
        # One model call per ReAct decision round; the callback also counts the
        # final-answer fallback if LangChain has to generate one.
        "steps": metrics.llm_calls,
        "tool_calls": metrics.tool_calls,
        "tool_errors": metrics.tool_errors,
        "prompt_tokens": metrics.prompt_tokens,
        "completion_tokens": metrics.completion_tokens,
        "duration_ms": duration_ms,
    }
    recorder.set_output(final_answer)
    trace.run_finish(
        status="success",
        steps=meta["steps"],
        tool_calls=meta["tool_calls"],
        tool_errors=meta["tool_errors"],
        prompt_tokens=meta["prompt_tokens"],
        completion_tokens=meta["completion_tokens"],
        duration_ms=duration_ms,
        output_chars=len(final_answer),
    )
    yield "[META] " + json.dumps(meta, ensure_ascii=False)
    logger.info(
        "Agent completed session=%s output_chars=%s steps=%s tool_calls=%s "
        "prompt_tokens=%s completion_tokens=%s duration_ms=%s",
        session_id or "-", len(final_answer), meta["steps"], meta["tool_calls"],
        meta["prompt_tokens"], meta["completion_tokens"], duration_ms,
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
