---
name: asr-transcribe
description: Use when audio, video, or an OSS-backed upload needs to be transcribed into Test-ready SRT and line JSON before delete, polish, or chapter work begins.
---

# ASR Transcribe Skill

## Overview
这个 skill 只负责把媒体输入转成原始 Test 转录稿。

它复用项目里当前正在使用的 DashScope Filetrans 转录逻辑，包括自有 OSS 上传、词级切分、标点切句和 `< No Speech >` 插入等后处理，并输出可直接进入后续编辑链路的 `.srt` 与 `.test.json`。这个 skill 不负责 delete、polish 或 chapter。

## When to Use
- 起点是音频、视频，而不是已经生成好的字幕文本
- 需要把 OSS 直传音频或本地媒体先转成原始字幕
- 需要保留当前项目里的 ASR 分句规则，作为后续 Test 编辑起点
- 需要端到端做 Test，且第一步必须先拿到原始转录稿

不要用于：
- 已经有原始 ASR 字幕，只需要删留 / 润色 / 分章
- 手动改写字幕正文
- 跳过转录直接开始 delete

## Outputs
- `<input>.srt`：原始转录字幕
- `<input>.test.json`：逐行 Test lines JSON，方便后续 delete / polish

## Canonical Entry
主入口已经收口到模块 CLI，不再通过 skill 目录下的薄包装脚本中转： 

```bash
python -m video_auto_cut.asr.transcribe_stage --input /path/to/media.mp4
```

常用参数：

```bash
python -m video_auto_cut.asr.transcribe_stage   --input /path/to/media.mp4   --lang Chinese   --prompt "专有名词提示"   --force
```

```bash
python -m video_auto_cut.asr.transcribe_stage   --input /path/to/media.mp4   --test-json-path /tmp/raw.test.json
```

## Quick Reference
| 场景 | 动作 |
| --- | --- |
| 本地音频 / 视频起步 | 运行 `python -m video_auto_cut.asr.transcribe_stage --input ...` |
| 需要后续 delete / polish 继续接 | 保留 `.srt` 和 `.test.json` |
| 已有 OSS object key 且媒体不在本地 | 传 `--oss-object-key` |
| 只想沿用项目默认 ASR 配置 | 不传额外参数，走环境变量 |

## Required Environment
- `DASHSCOPE_ASR_API_KEY` 或 `DASHSCOPE_API_KEY`
- 如使用自有 OSS：`OSS_ENDPOINT`、`OSS_BUCKET`、`OSS_ACCESS_KEY_ID`、`OSS_ACCESS_KEY_SECRET`
- 如通过 PI/Test 流程继续做编辑，还需要项目当前使用的 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`（或兼容回退）

## Common Mistakes
- 输入已经是字幕文本却还跑 ASR：不需要。
- 媒体起步却直接做 delete：会丢掉端到端工作流的第一步。
- 生成 `.srt` 后不保留 `.test.json`：后续衔接不方便。
- 忘记配置 API key：命令会直接失败。
