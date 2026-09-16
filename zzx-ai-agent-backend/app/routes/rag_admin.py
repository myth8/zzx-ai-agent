"""Administrator-only RAG document management APIs."""
import os
import threading
import uuid

from flask import Blueprint, current_app, jsonify, request
from pymysql.err import IntegrityError

from app.auth import admin_required
from app.rag_documents import (
    create_document,
    delete_document_record,
    document_path,
    get_document,
    list_all_chunk_ids,
    list_document_chunks,
    list_documents,
    mark_document_error,
    normalize_markdown_filename,
    update_index_results,
)


rag_admin_bp = Blueprint("rag_admin", __name__, url_prefix="/api/admin/rag")
_mutation_lock = threading.Lock()


def _ok(data=None, message="操作成功", status=200):
    return jsonify({"code": 0, "msg": message, "data": data}), status


def _error(message, status, error_code):
    return jsonify({
        "code": status,
        "msg": message,
        "error_code": error_code,
    }), status


def _serialize_document(row):
    if row is None:
        return None
    result = dict(row)
    for key in ("created_at", "updated_at"):
        value = result.get(key)
        if value is not None:
            result[key] = value.isoformat()
    return result


def _refresh_index(force=False):
    from app.llm.rag import rebuild_engine

    result = rebuild_engine(force=force)
    update_index_results(result["chunk_counts"])
    return result


def _restore_index_after_rollback():
    """Best-effort repair when a filesystem mutation has been rolled back."""
    try:
        from app.llm.rag import rebuild_initialized_engine

        result = rebuild_initialized_engine()
        if result is not None:
            update_index_results(result["chunk_counts"])
    except Exception:
        current_app.logger.exception("RAG index rollback refresh failed")


def _index_status():
    from app.llm.rag import inspect_index_status

    result = inspect_index_status(
        current_app.config["RAG_DOCUMENTS_DIR"],
        current_app.config["RAG_CHROMA_DIR"],
    )
    expected_ids = set(result.pop("expected_chunk_ids", []))
    database_ids = list_all_chunk_ids()
    result["database_chunk_count"] = len(database_ids)
    if result["up_to_date"] and database_ids != expected_ids:
        result.update({
            "up_to_date": False,
            "reason": "数据库切片与源文档不一致",
            "reason_code": "DATABASE_MISMATCH",
        })
    return result


@rag_admin_bp.get("/documents")
@admin_required
def documents():
    rows = [_serialize_document(row) for row in list_documents()]
    return _ok({
        "documents": rows,
        "document_count": len(rows),
        "chunk_count": sum(row["chunk_count"] for row in rows),
    })


@rag_admin_bp.get("/index-status")
@admin_required
def index_status():
    return _ok(_index_status())


@rag_admin_bp.get("/documents/<int:document_id>")
@admin_required
def document_detail(document_id):
    row = get_document(document_id)
    if row is None:
        return _error("文档不存在", 404, "RAG_DOCUMENT_NOT_FOUND")
    path = document_path(row["filename"])
    if not path.is_file():
        return _error("文档文件不存在", 404, "RAG_FILE_NOT_FOUND")
    from app.llm.rag import parse_markdown_document

    raw_content = path.read_text(encoding="utf-8")
    file_metadata, body = parse_markdown_document(raw_content)
    payload = _serialize_document(row)
    payload["document_metadata"] = file_metadata
    payload["content"] = body
    return _ok(payload)


@rag_admin_bp.get("/documents/<int:document_id>/chunks")
@admin_required
def document_chunks(document_id):
    row = get_document(document_id)
    if row is None:
        return _error("文档不存在", 404, "RAG_DOCUMENT_NOT_FOUND")
    data = [_serialize_document(chunk) for chunk in list_document_chunks(document_id)]
    return _ok({"document_id": document_id, "chunks": data, "count": len(data)})


