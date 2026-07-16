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
import sys
from datetime import datetime
from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.prompts import PromptTemplate
from langchain.tools import tool
from app.llm import llm
import re

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


# ==============================
# ReAct Prompt Template
# ==============================
# Required variables: {tools}, {tool_names}, {input}, {agent_scratchpad}
# {system_prompt} is pre-filled via .partial() at factory time.
AGENT_TEMPLATE = """{system_prompt}
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
def make_agent(system_prompt):
    """
    Build a ReAct AgentExecutor.
    Args:
        system_prompt: Role instruction for the AI.
    Returns:
        AgentExecutor (Runnable) usable with .stream() / .invoke()
    """
    tools = [get_time, calc]
    prompt = PromptTemplate.from_template(AGENT_TEMPLATE).partial(system_prompt=system_prompt)
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


def stream_agent(executor, message):
    """
    Synchronous agent streaming with real-time thinking log.

    Yields intermediate thinking events and the final answer via SSE,
    and prints each step to stdout for server-side debugging.

    Args:
        executor: AgentExecutor returned by make_agent()
        message: User input string.

    Yields:
        str: Event strings for SSE - either "[THINK] <msg>"
             or the final answer text.
    """
    print(f"\n{'='*60}", flush=True)
    print(f"[Agent] Input: {message}", flush=True)
    print(f"{'='*60}", flush=True)

    for step in executor.stream({"input": message}):
        actions = step.get("actions", [])
        steps = step.get("steps", [])
        for action in actions:
            if getattr(action, "tool", None):
                # 提取 Thought 内容
                thought_text = extract_thought(action.log) if hasattr(action, 'log') else ""
                if thought_text:
                    print(f"  |- Thought: {thought_text}")
                    yield f"[THINK] 思考:{thought_text}"
                print(f"  |- Tool  : {action.tool}")
                print(f"  |- Input : {action.tool_input}")
        for s in steps:
            obs = s.observation.strip() if s.observation else ""
            if obs and "Invalid Format" not in obs and "Could not parse" not in obs:
                print(f"  |- Obs   : {obs[:200]}")
                tool_name = getattr(s.action, 'tool', '?') if hasattr(s, 'action') and s.action else '?'
                tool_in = getattr(s.action, 'tool_input', '') if hasattr(s, 'action') and s.action else ''
                yield f"[STEP] 工具: {tool_name} 输入: {tool_in} 结果: {obs[:300]}"
        if "output" in step:
            answer = step["output"]
            print(f"\n  -- Final Answer:\n{answer}\n", flush=True)
            yield f"[FINAL] {answer}"
