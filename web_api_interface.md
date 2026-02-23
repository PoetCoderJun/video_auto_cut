# Web 前后端接口文档（精简 MVP）

更新时间：2026-02-23  
版本：v1-mvp

## 1. 目标

只覆盖最小可用闭环：

1. 上传并校验视频
2. Step1 生成并人工确认逐行字幕
3. Step2 生成并人工确认章节
4. 渲染并下载成片

不包含：登录、支付、复杂权限、多端同步。

## 2. 全局约定

- Base URL：`/api/v1`
- 响应格式：`application/json`（下载接口除外）
- 鉴权：P0 不做

统一成功响应：

```json
{
  "request_id": "req_x1",
  "data": {}
}
```

统一失败响应：

```json
{
  "request_id": "req_x1",
  "error": {
    "code": "INVALID_STEP_STATE",
    "message": "Step1 not confirmed"
  }
}
```

MVP 只保留 6 个错误码：

- `BAD_REQUEST` (400)
- `NOT_FOUND` (404)
- `UPLOAD_TOO_LARGE` (413)
- `UNSUPPORTED_VIDEO_FORMAT` (422)
- `INVALID_STEP_STATE` (409)
- `INTERNAL_ERROR` (500)

## 3. 状态与进度（最小集合）

`status` 枚举：

- `CREATED`
- `UPLOAD_READY`
- `STEP1_RUNNING`
- `STEP1_READY`
- `STEP1_CONFIRMED`
- `STEP2_RUNNING`
- `STEP2_READY`
- `STEP2_CONFIRMED`
- `RENDER_RUNNING`
- `SUCCEEDED`
- `FAILED`

`progress` 建议：

- 上传完成：`10`
- Step1 处理中：`35`
- Step1 已确认：`55`
- Step2 已确认：`75`
- 渲染中：`95`
- 完成：`100`

## 4. 数据模型（最小字段）

## 4.1 Job

```json
{
  "job_id": "job_01",
  "status": "STEP1_READY",
  "progress": 55,
  "error": null
}
```

## 4.2 Step1 Line

```json
{
  "line_id": 1,
  "start": 0.0,
  "end": 2.4,
  "original_text": "我们今天讲三个点",
  "optimized_text": "我们今天讲三个点。",
  "ai_suggest_remove": false,
  "user_final_remove": false
}
```

## 4.3 Step2 Chapter

```json
{
  "chapter_id": 1,
  "title": "开场",
  "summary": "说明主题",
  "start": 0.0,
  "end": 32.5,
  "line_ids": [1, 2, 3]
}
```

## 5. 接口清单（MVP）

| 接口 | 方法 | 说明 |
|---|---|---|
| `/jobs` | `POST` | 创建任务 |
| `/jobs/{job_id}` | `GET` | 查询任务状态与进度 |
| `/jobs/{job_id}/upload` | `POST` | 上传并校验视频 |
| `/jobs/{job_id}/step1/run` | `POST` | 运行 Step1 |
| `/jobs/{job_id}/step1` | `GET` | 获取 Step1 结果 |
| `/jobs/{job_id}/step1/confirm` | `PUT` | 提交并确认 Step1 |
| `/jobs/{job_id}/step2/run` | `POST` | 运行 Step2 |
| `/jobs/{job_id}/step2` | `GET` | 获取 Step2 结果 |
| `/jobs/{job_id}/step2/confirm` | `PUT` | 提交并确认 Step2 |
| `/jobs/{job_id}/render/run` | `POST` | 启动渲染 |
| `/jobs/{job_id}/download` | `GET` | 下载最终视频 |

## 6. 关键接口定义

## 6.1 创建任务

`POST /jobs`

响应：

```json
{
  "request_id": "req_1",
  "data": {
    "job": {
      "job_id": "job_01",
      "status": "CREATED",
      "progress": 0,
      "error": null
    }
  }
}
```

## 6.2 上传并校验视频

`POST /jobs/{job_id}/upload`  
`Content-Type: multipart/form-data`，字段：`file`

校验规则：

- 扩展名：`.mp4 .mov .mkv .avi .webm .flv .f4v`
- 大小上限：`MAX_UPLOAD_MB`（默认 2048）
- 必须有可读视频流

