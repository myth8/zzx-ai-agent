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

## 2026-09-15：阶段 0.2 认证、Redis 会话与资源归属

### 本次目标

将原有的单一长期 JWT 升级为可续签、可吊销、可按设备管理的认证体系；为后续 RAG 管理系统建立轻量管理员授权基础，并封闭会话和 SSE 接口仅凭 session_id 越权访问的风险。

### 已完成内容

#### 1. JWT 生命周期升级

- 使用 Flask-JWT-Extended 统一签发与校验 JWT。
- Access Token 默认有效期为 30 分钟，继续通过 Authorization Bearer 头发送。
- Refresh Token 默认有效期为 14 天，保存到 HttpOnly Cookie，前端 JavaScript 无法直接读取 Token 内容。
- Refresh Cookie 启用 CSRF 保护；前端只读取独立的 CSRF Cookie，并通过 X-CSRF-TOKEN 请求头完成校验。
- JWT 包含并校验 issuer、audience、issued_at、expires_at、jti、sid 和 token type。
- 新增 POST /api/auth/refresh、DELETE /api/auth/logout 和 DELETE /api/auth/logout-all。
- 前端普通 API 遇到 401 时自动执行一次续签并重试；并发 401 共用同一次刷新请求，避免 Refresh Token 并发轮换互相冲突。

#### 2. Redis 登录会话与吊销状态

- 新增统一 Redis 扩展和认证状态存储模块。
- Redis 只保存登录会话 sid、用户 ID、当前 Refresh Token jti 和吊销标记，不保存完整 Access Token 或 Refresh Token。
- Refresh Token 每次使用后通过 Redis WATCH/MULTI 原子轮换；旧 Refresh Token 不能再次使用。
- 单设备退出会删除对应登录会话；全部退出会删除该用户的所有登录会话。
- Access Token 被显式吊销后，吊销标记只保留到 Token 自然过期，避免无界增长。
- Redis 异常时认证校验采用 fail-closed：无法确认 Token 状态就拒绝访问，避免以不安全方式降级。
- /api/health 增加 redis 状态；Redis 不可用时整体状态为 degraded。

#### 3. 轻量管理员授权

- users 表增加 role 字段和索引，默认值为 user；已有数据库会在后端首次启动时自动补充字段。
- 公开注册接口始终写入 user，不接受客户端提交管理员角色。
- 新增 admin_required 装饰器，预留给后续 RAG 管理、用户管理等后台接口。
- login_required 和 admin_required 每次请求都按用户 ID 查询数据库最新状态，因此降权、升权和删除用户可以即时生效，不依赖旧 JWT 中的角色声明。
- 前端返回的 role 只用于页面入口和展示；真正的权限边界始终由后端 admin_required 执行。

首个管理员需要由数据库管理员明确指定，例如：

```sql
UPDATE users
SET role = 'admin'
WHERE username = '需要设为管理员的账号';
```

#### 4. 会话资源归属

- 会话列表、创建、重命名、删除、消息读取全部统一使用 login_required。
- 新增 get_user_session(user_id, session_id)，所有资源访问以 user_id 和 session_id 联合校验。
- 消息写入、最近消息、消息统计、对话摘要读取与更新同样加入用户归属约束。
- 删除会话先锁定并确认归属，再删除消息、摘要和会话本身。
- 用户访问不属于自己的 session_id 时统一按“资源不存在”返回 404，避免泄露资源是否存在。

#### 5. SSE 鉴权与前端兼容

- Love Master 和 Manus 两个 SSE 聊天接口均增加登录校验和会话类型、会话归属校验。
- 浏览器原生 EventSource 不能设置 Authorization 请求头，因此前端改为 fetch + ReadableStream 解析 SSE，同时保留原有 onmessage、onerror、close 调用形式。
- SSE 首次遇到 401 时会通过 Refresh Cookie 续签 Access Token，并只重试一次。
- 前端退出按钮改为调用后端退出接口，不再仅删除 localStorage。
- 跨域配置改为精确来源列表，并允许 Refresh Cookie 随请求发送。

