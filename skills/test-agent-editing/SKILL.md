---
name: test-agent-editing
description: Use when raw media or a Chinese talking-head ASR transcript contains retakes, false starts, immediate corrections, superseded lines, or no-speech placeholders and needs end-to-end cleanup into final Test subtitles and chapters.
---

# Test Agent Editing Skill

## Overview
这个 skill 是本项目口播字幕清理的顶层工作流。

适用场景是：用户录口播时经常口误、重说、说半句又重来、夹杂多余语气词，而且说错之后通常不会停机重录，而是直接顺着往下把同一个意思重新说一遍。目标不是保留录制过程，而是尽量只留下最终成片真正需要的表达，让用户不需要再为了这些返工痕迹手动二次剪辑。

这是一个“总任务”skill，而不只是机械按 1、2、3、4 顺序执行的路由器。虽然默认流程是 `asr-transcribe -> delete -> polish -> chapter`，但在执行过程中，只要你发现任何环节实现得不清楚、不完整、不够好，或者最终结果里还残留明显问题（包括需要二次修订的字词、ASR 错词、表达不顺、章节覆盖不稳、前一步判断明显失误），就应该直接回到对应步骤修正并重新产出，而不是等用户二次指出。

## When to Use
- 输入是音频、视频或 OSS 音频对象，需要从媒体开始端到端处理
- 输入是原始 ASR 字幕，需要端到端清理成最终 Test 字幕
- 录制内容是中文口播，存在明显返工链条、重说、补说、口误修正
- 需要同时交付清理后的字幕和最终章节

不要用于：
- 只做单一步骤的小修小补
- 与口播返工无关的普通文本润色
- 纯摘要任务

## Routing
- 输入是媒体文件，需要先生成原始字幕：用 `asr-transcribe`
- 只需要逐行删留判断：用 `delete`
- 只需要保留单行并润色表达：用 `polish`
- 只需要给最终保留字幕分章：用 `chapter`
- 需要端到端完成 Test 清理：用 `test-agent-editing`

## Required Sub-Skills
- **REQUIRED SUB-SKILL:** `asr-transcribe`
- **REQUIRED SUB-SKILL:** `delete`
- **REQUIRED SUB-SKILL:** `polish`
- **REQUIRED SUB-SKILL:** `chapter`

## Workflow
1. 如果起点是音频 / 视频 / OSS 音频对象，先调用 `asr-transcribe` skill，生成原始 `.srt` 与 `.test.json`。
2. 全文阅读原始字幕，识别口播返工链条：哪些是说错后的重说，哪些是没说完的残句，哪些是最终稳定版本。
3. 调用 `delete` skill，清理返工链条里应删除的旧版本、残句、无语音占位和明显无效噪声。
4. 调用 `polish` skill，只对保留下来的内容做逐行整理，让口播字幕自然、准确、适合直接进成片。
5. 调用 `chapter` skill，基于最终保留字幕做章节划分。
6. 最后做一次 end-to-end 复核：如果成片字幕里还残留明显“说错后又重说”的痕迹，或者章节覆盖不完整，或者还有明显 ASR 错词、错别字、用词不顺、需要二次修订的点，就回到对应步骤直接自我纠正。

中间产物标准：
- delete / polish 使用用户可读的逐行格式：`【time】句子` 或 `【time】<remove>句子`
- chapter 使用轻量章节格式：`【start-end】标题`

## Shortcuts Not Allowed
- 不要在只有媒体输入时跳过 `asr-transcribe`。
- 不要先 `polish` 再 `delete`。
- 不要在 `polish` 阶段偷偷删除内容或跨行合并。
- 不要在 delete 结果还不稳定时先分章。
- 不要为了“读起来更顺”而补充原文没有的新事实。
- 不要把返工链条误当成“正常重复强调”而整段保留。
- 不要明知某一步结果还有明显问题，却机械进入下一步并等用户回来补救。

## Quality Bar
最终结果要满足：
- 读起来像用户本来就应该这样顺畅地说完，而不是保留返工过程
- 不因为追求简洁而误删真正新增的信息
- 不因为追求自然就捏造事实
- 不把明显 ASR 错词、错别字、术语误识别、别扭用词留给用户二次手改
- 章节完整覆盖全部保留内容

## Final Review Checklist
- 是否还残留“前一句刚说完、后一句立刻重说一遍同一意思”的返工痕迹？
- 是否把没说完的半句、试探句、不稳定版本删掉了？
- 是否保留了真正新增的信息，而不是误删？
- polish 后是否只是整理表达，而没有改变事实？
- 是否还残留明显的 ASR 错词、错别字、术语错误或需要二次修订的字词？
- chapter 是否连续覆盖全部保留字幕？

## Red Flags
- “媒体我先不转录，直接猜字幕再 edit。”
- “我先把文本润顺，再回头删重复。”
- “这两句都差不多，先都留着吧。”
- “章节先分出来，后面再看要不要删。”
- “为了更自然，我顺手把没说出的信息补全了。”
- “这里看起来不太对，但先交给用户自己改吧。”
