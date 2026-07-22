# MCP 模型上下文协议

> 本文档详细阐述 ZZX-AI 超级智能体中的 MCP（Model Context Protocol）实现——一种标准化的工具通信协议，使 AI 应用能够通过统一接口与外部服务交互。从概念、作用、实现思路、实现效果四个维度展开。

---

## 一、概念

### 1.1 什么是 MCP

MCP（Model Context Protocol，模型上下文协议）是由 Anthropic 提出的一种开放标准协议，旨在为 AI 模型（特别是 LLM）提供一种统一的方式来发现和调用外部工具与服务。类比于 USB 协议为计算机外设提供了标准化的即插即用接口，MCP 为 AI 应用提供了标准化的"工具即插即用"接口。

**核心思想：**

```
AI 应用（MCP 客户端）                    外部服务（MCP 服务端）
┌─────────────────────┐               ┌──────────────────────┐
│  Agent / LLM        │  tools/list   │  FastMCP Server      │
│                     │ ────────────→ │                      │
│  LangChain 适配层   │               │  get_weather 工具     │
│                     │  tools/call   │                      │
│  get_now_weather()  │ ────────────→ │  心知天气 API        │
│                     │               │                      │
└─────────────────────┘               └──────────────────────┘
      streamable-http 传输协议
```

### 1.2 为什么需要 MCP

| 问题 | 传统方案 | MCP 方案 |
| :--- | :--- | :--- |
| **工具接口不统一** | 每个外部服务需要单独编写适配代码 | 统一通过 tools/list 和 tools/call 标准方法交互 |
| **服务发现困难** | 工具列表硬编码在代码中 | 运行时可动态查询可用工具 |
| **异步调用复杂** | 需要手动管理事件循环和超时 | 框架层提供标准化的异步包装 |
| **跨语言通信** | 需要共享库或 SDK | 基于 HTTP 的标准化协议，语言无关 |

### 1.3 项目中的 MCP 双架构

本项目实现了 MCP 的两种传输方式：

| 传输方式 | 组件 | 用途 |
| :--- | :--- | :--- |
| **streamable-http** | `server.py` (FastMCP) + `mcp_tools.py` (客户端) | 生产环境的主要通信方式 |
| **stdio** | `mcp_helper.py` | 命令行交互和调试 |

---

## 二、作用

### 2.1 解决的问题

- **天气数据获取**：LLM 本身不具备实时天气查询能力，通过 MCP 调用心知天气 API
- **工具标准化**：任何遵循 MCP 协议的服务都可以无缝接入，无需修改 Agent 核心代码
- **运行时发现**：Agent 可以在运行时刻查询 MCP 服务端提供了哪些工具，而非硬编码
- **异步转同步**：MCP 原生基于异步，通过适配层包装为同步调用，兼容 LangChain 的同步 Agent 执行器

### 2.2 核心价值

| 价值 | 说明 |
| :--- | :--- |
| **即插即用** | 新增外部服务只需启动新的 MCP 服务端，修改客户端配置即可 |
| **协议标准化** | 统一通过 `tools/list` 发现工具、`tools/call` 调用工具 |
| **超时保护** | 每次工具调用有 30 秒超时控制，防止外部服务挂起 |
| **错误隔离** | MCP 服务端崩溃不影响 AI 应用主进程 |
| **生产就绪** | 使用 `streamable-http` 传输协议，支持流式响应 |

---

## 三、实现思路

### 3.1 系统架构

