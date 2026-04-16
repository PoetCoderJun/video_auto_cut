# Merge Step1/Step2 Into Single Timeline Plan

## Requirements Summary

- 合并 `Step1` 字幕编辑页和 `Step2` 章节页为单一时间线编辑页。
- 章节降级为字幕列表中的 separator 行，可编辑标题、可删除、可拖动相邻边界。
- 用户始终只面对一个“字幕时间线”，不再切换到独立“确认章节”页面。
- 导出继续消费 `topics`，不破坏现有 `STEP2_*` 内部实现和渲染链路。

## Grounding

- 当前前端仍是 4 步流程，含独立“确认章节”步骤：`web_frontend/components/job-workspace.tsx:137`
- 当前存在独立 `STEP2_READY` 章节草稿轮询与章节页字幕轮询：`web_frontend/components/job-workspace.tsx:1374`
- 当前前端保存链路拆成 `confirmStep1 -> runStep2` 与 `confirmStep2`：`web_frontend/components/job-workspace.tsx:1891`
- 当前 Step2 UI 是独立章节卡片页：`web_frontend/components/job-workspace.tsx:2668`
- 现有 API 明确分离 `/step1/*` 与 `/step2/*`：`web_api/api/routes.py:299`
- `confirm_step1()` 会推进到 `STEP1_CONFIRMED`：`web_api/services/step1.py:232`
- `confirm_step2()` 要求章节连续覆盖全部 kept subtitles：`web_api/services/step2.py:239`
- 导出从 `list_step2_chapters(job_id)` 读取 `topics`：`web_api/services/render_web.py:633`

## RALPLAN-DR

### Principles

- 用户只看一个时间线，字幕是主对象，章节只是嵌入式 separator。
- `kept subtitles` 是唯一 canonical source；separator/chapters 只能是派生分区。
- 一致性由服务端裁决：`subtitle_revision` 由服务端计算并返回。
- 低风险优先：保留现有 Step2 生成与导出消费链路，只补最小协议与状态映射。
- finalize 必须显式、可校验、不可隐式修复 stale separator。

### Decision Drivers

- 降低认知负担。
- 维持导出继续依赖 `topics`：`web_api/services/render_web.py:633`
- 解决当前 `confirmStep1/confirmStep2` 与单页编辑的门禁冲突：`web_api/api/routes.py:299`, `web_api/api/routes.py:345`

### Options

- A: 纯前端单页合并，继续串行调旧接口
Pros: 表面改动少
Cons: 原子保存、晚到草稿、门禁错位都不稳

- A': 前端单页合并 + 最小协议修补
Pros: 风险最低；能补 revision、一致性和原子 finalize；导出链路不动
Cons: 要增加少量 schema / route / service 编排

- C: 重写整个状态机
Pros: 概念最统一
Cons: 波及面过大，不符合当前低风险目标

## ADR

- Decision
采用 A'：前端单页时间线 + 服务端权威 `subtitle_revision` + 新增 `timeline/finalize` 组合接口。

- Drivers
降低用户心智负担；保留 `topics` 导出依赖；修复旧双接口门禁与单页异步编辑的冲突。

- Alternatives Considered
纯前端合并继续调用旧接口；彻底重写状态机；保持双页现状。

- Why Chosen
A' 能以最小改动同时解决页面合并、revision 一致性、stale 控制和原子 finalize。

- Consequences
UI 变简单，但内部仍保留 `STEP2_*` 作为实现细节；系统新增服务端 revision 机制；旧接口保留一段时间做兼容。

- Follow-ups
定义并测试 `subtitle_revision` 算法；让 `getStep2` 返回 revision；实现后再评估是否继续收敛状态机。

## Data Invariants

- `kept subtitles` 是 canonical source。
- separator 是对 kept subtitle blocks 的连续分区。
- chapters 必须连续覆盖全部 kept blocks。
- chapters 不允许空洞、重叠、空章节。
- 系统必须始终至少保留 1 个合法章节。
- `timeline/finalize` 成功后，DB 中 step2 chapters 与 `final_topics.json` 必须一致。

## UI Substates

- `subtitle_editable`
触发：`STEP1_READY`，但还没有匹配当前 revision 的 separator 草稿。

- `separators_generating`
触发：结构性编辑后触发重生成，或后端处于 `STEP2_RUNNING`。

- `separators_ready`
触发：`getStep2()` 返回且 `subtitle_revision` 与当前 step1 revision 一致。

- `separators_stale`
触发：`STEP2_READY` 后继续做结构性编辑，或收到 revision 不匹配的晚到草稿。
规则：不允许 finalize；必须等待重生成完成，或显式“按当前 kept subtitles 重建 separators”。

## Protocol Decisions

- `subtitle_revision` 由服务端基于规范化 kept lines 序列计算，并随 `getStep1/getStep2` 返回。
- 前端只回传“当前编辑所基于的 revision”。
- 晚到 `step2 draft` 若 revision 不匹配，直接丢弃并标记 `separators_stale`，不得覆盖当前编辑态。
- 新增 `PUT /jobs/{job_id}/timeline/finalize`。
- `timeline/finalize` 仅允许状态：
  - `STEP1_READY`
  - `STEP2_READY`
