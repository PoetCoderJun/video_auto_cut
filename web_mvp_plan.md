# Web 版自动口播剪辑项目规划（P0 骨架）

更新时间：2026-02-23

## 1. 目标与范围

### 1.1 项目目标（当前阶段）
- 把已在 Mac 本地跑通的命令行流程，升级为 Web 可用版本。
- 面向不懂技术的自媒体用户，提供最少步骤的一键流程。
- 优先实现核心骨架，不做用户管理和付费系统。

### 1.2 本阶段明确不做
- 登录/注册/权限管理
- 计费、支付、订单
- 多租户隔离、企业级审计
- 大规模并发优化（先保证单机/小规模可用）

## 2. 核心用户流程（3 步 + 进度）

1. 上传视频（含格式和大小校验）
2. Step 1：生成优化字幕与切片建议（HITL 可改）
3. Step 2：生成章节建议（HITL 可改）
4. Step 3：确认后渲染并下载成片（展示进度条）

说明：每一步都必须“确认”后才能进入下一步。

## 3. 功能需求拆解

## 3.1 上传与校验（P0）

### 前端（H5）
- 使用通用 H5 上传界面：点击上传 + 拖拽上传。
- 上传后显示：文件名、大小、时长（校验通过后）、状态。

### 后端校验规则
- 扩展名白名单（P0）：`.mp4 .mov .mkv .avi .webm .flv .f4v`
- MIME/容器校验：不能只看扩展名，需二次校验。
- `ffprobe` 校验：确认存在可读视频流。
- 文件大小限制：默认 `<= 2048MB`（通过环境变量可配置，例如 `MAX_UPLOAD_MB`）。
- 校验失败返回清晰错误文案（给非技术用户可理解提示）。

### 建议错误提示（示例）
- 格式不支持：`仅支持 mp4/mov`
- 文件过大：`文件超过 2GB，请压缩后重试`
- 文件损坏：`视频文件无法读取，请重新导出后上传`

## 3.2 Step 1：优化字幕与切片（HITL，P0）

### 目标
基于现有流程 `ASR -> auto_edit` 先生成建议，再让用户逐行确认。

### 列表交互（逐行）
每一行包含：
- 行号
- 时间范围（start/end）
- 原文本（可查看）
- 优化后文本（可直接编辑）
- 是否删除（checkbox）

### 默认选中逻辑（严格按你的要求）
- 大模型建议删除的行：默认选中“删除”
- 大模型未建议删除的行：默认不选中
- 用户可手工修改任意行（勾选状态和文本内容都可改）

### 确认动作
- 点击“确认 Step 1”后，冻结 Step 1 结果并进入 Step 2。
- 后端保存 `final_step1.json`（用于可追溯和后续渲染）。

## 3.3 Step 2：章节生成与人工修订（HITL，P0）

### 目标
基于 Step 1 确认后的内容生成章节，再允许用户修改。

### 章节列表交互
每个章节包含：
- 章节序号（1/2/3/4...）
- 标题（可编辑）
- 摘要（可编辑）
- 覆盖时间范围（start/end，可编辑）
- 包含的行范围（可调整）

### 确认动作
- 点击“确认 Step 2”后，冻结章节结果。
- 后端保存 `final_topics.json`。

## 3.4 Step 3：渲染与进度条（P0）

### 渲染前置
- 仅在 Step 1、Step 2 都确认后可触发。

### 进度条阶段建议
- `10%` 上传完成
- `35%` Step 1 处理中
- `55%` Step 1 已确认
- `75%` Step 2 处理中/确认
- `95%` 渲染中
- `100%` 完成（可下载）

### 产物
- 最终视频：`*_remotion.mp4`
- 中间产物：`.srt`、`.optimized.srt`、`.cut.srt`、`.cut.topics.json`
- 人工确认产物：`final_step1.json`、`final_topics.json`

## 4. 技术架构建议

## 4.1 后端（确认 Python）

### 推荐技术栈（P0）
- API：FastAPI
- 异步任务：RQ/Celery（二选一，P0 可先用 FastAPI BackgroundTasks）
- 任务状态存储：SQLite（P0）
- 文件存储：本地磁盘（P0）

### 与当前代码衔接
- 直接复用现有模块：
  - `video_auto_cut/asr/transcribe.py`
  - `video_auto_cut/editing/auto_edit.py`
  - `video_auto_cut/editing/topic_segment.py`
  - `video_auto_cut/rendering/remotion_renderer.py`
- 新增 `web_api/` 做适配层，不改动核心算法模块。

## 4.2 前端：Next.js（已确定）

### 结论（按你的要求）
- 前端框架确定为 `Next.js`。
- 部署方式确认：采用纯自部署（不使用 Vercel / EdgeOne）。
- P0 阶段以工作台为主：上传、任务状态、逐行编辑、章节编辑、渲染进度。