### 配置与依赖

新增依赖：

- Flask-JWT-Extended==4.7.4
- redis==8.1.0

新增或补充环境变量：

- JWT_ACCESS_TOKEN_MINUTES
- JWT_REFRESH_TOKEN_DAYS
- JWT_ISSUER
- JWT_AUDIENCE
- REDIS_URL
- REDIS_AUTH_PREFIX
- REDIS_CONNECT_TIMEOUT
- REDIS_SOCKET_TIMEOUT
- CORS_ORIGINS

### 验证结果

- Redis-backed JWT 安全回归测试 3 项通过：缺少 Token 的统一错误、数据库实时管理员校验、Refresh Token 轮换和会话吊销。
- 当前本地 MySQL 已完成 users.role 字段与 idx_users_role 索引的兼容迁移。
- 后端 Python 语法编译通过。
- 前端生产构建通过。
- Git diff 格式检查通过。

### 部署注意事项

- Redis 已成为认证链路的必要组件，生产环境应开启持久化和备份，并限制网络访问；不能使用无保护的公网 Redis。
- 现有旧版 JWT 没有 sid，也没有 Redis 登录会话记录，升级后会按设计失效，用户需要重新登录。
- 本地开发先启动 Redis，并确认 REDIS_URL 指向正确实例；测试建议使用独立 DB 或独立前缀。
- Refresh Token 使用 Cookie，因此生产环境必须通过 HTTPS；production 配置会自动启用 Secure Cookie。
- 当前 Access Token 为兼容现有前端仍保存在 localStorage。后续完成 CSP、Markdown 清洗等前端安全基线后，可再评估改为仅内存保存以进一步降低 XSS 风险。

### 后续阶段

继续阶段 0.3“输入、工具与前端渲染安全”。开发 RAG 管理页面时，前端根据 user.role 控制菜单可见性，后端所有管理接口必须使用 admin_required，不能依赖前端隐藏页面作为权限控制。

## 2026-09-15：管理员邀请码扩展

### 已完成内容

- 新增 ADMIN_INVITE_CODE 环境配置；当前本地开发值按需求设为 9527，示例配置只保留占位格式。
- 注册接口增加可选 invite_code。未填写时创建普通 user；填写正确时创建 admin；填写但校验失败时拒绝注册。
- 邀请码使用 hmac.compare_digest 比较，且不写入 JWT、数据库或业务日志。
- 新增 POST /api/auth/invite/redeem，登录用户可兑换邀请码并将数据库角色升级为 admin。
- 兑换接口具有幂等性；已经是管理员的用户重复兑换时直接返回当前状态。
- 管理员角色仍由 login_required 在每次请求中从 MySQL 实时加载，因此兑换成功后无需重新登录即可通过 admin_required。
- 注册页面新增选填的邀请码输入框；主页为普通用户增加“兑换邀请码”入口和主题一致的弹窗，升级后立即更新本地用户状态并显示 ADMIN 标识。

### 验证结果

- 安全回归测试扩展到 5 项并全部通过，覆盖正确/错误注册邀请码和登录后兑换。
- 后端 Python 语法编译通过。
- 前端生产构建通过。
- Git diff 格式检查通过。

### 风险说明

固定邀请码是当前阶段的轻量方案，本质上属于可重复使用的管理员凭据。生产环境应改用足够长的随机值并定期轮换；后续建议升级为数据库邀请码记录，支持单次使用、过期时间、使用人、创建人、吊销和审计日志，并对注册及兑换接口增加限流。

## 2026-09-15：开发环境跨域修复

### 问题原因