- 在 `STEP1_CONFIRMED` / `STEP2_RUNNING` 下不接受新的 finalize，只允许等待或刷新。
- 单页新流程只走 `timeline/finalize`；旧 `/step1/confirm` 与 `/step2/confirm` 仅保兼容。

## Interaction Rules

- separator 删除默认向前合并；若删除的是第一个 separator，则并入后一章。
- 只剩 1 个章节时，删除 separator 禁用。
- 拖动只允许落在相邻字幕边界。
- 自动重生成只由结构性编辑触发：删除/恢复 kept set；纯文本编辑不触发。
- 自动重生成采用 debounce + 串行化，避免频繁重复 `runStep2`。

## Acceptance Criteria

- 顶部步骤不再出现独立“确认章节”。
- 编辑区始终是单时间线页，章节以内嵌 separator 行展示。
- `getStep1/getStep2` 都返回服务端生成的 `subtitle_revision`。
- revision 不匹配的晚到 Step2 草稿不会覆盖当前 UI，只会标记 `separators_stale`。
- `STEP2_READY` 后继续删句/恢复句会进入 `separators_stale`，且 finalize 按钮禁用。
- separator 删除与拖动后，导出的 chapters 始终满足完整 coverage 且至少 1 章。
- `timeline/finalize` 成功后，任务进入可导出态，且 DB step2 chapters 与 `final_topics.json` 一致。
- `timeline/finalize` revision 冲突或 coverage 非法时，返回错误且不推进到可导出态。
- 导出继续能读取最新有效 `topics`。

## Implementation Steps

1. 前端先合并页面骨架
路径：`web_frontend/components/job-workspace.tsx`, `web_frontend/lib/job-status.ts`
将独立 Step3 页面收敛为单页 timeline 容器，但先不切换提交协议。

2. 服务端补 revision 权威返回
路径：`web_api/services/step1.py`, `web_api/services/step2.py`, `web_api/api/routes.py`, `web_api/schemas.py`
让 `getStep1/getStep2` 返回 `subtitle_revision`。

3. 前端接入 substate 与 stale 规则
路径：`web_frontend/components/job-workspace.tsx`, `web_frontend/lib/api.ts`
修正当前 `STEP2_READY` 盲写草稿逻辑，接入 revision 对比、late draft discard、stale UI。

4. 新增 `timeline/finalize`
路径：`web_api/schemas.py`, `web_api/api/routes.py`, `web_api/services/step1.py`, `web_api/services/step2.py`
增加组合 schema、route 和单编排服务入口。

5. 替换前端提交路径
路径：`web_frontend/lib/api.ts`, `web_frontend/components/job-workspace.tsx`
单页主按钮统一调用 `finalizeTimeline()`，不再走两段式保存。

6. 一致性与回归测试
路径：`web_api/tests/`, `web_frontend/lib/job-status.test.mjs`, 视需要新增前端 timeline/reducer 测试
覆盖 revision 冲突、late draft discard、stale 禁止 finalize、coverage 非法、DB/file 一致性。

## Risks And Mitigations

- 风险：晚到草稿覆盖新编辑态
缓解：revision 以服务端为准；不匹配即丢弃并标 stale

- 风险：结构性编辑频繁触发重生成
缓解：仅结构性编辑触发；debounce；同一时刻只允许一个生成任务在途

- 风险：finalize 出现半成功语义
缓解：通过服务层单编排入口，先校验后统一提交最终可导出状态

- 风险：实现时留下 DB / `final_topics.json` 脏不一致
缓解：把“先校验、再统一提交”的顺序写死，并补一致性回归

## Verification

- `cd web_frontend && npx tsc --noEmit`
- `npm --prefix web_frontend run build`
- `python -m unittest discover web_api/tests -p "test_*.py"`
- 手工验证：
上传后只进入单时间线页；separator 初始为生成中；匹配 revision 的草稿到达后插入；`STEP2_READY` 后删句/恢复句进入 stale；late draft 不覆盖；finalize 成功后直接进入导出；导出读取最新 topics。

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
`architect/high` 定协议边界 -> `executor/high` 实现后端 finalize + revision -> `executor/high` 实现前端单页 timeline -> `test-engineer/medium` 补测试 -> `verifier/high` 做最终核验

- `team` lane
Worker 1: `executor/high` 负责 `web_api` 协议、schema、service、tests
Worker 2: `executor/high` 负责 `web_frontend` timeline UI、state、API client
Worker 3: `test-engineer/medium` 负责回归矩阵与验收脚本
Leader: `architect/high` 盯 revision / stale / finalize 原子语义

## Launch Hints

- `ralph`
按“服务端 revision -> 前端单页状态 -> finalize -> 测试验证”顺序执行本计划。

- `team`
以后端 lane 与前端 lane 并行，最后统一走 verifier 收口。

## Team Verification Path

- 证明 `getStep1/getStep2` revision 返回一致且可比较
- 证明 late draft 不覆盖新 revision
- 证明 stale 禁止 finalize
- 证明 finalize 成功后 DB step2 chapters 与 `final_topics.json` 一致
- 证明导出读到的是 finalize 后最新 topics，而非旧草稿
