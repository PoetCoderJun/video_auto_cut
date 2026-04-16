# A 批次（主路径与模块边界）RALPLAN 共识计划

- 日期：2026-04-16
- 分支：`work/2026-04-16-a-batch-ralplan`
- 模式：RALPLAN-DR deliberate（因 A5 涉及启动迁移/兼容退出）
- 范围假设：本次将 `docs/requirements_todo.md` 中 **A1-A6** 作为同一批次规划；若执行时只先做 A1，可把 Step 1-2 单独切分。

## Requirements Summary

目标是把当前主路径里的 6 类结构性问题按真实依赖顺序拆开处理：
1. **先明确容器内 Test/PI 能否运行（A6）**。当前 canonical Test 主路径会调用 `run_test_pi()`，而镜像未打包 `.pi/`、`skills/`、`pi` CLI。证据：`web_api/services/test.py:131-163`、`web_api/services/step2.py:21-43`、`video_auto_cut/pi_agent_runner.py:194-215,520-529`、`Dockerfile:10-15`、`README.md:47-80,97-119`。
2. **去掉 `video_auto_cut -> web_api` 的反向依赖（A1）**，并先定义 shared 协议 owner，而不只是搬几个 helper。证据：`video_auto_cut/editing/auto_edit.py:11-13`、`video_auto_cut/pi_agent_runner.py:16-18,632-639`、`video_auto_cut/asr/transcribe_stage.py:25-49`、`web_api/utils/srt_utils.py:11-17,58-103,131-217`。
3. **拉直参数入口与阶段配置（A4）**。现有 CLI/Web 两套 options authority，再叠加 `PipelineOptions -> SimpleNamespace -> getattr` 链路。证据：`video_auto_cut/orchestration/full_pipeline.py:121-150`、`web_api/services/pipeline_options.py:9-63`、`video_auto_cut/orchestration/pipeline_service.py:83-183`、`video_auto_cut/asr/transcribe.py:19-131`、`video_auto_cut/editing/auto_edit.py:91-109`。
4. **收掉旧 CLI / Step2 / 兼容状态 / 过期接口文档（A2）**，统一到当前 Test/PI 主路径。证据：`web_api/repository.py:687-706,853-860`、`web_api/services/step2.py:14-44`、`docs/web_api_interface.md:10-14,60-81,132-139`。
5. **收窄 `render_web.py` 的职责（A3）**：优先冻结最小 render DTO，并清理未接入 live path 的后端排版/标题改写 helper；当前 live 排版主要已在前端。证据：`web_api/services/render_web.py:541-669`、`web_frontend/lib/remotion/stitch-video-web.tsx:419-524`、`web_frontend/components/export-frame-preview.tsx:439-540`。
6. **让 `init_db()` 只做当前 schema 初始化/校验（A5）**，历史迁移和删表改为显式脚本，并补 schema preflight/fail-fast。证据：`web_api/db.py:267-532`、`web_api/app.py:324`、`web_api/worker/runner.py:94`、`scripts/coupon_admin.py:322`。

## RALPLAN-DR Summary

### Principles
1. **部署前提先确认**：若容器中 Test/PI 主路径不可运行，其他主路径优化都不算完成，且 Step 0 必须作为执行前置 phase 单独完成。
2. **核心层不得反向依赖服务层**：`video_auto_cut` 只能依赖 shared/domain/orchestration，不直接依赖 `web_api/*`。
3. **协议 owner 单一化**：Test 文本/SRT/章节文本协议必须有唯一 owner，避免双语义解析。
4. **配置事实源单一化**：options builder 归核心编排层所有；web 层只做 settings 适配，不做唯一 owner。
5. **启动动作可预测**：应用启动只做当前 schema 准备；迁移和清理必须显式触发并可审计。

### Decision Drivers
1. **避免优化一个部署前提尚未成立的主路径**：A6 必须前置。
2. **优先消除跨层耦合与双 authority**：A1/A4/A2 是一条依赖链，顺序错了会反复返工。
3. **把 live path 和 dead helper 分开**：A3 不应被误判为当前最高风险 live issue。

### Viable Options

