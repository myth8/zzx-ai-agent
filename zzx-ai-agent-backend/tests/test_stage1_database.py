"""MySQL integration tests for stage 1 transactions and idempotency."""
import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

from flask import Flask

from app.chat_history import create_session
from app.db import connection, init_db_engine, transaction
from app.repositories.chat_runs import transition_chat_run
from app.services.chat_submission import IdempotencyConflict, create_chat_submission


@unittest.skipUnless(
    os.getenv("RUN_MYSQL_INTEGRATION") == "1",
    "set RUN_MYSQL_INTEGRATION=1 to run MySQL integration tests",
)
class Stage1DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            MYSQL_HOST=os.getenv("MYSQL_HOST", "127.0.0.1"),
            MYSQL_PORT=int(os.getenv("MYSQL_PORT", "3306")),
            MYSQL_USER=os.environ["MYSQL_USER"],
            MYSQL_PASSWORD=os.environ["MYSQL_PASSWORD"],
            MYSQL_DB=os.environ["MYSQL_DB"],
            MYSQL_POOL_SIZE=8,
            MYSQL_MAX_OVERFLOW=12,
            MYSQL_POOL_TIMEOUT=10,
            MYSQL_POOL_RECYCLE=1800,
            MYSQL_CONNECT_TIMEOUT=5,
            MYSQL_READ_TIMEOUT=30,
            MYSQL_WRITE_TIMEOUT=30,
            MYSQL_SLOW_QUERY_MS=500,
        )
        init_db_engine(self.app)
        self.username = f"stage1-{uuid.uuid4()}"
        with self.app.app_context(), transaction() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (username,nickname,password,role) VALUES (%s,%s,%s,'user')",
                (self.username, "Stage 1 test", "!disabled-test-account"),
            )
            self.user_id = cur.lastrowid
        with self.app.app_context():
            self.session_id = create_session(self.user_id, "chain", "stage1-test")

    def tearDown(self):
        if not hasattr(self, "user_id"):
            return
        with self.app.app_context(), transaction() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE id=%s", (self.user_id,))
        self.app.extensions["mysql_engine"].dispose()

    def _submit(self, client_message_id, key, content="hello"):
        with self.app.app_context():
            return create_chat_submission(
                user_id=self.user_id,
                session_id=self.session_id,
                content=content,
                client_message_id=client_message_id,
                idempotency_key=key,
                endpoint=f"/api/sessions/{self.session_id}/messages",
                agent_type="chain",
                request_id=uuid.uuid4().hex,
                model="test-model",
            )

    def test_twenty_duplicate_submissions_create_one_message_and_run(self):
        client_message_id = str(uuid.uuid4())
        key = uuid.uuid4().hex
        with ThreadPoolExecutor(max_workers=20) as executor:
            results = list(
                executor.map(
                    lambda _index: self._submit(client_message_id, key),
                    range(20),
                )
            )
        self.assertEqual(sum(item["created"] for item in results), 1)
        self.assertEqual(len({item["data"]["run_id"] for item in results}), 1)
        with self.app.app_context(), connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) count,MIN(msg_order) min_order,MAX(msg_order) max_order "
                "FROM chat_messages WHERE session_id=%s",
                (self.session_id,),
            )
            message_stats = cur.fetchone()
            cur.execute("SELECT COUNT(*) count FROM chat_runs WHERE session_id=%s", (self.session_id,))
            run_count = cur.fetchone()["count"]
            cur.execute("SELECT next_message_order FROM sessions WHERE session_id=%s", (self.session_id,))
            next_order = cur.fetchone()["next_message_order"]
        self.assertEqual(message_stats, {"count": 1, "min_order": 1, "max_order": 1})
        self.assertEqual(run_count, 1)
        self.assertEqual(next_order, 2)

    def test_same_key_with_different_content_conflicts(self):
        client_message_id = str(uuid.uuid4())
        key = uuid.uuid4().hex
        self._submit(client_message_id, key, "first")
        with self.assertRaises(IdempotencyConflict):
            self._submit(client_message_id, key, "different")

    def test_run_state_transition_uses_status_and_version_compare_and_swap(self):
        result = self._submit(str(uuid.uuid4()), uuid.uuid4().hex)
        run_id = result["data"]["run_id"]
        with self.app.app_context():
            self.assertTrue(
                transition_chat_run(
                    self.user_id,
                    run_id,
                    from_status="queued",
                    to_status="running",
                    expected_version=1,
                )
            )
            self.assertFalse(
                transition_chat_run(
                    self.user_id,
                    run_id,
                    from_status="queued",
                    to_status="running",
                    expected_version=1,
                )
            )
            with self.assertRaises(ValueError):
                transition_chat_run(
                    self.user_id,
                    run_id,
                    from_status="succeeded",
                    to_status="running",
                    expected_version=2,
                )
