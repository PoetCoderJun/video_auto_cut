# review direct prompt mirror

> Runtime source of truth: `video_auto_cut/editing/direct_prompts.py`
> This file is documentation only.

## Purpose

在 auto_edit 主链路的 delete / polish 完成之后，对最终稿做一次独立质量复核。

## Reviewer model

运行时固定交叉验证模型：`qwen3.6-max-preview`。

## Review focus

- delete 是否真正删掉了录制返工过程，做到删前留后，而不是保留更早、更差的返工版。
- 最终稿里是否还残留明显半句、起手残片、返工铺垫句、重复语义或无意义噪声。
- polish 是否修复了 ASR 错词、同音误识别、英文/专有名词误识别与明显别扭的说法。
- polish 是否过度改写，导致事实、判断、结论或原本应该保留的新信息被改坏。

## Output shape

纯文本审稿结论，包含：
- `总评：通过/不通过`
- `关键问题：`
- `证据：`
- `建议：`
