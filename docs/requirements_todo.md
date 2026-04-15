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
- 2026-04-14: 按最新 `$ralplan` 将当前 Step1 PI 编辑链路收敛为一个干净 PI runner，并仅保留 3 个 editing skills（`delete` / `polish` / `chapter`）；移除 chunking 主设计与显式 JSON repair/fixup prompt 依赖，把完整任务 framing 收敛到统一 system prompt，并保持 runner 与 skills 解耦。相关路径：`video_auto_cut/editing/auto_edit.py`、`video_auto_cut/editing/pi_agent_remove.py`、`video_auto_cut/editing/pi_agent_polish.py`、`video_auto_cut/editing/pi_agent_boundary.py`、`video_auto_cut/editing/pi_agent_chunking.py`、`video_auto_cut/editing/pi_agent_merge.py`、`video_auto_cut/orchestration/pipeline_service.py`、`video_auto_cut/orchestration/full_pipeline.py`、`web_api/services/step1.py`、`web_api/services/step2.py`、`skills/video-auto-cut-human-loop/SKILL.md`；实施 PRD 已落档：`docs/plans/2026-04-14-pi-runner-three-skills.md`
- 2026-04-14: 针对上条需求的 Architect review 补充硬约束：唯一 `run_pi_edit(...)`/canonical runner 产出编辑结果；先冻结 `delete` / `polish` / `chapter` 三个 skill 的公开合同；主路径不得再以 chunk/boundary/reconcile 为默认编排，也不得依赖显式 JSON repair/fixup；章节 invariant 应从 `web_api` 下沉到 shared domain / runner output contract。相关路径：`video_auto_cut/editing/auto_edit.py`、`video_auto_cut/editing/pi_agent_remove.py`、`video_auto_cut/editing/pi_agent_polish.py`、`video_auto_cut/editing/pi_agent_boundary.py`、`video_auto_cut/editing/pi_agent_chunking.py`、`video_auto_cut/editing/pi_agent_merge.py`、`video_auto_cut/orchestration/pipeline_service.py`、`video_auto_cut/orchestration/full_pipeline.py`、`web_api/services/step1.py`、`web_api/services/step2.py`
- 2026-04-14: 按第一性原则审视 PI agent / 剪辑链路，目标是将剪辑能力解耦为 Codex 可直接运行的 canonical Step1 seam；`$ralplan` 已收敛为 approval-ready 方案，下一步按单一 `run_step1_artifacts(...)` 入口、Python 3.10+ runtime floor、topic/import 隔离、deployment-policy 脱钩与 chapter invariant 下沉执行。相关路径：`video_auto_cut/editing/auto_edit.py`、`video_auto_cut/editing/__init__.py`、`video_auto_cut/orchestration/pipeline_service.py`、`video_auto_cut/orchestration/full_pipeline.py`、`web_api/services/step1.py`、`web_api/services/step2.py`、`skills/video-auto-cut-human-loop/SKILL.md`
- 2026-03-27: 上传前导出能力校验从阻断式一帧试渲染改为 `canRenderMediaOnWeb()` 轻量能力检查，减少误判同时保留前置提示。相关路径：`web_frontend/lib/upload-render-validation.ts`、`web_frontend/components/home-page-client.tsx`、`web_frontend/components/job-workspace.tsx`

## Done
- 2026-03-25: 初始化需求 todo 文档，并约定由代理持续维护。
- 2026-04-14: 盘点当前仓库源码内维护的 prompts，并归档输出到 `docs/current_prompts_inventory.txt`，便于后续统一治理 prompt source of truth。相关路径：`docs/current_prompts_inventory.txt`、`video_auto_cut/editing/auto_edit.py`、`video_auto_cut/editing/pi_agent_remove.py`、`video_auto_cut/editing/pi_agent_boundary.py`、`video_auto_cut/editing/pi_agent_polish.py`、`video_auto_cut/editing/topic_segment.py`、`video_auto_cut/editing/llm_client.py`、`video_auto_cut/asr/qwen3_asr.py`、`web_api/services/render_web.py`
- 2026-04-14: 彻底删除独立 Step2，将自动分章并入 Step1 的最后一个内部子阶段；`GET/PUT /step1` 收口为统一文档契约，Step1 编辑页在同一时间线内完成字幕和章节确认，确认后直接进入导出，不保留任何 Step2 兼容桥接。相关路径：`web_frontend/components/job-workspace.tsx`、`web_frontend/lib/api.ts`、`web_frontend/lib/job-status.ts`、`web_frontend/lib/workflow.ts`、`web_api/constants.py`、`web_api/api/routes.py`、`web_api/repository.py`、`web_api/services/step1.py`、`web_api/services/render_web.py`、`web_api/services/tasks.py`
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
