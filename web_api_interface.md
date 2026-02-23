# Web 前后端接口文档（P0）

更新时间：2026-02-23  
版本：v1

## 1. 文档目标

本文档用于定义 Next.js 前端与 Python（FastAPI）后端在 P0 阶段的接口契约，确保以下能力可联调：

1. 上传视频并做格式/大小校验  
2. Step 1：生成优化字幕与删减建议，支持逐行人工修改  
3. Step 2：生成章节建议，支持人工修改  
4. Step 3：渲染成片，展示任务进度并下载产物  

## 2. 全局约定

## 2.1 Base URL

- 本地开发：`http://localhost:8000/api/v1`
- 生产环境：`https://<your-domain>/api/v1`

## 2.2 鉴权（P0）

- P0 不做登录鉴权。
- 所有接口默认开放到内网或受控环境。
- P1 再扩展 `Authorization: Bearer <token>`。

## 2.3 数据格式

- 请求：`application/json`（上传接口除外）
- 响应：`application/json`
- 时间：ISO8601 UTC（例如 `2026-02-23T10:20:30Z`）

## 2.4 统一响应结构

成功：

```json
{
  "request_id": "req_01HXYZ",
  "data": {}
}
```

失败：

```json
{
  "request_id": "req_01HXYZ",
  "error": {
    "code": "INVALID_STEP_STATE",
    "message": "Step1 must be confirmed before Step2 run",
    "details": {}
  }
}
```

## 2.5 统一错误码（P0）

| code | 含义 | HTTP |
|---|---|---|
| `BAD_REQUEST` | 参数错误 | 400 |
| `NOT_FOUND` | 资源不存在 | 404 |
| `UNSUPPORTED_VIDEO_FORMAT` | 不支持的视频格式 | 422 |
| `UPLOAD_TOO_LARGE` | 上传文件超过限制 | 413 |
| `VIDEO_STREAM_NOT_FOUND` | 文件中无可读视频流 | 422 |
| `INVALID_STEP_STATE` | 步骤状态不合法 | 409 |
| `REVISION_CONFLICT` | 编辑版本冲突 | 409 |
| `TASK_ALREADY_RUNNING` | 当前任务正在执行 | 409 |
| `INTERNAL_ERROR` | 服务内部错误 | 500 |

## 3. 任务状态机

| status | 说明 | 前端动作 |
|---|---|---|
| `CREATED` | 任务已创建，未上传 | 显示上传控件 |
| `UPLOADING` | 上传中 | 显示上传进度 |
| `UPLOAD_READY` | 上传并校验完成 | 可触发 Step1 |
| `STEP1_RUNNING` | Step1 处理中 | 显示处理中 |
| `STEP1_READY` | Step1 结果已生成 | 进入逐行编辑 |
| `STEP1_CONFIRMED` | Step1 已确认 | 可触发 Step2 |
| `STEP2_RUNNING` | Step2 处理中 | 显示处理中 |
| `STEP2_READY` | Step2 结果已生成 | 进入章节编辑 |
| `STEP2_CONFIRMED` | Step2 已确认 | 可触发渲染 |
| `RENDER_RUNNING` | 渲染中 | 显示渲染进度 |
| `SUCCEEDED` | 全流程成功 | 展示下载按钮 |
| `FAILED` | 任务失败 | 展示错误并可重试 |

## 4. 核心数据模型

## 4.1 Job

```json
{
  "job_id": "job_01HXYZ",
  "status": "STEP1_READY",
  "progress": 55,
  "current_step": "step1",
  "created_at": "2026-02-23T10:20:30Z",
  "updated_at": "2026-02-23T10:28:11Z",
  "error": null
}
```

## 4.2 Step1 Line（逐行编辑）

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

## 4.3 Step2 Chapter（章节编辑）

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

## 4.4 Artifact（产物）

```json
{
  "name": "final_video",
  "filename": "demo_remotion.mp4",
  "download_url": "/api/v1/jobs/job_01HXYZ/artifacts/final_video/download",
  "size_bytes": 128900123
}
```

## 5. API 详细定义

## 5.1 创建任务

`POST /jobs`

请求体：

```json
{}
```

响应：

```json
{
  "request_id": "req_x1",
  "data": {
    "job": {
      "job_id": "job_01HXYZ",
      "status": "CREATED",
      "progress": 0,
      "current_step": "upload",
      "created_at": "2026-02-23T10:20:30Z",
      "updated_at": "2026-02-23T10:20:30Z",
      "error": null
    }
  }
}
```

## 5.2 上传视频并校验

`POST /jobs/{job_id}/upload`

`Content-Type: multipart/form-data`

字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | binary | 是 | 视频文件 |

校验规则：

1. 扩展名：`.mp4 .mov .mkv .avi .webm .flv .f4v`
2. 文件大小：默认 `<= 2048MB`（由 `MAX_UPLOAD_MB` 控制）
3. `ffprobe` 校验：必须有可读视频流

