"""Tests for administrator-only RAG document management."""
import io
import os
import tempfile
import unittest
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from redis.exceptions import RedisError

from app.auth import _token_response
from app.extensions import get_redis, init_extensions
from app.rag_documents import normalize_markdown_filename
from app.routes.rag_admin import rag_admin_bp


class RagFilenameTest(unittest.TestCase):
    def test_only_safe_markdown_filenames_are_accepted(self):
        self.assertEqual(normalize_markdown_filename("恋爱知识.md"), "恋爱知识.md")
        with self.assertRaises(ValueError):
            normalize_markdown_filename("../secret.md")
        with self.assertRaises(ValueError):
            normalize_markdown_filename("notes.txt")
        with self.assertRaises(ValueError):
            normalize_markdown_filename(".hidden.md")

    def test_splitter_adds_source_and_chunk_indexes(self):
        from app.llm.rag import parse_markdown_document, split_markdown_text

        text = (
            "---\ntitle: 示例\ntopics:\n  - 沟通\n  - 信任\n---\n\n"
            "# 标题\n\n## 问题\n\n答案内容。"
        )
        metadata, body = parse_markdown_document(text)
        chunks = split_markdown_text(
            text,
            "sample.md",
        )
        self.assertEqual(metadata["topics"], ["沟通", "信任"])
        self.assertNotIn("title: 示例", body)
        self.assertEqual(len(chunks), 1)
        self.assertNotIn("title: 示例", chunks[0].page_content)
        self.assertEqual(chunks[0].metadata["source"], "sample.md")
        self.assertEqual(chunks[0].metadata["chunk_index"], 1)
        self.assertEqual(chunks[0].metadata["section_title"], "问题")
        self.assertEqual(len(chunks[0].metadata["chunk_id"]), 24)
        self.assertEqual(len(chunks[0].metadata["content_sha256"]), 64)


class RagAdminRouteTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.prefix = f"zzx:test:rag:{uuid.uuid4()}"
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
            JWT_COOKIE_CSRF_PROTECT=True,
            REDIS_URL=os.getenv("TEST_REDIS_URL", "redis://127.0.0.1:6379/15"),
            REDIS_AUTH_PREFIX=self.prefix,
            REDIS_CONNECT_TIMEOUT=1,
            REDIS_SOCKET_TIMEOUT=1,
            RAG_DOCUMENTS_DIR=self.temp_dir.name,
            RAG_CHROMA_DIR=str(Path(self.temp_dir.name) / "chroma"),
            RAG_MAX_FILE_SIZE_BYTES=1024 * 1024,
        )
        init_extensions(self.app)
        self.app.register_blueprint(rag_admin_bp)
        try:
            with self.app.app_context():
                get_redis().ping()
        except RedisError as exc:
            self.temp_dir.cleanup()
            self.skipTest(f"Redis is not available: {exc}")
        self.client = self.app.test_client()
        self.admin = {
            "id": 9,
            "username": "rag-admin",
            "nickname": "知识库管理员",
            "role": "admin",
        }
        with self.app.app_context():
            response = _token_response(self.admin)
            self.token = response.get_json()["data"]["access_token"]

    def tearDown(self):
        try:
            with self.app.app_context():
                redis_client = get_redis()
                keys = list(redis_client.scan_iter(match=f"{self.prefix}:*"))
                if keys:
                    redis_client.delete(*keys)
        except (RedisError, AttributeError):
            pass
        self.temp_dir.cleanup()

    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def document_row(self, filename="guide.md"):
        return {
            "id": 12,
            "filename": filename,
            "display_name": Path(filename).stem,
            "file_size": 12,
            "sha256": "a" * 64,
            "chunk_count": 1,
            "status": "ready",
            "last_error": None,
            "uploaded_by": 9,
            "uploader_name": "知识库管理员",
            "created_at": datetime(2026, 1, 1),
            "updated_at": datetime(2026, 1, 1),
        }

    def test_non_admin_cannot_access_document_list(self):
        user = {**self.admin, "role": "user"}
        with patch("app.auth.get_user_by_id", return_value=user):
            response = self.client.get(
                "/api/admin/rag/documents", headers=self.headers()
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error_code"], "AUTH_ADMIN_REQUIRED")

    def test_chunk_details_are_read_from_relational_chunk_table(self):
        chunk = {
            "id": 101,
            "document_id": 12,
            "chunk_id": "a" * 24,
            "index": 1,
            "content": "# 标题\n\n正文内容",
            "content_sha256": "b" * 64,
            "char_count": 10,
            "section_title": "标题",
            "metadata": {"chunk_index": 1, "source": "guide.md"},
            "vector_id": "a" * 24,
            "created_at": datetime(2026, 1, 1),
            "updated_at": datetime(2026, 1, 1),
        }
        with (
            patch("app.auth.get_user_by_id", return_value=self.admin),
            patch("app.routes.rag_admin.get_document", return_value=self.document_row()),
            patch(
                "app.routes.rag_admin.list_document_chunks",
                return_value=[chunk],
            ) as load_chunks,
        ):
            response = self.client.get(
                "/api/admin/rag/documents/12/chunks",
                headers=self.headers(),
            )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()["data"]
        self.assertEqual(payload["chunks"][0]["vector_id"], chunk["chunk_id"])
        load_chunks.assert_called_once_with(12)

    def test_rebuild_is_skipped_when_index_is_current(self):
        current = {
            "up_to_date": True,
            "reason": "当前索引已经是最新",
            "reason_code": "UP_TO_DATE",
        }
        with (
            patch("app.auth.get_user_by_id", return_value=self.admin),
            patch("app.routes.rag_admin._index_status", return_value=current),
            patch("app.routes.rag_admin._refresh_index") as rebuild,
        ):
            response = self.client.post(
                "/api/admin/rag/rebuild",
                headers=self.headers(),
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["data"]["rebuilt"])
        rebuild.assert_not_called()

    def test_stale_index_is_rebuilt(self):
        stale = {
            "up_to_date": False,
            "reason": "源文档内容已经发生变化",
            "reason_code": "SOURCE_CHANGED",
        }
        current = {
            "up_to_date": True,
            "reason": "当前索引已经是最新",
            "reason_code": "UP_TO_DATE",
        }
        with (
            patch("app.auth.get_user_by_id", return_value=self.admin),
            patch("app.routes.rag_admin._index_status", side_effect=[stale, current]),
            patch(
                "app.routes.rag_admin._refresh_index",
                return_value={"document_count": 1, "chunk_count": 1},
            ) as rebuild,
        ):
            response = self.client.post(
                "/api/admin/rag/rebuild",
                headers=self.headers(),
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["data"]["rebuilt"])
        rebuild.assert_called_once_with(force=True)

    def test_admin_can_upload_markdown_and_trigger_rebuild(self):
        row = self.document_row()
        with (
            patch("app.auth.get_user_by_id", return_value=self.admin),
            patch("app.routes.rag_admin.create_document", return_value=12),
            patch("app.routes.rag_admin.get_document", return_value=row),
            patch(
                "app.routes.rag_admin._refresh_index",
                return_value={
                    "document_count": 1,
                    "chunk_count": 1,
                    "chunk_counts": {"guide.md": 1},
                },
            ) as rebuild,
        ):
            response = self.client.post(
                "/api/admin/rag/documents",
                headers=self.headers(),
                data={"file": (io.BytesIO(b"# Guide\n\nContent"), "guide.md")},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 201)
        self.assertTrue((Path(self.temp_dir.name) / "guide.md").is_file())
        rebuild.assert_called_once()

    def test_admin_upload_rejects_non_markdown_file(self):
        with patch("app.auth.get_user_by_id", return_value=self.admin):
            response = self.client.post(
                "/api/admin/rag/documents",
                headers=self.headers(),
                data={"file": (io.BytesIO(b"text"), "guide.txt")},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error_code"], "RAG_FILE_INVALID")

    def test_failed_rebuild_rolls_back_uploaded_file(self):
        with (
            patch("app.auth.get_user_by_id", return_value=self.admin),
            patch("app.routes.rag_admin.create_document", return_value=13),
            patch("app.routes.rag_admin.mark_document_error"),
            patch("app.routes.rag_admin.delete_document_record"),
            patch(
                "app.routes.rag_admin._refresh_index",
                side_effect=RuntimeError("index failed"),
            ),
            patch("app.routes.rag_admin._restore_index_after_rollback"),
        ):
            response = self.client.post(
                "/api/admin/rag/documents",
                headers=self.headers(),
                data={"file": (io.BytesIO(b"# Broken"), "broken.md")},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 500)
        self.assertFalse((Path(self.temp_dir.name) / "broken.md").exists())


if __name__ == "__main__":
    unittest.main()
