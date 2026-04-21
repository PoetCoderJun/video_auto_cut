# chapter direct prompt mirror

> Runtime source of truth: `video_auto_cut/editing/direct_prompts.py`
> This file is documentation only.

## Input

只包含保留字幕的 block 文本：`【block_index】正文`

## Output

章节文本：`【start-end】标题` 或 `【start】标题`

## Prompt mirror

- 只做 chapter，不改字幕正文。
- 输出必须逐行使用 `【start-end】标题` 或 `【start】标题` 格式。
- 所有 block_range 必须按顺序连续覆盖全部 block，不能空洞、不能重叠、不能跳号、不能越界。
- 章节数受调用方传入的 `max_chapters` 约束控制。
- 标题尽量简短。
- 只有出现明确话题/阶段切换时才新开章节。
- 寒暄、过渡句、重复补充、没有实质新内容的短段落必须并入相邻章节。
- 没有必要时宁少勿多，优先合并而不是拆碎。
- 不要输出 markdown，不要输出解释，不要输出编号，只输出最终章节文本。
