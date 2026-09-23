# 数据库迁移

入门说明见 `../../docs/blogs/阶段1.1-SQLAlchemy连接管理与Alembic迁移基线.md`。

数据库结构只由 Alembic revision 管理，应用启动不会再执行建表或改表 SQL。

升级前按顺序执行：

```bash
python scripts/db_preflight.py --output ../database-backups/preflight.json
python scripts/backup_database.py --output-dir ../database-backups
alembic upgrade head
alembic current
```

查看迁移链与当前版本：

```bash
alembic history
alembic current
```

新建结构变更：

```bash
alembic revision -m "describe_schema_change"
```

当前项目没有配置 ORM `target_metadata`，因此迁移脚本需要手工编写并审核，
不要直接依赖 `--autogenerate`。每个 revision 应说明结构变化、数据回填、
升级前置检查以及降级策略。

部署时先执行迁移，成功后再启动 Web 进程。不要让每个 Gunicorn Worker 自行改表。
