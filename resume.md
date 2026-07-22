# ZZX-AI 超级智能体 — 项目要点

> 基于 Flask + LangChain + DeepSeek + Vue 3 的全栈 AI 对话平台，集成 ReAct Agent、RAG、MCP、Skills 技能系统等机制，提供恋爱大师（Chain 模式）和超级智能体（Agent 模式）两种 AI 服务。

---

## 架构与交互模式

- 基于 LangChain 框架构建 **Chain 链式调用** 和 **ReAct Agent 智能体** 两种 LLM 交互模式，Chain 负责轻量快速的情感对话，Agent 负责复杂多步推理与工具协作
- 在 Agent 中实现 **Thought → Action → Observation → Final Answer** 的推理循环，设定 15 轮最大迭代和 90 秒超时保护，防止推理失控
- 利用 LangChain LCEL 声明式语法构建 Chain 管道 `ChatPromptTemplate → ChatOpenAI → StrOutputParser`，首 Token 响应延迟控制在 1-2 秒内
- 注册 6 种 Agent 工具（get_time / calc / get_now_weather / rag_search / list_skills / read_skill），覆盖时间查询、数学计算、实时天气、知识检索、技能加载五大领域

## JWT 用户认证与 SSE 流式通信

- 基于 PyJWT 实现 HS256 签名的 **JWT 无状态认证**，Token 有效期 7 天，密码经 Werkzeug 哈希存储，覆盖注册/登录/验证/用户信息完整闭环
- 使用 Flask `stream_with_context` 原生实现 **SSE 服务端推送**，无需 WebSocket 或第三方库，支持 Agent 的 [THINK]/[STEP]/[FINAL] 多阶段事件流实时推送到前端
- 前端通过 Vue Router 路由守卫 + Axios 拦截器双重保护 API 安全，未登录用户自动跳转登录页，Token 自动附加到请求 Header

## 多轮对话与持久化记忆

- 基于 session_id（UUID[:8]）驱动多轮对话，前端通过 URL 路由参数 `/love-master/:sessionId` 传递，后端从 MySQL 实时构建上下文
- 设计 MySQL 三层持久化存储：sessions 表（会话元信息）、chat_messages 表（消息记录）、chat_summaries 表（对话摘要），消息顺序由自增 msg_order 保证
- 提供完整会话 CRUD API（创建/列表/重命名/删除），前端支持会话列表按最后活跃时间排序、点击标题重命名、删除会话级联清除关联数据

## 对话摘要机制

- 使用 **LLM 自动摘要** 压缩长对话，采用双条件"或"触发策略：每 5 轮对话触发一次，或累计字符数超 8000（约 4000 Token）时强制触发
- 采用 **增量更新策略**：将已有摘要 + 最近 20 条消息传入 LLM 生成新摘要，而非每次全量重写，节省 50%-80% 的 Token 消耗
- 摘要 Prompt 设计为三要素提取：用户身份/兴趣/目标（长期信息）、主要问题或请求（短期信息）、AI 关键回答（决策信息），长度限制 500 字以内

## RAG 检索增强生成

- 构建 **多路召回 + 加权融合 + 重排序** 的经典 RAG 架构：向量检索（Chroma + BGE-small-zh-v1.5，召回 Top-10）+ BM25 关键词检索（召回 Top-10）→ 加权 RRF 融合（Top-5）→ Cross-Encoder 重排序（BGE-reranker-base，精筛至 Top-3）
- 使用 BAAI/bge-small-zh-v1.5 轻量中文嵌入模型（24M 参数，512 维向量），CPU 推理速度满足实时查询需求
- 采用 Markdown 标题切分 + 递归字符切分的双层文档切分策略，Chunk 大小 600 字、重叠 50 字，保持语义完整性的同时控制上下文窗口
- 解析 YAML Front Matter 提取文档元数据（title/status/category），元数据沿切分链继承到每个 Chunk，支持未来按属性过滤检索
- 动态权重 RRF 融合：短查询（<20 字）偏重 BM25（权重 0.6），长查询偏重向量检索（权重 0.7），适应不同查询特征
- 将完整 RAG 链路封装为单个 LangChain `@tool`，Agent 通过 `rag_search(query)` 一键调用，实现恋爱知识问答的检索增强生成

## Skills 渐进式技能系统

- 设计 **渐进式暴露（Progressive Disclosure）** 技能系统：技能指令以独立 Markdown 文件存储在 `skills/` 目录，Agent 运行时通过 `list_skills` → `read_skill` 按需发现和加载
- Agent 模板中嵌入 CRITICAL ROUTING RULE 自动路由规则，当检测到模糊/复杂/创意类请求时自主触发技能加载流程（Step A→B→C→D）
- 内置浪漫时刻表白生成器技能：调用 get_time 获取精确时间，通过时间-意象映射表（清晨/正午/黄昏/深夜四种时段）和四段式告白结构生成时刻独特的文案

## MCP 模型上下文协议

- 基于 FastMCP 框架搭建 **MCP 服务端**，采用 streamable-http 传输协议，部署在 `http://127.0.0.1:8000/mcp`，注册 get_weather 工具对接心知天气 API
- 基于 langchain-mcp-adapters 的 MultiServerMCPClient 实现 **MCP 客户端适配**，将异步 MCP 工具通过新事件循环 + 30 秒超时包装为同步 StructuredTool
- 工具调用采用桥接模式：Agent 调用 `get_now_weather` → 从 MCP 客户端筛选 `get_weather` 工具 → 异步调用 → 同步返回，实现标准化的外部服务对接

## 提示词工程

- 设计 20+ 个提示词模板，覆盖 System Prompt、Agent 模板、工具描述、摘要生成 Prompt、Skills 模板等，构建完整的 Prompt Engineering 体系
- Agent 模板采用五层结构（角色注入 → Skills 路由 → 工具列表 → 格式约束 → 零样本示例），约束 Agent 严格遵循 Thought/Action/Action Input/Final Answer 双模式输出格式
- 通过少样本示例（完整演示 get_time 工具调用链路）和 6 条 CRITICAL RULES（否定指令 + 大写强调 + 格式模板化）确保 LLM 输出格式准确性

## 前端工程

- 基于 Vue 3 + Vue Router + Vite 构建单页应用，支持懒加载路由和动态标题元数据
- 前端 API 层统一封装：Axios 实例管理 REST 请求 + EventSource 管理 SSE 流式连接，Agent 模式前端按 [THINK]/[STEP]/[FINAL] 事件类型分类渲染对话气泡
- 赛博朋克风格 UI 设计：Orbitron 字体、霓虹蓝/紫/粉配色方案、动态漂移动画背景、故障特效标题，两种 AI 服务使用差异化主题色
