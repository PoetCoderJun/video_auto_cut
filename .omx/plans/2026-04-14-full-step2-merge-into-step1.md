# Full Step2 Merge Into Step1

## Requirements Summary

- 彻底删除独立 `Step2`，不保留任何兼容桥接。
- 自动分章保留，但只能作为 `Step1` 的最后一个内部子阶段。
- 只保留一个 AI 生成字幕后的编辑页；该页同时编辑并最终确认字幕 Ground Truth 与章节文件。
- `Step1` 完成后直接进入导出。

## Grounding

- 现状显式依赖 `STEP2_*`：`web_api/constants.py:27-83`、`web_frontend/lib/job-status.ts:1-64`
- 现状有独立 `/step2/*` 路由：`web_api/api/routes.py:319-356`
- 现状仓库状态推断依赖 `final_topics_path` 与 `STEP2_*`：`web_api/repository.py:684-790`
- 现状 render 依赖 `list_step2_chapters(job_id)`：`web_api/services/render_web.py:633-636`
- 现状前端保存 Step1 后会进入独立章节页：`web_frontend/components/job-workspace.tsx:1891-1898`, `web_frontend/components/job-workspace.tsx:2666-2863`
- 现状 Step2 的核心价值是章节连续覆盖校验与规范化：`web_api/services/step2.py:239-280`

## RALPLAN-DR

### Principles

- 系统只保留单一 `Step1`；`Step2` 在状态、路由、任务、页面、导出门禁中全部删除。
- 字幕 Ground Truth 是唯一真值；章节始终是基于 `kept subtitles` 的完整连续分区。
- 自动分章仅作为 `Step1` 的最后一个内部子阶段，不形成独立工作流。
- `Step1` 编辑文档契约固定，最终确认必须由服务端基于 `block_range` 规范化章节后原子落盘。
- 不存在兼容桥接；旧 `Step2` 任务和旧 `step2/` 工件在 cutover 后直接判失效。

### Decision Drivers

- 用户硬约束要求彻底删除 `Step2`。
- 当前 `Step2` 已深嵌状态常量、路由、仓库推断与导出读取，必须整体重构。
- 当前章节连续覆盖校验是硬约束，删除 `Step2` 后必须转移进 `Step1`，不能弱化。

### Options

- A: 前端单页，后台保留 `STEP2_*`
Pros: 表面改动较小
Cons: 直接违反硬约束

- B: 彻底删除 `Step2`，`TASK_TYPE_STEP1` 一次完成字幕与章节草稿，`Step1` 页面统一编辑与确认
Pros: 满足产品心智和系统一致性
Cons: 需要重构执行链、仓库推断、前端页面和测试

- C: 删除 `Step2`，但允许字幕先就绪、章节后补
Pros: 首屏更快
Cons: 需要晚到草稿与额外一致性协议，第一版复杂度更高

### Chosen Direction

- 选 B。最终目标态：
  - 状态机：`CREATED -> UPLOAD_READY -> STEP1_RUNNING -> STEP1_READY -> STEP1_CONFIRMED -> SUCCEEDED | FAILED`
  - 任务链：仅 `TASK_TYPE_STEP1`
  - 页面：仅一个 `Step1` 编辑页
  - 导出：`STEP1_CONFIRMED` 后直接进入

## Target Contract

### Step1 Document

- `GET /jobs/{job_id}/step1` 返回：
  - `lines`
  - `chapters`
  - `document_revision`

- `PUT /jobs/{job_id}/step1/confirm` 请求体返回：
  - `lines`
  - `chapters: [{ chapter_id, title, block_range }]`
  - `expected_revision`

### Canonicalization

- 服务端不信任客户端 chapter `start/end`。
- 服务端仅基于 `kept subtitles + block_range` 规范化 chapters。
- 服务端重算每个 chapter 的 `start/end` 后再写最终章节文件。

### Hard Invariants

- 任一结构性字幕编辑后，前端内存中的 chapters 仍必须是对全部 kept subtitle blocks 的完整连续分区。
- 不存在“字幕已变、章节待修复”的持久状态。
- `STEP1_READY` 必须要求 `lines_draft + chapters_draft` 同时存在。
- `STEP1_CONFIRMED` 必须要求 `final_step1 + final_chapters + .confirmed` 同时存在。

## How To Truly Remove Step2

### Status Machine

