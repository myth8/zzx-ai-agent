# JWT 用户登录、Redis 会话与 SSE 通信

本文档描述当前实现。旧版“长期 JWT、原生 EventSource、不校验 SSE Token、仅依靠前端路由守卫”的方案已经废弃。

## 一、当前认证结构

```text
浏览器
  ├─→ Access Token 保存在 localStorage
  ├─→ Refresh Token 保存在 HttpOnly Cookie
  └─→ CSRF Token 保存在浏览器可读 Cookie
              │
              ▼
Flask-JWT-Extended 校验 JWT
  ├─→ Redis 校验 sid、refresh jti 和吊销记录
  └─→ MySQL 读取最新用户角色与资源归属
              │
              ▼
普通 API 与 Fetch SSE 使用相同登录校验
```

职责边界：

| 组件 | 职责 |
|---|---|
| JWT | 携带身份、有效期、issuer、audience、jti 和 sid |
| Redis | 保存登录会话、Refresh 当前 jti、吊销状态和限流计数 |
| MySQL | 保存用户、密码哈希、role、会话、消息和资源归属 |
| 前端 | 携带 Access Token、在过期时调用刷新接口、读取 SSE |

这不是完全无状态 JWT。JWT 负责凭证表达，Redis 让登录可以被立即吊销，MySQL 提供最新权限真相。

## 二、Access Token 与 Refresh Token

### Access Token

- 默认有效期 30 分钟。
- 通过 `Authorization: Bearer <token>` 调用普通 API 和 SSE。
- 过期、签名错误、issuer 或 audience 不匹配都会被拒绝。
- 携带唯一 `jti` 和本次设备登录的 `sid`。

### Refresh Token

- 默认有效期 14 天。
- 保存于 HttpOnly Cookie，JavaScript 无法直接读取 Token 正文。
- 只能用于刷新接口，不能直接调用业务接口。
- 刷新时原子轮换 jti，旧 Refresh Token 不能重复使用。
- 刷新请求还需要 CSRF Cookie 和 `X-CSRF-TOKEN` 请求头。

可以类比为：

```text
Access Token：短期门票
Refresh Token：续票凭证
jti：每张票的唯一编号
sid：本次设备登录编号
```

## 三、登录流程

```text
提交用户名和密码
      │
      ▼
登录 IP 限流
      │
      ▼
登录账号摘要限流
      │
      ▼
MySQL 查询用户并校验密码哈希
      │
      ▼
生成 sid、Access Token 和 Refresh Token
      │
      ▼
Redis 保存登录会话与 Refresh jti
      │
      ▼
返回 Access Token，并设置 Refresh Cookie
```

登录使用双层限流：同一来源 IP 默认每分钟 20 次，同一归一化账号默认每分钟 5 次。

账号先进行 NFKC、去空格和小写归一化，再计算 SHA-256 摘要作为 Redis 限流身份，避免 Redis Key 暴露明文用户名。

## 四、普通请求鉴权

```text
读取 Authorization
      │
      ▼
校验 JWT 签名、类型、时间、issuer 和 audience
      │
      ▼
检查 jti 与 sid 是否被 Redis 吊销
      │
      ▼
从 MySQL 加载最新用户
      │
      ▼
设置 request.current_user
      │
      ▼
业务接口按 user_id 校验资源归属
```

管理员接口继续从 MySQL 读取最新 role，不信任前端缓存，也不把 JWT 中的旧角色作为最终授权依据。

会话查询、消息查询、重命名和删除都使用 `user_id + session_id` 联合条件。知道另一个用户的 session_id 也不能访问对应资源。

## 五、SSE 为什么改用 Fetch

浏览器原生 `EventSource` 不能方便地设置自定义 Authorization 请求头。旧方案只依靠前端页面守卫，攻击者仍然可以绕过页面直接请求 SSE URL，因此不能作为后端安全边界。

当前前端改用 Fetch 读取流：

```javascript
fetch(url, {
  headers: {
    Authorization: `Bearer ${accessToken}`
  }
})
```

两个 SSE 入口都使用 `login_required`，再使用 `chat_rate_limit`：

