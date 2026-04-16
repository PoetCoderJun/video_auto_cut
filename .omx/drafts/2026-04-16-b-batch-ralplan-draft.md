# B Batch Backend/Core Cleanup Plan (Draft)

## Requirements Summary

- 处理 `docs/requirements_todo.md` 中 B 批次（B1-B6），但不把 6 个子项粗暴塞进一个 mega-refactor。
- 目标是先清掉已脱离主路径或明显重复的低风险问题，再重塑当前主路径的字幕/剪辑数据契约，最后单独审视任务队列模型。
- 本轮按 `$ralplan` 只输出共识计划，不直接编码；用户工作分支已创建为 `work/2026-04-16-b-batch-ralplan`。

## Grounding

- 当前 Web/API 转写主链只允许 `dashscope_filetrans`：`video_auto_cut/asr/transcribe.py:22-30`、`web_api/config.py:137-142`、`scripts/start_web_mvp.sh:87-90`。
- `qwen3_asr.py` 与 `scripts/qwen3_asr_transcribe.py` 仍完整存在，但已脱离主 Web/API 主路径：`video_auto_cut/asr/qwen3_asr.py:1-120`、`scripts/qwen3_asr_transcribe.py:168-239`。
- `auto_edit` 已是 PI runner 主链；输入/输出在 `segments`、`lines`、SRT、JSON、EDL 间互转：`video_auto_cut/editing/auto_edit.py:25-69`、`video_auto_cut/editing/auto_edit.py:123-193`、`video_auto_cut/pi_agent_runner.py:120-160`、`video_auto_cut/pi_agent_runner.py:305-370`、`video_auto_cut/pi_agent_runner.py:398-424`、`video_auto_cut/pi_agent_runner.py:532-616`。
- 当前轻量删除标记为 `<remove>`，且仍被字幕导出/剪辑链路消费：`web_api/utils/srt_utils.py`、`video_auto_cut/pi_agent_runner.py`、`video_auto_cut/rendering/cut.py`。
- DashScope 切句逻辑集中在 `dashscope_filetrans.py` 的 `_split_by_words` 状态机：`video_auto_cut/asr/dashscope_filetrans.py:225-341`。
- `rendering/cut.py` 同时承载 helper 与 `Cutter` 大类；主链实际只明确复用了 helper 到 `cut_srt.py`：`video_auto_cut/rendering/cut.py:31-73`、`video_auto_cut/rendering/cut.py:85-135`、`video_auto_cut/rendering/cut.py:198-351`、`video_auto_cut/rendering/cut_srt.py:10-17`、`video_auto_cut/rendering/cut_srt.py:120-147`、`video_auto_cut/orchestration/pipeline_service.py:243-257`。
- 低层 JSON 解析/修复已主要收口在 `llm_client.py`，但 `topic_segment.py` 仍保留局部 fence/json 包装：`video_auto_cut/editing/llm_client.py:238-353`、`video_auto_cut/editing/topic_segment.py:206-259`、`video_auto_cut/editing/topic_segment.py:331-351`。
- `render_web.py` 仍依赖 `topic_segment` 标题规则与 `llm_client.request_json`：`web_api/services/render_web.py:8-14`、`web_api/services/render_web.py:521-532`。
- `repository.py` 与 `task_queue.py` 有重复 helper：`web_api/repository.py:58-85`、`web_api/task_queue.py:19-33`、`web_api/task_queue.py:79-89`。
- `db.py` 仍承担 sqlite/libsql 兼容胶水与历史 schema 处理：`web_api/db.py:36-55`、`web_api/db.py:244-253`、`web_api/db.py:267-532`。
- `repository.py` 中存在近似重复的 jobs 扫描函数：`web_api/repository.py:1041-1094`。
- OSS uploader 构造散落在多处：`web_api/services/oss_presign.py:10-23`、`web_api/services/test.py:199-248`、`video_auto_cut/asr/transcribe.py:72-88`。
- 当前 task queue 不是“简单触发器”，而是持久化可靠性队列：建表 `web_api/task_queue.py:44-76`、reclaim `web_api/task_queue.py:116-169`、heartbeat `web_api/task_queue.py:172-193`、claim `web_api/task_queue.py:261-340`；并且只支持 `TASK_TYPE_TEST`：`web_api/task_queue.py:195-199`、`web_api/services/tasks.py:20-22`、`web_api/services/tasks.py:65-83`、`web_api/api/routes.py:257-266`。
- 作业元数据主要已落到文件仓储而非 DB job 表：`web_api/db.py:515-530`、`web_api/repository.py:547-612`、`web_api/repository.py:816-833`、`web_api/repository.py:1097-1140`。

