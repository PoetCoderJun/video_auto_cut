# Context Snapshot: PI Agent Decoupling Review

- task statement: Review current PI agent implementation from first principles; determine whether editing/clipping is a skill vs coupled to core/backend; define path to complete decoupling so clipping can run directly in Codex.
- desired outcome: Architecture review with verdict, concrete coupling map, target decoupled architecture, and migration plan.
- known facts/evidence:
  - PI auto-edit logic lives in `video_auto_cut/editing/auto_edit.py` and `pi_agent_*` modules.
  - Web backend Step1 orchestration calls `video_auto_cut.orchestration.pipeline_service.run_auto_edit()` from `web_api/services/step1.py`.
  - There is a workflow skill at `skills/video-auto-cut-human-loop/SKILL.md`, but it explicitly reuses repo modules instead of owning loop/chunk logic.
  - `AutoEdit` directly instantiates remove/polish/boundary PI loops and owns LLM config/building plus callbacks.
- constraints:
  - User wants complete decoupling standard: clipping should run directly in Codex.
  - Review only; avoid speculative implementation without grounded inspection.
  - Need to maintain `docs/requirements_todo.md` when adding a new requirement/change request.
- unknowns/open questions:
  - How much of current coupling is acceptable adapter glue vs domain leakage?
  - Whether a CLI/wrapper already provides a codex-direct execution lane robust enough for the user standard.
  - Whether chapter generation/export stages are also entangled with web-specific persistence.
- likely codebase touchpoints:
  - `video_auto_cut/editing/auto_edit.py`
  - `video_auto_cut/editing/pi_agent_*.py`
  - `video_auto_cut/orchestration/pipeline_service.py`
  - `video_auto_cut/orchestration/full_pipeline.py`
  - `web_api/services/step1.py`
  - `skills/video-auto-cut-human-loop/SKILL.md`
  - `docs/requirements_todo.md`


## User Override (2026-04-14)

最新用户明确：本轮要修的是当前目录 `video_auto_cut`，`tracking_agent` 只是边界干净的参考实现，不是目标仓库。

新的目标终态：
- 只保留 3 个 editing skills：`delete`、`polish`、`chapter`。
- 暂时抛弃其它多余 flow。
- 使用更大的模型，因此不再围绕 chunking 设计。
- 不再显式设计 JSON repair / fixup prompts。
- 在一个统一的 system prompt 中描述完整任务。
- 产出一个干净的 PI runner，skills 与 runner 解耦。
