# Chain、Agent 与 Tool Calling

> 本文档详细阐述 ZZX-AI 超级智能体中的三种核心 AI 交互模式：Chain（链式调用）、Agent（智能体）和 Tool Calling（工具调用）。分别从概念、作用、实现思路、实现效果四个维度展开，并在最后对比三者的关系与适用场景。

---

## 一、Chain（链式调用）

### 1.1 概念

Chain（链式调用）是 LangChain 框架中最基础的编排模式，本质上是将多个处理步骤串联成一条**单向数据管道**——数据从 Prompt 流入 LLM，经过解析后直接流出结果，中间没有分支、循环或工具调用。

本项目中的 Chain 采用 LangChain LCEL（LangChain Expression Language）声明式语法构建：

```
ChatPromptTemplate (system + human) → ChatOpenAI → StrOutputParser → 文本流
```

整个链路是一个 `Runnable` 对象，支持 `.invoke()`（同步调用）和 `.stream()`（流式调用）。

### 1.2 作用

Chain 模式承担 **AI 恋爱大师**（AI Love Master）的对话引擎。其核心定位是：

- **轻量快速**：无需工具解析和循环推理，LLM 直接生成回复，响应延迟最低
- **情感专注**：面向情感咨询场景，System Prompt 设定为温暖共情的恋爱顾问角色
- **上下文感知**：支持通过构建好的对话历史字符串（含摘要 + 最近消息）注入上下文

### 1.3 实现思路

#### 1.3.1 工厂函数 `make_chain`

```python
# app/llm/chain.py
def make_chain(system_prompt, context=""):
```

**参数说明：**

| 参数 | 类型 | 说明 |
| :--- | :--- | :--- |
| `system_prompt` | str | AI 角色指令（例如 "You are AI Love Master, a warm relationship advisor."） |
| `context` | str | 对话上下文（由 `chat_history.build_context()` 生成的摘要 + 最近消息字符串） |

**实现逻辑：**

1. **无上下文时**：使用简单模板 `{input}` 作为 human message，直接将用户输入传入 LLM
2. **有上下文时**：切换到带 history 的模板，将构建好的对话历史通过 `{history}` 变量注入，与用户输入 `{input}` 一起传给 LLM
3. **LCEL 管道**：`prompt | llm | StrOutputParser()` 三个环节串联

**核心代码段：**

```python
prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    ("human", human_template),
])
return prompt | llm | StrOutputParser()
```

#### 1.3.2 流式调用 `stream_chain`

```python
# app/llm/chain.py
def stream_chain(chain, message, context="", session_id="", llm_ref=None):
```

**流式逻辑：**

1. 构造调用参数：`{"input": message}`，有上下文时额外传入 `{"history": context}`
2. 遍历 `chain.stream(invoke_input)` 产生的每一个 token 块，逐块 `yield`
3. 流结束后，如果提供了 `session_id`，自动保存 assistant 回复到 MySQL，并触发对话摘要更新

**路由集成**（`app/routes/love_app.py`）：

```python
@love_bp.route("/api/ai/love_app/chat/sse")
def chat():
    message = request.args.get("message", "")
    session_id = request.args.get("session_id", "")
    # 加载上下文、保存用户消息
    context = build_context(session_id)
    save_message(session_id, "user", message)
    chain = make_chain(SYSTEM_PROMPT, context)
    return sse_response(stream_chain, chain, message, context, session_id, llm)
```

**System Prompt：**

```
"You are AI Love Master, a warm relationship advisor.\n"
"Answer in Chinese. Be empathetic and give practical advice."
```

### 1.4 实现效果

- **响应速度**：Chain 模式从用户输入到 LLM 输出首 token 的延迟通常在 1-2 秒内，因为不需要工具解析和多次 LLM 调用
- **输出粒度**：`stream_chain` 以 token 块级别流式输出，前端可实时渲染文字
- **上下文管理**：通过 `build_context()` 注入摘要 + 最近 50 条消息，兼顾长对话压缩和短距离上下文
- **适用场景**：情感倾诉、关系建议、心理疏导等偏向**对话式、情感化**的交互

