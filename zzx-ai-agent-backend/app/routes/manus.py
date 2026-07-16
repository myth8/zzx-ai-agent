from app.llm.skill_middleware import SkillsMiddleware, create_agent
import os as _os

# Initialize skill middleware (progressive disclosure)
_skill_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "skills")
_skill_middleware = SkillsMiddleware(sources=[_skill_dir])

"""
AI Super Agent — route: /api/ai/manus/chat?message=xxx

Selects Chain or Agent based on Config.LLM_MODE.
"""
from flask import Blueprint, request

from app.llm.agent import stream_agent, get_time, calc
from app.utils.sse import sse_response

manus_bp = Blueprint("manus", __name__)

SYSTEM_PROMPT = (
    "You are AI Super Agent, a versatile assistant.\n"
    "Answer in Chinese. Be clear, structured, and helpful."
)


@manus_bp.route("/api/ai/manus/chat")
def chat():
    message = request.args.get("message", "")
    if not message:
        return {"error": "message is required"}, 400

    # SuperAgent always uses Agent mode ? tool calling, multi-bubble display
    executor = create_agent(SYSTEM_PROMPT, middleware=[_skill_middleware], extra_tools=[get_time, calc])
    return sse_response(stream_agent, executor, message)
