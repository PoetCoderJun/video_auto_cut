# ASR Boundary Layering Plan

**Date:** 2026-04-15  
**Scope:** Test ASR segmentation, Test delete/polish input units, final subtitle display units  
**Goal:** Separate recognition boundaries, editing boundaries, and display boundaries so the system can both expose retake artifacts for AI deletion and produce readable final subtitles.

---

## 1. Problem Statement

The current Test path effectively uses one boundary system for two different jobs:

1. expose minimal editable units for `delete`
2. produce final subtitles for preview/export

These goals conflict.

For editing, short isolated fragments can be useful:

- `嗯，`
- `首先，`
- `第三就是，`
- half-sentences from false starts / retakes

For display, those same fragments are often undesirable.

Because `polish` explicitly does not merge lines, the current system has no later stage that can convert editing-friendly boundaries into display-friendly boundaries.

---

## 2. Current Pipeline Reality

Current pipeline:

1. ASR returns sentence rows and optional word timestamps.
2. Local ASR post-process further splits into smaller segments.
3. `delete` decides KEEP / REMOVE per segment.
4. `polish` rewrites each kept line independently.
5. `chapter` groups final kept lines.
6. `optimized.srt` is built directly from Test lines.

Relevant paths:

- `video_auto_cut/asr/dashscope_filetrans.py`
- `video_auto_cut/asr/transcribe.py`
- `video_auto_cut/editing/auto_edit.py`
- `video_auto_cut/pi_agent_runner.py`
- `skills/delete/SKILL.md`
- `skills/polish/SKILL.md`
- `skills/chapter/SKILL.md`
- `web_api/services/test.py`

Important constraint:

- `delete` wants small, explicit units.
- `polish` cannot cross line boundaries.
- there is currently no post-edit recut stage for final display.

So the present segmentation is implicitly an **editing segmentation**, not a final display segmentation.

---

## 3. First-Principles Model

The system should explicitly own three boundary layers.

## 3.1 Recognition Boundary

Owned by cloud ASR.

Purpose:

- recognize text correctly
- return punctuation
- return word timestamps
- provide initial sentence-level structure

Primary controls:

- `DASHSCOPE_ASR_ENABLE_WORDS`
- `DASHSCOPE_ASR_LANGUAGE` when single-language is known
- `DASHSCOPE_ASR_ENABLE_ITN`
- `DASHSCOPE_ASR_TEXT`
- `DASHSCOPE_ASR_CHANNEL_IDS`

This layer does **not** need to solve subtitle readability.

## 3.2 Editing Boundary

Owned by local ASR post-process before `delete`.

Purpose:

- expose retake chains
- expose filler/hesitation markers
- expose incomplete starts
- expose superseded fragments
- keep units small enough for reliable KEEP / REMOVE decisions

This layer should bias toward:

- over-exposing removable fragments
- preserving temporal locality
- keeping correction chains visible

This is the right place for:

- `嗯，`
- `首先，`
- `那个，`
- false-start residues
- `< No Speech >`

These are not bugs here. They are editing signals.

## 3.3 Display Boundary

Owned by a new stage after delete/polish and before final export / preview.

Purpose:

- produce readable subtitles
- suppress isolated residual fragments
- maintain good reading rhythm
- avoid over-fragmentation in final output

This layer should operate only on kept/polished content.

It should **not** try to rediscover retake chains. That work is already done.

---

## 4. Verdict on Current Segmentation State

## 4.1 Recognition Layer

Acceptable baseline.

Using `enable_words=true` is correct because it gives the local system the timestamp granularity it needs.

## 4.2 Editing Layer

Current state: **directionally correct, but slightly over-aggressive in a few patterns.**

Evidence from sample `test_data/media/1.asr.wav`:

- raw cloud sentence count: `20`
- local split count: `63`
- changed raw rows: `18`

Observed good behavior:

- long spoken clauses are split into AI-manageable units
- retake chains are exposed instead of buried inside long sentences
- filler fragments like `首先，` and `嗯，` are visible to `delete`

Observed costs:

- some isolated fragments are probably smaller than needed even for editing
- some clauses split at points that do not add much delete value
- current `word_max_segment_s` protection is not reliably enforcing intended behavior

Interpretation:

- **not suitable as final display segmentation**
- **mostly suitable as editing segmentation**
- should be refined, not discarded

## 4.3 Display Layer

Missing.

This is the core architectural gap.

The project currently asks the editing layer to double as the display layer, which creates the perceived contradiction.

---

## 5. Proposed Architecture Change

Keep the current ASR/local split stage as the producer of **editing units**, then add one new stage:

