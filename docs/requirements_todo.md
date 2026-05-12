# Requirements TODO

这个文档只记录当前还没做完的需求，以及非常近期已经完成、仍可能影响下一轮迭代判断的改动。旧历史请查 Git。

## 使用规则
- 新需求进入时，先补到 `Backlog`。
- 开始实现时，把条目移动到 `In Progress`，并补充负责人、相关路径或备注。
- 完成并验证后，移动到 `Recent Done`，注明完成日期和关键结果。
- `Recent Done` 只保留最近几天或当前上下文仍高频相关的记录；更早的完成项及时清理。

## Backlog

## In Progress
- 2026-05-12: **修复 delete 对未被后文完整覆盖内容的过删**：当前真实样例中费用信息段被后续流程信息段误判为重说覆盖并整段删除；delete 判断应回到核心原则：只有后文能完整替代前文且不丢信息时才删除前文，后文只是补充、展开或进入新的信息增量时必须保留。相关路径：`skills/direct-prompts/delete.md`、`web_api/tests/test_direct_prompt_source_of_truth.py`、`web_api/tests/test_direct_prompt_runner_contract.py`、`docs/requirements_todo.md`
- 2026-04-21: **收紧 polish/chapter/highlight 提示词以改善质量**：按最新反馈，`polish` prompt 现更明确要求主动修复 ASR 错词、同音误识别与英文/专有名词误识别；`chapter` 保持最多 6 章，但进一步强调“没有必要时宁少勿多，优先合并”；`highlight` 改为更保守，只挑少量真正关键的词，最多 2 个且优先 1 个，并在代码侧过滤整句/过长短语，避免高亮泛滥。相关路径：`video_auto_cut/editing/direct_prompts.py`、`video_auto_cut/rendering/subtitle_render_contract.py`、`web_api/tests/test_subtitle_render_contract.py`、`docs/requirements_todo.md`
- 2026-04-21: **导出高亮合同前移到 editor-ready 后台预热，并优先复用同 revision 结果**：章节生成完成、进入用户编辑阶段（`TEST_READY`）后，后端应立即开始运行 highlight 计算并落盘缓存；预热缓存必须覆盖当前 editor 里的全部行，包括已标记删除的行；confirm/export 优先复用同一 test document revision 的已生成结果，`/render/config` 不兜底触发 LLM 高亮计算。相关路径：`web_api/services/test.py`、`web_api/services/render_web.py`、`web_api/tests/test_render_web.py`、`web_api/tests/test_test_chapters.py`、`docs/requirements_todo.md`
- 2026-04-21: **放宽浏览器 E2E 脚本对“保存并进入导出”的等待时间**：本地真机回归证明 `PUT /api/v1/jobs/<job>/test/confirm` 在生成导出前合同时可能耗时约 69 秒；`scripts/e2e_browser_upload_export.mjs` 的 confirm 等待窗口需要保持足够宽，并继续用成功 job 验证导出。相关路径：`scripts/e2e_browser_upload_export.mjs`、`docs/requirements_todo.md`
- 2026-04-21: **修复 delete 对“仅去掉行尾逗号/句号”等轻微文本归一化的误判**：delete parser 对模型输出正文的比对过于逐字，连行尾口播标点被模型顺手规整也会被当成非法改写；需要收紧为“时间轴与正文语义必须一致，但允许行尾冗余标点归一化”，并补充回归测试。相关路径：`video_auto_cut/pi_agent_runner.py`、`web_api/tests/test_pi_runner_contract.py`、`docs/requirements_todo.md`
- 2026-04-21: **修复 polish 对“嗯/啊/呃”类单字语气词输出空文本时的合同崩溃**：skill 允许把无信息单字语气词直接润色掉，但 parser 仍把空文本视为非法；需要对齐合同并补充回归测试，避免上传到导出的链路被 filler 行打断。相关路径：`video_auto_cut/pi_agent_runner.py`、`web_api/tests/test_pi_runner_contract.py`、`docs/requirements_todo.md`
- 2026-04-21: **修复 `TEST_READY` 首帧进入 editor 时 `保存并进入导出` 偶发 409 revision conflict**：`TEST_READY` 刚到时存在 editor 首帧竞态，按钮可点早于最终 test document/revision 完整加载；需要修复 editor/export handoff gating，并补充前端回归测试。相关路径：`web_frontend/components/job-workspace/use-test-document-polling.ts`、`web_frontend/components/job-workspace/use-editor-step-controller.ts`、`web_frontend/components/job-workspace/workspace-state.ts`、`web_frontend/components/job-workspace/workspace-state.test.mjs`、`docs/requirements_todo.md`
- 2026-04-17: **导出排版取消共享字号概念并引入 `@remotion/layout-utils`**：取消全片字幕统一字号、progress 共享字号等概念，改成章节标题、当前字幕、每个 progress segment 各自独立 fit；浏览器/Remotion 运行时优先使用 `@remotion/layout-utils`，Node 测试环境保留兜底实现。相关路径：`web_frontend/lib/remotion/typography.ts`、`web_frontend/lib/remotion/stitch-video-web.tsx`、`web_frontend/package.json`、`web_frontend/package-lock.json`、`docs/requirements_todo.md`
- 2026-04-17: **网感字幕链路重构（H5 样式框架版）**：当前已落地 token-level timing、最小 LLM 标注和静态 H5 文本卡片呈现；后续待继续打磨样式系统本身。相关路径：`video_auto_cut/asr/`、`web_api/services/render_word_timing.py`、`web_api/services/render_caption_labels.py`、`web_api/services/render_web.py`、`web_frontend/lib/remotion/stitch-video-web.tsx`、`web_frontend/components/export-frame-preview/`
- 2026-04-16: **导出 overlay 渲染执行层回归 CSS**：保持字幕/章节/进度标签字号与可见性求解逻辑不变，但把章节卡片自然高度、`fit-content`/`max-width`、字幕盒子 padding/radius/theme 样式、进度标签 padding 的执行从 `typography.ts` 数值 token 回收至 CSS/呈现 helper。相关路径：`web_frontend/lib/remotion/typography.ts`、`web_frontend/lib/remotion/overlay-presentation.ts`、`web_frontend/lib/remotion/stitch-video-web.tsx`、`web_frontend/components/export-frame-preview/use-overlay-layout.ts`、`web_frontend/components/export-frame-preview/overlay-layer.tsx`、`docs/requirements_todo.md`

