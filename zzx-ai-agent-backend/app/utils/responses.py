"""统一 API 错误响应，避免各路由泄露内部异常或自行定义结构。"""
from flask import g, jsonify


def get_request_id():
    """返回当前请求 ID；未经过中间件的轻量测试应用使用占位值。"""
    return getattr(g, "request_id", "unavailable")


def api_error(error_code, message, status=400, details=None):
    """构造稳定错误结构；details 只能放可公开的字段级提示。"""
    return jsonify({
        "code": error_code,
        "message": message,
        "request_id": get_request_id(),
        "details": details,
    }), status

