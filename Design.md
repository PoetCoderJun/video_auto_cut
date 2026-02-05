# 自动口播剪辑 + 可编辑工作台（设计说明）

日期：2026-02-05

## 项目背景
目标是构建一个“自动剪辑 + 人工可编辑 + 成片导出”的口播视频工具，解决口播录制后人工剪辑成本高、重复劳动多的问题。现阶段优先验证算法链路的可行性与稳定性，确保“可剪可出片”，再逐步引入前后端工作台与高级渲染能力。

## 总体思路
- 算法优先：先把 autocut 思路 + ASR + 自动剪辑的闭环跑通
- 可撤销：自动建议必须可人工撤回
- 可复用：每一步都输出结构化中间结果（SRT/EDL/JSON）
- 分阶段演进：算法链路验证 → 人工确认 → Remotion 统一渲染 → PPT 模板

## 目标与边界（按优先级）
1. 先跑通算法链路：autocut 思路 + ASR + 自动剪辑（能出成片与字幕）
2. 再做前后端工作台：人工确认/撤销/微调剪辑
3. 最后做高阶渲染与 PPT（Remotion、画中画、模板）

## 核心概念
- 微分段（ASR Segments）：基于气口/停顿切分的短句，用于精剪
- 语义段（Semantic Segments）：多个微分段合并成主题页（PPT 阶段启用）
- EDL：剪辑后的时间段列表，作为渲染/拼接的通用输入

## 系统架构（简化）
- 前端：上传、分段列表、勾选/撤销、导出
- 后端：ASR、自动剪辑建议、EDL 生成、渲染编排
- 渲染层：先用 ffmpeg/moviepy 验证，后切 Remotion
- 存储：本地文件 + SQLite（后续可扩展对象存储）

## 核心流程（算法链路优先）
1. 输入视频 → 抽取音频（16k 单声道）
2. VAD 分段 → ASR → 生成 SRT
3. 自动剪辑：基于字幕/规则/LLM 输出删除建议
4. 片段合并与清洗 → 输出 EDL
5. 临时拼接生成成片（ffmpeg/moviepy）
6. 后续替换为 Remotion 统一渲染

## 关键模块设计
### ASR 与分段
- 音频抽取：FFmpeg 直出 PCM 16k
- 语音活动检测：Silero VAD + 片段清洗（去短段、扩展、合并）
- ASR：DashScope/Qwen（MVP），输出短句级时间戳

### 自动剪辑与 EDL
- 输入：SRT + 分段信息
- 规则：合并 0.5s 内的相邻片段、过滤过短片段
- 输出：`edl[] = { start, end }`

### 成片输出
- 先用 ffmpeg/moviepy 验证算法链路
- 稳定后切换 Remotion 统一渲染（字幕样式与模板化）

### 人工确认工作台（Phase 1）
- 分段列表：删除/保留/撤销
- 输出：编辑后的 EDL + 导出参数

## 数据结构（最小集）
- `asr_segments[]`: { id, start, end, text, confidence }
- `edit_decisions[]`: { segment_id, decision, reason }
- `edl[]`: { start, end }
- `semantic_segments[]`: { id, start, end, summary, bullets[] }（PPT 阶段启用）

## AutoCut 可复用设计点
- 音频抽取与采样：`autocut/autocut/utils.py::load_audio`
- VAD 分段：`autocut/autocut/transcribe.py::_detect_voice_activity`
- 片段清洗：`autocut/autocut/utils.py::{remove_short_segments, expand_segments, merge_adjacent_segments}`
- SRT 生成：`autocut/autocut/whisper_model.py::gen_srt`
- 字幕驱动剪辑：`autocut/autocut/cut.py::Cutter.run`（只复用逻辑，输出改为 EDL）

## 风险与对策（简版）
- LLM 误删：默认保守 + 全可撤销
- 分段过碎：片段合并阈值可调
