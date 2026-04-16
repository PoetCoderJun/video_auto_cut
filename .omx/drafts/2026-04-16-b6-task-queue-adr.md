# B6 Task Queue ADR 草案

- **日期**：2026-04-16
- **状态**：Review-ready draft
- **范围**：B 批次 Wave 3 / B6
- **基线计划**：`.omx/plans/2026-04-16-b-batch-backend-core-cleanup.md`

## 1. 背景

当前 `web_api/task_queue.py` 不是“简单触发器”或临时内存队列，而是已经承担了可恢复的持久化执行语义：队列表落在数据库/本地副本中，worker 通过 claim、heartbeat、reclaim 维持运行，API 路由则把任务队列和 job 状态机绑在一起。

B6 的目标不是先把队列“变简单”，而是先把现有语义说清楚，再决定未来是：

1. 继续保留 durable queue，但收窄职责；
2. 把 dispatch 与 execution 分开；
3. 还是在更强的任务契约之上扩展当前实现。

在 ADR 批准前，不应做破坏性模型替换。

## 1.1 非目标

本 ADR 当前**不**做以下事情：

- 不直接改 queue schema；
- 不把 queue 重写成内存队列；
- 不引入新的 task type；
- 不在本草案里顺手改 job state machine；
- 不把 `services/tasks.py` 的 dispatch/runtime 胶水直接替换成新框架。

当前目标仅是：把现状说清楚、把可选方向说清楚、把“什么时候可以继续实现”说清楚。

## 2. 当前不变量

### 2.1 Persistence

- 队列数据写入 `queue_tasks` 表，而不是内存结构。
- `init_task_queue_db()` 会创建 `queue_tasks`、`idx_queue_tasks_status_task_id`、`idx_queue_tasks_job_type_status`。
- `get_queue_db_path()` 会根据 Turso / 本地离线配置返回共享副本路径或本地副本路径，因此队列本身已经以“跨进程可见”的持久化资源存在。
- 这意味着队列语义必须考虑重启、重复启动、worker 崩溃和外部清理，而不能假设单进程生命周期。

### 2.2 Lease

- `claim_next_task()` 先调用 `reclaim_stale_running_tasks()`，再尝试 claim。
- claim 成功后，任务会被标记为 `RUNNING`，同时写入 `worker_id`、`started_at`、`updated_at`。
- `claim_next_task()` 采用 `BEGIN IMMEDIATE`，并在冲突时重试最多 3 次，说明它不是“读到一行就算拿到任务”，而是显式的 ownership 转移。
- 当前 claim 选择的是 `status = QUEUED` 且 `task_id ASC` 的最早任务；这更接近 FIFO-like 顺序，而不是复杂公平调度。

### 2.3 Reclaim

- `reclaim_stale_running_tasks()` 会扫描所有 `RUNNING` 任务，比较 `updated_at` 与 `task_queue_lease_seconds`。
- 超过 lease 的任务会被重新置回 `QUEUED`。
- 如果旧任务没有错误信息，reclaim 会填入 `TASK_HEARTBEAT_TIMEOUT`，以便后续诊断。
- 这条路径意味着队列天然需要“可恢复的失联 worker”模型，而不是只看一次执行是否返回。

### 2.4 Heartbeat

- `heartbeat_task()` 只接受 `status = RUNNING` 且 `worker_id` 匹配的任务。
- heartbeat 会刷新 `updated_at`，并在必要时清理 `TASK_HEARTBEAT_TIMEOUT` 标记。
- worker 侧的 heartbeat 线程由 `web_api/worker/runner.py` 启动，说明 queue 语义不是纯 API 端的入队器，而是 worker 生命周期的一部分。

### 2.5 Claim

- `claim_next_task()` 不是“弹出一个任务名”这么简单，而是先读 queue，再原子更新状态，再回读 claimed row。
- 返回给 worker 的不是 task id 而是完整任务记录，包含 `task_id`、`job_id`、`task_type`、`payload`、`worker_id` 等字段。
- 这说明后续执行逻辑依赖 queue 中的持久化上下文，而不是只依赖路由时传入的参数。

### 2.6 Task routing