---

## 二、Agent（智能体）

### 2.1 概念

Agent（智能体）是比 Chain 更高级的 AI 交互模式，其核心是 **ReAct（Reasoning + Acting）范式**。Agent 不再是简单的问题-回答流水线，而是一个能够**自主推理、决策、行动**的循环系统：

```
Thought（思考）→ Action（行动）→ Observation（观察）→ Thought（思考）→ ... → Final Answer（最终答案）
```

每一轮循环中，Agent 分析当前状态和用户问题，自主选择调用某个工具，观察工具返回的结果，再将观察纳入推理，如此往复，直到得出结论并输出最终答案。

本项目中的 Agent 基于 LangChain 的 `create_react_agent` 构建，部署在 **AI 超级智能体**（AI Super Agent）服务中。

### 2.2 作用

Agent 模式承担 **AI 超级智能体**的对话引擎，其核心定位是：

- **全能型助手**：能够回答各类专业问题，不局限于特定领域
- **工具驱动**：可根据问题自主调用工具（时间查询、天气查询、数学计算、RAG 知识库、Skills 技能模板等）
- **多步推理**：能够将复杂问题拆解为多个子任务，逐步解决并汇总结果
- **技能自动路由**：遇到创意类、模糊类请求时，自动发现并执行领域技能模板

### 2.3 实现思路

#### 2.3.1 共享 LLM 实例

```python
# app/llm/__init__.py
llm = ChatOpenAI(
    model=Config.DEEPSEEK_MODEL,       # deepseek-chat
    api_key=Config.DEEPSEEK_API_KEY,
    base_url=Config.DEEPSEEK_API_BASE,  # https://api.deepseek.com/v1
    temperature=0.7,
)
```

Chain 和 Agent **共享同一个 LLM 实例**，保证底层模型一致性。

#### 2.3.2 Agent Prompt 模板

Agent 使用精心设计的 ReAct 模板（`AGENT_TEMPLATE`），包含几个关键区域：

1. **系统指令区**：由外部传入的 `system_prompt` 填充
2. **Skills 路由指令**：指导 Agent 如何自动发现和使用技能模板
3. **工具列表区**：LangChain 自动填充 `{tools}` 和 `{tool_names}`
4. **格式约束区**：严格规定 Thought / Action / Action Input / Final Answer 的输出格式
5. **示例区**：通过一个简单示例引导 Agent 理解格式要求

**关键约束规则：**

```text
=== Pattern 1 - Call a tool ===
Thought: (your reasoning)
Action: (tool name)
Action Input: (input for the tool)

=== Pattern 2 - Give the final answer ===
Thought: (your reasoning)
Final Answer: (your complete answer to the user)
```

#### 2.3.3 Agent 工厂函数 `make_agent`

```python
# app/llm/agent.py
def make_agent(system_prompt, context=""):
    full_prompt = system_prompt
    if context:
        full_prompt = system_prompt + "\n\n【对话历史】\n" + context
    tools = [get_time, calc]  # 基础工具
    prompt = PromptTemplate.from_template(AGENT_TEMPLATE).partial(system_prompt=full_prompt)
    agent = create_react_agent(llm, tools, prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=False,
        handle_parsing_errors=True,   # 格式解析容错
        max_iterations=15,             # 最大推理轮次
        early_stopping_method="generate",  # 输出不完整时强制生成答案
        max_execution_time=90,         # 超时保护（秒）
    )
```

**安全保护机制：**

| 机制 | 值 | 作用 |
| :--- | :--- | :--- |
| `max_iterations` | 15 | 防止 Agent 陷入死循环 |
| `max_execution_time` | 90 秒 | 超时强制终止 |
| `handle_parsing_errors` | True | 输出格式异常时自动重试 |
| `early_stopping_method` | "generate" | 无法继续时强制输出 |

#### 2.3.4 增强版工厂函数 `create_agent`

项目在 `skill_middleware.py` 中提供了一个增强版工厂函数，支持注入中间件和额外工具：

