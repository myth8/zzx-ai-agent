# Redis 差异化限流与生产运行基线

本文记录阶段 0.3、0.4 中与接口限流、Redis 存储、反向代理、Gunicorn 和安全回归有关的实现细节，作为后续阅读代码、调整生产参数和排查 429 问题的技术参考。

## 一、当前方案解决什么问题

没有限流时，登录爆破、批量注册、重复聊天和频繁重建 RAG 索引都可能直接消耗数据库、模型或向量计算资源。单纯在 Python 进程里维护计数又无法覆盖多线程和多个 Gunicorn Worker。

当前方案采用：

```text
Flask 路由装饰器
      │
      ▼
Flask-Limiter 生成限流规则
      │
      ▼
按 IP、账号摘要或 user_id 生成身份键
      │
      ▼
Redis 原子增加固定窗口计数
  ├─→ 未超限：继续执行业务接口
  └─→ 已超限：返回统一 HTTP 429
```

职责边界如下：

| 组件 | 职责 |
|---|---|
| `app/utils/rate_limit.py` | 定义额度、身份键和共享 scope |
| Flask-Limiter | 包装路由、解析规则、检查额度并产生 429 |
| `limits` Redis Storage | 原子计数、过期时间和窗口状态 |
| Redis | 跨线程、跨进程保存短期限流状态 |
| Flask 统一错误处理 | 将超限异常转换成稳定 JSON 响应 |

## 二、当前差异化额度

| 功能 | 默认额度 | 统计维度 | 共享范围 |
|---|---:|---|---|
| 注册 | 5 次/小时 | 来源 IP | `auth-register` |
| 登录第一层 | 20 次/分钟 | 来源 IP | `auth-login-ip` |
| 登录第二层 | 5 次/分钟 | 归一化账号摘要 | `auth-login-account` |
| 两个聊天入口 | 12 次/分钟 | 登录用户 ID | `chat-stream` |
| RAG 管理读取 | 120 次/分钟 | 管理员用户 ID | `rag-admin-read` |
| 管理写入 | 6 次/分钟 | 登录用户 ID | `admin-write` |

管理写入包括邀请码兑换、文档上传、文档删除和索引重建。这些操作共享同一额度，避免调用方轮换不同接口绕过限制。

所有额度都可通过 `.env` 调整：

```ini
RATELIMIT_KEY_PREFIX=zzx:ratelimit
REGISTER_RATE_LIMIT=5 per hour
LOGIN_IP_RATE_LIMIT=20 per minute
LOGIN_ACCOUNT_RATE_LIMIT=5 per minute
CHAT_RATE_LIMIT=12 per minute
ADMIN_READ_RATE_LIMIT=120 per minute
ADMIN_WRITE_RATE_LIMIT=6 per minute
```

## 三、三个限流身份键

### 3.1 来源 IP

注册和登录 IP 层使用：

```python
def remote_ip_key():
    return f"ip:{get_remote_address()}"
```

示例：

```text
ip:192.0.2.10
```

`get_remote_address()` 最终读取 Flask 的 `request.remote_addr`。生产环境只有在 Flask 确实位于固定层数的可信反向代理后面时，才配置 `TRUST_PROXY_HOPS`，否则客户端可能伪造 `X-Forwarded-For` 绕过按 IP 限流。

### 3.2 登录账号摘要

登录账号键的生成过程为：

```text
读取 username
      │
      ▼
Unicode NFKC 归一化
      │
      ▼
去首尾空格并转小写
      │
      ▼
计算 SHA-256
      │
      ▼
取前 24 个十六进制字符
```

因此 `Alice`、` ALICE ` 和 `alice` 会进入同一个计数桶。Redis Key 不保存明文用户名，而是类似：

```text
login-account:2bd806c97f0e00af1a1fc332
```

这层限制可以应对攻击者更换代理 IP、但持续爆破同一账号的情况。

### 3.3 当前登录用户

聊天与管理接口在 `login_required` 或 `admin_required` 之后执行限流：

```python
def current_user_key():
    user = getattr(request, "current_user", None) or {}
    user_id = user.get("user_id")
    return f"user:{user_id}" if user_id is not None else remote_ip_key()
```

正常情况下生成：

```text
user:9
```

