"""
RAG 检索与索引生命周期。

这个模块同时负责两类事情：
1. 将 documents 目录中的 Markdown 解析、切片并构建 Chroma/BM25 索引；
2. 在线查询时执行元数据预过滤、双路召回、RRF 融合和重排序。

索引更新采用“先构建新版本，再切换引用”的方式。旧查询仍然持有旧
collection，最后一个旧查询结束后才删除旧 collection，避免重建过程中
出现短暂无索引或正在查询的数据被删除。
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
# 索引结构版本描述“切片和向量 ID 的生成规则”，不是文档内容版本。
# 修改切片规则、chunk_id 规则或必须重建的元数据结构时需要递增该值，
# 让旧 manifest 自动失效，避免用新代码读取语义不兼容的旧索引。
RAG_INDEX_SCHEMA_VERSION = 2

_METADATA_FILTER_FIELDS = ("title", "topics", "topic")
_METADATA_FILTER_MIN_TERM_LENGTH = 2


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
    """解析 YAML Front Matter，并返回不含 Front Matter 的正文。"""
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
    """把 YAML 丰富类型转换成 Chroma 支持的标量元数据。"""
    result = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            result[str(key)] = value
        else:
            # Chroma metadata 只能直接保存标量。topics/audience 等列表转成
            # JSON 字符串，读取时仍可无损恢复，也能显示在切片详情页面。
            result[str(key)] = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return result


def _metadata_values(value) -> List[str]:
    """将标量、容器或 JSON 字符串统一展开成可匹配的字符串列表。"""
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("[", "{")):
            try:
                return _metadata_values(json.loads(stripped))
            except (TypeError, ValueError):
                pass
        return [stripped] if stripped else []
    if isinstance(value, dict):
        result = []
        for item in value.values():
            result.extend(_metadata_values(item))
        return result
    if isinstance(value, (list, tuple, set)):
        result = []
        for item in value:
            result.extend(_metadata_values(item))
        return result
    return [str(value)]


def _normalize_metadata_match_text(value: str) -> str:
    """Normalize Chinese/Latin metadata text for conservative substring matching."""
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value).lower())


def _title_filter_terms(value: str) -> List[str]:
    """Extract the distinctive part of titles such as '恋爱常见问题 - 已婚篇'."""
    terms = []
    for part in re.split(r"[\s\-—–:：|/·,，、]+", str(value)):
        normalized = _normalize_metadata_match_text(part)
        normalized = re.sub(r"^(?:恋爱)?常见问题", "", normalized)
        normalized = re.sub(r"篇$", "", normalized)
        if len(normalized) >= _METADATA_FILTER_MIN_TERM_LENGTH:
            terms.append(normalized)
    return terms


def _metadata_filter_terms(metadata: dict) -> Dict[str, List[str]]:
    """Build conservative exact-substring terms from title and topic metadata."""
    result = {}
    for field in _METADATA_FILTER_FIELDS:
        values = _metadata_values(metadata.get(field))
        if field == "title":
            terms = [term for value in values for term in _title_filter_terms(value)]
        else:
            terms = [
                normalized
                for value in values
                if len(normalized := _normalize_metadata_match_text(value))
                >= _METADATA_FILTER_MIN_TERM_LENGTH
            ]
        if terms:
            result[field] = list(dict.fromkeys(terms))
    return result


def select_metadata_filtered_documents(query_text: str, docs: List[LCDocument]):
    """
    使用 title/topics 做保守的文档级预过滤。

    返回值中的 filtered_docs 为空表示“不启用过滤”，不是“没有结果”。调用方
    此时必须让 Chroma 和 BM25 同时搜索全库。只有查询明确包含标题或主题词
    时才返回候选文档，避免错误分类导致相关文档在向量检索前就被排除。
    """
    normalized_query = _normalize_metadata_match_text(query_text)
    if len(normalized_query) < _METADATA_FILTER_MIN_TERM_LENGTH:
        return [], {}

    matched_sources = {}
    seen_sources = set()
    for doc in docs:
        source = doc.metadata.get("source")
        if not source or source in seen_sources:
            continue
        # title/topics 是文档级元数据，会被复制到该文档的每个切片。
        # 每个 source 检查一次即可，没必要对同一文档的所有切片重复匹配。
        seen_sources.add(source)
        field_terms = _metadata_filter_terms(doc.metadata)
        matches = {
            field: [term for term in terms if term in normalized_query]
            for field, terms in field_terms.items()
        }
        matches = {field: terms for field, terms in matches.items() if terms}
        if matches:
            matched_sources[source] = matches

    if not matched_sources:
        return [], {}
    # 命中后保留整份源文档的所有切片。元数据负责缩小文档范围，真正决定
    # 哪些切片更相关的工作仍交给后续向量检索、BM25 和 Reranker。
    filtered_docs = [
        doc for doc in docs if doc.metadata.get("source") in matched_sources
    ]
    return filtered_docs, matched_sources


def split_markdown_text(text: str, source: str = "") -> List[LCDocument]:
    """切分一份 Markdown，并为每个切片生成可追踪的稳定元数据。"""
    # Front Matter 只作为元数据继承给切片，不进入 page_content，避免
    # title/status/category 等配置文本被错误地当成一个知识片段参与召回。
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
        # 标题本身保留在正文中，使标题语义也能进入 Embedding 和 BM25。
        strip_headers=False,
    )
    char_splitter = RecursiveCharacterTextSplitter(
        chunk_size=600,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "，", " ", ""],
    )

    chunks = []
    for header_chunk in markdown_splitter.split_text(body):
        # 每个切片先继承文档 Front Matter，再覆盖当前标题上下文。
        # 因此一个切片同时知道“来自哪份文档”和“属于哪个章节”。
        chunk_meta = dict(file_meta)
        if header_chunk.metadata:
            chunk_meta.update(header_chunk.metadata)
        header_chunk.metadata = chunk_meta
        if len(header_chunk.page_content) < 600:
            chunks.append(header_chunk)
        else:
            # 标题块过长时再按字符递归切分，但继续复制同一份文档/标题元数据。
            for sub_chunk in char_splitter.split_documents([header_chunk]):
                sub_meta = dict(chunk_meta)
                if sub_chunk.metadata:
                    sub_meta.update(sub_chunk.metadata)
                sub_chunk.metadata = sub_meta
                chunks.append(sub_chunk)

    for index, chunk in enumerate(chunks, 1):
        chunk.metadata["chunk_index"] = index
        chunk.metadata["char_count"] = len(chunk.page_content)
        # content_sha256 只反映当前切片正文，用于判断内容是否变化和审计。
        chunk.metadata["content_sha256"] = hashlib.sha256(
            chunk.page_content.encode("utf-8")
        ).hexdigest()
        # chunk_id 同时写入 MySQL chunk_id/vector_id 和 Chroma record ID。
        # source + 顺序 + 内容指纹确保同一版本可重复生成相同 ID；文件改名、
        # 切片位置变化或正文变化都会产生新 ID，从而暴露索引需要更新。
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
    """
    计算整个 Markdown 源目录的内容签名。

    文件按名称排序后，将“文件名 + 分隔符 + 原始字节 + 分隔符”依次送入
    SHA-256。因此新增、删除、改名或修改任意文件都会改变签名；排序和明确
    分隔符保证同一组文件无论文件系统枚举顺序如何都得到相同结果。

    该签名用于快速判断“索引对应的源文件集合是否仍是当前版本”，不同于
    rag_documents.sha256：后者是一份文件的内容指纹，这里是整个知识库快照。
    """
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
    """
    检查源文件、manifest 与 Chroma 是否一致，不加载 Embedding 模型。

    检查顺序从成本较低、错误更基础的条件开始：manifest 是否存在且合法、
    索引结构版本、源目录内容签名、collection 名称、collection 可读取性，
    最后比较预期 chunk_id 与实际向量 ID 集合。返回 reason_code 供前端显示
    明确原因，也供“检查并重建”决定是否跳过耗时的 Embedding。
    """
    documents_dir = str(documents_dir)
    chroma_dir = str(chroma_dir)
    manifest_path = Path(chroma_dir) / "rag_index_manifest.json"
    # 只执行确定性的 Markdown 切片，不初始化模型。由当前源文件重新计算出的
    # chunk_id 集合就是“当前代码规则下应该存在的向量 ID 集合”。
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
    # manifest 是当前有效 collection 的轻量指针和版本凭证。
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
    # 结构版本不一致意味着即使源文档没变，切片/ID 规则也可能已经变化。
    if manifest.get("schema_version") != RAG_INDEX_SCHEMA_VERSION:
        return {**base, "reason": "索引结构版本已过期", "reason_code": "SCHEMA_OUTDATED"}
    # 内容签名不一致覆盖新增、删除、改名、修改四类源文件变化。
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
    # 数量相同也不代表一致，因此比较完整集合而不是只比较 count。
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
        # state_lock 只保护当前索引引用和查询计数，持锁时间必须很短；
        # rebuild_lock 则保证同一进程一次只有一个全量重建，避免重复消耗资源。
        self._state_lock = threading.Lock()
        self._rebuild_lock = threading.Lock()
        # active_queries 记录仍持有旧索引快照的查询。重建切换后不能立即删除
        # 旧 collection，要等计数归零后再清理。
        self._active_queries = 0
        self._retired_stores = []
        self._docs = []
        self._vector_store = None
        self._vector_retriever = None
        self._bm25 = None
        self._bm25_retriever = None
        # Reranker 在第一次真实查询时才加载。单独使用初始化锁，避免多个首次
        # 请求重复加载同一模型；不复用 state_lock，防止慢速模型加载阻塞查询
        # 获取索引快照。
        self._reranker = None
        self._reranker_initialized = False
        self._reranker_lock = threading.Lock()
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
        # 启动优先复用已验证的持久化 collection；任一校验不通过才全量重建。
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
        """源文件和向量记录均一致时，复用磁盘上的 Chroma collection。"""
        if not self._manifest_path.is_file():
            return False
        try:
            manifest = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            # 先用 manifest 做廉价判断，失败就交给 rebuild 创建新 collection。
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
            # 内容签名只能证明源文件未变；再比较完整 ID 集合，防止 collection
            # 被部分删除、写入中断或混入额外向量。
            stored_ids = set(store.get()["ids"])
            expected_ids = {doc.metadata["chunk_id"] for doc in docs}
            if stored_ids != expected_ids:
                return False
            vector_retriever = (
                store.as_retriever(search_kwargs={"k": VECTOR_TOP_K})
                if docs else None
            )
            # Chroma 持久化在磁盘，BM25 是进程内对象，应用重启后必须重建。
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
        """原子写入当前有效索引的轻量清单。"""
        # 先完整写临时文件，再通过 os.replace 原子替换。进程中断时不会留下
        # 半截 JSON，读者只会看到旧 manifest 或完整的新 manifest。
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
        """释放一次查询快照，并在最后一个旧查询结束后清理退役索引。"""
        retired = []
        with self._state_lock:
            self._active_queries -= 1
            if self._active_queries == 0 and self._retired_stores:
                retired = self._retired_stores
                self._retired_stores = []
        self._dispose_stores(retired)

    def rebuild(self):
        """
        全量构建一套新索引，成功后再原子发布，失败时保留当前索引。

        这是简化的蓝绿切换：新 collection 使用随机名称，与线上 collection
        隔离；Chroma、BM25 和 manifest 全部准备成功后，才在 state_lock 内
        一次性替换查询所需的全部引用。
        """
        with self._rebuild_lock:
            docs = load_and_split_documents(self._documents_dir)
            # 签名必须和本次实际读取的源文件处于同一重建过程，用于下次启动
            # 或管理员检查时确认 collection 对应的是哪一版文件集合。
            source_signature = self._document_signature()
            # 不复用固定 collection 名，避免失败的重建污染当前可用索引。
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
                # 只有两路索引都构建成功后才发布 manifest。
                self._write_manifest(collection_name, source_signature)
            except Exception:
                # 新版本失败只清理新 collection，当前线上索引引用完全不动。
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
                # 在同一个短临界区内替换 docs、Chroma、BM25 和统计数据，
                # 查询线程不会观察到“向量是新版但 BM25 还是旧版”的混合状态。
                old_store = self._vector_store
                self._docs = docs
                self._vector_store = new_store
                self._vector_retriever = vector_retriever
                self._bm25 = bm25
                self._bm25_retriever = bm25_retriever
                self._stats = result
                if old_store is not None:
                    self._retired_stores.append(old_store)
                # 没有正在运行的查询时可立即删除旧 collection；否则由最后一个
                # 查询在 _release_query 中完成延迟清理。
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
        """线程安全地懒加载 Cross-Encoder；同一进程最多初始化一次。"""
        # 快速路径：加载完成后的普通查询无需每次竞争初始化锁。
        if self._reranker_initialized:
            return self._reranker

        with self._reranker_lock:
            # 等待锁期间，另一个线程可能已经完成初始化，必须再次检查。
            if self._reranker_initialized:
                return self._reranker

            try:
                from sentence_transformers import CrossEncoder
                print("   🔄 正在加载 Cross-Encoder 重排序模型 (BAAI/bge-reranker-base)...")
                self._reranker = CrossEncoder("BAAI/bge-reranker-base")
                print("   ✅ 重排序模型加载成功")
            except ImportError:
                print("   ⚠️ 未安装 sentence-transformers，重排序功能将跳过")
                self._reranker = None
            # initialized 与模型对象分开记录：True + None 表示已经确认依赖
            # 不可用，后续查询直接降级，不再反复尝试 import。
            # CrossEncoder 构造时若出现网络/文件等其他异常，本行不会执行，
            # 异常继续抛出且 initialized 保持 False，后续请求仍有机会重试。
            self._reranker_initialized = True
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
            # 查询开始时一次性取得同一版本的只读快照。随后即使发生索引切换，
            # 本次查询的 Chroma、BM25 和 docs 仍来自同一个旧版本。
            self._active_queries += 1
            docs = tuple(self._docs)
            vector_store = self._vector_store
            vector_retriever = self._vector_retriever
            bm25_retriever = self._bm25_retriever
        try:
            return self._query_with_state(
                query_text,
                top_k,
                docs,
                vector_store,
                vector_retriever,
                bm25_retriever,
            )
        finally:
            self._release_query()

    def _query_with_state(
        self,
        query_text,
        top_k,
        docs,
        vector_store,
        vector_retriever,
        bm25_retriever,
    ):
        if vector_store is None or vector_retriever is None or bm25_retriever is None:
            return "知识库当前没有可检索的文档。"

        print(f"\n收到 RAG 查询，字符数: {len(query_text)}")

        # ---------- 0. title/topics 轻量元数据预过滤 ----------
        filtered_docs, metadata_matches = select_metadata_filtered_documents(
            query_text,
            docs,
        )
        if filtered_docs:
            matched_sources = sorted(metadata_matches)
            chroma_filter = (
                {"source": matched_sources[0]}
                if len(matched_sources) == 1
                else {"source": {"$in": matched_sources}}
            )
            # Chroma 使用 source filter；BM25 没有动态 where 条件，因此直接在
            # 完全相同的候选切片上创建轻量索引，保证两路召回范围一致。
            _, active_bm25_retriever = self._build_keyword_index(filtered_docs)
            print(
                "\n[元数据预过滤] "
                f"title/topics 命中 {len(matched_sources)} 份文档、"
                f"{len(filtered_docs)} 个切片: {', '.join(matched_sources)}"
            )
        else:
            # 没有高置信度元数据命中时不做硬过滤，两路同时回退全库。
            chroma_filter = None
            active_bm25_retriever = bm25_retriever
            print("\n[元数据预过滤] title/topics 未命中，使用全库检索")

        # ---------- 1. 向量检索 ----------
        print("\n[召回-1] 向量检索 (Chroma)...")
        if chroma_filter is not None:
            vector_docs = vector_store.similarity_search(
                query_text,
                k=min(VECTOR_TOP_K, len(filtered_docs)),
                filter=chroma_filter,
            )
        else:
            vector_docs = vector_retriever.invoke(query_text)
        print(f"   ✅ 召回 {len(vector_docs)} 个文档")
        if vector_docs:
            print(f"   最高分片段预览: {vector_docs[0].page_content[:60]}...")

        # ---------- 2. BM25 检索 ----------
        print("\n[召回-2] BM25 关键词检索...")
        bm25_docs = active_bm25_retriever.invoke(query_text)
        print(f"   ✅ 召回 {len(bm25_docs)} 个文档")
        if bm25_docs:
            print(f"   最高分片段预览: {bm25_docs[0].page_content[:60]}...")

        # ---------- 3. 动态权重融合 (加权 RRF) ----------
        w_vec, w_bm25 = self._compute_weights(query_text)
        print(f"\n[融合] 权重分配: 向量={w_vec:.1f}, BM25={w_bm25:.1f}")

        # RRF 使用名次而不是两种模型不可直接比较的原始分数。k_const 越大，
        # 前几名之间的分差越平缓；两路都命中的切片会累加两份贡献。
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
        # 双路召回解决“尽量不要漏”，Cross-Encoder 读取 query 与完整候选正文，
        # 负责在较小候选集中提高最终排序精度。
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
    """
    获取引擎并发布最新索引。

    force 当前用于保留管理接口的调用语义；是否需要重建由路由层的完整一致性
    检查决定。引擎已经初始化时调用本函数会执行 rebuild；未初始化时，构造
    RAGEngine 会自行判断复用现有索引还是重建。
    """
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
