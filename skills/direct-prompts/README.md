# direct-prompts

这个目录是当前 `delete / polish / chapter / highlight` 直连链路的**唯一运行时真相来源**。

这里的 prompt 以 **`skills/direct-prompts/` 目录里原始手写文件** 为准。
代码可以在运行时补充少量动态参数，但**不能再把别处的 prompt 文案反向回填、覆盖或“同步生成”到这里**。

## 运行时约定

- 运行时代码会直接读取这里的 markdown 文件。
- 每个 prompt 文件都必须包含一段：
  - `<!-- SYSTEM_PROMPT:START -->`
  - `<!-- SYSTEM_PROMPT:END -->`
- 两个 marker 之间的内容就是运行时真正发送给模型的 system prompt 基底。
- `video_auto_cut/editing/direct_prompts.py` 只负责：
  - 读取这些文件
  - 在发送前补充少量运行时约束（例如章节上限、标题字数、字幕主题说明）
  - 组装 user message

## 文件

- `delete.md`
- `polish.md`
- `chapter.md`
- `highlight.md`

## 修改规则

- 如果要改这条链路的 prompt，先改这里。
- 这里的文案是 source of truth，不要再从代码、旧镜像、脚本或别的目录反向覆盖这里。
- 代码侧不应再内嵌同一份 prompt 正文，只能读取这里并补少量运行时参数。
- 新增 prompt 文件时，也要补齐 marker，保证运行时可解析。