## RALPLAN-DR

### Principles

- 先削减无争议遗留与重复，再触碰当前主路径的数据契约。
- 把“安全去重”和“架构重审”分开，避免 B6 被误实现成预设答案。
- 当前 Test/PI 主路径优先保持行为等价；任何契约重塑都必须先锁定回归验证。
- 减少跨层协议型中间态，但不能用一次性大重写换取表面整洁。
- 所有子项都要收敛到更清晰的 ownership：ASR、editing、rendering、queue 各自只承担单一责任。

### Decision Drivers

- B 批次横跨遗留删除、低层去重、主路径契约重塑、队列架构，风险密度不均。
- 当前真正在线上的主路径集中在 `dashscope_filetrans`、PI runner、Test queue，不能和纯遗留清理混做。
- `task_queue` 已承担可靠性语义，B6 需要 ADR 级决策而不是代码洁癖式“简化”。

### Options

- **A. 整个 B 批次单 PR 一次收口**  
  Pros: 表面上一次做完。  
  Cons: 风险耦合过大，难以定位回归，B6 也会被迫提前拍板。

- **B. 三阶段分治：低风险收敛 -> 主路径契约重塑 -> 队列 ADR**  
  Pros: 与代码风险面匹配，便于逐步验证，B6 可先评审后实施。  
  Cons: 需要多个提交/PR，短期看起来推进更慢。

- **C. 只做 B1/B4/B5，完全冻结 B2/B3/B6**  
  Pros: 最安全。  
  Cons: 不能真正解决主路径数据模型与剪辑封装问题，只是推迟核心债务。

### Chosen Direction

- 选 **B**：
  1. **Wave 1：B1 + B4 + B5** —— 清遗留、收 helper、抽 OSS factory、去局部 JSON 包装重复。
  2. **Wave 2：B2 + B3** —— 先定义单一字幕/编辑文档，再让 cut/helper/ffmpeg 只消费该文档。
  3. **Wave 3：B6** —— 先产出队列 ADR，再决定是否保留通用 task 抽象、是否调整 DB/file 边界。

## Acceptance Criteria

- B1：仓库主路径不再保留误导性的本地 Qwen ASR 入口；删除或明确归档后的调用图中，不再有 Web/API 主链指向 `qwen3_asr.py` / `scripts/qwen3_asr_transcribe.py`，并且 `docs/current_prompts_inventory.txt`、相关旧计划文档中的引用已同步清理或标记为 legacy；`rg -n "qwen3_asr|qwen3_asr_transcribe" video_auto_cut scripts README.md` 不再命中主路径源码/脚本入口；文档侧仅允许命中 legacy/归档说明。
- B4：`repository.py` 与 `task_queue.py` 不再各自维护一套重复的时间/row helper；OSS uploader 构造改为单一 factory；重复 jobs 扫描函数合并为共享实现，同时 queue schema / claim / heartbeat / reclaim 运行语义不变。
- B5：`topic_segment.py` 不再保留与 `llm_client.py` 重复的 JSON fence/loads 包装，只保留 topic 领域校验与编排逻辑；`render_web.py` 与 topic flow 回归通过。
- B2：全项目继续统一到当前轻量文本契约（delete/polish：`【time】句子` / `【time】<remove>句子`；chapter：`【start-end】标题`），不再新增重 JSON/内部归一化契约；`.test.txt`、`optimized.srt`、chapter text 的 round-trip/adapter 测试通过，仅保留 `<remove>` 轻量标记，不再兼容 `<<REMOVE>>`。
- B3：拆成 B3a/B3b 两半执行：B3a 处理 `rendering/cut.py` / `cut_srt.py` / ffmpeg 封装与 legacy `Cutter`，并有命令组装或 builder 单测；B3b 对 `dashscope_filetrans.py` 仅允许等价重构或 guardrail 修正，不在本批做 editing-boundary 策略调优；`optimized.srt -> cut_srt`（或其替代边界）验证通过。
- B6：形成一份 ADR，明确 task queue 的职责、why-not、边界与后续实现方向；在 ADR 批准前不做破坏性模型替换。

