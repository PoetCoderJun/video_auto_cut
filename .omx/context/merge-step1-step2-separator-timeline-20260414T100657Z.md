## Task Statement

将当前 Job Workspace 的 Step1 字幕页 + Step2 章节页合并为单一编辑页。章节不再是独立页面，而是字幕列表中的可拖动、可编辑、可删除“分隔符”；主界面始终保持熟悉的时间线/字幕流。

## Desired Outcome

- 上传后，AI 一次性准备字幕与章节草稿。
- 用户进入编辑区时只看到一个字幕时间线。
- 章节作为嵌入在字幕流里的 separator 行存在，可编辑标题、可调整位置、可删除/重建。
- 导出阶段仍能拿到稳定的 `topics` 数据，不破坏现有渲染链路。

## Known Facts / Evidence

- 前端仍维护 4 步流程，Step 3 明确为“确认章节”。证据：`web_frontend/components/job-workspace.tsx:137-141`。
- 前端存在独立的 `STEP2_READY` 章节草稿轮询与章节页字幕轮询。证据：`web_frontend/components/job-workspace.tsx:1374-1453`。
- Step1 确认动作会立即调用 `runStep2()`，说明用户操作上已经接近串行单流，只是 UI 仍分两页。证据：`web_frontend/components/job-workspace.tsx:1891-1898`。
- Step2 页面当前是独立章节卡片列表，每个章节承载标题编辑、相邻章节拖拽边界和字幕二次修改。证据：`web_frontend/components/job-workspace.tsx:2665-2863`。
- 后端 API 仍是明确分离的 `/step1/*` 与 `/step2/*` 协议，且 `step2_run` 只能在 `STEP1_CONFIRMED` 后触发。证据：`web_api/api/routes.py:299-356`。
- Step2 服务本质是生成并确认 `topics`/`block_range`，最终把任务推进到 `STEP2_CONFIRMED`。证据：`web_api/services/step2.py:157-280`。
- 浏览器导出配置从 `list_step2_chapters(job_id)` 读取 `topics`，说明渲染链路只依赖章节结果，不依赖章节 UI 形态。证据：`web_api/services/render_web.py:633-636`。
- 当前状态机和轮询逻辑显式区分 `STEP1_*` 与 `STEP2_*`。证据：`web_frontend/lib/job-status.ts:1-64`、`web_api/constants.py:27-82`。
- 已有测试保证 `run_step2()` 生成章节后停留在 `STEP2_READY`，等待人工确认。证据：`web_api/tests/test_step2_auto_confirm.py:12-76`。

## Constraints

- 优先降低用户负担，不要牺牲“熟悉的时间线编辑”。
- 章节是加分项，不应再主导主流程。
- 变更要兼容现有导出链路与 `topics` 数据消费。
- 按仓库约定，本次需求需要同步更新 `docs/requirements_todo.md`。

## Unknowns / Open Questions

- 是否保留后端 `STEP2_*` 状态作为内部实现细节，还是进一步收敛为单页编辑态。
- separator 的最小能力边界：是否允许删除后完全无章节、是否允许新增 separator、是否允许拖到开头/结尾。
- 单页中“保存并导出”的触发策略：进入页面前预生成章节，还是首次加载页面后后台补齐。

## Likely Touchpoints

- `web_frontend/components/job-workspace.tsx`
- `web_frontend/lib/job-status.ts`
- `web_frontend/lib/api.ts`
- `web_api/api/routes.py`
- `web_api/services/step2.py`
- `web_api/constants.py`
- `web_api/tests/test_step2_auto_confirm.py`
- `web_frontend/lib/job-status.test.mjs`
- `docs/requirements_todo.md`
