# 设计草案：音频上 OSS + Qwen3-ASR-Flash-Filetrans

## 目标
- 前端继续只上传“提取后的音频”，不上传视频。
- Step1 改为云端 ASR：先把音频上传 OSS，再调用 DashScope `qwen3-asr-flash` 的 `file_trans_para`。
- 后端产物保持不变：继续输出 `.srt` 并复用现有 Step2 与客户端渲染链路。

## 处理链路
1. 浏览器提取音频并上传到 `POST /api/v1/jobs/{job_id}/audio`。
2. Step1 读取本地 `audio_path`，上传到 OSS（私有桶对象）。
3. 后端生成 OSS 签名下载 URL（短期有效）。
4. 调用 DashScope 提交异步任务：
   - `POST /api/v1/services/audio/asr/transcription`
   - `task=file_trans_para`
   - `input.file_url=<oss_signed_url>`
5. 轮询任务状态：
   - `GET /api/v1/tasks/{task_id}`
   - 成功后读取 `output.result.transcription_url`
6. 下载转写 JSON，转换为内部 token，再写出与当前一致的 SRT。

## 成本与复杂度
- 带宽：只传音频，远低于传视频。
- 存储：OSS 仅存放音频中间件，可配生命周期策略自动清理。
- 计算：后端无需本地 ASR 推理，CPU 主要用于 I/O 与编排，单机压力显著降低。
- 复杂度：新增 OSS 凭证与 Filetrans 轮询逻辑，但对现有 Step2/渲染影响极小。

## 安全建议
- OSS Bucket 建议私有读写，仅通过签名 URL 提供给 DashScope 拉取。
- 签名 URL TTL 建议 `1h~24h`（与最长音频和重试窗口匹配）。
- OSS AK/SK 仅放服务端 `.env`，不要下发前端。

## 服务器规格建议（仅编排 + API）
- 起步：`2 vCPU / 4GB`，系统盘 `60GB+`。
- 稳定并发：`2 vCPU / 8GB` 或 `4 vCPU / 8GB`。
- 关键瓶颈通常是公网带宽与上传并发，不是 CPU。
