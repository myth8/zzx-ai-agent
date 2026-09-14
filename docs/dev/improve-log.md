# 项目优化记录

## 2026-09-14：阶段 0.1 敏感配置治理

### 本次目标

移除运行代码中的硬编码凭据，建立开发、测试、生产环境配置边界，在应用启动时尽早发现缺失或不安全配置，并降低日志和代码提交再次泄露秘密的风险。

### 已完成内容

#### 1. 后端配置环境化

- app/config.py 已改为从操作系统环境变量加载配置。
- 支持从 zzx-ai-agent-backend/.env 和仓库根目录 .env 读取本地配置；操作系统环境变量优先，其次是服务目录配置。
- 模型 Key、MySQL 账号密码和 JWT Secret 不再提供代码内默认秘密。
- 增加 development、test、production 三种配置：
  - development：用于本地开发，可开启 Flask 调试模式。
  - test：只提供明确标记为 test-only 的隔离默认值。
  - production：关闭调试，并拒绝明显的示例或测试占位密钥。
- 启动应用前调用配置校验。必需变量缺失时直接停止启动，并列出缺失的变量名。
- JWT 签发和解析不再回退到固定弱密钥。
- 健康检查增加当前 environment 字段，便于确认服务使用的运行环境。

#### 2. 启动入口安全化

- run.py 不再固定 debug=True。
- 调试状态由 APP_ENV 对应配置决定，production 始终关闭。
- APP_HOST 和 APP_PORT 可通过环境变量配置。
- 默认监听地址改为 127.0.0.1，避免本地开发服务无意暴露到局域网；需要容器或远程访问时可显式设为 0.0.0.0。

#### 3. MCP 配置环境化

- 天气服务 Key 已从 zzx_mcp_server/server.py 移除。
- 新增 MCP 独立配置模块，从根目录或 MCP 服务目录 .env 加载。
- SENIVERSE_API_KEY 缺失时拒绝启动或调用天气工具。
- MCP_HOST、MCP_PORT、MCP_PATH 和 LOG_LEVEL 支持环境变量。
- production 环境会拒绝示例、测试或 change-me 类型的占位 Key。

#### 4. 示例配置与文件保护

新增以下无真实秘密的模板：

- zzx-ai-agent-backend/.env.example
- zzx_mcp_server/.env.example
- zzx-ai-agent-frontend/.env.example
- zzx-ai-agent-frontend/.env.development.example
- zzx-ai-agent-frontend/.env.production.example

根目录 .gitignore 已更新：

- 忽略根目录和各子目录的 .env 及其环境变体。
- 明确保留所有 .env.example 和 .env.*.example。
- 忽略运行日志文件与 logs 目录。

使用方式：

1. 将对应服务的 .env.example 复制为 .env。
2. 填入新生成或新申请的真实凭据。
3. 根据环境设置 APP_ENV 为 development、test 或 production。
4. 不要将 .env、日志或实际凭据提交到 Git。

#### 5. 前端部署配置

- 前端 API 地址改用 VITE_API_BASE_URL。
- 开发环境未设置时回退到本地后端地址，生产环境未设置时回退到 /api。
- 明确注明所有 VITE_ 变量都会进入浏览器产物，禁止放置秘密。
- Dockerfile 支持通过 VITE_API_BASE_URL 构建参数设置 API 地址。
- Docker 构建依赖安装改用 npm ci，使 package-lock.json 对应的安装结果更稳定。

#### 6. 日志脱敏与最小化

- 后端新增统一日志配置和 RedactingFilter。
- MCP 服务增加同类日志过滤器。
- 常见 Bearer Token、API Key、Authorization、Cookie、JWT Secret、Password 和 Token 字段会替换为 REDACTED。
- Chain 不再记录完整用户输入或完整模型回答，只记录 session_id 和字符数。
- Agent 不再向服务端日志写入完整问题、回答、Thought、工具输入和工具结果，只记录任务阶段和工具名称。
- RAG 不再打印完整查询，只记录查询字符数。
- MCP 天气查询不再记录具体地点，只记录输入长度。

说明：脱敏过滤器是最后一道保护，不能代替“不要记录敏感内容”。因此本次同时移除了主要对话链路中的原文日志。

#### 7. 持续集成密钥扫描

- 新增 .github/workflows/secret-scan.yml。
- 在 push、pull request、手动触发和每周定时任务中执行。
- 使用完整 Git 历史检出，并通过 Gitleaks 扫描已提交的秘密。
- 工作流使用 actions/checkout v6 和 gitleaks-action v3。

### 必须人工完成的事项

代码无法代替外部平台执行凭据吊销。以下操作仍需仓库或账号管理员立即完成：

1. 在 DeepSeek 控制台撤销旧 API Key，并创建权限最小化的新 Key。
2. 在心知天气控制台撤销旧 API Key，并创建新 Key。
3. 修改 MySQL 用户密码；不要继续使用已进入仓库的旧密码。
4. 生成新的高强度 JWT Secret。更换后已有登录 Token 会失效，需要重新登录。
5. 将新值写入本地或部署平台的安全环境变量，不要写回代码。
6. 检查 Git 历史中的泄露记录。密钥轮换后旧记录不再可用；如项目合规要求彻底清除，再单独规划历史重写，并通知所有协作者重新同步仓库。

### 兼容性影响

- 本地后端首次启动前必须创建 .env 并填入必需变量，否则会按设计快速失败。
- MCP 天气服务首次启动前必须配置 SENIVERSE_API_KEY。
- production 不再开启 Flask debug。
- 默认 APP_HOST 从 0.0.0.0 收紧为 127.0.0.1；容器部署需显式设置 APP_HOST=0.0.0.0。
- 前端自定义 API 地址需要使用 VITE_API_BASE_URL。
- 更换 JWT Secret 后，旧 Token 全部失效。

### 验证清单

- Python 文件语法编译通过。
- development 缺失必需变量时配置校验失败。
- test 环境可使用隔离的 test-only 配置完成配置校验。
- production 使用占位密钥时配置校验失败。
- MCP 缺少天气 Key 时配置校验失败。
- 日志过滤器能遮盖 Bearer Token 和常见敏感字段。
- 前端生产构建通过。
- 当前工作树中不再存在原先硬编码的模型 Key、天气 Key、数据库密码和 JWT Secret。
- 归档的 JWT 与 MCP 技术文档中复制的旧密码、Secret 和天气 Key 示例已同步改为环境变量写法。
- Git diff 格式检查通过。

### 后续阶段

阶段 0.1 完成后，建议继续阶段 0.2“认证与资源归属”，优先修复聊天 SSE 未统一鉴权以及会话重命名、删除、消息读取缺少 user_id 联合校验的问题。
