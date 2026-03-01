# 设计草案：单台 CPU 主机 + Qwen3-ASR-Flash-Filetrans（不使用 OSS）

目标：把 ASR 改为调用阿里云 DashScope 的 `Qwen3-ASR-Flash-Filetrans`（异步文件转写），同时不引入 OSS；浏览器只上传「音频」到后端，视频不离开客户端；后端产出 `final_step1.srt/final_step1.json`，保持现有 Step1/Step2/渲染的产品流程基本不变。

本方案的核心取舍：
- 不引入 OSS：降低系统依赖与开发量，但需要后端提供一个“可公网访问 + 带短期签名”的音频下载地址，让 Filetrans 拉取。
- 不上传视频：大幅降低带宽/存储压力与费用；同时避免后端成为大文件中转站（你当前也计划客户端渲染）。
- Step1 拆分为“提交 ASR”与“轮询 ASR 完成”：避免 worker 长时间阻塞，提高并发可用性。

---

## 1. 端到端流程

### 1) 浏览器侧（纯 Web）
1. 用户选择本地视频文件。
2. 浏览器将视频本地转码/提取为音频（建议使用 `ffmpeg.wasm`）。
   - 推荐输出：`m4a`/`mp3`（单声道，16k/32k 采样，32–64kbps）。
   - 目标：在可接受的识别质量下，把“上传体积”压到最低。
3. 浏览器发起 `Create Job`（或复用现有 job 创建逻辑），拿到 `job_id`。
4. 浏览器上传音频到后端：`POST /api/v1/jobs/{job_id}/audio`（multipart）。
5. 浏览器触发 Step1：`POST /api/v1/jobs/{job_id}/step1/run`。
6. 导出渲染：浏览器用本地视频文件导出（Remotion Web Renderer），并在请求 `GET /api/v1/jobs/{job_id}/render/config` 时携带视频元数据（`width/height/fps/duration_sec`），后端不再需要保存/探测视频文件。

### 2) 后端侧（单台 ECS：FastAPI + worker）
1. 接收音频上传，存入 `workdir/jobs/{job_id}/input/audio.<ext>`，写入 `job.files.json` 的 `audio_path`，并将 job 标记为 `UPLOAD_READY`（用于允许 Step1）。
2. Step1（改造后）分两段：
   - Step1-A：提交 Filetrans 任务（保存 `task_id`、`submitted_at`、`filetrans_model`、`source_url_expire_at`）。
   - Step1-B：轮询任务状态 -> 成功后下载结果 -> 转换为内部 token/字幕结构 -> 写 `final_step1.srt/json` -> 扣减 credits -> 进入现有“确认/Step2/渲染配置”流程。

---

## 2. API 设计（建议最小增量）

### 2.1 上传音频
- `POST /api/v1/jobs/{job_id}/audio`
  - 入参：`multipart/form-data`，字段名例如 `file`
  - 行为：
    - 校验扩展名与 MIME（白名单：`m4a/mp3/wav/mp4/aac` 等）
    - 校验大小（例如 `MAX_UPLOAD_MB`）
    - 落盘到 job input 目录
    - 在 `job.files.json` 记录 `audio_path`
    - 更新 job 状态为 `UPLOAD_READY`
  - 返回：`{ ok: true }`

### 2.2 生成“供 Filetrans 拉取”的公网下载链接（短期签名）
- `GET /api/v1/jobs/{job_id}/audio/source?token=...`
  - 注意：这是给 DashScope Filetrans 拉取的 URL，不给浏览器用。
  - token 推荐使用 HMAC 签名（无状态）：
    - payload：`job_id`, `file`, `exp`（unix ts）, `nonce`
    - token：`base64url(payload).base64url(hmac_sha256(secret, payload))`
  - 服务器校验：
    - `exp` 未过期
    - `job_id` 与 path 匹配且固定映射到 input/audio（禁止任意路径）
    - 可选：限制 User-Agent/来源 IP（不可靠，主要靠签名）
  - 响应：`StreamingResponse` 直接流式返回音频文件（避免占用内存）。

### 2.3 Step1（提交/轮询）
建议把现有 `POST /api/v1/jobs/{job_id}/step1/run` 的内部实现改为“只提交 + 快速返回”，轮询由 worker 驱动。

- `POST /api/v1/jobs/{job_id}/step1/run`
  - 行为：
    - 确认 `audio_path` 存在
    - 生成 `source_url = {PUBLIC_BASE_URL}/api/v1/jobs/{job_id}/audio/source?token=...`（有效期建议 1–6 小时）
    - 调用 DashScope Filetrans 提交任务（保存 `task_id` 与必要参数）
    - 更新 job 状态为 `STEP1_ASR_PENDING`（或复用 progress 段落）
    - `enqueue_task(job_id, TASK_TYPE_STEP1_POLL, payload={task_id})`
  - 返回：`{ ok: true, task_id }`