```python
# app/llm/skill_middleware.py
def create_agent(system_prompt, middleware=None, extra_tools=None):
    tools = list(extra_tools or [])
    if middleware:
        for m in middleware:
            if hasattr(m, "get_tools"):
                tools.extend(m.get_tools())
    # ... 同上构建 AgentExecutor
```

#### 2.3.5 流式调用 `stream_agent`

```python
# app/llm/agent.py
def stream_agent(executor, message, session_id="", llm_ref=None):
```

**流式逻辑（核心差异点）：**

与 Chain 简单的 token 块流不同，Agent 的流包含多阶段事件：

1. **遍历 executor.stream()**：每一次 `yield` 包含一组 `actions` 和可能的 `output`
2. **action 阶段**：提取 Thought 内容，生成 `[THINK]` 事件
3. **step 阶段**：提取工具执行结果，生成 `[STEP]` 事件
4. **output 阶段**：提取最终答案，生成 `[FINAL]` 事件
5. 所有事件通过 SSE 实时推送到前端

**SSE 事件格式：**

```
data: [THINKING]                     # 心跳信号
data: [THINK] 用户想知道当前时间     # Agent 的思考过程
data: [STEP] 工具: get_time 结果: 2026-07-22 10:00:00  # 工具执行
data: [FINAL] 当前时间是...          # 最终答案
data: [DONE]                         # 流结束
```

#### 2.3.6 路由集成

```python
# app/routes/manus.py
@manus_bp.route("/api/ai/manus/chat")
def chat():
    executor = create_agent(
        prompt,
        middleware=[_skill_middleware],
        extra_tools=[get_time, calc, get_now_weather, rag_search]
    )
    return sse_response(stream_agent, executor, message, session_id, llm)
```

### 2.4 实现效果

- **多步推理可见性**：前端可实时展示 Agent 的思考过程（`[THINK]`）、工具调用步骤（`[STEP]`）和最终答案（`[FINAL]`），交互透明
- **复杂问题拆解**：例如用户问"北京现在天气怎么样，适合约会吗？"，Agent 会先调用天气工具查询，再结合恋爱知识库给出建议
- **技能自动匹配**：当用户说"帮我想一段表白的话"，Agent 自动调用 `list_skills` → `read_skill`，加载浪漫表白模板并执行
- **安全兜底**：15 轮推理上限 + 90 秒超时，避免无限循环
- **适用场景**：专业问答、知识检索、数据分析、创意生成等需要**工具协作与多步推理**的交互

---

## 三、Tool Calling（工具调用）

### 3.1 概念

Tool Calling（工具调用）是 Agent 模式的**能力基石**，指的是 LLM 在推理过程中自主选择并调用外部函数的能力。Agent 本身不具备执行特定操作（如获取时间、查询天气）的能力，它通过生成结构化的工具调用指令，由框架执行并返回结果。

本项目中的工具分为三个来源：

| 来源 | 工具 | 注册方式 |
| :--- | :--- | :--- |
| **内置工具** | `get_time`、`calc` | LangChain `@tool` 装饰器 |
| **代理工具** | `get_now_weather` | 通过 MCP 客户端桥接 |
| **RAG 工具** | `rag_search` | LangChain `@tool` 装饰器封装 RAG 引擎 |
| **Skills 工具** | `list_skills`、`read_skill` | `SkillsMiddleware.get_tools()` 动态生成 |

### 3.2 作用

工具调用使 AI 超级智能体具备以下能力：

- **突破知识截止**：通过天气 API 获取实时数据，不受模型训练数据的时效限制
- **精确计算**：通过 `calc` 工具进行数学运算，避免 LLM 在算术上的天生缺陷
- **知识库检索**：通过 `rag_search` 从领域知识库中检索精确信息
- **技能模板加载**：通过 `list_skills` / `read_skill` 动态加载领域专用工作流
- **MCP 标准协议**：通过 MCP 工具适配器，可与任何遵循 MCP 协议的外部服务通信

### 3.3 实现思路

#### 3.3.1 内置工具（`@tool` 装饰器）

**`get_time` 工具：**

```python
@tool
def get_time():
    """Get current date and time. Use when user asks about time."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
```