### 技术落地建议（P0）
- `Next.js + TypeScript + App Router`
- 交互密集页面优先 `Client Components`，避免不必要 SSR 复杂度。
- 状态管理可先用 `Zustand` 或 React Context（保持轻量）。
- 与 Python 后端通过 REST API 通信，任务进度先用轮询，后续可升级 SSE/WebSocket。

### 部署建议（纯自部署）
- 默认方案：`Nginx + Next.js(next start) + FastAPI(uvicorn) + Worker`。
- 静态资源和上传资源分离，上传文件由 Python 服务管理，前端只负责交互与展示。
- 若后续要标准化交付，再切 `Docker + Nginx`（P1）。

## 4.3 已确认部署方案（MVP）

### 服务拓扑（单机）
- `Nginx`：`80/443`，统一入口和 HTTPS
- `Next.js`：`127.0.0.1:3000`
- `FastAPI`：`127.0.0.1:8000`
- `Worker`：后台任务进程（无公网端口）
- `SQLite + 本地磁盘`：任务状态和视频产物

### Nginx 路由约定
- `/` -> `Next.js:3000`
- `/api/v1/*` -> `FastAPI:8000`
- `/downloads/*` -> 由 FastAPI 校验后返回下载流

### 进程管理
- `Next.js`：`pm2` 或 `systemd`
- `FastAPI`：`systemd`（或 `supervisor`）
- `Worker`：独立 `systemd` 服务，避免和 API 进程混跑

## 5. API 骨架（建议）

以 `web_api_interface.md` 为准，MVP 实现 11 个接口：

## 5.1 任务与上传
- `POST /api/v1/jobs`
  - 创建任务，返回 `job_id`
- `GET /api/v1/jobs/{job_id}`
  - 查询任务状态与进度
- `POST /api/v1/jobs/{job_id}/upload`
  - 上传并校验视频

## 5.2 Step 1（字幕/切片）
- `POST /api/v1/jobs/{job_id}/step1/run`
  - 异步生成 Step1 结果
- `GET /api/v1/jobs/{job_id}/step1`
  - 获取逐行列表
- `PUT /api/v1/jobs/{job_id}/step1/confirm`
  - 提交并确认 Step1

## 5.3 Step 2（章节）
- `POST /api/v1/jobs/{job_id}/step2/run`
  - 异步生成章节
- `GET /api/v1/jobs/{job_id}/step2`
  - 获取章节列表
- `PUT /api/v1/jobs/{job_id}/step2/confirm`
  - 提交并确认 Step2

## 5.4 渲染与下载
- `POST /api/v1/jobs/{job_id}/render/run`
  - 启动渲染
- `GET /api/v1/jobs/{job_id}/download`
  - 下载最终视频

## 6. 数据结构（最小闭环）

## 6.1 Step 1 行数据
```json
{
  "line_id": 12,
  "start": 35.2,
  "end": 37.8,
  "original_text": "我们先说第一点",
  "optimized_text": "我们先说第一点。",
  "ai_suggest_remove": false,
  "user_final_remove": false,
  "user_edited": true
}
```

## 6.2 Step 2 章节数据
```json
{
  "chapter_id": 2,
  "title": "第二个问题",
  "summary": "讲清常见误区",
  "start": 45.0,
  "end": 88.5,
  "line_ids": [18, 19, 20, 21]
}
```

## 7. 里程碑（建议）

1. M1（P0-1）：上传 + 校验 + 任务状态
2. M2（P0-2）：Step 1 建议生成 + 逐行 HITL 编辑 + 确认
3. M3（P0-3）：Step 2 章节生成 + 章节 HITL 编辑 + 确认
4. M4（P0-4）：渲染 + 进度条 + 下载
5. M5（P0-5）：稳定性修复 + Demo 打包

## 8. 风险与对策

- 长视频处理耗时高：采用异步任务 + 前端轮询/事件推送。
- LLM 建议不准：默认仅“建议”，最终以人工确认为准。
- 上传失败率：前端分片/断点续传（P1），P0 先整文件上传。
- 渲染依赖复杂：后端启动时做依赖自检（ffmpeg/node/remotion）。

## 9. 需要你确认的决策点

1. P0 文件大小上限是否确定为 `2GB`？
2. 自部署第一版是否按“单机拓扑”上线（`Nginx + Next + FastAPI + Worker + SQLite`）？
3. Step 2 章节编辑粒度：
   - 仅改标题/摘要
   - 还是允许调整章节覆盖的行范围（推荐）

## 10. 参考（技术选型）

- Next.js 官方部署文档（包含自托管）：https://nextjs.org/docs/app/building-your-application/deploying
- Next.js 自托管指南：https://nextjs.org/docs/app/guides/self-hosting
- Next.js 静态导出：https://nextjs.org/docs/app/building-your-application/deploying/static-exports

## 11. 接口文档

- 前后端接口规范（P0）：`web_api_interface.md`
- 开发计划与架构设计：`web_dev_plan_architecture.md`
