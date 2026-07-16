"""
AI Love Master — route: /api/ai/love_app/chat/sse?message=xxx&chatId=xxx

Selects Chain or Agent based on Config.LLM_MODE.
chatId is accepted but not persisted (single-turn for now).
"""
from flask import Blueprint, request

from app.llm.chain import make_chain, stream_chain
from app.utils.sse import sse_response

love_bp = Blueprint("love", __name__)

SYSTEM_PROMPT = (
    "You are AI Love Master, a warm relationship advisor.\n"
    "Answer in Chinese. Be empathetic and give practical advice."
)


@love_bp.route("/api/ai/love_app/chat/sse")
def chat():
    message = request.args.get("message", "")
    if not message:
        return {"error": "message is required"}, 400

    # LoveMaster always uses Chain mode ? simple Q&A, token-level streaming
    chain = make_chain(SYSTEM_PROMPT)
    return sse_response(stream_chain, chain, message)
