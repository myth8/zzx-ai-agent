# ZZX-AI 超级智能体

## 项目背景

ZZX-AI 超级智能体是一个基于大语言模型的 AI 对话平台，当前提供两类 AI 对话能力和一个管理员知识库空间：

- **AI 恋爱大师**（AI Love Master）：面向情感咨询场景的温暖型对话助手，通过链式调用（Chain）模式提供温柔、共情的恋爱建议。
- **AI 超级智能体**（AI Super Agent）：面向通用问答场景的全能型 AI 助手，基于 ReAct Agent 模式，具备工具调用、知识检索、技能模板等能力，可以解决各类专业问题。
- **RAG 知识库管理**：仅管理员可见，支持 Markdown 文档、全文、切片、上传、删除和索引重建。

项目采用前后端分离架构，后端以 Flask 提供 RESTful API 和 SSE 流式接口，前端以 Vue 3 构建单页应用，覆盖了从用户注册登录、会话管理、流式对话到持久化记忆的完整链路。

## 技术栈

| 层级 | 技术 | 用途 |
| :--- | :--- | :--- |
| **后端框架** | Flask 3.x | Web 服务框架，路由分发、蓝图注册 |
| **AI 框架** | LangChain 0.3.x | LLM 调用、Agent/Chain 构建、Prompt 管理 |
| **LLM 模型** | DeepSeek Chat (deepseek-chat) | 底层大语言模型 |
| **数据库** | MySQL + PyMySQL | 用户权限、会话消息和 RAG 文档台账 |
| **向量数据库** | ChromaDB + BGE embedding | RAG 知识库语义检索 |
| **关键词检索** | BM25 (rank_bm25) | RAG 多路召回的关键词分支 |
| **重排序** | BGE Reranker (Cross-Encoder) | RAG 多路召回后的结果排序 |
| **MCP 服务** | FastMCP + langchain-mcp-adapters | 标准化工具协议，连接外部服务 |
| **前端框架** | Vue 3 + Vue Router | 单页应用框架 |
| **前端构建** | Vite | 前端开发服务器与打包 |
| **HTTP 客户端** | Axios | 前端 API 请求 |
| **SSE 通信** | Fetch + ReadableStream | 携带 Bearer Token 的流式对话 |
| **身份认证** | Flask-JWT-Extended + Redis | JWT 续签、登录状态和吊销 |
| **密码加密** | Werkzeug | 密码哈希存储 |

## 编程软件

- **PyCharm 2024** — 后端 Python 代码开发与调试，Flask / LangChain 等服务的本地运行和断点调试。
- **Codex** — AI 辅助编程工具，用于代码补全、重构优化、项目文档生成和技术方案讨论。
- **VSCode** — 前端 Vue 3 项目的开发与预览。
- **Navicat / MySQL Workbench** — MySQL 数据库可视化管理。

## 关键技术

### 1. ReAct Agent（推理-行动循环）

项目核心之一，基于 LangChain 的 `create_react_agent` 实现。Agent 遵循 **Thought → Action → Observation → Final Answer** 的循环范式：

```
用户输入 → 思考(Thought) → 选择工具(Action) → 观察结果(Observation) → 继续推理或输出最终答案(Final Answer)
```

实现文件：`app/llm/agent.py`

Agent 内置了以下能力：
- **最大推理轮次**：15 轮，防止死循环
- **超时保护**：90 秒强制终止
- **解析容错**：遇到格式错误自动重试
- **提前停止**：使用 `generate` 策略，输出不完整时强制生成最终答案

### 2. 工具调用（Tool Calling）

Agent 注册了多类工具，可根据用户问题自主选择合适的工具：

| 工具名称 | 功能 | 来源 |
| :--- | :--- | :--- |
| `get_time` | 获取当前日期时间 | 内置工具 |
| `calc` | 数学表达式计算 | 内置工具 |
| `get_now_weather` | 查询实时天气 | 通过 MCP 代理调用外部天气服务 |
| `rag_search` | 情感知识库语义搜索 | RAG 引擎封装 |
| `list_skills` | 列出所有可用技能模板 | Skills 中间件 |
| `read_skill` | 读取指定技能的完整指令 | Skills 中间件 |

### 3. 多轮对话（Multi-turn Conversation）

后端通过 `session_id` 管理对话上下文。每次请求携带 `session_id`，服务端从 MySQL 中加载该会话的历史消息和对话摘要，构造完整的上下文窗口传入 LLM，实现多轮对话能力。

实现文件：`app/chat_history.py`

前端路由设计：
- `/love-master/:sessionId` — AI 恋爱大师多轮对话
- `/super-agent/:sessionId` — AI 超级智能体多轮对话

### 4. 持久化记忆（Persistent Memory）

所有对话历史持久化存储在 MySQL 中，包含三张核心表：

- **sessions 表** — 会话元信息（用户 ID、会话 ID、对话类型、标题、时间戳）
- **chat_messages 表** — 消息详细记录（角色、内容、序号、时间）
- **chat_summaries 表** — 对话摘要（用于长对话压缩）

