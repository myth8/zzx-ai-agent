# RAG 检索增强生成

> 本文档详细阐述 ZZX-AI 超级智能体中的 RAG（Retrieval-Augmented Generation）实现——一种多路召回 + 加权融合 + 重排序的经典检索增强生成架构，专门服务于恋爱情感领域的知识问答。从概念、作用、实现思路、实现效果四个维度展开，深入分析每个环节的原理与设计决策。

---

## 一、概念

### 1.1 什么是 RAG

RAG（Retrieval-Augmented Generation，检索增强生成）是一种将**信息检索**与**文本生成**相结合的 AI 技术架构。核心思想是：在 LLM 生成回答之前，先从外部知识库中检索出与问题相关的文档片段，将其作为上下文注入到 LLM 的输入中，从而让 LLM 基于检索到的知识生成更准确、更可靠的回答。

**与传统 LLM 的对比：**

```
传统 LLM 问答：
  用户问题 → LLM（仅依赖训练数据中的知识） → 回答
  （知识截止于训练数据日期，可能过时或幻觉）

RAG 问答：
  用户问题 → 知识库检索（实时查询） → 检索结果 + 问题 → LLM → 回答
  （知识来自实时检索的文档，可更新、可追溯）
```

### 1.2 为什么需要 RAG

| 问题 | 说明 | RAG 的解决方式 |
| :--- | :--- | :--- |
| **知识截止** | LLM 训练数据有时间截止点，新知识无法覆盖 | 通过外部知识库提供最新信息 |
| **幻觉问题** | LLM 可能编造不存在的知识 | 检索结果作为事实依据，约束 LLM 输出 |
| **领域专精** | 通用 LLM 在垂直领域（如恋爱咨询）表现不佳 | 领域知识库提供专业化内容 |
| **可追溯性** | LLM 的回答无法溯源 | 检索结果可追溯到具体文档段落 |

### 1.3 本项目 RAG 架构概览

```
                    ┌─────────────────────────────────────┐
                    │           用户查询                    │
                    └──────────┬──────────────────────────┘
                               │
                    ┌──────────▼──────────────────────────┐
                    │     Markdown 文档预处理（离线）        │
                    │                                      │
                    │   documents/                         │
                    │   ├── dating.md    (恋爱篇)           │
                    │   ├── married.md   (已婚篇)           │
                    │   └── single.md    (单身篇)           │
                    │         │                             │
                    │         ├→ Front Matter 解析（元数据） │
                    │         ├→ Markdown 标题切分          │
                    │         └→ 递归字符切分（chunk）       │
                    └──────────┬──────────────────────────┘
                               │
                    ┌──────────▼──────────────────────────┐
                    │       双路检索引擎（在线）             │
                    │                                      │
                    │  ┌─────────────┐  ┌─────────────┐   │
                    │  │ 向量检索     │  │ BM25 关键词  │   │
                    │  │ (Chroma +   │  │ (rank_bm25) │   │
                    │  │  BGE emb)   │  │             │   │
                    │  │ 语义匹配     │  │ 精确关键词   │   │
                    │  │ Top-10      │  │ Top-10      │   │
                    │  └──────┬──────┘  └──────┬──────┘   │
                    │         │                │           │
                    │         └──────┬─────────┘           │
                    │                │                     │
                    │         ┌──────▼──────┐              │
                    │         │ 加权 RRF    │              │
                    │         │ 融合排序    │              │
                    │         │ Top-5       │              │
                    │         └──────┬──────┘              │
                    │                │                     │
                    │         ┌──────▼──────┐              │
                    │         │ Cross-     │              │
                    │         │ Encoder    │              │
                    │         │ 重排序     │              │
                    │         │ Top-3      │              │
                    │         └────────────┘              │
                    └──────────┬──────────────────────────┘
                               │
                    ┌──────────▼──────────────────────────┐
                    │    Agent 工具调用                    │
                    │                                      │
                    │   rag_search(query) → 格式化结果文本   │
                    │   → 注入 LLM 上下文 → 生成回答        │
                    └─────────────────────────────────────┘
```

---

## 二、作用