```
┌─────────────────────────────────────────────────────────┐
│  AI 应用（Flask + LangChain + Agent）                    │
│                                                         │
│  app/llm/agent.py                                       │
│    get_now_weather()  ← 桥接函数，内部调用 MCP 客户端     │
│                                                         │
│  app/llm/mcp_tools.py                                   │
│    MultiServerMCPClient → 连接 MCP 服务端                │
│    _make_sync_tool()   → 异步工具包装为同步工具           │
│    get_mcp_tools()     → 单例模式获取工具列表             │
│                                                         │
│  zzx_mcp_server/mcp_helper.py (备选 stdio 客户端)        │
│    ClientSession + stdio_client → JSON-RPC 交互          │
└──────────────────────┬──────────────────────────────────┘
                       │ streamable-http
                       │ http://127.0.0.1:8000/mcp
┌──────────────────────▼──────────────────────────────────┐
│  MCP 服务端                                              │
│                                                         │
│  zzx_mcp_server/server.py                               │
│    FastMCP("ZZX_MCP_SERVER")                            │
│    @mcp.tool() get_weather(location)                    │
│      → httpx → api.seniverse.com (心知天气 API)          │
│                                                         │
│  传输: streamable-http                                   │
│  监听: 127.0.0.1:8000/mcp                               │
└─────────────────────────────────────────────────────────┘
```

### 3.2 MCP 服务端

**文件位置**：`zzx_mcp_server/server.py`

#### 3.2.1 FastMCP 实例化

```python
from fastmcp import FastMCP

mcp = FastMCP("ZZX_MCP_SERVER")
```

- 使用 FastMCP 框架创建 MCP 服务端实例
- 服务端名称为 "ZZX_MCP_SERVER"

#### 3.2.2 工具定义：get_weather

```python
@mcp.tool()
async def get_weather(location: str) -> dict:
    """
    查询指定位置的实时天气信息
    Args:
        location: 所查询的位置，支持城市名（如"上海"）、
                  城市拼音（如"shanghai"）、
                  经纬度（如"31.23:121.47"）等
    Returns:
        包含实时天气信息的字典，包括温度、天气现象、更新时间等
    """
    logger.info(f"Weather query: {location}")
    url = "https://api.seniverse.com/v3/weather/now.json"
    params = {
        "key": "S6RhdAuuJQduDCSig",   # 心知天气 API Key
        "location": location,
        "language": "zh-Hans",
        "unit": "c",                   # 摄氏度
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    if data.get("results"):
        result = data["results"][0]
        location_info = result.get("location", {})
        now = result.get("now", {})
        return {
            "location": location_info.get("name", "未知"),
            "country": location_info.get("country", "未知"),
            "weather": now.get("text", "未知"),
            "temperature": now.get("temperature", "未知"),
            "last_update": result.get("last_update", "未知"),
            "raw": data,
        }
    return {"error": "未获取到天气数据", "raw": data}
```

**实现要点：**

| 方面 | 说明 |
| :--- | :--- |
| **框架** | FastMCP 的 `@mcp.tool()` 装饰器 |
| **名称** | 函数名 `get_weather` 作为工具名 |
| **描述** | 中文 docstring 供 LLM 理解和选择 |
| **参数** | `location: str`，支持多种格式 |
| **外部 API** | 心知天气 (seniverse.com) v3/weather/now.json |
| **HTTP 客户端** | httpx.AsyncClient（异步） |
| **超时** | 10 秒 |
| **返回格式** | 结构化的 dict（location/country/weather/temperature/last_update）|

#### 3.2.3 服务启动

```python
if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",   # 传输协议
        host="127.0.0.1",             # 仅本机可访问
        port=8000,                    # 端口
        path="/mcp",                  # 端点路径
    )
```

**配置参数：**

| 参数 | 值 | 说明 |
| :--- | :--- | :--- |
| `transport` | `"streamable-http"` | 基于 HTTP 的流式传输 |
| `host` | `127.0.0.1` | 仅监听本机，安全可控 |
| `port` | `8000` | 端口号 |
| `path` | `"/mcp"` | 端点路径，客户端需拼接为 `http://127.0.0.1:8000/mcp` |

### 3.3 MCP 客户端适配器

**文件位置**：`app/llm/mcp_tools.py`

这是连接 MCP 服务端和 LangChain Agent 的桥梁组件。

#### 3.3.1 单例模式加载

