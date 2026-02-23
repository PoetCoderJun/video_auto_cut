# Web MVP 开发计划与架构设计

更新时间：2026-02-23  
输入依据：`web_mvp_plan.md`、`web_api_interface.md`

## 1. 目标与边界

## 1.1 MVP 目标

在最短时间内交付可用的 Web 版自动剪辑闭环：

1. 上传并校验视频  
2. Step1：生成逐行建议并人工确认  
3. Step2：生成章节并人工确认  
4. 渲染并下载最终视频  

## 1.2 MVP 不做

- 登录/支付/权限系统  
- 多机扩缩容  
- 实时推送（先用轮询）  

## 2. 总体架构

## 2.1 架构分层

1. 前端层（Next.js）
- 页面：上传、Step1 编辑、Step2 编辑、渲染进度、下载
- 与后端通过 REST 接口通信（`/api/v1`）
- 任务状态通过轮询 `GET /jobs/{job_id}`

2. API 层（FastAPI）
- 提供 11 个 MVP 接口（见 `web_api_interface.md`）
- 只做参数校验、状态流转、任务调度、结果读写
- 不直接承载耗时任务

3. Worker 层（Python 后台任务）
- 执行 Step1/Step2/Render 长任务
- 复用现有核心模块，不改算法内核

4. 存储层
- SQLite：任务状态与结构化结果
- 本地文件系统：上传文件、中间文件、渲染产物

## 2.2 关键模块映射

- Step1：`video_auto_cut/asr/transcribe.py` + `video_auto_cut/editing/auto_edit.py`
- Step2：`video_auto_cut/editing/topic_segment.py`
- Render：`video_auto_cut/rendering/remotion_renderer.py`

## 2.3 目录建议

```text
web_api/
  app.py
  api/
    jobs.py
  service/
    job_service.py
    step1_service.py
    step2_service.py
    render_service.py
  worker/
    runner.py
  repo/
    sqlite_repo.py
  model/
    schemas.py
  utils/
    media_validate.py
    paths.py

web_frontend/   (Next.js)
  app/
    page.tsx
    jobs/[jobId]/page.tsx
  components/
    upload-panel.tsx
    step1-editor.tsx
    step2-editor.tsx
    progress-panel.tsx
  lib/
    api-client.ts
    types.ts
```

## 3. 核心流程设计

## 3.1 状态机

`CREATED -> UPLOAD_READY -> STEP1_RUNNING -> STEP1_READY -> STEP1_CONFIRMED -> STEP2_RUNNING -> STEP2_READY -> STEP2_CONFIRMED -> RENDER_RUNNING -> SUCCEEDED/FAILED`

说明：
- 任一步骤失败都进入 `FAILED`，记录错误信息。
- 用户可在失败后重试当前步骤（不回退已确认步骤）。

## 3.2 上传流程

1. 前端 `POST /jobs` 创建任务  
2. 前端 `POST /jobs/{job_id}/upload` 上传文件  
3. 后端执行：
- 扩展名校验
- 大小校验（`MAX_UPLOAD_MB`）
- `ffprobe` 校验视频流
4. 成功后写入 `UPLOAD_READY`

## 3.3 Step1 流程（逐行 HITL）

1. `POST /jobs/{job_id}/step1/run` 触发后台任务  
2. Worker 调用 ASR + auto_edit 生成建议  
3. `GET /jobs/{job_id}/step1` 返回逐行列表  
4. 前端编辑后 `PUT /jobs/{job_id}/step1/confirm` 一次性提交并确认  
5. 后端写入 `STEP1_CONFIRMED`

## 3.4 Step2 流程（章节 HITL）

1. `POST /jobs/{job_id}/step2/run` 触发章节生成  
2. `GET /jobs/{job_id}/step2` 返回章节列表  
3. 前端编辑后 `PUT /jobs/{job_id}/step2/confirm` 提交并确认  
4. 后端写入 `STEP2_CONFIRMED`

## 3.5 渲染与下载流程

1. `POST /jobs/{job_id}/render/run` 触发渲染任务  
2. Worker 调用 `remotion_renderer` 生成成片  
3. 状态更新为 `SUCCEEDED`  
4. 前端调用 `GET /jobs/{job_id}/download` 下载视频

## 4. 数据设计（MVP）

## 4.1 SQLite 表（建议最小化）

`jobs`
- `job_id` (pk)
- `status`
- `progress`
- `error_code` (nullable)
- `error_message` (nullable)
- `created_at`
- `updated_at`

`job_step1_lines`
- `job_id`
- `line_id`
- `start_sec`
- `end_sec`
- `original_text`
- `optimized_text`
- `ai_suggest_remove`
- `user_final_remove`

`job_step2_chapters`
- `job_id`
- `chapter_id`
- `title`
- `summary`
- `start_sec`
- `end_sec`
- `line_ids_json`

