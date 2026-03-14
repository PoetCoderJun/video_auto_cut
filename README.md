# video_auto_cut

`video_auto_cut` 的 GPL-3.0 Skills 版：保留本地转写、Step1 自动删改、Step2 分段、人审确认和最终裁剪，不再包含 Web 前端或 Web API。

## License

本分支使用 `GPL-3.0-only`。完整协议见 [LICENSE](/Users/huzujun/Desktop/video_auto_cut_skill/LICENSE)。

## 仓库结构

- `video_auto_cut/`：核心 ASR、自动删改、主题分段、裁剪流水线
- `video_auto_cut/human_loop/`：面向代理的本地工件管理与 Human-in-the-Loop 状态机
- `skills/video-auto-cut-human-loop/`：给 Codex、Claude Code、PyAgent 使用的 Skill
- `scripts/run_human_loop_pipeline.py`：可中断、可恢复的人审 wrapper
- `tests/`：Skill 版新增的 wrapper 回归测试

## 依赖

```bash
python -m pip install -r requirements.txt
ffmpeg -version
```

常用环境变量：

- `ASR_DASHSCOPE_API_KEY` 或 `DASHSCOPE_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `LLM_API_KEY`
- `OSS_ENDPOINT` / `OSS_BUCKET` / `OSS_ACCESS_KEY_ID` / `OSS_ACCESS_KEY_SECRET`（可选）

## 顶层体验

理想的代理侧输入应该只需要一句话，例如：

- `把 /abs/path/input.mp4 自动剪成成片`
- `处理这个视频 /abs/path/input.mp4`

在 Skill 设计里，以下都是默认行为，不该要求用户额外说明：

- Step1 要停下来给人审核
- Step2 要停下来给人审核
- 没写输出路径时，默认输出到当前工作目录下的 `<输入文件名>_cut.mp4`

## Human Loop 用法

1. 只给输入视频也可以直接开跑。若未指定输出路径，默认输出到当前工作目录下的 `<输入文件名>_cut.mp4`：

```bash
python scripts/run_human_loop_pipeline.py run \
  --input-video /abs/path/input.mp4
```

如果你想自定义输出路径，再额外传 `--output-video`。

2. 编辑 `artifact_root/step1/draft_step1.json` 后确认：

```bash
python scripts/run_human_loop_pipeline.py approve-step1 \
  --input-video /abs/path/input.mp4
```

3. 再次执行 `run`，生成 Step2 草稿；编辑 `artifact_root/step2/draft_topics.json` 后确认：

```bash
python scripts/run_human_loop_pipeline.py approve-step2 \
  --input-video /abs/path/input.mp4
```

4. 最终导出：

```bash
python scripts/run_human_loop_pipeline.py render \
  --input-video /abs/path/input.mp4
```

默认工件目录是输入视频旁边的 `<video_stem>.video-auto-cut/`。也可以用 `--artifact-root` 指定。
如果你更想用单个“继续”动作，`next` 也可以作为恢复入口，但它只会在当前阶段已经存在显式审批记录时推进；它不会把“继续执行”自动当成“已经审核通过”。

## Skill 用法

这个仓库的目标不是提供网页，而是让代理接管流程。直接使用 [skills/video-auto-cut-human-loop/SKILL.md](/Users/huzujun/Desktop/video_auto_cut_skill/skills/video-auto-cut-human-loop/SKILL.md)，并让代理调用 `scripts/run_human_loop_pipeline.py`。

适合的场景：

- Codex 桌面版本地跑视频处理
- Claude Code 驱动本地视频剪辑
- PyAgent / 自定义 Agent 做“生成工件 -> 等人确认 -> 继续执行”的工作流