### 2.1 知识库概况

RAG 知识库包含 3 篇 Markdown 文档，覆盖恋爱、已婚、单身三种情感状态：

| 文档 | 文件名 | Front Matter |
| :--- | :--- | :--- |
| 恋爱篇 | `dating.md` | title: 恋爱常见问题 - 恋爱篇, status: 恋爱中, category: 情感解惑 |
| 已婚篇 | `married.md` | title: 恋爱常见问题 - 已婚篇, status: 已婚, category: 情感解惑 |
| 单身篇 | `single.md` | title: 恋爱常见问题 - 单身篇, status: 单身, category: 情感解惑 |

每篇文档包含 5 个常见问题，每个问题包含：
- 关键词标签（`>` 行）
- 核心观点（**加粗强调**）
- 详细解释
- 推荐课程链接

### 2.2 解决的问题

| # | 场景 | 无 RAG 时 | 有 RAG 时 |
| :--- | :--- | :--- | :--- |
| 1 | "经常吵架是不是不合适" | LLM 给出通用回答，可能缺乏针对性 | 检索到文档中的具体建议，包括沟通技巧和倾听方法 |
| 2 | "总想翻对方手机" | 可能给出空泛的心理分析 | 检索到信任危机和安全感相关的专业分析 |
| 3 | "消费观差异大" | 可能忽略财务管理方面的建议 | 检索到财务沟通和价值观磨合的实用技巧 |

### 2.3 核心价值

| 价值 | 说明 |
| :--- | :--- |
| **领域专业化** | 知识库由恋爱咨询专家编写，比通用 LLM 更专业 |
| **可追溯** | 每个检索结果都带有相关性评分，可追溯到原文 |
| **可更新** | 更新知识库只需修改或添加 .md 文件，无需重新训练模型 |
| **低延迟** | 首次初始化后查询延迟在秒级，BM25 检索 < 10ms |

---

## 三、实现思路

### 3.1 系统架构

```
RAGEngine 单例
  │
  ├── 离线初始化阶段（应用启动时执行一次）
  │     ├── load_and_split_documents()
  │     │     ├── 遍历 documents/*.md
  │     │     ├── _parse_front_matter()     → 提取 YAML 元数据
  │     │     ├── MarkdownHeaderTextSplitter → 按标题切分
  │     │     └── RecursiveCharacterTextSplitter → 过长块二次切分
  │     │
  │     ├── Chroma.from_documents()
  │     │     └── BAAI/bge-small-zh-v1.5 → 计算 embedding 并持久化
  │     │
  │     ├── BM25Okapi()
  │     │     └── 基于分词结果构建倒排索引
  │     │
  │     └── Cross-Encoder (lazy loading)
  │           └── BAAI/bge-reranker-base → 重排序模型
  │
  └── 在线查询阶段（每次用户请求触发）
        ├── 向量检索（Chroma）→ Top-10
        ├── BM25 检索       → Top-10
        ├── 加权 RRF 融合   → Top-5
        └── Cross-Encoder 重排序 → Top-3
```

### 3.2 文档加载与切分

**文件位置**：`app/llm/rag.py` 中的 `load_and_split_documents` 函数

#### 3.2.1 Front Matter 解析

```python
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
```

**原理**：YAML Front Matter 是 Markdown 文件头部用 `---` 包裹的元数据区域。解析器提取每一行 `key: value` 格式的键值对，作为文档的元数据字典。

**解析示例：**

```markdown
原文：                          解析结果：
---                             meta = {
title: 恋爱常见问题 - 恋爱篇       "title": "恋爱常见问题 - 恋爱篇",
status: 恋爱中                    "status": "恋爱中",
category: 情感解惑                "category": "情感解惑"
---                             }
```

**元数据的用途**：
- **过滤条件**：未来可按 `status` 或 `category` 过滤检索范围
- **上下文增强**：元数据会传递到每个 Chunk 的 `metadata` 字段，随检索结果一起返回
- **溯源标识**：当检索到某个 Chunk 时，可以通过 metadata 追溯到所属文档

#### 3.2.2 双层切分策略

**第一层：Markdown 标题切分**