#### 方案 A：一次性大重写 A1-A6
- 优点：概念上最干净，能最快消除中间适配层。
- 缺点：变更面横跨核心、API、前端、部署与文档；当前工作树已较脏，回归和回滚成本过高。

#### 方案 B：按依赖顺序分阶段收口（推荐）
- 优点：先确认部署 gate，再固化 shared 协议 owner、统一配置 owner、typed 化阶段入参，最后清旧双轨、render helper、DB 启动副作用；每阶段都有独立验收点。
- 缺点：短期内会保留少量 shim / adapter / 迁移脚本，需要在后续步骤再删一次。

#### 方案 C：仅做文档收口，代码延后
- 优点：风险最低。
- 缺点：A1/A4/A5/A6 的 live coupling 仍在线上路径里，不能满足“处理 A 问题”的目标。

### Recommendation
选择 **方案 B：按依赖顺序分阶段收口**。

## Pre-mortem（3 scenarios）
1. **容器误判可运行**：本地 shell 能跑 `pi`，镜像里却缺 `.pi/skills/pi`，上线后 worker 在生成章节时失败。
2. **协议 owner 迁移不彻底**：`transcribe_stage` 与 shared/test_text 仍保留两套 parse/render 语义，导致 Test 文本 round-trip 不一致。
3. **DB 启动瘦身后故障不透明**：旧 schema 库不再被隐式迁移，但 preflight 又没给出清晰错误和迁移命令，导致 API/worker/coupon_admin 同步崩溃。

## Acceptance Criteria

1. A6 先得到明确结论，并体现在代码与文档里：
   - **支持容器内 Test/PI 编辑**：镜像复制 `.pi/`、`skills/` 并安装 `pi` CLI，带真实 `run_test_pi()` smoke test；或
   - **不支持**：worker/API/CLI 相关路径显式 fail-fast，并统一报错文案与 README/部署说明。
2. `video_auto_cut/orchestration/pi_capability.py`（或等价单一模块）成为 PI/Test 容器能力判定唯一 owner；worker/API/CLI 都通过它判断支持/不支持，而不是各自散落判断。
3. capability probe 暴露统一的结构化结果 contract（至少包含 supported / mode / reason_code / reason_message / required_artifacts）；worker/API/CLI 统一消费同一结果模型，不再各自解释 support/fail-fast 语义。
2. `rg "from web_api\\.|import web_api" video_auto_cut` 返回空；`video_auto_cut/` 下不再 import `web_api.utils.srt_utils` 或 `web_api.services.pipeline_options`。
5. `video_auto_cut/shared/` 存在唯一 Test 文本协议 owner，至少统一：`REMOVE_TOKEN`、timed-line regex、`build_test_lines_from_srt`、`build_test_lines_from_text`、`write_test_text`、chapter text parse/render；旧 live 语义只保留一套。
6. options builder owner 明确下沉到 `video_auto_cut/orchestration/`（或同层 shared/orchestration 模块）；`web_api/services/pipeline_options.py` 仅做 web settings wrapper，不再是唯一 authority。
7. `video_auto_cut/asr/transcribe.py`、`video_auto_cut/editing/auto_edit.py`、topic path 不再出现业务字段级 `getattr(args, "...")` 主链路；允许 orchestration 边界 adapter 存在，但业务实现内部不再依赖它。
8. `web_api/services/step2.py`、`web_api/repository.py` 中旧 Step2 兼容状态/文件探测被删除或只剩显式迁移入口；`docs/web_api_interface.md` 不再把 Step2 作为当前 API 主流程。
9. `web_api/services/render_web.py` 不再 import `video_auto_cut.editing.topic_segment`；`BAD_TITLE_ENDING_PATTERN`、`GENERIC_SECTION_TITLE_PATTERN`、`PLACEHOLDER_TITLE_PATTERN` 的 owner 明确迁到 shared title-rules 模块；`build_web_render_config()` 仅做 artifact 读取、timeline remap、DTO 组装，不再做标题 rewrite / fit 决策。
10. `init_db()` 仅包含当前 schema 建表、必要 index、seed、轻量 schema 校验；旧 schema 下 app/worker/coupon_admin 均给出同一 fail-fast 提示；运行迁移脚本后恢复正常启动。
11. 通过以下验证：`python -m unittest discover web_api/tests -p "test_*.py"`、`cd web_frontend && npx tsc --noEmit`、`npm --prefix web_frontend run build`、`docker build -f Dockerfile .`，以及至少 1 条 Test 主路径手工冒烟。