## Recent Done
- 2026-05-12: **为参考口播脚本拆出独立 delete/polish prompt**：参考脚本不再混入普通 `delete.md` / `polish.md`，而是新增 `delete-with-reference.md` 与 `polish-with-reference.md`；运行时仅在 job 提供脚本时选择对应 reference prompt，并把参考脚本作为显式输入资料传入。相关路径：`skills/direct-prompts/delete-with-reference.md`、`skills/direct-prompts/polish-with-reference.md`、`video_auto_cut/editing/direct_prompts.py`、`web_api/tests/test_direct_prompt_source_of_truth.py`、`web_api/tests/test_direct_prompt_runner_contract.py`、`web_api/tests/test_repo_skill_layout.py`、`docs/requirements_todo.md`
- 2026-05-12: **polish 阶段覆盖 delete 已标记删除的行**：direct prompt runner 的 polish 输入不再过滤 `user_final_remove` 行；模型返回已删除行的改写时会更新 `optimized_text`，但保留 `ai_suggest_remove` / `user_final_remove` 删除标记不被 polish 取消。相关路径：`video_auto_cut/direct_prompt_runner.py`、`skills/direct-prompts/polish.md`、`web_api/tests/test_direct_prompt_runner_contract.py`、`web_api/tests/test_auto_edit_two_pass_rules.py`、`docs/requirements_todo.md`
- 2026-05-12: **补充面向后续 vibe coding 的项目地图与迭代守则**：在 `AGENTS.md` 中新增当前产品流、direct prompt/LLM 边界、常见功能入口、快速验证矩阵和迭代循环；明确不应重引入隐藏 prompt 拼接、旧 PI provider 或 `skills/direct-prompts` 之外的运行时 prompt 入口。相关路径：`AGENTS.md`、`docs/requirements_todo.md`
- 2026-05-11: **导出字幕支持显式黑/白颜色选择并统一关键词高亮**：导出高级设置中的“字幕样式”改为“字幕颜色”，选项文案改为“白色字幕（深色视频）/ 黑色字幕（浅色视频）”；黑白字幕只切换普通文字颜色与可读性描边，关键词高亮统一使用同一套青绿色、放大和字重。相关路径：`web_frontend/lib/remotion/constants.ts`、`web_frontend/lib/remotion/overlay-presentation.ts`、`web_frontend/lib/remotion/stitch-video-web.tsx`、`web_frontend/components/job-workspace/export-step.tsx`、`web_frontend/app/dev-export-preview/page.tsx`、`docs/requirements_todo.md`
- 2026-05-11: **运行时 prompt 完全收口到 `skills/direct-prompts` 原文**：`delete` / `polish` / `chapter` / `highlight` 不再追加章节数、标题字数、横屏策略、高亮主题、script 提示或固定任务说明；运行时只读取 `skills/direct-prompts/*.md` 原文并拼接本次输入载荷。相关路径：`video_auto_cut/editing/direct_prompts.py`、`skills/direct-prompts/`、`web_api/tests/test_direct_prompt_source_of_truth.py`、`web_api/tests/test_direct_prompt_runner_contract.py`、`web_api/tests/test_repo_skill_layout.py`、`docs/requirements_todo.md`