## Implementation Steps

### Step 1 — Wave 1A: 清理已脱离主路径的本地 Qwen ASR 遗留（B1）
- 复核并删除/归档 `video_auto_cut/asr/qwen3_asr.py`、`scripts/qwen3_asr_transcribe.py` 的仓库内入口。
- 同步清理 README / docs / tests / scripts 中可能残留的 Qwen 本地 ASR 指引。
- 把 `docs/current_prompts_inventory.txt` 与仍引用该链路的旧计划文档一并清理或补 legacy 标记，避免 B1 只删代码不删认知入口。
- 如果决定保留研究样例，则迁到明确的 `legacy/` 或 docs 归档位置，避免误判为当前可部署路径。
- 触点：`video_auto_cut/asr/`、`scripts/`、`README.md`、`docs/current_prompts_inventory.txt`（如仍引用）。

### Step 2 — Wave 1B: 收口重复 helper 与 OSS factory（B4）
- 提取共享 `time/iso/row` helper，供 `repository.py` 与 `task_queue.py` 复用。
- 合并 `list_expired_succeeded_jobs` / `list_succeeded_jobs_with_artifacts` 为单一扫描器 + 参数化过滤。
- 提取 `get_oss_uploader()` 级工厂，替换 `services/test.py`、`services/oss_presign.py`、`asr/transcribe.py` 中的重复构造；工厂落点只能在 `video_auto_cut` 侧共享模块或 ASR 邻近模块，禁止新增 `video_auto_cut -> web_api` 反向依赖。
- 保持 `db.py` 的 `_extract_column_names` / `_executescript` 暂留在 DB 层，不在本波误下沉到“通用 util”。
- 明确边界：Wave 1B 只允许抽 `task_queue.py` 的纯 helper，不得改 queue schema、claim、heartbeat、reclaim 等运行语义。
- 触点：`web_api/repository.py`、`web_api/task_queue.py`、`web_api/services/test.py`、`web_api/services/oss_presign.py`、`video_auto_cut/asr/transcribe.py`、必要时新增 `video_auto_cut/shared/*`。

### Step 3 — Wave 1C: 去掉 topic JSON 辅助的局部重复（B5）
- 让 `topic_segment.py` 直接复用 `llm_client.extract_json` / `request_json`，删除本地 `_strip_code_fence` / `_json_loads` 类薄包装。
- 保留 topic 领域约束（block/segment plan normalize、title rules、validate）不动。
- 校对 `render_web.py` 的标题改写仍可使用同一低层 JSON helper。
- 触点：`video_auto_cut/editing/llm_client.py`、`video_auto_cut/editing/topic_segment.py`、`web_api/services/render_web.py`、相关 tests。

### Step 4 — Wave 2A: 保持轻量文本契约不变，只收口内部 adapter
- 不新增 `EditDocument` / `line contract` 一类重内部契约；以 `video_auto_cut/shared/test_text_protocol.py` 定义的轻量文本协议作为全项目统一 seam。
- 先建立/收口 adapter 边界，明确迁移面：`optimized.srt`、`.test.txt`、EDL、line dict；但这些仅作为实现细节，不再上升为新的正式 contract。
- 让 `auto_edit.py` 只做“输入加载 -> runner -> artifact 写出”，不再自己拼多套 shape。
- 删除 `<<REMOVE>>` 旧兼容路径，只保留 `<remove>` 轻量标记；内部布尔字段继续只是实现细节。
- 明确兼容策略：`.test.txt`、`optimized.srt`、chapter text 在 Wave 2 期间保持外部兼容；只保留 `<remove>` 轻量标记，不再保留 `<<REMOVE>>` 导入/导出兼容。
- 确认 `web_api/services/test.py`、`web_api/utils/srt_utils.py`、`video_auto_cut/editing/chapter_domain.py`、`repository.py`、`rendering/cut.py`、`cut_srt.py`、`video_auto_cut/orchestration/pipeline_service.py` 统一围绕轻量文本协议及其必要 adapter 工作。必要时补看 `web_api/services/render_web.py` 的消费边界。
- 触点：`video_auto_cut/editing/auto_edit.py`、`video_auto_cut/pi_agent_runner.py`、`web_api/services/test.py`、`web_api/utils/srt_utils.py`、`video_auto_cut/editing/chapter_domain.py`、`web_api/repository.py`、`video_auto_cut/rendering/cut.py`、`video_auto_cut/rendering/cut_srt.py`、`video_auto_cut/orchestration/pipeline_service.py`、必要时 `web_api/services/render_web.py`。

