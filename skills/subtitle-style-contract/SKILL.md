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

默认要**主动判断**高亮，不要保守平均分配。高亮不是装饰，而是提取这一句里最值得看的信息。

## Highlight Decision
- 优先高亮：语气落点、结论信息、对比关系、动作信息、数字结果
- 语气落点：强判断、转折后的态度、带结论感的收束词
- 结论信息：最终判断、核心观点、明确答案
- 对比关系：前后反差、比较结果、取舍方向
- 动作信息：关键动作、执行建议、命令、变化行为
- 数字结果：金额、比例、时长、数量、涨跌、结果值
- 如果一句里同时有多个候选，先选最能改变理解的那一个，再补 0-2 个辅助短语
- 不要用抽象标签、badge、摘要词去代替正文高亮；优先直接高亮原句里的词或短语

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
- `label.highlights` 可以为空，但只在这句没有明确高亮价值时为空
- 高亮判断不要保守。只要一句里存在明显的语气重音、结论词、转折词、对比词、动作词、数字结果，就应该主动标出来。
- 每句优先高亮 1-3 个真正有信息密度或语气张力的短语；不要机械平均分配，也不要因为犹豫而全部留空。
- 优先高亮：
  - 结论 / 判断
  - 对比 / 转折
  - 动作 / 结果
  - 数字 / 产品名 / 关键词
- 如果一句没有明显重点，才允许 `highlights: []`
- 每个高亮项只输出：
  - `text`
  - `color`
  - `fontScale`
- `text` 必须是原句里的原文片段，不能改写
- `fontScale` 默认用明显变化，不要太保守；常用范围 `1.14 - 1.32`
- 高亮词默认是词级或短语级，不要整句全高亮
- 对纯连接词、寒暄词、铺垫词保持克制，不要为了“有高亮”而硬标
