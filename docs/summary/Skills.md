# Skills 技能系统

> 本文档详细阐述 ZZX-AI 超级智能体中的 Skills 技能系统——一种基于渐进式暴露（Progressive Disclosure）的领域技能模板机制。从概念、作用、实现思路、实现效果四个维度展开，并深入分析浪漫时刻表白生成器这个内置技能的完整设计。

---

## 一、概念

### 1.1 什么是 Skills

Skills（技能系统）是本项目中一种独特的**运行时技能发现与加载机制**。它不是将领域特定的工作流指令硬编码在 Agent 的 Prompt 中，而是将指令以 Markdown 文档的形式存放在独立目录中，由 Agent 在运行时按需发现、加载和执行。

**核心思想：**

```
技能文档（.md 文件）                           Agent 运行时
┌──────────────────────┐                  ┌──────────────────────┐
│ name: xxx            │   list_skills    │                      │
│ description: xxx     │ ──────────────→  │  看到技能名称和简介   │
│                      │                  │                      │
│ ## 执行步骤          │   read_skill     │                      │
│ 1. 调用 get_time     │ ──────────────→  │  获取完整指令文档     │
│ 2. 生成告白文案      │                  │                      │
│ ...                  │                  │  按指令逐步执行       │
└──────────────────────┘                  └──────────────────────┘
```

### 1.2 渐进式暴露（Progressive Disclosure）

Skills 的设计核心是**渐进式暴露**——信息不是一次性全部暴露给 Agent，而是分层按需暴露：

```
第 1 层：名称层
    Agent 调用 list_skills
    → 获得技能名称和一行简介（如 "romantic_confession_generator: 生成时刻浪漫表白"）
    → 决定是否加载

第 2 层：指令层
    Agent 调用 read_skill("romantic_confession_generator")
    → 获得完整的 Markdown 指令文档
    → 理解执行步骤

第 3 层：执行层
    Agent 按指令逐段执行
    → 调用其他工具（如 get_time）
    → 按照格式要求生成输出
```

### 1.3 与硬编码指令的对比

| 维度 | 硬编码指令 | Skills 渐进式暴露 |
| :--- | :--- | :--- |
| **位置** | 写在 Agent Prompt 模板中 | 存放在独立的 .md 文件中 |
| **加载时机** | 每次调用都加载 | 按需加载（Agent 自主决策） |
| **上下文占用** | 总是占用 Prompt Token | 不使用时零占用 |
| **可扩展性** | 修改需改代码 | 新增 .md 文件即可 |
| **复杂度控制** | Prompt 越长，LLM 越难遵循 | 单篇技能文档聚焦一个任务 |

---

## 二、作用

### 2.1 解决的问题

| 问题 | 表现 | Skills 的解决方式 |
| :--- | :--- | :--- |
| **Prompt 膨胀** | 所有功能指令塞入一个 Prompt，导致 Token 浪费和注意力分散 | 指令分离到独立文件，按需加载 |
| **推理退化** | 过长的 Prompt 导致 LLM 在复杂任务上表现下降 | 每个技能聚焦一个任务，指令精简 |
| **扩展困难** | 新增功能需要修改 Agent 核心代码 | 只需在 skills 目录下新增 .md 文件 |
| **触发门槛** | 用户需要记住并输入特定的触发命令 | Agent 自动识别用户意图并触发技能 |

### 2.2 核心价值

- **Token 经济性**：技能指令不使用时零上下文占用
- **即插即用**：新增技能只需在 `skills/` 目录下添加 .md 文件，无需修改代码
- **可维护性**：技能文档独立于代码逻辑，非技术人员也可编写和修改
- **自动路由**：Agent 在用户意图匹配时自动执行技能，无需用户手动触发

---

## 三、实现思路

### 3.1 系统架构

```
skills/                          # 技能文档目录
├── romantic_confession_generator.md   # 浪漫表白生成器
├── ...其他技能文件.md

app/llm/skill_middleware.py       # Skills 中间件（核心）
├── class SkillsMiddleware        # 技能发现与加载引擎
├── def list_skills               # 工具：列出可用技能
├── def read_skill                # 工具：读取技能详情
└── def create_agent              # Agent 工厂（含 Skills 集成）

app/llm/agent.py                  # Agent 模板（Skills 路由指令）
├── AGENT_TEMPLATE                # 包含 Skills 自动路由规则

app/routes/manus.py               # 路由层（注入 Skills 中间件）
└── _skill_middleware = SkillsMiddleware(...)
```

