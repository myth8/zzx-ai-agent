"""
RAG 管道 — LangChain + Chroma + BM25 + Cross-Encoder 重排序
完全基于 LangChain 实现，无 llama_index 依赖
"""

import os
import threading
import uuid
import hashlib
import json
import re
from datetime import datetime, timezone
from collections import Counter
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# 设置 HuggingFace 镜像加速
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from langchain.tools import tool
from langchain.text_splitter import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_core.documents import Document as LCDocument
from langchain_huggingface import HuggingFaceEmbeddings

from langchain_chroma import Chroma
from langchain_community.retrievers import BM25Retriever

from rank_bm25 import BM25Okapi
import yaml

# ==============================
#  路径与常量配置
# ==============================
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCUMENTS_DIR = os.path.join(BACKEND_DIR, "documents")   # Markdown 文档存放目录
CHROMA_DIR = os.path.join(BACKEND_DIR, "chroma_db")      # Chroma 向量库持久化目录

VECTOR_TOP_K = 10      # 向量检索召回数量
BM25_TOP_K = 10        # BM25 召回数量
FUSION_TOP_K = 5       # 融合后候选数量
RERANK_TOP_K = 3       # 最终重排序后返回数量
RAG_INDEX_SCHEMA_VERSION = 2


# ==============================
#  文档加载与切分
# ==============================

_FRONT_MATTER_PATTERN = re.compile(
    r"\A---[ \t]*\r?\n(?P<yaml>.*?)\r?\n---[ \t]*(?:\r?\n|\Z)",
    re.DOTALL,
)


