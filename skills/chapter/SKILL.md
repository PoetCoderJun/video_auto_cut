---
name: chapter
description: Use when final kept Test subtitle lines are ready and need short chapter titles with contiguous full block coverage for Test preview, export, or navigation.
---

# Chapter Skill

## Overview
Chapter 只负责给最终保留字幕分章并命名。

目标是基于已经确认的 Test 行，输出连续、无空洞、无重叠的 `block_range`，并给每段起一个简短标题。这个技能不负责删句，也不负责润色。

这里的 `block_range` 不是原始 `line_id`，而是保留后的连续 block 序号范围。  
如果最终保留了 63 段字幕，那么所有章节必须把 `1..63` 连续完整覆盖。

## When to Use
- delete 和 polish 已完成
- 需要给最终字幕生成章节标题与范围
- 需要保证章节覆盖全部保留 block，方便 Test 预览和导出
- 需要做导航标题，而不是长摘要、完整口播句子或解释文案

不要用于：
- 修改字幕正文
- 重新判断删留
- 输出长摘要或解释文案

## Core Rules
1. 章节必须按顺序连续覆盖全部保留 block。
2. 不允许空洞、重叠、跳号。
3. 每个 `block_range` 都必须表示某一段连续范围，例如 `1-5`、`6-14`。
4. 标题要短，优先概括主题，不写成长句。
5. 章节标题服务于导航，不是复述字幕全文。
6. 只输出章节结构，不改字幕行内容。

## Output Discipline
输出文件使用轻量章节格式：

```text
【1-3】开场
【4-8】变化一
```

- 每一行表示一个章节
- `block_range` 使用连续区间
- 必须连续覆盖全部保留 block
- 不要输出 JSON，不要输出解释文本

## Quick Reference
| 场景 | 动作 |
| --- | --- |
| 同一主题连续展开 | 放在同一章 |
| 话题明显切换 | 开新章 |
| 标题太像完整句子 | 再压缩 |
| 无法覆盖全部 block | 说明当前分章方案不合格，需重做 |
| `block_range` 写成原始 line_id | 错误，必须改成保留 block 的连续序号 |

## Common Mistakes
- 漏掉中间 block：不允许。
- 章节互相重叠：不允许。
- 标题写成一句完整口播：过长，应压缩成主题词。
- 把 `block_range` 写成原始 `line_id` 范围：不允许，必须按保留后的 block 序号全覆盖。
