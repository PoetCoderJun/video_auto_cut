---
name: subtitle-style-contract
description: Use when turning subtitle lines into directly usable Remotion + Tailwind v4 JSX blocks instead of abstract style discussion or JSON schema design.
---

# Subtitle Style Contract

## Task
主输入是**一个完整的轻量字幕文本文件**，按行提供整段字幕。

默认格式：
`【00:00:00.000-00:00:02.000】字幕文本`

也就是：
- 一行一条字幕
- 整个文件 = `【time】text` * N
- 按原顺序处理整份文件，不是只处理单独摘出来的几句

可选补充输入：
- `tokens`
- `label.badgeText`
- `label.emphasisSpans`

目标只有一个：
**针对每一句字幕，直接生成可粘贴的 Remotion + Tailwind v4 JSX 代码块。**

不讨论：
- ASR / 切句 / 时间轴
- JSON schema / 样式契约
- 完整主题系统 / 多方案设计分析

## Output
按输入文件中的原顺序逐句输出：

### `Line <line_id>`
- 最多一句简短说明，可省略
- 一个 `tsx` 代码块

代码块要求：
- 直接对应当前这一句字幕
- 使用 Remotion JSX
- 使用 Tailwind v4 `className`
- 可直接粘贴试验
- 高亮直接拆 `span`
- badge 直接写进 JSX
- 如需轻动画，可直接用 `useCurrentFrame()`、`spring()`、`interpolate()`

如果多句共享逻辑非常明显，最后可以补一个很短的共享 helper；否则不要输出 helper。

## Constraints
- 不要输出 JSON
- 不要输出长篇设计分析
- 不要输出多个备选方案
- 不要只给 class 名，不给 JSX
- 默认少解释，多代码
- 默认轻动效，不做夸张 TikTok 弹跳
