"""
会话管理 API
============
提供用户聊天会话的增删改查功能。
"""
from flask import Blueprint, request, jsonify
from app.auth import login_required
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
    chat_type = request.args.get("chat_type", "chain")
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
    data = request.get_json(force=True) or {}
    chat_type = data.get("chat_type", "chain")
    title = data.get("title", None)
    session_id = create_session(user_id, chat_type, title)
    return jsonify({"code": 0, "msg": "创建成功", "data": {"session_id": session_id}}), 201


@session_bp.route("/rename", methods=["PUT"])
@login_required
def rename():
    """重命名会话"""
    data = request.get_json(force=True) or {}
    session_id = data.get("session_id", "")
    title = data.get("title", "").strip()
    if not session_id or not title:
        return jsonify({"code": 400, "msg": "参数不完整"}), 400
    rename_session(session_id, title)
    return jsonify({"code": 0, "msg": "更新成功"})


@session_bp.route("/<session_id>", methods=["DELETE"])
@login_required
def remove(session_id):
    """删除指定会话"""
    delete_session(session_id)
    return jsonify({"code": 0, "msg": "删除成功"})


@session_bp.route("/<session_id>/messages", methods=["GET"])
@login_required
def messages(session_id):
    """获取指定会话的所有消息"""
    rows = get_session_messages(session_id)
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