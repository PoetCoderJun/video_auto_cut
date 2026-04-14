# Requirements TODO

这个文档用于持续记录产品需求、实现进度和后续动作，方便代理和人工协作时保持同一份事实来源。

## 使用规则
- 新需求进入时，先补到 `Backlog`。
- 开始实现时，把条目移动到 `In Progress`，并补充负责人、相关路径或备注。
- 完成并验证后，移动到 `Done`，注明完成日期和关键结果。
- 如果需求被取消或延期，在条目后补充原因，不要直接删除历史记录。

## Backlog
- 暂无

## In Progress
- 2026-03-27: 上传前导出能力校验从阻断式一帧试渲染改为 `canRenderMediaOnWeb()` 轻量能力检查，减少误判同时保留前置提示。相关路径：`web_frontend/lib/upload-render-validation.ts`、`web_frontend/components/home-page-client.tsx`、`web_frontend/components/job-workspace.tsx`

## Done
- 2026-03-25: 初始化需求 todo 文档，并约定由代理持续维护。
- 2026-04-14: 修复 OSS 直传确认绑定、公共端点限流、JSON 请求体大小约束和 DashScope 结果 URL scheme 校验，收敛对象串改、暴力刷接口与本地文件读取风险。相关路径：`web_api/api/routes.py`、`web_api/services/jobs.py`、`web_api/app.py`、`web_api/schemas.py`、`video_auto_cut/asr/dashscope_filetrans.py`
- 2026-04-14: 修复 `claim_next_task()` 对 Turso 瞬时错误的函数内自动重试风险，避免队列领取在提交边界重复回放；保留 worker loop 外层重试。相关路径：`web_api/task_queue.py`、`web_api/tests/test_task_queue.py`
- 2026-04-13: 补充 `README.md` 的 Quick Start，新增 `uv` / `pi` 安装方式与 `.env` 凭证加载说明，并注明当前仓库尚未切到 `uv sync` 项目结构。相关路径：`README.md`
- 2026-04-13: 修复浏览器端 `AudioData.copyTo(...f32-planar)` 兼容异常导致的上传/导出报错，补充音频链路识别与友好提示；上传前能力校验改为逐项兜底。相关路径：`web_frontend/lib/browser-audio-pipeline-error.ts`、`web_frontend/lib/upload-render-validation.ts`、`web_frontend/lib/remotion/rendering.ts`、`web_frontend/components/job-workspace.tsx`
- 2026-04-13: 按需求取消浏览器导出阶段的“静音兜底”降级；当音频编码链路不可用或不稳定时，上传前校验与导出都直接报错，不再生成无声文件。相关路径：`web_frontend/lib/browser-audio-pipeline-error.ts`、`web_frontend/lib/upload-render-validation.ts`、`web_frontend/lib/remotion/rendering.ts`、`web_frontend/components/job-workspace.tsx`
- 2026-04-13: 按需求回退 Job Workspace 两步式字幕/章节流程与对应状态轮询，恢复“确认字幕后自动生成章节”和章节页相邻拖拽调整方式。相关路径：`web_frontend/components/job-workspace.tsx`、`web_frontend/lib/job-status.ts`、`web_frontend/lib/job-status.test.mjs`、`web_api/api/routes.py`
- 2026-03-27: 删除上传前阻断式“一帧导出探测”，避免浏览器本地预检查误判导致上传被拦截；保留前端上传失败上报。相关路径：`web_frontend/components/home-page-client.tsx`、`web_frontend/components/job-workspace.tsx`、`web_frontend/lib/api.ts`
- 2026-03-27: `/invite` 公共邀请入口新增 5 个领取名额，线上 `public_invite_settings.max_claims` 从 100 调整到 105。
- 2026-03-27: `/invite` 公共邀请入口再次新增 3 个领取名额，线上 `public_invite_settings.max_claims` 从 105 调整到 108。
- 2026-03-27: Job Workspace 重构为两步式流程。Step1 改为保存字幕后停留当前页，由用户显式触发 Step2 生成章节；Step2 改为基于字幕列表的章节编辑，支持左侧范围拖动控件、章节拆分和删除合并。相关路径：`web_frontend/components/job-workspace.tsx`、`web_frontend/lib/job-status.ts`、`web_api/api/routes.py`
- 2026-03-28: 修正章节确认页状态流转，`STEP2_READY` 改为纯人工编辑态，不再继续自动轮询推进，避免页面表现成“还在自动生成/自动跳转”。相关路径：`web_frontend/lib/job-status.ts`、`web_frontend/lib/job-status.test.mjs`
- 2026-03-29: 本机 Ghostty 显式新增 `Ctrl+V` 原样转发到终端应用，确保 Codex TUI 可直接从系统剪贴板附加图片。相关配置：`~/.config/ghostty/config`
