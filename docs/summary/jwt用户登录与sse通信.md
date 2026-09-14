# JWT 用户登录与 SSE 通信

> 本文档详细阐述 ZZX-AI 超级智能体中的用户认证体系与实时通信机制：JWT（JSON Web Token）用户登录认证和 SSE（Server-Sent Events）服务端事件流通信。分别从概念、作用、实现思路、实现效果四个维度展开，并在最后分析两者的协作关系。

---

## 一、JWT 用户登录

### 1.1 概念

JWT（JSON Web Token）是一种基于 JSON 的开放标准（RFC 7519），用于在各方之间安全地传输信息。在本项目中，JWT 作为**用户身份认证**的核心机制，采用 HS256（HMAC with SHA-256）签名算法，服务端签发 Token，客户端持 Token 访问受保护的 API 资源。

**Token 结构：**

```
Header:    { "alg": "HS256", "typ": "JWT" }
Payload:   { "user_id": 1, "username": "zzx", "exp": 1700000000 }
Signature: HMAC-SHA256(base64UrlEncode(header) + "." + base64UrlEncode(payload), secret)
```

**认证流程：**

```
注册/登录 → 服务端验证 → 签发 JWT Token → 客户端存储 → 每次请求携带 → 服务端验证
```

### 1.2 作用

JWT 用户登录体系在项目中承担以下职责：

- **用户身份认证**：确保只有注册用户才能访问对话服务与会话管理 API
- **无状态鉴权**：服务端无需存储 session，Token 自身包含完整的用户身份信息
- **跨端兼容**：Token 可同时在 Web 前端和未来可能的移动端使用
- **安全防护**：密码经过 Werkzeug 哈希存储，Token 通过 Bearer 方案传输

### 1.3 实现思路

#### 1.3.1 配置层

JWT 密钥和数据库连接信息通过环境变量注入，并在 `app/config.py` 中集中读取：

```python
# app/config.py
class BaseConfig:
    MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("MYSQL_USER", "")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DB = os.getenv("MYSQL_DB", "zzx_agent_db")
    JWT_SECRET = os.getenv("JWT_SECRET", "")
```

**参数说明：**

| 参数 | 值 | 说明 |
| :--- | :--- | :--- |
| `JWT_SECRET` | 由环境变量提供 | Token 签名密钥，必须使用随机高强度值 |
| Token 有效期 | 7 天（86400 × 7 秒） | 在 `make_token` 中通过 `exp` 字段设定 |
| 签名算法 | HS256 | PyJWT 库支持的对称签名算法 |

#### 1.3.2 数据库模型

用户信息存储在 MySQL `users` 表中：

```sql
CREATE TABLE IF NOT EXISTS users (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    username   VARCHAR(50)  NOT NULL UNIQUE,
    nickname   VARCHAR(50)  NOT NULL,
    password   VARCHAR(255) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
```

- `username`：唯一索引，用作登录凭证
- `nickname`：显示昵称
- `password`：Werkzeug 哈希密文，非明文

#### 1.3.3 核心工具函数

**获取数据库连接：**

```python
# app/auth.py
def get_db():
    cfg = current_app.config
    return pymysql.connect(
        host=cfg.get("MYSQL_HOST", "127.0.0.1"),
        port=cfg.get("MYSQL_PORT", 3306),
        user=cfg["MYSQL_USER"],
        password=cfg["MYSQL_PASSWORD"],
        database=cfg.get("MYSQL_DB", "zzx_agent_db"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
```

- 使用 `pymysql` 直连 MySQL，返回字典游标方便访问字段名
- 配置从 Flask `current_app.config` 中读取，与环境变量兼容

**签发 Token：**

```python
# app/auth.py
def make_token(user_id, username):
    import jwt as pyjwt
    secret = current_app.config["JWT_SECRET"]
    payload = {
        "user_id":  user_id,
        "username": username,
        "exp":      int(time.time()) + 86400 * 7,  # 7 days
    }
    return pyjwt.encode(payload, secret, algorithm="HS256")
```