## Implementation Steps

### Step 0 — A6 前置 gate：先确认容器内 Test/PI 能力
**目标**：先判定当前 canonical Test 主路径在部署镜像中是否可运行，避免后续规划建立在错误前提上。

- 盘点 worker/Test/chapter 路径对 `pi`、`.pi/`、`skills/` 的运行时依赖：`web_api/services/test.py:131-163`、`web_api/services/step2.py:21-43`、`video_auto_cut/pi_agent_runner.py:194-215,520-529`。
- 在 `video_auto_cut/orchestration/pi_capability.py`（或等价模块）集中实现唯一 capability probe，统一检查：repo-root cwd、`.pi/settings.json`、`.pi/APPEND_SYSTEM.md`、`skills/`、`pi` CLI 可用性，以及当前模式是 support 还是 fail-fast。该 probe 必须返回统一结构化结果 contract（至少包含 `supported` / `mode` / `reason_code` / `reason_message` / `required_artifacts`）。
- 基于 `Dockerfile:10-15` 与 README 部署说明，做明确产品/部署决策：
  - **支持容器内 PI/Test 编辑**：扩展镜像复制 `.pi/` 与 `skills/`，安装 Node + `pi` CLI，并通过 capability probe + 真实 `run_test_pi()` smoke test；或
  - **暂不支持**：worker/API/CLI 全部通过同一 capability probe 显式 fail-fast，并同步文档。
- 该结论必须成为 A 批次执行 gate：Step 1-4 在 Step 0 完成前不得并行启动。

**交付物**：容器能力口径唯一，运行时行为与 README/部署说明一致。

### Step 1 — A1：先定义 shared 协议 owner，再迁反向依赖
**目标**：先统一 Test 文本/SRT/章节文本协议语义，再移除 `video_auto_cut -> web_api` 反向依赖。

- 新建 `video_auto_cut/shared/test_text.py`（或等价命名），承接并定义唯一 owner：
  - `REMOVE_TOKEN`
  - timed-line / chapter-line regex
  - `build_test_lines_from_srt`
  - `build_test_lines_from_text`
  - `write_test_text`
  - `build_test_chapters_from_text` / `write_chapters_text`
- 统一 `video_auto_cut/asr/transcribe_stage.py:25-49` 与 `web_api/utils/srt_utils.py:58-103` 当前重复/分叉的解析语义，避免双实现长期并存。
- 更新 `video_auto_cut/editing/auto_edit.py:11-13`、`video_auto_cut/pi_agent_runner.py:16-18`、`video_auto_cut/asr/transcribe_stage.py:46-49` 改依赖 shared 层。
- `web_api/utils/srt_utils.py` 短期可退化为向下转发层，待全部迁完后删除或只保留 API 层组合函数。

**交付物**：核心层不再 import `web_api.*`；协议 owner 单一化。

### Step 2a — A4 第一段：固定 options builder owner
**目标**：先消除 options 双 authority 和 core→web 反向取值。

- 明确 owner 决策：**options builder 下沉到 `video_auto_cut/orchestration/`**；`web_api/services/pipeline_options.py` 只负责读取 settings 并调用 core builder 组装 `PipelineOptions`。
- CLI 路径 `video_auto_cut/orchestration/full_pipeline.py:121-150` 与 `video_auto_cut/__main__.py:1-5` 若继续支持，也必须复用同一 core builder；不允许 builder 继续留在 `web_api/services/` 作为唯一 authority。
- 先消掉 `video_auto_cut/pi_agent_runner.py:632-639` 对 `web_api.services.pipeline_options` 的反向 import。

**交付物**：options authority 单一，且 owner 在核心编排层而不是 service 层。

### Step 2b — A4 第二段：阶段参数 typed 化
**目标**：在单一 options authority 基础上，把阶段入参从 `SimpleNamespace + getattr` 改为 typed config。