```python
_tools = None
_initialized = False

def get_mcp_tools() -> List[Any]:
    global _tools, _initialized
    if not _initialized:
        _tools = _load_tools_sync()
        _initialized = True
    return _tools
```

- 工具列表只在首次调用时加载
- 后续调用直接返回缓存列表
- 避免每次请求都重新建立 MCP 连接

#### 3.3.2 同步加载 MCP 工具

```python
def _load_tools_sync() -> List[Any]:
    client = MultiServerMCPClient({
        "weather_service": {
            "transport": "streamable_http",
            "url": "http://127.0.0.1:8000/mcp",
        }
    })
    async_tools = asyncio.run(client.get_tools())
    return [_make_sync_tool(t) for t in async_tools]
```

**配置结构：**

```json
{
    "weather_service": {
        "transport": "streamable_http",
        "url": "http://127.0.0.1:8000/mcp"
    }
}
```

- `weather_service`：服务实例名称（可配置多个 MCP 服务端）
- `transport`：传输协议，与服务端一致
- `url`：服务端端点地址

**工作流程：**

1. `MultiServerMCPClient` 通过 `streamable-http` 连接到服务端
2. 自动调用 `tools/list` 获取所有可用工具列表
3. 每个工具有 `name`、`description`、`args_schema` 等属性
4. 工具本身是异步的（返回 coroutine）

#### 3.3.3 异步工具包装为同步工具

```python
def _make_sync_tool(async_tool) -> StructuredTool:
    # 异步包装器
    async def async_wrapper(**kwargs):
        return await async_tool.ainvoke(kwargs)

    # 同步函数：在新事件循环中运行异步调用
    def sync_func(**kwargs):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                asyncio.wait_for(async_wrapper(**kwargs), timeout=30.0)
            )
        finally:
            loop.close()

    return StructuredTool(
        name=async_tool.name,
        description=async_tool.description,
        args_schema=async_tool.args_schema,
        func=sync_func,
        coroutine=async_wrapper,
    )
```

**包装逻辑：**

| 原属性 | 包装后 | 说明 |
| :--- | :--- | :--- |
| `name` | `StructuredTool.name` | 工具名称不变 |
| `description` | `StructuredTool.description` | 工具描述不变 |
| `args_schema` | `StructuredTool.args_schema` | 参数 schema 不变 |
| `ainvoke()` | `func` (同步) + `coroutine` (异步) | 通过新事件循环将异步转为同步 |

**超时控制：**

```python
asyncio.wait_for(async_wrapper(**kwargs), timeout=30.0)
```

- 每次工具调用最多等待 30 秒
- 超时后抛出 `asyncio.TimeoutError`，由调用方捕获处理

**事件循环管理：**

```python
loop = asyncio.new_event_loop()
try:
    return loop.run_until_complete(...)
finally:
    loop.close()
```

- 每次调用创建新的事件循环，避免与 Flask 主事件循环冲突
- 使用 `new_event_loop` 而非 `get_event_loop`，确保线程安全
- `finally` 保证循环总被关闭，防止资源泄漏

### 3.4 MCP Helper（备选 stdio 客户端）

**文件位置**：`zzx_mcp_server/mcp_helper.py`

这是一个基于 stdio 传输的 MCP 客户端，通过标准输入输出与 MCP 服务端通信。

#### 3.4.1 连接建立

```python
async def main():
    params = StdioServerParameters(
        command=sys.executable,      # 使用当前 Python 解释器
        args=[MCP_SERVER_SCRIPT],   # 启动 server.py
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            sys.stdout.buffer.write(b"READY\n")  # 就绪信号
            sys.stdout.buffer.flush()
```

- 使用 subprocess 启动 `server.py` 作为子进程
- 通过 stdio（stdin/stdout）进行 JSON-RPC 通信
- 就绪后输出 "READY\n" 信号

#### 3.4.2 JSON-RPC 消息循环

