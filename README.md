# ZZX-AI Agent Platform

一个面向真实业务场景的全栈 AI Agent 平台。后端使用 Flask，前端使用 Vue 3，模型层接入 DeepSeek，围绕 **多引擎 Agent、RAG、MCP、Skills、会话记忆与可观测性** 构建完整闭环。

## 项目简介

项目最早从 AI 对话 Demo 起步，逐步补齐了认证、会话、RAG、MCP、Skills、多引擎 Agent、Telemetry 和测试体系，目前包含三类 AI 服务空间：

- **AI 恋爱大师**：面向情感咨询的 Chain 模式助手，轻量、快速、擅长共情式建议。
- **AI 超级智能体**：支持 LangChain ReAct、ToolCallingAgent、CodeAgent 三种 Agent 引擎。
- **管理员空间**：RAG 知识库管理与 Agent Telemetry 观测台。

三种 Agent 引擎共享同一套工具、会话体系、SSE 协议和指标口径，便于横向对比和按场景选型。

## 设计借鉴与致谢

项目在实现过程中参考了以下开源项目和设计思想，并在当前业务场景下做了重新实现：

- **LangChain**：ReAct Agent 与 Chain 模式的基线实现。
- **HuggingFace smolagents**：MultiStepAgent 多步循环、ToolCallingAgent / CodeAgent 的动作语义、AgentMemory / 步骤记忆与内容截断思路；本项目在此基础上增加了项目化提示词、上下文字符预算、Telemetry 和统一 META。
- **DSH Telemetry（DeepSeek Harness）**：结构化 run/step 事件、session/request 关联、显式脱敏和 best-effort 的设计思路；本项目没有直接接入 OTel exporter，而是落地为本地 MySQL Telemetry 与管理员观测台。
- **assistant-ui**：Thread list / thread view / composer 的交互分层参考；当前前端是 Vue 3，因此采用 Vue 原生实现，没有直接引入 React 组件库。

参考链接：