### Step 5 — Wave 2B: 拆开 B3 的 rendering 清理与 ASR 等价重构
- **B3a / rendering side:** 审视 `rendering/cut.py`：将仍被 `cut_srt.py` 消费的 helper 留在轻量模块；先做 repo-wide `Cutter` import/export 审计，再按决策门槛处理：若无运行时消费者，仅保留 package export/历史注释则直接删除；若仍有 CLI/手工链路使用，则显式降级为 legacy CLI-only seam；视频/音频 ffmpeg 参数构造改成共享 builder，减少两套重复 filter/命令拼装。
- **B3b / ASR side:** `dashscope_filetrans.py` 仅做规则函数拆分、命名澄清与 guardrail 修正；本批不做 editing-boundary 策略调优。若需要调优，转入 `docs/plans/2026-04-15-asr-boundary-layering.md` 的后续批次。
- 触点：`video_auto_cut/asr/dashscope_filetrans.py`、`video_auto_cut/rendering/cut.py`、`video_auto_cut/rendering/cut_srt.py`、`docs/plans/2026-04-15-asr-boundary-layering.md`。

### Step 6 — Wave 3: 只为 B6 产出 ADR 与评审结论，不预设实现
- 记录 task queue 当前真实职责：持久化、lease、heartbeat、reclaim、only TEST。
- 明确 2~3 个可行方向，例如：
  - 保留 DB 可靠性队列，但把接口收窄到 Test-only。
  - 保留通用 schema，但引入正式 task contract / payload shape。
  - 调整 repository/file-storage 边界，但不动可靠性语义。
- 先出 ADR，再决定是否另起实施批次；本波默认不把 B6 夹带成顺手重写。
- 触点：`web_api/task_queue.py`、`web_api/services/tasks.py`、`web_api/worker/runner.py`、`web_api/repository.py`、`web_api/db.py`、`docs/plans/` 或 ADR 文档位置。

## Risks and Mitigations

- **Risk:** B2 重塑时误伤当前 Test 编辑主链。  
  **Mitigation:** 先锁回归测试，先引入 typed model + adapter，再删除旧 shape。
- **Risk:** B3 简化切句后字幕边界质量下降。  
  **Mitigation:** 保留现有 granularity 测试与样本对比，先“等价重构”后再做策略修正。
- **Risk:** B4 抽共用 helper 时把 DB 兼容 shim 混成跨层 util。  
  **Mitigation:** 明确 `_extract_column_names` / `_executescript` 仍属于 DB 私有层，只收真正跨文件重复项。
- **Risk:** B6 被当作“把 queue 改成最简单实现”。  
  **Mitigation:** 强制先出 ADR，要求 Alternatives/Consequences 写清 before implementation。
- **Risk:** 当前工作树很脏，执行时难以隔离验证。  
  **Mitigation:** 后续实现前建议再从此分支切更细的 feature 子分支或按 wave 拆 commit。

## Verification Steps

- 基础后端回归：`python -m unittest discover web_api/tests -p "test_*.py"`
- B1/B4/B5 重点回归：
  - `rg -n "qwen3_asr|qwen3_asr_transcribe" video_auto_cut scripts README.md`
  - 如需复查文档残留：`rg -n "qwen3_asr|qwen3_asr_transcribe" docs .omx | cat`，但仅允许命中文档归档/需求记录，不得作为失败判定。
  - `python -m unittest web_api.tests.test_asr_env_names`
  - `python -m unittest web_api.tests.test_task_queue`
  - `python -m unittest web_api.tests.test_step2_topic_model`
  - `python -m unittest web_api.tests.test_render_web`
