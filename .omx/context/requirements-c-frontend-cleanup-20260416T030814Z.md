# Context Snapshot: requirements-c-frontend-cleanup

## task statement
创建一个工作分支，并处理 `docs/requirements_todo.md` 中的 C 批次前端问题（C1-C4）。当前回合按 `$ralplan` 先做共识规划。

## desired outcome
- 已创建独立工作分支承载后续修改。
- 明确 C1-C4 的实现顺序、代码触点、验证路径与风险。
- 在需求清单中把本轮处理状态更新到合适栏目，便于后续执行。

## known facts/evidence
- `docs/requirements_todo.md` 中 C 批次包含四项：
  - C1 收口 API client 重复入口
  - C2 收口 `job-workspace.tsx` 局部状态辅助函数
  - C3 统一前端公共小工具
  - C4 明确导出预览比例展示规则
- 相关前端路径主要集中在 `web_frontend/lib/api.ts`、`web_frontend/components/job-workspace.tsx`、`web_frontend/components/export-frame-preview.tsx` 及多个 `web_frontend/lib/remotion/*` 工具文件。
- 仓库当前工作树本身已有大量未提交修改；新分支将承接当前工作树状态，而非从干净树开始。
- 仓库已存在历史 context snapshots，但没有直接对应 C 批次前端清理的 snapshot。

## constraints
- 遵守仓库要求：需求状态以 `docs/requirements_todo.md` 为单一事实来源。
- 前端改动需要至少运行 `cd web_frontend && npx tsc --noEmit` 和 `npm --prefix web_frontend run build`。
- 当前回合使用 `$ralplan`，先完成 consensus 计划，不直接进入实现。

## unknowns/open questions
- C1-C4 是否应作为一个批次整体推进，还是拆成独立提交/独立验证。
- `request` 与 `requestWithExplicitToken` 的差异是否仍被某些调用点依赖。
- 比例展示规则在导出预览中更适合“精确比例”还是“查表近似名”。
- 若统一公共小工具，最合适的宿主模块是现有 util 文件还是新增 shared frontend utils。

## likely codebase touchpoints
- `docs/requirements_todo.md`
- `web_frontend/lib/api.ts`
- `web_frontend/components/job-workspace.tsx`
- `web_frontend/components/export-frame-preview.tsx`
- `web_frontend/lib/job-draft-storage.ts`
- `web_frontend/lib/remotion/export-bitrate.ts`
- `web_frontend/lib/remotion/typography.ts`
- `web_frontend/lib/remotion/overlay-controls.ts`
- `web_frontend/lib/source-video-guard.ts`