```python
headers_to_split_on = [
    ("#", "文档标题"),
    ("##", "问题标题"),
]
markdown_splitter = MarkdownHeaderTextSplitter(
    headers_to_split_on=headers_to_split_on,
    strip_headers=False,
)
```

**原理**：`MarkdownHeaderTextSplitter` 根据 Markdown 标题层级（`#`、`##`）将文档切分为语义块。每个标题及其下的内容构成一个独立的 Chunk。

**切分示例：**
```
原始文档：
# 恋爱篇                    → Chunk 1（标题：恋爱篇）
## 1. 经常吵架...          → Chunk 2（标题：恋爱篇 > 1. 经常吵架...）
## 2. 总想翻手机...        → Chunk 3（标题：恋爱篇 > 2. 总想翻手机...）
```

**为什么先按标题切？** 因为标题是文档最自然的语义分割点。一个问题标题下的内容本身就是一个完整的 QA 对，保持这种完整性对后续检索和 LLM 理解至关重要。

**第二层：递归字符切分（过长块二次切分）**

```python
char_splitter = RecursiveCharacterTextSplitter(
    chunk_size=600,
    chunk_overlap=50,
    separators=["\n\n", "\n", "。", "，", " ", ""],
)
```

**原理**：`RecursiveCharacterTextSplitter` 按照分隔符优先级（从高到低）递归地拆分文本。它先尝试按段落（`\n\n`）切分，如果得到的块仍然过长，则依次尝试按行（`\n`）、句号（`。`）、逗号（`，`）切分。

**为什么要二次切分？** 一个问题可能包含多个段落、大量细节，整体作为一个 Chunk 可能会：
- 超过 embedding 模型的最大输入长度（BGE-small-zh 最大 512 token）
- 包含过多噪声，降低检索精度
- 占据过多 LLM 上下文空间

**参数设计：**

| 参数 | 值 | 说明 |
| :--- | :--- | :--- |
| `chunk_size` | 600 字符 | 约 300-400 token，适合 BGE 模型 |
| `chunk_overlap` | 50 字符 | 相邻块间的重叠，避免切在关键句上 |
| `separators` | `["\n\n", "\n", "。", "，", " ", ""]` | 从段落到字符的逐步递进 |

**Chunk 的 metadata 继承链：**

```
原始文件 → _parse_front_matter() → file_meta（文档级元数据）
    │
    ├→ MarkdownHeaderTextSplitter → chunk.metadata（标题级元数据）
    │     │
    │     └→ 合并: chunk_meta = dict(file_meta) + chunk.metadata
    │
    └→ RecursiveCharacterTextSplitter（仅对过长块）
          │
          └→ 合并: sub_meta = dict(chunk_meta) + sub.metadata
```

**metadata 最终结构示例：**

```python
{
    "title": "恋爱常见问题 - 恋爱篇",     # 来自 Front Matter
    "status": "恋爱中",                   # 来自 Front Matter
    "category": "情感解惑",               # 来自 Front Matter
    "文档标题": "恋爱篇",                 # 来自 Markdown #{header}
    "问题标题": "1. 经常吵架..."         # 来自 Markdown ##{header}
}
```

#### 3.2.3 切分效果

```
3 篇文档 → 按标题切分 → ~15 个块（每文档5个问题）
                          ↓
                   过长块二次切分 → ~XX 个最终 Chunk
```

每个 Chunk 包含：
- `page_content`：文本内容（600 字以内）
- `metadata`：继承自文档和标题的元数据字典

### 3.3 向量检索（Chroma + BGE）

**文件位置**：`RAGEngine.__init__` 中的初始化过程

#### 3.3.1 Embedding 模型

```python
embed_model = HuggingFaceEmbeddings(
    model_name='BAAI/bge-small-zh-v1.5',
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': True}
)
```

**模型选择理由：**

| 维度 | BAAI/bge-small-zh-v1.5 | 说明 |
| :--- | :--- | :--- |
| **参数量** | 约 24M | 轻量级，CPU 推理速度快 |
| **语言** | 中文优化 | 针对中文语义理解做了专门训练 |
| **向量维度** | 512 维 | 平衡精度和存储成本 |
| **归一化** | `normalize_embeddings=True` | 使向量模长为 1，余弦相似度 = 点积，加速计算 |