- Payload 包含 `user_id`、`username` 和 `exp`（过期时间）
- 使用 HS256 算法签名
- 过期时间设为 7 天，平衡安全性与用户体验

**验证 Token：**

```python
# app/auth.py
def decode_token(token):
    import jwt as pyjwt
    secret = current_app.config["JWT_SECRET"]
    try:
        return pyjwt.decode(token, secret, algorithms=["HS256"])
    except Exception:
        return None
```

- 解码失败（过期、签名错误、格式非法）时返回 `None`
- 使用 `try/except` 兜底所有异常类型

#### 1.3.4 认证装饰器

`@login_required` 装饰器保护需要登录的 API 路由：

```python
# app/auth.py
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"code": 401, "msg": "未登录或 Token 已过期"}), 401
        token = auth[7:]
        payload = decode_token(token)
        if payload is None:
            return jsonify({"code": 401, "msg": "Token 无效或已过期"}), 401
        request.current_user = payload
        return f(*args, **kwargs)
    return decorated
```

**验证流程：**

1. 从 `Authorization` 请求头提取 Bearer Token
2. 检查是否以 `"Bearer "` 开头，否则直接返回 401
3. 截取 Token 部分（去掉 "Bearer " 前缀）
4. 调用 `decode_token` 解码，失败则返回 401
5. 解码成功则将用户信息注入 `request.current_user`
6. 执行被装饰的路由函数

#### 1.3.5 API 接口

**注册接口 `POST /api/auth/register`：**

```python
@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    nickname = (data.get("nickname") or "").strip()
    password = (data.get("password") or "").strip()
```

**输入校验规则：**

| 字段 | 规则 |
| :--- | :--- |
| username | 必填，3-50 个字符，唯一 |
| nickname | 必填，不可为空 |
| password | 必填，至少 6 位 |

**业务逻辑：**

1. 校验输入参数
2. 检查用户名是否已注册（`SELECT id FROM users WHERE username=%s`）
3. 对密码进行 Werkzeug 哈希：`generate_password_hash(password)`
4. 插入用户记录
5. 返回成功响应

**登录接口 `POST /api/auth/login`：**

```python
@auth_bp.route("/login", methods=["POST"])
def login():
    # 查询用户
    cur.execute("SELECT id, username, nickname, password FROM users WHERE username=%s", (username,))
    row = cur.fetchone()
    # 验证密码
    if row is None or not check_password_hash(row["password"], password):
        return jsonify({"code": 401, "msg": "账号或密码错误"}), 401
    # 签发 Token
    token = make_token(row["id"], row["username"])
```

**登录响应格式：**

```json
{
    "code": 0,
    "msg": "登录成功",
    "data": {
        "token": "eyJhbGciOiJIUzI1NiIs...",
        "user_id": 1,
        "username": "zzx",
        "nickname": "ZZX"
    }
}
```

- `token`：JWT Token 字符串
- `user_id`：用户数字 ID
- `username`：登录用户名
- `nickname`：显示昵称

**其他接口：**

| 接口 | 方法 | 认证 | 说明 |
| :--- | :--- | :--- | :--- |
| `/api/auth/verify` | GET | @login_required | 验证 Token 有效性 |
| `/api/auth/userinfo` | GET | @login_required | 获取当前用户完整信息 |

#### 1.3.6 前端集成

**API 请求层**（`src/api/index.js`）：

```javascript
// Axios 请求拦截器 - 自动附加 Bearer Token
request.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = 'Bearer ' + token
  }
  return config
})
```

- 每次请求前从 `localStorage` 读取 token
- 自动附加到 HTTP Header 的 `Authorization` 字段
- 对 SSE 连接无效（SSE 的 EventSource 不支持自定义请求头）

**路由守卫**（`src/router/index.js`）：