- 3000 端口已被另一个前端项目占用，当前项目的 Vite 自动顺延到 3003。
- 浏览器仍直接请求 http://localhost:8123/api，而后端 CORS_ORIGINS 只允许 localhost:3000 和 127.0.0.1:3000。
- 因 Origin 包含协议、主机和端口，localhost:3003 与 localhost:3000 是不同来源，登录、注册以及其他带 JSON、Authorization 或 Cookie 的请求都会受到影响。

### 修复内容

- 开发环境 API 地址统一改为相对路径 /api。
- Vite 增加 /api 反向代理，固定转发到 http://127.0.0.1:8123。
- 移除开发服务器的全开放 cors:true，继续使用 Vite 默认的本机开发来源策略。
- .env、.env.example 和 .env.development.example 均改为 VITE_API_BASE_URL=/api。
- 后端仍保留精确 CORS_ORIGINS 白名单，用于前后端确实跨域的独立部署场景。

### 检查范围与结果

- 通过当前实际前端端口 3003 访问 /api/health，成功代理到后端并返回 200。
- 批量检查注册、登录、刷新、邀请码兑换、退出、用户信息、会话增删改查以及两个 SSE 接口，15 个路径的预检均可达。
- 对注册、登录、邀请码、会话和 SSE 发起无敏感数据请求，分别得到预期的 400 参数错误或 401 未登录响应，证明请求已到达后端而非被跨域层拦截。
- 前端生产构建与后端安全回归测试继续通过。

## 2026-09-15：RAG 知识库管理 MVP

### 本次目标

为现有 RAG 检索链路增加管理员可操作的文档管理闭环，使 documents 目录中的 Markdown 知识源可以在前端查看、上传和删除，并在内容变化后安全刷新 Chroma 与 BM25 索引。

### 后端实现

- 新增 rag_documents 表，保存文件名、展示名、文件大小、SHA-256、切片数量、索引状态、错误摘要、上传人和时间信息。
- 应用启动时自动创建表，并将 documents 目录中已有的 Markdown 文件同步到数据库台账；修复元数据切分后，当前 3 份文档同步为 15 个有效正文切片。
- 新增 /api/admin/rag 管理蓝图，提供文档列表、全文、切片详情、上传、删除和手动重建接口。
- 全部接口使用 admin_required；普通用户即使绕过前端直接调用，也会收到统一 403 响应。
- 文件上传仅接受安全文件名的 .md 文件，要求 UTF-8、非空、不能与现有文件同名，并受 RAG_MAX_FILE_SIZE_MB 与 MAX_REQUEST_SIZE_MB 限制。
- 删除前先将源文件原子移动到临时名称；索引刷新失败时恢复原文件，避免文件已经删除但检索索引未更新。
- 文档切片增加 source 和 chunk_index 元数据，前端展示的切片与实际进入检索器的切片使用同一套逻辑。

### 索引刷新设计

- 每次刷新先构建新的 Chroma collection 和 BM25 检索器，全部成功后再原子替换进程内查询状态。
- 持久化索引清单，记录当前 collection、文档内容签名和切片数；应用重启时若文档未变化，则直接复用已有 Chroma collection，避免重复计算全部向量。
- 构建过程中已有查询继续使用旧索引；切换完成且旧查询结束后，再清理旧 collection。
- 上传或删除失败会回滚文件与数据库操作，并尽力恢复与磁盘内容一致的索引状态。
- 修复旧实现重复使用固定 collection、重复初始化可能持续追加相同文档的问题。
- 当前仍是全量重建和单进程状态切换；增量索引、跨 Worker active_version、分布式锁与后台任务属于阶段 4.1 后续增强。

### 文档与切片元数据完善