如果上下文中没有登录用户，会退回 IP 键，不会让所有匿名请求落入同一个空键。

## 四、装饰器顺序为什么重要

聊天接口的结构是：

```python
@login_required
@chat_rate_limit
def chat():
    ...
```

Python 装饰后的调用关系可理解为：

```text
login_required
      │
      ▼
校验 JWT 并设置 request.current_user
      │
      ▼
chat_rate_limit 按 user_id 检查额度
      │
      ▼
业务函数
```

如果把顺序反过来，限流执行时还没有 `request.current_user`，请求只能退回 IP 维度，无法实现真正的用户级额度。

登录接口则叠加两层：

```python
@login_ip_rate_limit
@login_account_rate_limit
def login():
    ...
```

请求先经过 IP 总量限制，再经过账号限制，最后才读取 MySQL 和校验密码。无论密码是否正确，请求尝试都会消耗额度。

## 五、为什么使用 shared_limit

`limiter.shared_limit()` 的关键参数是 `scope`。只要身份键、scope 和规则相同，多个接口就会使用同一个计数桶。

例如两个聊天入口都使用：

```text
key = user:9
scope = chat-stream
limit = 12 per minute
```

用户先调用恋爱大师 7 次，再调用超级智能体 5 次，就已经消耗 12 次，而不是每个入口分别拥有 12 次。

管理员写操作同理：

```text
上传 2 次
删除 1 次
重建 2 次
邀请码兑换 1 次
----------------
共享计数 6 次
```

下一次任意管理员写操作都会超限。

## 六、Redis 到底保存什么

### 6.1 K-V 存储不等于 Redis Hash 类型

Redis 整体是 Key-Value 数据库，但 Value 可以是 String、Hash、List、Set、Sorted Set 等类型。

当前固定窗口限流使用的是：

```text
Redis Key → Redis String Value
```

不是：

```text
Redis Key → Redis Hash<Field, Value>
```

可以从三个层次区分：

| 层次 | 结论 |
|---|---|
| 通用模型 | 它是 K-V 映射 |
| Redis 对外数据类型 | Value 是 String，不是 Hash |
| Redis 内部实现 | Key 空间可由哈希表组织，这是实现细节 |

### 6.2 一条真实记录

隔离测试中使用“同一 IP 每分钟最多 2 次”，Redis 产生了：

```text
Key:
LIMITS:LIMITER/zzx:demo:ratelimit/192.0.2.10/demo-api/2/1/minute

Value:
3

TTL:
60 秒左右
```

真实请求结果：

| 请求 | HTTP 状态 | Redis Value | 剩余额度 | TTL |
|---|---:|---:|---:|---:|
| 第 1 次 | 200 | 1 | 1 | 约 60 秒 |
| 第 2 次 | 200 | 2 | 0 | 约 60 秒 |
| 第 3 次 | 429 | 3 | 0 | 约 60 秒 |

第三次会先被记录，再因为 `3 > 2` 被拒绝。因此被拒绝的攻击请求仍会进入计数，后续请求可能继续增长为 4、5、6，但在窗口过期前都会返回 429。

### 6.3 Value 里的数字存在哪里

从 Redis 命令视角：

```redis
TYPE "LIMITS:LIMITER/..."
```

返回：

```text
string
```

读取计数：

```redis
GET "LIMITS:LIMITER/..."
```

返回：

```text
"3"
```

这个 `3` 就是 Key 对应的 Value。Redis String 可以保存文本、整数表示、JSON 或二进制数据。由于该值是合法整数，Redis 可以对它执行原子的 `INCR`。

小整数在 Redis 内部可能采用整数编码以节省空间，但对外数据类型仍然是 String。可以使用 `OBJECT ENCODING key` 观察内部编码；不能因为内部编码为 `int` 就把它理解成另一种 Redis 数据类型。

### 6.4 TTL 不在 Value 中

TTL 不会被拼进字符串 `"3"`，而是 Redis 为 Key 单独维护的过期信息。逻辑上可以理解成：

```text
值映射：Key → 3
过期映射：Key → 到期时间
```

因此每个用户、scope 和窗口都能拥有独立 TTL。若使用一个大 Hash 保存所有用户，Redis 无法直接为每个普通 Hash Field 设置独立 TTL，这也是固定窗口计数器适合使用独立 String Key 的原因之一。