```python
while True:
    line_bytes = await loop.run_in_executor(None, sys.stdin.buffer.readline)
    if not line_bytes:
        break
    line = line_bytes.decode("utf-8").strip()
    if not line:
        continue

    cmd = json.loads(line)
    req_id = cmd.get("id")
    method = cmd.get("method")
    params = cmd.get("params", {})

    if method == "tools/list":
        result = await session.list_tools()
        # ... 格式化响应 ...
    elif method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        call_result = await session.call_tool(name, arguments)
        # ... 格式化响应 ...
```

**支持的 RPC 方法：**

| 方法 | 功能 | 实现 |
| :--- | :--- | :--- |
| `tools/list` | 列出所有可用工具 | `session.list_tools()` |
| `tools/call` | 调用指定工具 | `session.call_tool(name, arguments)` |

**响应格式：**

```json
{
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "tools": [
            {
                "name": "get_weather",
                "description": "查询指定位置的实时天气信息",
                "inputSchema": {}
            }
        ]
    }
}
```

### 3.5 Agent 集成

MCP 工具通过 `get_now_weather` 桥接函数集成到 Agent 中：

```python
# app/llm/agent.py
@tool
def get_now_weather(location: str) -> dict:
    """
    Query real-time weather information for a specified location.

    Args:
        location: The location to query, supports city name (e.g., "Shanghai"),
                  city pinyin (e.g., "shanghai"), or coordinates (e.g., "31.23:121.47").

    Returns:
        A string containing the real-time weather information...
    """
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

**桥接模式分析：**

| 步骤 | 代码 | 说明 |
| :--- | :--- | :--- |
| 1 | `get_mcp_tools()` | 获取 MCP 工具列表（单例） |
| 2 | `next(t for t in ... if t.name == "get_weather")` | 按名称筛选出天气工具 |
| 3 | `weather_tool.ainvoke(...)` | 调用 MCP 工具的异步方法 |
| 4 | `asyncio.run(...)` | 在新事件循环中执行异步调用 |
| 5 | `str(result)` | 将 dict 转为字符串供 Agent 使用 |
| 6 | `except Exception` | 异常时返回友好错误信息 |

### 3.6 完整的 MCP 调用链路

```
Agent 推理：用户想知道北京天气
  │
  ├── Agent 选择工具 get_now_weather("北京")
  │
  ├── get_now_weather（桥接函数）
  │     ├── get_mcp_tools()              → 获取 MCP 工具列表（单例）
  │     ├── 筛选出 get_weather 工具       → 从列表中匹配
  │     └── asyncio.run(weather_tool.ainvoke({"location": "北京"}))
  │
  ├── MCP 客户端（mcp_tools.py）
  │     ├── _make_sync_tool 包装的异步→同步适配器
  │     ├── 通过 streamable-http 发送 tools/call 请求
  │     └── 等待响应（30 秒超时）
  │
  ├── MCP 服务端（server.py）
  │     ├── FastMCP 接收 tools/call 请求
  │     ├── 执行 get_weather 函数
  │     ├── httpx 调用心知天气 API
  │     └── 返回结构化天气数据
  │
  ├── get_now_weather 返回天气字符串
  │
  └── Agent 生成最终答案："北京现在25℃，晴..."
        SSE 事件：
        [STEP] 工具: get_now_weather 结果: {"location": "北京", "weather": "晴", ...}
        [FINAL] 北京现在25℃，晴...