```javascript
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  if (!publicRoutes.includes(to.name)) {
    if (!token) {
      return next({ name: 'Login', query: { redirect: to.fullPath } })
    }
  } else {
    if (token) {
      return next({ name: 'Home' })
    }
  }
  next()
})
```

**守卫逻辑：**

| 当前状态 | 目标路由 | 行为 |
| :--- | :--- | :--- |
| 未登录 | 公开页面（Login/Register） | 正常访问 |
| 未登录 | 受保护页面 | 跳转到 Login，附带 redirect 参数 |
| 已登录 | 公开页面（Login/Register） | 跳转到 Home |
| 已登录 | 受保护页面 | 正常访问 |

**退出登录：**

```javascript
// src/views/Home.vue
function handleLogout() {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  router.push('/login')
}
```

- 清除 `localStorage` 中的 token 和用户信息
- 跳转到登录页
- 路由守卫自动拦截后续对受保护页面的访问

### 1.4 实现效果

- **注册/登录流程完整闭环**：从用户注册、密码哈希存储、Token 签发、前端持久化到 API 鉴权，形成完整的认证链路
- **双重安全机制**：密码通过 Werkzeug 的 `generate_password_hash`（基于 pbkdf2:sha256）存储，Token 通过 HS256 签名防篡改
- **无状态扩展性**：后端不做 session 存储，Token 自包含用户身份信息，方便横向扩展
- **路由级保护**：前端路由守卫 + 后端 @login_required 装饰器双重保护
- **友好的用户体验**：登录成功后自动跳回原始页面（redirect 参数），退出登录无需确认

---

## 二、SSE 通信

### 2.1 概念

SSE（Server-Sent Events）是一种基于 HTTP 的**服务端推送**技术，允许服务端通过单一的 HTTP 长连接持续向客户端发送数据。与 WebSocket 不同，SSE 是**单向**的（仅服务端 → 客户端），但天然基于 HTTP 协议，无需额外的握手开销。

**协议格式：**

```
data: [THINKING]\n\n
data: 当前温度25℃\n
data: 适合户外活动\n\n
data: [DONE]\n\n
```

每条消息以 `data:` 开头，以 `\n\n` 结尾，可以跨多行。

### 2.2 作用

SSE 通信在项目中承担以下职责：

- **实时流式输出**：LLM 的 Token 级输出实时推送到前端，用户无需等待完整回答即可阅读中间结果
- **Agent 过程透明**：Agent 的思考过程（`[THINK]`）、工具调用步骤（`[STEP]`）和最终答案（`[FINAL]`）分阶段推送
- **心跳保活**：连接建立后立即发送 `[THINKING]` 心跳信号，防止前端因未收到数据而超时关闭连接
- **前后端分离通信**：Flask 后端通过 SSE StreamingResponse 输出，Vue 前端通过原生 EventSource 接收，不依赖 WebSocket 等额外库

### 2.3 实现思路

#### 2.3.1 后端 SSE 工具函数

**`sse_response` 函数**（`app/utils/sse.py`）：