## 七、固定窗口如何判断

当前配置：

```python
RATELIMIT_STRATEGY = "fixed-window"
```

简化后的等价逻辑是：

```text
根据身份、scope 和规则生成 Key
      │
      ▼
Redis 原子增加计数并维护过期时间
      │
      ▼
新计数是否大于额度
  ├─→ 否：继续处理
  └─→ 是：抛出 RateLimitExceeded
```

Redis 负责原子递增，因此多个线程、多个 Gunicorn Worker 甚至多台连接同一 Redis 的服务器都不会各自维护一份独立计数。

固定窗口性能好、存储简单，适合当前规模。它的边界是窗口交界处可能产生瞬时突发；未来如果需要更平滑的模型流量，可以评估 moving-window 或滑动窗口计数器，但 Redis 成本会更高。

## 八、超限响应

超限后统一返回：

```json
{
  "code": "RATE_LIMIT_EXCEEDED",
  "message": "请求过于频繁，请稍后重试",
  "request_id": "本次请求的关联 ID",
  "details": null
}
```

响应还会携带：

```text
X-RateLimit-Limit
X-RateLimit-Remaining
X-RateLimit-Reset
Retry-After
```

前端未来可以依据 `Retry-After` 展示倒计时，而不需要猜测恢复时间。

## 九、Redis 故障策略

当前配置：

```python
RATELIMIT_SWALLOW_ERRORS = False
```

含义是 Redis 异常时不静默忽略限流。如果静默放行，登录爆破者可能在限流存储不可用时获得无限尝试机会。当前方案倾向安全失败：请求进入统一异常处理并返回稳定服务错误，同时服务端日志记录 request_id。

生产环境需要为 Redis 配置监控、持久化、高可用和连接告警。限流数据可以在窗口结束后丢弃，但 Redis 同时还承担 JWT 登录会话与吊销状态，因此不能把它当作完全可有可无的缓存。

## 十、Gunicorn 与限流的关系

Redis 限流已经具备跨 Worker 共享能力，但 RAG 在线索引仍是进程本地状态。因此当前 Gunicorn 默认：

```text
Worker：1
Threads：4
Worker Class：gthread
```

这让多个线程可以并发处理普通请求与 SSE，同时只保留一份进程内 RAG 索引、Embedding 和 Reranker。

增加 Worker 前还需完成：

1. Redis 分布式重建锁。
2. 持久化 active index version。
3. 跨进程索引发布与刷新通知。
4. 避免不同进程持有不同 Chroma/BM25 版本。

限流支持多 Worker，不代表整个应用当前已经适合直接扩成多 Worker。

## 十一、测试覆盖

限流测试实际连接 Redis，覆盖：

- 注册按来源 IP 超限。
- 账号大小写和首尾空格归一化后共享额度。
- 不同账号不会错误共享账号桶。
- 聊天按 user_id 隔离。
- 不同管理员拥有独立写额度。
- 上传、删除和重建共享管理员写 scope。
- Redis 中确实产生带指定前缀的限流 Key。
- 429 响应具有稳定错误码、额度 Header 和 Retry-After。

CI 使用独立 Redis 7 服务运行测试，避免因为本机 Redis 不存在而把关键用例跳过。

## 十二、运维排查命令

查看限流 Key：

```redis
SCAN 0 MATCH "LIMITS:LIMITER/zzx:ratelimit/*" COUNT 100
```

查看类型：

```redis
TYPE "完整 Key"
```

查看计数：

```redis
GET "完整 Key"
```

查看剩余过期时间：

```redis
TTL "完整 Key"
```

生产环境不建议使用无范围的 `KEYS *`，它会阻塞 Redis；应使用 `SCAN` 并限定前缀。

## 十三、后续优化方向

1. 前端识别 429 和 Retry-After，提供明确倒计时。
2. 为限流命中率、Redis 延迟和 429 数量增加指标。
3. 根据真实调用分布调整聊天与管理额度。
4. 对高成本工具增加独立 cost，而不是所有请求固定消耗 1。
5. 为内部健康检查和可信任务 Worker设计明确豁免策略，避免随意绕过。
6. 评估滑动窗口，降低固定窗口边界突发。
7. Redis 集群部署时验证 Lua 脚本、Key 前缀和故障转移行为。

