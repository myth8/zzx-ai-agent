# RAG 锁、多线程与索引一致性设计

## 1. 文档目的

本文总结当前 RAG 管理与检索链路中的并发控制方案，重点说明：

- 当前有哪些锁，每把锁保护什么资源；
- 查询、索引重建、上传、删除和 Reranker 初始化如何协作；
- `threading.Lock`、数据库事务、原子文件替换和补偿操作之间有什么区别；
- 当前方案能保证什么、不能保证什么；
- 从单进程多线程升级到多进程、分布式部署时应如何继续演进。

涉及的主要代码：

- `zzx-ai-agent-backend/app/llm/rag.py`
- `zzx-ai-agent-backend/app/routes/rag_admin.py`
- `zzx-ai-agent-backend/app/rag_documents.py`
- `zzx-ai-agent-backend/tests/test_rag_management.py`

## 2. 先明确几个概念

### 2.1 当前使用的是互斥锁

当前 RAG 中显式创建的锁都是 Python 的 `threading.Lock`。它们属于不可重入的互斥锁：

- 同一时刻最多只有一个线程持有某一把锁；
- 其他线程执行到 `with lock:` 时会等待；
- 持锁线程离开 `with` 代码块时自动释放锁；
- 即使代码块抛出异常，锁也会被释放；
- 同一线程不能在未释放时再次获取同一把 `threading.Lock`，否则会把自己阻塞住。

因此：

```python
with self._state_lock:
    # 临界区
```

既包含“尝试获取锁并在必要时等待”，也包含“离开代码块后自动释放锁”。它不是允许多个线程同时进入的读锁。

### 2.2 GIL 不能替代业务锁

Python 的 GIL 不保证一组业务操作的整体原子性。例如下面这些复合操作仍可能被其他线程穿插：

- 同时判断单例为空并创建两个对象；
- 同时判断 Reranker 未初始化并加载两份模型；
- 分多行替换 Chroma、BM25、文档列表和统计信息；
- 上传文件的同时删除文件或重建索引。

因此，即使使用 CPython，仍需要显式锁保护共享状态和跨步骤业务流程。

### 2.3 锁、事务与原子替换不是同一件事

当前 RAG 一致性由多种机制共同完成：

| 机制 | 保护范围 | 主要作用 |
| --- | --- | --- |
| `threading.Lock` | 当前 Python 进程 | 防止多个线程同时进入关键代码段 |
| MySQL 事务 | 当前数据库连接中的 SQL | 保证多条 SQL 一起提交或一起失败 |
| `os.replace` | 单次文件路径替换 | 避免其他读取者看到写了一半的文件 |
| 新旧 collection 切换 | RAG 索引版本 | 新索引构建失败时继续保留旧索引 |
| 补偿操作 | 文件、MySQL、Chroma 之间 | 跨系统操作失败后尽力恢复到原状态 |

`with conn.cursor()` 只管理游标生命周期，并不代表事务范围。事务通常从连接开始执行 SQL 后持续到 `conn.commit()` 或 `conn.rollback()`；`update_index_results()` 中真正的提交点是 `conn.commit()`。

## 3. 当前 RAG 涉及的五把锁

### 3.1 `RAGEngine._lock`：引擎单例创建锁

位置：`app/llm/rag.py` 的 `RAGEngine` 类和 `get_engine()`。

保护对象：当前进程的全局 `_engine`。

解决的问题：多个请求第一次同时调用 `get_engine()` 时，如果没有锁，可能同时创建多个 `RAGEngine`，进而重复加载 Embedding 模型、读取文档甚至重建索引。

当前采用双重检查：

```text
请求进入 get_engine
  -> 第一次检查 _engine
  -> 尚未创建时获取 RAGEngine._lock
  -> 获取锁后再次检查 _engine
  -> 只有一个线程真正创建引擎
  -> 其他线程复用已经创建的实例
```

这把锁只负责“单例创建”，不负责后续查询和重建。

### 3.2 `self._state_lock`：在线索引状态锁

位置：`RAGEngine.__init__()`、`query()`、`rebuild()`、`stats()` 和 `_release_query()`。

保护的共享状态包括：

- `_docs`
- `_vector_store`
- `_vector_retriever`
- `_bm25`
- `_bm25_retriever`
- `_stats`
- `_active_queries`
- `_retired_stores`