- [LangChain](https://github.com/langchain-ai/langchain)
- [HuggingFace smolagents](https://github.com/huggingface/smolagents)
- [assistant-ui](https://www.assistant-ui.com/)

## 核心能力

### 1. 三种 Agent 引擎

| 引擎 | 动作语言 | 控制循环 | 适用场景 |
|---|---|---|---|
| **LangChain ReAct** | 文本 `Thought / Action / Observation` | LangChain `AgentExecutor` | 通用问答、稳定生产基线 |
| **MultiStep ToolCallingAgent** | OpenAI 原生 `tool_calls` | 自研 `MultiStepAgent` | 多工具、结构化参数、工具链审计 |
| **MultiStep CodeAgent** | Python 代码 | 自研 `MultiStepAgent` + 受限 AST 执行器 | 计算、循环、数据编排、复杂多工具任务 |

三个引擎：

- 共享同一套 `ToolSpec` 工具目录；
- 共享会话存储、SSE 协议和 `[META]` 指标；
- 通过 `engine=react|toolcalling|code` 路由切换；
- 每个引擎拥有独立会话空间，避免不同动作协议污染同一段记忆。

前端入口：

```text
/super-agent                    引擎选择
/super-agent/react              ReAct 会话列表
/super-agent/toolcalling        ToolCalling 会话列表
/super-agent/code               CodeAgent 会话列表
/super-agent/:engine/:sessionId 对应引擎对话页
```

### 2. RAG 知识库

- Markdown 为知识源，支持 YAML Front Matter 元数据；
- Chroma 向量召回 + BM25 关键词召回；
- 加权 RRF 融合 + BGE Cross-Encoder 重排序；
- 稳定切片 ID、内容指纹、索引版本与一致性检查；
- 管理员可上传、删除、预览切片、检查并重建索引；
- 重建期间旧索引继续服务，新索引成功后原子切换。

### 3. MCP 与工具生态

Agent 工具目录包含：

- `get_time`：当前时间；
- `calc`：安全数学表达式计算；
- `get_now_weather`：通过 MCP 天气服务查询实时天气；
- `rag_search`：检索恋爱情感知识库；
- `list_skills` / `read_skill`：渐进式技能发现与读取。

MCP 服务独立运行，Agent 通过 streamable HTTP 连接，工具实现不绑定某个引擎。

### 4. Skills 渐进式技能

Skills 用 Markdown 描述领域工作流，Agent 按需发现和加载：

```text
list_skills → read_skill → 按技能正文执行
```

当前示例技能：时间敏感型浪漫表白文案生成器。技能正文只在需要时进入上下文，避免常驻 prompt 膨胀。

### 5. 会话记忆与上下文管理

- 会话和消息持久化在 MySQL；
- 长对话使用摘要 + 最近消息构建上下文；
- Agent 内部使用 `AgentMemory` 保存 `TaskStep` / `ActionStep`；
- 上下文预算会保留最近步骤、整步丢弃旧步骤并截断超长 Observation；
- 整步丢弃保证 `tool_calls` 与 tool response 不被拆散。

### 6. 可观测性

三层观测：

1. **前端统计条**：步数、工具调用、Token、耗时；
2. **SSE `[META]`**：每轮运行的结构化指标；
3. **`agent.trace` JSON 日志 + MySQL Telemetry**：
   - run / step / LLM / tool 事件；
   - token、耗时、工具调用、上下文预算；
   - 原始问题与最终回答仅管理员可见；
   - 仅管理员可访问 `/telemetry-admin` 观测台。

管理员观测台按 **会话 → 运行 → 事件时间线** 展示，支持引擎/状态筛选和自动刷新。

### 7. 安全与认证

- JWT Access/Refresh Token；
- Redis 登录会话、吊销与续签；
- 管理员角色与邀请码；
- 登录、注册、聊天、管理接口差异化限流；
- 输入长度、格式、控制字符、Markdown 上传校验；
- 前端 Markdown 渲染清洗与请求上下文日志。

### 8. SSE 流式响应

对话使用 SSE 推送：

```text
[THINK] / [CODE] / [STEP] / [OBSERVE] / [FINAL] / [META]
```

前端基于 Fetch + ReadableStream 读取，支持 Bearer Token、错误事件和请求 ID。

## 技术栈

| 层级 | 技术 | 用途 |
|---|---|---|
| 后端框架 | Flask 3.x | RESTful API、蓝图、SSE |
| 模型框架 | LangChain 0.3.x | ReAct Agent、Chain、Prompt |
| 模型适配 | langchain-openai + openai SDK | LangChain 与 MultiStep 引擎 |
| 模型 | DeepSeek Chat | 对话与 Agent 推理 |
| 数据库 | MySQL + PyMySQL + SQLAlchemy | 会话、消息、RAG、Telemetry |
| 迁移 | Alembic | 数据库版本管理 |
| 缓存/认证 | Redis | JWT 会话、吊销、限流 |
| 向量检索 | ChromaDB + BGE Embedding | RAG 语义召回 |
| 关键词检索 | rank_bm25 | RAG 关键词召回 |
| 重排序 | BGE Cross-Encoder | RAG 结果重排 |
| MCP | FastMCP + langchain-mcp-adapters | 外部工具协议 |
| 前端 | Vue 3 + Vue Router + Vite | 单页应用 |
| HTTP | Axios | API 请求 |
| 身份认证 | Flask-JWT-Extended | JWT 与角色鉴权 |

## 系统架构

```text
浏览器 Vue 3
  ├─ 登录 / 会话 / 对话 / 管理页
  └─ SSE 流式对话
          │
          ▼
Flask API
  ├─ JWT + Redis + 限流
  ├─ 会话与摘要 MySQL
  ├─ 三引擎路由
  │    ├─ LangChain ReAct
  │    └─ MultiStepAgent
  │          ├─ ToolCallingAgent
  │          └─ CodeAgent
  ├─ 共享工具目录
  │    ├─ RAG
  │    ├─ MCP 天气
  │    └─ Skills
  └─ Telemetry
       ├─ agent.trace JSON
       └─ MySQL run/event 表
```

## 快速开始

### 1. 环境

- Python 3.11+
- Node.js 20+
- MySQL 8
- Redis 7+
- 可选：Conda

### 2. 后端

```bash
cd zzx-ai-agent-backend
conda create -n zzx-ai-agent python=3.11
conda activate zzx-ai-agent
pip install -r requirements.txt

cp .env.example .env
# 填写 DEEPSEEK_API_KEY、MySQL、Redis 等配置

alembic upgrade head
python run.py
```

默认地址：`http://127.0.0.1:18317`

健康检查：`GET /api/health`

### 3. 前端

```bash
cd zzx-ai-agent-frontend
npm install
npm run dev
```

默认地址：`http://localhost:17317`

### 4. MCP 天气服务

```bash
cd zzx_mcp_server
conda activate zzx-ai-agent
# 在 .env 中配置 SENIVERSE_API_KEY
python server.py
```

默认地址：`http://127.0.0.1:19317/mcp`

## API 摘要

### 认证

```text
POST /api/auth/register
POST /api/auth/login
POST /api/auth/refresh
DELETE /api/auth/logout
GET  /api/auth/userinfo
```

### 会话

```text
GET    /api/session/list
POST   /api/session/create
PUT    /api/session/rename
DELETE /api/session/<session_id>
GET    /api/session/<session_id>/messages
```

### 对话

```text
GET /api/ai/love_app/chat/sse?message=...&session_id=...
GET /api/ai/manus/chat?message=...&session_id=...&engine=react|toolcalling|code
```

### 管理员

```text
/api/admin/rag/*
/api/admin/telemetry/conversations
/api/admin/telemetry/runs
/api/admin/telemetry/runs/<run_id>
/api/admin/telemetry/summary
```

## 项目结构

```text
zzx-ai-agent/
├── zzx-ai-agent-backend/
│   ├── app/
│   │   ├── agent_core/            # 手写 MultiStepAgent 引擎
│   │   │   ├── agents.py          # MultiStepAgent / ToolCallingAgent / CodeAgent
│   │   │   ├── memory.py          # AgentMemory / 上下文预算
│   │   │   ├── observability.py   # agent.trace JSON 事件
│   │   │   ├── local_python_executor.py
│   │   │   ├── runner.py          # 引擎构建 + SSE 桥接
│   │   │   └── prompts/           # 项目化提示词
│   │   ├── llm/
│   │   │   ├── agent.py           # LangChain ReAct
│   │   │   ├── chain.py           # Chain 模式
│   │   │   ├── rag.py             # RAG 引擎
│   │   │   ├── tool_registry.py   # 三引擎共享工具目录
│   │   │   └── agent_metrics.py   # ReAct 指标回调
│   │   ├── telemetry.py           # Telemetry 持久化与查询
│   │   ├── routes/                # 对话、会话、RAG、Telemetry 路由
│   │   ├── repositories/          # chat_runs、幂等
│   │   ├── auth.py                # JWT + Redis 认证
│   │   ├── chat_history.py        # 会话、消息、摘要
│   │   ├── rag_documents.py       # RAG 文档台账
│   │   └── db.py                  # SQLAlchemy 连接池
│   ├── migrations/                # Alembic 迁移
│   ├── tests/                     # unittest 回归测试
│   ├── scripts/                   # 备份、预检、benchmark
│   ├── documents/                 # RAG 知识文档
│   └── skills/                    # Skills 模板
│
├── zzx-ai-agent-frontend/
│   └── src/
│       ├── views/
│       │   ├── EngineSelect.vue   # 引擎选择
│       │   ├── SessionList.vue    # 会话列表
│       │   ├── SuperAgent.vue     # 智能体对话
│       │   ├── TelemetryAdmin.vue # 管理员观测台
│       │   └── RagAdmin.vue       # RAG 管理
│       ├── components/            # ChatRoom、Markdown、EngineTabs
│       └── config/engines.js      # 引擎元数据
│
├── zzx_mcp_server/                # FastMCP 天气服务
└── docs/                          # 设计、测试、博客与索引
```

## 测试与基准

```bash
cd zzx-ai-agent-backend
conda activate zzx-ai-agent
python -m unittest discover -s tests

cd ../zzx-ai-agent-frontend
npm run build
```

三引擎基准：

```bash
cd zzx-ai-agent-backend
python scripts/benchmark_agents.py --runs 3 \
  --out ../docs/dev/agent-benchmark-v2-adapted.json
```

当前实测：7 类任务 × 3 个引擎 × 3 次重复，共 63 次运行。详细结果见测试报告。

## 文档导航

- [项目文档索引](docs/文档索引.md)
- [多引擎 Agent 架构与实现](docs/dev/多引擎Agent架构与实现.md)
- [三引擎 Token 计算与代码位置详解](docs/dev/三引擎Token计算与代码位置详解.md)
- [三引擎 Agent 性能测试报告](docs/dev/三引擎Agent性能测试报告.md)
- [三引擎 Agent 方案设计与性能总结](docs/dev/三引擎Agent方案设计与性能测试总结.md)
- [Agent 上下文管理与可观测性](docs/dev/Agent上下文管理与可观测性.md)
- [Agent Telemetry 观测台设计](docs/dev/AgentTelemetry观测台设计.md)
- [多引擎 Agent 提交计划](docs/dev/多引擎Agent提交计划.md)
- [本地开发服务配置](docs/dev/本地开发服务配置.md)

## License

本项目采用 MIT License，详见 [LICENSE](LICENSE)。
`opencoderef/smolagents_ref` 为 smolagents 参考源码，遵循其 Apache-2.0 协议。
