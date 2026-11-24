# SQLAlchemy 与 Alembic 分批 Git 提交方案

## 1. 目标

首批只提交已经可以独立理解的数据库基础设施：

- SQLAlchemy Engine、QueuePool、超时和慢查询基础。
- 统一的 `connection()` / `transaction()` 上下文。
- Alembic 运行环境和 legacy baseline。
- 应用启动时停止自动执行 DDL。
- 迁移前预检、备份和使用文档。

首批明确不包含：

- `chat_runs` 表、repository 和状态机。
- `idempotency_records` 表、repository 和接纳服务。
- `next_message_order + FOR UPDATE` 消息顺序改造。
- 完整 UUID 会话、`message_id` 和 `client_message_id` 改造。
- 注册并发唯一冲突映射。
- 阶段 1.2 至 1.5 的集成测试与设计日志。

## 2. 为什么不能直接提交当前暂存区

当前暂存区同时包含数据库基础、消息事务、run、幂等性、测试和文档，另有 `.idea` 和 `.DS_Store` 这类个人文件。

直接执行 `git commit` 或 `git add .` 会越过本次边界。提交前应先只清理暂存状态，不删除工作区内容：

```bash
git restore --staged .
```

随后按文件和 hunk 重新暂存。对同时包含基础改造和后续功能的文件，使用：

```bash
git add -p <file>
```

## 3. 提交一：SQLAlchemy 运行时基础

建议提交信息：

```text
feat(db): 引入 SQLAlchemy 连接池与统一事务入口
```

完整暂存的文件：

- `zzx-ai-agent-backend/app/db.py`
- `zzx-ai-agent-backend/app/config.py`
- `zzx-ai-agent-backend/.env.example`

按 hunk 暂存的文件：

- `zzx-ai-agent-backend/requirements.txt`：只选 `SQLAlchemy==2.0.52`，暂不选 Alembic。
- `zzx-ai-agent-backend/app/__init__.py`：只选 `init_db_engine(app)`，暂不选“用 schema 检查取代启动 DDL”。
- `zzx-ai-agent-backend/app/auth.py`：只选 `get_db()` 改为返回池化连接，暂不选注册逻辑修改。

这个提交完成后，旧业务方法仍然通过 `get_db()` 获取连接，但底层已经改为 SQLAlchemy QueuePool。应用启动时仍然保持原有建表逻辑，因此该提交可独立运行。

验证：

```bash
cd zzx-ai-agent-backend
python -m unittest discover -s tests -v
python -m compileall -q app tests run.py wsgi.py gunicorn.conf.py
```

## 4. 提交二：Alembic 迁移基线

建议提交信息：

```text
feat(db): 引入 Alembic 基线并移除启动期 DDL
```

完整暂存的文件：

- `.gitignore`：忽略 `database-backups/`。
- `zzx-ai-agent-backend/alembic.ini`
- `zzx-ai-agent-backend/migrations/env.py`
- `zzx-ai-agent-backend/migrations/script.py.mako`
- `zzx-ai-agent-backend/migrations/versions/20260918_0001_legacy_baseline.py`
- `zzx-ai-agent-backend/migrations/README.md`
- `zzx-ai-agent-backend/app/db_schema.py`
- `zzx-ai-agent-backend/scripts/backup_database.py`
- `zzx-ai-agent-backend/scripts/db_preflight.py`

按 hunk 暂存的文件：

- `zzx-ai-agent-backend/requirements.txt`：只选 `alembic==1.16.5`。
- `zzx-ai-agent-backend/app/__init__.py`：选择“启动时校验 Alembic 版本，不再调用建表函数”。
- `zzx-ai-agent-backend/app/auth.py`：只选 `init_db()` 改为兼容性迁移检查，不选注册逻辑。
- `zzx-ai-agent-backend/app/chat_history.py`：只选 `init_tables()` 停止建表的 hunk，不选 UUID、消息顺序和事务改造。
- `zzx-ai-agent-backend/app/rag_documents.py`：只选 `init_rag_tables()` 停止建表的 hunk。

不暂存 `20260918_0002_stage1_data_integrity.py`。这样远程首批的 Alembic head 是 `20260918_0001`，只表示“原有数据库结构已纳入版本管理”。

验证需要 MySQL 8 测试库：

```bash
cd zzx-ai-agent-backend
python scripts/db_preflight.py --output ../database-backups/preflight.json
python scripts/backup_database.py --output-dir ../database-backups
alembic upgrade head
alembic current
python -m unittest discover -s tests -v
```

对全新空库和已有历史表的数据库各验证一次。

## 5. 提交三：独立学习文档

建议提交信息：

```text
docs(db): 补充 SQLAlchemy 与 Alembic 数据库演进说明
```

提交：

- `docs/blogs/阶段1.1-SQLAlchemy连接管理与Alembic迁移基线.md`
- `docs/dev/SQLAlchemy与Alembic分批Git提交方案.md`

暂不提交完整阶段 1 设计文档和 improve log，因为它们已经记载 run、幂等性和消息事务等尚未准备提交的内容。

## 6. 后续功能的预留提交

等理解对应设计后，再依次提交：

```text
feat(db): 增加数据完整性约束与消息顺序事务
feat(chat): 增加 chat run 生命周期和状态机
feat(chat): 增加幂等记录与原子消息接纳
test(db): 增加 MySQL 并发与幂等集成测试
docs(db): 更新阶段 1 完整设计与实施日志
```

`20260918_0002_stage1_data_integrity.py` 当前同时包含数据完整性、run 和幂等表。在准备后续提交前，应再决定是保持一个整体 revision，还是在尚未共享到其他环境时重新拆成多个 revision。一旦某个 revision 已被其他人或共享环境执行，就不应再改写它的历史。

## 7. 推送方案

三个提交都通过检查后，先确认将要推送的提交：

```bash
git log --oneline origin/develop..HEAD
git status --short
```

项目当前 `origin` 配置了 Gitee 和 GitHub 两个 push URL，因此：

```bash
git push origin develop
```

会尝试向两个地址推送。如果只想更新 GitHub，使用：

```bash
git push github develop
```

推送前应再用 `git show --stat HEAD~2..HEAD` 和 `git diff <remote>/develop...HEAD` 确认边界，不应将 `.idea`、`.DS_Store`、`20260918_0002`、run 或幂等服务带入首批推送。