### 3.2 SkillsMiddleware 类

**文件位置**：`app/llm/skill_middleware.py`

#### 3.2.1 初始化与技能发现

```python
class SkillsMiddleware:
    """Scans a directory for .md files and exposes them as progressive-disclosure skills."""

    def __init__(self, sources):
        self.sources = sources
        self._skills = {}  # name -> {"description": ..., "body": ...}
        self._discover()
```

**`_discover` 方法**：遍历所有来源目录，扫描其中的 `.md` 文件

```python
def _discover(self):
    for src in self.sources:
        skill_dir = _os.path.abspath(src)
        if not _os.path.isdir(skill_dir):
            continue
        for fname in sorted(_os.listdir(skill_dir)):
            if fname.endswith(".md"):
                self._load(fname, skill_dir)
```

#### 3.2.2 Front Matter 解析

每个技能文件的开头包含 YAML Front Matter 元数据：

```markdown
---
name: romantic_confession_generator
description: Trigger this skill by entering the command "[时刻浪漫表白]"...
---
```

`_load` 方法负责解析这些元数据：

```python
def _load(self, fname, skill_dir):
    filepath = _os.path.join(skill_dir, fname)
    with open(filepath, "r", encoding="utf-8") as f:
        raw = f.read()

    name = fname[:-3]  # 默认：文件名去掉 .md
    description = ""
    body = raw          # 默认：整个文件内容

    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            fm = parts[1].strip()
            body = parts[2].strip()
            for line in fm.split("\n"):
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("description:"):
                    description = line.split(":", 1)[1].strip()

    self._skills[name] = {"description": description, "body": body}
```

**解析逻辑：**

| 字段 | 默认值 | 来源 |
| :--- | :--- | :--- |
| `name` | 文件名去掉 `.md` | Front Matter 中的 `name:` 可覆盖 |
| `description` | 空字符串 | Front Matter 中的 `description:` |
| `body` | 全文 | Front Matter 之后的内容（第二个 `---` 之后的正文） |

#### 3.2.3 工具生成

`get_tools` 方法动态生成两个 LangChain 工具：

**`list_skills` 工具：**

```python
@tool
def list_skills():
    """列出所有可用的技能模块名称和简介。"""
    if not skills_ref:
        return "当前没有可用的技能模块。"
    result = ["可用的技能模块："]
    for name, info in skills_ref.items():
        desc = info.get("description", "暂无描述")
        result.append(f"  - {name}: {desc}")
    return "\n".join(result)
```

- **docstring** 使用中文描述，与 Skills 文档语言一致
- 遍历 `_skills` 字典，返回所有注册的技能名称和描述
- 空技能列表时友好提示

**`read_skill` 工具：**

```python
@tool
def read_skill(skill_name: str):
    """读取指定技能的完整内容，输入技能名称。"""
    if skill_name in skills_ref:
        return skills_ref[skill_name]["body"]
    available = ", ".join(skills_ref.keys())
    return f"技能"{skill_name}"不存在。可用的技能: {available}"
```

- 接受一个参数 `skill_name`
- 找到时返回完整的 Markdown 正文（body）
- 未找到时列出所有可用技能作为引导

#### 3.2.4 闭包捕获技巧

注意 `get_tools` 方法中使用了一个关键技巧：

```python
def get_tools(self):
    skills_ref = self._skills   # ← 在闭包中捕获 _skills 引用

    @tool
    def list_skills():
        ... skills_ref ...      # ← 在嵌套函数中访问捕获的变量

    @tool
    def read_skill(skill_name: str):
        ... skills_ref ...
```

因为在 `@tool` 装饰器执行时，函数即被注册为工具。如果直接引用 `self._skills`，Python 的闭包规则会导致运行时错误（`self` 在装饰器上下文中不可用）。通过预先将 `self._skills` 赋值给局部变量 `skills_ref`，再在嵌套函数中引用该局部变量，绕过了闭包限制。

### 3.3 Agent 集成

#### 3.3.1 增强版 Agent 工厂

```python
# app/llm/skill_middleware.py
def create_agent(system_prompt, middleware=None, extra_tools=None):
    tools = list(extra_tools or [])

    if middleware:
        for m in middleware:
            if hasattr(m, "get_tools"):
                tools.extend(m.get_tools())   # ← 将 Skills 工具注入到 Agent

    prompt = PromptTemplate.from_template(AGENT_TEMPLATE).partial(system_prompt=system_prompt)
    agent = _create_react(llm, tools, prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=False,
        handle_parsing_errors=True,
        max_iterations=15,
        early_stopping_method="generate",
        max_execution_time=90,
    )
```