- 修复 YAML Front Matter 虽已解析、却仍进入正文切分的问题；Front Matter 现在只作为结构化元数据，正文从第一个 Markdown 标题开始切片，不再生成无意义的“元数据切片”。
- rag_documents 使用 document_metadata 保存文档级元数据；新增 rag_document_chunks 子表，逐条保存切片正文、章节、内容哈希、完整 metadata 和 vector_id，并通过 document_id 外键关联文档。
- 切片详情接口改为直接查询 rag_document_chunks，不再在每次请求时读取文件并临时重新切片；删除文档时通过 ON DELETE CASCADE 自动清理子表记录。
- chunk_id 同时作为 Chroma 的向量记录 ID 和 MySQL 的唯一业务 ID，使关系库切片与向量记录可以一一对应。索引清单增加结构版本，切片 ID 规则变化时会强制重建旧 collection。
- 删除早期 MVP 中的 rag_documents.chunk_metadata JSON 字段，避免与 rag_document_chunks 重复维护；升级环境会在启动初始化时自动移除旧字段，全新环境不会创建该字段。
- 切片元数据统一增加 source、document_title、section_title、chunk_index、chunk_id、char_count 和 content_sha256，并继承可用于检索过滤的文档级业务元数据。
- 内置文档补充 description、relationship_stage、topics、audience、language、version、source_type 和 schema_version 等字段。
- 管理页面将文档元数据、正文和切片详情分区展示；文档级字段不再在每张切片卡片上重复堆叠。
- 应用启动会自动创建切片表、迁移现有文档的全部切片，同时重新同步磁盘文件、文档元数据和切片记录。

### 前端实现

- 首页为管理员增加 SYSTEM / 003“RAG 知识库”入口；普通用户不渲染该入口。
- 新增知识库管理页面，展示文档数、切片数、索引状态和文档目录。
- 支持 Markdown 全文渲染、切片内容、字符数与标题元数据查看。
- 支持上传 Markdown、删除确认、操作反馈、索引刷新状态和手动重建。
- “重建索引”升级为“检查并重建”：联合校验源文件内容签名、索引结构版本、Chroma collection、向量 ID 集合和 MySQL 切片 ID 集合；索引最新时直接提示无需重建，仅在状态过期或不一致时触发实际重建。
- 新增管理员索引状态接口，页面可展示 CHECKING、READY、STALE 和 UNKNOWN，并显示需要重建的具体原因。
- 上传区新增“格式示例”说明窗口，展示 Front Matter、标题层级与 UTF-8 要求，并提供可直接下载修改的 示例.md。
- 上传过程增加分阶段进度面板：文件校验、真实上传进度、后端切片与向量构建、页面刷新和完成状态；无法获得精确百分比的索引阶段使用动态状态和实际耗时展示。
- 前端路由增加管理员可见性守卫；最终权限仍以后端 admin_required 为准。

### 配置与依赖

- 新增 RAG_DOCUMENTS_DIR、RAG_CHROMA_DIR、RAG_MAX_FILE_SIZE_MB 和 MAX_REQUEST_SIZE_MB。
- 补充 sentence-transformers==6.0.1；原项目虽然使用 HuggingFaceEmbeddings 和 CrossEncoder，但依赖文件此前没有声明该运行依赖。

### 验证结果

- 前端生产构建通过。
- 后端 14 项测试通过，覆盖原有 JWT/Redis 回归、管理员拒绝、Markdown 文件校验、上传触发重建、切片元数据、切片表读取、最新索引跳过及过期索引重建。
- 使用当前 MySQL 初始化并同步 rag_documents 表成功；修复 Front Matter 切分后，dating.md、married.md、single.md 各生成 5 个有效正文切片，共 15 个切片。
- 使用 BAAI/bge-small-zh-v1.5 实际完成 Chroma 与 BM25 索引构建；文档内容变化后会依据内容签名触发重建。
- 使用临时管理员登录会话实际调用文档列表、全文和切片接口，均返回 200；测试会话随后已吊销。
- 完整功能验收时，当前 5 份文档对应 MySQL 25 条切片和 Chroma 25 条向量，三侧 ID 集合一致；索引状态返回 UP_TO_DATE。
