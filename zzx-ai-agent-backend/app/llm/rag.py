"""
RAG 管道 — LangChain + Chroma + BM25 + Cross-Encoder 重排序
完全基于 LangChain 实现，无 llama_index 依赖
"""

import os
import threading
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


# ==============================
#  文档加载与切分
# ==============================

def _parse_front_matter(text: str) -> dict:
    """
    提取 Markdown 文件开头的 YAML Front Matter 作为元数据
    格式：
    ---
    key: value
    ---
    """
    meta = {}
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            for line in text[3:end].strip().split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
    return meta


def load_and_split_documents(doc_dir: str) -> List[LCDocument]:
    """
    读取 doc_dir 下所有 .md 文件，先按 Markdown 标题（# 和 ##）切分，
    再对过长的段落用 RecursiveCharacterTextSplitter 二次切分，
    返回 LangChain Document 列表。
    """
    md_files = sorted(Path(doc_dir).glob("*.md"))
    all_docs: List[LCDocument] = []

    # 定义按 Markdown 标题切分的层级
    headers_to_split_on = [
        ("#", "文档标题"),
        ("##", "问题标题"),
    ]
    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=False,
    )
    # 用于二次切分过长的块
    char_splitter = RecursiveCharacterTextSplitter(
        chunk_size=600,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "，", " ", ""],
    )

    print(f"📂 开始加载文档目录: {doc_dir}")
    print(f"   找到 {len(md_files)} 个 Markdown 文件")

    for idx, md_path in enumerate(md_files, 1):
        print(f"   [{idx}/{len(md_files)}] 处理文件: {md_path.name}")
        text = md_path.read_text(encoding="utf-8")
        file_meta = _parse_front_matter(text)

        # 1. 按 Markdown 标题切分
        header_splits = markdown_splitter.split_text(text)
        print(f"      → 按标题切分为 {len(header_splits)} 个块")

        for chunk in header_splits:
            chunk_meta = dict(file_meta)
            if hasattr(chunk, "metadata") and chunk.metadata:
                chunk_meta.update(chunk.metadata)

            # 2. 如果块较短则直接添加，否则进行二次切分
            if len(chunk.page_content) < 600:
                chunk.metadata = chunk_meta
                all_docs.append(chunk)
            else:
                sub_chunks = char_splitter.split_documents([chunk])
                for sub in sub_chunks:
                    sub_meta = dict(chunk_meta)
                    if hasattr(sub, "metadata") and sub.metadata:
                        sub_meta.update(sub.metadata)
                    sub.metadata = sub_meta
                    all_docs.append(sub)

        print(f"      → 当前累计文档片段数: {len(all_docs)}")

    print(f"✅ 文档加载完成，共生成 {len(all_docs)} 个文档片段\n")
    return all_docs


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

    def __init__(self):
        os.makedirs(CHROMA_DIR, exist_ok=True)

        print("=" * 60)
        print("🚀 初始化 RAG 引擎")
        print("=" * 60)

        # ---------- 1. 加载并切分文档 ----------
        print("\n[1/5] 加载并切分文档...")
        self._docs = load_and_split_documents(DOCUMENTS_DIR)

        if not self._docs:
            raise RuntimeError(f"未在 {DOCUMENTS_DIR} 中找到任何文档")

        # 打印一个片段样例供参考
        sample = self._docs[0]
        print(f"   样例片段（前80字符）: {sample.page_content[:80]}...")
        print(f"   片段元数据: {sample.metadata}")

        # ---------- 2. 初始化 Embedding 模型 ----------
        print("\n[2/5] 初始化 Embedding 模型 (BAAI/bge-small-zh-v1.5)...")
        embed_model = HuggingFaceEmbeddings(
            model_name='BAAI/bge-small-zh-v1.5',
            model_kwargs={'device': 'cpu'},   # 如有 GPU 可改为 'cuda'
            encode_kwargs={'normalize_embeddings': True}
        )
        print("   ✅ Embedding 模型加载成功")

        # ---------- 3. 构建 Chroma 向量库 ----------
        print("\n[3/5] 构建 Chroma 向量库（计算所有片段的 embedding 并写入磁盘）...")
        print(f"   持久化目录: {CHROMA_DIR}")
        print(f"   待处理文档片段数: {len(self._docs)}")
        self._vector_store = Chroma.from_documents(
            documents=self._docs,
            embedding=embed_model,
            persist_directory=CHROMA_DIR,
            collection_name="love_rag",
        )
        print("   ✅ Chroma 向量库构建完成")

        # ---------- 4. 创建向量检索器 ----------
        print("\n[4/5] 创建向量检索器...")
        self._vector_retriever = self._vector_store.as_retriever(
            search_kwargs={"k": VECTOR_TOP_K}
        )
        print(f"   ✅ 向量检索器就绪，召回 top-{VECTOR_TOP_K}")

        # ---------- 5. 构建 BM25 索引 ----------
        print("\n[5/5] 构建 BM25 关键词索引...")
        # 用所有文档的内容（分词）构建 BM25 模型
        self._bm25 = BM25Okapi([d.page_content.split() for d in self._docs])
        self._bm25_retriever = BM25Retriever.from_documents(self._docs)
        self._bm25_retriever.k = BM25_TOP_K
        print(f"   ✅ BM25 索引构建完成，召回 top-{BM25_TOP_K}")

        # Cross-encoder 重排序器（懒加载，在第一次查询时初始化）
        self._reranker = None

        print("\n🎉 RAG 引擎初始化完成！")
        print("=" * 60 + "\n")

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
        print("\n" + "🔍" * 20)
        print(f"📝 已接收查询，字符数: {len(query_text)}")
        print("🔍" * 20)

        # ---------- 1. 向量检索 ----------
        print("\n[召回-1] 向量检索 (Chroma)...")
        vector_docs = self._vector_retriever.invoke(query_text)
        print(f"   ✅ 召回 {len(vector_docs)} 个文档")
        if vector_docs:
            print(f"   最高分片段预览: {vector_docs[0].page_content[:60]}...")

        # ---------- 2. BM25 检索 ----------
        print("\n[召回-2] BM25 关键词检索...")
        bm25_docs = self._bm25_retriever.invoke(query_text)
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
                _engine = RAGEngine()
    return _engine


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
__all__ = ["rag_search", "RAG_TOOLS", "get_engine", "RAGEngine"]
