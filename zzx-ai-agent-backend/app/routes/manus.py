from app.llm.skill_middleware import SkillsMiddleware, create_agent
import os as _os

_skill_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "skills")
_skill_middleware = SkillsMiddleware(sources=[_skill_dir])

"""
AI Super Agent - route: /api/ai/manus/chat?message=xxx&session_id=xxx

Support multi-turn conversation via session_id + summary persistence.
"""
from flask import Blueprint, request

from app.auth import login_required
from app.chat_history import get_user_session
from app.llm.agent import stream_agent, get_time, calc, get_now_weather
from app.llm.rag import rag_search
from app.llm import llm
from app.utils.sse import sse_response

manus_bp = Blueprint("manus", __name__)

SYSTEM_PROMPT = (
    "You are AI Super Agent, a versatile assistant."
    "Answer in Chinese. Be clear, structured, and helpful."
)


@manus_bp.route("/api/ai/manus/chat")
@login_required
def chat():
    message = request.args.get("message", "")
    session_id = request.args.get("session_id", "")
    user_id = request.current_user["user_id"]

    if not message:
        return {"error": "message is required"}, 400

    context = ""
    if session_id:
        from app.chat_history import build_context, save_message
        session = get_user_session(user_id, session_id)
        if session is None or session["chat_type"] != "agent":
            return {"code": 404, "msg": "会话不存在"}, 404
        context = build_context(user_id, session_id)
        save_message(user_id, session_id, "user", message)

    prompt = SYSTEM_PROMPT
    if context:
        prompt = SYSTEM_PROMPT + "\n\n【对话历史】\n" + context
    executor = create_agent(prompt, middleware=[_skill_middleware], extra_tools=[get_time, calc, get_now_weather, rag_search])
    return sse_response(
        stream_agent, executor, message, user_id, session_id, llm
    )
