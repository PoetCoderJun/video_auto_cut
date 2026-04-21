# direct-prompts

这个目录现在是当前 `delete / polish / chapter / highlight` 直连链路的**唯一运行时真相来源**。

## 运行时约定

- 运行时代码会直接读取这里的 markdown 文件。
- 每个 prompt 文件都必须包含一段：
  - `<!-- SYSTEM_PROMPT:START -->`
  - `<!-- SYSTEM_PROMPT:END -->`
- 两个 marker 之间的内容就是运行时真正发送给模型的 system prompt。
- `video_auto_cut/editing/direct_prompts.py` 只负责：
  - 读取这些文件
  - 注入少量动态占位符（例如章节上限、标题字数、字幕主题）
  - 组装 user message

## 占位符

- `chapter.md`
  - `{{MAX_CHAPTERS_RULE}}`
  - `{{TITLE_MAX_CHARS}}`
- `highlight.md`
  - `{{SUBTITLE_THEME_NOTE}}`

## 文件

- `delete.md`
- `polish.md`
- `chapter.md`
- `highlight.md`

## 修改规则

- 如果要改这条链路的 prompt，先改这里。
- 代码侧不应再内嵌对应 prompt 正文。
- 新增 prompt 文件时，也要补齐 marker，保证运行时可解析。
