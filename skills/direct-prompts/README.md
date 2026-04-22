# direct-prompts

这个目录是当前 `delete / polish / chapter / highlight` 直连链路的**唯一运行时真相来源**。

这里的 prompt 以 **`skills/direct-prompts/` 目录里原始手写文件** 为准。
这也包括较早历史里那版手写的 `Overview / Prompt mirror` 结构：运行时代码会直接读取这些文件，并兼容旧格式解析，不允许再把代码里的 prompt 文案反向回填覆盖这里。

## 运行时约定

- 运行时代码会直接读取这里的 markdown 文件。
- prompt 文件允许两种来源格式，都会被直接当作运行时真源：
  - 新格式：包含 `<!-- SYSTEM_PROMPT:START --> ... <!-- SYSTEM_PROMPT:END -->`
  - 旧格式：手写的 markdown 文档结构（如 `Overview / Input / Output / Prompt mirror`）
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
- 新增 prompt 文件时，可以继续用旧版文档结构，也可以用 marker 新格式；但无论哪种，目录内文件本身才是唯一真相。
