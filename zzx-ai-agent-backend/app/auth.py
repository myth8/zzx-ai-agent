"""Authentication, JWT lifecycle, and lightweight role authorization."""
import hmac
import uuid
from functools import wraps

import pymysql
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
    set_refresh_cookies,
    unset_jwt_cookies,
)
from werkzeug.security import check_password_hash, generate_password_hash

from app.auth_store import (
    AuthStoreUnavailable,
    create_login_session,
    is_token_revoked,
    revoke_all_login_sessions,
    revoke_login_session,
    revoke_token,
    rotate_refresh_token,
)
from app.extensions import jwt


auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def auth_error(message, status, error_code):
    """Return one stable JSON shape for authentication/authorization errors."""
    return jsonify({
        "code": status,
        "msg": message,
        "error_code": error_code,
    }), status


def _is_admin_invite_valid(invite_code):
    """Compare the configured administrator invite without loose coercion."""
    configured = current_app.config.get("ADMIN_INVITE_CODE", "")
    return bool(
        invite_code
        and configured
        and hmac.compare_digest(invite_code, configured)
    )


def get_db():
    """Get a MySQL database connection from validated configuration."""
    cfg = current_app.config
    return pymysql.connect(
        host=cfg["MYSQL_HOST"],
        port=cfg["MYSQL_PORT"],
        user=cfg["MYSQL_USER"],
        password=cfg["MYSQL_PASSWORD"],
        database=cfg["MYSQL_DB"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def init_db():
    """Initialize the user schema, including the lightweight role column."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id         INT AUTO_INCREMENT PRIMARY KEY,
                    username   VARCHAR(50)  NOT NULL UNIQUE,
                    nickname   VARCHAR(50)  NOT NULL,
                    password   VARCHAR(255) NOT NULL,
                    role       VARCHAR(32)  NOT NULL DEFAULT 'user',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_users_role (role)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("SHOW COLUMNS FROM users LIKE 'role'")
            if cur.fetchone() is None:
                cur.execute(
                    "ALTER TABLE users "
                    "ADD COLUMN role VARCHAR(32) NOT NULL DEFAULT 'user' "
                    "AFTER password"
                )
            cur.execute(
                "SHOW INDEX FROM users WHERE Key_name='idx_users_role'"
            )
            if cur.fetchone() is None:
                cur.execute("CREATE INDEX idx_users_role ON users (role)")
        conn.commit()
    finally:
        conn.close()


def get_user_by_id(user_id):
    """Load current user state without exposing the password hash."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, nickname, role, created_at "
                "FROM users WHERE id=%s",
                (user_id,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def _token_response(user):
    """Create a Redis-tracked access/refresh token pair."""
    session_id = str(uuid.uuid4())
    identity = str(user["id"])
    refresh_token = create_refresh_token(
        identity=identity,
        additional_claims={"sid": session_id},
    )
    refresh_payload = decode_token(refresh_token)
    access_token = create_access_token(
        identity=identity,
        additional_claims={"sid": session_id},
    )
    create_login_session(
        user_id=user["id"],
        session_id=session_id,
        refresh_jti=refresh_payload["jti"],
        expires_at=refresh_payload["exp"],
    )

    response = jsonify({
        "code": 0,
        "msg": "登录成功",
        "data": {
            # Keep token for compatibility with the current frontend.
            "token": access_token,
            "access_token": access_token,
            "user_id": user["id"],
            "username": user["username"],
            "nickname": user["nickname"],
            "role": user["role"],
        },
    })
    set_refresh_cookies(response, refresh_token)
    return response


def login_required(view):
    """Require a valid tracked JWT and load the latest user state."""
    @jwt_required()
    @wraps(view)
    def decorated(*args, **kwargs):
        identity = get_jwt_identity()
        try:
            user_id = int(identity)
        except (TypeError, ValueError):
            return auth_error("Token 身份无效", 401, "AUTH_INVALID_IDENTITY")

        user = get_user_by_id(user_id)
        if user is None:
            return auth_error("用户不存在或已停用", 401, "AUTH_USER_NOT_FOUND")

        request.current_user = {
            "user_id": user["id"],
            "username": user["username"],
            "nickname": user["nickname"],
            "role": user["role"],
        }
        return view(*args, **kwargs)

    return decorated


def admin_required(view):
    """Require the latest database role to be admin."""
    @login_required
    @wraps(view)
    def decorated(*args, **kwargs):
        if request.current_user["role"] != "admin":
            return auth_error("无权访问该功能", 403, "AUTH_ADMIN_REQUIRED")
        return view(*args, **kwargs)

    return decorated


@jwt.token_in_blocklist_loader
def token_in_blocklist(_jwt_header, jwt_payload):
    return is_token_revoked(jwt_payload)


@jwt.unauthorized_loader
def missing_token(reason):
    return auth_error("请先登录", 401, "AUTH_TOKEN_MISSING")


@jwt.invalid_token_loader
def invalid_token(reason):
    return auth_error("Token 无效", 401, "AUTH_TOKEN_INVALID")


@jwt.expired_token_loader
def expired_token(_jwt_header, _jwt_payload):
    return auth_error("登录状态已过期", 401, "AUTH_TOKEN_EXPIRED")


@jwt.revoked_token_loader
def revoked_token(_jwt_header, _jwt_payload):
    return auth_error("登录状态已失效", 401, "AUTH_TOKEN_REVOKED")


@jwt.needs_fresh_token_loader
def needs_fresh_token(_jwt_header, _jwt_payload):
    return auth_error("请重新验证身份", 401, "AUTH_FRESH_TOKEN_REQUIRED")


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    nickname = (data.get("nickname") or "").strip()
    password = (data.get("password") or "").strip()
    invite_code = str(data.get("invite_code") or "").strip()

    if not username or not nickname or not password:
        return jsonify({"code": 400, "msg": "账号、昵称、密码不能为空"}), 400
    if len(username) < 3 or len(username) > 50:
        return jsonify({"code": 400, "msg": "账号长度为 3-50 个字符"}), 400
    if len(password) < 6:
        return jsonify({"code": 400, "msg": "密码长度至少 6 位"}), 400
    if invite_code and not _is_admin_invite_valid(invite_code):
        return auth_error("管理员邀请码无效", 400, "AUTH_INVITE_INVALID")

    role = "admin" if invite_code else "user"

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE username=%s", (username,))
            if cur.fetchone():
                return jsonify({"code": 409, "msg": "该账号已被注册"}), 409

            hashed = generate_password_hash(password)
            cur.execute(
                "INSERT INTO users (username, nickname, password, role) "
                "VALUES (%s, %s, %s, %s)",
                (username, nickname, hashed, role),
            )
        conn.commit()
    finally:
        conn.close()

    return jsonify({
        "code": 0,
        "msg": "注册成功",
        "data": {"role": role},
    }), 201


@auth_bp.route("/invite/redeem", methods=["POST"])
@login_required
def redeem_admin_invite():
    """Promote the current user after validating the configured invite."""
    if request.current_user["role"] == "admin":
        return jsonify({
            "code": 0,
            "msg": "当前账号已是管理员",
            "data": {"role": "admin", "changed": False},
        })

    data = request.get_json(silent=True) or {}
    invite_code = str(data.get("invite_code") or "").strip()
    if not invite_code:
        return auth_error("请输入管理员邀请码", 400, "AUTH_INVITE_REQUIRED")
    if not _is_admin_invite_valid(invite_code):
        return auth_error("管理员邀请码无效", 400, "AUTH_INVITE_INVALID")

    user_id = request.current_user["user_id"]
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET role='admin' WHERE id=%s AND role<>'admin'",
                (user_id,),
            )
            changed = cur.rowcount > 0
        conn.commit()
    finally:
        conn.close()

    return jsonify({
        "code": 0,
        "msg": "管理员权限已激活",
        "data": {"role": "admin", "changed": changed},
    })


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if not username or not password:
        return jsonify({"code": 400, "msg": "账号和密码不能为空"}), 400

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, nickname, password, role "
                "FROM users WHERE username=%s",
                (username,),
            )
            user = cur.fetchone()
    finally:
        conn.close()

    if user is None or not check_password_hash(user["password"], password):
        return auth_error("账号或密码错误", 401, "AUTH_INVALID_CREDENTIALS")

    try:
        return _token_response(user)
    except AuthStoreUnavailable as exc:
        return jsonify({
            "code": 503,
            "msg": str(exc),
            "error_code": "AUTH_STORE_UNAVAILABLE",
        }), 503


@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True, locations=["cookies"])
def refresh():
    old_payload = get_jwt()
    identity = get_jwt_identity()
    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        return auth_error("Token 身份无效", 401, "AUTH_INVALID_IDENTITY")

    user = get_user_by_id(user_id)
    if user is None:
        return auth_error("用户不存在或已停用", 401, "AUTH_USER_NOT_FOUND")

    session_id = old_payload.get("sid", "")
    new_refresh = create_refresh_token(
        identity=str(user_id),
        additional_claims={"sid": session_id},
    )
    new_refresh_payload = decode_token(new_refresh)
    new_access = create_access_token(
        identity=str(user_id),
        additional_claims={"sid": session_id},
    )

    try:
        rotated = rotate_refresh_token(
            session_id=session_id,
            old_jti=old_payload["jti"],
            new_jti=new_refresh_payload["jti"],
            expires_at=new_refresh_payload["exp"],
        )
    except AuthStoreUnavailable as exc:
        return jsonify({
            "code": 503,
            "msg": str(exc),
            "error_code": "AUTH_STORE_UNAVAILABLE",
        }), 503

    if not rotated:
        return auth_error("刷新凭据已失效", 401, "AUTH_REFRESH_REUSED")

    response = jsonify({
        "code": 0,
        "msg": "刷新成功",
        "data": {
            "token": new_access,
            "access_token": new_access,
            "user_id": user["id"],
            "username": user["username"],
            "nickname": user["nickname"],
            "role": user["role"],
        },
    })
    set_refresh_cookies(response, new_refresh)
    return response


