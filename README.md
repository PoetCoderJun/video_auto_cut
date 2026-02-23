# video_auto_cut

口播视频自动剪辑流水线：`ASR -> LLM 优化字幕 -> 切片重映射 -> Remotion 渲染`。

## `--skip-render` 是什么

`--skip-render` 表示只跑前两步，不生成最终视频：

1. 转录：`video -> .srt`
2. 自动剪辑：`.srt -> .optimized.srt`
3. 渲染：`video + .optimized.srt -> .cut.srt/.cut.topics.json/_remotion.mp4`（被跳过）

适用场景：

- 只想先验证 ASR 和 LLM 字幕优化结果
- 暂时不想安装或执行 Remotion 渲染
- 调试字幕阶段，后续再单独渲染

## 快速开始（Apple CPU 推荐）

### 1) 创建环境（建议 Python 3.12）

```bash
conda create -n qwen312 python=3.12 -y
conda activate qwen312
python -m pip install -U pip setuptools wheel
```

### 2) 安装 Python 依赖

```bash
python -m pip install -r requirements.txt
python -m pip install -U qwen-asr
```

可选（仅在需要本地 TTS 时）：

```bash
python -m pip install -U qwen-tts
```

### 3) 下载模型到 `/model`

运行时可自动拉取模型；如果环境不能联网或希望提前下载，请手动下载到 `./model/`：

```bash
# 方式 A：ModelScope（国内推荐）
python -m pip install -U modelscope
modelscope download --model Qwen/Qwen3-ASR-0.6B --local_dir ./model/Qwen3-ASR-0.6B
modelscope download --model Qwen/Qwen3-ForcedAligner-0.6B --local_dir ./model/Qwen3-ForcedAligner-0.6B

# 方式 B：Hugging Face
python -m pip install -U "huggingface_hub[cli]"
huggingface-cli download Qwen/Qwen3-ASR-0.6B --local-dir ./model/Qwen3-ASR-0.6B
huggingface-cli download Qwen/Qwen3-ForcedAligner-0.6B --local-dir ./model/Qwen3-ForcedAligner-0.6B
```

### 4) 安装 Remotion 依赖

```bash
cd remotion
npm install
cd ..
```

### 5) 安装 ffmpeg / ffprobe

```bash
brew install ffmpeg
```

### 6) 配置 LLM（自动剪辑优化字幕）

项目根目录 `.env` 填写：

```env
DASHSCOPE_API_KEY=sk-***
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen3-max
```

语言参数说明：

- 默认 `--lang Chinese`
- 也支持别名：`zh` -> `Chinese`，`en` -> `English`
- 可用 `--qwen3-language` 覆盖

## 运行

入口：`main.py`（等价于 `python -m video_auto_cut`）
若项目根目录存在 `.env`，会自动读取 LLM 配置。

全流程：

```bash
python main.py test_data/1.MOV \
  --device cpu \
  --qwen3-model ./model/Qwen3-ASR-0.6B \
  --qwen3-aligner ./model/Qwen3-ForcedAligner-0.6B \
  --llm-base-url https://dashscope.aliyuncs.com/compatible-mode/v1 \
  --llm-model qwen3-max

# 或
python -m video_auto_cut test_data/1.MOV \
  --device cpu \
  --qwen3-model ./model/Qwen3-ASR-0.6B \
  --qwen3-aligner ./model/Qwen3-ForcedAligner-0.6B \
  --llm-base-url https://dashscope.aliyuncs.com/compatible-mode/v1 \
  --llm-model qwen3-max
```

只跑到优化字幕（不渲染）：

```bash
python main.py test_data/1.MOV \
  --device cpu \
  --skip-render
```

默认行为：

- 若目标文件已存在，对应步骤自动跳过
- `--force` 强制覆盖并重跑

## 输出文件

以 `test_data/1.MOV` 为例：

- `test_data/1.srt`：ASR 字幕
- `test_data/1.optimized.srt`：LLM 优化字幕（含删除标记）
- `test_data/1.cut.srt`：切片后重映射字幕（仅渲染步骤）
- `test_data/1.cut.topics.json`：章节结果（仅渲染步骤）
- `test_data/1_remotion.mp4`：最终视频（仅渲染步骤）

## 当前代码结构

```text
main.py

video_auto_cut/
  __main__.py
  orchestration/
    full_pipeline.py
    cli.py
  asr/
    qwen3_asr.py
    transcribe.py
  editing/
    llm_client.py
    auto_edit.py
    topic_segment.py
  rendering/
    cut.py
    remotion_renderer.py
  shared/
    media.py

remotion/
  render.mjs
  src/
```

## 常用参数

- `--skip-transcribe`：跳过转录（要求已有 `.srt`）
- `--skip-auto-edit`：跳过自动剪辑（要求已有 `.optimized.srt`）
- `--skip-render`：跳过渲染（不生成 cut 字幕/章节/视频）
- `--force`：覆盖已存在文件并重跑
- `--no-render-topics`：渲染时不生成章节
- `--render-preview`：预览模式（轻量渲染）
- `--render-output`：指定最终视频路径
- `--topic-output`：指定章节 JSON 路径