它的核心职责不是保护整段查询，而是以很短的持锁时间取得或替换“一整套同版本索引状态”。

查询线程进入时：

```text
获取 state_lock
  -> active_queries 加一
  -> 一次性复制 docs、Chroma、BM25 等引用
释放 state_lock
  -> 使用快照完成耗时检索和重排
再次获取 state_lock
  -> active_queries 减一
  -> 必要时取出待清理的旧 collection
释放 state_lock
  -> 在锁外删除旧 collection
```

重建线程发布新索引时：

```text
在锁外完成新 Chroma 和 BM25 构建
  -> 获取 state_lock
  -> 一次性替换全部在线索引引用和统计信息
  -> 将旧 Chroma 放入 retired_stores
  -> 判断是否仍有查询运行
  -> 释放 state_lock
  -> 安全时在锁外删除旧 collection
```

这样可以避免查询看到混合状态，例如“Chroma 已经是新版，但 BM25 仍是旧版”。同时，耗时的向量检索、模型推理、索引构建和 collection 删除都不在 `state_lock` 内进行，因此普通查询不会因为这把锁被长时间串行化。

`_active_queries` 与 `_retired_stores` 实现了简化的引用计数和延迟回收：切换完成后，已经取得旧索引快照的查询仍能继续使用旧 collection；只有活动查询归零后才清理退役 collection。

当前回收策略偏保守：计数包含所有活动查询，因此即使部分新查询使用的是新索引，也可能让旧 collection 多保留一会儿。这不会破坏正确性，只会延迟释放少量磁盘资源。

### 3.3 `self._rebuild_lock`：全量索引重建锁

位置：`RAGEngine.rebuild()`。

保护范围：单个 `RAGEngine` 实例内的一次完整重建。

解决的问题：防止同一进程中两个线程同时进行以下高成本操作：

- 读取和切分全部 Markdown 文档；
- 计算 Embedding；
- 创建新的 Chroma collection；
- 构建 BM25；
- 写入 manifest；
- 发布新索引。

它的持锁时间较长，这是有意设计的，因为重建本身必须串行。但它不会阻塞使用旧快照的普通查询。

当前重建采用类似“蓝绿发布”的方式：

```text
获取 rebuild_lock
  -> 读取同一版源文档
  -> 生成内容签名
  -> 使用随机名称创建新 collection
  -> 构建 Chroma 和 BM25
  -> 原子写入 manifest
  -> 短暂获取 state_lock
  -> 一次性发布新索引引用
  -> 延迟清理旧 collection
释放 rebuild_lock
```

如果新索引构建失败，只清理未发布的新 collection，当前在线索引不会被替换。

### 3.4 `self._reranker_lock`：Reranker 懒加载锁

位置：`RAGEngine._get_reranker()`。

保护对象：Cross-Encoder Reranker 的首次初始化。

Reranker 模型体积较大，并且只在第一次真实查询时加载。如果多个请求同时首次进入，没有锁就可能重复下载、读取或构造模型，造成内存暴涨、磁盘竞争和响应超时。

当前也采用双重检查：

```text
先检查 reranker_initialized
  -> 未初始化才竞争 reranker_lock
  -> 获取锁后再次检查
  -> 只有一个线程加载模型
  -> 其他线程等待并复用同一个实例
```

使用独立锁而不是复用 `state_lock`，是为了避免慢速模型加载阻塞查询获取索引快照。

当前锁只保护“模型初始化”，不保护 `reranker.predict()`。也就是说，初始化完成后多个查询可以并发调用同一模型实例。这样吞吐量更高，但是否适合取决于底层推理框架、CPU/GPU、内存和实测结果。后续可以增加推理并发上限，而不是默认把所有推理完全串行化。

异常策略如下：

- 缺少 `sentence-transformers`：记录为已初始化但模型为 `None`，后续直接降级，避免反复导入；
- 下载、文件或构造模型等其他异常：不把初始化状态设为成功，异常继续抛出，后续请求仍可重试。

### 3.5 `_mutation_lock`：RAG 管理操作锁

位置：`app/routes/rag_admin.py`。

保护范围：当前进程内所有会修改 RAG 数据源或索引的管理员操作：

- 上传文档；
- 删除文档；
- 手动重建索引。

