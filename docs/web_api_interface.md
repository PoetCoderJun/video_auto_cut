# Web API 接口文档（当前维护版本）

更新时间：2026-04-16  
范围：当前 `/api/v1` 对外契约，仅覆盖仍在维护的公开路由与当前 `/test` 单流程。  
明确不再作为当前真相的历史内容：独立 `Step2` 路由、旧 `/jobs/{job_id}/upload` 视频上传接口、Clerk 专属鉴权表述。

## 1. 全局约定

- Base URL：`/api/v1`
- 响应格式：默认 `application/json`
- 成功格式：

```json
{
  "request_id": "req_x1",
  "data": {}
}
```

- 失败格式：

```json
{
  "request_id": "req_x1",
  "error": {
    "code": "INVALID_STEP_STATE",
    "message": "额度不足，请先兑换邀请码后重试"
  }
}
```

## 2. 鉴权

### 2.1 需要登录的接口
默认要求 `Authorization: Bearer <jwt>`，由当前 Better Auth / JWKS 配置校验：

- `WEB_AUTH_JWKS_URL`
- `WEB_AUTH_ISSUER`
- `WEB_AUTH_AUDIENCE`

### 2.2 公开接口
以下接口无需登录：

- `POST /public/coupons/verify`
- `POST /public/invites/claim`

## 3. 当前任务状态

当前有效 `job.status`：

- `CREATED`
- `UPLOAD_READY`
- `TEST_RUNNING`
- `TEST_READY`
- `TEST_CONFIRMED`
- `SUCCEEDED`
- `FAILED`

当前实现里不再维护独立 `STEP2_*` 状态。

## 4. 关键数据结构

### 4.1 Job

```json
{
  "job_id": "job_01",
  "status": "TEST_READY",
  "progress": 35,
  "stage": null,
  "error": null
}
```

### 4.2 TestDocument

```json
{
  "lines": [
    {
      "line_id": 1,
      "start": 0.0,
      "end": 2.4,
      "original_text": "我们今天讲三个点",
      "optimized_text": "我们今天讲三个点",
      "ai_suggest_remove": false,
      "user_final_remove": false
    }
  ],
  "chapters": [
    {
      "chapter_id": 1,
      "title": "开场",
      "start": 0.0,
      "end": 32.5,
      "block_range": "1-3"
    }
  ],
  "document_revision": "rev_x1"
}
```

### 4.3 RenderConfig

`GET /jobs/{job_id}/render/config` 返回：

- `output_name`
- `composition`（`id / fps / width / height / durationInFrames`）
- `input_props`（字幕、章节、进度条、主题、比例等浏览器导出所需输入）

该接口只负责生成浏览器导出配置，不直接返回文件下载流。

## 5. 当前维护中的路由

| 路由 | 方法 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| `/me` | `GET` | 登录 | 获取当前用户资料与额度 |
| `/auth/coupon/redeem` | `POST` | 登录 | 兑换 coupon 并刷新当前用户资料 |
| `/public/coupons/verify` | `POST` | 公开 | 注册前校验 coupon 是否可用 |
| `/public/invites/claim` | `POST` | 公开 | 按 IP 领取公共邀请码 |
| `/client/upload-issues` | `POST` | 登录 | 上报浏览器端上传/预检问题 |
| `/jobs` | `POST` | 登录 | 创建任务 |
| `/jobs/{job_id}` | `GET` | 登录 | 查询任务状态 |
| `/jobs/{job_id}/oss-upload-url` | `POST` | 登录 | 获取音频直传 OSS 的 PUT URL |
| `/jobs/{job_id}/audio-oss-ready` | `POST` | 登录 | 告知后端 OSS 直传已完成 |
| `/jobs/{job_id}/audio` | `POST` | 登录 | 通过 API 直接上传音频 |
| `/jobs/{job_id}/test/run` | `POST` | 登录 | 启动 Test 任务 |
| `/jobs/{job_id}/test` | `GET` | 登录 | 读取当前 Test 文档 |
| `/jobs/{job_id}/test/confirm` | `PUT` | 登录 | 提交最终字幕与章节并确认 |
| `/jobs/{job_id}/render/config` | `GET` | 登录 | 获取浏览器导出配置 |
| `/jobs/{job_id}/render/complete` | `POST` | 登录 | 标记浏览器导出完成并结算额度 |

## 6. 路由说明

### 6.1 用户与权益

#### `GET /me`
返回当前用户资料，包括：

- `user_id`
- `email`
- `status`
- `activated_at`
- `credits.balance`
- `credits.recent_ledger`

