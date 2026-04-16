---
name: delete
description: Use when a Chinese talking-head Test transcript contains retakes, false starts, immediate re-says, superseded lines, correction chains, or < No Speech > / < Low Speech > placeholders and each line still needs a KEEP or REMOVE decision.
---

# Delete Skill

## Overview
Delete 只负责逐行判断 `KEEP` / `REMOVE`。

目标是清理口播录制过程里的“返工痕迹”：删掉被后文取代的旧表达、没说完就被后文重说的残句、意思已经被更完整版本覆盖的重复句、明显无效的试录、以及 `< Low Speech >` / `< No Speech >` 之类的占位行，同时保留剩余字幕的原始时轴和 line_id。这个技能不负责润色，也不负责分章。

判断标准不是“这两句像不像”，而是：
- 如果用户前面说错了、说半句、或者刚说完就马上用后一句重说了更准确/更完整的版本，那么前面的返工部分应该删掉。
- 删除后的目标是让用户尽量不需要再手动剪这段口播返工。

## When to Use
- 字幕里有重说、改口、后一行覆盖前一行的情况
- 字幕里出现“前一句刚说完，后一句立刻把它重新说一遍且意思更完整”的返工链条
- 存在没说完的半句、试探句、刚起头就被后面重说覆盖的内容
- 存在无语音占位、口误残句、明显应删除的噪声
- 存在 retake / false start / correction / superseded line 这类录制返工痕迹
- 需要一份覆盖全部 line_id 的删除决策表

不要用于：
- 改写保留文本
- 合并多行
- 生成章节

## Core Rules
1. 每个 `line_id` 都必须输出且只能输出一次。
2. 默认保守：不确定时优先 `KEEP`。
3. 只要后一句是在口播返工语境里对前一句的重说、补全、纠正或更完整复述，就应删除前一句返工内容。
4. 删除判断只改 action，不改字幕文案。
5. 保留行的时间、顺序、lineage 都不能动。
6. 目标是删掉“录制过程”，保留“最终想表达的内容”。

## Output Discipline
输出文件只保留用户可读的轻量行格式：

```text
【00:00:02.588-00:00:03.308】哟，这是俊。
【00:00:18.908-00:00:19.148】<remove>嗯，
```

- 每个输入字幕块都必须输出且只能输出一次
- 时间标签必须原样保留
- 删除时只是在正文前加 `<remove>`
- 不要输出 JSON，不要输出解释段落

## Quick Reference
| 场景 | 动作 |
| --- | --- |
| 后一句更完整、更准确，前一句只是口误、铺垫或返工版本 | 前一句 `REMOVE` |
| 前一句没说完，后一句立刻重新说了一版完整意思 | 前一句 `REMOVE` |
| 前一句和后一句语义接近，但后一句明显是最终稳定版本 | 前一句 `REMOVE` |
| `< Low Speech >` / `< No Speech >` / 明显无效占位 | `REMOVE` |
| 两句相近但信息并未真正覆盖 | 都 `KEEP` |
| 拿不准是否属于重复 | 先 `KEEP` |

## Common Mistakes
- 只按字面相似度删：不对，应该按“后句是否是前句的返工重说/补全”判断。
- 看到前一句已经是完整句就不敢删：如果后一句明显是在重说同一意思且更适合作为最终成片内容，前一句仍应删。
- 把真正新增信息也删掉：只有被后文覆盖的返工部分能删，新增信息必须保留。
- 在 delete 阶段顺手改写句子内容：不允许，delete 只决定是否加 `<remove>`。
- 在 delete 阶段顺手润色：禁止。
- 漏掉某个 `line_id`：这是硬错误。

## Red Flags
- 因为“两句都像完整句”就不敢删除前一句。
- 因为“字面不完全一样”就忽略明显的返工重说关系。
- 看到相邻句很像就顺手改写文案，而不是只做 `KEEP` / `REMOVE`。
