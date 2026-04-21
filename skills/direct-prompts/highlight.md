# highlight direct prompt mirror

> Runtime source of truth: `video_auto_cut/editing/direct_prompts.py`
> This file is documentation only.

## Input

`行号<TAB>正文`

## Output

只输出需要高亮的行：
- `行号<TAB>高亮词1`
- `行号<TAB>高亮词1|高亮词2`

## Prompt mirror

- 只输出纯文本，不要输出 JSON，不要输出 markdown，不要输出解释。
- 只输出有高亮的行；没有高亮的行不要输出。
- 每个高亮词必须是该行正文里的原文片段，不能改写。
- 每行最多 2 个高亮词，而且优先只给 1 个。
- 只高亮少量真正关键的词，不要高亮整句、长短语、普通修饰词、礼貌词或上下文已经明显的内容。
- 优先高亮：数字、专有名词、政策关键词、强结论词、强对比词、动作结果词。
- 如果没有明显值得强调的关键词，就不要输出该行。
