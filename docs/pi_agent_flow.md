# PI Agent Flow

## Current Main Flow

The main Step1 auto-edit path lives in [`video_auto_cut/editing/auto_edit.py`](/Users/huzujun/Desktop/video_auto_cut/video_auto_cut/editing/auto_edit.py).

Current flow:

1. Load ASR segments from the input `.srt`.
2. Split the input into overlapping windows with `build_chunk_windows()`.
3. Run `PiAgentRemoveLoop` on each window to decide which lines are `KEEP` or `REMOVE`.
4. Run `PiAgentBoundaryReview` between adjacent windows so overlap lines use one consistent decision.
5. Collect the final core decisions in original timeline order.
6. Build merged keep-groups with `build_merged_groups()`.
   These groups are the first place where short neighboring kept lines are combined into contextual chunks.
7. Run `PiAgentChunkPolishLoop` on merged groups.
   This is now the main rewrite stage.
8. Rebuild final subtitles:
   Removed lines stay as `<<REMOVE>> ...` markers for Step1 UI.
   Kept groups become rewritten merged subtitles.
9. Derive `step1_lines` from the merged rewritten subtitles.
10. Persist:
   - `.optimized.srt`
   - `.optimized.raw.srt`
   - `.step1.json`
   - debug payloads

## Current Skills

### 1. Remove Skill

File: [`video_auto_cut/editing/pi_agent_remove.py`](/Users/huzujun/Desktop/video_auto_cut/video_auto_cut/editing/pi_agent_remove.py)

Purpose:
- Remove earlier wrong takes
- Remove repeated meaning
- Keep the final intended spoken version

Output:
- `LineDecision` list with `KEEP` / `REMOVE`

### 2. Boundary Review Skill

File: [`video_auto_cut/editing/pi_agent_boundary.py`](/Users/huzujun/Desktop/video_auto_cut/video_auto_cut/editing/pi_agent_boundary.py)

Purpose:
- Reconcile overlapping chunk decisions
- Avoid two adjacent windows disagreeing on the same line

Output:
- Revised `ChunkExecutionState` values

### 3. Chunk Rewrite Skill

File: [`video_auto_cut/editing/pi_agent_polish.py`](/Users/huzujun/Desktop/video_auto_cut/video_auto_cut/editing/pi_agent_polish.py)

Class:
- `PiAgentChunkPolishLoop`

Purpose:
- Rewrite merged keep-groups instead of single lines
- Use surrounding context inside each merged chunk
- Boldly repair likely ASR errors, broken phrases, and incomplete expressions
- Preserve original facts, numbers, and policy meaning

Internal sub-skills:
- `draft`: produce first full chunk rewrite
- `critique`: detect ASR leftovers, bad sentences, or over-invention
- `revise`: regenerate a complete corrected chunk set when critique says revision is needed

Output:
- Rewritten `MergedGroup` list

## Legacy Skill Still Present

File: [`video_auto_cut/editing/pi_agent_polish.py`](/Users/huzujun/Desktop/video_auto_cut/video_auto_cut/editing/pi_agent_polish.py)

Class:
- `PiAgentPolishLoop`

Status:
- Still exists in code and tests
- Not used by the current main `AutoEdit._auto_edit_segments()` path

Purpose:
- Historical line-by-line polish loop

## Why The Main Path Changed

The old line-level polish path had two structural weaknesses:

1. The model only saw one line at a time, so it could not reliably infer missing words or repair broken ASR fragments.
2. Short fragmented subtitles were being polished before they had enough context.

The new path fixes that by:

- removing first
- merging kept short lines into contextual groups
- rewriting the merged groups as chunk-level oral-script text

## Files To Read

- Main orchestration:
  [`video_auto_cut/editing/auto_edit.py`](/Users/huzujun/Desktop/video_auto_cut/video_auto_cut/editing/auto_edit.py)
- Group building:
  [`video_auto_cut/editing/pi_agent_merge.py`](/Users/huzujun/Desktop/video_auto_cut/video_auto_cut/editing/pi_agent_merge.py)
- Chunk rewrite loop:
  [`video_auto_cut/editing/pi_agent_polish.py`](/Users/huzujun/Desktop/video_auto_cut/video_auto_cut/editing/pi_agent_polish.py)
- Remove loop:
  [`video_auto_cut/editing/pi_agent_remove.py`](/Users/huzujun/Desktop/video_auto_cut/video_auto_cut/editing/pi_agent_remove.py)
- Boundary review:
  [`video_auto_cut/editing/pi_agent_boundary.py`](/Users/huzujun/Desktop/video_auto_cut/video_auto_cut/editing/pi_agent_boundary.py)