```

---

## 四、实现效果

### 4.1 核心指标

| 指标 | 表现 |
| :--- | :--- |
| **工具加载** | 首次调用时通过 `MultiServerMCPClient` 连接服务端，后续使用缓存（单例） |
| **调用延迟** | 天气查询约 0.5-2 秒（取决于心知天气 API 响应时间） |
| **超时控制** | 30 秒超时保护，防止外部服务挂起阻塞 Agent |
| **错误隔离** | MCP 服务端崩溃不导致 Agent 崩溃，返回友好错误提示 |
| **跨语言** | `streamable-http` 协议使任何语言的服务端都可接入 |

### 4.2 前端可见性

MCP 工具调用通过 SSE 事件在前端透明展示：

```
[STEP] 工具: get_now_weather 输入: 北京 结果: {"location": "北京", "weather": "晴", "temperature": "25"}
```

### 4.3 双客户端设计

项目中存在两个 MCP 客户端：

| 客户端 | 位置 | 传输 | 用途 | 状态 |
| :--- | :--- | :--- | :--- | :--- |
| **主客户端** | `app/llm/mcp_tools.py` | streamable-http | 生产环境 Agent 调用 | **实际使用** |
| **备选客户端** | `zzx_mcp_server/mcp_helper.py` | stdio | 调试和命令行交互 | 备用方案 |

---

## 五、MCP 的技术设计要点

### 5.1 异步转同步模式

MCP 工具本质上是异步的（`ainvoke`），但 LangChain 的 `AgentExecutor.stream()` 是同步的。项目通过两种方式解决这个矛盾：

**服务端适配（主）：**

```python
def sync_func(**kwargs):
    loop = asyncio.new_event_loop()     # 新事件循环
    try:
        return loop.run_until_complete(
            asyncio.wait_for(async_wrapper(**kwargs), timeout=30.0)
        )
    finally:
        loop.close()                    # 确保释放
```

**桥接函数适配（备）：**

```python
result = asyncio.run(weather_tool.ainvoke({"location": location}))
```

两种方式本质相同：在新事件循环中执行异步代码，等待结果后关闭循环。

### 5.2 单例缓存

```python
_tools = None
_initialized = False

def get_mcp_tools():
    global _tools, _initialized
    if not _initialized:
        _tools = _load_tools_sync()
        _initialized = True
    return _tools
```

- 工具列表只建立一次 MCP 连接
- 后续 Agent 调用直接使用缓存列表
- 避免了每次 Agent 推理都重新连接 MCP 服务端的高昂开销

### 5.3 错误传导设计

工具执行异常采取"友好错误 + 由 Agent 决定下一步"的策略：

```python
try:
    result = asyncio.run(weather_tool.ainvoke(...))
    return str(result)
except Exception as e:
    return "未获取到天气数据"     # ← 不抛异常，返回错误文本
```

当 MCP 服务端未启动或 API 不可用时，Agent 不会崩溃。Agent 会收到"未获取到天气数据"的文本，然后自行决定是重试还是告诉用户。

### 5.4 与直接 API 调用的对比

| 维度 | 直接调用心知天气 API | 通过 MCP 调用 |
| :--- | :--- | :--- |
| **代码耦合** | 天气 API 逻辑硬编码在 Agent 工具中 | 天气逻辑在独立 MCP 服务端中 |
| **可替换性** | 替换天气服务商需要修改 Agent 代码 | 替换天气服务商只需修改 MCP 服务端 |
| **协议标准** | 特定 API 的 HTTP 请求格式 | 统一 tools/list + tools/call 标准 |
| **服务发现** | 硬编码接口地址 | 运行时动态发现工具 |

---

## 六、总结

| 概念 | 一句话总结 |
| :--- | :--- |
| **MCP** | 为 AI 模型提供统一工具调用接口的开放标准协议，类似"AI 世界的 USB" |
| **MCP 服务端** | 基于 FastMCP，注册 get_weather 工具，通过 streamable-http 对外提供服务 |
| **MCP 客户端** | 基于 langchain-mcp-adapters，将异步 MCP 工具包装为同步 LangChain 工具 |
| **桥接函数** | `get_now_weather` 作为 MCP 工具和 Agent 之间的桥梁，封装了连接、调用、异常处理 |

MCP 的核心价值在于**工具标准化**——只要外部服务遵循 MCP 协议，Agent 就能无缝使用它。项目中以天气查询场景演示了从服务端注册、客户端适配到 Agent 调用的完整 MCP 实现链路。