`job_files`
- `job_id`
- `video_path`
- `srt_path`
- `optimized_srt_path`
- `topics_path`
- `final_video_path`

## 4.2 文件路径约定

```text
workdir/jobs/{job_id}/
  input/<original_file>
  step1/
    input.srt
    optimized.srt
    final_step1.json
  step2/
    topics.json
    final_topics.json
  render/
    output.mp4
```

## 5. 开发计划（两周到三周）

## 5.1 里程碑与交付

1. M1（D1-D3）：基础骨架与上传
- FastAPI 项目骨架
- `/jobs`、`/jobs/{id}`、`/upload`
- 视频格式/大小/ffprobe 校验
- Next.js 上传页 + 任务状态页

2. M2（D4-D7）：Step1 闭环
- `/step1/run`、`/step1`、`/step1/confirm`
- Worker 集成 `transcribe + auto_edit`
- Step1 逐行编辑 UI（删除勾选 + 文本可改）

3. M3（D8-D10）：Step2 闭环
- `/step2/run`、`/step2`、`/step2/confirm`
- Worker 集成 `topic_segment`
- Step2 章节编辑 UI（标题/摘要/范围）

4. M4（D11-D13）：渲染与下载
- `/render/run`、`/download`
- Worker 集成 `remotion_renderer`
- 前端进度条 + 下载按钮

5. M5（D14）：稳定性与验收
- 异常路径处理
- 日志补齐
- E2E 冒烟测试

## 5.2 任务拆分

后端：
- 接口实现与状态机约束
- Worker 调度与任务隔离
- SQLite 持久化
- 文件路径与清理策略

前端：
- 上传页、编辑页、进度页
- API Client 与类型定义
- 状态轮询和错误提示

联调：
- 按 `web_api_interface.md` 顺序逐步联调
- 每个里程碑保留可演示版本

## 6. 验收标准（MVP）

1. 用户可完成一次完整流程并拿到可下载 MP4。  
2. Step1 默认删除建议符合“AI 建议删 -> 默认勾选”。  
3. Step2 章节支持人工修改后再渲染。  
4. 失败场景能返回清晰错误并可重试。  
5. 前端无刷新完成全流程操作。  

## 7. 风险与应对

1. 长任务超时  
- 方案：全部改为后台任务；API 只返回 accepted。

2. 渲染依赖问题（Node/ffmpeg/remotion）  
- 方案：服务启动时依赖自检；失败直接阻断 render 接口。

3. 大文件上传失败  
- 方案：MVP 先限制 2GB 内；失败后给出可理解提示。  

4. LLM 结果质量波动  
- 方案：保持 HITL，可人工修改后确认。  

## 8. 部署架构（MVP）

## 8.1 单机部署

- `nginx`：统一入口与反向代理  
- `next.js`：前端服务（`next start`）  
- `fastapi`：API 服务（`uvicorn`）  
- `worker`：后台任务进程  
- `sqlite + 本地磁盘`：状态与文件  

## 8.2 端口与路由（自部署默认）

- `Nginx` 对外：`80/443`
- `Next.js` 内网：`127.0.0.1:3000`
- `FastAPI` 内网：`127.0.0.1:8000`
- 路由规则：
- `/` 和页面路由 -> `Next.js`
- `/api/v1/*` -> `FastAPI`
- 下载接口由 `FastAPI` 返回文件流，不直接暴露磁盘目录

## 8.3 启动方式（推荐）

- `Next.js`
- `npm ci && npm run build && pm2 start \"npm run start -- -p 3000\" --name web-frontend`
- `FastAPI`
- `uvicorn web_api.app:app --host 127.0.0.1 --port 8000 --workers 2`
- `Worker`
- `python -m web_api.worker.runner`

## 8.4 上线最小步骤

1. 安装依赖：`python`、`node`、`ffmpeg`、`nginx`
2. 配置环境变量（见 8.5）
3. 启动 `FastAPI` 和 `Worker`
4. 构建并启动 `Next.js`
5. 配置 Nginx 反向代理并开启 HTTPS
6. 冒烟验证：
- `POST /api/v1/jobs`
- 上传一个小视频
- 全链路跑到下载成功

## 8.5 环境变量建议

- `MAX_UPLOAD_MB=2048`
- `WORK_DIR=./workdir`
- `LLM_BASE_URL=...`
- `LLM_MODEL=...`
- `LLM_API_KEY=...`
- `NODE_ENV=production`

## 9. 第一阶段实现优先级（必须先做）

1. `jobs + upload + job_status`  
2. `step1 run/get/confirm`  
3. `step2 run/get/confirm`  
4. `render run + download`  

只要以上四组打通，即达到 MVP 可交付标准。