**原理**：Embedding 模型将文本映射到高维向量空间。语义相近的文本在向量空间中距离更近。例如"男女朋友吵架怎么办"和"恋爱中的冲突处理"两个文本的向量在空间中的夹角会比"男女朋友吵架怎么办"和"如何理财"更小。

#### 3.3.2 Chroma 向量数据库

```python
self._vector_store = Chroma.from_documents(
    documents=self._docs,
    embedding=embed_model,
    persist_directory=CHROMA_DIR,   # chroma_db/
    collection_name="love_rag",
)
```

**原理**：Chroma 是一个开源向量数据库，支持：
- 将文档自动转换为 embedding 并索引
- 基于向量相似度进行 ANN（Approximate Nearest Neighbor）检索
- 持久化到磁盘，重启后可恢复

**存储结构：**

```
chroma_db/
├── chroma.sqlite3              # 元数据和索引
└── 6d72db2b-d732-42c4-8ae3-49fee836b411/
    ├── header.bin              # 向量头部
    ├── length.bin              # 向量长度
    ├── data_level0.bin         # 向量数据（HNSW 图索引）
    └── link_lists.bin          # HNSW 图连接列表
```

#### 3.3.3 向量检索执行

```python
self._vector_retriever = self._vector_store.as_retriever(
    search_kwargs={"k": VECTOR_TOP_K}  # 10
)
```

**检索原理**：
1. 用户查询文本经 BGE 模型转换为查询向量（`normalize_embeddings=True`，计算点积 ≈ 余弦相似度）
2. Chroma 使用 HNSW（Hierarchical Navigable Small World）算法在向量空间中搜索
3. 返回与查询向量最相似的 Top-10 文档块

**为什么召回 Top-10 而非 Top-3？** 召回阶段优先保证**查全率**（Recall），后续的融合和重排序阶段会处理**查准率**（Precision）。如果召回阶段就限制为 Top-3，可能遗漏一些通过不同方式表达的但实际相关的文档。

### 3.4 BM25 关键词检索

```python
self._bm25 = BM25Okapi([d.page_content.split() for d in self._docs])
self._bm25_retriever = BM25Retriever.from_documents(self._docs)
self._bm25_retriever.k = BM25_TOP_K  # 10
```

#### 3.4.1 原理

BM25（Best Matching 25）是一种基于**词频-逆文档频率**（TF-IDF）改进的排序算法。其核心公式：

```
Score(D, Q) = Σ (IDF(qi) * TF(qi, D) * (k1 + 1) / (TF(qi, D) + k1 * (1 - b + b * |D|/avgdl)))
```

其中：
- `qi`：查询中的第 i 个词
- `TF(qi, D)`：词 qi 在文档 D 中的出现频率
- `IDF(qi)`：词 qi 的逆文档频率（稀有词权重大）
- `|D|`：文档 D 的长度
- `avgdl`：所有文档的平均长度
- `k1`、`b`：可调参数（控制词频饱和度和文档长度归一化）

**为什么需要 BM25？** 向量检索捕捉的是"语义相似性"，但可能忽略精确的关键词匹配。例如用户问"如何与伴侣沟通"，BM25 能精确匹配到含有"沟通技巧"关键词的文档，即使这些文档的语义向量与查询不完全对齐。

#### 3.4.2 向量检索 vs BM25 的互补性

| 维度 | 向量检索（Chroma） | 关键词检索（BM25） |
| :--- | :--- | :--- |
| **匹配方式** | 语义匹配 | 精确关键词匹配 |
| **优势** | 理解近义词、同义表达 | 精确匹配专有名词、短查询 |
| **劣势** | 对短查询、罕见词不敏感 | 无法处理同义表达 |
| **适用场景** | 长查询、自然语言描述 | 短查询、精确关键词 |
| **延时** | ~100ms | ~5ms |