- 删除 `JOB_STATUS_STEP2_RUNNING/READY/CONFIRMED`
- 删除 `PROGRESS_STEP2_*`
- 删除 `TASK_TYPE_STEP2`
- `STEP1_RUNNING` 细分为内部 `stage.code`：
  - `TRANSCRIBING`
  - `OPTIMIZING_SUBTITLES`
  - `GENERATING_CHAPTERS`

### Routes

- 删除：
  - `POST /jobs/{job_id}/step2/run`
  - `GET /jobs/{job_id}/step2`
  - `PUT /jobs/{job_id}/step2/confirm`
- 重写：
  - `GET /jobs/{job_id}/step1` 返回完整编辑文档
  - `PUT /jobs/{job_id}/step1/confirm` 一次性提交字幕与章节确认
- 修改 render gate：
  - `GET /jobs/{job_id}/render/config` 允许 `STEP1_CONFIRMED | SUCCEEDED`
  - `POST /jobs/{job_id}/render/complete` 允许 `STEP1_CONFIRMED | SUCCEEDED`

### Task Queue / Execution

- 删除 `queue_job_task(..., TASK_TYPE_STEP2)` 与 `run_step2()` 链路
- `TASK_TYPE_STEP1` 成为唯一 AI 处理入口
- `TASK_TYPE_STEP1` 内部一次完成字幕生成、文本优化、自动分章

### Repository

- 删除 `final_topics_path`、`_step2_confirmed_path()` 及所有 `STEP2_*` 推断分支
- 新文件语义：
  - `step1/lines_draft.json`
  - `step1/chapters_draft.json`
  - `step1/final_step1.json`
  - `step1/final_step1.srt`
  - `step1/final_chapters.json`
  - `step1/.confirmed`
- 推断规则：
  - 有 `lines_draft + chapters_draft` -> `STEP1_READY`
  - 有 `final_step1 + final_chapters + .confirmed` -> `STEP1_CONFIRMED`

### Render

- `render_web.py` 从 `list_step1_chapters(job_id)` 读取章节
- render 不再读取任何 `step2` 产物

### Cutover

- 部署后检测到旧 `TASK_TYPE_STEP2` 队列项：直接标失败，错误文案要求重新进入新 Step1
- 检测到旧 `step2/` 工件或旧 `STEP2_*` 任务状态：直接判任务失效，要求重跑新流程
- 不做旧工件回读，不做兼容桥接

## Acceptance Criteria

- 全仓不再存在 `STEP2_*`、`TASK_TYPE_STEP2`、`/step2/*`
- `TASK_TYPE_STEP1` 完成后直接进入 `STEP1_READY`
- `GET /step1` 同时返回字幕草稿、章节草稿、`document_revision`
- 前端任何结构性字幕编辑后，内存中的 chapters 仍是合法连续分区
- `PUT /step1/confirm` 必须要求 `expected_revision`
- `PUT /step1/confirm` 只接受 `chapter_id/title/block_range`
- 即使前端传入 chapter 时间偏了，只要 `block_range` 合法，最终 `final_chapters.json` 仍由服务端规范化生成
- 非法 coverage 会在 Step1 confirm 被拒绝，且不会写入半成品
- `render/config` 在 `STEP1_CONFIRMED` 成功返回
- 前端工作流只剩“上传 / 编辑 / 导出”三段

## Implementation Steps

1. 收口常量与共享类型
路径：
  - `web_api/constants.py`
  - `web_frontend/lib/job-status.ts`
  - `web_frontend/lib/workflow.ts`
  - `web_frontend/lib/api.ts`

2. 删除 Step2 任务链，把自动分章并入 `TASK_TYPE_STEP1`
路径：
  - `web_api/services/tasks.py`
  - `web_api/task_queue.py`
  - `web_api/services/step1.py`
  - `web_api/services/step2.py`

3. 重写 repository 文件模型与状态推断
路径：
  - `web_api/repository.py`

4. 固化 Step1 文档契约与确认规范化逻辑
路径：
  - `web_api/api/routes.py`
  - `web_api/schemas.py`
  - `web_api/services/step1.py`

5. 重构前端单一编辑页和 no-stale reducer
路径：
  - `web_frontend/components/job-workspace.tsx`
  - `web_frontend/lib/job-draft-storage.ts`

6. 修改 render 读取与 cutover 失效策略，补测试
路径：
  - `web_api/services/render_web.py`
  - `web_api/tests/*`
  - `docs/requirements_todo.md`

## Risks And Mitigations