响应：

```json
{
  "request_id": "req_2",
  "data": {
    "job": {
      "job_id": "job_01",
      "status": "UPLOAD_READY",
      "progress": 10,
      "error": null
    }
  }
}
```

## 6.3 查询任务状态

`GET /jobs/{job_id}`

响应：

```json
{
  "request_id": "req_3",
  "data": {
    "job": {
      "job_id": "job_01",
      "status": "STEP1_RUNNING",
      "progress": 35,
      "error": null
    }
  }
}
```

前端轮询建议：每 2 秒一次。

## 6.4 Step1：运行、获取、确认

1) `POST /jobs/{job_id}/step1/run`  
前置状态：`UPLOAD_READY`

2) `GET /jobs/{job_id}/step1`  
前置状态：`STEP1_READY` 或 `STEP1_CONFIRMED`

响应：

```json
{
  "request_id": "req_4",
  "data": {
    "lines": [
      {
        "line_id": 1,
        "start": 0.0,
        "end": 2.4,
        "original_text": "我们今天讲三个点",
        "optimized_text": "我们今天讲三个点。",
        "ai_suggest_remove": false,
        "user_final_remove": false
      }
    ]
  }
}
```

3) `PUT /jobs/{job_id}/step1/confirm`  
前置状态：`STEP1_READY`

请求：

```json
{
  "lines": [
    {
      "line_id": 1,
      "optimized_text": "我们今天讲三个点。",
      "user_final_remove": false
    }
  ]
}
```

响应：

```json
{
  "request_id": "req_5",
  "data": {
    "confirmed": true,
    "status": "STEP1_CONFIRMED"
  }
}
```

## 6.5 Step2：运行、获取、确认

1) `POST /jobs/{job_id}/step2/run`  
前置状态：`STEP1_CONFIRMED`

2) `GET /jobs/{job_id}/step2`  
前置状态：`STEP2_READY` 或 `STEP2_CONFIRMED`

响应：

```json
{
  "request_id": "req_6",
  "data": {
    "chapters": [
      {
        "chapter_id": 1,
        "title": "开场",
        "summary": "说明主题",
        "start": 0.0,
        "end": 32.5,
        "line_ids": [1, 2, 3]
      }
    ]
  }
}
```

3) `PUT /jobs/{job_id}/step2/confirm`  
前置状态：`STEP2_READY`

请求：

```json
{
  "chapters": [
    {
      "chapter_id": 1,
      "title": "开场问题",
      "summary": "先抛出痛点",
      "start": 0.0,
      "end": 30.0,
      "line_ids": [1, 2]
    }
  ]
}
```

响应：

```json
{
  "request_id": "req_7",
  "data": {
    "confirmed": true,
    "status": "STEP2_CONFIRMED"
  }
}
```

## 6.6 启动渲染与下载

1) `POST /jobs/{job_id}/render/run`  
前置状态：`STEP2_CONFIRMED`

响应：

```json
{
  "request_id": "req_8",
  "data": {
    "accepted": true,
    "status": "RENDER_RUNNING"
  }
}
```

2) `GET /jobs/{job_id}/download`  
前置状态：`SUCCEEDED`  
响应：视频文件流（`video/mp4`）

## 7. 前端最小联调顺序

1. `POST /jobs`
2. `POST /jobs/{job_id}/upload`
3. `POST /jobs/{job_id}/step1/run` + 轮询 `GET /jobs/{job_id}`
4. `GET /jobs/{job_id}/step1` -> 编辑 -> `PUT /jobs/{job_id}/step1/confirm`
5. `POST /jobs/{job_id}/step2/run` + 轮询 `GET /jobs/{job_id}`
6. `GET /jobs/{job_id}/step2` -> 编辑 -> `PUT /jobs/{job_id}/step2/confirm`
7. `POST /jobs/{job_id}/render/run` + 轮询 `GET /jobs/{job_id}`
8. `GET /jobs/{job_id}/download`

## 8. 与当前代码模块映射

- Step1：`video_auto_cut/asr/transcribe.py` + `video_auto_cut/editing/auto_edit.py`
- Step2：`video_auto_cut/editing/topic_segment.py`
- Render：`video_auto_cut/rendering/remotion_renderer.py`
