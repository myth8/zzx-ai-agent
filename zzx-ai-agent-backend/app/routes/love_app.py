"""
AI Love Master - route: /api/ai/love_app/chat/sse?message=xxx&session_id=xxx

Support multi-turn conversation via session_id + summary persistence.
"""
from flask import Blueprint, request

from app.llm.chain import make_chain, stream_chain
from app.llm import llm
from app.utils.sse import sse_response

love_bp = Blueprint("love", __name__)

SYSTEM_PROMPT = (
    "You are AI Love Master, a warm relationship advisor.\n"
    "Answer in Chinese. Be empathetic and give practical advice."
)


@love_bp.route("/api/ai/love_app/chat/sse")
def chat():
    message = request.args.get("message", "")
    session_id = request.args.get("session_id", "")

    if not message:
        return {"error": "message is required"}, 400

    context = ""
    if session_id:
        from app.chat_history import build_context, save_message
        context = build_context(session_id)
        save_message(session_id, "user", message)

    chain = make_chain(SYSTEM_PROMPT, context)
    return sse_response(stream_chain, chain, message, context, session_id, llm)