API 提供了完整的会话 CRUD 接口：
- `GET /api/session/list` — 获取会话列表
- `POST /api/session/create` — 创建新会话
- `PUT /api/session/rename` — 重命名会话
- `DELETE /api/session/:id` — 删除会话
- `GET /api/session/:id/messages` — 获取会话消息

### 5. 对话摘要（Dialogue Summarization）

长对话场景下，上下文窗口会持续增长。系统采用**自动摘要更新策略**，在以下条件满足时触发 LLM 生成对话摘要：

- **轮次触发**：每 5 轮对话（user + assistant 为一轮）自动生成一次摘要
- **Token 阈值触发**：当累计字符数估算的 token 超过 4000 时强制生成摘要

摘要信息与最近 N 条消息共同构成上下文，传递给 Agent 或 Chain，有效控制了上下文窗口长度，同时保留了对话的关键信息。

### 6. RAG（检索增强生成）

RAG 引擎基于 **多路召回 + 加权融合 + 重排序** 的经典架构，专门服务于恋爱情感领域的知识问答。

**检索流程：**

```
用户查询 → [向量检索(Chroma) + BM25关键词检索] → 加权RRF融合 → Cross-Encoder重排序 → 输出Top-K结果
```

**实现细节：**
- **向量模型**：`BAAI/bge-small-zh-v1.5`（轻量中文 embedding 模型）
- **文档切分**：先按 Markdown 标题切分，再对长块做递归字符切分（chunk_size=600, overlap=50）
- **ChromaDB**：持久化向量存储，支持语义搜索
- **BM25**：关键词检索，与向量检索形成互补
- **动态权重**：短查询偏向 BM25（0.6），长查询偏向向量检索（0.7）
- **Cross-Encoder**：`BAAI/bge-reranker-base` 对融合结果进行精确相关性排序

RAG 工具暴露为 LangChain 的 `@tool`，可直接被 Agent 调用。

管理员可以通过 `/rag-admin` 管理 `documents` 目录中的 Markdown 知识源。YAML Front Matter 作为文档元数据独立解析，不参与正文向量化；每个正文切片拥有稳定 ID、章节标题和内容指纹。后端使用 `rag_documents` 保存文档台账，使用 `rag_document_chunks` 逐条保存切片正文与元数据；`chunk_id` 同时作为 Chroma `vector_id`，保证两侧一一对应。上传、删除成功后会刷新 Chroma 与 BM25。新向量 collection 构建完成后才切换查询状态，失败时回滚文件操作并保留旧索引；文档内容未变化时，应用重启会通过索引清单复用已有向量 collection。

管理页面提供 Markdown 格式说明和可下载的 `示例.md`。上传时会依次展示文件校验、上传、切片与向量构建、页面刷新状态；索引构建阶段显示动态进度和已用时间。

“检查并重建”会先核对源文件签名、索引结构版本、Chroma collection、向量 ID 和 MySQL 切片 ID；全部一致时跳过重建，只有索引过期或数据不一致时才重新生成向量。

RAG 管理接口全部使用 `admin_required`。前端隐藏入口只负责使用体验，不能替代后端授权。

实现文件：`app/llm/rag.py`

### 7. Skills（渐进式技能模板）

Skills 是一种**渐进式技能模板**机制，允许 Agent 在运行时按需发现并加载领域特定的多步骤工作流程。

**设计理念：**
- **渐进式暴露**：Agent 先通过 `list_skills` 查看有哪些可用技能，再通过 `read_skill` 获取完整的指令文档，按指令逐步执行
- **自动路由**：当用户提出模糊、复杂或创意类请求时，Agent 会自动判断是否匹配某个技能，无需用户手动触发

**内置技能：**
- **浪漫时刻表白生成器**（`romantic_confession_generator`）：根据当前精确时间（调用 `get_time` 工具），生成约 200 字的情景化表白文案，包含时间意象映射和四段式结构（定格瞬间 → 自然联想 → 核心告白 → 未来邀约）

实现文件：
- `app/llm/skill_middleware.py`
- `skills/romantic_confession_generator.md`

### 8. MCP（模型上下文协议）

项目实现了完整的 MCP 双向通信架构，包含 MCP 服务端和客户端适配器。

**MCP 服务端**（`zzx_mcp_server/server.py`）：
- 基于 FastMCP 框架，使用 `streamable-http` 传输协议
- 注册了 `get_weather` 工具，对接心知天气 API 获取实时天气数据
- 部署在 `http://127.0.0.1:8000/mcp`

**MCP 客户端适配**（`app/llm/mcp_tools.py`）：
- 基于 `langchain-mcp-adapters` 的 `MultiServerMCPClient` 连接 MCP 服务端
- 将异步 MCP 工具包装为同步 LangChain `StructuredTool`，与 Agent 无缝集成
- 支持超时控制（30 秒）和异常处理

**MCP Helper**（`zzx_mcp_server/mcp_helper.py`）：
- 基于 stdio 传输的备选客户端，通过 JSON-RPC 协议与 MCP 服务端交互
- 支持 `tools/list` 和 `tools/call` 标准方法

### 9. JWT 登录认证