- 当前队列只接受 `TASK_TYPE_TEST`。
- `enqueue_task()` 明确拒绝其他 task type。
- `web_api/services/tasks.py` 的 `TASK_DISPATCH` 目前也只映射 `TASK_TYPE_TEST -> run_test`。
- API 路由 `/jobs/{job_id}/test/run` 只会尝试入队 TEST 任务，并在入队前做 upload-ready 与 credit 检查。
- 这意味着当前队列不是通用 task bus，而是“TEST 流程的持久化执行通道”。

### 2.7 Job state coupling

- `queue_job_task()` 在 enqueue 成功后，会立刻把 job 更新为 `JOB_STATUS_TEST_RUNNING`，同时写 `stage_code = TEST_QUEUED`。
- `run_test()` 在 worker 侧会继续把 job 置为 `TEST_RUNNING`，并在识别、编辑、章节生成等阶段不断刷新 progress/stage。
- `run_test()` 最终会把 job 置为 `TEST_READY`，并写入字幕、章节与相关 artifact 路径。
- `confirm_test()` 会进一步把 job 置为 `TEST_CONFIRMED`，写出最终文本/字幕/章节文件。
- `render_completion` 最终才会把 job 置为 `SUCCEEDED`。
- 失败路径也会回写 job：不足额度会退回 `UPLOAD_READY`，其他异常通常落到 `FAILED`。
- 因此，队列不仅管理任务生命周期，还直接参与 job 状态机、错误回退和 artifact 落盘的耦合。

## 3. 为什么不能先写死成内存队列或极简单表

### 3.1 内存队列不符合现有可靠性语义

如果把当前实现退化为内存队列，会立刻丢掉以下能力：

- API / worker 重启后任务仍可恢复；
- worker 失联后可以靠 lease reclaim；
- heartbeat 可以区分“执行中”与“已经卡死”；
- claim 过程可以保证单任务 ownership；
- job 状态与任务执行结果可以持续落盘。

这些能力现在都已经在代码里使用，不是“未来可有可无的增强”。

### 3.2 极简单表会抹掉当前的运行语义

如果只保留一个“待处理记录表”，但没有 lease / heartbeat / reclaim / ownership 转移，那么：

- 任务是否已被某个 worker 拿走会变得不可靠；
- 卡死任务不会自动回收；
- 重试与重复执行很容易混在一起；
- job 状态机会失去和 worker 生命周期绑定的信号。

换句话说，简单表只能表示“有一条待办”，不能表示“这条待办已经被哪个 worker 持有、何时开始、是否超时、是否可回收”。

### 3.3 当前流程已经不是单点脚本模型

`/jobs/{job_id}/test/run`、`queue_job_task()`、worker `execute_task()`、`run_test()` 已经形成跨进程的可靠执行链。把 queue 简化成一次性缓存，会把问题从“队列复杂度”转成“难以诊断的任务丢失/重复执行/状态漂移”。

## 4. 可行的未来方向

### 方向 A：保留 durable queue，但把职责收窄为明确的 Test-only 可靠执行层

适合当前代码事实的保守方案。

- 保留数据库持久化、lease、heartbeat、reclaim、claim 顺序。
- 将队列明确定义为“Test flow 的可靠执行层”，而不是通用任务总线。
- 进一步收窄 public API，让 task type、payload shape、错误回退都显式化。
- 如果未来真的要支持更多 task type，再在这个 durable core 上扩展，而不是先去掉可靠性语义。

### 方向 B：拆分 dispatch 与 execution

如果未来任务种类增多，或者 API 侧与 worker 侧的职责边界需要更清晰，可以考虑把队列拆成两层：

- **Dispatch / control plane**：决定任务是否可入队、属于哪个 domain、写入哪种 job 状态；
- **Execution / runtime plane**：负责 claim、heartbeat、reclaim、执行与结果回写。

这一路径的价值是把“选任务”和“干活”拆开，避免 `services/tasks.py` 继续承担太多路由、状态更新和执行编排的胶水逻辑。

### 方向 C：如果未来证据表明队列只服务于一种稳定工作流，再把它显式命名为产品内专用 queue

