---
name: subtitle-style-contract
description: Use when turning subtitle lines into directly usable Remotion + Tailwind v4 JSX blocks instead of abstract style discussion or JSON schema design.
---

# Subtitle Style Contract

## Overview
这个 skill 不再产出“样式契约 JSON”。

它的唯一目标是：
**针对用户给出的每一句字幕，直接生成可落地的 Remotion + Tailwind v4 代码块。**

适用场景：
- 已经有逐句字幕，想直接试样式
- 已经有 token / emphasis / badge 等标注，想直接变成 JSX
- 想让模型少讲抽象设计，多给可贴进工程的代码

不适用场景：
- ASR、切句、词级时间回映射
- 修 Remotion 运行时 bug
- 设计完整主题系统、preset 系统、品牌系统

## Core Rule
禁止输出长篇样式分析。
禁止先写一大段“目标 / 边界 / schema / layers / contract”再给代码。
禁止输出 JSON schema 让工程侧自己翻译。

默认做法是：
1. 读取输入字幕
2. 逐句判断最适合的视觉表现
3. 直接输出每一句对应的 Remotion + Tailwind v4 JSX 代码块

## Input Assumptions
除非用户明确推翻，否则默认输入可能包含这些字段：
- `line_id`
- `text`
- `tokens`
- `label.badgeText`
- `label.emphasisSpans`
- 可选字体列表
- 可选画面尺寸、横竖屏信息

如果部分字段缺失，不要停下来讨论 schema；
直接基于现有字段生成最稳妥的代码。

## Output Goal
输出必须让工程侧能直接拿去试，不需要再把抽象 spec 翻译一遍。

优先级：
1. 可直接粘贴
2. 每句独立可读
3. Tailwind v4 class 清晰
4. Remotion 结构明确
5. 少解释，多代码

## Required Output Format
回答时默认使用下面的结构：

### 1. Shared Notes
只允许 0-3 条短 bullet。
仅在确实有必要时说明：
- 共用字体
- 共用颜色基调
- 共用动画原则

如果没必要，就省略这一段。

### 2. Per-Line Blocks
对每一句字幕都输出以下内容，按顺序重复：

#### `Line <line_id>`
- 一句话说明这一句的表现意图，最长 1 句
- 一个 `tsx` 代码块

每个代码块必须：
- 直接对应当前这一句字幕
- 使用 Remotion JSX
- 使用 Tailwind v4 `className`
- 尽量完整到可直接粘贴试验
- 如需高亮，直接在 JSX 里拆 span，不要再输出抽象规则
- 如需 badge，直接把 badge 写出来
- 如需轻动画，可直接使用 Remotion 的 `interpolate()` / `spring()` / `useCurrentFrame()`

### 3. Optional Shared Helper
只有在多句重复逻辑非常明显时，才允许额外输出一个共享 helper。

这个 helper 必须：
- 是 `tsx` 代码块
- 足够短
- 真能减少重复

如果 helper 不是必须，就不要输出。

## Hard Constraints
- 不要输出 JSON。
- 不要输出“Focus / Goal / Boundaries / Font Role / Highlight Rule / Dynamic Component Rule”这类分析框架。
- 不要输出多个备选方案让工程自己挑。
- 不要把“逐句代码生成”重新退化成“设计说明文档”。
- 不要只写 class 名建议而不给 JSX。
- 不要依赖未声明的巨大外部样式系统。
- 除非用户要求，否则不要引入完整组件库抽象。

## Code Expectations
默认代码风格：
- `tsx`
- Remotion primitive 优先，例如 `AbsoluteFill`
- Tailwind v4 utility classes 直接写在 `className`
- 视觉风格偏短视频字幕，不要写成普通网页卡片
- 动效保持轻量，不做 TikTok 式过度弹跳

如果用户给了 token / emphasis 数据：
- 直接把高亮词拆成 `<span>`
- 高亮控制在词级或短语级
- 不要把整句都做成 headline

如果用户给了 badge 数据：
- 直接在当前句的 JSX 中输出 badge
- badge 是辅助信息，不要抢主字幕

## Preferred Thinking Pattern
对每一句字幕，默认按这个顺序思考，但不要把这套思考过程完整写出来：
1. 这一句的语义重心是什么
2. 哪些词需要高亮
3. 这一句适合纯字幕、badge 字幕，还是轻组件字幕
4. 最后直接写 JSX

## Common Mistakes
- 产出一份很长的样式 spec，却没有任何可运行代码
- 只给 Tailwind class token，不给 Remotion 结构
- 先谈十段抽象审美，再补一个很短的代码块
- 每句都依赖一个没有定义的大型模板系统
- 明明是逐句任务，却输出全局 preset 设计文档

## Build Next
当使用这个 skill 时，默认下一步是：
**基于用户提供的逐句字幕，逐句生成 Remotion + Tailwind v4 的 JSX 代码块，而不是生成 JSON 样式契约。**
