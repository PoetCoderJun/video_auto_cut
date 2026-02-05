# video_auto_cut

自动口播剪辑与可编辑工作台（算法链路优先）。

## 快速开始

### 1) 安装依赖

```bash
python -m pip install -e autocut
```

### 2) 配置 LLM（纠错 + 主题分段）

项目根目录的 `.env` 已包含默认模板，请填入你的 API Key：

```bash
DASHSCOPE_API_KEY=sk-***
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen3-max
```

### 3) 运行转录 + 纠错 + 主题分段

```bash
autocut -t test_data/1.MOV \
  --whisper-mode qwen3 \
  --qwen3-model ./model/Qwen3-ASR-0.6B \
  --qwen3-aligner ./model/Qwen3-ForcedAligner-0.6B \
  --qwen3-offline \
  --device cpu \
  --qwen3-correct \
  --qwen3-topic-llm \
  --llm-temperature 0.0 \
  --force
```

输出文件：
- `test_data/1.srt`：字幕（已纠错、带标点）
- `test_data/1.md`：可编辑标注文件
- `test_data/1.topics.json`：LLM 主题分段结果

## 说明

- 纠错流程：`ASR → 对齐（原文）→ LLM 纠错（仅改文本，不改时间）`
- 主题分段：LLM 基于字幕内容进行语义分块

## 自动剪辑（规则 + LLM + 质量评分 + EDL）

从 `.srt` 或 segments JSON 直接生成剪辑建议与 EDL。

```bash
autocut -e test_data/1.srt --force
```

输出：
- `test_data/1.auto_edit.json`：每条字幕的 decision=keep/remove + 质量分数
- `test_data/1.edl.json`：自动剪辑的时间段（可直接用于渲染）
- `test_data/1.auto_edit.srt`：带 KEEP/REMOVE 标记的可读版字幕

启用 LLM 水词检测：

```bash
autocut -e test_data/1.srt --auto-edit-llm \
  --llm-base-url https://dashscope.aliyuncs.com/compatible-mode/v1 \
  --llm-model qwen3-max --force
```

## 常见问题

- 如果提示 LLM 配置缺失，请确认 `.env` 已填写且在项目根目录。
- 若使用 CPU，速度较慢属于正常现象。
