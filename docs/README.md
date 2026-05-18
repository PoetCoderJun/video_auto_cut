# Docs

当前文档按“什么是当前 source of truth”来组织，而不是按历史产物堆叠。

## 当前维护中的文档

- `requirements_todo.md`
  - 当前需求、执行状态和后续动作的唯一追踪面。
- `web_api_interface.md`
  - 当前 Web API 对外契约说明，只覆盖仍在维护的路由与流程。
- `net_feel_packaging_brainstorm.md`
  - 网感剪辑三层定义，以及后续轻量包装体系的头脑风暴与实现边界。
- `open_source_strategy.md`
  - 开源协议、开放范围、商业线上服务保留范围和发布前检查清单。
- `current_prompts_inventory.txt`
  - 当前 prompt / skill / system prompt 入口索引；真正的 source of truth 仍是对应源码或 `SKILL.md` 文件本身。
- `plans/2026-04-15-asr-boundary-layering.md`
  - ASR 三层边界设计稿，供后续 A/B 批次实现参考。

## 历史规划文档

- `plans/`
  - 历史 ralplan / PRD /执行方案归档；这些文档提供背景，但不自动覆盖当前代码与接口事实。

## 运行与部署边界

- 根目录 `Dockerfile` 当前只打包 `requirements.txt`、`web_api/`、`video_auto_cut/`。
- 它会把 `skills/direct-prompts/` 打进 API / worker 镜像，因为运行时 direct prompt loader 依赖这些文件。
- 它**不会**把 `scripts/`、`web_frontend/` 打进 API / worker 镜像。
- API / worker 镜像内的 Test 编辑链路走 Python direct-prompt runner，不再依赖 repo-local PI 配置。