响应：

```json
{
  "request_id": "req_x2",
  "data": {
    "job": {
      "job_id": "job_01HXYZ",
      "status": "UPLOAD_READY",
      "progress": 10,
      "current_step": "step1",
      "created_at": "2026-02-23T10:20:30Z",
      "updated_at": "2026-02-23T10:22:01Z",
      "error": null
    },
    "upload": {
      "filename": "input.MOV",
      "size_bytes": 801245112,
      "duration_sec": 182.37,
      "video_codec": "h264",
      "audio_codec": "aac"
    }
  }
}
```

## 5.3 查询任务状态

`GET /jobs/{job_id}`

响应：

```json
{
  "request_id": "req_x3",
  "data": {
    "job": {
      "job_id": "job_01HXYZ",
      "status": "STEP1_RUNNING",
      "progress": 35,
      "current_step": "step1",
      "created_at": "2026-02-23T10:20:30Z",
      "updated_at": "2026-02-23T10:23:15Z",
      "error": null
    }
  }
}
```

前端轮询建议：`2s` 一次，状态到 `*_READY / *_CONFIRMED / SUCCEEDED / FAILED` 后停止轮询。

## 5.4 运行 Step1（ASR + 优化建议）

`POST /jobs/{job_id}/step1/run`

前置状态：`UPLOAD_READY`

请求体（可选参数）：

```json
{
  "lang": "Chinese",
  "device": "cpu",
  "llm_model": "qwen3-max"
}
```

响应：

```json
{
  "request_id": "req_x4",
  "data": {
    "accepted": true,
    "job_id": "job_01HXYZ",
    "status": "STEP1_RUNNING"
  }
}
```

## 5.5 获取 Step1 结果（逐行列表）

`GET /jobs/{job_id}/step1/result`

前置状态：`STEP1_READY` 或 `STEP1_CONFIRMED`

响应：

```json
{
  "request_id": "req_x5",
  "data": {
    "revision": 3,
    "lines": [
      {
        "line_id": 1,
        "start": 0.0,
        "end": 2.4,
        "original_text": "我们今天讲三个点",
        "optimized_text": "我们今天讲三个点。",
        "ai_suggest_remove": false,
        "user_final_remove": false,
        "user_edited": false
      },
      {
        "line_id": 2,
        "start": 2.4,
        "end": 3.8,
        "original_text": "呃不对我重说",
        "optimized_text": "呃不对我重说",
        "ai_suggest_remove": true,
        "user_final_remove": true,
        "user_edited": false
      }
    ]
  }
}
```

## 5.6 保存 Step1 人工修改

`PUT /jobs/{job_id}/step1/result`

请求体：

```json
{
  "revision": 3,
  "lines": [
    {
      "line_id": 1,
      "optimized_text": "我们今天讲三个点。",
      "user_final_remove": false
    },
    {
      "line_id": 2,
      "optimized_text": "呃不对我重说",
      "user_final_remove": false
    }
  ]
}
```

响应：

```json
{
  "request_id": "req_x6",
  "data": {
    "revision": 4,
    "saved": true
  }
}
```

说明：若 `revision` 不匹配，返回 `REVISION_CONFLICT`。

## 5.7 确认 Step1

`POST /jobs/{job_id}/step1/confirm`

请求体：

```json
{
  "revision": 4
}
```

响应：

```json
{
  "request_id": "req_x7",
  "data": {
    "confirmed": true,
    "status": "STEP1_CONFIRMED"
  }
}
```

## 5.8 运行 Step2（章节建议）

`POST /jobs/{job_id}/step2/run`

前置状态：`STEP1_CONFIRMED`

请求体（可选）：

```json
{
  "max_topics": 8,
  "summary_max_chars": 6
}
```

响应：

```json
{
  "request_id": "req_x8",
  "data": {
    "accepted": true,
    "status": "STEP2_RUNNING"
  }
}
```

## 5.9 获取 Step2 结果（章节列表）

`GET /jobs/{job_id}/step2/result`

前置状态：`STEP2_READY` 或 `STEP2_CONFIRMED`

响应：

```json
{
  "request_id": "req_x9",
  "data": {
    "revision": 2,
    "chapters": [
      {
        "chapter_id": 1,
        "title": "开场",
        "summary": "说明主题",
        "start": 0.0,
        "end": 32.5,
        "line_ids": [1, 2, 3, 4]
      },
      {
        "chapter_id": 2,
        "title": "核心方法",
        "summary": "给出步骤",
        "start": 32.5,
        "end": 90.1,
        "line_ids": [5, 6, 7, 8, 9]
      }
    ]
  }
}
```

## 5.10 保存 Step2 人工修改

`PUT /jobs/{job_id}/step2/result`

请求体：