- 通过 `middleware` 参数接收 `SkillsMiddleware` 实例列表
- 调用 `m.get_tools()` 将 `list_skills` 和 `read_skill` 注入到 Agent 的工具列表
- 与 `extra_tools`（如 `get_time`、`calc` 等）合并为 Agent 的完整工具集

#### 3.3.2 路由层注入

```python
# app/routes/manus.py
_skill_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..", "skills")
_skill_middleware = SkillsMiddleware(sources=[_skill_dir])

@manus_bp.route("/api/ai/manus/chat")
def chat():
    # ... 构建 prompt ...
    executor = create_agent(
        prompt,
        middleware=[_skill_middleware],         # ← 注入 Skills 中间件
        extra_tools=[get_time, calc, get_now_weather, rag_search]
    )
    return sse_response(stream_agent, executor, message, session_id, llm)
```

- `_skill_middleware` 在模块加载时实例化为单例
- 技能目录路径相对于路由文件定位（`__file__` → `../../skills/`）

### 3.4 Agent 模板中的 Skills 路由指令

**文件位置**：`app/llm/agent.py` 的 `AGENT_TEMPLATE`

Agent 模板中包含完整的 Skills 路由指令，指导 Agent 何时以及如何使用技能：

```text
You have access to a set of advanced "Skills" — these are specialized, multi-step workflows
for handling specific domain tasks (e.g., romantic confession generation, conflict resolution,
trust repair).

Your available skill-related tools are:
- `list_skills` — lists all available skills and their brief descriptions.
- `read_skill` — retrieves the full instruction body of a specific skill by its name.
```

**CRITICAL ROUTING RULE（自动路由规则）：**

```text
CRITICAL ROUTING RULE — HOW TO USE SKILLS AUTOMATICALLY:
When a user's request falls into any of the following categories, DO NOT respond with a
generic answer or force the user to type an explicit trigger command. Instead, you MUST
proactively consider using a skill:
1. The request is vague, complex, or creative in nature, and the user does not specify
   a concrete tool or format.
```

**自动决策流程：**

```text
Your decision flow:
Step A — Identify the domain. If it matches the above, call `list_skills` to check
         if a relevant skill exists.
Step B — If a matching skill is found (e.g., "romantic_confession_generator"),
         call `read_skill` with its exact name to load its full instructions.
Step C — Execute the skill's body step by step. This may include calling other base
         tools (like `get_time`) as required by the skill.
Step D — Produce the final output strictly according to the skill's format and
         length requirements.

IMPORTANT — You DO NOT need the user to repeat any special command like "[时刻浪漫表白]".
Once the skill is loaded, act as if it is already activated, and follow its internal
workflow precisely. This makes the experience seamless for the user.
```

**指令设计要点：**

| 设计 | 说明 |
| :--- | :--- |
| **概念先定义** | 先解释"What is Skills"，再说明如何使用 |
| **场景描述** | 明确何时应该使用 Skills（vague, complex, creative） |
| **否定约束** | "DO NOT respond with a generic answer" 防止 Agent 绕过技能 |
| **四步流程** | Step A → B → C → D 将模糊的判断转化为可执行的伪代码 |
| **IMPORTANT 强调** | 大写关键字强调"不需要用户触发"，确保体验无缝 |
| **参数量控制** | Skills 指令本身只占用 Agent 模板中约 30 行的空间 |

### 3.5 内置技能：浪漫时刻表白生成器

**文件位置**：`skills/romantic_confession_generator.md`

这是项目中唯一内置的 Skills 模板，是一个**多步骤的创意文案生成工作流**。

#### 3.5.1 Front Matter

```yaml
---
name: romantic_confession_generator
description: Trigger this skill by entering the command "[时刻浪漫表白]"...
---
```

- **name**: 技能名称，Agent 通过 `read_skill("romantic_confession_generator")` 加载
- **description**: 技能描述，Agent 通过 `list_skills` 查看

#### 3.5.2 五段式正文结构

**第 1 节：获取时间的诗意坐标**

```markdown
### 1. Obtaining the Poetic Coordinates of Time

First, **you must call the `get_time` tool** to obtain the following precise information:
- Current date (year, month, day)
- Current time (hour, minute)

These data are not cold numbers; they are the core material that gives the confession
its uniqueness. Our goal is: **This confession can only be spoken at this exact moment—
not one second earlier, not one second later.**
```

