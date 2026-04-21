# review direct prompt mirror

> Runtime source of truth: `video_auto_cut/editing/direct_prompts.py`
> This file is documentation only.

## Purpose

在 auto_edit 主链路的 delete / polish 完成之后，对最终稿做一次独立质量复核。

## Merged overview

- `delete` 的目标是清理口播录制过程里的返工痕迹：删掉被后文取代的旧表达、没说完就被后文重说的残句、被更完整版本覆盖的重复句，以及明显无效的占位和噪声，同时保留剩余字幕的原始时轴和 line_id。
- `polish` 的目标是只在已经保留的字幕行上做轻量整理：让口播字幕更顺、更自然，但尽量以词语级修正为主，优先修正 ASR 错词、同音误识别、专有名词误识别和明显别扭的说法，同时不改变事实、删留结果和单行边界。
- 所以 review 审的不是“成品顺不顺”，而是 delete 有没有删干净录制过程、polish 有没有在不越界的前提下把保留内容修顺。

## Reviewer model

运行时固定交叉验证模型：`qwen3.6-max-preview`。

## Review focus

### Delete 标准

- 是否真正做到删前留后：后一句更完整、更准确、更最终时，前一句应被删掉。
- 是否按“重复语义”而不是只按字面相似审查返工簇。
- 最终稿里是否仍残留半句、起手残片、返工铺垫句、重复版本、`< No Speech >` / `< Low Speech >` 或其他无意义噪声。
- 是否出现删错方向：把后句删了、把前句留了。

### Polish 标准

- 是否主动修复了 ASR 错词、同音误识别、英文/专有名词误识别与明显别扭的说法。
- 是否清掉了无信息语气词、连接残片和不该留在成片里的口语残留。
- 是否只做轻量整理，而没有跨行借内容、补新事实、改判断、改结论。
- 是否出现“修过头”：把原本应该保留的新信息抹掉，或把语义越修越偏。

## Output shape

纯文本审稿结论，包含：
- `总评：通过/不通过`
- `关键问题：`
- `证据：`
- `建议：`