```text
ASR recognition
-> local editing split
-> delete
-> polish
-> display recut
-> final preview/export SRT
```

### 5.1 Editing split should remain before delete

Reason:

- delete skill explicitly benefits from exposed retake / filler / false-start units
- shrinking those units too early would hide removable artifacts inside longer lines

### 5.2 Display recut should happen after polish

Reason:

- only kept lines should participate
- polished text is a better source for display-friendly re-segmentation
- delete has already removed obvious junk, so display recut can optimize for readability only

### 5.3 Chapter should run on final kept block structure

Preferred end state:

- internal Test editing can still use editing units
- final `chapter` input should be based on kept blocks after delete/polish
- display recut may either:
  - preserve block identity for chapter/navigation, or
  - create a separate export-only display timeline

For minimal disruption, initial implementation should keep chapter ownership on Test kept blocks and apply display recut only to export/preview text rows.

---

## 6. Recommended Ownership of Existing Parameters

## 6.1 Recognition layer

- `DASHSCOPE_ASR_ENABLE_WORDS`
- `DASHSCOPE_ASR_LANGUAGE`
- `DASHSCOPE_ASR_ENABLE_ITN`
- `DASHSCOPE_ASR_TEXT`
- `DASHSCOPE_ASR_CHANNEL_IDS`

## 6.2 Editing layer

- `ASR_WORD_SPLIT_ENABLED`
- `ASR_WORD_SPLIT_ON_COMMA`
- `ASR_WORD_SPLIT_COMMA_PAUSE_S`
- `ASR_WORD_SPLIT_MIN_CHARS`
- `ASR_WORD_VAD_GAP_S`
- `ASR_WORD_MAX_SEGMENT_S`
- `ASR_SENTENCE_RULE_WITH_PUNC`
- `ASR_INSERT_NO_SPEECH`
- `ASR_INSERT_HEAD_NO_SPEECH`

## 6.3 Display layer

New parameter family should be introduced later, for example:

- `DISPLAY_SUBTITLE_MAX_CHARS`
- `DISPLAY_SUBTITLE_MAX_SECONDS`
- `DISPLAY_SUBTITLE_MIN_SECONDS`
- `DISPLAY_SUBTITLE_ALLOW_COMMA_SPLIT`

These should not reuse editing-layer names.

---

## 7. Assessment of Current Editing-Split Parameters

### `ASR_SENTENCE_RULE_WITH_PUNC=1`

Low importance on the default path when word timestamps are enabled.

### `ASR_WORD_SPLIT_ENABLED=1`

Correct. Should stay on.

### `ASR_WORD_SPLIT_ON_COMMA=1`

Correct for editing segmentation. Keep on.

### `ASR_WORD_SPLIT_COMMA_PAUSE_S=0.4`

Reasonable for editing segmentation.

### `ASR_WORD_SPLIT_MIN_CHARS=12`

Acceptable but aggressive. Not obviously wrong for editing segmentation.

### `ASR_WORD_VAD_GAP_S=1.0`

Reasonable.

### `ASR_WORD_MAX_SEGMENT_S=8.0`

Intended direction is correct, but implementation behavior should be fixed so it becomes a real guardrail.

### `ASR_INSERT_NO_SPEECH=1`

Useful for delete-stage cleanup.

### `ASR_INSERT_HEAD_NO_SPEECH=1`

Useful for delete-stage cleanup.

Overall verdict:

- **for editing segmentation:** mostly acceptable today
- **for final display segmentation:** not acceptable as the sole boundary system

---

## 8. Minimal-Change Implementation Path

### Phase 1

Do not weaken current editing split much.

Reason:

- weakening it now would reduce delete quality before a display layer exists

Work:

- keep current editing split behavior broadly intact
- fix `word_max_segment_s` so it actually acts as a guardrail
- document editing split as intentional

### Phase 2

Add display recut after delete/polish.

Work:

- build final display rows from kept/polished Test lines
- export preview/final SRT from display rows
- preserve Test line/block structure for editing + chapters

### Phase 3

Tune editing split only after display layer exists.

Work:

- evaluate whether some fragments are still too small even for delete
- shrink or expand editing units based on delete accuracy, not display aesthetics

---

## 9. Recommendation

Do **not** treat the current segmentation as globally wrong.

Treat it as:

- reasonably good **editing segmentation**
- insufficient **display segmentation**

The main architectural action is not “make the current split less碎” in isolation.

The main action is:

**introduce a post-edit display recut layer and stop forcing one segmentation to satisfy both delete and final subtitle readability.**