```
互补场景示例：
  用户查： "情侣间怎么和好"
  向量检索：能匹配到"吵架后如何修复关系"（语义相近但字面不同）✓
  BM25：    能匹配到"和好"这个词出现的文档 ✓
  单一路径可能遗漏，双路互补提高召回率
```

### 3.5 加权 RRF 融合

#### 3.5.1 原理：RRF（Reciprocal Rank Fusion）

RRF 是一种**无监督的排序融合算法**，其核心思想是：如果一个文档在多个排序系统中都排在前面，它应该获得更高的融合分数。

**RRF 公式：**

```
Score(d) = Σ (w_i / (k + rank_i(d)))
```

其中：
- `rank_i(d)`：文档 d 在第 i 个检索系统中的排名
- `k`：常数（通常为 60）
- `w_i`：第 i 个检索系统的权重

#### 3.5.2 加权实现

本项目对 RRF 进行了加权改进，为向量检索和 BM25 分配不同权重：

```python
def _compute_weights(query: str) -> Tuple[float, float]:
    """根据查询长度动态调整向量检索和 BM25 的权重。"""
    if len(query) < 20:
        return 0.4, 0.6   # (向量权重, BM25权重)
    return 0.7, 0.3
```

**为什么动态权重？**

| 查询长度 | 含义 | 权重倾向 | 原因 |
| :--- | :--- | :--- | :--- |
| < 20 字 | 短查询（关键词式） | BM25=0.6 > 向量=0.4 | 短查询关键词精确，BM25 更有效 |
| ≥ 20 字 | 长查询（句子式） | 向量=0.7 > BM25=0.3 | 长查询语义丰富，向量检索更有效 |

**融合计算：**

```python
k_const = 60
for rank, doc in enumerate(vector_docs):
    key = doc.page_content[:200]                  # 去重键（前200字符）
    score_map[key] += w_vec / (k_const + rank + 1) # 向量贡献
    text_map[key] = doc.page_content

for rank, doc in enumerate(bm25_docs):
    key = doc.page_content[:200]
    score_map[key] += w_bm25 / (k_const + rank + 1) # BM25 贡献
    if key not in text_map:
        text_map[key] = doc.page_content
```

**融合效果示意（假设 3 个文档）：**

```
            向量排序     BM25 排序    RRF 融合得分    融合排名
文档 A:     第 1 名     第 3 名      0.4/61 + 0.6/63   第 1 名
文档 B:     第 2 名     未召回        0.4/62            第 3 名
文档 C:     未召回       第 1 名      0.6/61            第 2 名
```

**文档 B** 只在向量检索中命中且排名靠后，融合后掉到第 3。
**文档 C** 只在 BM25 中命中但排名第 1，融合后排到第 2。
**文档 A** 在两个系统中都命中，融合后排第 1。

**去重机制**：使用 `doc.page_content[:200]` 作为去重键，避免同一文档在两种检索中重复计分。

#### 3.5.3 为什么需要融合

| 方案 | 查全率 | 查准率 | 鲁棒性 |
| :--- | :--- | :--- | :--- |
| 仅向量检索 | 中（遗漏关键词精确匹配） | 高 | 低（受 embedding 质量影响） |
| 仅 BM25 | 中（遗漏语义相似内容） | 中 | 低（受分词质量影响） |
| **双路融合** | **高** | **高** | **高**（两路互补） |

### 3.6 Cross-Encoder 重排序

#### 3.6.1 原理

Cross-Encoder 与 Bi-Encoder（Embedding 模型）的本质区别在于计算方式：

| 模型 | 计算方式 | 精度 | 速度 | 适用阶段 |
| :--- | :--- | :--- | :--- | :--- |
| **Bi-Encoder** | 分别编码查询和文档，计算向量距离 | 中 | 快（可预计算） | **召回阶段** |
| **Cross-Encoder** | 将查询和文档拼接后一同编码，输出相关性分数 | **高** | 慢（不可预计算） | **重排序阶段** |

**原理示意图：**