- 使用 LangChain `@tool` 装饰器将普通函数注册为工具
- 函数名即工具名，docstring 即工具描述（供 LLM 理解用途）
- 返回简单字符串

**`calc` 工具：**

```python
@tool
def calc(expr: str):
    """Calculate a math expression. Input: expression string like "2 + 3 * 4"."""
    try:
        result = eval(expr, {"__builtins__": {}}, {})
        return str(result)
    except Exception as e:
        return f"Error: {e}"
```

- 接受一个参数 `expr`，由 LLM 自动提取用户问题中的表达式
- 使用安全 `eval`（限制内置函数），防止代码注入
- 提供友好错误提示

#### 3.3.2 MCP 代理工具

**`get_now_weather` 工具：**

```python
@tool
def get_now_weather(location: str) -> dict:
    """Query real-time weather information for a specified location."""
    import asyncio
    from app.llm.mcp_tools import get_mcp_tools
    mcp_tools = get_mcp_tools()
    weather_tool = next((t for t in mcp_tools if t.name == "get_weather"), None)
    try:
        result = asyncio.run(weather_tool.ainvoke({"location": location}))
        return str(result)
    except Exception as e:
        return "未获取到天气数据"
```

这是项目中最具代表性的**桥接模式**工具：

1. **获取 MCP 工具列表**：通过 `get_mcp_tools()` 从 `MultiServerMCPClient` 获取已连接的远程工具
2. **按名称筛选**：从工具列表中筛选出 `get_weather` 工具
3. **异步转同步**：MCP 工具是异步的（`ainvoke`），通过新的事件循环包装为同步调用
4. **异常保护**：任何异常都返回友好的错误提示，不阻塞 Agent 的后续推理

**MCP 客户端适配器**（`app/llm/mcp_tools.py`）：

```python
def get_mcp_tools() -> List[Any]:
    global _tools, _initialized
    if not _initialized:
        _tools = _load_tools_sync()   # 连接 http://127.0.0.1:8000/mcp
        _initialized = True
    return _tools
```

- 使用 **单例模式**，工具列表只在首次加载时初始化
- 传输协议为 `streamable-http`，通过 HTTP 流式连接 FastMCP 服务端
- 异步工具通过 `_make_sync_tool()` 包装为同步 `StructuredTool`

#### 3.3.3 RAG 工具

**`rag_search` 工具：**

```python
@tool
def rag_search(query: str) -> str:
    """
    Search the love-and-relationship knowledge base.
    Use this when the user asks questions about dating, marriage, breakups,
    relationship advice, emotional issues, or similar topics.
    """
    return get_engine().query(query)
```

- 封装了整个 RAG 引擎（Chroma 向量检索 + BM25 关键词检索 + Cross-Encoder 重排序）
- Agent 将用户问题中的关键信息提取为 `query` 参数传入
- 返回格式化的知识库搜索结果，包含相关性评分

#### 3.3.4 Skills 中间件工具

**`list_skills` 工具：**

```python
@tool
def list_skills():
    """列出所有可用的技能模块名称和简介。"""
    # 遍历 _skills 字典，返回所有技能名称和描述
```

**`read_skill` 工具：**

```python
@tool
def read_skill(skill_name: str):
    """读取指定技能的完整内容，输入技能名称。"""
    # 根据技能名称返回对应 .md 文件的完整内容
```

- 由 `SkillsMiddleware` 类动态生成
- 工具描述和 docstring 使用中文，供 LLM 理解技能发现流程
- `read_skill` 返回的技能内容是完整的 Markdown 指令文档，Agent 按指令逐步执行

#### 3.3.5 工具注册与发现

工具通过两种方式注册到 Agent：

**方式一：基础 Agent（`agent.py` 中的 `make_agent`）**

```python
tools = [get_time, calc]
```

仅注册两个基础内置工具，适用于简单场景。

**方式二：增强 Agent（`skill_middleware.py` 中的 `create_agent`）**

```python
executor = create_agent(
    prompt,
    middleware=[_skill_middleware],
    extra_tools=[get_time, calc, get_now_weather, rag_search]
)
```

