"""
SSE (Server-Sent Events) utility.
Wraps any synchronous generator into Flask SSE response.

Output format:
  data: [THINKING]\n\n           (immediate heartbeat)
  data: (incremental chunks)\n\n
  data: [DONE]\n\n
"""
from flask import Response, stream_with_context


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
    def generate():
        try:
            # Immediate heartbeat ? prevents frontend timeout
            yield "data: [THINKING]\n\n"
            for chunk in generator_fn(*args):
                # SSE: multi-line data needs multiple "data:" lines
                for line in chunk.split("\n"):
                    yield f"data: {line}\n"
                yield "\n"
        except Exception as e:
            yield f"data: Error: {e}\n\n"
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