- 风险：Step1 耗时变长
缓解：拆细 `stage.code/message`，让用户看到转写、优化、分章进度

- 风险：前端结构编辑导致章节错乱
缓解：单一 reducer 保证每次编辑后 chapters 立即重分区，服务端提交前再校验

- 风险：客户端伪造章节时间导致漂移
缓解：服务端完全忽略客户端 `start/end`，只信任 `block_range`

- 风险：cutover 后旧任务残留引发混乱
缓解：明确失效策略，不做桥接读取

- 风险：确认过程出现半成功落盘
缓解：Step1 confirm 先校验 revision 与 coverage，再统一写 final 文件与 `.confirmed`

## Verification

- `python -m unittest discover web_api/tests -p "test_*.py"`
- `cd web_frontend && npx tsc --noEmit`
- `npm --prefix web_frontend run build`

### Must-pass Regression

- `STEP1_READY` 必须要求 `lines_draft + chapters_draft`
- `STEP1_CONFIRMED` 必须要求 `final_step1 + final_chapters + .confirmed`
- Step1 confirm 的服务端规范化会重算 `start/end`
- 非法连续覆盖会被拒绝
- render 仅依赖 Step1 chapters
- 旧 `TASK_TYPE_STEP2` / 旧 `step2/` 工件被直接判失效
- 前端 reducer 在删除句子、恢复句子、拖动 separator、删除 separator 后仍保持连续分区

### Manual Flow

- 上传视频
- 等待 Step1 完成 AI 生成
- 进入唯一编辑页
- 修改字幕与 separator
- 确认并落盘
- 直接进入导出

## ADR

- Decision
彻底删除独立 Step2，将自动分章并入单一 Step1 的最后一个内部子阶段；以单一文档契约完成字幕和章节确认。

- Drivers
用户要求无 Step2、无桥接、Step1 完成后直接导出。

- Alternatives Considered
保留后台 Step2；允许章节晚到；取消自动分章。

- Why Chosen
只有当前方案同时满足产品心智、系统一致性和可验证性。

- Consequences
需要一次性重构核心流程，但之后只有一个编辑真值、一个确认点、一个导出门禁。

- Follow-ups
定死前端 timeline reducer 规则；执行时同步更新 `docs/requirements_todo.md`；实现前按后端先行、前端跟进拆分实施单。

## Available-Agent-Types Roster

- `planner`
- `architect`
- `critic`
- `executor`
- `test-engineer`
- `verifier`
- `build-fixer`

## Follow-up Staffing Guidance

- `ralph` lane
建议顺序：
  - `architect/high` 先锁定 Step1 文档契约与 cutover 失效语义
  - `executor/high` 先改后端常量、repository、step1 confirm、render gate
  - `executor/high` 再改前端单页编辑器与 no-stale reducer
  - `test-engineer/medium` 补回归矩阵
  - `verifier/high` 验证 cutover、确认原子性与导出

- `team` lane
  - Worker 1: `executor/high` 负责 `web_api` 状态机、route、repository、render、tests
  - Worker 2: `executor/high` 负责 `web_frontend` 单页编辑器、API client、workflow/status、tests
  - Worker 3: `test-engineer/medium` 负责 cutover、reducer、render regression
  - Leader: `architect/high` 盯 contract / canonicalization / no-stale 不变量

## Launch Hints

- `ralph`
把这份计划作为唯一 spec，按“后端收口 -> 前端单页 -> cutover/test 收尾”顺序执行

- `team`
以后端 lane 和前端 lane 并行，最后由 verifier 汇总验证：
  - 后端 lane：`web_api/constants.py`, `web_api/api/routes.py`, `web_api/repository.py`, `web_api/services/step1.py`, `web_api/services/render_web.py`, `web_api/services/tasks.py`
  - 前端 lane：`web_frontend/components/job-workspace.tsx`, `web_frontend/lib/api.ts`, `web_frontend/lib/job-status.ts`, `web_frontend/lib/workflow.ts`

## Team Verification Path

- 证明全仓已无 `STEP2_*`、`TASK_TYPE_STEP2`、`/step2/*`
- 证明 `STEP1_READY` 与 `STEP1_CONFIRMED` 的新判定完全基于 Step1 draft/final 工件
- 证明服务端确认时只信任 `block_range` 并重算章节时间
- 证明旧 Step2 队列项和旧工件在 cutover 后会明确失效，不会静默卡死
- 证明 render 读取的是 Step1 chapters，且章节卡片/进度条行为不回退