@auth_bp.route("/logout", methods=["DELETE"])
@login_required
def logout():
    token = get_jwt()
    user_id = request.current_user["user_id"]
    try:
        revoke_token(token["jti"], token["exp"])
        revoke_login_session(user_id, token.get("sid", ""))
    except AuthStoreUnavailable as exc:
        return jsonify({
            "code": 503,
            "msg": str(exc),
            "error_code": "AUTH_STORE_UNAVAILABLE",
        }), 503

    response = jsonify({"code": 0, "msg": "退出成功"})
    unset_jwt_cookies(response)
    return response


@auth_bp.route("/logout-all", methods=["DELETE"])
@login_required
def logout_all():
    user_id = request.current_user["user_id"]
    try:
        count = revoke_all_login_sessions(user_id)
    except AuthStoreUnavailable as exc:
        return jsonify({
            "code": 503,
            "msg": str(exc),
            "error_code": "AUTH_STORE_UNAVAILABLE",
        }), 503

    response = jsonify({
        "code": 0,
        "msg": "所有设备均已退出",
        "data": {"revoked_sessions": count},
    })
    unset_jwt_cookies(response)
    return response


@auth_bp.route("/verify", methods=["GET"])
@login_required
def verify():
    return jsonify({
        "code": 0,
        "msg": "ok",
        "data": request.current_user,
    })


@auth_bp.route("/userinfo", methods=["GET"])
@login_required
def userinfo():
    user_id = request.current_user["user_id"]
    user = get_user_by_id(user_id)
    if user is None:
        return auth_error("用户不存在", 401, "AUTH_USER_NOT_FOUND")
    return jsonify({"code": 0, "data": user})
