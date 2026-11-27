"""
AI Super Agent - route: /api/ai/manus/chat?message=xxx&session_id=xxx

支持通过 `engine` 参数选择引擎：
  - react（默认，等价 langchain）：现有 LangChain ReAct Agent
  - toolcalling：手写 MultiStepAgent / ToolCallingAgent
  - code：手写 MultiStepAgent / CodeAgent

会话的 chat_type 决定会话属于哪个引擎；如果显式传入的 engine 与会话
不一致，会返回 409，避免把两种引擎的消息混写进同一段记忆。
"""
from flask import Blueprint, request

from app.agent_core.registry import (
    chat_type_for_engine,
    engine_for_chat_type,
    normalize_engine,
)
from app.auth import login_required
from app.chat_history import get_user_session
from app.llm import llm
from app.llm.agent import stream_agent
from app.llm.skill_middleware import create_agent
from app.llm.tool_registry import BASE_TOOLS, skill_middleware
from app.utils.rate_limit import chat_rate_limit
from app.utils.responses import api_error
from app.utils.sse import sse_response
from app.utils.validation import InputValidationError, validate_chat_message

manus_bp = Blueprint("manus", __name__)

SYSTEM_PROMPT = (
    "You are AI Super Agent, a versatile assistant."
    "Answer in Chinese. Be clear, structured, and helpful."
)


def _resolve_engine(requested: str, session: dict | None = None) -> str:
    """Resolve the engine from the query string and the persisted session."""
    if session is not None:
        session_engine = engine_for_chat_type(session["chat_type"])
        if session_engine is None:
            raise ValueError("会话使用了未知的引擎类型")
        if requested:
            engine = normalize_engine(requested)
            if chat_type_for_engine(engine) != session["chat_type"]:
                raise ValueError(
                    f"该会话属于 {session_engine} 引擎，不能切换到 {engine}"
                )
            return engine
        return session_engine
    return normalize_engine(requested or "react")


@manus_bp.route("/api/ai/manus/chat")
@login_required
@chat_rate_limit
def chat():
    try:
        message = validate_chat_message(request.args.get("message", ""))
    except InputValidationError as exc:
        return api_error(exc.code, exc.message, 400, exc.details)
    session_id = request.args.get("session_id", "")
    user_id = request.current_user["user_id"]

    context = ""
    session = None
    if session_id:
        from app.chat_history import build_context, save_message
        session = get_user_session(user_id, session_id)
        if session is None or session["chat_type"] not in {"agent", "toolcalling", "code"}:
            return api_error("SESSION_NOT_FOUND", "会话不存在", 404)
        context = build_context(user_id, session_id)

    try:
        engine = _resolve_engine(request.args.get("engine", ""), session)
    except ValueError as exc:
        return api_error("ENGINE_INVALID", str(exc), 409 if session else 400)

    if session_id:
        save_message(user_id, session_id, "user", message)

    prompt = SYSTEM_PROMPT
    if context:
        prompt = SYSTEM_PROMPT + "\n\n【对话历史】\n" + context

    if engine == "react":
        executor = create_agent(
            prompt,
            middleware=[skill_middleware],
            extra_tools=BASE_TOOLS,
        )
        return sse_response(stream_agent, executor, message, user_id, session_id, llm)

    # Import lazily: the MultiStepAgent engine (and its Python executor) is
    # only loaded when the user actually selects it.
    from app.agent_core.runner import stream_multistep_agent

    return sse_response(
        stream_multistep_agent,
        engine,
        message,
        SYSTEM_PROMPT,
        context,
        user_id,
        session_id,
        llm,
    )