- worker 任务：`TASK_TYPE_STEP1_POLL`
  - 行为：
    - 查询任务状态：`RUNNING/SUCCEEDED/FAILED`
    - `SUCCEEDED`：下载 `transcription_url`，转换为 SRT（生成 `final_step1.srt/json`），并进入现有 auto-edit/确认流程
    - `FAILED`：写 job error_code/error_message
    - `RUNNING`：延时重试（指数退避 + 最大超时）

---

## 3. DashScope 调用注意点（与“不用 OSS”的关系）

1. Filetrans 需要 `file_url` 可公网访问，且在任务处理期间可被服务端多次读取。
2. 不用 OSS 时，`file_url` 指向你的 ECS：
   - 你的 ECS 必须有公网可达的域名/IP + 80/443 端口（建议走 HTTPS）。
   - 你承担这次下载的“出向流量”（从 ECS 发出到对端）。
3. 结果一般以 `transcription_url` 提供，且通常带有效期：worker 需要尽快拉取并落盘（或存 DB）。

---

## 4. 安全边界（必须做）

### 4.1 避免“任意公网 URL 透传”
- 后端不接受用户提交的 `file_url`。
- 后端只允许下载自己落盘的 `audio` 文件，并通过短期签名 URL 暴露给 Filetrans。

### 4.2 签名下载链接
- 必须包含 `exp`（短期过期），默认 1–6 小时。
- token 使用独立 secret（例如 `ASR_SOURCE_URL_SECRET`），不要复用 JWT 密钥。
- token 校验失败返回 403；不要回显路径信息。

### 4.3 路径映射固定
- `job_id` 仅允许 `[a-zA-Z0-9_-]` 这类安全字符（或用 UUID）。
- 文件路径只允许固定为 `workdir/jobs/{job_id}/input/audio.*`，禁止请求参数携带任意路径。

### 4.4 上传限制
- `MAX_UPLOAD_MB` 限制。
- MIME/扩展名白名单。
- 可选：对音频时长做上限（例如 2 小时），避免 DoS 与账单失控。

---

## 5. 清理策略（控制磁盘与隐私）

建议：
- 上传音频：保留 24–72 小时（用于重试），然后自动删除。
- 转写结果与 `final_step1.*`：按产品需要保留；如果渲染在客户端且不需要云端留存，可设置更短 TTL。

落地方式：
- 复用你现有的 `cleanup` 机制（worker 定时清理 `workdir/jobs/*` 下过期目录）。

---

## 6. 对现有代码结构的改造落点（对齐当前仓库）

当前 Step1 入口：`web_api/services/step1.py::run_step1()` -> `video_auto_cut/orchestration/pipeline_service.py::run_transcribe()`

建议改造点：
- `web_api/services/step1.py`
  - 从读取 `video_path` 改为读取 `audio_path`（本地开发可保留视频上传用于客户端渲染，但 ASR 只依赖音频）
  - Step1 改为提交/轮询两段
- `web_api/repository.py`
  - job_files 增加 `audio_path`、`asr_task_id`、`asr_status`、`asr_submitted_at` 等字段（或以 json 存储在现有表结构中）
- `video_auto_cut/asr/transcribe.py`
  - 增加一个 “filetrans 后端” 类：从 DashScope 返回结构生成与现有 `Qwen3Model.gen_srt()` 兼容的 tokens，再输出 `.srt`
  - 保留现有本地 qwen-asr 作为 fallback（可用配置切换）
- `web_api/api/routes.py`
  - 新增上传音频与签名下载的路由

---

## 7. ECS 规格建议（只用 CPU、不上 OSS）

你的后端主要负载是：HTTP 上传/下载（音频）、任务编排、调用外部 API、少量文本处理与 JSON/SRT 生成。
只要“音频文件尽量小”，CPU 压力很轻，瓶颈更可能在带宽与磁盘 I/O。

### 推荐起步（MVP/小流量）
- `2 vCPU / 4GB`（通用型即可）
- 系统盘 `ESSD 60–100GB`
- 公网带宽：`5Mbps` 起（建议按“同时在转写的任务数”预估）

### 稳定版（有一定并发/需要更平滑）
- `2 vCPU / 8GB` 或 `4 vCPU / 8GB`
- 系统盘 `ESSD 100–200GB`（留出重试缓存与日志空间）
- 公网带宽：`10–20Mbps`（看峰值并发与音频大小）

### 如何用数据估算带宽/磁盘（便于你按量升级）
如果音频采用 64kbps：
- 体积约 `0.5 MB/分钟`，约 `30 MB/小时`
- 同时 10 个 1 小时任务被 Filetrans 拉取：瞬时总下行约 `300 MB`（取决于对端拉取速度与重试）

结论：只要坚持“浏览器先转小音频再上传”，单台小规格 ECS 完全可行；不要在 ECS 上中转视频。