#### `POST /auth/coupon/redeem`
请求：

```json
{ "code": "CPN-XXXX" }
```

返回：

- `coupon`
- `user`

#### `POST /public/coupons/verify`
请求：

```json
{ "code": "CPN-XXXX" }
```

返回可用于前端注册前提示的 coupon 校验结果。

#### `POST /public/invites/claim`
按客户端 IP 领取公共邀请码，返回 `invite` 信息。

### 6.2 上传前诊断

#### `POST /client/upload-issues`
用于浏览器侧上报这些阶段的问题：

- `session_check`
- `profile_check`
- `source_preflight`
- `render_validation`
- `job_create`
- `audio_extract`
- `audio_upload`
- `source_cache`

此接口只做日志记录，成功时返回 `{ "accepted": true }`。

### 6.3 任务创建与音频上传

#### `POST /jobs`
创建一个新任务，初始状态为 `CREATED`。

#### `GET /jobs/{job_id}`
返回当前 `job`，前端据此轮询状态与进度。

#### `POST /jobs/{job_id}/oss-upload-url`
前置状态：`CREATED` 或 `UPLOAD_READY`

返回：

```json
{
  "put_url": "https://...",
  "object_key": "video-auto-cut/asr/job_xxx/audio.wav"
}
```

如果当前部署未配置 OSS 直传能力，会返回 503，并提示改走 `/jobs/{job_id}/audio`。

#### `POST /jobs/{job_id}/audio-oss-ready`
请求：

```json
{ "object_key": "video-auto-cut/asr/job_xxx/audio.wav" }
```

用于在前端完成 OSS PUT 后，让后端绑定该 object key 到任务。

#### `POST /jobs/{job_id}/audio`
`multipart/form-data`，字段：`file`

作为 OSS 直传不可用时的 API 上传兜底路径。

上传成功后，任务会进入 `UPLOAD_READY`。

### 6.4 Test 单流程

#### `POST /jobs/{job_id}/test/run`
前置状态：`UPLOAD_READY`

动作：

- 校验额度
- 创建 `TASK_TYPE_TEST`
- worker 异步执行 `asr -> delete -> polish -> chapter`

返回：

```json
{
  "accepted": true,
  "task_id": 123,
  "job": { "job_id": "job_01", "status": "TEST_RUNNING", "progress": 30 }
}
```

#### `GET /jobs/{job_id}/test`
允许状态：

- `TEST_RUNNING`
- `TEST_READY`
- `TEST_CONFIRMED`
- `SUCCEEDED`

返回当前 Test 文档：`lines + chapters + document_revision`。

#### `PUT /jobs/{job_id}/test/confirm`
前置状态：`TEST_READY`

请求：

```json
{
  "lines": [
    { "line_id": 1, "optimized_text": "我们今天讲三个点", "user_final_remove": false }
  ],
  "chapters": [
    { "chapter_id": 1, "title": "开场", "block_range": "1-3" }
  ],
  "expected_revision": "rev_x1"
}
```

成功后任务进入 `TEST_CONFIRMED`。

### 6.5 浏览器导出

#### `GET /jobs/{job_id}/render/config`
允许状态：`TEST_CONFIRMED` 或 `SUCCEEDED`

可附带查询参数：

- `width`
- `height`
- `fps`
- `duration_sec`

返回浏览器端 Remotion 导出所需配置。

#### `POST /jobs/{job_id}/render/complete`
允许状态：`TEST_CONFIRMED` 或 `SUCCEEDED`

用于前端浏览器导出成功后回写后端，完成额度结算与最终状态推进。

## 7. 当前推荐时序

1. `POST /jobs`
2. 上传音频：优先 `POST /jobs/{job_id}/oss-upload-url` + OSS PUT + `POST /jobs/{job_id}/audio-oss-ready`；否则走 `POST /jobs/{job_id}/audio`
3. `POST /jobs/{job_id}/test/run`
4. 轮询 `GET /jobs/{job_id}`
5. `GET /jobs/{job_id}/test`，编辑后 `PUT /jobs/{job_id}/test/confirm`
6. `GET /jobs/{job_id}/render/config`，浏览器本地导出
7. 导出成功后 `POST /jobs/{job_id}/render/complete`

## 8. 明确不在本文维护范围内的内容

- worker 内部租约/心跳/回收细节
- Turso schema 与 repository 内部持久化布局
- Railway Variables 的完整部署清单
- 已删除的独立 `Step2` 路由与旧视频上传接口历史细节
