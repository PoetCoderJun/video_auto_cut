---
name: subtitle-style-contract
description: Use when converting a full timed subtitle text file into a compact JSON file that marks per-line highlight words for later Remotion rendering.
---

# Subtitle Style Contract

## Task
主输入是**一个完整的轻量字幕文本文件**。

默认格式：
`【00:00:00.000-00:00:02.000】字幕文本`

目标只有一个：
**输出一个 JSON 文件，保留每句时间和文本，并标出需要高亮的词语。**

不讨论：
- ASR / 切句 / 时间轴
- JSX / tsx 代码块
- 多套样式方案

## Output
只输出一个 JSON 对象，不要输出 markdown，不要输出解释。

固定格式：

```json
{
  "version": "subtitle-render.v1",
  "subtitleTheme": "black",
  "captions": [
    {
      "start": "00:00:00.000",
      "end": "00:00:02.000",
      "text": "这里是字幕正文",
      "label": {
        "highlights": [
          {
            "text": "关键词",
            "color": "#22c55e",
            "fontScale": 1.18
          }
        ]
      }
    }
  ]
}
```

## Constraints
- 必须覆盖输入文件中的全部字幕行，顺序不变
- `start` / `end` 必须保留原时间
- `text` 必须保留原句子
- 只允许两种 `subtitleTheme`：`black` 或 `white`
- `label.highlights` 可以为空，但字段含义必须明确
- 每个高亮项只输出：
  - `text`
  - `color`
  - `fontScale`
- 高亮词默认是词级或短语级，不要整句全高亮
