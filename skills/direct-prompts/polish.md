# polish direct prompt mirror

> Runtime source of truth: `video_auto_cut/editing/direct_prompts.py`
> This file is documentation only.

## Input

仅包含当前保留行，格式：`行号<TAB>正文`

## Output

只输出需要改动的行，格式：`行号<TAB>改后正文`

如果某行应被清空/删除，输出：`行号<TAB><empty>`

## Prompt mirror

- 只输出需要改动的行；未改动的行不要输出。
- 每个输出行格式固定为：`行号<TAB>改后正文`。
- 如果某行应被清空/删除（例如整行只是“嗯/啊/呃”这类无信息语气词），输出：`行号<TAB><empty>`。
- 只能做词语级纠错、顺句、ASR 错词修正和轻微措辞整理。
- 尤其要主动修复明显的 ASR 错词、同音误识别、英文/专有名词误识别。
- 不要扩写事实，不要改结论，不要跨行借内容。
- 每行最多对应一个输出行，不能重复输出同一行号。
- 不要输出 markdown，不要输出解释，不要输出未修改的行。
- 除问句外，去掉行尾冗余标点。