- 在 `video_auto_cut/orchestration/pipeline_service.py:83-183` 引入显式 dataclass，例如 `TranscribeOptions` / `AutoEditOptions` / `TopicOptions`。
- 将 `video_auto_cut/asr/transcribe.py:19-131`、`video_auto_cut/editing/auto_edit.py:91-109`、`video_auto_cut/editing/topic_segment.py` 的 topic path 一并改为直接读取 typed 字段，不再依赖业务字段级 `getattr(...)`。
- 若某条旧 topic CLI 路径决定退出支持，必须在 Step 2c 明确写出降级/移除范围，并同步从 Acceptance Criteria 与 Verification 中删去豁免说明；默认假设是 topic path 也完成 typed 化。
- 允许 orchestration 边界保留薄 adapter，但 adapter 只能集中在 orchestration 层，不扩散到业务实现内部。

**交付物**：阶段实现使用 typed config；`SimpleNamespace + getattr` 不再是主链路。

### Step 2c — A2：最后删除旧双轨与 Step2 runtime 兼容
**目标**：在 shared 协议与 typed config 稳定后，再收掉旧 CLI / Step2 / legacy runtime 分支。

- 删除或收口 `web_api/services/step2.py:14-44`，让章节生成只保留 canonical Test 主路径。
- 清除 `web_api/repository.py:687-706,853-860` 的 legacy Step2 状态探测；若需历史迁移，只保留显式离线迁移入口。
- 更新 `docs/web_api_interface.md:10-14,60-81,132-139`，删掉 Step2 现役接口/状态说明。
- 复核 `video_auto_cut/orchestration/full_pipeline.py` 与 `video_auto_cut/__main__.py` 是否仍属于支持中的 CLI；若不再是主路径，则降为开发/迁移工具并写明边界。

**交付物**：运行态只剩一个 canonical Test 主路径；Step2 不再参与 live flow。

### Step 3 — A3：固定 title-rules owner，冻结最小 render DTO，并清理 dead helper
**目标**：避免把并未接入 live path 的后端排版 helper 当成主问题；先冻结 DTO，再清理 dead/over-coupled helper。

- 明确 title-rules owner：将 `BAD_TITLE_ENDING_PATTERN`、`GENERIC_SECTION_TITLE_PATTERN`、`PLACEHOLDER_TITLE_PATTERN` 从 `video_auto_cut/editing/topic_segment.py:31-37` 抽到 `video_auto_cut/shared/title_rules.py`（或等价 shared 模块），避免 `render_web.py -> topic_segment.py` 的现存耦合。
- 以 `web_api/services/render_web.py:596-669` 当前 `build_web_render_config()` 为基线，区分：
  1. **保留在后端**：job artifact 读取、cut timeline remap、render config 聚合；
  2. **前端 live owner**：标题/字幕 fit、wrap、overflow、responsive typography，已由 `web_frontend/lib/remotion/stitch-video-web.tsx:419-524`、`web_frontend/components/export-frame-preview.tsx:439-540`、`web_frontend/lib/remotion/typography.ts` 负责；
  3. **待删除/迁离线**：`render_web.py` 中未接入 live path 的 `_prepare_render_topics()`、标题 rewrite/fit/layout helper。
- 定义稳定 DTO：topics 提供原始标题、时间范围、可选 backend-normalized 字段，但不再输出“已按当前屏幕 fit 的标题”。

**交付物**：后端只产结构化 render DTO；shared title-rules 脱离 `topic_segment.py`；前端成为唯一 live 排版 owner。

### Step 4 — A5：拆分 init / migration，并补 schema preflight
**目标**：API/worker/脚本启动只做当前 schema 准备，历史兼容逻辑迁往显式迁移脚本，同时避免“神秘报错”。

- 将 `web_api/db.py:341-532` 中的 `ALTER TABLE`、旧表搬迁、legacy 表删除拆到 `scripts/db_migrate_legacy_web_mvp.py`（或等价脚本）。
- 保留 `init_db()` 中真正需要每次启动都安全执行的逻辑：当前表 `CREATE TABLE IF NOT EXISTS`、必要 index、seed、有限 schema mismatch 检查。
- 在 `web_api/app.py:324`、`web_api/worker/runner.py:94`、`scripts/coupon_admin.py:322` 覆盖统一 preflight/fail-fast 语义：若检测到旧 schema 未迁移，报出明确可执行提示，而不是隐式迁移或神秘失败。