```
Bi-Encoder（向量检索）：
  查询："吵架怎么办" → [0.2, 0.5, 0.1, ...]  ← 独立编码
  文档："冲突处理"   → [0.3, 0.4, 0.2, ...]  ← 独立编码
  → 计算余弦相似度（信息有损）

Cross-Encoder（重排序）：
  拼接：[CLS] 吵架怎么办 [SEP] 冲突处理方法包括... [SEP]
  → 注意力机制同时观察查询和文档的每个词
  → 直接输出相关性分数（信息无损）
```

**为什么 Cross-Encoder 精度更高？** 因为 Cross-Encoder 让查询和文档在 Transformer 的注意力层中**交互计算**，模型可以捕捉查询中的每个词与文档中的每个词之间的细粒度关系。而 Bi-Encoder 将查询和文档分别编码为固定向量后再计算相似度，在这一过程中丢失了词级别的交互信息。

#### 3.6.2 实现

```python
self._reranker = CrossEncoder("BAAI/bge-reranker-base")
```

**懒加载机制：**

```python
def _get_reranker(self):
    if self._reranker is None:
        try:
            from sentence_transformers import CrossEncoder
            self._reranker = CrossEncoder("BAAI/bge-reranker-base")
        except ImportError:
            self._reranker = None    # sentence-transformers 未安装时跳过
    return self._reranker
```

**执行重排序：**

```python
pairs = [[query_text, c] for c in candidates]        # 构建查询-文档对
scores = reranker.predict(pairs)                      # 批量预测相关性
ranked = sorted(zip(candidates, scores), key=lambda x: -x[1])  # 按分数降序
```

#### 3.6.3 为什么重排序重要

假设融合后 Top-5 候选文档的相关性得分如下：

| 排名 | 融合前 | 内容 | Cross-Encoder | 重排序后 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | 文档 C | 关于吵架的详细分析 | 0.92 | **第 1 名** |
| 2 | 文档 A | 包含"吵架"关键词但内容泛化 | 0.45 | **第 5 名**（被淘汰） |
| 3 | 文档 B | 部分相关但主题偏离 | 0.38 | 被淘汰 |

重排序在这里的重要性：
1. **纠正融合误差**：融合排名第 1 的文档 A 只是因为关键词"吵架"在两种检索中都有命中，但实际内容不够相关，Cross-Encoder 将其分数降至 0.45
2. **精确筛选**：从 Top-5 精确到 Top-3，只保留真正相关的文档注入 LLM 上下文
3. **减少噪声**：不相关的检索结果会干扰 LLM 的生成质量，重排序将噪声降至最低

### 3.7 格式化输出

```python
parts = []
for i, (txt, score) in enumerate(ranked[:top_k], 1):
    parts.append(f"[参考{i}]（相关度: {score:.3f}）\n{txt}")

final_output = "\n\n".join(parts)
```

**输出格式示例：**

```
[参考1]（相关度: 0.923）
沟通是恋爱中最关键的技能之一...

[参考2]（相关度: 0.897）
当你们经常因为小事争吵时，重要的是...

[参考3]（相关度: 0.856）
建立健康的冲突处理模式需要双方努力...
```

每个结果包含：
- **编号**：`[参考1]` 等，供 LLM 引用
- **相关度**：`（相关度: 0.923）`，Cross-Encoder 的精确评分
- **内容**：文档正文

### 3.8 全局单例与线程安全

```python
_engine: Optional[RAGEngine] = None

def get_engine() -> RAGEngine:
    global _engine
    if _engine is None:
        with RAGEngine._lock:
            if _engine is None:
                _engine = RAGEngine()
    return _engine
```

**双重检查锁定（Double-checked Locking）：**

```
线程 A                  线程 B
  │                      │
  │ _engine is None?     │
  │ → True               │
  │                      │
  │ 获取锁               │
  │                      │ _engine is None?
  │ _engine is None?     │ → True（A 还没创建完）
  │ → True（第一次检查已过）│
  │                      │
  │ 创建 engine          │ 等待锁释放
  │ 释放锁               │
  │                      │
  │                      │ 获取锁
  │                      │ _engine is None?
  │                      │ → False（A 已创建）
  │                      │ 释放锁（不创建）
```

这种模式在保证线程安全的同时，避免了每次调用都加锁的性能开销。