- B2/B3 重点回归：
  - `python -m unittest web_api.tests.test_auto_edit_two_pass_rules`
  - `python -m unittest web_api.tests.test_auto_edit_e2e`
  - `python -m unittest web_api.tests.test_pi_runner_contract`
  - `python -m unittest web_api.tests.test_pi_runner_end_to_end`
  - `python -m unittest web_api.tests.test_asr_split_granularity`
  - 新增/补强 round-trip 验证：轻量文本协议 <-> `.test.txt` / line dict / `optimized.srt` adapter 测试
  - 新增/补强 cut 验证：`optimized.srt -> cut_srt`（或替代边界）与 ffmpeg builder/命令组装测试
- 手工验证：上传音频 -> `/test/run` -> 编辑字幕/章节 -> confirm -> render/export；必要时用 `test_data/media/1.wav` 与 `web_frontend/app/dev-export-preview/page.tsx` 辅助观察产物。

## ADR

- **Decision:** 采用“三阶段分治”处理 B 批次：先 B1/B4/B5，后 B2/B3，最后 B6 ADR。
- **Drivers:** 风险密度不均；主路径与遗留清理应分离；task queue 已承担可靠性语义。
- **Alternatives considered:** 单次 mega-refactor；只做低风险清理并长期冻结核心债务。
- **Why chosen:** 既能尽快收口无争议问题，又能为高风险契约重塑保留充分验证空间，还能避免对 B6 预设答案。
- **Consequences:** 需要多个 commit/PR；计划周期更长，但每波更易 review 与回滚。
- **Follow-ups:** 为 Wave 2 补 typed model 设计草图；为 Wave 3 单独出 queue ADR 文档。

## Available-Agent-Types Roster

- `architect`: 波次拆分、ADR、边界审查。
- `executor`: B1/B4/B5/B2/B3 的代码实施主力。
- `code-reviewer`: 跨波 review，尤其关注跨层依赖回流。
- `verifier`: 对照计划核验完成度与测试证据。
- `test-engineer`: 回归矩阵、样本数据、契约测试补强。
- `debugger` / `build-fixer`: 处理重构引入的失败与环境问题。
- `writer`: ADR、迁移说明、requirements/doc 更新。

## Follow-up Staffing Guidance

### Ralph path
- **Lane 1 (medium reasoning):** B1/B4/B5 低风险收敛，由 `executor` 主做，`verifier` 跟收尾。
- **Lane 2 (high reasoning):** B2/B3 契约重塑，由 `architect` 先定模型，再由 `executor` 落地，`test-engineer` 同步补测试。
- **Lane 3 (medium reasoning):** B6 ADR，由 `architect` + `writer` 产出，`critic/code-reviewer` 复核。

### Team path
- **Worker A (medium):** B1 + 文档/脚本残留清理。
- **Worker B (medium):** B4 helper/OSS factory 去重。
- **Worker C (medium-high):** B5 JSON helper 收口与 render/topic 回归。
- **Worker D (high):** B2 轻量文本契约统一与 adapter 收口。
- **Worker E (high):** B3 cut/ffmpeg 重构，依赖 D 的契约完成后再接入。
- **Worker F (medium):** B6 ADR/评审材料，不直接改运行时。

## Launch Hints

- 当前评审阶段引用 draft：`.omx/drafts/2026-04-16-b-batch-ralplan-draft.md`；promotion 后统一切到 `.omx/plans/2026-04-16-b-batch-backend-core-cleanup.md`。
- Ralph: `$ralph 按 .omx/plans/2026-04-16-b-batch-backend-core-cleanup.md 的 Wave 1 开始，先完成 B1/B4/B5，再停下来汇报验证结果。`
- Team: `$team 按 .omx/plans/2026-04-16-b-batch-backend-core-cleanup.md 分 6 lane 执行，D/E 不要并发改同一协议文件，E 等待 D 先完成轻量文本协议边界收口后再接。`
- OMX team CLI hint: `omx team run .omx/plans/2026-04-16-b-batch-backend-core-cleanup.md --lanes "B1,B4,B5,B2,B3,B6-adr"`

## Team Verification Path

- Team 在各自 lane 完成后必须提交：变更文件列表、所跑测试、未解决风险。
- `verifier` 汇总检查：
  - Wave 1 没有改坏 `/test/run` 与 topic/render 标题链路；
  - Wave 2 没有改变 delete/polish/chapter 的对外 contract；
  - Wave 3 只产出 ADR，不偷偷改变 queue 运行模型。
- Ralph 或主代理最终复核：requirements 状态更新、关键测试命令、手工验证路径、是否需要下一轮实施批准。
