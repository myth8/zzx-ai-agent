"""输入边界、AST 计算器和稳定 SSE 错误的安全回归测试。"""
import json
import logging
import unittest

from flask import Flask

from app.utils.request_context import init_request_context
from app.utils.logging_config import RedactingFormatter
from app.utils.safe_math import SafeMathError, evaluate_math_expression
from app.utils.sse import sse_response
from app.utils.validation import (
    CHAT_MESSAGE_MAX_LENGTH,
    InputValidationError,
    validate_chat_message,
    validate_document_metadata,
    validate_markdown_mime_type,
    validate_username,
)


class SafeMathTest(unittest.TestCase):
    def test_approved_arithmetic_is_evaluated(self):
        self.assertEqual(evaluate_math_expression("(2 + 3) * 4"), 20)
        self.assertEqual(evaluate_math_expression("9 // 2"), 4)

    def test_code_execution_and_resource_abuse_are_rejected(self):
        dangerous = (
            "__import__('os').system('id')",
            "(1).__class__",
            "2 ** 999999",
            "[1, 2, 3]",
        )
        for expression in dangerous:
            with self.subTest(expression=expression):
                with self.assertRaises(SafeMathError):
                    evaluate_math_expression(expression)


class InputValidationTest(unittest.TestCase):
    def test_username_and_chat_message_boundaries(self):
        self.assertEqual(validate_username("valid_user-1"), "valid_user-1")
        with self.assertRaises(InputValidationError):
            validate_username("bad user")
        with self.assertRaises(InputValidationError):
            validate_chat_message("x" * (CHAT_MESSAGE_MAX_LENGTH + 1))

    def test_markdown_mime_and_metadata_boundaries(self):
        self.assertEqual(validate_markdown_mime_type("text/markdown"), "text/markdown")
        with self.assertRaises(InputValidationError):
            validate_markdown_mime_type("text/html")
        with self.assertRaises(InputValidationError):
            validate_document_metadata({"x": {"a": {"b": {"c": {"d": "deep"}}}}})


class SseErrorTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        init_request_context(self.app)

        @self.app.get("/stream")
        def stream():
            def broken_generator():
                raise RuntimeError("database-password=must-not-leak")
                yield "unreachable"

            return sse_response(broken_generator)

        @self.app.get("/error")
        def error():
            from app.utils.responses import api_error
            return api_error(
                "VALIDATION_ERROR", "输入无效", 400, {"field": "message"}
            )

        self.client = self.app.test_client()

    def test_stream_error_is_stable_and_correlated(self):
        response = self.client.get(
            "/stream", headers={"X-Request-ID": "test-request-123"}
        )
        body = response.get_data(as_text=True)
        self.assertIn("event: error", body)
        self.assertNotIn("database-password", body)
        data_line = next(line for line in body.splitlines() if line.startswith("data: {") )
        payload = json.loads(data_line.removeprefix("data: "))
        self.assertEqual(payload["code"], "CHAT_STREAM_FAILED")
        self.assertEqual(payload["request_id"], "test-request-123")
        self.assertEqual(response.headers["X-Request-ID"], "test-request-123")

    def test_json_error_uses_the_same_request_id(self):
        response = self.client.get(
            "/error", headers={"X-Request-ID": "test-request-456"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {
            "code": "VALIDATION_ERROR",
            "message": "输入无效",
            "request_id": "test-request-456",
            "details": {"field": "message"},
        })
        self.assertEqual(response.headers["X-Request-ID"], "test-request-456")


class LoggingSecurityTest(unittest.TestCase):
    def test_formatter_redacts_secrets_inside_tracebacks(self):
        try:
            raise RuntimeError("password=super-secret-value")
        except RuntimeError:
            record = logging.LogRecord(
                "test", logging.ERROR, __file__, 1, "operation failed", (),
                exc_info=__import__("sys").exc_info(),
            )
        record.request_id = "test-request"
        output = RedactingFormatter(
            "%(levelname)s request_id=%(request_id)s %(message)s"
        ).format(record)
        self.assertNotIn("super-secret-value", output)
        self.assertIn("password=[REDACTED]", output)


if __name__ == "__main__":
    unittest.main()
