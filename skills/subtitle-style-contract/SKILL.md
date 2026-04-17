---
name: subtitle-style-contract
description: Use when designing subtitle styling for this project and you need a strict output contract that fixes goals, limits, and a Remotion-readable style spec instead of vague visual advice.
---

# Subtitle Style Contract

## Overview
这个 skill 用来约束字幕样式设计输出，不讨论 ASR、时间抽取、render pipeline 改造，只讨论：

1. 目标观感
2. 不允许越界的限制
3. 可发挥的空间
4. 一个 **Remotion 可直接消费** 的固定输出格式

它适用于：
- 你已经有字幕文本、token、label 数据
- 你要让另一个模型负责“字幕表现层设计”
- 你不想让模型只给抽象美术意见
- 你要保证输出可被工程直接接入

## When to Use
Use when:
- 用户在讨论字幕样式、字体高亮、组件化字幕、动态字幕表现
- 用户强调“边界”“约束”“输出格式”
- 用户提供字体列表，想做字体驱动的高亮样式
- 用户希望 Pi Agent 直接给出可实现的字幕样式 spec

Do NOT use when:
- 任务是 ASR 识别、时间轴抽取、字幕切分、token 回映射
- 任务是修复 Remotion 代码 bug
- 任务是泛泛讨论“更高级”“更像剪映开拍”但不要求固定格式

## Core Rule
禁止输出抽象审美建议。
禁止发散成完整模板系统、完整品牌系统、多 preset 系统，除非用户明确要求。

必须把回答收敛成：
1. 当前目标
2. 允许范围
3. 禁止范围
4. 字体在样式中的角色
5. 高亮规则
6. 少量动态组件规则
7. 固定 JSON 输出格式

## Scope Lock
默认只允许讨论这三层：
- `main_subtitle`
- `highlight`
- `dynamic_component`

如果用户没有明确要求，不要新增第四层。

## Default Assumptions
除非用户明确推翻，否则默认：
- 内容类型：知识口播 / 产品介绍 / 观点表达
- 第一阶段目标：**字体高亮优先**
- 允许少量动态组件，但不能太多
- 不是 TikTok/Karaoke 跟读字幕
- 也不是纯静态网页卡片
- 动态组件只服务重点信息，不抢主字幕

## Required Output Format
回答时必须严格使用以下 7 段，按顺序输出：

### 1. Focus
一句话说明当前这轮只解决什么。

### 2. Goal
明确目标观感，用 2–4 条 bullets。

### 3. Boundaries
分成两组：
- Must do
- Must not do

### 4. Font Role
必须回答：
- 字体控制什么
- 字体不控制什么

### 5. Highlight Rule
必须回答：
- 高亮目标是什么
- 高亮如何表现
- 高亮最多能覆盖到什么范围

### 6. Dynamic Component Rule
只允许少量组件，并且每个组件都必须说明：
- `type`
- `when`
- `strength`

### 7. Output Schema
必须输出一个 JSON 代码块。
这个 JSON 必须是给 Remotion/前端实现层使用的字幕样式契约。

## Remotion-Readable Output Contract
默认 JSON 必须长这样：

```json
{
  "subtitle_style": {
    "scope": "font-highlight-first",
    "layers": ["main_subtitle", "highlight", "dynamic_component"],
    "goal": {
      "feel": "professional-short-video-subtitle",
      "avoid": ["tiktok-bounce", "static-web-card"]
    },
    "font_role": {
      "source": "user_font_list",
      "controls": ["tone", "weight_feel", "keyword_identity", "contrast"],
      "does_not_control": ["timing_logic", "template_system", "animation_system"]
    },
    "highlight_rule": {
      "targets": ["keyword", "emotion_word", "number", "conclusion_phrase"],
      "max_highlight_segments_per_line": 3,
      "styles": {
        "font_swap": true,
        "weight_shift": true,
        "color_shift": true,
        "stroke": "optional-light",
        "background_fill": "optional-light"
      },
      "forbidden": [
        "full_line_highlight",
        "multi_line_spread",
        "highlight_turns_whole_subtitle_into_headline"
      ]
    },
    "dynamic_component_rule": {
      "allowed": [
        {
          "type": "badge",
          "when": "short_label_or_tag",
          "strength": "medium"
        },
        {
          "type": "keyword_chip",
          "when": "single_high_value_keyword",
          "strength": "medium-strong"
        },
        {
          "type": "floating_phrase_card",
          "when": "rare_detached_phrase",
          "strength": "medium"
        }
      ],
      "max_active_components_per_screen": 1,
      "motion_limit": "light_entry_only"
    }
  }
}
```

## Additional Rules
- 不要输出多个 schema 方案，让工程侧自行挑。
- 不要输出模糊字段如 `modern`, `cool`, `nicer` 而没有规则解释。
- 若用户给了字体列表，必须围绕字体列表组织风格，不要绕开字体重新发明完整 preset。
- 动态组件默认最多 1 个同屏活跃。
- 高亮默认只做词级或短语级，不做整句级轰炸。

## Common Mistakes
- 把“字体列表”问题回答成“完整字幕模板系统”
- 把“高亮”理解成整句全加粗
- 把“允许少量动态组件”扩张成满屏特效
- 没有输出 JSON schema
- 输出不能直接被工程消费的纯文案说明

## Build Next
当使用这个 skill 时，下一步默认是：
**基于用户提供的字体列表，生成一版符合上述 JSON schema 的字幕样式 spec，供 Remotion 渲染层直接读取。**
