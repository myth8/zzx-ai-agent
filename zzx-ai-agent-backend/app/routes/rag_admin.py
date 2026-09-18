"""管理员 RAG 文档接口，以及文件、MySQL、索引三者的一致性编排。"""
import os
import threading
import uuid
import yaml

from flask import Blueprint, current_app, jsonify, request
from pymysql.err import IntegrityError

from app.auth import admin_required
from app.utils.responses import api_error
from app.utils.rate_limit import admin_read_rate_limit, admin_write_rate_limit
from app.utils.validation import InputValidationError, validate_markdown_mime_type
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
# 上传、删除和手动重建都会修改同一套文件与索引。同一进程内串行执行这些
# 操作，避免两个请求同时重建并互相覆盖；多进程部署仍需升级为分布式锁。
_mutation_lock = threading.Lock()


def _ok(data=None, message="操作成功", status=200):
    return jsonify({"code": 0, "msg": message, "data": data}), status


def _error(message, status, error_code):
    return api_error(error_code, message, status)


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
    """先发布新的在线索引，再把该版本的切片结果同步到 MySQL。"""
    from app.llm.rag import rebuild_engine

    result = rebuild_engine(force=force)
    update_index_results(result["chunk_counts"])
    return result


def _restore_index_after_rollback():
    """文件操作回滚后，尽力让已初始化的在线索引重新匹配磁盘内容。"""
    try:
        from app.llm.rag import rebuild_initialized_engine

        result = rebuild_initialized_engine()
        if result is not None:
            update_index_results(result["chunk_counts"])
    except Exception:
        current_app.logger.exception("RAG index rollback refresh failed")


def _index_status():
    """
    汇总源文件、manifest、Chroma 和 MySQL 四层一致性状态。

    inspect_index_status 已比较源文件签名与 Chroma 向量 ID；这里再比较 MySQL
    chunk_id。只有三侧切片 ID 集合都一致，管理页面才显示 UP_TO_DATE。
    """
    from app.llm.rag import inspect_index_status

    result = inspect_index_status(
        current_app.config["RAG_DOCUMENTS_DIR"],
        current_app.config["RAG_CHROMA_DIR"],
    )
    # expected_ids 由当前磁盘文件按当前切片规则重新计算，是本次核对的基准。
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
@admin_read_rate_limit
def documents():
    rows = [_serialize_document(row) for row in list_documents()]
    return _ok({
        "documents": rows,
        "document_count": len(rows),
        "chunk_count": sum(row["chunk_count"] for row in rows),
    })


@rag_admin_bp.get("/index-status")
@admin_required
@admin_read_rate_limit
def index_status():
    return _ok(_index_status())


@rag_admin_bp.get("/documents/<int:document_id>")
@admin_required
@admin_read_rate_limit
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
@admin_read_rate_limit
def document_chunks(document_id):
    row = get_document(document_id)
    if row is None:
        return _error("文档不存在", 404, "RAG_DOCUMENT_NOT_FOUND")
    data = [_serialize_document(chunk) for chunk in list_document_chunks(document_id)]
    return _ok({"document_id": document_id, "chunks": data, "count": len(data)})


@rag_admin_bp.post("/documents")
@admin_required
@admin_write_rate_limit
def upload_document():
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return _error("请选择要上传的 Markdown 文件", 400, "RAG_FILE_REQUIRED")
    try:
        validate_markdown_mime_type(uploaded.mimetype)
    except InputValidationError as exc:
        return api_error(exc.code, exc.message, 415, exc.details)
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
    except InputValidationError as exc:
        return api_error(exc.code, exc.message, 400, exc.details)
    except (ValueError, yaml.YAMLError):
        return _error(
            "Markdown 元数据格式无效",
            400,
            "RAG_METADATA_INVALID",
        )
    except Exception:
        current_app.logger.exception("Unexpected Markdown validation failure")
        return _error(
            "Markdown 文档无法解析",
            400,
            "RAG_DOCUMENT_INVALID",
        )
    if not body.strip() or not chunks:
        return _error("Markdown 文档必须包含正文", 400, "RAG_BODY_EMPTY")

    # 下方是一个跨文件系统、MySQL、Chroma 的业务事务。它们无法共享数据库
    # transaction，因此通过临时文件和补偿操作实现“失败后回到原状态”。
    with _mutation_lock:
        path = document_path(filename)
        if path.exists():
            return _error("同名文档已存在", 409, "RAG_DOCUMENT_EXISTS")

        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.uploading")
        document_id = None
        try:
            # 先写隐藏临时文件，再原子替换为正式文件，避免其他线程读到
            # 只写入一部分的 Markdown。
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
            # 任一步失败都删除新文件和数据库记录，并按恢复后的磁盘目录重建
            # 已初始化索引。这里采用补偿事务，而不是留下“文件已上传但不可查”。
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
@admin_write_rate_limit
def delete_document(document_id):
    row = get_document(document_id)
    if row is None:
        return _error("文档不存在", 404, "RAG_DOCUMENT_NOT_FOUND")

    with _mutation_lock:
        path = document_path(row["filename"])
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.deleting")
        try:
            # 先把正式文件改名为临时文件，相当于可恢复的逻辑删除。索引会按
            # “文件已不存在”的目录快照重建，成功后才删除 MySQL 台账和临时文件。
            if path.exists():
                os.replace(path, temporary)
            index_result = _refresh_index()
            delete_document_record(document_id)
        except Exception:
            # 索引构建失败时把文件恢复原名，并恢复旧目录对应的在线索引。
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
@admin_write_rate_limit
def rebuild_index():
    """仅在四层一致性检查发现变化时执行手动全量重建。"""
    with _mutation_lock:
        try:
            # 先检查可避免用户重复点击时反复计算 Embedding。before 同时保留
            # 具体 reason_code，重建响应可说明本次为何需要执行。
            before = _index_status()
            if before["up_to_date"]:
                return _ok(
                    {"rebuilt": False, "status": before},
                    "当前索引已经是最新，无需重建",
                )
            result = _refresh_index(force=True)
            # 重建后再次核对，而不是仅凭 rebuild 没抛异常就宣称索引可用。
            after = _index_status()
        except Exception:
            current_app.logger.exception("Manual RAG index rebuild failed")
            return _error("索引重建失败", 500, "RAG_REBUILD_FAILED")
    return _ok(
        {"rebuilt": True, "before": before, "index": result, "status": after},
        "检测到索引变化，已完成重建",
    )
