# Workflow Contract

## Intent

This skill wraps the repo's existing AI pipeline as a single human-in-the-loop agent workflow.

The goal is not to expose every internal module as a separate top-level skill.
The goal is to give Codex, Claude Code, or a PI agent one stable playbook for:

1. taking a source video path
2. generating step1 review artifacts
3. pausing for human confirmation
4. generating step2 review artifacts
5. pausing for human confirmation
6. producing the final cut video

## Recommended artifact layout

Use a stable artifact root per input video, for example:

```text
<artifact_root>/
  input/
    source.mp4
  step1/
    source.srt
    source.optimized.srt
    source.optimized.raw.srt
    source.optimized.step1.json
    final_step1.srt
    final_step1.json
  step2/
    cut.srt
    topics.json
    final_topics.json
  render/
    cut.srt
    output.mp4
```

If the repo already has a stronger existing layout, preserve that layout instead of inventing a new one.

## Required agent inputs

- `input_video_path`
- `output_video_path`

Optional runtime inputs:

- `artifact_root`
- `llm_base_url`
- `llm_model`
- `llm_api_key`
- ASR provider settings
- `bitrate`
- `cut_merge_gap`

## Stage contract

### Stage 1

Input:

- source video or extracted audio

Core action:

- transcribe
- run auto-edit remove/polish flow

Outputs:

- `.srt`
- `.optimized.srt`
- `.step1.json`
- human-confirmed `final_step1.srt`
- human-confirmed `final_step1.json`

Human gate:

- the agent must stop after generating step1 artifacts
- the human may directly edit text, mark removals, or approve as-is

### Stage 2

Input:

- human-confirmed `final_step1.srt`

Core action:

- build `cut.srt`
- run topic segmentation
- normalize chapter coverage

Outputs:

- generated `topics.json`
- human-confirmed `final_topics.json`

Human gate:

- the agent must stop after generating step2 artifacts
- the human may rename chapters, adjust boundaries, or approve as-is

### Final cut

Input:

- original video
- human-confirmed step1 and step2 artifacts

Core action:

- build the cut timeline from confirmed subtitles
- export final cut video

Output:

- final video at the requested `output_video_path`

## Where loop and chunk rules should live

Do not duplicate detailed loop/chunk prompts inside `SKILL.md`.

Keep them in repo code or scripts because they are implementation rules, not top-level usage rules.
This repo already has loop/chunk behavior inside the auto-edit system, including:

- chunk windowing
- overlap handling
- remove loop
- critique/revise polish loop
- boundary review
- merged group rewrite

The top-level skill should instruct the agent to reuse those modules.

If a dedicated wrapper is later added, the wrapper should own:

- checkpoint creation
- artifact path resolution
- stage resume behavior
- human approval status recording

## Recommended future wrapper

If you want this skill to be robust for repeated use, add one script such as:

`scripts/run_human_loop_pipeline.py`

That wrapper should accept:

```text
--input-video
--output-video
--artifact-root
--resume-from step1|step2|render
--approve-step1
--approve-step2
```

Suggested behavior:

1. `run` mode generates artifacts until the next human gate, then exits cleanly.
2. `approve-step1` tells the wrapper to continue from confirmed step1 artifacts.
3. `approve-step2` tells the wrapper to continue from confirmed step2 artifacts.
4. `render` produces the final output video.

This keeps the skill concise while making execution deterministic.