```python
def sse_response(generator_fn, *args):
    """
    Convert a streaming generator into a Flask SSE StreamingResponse.
    """
    def generate():
        try:
            # Immediate heartbeat → prevents frontend timeout
            yield "data: [THINKING]\n\n"
            for chunk in generator_fn(*args):
                # SSE: multi-line data needs multiple "data:" lines
                for line in chunk.split("\n"):
                    yield f"data: {line}\n"
                yield "\n"
        except Exception as e:
            yield f"data: Error: {e}\n\n"
        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

**实现逻辑：**

| 阶段 | 输出 | 作用 |
| :--- | :--- | :--- |
| 连接建立 | `data: [THINKING]\n\n` | 心跳信号，防止前端 EventSource 超时重连 |
| 流式数据 | `data: {chunk}`（逐行拆分） | 将生成器产生的每块文本按换行符拆分为多条 SSE 消息 |
| 异常处理 | `data: Error: {e}\n\n` | 捕获生成器内的异常并推送 |
| 流结束 | `data: [DONE]\n\n` | 通知前端关闭连接 |

**响应头说明：**

| 头字段 | 值 | 作用 |
| :--- | :--- | :--- |
| `Content-Type` | text/event-stream | SSE 标准 MIME 类型 |
| `Cache-Control` | no-cache | 禁止代理和浏览器缓存 |
| `Connection` | keep-alive | 保持长连接 |
| `X-Accel-Buffering` | no | 禁用 Nginx 等反向代理的缓冲，确保实时性 |

#### 2.3.2 Agent 模式流的 SSE 事件

在 **AI 超级智能体**（Agent 模式）中，`stream_agent` 产生三类事件：

| SSE 前缀 | 触发时机 | 示例 |
| :--- | :--- | :--- |
| `[THINK]` | Agent 每次推理时，提取 Thought 内容 | `data: [THINK] 用户想知道当前时间` |
| `[STEP]` | 工具调用完成后，包含工具名和结果 | `data: [STEP] 工具: get_time 结果: 2026-07-22 10:00` |
| `[FINAL]` | Agent 输出最终答案 | `data: [FINAL] 当前北京时间是......` |

**具体实现**（`app/llm/agent.py` 中的 `stream_agent`）：

```python
for step in executor.stream({"input": message}):
    actions = step.get("actions", [])
    steps = step.get("steps", [])
    for action in actions:
        if getattr(action, "tool", None):
            thought_text = extract_thought(action.log) if hasattr(action, 'log') else ""
            if thought_text:
                yield f"[THINK] 思考: {thought_text}"  # 思考过程
                print(f"  |- Thought: {thought_text}")
            yield f"[STEP] 工具: {action.tool}"          # 工具调用
    for s in steps:
        obs = s.observation.strip() if s.observation else ""
        if obs and "Invalid Format" not in obs and "Could not parse" not in obs:
            yield f"[STEP] 工具: {tool_name} 结果: {obs[:300]}"  # 工具结果
    if "output" in step:
        answer = step["output"]
        yield f"[FINAL] {answer}"                       # 最终答案
```

#### 2.3.3 Chain 模式流的 SSE 事件

在 **AI 恋爱大师**（Chain 模式）中，`stream_chain` 的事件更加简单：

```python
for chunk in chain.stream(invoke_input):
    if chunk:
        yield chunk  # 直接输出 Token 块
```

Chain 模式的 SSE 没有 `[THINK]` / `[STEP]` / `[FINAL]` 前缀，因为 Chain 不需要工具调用，直接输出 LLM 生成的文本流。

#### 2.3.4 路由集成

**Agent 路由：**

```python
# app/routes/manus.py
@manus_bp.route("/api/ai/manus/chat")
def chat():
    executor = create_agent(prompt, middleware=[...], extra_tools=[...])
    return sse_response(stream_agent, executor, message, session_id, llm)
```

**Chain 路由：**

```python
# app/routes/love_app.py
@love_bp.route("/api/ai/love_app/chat/sse")
def chat():
    chain = make_chain(SYSTEM_PROMPT, context)
    return sse_response(stream_chain, chain, message, context, session_id, llm)
```

**CORS 支持：**

```python
# app/__init__.py
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response
```

SSE 连接在 fetch/EventSource 层面受 CORS 限制，服务端通过全局 `after_request` 中间件开放跨域访问。

#### 2.3.5 前端 SSE 客户端

**通用 SSE 连接函数**（`src/api/index.js`）：

```javascript
export const connectSSE = (url, params, onMessage, onError) => {
  // 构建查询字符串
  const queryString = Object.keys(params)
    .map(key => encodeURIComponent(key) + '=' + encodeURIComponent(params[key]))
    .join('&')

  const fullUrl = API_BASE_URL + url + '?' + queryString

  const eventSource = new EventSource(fullUrl)

  eventSource.onmessage = event => {
    let data = event.data
    if (data === '[DONE]') {
      if (onMessage) onMessage('[DONE]')
    } else {
      if (onMessage) onMessage(data)
    }
  }

  eventSource.onerror = error => {
    if (onError) onError(error)
    eventSource.close()
  }

  return eventSource
}
```

**API 封装：**

```javascript
// AI 恋爱大师 SSE
export const chatWithLoveApp = (message, sessionId) => {
  const params = { message }
  if (sessionId) params.session_id = sessionId
  return connectSSE('/ai/love_app/chat/sse', params)
}