### 3.9 Agent 工具集成

```python
@tool
def rag_search(query: str) -> str:
    """
    Search the love-and-relationship knowledge base.
    Use this when the user asks questions about dating, marriage, breakups,
    relationship advice, emotional issues, or similar topics.
    Input: the user's question or keywords.
    """
    return get_engine().query(query)
```

**工具描述的作用：**
- 场景指引："dating, marriage, breakups, relationship advice" 枚举所有适用场景
- 领域限定："love-and-relationship knowledge base" 让 Agent 知道搜索范围
- 参数说明：传入用户的原始问题或关键词

---

## 四、实现效果

### 4.1 核心指标

| 指标 | 值 | 说明 |
| :--- | :--- | :--- |
| **知识库规模** | 3 篇文档，~15 个问题 | 覆盖恋爱/已婚/单身三种状态 |
| **Chunk 数量** | 按标题切分 + 二次切分 | 每个 Chunk ≤ 600 字 |
| **向量检索召回数** | Top-10 | 优先保证查全率 |
| **BM25 检索召回数** | Top-10 | 与向量检索互补 |
| **融合后候选数** | Top-5 | 经 RRF 加权融合筛选 |
| **最终返回数** | Top-3 | 经 Cross-Encoder 精确重排序 |
| **初始化时间** | ~2-5 分钟 | 加载 Embedding 模型 + 计算向量 |
| **单次查询时间** | < 1 秒 | 向量检索 ~100ms + BM25 ~5ms + 重排序 ~300ms |

### 4.2 完整查询链路示例

```
用户提问："经常吵架是不是说明不合适"
  │
  ├── Agent 识别 → 恋爱问题，调用 rag_search("经常吵架是不是说明不合适")
  │
  ├── 向量检索（Chroma）
  │     ├── 查询向量：[0.12, 0.45, ...]
  │     └── 返回 Top-10 语义相关文档
  │
  ├── BM25 检索
  │     ├── 关键词：经常、吵架、说明、不合适
  │     └── 返回 Top-10 关键词匹配文档
  │
  ├── 加权 RRF 融合（短查询 < 20 字，BM25 权重 0.6）
  │     └── 融合排序 → Top-5
  │
  ├── Cross-Encoder 重排序
  │     ├── 构建 ["经常吵架是不是说明不合适", "吵架本身不意味着不合适..."]
  │     └── 返回精确相关性评分 → Top-3
  │
  └── 格式化结果：
        [参考1]（相关度: 0.923）
        吵架本身不意味着不合适，不会吵架才意味着问题...

        [参考2]（相关度: 0.897）
        恋爱中的冲突往往源于沟通不畅...
```

### 4.3 RAG 引擎初始化日志

```
============================================================
🚀 初始化 RAG 引擎
============================================================

[1/5] 加载并切分文档..
📨 开始加载文档目录 xxx/documents
    找到 3 个 Markdown 文件
   [1/3] 处理文件: dating.md
      → 按标题切分为 5 个块
      → 当前累计文档片段数 5
   [2/3] 处理文件: married.md
      → 按标题切分为 5 个块
      → 当前累计文档片段数 10
   [3/3] 处理文件: single.md
      → 按标题切分为 5 个块
      → 当前累计文档片段数 15
✅ 文档加载完成，共生成 15 个文档片段

[2/5] 初始化 Embedding 模型 (BAAI/bge-small-zh-v1.5)...
    ✅ Embedding 模型加载成功

[3/5] 构建 Chroma 向量数据库...
    ✅ Chroma 向量数据库构建完成

[4/5] 创建向量检索器...
    ✅ 向量检索器就绪，召回 top-10

[5/5] 构建 BM25 关键词索引...
    ✅ BM25 索引构建完成，召回 top-10

🎉 RAG 引擎初始化完成！
============================================================
```

### 4.4 重排序的重要性：一个具体例子

**用户查询**："总想翻对方手机"

**无重排序时**（仅融合 Top-3）：

