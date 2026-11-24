"""
SSE (Server-Sent Events) utility.
Wraps any synchronous generator into Flask SSE response.

Output format:
  data: [THINKING]\n\n           (immediate heartbeat)
  data: (incremental chunks)\n\n
  data: [DONE]\n\n
"""
import json
import logging

from flask import Response, stream_with_context

from app.utils.responses import get_request_id


logger = logging.getLogger(__name__)


def sse_response(generator_fn, *args):
    """
    Convert a streaming generator into a Flask SSE StreamingResponse.

    Args:
        generator_fn: A generator function that yields text strings.
        *args: Arguments passed to generator_fn.

    Returns:
        Flask Response with text/event-stream content type.

    Example:
        @app.route("/chat")
        def chat():
            return sse_response(my_stream_fn, "hello")
    """
    request_id = get_request_id()

    def generate():
        try:
            # Immediate heartbeat ? prevents frontend timeout
            yield "data: [THINKING]\n\n"
            for chunk in generator_fn(*args):
                # SSE: multi-line data needs multiple "data:" lines
                for line in chunk.split("\n"):
                    yield f"data: {line}\n"
                yield "\n"
        except Exception:
            # 详细堆栈只进入服务端日志。客户端只接收稳定代码、可理解提示和
            # request_id，方便反馈问题时关联同一次请求。
            logger.exception("SSE stream failed")
            payload = json.dumps({
                "code": "CHAT_STREAM_FAILED",
                "message": "生成过程中出现异常，请稍后重试",
                "request_id": request_id,
                "details": None,
            }, ensure_ascii=False)
            yield f"event: error\ndata: {payload}\n\n"
            return
        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