这把锁的层级比 `_rebuild_lock` 更高。它保护的不只是索引构建，还包括文件改名、文件落盘、MySQL 文档记录、切片快照和失败补偿等完整业务流程。

例如上传流程为：

```text
获取 mutation_lock
  -> 校验同名文件
  -> 写入隐藏临时文件
  -> os.replace 发布正式文件
  -> 写入 MySQL 文档记录
  -> 获取 rebuild_lock 并构建新索引
  -> 更新 MySQL 切片快照
  -> 成功返回
释放 mutation_lock
```

删除流程为：

```text
获取 mutation_lock
  -> 将正式文件改名为可恢复临时文件
  -> 按新目录重建并发布索引
  -> 删除 MySQL 文档记录
  -> 删除临时文件
释放 mutation_lock
```

如果上传或删除中途失败，路由层会删除新文件、恢复旧文件、清理数据库记录，并尽力按恢复后的磁盘目录再次刷新在线索引。这是一种补偿事务，因为文件系统、MySQL 和 Chroma 无法共享一个真正的 ACID 事务。

`_mutation_lock` 和 `_rebuild_lock` 看似有部分重复，但职责不同：

- `_mutation_lock` 保证管理员业务操作之间不互相穿插；
- `_rebuild_lock` 保证引擎层无论被哪个调用方触发，都不会同时执行两次全量重建。

当前加锁顺序始终是先 `_mutation_lock`，再 `_rebuild_lock`，重建代码不会反向获取 `_mutation_lock`，因此当前没有形成循环等待。后续增加新入口时必须继续保持固定加锁顺序。

## 4. 查询与重建如何同时运行

当前设计的目标不是“重建期间停止所有查询”，而是让查询继续使用稳定的旧版本，等新版本完全准备好后再瞬间切换。

```text
查询 A 获取版本 V1 快照
  |
  | 查询 A 使用 V1 检索
  |
重建线程在后台构建 V2
  |
  | V2 构建完成
  | state_lock 内将在线引用从 V1 切换到 V2
  |
查询 B 获取版本 V2 快照
  |
查询 A 完成并释放 V1
  |
最后一个活动查询结束后清理 V1 collection
```

这套方式具备以下优点：

- 重建失败时旧索引仍可服务；
- 查询不会看到半成品索引；
- 重建期间大部分查询不需要等待；
- Chroma 与 BM25 始终按同一版本切换；
- 旧查询不会因为 collection 被立即删除而报错。

## 5. 索引一致性链路

### 5.1 文件内容签名

源文件签名用于表示当前 `documents` 目录中文件集合及内容版本。它不是用户密码签名，也不是权限凭证，而是索引一致性校验依据。

启动复用索引或管理员检查状态时，会结合以下信息判断索引是否最新：

- 索引 schema 版本；
- 当前源文件内容签名；
- manifest 中记录的 collection 名称和签名；
- Chroma 中实际存在的完整 chunk ID 集合；
- MySQL `rag_document_chunks` 中的完整 chunk ID 集合。

仅比较切片数量是不够的，因为“删除一个旧切片并新增一个新切片”可能使数量不变。因此当前会比较完整 ID 集合。

### 5.2 manifest 原子写入

manifest 先写入同目录临时文件，再通过 `os.replace()` 原子替换。读取者只会看到旧的完整文件或新的完整文件，不会读到只写了一半的 JSON。

原子替换只保证单次文件发布完整，不等于跨进程互斥；两个进程仍可能先后写入两个各自完整但版本不同的 manifest。

### 5.3 MySQL 切片事务

`update_index_results()` 在同一数据库连接中完成：

```text
清零文档切片统计
  -> 删除旧 rag_document_chunks
  -> 按当前文件重新生成文档元数据和切片记录
  -> 更新 rag_documents 状态及数量
  -> commit
```

在正常的非自动提交连接配置下，`commit` 前的这些 SQL 属于同一事务；发生异常并关闭未提交连接时不会提交半套结果。后续可以显式调用 `rollback()`，让事务意图和错误日志更清晰。

需要注意：MySQL 事务无法回滚已经发布的文件和 Chroma collection，因此外层仍需要补偿流程和一致性检查。

## 6. 当前方案已经提供的保证

在“单个 Python 进程、多个线程”的部署模型下，当前实现能够提供：