- 明确要求调用特定工具（`get_time`）
- 通过诗意化的语言解释数据的意义，引导 LLM 超越机械化使用

**第 2 节：时间意象的情感映射**

```markdown
| Time Slot | Poetic Transformation (Example) |
| :--- | :--- |
| **Early morning (5:00-9:00)** | The first light of dawn... |
| **Midday (11:00-14:00)**     | The blazing sun...        |
| **Dusk (17:00-19:00)**       | The gradual shift of sunset... |
| **Late night (22:00-5:00)**  | The coolness of moonlight... |
```

- 用表格将时间段映射到情感意象
- 这种结构化映射在传统编程中是枚举 switch，在 Prompt 中是"参考表"

**第 3 节：四段式告白结构**

```markdown
- **Paragraph 1 (Opening · Freezing the Moment):**
  Directly state the current exact time and scene, creating a strong sense of presence.
- **Paragraph 2 (Immersion · Natural Association):**
  Cleverly project your observations of the current time onto your feelings for the other person.
- **Paragraph 3 (Climax · Core Confession):**
  Clearly say "I love you" or "I like you," and give it a time-based uniqueness.
- **Paragraph 4 (Hope · Future Invitation):**
  Gently extend an action invitation or future commitment.
```

- 将创意写作分解为 4 个可执行的步骤
- 每段都有明确的"目的说明"，不止是结构描述

**第 4 节：示例输出**

提供了约 200 字的完整中文范文（基于假设时间 2026年7月16日 14:35），作为少样本（Few-shot）参考：

```
现在是2026年7月16日，周四，午后两点三十五分。
外面的蝉鸣快把空气煮沸了...
我喜欢你。不是春风秋雨的温柔试探，是此刻这盛夏正午般的坦诚与笃定。
所以，要不要和我一起，去浪费这个夏天？就从今天开始。
```

**第 5 节：微调建议**

```markdown
- **Avoid clichés:** 必须使用 get_time 返回的真实数据
- **Pronoun adjustment:** 可替换为对方的昵称
- **Length control:** 严格保持 180-220 字
- **Consistent style:** 保持"深情、细腻、略带文艺"的基调
- **Alternative for late night:** 00:00-04:00 时调整语气为内敛克制
- **Language requirement:** MUST be Simplified Chinese
```

#### 3.5.3 技能执行流程

```
用户说："帮我想一段表白的话"
  │
  ├── Agent 识别 → "vague, complex, creative" → 匹配 Skills
  │
  ├── Step A: Agent 调用 list_skills
  │     → 看到 "romantic_confession_generator"
  │
  ├── Step B: Agent 调用 read_skill("romantic_confession_generator")
  │     → 获取完整的 Markdown 指令
  │
  ├── Step C: Agent 按指令执行
  │     ├── 调用 get_time → 获取当前精确时间
  │     ├── 根据时间匹配情感意象（如 Midday → 盛夏正午）
  │     ├── 按四段式结构生成告白文案
  │     └── 控制字数在 180-220 字
  │
  └── Step D: Agent 输出最终答案
        → 约 200 字的中文告白文案
```

### 3.6 完整的 Skills 工作流

```
用户发送消息
  │
  ├── Agent 加载 Prompt（含 Skills 路由指令）
  │
  ├── Agent 进行意图识别
  │     ├── 普通问答 → 直接使用 LLM 生成回答
  │     └── 模糊/复杂/创意类 → 进入 Skills 流程
  │
  ├── Skills 流程
  │     ├── [THINK] 用户请求属于创意类，考虑使用技能
  │     ├── [STEP] 工具: list_skills 结果: romantic_confession_generator...
  │     ├── [STEP] 工具: read_skill 结果: (完整指令文档)
  │     ├── [STEP] 工具: get_time 结果: 2026-07-22 14:35
  │     └── [FINAL] (生成的告白文案)
  │
  └── 前端渲染 SSE 事件
        ├── [THINK] 用户请求属于创意类...
        ├── [STEP] 工具: list_skills...
        ├── [STEP] 工具: read_skill...
        ├── [STEP] 工具: get_time...
        └── [FINAL] 现在是2026年7月22日...
```

---

## 四、实现效果

### 4.1 核心指标

