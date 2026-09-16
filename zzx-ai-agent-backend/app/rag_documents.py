"""RAG document catalog and filesystem helpers."""
import hashlib
import json
import re
import unicodedata
from pathlib import Path

from flask import current_app

from app.auth import get_db


_SAFE_FILENAME = re.compile(r"^[\w\-.\u4e00-\u9fff ]+$", re.UNICODE)


def get_documents_dir() -> Path:
    path = Path(current_app.config["RAG_DOCUMENTS_DIR"]).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def normalize_markdown_filename(filename: str) -> str:
    """Return a safe, normalized Markdown filename or raise ValueError."""
    name = unicodedata.normalize("NFC", str(filename or "").strip())
    if not name or name != Path(name).name or "/" in name or "\\" in name:
        raise ValueError("文件名无效")
    if name.startswith(".") or Path(name).suffix.lower() != ".md":
        raise ValueError("仅支持 .md 格式的 Markdown 文件")
    if len(name) > 255 or not _SAFE_FILENAME.fullmatch(name):
        raise ValueError("文件名只能包含中英文、数字、空格、点、横线和下划线")
    return name


def document_path(filename: str) -> Path:
    name = normalize_markdown_filename(filename)
    root = get_documents_dir()
    path = (root / name).resolve()
    if path.parent != root:
        raise ValueError("文件路径无效")
    return path


def content_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _metadata_snapshot(path: Path):
    """Build the document metadata and its materialized chunks."""
    from app.llm.rag import parse_markdown_document, split_markdown_file

    raw_text = path.read_text(encoding="utf-8")
    document_metadata, _ = parse_markdown_document(raw_text)
    chunks = split_markdown_file(path)
    return document_metadata, chunks


def _decode_json_fields(row):
    if row is None:
        return None
    result = dict(row)
    for field, default in (("document_metadata", {}), ("metadata", {})):
        if field not in result:
            continue
        value = result.get(field)
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError):
                value = default
        result[field] = value if value is not None else default
    return result


def _replace_document_chunks(cur, document_id, chunks):
    """Replace one document's relational chunk snapshot in the current transaction."""
    cur.execute(
        "DELETE FROM rag_document_chunks WHERE document_id=%s",
        (document_id,),
    )
    for chunk in chunks:
        metadata = dict(chunk.metadata)
        chunk_id = metadata["chunk_id"]
        cur.execute(
            "INSERT INTO rag_document_chunks "
            "(document_id, chunk_id, chunk_index, content, content_sha256, "
            "char_count, section_title, metadata, vector_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                document_id,
                chunk_id,
                metadata["chunk_index"],
                chunk.page_content,
                metadata["content_sha256"],
                metadata["char_count"],
                metadata.get("section_title"),
                json.dumps(metadata, ensure_ascii=False),
                chunk_id,
            ),
        )


