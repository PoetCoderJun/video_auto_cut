# direct-prompts

这个目录只存放 **direct prompt 的文档镜像**，方便在 `skills/` 下面集中查阅。

## 重要说明

- **唯一运行时真源（source of truth）** 在：
  - `video_auto_cut/editing/direct_prompts.py`
- 当前 edit/highlight 主链路 **不会** 从这个目录加载运行时 prompt。
- 这个目录 **不是 skill 入口**，因此故意不放 `SKILL.md`，避免被当作可执行 skill 自动触发。
- 如果运行时 prompt 有变化，应先改代码，再同步更新这里的文档镜像。

## 镜像文件

- `delete.md`
- `polish.md`
- `chapter.md`
- `highlight.md`

这些文件仅用于阅读、审阅和讨论，不参与运行。