这不是削弱可靠性，而是承认它是一个产品内工作流基础设施，而不是通用任务平台。

- 继续保留 durable semantics；
- 但不把它包装成“通用 task framework”；
- 将扩展面限制在明确的 job contract 内。

## 4.1 方向比较

| 方向 | 优点 | 代价/风险 | 适用条件 |
| --- | --- | --- | --- |
| A. 保留 durable queue，但收窄为 Test-only 执行层 | 最贴合现状；实现风险最低；保住 lease/reclaim/heartbeat | 仍保留一定历史胶水；“通用队列”形象会进一步弱化 | 未来一段时间仍以 Test 为唯一或绝对主任务 |
| B. 拆分 dispatch 与 execution | 边界最清晰；便于后续扩展多任务类型 | 改动面最大；需要先冻结 task contract 与 job-state coupling | 明确会扩展多个 task type，且需要更清楚的控制面 |
| C. 承认其为产品内专用 queue | 语义最诚实；有利于减少过度抽象 | 对未来通用化帮助有限；若后续扩任务仍要再演进 | 长期确认只服务单一工作流 |

## 5. 决策倾向

基于当前代码事实，B6 不应默认选择“最简单实现”。更合理的默认倾向是：

- 先保留 durable queue 的可靠性语义；
- 再决定它是继续作为 Test-only workflow queue，还是拆成更清晰的 dispatch/runtime 边界；
- 在没有新的可靠性需求证据前，不引入内存队列或无 lease 的简单表替代方案。

### 当前推荐

如果现在就要给出一个**默认推荐**，应优先选 **方向 A**：

- 把当前 queue 明确定义为 **Test-only durable execution layer**；
- 保留 `claim / heartbeat / reclaim / set_task_*` 语义；
- 先把 dispatch/payload/job-state coupling 记录清楚；
- 等出现第二类稳定任务后，再考虑是否演进到方向 B。

## 6. 风险

- **过度抽象**：为了“通用化”而引入比当前实现更复杂的任务框架。
- **误判边界**：把实际上依赖可靠性的 Test 流程，错误当成一次性后台触发器。
- **状态漂移**：如果 queue、job meta、artifact files 的耦合没有写清，后续改动容易互相打架。
- **未来扩展压力**：如果任务类型增长，当前 `TASK_TYPE_TEST` only 的实现可能需要正式的 contract/payload 设计，而不是临时补丁。

## 7. 后续工作建议

1. 为 `claim / reclaim / heartbeat / set_task_failed / set_task_succeeded` 增加或保留契约测试，覆盖 worker 崩溃、lease 超时、重复 claim、错误回退。
2. 明确 B6 最终输出是：
   - 继续保留 Test-only durable queue；或
   - 拆分 dispatch / execution；或
   - 在 durable core 上扩展正式 task contract。
3. 在任何 queue schema 变更前，先冻结当前 job 状态链：`UPLOAD_READY -> TEST_RUNNING -> TEST_READY -> TEST_CONFIRMED -> SUCCEEDED`，以及失败时退回 `UPLOAD_READY` / `FAILED` 的分支。
4. 如果未来要扩展 task type，先定义 payload 和 handler contract，再动 storage 结构。

## 7.1 进入实现前的决策门槛

只有同时满足下面几条，才建议把 B6 从 ADR 推进到实现：

1. 已明确选择方向 A / B / C 中的一个；
2. 已说明为什么没有选其他方向；
3. 已冻结当前 job 状态链和失败回边；
4. 已列出至少一组契约测试，覆盖 claim/reclaim/heartbeat 的核心不变量；
5. 若打算支持新 task type，已先给出 payload/handler contract 草图。

## 8. ADR 结论草案

**建议结论**：当前 B6 应把队列定义为“持久化、可 lease 回收、可 heartbeat、与 job 状态强耦合的 Test flow 执行层”，而不是通用任务平台；在没有新证据之前，不应改成内存队列或无可靠性语义的简单表。默认推荐方向 A：先保留 durable core，并把其职责诚实收窄为 Test-only；若后续要扩展，再从 durable core 出发拆分 dispatch 与 execution。