// AI 超级智能体 SSE
export const chatWithManus = (message, sessionId) => {
  const params = { message }
  if (sessionId) params.session_id = sessionId
  return connectSSE('/ai/manus/chat', params)
}
```

#### 2.3.6 前端 Agent 事件消费

在 **SuperAgent.vue** 中，SSE 事件按照类型分别消费：

```javascript
const sendMessage = (message) => {
  addMessage(message, true, 'user-question')

  if (eventSource) {
    eventSource.close()   // 关闭已有连接
  }

  connectionStatus.value = 'connecting'
  eventSource = chatWithManus(message, sessionId.value)

  eventSource.onmessage = (event) => {
    const data = event.data
    if (data === '[THINKING]') return          // 忽略心跳
    if (data === '[DONE]') {                    // 流结束
      connectionStatus.value = 'disconnected'
      eventSource.close()
      return
    }
    if (!data) return

    if (data.startsWith('[THINK]')) {
      addMessage(data.slice(7).trim(), false, 'ai-think')       // 思考标签
    } else if (data.startsWith('[STEP]')) {
      addMessage(data.slice(6).trim(), false, 'ai-step')        // 步骤标签
    } else if (data.startsWith('[FINAL]')) {
      addMessage(data.slice(7).trim(), false, 'ai-final')       // 最终答案
    }
  }

  eventSource.onerror = (error) => {
    console.error('SSE Error:', error)
    connectionStatus.value = 'error'
    eventSource.close()
  }
}
```

在 **LoveMaster.vue** 中，Chain 模式的 SSE 消费更加简单：

```javascript
const sendMessage = (message) => {
  addMessage(message, true)
  connectionStatus.value = 'connecting'
  eventSource = chatWithLoveApp(message, sessionId.value)

  eventSource.onmessage = (event) => {
    const data = event.data
    if (data === '[DONE]') {
      connectionStatus.value = 'disconnected'
      eventSource.close()
    }
    if (!data || data === '[THINKING]') return
    // 直接附加到最后一条消息（continuous 标记）
  }
}
```

#### 2.3.7 完整数据流

**Agent 模式完整数据流：**

```
用户点击发送
  │
  ├── 前端：addMessage(userText, true)          → 立即显示用户消息
  ├── 前端：eventSource = new EventSource(url)  → 建立 SSE 连接
  │
  ├── 后端：sse_response()                      → 立即发送心跳 [THINKING]
  ├── 后端：stream_agent()                      → Agent 开始推理
  │     ├── [THINK] 思考内容                    → 前端显示思考气泡
  │     ├── [STEP] 工具调用 + 结果              → 前端显示工具步骤
  │     ├── [THINK] 继续推理...
  │     └── [FINAL] 最终答案                    → 前端显示 AI 回复
  │
  ├── 后端：保存消息到 MySQL                    → 持久化对话记录
  ├── 后端：触发摘要更新                        → 长对话压缩
  │
  └── 前端：收到 [DONE]                         → 关闭连接
```

**Chain 模式完整数据流：**

```
用户点击发送
  │
  ├── 前端：addMessage(userText, true)          → 立即显示用户消息
  ├── 前端：eventSource = new EventSource(url)  → 建立 SSE 连接
  │
  ├── 后端：sse_response()                      → 立即发送心跳 [THINKING]
  ├── 后端：stream_chain()                      → LLM 逐 token 流式输出
  │     └── 直接输出文本块                      → 前端实时渲染
  │
  ├── 后端：保存消息到 MySQL                    → 持久化对话记录
  ├── 后端：触发摘要更新                        → 长对话压缩
  │
  └── 前端：收到 [DONE]                         → 关闭连接
