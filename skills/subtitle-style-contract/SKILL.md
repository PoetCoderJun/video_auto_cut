---
name: subtitle-style-contract
description: Use when converting a full timed subtitle text file into a minimal JSON file that marks per-line highlight words for later Remotion rendering.
---

# Subtitle Style Contract

## Task
输入是一整份轻量字幕文本，每行格式固定为：

`【00:00:00.000-00:00:02.000】字幕文本`

你的任务只有一个：
**为每一行字幕挑出最值得高亮的原文词语或短语。**

## Output
只输出一个 JSON 对象，不要输出 markdown，不要输出解释。

```json
{
  "version": "subtitle-style.v1",
  "subtitleTheme": "white",
  "captions": [
    {
      "start": "00:00:00.000",
      "end": "00:00:02.000",
      "text": "这里是字幕正文",
      "highlights": ["重点词", "结果词"]
    }
  ]
}
```

## Constraints
- 必须覆盖输入中的全部字幕行，顺序不变
- `start` / `end` / `text` 必须保留原值
- `subtitleTheme` 只允许 `white` 或 `black`
- `highlights` 只允许是字符串数组
- 每个高亮项必须是当前句子的**原文片段**，不能改写
- 每句优先返回 0-3 个高亮短语
- 优先高亮：结论、转折、对比、动作、结果、数字、产品名、关键词
- 没有明显重点时才返回 `[]`
- 不要输出颜色、字号、badge、解释、额外字段
