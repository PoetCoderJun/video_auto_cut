# Codex Skill Usage

## 这个 Skill 是什么

这个项目里的 Skill 是：

- [video-auto-cut-human-loop](/Users/huzujun/Desktop/video_auto_cut_skill/skills/video-auto-cut-human-loop/SKILL.md)

它的主要功能是：

- 剪辑本地口播视频
- 默认走 Step1 字幕审核
- 默认走 Step2 章节审核
- 审核通过后再导出成片

它不是网页功能，而是一个给 Codex、Claude Code、PyAgent 这类代理用的顶层工作流 Skill。

## Codex 怎么发现它

Codex 会从自己的 Skill 目录里发现自定义 Skill：

- `~/.codex/skills/`

我这次在这台机器上实际安装的方式是给 Skill 目录做软链：

```bash
ln -s /Users/huzujun/Desktop/video_auto_cut_skill/skills/video-auto-cut-human-loop \
  ~/.codex/skills/video-auto-cut-human-loop
```

当前机器上的实际安装位置是：

- [~/.codex/skills/video-auto-cut-human-loop](/Users/huzujun/.codex/skills/video-auto-cut-human-loop)

如果你更新了仓库里的 Skill 内容，因为这里是软链，Codex 读到的就是最新版本。

## 要不要在同一个命令行里启动

不用。

关键不是“同一个命令行窗口”，而是：

- Skill 已经安装到 `~/.codex/skills/`
- 你启动的是一个新的 Codex 会话

也就是说：

- 已经打开着的 Codex 会话，通常要退出后重新启动，才能重新发现新 Skill
- 新开一个终端窗口也可以
- 还是原来的终端窗口，先退出再重新运行 `codex` 也可以

## 怎么启动

### 交互式启动

在任意终端里运行：

```bash
codex
```

然后直接说一句话就可以。

### 非交互式启动

如果你想在命令行里一次性发任务，也可以：

```bash
codex exec -C /Users/huzujun/Desktop/video_auto_cut_skill \
  "把 /绝对路径/输入视频.mp4 自动剪成成片"
```

## 口袋启动词

如果你说的“口袋”是指一句话就能把流程拉起来，那推荐这些口袋启动词：

```text
把 /绝对路径/输入视频.mp4 自动剪成成片
```

```text
帮我剪一下这个口播视频 /绝对路径/输入视频.mp4
```

```text
处理这个视频 /绝对路径/输入视频.mp4
```

如果你要指定输出路径，再多说一句就够了：

```text
把 /绝对路径/输入视频.mp4 自动剪成成片，输出到 /绝对路径/输出视频.mp4
```

## 默认行为

用户不需要额外说明下面这些事情：

- Step1 要审核
- Step2 要审核
- 没给输出路径时要自动推断

默认规则是：

- `input_video_path` 必填
- `output_video_path` 可选
- 没给输出路径时，默认输出到当前工作目录下的 `<输入文件名>_cut.mp4`
- Step1 和 Step2 都是硬门禁

## 当前仓库里的真实入口

虽然对用户来说它应该像一个顶层 Skill，但仓库里的执行入口仍然是：

- [run_human_loop_pipeline.py](/Users/huzujun/Desktop/video_auto_cut_skill/scripts/run_human_loop_pipeline.py)

这个脚本负责：

- 断点续跑
- 工件路径管理
- 审核 receipt 记录
- render 导出

Skill 的职责是让代理知道：

- 什么时候该触发这条流程
- 默认行为是什么
- 什么时候必须停下来等人审

## 验证建议

最简单的验证方式：

1. 重启 Codex
2. 进入任意终端，运行 `codex`
3. 输入一句：

```text
把 /Users/huzujun/Desktop/video_auto_cut/test_data/AI1.MOV 自动剪成成片
```

预期行为：

1. Codex 开始转写和 Step1 自动删改
2. 停在 Step1 审核点
3. 你确认后，它继续生成 Step2 草稿
4. 再确认后，它导出最终成片