```

### 2.4 实现效果

- **零额外依赖**：不依赖 WebSocket、Socket.IO 等库，前后端均使用原生 API（后端 `stream_with_context`，前端 `EventSource`）
- **实时体验**：首 token 延迟在 1-2 秒内，用户可逐字阅读 AI 回复
- **过程透明**：Agent 模式中，用户可以看到 AI 的思考过程和工具调用步骤，增强可解释性和信任感
- **自动重连**：前端 EventSource 在连接意外断开时自动重试（浏览器原生行为）
- **连接管理**：每次发送新消息前关闭旧连接，避免多条消息堆积

---

## 三、JWT 与 SSE 的关系

### 3.1 分工

| 维度 | JWT 用户登录 | SSE 通信 |
| :--- | :--- | :--- |
| **职责** | 身份认证与权限控制 | 实时数据传输 |
| **方向** | 双向请求-响应 | 服务端→客户端单向推送 |
| **协议** | HTTP Restful API | HTTP SSE (text/event-stream) |
| **状态** | 无状态（Token 自包含） | 有状态（长连接） |
| **生命周期** | 每次请求独立验证 | 单次对话持续存在 |

### 3.2 协作

JWT 和 SSE 在项目中**各司其职**，共同构成完整的用户交互链路：

```
用户 → [JWT 登录] → 获取 Token → [SSE 对话] → AI 回复
                  ↓                                      ↓
          会话管理 API（受 @login_required 保护）     流式输出（无需额外认证）
```

- **对话之前**：用户必须通过 JWT 登录系统，获取 Token 后才能访问对话页面
- **对话之中**：SSE 连接不携带 Token（EventSource 不支持自定义请求头），但对话页面本身已受路由守卫保护，未登录用户无法进入
- **对话之后**：会话 CRUD 接口（创建、重命名、删除）通过 Axios 拦截器自动附加 JWT Token，受 `@login_required` 装饰器保护

### 3.3 对比

| 对比项 | JWT 认证 | SSE 通信 |
| :--- | :--- | :--- |
| **模式** | 请求-响应 | 推送 |
| **传输层** | HTTP (JSON) | HTTP (text/event-stream) |
| **认证方式** | Bearer Token | 页面级路由守卫 |
| **状态管理** | 无状态 | 长连接 |
| **超时处理** | Token 7 天过期 | 流结束后自动关闭 |
| **安全性** | 加密签名 + 密码哈希 | 不直接对外暴露 |
| **前端实现** | Axios 拦截器 | 原生 EventSource |

### 3.4 关键设计决策

1. **SSE 不走 JWT 认证**：原生 `EventSource` API 不支持自定义请求头，无法直接传递 `Authorization: Bearer <token>`。解决方案是利用 Vue Router 的路由守卫——未登录用户根本进不了对话页面，天然保证了 SSE 连接发起者一定是已登录用户。

2. **Token 存储在 localStorage**：简单且符合单页应用模式。不受 SSR 影响，在页面刷新后仍然可用。

3. **SSE 优于 WebSocket 的选择**：项目只需要服务端→客户端的单向实时推送（AI 回复流），不需要双向（客户端不需要通过长连接向服务端发消息），SSE 是更轻量、更符合语义的选择。如果未来需要双向实时交互，可考虑升级为 WebSocket。

---

## 四、总结

| 概念 | 一句话总结 |
| :--- | :--- |
| **JWT 用户登录** | 通过 HS256 签名 Token 实现无状态身份认证，覆盖注册、登录、鉴权、登出完整链路 |
| **SSE 通信** | 基于原生 HTTP 的服务端推送协议，实现 LLM Token 级流式输出和 Agent 过程透明化 |
| **两者协作** | JWT 负责"进门安检"，SSE 负责"对话流畅"——页面守卫保证安全，SSE 保证实时 |