1. RAG 引擎在进程内只初始化一次。
2. Reranker 在进程内不会被并发重复初始化。
3. 同一进程一次只进行一个全量索引重建。
4. 上传、删除和手动重建不会在同一进程内互相穿插。
5. 查询取得 Chroma、BM25、文档和统计信息的同版本快照。
6. 新索引构建失败不会替换当前可用索引。
7. 仍在使用旧索引的查询结束前，旧 collection 不会被主动清理。
8. MySQL 文档切片更新不会正常提交半套 SQL 结果。
9. 临时文件加原子替换可以避免读取半写入文件。
10. 文件、数据库或索引操作失败后会执行补偿和重新同步。

## 7. 当前边界与风险

### 7.1 所有 `threading.Lock` 都只在单进程内有效

如果使用 Gunicorn 多 worker、多个容器或多台机器，每个进程都有自己的：

- `_engine`
- `_mutation_lock`
- `_rebuild_lock`
- `_state_lock`
- `_reranker_lock`

因此两个 worker 仍可能同时上传、删除或重建。随机 collection 名称能减少直接覆盖，但 manifest、MySQL 切片快照、源文件和旧 collection 清理仍可能发生竞争。

### 7.2 每个进程可能各自加载一份模型

Embedding 模型和 Reranker 都是进程内对象。多 worker 会各自占用一份内存；如果使用 GPU，还可能导致显存不足。初始化锁只能阻止同一进程内重复加载，无法让多个进程共享 Python 模型对象。

### 7.3 Reranker 推理并发尚未限流

并发 `predict()` 可能带来以下问题：

- CPU 线程过度竞争；
- GPU 显存峰值过高；
- 底层模型对象并发安全性不确定；
- 单个重排请求拖慢其他普通请求。

当前应通过压测决定是否增加 `BoundedSemaphore` 或独立推理队列。

### 7.4 管理请求会同步等待完整重建

`_mutation_lock` 会覆盖上传或删除后的整次索引刷新。这样逻辑简单且一致性较强，但大型知识库下接口等待时间会变长，其他管理员变更也必须排队。

### 7.5 进程异常退出时补偿可能来不及执行

普通 Python 异常可以进入 `except` 完成补偿，但断电、容器强杀或进程崩溃可能发生在文件、索引和 MySQL 状态之间。当前的一致性检查可以发现问题，但还缺少可恢复任务记录和自动修复流程。

### 7.6 锁状态当前缺少可观测性

目前无法直接看到：

- 等待 `_mutation_lock` 或 `_rebuild_lock` 的请求数量；
- 获取锁耗时和持锁时长；
- 当前活动查询数量；
- 退役 collection 数量；
- Reranker 初始化耗时和推理并发数。

出现延迟尖峰时，排查仍主要依赖日志。

## 8. 后续优化建议

### 8.1 第一阶段：完善单进程并发与可观测性

优先级：高，适合当前架构直接实施。

1. 为 `_mutation_lock`、`_rebuild_lock` 和 Reranker 初始化增加等待耗时、持锁时长与结果日志。
2. 暴露活动查询数、索引版本、退役 collection 数和最后重建时间等指标。
3. 为重建设置明确的超时、失败状态和 request ID。
4. 在数据库异常路径显式执行 `rollback()`。
5. 增加以下并发测试：
   - 多线程首次查询只初始化一次 Reranker；
   - 查询使用旧快照时重建并切换新索引；
   - 旧查询完成前不删除旧 collection；
   - 两个重建请求不会并行执行；
   - 上传与删除不会交叉修改同一文件；
   - 重建失败时在线索引不变。
6. 压测 Reranker 并发推理；若资源竞争明显，使用 `threading.BoundedSemaphore(n)` 限制并行推理数。`n` 应通过 CPU、GPU 和延迟测试确定，不建议直接固定为 1。

### 8.2 第二阶段：将重建改为异步任务

优先级：中高，适用于文档增多或重建时间明显增长后。

建议将管理接口与重建执行拆开：

```text
管理员上传文档
  -> 保存文件和文档任务记录
  -> 返回 job_id 与 processing 状态
  -> Worker 串行消费 RAG 变更任务
  -> 构建新索引
  -> 原子发布索引版本
  -> 更新 MySQL 文档与切片状态
  -> 前端轮询或订阅任务进度
```

需要新增可恢复的任务表，例如 `rag_index_jobs`：