**交付物**：启动副作用显著缩小；迁移动作改为可审计的显式命令。

### Step 5 — 文档与需求单一事实源收口
**目标**：让需求、接口、部署说明与实施计划一致。

- 更新 `docs/requirements_todo.md`：A 批次进入 In Progress，并挂上分支/计划文件；完成后逐项移到 Done。
- 重写 `docs/web_api_interface.md` 当前流程章节，删除 Step2 现役描述，只保留必要历史说明。
- 根据 Step 0 结论更新 README / 部署说明：明确容器是否支持 PI/Test 编辑及验证方式。

**交付物**：需求追踪、接口文档、部署说明三者一致。

## Risks and Mitigations

- **风险 1：A6 迟迟不定，导致后续规划建立在错误部署前提上。**
  - 缓解：把 A6 设为 Step 0 gate；未明确前不宣布 A 批次可执行。
- **风险 2：A1 只搬 helper，不统一协议 owner，结果保留双语义解析。**
  - 缓解：先统一 token/regex/parse/render owner，再迁调用；以 round-trip 测试锁住协议。
- **风险 3：A2 与 A4 顺序不当，继续保留 options 双 authority。**
  - 缓解：严格按“固定 owner → stage typed 化 → 删除旧双轨”执行。
- **风险 4：A3 误把 dead helper 当 live path 重点，浪费阶段预算。**
  - 缓解：先用调用证据冻结 live owner，再只清理未接入 helper 与 DTO 边界；title-rules 先抽 shared 再删 helper。
- **风险 5：A5 拆迁移后，启动体验从‘自动修’退化成‘失败不透明’。**
  - 缓解：补 schema preflight/fail-fast 与明确迁移提示，覆盖 API/worker/coupon_admin 三入口。

## Expanded Test Plan

### Unit
- `web_api/tests/test_test_srt_utils.py`：shared test_text owner 的 text/SRT round-trip、remove token、chapter text parse/render。
- `web_api/tests/test_test_chapters.py`：章节文本协议与 shared title-rules 的基础约束。
- 新增 `web_api/tests/test_pipeline_options_owner.py`：验证 web wrapper 与 CLI/core builder 走同一 authority。
- 新增 `web_api/tests/test_db_preflight.py`：旧 schema 检测、统一 fail-fast 文案、迁移后通过。

### Integration
- `web_api/tests/test_test_run.py`：Test 主路径仍能从 transcribe → auto_edit → chapter 跑通。
- `web_api/tests/test_pi_agent_runner.py` / `test_pi_runner_contract.py`：容器支持/不支持模式下的 runtime gate 或 CLI 调用约束。
- `web_api/tests/test_render_web.py` / `test_routes_render_config.py`：render DTO 仍完整，但不再含标题 rewrite/fit 决策。

### E2E
- 本地执行 `scripts/run_pi_test.sh test_data/media/1.wav` 或等价上传/Test/确认/导出路径。
- 若支持容器内 PI/Test：镜像内验证 `pi --help`、skills 可见、Test 主路径至少到 chapter 生成。
- 若不支持：镜像内验证 worker/API/CLI 在相关路径统一 fail-fast。

### Observability
- 为 Step 0 capability probe、schema preflight、legacy migration script 增加明确日志标签。
- 在 Test 主路径日志中保留“当前容器能力判定 / 当前 options owner / 当前 render DTO 模式”关键信息，便于定位回归。

## Verification Steps

### Step 0 验证
- 支持模式：
  1. `docker build -f Dockerfile .`
  2. 进入镜像后注入最小必需 LLM env（`LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`）
  3. 执行 capability probe，期望返回 `supported=true`、稳定 `mode`、空或成功级 `reason_code`
  4. 执行 `pi --help` 作为辅助检查
  5. 用固定 fixture lines 运行一次最小真实 smoke（例如 `python -m video_auto_cut.pi_agent_runner --task delete --input test_data/media/1.srt --output workdir/pi_probe_delete.json`，或等价 `chapter` smoke），确认 repo-root cwd、`.pi/settings.json` 自动加载、skills 解析、runner 调用链都可用。
