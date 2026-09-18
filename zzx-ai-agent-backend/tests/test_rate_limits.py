"""Redis-backed differential rate limit regression tests."""
import os
import unittest

from flask import Flask, jsonify, request
from redis.exceptions import RedisError

from app.extensions import get_redis, init_extensions
from app.utils.rate_limit import (
    admin_write_rate_limit,
    chat_rate_limit,
    login_account_rate_limit,
    register_rate_limit,
)
from app.utils.request_context import init_request_context
from app.utils.responses import api_error


class RedisRateLimitTest(unittest.TestCase):
    def setUp(self):
        self.prefix = "zzx:test:ratelimit"
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            REDIS_URL=os.getenv("TEST_REDIS_URL", "redis://127.0.0.1:6379/15"),
            REDIS_CONNECT_TIMEOUT=1,
            REDIS_SOCKET_TIMEOUT=1,
            RATELIMIT_STORAGE_URI=os.getenv(
                "TEST_REDIS_URL", "redis://127.0.0.1:6379/15"
            ),
            RATELIMIT_KEY_PREFIX=self.prefix,
            RATELIMIT_HEADERS_ENABLED=True,
            RATELIMIT_SWALLOW_ERRORS=False,
            REGISTER_RATE_LIMIT="2 per hour",
            LOGIN_ACCOUNT_RATE_LIMIT="2 per minute",
            CHAT_RATE_LIMIT="2 per minute",
            ADMIN_WRITE_RATE_LIMIT="1 per minute",
        )
        init_request_context(self.app)
        init_extensions(self.app)

        @self.app.errorhandler(429)
        def limited(_error):
            return api_error(
                "RATE_LIMIT_EXCEEDED", "请求过于频繁，请稍后重试", 429
            )

        @self.app.post("/register-like")
        @register_rate_limit
        def register_like():
            return jsonify({"ok": True})

        @self.app.post("/login-like")
        @login_account_rate_limit
        def login_like():
            return jsonify({"ok": True})

        @chat_rate_limit
        def limited_chat():
            return jsonify({"ok": True})

        @self.app.get("/chat-like/<int:user_id>")
        def chat_like(user_id):
            request.current_user = {"user_id": user_id}
            return limited_chat()

        @admin_write_rate_limit
        def limited_admin_write():
            return jsonify({"ok": True})

        @self.app.post("/admin-like/<operation>/<int:user_id>")
        def admin_like(operation, user_id):
            request.current_user = {"user_id": user_id}
            return limited_admin_write()

        try:
            with self.app.app_context():
                redis_client = get_redis()
                redis_client.ping()
                self.clear_rate_limits(redis_client)
        except RedisError as exc:
            self.skipTest(f"Redis is not available: {exc}")
        self.client = self.app.test_client()

    def tearDown(self):
        try:
            with self.app.app_context():
                redis_client = get_redis()
                keys = list(redis_client.scan_iter(
                    match=f"LIMITS:LIMITER/{self.prefix}/*"
                ))
                if keys:
                    redis_client.delete(*keys)
        except (RedisError, AttributeError):
            pass

    def clear_rate_limits(self, client):
        keys = list(client.scan_iter(
            match=f"LIMITS:LIMITER/{self.prefix}/*"
        ))
        if keys:
            client.delete(*keys)

    def assert_limited(self, response):
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.get_json()["code"], "RATE_LIMIT_EXCEEDED")
        self.assertTrue(response.headers.get("X-RateLimit-Limit"))
        self.assertTrue(response.headers.get("Retry-After"))

    def test_registration_is_limited_by_source_ip(self):
        self.assertEqual(self.client.post("/register-like").status_code, 200)
        self.assertEqual(self.client.post("/register-like").status_code, 200)
        self.assert_limited(self.client.post("/register-like"))

    def test_login_limit_is_scoped_by_normalized_account_hash(self):
        for username in ("Alice", " alice "):
            response = self.client.post("/login-like", json={"username": username})
            self.assertEqual(response.status_code, 200)
        self.assert_limited(
            self.client.post("/login-like", json={"username": "ALICE"})
        )
        # A different account does not consume Alice's account bucket.
        self.assertEqual(
            self.client.post("/login-like", json={"username": "bob"}).status_code,
            200,
        )

    def test_chat_limit_is_per_user(self):
        self.assertEqual(self.client.get("/chat-like/7").status_code, 200)
        self.assertEqual(self.client.get("/chat-like/7").status_code, 200)
        self.assert_limited(self.client.get("/chat-like/7"))
        self.assertEqual(self.client.get("/chat-like/8").status_code, 200)

    def test_admin_write_limit_is_shared_across_operations(self):
        self.assertEqual(self.client.post("/admin-like/upload/9").status_code, 200)
        self.assert_limited(self.client.post("/admin-like/rebuild/9"))
        self.assertEqual(self.client.post("/admin-like/upload/10").status_code, 200)

    def test_limiter_state_is_stored_in_redis_with_configured_prefix(self):
        self.client.post("/register-like")
        with self.app.app_context():
            keys = list(get_redis().scan_iter(
                match=f"LIMITS:LIMITER/{self.prefix}/*"
            ))
        self.assertTrue(keys)


if __name__ == "__main__":
    unittest.main()