用户认证采用 JWT（JSON Web Token）方案，基于 HS256 签名算法。

**实现细节：**
- **注册接口**：`POST /api/auth/register` — 用户名 + 昵称 + 密码，密码经 Werkzeug 哈希后存储
- **登录接口**：`POST /api/auth/login` — 验证凭据后签发 7 天有效期的 JWT Token
- **验证接口**：`GET /api/auth/verify` — 验证 Token 有效性
- **用户信息**：`GET /api/auth/userinfo` — 获取当前用户信息
- **装饰器**：`@login_required` — 保护需要登录的 API 路由，从 Authorization Header 中提取并验证 Bearer Token

**前端集成：**
- Axios 请求拦截器自动附加 Bearer Token
- 路由守卫（`beforeEach`）控制未登录用户跳转到登录页
- Token 和用户信息存储在 `localStorage` 中

实现文件：`app/auth.py`

### 10. SSE 流式响应

前后端通信基于 Server-Sent Events（SSE）实现实时流式输出。

**事件格式：**
```
data: [THINKING]       // 心跳信号，防止前端超时
data: [THINK] 思考内容  // Agent 的思考过程
data: [STEP] 工具调用   // 工具执行步骤与结果
data: [FINAL] 最终答案  // LLM 生成的最终回复
data: [DONE]           // 流结束信号
```

实现文件：
- `app/utils/sse.py`
- `src/api/index.js`（前端）

### 11. Chain 模式（链式调用）

AI 恋爱大师采用 LangChain 的 LCEL（LangChain Expression Language）链式调用模式：

```
ChatPromptTemplate (system + human) → ChatOpenAI → StrOutputParser → 文本流
```

相比 Agent 模式，Chain 模式更轻量、响应更快，适合情感咨询这类不需要复杂工具调用的场景。

实现文件：`app/llm/chain.py`

### 12. 双模式切换

系统支持两种 LLM 调用模式：

- **chain（AI 恋爱大师）**— 链式调用，直接对话，快速回复
- **agent（AI 超级智能体）** — ReAct Agent 模式，具备工具调用、RAG、Skills、MCP 等全部能力

提供了统一健康检查接口 `GET /api/health` 返回当前运行状态。

## 项目结构

```
zzx-ai-agent/
├── zzx-ai-agent-backend/          # 后端 Flask 应用
│   ├── app/
│   │   ├── __init__.py            # Flask 应用工厂
│   │   ├── config.py              # 全局配置（API Key、数据库、JWT）
│   │   ├── auth.py                # JWT 认证（注册/登录/鉴权）
│   │   ├── chat_history.py        # 会话管理、消息持久化、摘要生成
│   │   ├── rag_documents.py       # RAG 文档台账和文件安全处理
│   │   ├── llm/
│   │   │   ├── __init__.py        # 共享 LLM 实例（ChatOpenAI）
│   │   │   ├── agent.py           # ReAct Agent 实现（工具调用 + 流式输出）
│   │   │   ├── chain.py           # Chain 链式调用实现
│   │   │   ├── rag.py             # RAG 引擎（Chroma + BM25 + Reranker）
│   │   │   ├── skill_middleware.py # Skills 渐进式技能模板中间件
│   │   │   └── mcp_tools.py       # MCP 工具适配器
│   │   ├── routes/
│   │   │   ├── manus.py           # AI 超级智能体路由
│   │   │   ├── love_app.py        # AI 恋爱大师路由
│   │   │   ├── session.py         # 会话 CRUD API
│   │   │   └── rag_admin.py       # 管理员 RAG 文档 API
│   │   └── utils/
│   │       └── sse.py             # SSE 流式响应工具
│   ├── documents/                 # RAG 知识库文档（Markdown）
│   ├── chroma_db/                 # ChromaDB 持久化文件
│   ├── skills/                    # Skills 技能模板
│   ├── requirements.txt
│   └── run.py                     # 启动入口
│
├── zzx-ai-agent-frontend/         # 前端 Vue 3 应用
│   ├── src/
│   │   ├── api/index.js           # API 封装（Axios + SSE）
│   │   ├── router/index.js        # 路由配置（含登录守卫）
│   │   ├── views/
│   │   │   ├── Home.vue           # 首页
│   │   │   ├── Login.vue          # 登录页
│   │   │   ├── Register.vue       # 注册页
│   │   │   ├── SessionList.vue    # 会话列表
│   │   │   ├── LoveMaster.vue     # AI 恋爱大师对话页
│   │   │   ├── SuperAgent.vue     # AI 超级智能体对话页
│   │   │   └── RagAdmin.vue       # RAG 知识库管理页
│   │   └── components/
│   │       ├── ChatRoom.vue       # 聊天室组件
│   │       ├── MarkdownRenderer.vue # Markdown 渲染器
│   │       └── AppFooter.vue      # 页脚组件
│   ├── package.json
│   └── vite.config.js
│
├── zzx_mcp_server/                # MCP 服务端
│   ├── server.py                  # FastMCP 服务（天气查询）
│   └── mcp_helper.py              # MCP 命令行助手
│
└── README.md