- 不支持模式：
  1. 对 API Test 入口、worker task 执行入口、CLI 入口分别触发一次 capability probe
  2. 三者都必须返回同一 `reason_code` / `reason_message` contract，并在未满足前置条件时 fail-fast，不进入 `run_test_pi()`。

### Step 1 验证
- 运行：`rg "from web_api\\.|import web_api" video_auto_cut`
- 运行 shared 协议 round-trip 单测：`python -m unittest web_api.tests.test_test_srt_utils web_api.tests.test_test_chapters`

### Step 2 验证
- 运行 options owner/typed config 回归：`python -m unittest web_api.tests.test_pipeline_options_owner web_api.tests.test_test_run web_api.tests.test_pi_agent_runner web_api.tests.test_step2_topic_model`
- 代码 grep：确认 `transcribe.py` / `auto_edit.py` / `topic_segment.py` 不再含业务字段级 `getattr(args, ...)`；若 topic CLI 被正式降级，则 grep 与测试必须同步更新豁免说明。

### Step 3 验证
- 运行：`python -m unittest web_api.tests.test_render_web web_api.tests.test_routes_render_config`
- grep：`rg "topic_segment" web_api/services/render_web.py` 返回空。
- 用 `web_frontend/app/dev-export-preview/page.tsx` 覆盖长标题、横竖屏、低清/高分辨率。

### Step 4 验证
- 用 legacy schema fixture 触发 app/worker/coupon_admin 三入口，确认统一 fail-fast。
- 执行迁移脚本后重复启动检查，确认恢复正常。
- 运行：`python -m unittest web_api.tests.test_db_preflight`

### 全局验证
- `python -m unittest discover web_api/tests -p "test_*.py"`
- `cd web_frontend && npx tsc --noEmit`
- `npm --prefix web_frontend run build`
- 至少 1 条 Test 主路径手工冒烟。

## ADR

### Decision
采用 **“A6 gate 前置 + shared 协议 owner + core-owned options builder + typed stage config + 再删旧双轨/非 live helper/启动副作用”** 的 staged plan，按 Step 0-5 顺序推进 A1-A6。

### Drivers
- 先确认容器前提，避免优化不存在的部署主路径。
- 先统一协议与 options owner，才能稳定收掉 Step2/CLI 双轨。
- A3 需要以实际调用证据为准，而不是把 dead helper 当 live path 风险。

### Alternatives considered
- 一次性大重写：过险。
- 只做文档：不能解决 live coupling。
- 让 `web_api/services/pipeline_options.py` 继续做唯一 builder：会违反“核心层不得反向依赖服务层”，且 CLI 仍是活入口，不接受。

### Why chosen
该路径保留了“低爆炸半径、分阶段验收”的优势，同时明确了 Critic 要求的两个 owner 决策：
- options builder owner 固定在核心编排层；
- title-rules owner 固定在 shared 层。

### Consequences
- 短期内会出现 shared shim / adapter / 显式迁移脚本。
- 需要新增一批 preflight、迁移和容器 smoke test。
- A6 需要产品/部署层面的明确结论，不能无限拖后。

### Follow-ups
- A6 若选择支持容器内 PI/Test，后续还需评估镜像体积、Node 安装时间和 Railway 冷启动影响。
- A3 完成后，可继续衔接 backlog 里的 C4（比例展示规则）与 D3（文档 source of truth）。

## Available-Agent-Types Roster

推荐在后续执行中优先使用这些角色：
- `architect`：守住 A1/A3/A5/A6 的边界与职责分层。
- `executor`：实现 shared 抽取、options owner 合并、typed config、runtime 重构。
- `critic` / `code-reviewer`：把关是否又引入跨层耦合或双 authority。
- `test-engineer`：设计协议 owner、Step2 收口、DB preflight/迁移、容器 smoke 和 render 回归测试。
- `build-fixer`：处理 Python/TS 构建或 Docker 构建故障。
- `verifier`：核对 Acceptance Criteria、测试证据、docker smoke 结果。
- `writer`：同步 `docs/requirements_todo.md`、`docs/web_api_interface.md`、README/部署说明。
- `explorer`：快速确认 import 边界、调用链、遗留 Step2/A3 helper 触点。

## Follow-up Staffing Guidance