| 排名 | 文档片段 | 是否真正相关 |
| :--- | :--- | :--- |
| 1 | 翻手机这个行为本身往往是不安全感的... | ✅ 是 |
| 2 | 消费观差异大时，需要坦诚沟通... | ❌ 否（包含"差异"但主题偏离） |
| 3 | 激情消退不意味着不爱... | ❌ 否 |

**有重排序后（Cross-Encoder Top-3）：**

| 排名 | 文档片段 | Cross-Encoder 得分 |
| :--- | :--- | :--- |
| 1 | 翻手机这个行为本身往往是不安全感的... | 0.94 |
| 2 | 安全感缺失时，需要先问自己... | 0.88 |
| 3 | 信任危机需要双方坦诚沟通... | 0.82 |

重排序将不相关的文档从 Top-3 中剔除，确保注入 LLM 的上下文都是高质量的。

---

## 五、总结

### 5.1 各环节职责总结

| 环节 | 组件 | 职责 | 输入 | 输出 |
| :--- | :--- | :--- | :--- | :--- |
| **文档预处理** | `load_and_split_documents` | 将原始 Markdown 切分为标准化的 Chunk | .md 文件 | LangChain Document 列表 |
| **Front Matter 解析** | `_parse_front_matter` | 提取 YAML 元数据 | 文档文本 | metadata 字典 |
| **标题切分** | `MarkdownHeaderTextSplitter` | 按语义边界初次切分 | 整篇文档 | 标题级 Chunk |
| **字符切分** | `RecursiveCharacterTextSplitter` | 控制 Chunk 长度 | 过长 Chunk | 合规模的子 Chunk |
| **向量索引** | Chroma + BGE | 构建语义索引 | Chunk 列表 | 向量数据库 |
| **向量检索** | Chroma retriever | 语义相似度搜索 | 用户查询 | Top-10 语义相关文档 |
| **关键词索引** | BM25Okapi | 构建倒排索引 | Chunk 内容 | BM25 索引 |
| **关键词检索** | BM25Retriever | 精确关键词匹配 | 用户查询 | Top-10 关键词匹配文档 |
| **融合排序** | 加权 RRF | 融合两种检索结果 | 双路结果 | Top-5 候选 |
| **重排序** | Cross-Encoder | 精确计算相关性 | 候选列表 | Top-3 最终结果 |
| **工具封装** | `rag_search` | 对外暴露为 LangChain 工具 | 用户查询 | 格式化结果字符串 |

### 5.2 设计决策总结

| 决策 | 选择 | 理由 |
| :--- | :--- | :--- |
| 向量模型 | BGE-small-zh-v1.5 | 轻量中文模型，CPU 可运行 |
| 向量维度 | 512 | 平衡精度和存储 |
| 切分策略 | 标题 + 递归字符 | 保持语义完整性 + 控制长度 |
| Chunk 大小 | 600 字 | 适合 BGE 模型输入限制 |
| 检索召回数 | 各 Top-10 | 查全优先，后续有融合和重排序 |
| 融合算法 | 加权 RRF | 简单高效，无需训练 |
| 权重策略 | 动态（按查询长度） | 短查询偏 BM25，长查询偏向量 |
| 重排序模型 | BGE-reranker-base | 高性能中文重排序模型 |
| 返回数 | Top-3 | 够用不冗余，节省 LLM Token |
| 单例模式 | 双重检查锁定 | 线程安全 + 高性能 |
| 懒加载 | Cross-Encoder | 避免不必要的模型加载 |

### 5.3 一句话总结

| 概念 | 一句话总结 |
| :--- | :--- |
| **文档预处理** | Markdown → Front Matter 元数据 + 双层切分 → 标准化 Chunk |
| **向量检索** | BGE 语义编码 + Chroma ANN 索引，捕捉"意思相近"的文档 |
| **BM25 检索** | 关键词精确匹配，弥补向量检索在短查询上的不足 |
| **加权 RRF 融合** | 按查询长度动态调整两路权重，融合排序取 Top-5 |
| **Cross-Encoder 重排序** | 查询-文档对交叉编码，精确计算相关性，从 Top-5 精筛到 Top-3 |
| **Agent 工具** | `rag_search` 将完整 RAG 链路封装为一句工具调用，Agent 按需使用 |
