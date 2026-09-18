"""
会话管理 API
============
提供用户聊天会话的增删改查功能。
"""
from flask import Blueprint, request, jsonify
from app.auth import login_required
from app.utils.responses import api_error
from app.utils.validation import (
    InputValidationError,
    validate_chat_type,
    validate_session_title,
)
from app.chat_history import (
    create_session,
    get_user_sessions,
    rename_session,
    delete_session,
    get_session_messages,
)

session_bp = Blueprint("session", __name__, url_prefix="/api/session")


@session_bp.route("/list", methods=["GET"])
@login_required
def list_sessions():
    """获取当前用户的所有会话列表"""
    user_id = request.current_user["user_id"]
    try:
        chat_type = validate_chat_type(request.args.get("chat_type", "chain"))
    except InputValidationError as exc:
        return api_error(exc.code, exc.message, 400, exc.details)
    rows = get_user_sessions(user_id, chat_type)
    return jsonify({
        "code": 0,
        "data": [
            {
                "session_id": r["session_id"],
                "title": r["title"],
                "chat_type": r["chat_type"],
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
            }
            for r in rows
        ],
    })


@session_bp.route("/create", methods=["POST"])
@login_required
def new_session():
    """创建新会话"""
    user_id = request.current_user["user_id"]
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return api_error("JSON_BODY_REQUIRED", "请求体必须是 JSON 对象", 400)
    try:
        chat_type = validate_chat_type(data.get("chat_type", "chain"))
        title = validate_session_title(data.get("title"), default="新对话")
    except InputValidationError as exc:
        return api_error(exc.code, exc.message, 400, exc.details)
    session_id = create_session(user_id, chat_type, title)
    return jsonify({"code": 0, "msg": "创建成功", "data": {"session_id": session_id}}), 201


@session_bp.route("/rename", methods=["PUT"])
@login_required
def rename():
    """重命名会话"""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return api_error("JSON_BODY_REQUIRED", "请求体必须是 JSON 对象", 400)
    session_id = data.get("session_id", "")
    if not isinstance(session_id, str) or not session_id.strip():
        return api_error(
            "SESSION_ID_REQUIRED", "会话 ID 不能为空", 400, {"field": "session_id"}
        )
    try:
        title = validate_session_title(data.get("title"))
    except InputValidationError as exc:
        return api_error(exc.code, exc.message, 400, exc.details)
    user_id = request.current_user["user_id"]
    if not rename_session(user_id, session_id, title):
        return api_error("SESSION_NOT_FOUND", "会话不存在", 404)
    return jsonify({"code": 0, "msg": "更新成功"})


@session_bp.route("/<session_id>", methods=["DELETE"])
@login_required
def remove(session_id):
    """删除指定会话"""
    user_id = request.current_user["user_id"]
    if not delete_session(user_id, session_id):
        return api_error("SESSION_NOT_FOUND", "会话不存在", 404)
    return jsonify({"code": 0, "msg": "删除成功"})


@session_bp.route("/<session_id>/messages", methods=["GET"])
@login_required
def messages(session_id):
    """获取指定会话的所有消息"""
    user_id = request.current_user["user_id"]
    from app.chat_history import get_user_session
    if get_user_session(user_id, session_id) is None:
        return api_error("SESSION_NOT_FOUND", "会话不存在", 404)
    rows = get_session_messages(user_id, session_id)
    return jsonify({
        "code": 0,
        "data": [
            {
                "role": r["role"],
                "content": r["content"],
                "msg_order": r["msg_order"],
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            }
            for r in rows
        ],
    })