```json
{
  "revision": 2,
  "chapters": [
    {
      "chapter_id": 1,
      "title": "开场问题",
      "summary": "先抛出痛点",
      "start": 0.0,
      "end": 30.0,
      "line_ids": [1, 2, 3]
    },
    {
      "chapter_id": 2,
      "title": "解决方案",
      "summary": "给出可执行步骤",
      "start": 30.0,
      "end": 90.1,
      "line_ids": [4, 5, 6, 7, 8, 9]
    }
  ]
}
```

响应：

```json
{
  "request_id": "req_x10",
  "data": {
    "revision": 3,
    "saved": true
  }
}
```

## 5.11 确认 Step2

`POST /jobs/{job_id}/step2/confirm`

请求体：

```json
{
  "revision": 3
}
```

响应：

```json
{
  "request_id": "req_x11",
  "data": {
    "confirmed": true,
    "status": "STEP2_CONFIRMED"
  }
}
```

## 5.12 启动渲染

`POST /jobs/{job_id}/render/run`

前置状态：`STEP2_CONFIRMED`

请求体（可选）：

```json
{
  "render_preview": false,
  "render_fps": 30,
  "render_codec": "h264",
  "render_crf": 18
}
```

响应：

```json
{
  "request_id": "req_x12",
  "data": {
    "accepted": true,
    "status": "RENDER_RUNNING"
  }
}
```

## 5.13 获取产物清单

`GET /jobs/{job_id}/artifacts`

建议在任务状态 `SUCCEEDED` 后调用。

响应：

```json
{
  "request_id": "req_x13",
  "data": {
    "artifacts": [
      {
        "name": "final_video",
        "filename": "input_remotion.mp4",
        "download_url": "/api/v1/jobs/job_01HXYZ/artifacts/final_video/download",
        "size_bytes": 182901231
      },
      {
        "name": "cut_srt",
        "filename": "input.cut.srt",
        "download_url": "/api/v1/jobs/job_01HXYZ/artifacts/cut_srt/download",
        "size_bytes": 20123
      },
      {
        "name": "topics_json",
        "filename": "input.cut.topics.json",
        "download_url": "/api/v1/jobs/job_01HXYZ/artifacts/topics_json/download",
        "size_bytes": 3921
      }
    ]
  }
}
```

## 5.14 下载单个产物

`GET /jobs/{job_id}/artifacts/{artifact_name}/download`

响应：文件流（`video/mp4`、`application/json`、`text/plain` 等）

## 6. 前端（Next.js）数据契约建议

```ts
export type JobStatus =
  | "CREATED"
  | "UPLOADING"
  | "UPLOAD_READY"
  | "STEP1_RUNNING"
  | "STEP1_READY"
  | "STEP1_CONFIRMED"
  | "STEP2_RUNNING"
  | "STEP2_READY"
  | "STEP2_CONFIRMED"
  | "RENDER_RUNNING"
  | "SUCCEEDED"
  | "FAILED";

export interface Job {
  job_id: string;
  status: JobStatus;
  progress: number;
  current_step: "upload" | "step1" | "step2" | "render";
  created_at: string;
  updated_at: string;
  error: null | { code: string; message: string };
}

export interface Step1Line {
  line_id: number;
  start: number;
  end: number;
  original_text: string;
  optimized_text: string;
  ai_suggest_remove: boolean;
  user_final_remove: boolean;
  user_edited: boolean;
}

export interface Chapter {
  chapter_id: number;
  title: string;
  summary: string;
  start: number;
  end: number;
  line_ids: number[];
}
```

## 7. 前端联调时序（P0）

1. `POST /jobs`  
2. `POST /jobs/{job_id}/upload`  
3. `POST /jobs/{job_id}/step1/run` + 轮询 `GET /jobs/{job_id}`  
4. `GET /jobs/{job_id}/step1/result` -> 编辑 -> `PUT /step1/result` -> `POST /step1/confirm`  
5. `POST /jobs/{job_id}/step2/run` + 轮询 `GET /jobs/{job_id}`  
6. `GET /jobs/{job_id}/step2/result` -> 编辑 -> `PUT /step2/result` -> `POST /step2/confirm`  
7. `POST /jobs/{job_id}/render/run` + 轮询 `GET /jobs/{job_id}`  
8. `GET /jobs/{job_id}/artifacts` + 下载  

## 8. 与现有后端模块映射

| API 阶段 | 对应模块 |
|---|---|
| Step1 run | `video_auto_cut/asr/transcribe.py` + `video_auto_cut/editing/auto_edit.py` |
| Step2 run | `video_auto_cut/editing/topic_segment.py` |
| Render run | `video_auto_cut/rendering/remotion_renderer.py` |

## 9. 非功能要求（P0）

1. 所有长任务必须异步执行，避免 HTTP 请求超时。  
2. 任务状态更新必须持久化（SQLite 即可）。  
3. 下载接口必须校验 `job_id` 与文件归属关系，防止越权读取。  
4. 错误信息要区分“用户可修复”和“系统异常”。  

