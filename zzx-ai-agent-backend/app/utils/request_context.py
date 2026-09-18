"""请求关联 ID：贯穿响应、SSE 和服务端日志。"""
import re
import uuid

from flask import g, request


_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,128}$")


def init_request_context(app):
    @app.before_request
    def assign_request_id():
        supplied = request.headers.get("X-Request-ID", "").strip()
        g.request_id = (
            supplied if _REQUEST_ID_PATTERN.fullmatch(supplied) else uuid.uuid4().hex
        )

    @app.after_request
    def attach_request_id(response):
        response.headers["X-Request-ID"] = g.request_id
        return response

