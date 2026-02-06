# video_auto_cut

自动口播剪辑与可编辑工作台（算法链路优先）。

## 快速开始

### 1) 安装依赖

```bash
python -m pip install -e autocut
```

### 2) 配置 LLM（纠错）

项目根目录的 `.env` 已包含默认模板，请填入你的 API Key：

```bash
DASHSCOPE_API_KEY=sk-***
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen3-max
```

### 3) 运行转录 + 纠错

```bash
autocut -t test_data/1.MOV \
  --whisper-mode qwen3 \
  --qwen3-model ./model/Qwen3-ASR-0.6B \
  --qwen3-aligner ./model/Qwen3-ForcedAligner-0.6B \
  --qwen3-offline \
  --device cpu \
  --qwen3-correct \
  --llm-temperature 0.0 \
  --force
```

核心输出：
- `test_data/1.srt`：字幕（已纠错、带标点）

## 说明

- 纠错流程：`ASR → 对齐（原文）→ LLM 纠错（仅改文本，不改时间）`

## 自动剪辑（LLM 语义优化 → 优化 SRT）

从 `.srt` 或 segments JSON 生成优化后的字幕（行对齐，删除行标注 `<<REMOVE>>`，不删行）。

启用 LLM 全文语义优化（允许句内修正，禁止跨句修改）：

```bash
autocut -e test_data/1.srt --auto-edit-llm \
  --llm-base-url https://dashscope.aliyuncs.com/compatible-mode/v1 \
  --llm-model qwen3-max --force
```

输出：
- `test_data/1.optimized.srt`

说明：
- 仅保留与原 `1.srt` 相同的行号和时间戳。
- 被删除的行会标记为 `<<REMOVE>> 原文`，不会直接删除该行。
- 中间产物写入 `.cache/auto_edit/`，无需关注。

## 用 Remotion 渲染成片（拼接优化段）

先安装 Remotion 依赖：

```bash
cd remotion
npm install
```

然后使用优化后的 SRT 渲染成片（会自动拼接 `<<REMOVE>>` 之外的片段）：

```bash
autocut --render test_data/1.MOV test_data/1.optimized.srt
```

输出：
- `test_data/1_remotion.mp4`

快速预览（720p/15fps）：

```bash
autocut --render test_data/1.MOV test_data/1.optimized.srt --render-preview
```

## 常见问题

- 如果提示 LLM 配置缺失，请确认 `.env` 已填写且在项目根目录。
- 若使用 CPU，速度较慢属于正常现象。