| 指标 | 表现 |
| :--- | :--- |
| **技能发现成功率** | Agent 能够在接收到模糊创意类请求时主动调用 `list_skills` |
| **技能加载准确率** | Agent 能正确使用技能名称调用 `read_skill` |
| **指令遵循度** | Agent 能按技能文档中的步骤逐步执行（调用 `get_time`、按四段式结构输出） |
| **零代码扩展** | 新增技能只需在 `skills/` 目录下添加 `.md` 文件，无需修改 Python 代码 |
| **上下文零占用** | 技能指令不使用时完全不占用 Agent Prompt 的 Token 预算 |

### 4.2 前端可见性

Skills 的执行过程通过 SSE 事件在前端完整可见：

```
[THINK] 用户想让我帮忙写一段表白文案，这属于创意类请求
[STEP] 工具: list_skills 输入: (无参数) 结果: romantic_confession_generator...
[STEP] 工具: read_skill 输入: romantic_confession_generator 结果: (完整指令)
[STEP] 工具: get_time 输入: (无参数) 结果: 2026-07-22 14:35
[FINAL] 现在是2026年7月22日，午后两点三十五分。窗外的蝉鸣...
```

这种透明性增强了用户对 AI 行为的理解和信任。

### 4.3 适用场景

| 场景 | 是否匹配 Skills | 说明 |
| :--- | :--- | :--- |
| "帮我算一下 23*45" | 否 | 明确、具体，直接调用 calc 工具 |
| "北京今天天气怎么样" | 否 | 明确、具体，直接调用 get_now_weather |
| "帮我写一段表白的话" | 是 | 模糊、创意类，需要多步骤工作流 |
| "我女朋友生气了怎么办" | 否 | 情感咨询，通过 RAG 搜索知识库 |
| "给我一个惊喜的约会方案" | 是 | 模糊、创意类，适合 Skills 模板 |

---

## 五、Skills 的 Prompt 工程特点

### 5.1 传统 Prompt vs Skills 指令

| 维度 | 传统 Prompt | Skills 指令（.md 文件） |
| :--- | :--- | :--- |
| **语言** | 通常为英文（与 LLM 训练语料一致） | 英文指令 + 中文输出要求 |
| **结构** | 纯文本说明 | Markdown 结构化（标题、表格、列表、代码块） |
| **长度** | 简短（几行到几十行） | 完整详细（可达数百行） |
| **目标受众** | LLM 本身 | LLM 作为"执行者"阅读并执行 |
| **示例** | 可选 | 必备（少样本引导输出风格） |
| **约束** | 隐式约束为主 | 显式约束列表 |

### 5.2 设计技巧总结

| # | 技巧 | 在 Skills 中的应用 |
| :--- | :--- | :--- |
| 1 | **渐进式暴露** | 三层信息暴露（名称 → 指令 → 执行） |
| 2 | **概念前导** | 先定义 Skills 是什么，再说明如何使用 |
| 3 | **决策流程化** | Step A → B → C → D 伪代码 |
| 4 | **否定指令** | "DO NOT respond with a generic answer" |
| 5 | **大写强调** | CRITICAL、IMPORTANT、MUST |
| 6 | **结构化文档** | Markdown 标题、表格、列表 |
| 7 | **少样本示例** | 完整的告白范文 |
| 8 | **长度约束** | "180-220 字" |
| 9 | **语言约束** | "MUST be Simplified Chinese" |
| 10 | **兜底处理** | "技能不存在"时列出可用技能 |
| 11 | **闭包捕获** | `skills_ref = self._skills` 绕过闭包限制 |
| 12 | **单例模式** | SkillsMiddleware 在路由层实例化为单例 |

---

## 六、总结

| 概念 | 一句话总结 |
| :--- | :--- |
| **Skills 技能系统** | 基于渐进式暴露的运行时技能发现与加载机制，将领域工作流以 Markdown 文档形式独立存储，由 Agent 按需加载执行 |
| **渐进式暴露** | 三层信息暴露（名称 → 指令 → 执行），避免 Prompt 膨胀，实现零上下文占用 |
| **浪漫表白生成器** | 首个内置技能，通过 get_time + 时间意象映射 + 四段式结构，生成时刻独特的告白文案 |

Skills 的核心价值在于**将"教 AI 做什么"从代码中分离出来，变成 AI 自己可以阅读和执行的文档**。这种设计使得：
- 新增技能不需要改代码
- 技能文档可以由非技术人员编写
- AI 可以自主决定何时使用什么技能
- 技能指令在不使用时完全不占用上下文空间
