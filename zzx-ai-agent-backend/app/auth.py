import time
from functools import wraps

import pymysql
from flask import Blueprint, request, jsonify, current_app
from werkzeug.security import generate_password_hash, check_password_hash

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def get_db():
    """Get MySQL database connection."""
    cfg = current_app.config
    return pymysql.connect(
        host=cfg.get("MYSQL_HOST", "127.0.0.1"),
        port=cfg.get("MYSQL_PORT", 3306),
        user=cfg.get("MYSQL_USER", "root"),
        password=cfg.get("MYSQL_PASSWORD", ""),
        database=cfg.get("MYSQL_DB", "zzx_agent_db"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def init_db():
    """Initialize database table schema."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id         INT AUTO_INCREMENT PRIMARY KEY,
                    username   VARCHAR(50)  NOT NULL UNIQUE,
                    nickname   VARCHAR(50)  NOT NULL,
                    password   VARCHAR(255) NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        conn.commit()
    finally:
        conn.close()


def make_token(user_id, username):
    """Generate a simple JWT token (HS256)."""
    import jwt as pyjwt
    secret = current_app.config["JWT_SECRET"]
    payload = {
        "user_id":  user_id,
        "username": username,
        "exp":      int(time.time()) + 86400 * 7,  # 7 days
    }
    return pyjwt.encode(payload, secret, algorithm="HS256")


def decode_token(token):
    """Decode JWT token, return payload or None."""
    import jwt as pyjwt
    secret = current_app.config["JWT_SECRET"]
    try:
        return pyjwt.decode(token, secret, algorithms=["HS256"])
    except Exception:
        return None


def login_required(f):
    """Decorator: require a valid Bearer token."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"code": 401, "msg": "未登录或 Token 已过期"}), 401
        token = auth[7:]
        payload = decode_token(token)
        if payload is None:
            return jsonify({"code": 401, "msg": "Token 无效或已过期"}), 401
        request.current_user = payload
        return f(*args, **kwargs)
    return decorated


# --- Register -------------------------------------------------

@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    nickname = (data.get("nickname") or "").strip()
    password = (data.get("password") or "").strip()

    if not username or not nickname or not password:
        return jsonify({"code": 400, "msg": "账号、昵称、密码不能为空"}), 400
    if len(username) < 3 or len(username) > 50:
        return jsonify({"code": 400, "msg": "账号长度为 3-50 个字符"}), 400
    if len(password) < 6:
        return jsonify({"code": 400, "msg": "密码长度至少 6 位"}), 400

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE username=%s", (username,))
            if cur.fetchone():
                return jsonify({"code": 409, "msg": "该账号已被注册"}), 409

            hashed = generate_password_hash(password)
            cur.execute(
                "INSERT INTO users (username, nickname, password) VALUES (%s, %s, %s)",
                (username, nickname, hashed),
            )
        conn.commit()
    finally:
        conn.close()

    return jsonify({"code": 0, "msg": "注册成功"}), 201


# --- Login ----------------------------------------------------

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
                "SELECT id, username, nickname, password FROM users WHERE username=%s",
                (username,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if row is None or not check_password_hash(row["password"], password):
        return jsonify({"code": 401, "msg": "账号或密码错误"}), 401

    token = make_token(row["id"], row["username"])
    return jsonify({
        "code": 0,
        "msg": "登录成功",
        "data": {
            "token":    token,
            "user_id":  row["id"],
            "username": row["username"],
            "nickname": row["nickname"],
        },
    })


# --- Verify Token ---------------------------------------------

@auth_bp.route("/verify", methods=["GET"])
@login_required
def verify():
    return jsonify({
        "code": 0,
        "msg": "ok",
        "data": {
            "user_id":  request.current_user["user_id"],
            "username": request.current_user["username"],
        },
    })


# --- User Info ------------------------------------------------

@auth_bp.route("/userinfo", methods=["GET"])
@login_required
def userinfo():
    user_id = request.current_user["user_id"]
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, nickname, created_at FROM users WHERE id=%s",
                (user_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        return jsonify({"code": 404, "msg": "用户不存在"}), 404
    return jsonify({"code": 0, "data": row})