### Ralph lane（顺序执行，适合一个人盯质量）
- Phase 0 `architect` + `executor`（high）：只完成 Step 0，先产出 capability probe 与容器支持/不支持结论。
- Phase 1 `architect`（high）：确认 protocol owner、options owner、title-rules owner 三个边界。
- Phase 2 `executor`（high）：做 Step 1-2a，先把 shared owner、options owner 定住。
- Phase 3 `executor`（high）：做 Step 2b-2c，完成 typed config 与旧双轨删除。
- Phase 4 `executor`（medium）：做 Step 3-4，清 render helper、DB init/migration/preflight。
- Phase 5 `test-engineer` + `verifier`（medium/high）：补测试、跑构建、校验 AC。
- Phase 6 `writer`（medium）：同步需求/接口/部署文档。

### Team lane（并行执行，前提是写集隔离）
- **Phase 0（必须先完成，禁止并行跳过）**：由单独 owner 完成 Step 0 capability probe 与容器支持/不支持结论。
- Worker 1：Step 1 shared 协议 owner（`video_auto_cut/shared/*`、`web_api/utils/srt_utils.py`、`transcribe_stage.py`）。
- Worker 2：Step 2a-2b options owner + typed config（`pipeline_service.py`、`pipeline_options.py`、`full_pipeline.py`、`pi_agent_runner.py`、`transcribe.py`、`auto_edit.py`）。
- Worker 3：Step 2c + Step 5 文档收口（`services/step2.py`、`repository.py`、`docs/web_api_interface.md`、`docs/requirements_todo.md`）。
- Worker 4：Step 3-4 render/title-rules/DB（`render_web.py`、`topic_segment.py`、`web_frontend/lib/remotion/*`、`web_api/db.py`、`scripts/*`、`Dockerfile`、README）。
- 收尾：`verifier` 汇总测试与 docker 证据，再由 `architect` 做最终边界复核。

## Launch Hints

### Ralph
```bash
$ralph ".omx/plans/2026-04-16-a-batch-module-boundaries.md"
```

### Team
```bash
$team ".omx/plans/2026-04-16-a-batch-module-boundaries.md"
omx team run .omx/plans/2026-04-16-a-batch-module-boundaries.md
```

## Team Verification Path

1. Step 0 先证明：单一 capability probe 已落地，容器内 PI/Test 能力已有明确支持/不支持结论，且运行时行为一致。
2. Worker 1 证明：`video_auto_cut/` 不再 import `web_api.*`，shared protocol owner 已统一。
3. Worker 2 证明：options owner 已单一且位于核心编排层，typed stage config 已替代 `SimpleNamespace/getattr` 主链路。
4. Worker 3 证明：Step2 runtime 分支被移除，接口/需求文档已同步。
5. Worker 4 证明：`render_web.py` 不再 import `topic_segment`，live 排版仅在前端；`init_db()` 已瘦身并补 preflight。
6. `verifier` 汇总测试、build、docker、手工 smoke 证据。
7. Ralph/最终负责人再核对本计划的 11 条 Acceptance Criteria 后再宣布完成。

## Changelog
- v1：基于仓库现状与 `docs/requirements_todo.md` A1-A6 生成初稿。
- v2：吸收 Architect 审查意见，调整为 A6 gate 前置、A1 先定义协议 owner、A2/A4 拆成“固定 owner → stage typed 化 → 删旧双轨”，并将 A3 收窄为 DTO + dead helper 清理优先。
- v3：吸收 Critic 审查意见，写死 options owner 与 title-rules owner，补充可机械验证的 Acceptance Criteria、分阶段 Verification、pre-mortem 与 expanded test plan。
- v4：吸收第二轮 Architect 审查意见，将 Step 0 制度化为独立前置 phase，新增单一 capability probe owner，并把支持模式验证升级为真实 `run_test_pi()` smoke。
- v5：吸收第三轮 Architect 复审意见，补充 capability probe 的统一结果 contract。
- v6：吸收最终 Critic 审查意见，将 `coupon_admin` 从 A6 probe 覆盖面移回 A5 preflight，并把 `topic_segment.py` 明确纳入 Step 2 typed-config 改造，同时细化 Step 0 可直接执行的验证闭环。