- `id`
- `operation`
- `document_id`
- `status`
- `source_signature`
- `target_index_version`
- `progress`
- `error_code`
- `error_message`
- `created_at`
- `started_at`
- `finished_at`

这样进程重启后可以识别未完成任务，而不是只依赖内存锁和请求线程。

### 8.3 第三阶段：引入 Redis 分布式锁

优先级：多 worker 或多实例部署前必须完成。

建议对“修改知识库并发布索引”的完整流程使用一个跨进程锁，例如：

```text
锁名称：rag:index:mutation
锁值：本次任务唯一 owner token
获取方式：SET key token NX PX ttl
续期方式：仅 owner 可续期
释放方式：Lua 脚本比较 token 后删除
```

关键要求：

1. 必须设置 TTL，避免持锁进程崩溃后形成永久死锁。
2. 重建可能超过 TTL 时必须实现看门狗续期。
3. 释放时必须校验 owner token，不能直接 `DEL`，否则旧任务可能误删新任务的锁。
4. Redis 不可用时，管理写操作应失败关闭，而不是绕过锁继续执行。
5. 锁只负责互斥，不应代替任务状态、数据库事务和幂等设计。

仅使用 Redis 锁仍存在“锁过期后旧任务继续运行”的风险。更严格的方案应加入 fencing token：每次成功获取锁都得到单调递增版本号，MySQL 和索引 manifest 只接受不小于当前版本的发布，防止失去锁的旧任务覆盖新任务。

### 8.4 第四阶段：显式索引版本与发布记录

优先级：中，建议与分布式部署一起实施。

将目前主要依赖 collection 名和文件签名的模式升级为显式版本：

- 每次重建生成唯一 `index_version`；
- manifest 记录版本、签名、collection、构建时间和构建节点；
- MySQL 保存当前已发布版本；
- 查询实例定期检查版本或通过 Redis Pub/Sub 接收版本切换通知；
- 只有成功发布的版本才能成为 current；
- 旧版本按引用、宽限时间和保留数量清理。

多进程下，每个进程仍有自己的内存快照。某个进程完成重建后，需要通知其他进程重新加载新 collection，否则不同 worker 可能在一段时间内返回不同版本结果。

### 8.5 第五阶段：增量索引与资源隔离

优先级：文档规模增大后实施。

1. 根据文件 SHA-256 和稳定 chunk ID 只更新发生变化的文档与切片，避免每次全量 Embedding。
2. 将构建 collection、Reranker 推理和普通 Web 请求放到不同 Worker 或服务中，分别设置资源配额。
3. 为 Embedding、Chroma、BM25 和 Reranker 分别设置超时、并发上限与降级策略。
4. 使用有界任务队列提供背压，避免大量上传同时耗尽内存。
5. 对相同内容签名的重复重建请求做幂等合并。
6. 为旧 collection 建立定时回收任务，并保留最近若干可回滚版本。

## 9. 推荐演进顺序

```text
当前单进程互斥锁与蓝绿切换
  -> 补齐并发测试、指标、超时和显式 rollback
  -> Reranker 推理压测与并发上限
  -> 重建任务异步化和持久化
  -> Redis 分布式锁与 owner token
  -> fencing token 和显式索引版本
  -> 多实例索引切换通知
  -> 增量索引、独立 Worker 与资源隔离
```

不要只把 `threading.Lock` 机械替换成 Redis 锁。正确的分布式方案应同时覆盖互斥、锁租约、任务恢复、幂等、版本发布、实例通知和旧版本回收。

## 10. 当前设计总结

当前方案的亮点是将不同职责拆给不同锁：

- 单例锁避免引擎重复创建；
- 状态锁保证同版本快照和原子切换；
- 重建锁避免重复构建高成本索引；
- Reranker 锁避免大模型重复初始化；
- 管理操作锁保证文件、数据库和索引变更按顺序执行。

同时，通过临时文件、`os.replace`、新旧 collection 切换、活动查询计数、MySQL 事务和失败补偿，形成了单进程环境下较完整的一致性保护链路。

它目前最明确的边界是：锁只在单个 Python 进程内生效。项目一旦切换到 Gunicorn 多 worker、多个容器或多台机器，就应优先引入持久化重建任务、Redis 分布式锁、fencing token 和显式索引版本，而不能继续把进程内互斥锁当作全局一致性保证。