```text
Fetch 建立流式请求
      │
      ▼
校验 Access Token 与 Redis 登录状态
      │
      ▼
加载最新用户并设置 current_user
      │
      ▼
按 user_id 检查聊天限流
      │
      ▼
校验 session_id 是否属于当前用户
      │
      ▼
生成并返回 SSE 内容
```

恋爱大师与超级智能体共享默认每分钟 12 次的用户级聊天额度。

## 六、SSE 数据与稳定错误

正常流程：

```text
data: [THINKING]

data: 第一段内容

data: 第二段内容

data: [DONE]
```

异常发生时，连接通常已经开始返回 HTTP 200，无法再稳定切换成普通 JSON 500。因此后端发送稳定的 `event: error`，内容只包含 `CHAT_STREAM_FAILED`、安全提示、request_id 和空 details。

客户端不会收到 Python 堆栈、数据库错误、工具参数或原始异常文本。服务端日志保留脱敏后的详细堆栈，并使用同一个 request_id 关联。

## 七、自动刷新流程

```text
业务请求返回 Access Token 过期
      │
      ▼
前端读取 CSRF Cookie
      │
      ▼
携带 Refresh HttpOnly Cookie 和 X-CSRF-TOKEN
      │
      ▼
Redis 原子校验并轮换 Refresh jti
  ├─→ 失败：清理登录状态并要求重新登录
  └─→ 成功：返回新 Access Token 和 Refresh Cookie
                     │
                     ▼
              重试原业务请求
```

刷新不是为了让 Access Token 无限有效，而是将“短期业务凭证”和“长期登录体验”分开。用户也可以选择不用 Refresh Token，直接设置较长 Access Token 并在过期后重新登录，但代价是泄露后的可利用时间更长、主动吊销更依赖服务端状态。

## 八、退出与吊销

退出当前设备时：

1. 当前 Access Token jti 写入吊销记录。
2. 当前 sid 登录会话失效。
3. 从用户会话集合移除该 sid。
4. 清除 Refresh Cookie。

退出所有设备时，当前用户的所有 sid 都会失效。后续请求即使携带尚未自然过期的 Access Token，也会因为 Redis 状态失效而被拒绝。

## 九、限流与 Redis 数据结构

认证状态和限流状态共用 Redis 服务，但使用不同前缀和数据结构语义。

固定窗口限流记录是：

```text
Redis Key → String 计数值，并附带 Key TTL
```

例如：

```text
LIMITS:LIMITER/zzx:ratelimit/user:9/chat-stream/12/1/minute → 5
```

Redis 是 K-V 数据库，但这里的 Value 类型是 String，不是 Redis Hash。计数通过原子递增更新，TTL 到期后 Key 自动删除。

完整说明见 `docs/summary/Redis差异化限流与生产运行基线.md`。

## 十、安全存储说明

当前 Access Token 仍保存在 localStorage，以兼容现有前端架构。阶段 0.3 已增加 Markdown-It、DOMPurify、危险 URL 协议白名单和 CSP，显著降低模型输出导致的 XSS 风险。

但 localStorage 仍可被同源 JavaScript 读取，所以后续可以进一步评估：

- Access Token 仅保存在内存。
- 页面刷新时通过 Refresh Cookie 恢复 Access Token。
- 更严格 CSP，逐步去除 `unsafe-inline`。
- 依赖供应链与第三方脚本控制。

## 十一、回归测试

当前相关测试覆盖：

- Token 缺失、过期、错误签名和错误 audience。
- Redis 登录会话、Refresh 轮换和吊销。
- 管理员读取 MySQL 最新角色。
- 两个 SSE 接口未登录拒绝。
- 用户 A 无法访问用户 B 会话。
- 登录 IP、账号摘要和聊天限流。
- SSE 稳定错误与 request_id。
- 日志正文及 traceback 脱敏。

## 十二、结论

```text
JWT 负责证明“请求携带了什么身份凭证”
Redis 负责判断“这次登录和 Token 现在是否仍然有效”
MySQL 负责判断“用户当前拥有什么权限和资源”
Fetch SSE 负责“在同一认证边界下传输流式内容”
```

前端路由守卫只改善用户体验，真正的认证、资源归属和限流全部由后端执行。