def init_rag_tables():
    """Create the RAG document catalog and import existing Markdown files."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS rag_documents (
                    id           INT AUTO_INCREMENT PRIMARY KEY,
                    filename     VARCHAR(255) NOT NULL UNIQUE,
                    display_name VARCHAR(255) NOT NULL,
                    file_size    BIGINT NOT NULL DEFAULT 0,
                    sha256       CHAR(64) NOT NULL,
                    chunk_count  INT NOT NULL DEFAULT 0,
                    document_metadata JSON DEFAULT NULL,
                    status       VARCHAR(20) NOT NULL DEFAULT 'ready',
                    last_error   VARCHAR(500) DEFAULT NULL,
                    uploaded_by  INT DEFAULT NULL,
                    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_rag_documents_status (status),
                    INDEX idx_rag_documents_uploader (uploaded_by)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("SHOW COLUMNS FROM rag_documents LIKE 'document_metadata'")
            if cur.fetchone() is None:
                cur.execute(
                    "ALTER TABLE rag_documents "
                    "ADD COLUMN document_metadata JSON DEFAULT NULL AFTER chunk_count"
                )
            # Remove the obsolete JSON chunk snapshot introduced by the early MVP.
            # Relational chunks in rag_document_chunks are now the sole source of truth.
            cur.execute("SHOW COLUMNS FROM rag_documents LIKE 'chunk_metadata'")
            if cur.fetchone() is not None:
                cur.execute(
                    "ALTER TABLE rag_documents DROP COLUMN chunk_metadata"
                )
            cur.execute("""
                CREATE TABLE IF NOT EXISTS rag_document_chunks (
                    id             BIGINT AUTO_INCREMENT PRIMARY KEY,
                    document_id    INT NOT NULL,
                    chunk_id       CHAR(24) NOT NULL,
                    chunk_index    INT NOT NULL,
                    content        LONGTEXT NOT NULL,
                    content_sha256 CHAR(64) NOT NULL,
                    char_count     INT NOT NULL,
                    section_title  VARCHAR(500) DEFAULT NULL,
                    metadata       JSON DEFAULT NULL,
                    vector_id      VARCHAR(255) NOT NULL,
                    created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uk_rag_chunks_chunk_id (chunk_id),
                    UNIQUE KEY uk_rag_chunks_document_index (document_id, chunk_index),
                    INDEX idx_rag_chunks_document (document_id),
                    INDEX idx_rag_chunks_content_sha256 (content_sha256),
                    CONSTRAINT fk_rag_chunks_document
                        FOREIGN KEY (document_id) REFERENCES rag_documents(id)
                        ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        conn.commit()
    finally:
        conn.close()
    sync_document_catalog()


def sync_document_catalog():
    """Make the database catalog reflect Markdown files already on disk."""
    files = {}
    paths = sorted(
        path for path in get_documents_dir().iterdir()
        if path.is_file() and path.suffix.lower() == ".md"
    )
    for path in paths:
        content = path.read_bytes()
        document_metadata, chunks = _metadata_snapshot(path)
        files[path.name] = (
            len(content),
            content_sha256(content),
            document_metadata,
            chunks,
        )

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, filename FROM rag_documents")
            rows = cur.fetchall()
            known = {row["filename"]: row["id"] for row in rows}

            for filename, (
                file_size, digest, document_metadata, chunks
            ) in files.items():
                display_name = document_metadata.get("title") or Path(filename).stem
                cur.execute(
                    "INSERT INTO rag_documents "
                    "(filename, display_name, file_size, sha256, chunk_count, "
                    "document_metadata, status) "
                    "VALUES (%s, %s, %s, %s, %s, %s, 'ready') "
                    "ON DUPLICATE KEY UPDATE file_size=VALUES(file_size), "
                    "sha256=VALUES(sha256), chunk_count=VALUES(chunk_count), "
                    "document_metadata=VALUES(document_metadata), "
                    "display_name=VALUES(display_name)",
                    (
                        filename,
                        str(display_name)[:255],
                        file_size,
                        digest,
                        len(chunks),
                        json.dumps(document_metadata, ensure_ascii=False),
                    ),
                )
                cur.execute(
                    "SELECT id FROM rag_documents WHERE filename=%s",
                    (filename,),
                )
                document_id = cur.fetchone()["id"]
                _replace_document_chunks(cur, document_id, chunks)

            missing = set(known) - set(files)
            for filename in missing:
                cur.execute(
                    "DELETE FROM rag_documents WHERE filename=%s",
                    (filename,),
                )
        conn.commit()
    finally:
        conn.close()


def list_documents():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT d.id, d.filename, d.display_name, d.file_size, "
                "d.sha256, d.chunk_count, d.document_metadata, "
                "d.status, d.last_error, "
                "d.uploaded_by, d.created_at, d.updated_at, u.nickname AS uploader_name "
                "FROM rag_documents d LEFT JOIN users u ON u.id=d.uploaded_by "
                "ORDER BY d.updated_at DESC, d.id DESC"
            )
            return [_decode_json_fields(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_document(document_id):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT d.id, d.filename, d.display_name, d.file_size, "
                "d.sha256, d.chunk_count, d.document_metadata, "
                "d.status, d.last_error, "
                "d.uploaded_by, d.created_at, d.updated_at, u.nickname AS uploader_name "
                "FROM rag_documents d LEFT JOIN users u ON u.id=d.uploaded_by "
                "WHERE d.id=%s",
                (document_id,),
            )
            return _decode_json_fields(cur.fetchone())
    finally:
        conn.close()


def create_document(filename, content, uploaded_by):
    from app.llm.rag import parse_markdown_document, split_markdown_text

    text = content.decode("utf-8")
    document_metadata, _ = parse_markdown_document(text)
    chunks = split_markdown_text(text, filename)
    display_name = document_metadata.get("title") or Path(filename).stem
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO rag_documents "
                "(filename, display_name, file_size, sha256, chunk_count, "
                "document_metadata, status, uploaded_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'indexing', %s)",
                (
                    filename,
                    str(display_name)[:255],
                    len(content),
                    content_sha256(content),
                    len(chunks),
                    json.dumps(document_metadata, ensure_ascii=False),
                    uploaded_by,
                ),
            )
            document_id = cur.lastrowid
            _replace_document_chunks(cur, document_id, chunks)
        conn.commit()
        return document_id
    finally:
        conn.close()


def delete_document_record(document_id):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM rag_documents WHERE id=%s", (document_id,))
            deleted = cur.rowcount
        conn.commit()
        return deleted > 0
    finally:
        conn.close()


def list_document_chunks(document_id):
    """Return stored chunks in document order; content is not regenerated per request."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, document_id, chunk_id, chunk_index AS `index`, content, "
                "content_sha256, char_count, section_title, metadata, vector_id, "
                "created_at, updated_at FROM rag_document_chunks "
                "WHERE document_id=%s ORDER BY chunk_index ASC",
                (document_id,),
            )
            return [_decode_json_fields(row) for row in cur.fetchall()]
    finally:
        conn.close()


def list_all_chunk_ids():
    """Return all relational chunk IDs for index consistency checks."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT chunk_id FROM rag_document_chunks")
            return {row["chunk_id"] for row in cur.fetchall()}
    finally:
        conn.close()


def update_index_results(chunk_counts, status="ready", last_error=None):
    """Update indexing results for all cataloged documents."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE rag_documents SET chunk_count=0, status=%s, last_error=%s",
                (status, last_error),
            )
            cur.execute("DELETE FROM rag_document_chunks")
            for filename, count in chunk_counts.items():
                path = document_path(filename)
                document_metadata, chunks = _metadata_snapshot(path)
                cur.execute(
                    "SELECT id FROM rag_documents WHERE filename=%s",
                    (filename,),
                )
                row = cur.fetchone()
                if row is None:
                    continue
                cur.execute(
                    "UPDATE rag_documents SET chunk_count=%s, document_metadata=%s, "
                    "status=%s, last_error=%s "
                    "WHERE filename=%s",
                    (
                        count,
                        json.dumps(document_metadata, ensure_ascii=False),
                        status,
                        last_error,
                        filename,
                    ),
                )
                _replace_document_chunks(cur, row["id"], chunks)
        conn.commit()
    finally:
        conn.close()


def mark_document_error(document_id, message):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE rag_documents SET status='failed', last_error=%s WHERE id=%s",
                (str(message)[:500], document_id),
            )
        conn.commit()
    finally:
        conn.close()
