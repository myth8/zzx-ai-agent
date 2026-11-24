"""Regression tests for user ownership checks on session resources."""
import os
import unittest
import uuid
from unittest.mock import patch

from flask import Flask
from redis.exceptions import RedisError

from app.auth import _token_response
from app.extensions import get_redis, init_extensions
from app.routes.session import session_bp


class SessionOwnershipTest(unittest.TestCase):
    def setUp(self):
        self.prefix = f"zzx:test:session:{uuid.uuid4()}"
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
            JWT_TOKEN_LOCATION=["headers"],
            REDIS_URL=os.getenv("TEST_REDIS_URL", "redis://127.0.0.1:6379/15"),
            REDIS_AUTH_PREFIX=self.prefix,
            RATELIMIT_KEY_PREFIX="zzx:test:ratelimit",
            REDIS_CONNECT_TIMEOUT=1,
            REDIS_SOCKET_TIMEOUT=1,
        )
        init_extensions(self.app)
        self.app.register_blueprint(session_bp)
        try:
            with self.app.app_context():
                redis_client = get_redis()
                redis_client.ping()
                keys = list(redis_client.scan_iter(
                    match="LIMITS:LIMITER/zzx:test:ratelimit/*"
                ))
                if keys:
                    redis_client.delete(*keys)
        except RedisError as exc:
            self.skipTest(f"Redis is not available: {exc}")

        self.client = self.app.test_client()
        self.user = {
            "id": 7,
            "username": "owner-a",
            "nickname": "用户 A",
            "role": "user",
        }
        with self.app.app_context():
            response = _token_response(self.user)
            self.token = response.get_json()["data"]["access_token"]

    def tearDown(self):
        try:
            with self.app.app_context():
                client = get_redis()
                keys = list(client.scan_iter(match=f"{self.prefix}*"))
                keys.extend(client.scan_iter(
                    match="LIMITS:LIMITER/zzx:test:ratelimit/*"
                ))
                if keys:
                    client.delete(*keys)
        except (RedisError, AttributeError):
            pass

    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def test_user_cannot_read_rename_or_delete_another_users_session(self):
        session_id = "owned-by-user-b"
        with (
            patch("app.auth.get_user_by_id", return_value=self.user),
            patch("app.chat_history.get_user_session", return_value=None) as lookup,
            patch("app.routes.session.rename_session", return_value=False) as rename,
            patch("app.routes.session.delete_session", return_value=False) as delete,
            patch("app.routes.session.get_session_messages") as messages,
        ):
            read_response = self.client.get(
                f"/api/session/{session_id}/messages", headers=self.headers()
            )
            rename_response = self.client.put(
                "/api/session/rename",
                headers=self.headers(),
                json={"session_id": session_id, "title": "越权修改"},
            )
            delete_response = self.client.delete(
                f"/api/session/{session_id}", headers=self.headers()
            )

        self.assertEqual(read_response.status_code, 404)
        self.assertEqual(rename_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)
        lookup.assert_called_once_with(self.user["id"], session_id)
        rename.assert_called_once_with(self.user["id"], session_id, "越权修改")
        delete.assert_called_once_with(self.user["id"], session_id)
        messages.assert_not_called()


if __name__ == "__main__":
    unittest.main()