同时注册了：
- 基础工具：`get_time`, `calc`
- 代理工具：`get_now_weather`
- RAG 工具：`rag_search`
- Skills 工具：`list_skills`, `read_skill`（由 `_skill_middleware.get_tools()` 动态生成）

共 **6 个工具**，覆盖时间、计算、天气、知识检索、技能模板五大领域。

### 3.4 实现效果

- **工具选择准确率**：通过精细的 docstring 描述，LLM 能够根据用户问题准确匹配工具（如"现在几点"→`get_time`，"计算 23*45"→`calc`）
- **工具调用可见性**：Agent 的每一步工具调用都通过 `[STEP]` 事件实时显示在前端，用户可以清楚看到 AI 在做什么
- **异常传导**：工具执行失败不会导致 Agent 崩溃，而是返回错误信息供 LLM 重新推理或告知用户
- **即插即用**：新增工具只需定义 `@tool` 函数并传入 `extra_tools` 列表即可，无需修改 Agent 核心逻辑

---

## 四、三者关系与对比

### 4.1 架构关系图

```
用户输入
    │
    ├──→ Chain 模式（AI 恋爱大师）
    │      │
    │      └──→ ChatPromptTemplate → ChatOpenAI → StrOutputParser → 文本流
    │
    └──→ Agent 模式（AI 超级智能体）
           │
           ├──→ ReAct 循环：Thought → Action → Observation → Thought → ...
           │      │
           │      ├──→ 内置工具：get_time / calc
           │      ├──→ MCP 代理：get_now_weather
           │      ├──→ RAG 工具：rag_search
           │      └──→ Skills 工具：list_skills / read_skill
           │
           └──→ Final Answer
```

### 4.2 核心维度对比

| 维度 | Chain（链式调用） | Agent（智能体） | Tool Calling（工具调用） |
| :--- | :--- | :--- | :--- |
| **本质** | 单向数据管道 | 推理-行动循环 | Agent 的辅助能力 |
| **LLM 调用次数** | 1 次 | 1 ~ N 次（可多达 15 轮） | 每调用一次工具触发一次 LLM 调用 |
| **是否需要工具** | 不需要 | 需要（至少 1 个） | 工具本身是定义，不独立存在 |
| **输出方式** | 纯文本流 | 多阶段事件流（THINK/STEP/FINAL） | 工具执行结果，被 Agent 消费 |
| **响应速度** | 快（秒级出首 token） | 较慢（需工具调用 + 多次 LLM 调用） | 取决于具体工具（几毫秒到几秒） |
| **应用场景** | 情感对话、简单问答 | 复杂推理、多步骤任务 | 实时数据查询、精确计算、知识检索 |
| **所属服务** | AI 恋爱大师 | AI 超级智能体 | AI 超级智能体 |
| **API 端点** | `/api/ai/love_app/chat/sse` | `/api/ai/manus/chat` | 无独立端点，由 Agent 内部调度 |

### 4.3 选择依据

- **选 Chain**：当任务满足"一问一答、无需外部数据、内容为主"时（如情感建议、故事讲述、日常闲聊）
- **选 Agent**：当任务需要"实时数据、精确计算、知识检索、工具协作"时（如天气查询 + 出行建议、计算 + 时间 + 知识库联合查询）
- **关于 Tool Calling**：本质上是 Agent 的能力组成部分，不与 Chain / Agent 并列选择——**有工具，走 Agent；无工具，走 Chain**

---

## 五、总结

| 概念 | 一句话总结 |
| :--- | :--- |
| **Chain** | 最简的 Prompt→LLM→输出 流水线，适合轻量对话场景 |
| **Agent** | 基于 ReAct 范式的自主推理循环系统，能拆解复杂问题、调用工具、逐步求解 |
| **Tool Calling** | Agent 的「手和脚」，让 LLM 突破自身边界，获取实时数据、外部知识和精确计算能力 |

三者从简单到复杂构成了项目的 AI 交互能力谱系：**Chain 解决"怎么聊"，Agent 解决"怎么做"，Tool Calling 解决"用什么做"**。