def _json_metadata_value(value):
    """Normalize YAML-native values into JSON-safe metadata values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_metadata_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _json_metadata_value(item)
            for key, item in value.items()
        }
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def parse_markdown_document(text: str) -> Tuple[dict, str]:
    """Return parsed YAML metadata and Markdown body without front matter."""
    normalized = str(text or "").lstrip("\ufeff")
    match = _FRONT_MATTER_PATTERN.match(normalized)
    if match is None:
        return {}, normalized

    metadata = yaml.safe_load(match.group("yaml")) or {}
    if not isinstance(metadata, dict):
        raise ValueError("Markdown Front Matter 必须是键值对象")
    metadata = {
        str(key): _json_metadata_value(value)
        for key, value in metadata.items()
    }
    return metadata, normalized[match.end():].lstrip("\r\n")


def _chroma_metadata(metadata: dict) -> dict:
    """Convert rich YAML values to scalar values accepted by Chroma."""
    result = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            result[str(key)] = value
        else:
            result[str(key)] = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return result


def split_markdown_text(text: str, source: str = "") -> List[LCDocument]:
    """Split one Markdown document with stable source and chunk metadata."""
    rich_file_meta, body = parse_markdown_document(text)
    file_meta = _chroma_metadata(rich_file_meta)
    if source:
        file_meta["source"] = source

    headers_to_split_on = [
        ("#", "document_title"),
        ("##", "section_title"),
    ]
    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=False,
    )
    char_splitter = RecursiveCharacterTextSplitter(
        chunk_size=600,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "，", " ", ""],
    )

    chunks = []
    for header_chunk in markdown_splitter.split_text(body):
        chunk_meta = dict(file_meta)
        if header_chunk.metadata:
            chunk_meta.update(header_chunk.metadata)
        header_chunk.metadata = chunk_meta
        if len(header_chunk.page_content) < 600:
            chunks.append(header_chunk)
        else:
            for sub_chunk in char_splitter.split_documents([header_chunk]):
                sub_meta = dict(chunk_meta)
                if sub_chunk.metadata:
                    sub_meta.update(sub_chunk.metadata)
                sub_chunk.metadata = sub_meta
                chunks.append(sub_chunk)

    for index, chunk in enumerate(chunks, 1):
        chunk.metadata["chunk_index"] = index
        chunk.metadata["char_count"] = len(chunk.page_content)
        chunk.metadata["content_sha256"] = hashlib.sha256(
            chunk.page_content.encode("utf-8")
        ).hexdigest()
        chunk.metadata["chunk_id"] = hashlib.sha256(
            f"{source}\0{index}\0{chunk.metadata['content_sha256']}".encode("utf-8")
        ).hexdigest()[:24]
    return chunks


def split_markdown_file(path: Path) -> List[LCDocument]:
    path = Path(path)
    return split_markdown_text(path.read_text(encoding="utf-8"), path.name)


def load_and_split_documents(doc_dir: str) -> List[LCDocument]:
    """
    读取 doc_dir 下所有 .md 文件，先按 Markdown 标题（# 和 ##）切分，
    再对过长的段落用 RecursiveCharacterTextSplitter 二次切分，
    返回 LangChain Document 列表。
    """
    md_files = sorted(
        path for path in Path(doc_dir).iterdir()
        if path.is_file() and path.suffix.lower() == ".md"
    )
    all_docs: List[LCDocument] = []

    print(f"📂 开始加载文档目录: {doc_dir}")
    print(f"   找到 {len(md_files)} 个 Markdown 文件")

    for idx, md_path in enumerate(md_files, 1):
        print(f"   [{idx}/{len(md_files)}] 处理文件: {md_path.name}")
        file_chunks = split_markdown_file(md_path)
        print(f"      → 切分为 {len(file_chunks)} 个块")
        all_docs.extend(file_chunks)

        print(f"      → 当前累计文档片段数: {len(all_docs)}")

    print(f"✅ 文档加载完成，共生成 {len(all_docs)} 个文档片段\n")
    return all_docs


def _source_signature(documents_dir):
    digest = hashlib.sha256()
    paths = sorted(
        path for path in Path(documents_dir).iterdir()
        if path.is_file() and path.suffix.lower() == ".md"
    )
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def inspect_index_status(documents_dir, chroma_dir):
    """Inspect persisted source/vector consistency without loading model weights."""
    documents_dir = str(documents_dir)
    chroma_dir = str(chroma_dir)
    manifest_path = Path(chroma_dir) / "rag_index_manifest.json"
    expected_chunks = []
    for path in sorted(Path(documents_dir).glob("*")):
        if path.is_file() and path.suffix.lower() == ".md":
            expected_chunks.extend(split_markdown_file(path))
    expected_ids = {chunk.metadata["chunk_id"] for chunk in expected_chunks}
    base = {
        "up_to_date": False,
        "schema_version": RAG_INDEX_SCHEMA_VERSION,
        "document_count": len({chunk.metadata.get("source") for chunk in expected_chunks}),
        "expected_chunk_count": len(expected_ids),
        "indexed_chunk_count": 0,
        "collection_name": None,
        "indexed_at": None,
        "reason": "",
        "reason_code": "",
        "expected_chunk_ids": sorted(expected_ids),
    }
    if not manifest_path.is_file():
        return {**base, "reason": "尚未建立索引", "reason_code": "MANIFEST_MISSING"}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {**base, "reason": "索引清单无法读取", "reason_code": "MANIFEST_INVALID"}

    base.update({
        "collection_name": manifest.get("collection_name"),
        "indexed_at": manifest.get("indexed_at"),
    })
    if manifest.get("schema_version") != RAG_INDEX_SCHEMA_VERSION:
        return {**base, "reason": "索引结构版本已过期", "reason_code": "SCHEMA_OUTDATED"}
    if manifest.get("source_signature") != _source_signature(documents_dir):
        return {**base, "reason": "源文档内容已经发生变化", "reason_code": "SOURCE_CHANGED"}
    if not manifest.get("collection_name"):
        return {**base, "reason": "索引清单缺少 collection", "reason_code": "COLLECTION_MISSING"}
    try:
        import chromadb

        client = chromadb.PersistentClient(path=chroma_dir)
        collection = client.get_collection(manifest["collection_name"])
        stored_ids = set(collection.get(include=[])["ids"])
    except Exception:
        return {**base, "reason": "向量 collection 不存在或无法读取", "reason_code": "COLLECTION_UNAVAILABLE"}

    base["indexed_chunk_count"] = len(stored_ids)
    if stored_ids != expected_ids:
        return {**base, "reason": "向量记录与当前切片不一致", "reason_code": "VECTOR_MISMATCH"}
    return {**base, "up_to_date": True, "reason": "当前索引已经是最新", "reason_code": "UP_TO_DATE"}


# ==============================
#  RAG 引擎核心类
# ==============================

class RAGEngine:
    """
    RAG 引擎单例类。
    包含：
      - Chroma 向量检索（基于 BGE 小模型）
      - BM25 关键词检索
      - 加权 RRF 融合
      - Cross-Encoder 重排序（懒加载）
    """

    _instance = None
    _lock = threading.Lock()

    def __init__(self, documents_dir=DOCUMENTS_DIR, chroma_dir=CHROMA_DIR):
        self._documents_dir = str(documents_dir)
        self._chroma_dir = str(chroma_dir)
        self._manifest_path = Path(self._chroma_dir) / "rag_index_manifest.json"
        os.makedirs(self._documents_dir, exist_ok=True)
        os.makedirs(self._chroma_dir, exist_ok=True)
        self._state_lock = threading.Lock()
        self._rebuild_lock = threading.Lock()
        self._active_queries = 0
        self._retired_stores = []
        self._docs = []
        self._vector_store = None
        self._vector_retriever = None
        self._bm25 = None
        self._bm25_retriever = None
        self._reranker = None
        self._stats = {
            "document_count": 0,
            "chunk_count": 0,
            "chunk_counts": {},
        }

        print("\n初始化 Embedding 模型 BAAI/bge-small-zh-v1.5")
        self._embed_model = HuggingFaceEmbeddings(
            model_name="BAAI/bge-small-zh-v1.5",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        if not self._load_existing_index():
            self.rebuild()

    def _document_signature(self):
        return _source_signature(self._documents_dir)

    @staticmethod
    def _build_keyword_index(docs):
        if not docs:
            return None, None
        bm25 = BM25Okapi([doc.page_content.split() for doc in docs])
        retriever = BM25Retriever.from_documents(docs)
        retriever.k = BM25_TOP_K
        return bm25, retriever

    def _load_existing_index(self):
        """Reuse a complete persisted collection when source files are unchanged."""
        if not self._manifest_path.is_file():
            return False
        try:
            manifest = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            if manifest.get("schema_version") != RAG_INDEX_SCHEMA_VERSION:
                return False
            if manifest.get("source_signature") != self._document_signature():
                return False
            collection_name = manifest["collection_name"]
            docs = load_and_split_documents(self._documents_dir)
            store = Chroma(
                collection_name=collection_name,
                embedding_function=self._embed_model,
                persist_directory=self._chroma_dir,
            )
            stored_ids = set(store.get()["ids"])
            expected_ids = {doc.metadata["chunk_id"] for doc in docs}
            if stored_ids != expected_ids:
                return False
            vector_retriever = (
                store.as_retriever(search_kwargs={"k": VECTOR_TOP_K})
                if docs else None
            )
            bm25, bm25_retriever = self._build_keyword_index(docs)
            counts = Counter(
                doc.metadata.get("source", "") for doc in docs
                if doc.metadata.get("source")
            )
            self._docs = docs
            self._vector_store = store
            self._vector_retriever = vector_retriever
            self._bm25 = bm25
            self._bm25_retriever = bm25_retriever
            self._stats = {
                "document_count": len(counts),
                "chunk_count": len(docs),
                "chunk_counts": dict(counts),
            }
            print(f"复用现有 RAG collection: {collection_name}")
            return True
        except Exception as exc:
            print(f"现有 RAG 索引不可复用，将重新构建: {exc}")
            return False

    def _write_manifest(self, collection_name, source_signature):
        temporary = self._manifest_path.with_name(
            f".{self._manifest_path.name}.{uuid.uuid4().hex}.tmp"
        )
        temporary.write_text(
            json.dumps({
                "schema_version": RAG_INDEX_SCHEMA_VERSION,
                "collection_name": collection_name,
                "source_signature": source_signature,
                "indexed_at": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self._manifest_path)

    @staticmethod
    def _dispose_stores(stores):
        for store in stores:
            try:
                store.delete_collection()
            except Exception as exc:
                print(f"清理旧 RAG collection 失败: {exc}")

    def _release_query(self):
        retired = []
        with self._state_lock:
            self._active_queries -= 1
            if self._active_queries == 0 and self._retired_stores:
                retired = self._retired_stores
                self._retired_stores = []
        self._dispose_stores(retired)

    def rebuild(self):
        """Build a new collection first, then atomically switch query state."""
        with self._rebuild_lock:
            docs = load_and_split_documents(self._documents_dir)
            source_signature = self._document_signature()
            collection_name = f"love_rag_{uuid.uuid4().hex}"
            new_store = None
            try:
                if docs:
                    new_store = Chroma.from_documents(
                        documents=docs,
                        embedding=self._embed_model,
                        persist_directory=self._chroma_dir,
                        collection_name=collection_name,
                        ids=[doc.metadata["chunk_id"] for doc in docs],
                    )
                    vector_retriever = new_store.as_retriever(
                        search_kwargs={"k": VECTOR_TOP_K}
                    )
                    bm25, bm25_retriever = self._build_keyword_index(docs)
                else:
                    new_store = Chroma(
                        collection_name=collection_name,
                        embedding_function=self._embed_model,
                        persist_directory=self._chroma_dir,
                    )
                    vector_retriever = None
                    bm25 = None
                    bm25_retriever = None
                self._write_manifest(collection_name, source_signature)
            except Exception:
                if new_store is not None:
                    self._dispose_stores([new_store])
                raise

            counts = Counter(
                doc.metadata.get("source", "") for doc in docs
                if doc.metadata.get("source")
            )
            result = {
                "document_count": len(counts),
                "chunk_count": len(docs),
                "chunk_counts": dict(counts),
            }

            retired = []
            with self._state_lock:
                old_store = self._vector_store
                self._docs = docs
                self._vector_store = new_store
                self._vector_retriever = vector_retriever
                self._bm25 = bm25
                self._bm25_retriever = bm25_retriever
                self._stats = result
                if old_store is not None:
                    self._retired_stores.append(old_store)
                if self._active_queries == 0:
                    retired = self._retired_stores
                    self._retired_stores = []
            self._dispose_stores(retired)

            return result

    def stats(self):
        with self._state_lock:
            return {
                "document_count": self._stats["document_count"],
                "chunk_count": self._stats["chunk_count"],
                "chunk_counts": dict(self._stats["chunk_counts"]),
            }

    def _get_reranker(self):
        """懒加载 Cross-Encoder 重排序模型"""
        if self._reranker is None:
            try:
                from sentence_transformers import CrossEncoder
                print("   🔄 正在加载 Cross-Encoder 重排序模型 (BAAI/bge-reranker-base)...")
                self._reranker = CrossEncoder("BAAI/bge-reranker-base")
                print("   ✅ 重排序模型加载成功")
            except ImportError:
                print("   ⚠️ 未安装 sentence-transformers，重排序功能将跳过")
                self._reranker = None
        return self._reranker

    @staticmethod
    def _compute_weights(query: str) -> Tuple[float, float]:
        """
        根据查询长度动态调整向量检索和 BM25 的权重。
        短查询更依赖 BM25（关键词），长查询更依赖向量（语义）。
        """
        if len(query) < 20:
            return 0.4, 0.6   # (向量权重, BM25权重)
        return 0.7, 0.3

    def query(self, query_text: str, top_k: int = RERANK_TOP_K) -> str:
        """
        执行多路召回 → 加权 RRF 融合 → Cross-Encoder 重排序 → 返回最终结果。
        """
        with self._state_lock:
            self._active_queries += 1
            vector_retriever = self._vector_retriever
            bm25_retriever = self._bm25_retriever
        try:
            return self._query_with_state(
                query_text,
                top_k,
                vector_retriever,
                bm25_retriever,
            )
        finally:
            self._release_query()

    def _query_with_state(
        self, query_text, top_k, vector_retriever, bm25_retriever
    ):
        if vector_retriever is None or bm25_retriever is None:
            return "知识库当前没有可检索的文档。"

        print(f"\n收到 RAG 查询，字符数: {len(query_text)}")

        # ---------- 1. 向量检索 ----------
        print("\n[召回-1] 向量检索 (Chroma)...")
        vector_docs = vector_retriever.invoke(query_text)
        print(f"   ✅ 召回 {len(vector_docs)} 个文档")
        if vector_docs:
            print(f"   最高分片段预览: {vector_docs[0].page_content[:60]}...")

        # ---------- 2. BM25 检索 ----------
        print("\n[召回-2] BM25 关键词检索...")
        bm25_docs = bm25_retriever.invoke(query_text)
        print(f"   ✅ 召回 {len(bm25_docs)} 个文档")
        if bm25_docs:
            print(f"   最高分片段预览: {bm25_docs[0].page_content[:60]}...")

        # ---------- 3. 动态权重融合 (加权 RRF) ----------
        w_vec, w_bm25 = self._compute_weights(query_text)
        print(f"\n[融合] 权重分配: 向量={w_vec:.1f}, BM25={w_bm25:.1f}")

        k_const = 60
        score_map: Dict[str, float] = {}
        text_map: Dict[str, str] = {}

        # 添加向量检索结果
        for rank, doc in enumerate(vector_docs):
            key = doc.page_content[:200]   # 用前200字符作为去重键
            score_map[key] = score_map.get(key, 0.0) + w_vec / (k_const + rank + 1)
            text_map[key] = doc.page_content

        # 添加 BM25 检索结果
        for rank, doc in enumerate(bm25_docs):
            key = doc.page_content[:200]
            if key not in score_map:
                text_map[key] = doc.page_content
            score_map[key] = score_map.get(key, 0.0) + w_bm25 / (k_const + rank + 1)

        # 按分数排序，取前 FUSION_TOP_K 个
        fused_keys = sorted(score_map, key=score_map.get, reverse=True)[:FUSION_TOP_K]
        candidates = [text_map[k] for k in fused_keys if k in text_map]

        print(f"   融合后候选数: {len(candidates)} (取 top-{FUSION_TOP_K})")
        if candidates:
            print(f"   融合排序第1名片段预览: {candidates[0][:60]}...")

        if not candidates:
            print("   ⚠️ 未找到任何相关结果")
            return "未找到相关信息。"

        # ---------- 4. Cross-Encoder 重排序 ----------
        reranker = self._get_reranker()
        if reranker is not None:
            print("\n[重排序] 使用 Cross-Encoder 重新计算相关性...")
            pairs = [[query_text, c] for c in candidates]
            scores = reranker.predict(pairs)
            ranked = sorted(zip(candidates, scores), key=lambda x: -x[1])
            print("   ✅ 重排序完成")
            # 打印重排序后的得分情况（前 top_k）
            for i, (txt, score) in enumerate(ranked[:top_k], 1):
                print(f"      第{i}名 得分={score:.4f} 预览: {txt[:40]}...")
        else:
            print("\n[重排序] 未加载重排序模型，使用融合顺序作为最终顺序")
            ranked = [(c, 1.0 - i * 0.05) for i, c in enumerate(candidates)]

        # ---------- 5. 格式化输出 ----------
        parts = []
        for i, (txt, score) in enumerate(ranked[:top_k], 1):
            parts.append(f"[参考 {i}]（相关度: {score:.3f}）\n{txt}")

        final_output = "\n\n".join(parts)
        print("\n✅ 查询完成，返回结果\n")
        return final_output


# ==============================
#  全局单例引擎
# ==============================

_engine: Optional[RAGEngine] = None


def get_engine() -> RAGEngine:
    """获取或创建全局 RAG 引擎（线程安全）"""
    global _engine
    if _engine is None:
        with RAGEngine._lock:
            if _engine is None:
                try:
                    from flask import current_app
                    documents_dir = current_app.config.get(
                        "RAG_DOCUMENTS_DIR", DOCUMENTS_DIR
                    )
                    chroma_dir = current_app.config.get(
                        "RAG_CHROMA_DIR", CHROMA_DIR
                    )
                except RuntimeError:
                    documents_dir = DOCUMENTS_DIR
                    chroma_dir = CHROMA_DIR
                _engine = RAGEngine(documents_dir, chroma_dir)
    return _engine


def rebuild_engine(force=False):
    """Rebuild all RAG indexes and atomically publish the new query state."""
    global _engine
    if _engine is None:
        engine = get_engine()
        return engine.stats()
    return _engine.rebuild()


def rebuild_initialized_engine():
    """Rebuild only when this process already has a live RAG engine."""
    if _engine is None:
        return None
    return _engine.rebuild()


# ==============================
#  LangChain 工具包装器
# ==============================

@tool
def rag_search(query: str) -> str:
    """
    Search the love-and-relationship knowledge base.
    Use this when the user asks questions about dating, marriage, breakups,
    relationship advice, emotional issues, or similar topics.
    Input: the user's question or keywords.
    """
    return get_engine().query(query)


# ==============================
#  对外暴露
# ==============================

RAG_TOOLS = [rag_search]
__all__ = [
    "rag_search",
    "RAG_TOOLS",
    "get_engine",
    "rebuild_engine",
    "rebuild_initialized_engine",
    "RAGEngine",
    "split_markdown_file",
    "split_markdown_text",
    "parse_markdown_document",
    "inspect_index_status",
]
