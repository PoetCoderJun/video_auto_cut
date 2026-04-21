# review direct prompt mirror

> Runtime source of truth: `video_auto_cut/editing/direct_prompts.py`
> This file is documentation only.

## Purpose

在 delete / polish / chapter / highlight 完成之后，对最终产物做一次独立质量复核。

## Reviewer model

运行时固定交叉验证模型：`qwen3.6-max-preview`。

## Review focus

- delete 是否保留了更早返工版，却删除了更晚、更完整的版本。
- 是否残留明显半句、起手残片、返工铺垫句。
- polish 是否残留明显 ASR 错词、同音误识别、英文/专有名词误识别。
- chapter 是否过碎、标题是否过长或不准。
- highlight 是否过多、过长、过整句，或没抓到真正关键的词。

## Output shape

纯文本审稿结论，包含：
- `总评：通过/不通过`
- `关键问题：`
- `证据：`
- `建议：`