@rag_admin_bp.post("/documents")
@admin_required
def upload_document():
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return _error("请选择要上传的 Markdown 文件", 400, "RAG_FILE_REQUIRED")
    try:
        filename = normalize_markdown_filename(uploaded.filename)
    except ValueError as exc:
        return _error(str(exc), 400, "RAG_FILE_INVALID")

    max_bytes = current_app.config["RAG_MAX_FILE_SIZE_BYTES"]
    content = uploaded.stream.read(max_bytes + 1)
    if len(content) > max_bytes:
        return _error("文件大小超过限制", 413, "RAG_FILE_TOO_LARGE")
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        return _error("Markdown 文件必须使用 UTF-8 编码", 400, "RAG_FILE_ENCODING_INVALID")
    if not content.strip():
        return _error("不能上传空文档", 400, "RAG_FILE_EMPTY")
    try:
        from app.llm.rag import parse_markdown_document, split_markdown_text

        _, body = parse_markdown_document(text_content)
        chunks = split_markdown_text(text_content, filename)
    except Exception as exc:
        return _error(
            f"Markdown 元数据格式无效：{exc}",
            400,
            "RAG_METADATA_INVALID",
        )
    if not body.strip() or not chunks:
        return _error("Markdown 文档必须包含正文", 400, "RAG_BODY_EMPTY")

    with _mutation_lock:
        path = document_path(filename)
        if path.exists():
            return _error("同名文档已存在", 409, "RAG_DOCUMENT_EXISTS")

        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.uploading")
        document_id = None
        try:
            temporary.write_bytes(content)
            os.replace(temporary, path)
            document_id = create_document(
                filename,
                content,
                request.current_user["user_id"],
            )
            index_result = _refresh_index()
        except IntegrityError:
            path.unlink(missing_ok=True)
            temporary.unlink(missing_ok=True)
            return _error("同名文档已存在", 409, "RAG_DOCUMENT_EXISTS")
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            path.unlink(missing_ok=True)
            if document_id is not None:
                try:
                    mark_document_error(document_id, exc)
                    delete_document_record(document_id)
                except Exception:
                    current_app.logger.exception("RAG upload database rollback failed")
            _restore_index_after_rollback()
            current_app.logger.exception("RAG document upload failed")
            return _error("文档索引构建失败，上传已回滚", 500, "RAG_REBUILD_FAILED")

    row = _serialize_document(get_document(document_id))
    return _ok(
        {"document": row, "index": index_result},
        "文档上传并完成索引刷新",
        201,
    )


@rag_admin_bp.delete("/documents/<int:document_id>")
@admin_required
def delete_document(document_id):
    row = get_document(document_id)
    if row is None:
        return _error("文档不存在", 404, "RAG_DOCUMENT_NOT_FOUND")

    with _mutation_lock:
        path = document_path(row["filename"])
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.deleting")
        try:
            if path.exists():
                os.replace(path, temporary)
            index_result = _refresh_index()
            delete_document_record(document_id)
        except Exception:
            if temporary.exists():
                os.replace(temporary, path)
            _restore_index_after_rollback()
            current_app.logger.exception("RAG document delete failed")
            return _error("文档索引构建失败，删除已回滚", 500, "RAG_REBUILD_FAILED")
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            current_app.logger.warning("Could not remove staged RAG file %s", temporary)

    return _ok({"document_id": document_id, "index": index_result}, "文档已删除并刷新索引")


@rag_admin_bp.post("/rebuild")
@admin_required
def rebuild_index():
    with _mutation_lock:
        try:
            before = _index_status()
            if before["up_to_date"]:
                return _ok(
                    {"rebuilt": False, "status": before},
                    "当前索引已经是最新，无需重建",
                )
            result = _refresh_index(force=True)
            after = _index_status()
        except Exception:
            current_app.logger.exception("Manual RAG index rebuild failed")
            return _error("索引重建失败", 500, "RAG_REBUILD_FAILED")
    return _ok(
        {"rebuilt": True, "before": before, "index": result, "status": after},
        "检测到索引变化，已完成重建",
    )
