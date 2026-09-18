"""Security regression tests for Redis-backed JWT authentication."""
import os
import time
import unittest
import uuid
from unittest.mock import MagicMock, patch

import jwt as pyjwt
from flask import Flask, jsonify, request
from redis.exceptions import RedisError

from app.auth import _token_response, admin_required, auth_bp, login_required
from app.auth_store import revoke_login_session
from app.extensions import get_redis, init_extensions
from app.routes.love_app import love_bp
from app.routes.manus import manus_bp


class AuthSecurityTest(unittest.TestCase):
    def setUp(self):
        self.prefix = f"zzx:test:auth:{uuid.uuid4()}"
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            JWT_SECRET_KEY="test-only-jwt-secret-with-at-least-32-bytes",
            JWT_ACCESS_TOKEN_EXPIRES=300,
            JWT_REFRESH_TOKEN_EXPIRES=3600,
            JWT_ENCODE_ISSUER="zzx-ai-agent-test",
            JWT_DECODE_ISSUER="zzx-ai-agent-test",
            JWT_ENCODE_AUDIENCE="zzx-ai-agent-test-client",
            JWT_DECODE_AUDIENCE="zzx-ai-agent-test-client",
            JWT_TOKEN_LOCATION=["headers", "cookies"],
            JWT_REFRESH_COOKIE_PATH="/api/auth",
            JWT_REFRESH_CSRF_COOKIE_PATH="/",
            JWT_COOKIE_CSRF_PROTECT=True,
            JWT_CSRF_IN_COOKIES=True,
            JWT_COOKIE_SECURE=False,
            JWT_SESSION_COOKIE=False,
            ADMIN_INVITE_CODE="9527",
            REDIS_URL=os.getenv("TEST_REDIS_URL", "redis://127.0.0.1:6379/15"),
            REDIS_AUTH_PREFIX=self.prefix,
            RATELIMIT_KEY_PREFIX="zzx:test:ratelimit",
            REDIS_CONNECT_TIMEOUT=1,
            REDIS_SOCKET_TIMEOUT=1,
        )
        init_extensions(self.app)
        self.app.register_blueprint(auth_bp)
        self.app.register_blueprint(love_bp)
        self.app.register_blueprint(manus_bp)

        @self.app.get("/member-only")
        @login_required
        def member_only():
            return jsonify(request.current_user)

        @self.app.get("/admin-only")
        @admin_required
        def admin_only():
            return jsonify({"ok": True})

        try:
            with self.app.app_context():
                redis_client = get_redis()
                redis_client.ping()
                self.clear_rate_limits(redis_client)
        except RedisError as exc:
            self.skipTest(f"Redis is not available: {exc}")

        self.client = self.app.test_client()
        self.user = {
            "id": 7,
            "username": "tester",
            "nickname": "测试用户",
            "role": "user",
        }

    def tearDown(self):
        if not hasattr(self, "app"):
            return
        try:
            with self.app.app_context():
                client = get_redis()
                keys = list(client.scan_iter(match=f"{self.prefix}:*"))
                keys.extend(
                    client.scan_iter(match="LIMITS:LIMITER/zzx:test:ratelimit/*")
                )
                if keys:
                    client.delete(*keys)
        except RedisError:
            pass

    @staticmethod
    def clear_rate_limits(client):
        keys = list(
            client.scan_iter(match="LIMITS:LIMITER/zzx:test:ratelimit/*")
        )
        if keys:
            client.delete(*keys)

    def issue_tokens(self, user=None):
        with self.app.app_context():
            response = _token_response(user or self.user)
            payload = response.get_json()["data"]
            return payload["access_token"], response

    @staticmethod
    def bearer(token):
        return {"Authorization": f"Bearer {token}"}

    def test_missing_token_uses_stable_error_shape(self):
        response = self.client.get("/member-only")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["code"], "AUTH_TOKEN_MISSING")

    def test_both_sse_chat_endpoints_reject_unauthenticated_requests(self):
        for path in (
            "/api/ai/love_app/chat/sse?message=hello",
            "/api/ai/manus/chat?message=hello",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(
                    response.get_json()["code"], "AUTH_TOKEN_MISSING"
                )

    def make_raw_token(self, *, secret=None, audience=None, expires_at=None):
        """Build deliberately invalid tokens without creating Redis login state."""
        now = int(time.time())
        payload = {
            "fresh": False,
            "iat": now,
            "jti": str(uuid.uuid4()),
            "type": "access",
            "sub": str(self.user["id"]),
            "nbf": now,
            "exp": expires_at if expires_at is not None else now + 300,
            "iss": self.app.config["JWT_ENCODE_ISSUER"],
            "aud": audience or self.app.config["JWT_ENCODE_AUDIENCE"],
        }
        return pyjwt.encode(
            payload,
            secret or self.app.config["JWT_SECRET_KEY"],
            algorithm="HS256",
        )

    def test_expired_token_is_rejected_with_stable_code(self):
        token = self.make_raw_token(expires_at=int(time.time()) - 10)
        response = self.client.get("/member-only", headers=self.bearer(token))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["code"], "AUTH_TOKEN_EXPIRED")

    def test_wrong_signature_token_is_rejected(self):
        token = self.make_raw_token(
            secret="another-test-signing-secret-with-32-bytes"
        )
        response = self.client.get("/member-only", headers=self.bearer(token))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["code"], "AUTH_TOKEN_INVALID")

    def test_wrong_audience_token_is_rejected(self):
        token = self.make_raw_token(audience="another-client")
        response = self.client.get("/member-only", headers=self.bearer(token))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["code"], "AUTH_TOKEN_INVALID")

    def test_admin_required_reads_current_database_role(self):
        token, _ = self.issue_tokens()
        with patch("app.auth.get_user_by_id", return_value=self.user):
            response = self.client.get("/admin-only", headers=self.bearer(token))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["code"], "AUTH_ADMIN_REQUIRED")

        promoted = {**self.user, "role": "admin"}
        with patch("app.auth.get_user_by_id", return_value=promoted):
            response = self.client.get("/admin-only", headers=self.bearer(token))
        self.assertEqual(response.status_code, 200)

    def test_refresh_rotation_and_session_revocation(self):
        token, login_response = self.issue_tokens()
        for cookie in login_response.headers.getlist("Set-Cookie"):
            self.client.set_cookie(
                cookie.split("=", 1)[0],
                cookie.split("=", 1)[1].split(";", 1)[0],
            )

        csrf_cookie = self.client.get_cookie("csrf_refresh_token")
        with patch("app.auth.get_user_by_id", return_value=self.user):
            refreshed = self.client.post(
                "/api/auth/refresh",
                headers={"X-CSRF-TOKEN": csrf_cookie.value},
            )
        self.assertEqual(refreshed.status_code, 200)
        new_token = refreshed.get_json()["data"]["access_token"]

        with patch("app.auth.get_user_by_id", return_value=self.user):
            member = self.client.get(
                "/member-only", headers=self.bearer(new_token)
            )
        self.assertEqual(member.status_code, 200)

        from flask_jwt_extended import decode_token

        with self.app.app_context():
            session_id = decode_token(new_token)["sid"]
            revoke_login_session(self.user["id"], session_id)

        with patch("app.auth.get_user_by_id", return_value=self.user):
            revoked = self.client.get(
                "/member-only", headers=self.bearer(token)
            )
        self.assertEqual(revoked.status_code, 401)
        self.assertEqual(revoked.get_json()["code"], "AUTH_TOKEN_REVOKED")

    def test_register_invite_controls_initial_role(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None

        with patch("app.auth.get_db", return_value=connection):
            invalid = self.client.post("/api/auth/register", json={
                "username": "invite-user",
                "nickname": "邀请码用户",
                "password": "secret123",
                "invite_code": "wrong",
            })
            accepted = self.client.post("/api/auth/register", json={
                "username": "invite-user",
                "nickname": "邀请码用户",
                "password": "secret123",
                "invite_code": "9527",
            })

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.get_json()["code"], "AUTH_INVITE_INVALID")
        self.assertEqual(accepted.status_code, 201)
        self.assertEqual(accepted.get_json()["data"]["role"], "admin")
        insert_call = next(
            call for call in cursor.execute.call_args_list
            if "INSERT INTO users" in call.args[0]
        )
        self.assertEqual(insert_call.args[1][-1], "admin")

    def test_logged_in_user_can_redeem_admin_invite(self):
        token, _ = self.issue_tokens()
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.rowcount = 1

        with (
            patch("app.auth.get_user_by_id", return_value=self.user),
            patch("app.auth.get_db", return_value=connection),
        ):
            invalid = self.client.post(
                "/api/auth/invite/redeem",
                json={"invite_code": "wrong"},
                headers=self.bearer(token),
            )
            accepted = self.client.post(
                "/api/auth/invite/redeem",
                json={"invite_code": "9527"},
                headers=self.bearer(token),
            )

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.get_json()["code"], "AUTH_INVITE_INVALID")
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.get_json()["data"]["role"], "admin")
        connection.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
