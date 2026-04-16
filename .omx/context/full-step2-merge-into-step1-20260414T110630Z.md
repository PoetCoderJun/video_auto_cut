## Task Statement

按新的用户要求，彻底取消独立 Step2。只保留一个 Step1：AI 生成字幕后进入唯一编辑页，用户在该页同时确认字幕真值和章节文件；确认落盘后直接进入导出。

## Desired Outcome

- UI 只保留“上传 -> Step1 编辑 -> 导出”。
- Step1 编辑页维护唯一的字幕 Ground Truth 与最终字幕文件。
- 章节调整使用新的 UI/交互方式，但不再作为独立 step / 独立确认页。
- Step1 完成时，人工一次性确认并落盘字幕文件与章节文件。
- 导出阶段直接消费 Step1 已确认的字幕与章节产物。

## Known Facts / Evidence

- 当前前端和后端都显式存在 `STEP2_*` 状态：`web_api/constants.py:27-83`、`web_frontend/lib/job-status.ts:1-64`。
- 当前仓库用文件和状态推断 `STEP2_READY/CONFIRMED`，且 `final_topics_path` 直接决定任务是否处于 Step2 阶段：`web_api/repository.py:684-758`。
- 当前 `/jobs/{job_id}/step2/run|get|confirm` 是独立路由，且 `step2_run` 只能在 `STEP1_CONFIRMED` 后触发：`web_api/api/routes.py:319-356`。
- 当前 `render/config` 只允许 `STEP2_CONFIRMED` 或 `SUCCEEDED`，说明导出门禁依赖 Step2：`web_api/api/routes.py:359-381`、`web_api/constants.py:61-65`。
- 当前导出配置直接从 `list_step2_chapters(job_id)` 读取 `topics`：`web_api/services/render_web.py:633-636`。
- 当前前端保存 Step1 后会立即触发 `runStep2()`，然后跳去独立章节页：`web_frontend/components/job-workspace.tsx:1891-1898`、`web_frontend/components/job-workspace.tsx:2666-2863`。

## Constraints

- 新方案不能再保留独立 Step2 概念，不论前台还是内部主状态机都应收敛到单 Step1 编辑完成后直接可导出。
- 仍需保留章节文件这一产物，因为用户明确要求“字幕文件和章节文件并落盘”。
- 自动分章生成允许保留，但必须被定义为 Step1 的最后一个内部子阶段，而不是独立 Step2。
- 不允许任何兼容桥接；目标态里不应残留 `STEP2_*` 状态、旧 step2 路由，或“先保留再迁移”的长期设计。
- 章节编辑交互可以完全重做，不必沿用当前 Step2 卡片 UI。
- 需要同步更新 `docs/requirements_todo.md`。

## Unknowns / Open Questions

- 章节文件最终仍沿用 `topics/final_topics.json` 命名，还是收口到 Step1 命名空间。
- 是否保留后台“自动分章生成”任务，但将其视为 Step1 内部子阶段，而非独立 Step2。
- 导出链路是否直接改读新的 Step1 章节产物，还是保留兼容桥接一段时间。

## Likely Touchpoints

- `web_frontend/components/job-workspace.tsx`
- `web_frontend/lib/job-status.ts`
- `web_frontend/lib/api.ts`
- `web_frontend/lib/workflow.ts`
- `web_api/constants.py`
- `web_api/api/routes.py`
- `web_api/repository.py`
- `web_api/services/step1.py`
- `web_api/services/step2.py`
- `web_api/services/render_web.py`
- `web_api/services/tasks.py`
- `web_api/tests/*`
- `docs/requirements_todo.md`
