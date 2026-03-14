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
  state.json
  input/
    source.mp4
  step1/
    source.srt
    source.optimized.srt
    source.optimized.step1.json
    draft_step1.srt
    draft_step1.json
    review.receipt.json
    final_step1.srt
    final_step1.json
  step2/
    cut.srt
    topics.json
    draft_topics.json
    review.receipt.json
    final_topics.json
  render/
    cut.srt
    output.mp4
```

If the repo already has a stronger existing layout, preserve that layout instead of inventing a new one.

## Required agent inputs

- `input_video_path`

`output_video_path` is optional:

- use the user-provided path when given
- otherwise default to `<current working directory>/<input_stem>_cut.mp4`
- tell the user the inferred default path once instead of asking them to repeat it

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
- `draft_step1.srt`
- `draft_step1.json`
- human-confirmed `final_step1.srt`
- human-confirmed `final_step1.json`

Human gate:

- the agent must stop after generating step1 artifacts
- the human may directly edit text, mark removals, or approve as-is
- the workflow may resume only after an explicit review receipt is recorded for the current draft

### Stage 2

Input:

- human-confirmed `final_step1.srt`

Core action:

- build `cut.srt`
- run topic segmentation
- normalize chapter coverage

Outputs:

- generated `topics.json`
- editable `draft_topics.json`
- human-confirmed `final_topics.json`

Human gate:

- the agent must stop after generating step2 artifacts
- the human may rename chapters, adjust boundaries, or approve as-is
- the workflow may resume only after an explicit review receipt is recorded for the current draft

## Review receipt contract

Each review gate should leave behind a small receipt file so the workflow can resume durably and auditably.

Recommended fields:

- `stage`
- `action`
- `source`
- `reviewed_path`
- `reviewed_at`

Valid actions:

- `approve`
- `edit`

The receipt is the hard proof that a human actually reviewed the current draft.
`next` or any resume-style entrypoint should refuse to advance if the current stage has no valid receipt.

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

## Workflow entrypoint

This repo now includes:

`scripts/run_human_loop_pipeline.py`

Supported commands:

1. `next` advances the workflow according to current state:
   - first call generates Step1 draft artifacts
   - after Step1 approval has already been recorded, it advances into Step2
   - after Step2 approval has already been recorded, it renders the final output
2. `run` generates artifacts until the next human gate, then exits cleanly.
3. `approve-step1` records the human-confirmed Step1 result.
4. `approve-step2` records the human-confirmed Step2 result.
5. `render` produces the final output video.
6. `status` prints the current artifact-root state.

For agent-driven usage, prefer this posture:

1. Start with `run` or `next` to reach the next gate.
2. When the human responds, convert that response into an explicit approval or edited artifact for the current stage.
3. Only then call `approve-step1`, `approve-step2`, or resume with `next`.

The top-level user experience should still feel like one skill.
The lower-level commands exist to preserve durable state and strict Human-in-the-Loop semantics.
