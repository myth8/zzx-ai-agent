"""Bridge between Flask SSE routes and the MultiStepAgent engines."""
import json
import logging
import time

from app.config import Config
from app.llm.tool_registry import build_agent_tools

from .agents import CodeAgent, MultiStepAgent, ToolCallingAgent
from .registry import ENGINE_LABELS, normalize_engine
from .tools import build_tool_specs
from .types import ActionOutput, AgentEvent
from app.telemetry import TelemetryRecorder
from app.utils.responses import get_request_id


logger = logging.getLogger(__name__)

_EVENT_PREFIX = {
    "think": "[THINK] ",
    "code": "[CODE] ",
    "step": "[STEP] ",
    "observe": "[OBSERVE] ",
    "final": "[FINAL] ",
}

# Engine-specific instructions live in prompts/project_*.md. The runner only
# injects the product role and conversation history, avoiding duplicated rules
# that would otherwise be billed on every step.
_COMMON_INSTRUCTIONS = "请始终使用简体中文回答。\n\n【角色与业务背景】\n"


def _build_agent(engine: str, instructions: str) -> MultiStepAgent:
    tool_specs = build_tool_specs(build_agent_tools())
    tools = list(tool_specs.values())
    if engine == "code":
        return CodeAgent(
            tools=tools,
            instructions=instructions,
            max_steps=Config.MULTISTEP_MAX_STEPS,
        )
    return ToolCallingAgent(
        tools=tools,
        instructions=instructions,
        max_steps=Config.MULTISTEP_MAX_STEPS,
    )


def stream_multistep_agent(
    engine: str,
    message: str,
    system_prompt: str,
    context: str = "",
    user_id=None,
    session_id: str = "",
    llm_ref=None,
):
    """Yield the existing SSE text protocol for a MultiStepAgent run.

    The existing frontend already understands [THINK], [STEP] and [FINAL].
    [CODE] and [OBSERVE] are additive event types used by the new engine.
    """
    engine = normalize_engine(engine)
    instructions = _COMMON_INSTRUCTIONS + system_prompt + "\n"
    if context:
        instructions += f"\n【对话历史】\n{context}\n"

    logger.info(
        "MultiStepAgent started engine=%s session=%s input_chars=%s",
        engine, session_id or "-", len(message),
    )
    started = time.time()
    agent = _build_agent(engine, instructions)
    recorder = TelemetryRecorder(
        engine,
        session_id=session_id,
        request_id=get_request_id(),
        user_id=user_id,
        input_text=message,
    )
    recorder.start()
    agent.trace = recorder.trace()
    final_answer = ""

    try:
        for item in agent.run_stream(message):
            if isinstance(item, AgentEvent):
                prefix = _EVENT_PREFIX.get(item.kind)
                if prefix:
                    yield prefix + item.text
            elif isinstance(item, ActionOutput) and item.is_final_answer:
                final_answer = str(item.output or "")
    except Exception as exc:  # noqa: BLE001
        if agent.trace:
            agent.trace.event(
                "run_error",
                error_type=type(exc).__name__,
                elapsed_ms=int((time.time() - started) * 1000),
            )
        raise

    # Use the agent's own loop duration so tool-spec construction and other
    # request setup are not mixed into model/tool latency.
    recorder.set_output(final_answer)
    duration_ms = int(getattr(agent, "duration_seconds", time.time() - started) * 1000)
    meta = {
        "engine": engine,
        "engine_label": ENGINE_LABELS.get(engine, engine),
        # steps == number of model decisions (LLM calls), comparable with the
        # callback count used by the LangChain engine.
        "steps": getattr(agent, "llm_calls", agent.step_count),
        "tool_calls": agent.tool_call_count,
        "tool_errors": getattr(agent, "tool_error_count", 0),
        "prompt_tokens": agent.token_usage.input_tokens,
        "completion_tokens": agent.token_usage.output_tokens,
        "duration_ms": duration_ms,
    }
    yield "[META] " + json.dumps(meta, ensure_ascii=False)

    logger.info(
        "MultiStepAgent completed engine=%s session=%s steps=%s tool_calls=%s "
        "prompt_tokens=%s completion_tokens=%s duration_ms=%s",
        engine, session_id or "-", meta["steps"], agent.tool_call_count,
        agent.token_usage.input_tokens, agent.token_usage.output_tokens,
        duration_ms,
    )

    if session_id and final_answer:
        try:
            from app.chat_history import save_message, update_summary
            save_message(user_id, session_id, "assistant", final_answer)
            if llm_ref:
                update_summary(user_id, session_id)
        except Exception:
            logger.exception("MultiStepAgent persistence failed session=%s", session_id)
